#!/bin/zsh
# Keep the Advanced QA page current while the audit runs.
#
# The page reads a snapshot file rather than querying Supabase, so it only
# shows what was exported. This re-exports and rebuilds every 2 hours, and
# stops once every call is audited and one final refresh has been taken.
#
# Cheap and non-destructive: the export is a read, the build writes only to
# ci-dashboard/dist and the snapshot file. No LLM calls.
setopt NO_ERR_EXIT

JOB_ROOT="/Users/UNICA/Desktop/call transcription sunrooof"
LOG="$JOB_ROOT/out/logs/advanced-qa-refresh.log"
PY="$JOB_ROOT/.venv/bin/python"
export PYTHONUNBUFFERED=1

cd "$JOB_ROOT" || exit 1
exec >>"$LOG" 2>&1
stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

echo "$(stamp) ── Advanced QA refresher started (every 2h) ──"

for round in {1..60}; do
  sleep 7200

  echo "$(stamp) refresh $round"
  "$PY" scripts/export_qa_audits_for_dashboard.py || {
    echo "$(stamp) export failed; will retry next round"; continue; }
  npm --prefix ci-dashboard run build >/dev/null 2>&1 \
    && echo "$(stamp) dashboard rebuilt" \
    || echo "$(stamp) dashboard build failed"

  # Stop once the audit supervisor has finished and this refresh captured it.
  if ! pgrep -f "run_audit_all.zsh" >/dev/null 2>&1; then
    echo "$(stamp) audit supervisor is gone — final refresh taken, stopping"
    break
  fi
done
echo "$(stamp) ── Advanced QA refresher finished ──"
