#!/usr/bin/env python3
"""Pull OpenAI org spend (and optionally token counts) from the Usage API.

This reports SPEND, not remaining credits. OpenAI exposes no API for the
credit balance at all -- that number only exists on the browser billing page
(platform.openai.com -> Settings -> Organization -> Billing -> Overview).
The workflow is: read the balance there once, then subtract what this
reports.

Needs OPENAI_ADMIN_KEY in .env (an sk-admin- key, created under Settings ->
Organization -> Admin keys, read-only scope is enough). The normal
sk-proj- inference key cannot read usage -- it 403s on api.usage.read.

Costs lag: the costs endpoint buckets by UTC day and the current day is
usually incomplete, so today's row will read low until it settles.

Usage:
    python scripts/openai_usage.py                       # last 30 days, daily
    python scripts/openai_usage.py --since 2026-06-01
    python scripts/openai_usage.py --since 2026-06-01 --group-by line_item
    python scripts/openai_usage.py --since 2026-06-01 --tokens
    python scripts/openai_usage.py --since 2026-06-01 --json
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv

load_dotenv()
ADMIN_KEY = os.getenv("OPENAI_ADMIN_KEY")
BASE = "https://api.openai.com/v1/organization"


def headers():
    if not ADMIN_KEY:
        sys.exit("OPENAI_ADMIN_KEY is not set in .env (needs an sk-admin- key).")
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def to_epoch(datestr):
    d = dt.datetime.strptime(datestr, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def fetch_all(path, params):
    """Walk the cursor until has_more is exhausted. Returns flat bucket list."""
    buckets = []
    page = None
    while True:
        p = dict(params)
        if page:
            p["page"] = page
        r = requests.get(f"{BASE}/{path}", headers=headers(), params=p, timeout=60)
        if r.status_code != 200:
            sys.exit(f"{path} -> HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        buckets.extend(body.get("data", []))
        if not body.get("has_more"):
            return buckets
        page = body.get("next_page")
        if not page:
            return buckets


def fetch_costs(start, end, group_by):
    params = {"start_time": start, "bucket_width": "1d", "limit": 180}
    if end:
        params["end_time"] = end
    if group_by:
        params["group_by[]"] = group_by
    return fetch_all("costs", params)


def fetch_tokens(start, end):
    # The usage endpoints cap limit at 31 for 1d buckets (costs allows 180),
    # so longer windows come back over several cursor pages.
    params = {"start_time": start, "bucket_width": "1d", "limit": 31}
    if end:
        params["end_time"] = end
    return fetch_all("usage/completions", params)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD (UTC). Default: 30 days ago.")
    ap.add_argument("--until", help="YYYY-MM-DD (UTC), exclusive.")
    ap.add_argument("--group-by", choices=["line_item", "project_id"],
                    help="Break the total down by model/endpoint or by project.")
    ap.add_argument("--tokens", action="store_true",
                    help="Also pull input/output token counts for completions.")
    ap.add_argument("--json", action="store_true", help="Raw JSON instead of a table.")
    args = ap.parse_args()

    if args.since:
        start = to_epoch(args.since)
    else:
        start = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).timestamp())
    end = to_epoch(args.until) if args.until else None

    buckets = fetch_costs(start, end, args.group_by)

    if args.json:
        print(json.dumps(buckets, indent=2))
        return

    per_day = defaultdict(float)
    per_group = defaultdict(float)
    currency = "usd"
    total = 0.0
    for b in buckets:
        for res in b.get("results", []):
            amt = (res.get("amount") or {})
            val = amt.get("value") or 0.0
            currency = amt.get("currency", currency)
            per_day[day(b["start_time"])] += val
            total += val
            if args.group_by:
                key = res.get(args.group_by) or "(ungrouped)"
                per_group[key] += val

    if not per_day:
        print("No cost data returned for that window.")
        print("(New spend can take a few hours to appear; check the window is not in the future.)")
        return

    print(f"OpenAI spend, {min(per_day)} .. {max(per_day)} (UTC days)\n")
    for d in sorted(per_day):
        if per_day[d]:
            print(f"  {d}   {per_day[d]:>10.4f} {currency.upper()}")
    print(f"\n  {'TOTAL':<10} {total:>10.4f} {currency.upper()}")

    if args.group_by and per_group:
        print(f"\nBy {args.group_by}:")
        for k, v in sorted(per_group.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<45} {v:>10.4f} {currency.upper()}")

    if args.tokens:
        tin = tout = calls = 0
        for b in fetch_tokens(start, end):
            for res in b.get("results", []):
                tin += res.get("input_tokens") or 0
                tout += res.get("output_tokens") or 0
                calls += res.get("num_model_requests") or 0
        print("\nCompletions usage:")
        print(f"  requests       {calls:>14,}")
        print(f"  input tokens   {tin:>14,}")
        print(f"  output tokens  {tout:>14,}")
        if calls:
            print(f"  cost/request   {total / calls:>14.5f} {currency.upper()}")

    print("\nNote: this is spend, not remaining credit. Read the balance from the "
          "billing overview page and subtract.")


if __name__ == "__main__":
    main()
