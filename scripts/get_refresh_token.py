"""Exchange a Zoho self-client grant code for a refresh token.

Run once. See SETUP.md for how to generate the grant code.
The grant code is single-use and expires in minutes — if this fails with
"invalid_code", generate a fresh one rather than retrying the same one.
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

ACCOUNTS = {
    "com": "https://accounts.zoho.com",
    "in": "https://accounts.zoho.in",
    "eu": "https://accounts.zoho.eu",
    "com.au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
}


def main() -> int:
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")
    dc = os.getenv("ZOHO_DC", "in")

    if not client_id or not client_secret:
        print("Set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in .env first.")
        return 1

    if dc not in ACCOUNTS:
        print(f"ZOHO_DC must be one of: {', '.join(ACCOUNTS)}")
        return 1

    code = input("Paste the grant code from api-console.zoho.com: ").strip()
    if not code:
        print("No code given.")
        return 1

    resp = requests.post(
        f"{ACCOUNTS[dc]}/oauth/v2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        timeout=30,
    )
    payload = resp.json()

    if "refresh_token" not in payload:
        print(f"Failed: {payload}")
        print("\nCommon causes: the code expired (they last ~3-10 min), the code")
        print("was already used, or ZOHO_DC doesn't match your account's region.")
        return 1

    print("\nSuccess. Add this line to your .env:\n")
    print(f"ZOHO_REFRESH_TOKEN={payload['refresh_token']}")
    print("\nRefresh tokens do not expire. Keep it secret; revoke from the")
    print("API console if it ever leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
