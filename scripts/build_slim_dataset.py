#!/usr/bin/env python3
"""
build_slim_dataset.py — split the two build-time snapshots into a light list
payload and per-call detail files.

    dataset.json    54.2 MB  ->  dataset.slim.json    + public/data/detail/<id>.json
    qa_audits.json  56.5 MB  ->  qa_audits.slim.json  + the same detail files

WHY
The dashboard bundles both snapshots as static imports, so the built app is a
single ~110 MB JavaScript file and every visitor downloads every transcript and
every per-criterion audit to look at the Overview. Measured on the 29 Aug
snapshot, the fields that only ever render on Call Detail are:

    dataset.json    transcript 29.4 MB · entities 0.9 · recordingUrl 0.5   = 56.9%
    qa_audits.json  criteria 31.6 MB · conduct 14.7                        = 82.1%

Measured result: 110.6 MB of snapshot becomes a 23.1 MB first paint, because
qa_audits.slim.json (10.0 MB) is reached only from Advanced QA, which is a lazy
route.

Splitting them on that line is not a judgement call — it is the same boundary
already drawn in Postgres between `dashboard_calls` and `call_detail`, and the
detail file's shape deliberately mirrors that table so the API route planned for
Sunday is a drop-in replacement for the fetch, with no change to the caller.

WHICH FIELDS ARE SAFE TO DROP, AND ONE THAT LOOKED SAFE AND IS NOT
transcript, entities and recordingUrl are read only by CallDetail.tsx. criteria
and conduct are read only one call at a time — by QaAuditPanel on Call Detail,
and by the AdvancedQa drawer.

`redFlags` and `reviewReasons` are the trap. They are audit detail by every
intuition and they are read in AdvancedQa's LIST view: a red-flag column, its
sort comparator, the CSV export and the needs-review flag. Moving them out would
have emptied a column and a flag with no error raised and no page broken — the
failure would have looked like data, not like a bug. They stay in the slim file.

That boundary is established by reading the code. H7 establishes it empirically
by diffing every KPI before and after; until then this note is a claim, not proof.

OUTPUT LAYOUT
`public/` rather than `src/`: Vite copies public/ verbatim and never bundles it,
which is the whole point — a file under src/ that anything imports lands back in
the JS. Detail files are fetched at runtime by call id.

Usage
-----
    python scripts/build_slim_dataset.py --dry-run   # measure, write nothing
    python scripts/build_slim_dataset.py             # write, then verify

On Windows run with PYTHONUTF8=1 or the emoji-free output still dies on a cp1252
console when a customer name is non-Latin.
"""
import argparse
import json

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REAL = BASE / "ci-dashboard" / "src" / "data" / "real"
PUBLIC_DETAIL = BASE / "ci-dashboard" / "public" / "data" / "detail"

DATASET = REAL / "dataset.json"
AUDITS = REAL / "qa_audits.json"
DATASET_SLIM = REAL / "dataset.slim.json"
AUDITS_SLIM = REAL / "qa_audits.slim.json"

# Heavy per-call fields, lifted out of the list payload into one detail file per
# call. Named explicitly rather than by size: a field that happens to be small
# in this snapshot but is only ever read on Call Detail still belongs in detail.
CALL_DETAIL_FIELDS = ("transcript", "entities", "recordingUrl")

# Only these two. `redFlags` and `reviewReasons` look like detail and are not:
# AdvancedQa.tsx reads them in its LIST view — a red-flag column, a sort, a CSV
# export and the needs-review flag (lines 107, 109, 117, 202). Stripping them
# would have emptied that column and the flag silently, with no error and no
# missing page. criteria and conduct are read only in the per-call drawer, which
# is the same access pattern as Call Detail, so those are the two that move.
AUDIT_DETAIL_FIELDS = ("criteria", "conduct")

# Measured against the 29 Aug snapshot. Assertions, not documentation.
EXPECT_CALLS = 6253
EXPECT_AUDITS = 6260

COMPACT = {"separators": (",", ":"), "ensure_ascii": False}


