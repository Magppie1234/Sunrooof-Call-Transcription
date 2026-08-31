#!/usr/bin/env python3
"""Write call insights back into Zoho CRM: a condensed Note + Call_Result on
the Call record, and backfill the linked Lead/Contact's City when Zoho has
none on file but our extraction found one.

Composes the note entirely from already-extracted Supabase `call_summaries`
data (commitments, action_items, objections, call_outcome) — no new LLM call,
so this works even while OpenAI credits are out.

Usage:
    python scripts/sync_notes_to_zoho.py --limit 5 --dry-run   # preview only
    python scripts/sync_notes_to_zoho.py --limit 5             # actually write
    python scripts/sync_notes_to_zoho.py                       # all pending
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
from batch_transcribe import ZOHO_API, ZOHO_ACC  # noqa: E402

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# This script deliberately does NOT use batch_transcribe.get_token()'s shared
# .zoho_token_cache.json — that file is written by every other Zoho-touching
# script in this pipeline (the dataset-refresh loop's `zoho` stage,
# fetch_zoho_enrichment.py, etc.), and a run of this length (thousands of
# calls, many minutes) reliably outlives whatever token was cached when it
# started, or gets clobbered by a concurrent refresh from another process.
# A ~1600-call live-CRM run failed silently (826 successful writes, then 100%
# 401s for the rest) from exactly this on 2026-08-07. Own the token locally
# and re-auth on demand instead of trusting a file other processes mutate.
class ZohoAuth:
    def __init__(self):
        self.token = None
        self.refresh()

    def refresh(self):
        r = requests.post(f"{ZOHO_ACC}/oauth/v2/token", data={
            "grant_type": "refresh_token",
            "client_id": os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
        }, timeout=30)
        d = r.json()
        if not d.get("access_token"):
            raise RuntimeError(f"Zoho token refresh failed: {d}")
        self.token = d["access_token"]

    def headers(self):
        return {"Authorization": f"Zoho-oauthtoken {self.token}"}


def zreq(method, path, auth, **kwargs):
    """Any Zoho REST call, with one automatic re-auth-and-retry on 401."""
    r = requests.request(method, f"{ZOHO_API}/crm/v7/{path}", headers=auth.headers(),
                          timeout=kwargs.pop("timeout", 30), **kwargs)
    if r.status_code == 401:
        auth.refresh()
        r = requests.request(method, f"{ZOHO_API}/crm/v7/{path}", headers=auth.headers(),
                              timeout=30, **kwargs)
    return r

# Local incremental state, same pattern as the rest of the pipeline (no
# Supabase schema change required — this project's service-role key can't
# run DDL over REST anyway).
BASE = Path(__file__).resolve().parent.parent
SYNCED_FILE = BASE / "out" / "zoho_notes_synced.json"


def load_synced():
    if SYNCED_FILE.exists():
        return set(json.loads(SYNCED_FILE.read_text()))
    return set()


def mark_synced(call_id, synced_set):
    synced_set.add(call_id)
    SYNCED_FILE.write_text(json.dumps(sorted(synced_set)))

OUTCOME_TO_RESULT = {
    "interested": "Interested",
    "not_interested": "Not interested",
    "callback_requested": "Requested call back",
    "not_reachable": "No response/Busy",
    "wrong_number": "Invalid number",
    "follow_up_needed": "Requested more info",
    # already_purchased / unclear: no clean Call_Result match — left unmapped
    # (Note still gets written; Call_Result is skipped for these).
}

NOTE_MARKER = "[AI-Generated Summary — Sunrooof Call Intelligence]"  # prefix so a re-run
# can find/skip its own notes, and so anyone reading Zoho knows this note was written by
# the AI pipeline, not a human agent.
LEGACY_NOTE_MARKER = "[Call Intelligence]"  # the ~5021 notes already written before this
# rename used this shorter marker. get_our_note() must still recognise those as ours —
# otherwise every already-synced call looks note-less and the button creates a duplicate.


def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if extra:
        h.update(extra)
    return h


def fetch_pending(limit, synced_set):
    cols = ("call_id,agent,customer,call_outcome,summary,next_action,action_items,"
            "objections,customer_sentiment,location,analysis")
    rows, offset, page = [], 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(
            {"Range": f"{offset}-{offset + page - 1}"}), params={"select": cols}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        rows.extend(x for x in batch if x["call_id"] not in synced_set)
        if len(batch) < page:
            break
        offset += page
        if limit and len(rows) >= limit:
            break
    return rows[:limit] if limit else rows


def compose_note(row):
    """Short, scannable lines — only the actionable facts. Never truncates a
    genuinely important line; just skips empty/boilerplate content."""
    lines = []
    outcome = row.get("call_outcome")
    headline = {
        "interested": "Interested.",
        "not_interested": "Not interested.",
        "callback_requested": "Requested a callback.",
        "not_reachable": "Not reachable.",
        "wrong_number": "Wrong number.",
        "follow_up_needed": "Needs follow-up.",
        "already_purchased": "Already purchased.",
        "unclear": None,
    }.get(outcome)
    if headline:
        lines.append(headline)

    # "What happens next" has three possible sources (commitments,
    # action_items, next_action) that are frequently near-duplicate restatements
    # of the same single fact — concatenating all three produces a note that
    # says the same thing four ways. Pick ONE, in order of concreteness.
    analysis = row.get("analysis") or {}
    commitments = [c for c in (analysis.get("commitments") or []) if (c.get("what") or "").strip()]
    if commitments:
        for c in commitments:
            who = "Customer" if c.get("who") == "customer" else "Agent"
            what = c["what"].strip()
            due = c.get("due")
            lines.append(f"{who} to {what}{' — by ' + due if due else ''}.")
    elif row.get("action_items"):
        for item in row["action_items"][:2]:
            item = (item or "").strip()
            if item:
                lines.append(item if item.endswith((".", "!", "?")) else item + ".")
    elif row.get("next_action"):
        na = row["next_action"].strip()
        if na:
            lines.append(f"Next: {na}")

    for obj in row.get("objections") or []:
        obj = (obj or "").strip()
        if obj:
            lines.append(f"Objection: {obj}")

    if not lines and row.get("summary"):
        lines.append(row["summary"].strip())

    body = "\n".join(f"- {l}" for l in lines)
    return f"{NOTE_MARKER}\n{body}" if body else None


def zget(path, params, auth):
    r = zreq("get", path, auth, params=params)
    r.raise_for_status()
    return r.json()


# Who_Id can point at any of these four modules (confirmed live: of 5021
# linked calls, 4474 Leads, 305 Deals, 62 Contacts, 2 Accounts, 178
# unresolved). The original version only probed Leads/Contacts, so every
# Deals- or Accounts-linked call silently got no city write at all — not
# "wrote Mailing_City instead of City", just skipped entirely. Each module
# uses its own city field name (verified live via settings/fields):
# Leads.City, Contacts.Mailing_City, Deals.Mailing_City, Accounts.Billing_City.
LINK_MODULES = ("Leads", "Contacts", "Deals", "Accounts")
CITY_FIELD_BY_MODULE = {
    "Leads": "City",
    "Contacts": "Mailing_City",
    "Deals": "Mailing_City",
    "Accounts": "Billing_City",
}


def get_lead_link(call_id, auth):
    """The record this Call is linked to (Who_Id), if any. The lookup
    frequently omits `module` — probing candidates is the only reliable way
    to know which one a given id actually belongs to (guessing wrong means a
    GET on the wrong module, which Zoho answers with HTTP 204 / empty body,
    not a clean 404 — that crashed an earlier version of this script
    outright)."""
    try:
        d = zget(f"Calls/{call_id}", {"fields": "Who_Id"}, auth)
    except requests.HTTPError:
        return None
    who = (d.get("data") or [{}])[0].get("Who_Id")
    if not who:
        return None
    lead_id = who.get("id")
    module = who.get("module")
    if module:
        return lead_id, module
    for candidate in LINK_MODULES:
        r = zreq("get", f"{candidate}/{lead_id}", auth, params={"fields": "id"})
        if r.status_code == 200:
            return lead_id, candidate
    return None


def get_our_note(call_id, auth):
    """The existing note this script wrote, if any (full record, so callers
    can PUT an update to its id instead of only being able to skip)."""
    r = zreq("get", f"Calls/{call_id}/Notes", auth, params={"fields": "Note_Content"})
    if r.status_code == 204:
        return None
    r.raise_for_status()
    for n in r.json().get("data", []):
        content = n.get("Note_Content") or ""
        if NOTE_MARKER in content or LEGACY_NOTE_MARKER in content:
            return n
    return None


def has_our_note(call_id, auth):
    return get_our_note(call_id, auth) is not None


def sync_one(cid, auth, note=None, result=None, city=None, update_note=False):
    """Push one call's Result / Note / City to Zoho. Shared by the bulk
    loop (auto-composed values, create-note-if-absent) and the per-call
    "Update CRM" button (human-edited values, update-note-in-place).
    Returns a dict describing what actually happened, safe to serialize
    straight to JSON for the button's HTTP response.

    Result and City are ALWAYS write-only-if-currently-empty in Zoho —
    never overwritten, even from the button, even by a human-edited value.
    This is a deliberate policy, not an oversight: an earlier version of
    this script overwrote Call_Result unconditionally on every synced call
    with no check for an existing value, which risked clobbering a real
    disposition a sales agent had entered. A live check (calls our system
    intentionally never wrote Call_Result to) found 0/80 had any value —
    so the field appears to have started essentially empty everywhere —
    but that isn't a guarantee, and there's no reliable way to recover a
    prior value if one was overwritten (no pre-write snapshot, and Zoho's
    REST API doesn't expose per-field history). Rather than repeat that
    risk, both fields are now additive-only: they only ever fill a gap,
    never replace something already there. The Note is the one exception —
    it's a new, separate, clearly AI-labeled record, so it never touches or
    replaces anything a human wrote.

    Never raises for a City-side failure (unusual module, permission
    quirk) — City is best-effort on top of Result/Note, which are the
    primary deliverable and must not be blocked by it."""
    out = {"call_id": cid, "result": None, "note": None, "city": None}

    if result:
        try:
            existing = zget(f"Calls/{cid}", {"fields": "Call_Result"}, auth)
            cur = (existing.get("data") or [{}])[0].get("Call_Result")
        except Exception as e:
            out["result"] = f"failed: {e}"
            cur = "unknown"  # don't risk a write if we couldn't confirm it's empty
        if not out["result"]:
            if cur:
                out["result"] = f"skipped (already has Call_Result={cur!r})"
            else:
                r = zreq("put", f"Calls/{cid}", auth, json={"data": [{"id": cid, "Call_Result": result}]})
                r.raise_for_status()
                out["result"] = f"wrote {result!r}"

    if note:
        existing = get_our_note(cid, auth)
        if existing and update_note:
            if existing.get("Note_Content") != note:
                r = zreq("put", "Notes", auth,
                          json={"data": [{"id": existing["id"], "Note_Content": note}]})
                r.raise_for_status()
                out["note"] = "updated"
            else:
                out["note"] = "unchanged"
        elif not existing:
            r = zreq("post", f"Calls/{cid}/Notes", auth, json={"data": [{"Note_Content": note}]})
            r.raise_for_status()
            out["note"] = "created"
        else:
            out["note"] = "skipped (already synced)"

    if city:
        try:
            link = get_lead_link(cid, auth)
            if not link:
                out["city"] = "skipped (no linked Lead/Contact/Deal/Account)"
            else:
                lead_id, module = link
                city_field = CITY_FIELD_BY_MODULE.get(module)
                if not city_field:
                    out["city"] = f"skipped (unhandled module {module})"
                else:
                    existing = zget(f"{module}/{lead_id}", {"fields": city_field}, auth)
                    cur = (existing.get("data") or [{}])[0].get(city_field)
                    if not cur:
                        r = zreq("put", f"{module}/{lead_id}", auth,
                                  json={"data": [{"id": lead_id, city_field: city}]})
                        r.raise_for_status()
                        out["city"] = f"wrote {city_field}={city!r} on {module} {lead_id}"
                    else:
                        out["city"] = f"skipped (already has {city_field}={cur!r})"
        except Exception as e:
            out["city"] = f"failed: {e}"

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--call-id", help="Sync a single call with explicit human-edited values "
                                       "(used by the dashboard's Update CRM button), instead of "
                                       "the bulk auto-composed-from-Supabase pass.")
    ap.add_argument("--note")
    ap.add_argument("--result")
    ap.add_argument("--city")
    ap.add_argument("--draft", help="Print the auto-composed note/result/city for one call as "
                                     "JSON and exit — Supabase only, touches Zoho for nothing. "
                                     "Used to prefill the dashboard's Update CRM review panel "
                                     "before the user has clicked anything.")
    args = ap.parse_args()

    if args.draft:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print(json.dumps({"error": "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY"})); sys.exit(1)
        cols = ("call_id,agent,customer,call_outcome,summary,next_action,action_items,"
                "objections,customer_sentiment,location,analysis")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(),
                          params={"select": cols, "call_id": f"eq.{args.draft}"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            print(json.dumps({"error": f"No summary found for call {args.draft}"})); sys.exit(1)
        row = rows[0]
        print(json.dumps({
            "note": compose_note(row),
            "result": OUTCOME_TO_RESULT.get(row.get("call_outcome")),
            "city": (row.get("location") or "").strip() or None,
            "callOutcome": row.get("call_outcome"),
        }))
        return

    if args.call_id:
        # Any failure here (token refresh, network, Zoho 5xx) must come back
        # as clean JSON on stdout, not a Python traceback — this is what the
        # dashboard's Update CRM button parses and shows to the user.
        try:
            auth = ZohoAuth()
            result = sync_one(args.call_id, auth, note=args.note, result=args.result,
                               city=args.city, update_note=True)
        except Exception as e:
            result = {"call_id": args.call_id, "result": None, "note": None, "city": None,
                       "error": f"Could not reach Zoho: {e}"}
        print(json.dumps(result))
        return

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY"); sys.exit(1)

    synced = load_synced()
    rows = fetch_pending(args.limit, synced)
    print(f"{'[dry-run] ' if args.dry_run else ''}{len(rows)} call(s) to process "
          f"({len(synced)} already synced)\n")
    if not rows:
        return

    auth = None if args.dry_run else ZohoAuth()
    done = failed = 0
    for i, row in enumerate(rows, 1):
        cid = row["call_id"]
        note = compose_note(row)
        result = OUTCOME_TO_RESULT.get(row.get("call_outcome"))
        location = (row.get("location") or "").strip()

        print(f"── {cid} ({row.get('agent')} → {row.get('customer')}) ──")
        print(f"   Call_Result: {result or '(no mapping, skip)'}")
        print(f"   Note:\n" + "\n".join(f"     {l}" for l in (note or "(none)").splitlines()))
        print(f"   City candidate: {location or '(none extracted)'}")

        if args.dry_run:
            print()
            continue

        # Proactive refresh every 200 calls — cheap insurance against the
        # exact failure mode above, on top of the reactive 401 retry in zreq.
        # Best-effort: if Zoho is rate-limiting token refreshes right now, keep
        # using the current token rather than crashing the whole run.
        if i % 200 == 0:
            try:
                auth.refresh()
            except Exception as e:
                print(f"   ⚠ proactive token refresh failed, continuing with current token: {e}")

        try:
            r = sync_one(cid, auth, note=note, result=result, city=location or None,
                         update_note=False)
            if r["city"] and r["city"].startswith("wrote"):
                print(f"   -> {r['city']}")
            elif r["city"] and r["city"].startswith("failed"):
                print(f"   ⚠ city write skipped: {r['city']}")
            mark_synced(cid, synced)
            done += 1
        except Exception as e:
            print(f"   ❌ {e}")
            failed += 1
        print()
        time.sleep(0.3)

    if not args.dry_run:
        print(f"✅ {done} synced, {failed} failed")


if __name__ == "__main__":
    main()
