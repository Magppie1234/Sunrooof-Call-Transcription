#!/usr/bin/env python3
"""
load_dashboard_tables.py — Load the dashboard's build-time JSON snapshots into
the Supabase tables created by
supabase/migrations/20260829105655_dashboard_tables.sql.

    dataset.json    (6,253 calls)  -> dashboard_calls, call_detail
    qa_audits.json  (6,260 audits) -> dashboard_calls.qa_*, call_detail.qa_*

`call_actions` is deliberately left empty. It is an append-only log of human
actions on a call — the one table here holding data the pipeline cannot
regenerate. There is no history to load, and manufacturing rows would poison
exactly the trail the CRM write-back governance position depends on.

Writes over PostgREST with the service-role key, so no Postgres password is
needed. Upserts on call_id (`Prefer: resolution=merge-duplicates`), so a re-run
after a dataset rebuild is safe. Note that is an upsert, not
`ON CONFLICT DO NOTHING`: the "6,260-row file holding 4,965 unique calls"
incident began with a silent discard under a plausible-looking count.

Order matters: call_detail.call_id and call_actions.call_id are foreign keys
into dashboard_calls, so dashboard_calls is loaded in full first.

Usage
-----
    python scripts/load_dashboard_tables.py --dry-run   # validate, write nothing
    python scripts/load_dashboard_tables.py             # load, then verify
    python scripts/load_dashboard_tables.py --verify-only

On Windows the console is cp1252 and this script prints emoji, so run it with
PYTHONUTF8=1 or output dies mid-run on UnicodeEncodeError — which looks like a
failure and is not one.
"""
import argparse
import json
import os
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
import requests

BASE = Path(__file__).resolve().parent.parent

# Explicit path: load_dotenv() finds .env by walking the call stack, which has no
# calling frame when this file is piped in rather than run from disk.
load_dotenv(BASE / ".env")

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

DATASET = BASE / "ci-dashboard" / "src" / "data" / "real" / "dataset.json"
AUDITS = BASE / "ci-dashboard" / "src" / "data" / "real" / "qa_audits.json"

# ---------------------------------------------------------------------------
# Expected values, measured against the 29 Aug 2026 snapshot and copied from the
# migration's own verification block. These are assertions, not documentation:
# a load that disagrees is wrong and should say so rather than report success.
# ---------------------------------------------------------------------------
EXPECT_CALLS = 6253
EXPECT_SCORED = 4342
EXPECT_ORPHAN_AUDITS = 7
EXPECT_EMPLOYEES = 17
EXPECT_GEO = 456
# The audit set is SEVEN ROWS LARGER than the dataset: calls where Sarvam
# returned an empty transcript are dropped by build_ci_dataset.py and kept,
# ungraded, by the audit pipeline. Both are right. See EXPECT_ORPHAN_AUDITS.
EXPECT_AUDITS = 6260

# The dashboard anchors its default period to the newest call plus one day, NOT
# to midnight. The calendar-day version of this range returns 4,858 — close
# enough to pass a glance and wrong.
PERIOD_START = "2026-07-02T13:20:23+00:00"
PERIOD_END = "2026-08-01T13:20:23+00:00"
EXPECT_PERIOD = 4655

# Tier floors, mirrored from scripts/call_quality.py, used only to report which
# calls a rounded qa_score would put in a different band from their stored tier.
TIERS = [(85.0, "GOLD"), (75.0, "SILVER"), (60.0, "BRONZE"), (50.0, "DEVELOPING")]

# ---------------------------------------------------------------------------
# Field mapping
#
# The typed columns are what matchesDims() in ci-dashboard/src/lib/filters.ts
# actually narrows on. Anything not named here falls through to `payload`, which
# is the safe direction: a field added to dataset.json lands in jsonb rather
# than being dropped on the floor.
# ---------------------------------------------------------------------------
TYPED = {
    "id": "call_id",
    "dateTime": "call_ts",
    "employeeId": "employee_id",
    "customerId": "customer_id",
    "customerName": "customer_name",
    "customerType": "customer_type",
    "direction": "direction",
    "durationSec": "duration_sec",
    "language": "language",
    "connected": "connected",
    "meaningful": "meaningful",
    "transcribed": "transcribed",
    "transcriptionConfidence": "transcription_confidence",
    "diarizationReliable": "diarization_reliable",
    "region": "region",
    "state": "state",
    "city": "city",
    "productSeries": "product_series",
    "leadSource": "lead_source",
    "campaign": "campaign",
    "crmStage": "crm_stage",
    "outcome": "outcome",
    "intent": "intent",
    "summary": "summary",
    "topics": "topics",
}

