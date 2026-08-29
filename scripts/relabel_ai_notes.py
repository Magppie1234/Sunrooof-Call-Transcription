#!/usr/bin/env python3
"""One-time migration: every AI-written Zoho Note from before the marker
rename still says "[Call Intelligence]" — not explicit about being
AI-generated. Swap that prefix for the current, unambiguous marker
("[AI-Generated Summary — Sunrooof Call Intelligence]") in place, on Zoho's
live copy, so nobody reading the CRM mistakes an AI note for something a
caller/agent typed manually.

Only ever touches a note that already contains our OWN legacy marker — never
a note without it, so a human-written note can never be matched or edited.

Usage:
    python scripts/relabel_ai_notes.py --dry-run
    python scripts/relabel_ai_notes.py
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_notes_to_zoho import (  # noqa: E402
    ZohoAuth, zreq, NOTE_MARKER, LEGACY_NOTE_MARKER, SYNCED_FILE,
)

BASE = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    call_ids = sorted(json.loads(SYNCED_FILE.read_text())) if SYNCED_FILE.exists() else []
    if args.limit:
        call_ids = call_ids[:args.limit]
    print(f"{'[dry-run] ' if args.dry_run else ''}Checking {len(call_ids)} call(s) for legacy-marker notes\n")

    auth = ZohoAuth()
    relabelled = already_current = no_note = failed = 0
    for i, cid in enumerate(call_ids, 1):
        if i % 200 == 0:
            try:
                auth.refresh()
            except Exception as e:
                print(f"  ⚠ proactive token refresh failed, continuing with current token: {e}")

        try:
            r = zreq("get", f"Calls/{cid}/Notes", auth, params={"fields": "Note_Content"})
            if r.status_code == 204:
                no_note += 1
                continue
            r.raise_for_status()
            notes = r.json().get("data", [])
            target = next((n for n in notes if LEGACY_NOTE_MARKER in (n.get("Note_Content") or "")
                           and NOTE_MARKER not in (n.get("Note_Content") or "")), None)
            if not target:
                already_current += 1
                continue

            new_content = target["Note_Content"].replace(LEGACY_NOTE_MARKER, NOTE_MARKER, 1)
            if args.dry_run:
                print(f"── {cid} would relabel note {target['id']}")
                relabelled += 1
                continue

            r = zreq("put", "Notes", auth, json={"data": [{"id": target["id"], "Note_Content": new_content}]})
            r.raise_for_status()
            relabelled += 1
            if relabelled % 100 == 0:
                print(f"  {relabelled} relabelled...")
        except Exception as e:
            print(f"  ❌ {cid}: {e}")
            failed += 1
        time.sleep(0.3)

    print(f"\n✅ {relabelled} relabelled, {already_current} already current, "
          f"{no_note} had no note, {failed} failed")


if __name__ == "__main__":
    main()
