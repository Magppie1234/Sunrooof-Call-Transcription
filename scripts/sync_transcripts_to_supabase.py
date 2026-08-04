#!/usr/bin/env python3
"""
sync_transcripts_to_supabase.py — Upload local transcripts (out/transcripts/*.mp3.json)
into the Supabase `transcripts` table so the deployed dashboard (which has no
local disk) can see them.

Run this after batch_transcribe.py / clean_names.py, any time new transcripts
have been generated locally. Safe to re-run — upserts by call_id (PostgREST
`Prefer: resolution=merge-duplicates`), so no need to track what's already
uploaded.

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env, and the
`transcripts` table created (see dashboard/supabase-schema.sql).
"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

BASE  = Path(__file__).resolve().parent.parent
TDIR  = BASE / "out" / "transcripts"
URL   = os.getenv("SUPABASE_URL")
KEY   = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BATCH_SIZE = 100

def headers():
    return {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

def upload_batch(rows):
    r = requests.post(f"{URL}/rest/v1/transcripts", headers=headers(),
                       data=json.dumps(rows), timeout=30)
    r.raise_for_status()

def main():
    if not URL or not KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    files = sorted(TDIR.glob("*.mp3.json"))
    print(f"📄 {len(files)} local transcripts found")

    ok = failed = 0
    for i in range(0, len(files), BATCH_SIZE):
        batch_files = files[i:i + BATCH_SIZE]
        rows = [{
            "call_id": f.name.removesuffix(".mp3.json"),
            "transcript": json.loads(f.read_text(encoding="utf-8")),
        } for f in batch_files]
        try:
            upload_batch(rows)
            ok += len(rows)
        except requests.RequestException as e:
            failed += len(rows)
            print(f"  ❌ batch at {i}: {e}")
        print(f"  {min(i + BATCH_SIZE, len(files))}/{len(files)} processed")

    print(f"\n✅ Done. Uploaded {ok}, failed {failed}.")

if __name__ == "__main__":
    main()
