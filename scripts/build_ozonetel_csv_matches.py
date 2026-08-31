#!/usr/bin/env python3
"""Build a transcribe_ozonetel_july.py-compatible matches file from an Ozonetel
CDR CSV export (Reports -> CDR Reports in Ozonetel CloudAgent), joined against
Zoho Calls for the same window.

Join key: Ozonetel's own "Call ID" column equals the numeric ID embedded in
the path of Zoho's Voice_Recording__s phonebridge URL (the same join already
used for the api-july21-31 source in transcribe_ozonetel_july.py) — both are
identifiers for the same underlying telephony call.

Output shape matches out/ozonetel_july01_15_matches.json exactly:
    [{"zoho": {<call fields>}, "audio_url": "<ozonetel s3 url>"}, ...]

Usage:
    python scripts/build_ozonetel_csv_matches.py \\
        --csv "~/Downloads/sunrooof second batch.csv" \\
        --since 2026-07-16 --until 2026-07-31 \\
        --out out/ozonetel_second_batch_matches.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from batch_transcribe import ZOHO_API, get_token  # noqa: E402

load_dotenv()

BASE = Path(__file__).resolve().parent.parent


def duration_seconds(row):
    try:
        return int(row.get("Call_Duration_in_seconds") or 0)
    except (TypeError, ValueError):
        return 0


def fetch_zoho_calls(since, until):
    """All Zoho Calls with a recording in [since, until] via COQL, paged with
    the offset syntax ('limit offset, count') already proven to work against
    this org. COQL offset caps around 9800-10000; if a window is that dense,
    split --since/--until into narrower ranges and merge the outputs."""
    token = get_token()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    since_s = f"{since}T00:00:00+05:30"
    until_s = f"{until}T23:59:59+05:30"
    rows, offset, page = [], 0, 0
    while True:
        q = (
            "select id, Call_Start_Time, Call_Duration_in_seconds, Voice_Recording__s "
            f"from Calls where Call_Start_Time between '{since_s}' and '{until_s}' "
            f"and Voice_Recording__s is not null order by id asc limit {offset}, 200"
        )
        r = requests.post(f"{ZOHO_API}/crm/v7/coql", headers=headers,
                           json={"select_query": q}, timeout=60)
        if r.status_code != 200:
            print(f"    COQL error at offset {offset}: {r.status_code} {r.text[:200]}")
            break
        batch = r.json().get("data") or []
        if not batch:
            break
        rows.extend(batch)
        page += 1
        if page % 20 == 0:
            print(f"    ...scanned {len(rows)} Zoho calls")
        offset += 200
        if offset > 9800:
            print(f"    ⚠ hit COQL offset cap at {len(rows)} rows — "
                  f"narrow --since/--until if this window has more than that")
            break
    return rows


def provider_id(zoho_row):
    rec = zoho_row.get("Voice_Recording__s") or ""
    return Path(urlparse(rec).path).name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--since", required=True, help="YYYY-MM-DD")
    ap.add_argument("--until", required=True, help="YYYY-MM-DD")
    ap.add_argument("--min-duration", type=int, default=30)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    csv_path = Path(args.csv).expanduser()
    print(f"📄 reading {csv_path.name}...")
    csv_by_id = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cid = (row.get("Call ID") or "").strip()
            if cid and row.get("Recording URL", "").strip():
                csv_by_id[cid] = row
    print(f"   {len(csv_by_id)} CSV rows with a recording URL")

    print(f"☁️  scanning Zoho Calls {args.since} -> {args.until}...")
    zoho_rows = fetch_zoho_calls(args.since, args.until)
    print(f"   {len(zoho_rows)} Zoho calls with a recording in that window")

    done = {p.name.removesuffix(".mp3.json")
            for p in (BASE / "out" / "transcripts").glob("*.json")}

    matches, already_done, too_short, no_csv_match = [], 0, 0, 0
    for z in zoho_rows:
        zid = str(z.get("id") or "")
        if zid in done:
            already_done += 1
            continue
        if duration_seconds(z) < args.min_duration:
            too_short += 1
            continue
        pid = provider_id(z)
        csv_row = csv_by_id.get(pid)
        if not csv_row:
            no_csv_match += 1
            continue
        matches.append({"zoho": z, "audio_url": csv_row["Recording URL"].strip()})

    out_path = BASE / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matches, indent=1, ensure_ascii=False))

    total_sec = sum(duration_seconds(m["zoho"]) for m in matches)
    print(f"\n💾 wrote {out_path}")
    print(f"   {len(matches)} new matched calls ready to transcribe")
    print(f"   audio: {total_sec/60:.1f} min ({total_sec/3600:.1f} h)  "
          f"~Rs {total_sec/3600*45:.0f} at Rs45/audio-hour")
    print(f"   (skipped: {already_done} already transcribed, "
          f"{too_short} under {args.min_duration}s, {no_csv_match} no CSV match)")


if __name__ == "__main__":
    main()
