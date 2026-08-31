#!/usr/bin/env python3
"""Re-apply the scorer to already-audited calls. No LLM calls, no cost.

The model's per-sub-point judgements and evidence are stored inside
`call_quality_audit`, and every score, gate and tier is computed separately in
call_quality.py. So a change to a *scoring rule* — whether CM-5 auto-zeroes,
whether a criterion may be N/A, a duration cut-off — can be replayed over stored
data for free. Only a change to what the model should *look for* needs a re-run.

Usage:
    python scripts/rescore_audits.py --dry-run     # show what would change
    python scripts/rescore_audits.py
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from call_quality import build_audit  # noqa: E402

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HEAD = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# Written by the scorer, not the model — reconstructing it as a model judgement
# would make an unjudged criterion look deliberately marked N/A.
SCORER_NA_MARKER = "not assessed"


def judgements_from(audit):
    """Recover the model's original judgements out of a stored audit."""
    criteria = []
    for c in audit.get("criteria", []):
        if SCORER_NA_MARKER in (c.get("reason") or "").lower():
            continue          # scorer-inserted placeholder: leave it unjudged
        criteria.append({
            "criterion_id": c["criterion_id"],
            "applicability": c["applicability"],
            "score_label": c["score_label"] if c["score_label"] != "n_a" else "zero",
            "reason": c.get("reason", ""),
            "subpoints": [{"subpoint_id": s["subpoint_id"], "status": s["status"],
                           "evidence": s.get("evidence", []), "notes": s.get("notes", "")}
                          for s in c.get("subpoints", [])],
        })
    return {
        "criteria": criteria,
        "critical_misses": audit.get("critical_misses", []),
        "red_flags": audit.get("red_flags", []),
        "qualitative_assessment": audit.get("qualitative_assessment", {}),
        "coaching": audit.get("coaching", {}),
        # build_audit derives a lot from these two, so leaving them out did not
        # merely lose detail — it silently disabled every conduct-driven rule on
        # replay (CM-2, CM-3, the CM-5 install-deadline check, opening_quality
        # zeroing Criterion 1, and RF-8/RF-9 entirely) and reset a stored
        # `follow_up` context to the "full_consultation" default. A replay that
        # does not reproduce a fresh run is not a replay, and the whole
        # "scoring-rule changes replay for free" promise rests on it.
        "conduct": audit.get("conduct", {}),
        "call_context": audit.get("call_context") or "full_consultation",
        "context_reason": audit.get("context_reason", ""),
    }


