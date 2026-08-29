#!/bin/zsh
# Transcribe the remaining May/June windows back-to-back, one Sarvam job at a
# time. Waits out whatever transcription is already running so two batches
# never bill against Sarvam concurrently.
#
# Windows are split at the audio-retention boundary: Zoho's phonebridge serves
# recordings from 2026-05-11 onward, but returns an empty body for anything
# earlier, so May 1-10 is deliberately excluded — it needs the Ozonetel CSV
# export (S3 keeps the mp3s longer) and is not attemptable from here.
set -uo pipefail

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
STATE="$JOB_ROOT/out/may_june_state"
LOG="$JOB_ROOT/out/logs/may-june-chain.log"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

mkdir -p "$STATE" "$JOB_ROOT/out/logs"
cd "$JOB_ROOT" || exit 1
exec >>"$LOG" 2>&1

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

# Wait for any in-flight transcription to exit before starting our own.
while pgrep -f "transcribe_ozonetel_july.py" >/dev/null 2>&1; do
  echo "$(stamp) waiting for the June 1-15 job to finish..."
  sleep 120
done

# The downloads for these windows go through the local proxy, not S3.
proxy_status="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/api/audio 2>/dev/null || true)"
if [[ "$proxy_status" != "400" && "$proxy_status" != "500" ]]; then
  echo "$(stamp) starting audio proxy"
  node scripts/audio_proxy.mjs >>"$JOB_ROOT/out/logs/audio-proxy.log" 2>&1 &
  sleep 3
fi

stage() {
  local marker="$1" since="$2" until="$3"
  if [[ -f "$STATE/$marker.done" ]]; then
    echo "$(stamp) skipping completed stage $marker"
    return 0
  fi
  echo "$(stamp) ── stage $marker: $since -> $until ──"
  "$PY" scripts/batch_transcribe.py --since "$since" --until "$until" \
      --min-duration 30 --batch-size 20
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "$(stamp) STAGE FAILED $marker (exit $rc) — stopping chain"
    return $rc
  fi
  touch "$STATE/$marker.done"
  echo "$(stamp) completed stage $marker"
}

stage june_16_30 2026-06-16 2026-06-30 || exit $?
stage may_11_31  2026-05-11 2026-05-31 || exit $?

echo "$(stamp) chain complete — May 11-31 and June 16-30 transcribed"
echo "$(stamp) NOT attempted: May 1-10 (audio purged from Zoho; needs Ozonetel CSV)"