# Derived columns, flattened out of nested objects because the filter bar reads
# them directly. The full sentiment object and complianceFlags array stay in
# payload — this is a copy, not a move.
DERIVED = ("sentiment_overall", "compliance_flag_count", "qa_score", "qa_tier", "qa_status")

# Heavy fields that live in call_detail and must NOT be duplicated into payload.
DETAIL_FROM_CALL = {"transcript", "entities", "recordingUrl"}

# NOT NULL in the DDL with a false default; a null from the source would be
# rejected by Postgres, so coerce rather than send one.
BOOL_NOT_NULL = ("connected", "meaningful", "transcribed", "diarization_reliable")

BATCH_CALLS = 250
BATCH_DETAIL = 50


def headers(extra=None):
    h = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    if extra:
        h.update(extra)
    return h


def column_format(session, table, column):
    """The column's live Postgres type, from the PostgREST OpenAPI spec.

    Read rather than assumed, so that widening qa_score to numeric clears the
    fractional-score block on its own instead of needing this file edited too.
    Returns None if the spec cannot be reached; the caller treats that as the
    conservative case.
    """
    try:
        r = session.get(f"{URL}/rest/v1/", headers=headers(), timeout=30)
        r.raise_for_status()
        spec = r.json()["definitions"][table]["properties"][column]
        return spec.get("format")
    except (requests.RequestException, KeyError, ValueError):
        return None


def tier_for(score):
    if score is None:
        return "NOT_SCORED"
    for floor, name in TIERS:
        if score >= floor:
            return name
    return "AT_RISK"


def pg_round(value):
    """Round the way Postgres casts numeric to integer: half away from zero."""
    return int(Decimal(str(value)).quantize(0, rounding=ROUND_HALF_UP))


def is_integer_column(fmt):
    """True when the column cannot hold a decimal. An unreadable spec counts as
    narrow: assuming the permissive case is what loses data quietly."""
    return fmt is None or fmt.startswith(("integer", "bigint", "smallint"))


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------
def call_row(call, audit, round_scores):
    row = {}
    for src, col in TYPED.items():
        row[col] = call.get(src)

    for col in BOOL_NOT_NULL:
        row[col] = bool(row.get(col))

    if row.get("topics") is None:
        row["topics"] = []

    # matchesDims() compares against `c.sentiment?.overall ?? 'not_analysed'`,
    # so the flattened column stores that same fallback. A null here would make
    # the SQL filter and the current client-side filter disagree on 4 calls.
    sentiment = call.get("sentiment")
    row["sentiment_overall"] = (sentiment or {}).get("overall") or "not_analysed"

    row["compliance_flag_count"] = len(call.get("complianceFlags") or [])

    score = (audit or {}).get("score")
    if score is not None and round_scores:
        score = pg_round(score)
    row["qa_score"] = score
    row["qa_tier"] = (audit or {}).get("tier")
    row["qa_status"] = (audit or {}).get("status")

    # Everything no query filters on. Built by difference so a field added to
    # the dataset is carried into jsonb rather than silently lost.
    row["payload"] = {
        k: v for k, v in call.items()
        if k not in TYPED and k not in DETAIL_FROM_CALL
    }
    return row


# Audit fields that have a column of their own in call_detail. Everything else
# goes to qa_meta, by difference — so an audit field added upstream is carried
# rather than dropped, the same way payload works in dashboard_calls.
AUDIT_OWN_COLUMNS = ("criteria", "conduct", "redFlags", "reviewReasons")


# criteria and conduct are the heavy per-criterion fields — 46 MB across the
# corpus — and live in call_detail, read only when one audit is opened. Same
# split build_slim_dataset.py makes for the static files.
AUDIT_HEAVY_FIELDS = ("criteria", "conduct")
# Typed on qa_audits; everything else falls through to payload.
AUDIT_TYPED = {"score": "score", "tier": "tier", "status": "status"}


def audit_rows(audits):
    """One row per audited call, all 6,260 — including the seven with no
    dashboard_calls row. Those are the reason qa_audits has no foreign key."""
    rows = []
    for a in audits.values():
        payload = {k: v for k, v in a.items()
                   if k not in AUDIT_HEAVY_FIELDS and k not in AUDIT_TYPED and k != "id"}
        rows.append({
            "call_id": a["id"],
            "score": a.get("score"),
            "tier": a.get("tier"),
            "status": a.get("status"),
            "payload": payload,
        })
    return rows