def mb(obj) -> float:
    return len(json.dumps(obj, **COMPACT).encode("utf-8")) / 1048576


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="measure the split and report it, write nothing")
    args = p.parse_args()

    print(f"[read] {DATASET.relative_to(BASE)}")
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    print(f"[read] {AUDITS.relative_to(BASE)}")
    audits_doc = json.loads(AUDITS.read_text(encoding="utf-8"))

    calls = data["calls"]
    audits = {str(a["id"]): a for a in audits_doc["calls"]}

    print()
    print(f"   calls   {len(calls):,} (expected {EXPECT_CALLS:,})")
    print(f"   audits  {len(audits):,} (expected {EXPECT_AUDITS:,})")
    if len(calls) != EXPECT_CALLS or len(audits) != EXPECT_AUDITS:
        print("   !  the snapshot has moved on since these numbers were measured")

    before_ds, before_qa = mb(data), mb(audits_doc)

    # --- build the three outputs -------------------------------------------
    # Detail is keyed by call id and carries both halves, so Call Detail makes
    # one request rather than two. Audits with no matching call (the seven
    # orphans) get no detail file: nothing can navigate to them.
    detail: dict[str, dict] = {}
    slim_calls = []
    for c in calls:
        cid = str(c["id"])
        d = {"callId": cid}
        for f in CALL_DETAIL_FIELDS:
            d[f] = c.get(f)
        # The WHOLE audit, not just the stripped fields. Two different callers
        # need it — QaAuditPanel on Call Detail and the AdvancedQa drawer — and
        # both want the scalars (score, tier, needsReview) alongside criteria and
        # conduct. Duplicating ~1.6 KB of scalars per call costs about 10 MB
        # spread across 6,253 files that are fetched one at a time, and buys a
        # detail fetch that neither caller has to combine with anything.
        d["qa"] = audits.get(cid)
        detail[cid] = d
        slim_calls.append({k: v for k, v in c.items() if k not in CALL_DETAIL_FIELDS})

    slim_data = {**data, "calls": slim_calls}
    slim_audits = {
        **audits_doc,
        "calls": [{k: v for k, v in a.items() if k not in AUDIT_DETAIL_FIELDS}
                  for a in audits_doc["calls"]],
    }

    after_ds, after_qa = mb(slim_data), mb(slim_audits)
    detail_total = sum(mb(d) for d in detail.values())
    biggest = max(detail.values(), key=mb)

    print()
    print(f"   {'':<22} {'before':>10} {'after':>10} {'saved':>10}")
    print(f"   {'dataset.json':<22} {before_ds:9.1f}M {after_ds:9.1f}M "
          f"{before_ds - after_ds:9.1f}M")
    print(f"   {'qa_audits.json':<22} {before_qa:9.1f}M {after_qa:9.1f}M "
          f"{before_qa - after_qa:9.1f}M")
    print(f"   {'first paint (sum)':<22} {before_ds + before_qa:9.1f}M "
          f"{after_ds:9.1f}M {before_ds + before_qa - after_ds:9.1f}M")
    print()
    print(f"   detail files            {len(detail):,} · {detail_total:.1f} MB total "
          f"· {detail_total / len(detail) * 1024:.0f} KB mean · {mb(biggest) * 1024:.0f} KB largest")
    print(f"   qa_audits.slim is lazy  loaded only on Advanced QA, not at first paint")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    # --- write --------------------------------------------------------------
    # Rewritten wholesale rather than merged: these are derived artefacts, and a
    # stale file left behind from an earlier snapshot would be indistinguishable
    # from a current one.
    # Files are unlinked individually and the directory is kept, rather than
    # rmtree + mkdir. On Windows the tree lives under OneDrive, whose sync filter
    # holds a handle on the directory for a moment after its contents go, so
    # rmtree deletes every file and then dies with WinError 5 on the empty
    # directory — leaving the split half-applied and exiting non-zero.
    PUBLIC_DETAIL.mkdir(parents=True, exist_ok=True)
    stale = list(PUBLIC_DETAIL.glob("*.json"))
    for f in stale:
        f.unlink()
    if stale:
        print(f"\n[clean] removed {len(stale):,} stale detail files")

    DATASET_SLIM.write_text(json.dumps(slim_data, **COMPACT), encoding="utf-8")
    AUDITS_SLIM.write_text(json.dumps(slim_audits, **COMPACT), encoding="utf-8")
    print(f"\n[write] {DATASET_SLIM.relative_to(BASE)}")
    print(f"[write] {AUDITS_SLIM.relative_to(BASE)}")

    for cid, d in detail.items():
        (PUBLIC_DETAIL / f"{cid}.json").write_text(json.dumps(d, **COMPACT), encoding="utf-8")
    print(f"[write] {PUBLIC_DETAIL.relative_to(BASE)}/  ({len(detail):,} files)")

    # --- verify -------------------------------------------------------------
    print("\n[verify] exit code 0 is not evidence")
    ok = True
    written = list(PUBLIC_DETAIL.glob("*.json"))
    checks = [
        ("detail files on disk", len(written), len(calls)),
        ("slim calls", len(json.loads(DATASET_SLIM.read_text(encoding="utf-8"))["calls"]), len(calls)),
        ("slim audits", len(json.loads(AUDITS_SLIM.read_text(encoding="utf-8"))["calls"]), len(audits)),
    ]
    for label, got, expected in checks:
        good = got == expected
        ok &= good
        print(f"   {'ok  ' if good else 'FAIL'} {label:<22} {got:>6,}  expected {expected:,}")

    # No heavy field may survive in either slim file — the saving is the point,
    # and a field left behind would be invisible except as a size regression.
    leaked = [f for f in CALL_DETAIL_FIELDS if f in json.loads(
        DATASET_SLIM.read_text(encoding="utf-8"))["calls"][0]]
    leaked += [f for f in AUDIT_DETAIL_FIELDS if f in json.loads(
        AUDITS_SLIM.read_text(encoding="utf-8"))["calls"][0]]
    good = not leaked
    ok &= good
    print(f"   {'ok  ' if good else 'FAIL'} {'no heavy field leaked':<22} "
          f"{'none' if good else ', '.join(leaked)}")

    # A detail file must round-trip to the same call it came from.
    sample = json.loads((PUBLIC_DETAIL / f"{calls[0]['id']}.json").read_text(encoding="utf-8"))
    good = sample["callId"] == str(calls[0]["id"]) and sample["transcript"] == calls[0].get("transcript")
    ok &= good
    print(f"   {'ok  ' if good else 'FAIL'} {'sample round-trips':<22} {calls[0]['id']}")

    if not ok:
        print("\nThe split does not match the snapshot. Stop before wiring anything to it.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
