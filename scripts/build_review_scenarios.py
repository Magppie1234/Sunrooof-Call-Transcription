#!/usr/bin/env python3
"""List the calls the user wants to listen to.

Lead-level scenarios (one row per CRM record):

  1. 2-3 calls between the same agent and customer, NO raw quote raised
  2. 2-3 calls between them, AND the lead reached the Raw Quote stage
  3. ONE long call, and the lead reached the Raw Quote stage

Call-level contradiction cohorts (four calls each, one row per call), where two
systems disagree about what happened so one of them is provably wrong:

  4. AI read a quotation request, CRM never reached Raw Quote
  5. AI read a positive outcome, CRM record is closed Not Interested
  6. Sentiment came out positive, lead is closed dead
  7. Outcome says not connected, yet the recording runs for minutes

"Raw Quote" is a real stage in the Zoho Deals module — the point where the layout
has been sent and a rough quotation given.

Read-only: reads Supabase, Zoho, dataset.json and out/call_sequence.json. Writes
one report. No LLM calls, no changes to any summary or transcript.

Usage:
    .venv-win/Scripts/python.exe scripts/build_review_scenarios.py
    .venv-win/Scripts/python.exe scripts/build_review_scenarios.py --only-outliers
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize_calls as sc  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OUT_MD = BASE / "out" / "review_scenarios.md"
OUT_JSON = BASE / "out" / "review_scenarios.json"
DATASET = BASE / "ci-dashboard" / "src" / "data" / "real" / "dataset.json"
LONG_CALL_SECONDS = 600          # a "long call" for scenario 3


def zoho_raw_quote_deals():
    """Deal id + name for every deal that reached Raw Quote, paged."""
    tok = sc.get_token()
    h = {"Authorization": f"Zoho-oauthtoken {tok}"}
    out, offset = {}, 0
    while True:
        q = ("select id, Deal_Name, Stage, Created_Time from Deals "
             "where Created_Time between '2026-05-01T00:00:00+05:30' and "
             "'2026-08-31T23:59:59+05:30' "
             f"order by id asc limit {offset}, 200")
        r = requests.post(f"{sc.ZOHO_API}/crm/v7/coql", headers=h,
                          json={"select_query": q}, timeout=60)
        if r.status_code != 200:
            break
        try:
            rows = r.json().get("data") or []
        except ValueError:
            break
        if not rows:
            break
        for d in rows:
            out[str(d.get("id"))] = {"name": d.get("Deal_Name"),
                                     "stage": d.get("Stage"),
                                     "created": (d.get("Created_Time") or "")[:10]}
        offset += 200
        if offset > 9800:
            break
    return out


def fetch_calls():
    h = {"apikey": sc.SUPABASE_KEY, "Authorization": f"Bearer {sc.SUPABASE_KEY}"}
    rows, offset = [], 0
    while True:
        r = requests.get(f"{sc.SUPABASE_URL}/rest/v1/call_summaries",
                         headers={**h, "Range": f"{offset}-{offset + 999}"},
                         params={"select": "call_id,agent,customer,start_time,"
                                           "duration_seconds,call_outcome,summary",
                                 "order": "call_id.asc"}, timeout=120)
        if not r.ok:
            break
        b = r.json()
        rows.extend(b)
        if len(b) < 1000:
            break
        offset += 1000
    return {x["call_id"]: x for x in rows}


# ── Contradiction cohorts ────────────────────────────────────────────────────
# Four calls each from four groups where two systems disagree about what
# happened. These are call-level, not lead-level like scenarios 1-3, but they are
# emitted in the same shape (one call per "lead") so the dashboard renders them
# through the same table.
OUTLIER_N = 4
MIN_CONFIDENCE = 0.6
POSITIVE_OUTCOMES = {"Interested — follow-up", "Quotation requested",
                     "Site visit scheduled", "Demo scheduled", "Order confirmed"}
DEAD_STAGES = {"Not Interested", "Non-Serviceable"}


def _is_raw(stage):
    return (stage or "").lower().startswith("raw")


def _usable(c):
    """Transcript good enough that a disagreement means something.

    Below ~0.6 confidence the transcript is too noisy to tell a real
    contradiction from a transcription error, which would spend the reviewer's
    time on a bug that is not in the assessment.
    """
    return bool(c.get("meaningful")) and (c.get("transcriptionConfidence") or 0) >= MIN_CONFIDENCE


def _pick(pool, key_fn, used, n=OUTLIER_N):
    """Longest first, but one per distinct key before doubling up.

    Four near-identical calls teach less than four flavours of the same
    contradiction, so the first pass takes one of each key (CRM stage, outcome)
    and only then fills the remaining slots by length. `used` keeps a call from
    appearing in two cohorts.
    """
    pool = sorted((c for c in pool if c["id"] not in used),
                  key=lambda c: (-(c.get("durationSec") or 0), str(c["id"])))
    out, seen = [], set()
    for c in pool:
        k = str(key_fn(c))
        if k not in seen:
            seen.add(k)
            out.append(c)
        if len(out) == n:
            break
    if len(out) < n:
        for c in pool:
            if c not in out:
                out.append(c)
            if len(out) == n:
                break
    used.update(c["id"] for c in out)
    return out


# Static description of each cohort, separate from the selection that fills it.
# Kept at module level so --refresh-qa can rewrite the report without re-running
# the selection: re-selecting would silently swap which calls are under review,
# and a reviewer part-way through a set would lose their place.
COHORT_SPECS = [
    ("outlier_1_quotation_claimed_crm_disagrees",
     "Quotation claimed, CRM disagrees",
     "The call was read as a quotation request, but the CRM record never "
     "reached Raw Quote. Either the AI over-read the ask, or the stage was "
     "never moved.",
     "AI says quotation requested · CRM stage says otherwise"),
    ("outlier_2_positive_outcome_crm_not_interested",
     "Positive outcome, CRM says not interested",
     "The call was read as interested, a site visit or a demo, and the CRM "
     "record is closed as Not Interested.",
     "AI says positive outcome · CRM stage says Not Interested"),
    ("outlier_3_positive_sentiment_lead_died",
     "Positive sentiment, lead died",
     "Sentiment came out positive and the lead is closed Not Interested or "
     "Non-Serviceable. Tests whether sentiment tracks call tone rather than "
     "customer intent.",
     "Sentiment positive · lead closed dead"),
    ("outlier_4_not_connected_long_call",
     "Not connected, yet minutes of audio",
     "Marked not connected, but the recording runs for minutes. A call that "
     "never connected cannot have a conversation in it.",
     "Outcome says not connected · recording says otherwise"),
]


def outlier_cohorts(ds_calls):
    """The four cohorts, as (json_key, title, note, contradiction, [dataset calls])."""
    used = set()
    c1 = _pick([c for c in ds_calls
                if c.get("outcome") == "Quotation requested"
                and not _is_raw(c.get("crmStage")) and _usable(c)],
               lambda c: c.get("crmStage"), used)
    c2 = _pick([c for c in ds_calls
                if c.get("outcome") in POSITIVE_OUTCOMES
                and c.get("outcome") != "Quotation requested"
                and c.get("crmStage") == "Not Interested" and _usable(c)],
               lambda c: c.get("outcome"), used)
    c3 = _pick([c for c in ds_calls
                if (c.get("sentiment") or {}).get("overall") == "positive"
                and c.get("crmStage") in DEAD_STAGES and _usable(c)],
               lambda c: c.get("crmStage"), used)
    # No _usable() gate here: "not connected" calls are all flagged not-meaningful
    # by definition, and that flag is exactly what is in question.
    c4 = _pick([c for c in ds_calls if c.get("outcome") == "Not connected"],
               lambda c: c["id"], used)
    return [(*spec, group) for spec, group in zip(COHORT_SPECS, (c1, c2, c3, c4))]


def fetch_qa(ids):
    """qa_* columns for the selected calls. Read-only, one page, explicit order."""
    if not ids:
        return {}
    h = {"apikey": sc.SUPABASE_KEY, "Authorization": f"Bearer {sc.SUPABASE_KEY}"}
    r = requests.get(f"{sc.SUPABASE_URL}/rest/v1/call_summaries", headers=h, timeout=60,
                     params={"select": "call_id,qa_final_score,qa_tier,qa_auto_zero,"
                                       "qa_requires_human_review,call_quality_audit",
                             "call_id": f"in.({','.join(ids)})",
                             "order": "call_id.asc"})
    if not r.ok:
        print(f"⚠️  QA fetch failed ({r.status_code}); rows will show audit status unknown")
        return {}
    out = {}
    for row in r.json():
        out[row["call_id"]] = {
            "audited": row.get("call_quality_audit") is not None,
            "score": row.get("qa_final_score"),
            "tier": row.get("qa_tier"),
            "auto_zero": row.get("qa_auto_zero"),
            "needs_review": row.get("qa_requires_human_review"),
        }
    return out


def outlier_table(title, note, contradiction, groups_):
    out = [f"\n## {title}\n\n{note}\n\n_{contradiction}_\n",
           "| Call ID | Date | Agent | Length | AI outcome | CRM stage | Sentiment | Conf | QA |",
           "|---|---|---|---|---|---|---|---|---|"]
    for g in groups_:
        c = g["calls"][0]
        qa = c.get("qa") or {}
        qa_cell = ("not audited" if not qa.get("audited")
                   else f"{qa.get('score')} {qa.get('tier')}"
                        + (" auto-zero" if qa.get("auto_zero") else ""))
        out.append(f"| `{c['call_id']}` | {c['date']} | {c['agent'] or '—'} | {c['minutes']} min "
                   f"| {c.get('dataset_outcome') or c['outcome']} | {c.get('crm_stage') or '—'} "
                   f"| {c.get('sentiment') or '—'} | {c.get('confidence')} | {qa_cell} |")
    return "\n".join(out)


def write_payload(payload):
    """Both copies: the working file and the one the dashboard imports at build."""
    OUT_JSON.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    dash = BASE / "ci-dashboard" / "src" / "data" / "real" / "review_scenarios.json"
    dash.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _scenario_table(title, note, groups_):
    out = [f"\n## {title}\n\n{note}\n\n**{len(groups_)} leads**\n"]
    for g in groups_[:40]:
        head = g["calls"][0]
        out.append(f"\n### {head['agent']} → {head['customer']}"
                   f"{'  · ' + g['stage'] if g.get('stage') else ''}\n")
        out.append("| # | Call ID | Date | Length | Outcome |")
        out.append("|---|---|---|---|---|")
        for c in g["calls"]:
            out.append(f"| {c['contact_number']} | `{c['call_id']}` | {c['date']} "
                       f"| {c['minutes']} min | {c['outcome']} |")
    if len(groups_) > 40:
        out.append(f"\n_…and {len(groups_) - 40} more leads in "
                   f"`out/review_scenarios.json`._")
    return "\n".join(out)


def write_report(payload):
    """Rebuild the markdown from the payload alone.

    Takes its cohort titles from COHORT_SPECS rather than from a selection run,
    so --refresh-qa can rewrite the report without touching which calls are in it.
    """
    md = ["# Calls to review",
          "",
          "Read-only listing. No summary or transcript was changed.",
          "“Raw Quote” is the Zoho Deals stage reached once the layout has been sent "
          "and a rough quotation given.",
          _scenario_table("Scenario 1 — 2-3 calls, no raw quote",
                          "Multiple conversations that did not reach a quotation.",
                          payload["scenario_1_multi_call_no_raw_quote"]),
          _scenario_table("Scenario 2 — 2-3 calls, raw quote raised",
                          "Multiple conversations that did reach a quotation.",
                          payload["scenario_2_multi_call_with_raw_quote"]),
          _scenario_table("Scenario 3 — one long call, raw quote raised",
                          f"A single call of {LONG_CALL_SECONDS // 60}+ minutes that "
                          f"reached a quotation.",
                          payload["scenario_3_single_long_call_with_raw_quote"]),
          "\n---\n\n# Contradiction cohorts\n",
          "Four calls each where two systems disagree about the same call, so one "
          "of them is wrong.",
          ]
    for key, title, note, contradiction in COHORT_SPECS:
        md.append(outlier_table(title, note, contradiction, payload.get(key, [])))
    OUT_MD.write_text("\n".join(md), encoding="utf-8")


def refresh_qa(payload):
    """Re-read the qa_* columns for the calls already in the report.

    The report bakes a QA snapshot taken at build time, so any audit that runs
    afterwards leaves it stale — on 2026-08-26 the set was built at 15:16 and
    re-audited at 15:51, leaving 8 of 16 calls showing scores that no longer
    existed, four of them a whole tier out. Re-selecting the cohorts would fix
    the numbers but change which calls are under review; this only refreshes
    what is already there.

    Returns the list of (call_id, before, after) that actually moved.
    """
    ids, rows = [], []
    for key, *_ in COHORT_SPECS:
        for group in payload.get(key, []):
            for row in group.get("calls", []):
                ids.append(row["call_id"])
                rows.append(row)
    if not ids:
        return []

    fresh = fetch_qa(ids)
    changed = []
    for row in rows:
        before = row.get("qa")
        after = fresh.get(row["call_id"])
        # A call missing from the fetch keeps its old value rather than being
        # blanked: an empty result is far more likely to be a failed request
        # than a genuinely deleted audit.
        if after is None:
            continue
        if before != after:
            changed.append((row["call_id"], before, after))
            row["qa"] = after
    return changed


def main():
    ap = argparse.ArgumentParser(description="Build the review listening sets.")
    ap.add_argument("--only-outliers", action="store_true",
                    help="rebuild only the four contradiction cohorts and merge them into "
                         "the existing report, leaving scenarios 1-3 as they are. Skips the "
                         "Zoho Deals pull, which is the slow part.")
    ap.add_argument("--refresh-qa", action="store_true",
                    help="re-read the qa_* columns for the calls already in the report "
                         "and rewrite it. Changes no selection — the same calls stay "
                         "under review. Use after any audit run.")
    args = ap.parse_args()

    if args.refresh_qa:
        if not OUT_JSON.exists():
            sys.exit(f"❌ {OUT_JSON} does not exist — build the report first")
        payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        changed = refresh_qa(payload)
        if not changed:
            print("✅ QA already current — nothing changed.")
            return
        print(f"↻ {len(changed)} call(s) had stale QA:\n")
        for cid, before, after in changed:
            b, a = before or {}, after or {}
            print(f"   {cid}  {b.get('score')}/{b.get('tier')}"
                  f"  →  {a.get('score')}/{a.get('tier')}"
                  + ("  (auto-zero lifted)" if b.get("auto_zero") and not a.get("auto_zero")
                     else "  (now auto-zero)" if a.get("auto_zero") and not b.get("auto_zero")
                     else ""))
        write_payload(payload)
        write_report(payload)
        print(f"\n💾 {OUT_MD}")
        return

    seq = json.loads((BASE / "out" / "call_sequence.json").read_text())
    calls = fetch_calls()
    print(f"📞 {len(calls)} calls, {len(seq)} sequenced")

    if args.only_outliers:
        payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        print("↻ keeping scenarios 1-3 from the existing report")
    else:
        payload = {}

    def pack(cid):
        c = calls[cid]
        return {"call_id": cid, "agent": c.get("agent"), "customer": c.get("customer"),
                "date": (c.get("start_time") or "")[:10],
                "minutes": round((c.get("duration_seconds") or 0) / 60, 1),
                "outcome": c.get("call_outcome"),
                "contact_number": seq[cid]["contact_number"],
                "summary": (c.get("summary") or "")[:200]}

    if not args.only_outliers:
        enrich = json.loads((BASE / "out" / "zoho_enrichment.json").read_text())
        print("☁️  fetching Deal stages from Zoho…")
        deals = zoho_raw_quote_deals()
        raw_ids = {k for k, v in deals.items() if (v.get("stage") or "").lower() == "raw quote"}
        print(f"   {len(deals)} deals, {len(raw_ids)} at Raw Quote")

        # Group calls by the CRM record, and note whether that record hit Raw Quote.
        groups = defaultdict(list)
        group_raw = {}
        for cid, q in seq.items():
            if cid not in calls:
                continue
            groups[q["group_key"]].append(cid)
            rec = enrich.get(cid) or {}
            linked = str(rec.get("linked_id") or "")
            if linked in raw_ids or (rec.get("crm_stage") or "").lower() == "raw":
                group_raw[q["group_key"]] = deals.get(linked, {"stage": "Raw"})

        s1, s2, s3 = [], [], []
        for key, cids in groups.items():
            cids.sort(key=lambda c: calls[c].get("start_time") or "")
            n = len(cids)
            is_raw = key in group_raw
            if 2 <= n <= 3 and not is_raw:
                s1.append({"lead": key, "calls": [pack(c) for c in cids]})
            elif 2 <= n <= 3 and is_raw:
                s2.append({"lead": key, "stage": group_raw[key].get("stage"),
                           "calls": [pack(c) for c in cids]})
            elif n == 1 and is_raw and (calls[cids[0]].get("duration_seconds") or 0) >= LONG_CALL_SECONDS:
                s3.append({"lead": key, "stage": group_raw[key].get("stage"),
                           "calls": [pack(cids[0])]})

        for grp in (s1, s2, s3):
            grp.sort(key=lambda g: -sum(c["minutes"] for c in g["calls"]))

        payload["scenario_1_multi_call_no_raw_quote"] = s1
        payload["scenario_2_multi_call_with_raw_quote"] = s2
        payload["scenario_3_single_long_call_with_raw_quote"] = s3

    # ── the four contradiction cohorts ──
    print("🔎 selecting contradiction cohorts from dataset.json…")
    ds_calls = json.loads(DATASET.read_text(encoding="utf-8"))["calls"]
    cohorts = outlier_cohorts(ds_calls)
    picked = [str(c["id"]) for *_, group in cohorts for c in group]
    qa = fetch_qa(picked)
    n_unaudited = sum(1 for cid in picked if not (qa.get(cid) or {}).get("audited"))
    print(f"   {len(picked)} calls picked, {n_unaudited} without a quality audit")

    for key, title, _note, contradiction, group in cohorts:
        rows = []
        for c in group:
            cid = str(c["id"])
            if cid not in calls or cid not in seq:
                print(f"   ⚠️  {cid} in dataset but not in Supabase/sequence — skipped")
                continue
            row = pack(cid)
            row.update({"crm_stage": c.get("crmStage"),
                        "dataset_outcome": c.get("outcome"),
                        "sentiment": (c.get("sentiment") or {}).get("overall"),
                        "confidence": c.get("transcriptionConfidence"),
                        "qa": qa.get(cid)})
            rows.append({"lead": f"call:{cid}", "stage": c.get("crmStage"),
                         "contradiction": contradiction, "calls": [row]})
        payload[key] = rows
        print(f"   {title}: {len(rows)}")

    write_payload(payload)
    write_report(payload)

    print(f"\n💾 {OUT_MD}")
    for key in ("scenario_1_multi_call_no_raw_quote",
                "scenario_2_multi_call_with_raw_quote",
                "scenario_3_single_long_call_with_raw_quote"):
        print(f"   {key:45s}: {len(payload[key])} leads")


if __name__ == "__main__":
    main()
