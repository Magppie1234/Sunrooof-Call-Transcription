#!/usr/bin/env python3
"""
fetch_zoho_enrichment.py — Pull the CRM context the Call Intelligence dashboard
needs but `call_summaries` doesn't carry: lead source, campaign, CRM stage,
pincode, client/property type, product requirement, and deal/revenue signals.

Each Zoho Call links to a Lead (What_Id + $se_module) or Contact (Who_Id). For
Contacts we also look for an associated Deal to recover stage/amount.

    python scripts/fetch_zoho_enrichment.py            # all calls in Supabase
    python scripts/fetch_zoho_enrichment.py --limit 20 # smoke test

Writes out/zoho_enrichment.json: { call_id: {...crm fields...} }.
Read-only against Zoho.
"""
import os, sys, json, time, argparse
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
OUT_FILE = BASE / "out" / "zoho_enrichment.json"
TOKEN_CACHE = BASE / ".zoho_token_cache.json"

ZOHO_API = os.getenv("ZOHO_API_DOMAIN", "https://www.zohoapis.in")
ZOHO_ACC = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.in")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Field names verified against SUNROOOF's own Zoho org (org fields differ from
# Magppie's — e.g. Type_of_Space here vs Property_Type there, and Deals carry
# Total_Consoles / Proposed_Order_Amount, which Magppie's org did not).
LEAD_FIELDS = ("id,Lead_Source,Other_Source,Lead_Status,City,State1,Zip_Code,Lead_Type,"
               "Project_Stage,Client_Status,Type_of_Space,Type_of_Space1,Campaign_Name,"
               "Experienced_SUNROOOF_before,SUNROOOF_Handover_timeline,"
               "By_when_should_sunroof_installation_be_done,Priority_Type,Visit_Call_Type,"
               "Address_1_City,Address_1_State_Province,Address_1_Zip_Postal_Code,"
               "Company,Email,Phone")
CONTACT_FIELDS = ("id,Lead_Source,Mailing_City,Mailing_State,Mailing_Zip,Other_City,"
                  "Account_Name,Email,Phone")
DEAL_FIELDS = ("id,Deal_Name,Stage,Lead_Source,Amount,Proposed_Order_Amount,"
               "Total_Amount_Received,Due_Amount,Total_Consoles,Product_Items,"
               "Type_of_Space1,Project_Stage,Campaign_Name,Experienced_SUNROOOF_before,"
               "SUNROOOF_Handover_timeline,Mailing_City,Mailing_State,Mailing_Zip,"
               "Shipping_Address_City,Shipping_Address_Zip_Postal_Code,"
               "Closing_Date,Contact_Name")

_TOKEN = {"value": None, "expires_at": 0}


def get_token(force=False):
    now = time.time()
    if not force and _TOKEN["value"] and _TOKEN["expires_at"] > now + 120:
        return _TOKEN["value"]
    if not force:
        try:
            c = json.loads(TOKEN_CACHE.read_text())
            if c.get("token") and c.get("expiresAt", 0) > now * 1000 + 120_000:
                _TOKEN.update(value=c["token"], expires_at=c["expiresAt"] / 1000)
                return c["token"]
        except Exception:
            pass
    # Zoho allows ~10 token generations per 10 minutes. A tight per-record loop
    # can trip that, so back off in minutes rather than seconds and let the
    # caller decide whether a failure is fatal.
    for attempt in range(4):
        if attempt:
            time.sleep(min(90, 15 * 2 ** attempt))
        r = requests.post(f"{ZOHO_ACC}/oauth/v2/token", data={
            "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN"),
            "client_id": os.getenv("ZOHO_CLIENT_ID"),
            "client_secret": os.getenv("ZOHO_CLIENT_SECRET"),
            "grant_type": "refresh_token"}, timeout=30)
        d = r.json()
        if d.get("access_token"):
            exp = now + int(d.get("expires_in", 3600))
            _TOKEN.update(value=d["access_token"], expires_at=exp)
            try:
                TOKEN_CACHE.write_text(json.dumps({"token": d["access_token"],
                                                   "expiresAt": int(exp * 1000)}))
            except OSError:
                pass
            return d["access_token"]
        print(f"  ⚠ token attempt {attempt+1}/4: {d}")
    raise RuntimeError("Zoho token generation rate-limited")


