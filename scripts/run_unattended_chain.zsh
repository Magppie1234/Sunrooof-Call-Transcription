#!/bin/zsh
# Unattended continuation: wait for the summary backlog to drain, then rebuild
# every downstream analytic and the dashboard.
#
# Failure policy: a failing stage is recorded in out/logs/deferred-errors.log
# and the chain moves on. Nothing here is destructive, every stage is
# idempotent, and a stage that fails now can simply be re-run later — so
# stopping the whole chain on one bad stage would cost progress for no safety.
#
# Deliberately NOT included: the `zoho` stage. That one pushes AI-written notes
# out to live customer records in Zoho CRM, which is an external write that is
# awkward to reverse. It waits for a human to say go.
setopt NO_ERR_EXIT

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
LOG="$JOB_ROOT/out/logs/unattended-chain.log"
ERRLOG="$JOB_ROOT/out/logs/deferred-errors.log"
STATE="$JOB_ROOT/out/unattended_state"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

mkdir -p "$STATE" "$JOB_ROOT/out/logs"
cd "$JOB_ROOT" || exit 1
exec >>"$LOG" 2>&1

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }
defer() { echo "$(stamp) [$1] $2" >>"$ERRLOG"; }

echo "$(stamp) ── unattended chain started ──"

# ── Wait for the summary backlog ──────────────────────────────────────────
# Polls Supabase rather than scraping the log, so it is correct regardless of
# how many loop cycles it took to get there.
wait_for_summaries() {
  local idle=0
  while true; do
    local remaining
    remaining="$("$PY" - <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
try:
    import summarize_calls as sc
    done = sc.fetch_summarized_ids()
    todo = [p for p in sc.TDIR.glob("*.json")
            if p.name.removesuffix(".mp3.json") not in done]
    print(len(todo))
except Exception:
    print("ERR")
PYEOF
)"
    if [[ "$remaining" == "ERR" || -z "$remaining" ]]; then
      defer "wait_for_summaries" "could not read remaining count; retrying"
      sleep 300; continue
    fi
    echo "$(stamp) summaries remaining: $remaining"
    if [[ "$remaining" -le 5 ]]; then
      # A handful of permanently-failing calls must not block the chain forever.
      echo "$(stamp) backlog drained (<=5 left)"
      return 0
    fi
    idle=$((idle + 1))
    if [[ $idle -gt 180 ]]; then      # ~15h at 5-min polls
      defer "wait_for_summaries" "gave up waiting; $remaining still unsummarized"
      return 0
    fi
    sleep 300
  done
}

wait_for_summaries

# ── Downstream analytics ──────────────────────────────────────────────────
run_stage() {
  local name="$1"
  if [[ -f "$STATE/$name.done" ]]; then
    echo "$(stamp) skipping completed stage: $name"
    return 0
  fi
  echo "$(stamp) ── stage: $name ──"
  if "$PY" scripts/refresh_all.py --only "$name"; then
    touch "$STATE/$name.done"
    echo "$(stamp) completed stage: $name"
  else
    defer "$name" "refresh_all.py --only $name failed (exit $?)"
    echo "$(stamp) DEFERRED stage: $name — continuing"
  fi
}

for stage in regions regions-apply names faqs faq-agg enrich dataset; do
  run_stage "$stage"
done

# ── Dashboard ─────────────────────────────────────────────────────────────
if [[ ! -f "$STATE/dashboard.done" ]]; then
  echo "$(stamp) ── stage: dashboard build ──"
  if npm --prefix ci-dashboard run build; then
    touch "$STATE/dashboard.done"
    echo "$(stamp) completed stage: dashboard build"
  else
    defer "dashboard" "npm run build failed"
  fi
fi

echo "$(stamp) ── unattended chain finished ──"
if [[ -s "$ERRLOG" ]]; then
  echo "$(stamp) deferred problems recorded in $ERRLOG:"
  cat "$ERRLOG"
fi
echo "$(stamp) NOT run (needs a human): zoho note write-back; Sarvam transcription (no credits)"
