# Setup — Zoho credentials for discovery

Read-only. Nothing in this step can modify your CRM.

## 1. Install dependencies

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## 2. Create a Zoho Self Client

1. Go to https://api-console.zoho.com
2. **Add Client** -> **Self Client** (no redirect URL needed — this is a backend job)
3. Copy the **Client ID** and **Client Secret**

## 3. Fill in .env

    cp .env.example .env

Set `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, and `ZOHO_DC`.

`ZOHO_DC` is your region — check the domain you log into Zoho CRM with:
`crm.zoho.in` -> `in`, `crm.zoho.com` -> `com`, `.eu` -> `eu`, etc.
Getting this wrong is the most common cause of auth failures.

## 4. Generate a grant code

In the API console, on your Self Client, open the **Generate Code** tab.

**Scope** (read-only — paste as one comma-separated line, no spaces):

    ZohoCRM.settings.fields.READ,ZohoCRM.modules.calls.READ,ZohoCRM.modules.attachments.READ

Note there is no write scope here. We add `ZohoCRM.modules.notes.CREATE` later,
once you've seen a dry run and approved what gets written.

**Time Duration**: 10 minutes (the max — the code is single-use and short-lived)
**Scope Description**: anything, e.g. "call transcription discovery"

Click **Create**, pick your CRM portal, and copy the code.

## 5. Exchange it for a refresh token

    python scripts/get_refresh_token.py

Paste the code when prompted. It prints a `ZOHO_REFRESH_TOKEN=...` line — add
that to `.env`. Refresh tokens don't expire.

If it fails with `invalid_code`, the code expired or was already used. Generate
a fresh one; don't retry the same code.

## 6. Run discovery

    python scripts/discover_zoho.py

Prints what it finds and dumps raw JSON to `out/`. It answers:

- the recording field's real API name (Zoho never documented it)
- whether that field is actually populated
- whether recordings are attachments instead
- how many Call records exist

`out/` is gitignored — the dumps contain real customer data.

## Revoking access

api-console.zoho.com -> your Self Client -> revoke. Takes effect immediately.
