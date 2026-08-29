#!/usr/bin/env python3
"""Work out which contact each call is — first, second, third — and what earlier
calls already covered.

Why this matters: the scorecard expects an introduction, the wellness benefits and
the technical explanation. On a second or third call the agent has already done
all of that, and penalising them for not repeating it is wrong. Anubhav Singh was
marked down for "did not introduce himself" on a call that was his second contact
with Bhartpal Singh Kahlon, the day after a 1.4-minute first call.

How the sequence is established, in order of reliability:

1. **CRM linked record** (`linked_id` from zoho_enrichment.json — the Lead, Contact
   or Deal the call is attached to). This is the same entity across every call with
   that customer, so it groups reliably even when the display name varies. 6,041 of
   6,260 calls carry one.
2. **Agent + customer name** for the remainder. Weaker, because names repeat and
   arrive inconsistently from the CRM, so it is only a fallback.

Within a group, calls are ordered by `start_time`; position gives the contact
number. What earlier calls covered is read from their own stored audit, so it is
evidence-based rather than assumed.

No LLM calls — this is pure bookkeeping and costs nothing to rerun.

Usage:  .venv/bin/python scripts/build_call_sequence.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize_calls as sc  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out" / "call_sequence.json"

# Criteria whose content, once delivered, does not need repeating on a later call.
REPEATABLE = {
    3: "the SUNROOOF value proposition and wellness benefits",
    5: "the technical explanation",
    6: "pricing and console specifications",
}


def load_enrichment():
    p = BASE / "out" / "zoho_enrichment.json"
    try:
        raw = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def fetch_calls():
    h = {"apikey": sc.SUPABASE_KEY, "Authorization": f"Bearer {sc.SUPABASE_KEY}"}
    rows, offset, page = [], 0, 1000
    while True:
        r = requests.get(f"{sc.SUPABASE_URL}/rest/v1/call_summaries",
                         headers={**h, "Range": f"{offset}-{offset + page - 1}"},
                         params={"select": "call_id,agent,customer,start_time,"
                                           "duration_seconds,call_outcome,summary,"
                                           "call_quality_audit",
                                 "order": "call_id.asc"}, timeout=120)
        if not r.ok:
            break
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def covered_in(audit):
    """Which repeatable areas an earlier call actually delivered, per its audit."""
    if not isinstance(audit, dict):
        return []
    out = []
    for c in audit.get("criteria", []):
        cid = c.get("criterion_id")
        # Half marks or better means the substance was delivered, even if not perfectly.
        if cid in REPEATABLE and c.get("applicability") == "applicable" \
                and (c.get("points_awarded") or 0) >= (c.get("max_points") or 99) / 2:
            out.append(cid)
    return out


def main():
    enrich = load_enrichment()
    calls = fetch_calls()
    print(f"📞 {len(calls)} calls")

    groups = defaultdict(list)
    keyed_by_crm = 0
    for c in calls:
        rec = enrich.get(c["call_id"]) or {}
        linked = rec.get("linked_id")
        if linked:
            key = f"crm:{linked}"
            keyed_by_crm += 1
        else:
            key = f"name:{(c.get('agent') or '').lower()}|{(c.get('customer') or '').lower()}"
        groups[key].append(c)

    print(f"   grouped by CRM record: {keyed_by_crm}   by agent+name fallback: "
          f"{len(calls) - keyed_by_crm}")

    index, multi = {}, 0
    for key, items in groups.items():
        items.sort(key=lambda x: x.get("start_time") or "")
        if len(items) > 1:
            multi += 1
        for n, c in enumerate(items, 1):
            prior = items[:n - 1]
            # Coverage is read from the earlier calls' SUMMARIES, not their
            # audits. Every one of the 1,531 follow-ups has its previous call
            # summarised, whereas audits may not exist yet — keying off audits
            # made this silently do nothing on a fresh database.
            already = sorted({cid for p in prior
                              for cid in covered_in(p.get("call_quality_audit"))})
            history = [{"date": (p.get("start_time") or "")[:10],
                        "summary": (p.get("summary") or "")[:400],
                        "outcome": p.get("call_outcome")}
                       for p in prior[-3:]]
            index[c["call_id"]] = {
                "contact_number": n,
                "total_contacts": len(items),
                "group_key": key,
                "is_first_contact": n == 1,
                "previous_call_id": prior[-1]["call_id"] if prior else None,
                "previous_call_date": (prior[-1].get("start_time") or "")[:10] if prior else None,
                "previous_call_summary": (prior[-1].get("summary") or "")[:300] if prior else None,
                "already_covered": [{"criterion": cid, "what": REPEATABLE[cid]}
                                    for cid in already],
                "history": history,
            }

    OUT.write_text(json.dumps(index, ensure_ascii=False))
    seq = [v["contact_number"] for v in index.values()]
    print(f"\n💾 {OUT}")
    print(f"   customers with more than one call: {multi}")
    for n in (1, 2, 3):
        print(f"   contact #{n}: {sum(1 for x in seq if x == n)} call(s)")
    print(f"   contact #4 or later: {sum(1 for x in seq if x >= 4)}")
    follow = sum(1 for x in seq if x > 1)
    print(f"\n   {follow} of {len(seq)} calls ({follow / max(len(seq),1) * 100:.0f}%) are "
          f"follow-ups where an introduction is not expected")


if __name__ == "__main__":
    main()