def meta_from(audit):
    m = dict(audit.get("call_information") or {})
    m.update({k: v for k, v in (audit.get("filter_dimensions") or {}).items()
              if v is not None})
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", default="",
                    help="comma-separated call IDs to rescore (default: every audited call). "
                         "Use this to apply a scorer change to one cohort instead of "
                         "rewriting the whole system of record")
    args = ap.parse_args()

    ids = [i for i in (s.strip() for s in args.ids.split(",")) if i]

    params = {"select": "call_id,call_quality_audit,qa_final_score,qa_tier",
              "call_quality_audit": "not.is.null",
              # Explicit order, per the PostgREST paging rule: without it there is
              # no stable row order, and pages shift under a concurrent writer so
              # rows are silently skipped. The audit supervisor writes to this
              # exact table, so that is the normal case here, not a rare one.
              "order": "call_id.asc"}
    if ids:
        params["call_id"] = f"in.({','.join(ids)})"
        print(f"🎯 restricted to {len(ids)} call ID(s)")

    # Each audit is ~19KB of jsonb, so a 500-row page is a ~10MB response and
    # Supabase 500s on it while the audit run is writing concurrently. Small
    # pages with a retry are slower but actually complete.
    rows, offset, page = [], 0, 100
    while True:
        batch = None
        for attempt in range(4):
            try:
                r = requests.get(
                    f"{SUPABASE_URL}/rest/v1/call_summaries",
                    headers={**HEAD, "Range": f"{offset}-{offset + page - 1}"},
                    params=params, timeout=120)
                if r.ok:
                    batch = r.json()
                    break
                print(f"   ⚠ page at {offset}: HTTP {r.status_code}, retrying")
            except requests.RequestException as e:
                print(f"   ⚠ page at {offset}: {type(e).__name__}, retrying")
            import time as _t
            _t.sleep(5 * (attempt + 1))
        if batch is None:
            print(f"   ⛔ gave up on the page at offset {offset}; "
                  f"rescoring the {len(rows)} row(s) fetched so far")
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    print(f"📊 {len(rows)} audited call(s) to rescore")
    if ids:
        # A silently-dropped ID reads as "that call was fine" when it may simply
        # have no audit yet, so name the misses rather than let the count differ.
        missing = [i for i in ids if i not in {str(r["call_id"]) for r in rows}]
        if missing:
            print(f"   ⚠ {len(missing)} requested ID(s) had no audit to rescore: "
                  f"{', '.join(missing)}")

    moves, changed, updates, skipped = Counter(), 0, [], []
    for row in rows:
        old = row["call_quality_audit"]
        # A not_scored audit contains placeholder criteria written by the scorer,
        # not model judgements. Replaying them would read those placeholders as
        # real verdicts and turn "could not assess" into "zero on everything" —
        # the exact false-zero this design exists to prevent. They need a genuine
        # re-run against the model, so they are cleared for the supervisor.
        if old.get("audit_status") == "not_scored":
            skipped.append(row["call_id"])
            continue
        new = build_audit(judgements_from(old), meta_from(old))
        o_tier, n_tier = old["score"]["tier"], new["score"]["tier"]
        o_sc, n_sc = old["score"]["final_score"], new["score"]["final_score"]
        if o_tier != n_tier or o_sc != n_sc:
            changed += 1
            moves[f"{o_tier} -> {n_tier}"] += 1
        updates.append((row["call_id"], new))

    print(f"   {changed} call(s) change")
    for k, n in moves.most_common(12):
        print(f"     {n:4d}  {k}")
    if skipped:
        print(f"   {len(skipped)} not_scored call(s) cannot be rescored — "
              f"clearing them so the audit run redoes them properly")

    if args.dry_run:
        print("\ndry run — nothing written")
        return

    for cid in skipped:
        requests.patch(f"{SUPABASE_URL}/rest/v1/call_summaries",
                       headers={**HEAD, "Content-Type": "application/json",
                                "Prefer": "return=minimal"},
                       params={"call_id": f"eq.{cid}"},
                       data=json.dumps({"call_quality_audit": None, "qa_final_score": None,
                                        "qa_tier": None, "qa_auto_zero": None,
                                        "qa_requires_human_review": None,
                                        "qa_critical_miss_codes": None,
                                        "qa_red_flag_codes": None}), timeout=30)

    ok = fail = 0
    for cid, audit in updates:
        s = audit["score"]
        body = {
            "call_quality_audit": audit,
            "qa_final_score": s["final_score"], "qa_tier": s["tier"],
            "qa_auto_zero": s["auto_zero"],
            "qa_requires_human_review": audit["requires_human_review"],
            "qa_critical_miss_codes": audit["analytics"]["critical_miss_codes"],
            "qa_red_flag_codes": audit["analytics"]["red_flag_codes"],
        }
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/call_summaries",
                           headers={**HEAD, "Content-Type": "application/json",
                                    "Prefer": "return=minimal"},
                           params={"call_id": f"eq.{cid}"},
                           data=json.dumps(body), timeout=30)
        ok, fail = (ok + 1, fail) if r.ok else (ok, fail + 1)
    print(f"\n✅ rescored {ok}" + (f", {fail} failed" if fail else "") + " — no LLM calls made")


if __name__ == "__main__":
    main()
