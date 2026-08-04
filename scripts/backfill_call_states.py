#!/usr/bin/env python3
"""
backfill_call_states.py — Resolve each call's state/city from its linked
Zoho Lead/Contact, for calls already on the dashboard in July 2026.

Scope (per user request): calls already present in the Supabase `transcripts`
table (i.e. already visible in the app), Call_Start_Time in July 2026, either
direction (inbound/outbound), duration > 30 seconds.

Two-step by design, so the slow Zoho pass isn't repeated if the Supabase
schema isn't ready yet:

    python scripts/backfill_call_states.py --fetch
        Pulls July calls, resolves each linked Lead/Contact's state/city,
        writes out/call_states_july2026.json. No Supabase writes — safe to
        run any time.

    python scripts/backfill_call_states.py --apply
        Reads that file and PATCHes `state`/`city` onto the `transcripts`
        table, one row per call_id. Requires the columns to already exist:

            alter table transcripts add column if not exists state text;
            alter table transcripts add column if not exists city  text;

Requires ZOHO_* and SUPABASE_* vars in .env (same as the rest of the pipeline).
"""
import os, sys, json, time, argparse
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
OUT_FILE = BASE / "out" / "call_states_july2026.json"
TOKEN_CACHE = BASE / ".zoho_token_cache.json"

ZOHO_API = os.getenv("ZOHO_API_DOMAIN", "https://www.zohoapis.in")
ZOHO_ACC = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MONTH_START = "2026-07-01T00:00:00+05:30"
MONTH_END = "2026-08-01T00:00:00+05:30"  # exclusive
MIN_DURATION = 30  # seconds, strictly greater than

STATE_FIELDS = {
    "Leads": ("State1", "City"),
    "Contacts": ("Mailing_State1", "Mailing_City"),
}
FALLBACK_FIELDS = {
    "Leads": (None, None),
    "Contacts": ("Other_State", "Other_City"),
}


# ── Zoho auth (same cache as summarize_calls.py) ────────────────────────────
def get_token():
    try:
        c = json.loads(TOKEN_CACHE.read_text())
        if c.get("token") and c.get("expiresAt", 0) > time.time() * 1000 + 120_000:
            return c["token"]
    except Exception:
        pass
    r = requests.post(f"{ZOHO_ACC}/oauth/v2/token", data={
        "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
        "client_id": os.getenv("ZOHO_CLIENT_ID"),
        "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
        "grant_type": "refresh_token",
    }, timeout=30)
    d = r.json()
    if not d.get("access_token"):
        print("❌ Zoho token failed:", d); sys.exit(1)
    TOKEN_CACHE.write_text(json.dumps({
        "token": d["access_token"],
        "expiresAt": int(time.time() * 1000) + int(d.get("expires_in", 3600)) * 1000,
    }))
    return d["access_token"]


