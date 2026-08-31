#!/usr/bin/env python3
"""One-time reconciliation for the 739 calls whose agent/customer speaker
labels were swapped (leftover "Magppie" brand-detection regex never matched
"Sunrooof" — see the fixed COMPANY_RE in summarize_calls.py /
build_ci_dataset.py). Their Supabase summaries have been regenerated with the
corrected speaker labels; this pushes the corrected Note / Call_Result / City
to Zoho for exactly those 739 calls.

This is a deliberate, narrow exception to the write-only-if-empty policy that
governs every other write path in this project (sync_one() in
sync_notes_to_zoho.py, used by the bulk sync and the dashboard's Update CRM
button): the value currently sitting in Zoho for these specific calls is OUR
OWN past mistake — extracted from a transcript with agent/customer swapped —
not something a human agent typed in. Correcting it is fixing our error, not
overwriting real data. This script only ever touches the exact call IDs in
--ids-file; it has no path to any other call, so it cannot be accidentally
run wider than the known bug's blast radius.

Note is updated via the normal safe path (only ever replaces a note that
already carries our own marker). Call_Result and City are force-overwritten
for this bounded set only, after fetching Supabase's corrected value.

Usage:
    python scripts/reconcile_swapped_calls.py --dry-run
    python scripts/reconcile_swapped_calls.py
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
    ZohoAuth, zreq, zget, compose_note, OUTCOME_TO_RESULT, get_our_note,
    get_lead_link, CITY_FIELD_BY_MODULE, sb_headers,
)

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

BASE = Path(__file__).resolve().parent.parent
DEFAULT_IDS_FILE = BASE / "out" / "swapped_call_ids.txt"


def fetch_rows(call_ids):
    cols = ("call_id,agent,customer,call_outcome,summary,next_action,action_items,"
            "objections,customer_sentiment,location,analysis")
    rows = {}
    for i in range(0, len(call_ids), 100):
        chunk = call_ids[i:i + 100]
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(),
                          params={"select": cols, "call_id": f"in.({','.join(chunk)})"}, timeout=30)
        r.raise_for_status()
        for row in r.json():
            rows[row["call_id"]] = row
    return rows


def reconcile_one(cid, row, auth, dry_run=False):
    out = {"call_id": cid, "note": None, "result": None, "city": None}
    note = compose_note(row)
    result = OUTCOME_TO_RESULT.get(row.get("call_outcome"))
    city = (row.get("location") or "").strip() or None

    if dry_run:
        out["note"] = f"would set note (headline: {note.splitlines()[1] if note else None!r})"
        out["result"] = f"would force-write {result!r}" if result else "no mapping"
        out["city"] = f"would force-write {city!r}" if city else "none extracted"
        return out

    # Note — safe path: only ever replaces a note that already has our marker.
    if note:
        existing = get_our_note(cid, auth)
        if existing:
            if existing.get("Note_Content") != note:
                r = zreq("put", "Notes", auth, json={"data": [{"id": existing["id"], "Note_Content": note}]})
                r.raise_for_status()
                out["note"] = "updated"
            else:
                out["note"] = "already correct"
        else:
            r = zreq("post", f"Calls/{cid}/Notes", auth, json={"data": [{"Note_Content": note}]})
            r.raise_for_status()
            out["note"] = "created"

    # Result — FORCE overwrite (the exception this script exists for).
    if result:
        try:
            r = zreq("put", f"Calls/{cid}", auth, json={"data": [{"id": cid, "Call_Result": result}]})
            r.raise_for_status()
            out["result"] = f"force-wrote {result!r}"
        except Exception as e:
            out["result"] = f"failed: {e}"

    # City — FORCE overwrite, same reasoning.
    if city:
        try:
            link = get_lead_link(cid, auth)
            if not link:
                out["city"] = "skipped (no linked Lead/Contact/Deal/Account)"
            else:
                lead_id, module = link
                city_field = CITY_FIELD_BY_MODULE.get(module)
                if city_field:
                    r = zreq("put", f"{module}/{lead_id}", auth,
                              json={"data": [{"id": lead_id, city_field: city}]})
                    r.raise_for_status()
                    out["city"] = f"force-wrote {city_field}={city!r} on {module} {lead_id}"
                else:
                    out["city"] = f"skipped (unhandled module {module})"
        except Exception as e:
            out["city"] = f"failed: {e}"

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids-file", default=str(DEFAULT_IDS_FILE))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY"); sys.exit(1)

    call_ids = Path(args.ids_file).read_text().strip().split(",")
    if args.limit:
        call_ids = call_ids[:args.limit]
    print(f"{'[dry-run] ' if args.dry_run else ''}Reconciling {len(call_ids)} known speaker-swap-bug call(s)\n")

    rows = fetch_rows(call_ids)
    missing = [c for c in call_ids if c not in rows]
    if missing:
        print(f"⚠ {len(missing)} call(s) have no Supabase summary row (skipping): {missing[:5]}{'...' if len(missing) > 5 else ''}")

    auth = None if args.dry_run else ZohoAuth()
    done = failed = 0
    for i, cid in enumerate(call_ids, 1):
        row = rows.get(cid)
        if not row:
            continue
        if not args.dry_run and i % 200 == 0:
            try:
                auth.refresh()
            except Exception as e:
                print(f"  ⚠ proactive token refresh failed, continuing with current token: {e}")
        try:
            r = reconcile_one(cid, row, auth, dry_run=args.dry_run)
            print(f"── {cid}: note={r['note']} | result={r['result']} | city={r['city']}")
            done += 1
        except Exception as e:
            print(f"  ❌ {cid}: {e}")
            failed += 1
        if not args.dry_run:
            time.sleep(0.3)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}✅ {done} processed, {failed} failed, {len(missing)} had no summary yet")


if __name__ == "__main__":
    main()
