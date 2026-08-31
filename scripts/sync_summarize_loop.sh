#!/bin/bash
# Continuously push finished transcripts to Supabase and summarize whatever is
# new. Both stages are idempotent, so this is safe to run alongside an active
# transcription job — it just picks up each batch a few minutes after it lands.
cd "/Users/UNICA/Desktop/call transcription sunrooof" || exit 1
while true; do
  echo "── $(date '+%Y-%m-%dT%H:%M:%S%z') sync+summarize cycle ──"
  ./.venv/bin/python scripts/sync_transcripts_to_supabase.py 2>&1 | tail -3
  # NOT piped through tail: a long summarize run holds every line in the pipe
  # until it exits, so a multi-hour pass looks identical to a hung one. Streamed
  # instead, with PYTHONUNBUFFERED so progress lands in the log as it happens.
  # Each call spends ~45s waiting on generation, so throughput is parallelism,
  # not pacing. The binding constraint is the account's 200k tokens-per-minute
  # ceiling on gpt-4.1-mini, not requests-per-minute: OpenAI reserves the FULL
  # max_completion_tokens against TPM, so each call books ~9.4k whether it uses
  # it or not. 10 workers overran that (17% of calls 429'd and had to be
  # retried on a later cycle); 6 leaves headroom for anything else sharing the
  # same pool. Rejected requests are not billed, so this costs time, not money.
  PYTHONUNBUFFERED=1 ./.venv/bin/python scripts/summarize_calls.py \
      --workers 6 --min-interval 0.4 2>&1
  sleep 180
done
