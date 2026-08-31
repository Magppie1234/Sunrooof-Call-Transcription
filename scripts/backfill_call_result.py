#!/usr/bin/env python3
"""Backfill Call_Result for calls that were already marked synced, but whose
Zoho Call_Result is still empty — found via audit_zoho_sync.py: a call's
call_outcome apparently became mappable (e.g. resummarized from 'unclear' to
a concrete outcome) sometime after its one-time sync already ran, so the
disposition was never pushed. Safe by construction: sync_one()'s Result path
only ever writes when Zoho's current value is empty, so this can only fill a
gap, never overwrite anything.

Deliberately excludes the known speaker-swap-bug call IDs (--exclude-file) —
those get corrected via the reprocessing + separate reconciliation pass, not
this generic backfill.

Usage:
    python scripts/backfill_call_result.py --dry-run
    python scripts/backfill_call_result.py --exclude-file /tmp/swapped_call_ids.txt
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_notes_to_zoho import (  # noqa: E402
    ZohoAuth, sync_one, OUTCOME_TO_RESULT, SYNCED_FILE, sb_headers,
)

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def fetch_rows(call_ids):
    rows = {}
    for i in range(0, len(call_ids), 200):
        chunk = call_ids[i:i + 200]
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(),
                          params={"select": "call_id,call_outcome", "call_id": f"in.({','.join(chunk)})"}, timeout=30)
        r.raise_for_status()
        for row in r.json():
            rows[row["call_id"]] = row
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--exclude-file")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    excluded = set()
    if args.exclude_file and Path(args.exclude_file).exists():
        excluded = set(Path(args.exclude_file).read_text().strip().split(","))

    all_synced = json.loads(SYNCED_FILE.read_text())
    pool = [c for c in all_synced if c not in excluded]
    if args.limit:
        pool = pool[:args.limit]
    print(f"Checking {len(pool)} synced call(s) for a mapped-but-unwritten Call_Result "
          f"({len(excluded)} excluded)\n")

    rows = fetch_rows(pool)
    auth = ZohoAuth()
    checked = filled = already_ok = no_mapping = failed = 0

    for i, cid in enumerate(pool, 1):
        if i % 200 == 0:
            try:
                auth.refresh()
            except Exception as e:
                print(f"  ⚠ proactive token refresh failed, continuing with current token: {e}")

        row = rows.get(cid)
        expected = OUTCOME_TO_RESULT.get((row or {}).get("call_outcome"))
        if not expected:
            no_mapping += 1
            continue
        checked += 1

        if args.dry_run:
            continue
        try:
            r = sync_one(cid, auth, result=expected)
            if r["result"] and r["result"].startswith("wrote"):
                filled += 1
                print(f"  ✅ {cid}: {r['result']}")
            elif r["result"] and r["result"].startswith("skipped"):
                already_ok += 1
            else:
                failed += 1
                print(f"  ❌ {cid}: {r['result']}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {cid}: {e}")
        time.sleep(0.3)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}{checked} had a mapped outcome, "
          f"{filled} filled, {already_ok} already had a value, {no_mapping} no mapping, {failed} failed")


if __name__ == "__main__":
    main()