def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if extra:
        h.update(extra)
    return h


def fetch_call_ids():
    ids, offset, page = [], 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries",
                         headers=sb_headers({"Range": f"{offset}-{offset+page-1}"}),
                         params={"select": "call_id"}, timeout=30)
        r.raise_for_status()
        rows = r.json()
        ids.extend(row["call_id"] for row in rows)
        if len(rows) < page:
            return ids
        offset += page


def zget(path, params, token, _retry=False):
    r = requests.get(f"{ZOHO_API}/crm/v7/{path}",
                     params=params, headers={"Authorization": f"Zoho-oauthtoken {token}"},
                     timeout=30)
    if r.status_code == 401 and not _retry:
        return zget(path, params, get_token(force=True), _retry=True)
    if r.status_code == 429:
        time.sleep(5)
        return zget(path, params, token, _retry=True)
    if not r.ok:
        return None
    return r.json()


def fetch_calls_meta(token, call_ids):
    """Call -> linked record ref. Zoho has no bulk 'by ids' for Calls, so page the
    module and keep the ones we care about (far cheaper than 723 single GETs)."""
    want = set(call_ids)
    out, page_token = {}, None
    fields = "id,Subject,Call_Type,Call_Start_Time,Call_Duration_in_seconds,Owner,Who_Id,What_Id"
    for _ in range(400):
        params = {"fields": fields, "per_page": 200,
                  "sort_by": "Created_Time", "sort_order": "desc"}
        if page_token:
            params["page_token"] = page_token
        d = zget("Calls", params, token)
        if not d:
            break
        rows = d.get("data", [])
        if not rows:
            break
        for c in rows:
            if c["id"] in want:
                out[c["id"]] = c
        info = d.get("info", {})
        print(f"  …scanned, matched {len(out)}/{len(want)}")
        if len(out) >= len(want):
            break
        page_token = info.get("next_page_token")
        if not info.get("more_records") or not page_token:
            break
    return out


def bulk_fetch(token, module, ids, fields):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        d = zget(module, {"ids": ",".join(batch), "fields": fields}, token)
        for rec in ((d or {}).get("data") or []):
            out[rec["id"]] = rec
        time.sleep(0.2)
    return out


