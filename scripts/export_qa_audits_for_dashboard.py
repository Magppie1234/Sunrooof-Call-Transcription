#!/usr/bin/env python3
"""Export audited calls into ci-dashboard/src/data/real/qa_audits.json.

Kept as its own file rather than folded into dataset.json on purpose: the audit
is still running and its scoring rules are unapproved, so it must be
regenerable in seconds without rebuilding a 55 MB dataset that a hundred other
panels depend on.

Usage:  python scripts/export_qa_audits_for_dashboard.py
"""
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "ci-dashboard" / "src" / "data" / "real" / "qa_audits.json"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HEAD = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch(params, page=100):
    """Small pages with retry: each audit is ~19KB of jsonb and a large page
    500s while the audit run is writing concurrently."""
    rows, offset = [], 0
    while True:
        batch = None
        for attempt in range(4):
            try:
                r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                                 headers={**HEAD, "Range": f"{offset}-{offset + page - 1}"},
                                 params=params, timeout=120)
                if r.ok:
                    batch = r.json()
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (attempt + 1))
        if batch is None:
            print(f"   ⚠ gave up at offset {offset}; exporting {len(rows)} row(s)")
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def _conduct(c):
    """Improvements, praise, risks and communication flags for the call page."""
    if not isinstance(c, dict):
        return {}
    def lst(key, n, fields):
        v = c.get(key)
        if not isinstance(v, list):
            return []
        out = []
        for x in v[:n]:
            if isinstance(x, dict):
                out.append({f: (str(x.get(f) or "")[:400]) for f in fields})
        return out
    lf = c.get("language_fit") if isinstance(c.get("language_fit"), dict) else {}
    li = c.get("listening") if isinstance(c.get("listening"), dict) else {}
    oq = c.get("opening_quality") if isinstance(c.get("opening_quality"), dict) else {}
    rp = c.get("rapport") if isinstance(c.get("rapport"), dict) else {}
    return {
        "customerLanguage": c.get("customer_language"),
        "improvements": lst("improvements", 10,
                            ["area", "what_went_wrong", "what_they_said",
                             "timestamp", "what_to_say_instead", "severity"]),
        "didWell": lst("did_well", 6, ["what", "quote"]),
        "risks": lst("unsupported_claims", 5, ["claim", "quote", "timestamp",
                                               "risk_level", "why"]),
        "jargon": [{"term": str(t.get("term") or "")[:60],
                    "quote": str(t.get("quote") or "")[:200],
                    "suggestion": str(t.get("suggestion") or "")[:300]}
                   for t in (lf.get("flagged_terms") or [])[:10]
                   if isinstance(t, dict)],
        "languageCoaching": str(lf.get("coaching") or "")[:400],
        "listening": {"interrupted": bool(li.get("interrupted")),
                      "ignoredStated": bool(li.get("ignored_stated_information")),
                      "coaching": str(li.get("coaching") or "")[:400]},
        "opening": {"rating": oq.get("rating"), "coaching": str(oq.get("coaching") or "")[:300]},
        "rapport": {"rating": rp.get("rating"), "note": str(rp.get("note") or "")[:300]},
    }


def _coaching(c):
    """Audits written before the shape fix can hold a string here, not an object."""
    if isinstance(c, str):
        return {"strengths": [], "improvements": [], "summary": c[:600]}
    if not isinstance(c, dict):
        return {"strengths": [], "improvements": [], "summary": ""}
    def lst(k):
        v = c.get(k)
        return v[:5] if isinstance(v, list) else []
    summary = c.get("overall_call_quality_summary") or c.get("summary") or ""
    return {"strengths": lst("strengths"),
            "improvements": lst("priority_improvements") or lst("improvements"),
            "summary": (summary if isinstance(summary, str) else str(summary))[:600]}