def audit_run_row(audit_file):
    """The wrapper AdvancedQa.tsx reads for its header.

    generated_at goes in as the RAW STRING. The page prints its first sixteen
    characters, and the value carries a +0530 offset; normalised to UTC it would
    render five and a half hours early with nothing raising an error.
    """
    return {
        "id": True,
        "generated_at": audit_file["generatedAt"],
        "corpus_size": audit_file["corpusSize"],
        "audited_count": audit_file["auditedCount"],
        "model": audit_file["model"],
        "scorecard": audit_file["scorecard"],
    }


def employee_rows(dataset):
    """The agent roster, straight out of the snapshot.

    build_ci_dataset.py already resolved these names against Zoho; re-deriving
    them from dashboard_calls.employee_id would give a second definition of who
    the agents are, and team/manager/role are not on a call row at all.
    """
    return [
        {
            "employee_id": e["id"],
            "name": e["name"],
            "team": e.get("team"),
            "manager": e.get("manager"),
            "role": e.get("role"),
        }
        for e in dataset["employees"]
    ]


def geo_rows(calls):
    """Distinct region/state/city triples, ordered as data/taxonomy.ts orders them.

    First occurrence wins, then a stable sort on (region, state) — the exact
    shape of dedupeGeo() in the dashboard, so the cascading region -> state
    dropdowns offer the same options in the same order whichever mode the app
    runs in.

    The TypeScript sorts with localeCompare and this sorts by code point. On the
    29 Aug 2026 snapshot the two orderings are identical, checked row by row
    rather than assumed: every region and state is ASCII and capitalised, and
    the three non-ASCII values ('Dubai' spelt three ways) are all cities, which
    are not part of the sort key. It matters only until the dashboard stops
    building this list for itself, after which this is the only definition.
    """
    seen = set()
    out = []
    for c in calls:
        key = (c["region"], c["state"], c["city"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"region": c["region"], "state": c["state"], "city": c["city"], "pin": ""})
    out.sort(key=lambda g: (g["region"], g["state"]))
    return out


def snapshot_row(dataset):
    """The single dashboard_snapshot row.

    taxonomy is stored verbatim. It is not recomputed here and must not be
    recomputed in SQL: the Python that built it applied its own normalisation
    while joining Zoho, Sarvam and the enrichment files, and a second definition
    would agree today and drift the first time that changes.
    """
    return {
        "id": True,
        "generated_at": dataset["generatedAt"],
        "source_label": dataset["sourceLabel"],
        "taxonomy": dataset["taxonomy"],
        "geo": geo_rows(dataset["calls"]),
    }


def detail_row(call, audit):
    a = audit or {}
    return {
        "call_id": call["id"],
        "transcript": call.get("transcript"),
        "entities": call.get("entities"),
        "recording_url": call.get("recordingUrl"),
        "qa_criteria": a.get("criteria"),
        "qa_conduct": a.get("conduct"),
        "qa_red_flags": a.get("redFlags"),
        "qa_review_reasons": a.get("reviewReasons"),
        # QaAuditPanel reads context, contextReason and agent, none of which had
        # a home before this. Without them GET /api/call/[id] renders a panel
        # missing the subtitle that explains why a call scored as it did, while
        # the static detail files render it in full — the same page differing by
        # where its data came from, with nothing raising an error.
        "qa_meta": {k: v for k, v in a.items() if k not in AUDIT_OWN_COLUMNS} or None,
    }