# ── Supabase ─────────────────────────────────────────────────────────────────
def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def fetch_transcript_ids():
    ids, offset, page = set(), 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/transcripts",
                          headers=sb_headers({"Range": f"{offset}-{offset + page - 1}"}),
                          params={"select": "call_id"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        ids.update(row["call_id"] for row in rows)
        if len(rows) < page:
            return ids
        offset += page


# ── Zoho Calls (bulk, paginated newest-first) ───────────────────────────────
def fetch_july_calls(token):
    fields = "id,Call_Type,Call_Duration_in_seconds,Call_Start_Time,Who_Id,What_Id"
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    calls, page_token = [], None
    for _ in range(300):  # safety cap
        params = {"fields": fields, "per_page": 200,
                   "sort_by": "Created_Time", "sort_order": "desc"}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(f"{ZOHO_API}/crm/v7/Calls", headers=headers, params=params, timeout=30)
        if not r.ok:
            print(f"  ⚠ Zoho Calls page failed: {r.status_code} {r.text[:200]}")
            break
        d = r.json()
        rows = d.get("data", [])
        if not rows:
            break
        calls.extend(rows)
        oldest = rows[-1].get("Call_Start_Time")
        info = d.get("info", {})
        print(f"  …{len(calls)} calls scanned, oldest so far {oldest}")
        if oldest and oldest < MONTH_START:
            break
        page_token = info.get("next_page_token")
        if not info.get("more_records") or not page_token:
            break
    return calls


def in_scope(c, transcript_ids):
    if c["id"] not in transcript_ids:
        return False
    st = c.get("Call_Start_Time")
    if not st or not (MONTH_START <= st < MONTH_END):
        return False
    dur = c.get("Call_Duration_in_seconds") or 0
    return dur > MIN_DURATION


def lead_ref(c):
    """(module, id) of the call's linked Lead/Contact, or None."""
    what = c.get("What_Id")
    if what and what.get("id"):
        return c.get("$se_module") or "Leads", what["id"]
    who = c.get("Who_Id")
    if who and who.get("id"):
        return "Contacts", who["id"]
    return None


def fetch_state_city(token, module, ids):
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    primary = STATE_FIELDS.get(module, STATE_FIELDS["Leads"])
    fallback = FALLBACK_FIELDS.get(module, (None, None))
    want = {f for f in primary + fallback if f}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        params = {"ids": ",".join(batch), "fields": f"id,{','.join(want)}"}
        r = requests.get(f"{ZOHO_API}/crm/v7/{module}", headers=headers, params=params, timeout=30)
        if not r.ok:
            print(f"  ⚠ {module} lookup batch failed: {r.status_code} {r.text[:200]}")
            continue
        for rec in (r.json().get("data") or []):
            state = rec.get(primary[0]) or (rec.get(fallback[0]) if fallback[0] else None)
            city = rec.get(primary[1]) or (rec.get(fallback[1]) if fallback[1] else None)
            out[rec["id"]] = {"state": state, "city": city}
        time.sleep(0.2)
    return out


def cmd_fetch():
    token = get_token()
    print("📄 loading transcript ids already on the app…")
    transcript_ids = fetch_transcript_ids()
    print(f"  {len(transcript_ids)} calls already on the app (have a transcript)")

    print("☎️  pulling Zoho Calls, newest first, until we pass July 1…")
    calls = fetch_july_calls(token)

    scoped = [c for c in calls if in_scope(c, transcript_ids)]
    print(f"\n✅ {len(scoped)} calls in scope "
          f"(on the app, July 2026, >{MIN_DURATION}s, both directions)")

    by_module = {}
    call_to_ref = {}
    for c in scoped:
        ref = lead_ref(c)
        call_to_ref[c["id"]] = ref
        if ref:
            module, rid = ref
            by_module.setdefault(module, set()).add(rid)

    for module, ids in by_module.items():
        print(f"🔎 resolving {len(ids)} unique {module} record(s) for state/city…")

    NEEDED_FILE = BASE / "out" / "call_states_ids_needed.json"
    NEEDED_FILE.write_text(json.dumps({m: sorted(ids) for m, ids in by_module.items()}, indent=2))

    resolved_file = BASE / "out" / "call_states_resolved.json"
    resolved = {}
    if resolved_file.exists():
        resolved = json.loads(resolved_file.read_text())
        print(f"  (using externally-resolved state/city from {resolved_file})")
    else:
        for module, ids in by_module.items():
            resolved[module] = fetch_state_city(token, module, ids)

    results = {}
    no_ref = no_match = 0
    for c in scoped:
        ref = call_to_ref.get(c["id"])
        state = city = None
        if ref:
            module, rid = ref
            rec = resolved.get(module, {}).get(rid)
            if rec:
                state, city = rec["state"], rec["city"]
            else:
                no_match += 1
        else:
            no_ref += 1
        results[c["id"]] = {
            "state": state, "city": city,
            "call_start_time": c.get("Call_Start_Time"),
            "call_type": c.get("Call_Type"),
            "duration_seconds": c.get("Call_Duration_in_seconds"),
        }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    with_state = sum(1 for v in results.values() if v["state"])
    print(f"\n💾 wrote {len(results)} calls to {OUT_FILE}")
    print(f"   {with_state}/{len(results)} have a state; "
          f"{no_ref} had no linked Lead/Contact, {no_match} linked record had no state on file")


def cmd_apply():
    if not OUT_FILE.exists():
        print(f"❌ {OUT_FILE} not found — run with --fetch first"); sys.exit(1)
    results = json.loads(OUT_FILE.read_text())
    print(f"📤 applying state/city for {len(results)} calls to `transcripts`…")

    ok = failed = 0
    for call_id, v in results.items():
        row = {"state": v["state"], "city": v["city"]}
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/transcripts",
                            headers=sb_headers({"Prefer": "return=minimal"}),
                            params={"call_id": f"eq.{call_id}"},
                            data=json.dumps(row), timeout=30)
        if r.ok:
            ok += 1
        else:
            failed += 1
            print(f"  ❌ {call_id}: {r.status_code} {r.text[:200]}")
    print(f"\n✅ updated {ok} rows, {failed} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="pull from Zoho, write local JSON (no Supabase writes)")
    ap.add_argument("--apply", action="store_true", help="write the local JSON's state/city into Supabase")
    args = ap.parse_args()

    if not args.fetch and not args.apply:
        print("specify --fetch or --apply"); sys.exit(1)

    if args.fetch:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"); sys.exit(1)
        cmd_fetch()
    if args.apply:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env"); sys.exit(1)
        cmd_apply()


if __name__ == "__main__":
    main()