def main():
    print("☁️  loading audited calls…")
    rows = fetch({"select": "call_id,agent,customer,start_time,duration_seconds,summary,"
                            "customer_sentiment,call_outcome,call_quality_audit,qa_final_score,"
                            "qa_tier,qa_auto_zero,qa_requires_human_review",
                  "call_quality_audit": "not.is.null",
                  # call_id breaks the tie, and without it this silently loses rows.
                  # qa_final_score is massively non-unique — thousands of calls sit on
                  # 0 and ~1,900 are NOT_SCORED with null — so ordering on it alone
                  # leaves Postgres free to return tied rows in any order per page.
                  # Paged with Range:, that means some rows repeat and others are never
                  # returned: a 6,260-row export held 4,965 unique calls, 1,295 dupes
                  # and ~1,295 calls missing, including 4 that were under review.
                  "order": "qa_final_score.desc.nullslast,call_id.asc"})
    print(f"   {len(rows)} audited")

    # Defence in depth: if paging ever breaks again, fail loudly here rather than
    # shipping a dashboard that silently omits calls.
    seen, deduped = set(), []
    for r in rows:
        if r["call_id"] in seen:
            continue
        seen.add(r["call_id"])
        deduped.append(r)
    if len(deduped) != len(rows):
        print(f"   ⚠ paging returned {len(rows) - len(deduped)} duplicate row(s) — "
              f"exporting {len(deduped)} unique call(s). The order= clause is not stable.")
        rows = deduped

    total = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                         headers={**HEAD, "Prefer": "count=exact", "Range": "0-0"},
                         params={"select": "call_id"}, timeout=30)
    corpus = int(total.headers.get("Content-Range", "/0").split("/")[-1] or 0)

    calls = []
    for r in rows:
        a = r["call_quality_audit"] or {}
        score = a.get("score", {})
        criteria = []
        for c in a.get("criteria", []):
            # Audits written before evidence normalisation can hold bare strings
            # where an object is expected, so this stays tolerant of both shapes
            # rather than assuming every stored row has the current form.
            ev = []
            for s in c.get("subpoints", []):
                for e in (s.get("evidence") or []):
                    if isinstance(e, str):
                        ev.append({"t": None, "q": e[:220]})
                    elif isinstance(e, dict):
                        ev.append({"t": e.get("timestamp"),
                                   "q": (e.get("quote") or e.get("text") or "")[:220]})
            ev = ev[:3]
            # Names of the points not fully covered. Deliberately re-added after
            # the size trim: "1 of 2 points met" is useless to an agent trying to
            # improve — they need to know which point.
            def _pts(status):
                out = []
                for sp in c.get("subpoints", []):
                    if sp.get("status") != status:
                        continue
                    req = (sp.get("requirement") or "").split(":", 1)[-1]
                    req = req.replace("MANDATORY", "").replace("PROHIBITED", "").strip(" -")
                    if req:
                        out.append(req[:120])
                return out[:4]

            criteria.append({
                "missed": _pts("not_met"), "partial": _pts("partial"),
                "unverified": _pts("unknown"),
                "id": c["criterion_id"], "name": c["criterion_name"],
                "max": c["max_points"], "label": c["score_label"],
                "points": c["points_awarded"], "applicable": c["applicability"] == "applicable",
                "reason": (c.get("reason") or "")[:300], "evidence": ev,
            })
        calls.append({
            "id": r["call_id"],
            "agent": r.get("agent"), "customer": r.get("customer"),
            "date": (r.get("start_time") or "")[:10],
            "durationSec": r.get("duration_seconds") or 0,
            "summary": (r.get("summary") or "")[:400],
            "sentiment": r.get("customer_sentiment"),
            "outcome": r.get("call_outcome"),
            "score": score.get("final_score"),
            "preDeduction": score.get("pre_deduction_percentage"),
            "earned": score.get("earned_score"),
            "adjustedMax": score.get("adjusted_max_score"),
            "deduction": score.get("red_flag_deduction_total"),
            "tier": score.get("tier"), "autoZero": bool(score.get("auto_zero")),
            "autoZeroCodes": score.get("auto_zero_codes") or [],
            # Only code + observed: the descriptions are static scorecard text,
            # identical on every call, and repeating them 6,260 times inflates a
            # file that is bundled straight into the JS build.
            "criticalMisses": [{"code": c["code"], "observed": c["observed"]}
                               for c in a.get("critical_misses", [])],
            "redFlags": [{"code": f["code"], "observed": f["observed"],
                          "deduction": f["deduction_if_observed"]}
                         for f in a.get("red_flags", [])],
            "needsReview": bool(a.get("requires_human_review")),
            "reviewReasons": (a.get("human_review_reasons") or [])[:6],
            "status": a.get("audit_status"),
            "criteria": criteria,
            # The coaching layer — the reason this portal exists. Trimmed to what
            # the call page renders so the bundled file stays manageable.
            "context": a.get("call_context"),
            "contextReason": (a.get("context_reason") or "")[:200],
            "conduct": _conduct(a.get("conduct")),
            "coaching": _coaching(a.get("coaching")),
        })

    payload = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "corpusSize": corpus,
        "auditedCount": len(calls),
        "model": "gpt-4.1-mini",
        "scorecard": "SUNROOOF PSM / Wellness Consultant — 100 point",
        "calls": calls,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False))
    print(f"✅ {OUT}  ({OUT.stat().st_size / 1024 / 1024:.1f} MB, "
          f"{len(calls)} of {corpus} calls)")


if __name__ == "__main__":
    main()
