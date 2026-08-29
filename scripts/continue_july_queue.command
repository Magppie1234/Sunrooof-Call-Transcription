#!/bin/zsh

job_root="/Users/UNICA/Desktop/call transcription sunrooof"
pid_file="$job_root/out/july_backfill_state/runner.pid"

while [[ -f "$pid_file" ]]; do
  runner_pid="$(<"$pid_file")"
  if [[ -z "$runner_pid" ]] || ! kill -0 "$runner_pid" 2>/dev/null; then
    break
  fi
  sleep 60
done

exec /bin/zsh "$job_root/scripts/run_july_backfill.zsh"
