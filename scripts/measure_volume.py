"""Measure how many Calls actually have recordings, and their total duration.

Determines real transcription cost: unanswered dials have no audio and cost
nothing. Read-only.
"""

import os
import sys
from collections import Counter

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discover_zoho import access_token, domains  # noqa: E402

load_dotenv()

PAGES = int(os.getenv("SAMPLE_PAGES", "10"))  # 200 records per page
FIELDS = "id,Call_Start_Time,Call_Duration_in_seconds,Voice_Recording__s,Owner"


def main() -> int:
    accounts, api = domains()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token(accounts)}"}

    total = 0
    with_rec = 0
    seconds = 0
    per_owner = Counter()
    per_day = Counter()
    token = None

    for page in range(PAGES):
        params = {
            "fields": FIELDS,
            "per_page": 200,
            "sort_by": "Modified_Time",
            "sort_order": "desc",
        }
        if token:
            params["page_token"] = token
        elif page:
            params["page"] = page + 1

        resp = requests.get(
            f"{api}/crm/v7/Calls", params=params, headers=headers, timeout=60
        )
        if resp.status_code == 204:
            break
        if resp.status_code != 200:
            print(f"stopped at page {page + 1}: {resp.status_code} {resp.text[:200]}")
            break

        body = resp.json()
        for r in body.get("data", []):
            total += 1
            if r.get("Voice_Recording__s"):
                with_rec += 1
                secs = r.get("Call_Duration_in_seconds") or 0
                seconds += secs
                per_owner[(r.get("Owner") or {}).get("name", "?")] += 1
                if r.get("Call_Start_Time"):
                    per_day[r["Call_Start_Time"][:10]] += 1

        info = body.get("info", {})
        if not info.get("more_records"):
            break
        token = info.get("next_page_token")
        if not token:
            break

    if not total:
        print("No records sampled.")
        return 1

    rate = with_rec / total
    avg = seconds / with_rec if with_rec else 0
    print(f"Sampled:            {total:,} calls")
    print(f"With recording:     {with_rec:,}  ({rate:.1%})")
    print(f"Avg recorded call:  {avg / 60:.1f} min")
    print(f"Sample audio total: {seconds / 3600:.1f} hours")

    if per_day:
        days = sorted(per_day)
        print(f"\nDate range:         {days[0]} .. {days[-1]}  ({len(days)} days)")
        per = sum(per_day.values()) / len(days)
        print(f"Recorded calls/day: {per:.0f}")
        hrs_month = per * avg / 3600 * 30
        print(f"\nProjected monthly:  {hrs_month:.0f} audio-hours")
        print(f"  Sarvam @ Rs30/hr: Rs {hrs_month * 30:,.0f}/month")
        print(f"  Sarvam @ Rs45/hr: Rs {hrs_month * 45:,.0f}/month (with diarization)")

    est = 49081 * rate
    print(f"\nBacklog estimate:   ~{est:,.0f} recorded calls of 49,081 total")
    print(f"  Backfill audio:   ~{est * avg / 3600:,.0f} hours")
    print(f"  One-off cost:     Rs {est * avg / 3600 * 45:,.0f} (at Rs45/hr)")

    if per_owner:
        print("\nTop callers in sample:")
        for name, n in per_owner.most_common(8):
            print(f"  {name:<25} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
