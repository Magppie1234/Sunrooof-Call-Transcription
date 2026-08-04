#!/usr/bin/env python3
"""
clean_names.py — Deterministic proper-noun cleanup for transcripts and summaries.

Free, no API. Normalises the many ways Sarvam mishears "Sunrooof" back to the
correct spelling, everywhere the name can appear:

  - local transcripts  (out/transcripts/*.mp3.json)
  - Supabase `transcripts`     (the copy the dashboard reads)
  - Supabase `call_summaries`  (summary, next_action, notes, objections, ...)

Usage:
    python scripts/clean_names.py                # fix everything, everywhere
    python scripts/clean_names.py --dry-run      # report changes, write nothing
    python scripts/clean_names.py --local-only   # skip Supabase
    python scripts/clean_names.py --ids id1,id2  # only these calls (local)

Re-running is safe — the correct spelling never matches its own variant set.

Mechanism: VARIANTS below — an explicit list. It is SEEDED with the obvious
ways an ASR model hears "Sunrooof" (it is spelled with three o's, so the
plain English word "sunroof" is itself the most common mishear). As real
transcripts come in, add every newly observed form here rather than loosening
the regex — explicit beats clever, a loose "sounds like Sunrooof" regex would
also eat legitimate words.

There is also an (optional) contextual rule: if agents always say the company
name right before a stable brand phrase or tagline, any token in that position
is the company name by definition, which catches unknown future mishears. Set
CONTEXT_RE below once real Sunrooof calls reveal such a phrase.
"""
import os, re, json, argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"

CORRECT = "Sunrooof"

# Likely mishearings, seeded before any real Sunrooof transcripts exist.
# Matched case-insensitively on word boundaries. As real call data comes in,
# add every observed form here rather than loosening the regex.
#
# NOTE: plain "sunroof" (the car part) is in this list on purpose. In these
# sales calls the word essentially always means the company; if a genuine
# car-sunroof discussion ever shows up in the data, move it to a SCOPED rule.
VARIANTS = [
    # sunroof-shaped (the dominant expected mishear — real English word)
    "sun ?roofs?", "sun ?roove?s?", "sun ?rooft?",
    # vowel/consonant drift
    "sun ?rufs?", "sun ?roofe", "sun ?ruff?", "sun ?roph", "sun ?roughs?",
    "sun ?roots?", "sun ?routes?", "sun ?roops?", "sun ?rupt?",
    # dropped/extra o's — careful: must never match "Sunrooof" itself
    "sunroof+", "sunrofs?", "sunroooo+fs?", "san ?roofs?", "son ?roofs?",
]

# Mishears that are also real words used legitimately elsewhere in the calls
# (place names, common nouns) must NOT be blanket-replaced. Put them here,
# scoped to a position where they can only be the company name — e.g. the
# agent's self-introduction. Add entries as real transcripts reveal them.
SCOPED = [
    # (re.compile(r"(?<=calling from )someword\b", re.IGNORECASE), CORRECT),
]

# Contextual catch-all for unknown future mishears. Observed in the first
# real transcripts (2026-07-31): agents pitch "Sunrooof wellness lighting" /
# "wellness lighting technology", so an unknown token right before "wellness
# light(ing)" is the company name — but only when the token is phonetically
# Sunrooof-shaped (starts with an s, then an n and an r sound). Without that
# guard this would eat generic phrasings like "our product wellness lighting".
CONTEXT_RE = re.compile(
    r"\b(?!Sunrooof\b)[Ss][A-Za-z']*[Nn][A-Za-z']*[Rr][A-Za-z']*"
    r"(?=\s+[Ww]ellness\s+[Ll]ight)",
)

def build_pattern():
    alts = [v for v in VARIANTS if v.lower() != CORRECT.lower()]
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.IGNORECASE)

VARIANT_RE = build_pattern()

def fix_text(text):
    """Returns (fixed_text, n_changes). Safe on None/empty."""
    if not text:
        return text, 0
    total = 0
    text, n = VARIANT_RE.subn(CORRECT, text); total += n
    for pat, repl in SCOPED:
        text, n = pat.subn(repl, text); total += n
    if CONTEXT_RE is not None:
        text, n = CONTEXT_RE.subn(CORRECT, text); total += n
    return text, total

def fix_list(items):
    if not items:
        return items, 0
    out, total = [], 0
    for s in items:
        s2, n = fix_text(s)
        out.append(s2); total += n
    return out, total

