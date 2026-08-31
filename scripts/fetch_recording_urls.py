#!/usr/bin/env python3
"""Fetch Voice_Recording__s (the Zoho phonebridge recording URL) for every
transcribed call and cache it locally.

Every prior script that touched this field (batch_transcribe.py,
transcribe_ozonetel_july.py) used it transiently to download the audio and
never persisted it — so it doesn't exist anywhere in Supabase or this
project's other cache files. This one exists purely to make it available to
the dashboard's audio player.

Usage:
    python scripts/fetch_recording_urls.py
"""
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from batch_transcribe import ZOHO_API, get_token  # noqa: E402

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
OUT_FILE = BASE / "out" / "recording_urls.json"


def main():
    ids = {p.name.removesuffix(".mp3.json") for p in (BASE / "out" / "transcripts").glob("*.json")}
    existing = {}
    if OUT_FILE.exists():
        existing = json.loads(OUT_FILE.read_text())
    pending = sorted(ids - set(existing))
    print(f"{len(ids)} transcribed calls, {len(existing)} already cached, {len(pending)} to fetch")
    if not pending:
        return

    token = get_token()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    fetched = 0
    # Zoho's bulk-read endpoint takes up to 100 ids per call.
    for i in range(0, len(pending), 100):
        batch = pending[i:i + 100]
        r = requests.get(f"{ZOHO_API}/crm/v7/Calls", headers=headers, timeout=30, params={
            "ids": ",".join(batch), "fields": "id,Voice_Recording__s",
        })
        if not r.ok:
            print(f"  ⚠ batch at {i} failed: {r.status_code} {r.text[:150]}")
            continue
        for row in r.json().get("data", []):
            url = row.get("Voice_Recording__s")
            if url:
                existing[row["id"]] = url
                fetched += 1
        if (i // 100) % 10 == 0:
            print(f"  ...{i + len(batch)}/{len(pending)}")

    OUT_FILE.write_text(json.dumps(existing, indent=1))
    print(f"\n💾 wrote {OUT_FILE} — {fetched} new URLs, {len(existing)} total")


if __name__ == "__main__":
    main()
