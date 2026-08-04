#!/bin/zsh
set -euo pipefail

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
STATE_DIR="$JOB_ROOT/out/july_backfill_state"
LOG_DIR="$JOB_ROOT/out/logs"
PID_FILE="$STATE_DIR/runner.pid"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

mkdir -p "$STATE_DIR" "$LOG_DIR"
exec >>"$LOG_DIR/july-backfill.log" 2>&1

if [[ -f "$PID_FILE" ]]; then
  prior_pid="$(<"$PID_FILE")"
  if [[ -n "$prior_pid" ]] && kill -0 "$prior_pid" 2>/dev/null; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') July backfill is already running as PID $prior_pid"
    exit 0
  fi
fi
echo $$ >"$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT INT TERM

cd "$JOB_ROOT"
echo "$(date '+%Y-%m-%dT%H:%M:%S%z') Starting/resuming July backfill"

proxy_status="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/api/audio 2>/dev/null || true)"
if [[ "$proxy_status" != "400" ]]; then
  node scripts/audio_proxy.mjs >>"$LOG_DIR/audio-proxy.log" 2>&1 &
  proxy_pid=$!
  sleep 2
  if ! kill -0 "$proxy_pid" 2>/dev/null; then
    echo "Audio proxy failed to start"
    exit 2
  fi
fi

run_once() {
  marker="$1"
  shift
  if [[ -f "$STATE_DIR/$marker.done" ]]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') Skipping completed stage: $marker"
    return
  fi
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') Running stage: $marker"
  "$@"
  touch "$STATE_DIR/$marker.done"
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') Completed stage: $marker"
}

run_once transcribe "$PY" scripts/batch_transcribe.py \
  --since 2026-07-01 --until 2026-07-31 --min-duration 31 --batch-size 20
run_once upload_transcripts "$PY" scripts/sync_transcripts_to_supabase.py

for stage in regions regions-apply names summaries faqs faq-agg zoho enrich dataset; do
  run_once "$stage" "$PY" scripts/refresh_all.py --only "$stage"
done

run_once dashboard_build npm --prefix ci-dashboard run build

if ! git diff --quiet -- ci-dashboard/src/data/real/dataset.json; then
  git add ci-dashboard/src/data/real/dataset.json
  git commit -m "Refresh July call intelligence dataset"
fi
git push
touch "$STATE_DIR/pushed.done"
echo "$(date '+%Y-%m-%dT%H:%M:%S%z') July backfill and dashboard refresh complete"
