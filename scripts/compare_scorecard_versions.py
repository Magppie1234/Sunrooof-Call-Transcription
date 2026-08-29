#!/usr/bin/env python3
"""Score the same calls under v1 and v2.1 and report what the scorecard change did.

Both runs use temperature 0 so the difference reflects the scorecard, not model
randomness — an earlier comparison at the SDK's default temperature of 1.0 showed
an 18.8-point mean swing that was mostly noise.

Writes nothing to Supabase. Output feeds the "Scorecard change review" panel on
the Advanced QA page.

Usage:  .venv/bin/python scripts/compare_scorecard_versions.py --limit 14
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import call_quality as cq  # noqa: E402
import summarize_calls as sc  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "ci-dashboard" / "src" / "data" / "real" / "scorecard_change_review.json"
V1_PROMPT = BASE / "prompts" / "_archive_v1_scorecard.md"

# v1 sub-point wording, restored so the checklist the model receives matches the
# version being tested. Without this both runs would share v2.1's checklist.
V1_SUBPOINTS = {
    "1.1": "Well-paced, clear, assumptive opening",
    "1.3": "Asked how the customer heard about us / confirmed lead source",
    "2.1": "Identified customer type: end-user, architect or builder",
    "2.4": "MANDATORY: captured by when the customer needs SUNROOOF installed and ready to use",
    "3.2": "MANDATORY: explained at least five distinct key benefits",
    "3.4": "Mentioned 900+ projects / market response / credibility",
    "5.3": "Explained the minimum quantity and why (four-console minimum)",
    "5.6": "Explained product life of 12-15 years",
    "5.7": "Explained power consumption 0.03 kW/hr and the 15W LED comparison",
    "5.9": "Explained where the product is manufactured",
    "5.10": "Clarified preset/GPS-based, not sensor-based, if needed",
    "6.2": "MANDATORY: gave the complete ceiling-console price range per console",
    "6.4": "MANDATORY: gave console measurements in both feet/inches and millimetres",
    "6.6": "MANDATORY/PROHIBITED: avoided GST, installation charges and remote pricing",
    "7.5": "Explained the modular nature of the product",
    "11.1": "MANDATORY: described the special package and price locking, and obtained a YES to explore",
}

# Plain-language reason a criterion can move between versions.
WHY = {
    1: "v2 defines an assumptive opening as NOT verifying identity ('Is this X speaking?' "
       "no longer counts as assumptive), and lets a confirmed lead source count without asking.",
    2: "v2 requires the agent to ask AND prompt for the install deadline; a customer who "
       "does not know no longer fails the agent.",
    3: "v2 pins the five wellness benefits to Sameer's exact chain and corrects credibility "
       "to 1000+ spaces.",
    4: "v2 adds the wall/window console route explicitly.",
    5: "v2 corrects the facts: life 12-14 years, power 20-40W, and drops the unsupported "
       "'less than a 15W LED' claim. Wall installs need only two consoles.",
    6: "v2 accepts any two of four measurement units (not specifically feet+mm) and ties "
       "quantity to the customer's purpose - wellness-only justifies the chart minimum.",
    7: "v2 spells out modularity (consoles move home, frames are rebought).",
    8: "v2 recognises the approved price-objection technique - cost spread over 180 months.",
    9: "unchanged between versions.",
    10: "v2 credits explaining the four-part payment structure as process, not a pricing breach.",
    11: "v2 requires urgency to be built on the customer's OWN stated deadline.",
    12: "unchanged between versions.",
}


def audit_once(client, cid, entries, meta, prompt_file, subpoint_override=None):
    """Run one audit with a given scorecard version, returning the scored object."""
    original_file = sc.QA_PROMPT_FILE
    original_card = [dict(c) for c in cq.SCORECARD]
    try:
        sc.QA_PROMPT_FILE = prompt_file
        if subpoint_override:
            for spec in cq.SCORECARD:
                spec["subpoints"] = [
                    (sid, subpoint_override.get(sid, req), mand)
                    for sid, req, mand in spec["subpoints"]]
        sid = sc.agent_speaker_id(entries)
        stamped = sc.render_transcript_timestamped(entries, sid, meta["agent"], meta["customer"])
        plain = sc.render_transcript(entries, sid, meta["agent"], meta["customer"])
        result = sc.summarize(client, meta, stamped, with_audit=True)
        sc.verify_evidence(result, plain)
        return sc.build_call_quality_audit(result, meta, cid)
    finally:
        sc.QA_PROMPT_FILE = original_file
        for spec, saved in zip(cq.SCORECARD, original_card):
            spec["subpoints"] = saved["subpoints"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=14)
    args = ap.parse_args()

    import requests
    h = {"apikey": sc.SUPABASE_KEY, "Authorization": f"Bearer {sc.SUPABASE_KEY}"}
    r = requests.get(f"{sc.SUPABASE_URL}/rest/v1/call_summaries", headers=h,
                     params={"select": "call_id,agent,customer,duration_seconds,summary,"
                                       "start_time,qa_final_score",
                             "start_time": "gte.2026-07-01T00:00:00",
                             "duration_seconds": "gte.480",
                             "order": "qa_final_score.desc",
                             "limit": 400}, timeout=60)
    pool = [x for x in r.json() if x.get("qa_final_score") is not None]
    # A deliberate spread: the best calls, the worst, and the middle — so the
    # review shows whether good work is being rewarded AND bad work flagged.
    half = max(args.limit // 2, 1)
    calls = pool[:half] + pool[-(args.limit - half):]
    print(f"comparing {len(calls)} call(s), both versions at temperature 0\n")

    client = sc.OpenAI(api_key=sc.API_KEY, base_url=sc.BASE_URL, max_retries=5, timeout=300.0)
    token = sc.get_token()
    rows = []
    for n, c in enumerate(calls, 1):
        cid = c["call_id"]
        tpath = sc.TDIR / f"{cid}.mp3.json"
        if not tpath.exists():
            continue
        entries = json.loads(tpath.read_text()).get("diarized_transcript", {}).get("entries", [])
        meta = (sc.meta_from_cache(cid) or sc.fetch_meta(token, cid)
                or sc.meta_from_summary(cid))
        if not meta or not entries:
            continue
        try:
            a1 = audit_once(client, cid, entries, meta, V1_PROMPT, V1_SUBPOINTS)
            a2 = audit_once(client, cid, entries, meta, sc.QA_PROMPT_FILE)
        except Exception as e:
            print(f"  ❌ {cid}: {type(e).__name__}: {e}")
            continue

        s1, s2 = a1["score"], a2["score"]

        def describe(crit):
            """Name every point the agent did not fully cover.

            A bare count ("1 of 2 points met") tells a manager or an agent nothing
            actionable — they need to know WHICH point. Partial and unverifiable
            points are named too, not just outright misses.
            """
            missed, met, partial, unknown = [], [], [], []
            for sp in crit.get("subpoints", []):
                raw = sp.get("requirement") or ""
                # A PROHIBITED sub-point states the BAD act, so not_met means the
                # agent correctly avoided it. Listing it under "missed" reads as
                # an accusation — e.g. "Missed: mentioned the old brand name" on a
                # call that scored full marks precisely because they did not.
                prohibited = raw.strip().upper().startswith("PROHIBITED")
                req = raw.split(":", 1)[-1].strip()
                req = req.replace("MANDATORY", "").replace("PROHIBITED", "").strip(" -")
                if not req:
                    continue
                status = sp.get("status")
                if prohibited:
                    if status == "met":
                        missed.append(f"BREACH - {req[:140]}")
                    continue
                if status == "not_met":
                    missed.append(req[:150])
                elif status == "met":
                    met.append(req[:150])
                elif status == "partial":
                    partial.append(req[:150])
                elif status == "unknown":
                    unknown.append(req[:150])
            return missed, met, partial, unknown

        changes = []
        for c1, c2 in zip(a1["criteria"], a2["criteria"]):
            if c1["points_awarded"] == c2["points_awarded"]:
                continue
            missed, met, partial, unknown = describe(c2)
            quote = next((e.get("quote", "") for sp in c2["subpoints"]
                          for e in (sp.get("evidence") or []) if e.get("quote")), "")
            ts = next((e.get("timestamp") for sp in c2["subpoints"]
                       for e in (sp.get("evidence") or []) if e.get("quote")), None)
            changes.append({
                "criterion": c1["criterion_id"],
                "name": c1["criterion_name"],
                "before": c1["points_awarded"], "after": c2["points_awarded"],
                "max": c1["max_points"],
                "verdict": "improved" if c2["points_awarded"] > c1["points_awarded"] else "reduced",
                "missed": missed[:4],
                "partial": partial[:3],
                "unknown": unknown[:3],
                "metCount": len(met),
                "totalPoints": len(c2.get("subpoints", [])),
                "evidence": quote[:220], "timestamp": ts,
            })

        cm1 = [x["code"] for x in a1["critical_misses"] if x["observed"] == "yes"]
        cm2 = [x["code"] for x in a2["critical_misses"] if x["observed"] == "yes"]
        rows.append({
            "id": cid, "agent": c.get("agent"), "customer": c.get("customer"),
            "date": (c.get("start_time") or "")[:10],
            "durationSec": c.get("duration_seconds") or 0,
            "summary": (c.get("summary") or "")[:300],
            "crmLink": f"https://crm.zoho.in/crm/tab/Calls/{cid}",
            "before": {"score": s1["final_score"], "tier": s1["tier"], "autoZero": cm1},
            "after": {"score": s2["final_score"], "tier": s2["tier"], "autoZero": cm2},
            "delta": (None if s1["final_score"] is None or s2["final_score"] is None
                      else round(s2["final_score"] - s1["final_score"], 1)),
            "criterionChanges": sorted(changes, key=lambda x: -abs(x["after"] - x["before"])),
            "allCriteria": [{"criterion": c["criterion_id"], "name": c["criterion_name"],
                             "points": c["points_awarded"], "max": c["max_points"],
                             "label": c["score_label"],
                             "missed": describe(c)[0][:3],
                             "partial": describe(c)[2][:3],
                             "unknown": describe(c)[3][:3],
                             "evidence": next((e.get("quote","")[:200] for sp in c["subpoints"]
                                               for e in (sp.get("evidence") or []) if e.get("quote")), "")}
                            for c in a2["criteria"]],
        })
        d = rows[-1]["delta"]
        print(f"  [{n}] {cid[-8:]} {round((c['duration_seconds'] or 0)/60):>3}min  "
              f"v1={s1['final_score']}  v2={s2['final_score']}  "
              f"delta={d:+.1f}" if d is not None else "")

    rows.sort(key=lambda x: -abs(x["delta"] or 0))
    OUT.write_text(json.dumps({"generatedAt": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
                               "note": "v1 vs v2.1, both at temperature 0",
                               "calls": rows}, ensure_ascii=False))
    print(f"\n✅ {OUT}  ({len(rows)} calls)")


if __name__ == "__main__":
    main()