def fetch_deals_for_contacts(token, contact_ids):
    """Deals linked to a contact, newest first — gives stage/amount signals."""
    out = {}
    for i, cid in enumerate(contact_ids, 1):
        d = zget(f"Contacts/{cid}/Deals", {"fields": DEAL_FIELDS, "per_page": 5}, token)
        rows = (d or {}).get("data") or []
        if rows:
            out[cid] = rows[0]
        if i % 25 == 0:
            print(f"  …deals for {i}/{len(contact_ids)} contacts")
        time.sleep(0.15)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    token = get_token()
    print("📄 loading call ids from Supabase…")
    call_ids = fetch_call_ids()
    if args.limit:
        call_ids = call_ids[:args.limit]
    print(f"   {len(call_ids)} calls")

    # The Calls scan pages the whole module and is by far the slowest step, so
    # cache it — reruns after a downstream failure are then near-instant.
    CACHE = BASE / "out" / "zoho_calls_cache.json"
    calls = {}
    if CACHE.exists():
        cached = json.loads(CACHE.read_text())
        calls = {k: v for k, v in cached.items() if k in set(call_ids)}
        print(f"☎️  reusing cached Call records ({len(calls)}/{len(call_ids)})")
    if len(calls) < len(call_ids):
        print("☎️  resolving Zoho Call records…")
        calls = fetch_calls_meta(token, call_ids)
        CACHE.write_text(json.dumps(calls))
    print(f"   {len(calls)} matched in Zoho")

    lead_ids, contact_ids = set(), set()
    ref = {}
    for cid, c in calls.items():
        what, who = c.get("What_Id"), c.get("Who_Id")
        if what and what.get("id"):
            module = c.get("$se_module") or "Leads"
            ref[cid] = (module, what["id"])
            (lead_ids if module == "Leads" else contact_ids).add(what["id"])
        elif who and who.get("id"):
            ref[cid] = ("Contacts", who["id"])
            contact_ids.add(who["id"])
        else:
            ref[cid] = None

    print(f"🔎 {len(lead_ids)} leads, {len(contact_ids)} contacts to resolve…")
    leads = bulk_fetch(token, "Leads", lead_ids, LEAD_FIELDS) if lead_ids else {}
    contacts = bulk_fetch(token, "Contacts", contact_ids, CONTACT_FIELDS) if contact_ids else {}
    print(f"   got {len(leads)} leads, {len(contacts)} contacts")

    # Deals are a bonus signal (revenue/stage). In this org almost no call-linked
    # contact has one, so a rate-limit here must not cost us the whole run.
    deals = {}
    if contact_ids:
        print(f"💼 looking for deals on {len(contact_ids)} contacts…")
        try:
            deals = fetch_deals_for_contacts(token, sorted(contact_ids))
            print(f"   {len(deals)} contacts have a deal")
        except Exception as e:
            print(f"   ⚠ deal lookup stopped early ({e}); continuing without deal signals")

    def pick(rec, *names):
        for n in names:
            v = rec.get(n)
            if isinstance(v, dict):
                v = v.get("name") or v.get("id")
            if v not in (None, "", "None"):
                return v
        return None

    results = {}
    for cid in call_ids:
        c = calls.get(cid, {})
        r = ref.get(cid)
        row = {
            "linked_module": r[0] if r else None,
            "linked_id": r[1] if r else None,
            "owner": (c.get("Owner") or {}).get("name"),
            "lead_source": None, "campaign": None, "crm_stage": None, "pincode": None,
            "client_type": None, "property_type": None, "product_requirement": None,
            "lead_rating": None, "deal_stage": None, "deal_amount": None,
            "deal_product": None, "has_deal": False,
            "install_timeline": None, "deal_received": None, "deal_consoles": None,
        }
        if r:
            module, rid = r
            if module == "Leads" and rid in leads:
                L = leads[rid]
                row.update(
                    lead_source=pick(L, "Lead_Source", "Other_Source"),
                    campaign=pick(L, "Campaign_Name"),
                    crm_stage=pick(L, "Lead_Status", "Project_Stage"),
                    pincode=pick(L, "Zip_Code", "Address_1_Zip_Postal_Code"),
                    client_type=pick(L, "Client_Status", "Lead_Type"),
                    property_type=pick(L, "Type_of_Space", "Type_of_Space1"),
                    product_requirement=pick(L, "Experienced_SUNROOOF_before"),
                    install_timeline=pick(L, "By_when_should_sunroof_installation_be_done",
                                          "SUNROOOF_Handover_timeline"),
                    lead_rating=pick(L, "Priority_Type"))
            elif rid in contacts:
                C = contacts[rid]
                row.update(lead_source=pick(C, "Lead_Source"),
                           pincode=pick(C, "Mailing_Zip"))
                D = deals.get(rid)
                if D:
                    row.update(has_deal=True,
                               deal_stage=pick(D, "Stage"),
                               deal_amount=pick(D, "Proposed_Order_Amount", "Amount"),
                               deal_received=pick(D, "Total_Amount_Received"),
                               deal_consoles=pick(D, "Total_Consoles"),
                               deal_product=pick(D, "Product_Items"),
                               crm_stage=pick(D, "Stage", "Project_Stage"),
                               property_type=pick(D, "Type_of_Space1"),
                               install_timeline=pick(D, "SUNROOOF_Handover_timeline"),
                               pincode=row["pincode"] or pick(D, "Mailing_Zip",
                                                              "Shipping_Address_Zip_Postal_Code"))
        results[cid] = row

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, indent=1, ensure_ascii=False))

    def cov(k):
        n = sum(1 for v in results.values() if v.get(k))
        return f"{k}: {n}/{len(results)} ({round(100*n/max(1,len(results)))}%)"
    print(f"\n💾 wrote {OUT_FILE}")
    for k in ["linked_module", "lead_source", "campaign", "crm_stage", "pincode",
              "client_type", "property_type", "product_requirement", "install_timeline",
              "lead_rating", "has_deal", "deal_stage", "deal_amount", "deal_received",
              "deal_consoles"]:
        print("   " + cov(k))


if __name__ == "__main__":
    main()
