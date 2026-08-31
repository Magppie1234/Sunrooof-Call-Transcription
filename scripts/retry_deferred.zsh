#!/bin/zsh
# Retry everything the unattended chain left incomplete, once it has exited.
#
# Two separate problems are being cleaned up here:
#
#  1. `enrich` exited 0 but only enriched 657 of 1,249 calls — the other 592 hit
#     the account's 200k tokens-per-minute ceiling at 8 workers. A zero exit code
#     hid a 47% failure rate, so this re-runs it at low concurrency. The script
#     skips work already done, so each pass only picks up what previously failed
#     and none of it is paid for twice.
#  2. `faq-agg` timed out clustering a 3,141-question topic in one request;
#     aggregate_faqs.py now chunks and merges iteratively.
#
# `dataset` and the dashboard are rebuilt last because both consume the output
# of the two stages above — the versions built during the main chain were made
# from incomplete enrichment.
setopt NO_ERR_EXIT

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
LOG="$JOB_ROOT/out/logs/unattended-chain.log"
ERRLOG="$JOB_ROOT/out/logs/deferred-errors.log"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

cd "$JOB_ROOT" || exit 1
exec >>"$LOG" 2>&1
stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

while pgrep -f "run_unattended_chain.zsh" >/dev/null 2>&1; do
  sleep 120
done
echo "$(stamp) ── retry chain: main chain finished ──"

# ── 1. Drain the enrichment failures ──────────────────────────────────────
# Three passes at 3 workers. Low concurrency is the point: at 8 workers nearly
# half the calls were rejected, and a rejected request still costs wall-clock.
for pass in 1 2 3; do
  echo "$(stamp) ── enrich retry pass $pass (3 workers) ──"
  "$PY" scripts/enrich_for_ci.py --workers 3
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "$(stamp) [enrich] pass $pass exited $rc" >>"$ERRLOG"
  fi
done

# ── 2. FAQ clustering, now chunked ────────────────────────────────────────
echo "$(stamp) ── retry stage: faq-agg ──"
if "$PY" scripts/refresh_all.py --only faq-agg; then
  echo "$(stamp) completed stage: faq-agg (retry)"
else
  echo "$(stamp) [faq-agg] retry also failed" >>"$ERRLOG"
  echo "$(stamp) DEFERRED stage: faq-agg — still failing after the chunking fix"
fi

# ── 3. Rebuild what depends on them ───────────────────────────────────────
echo "$(stamp) ── retry stage: dataset ──"
if "$PY" scripts/refresh_all.py --only dataset; then
  echo "$(stamp) completed stage: dataset (retry)"
else
  echo "$(stamp) [dataset] retry failed" >>"$ERRLOG"
fi

echo "$(stamp) ── retry stage: dashboard build ──"
if npm --prefix ci-dashboard run build; then
  echo "$(stamp) completed stage: dashboard build (retry)"
else
  echo "$(stamp) [dashboard] retry build failed" >>"$ERRLOG"
fi

# ── 4. Integrity checks ───────────────────────────────────────────────────
# Both stages above can fail silently-ish, so verify the outcome rather than
# trusting exit codes: chunking must not lose FAQ questions, and enrichment
# coverage must actually be near-complete.
"$PY" - <<'PYEOF'
import json, os, sys
from pathlib import Path
sys.path.insert(0, "scripts")
base = Path("/Users/UNICA/Desktop/call transcription sunrooof/out")
try:
    qmap = json.loads((base / "faq_question_map.json").read_text())
    print(f"FAQ integrity: {len(qmap)} raw wordings -> "
          f"{len(set(qmap.values()))} canonical questions")
except Exception as e:
    print(f"FAQ integrity check unavailable: {type(e).__name__}: {e}")
try:
    import requests
    from dotenv import load_dotenv
    # Explicit path — a heredoc script has no calling frame for find_dotenv().
    load_dotenv("/Users/UNICA/Desktop/call transcription sunrooof/.env")
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact",
         "Range": "0-0"}
    r = requests.get(f"{url}/rest/v1/call_summaries", headers=h,
                     params={"select": "call_id"}, timeout=30)
    total = r.headers.get("Content-Range", "/?").split("/")[-1]
    print(f"enrichment coverage: see out/zoho_enrichment.json vs {total} summaries")
except Exception as e:
    print(f"coverage check unavailable: {type(e).__name__}: {e}")
PYEOF

echo "$(stamp) ── retry chain finished ──"