# ---------------------------------------------------------------------------
# Preflight — every check that can fail the load, before a single row is written
# ---------------------------------------------------------------------------
def preflight(calls, audits, args, qa_score_fmt):
    problems = []

    ids = [c.get("id") for c in calls]
    unique = set(ids)
    print(f"   dataset calls          {len(calls):,} ({len(unique):,} unique)")
    if len(unique) != len(ids):
        problems.append(f"dataset.json holds {len(ids) - len(unique)} duplicate call_ids")
    if len(calls) != EXPECT_CALLS:
        print(f"   !  expected {EXPECT_CALLS:,} calls - the snapshot has moved on")

    print(f"   audits                 {len(audits):,}")

    orphans = sorted(set(audits) - unique)
    print(f"   audits with no call    {len(orphans)} (expected {EXPECT_ORPHAN_AUDITS})")
    if len(orphans) != EXPECT_ORPHAN_AUDITS:
        problems.append(
            f"{len(orphans)} audits reference call_ids absent from the dataset, expected "
            f"exactly {EXPECT_ORPHAN_AUDITS}. Those seven are the calls Sarvam returned an "
            f"empty transcript for. A different number means something changed and is "
            f"worth stopping for.\n"
            f"        {', '.join(orphans[:12])}"
        )
    else:
        for cid in orphans:
            a = audits[cid]
            print(f"      skip {cid}  tier={a.get('tier')} score={a.get('score')}")

    missing_audit = [i for i in ids if i not in audits]
    print(f"   calls with no audit    {len(missing_audit)}")
    if missing_audit:
        print(f"      qa_* stays null for these, e.g. {missing_audit[:5]}")

    no_employee = [c["id"] for c in calls if not c.get("employeeId")]
    no_ts = [c["id"] for c in calls if not c.get("dateTime")]
    if no_employee:
        problems.append(f"{len(no_employee)} calls have no employeeId (NOT NULL): {no_employee[:5]}")
    if no_ts:
        problems.append(f"{len(no_ts)} calls have no dateTime (NOT NULL): {no_ts[:5]}")

    scored = [audits[i] for i in ids if audits.get(i, {}).get("score") is not None]
    print(f"   scored calls           {len(scored):,} (expected {EXPECT_SCORED:,})")

    lo, hi = datetime.fromisoformat(PERIOD_START), datetime.fromisoformat(PERIOD_END)
    in_period = 0
    for c in calls:
        try:
            t = datetime.fromisoformat(c["dateTime"])
        except (TypeError, ValueError):
            continue
        if lo <= t < hi:
            in_period += 1
    print(f"   default period window  {in_period:,} (expected {EXPECT_PERIOD:,})")
    if in_period != EXPECT_PERIOD:
        print("   !  the Executive Overview total will not match the current build")

    # Some scores carry one decimal place. If qa_score is still an integer
    # column, sending them unrounded lets Postgres round on the way in,
    # silently, which is how a score ends up contradicting its own tier.
    fractional = [a for a in scored if float(a["score"]) != int(a["score"])]
    narrow = is_integer_column(qa_score_fmt)
    print(f"   qa_score column        {qa_score_fmt or 'unreadable, assuming integer'}")
    if fractional and narrow:
        flips = [
            a for a in fractional
            if tier_for(float(pg_round(a["score"]))) != tier_for(float(a["score"]))
        ]
        print()
        print(f"   !  {len(fractional):,} of {len(scored):,} scores are fractional and "
              f"qa_score cannot hold them")
        for a in flips:
            print(f"      {a['id']}  {a['score']} -> {pg_round(a['score'])} lands in "
                  f"{tier_for(float(pg_round(a['score'])))} while qa_tier stays {a['tier']}")
        if not args.allow_score_rounding:
            problems.append(
                f"{len(fractional):,} fractional qa_score values would be rounded by the "
                f"integer column, {len(flips)} of them into a band that contradicts the "
                f"stored qa_tier.\n"
                f"        Apply supabase/migrations/20260829143906_qa_score_numeric.sql, "
                f"which widens the column to numeric(4,1), then re-run.\n"
                f"        Or accept the rounding explicitly with --allow-score-rounding."
            )
    elif fractional:
        print(f"   fractional scores      {len(fractional):,}, held exactly by {qa_score_fmt}")

    return problems


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def post_batch(session, table, rows, attempts=4):
    for attempt in range(1, attempts + 1):
        try:
            r = session.post(
                f"{URL}/rest/v1/{table}",
                headers=headers(),
                data=json.dumps(rows).encode("utf-8"),
                timeout=180,
            )
            if r.status_code in (429, 500, 502, 503, 504) and attempt < attempts:
                wait = 2 ** attempt
                print(f"      {r.status_code} on {table}, retry {attempt}/{attempts - 1} in {wait}s")
                time.sleep(wait)
                continue
            if not r.ok:
                raise RuntimeError(f"{r.status_code} {r.text[:400]}")
            return
        except requests.RequestException as e:
            if attempt >= attempts:
                raise RuntimeError(str(e)) from e
            wait = 2 ** attempt
            print(f"      {type(e).__name__} on {table}, retry {attempt}/{attempts - 1} in {wait}s")
            time.sleep(wait)


