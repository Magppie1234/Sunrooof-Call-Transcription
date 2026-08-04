#!/usr/bin/env python3
"""
refresh_all.py — run the whole post-transcription pipeline in the right order.

Transcription itself (batch_transcribe.py) is NOT included: it is slow, costs
Sarvam money per run, and you usually want to choose its window yourself.
Everything downstream of it is here.

    python scripts/refresh_all.py                 # full refresh
    python scripts/refresh_all.py --dry-run       # show the plan and stop
    python scripts/refresh_all.py --from summaries  # resume partway

Order matters in two places, both of which have bitten us:
  * aggregate_faqs must run BEFORE build_ci_dataset — it writes
    out/faq_question_map.json, and without it the dataset builder silently
    falls back to fuzzy word-overlap FAQ clustering.
  * backfill_call_states must run before build_ci_dataset too, or every call
    lands in the "Unknown" region bucket.

Each step is skippable and re-runnable: the LLM steps skip calls they have
already processed, so an interrupted run resumes cheaply rather than paying
twice.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = str(BASE / ".venv" / "bin" / "python")

# (key, description, argv, spends_llm)
STEPS = [
    ("regions", "Backfill caller state/city from the linked Zoho Lead/Contact",
     ["scripts/backfill_call_states.py", "--fetch"], False),
    ("regions-apply", "Write those states/cities to Supabase `transcripts`",
     ["scripts/backfill_call_states.py", "--apply"], False),
    ("names", "Normalise company-name mishears everywhere (free, deterministic)",
     ["scripts/clean_names.py"], False),
    ("summaries", "Per-call summaries + scorecards → Supabase `call_summaries`",
     ["scripts/summarize_calls.py"], True),
    ("faqs", "Extract per-call customer questions with verified quotes",
     ["scripts/extract_faqs.py"], True),
    ("faq-agg", "Cluster into canonical FAQs (also writes faq_question_map.json)",
     ["scripts/aggregate_faqs.py"], True),
    ("zoho", "Pull CRM enrichment (lead source, stage, campaign, space type)",
     ["scripts/fetch_zoho_enrichment.py"], False),
    ("enrich", "Call-intelligence enrichment (sentiment journey, readiness, …)",
     ["scripts/enrich_for_ci.py", "--workers", "8"], True),
    ("dataset", "Join everything into ci-dashboard/src/data/real/dataset.json",
     ["scripts/build_ci_dataset.py"], True),
]


def run(step_key, desc, argv, i, total):
    print(f"\n{'='*72}\n▶  [{i}/{total}] {step_key} — {desc}\n{'='*72}", flush=True)
    t0 = time.time()
    r = subprocess.run([PY] + argv, cwd=BASE)
    mins = (time.time() - t0) / 60
    if r.returncode != 0:
        print(f"\n❌ step '{step_key}' failed (exit {r.returncode}) after {mins:.1f} min.")
        print(f"   Fix it, then resume with:  python scripts/refresh_all.py --from {step_key}")
        sys.exit(r.returncode)
    print(f"✅ {step_key} finished in {mins:.1f} min", flush=True)


def main():
    keys = [s[0] for s in STEPS]
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", choices=keys, default=keys[0],
                    help="resume from this step")
    ap.add_argument("--only", choices=keys, help="run just this one step")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = ap.parse_args()

    if args.only:
        plan = [s for s in STEPS if s[0] == args.only]
    else:
        plan = STEPS[keys.index(args.start):]

    print(f"Plan ({len(plan)} step(s)):")
    for s in plan:
        print(f"   {'💰' if s[3] else '  '} {s[0]:14} {s[1]}")
    print("\n💰 = spends LLM tokens (gpt-4.1-mini). Steps skip work already done,")
    print("   so re-running after an interruption does not pay twice.")
    if args.dry_run:
        return

    t0 = time.time()
    for i, (key, desc, argv, _) in enumerate(plan, 1):
        run(key, desc, argv, i, len(plan))
    print(f"\n🎉 all done in {(time.time()-t0)/60:.1f} min.")
    print("   Rebuild the dashboard:  cd ci-dashboard && npm run build && npm run preview -- --port 5199")


if __name__ == "__main__":
    main()
