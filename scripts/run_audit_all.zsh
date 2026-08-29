#!/bin/zsh
# Audit every call, and keep going until they are all done.
#
# The run is many hours long, so a single invocation is a single point of
# failure: an unhandled exception, a dropped connection or a machine sleep
# would leave it half finished with nothing to restart it. This supervises
# instead — summarize_calls.py --with-audit skips anything already audited, so
# relaunching costs nothing and never re-pays for completed work.
#
# Stops when Supabase reports zero unaudited calls, or when several consecutive
# passes make no progress (which means something is wrong that retrying cannot
# fix, and hammering the API would just burn money).
setopt NO_ERR_EXIT

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
LOG="$JOB_ROOT/out/logs/qa-audit-run.log"
SUP="$JOB_ROOT/out/logs/qa-audit-supervisor.log"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

cd "$JOB_ROOT" || exit 1
exec >>"$SUP" 2>&1
stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

remaining() {
  "$PY" - <<'PYEOF' 2>/dev/null
import os, requests
from dotenv import load_dotenv
# Explicit path: bare load_dotenv() locates .env by walking the call stack, and
# a script piped in via heredoc has no calling frame, so it dies on an
# AssertionError before doing anything.
load_dotenv("/Users/UNICA/Desktop/call transcription sunrooof/.env")
u, k = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
h = {"apikey": k, "Authorization": f"Bearer {k}", "Prefer": "count=exact", "Range": "0-0"}
try:
    # Counts only what this run targets: unaudited calls from SINCE onward.
    # Counting the whole corpus would never reach zero while June is deferred,
    # so the supervisor would loop until its stale-detector tripped.
    aud = int(requests.get(f"{u}/rest/v1/call_summaries", headers=h,
                           params={"select": "call_id",
                                   "start_time": f"gte.{os.environ['AUDIT_SINCE']}T00:00:00",
                                   "call_quality_audit": "is.null"}, timeout=30)
              .headers["Content-Range"].split("/")[-1])
    print(aud)
except Exception:
    print("ERR")
PYEOF
}

# July onward first; pre-July calls are deferred, not discarded — rerun with
# AUDIT_SINCE=2026-06-01 to pick them up afterwards.
export AUDIT_SINCE="${AUDIT_SINCE:-2026-07-01}"
echo "$(stamp) ── audit supervisor started (from $AUDIT_SINCE) ──"
stale=0
prev=-1
for attempt in {1..200}; do
  left="$(remaining)"
  if [[ "$left" == "ERR" || -z "$left" ]]; then
    echo "$(stamp) could not read remaining count; retrying in 5m"
    sleep 300; continue
  fi
  echo "$(stamp) pass $attempt — $left call(s) from $AUDIT_SINCE still unaudited"
  if [[ "$left" -eq 0 ]]; then
    echo "$(stamp) ✅ every call audited"
    break
  fi
  if [[ "$left" -eq "$prev" ]]; then
    stale=$((stale + 1))
    if [[ $stale -ge 3 ]]; then
      echo "$(stamp) ⛔ three passes with no progress ($left stuck) — stopping rather than burning tokens"
      echo "$(stamp) [audit] stalled with $left unaudited" >>"$JOB_ROOT/out/logs/deferred-errors.log"
      break
    fi
  else
    stale=0
  fi
  prev="$left"

  "$PY" scripts/summarize_calls.py --with-audit --force --since "$AUDIT_SINCE" \
      --workers 12 --min-interval 0.25 >>"$LOG" 2>&1
  echo "$(stamp) pass $attempt exited $?"
  sleep 20
done
echo "$(stamp) ── audit supervisor finished ──"
