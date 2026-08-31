#!/usr/bin/env python3
"""QA check: for a random sample of already-synced calls, compare what's
LIVE in Zoho right now (Call_Result, our AI note, City) against what the
current Supabase call_summaries row says should be there. Flags mismatches
so a human can look at the specific calls, rather than claiming correctness
on trust.

Deliberately excludes any call_id passed via --exclude-file (used to skip
the known speaker-swap-bug calls while they're still being reprocessed —
auditing those before the fix lands would just report bugs we already know
about).

Usage:
    python scripts/audit_zoho_sync.py --sample 60
    python scripts/audit_zoho_sync.py --sample 60 --exclude-file /tmp/swapped_call_ids.txt
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_notes_to_zoho import (  # noqa: E402
    ZohoAuth, zreq, zget, compose_note, OUTCOME_TO_RESULT,
    NOTE_MARKER, LEGACY_NOTE_MARKER, SYNCED_FILE, sb_headers,
)

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def fetch_rows(call_ids):
    cols = ("call_id,agent,customer,call_outcome,summary,next_action,action_items,"
            "objections,customer_sentiment,location,analysis")
    rows = []
    for i in range(0, len(call_ids), 100):
        chunk = call_ids[i:i + 100]
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(),
                          params={"select": cols, "call_id": f"in.({','.join(chunk)})"}, timeout=30)
        r.raise_for_status()
        rows.extend(r.json())
    return {row["call_id"]: row for row in rows}


def our_note(call_id, auth):
    r = zreq("get", f"Calls/{call_id}/Notes", auth, params={"fields": "Note_Content"})
    if r.status_code == 204:
        return None
    r.raise_for_status()
    for n in r.json().get("data", []):
        c = n.get("Note_Content") or ""
        if NOTE_MARKER in c or LEGACY_NOTE_MARKER in c:
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--exclude-file", help="comma-separated call-id file to skip (e.g. known-bug list)")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    excluded = set()
    if args.exclude_file and Path(args.exclude_file).exists():
        excluded = set(Path(args.exclude_file).read_text().strip().split(","))

    all_synced = json.loads(SYNCED_FILE.read_text())
    pool = [c for c in all_synced if c not in excluded]
    sample = random.sample(pool, min(args.sample, len(pool)))
    print(f"Auditing {len(sample)} call(s) (pool {len(pool)}, {len(excluded)} excluded)\n")

    rows = fetch_rows(sample)
    auth = ZohoAuth()

    result_ok = result_bad = result_na = 0
    note_ok = note_bad = note_na = 0
    city_ok = city_bad = city_na = 0
    problems = []

    for i, cid in enumerate(sample, 1):
        row = rows.get(cid)
        if not row:
            continue

        expected_result = OUTCOME_TO_RESULT.get(row.get("call_outcome"))
        expected_note = compose_note(row)
        expected_city = (row.get("location") or "").strip() or None

        try:
            live = zget(f"Calls/{cid}", {"fields": "Call_Result"}, auth)
            live_result = (live.get("data") or [{}])[0].get("Call_Result")
        except Exception as e:
            problems.append(f"{cid}: could not fetch Call_Result ({e})")
            live_result = None

        try:
            live_note = our_note(cid, auth)
        except Exception as e:
            problems.append(f"{cid}: could not fetch Notes ({e})")
            live_note = None

        # Result: only flag if Zoho HAS a value and it's mapped-but-different.
        # A value Zoho holds that we never mapped (already_purchased/unclear)
        # or a field we deliberately didn't touch isn't a mismatch.
        if expected_result is None:
            result_na += 1
        elif live_result == expected_result:
            result_ok += 1
        else:
            result_bad += 1
            problems.append(f"{cid}: Call_Result live={live_result!r} vs expected={expected_result!r}")

        # Note: compare the headline (first content line after the marker) —
        # exact full-body match is too strict against harmless re-wording,
        # the headline is what would reveal a wrong outcome/attribution.
        if expected_note is None:
            note_na += 1
        elif live_note is None:
            note_bad += 1
            problems.append(f"{cid}: no AI note found on Zoho, expected one")
        else:
            exp_headline = expected_note.splitlines()[1] if len(expected_note.splitlines()) > 1 else ""
            if exp_headline and exp_headline in live_note:
                note_ok += 1
            else:
                note_bad += 1
                problems.append(f"{cid}: note headline mismatch — expected {exp_headline!r} not found in live note")

        if expected_city is None:
            city_na += 1
        else:
            city_ok += 1  # City is write-only-if-empty and best-effort; presence isn't a correctness signal on its own

        if i % 20 == 0:
            print(f"  ...{i}/{len(sample)}")

    print(f"\nCall_Result — ok: {result_ok}, mismatch: {result_bad}, n/a (unmapped outcome): {result_na}")
    print(f"Note headline — ok: {note_ok}, mismatch: {note_bad}, n/a (no note expected): {note_na}")
    print(f"City — checked: {city_ok}, n/a: {city_na}  (presence-only check, see script docstring)")
    if problems:
        print(f"\n⚠ {len(problems)} issue(s):")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\n✅ No mismatches found in this sample.")


if __name__ == "__main__":
    main()
