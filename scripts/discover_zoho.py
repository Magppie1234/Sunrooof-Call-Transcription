"""Read-only reconnaissance of the Zoho CRM Calls module.

Answers the questions the docs can't:
  1. What is the recording field's actual API name? (undocumented by Zoho)
  2. Is it populated, and what does the URL look like?
  3. Are recordings stored as attachments instead?
  4. How many Calls exist, and over what date range?

Writes nothing to Zoho. Read scopes only.
Raw dumps land in out/ (gitignored — they contain customer data).
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_DC_ACCOUNTS = {
    "com": "https://accounts.zoho.com",
    "in": "https://accounts.zoho.in",
    "eu": "https://accounts.zoho.eu",
    "com.au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
}
_DC_APIS = {
    "com": "https://www.zohoapis.com",
    "in": "https://www.zohoapis.in",
    "eu": "https://www.zohoapis.eu",
    "com.au": "https://www.zohoapis.com.au",
    "jp": "https://www.zohoapis.jp",
}


def domains() -> tuple[str, str]:
    """Explicit domains win; otherwise derive them from ZOHO_DC."""
    accounts = os.getenv("ZOHO_ACCOUNTS_DOMAIN")
    api = os.getenv("ZOHO_API_DOMAIN")
    if accounts and api:
        return accounts.rstrip("/"), api.rstrip("/")
    dc = os.getenv("ZOHO_DC", "in")
    if dc not in _DC_APIS:
        raise SystemExit(
            "Set ZOHO_ACCOUNTS_DOMAIN and ZOHO_API_DOMAIN, "
            f"or ZOHO_DC to one of: {', '.join(_DC_APIS)}"
        )
    return _DC_ACCOUNTS[dc], _DC_APIS[dc]

# Field labels/names that plausibly hold a recording. Zoho never documented the
# real one, so we cast a wide net and report what we find.
RECORDING_HINTS = re.compile(
    r"record|audio|voice|call_url|media|mp3|wav|playback", re.IGNORECASE
)

OUT = Path(__file__).resolve().parent.parent / "out"


def access_token(accounts: str) -> str:
    resp = requests.post(
        f"{accounts}/oauth/v2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["ZOHO_CLIENT_ID"],
            "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
            "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    payload = resp.json()
    if "access_token" not in payload:
        raise SystemExit(f"Could not refresh access token: {payload}")
    return payload["access_token"]


def main() -> int:
    accounts, api = domains()
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        if not os.getenv(var):
            print(f"{var} missing from .env — see SETUP.md")
            return 1

    OUT.mkdir(exist_ok=True)
    headers = {"Authorization": f"Zoho-oauthtoken {access_token(accounts)}"}

    # --- 1. Field metadata -------------------------------------------------
    print("Fetching Calls field metadata...")
    resp = requests.get(
        f"{api}/crm/v7/settings/fields",
        params={"module": "Calls"},
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  Failed ({resp.status_code}): {resp.text[:400]}")
        print("  Check that the ZohoCRM.settings.fields.READ scope was granted.")
        return 1

    fields = resp.json().get("fields", [])
    (OUT / "calls_fields.json").write_text(json.dumps(fields, indent=2))
    print(f"  {len(fields)} fields. Full dump: out/calls_fields.json")

    candidates = [
        f for f in fields
        if RECORDING_HINTS.search(f.get("api_name", ""))
        or RECORDING_HINTS.search(f.get("field_label", ""))
    ]
    if candidates:
        print("\n  Possible recording fields:")
        for f in candidates:
            print(
                f"    {f['api_name']:<40} "
                f"label={f.get('field_label')!r} type={f.get('data_type')}"
            )
    else:
        print("\n  No recording-like field found in metadata.")
        print("  (May still exist as a $-prefixed system property — checking records.)")

    # --- 2. Recent records -------------------------------------------------
    print("\nFetching 20 most recent Calls...")
    names = [f["api_name"] for f in fields][:50]  # API caps `fields` at 50
    resp = requests.get(
        f"{api}/crm/v7/Calls",
        params={
            "fields": ",".join(names),
            "per_page": 20,
            "sort_by": "Modified_Time",
            "sort_order": "desc",
        },
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 204:
        print("  No Call records exist in this org at all.")
        return 0
    if resp.status_code != 200:
        print(f"  Failed ({resp.status_code}): {resp.text[:400]}")
        return 1

    body = resp.json()
    records = body.get("data", [])
    (OUT / "calls_sample.json").write_text(json.dumps(body, indent=2))
    print(f"  {len(records)} records. Full dump: out/calls_sample.json")

    # Any key anywhere in a record whose value looks like an audio URL.
    print("\n  Scanning record values for audio URLs...")
    hits = {}
    for rec in records:
        for key, val in rec.items():
            if not isinstance(val, str):
                continue
            if RECORDING_HINTS.search(key) or re.search(
                r"https?://\S+\.(mp3|wav|ogg|m4a)", val, re.IGNORECASE
            ):
                if val and val not in ("null", ""):
                    hits.setdefault(key, []).append(val)

    if hits:
        print("  FOUND — recording data is present in Zoho:")
        for key, vals in hits.items():
            print(f"    {key}: {len(vals)} populated")
            print(f"      e.g. {vals[0][:120]}")
        print("\n  => Zoho holds the recordings. Ozonetel API key likely NOT needed.")
    else:
        print("  Nothing. No populated recording field on any recent Call.")
        print("\n  => Recordings must come from Ozonetel's CDR API.")

    # --- 3. Attachments fallback ------------------------------------------
    if records:
        rec_id = records[0]["id"]
        print(f"\nChecking attachments on Call {rec_id}...")
        resp = requests.get(
            f"{api}/crm/v7/Calls/{rec_id}/Attachments",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            atts = resp.json().get("data", [])
            print(f"  {len(atts)} attachment(s)")
            for a in atts:
                print(f"    {a.get('File_Name')}  ({a.get('Size')} bytes)")
        elif resp.status_code == 204:
            print("  None.")
        else:
            print(f"  Could not check ({resp.status_code}) — scope may be missing.")

    # --- 4. Volume ---------------------------------------------------------
    print("\nCounting total Calls...")
    resp = requests.get(
        f"{api}/crm/v7/Calls/actions/count",
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 200:
        print(f"  Total Call records: {resp.json().get('count')}")
    else:
        print(f"  Count unavailable ({resp.status_code}); infer from dumps instead.")

    if records:
        times = sorted(
            r.get("Call_Start_Time") or r.get("Created_Time") or "" for r in records
        )
        print(f"  Most recent 20 span: {times[0]} .. {times[-1]}")

    print("\nDone. Nothing was modified. Review out/ for the raw data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
