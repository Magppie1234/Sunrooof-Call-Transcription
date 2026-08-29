#!/usr/bin/env python3
"""Run the same calls through two models and compare their audits.

Answers the question the model choice actually turns on: does the cheaper model
apply the mandatory gates and the scorecard consistently, or does it drift? Two
models scoring the same call 40 points apart means neither can be trusted alone.

Writes nothing to Supabase — this is a read-only comparison.

Usage:
    .venv/bin/python scripts/pilot_call_quality.py --limit 20
    .venv/bin/python scripts/pilot_call_quality.py --limit 20 --models gpt-4.1-mini,gpt-4.1
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import summarize_calls as sc  # noqa: E402
from call_quality import build_audit, validate  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out" / "pilot_call_quality.json"


def pick_calls(limit):
    """Longest transcripts first — a 40-second call exercises almost none of the
    scorecard, so short calls would make the two models look falsely identical."""
    scored = []
    for p in sc.TDIR.glob("*.json"):
        try:
            entries = json.loads(p.read_text()).get("diarized_transcript", {}).get("entries", [])
        except (OSError, ValueError):
            continue
        if len(entries) >= 20:
            scored.append((len(entries), p.name.removesuffix(".mp3.json")))
    scored.sort(reverse=True)
    return [cid for _, cid in scored[:limit]]


def audit_one(client, model, cid, token):
    path = sc.TDIR / f"{cid}.mp3.json"
    entries = json.loads(path.read_text()).get("diarized_transcript", {}).get("entries", [])
    meta = sc.fetch_meta(token, cid)
    if not meta:
        return None
    agent_sid = sc.agent_speaker_id(entries)
    plain = sc.render_transcript(entries, agent_sid, meta["agent"], meta["customer"])
    stamped = sc.render_transcript_timestamped(entries, agent_sid, meta["agent"], meta["customer"])

    result = sc.summarize(client, meta, stamped, with_audit=True, model=model)
    sc.verify_evidence(result, plain)
    audit = sc.build_call_quality_audit(result, meta, cid)
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--models", default="gpt-4.1-mini,gpt-4.1")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    if not sc.API_KEY:
        print("❌ No API key configured — set OPENAI_API_KEY in .env"); sys.exit(1)

    client = sc.OpenAI(api_key=sc.API_KEY, base_url=sc.BASE_URL)
    token = sc.get_token()
    calls = pick_calls(args.limit)
    print(f"📋 {len(calls)} calls x {len(models)} models\n")

    results = {m: {} for m in models}
    for n, cid in enumerate(calls, 1):
        for model in models:
            try:
                audit = audit_one(client, model, cid, token)
            except Exception as e:
                print(f"  ❌ [{n}] {cid} {model}: {type(e).__name__}: {e}")
                continue
            if not audit:
                continue
            results[model][cid] = audit
            s = audit["score"]
            print(f"  [{n}] {cid} {model:14s} {str(s['final_score']):>6} {s['tier']:<10} "
                  f"{'AUTO-ZERO ' + ','.join(s['auto_zero_codes']) if s['auto_zero'] else ''}")
        print()

    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"💾 wrote {OUT}\n")

    print("=" * 60)
    for model in models:
        audits = list(results[model].values())
        if not audits:
            print(f"{model}: no results"); continue
        scores = [a["score"]["final_score"] for a in audits
                  if a["score"]["final_score"] is not None]
        zeros = sum(1 for a in audits if a["score"]["auto_zero"])
        broken = sum(1 for a in audits if validate(a))
        print(f"{model}:")
        print(f"  n={len(audits)}  mean={statistics.mean(scores):.1f}  "
              f"median={statistics.median(scores):.1f}  "
              f"range={min(scores):.0f}-{max(scores):.0f}")
        print(f"  auto-zeroed: {zeros}/{len(audits)}   failed self-check: {broken}")

    if len(models) == 2:
        a_model, b_model = models
        shared = set(results[a_model]) & set(results[b_model])
        if shared:
            deltas, tier_agree, gate_disagree = [], 0, 0
            for cid in shared:
                a, b = results[a_model][cid], results[b_model][cid]
                sa, sb = a["score"]["final_score"], b["score"]["final_score"]
                if sa is not None and sb is not None:
                    deltas.append(abs(sa - sb))
                if a["score"]["tier"] == b["score"]["tier"]:
                    tier_agree += 1
                ga = {c["criterion_id"]: c["mandatory_gate_passed"] for c in a["criteria"]}
                gb = {c["criterion_id"]: c["mandatory_gate_passed"] for c in b["criteria"]}
                gate_disagree += sum(1 for k in ga if ga[k] != gb.get(k))
            print(f"\nAgreement across {len(shared)} shared calls:")
            print(f"  mean |score difference| : {statistics.mean(deltas):.1f} points")
            print(f"  max  |score difference| : {max(deltas):.1f} points")
            print(f"  same tier               : {tier_agree}/{len(shared)}")
            print(f"  mandatory-gate disagreements: {gate_disagree}")
            print("\nA mean gap under ~5 points and matching tiers on most calls means the")
            print("cheaper model is doing the same job. A wide spread means it is guessing.")


if __name__ == "__main__":
    main()