# ── Local transcript files ─────────────────────────────────────────────────
def process_local(dry_run, ids):
    files = sorted(TDIR.glob("*.json"))
    if ids:
        files = [f for f in files if f.name.removesuffix(".mp3.json") in ids]
    changed_files = total = 0
    for path in files:
        d = json.loads(path.read_text())
        n = 0
        d["transcript"], c = fix_text(d.get("transcript", "")); n += c
        for e in d.get("diarized_transcript", {}).get("entries", []):
            e["transcript"], c = fix_text(e.get("transcript", "")); n += c
        if n:
            changed_files += 1; total += n
            if not dry_run:
                path.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    return total, changed_files, len(files)

# ── Supabase ───────────────────────────────────────────────────────────────
def sb_config():
    from dotenv import load_dotenv
    load_dotenv()
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return url, {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

def sb_fetch_all(url, headers, table, select):
    """Paginated — PostgREST caps at 1000 rows per request."""
    import requests
    rows, offset, page = [], 0, 1000
    while True:
        h = dict(headers); h["Range"] = f"{offset}-{offset + page - 1}"
        r = requests.get(f"{url}/rest/v1/{table}", headers=h,
                         params={"select": select}, timeout=60)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if len(batch) < page:
            return rows
        offset += page

def sb_upsert(url, headers, table, rows):
    import requests
    h = dict(headers); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    for i in range(0, len(rows), 100):
        r = requests.post(f"{url}/rest/v1/{table}", headers=h,
                          data=json.dumps(rows[i:i + 100]), timeout=60)
        r.raise_for_status()

def process_supabase_transcripts(url, headers, dry_run):
    rows = sb_fetch_all(url, headers, "transcripts", "call_id,transcript")
    updates, total = [], 0
    for row in rows:
        d, n = row["transcript"], 0
        d["transcript"], c = fix_text(d.get("transcript", "")); n += c
        for e in d.get("diarized_transcript", {}).get("entries", []):
            e["transcript"], c = fix_text(e.get("transcript", "")); n += c
        if n:
            total += n
            updates.append({"call_id": row["call_id"], "transcript": d})
    if updates and not dry_run:
        sb_upsert(url, headers, "transcripts", updates)
    return total, len(updates), len(rows)

SUMMARY_TEXT_FIELDS = ["summary", "next_action", "professionalism_notes",
                       "room_type", "location", "timeline"]
SUMMARY_LIST_FIELDS = ["objections", "action_items", "red_flags"]

def process_supabase_summaries(url, headers, dry_run):
    cols = "call_id," + ",".join(SUMMARY_TEXT_FIELDS + SUMMARY_LIST_FIELDS)
    rows = sb_fetch_all(url, headers, "call_summaries", cols)
    updates, total = [], 0
    for row in rows:
        upd, n = {}, 0
        for f in SUMMARY_TEXT_FIELDS:
            v, c = fix_text(row.get(f))
            if c: upd[f] = v; n += c
        for f in SUMMARY_LIST_FIELDS:
            v, c = fix_list(row.get(f))
            if c: upd[f] = v; n += c
        if n:
            total += n
            updates.append({"call_id": row["call_id"], **upd})
    if updates and not dry_run:
        # PATCH per row: a partial upsert would null out unlisted NOT NULL cols.
        import requests
        h = dict(headers); h["Prefer"] = "return=minimal"
        for u in updates:
            cid = u.pop("call_id")
            r = requests.patch(f"{url}/rest/v1/call_summaries", headers=h,
                               params={"call_id": f"eq.{cid}"},
                               data=json.dumps(u), timeout=30)
            r.raise_for_status()
    return total, len(updates), len(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local-only", action="store_true", help="skip Supabase")
    ap.add_argument("--ids", type=str, default="", help="only these call ids (local files)")
    args = ap.parse_args()

    ids = set(filter(None, args.ids.split(",")))
    tag = "[dry-run] " if args.dry_run else ""
    verb = "would fix" if args.dry_run else "fixed"

    n, changed, seen = process_local(args.dry_run, ids)
    print(f"{tag}local transcripts:    {verb} {n} name(s) across {changed}/{seen} files")

    if args.local_only:
        return
    cfg = sb_config()
    if not cfg:
        print("  (skipping Supabase — SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set)")
        return
    url, headers = cfg

    n, changed, seen = process_supabase_transcripts(url, headers, args.dry_run)
    print(f"{tag}supabase transcripts: {verb} {n} name(s) across {changed}/{seen} rows")

    n, changed, seen = process_supabase_summaries(url, headers, args.dry_run)
    print(f"{tag}supabase summaries:   {verb} {n} name(s) across {changed}/{seen} rows")

if __name__ == "__main__":
    main()