def load(session, table, rows, size):
    print(f"\n[load] {table}: {len(rows):,} rows in batches of {size}")
    done = 0
    for i in range(0, len(rows), size):
        batch = rows[i:i + size]
        post_batch(session, table, batch)
        done += len(batch)
        print(f"   {done:,}/{len(rows):,}")
    return done


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
def count(session, table, params):
    # Params go through requests rather than into the path: the period bounds
    # carry a +00:00 offset, and an unencoded '+' in a query string is a space
    # by the time PostgREST parses it, which fails as an invalid timestamp.
    r = session.get(
        f"{URL}/rest/v1/{table}",
        params=params,
        headers=headers({"Prefer": "count=exact", "Range": "0-0"}),
        timeout=60,
    )
    r.raise_for_status()
    return int(r.headers["Content-Range"].split("/")[-1])


def verify(session):
    print("\n[verify] exit code 0 is not evidence")
    # count(distinct call_id) is not checked separately: call_id is the primary
    # key, so it cannot differ from count(*).
    checks = [
        ("dashboard_calls", "dashboard_calls", {"select": "call_id"}, EXPECT_CALLS),
        ("call_detail", "call_detail", {"select": "call_id"}, EXPECT_CALLS),
        ("qa_score not null", "dashboard_calls",
         {"select": "call_id", "qa_score": "not.is.null"}, EXPECT_SCORED),
        ("default period window", "dashboard_calls",
         {"select": "call_id", "call_ts": [f"gte.{PERIOD_START}", f"lt.{PERIOD_END}"]},
         EXPECT_PERIOD),
        ("dashboard_employees", "dashboard_employees",
         {"select": "employee_id"}, EXPECT_EMPLOYEES),
        ("dashboard_snapshot", "dashboard_snapshot", {"select": "id"}, 1),
        ("qa_audits", "qa_audits", {"select": "call_id"}, EXPECT_AUDITS),
        ("qa_audits scored", "qa_audits",
         {"select": "call_id", "score": "not.is.null"}, EXPECT_SCORED),
        ("qa_audit_run", "qa_audit_run", {"select": "id"}, 1),
    ]
    ok = True
    for label, table, params, expected in checks:
        got = count(session, table, params)
        if got != expected:
            ok = False
        mark = "ok  " if got == expected else "FAIL"
        print(f"   {mark} {label:<24} {got:>6,}  expected {expected:,}")
    # dashboard_meta is a view over one row, so a row count proves nothing about
    # what is IN that row: an empty taxonomy and a full one both count as 1.
    # Read the view the API actually reads and measure its contents.
    r = session.get(
        f"{URL}/rest/v1/dashboard_meta",
        params={"select": "call_count,max_ts,geo,taxonomy"},
        headers=headers({"Accept": "application/json"}),
        timeout=60,
    )
    r.raise_for_status()
    rows = r.json()
    if len(rows) != 1:
        print(f"   FAIL dashboard_meta            {len(rows)} rows, expected exactly 1")
        return False
    meta = rows[0]
    for label, got, expected in [
        ("meta call_count", int(meta["call_count"]), EXPECT_CALLS),
        ("meta geo triples", len(meta["geo"]), EXPECT_GEO),
        ("meta taxonomy keys", len(meta["taxonomy"]), 8),
    ]:
        if got != expected:
            ok = False
        print(f"   {'ok  ' if got == expected else 'FAIL'} {label:<24} {got:>6,}  expected {expected:,}")

    # The anchor the whole date filter hangs off. PERIOD_END is max_ts plus one
    # day, and the 4,655-call window checked above is measured from it, so a
    # max_ts that has moved invalidates every period figure on the dashboard.
    anchor = datetime.fromisoformat(meta["max_ts"]) + timedelta(days=1)
    want = datetime.fromisoformat(PERIOD_END)
    if anchor != want:
        ok = False
    print(f"   {'ok  ' if anchor == want else 'FAIL'} {'meta anchor':<24} "
          f"{anchor.isoformat()}  expected {want.isoformat()}")

    if not ok:
        print("\nThe load does not match the snapshot. Stop and find out why before "
              "trusting anything downstream.")
    return ok


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="read and validate the snapshots, report what would be written, touch nothing")
    p.add_argument("--verify-only", action="store_true",
                   help="run the verification counts against Supabase and exit")
    p.add_argument("--allow-score-rounding", action="store_true",
                   help="accept that fractional qa_score values are rounded into the integer column")
    p.add_argument("--only", choices=("all", "calls", "detail", "meta", "qa"), default="all",
                   help="load one table group instead of everything. call_detail is 97 MB and "
                        "several minutes; reloading it to change 17 employee rows is waste. "
                        "Verification always runs in full, whatever was loaded.")
    p.add_argument("--dataset", type=Path, default=DATASET)
    p.add_argument("--audits", type=Path, default=AUDITS)
    p.add_argument("--batch-size", type=int, default=BATCH_CALLS)
    p.add_argument("--detail-batch-size", type=int, default=BATCH_DETAIL)
    args = p.parse_args()

    if not URL or not KEY:
        print("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    session = requests.Session()

    if args.verify_only:
        sys.exit(0 if verify(session) else 2)

    print(f"[read] {args.dataset.relative_to(BASE)}")
    print(f"[read] {args.audits.relative_to(BASE)}")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    calls = dataset["calls"]
    audit_file = json.loads(args.audits.read_text(encoding="utf-8"))
    audits = {a["id"]: a for a in audit_file["calls"]}

    print("\n[preflight]")
    qa_score_fmt = column_format(session, "dashboard_calls", "qa_score")
    problems = preflight(calls, audits, args, qa_score_fmt)
    if problems:
        print("\nRefusing to load:")
        for i, prob in enumerate(problems, 1):
            print(f"   {i}. {prob}")
        sys.exit(2)
    print("\n   preflight clean")

    # Round only when the column genuinely cannot hold the decimal. Once
    # qa_score is numeric, --allow-score-rounding stops doing anything.
    round_scores = args.allow_score_rounding and is_integer_column(qa_score_fmt)
    call_rows = [call_row(c, audits.get(c["id"]), round_scores) for c in calls]
    detail_rows = [detail_row(c, audits.get(c["id"])) for c in calls]
    emp_rows = employee_rows(dataset)
    snap = snapshot_row(dataset)
    qa_rows = audit_rows(audits)
    qa_run = audit_run_row(audit_file)

    calls_mb = len(json.dumps(call_rows)) / 1e6
    detail_mb = len(json.dumps(detail_rows)) / 1e6
    payload_keys = sorted(call_rows[0]["payload"].keys())
    print(f"\n[plan] dashboard_calls  {len(call_rows):,} rows, {calls_mb:.1f} MB "
          f"({len(TYPED) + len(DERIVED)} typed columns + {len(payload_keys)} payload keys)")
    print(f"[plan] call_detail      {len(detail_rows):,} rows, {detail_mb:.1f} MB")
    print(f"[plan] call_actions     0 rows - append-only, nothing to backfill")
    print(f"[plan] dashboard_employees {len(emp_rows):,} rows")
    qa_mb = len(json.dumps(qa_rows)) / 1e6
    print(f"[plan] qa_audits         {len(qa_rows):,} rows, {qa_mb:.1f} MB "
          f"({len(qa_rows) - len(calls)} more than the dataset, expected {EXPECT_ORPHAN_AUDITS})")
    print(f"[plan] dashboard_snapshot  1 row, {len(snap['geo']):,} geo triples, "
          f"taxonomy: {', '.join(f'{k} {len(v)}' for k, v in snap['taxonomy'].items())}")
    print(f"       payload: {', '.join(payload_keys)}")

    if args.dry_run:
        print("\n[dry-run] nothing written. Sample dashboard_calls row:")
        sample = dict(call_rows[0])
        sample["payload"] = f"<{len(payload_keys)} keys>"
        sample["summary"] = (sample.get("summary") or "")[:60] + "..."
        for k, v in sample.items():
            print(f"       {k:<26} {v!r}")
        print("\n   Re-run without --dry-run to load.")
        return

    want = args.only
    if want in ("all", "meta"):
        load(session, "dashboard_employees", emp_rows, args.batch_size)
    if want in ("all", "qa"):
        load(session, "qa_audits", qa_rows, args.batch_size)
        load(session, "qa_audit_run", [qa_run], 1)
    if want in ("all", "calls"):
        load(session, "dashboard_calls", call_rows, args.batch_size)
    if want in ("all", "detail"):
        load(session, "call_detail", detail_rows, args.detail_batch_size)
    if want in ("all", "meta"):
        # Last, so its generated_at means "everything above this is loaded".
        load(session, "dashboard_snapshot", [snap], 1)

    sys.exit(0 if verify(session) else 2)


if __name__ == "__main__":
    main()
