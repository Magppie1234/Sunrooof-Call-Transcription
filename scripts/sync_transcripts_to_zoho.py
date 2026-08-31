#!/usr/bin/env python3
"""Push the full diarised transcript of each call into Zoho CRM as a Note —
literally the same speaker-by-speaker conversation already shown in the
dashboard, so anyone on Zoho can read the call without opening the app.

Purely additive: always creates a brand-new Note, never edits or replaces
anything already on the Call (including our own AI-summary note from
sync_notes_to_zoho.py, which is a separate note entirely). Idempotent via a
local synced-set, same pattern as the rest of this pipeline.

Usage:
    python scripts/sync_transcripts_to_zoho.py --limit 5 --dry-run
    python scripts/sync_transcripts_to_zoho.py --limit 5
    python scripts/sync_transcripts_to_zoho.py                # all pending
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from batch_transcribe import ZOHO_API, ZOHO_ACC  # noqa: E402
from summarize_calls import agent_speaker_id  # noqa: E402 — same speaker heuristic as everywhere else
from sync_notes_to_zoho import ZohoAuth, zreq  # noqa: E402 — reuse the same auth/retry plumbing

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
TDIR = BASE / "out" / "transcripts"
SYNCED_FILE = BASE / "out" / "zoho_transcripts_synced.json"
REFORMAT_FILE = BASE / "out" / "zoho_transcripts_reformatted.json"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

TRANSCRIPT_MARKER = "[AI-Transcribed Call — Sunrooof Call Intelligence]"
# Zoho's documented Note_Content ceiling is 32,000 characters; stay well clear
# of it and split on turn boundaries (never mid-sentence) for the rare very
# long call (10 of 5021 calls have a raw transcript over 25k characters).
MAX_NOTE_CHARS = 28000
# Zoho's note viewer renders plain text only — HTML is shown as literal tags,
# and leading spaces collapse, so the old right-indent for the agent never
# survived and the note read as an undifferentiated wall of text. What does
# survive is a marker at the start of the line and a blank line between turns,
# so each turn becomes a labelled block: speaker line, then what they said.
CUSTOMER_MARK = "\U0001f464"   # 👤 customer
AGENT_MARK = "\U0001f3a7"      # 🎧 Sunrooof agent


def load_synced():
    if SYNCED_FILE.exists():
        return set(json.loads(SYNCED_FILE.read_text()))
    return set()


def mark_synced(call_id, synced_set):
    synced_set.add(call_id)
    SYNCED_FILE.write_text(json.dumps(sorted(synced_set)))


def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if extra:
        h.update(extra)
    return h


def fetch_names():
    """call_id -> (agent, customer), bulk from Supabase (same names already
    shown in the dashboard) rather than a per-call Zoho round-trip."""
    names, offset, page = {}, 0, 1000
    while True:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/call_summaries", headers=sb_headers(
            {"Range": f"{offset}-{offset + page - 1}"}), params={"select": "call_id,agent,customer"}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        for row in batch:
            names[row["call_id"]] = (row.get("agent") or "Agent", row.get("customer") or "Customer")
        if len(batch) < page:
            break
        offset += page
    return names


def compose_blocks(entries, agent_sid, agent_name, customer_name):
    """One block per turn: '👤 Name (role)' then the speech on the next line.

    Diarisation splits a single spoken turn into several entries whenever the
    speaker pauses, so consecutive entries from the same speaker are merged
    first — otherwise the same name header repeats three or four times in a row
    and the blank lines make the note longer without making it clearer. On a
    sample of 399 transcripts this removes 27% of the headers."""
    turns = []
    for e in entries:
        text = (e.get("transcript") or "").strip()
        if not text:
            continue
        sid = e.get("speaker_id")
        if turns and turns[-1][0] == sid:
            turns[-1][1].append(text)
        else:
            turns.append((sid, [text]))

    blocks = []
    for sid, parts in turns:
        is_agent = sid == agent_sid
        mark = AGENT_MARK if is_agent else CUSTOMER_MARK
        name = agent_name if is_agent else customer_name
        role = "Sunrooof" if is_agent else "customer"
        blocks.append(f"{mark} {name} ({role})\n{' '.join(parts)}")
    return blocks


def chunk_blocks(blocks, header):
    """Group blocks into <=MAX_NOTE_CHARS notes, splitting only between
    turns. Returns a list of note bodies (usually just one)."""
    chunks, cur, cur_len = [], [], len(header)
    for block in blocks:
        if cur and cur_len + len(block) + 2 > MAX_NOTE_CHARS:
            chunks.append(cur)
            cur, cur_len = [], len(header)
        cur.append(block)
        cur_len += len(block) + 2
    if cur:
        chunks.append(cur)
    n = len(chunks)
    return [f"{header}{' — part ' + str(i) + '/' + str(n) if n > 1 else ''}\n\n" + "\n\n".join(c)
            for i, c in enumerate(chunks, 1)]


def compose_notes(call_id, names):
    tpath = TDIR / f"{call_id}.mp3.json"
    if not tpath.exists():
        return None
    data = json.loads(tpath.read_text())
    entries = data.get("diarized_transcript", {}).get("entries", []) or []
    if not entries:
        return None
    agent_sid = agent_speaker_id(entries)
    agent_name, customer_name = names.get(call_id, ("Agent", "Customer"))
    blocks = compose_blocks(entries, agent_sid, agent_name, customer_name)
    if not blocks:
        return None
    return chunk_blocks(blocks, TRANSCRIPT_MARKER)


def part_number(content):
    """'…] — part 2/3' -> 2, so existing notes are reconciled in the right
    order. Single-part notes carry no suffix and sort first."""
    head = content.split("\n", 1)[0]
    m = re.search(r"— part (\d+)/\d+", head)
    return int(m.group(1)) if m else 1


def fetch_our_notes(call_id, auth):
    """Every note on this Call that WE wrote, in part order.

    Selection is by the full transcript marker, never a loose substring: the
    summary note written by sync_notes_to_zoho.py is marked '[AI-Generated
    Summary — Sunrooof Call Intelligence]' and shares the trailing words, so a
    sloppy match would rewrite or delete it. Anything an agent typed by hand has
    no marker at all and is likewise never returned here."""
    rows, page = [], 1
    while True:
        r = zreq("get", f"Calls/{call_id}/Notes", auth,
                 params={"fields": "Note_Content,Created_Time", "per_page": 200, "page": page})
        if r.status_code == 204:
            break
        r.raise_for_status()
        batch = r.json().get("data", [])
        rows.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    ours = [n for n in rows if TRANSCRIPT_MARKER in (n.get("Note_Content") or "")]
    ours.sort(key=lambda n: (part_number(n.get("Note_Content") or ""), n.get("Created_Time") or ""))
    return ours


def reformat_one(call_id, names, auth, dry_run=False):
    """Make this Call's transcript notes exactly match the current format, in
    place: rewrite what exists, add any missing part, delete any surplus note
    (which is how a call that ended up with two copies of the transcript gets
    back to one). Returns (status, updated, created, deleted)."""
    desired = compose_notes(call_id, names)
    if not desired:
        return "no-transcript", 0, 0, 0
    ours = fetch_our_notes(call_id, auth)
    updated = created = deleted = 0

    for i, body in enumerate(desired):
        if i < len(ours):
            if (ours[i].get("Note_Content") or "") == body:
                continue  # already in the new format
            if not dry_run:
                zreq("put", f"Calls/{call_id}/Notes/{ours[i]['id']}", auth,
                     json={"data": [{"Note_Content": body}]}).raise_for_status()
            updated += 1
        else:
            if not dry_run:
                zreq("post", f"Calls/{call_id}/Notes", auth,
                     json={"data": [{"Note_Content": body}]}).raise_for_status()
            created += 1

    for extra in ours[len(desired):]:
        if not dry_run:
            zreq("delete", f"Calls/{call_id}/Notes/{extra['id']}", auth).raise_for_status()
        deleted += 1

    return "ok", updated, created, deleted


def has_our_transcript(call_id, auth):
    r = zreq("get", f"Calls/{call_id}/Notes", auth, params={"fields": "Note_Content"})
    if r.status_code == 204:
        return False
    r.raise_for_status()
    return any(TRANSCRIPT_MARKER in (n.get("Note_Content") or "") for n in r.json().get("data", []))


def reformat_all(args):
    """Bring every already-written transcript note up to the current format.

    Separate state file from the normal sync: 'this call's notes have been
    reformatted' is a different fact from 'this call has been synced', and
    conflating them would make a resumed run skip calls it never rewrote."""
    done_ids = set(json.loads(REFORMAT_FILE.read_text())) if REFORMAT_FILE.exists() else set()
    names = fetch_names()
    all_ids = [args.only] if args.only else [f.name.removesuffix(".mp3.json")
                                             for f in sorted(TDIR.glob("*.json"))]
    pending = [c for c in all_ids if c not in done_ids or args.only]
    if args.limit:
        pending = pending[:args.limit]

    print(f"{'[dry-run] ' if args.dry_run else ''}{len(pending)} call(s) to reformat "
          f"({len(done_ids)} already done)\n")
    auth = ZohoAuth()
    tot = {"updated": 0, "created": 0, "deleted": 0, "untouched": 0, "no_transcript": 0, "failed": 0}

    for i, cid in enumerate(pending, 1):
        if i % 200 == 0:
            try:
                auth.refresh()
            except Exception as e:
                print(f"  ⚠ proactive token refresh failed, continuing: {e}")
        try:
            status, upd, cre, dele = reformat_one(cid, names, auth, args.dry_run)
            if status == "no-transcript":
                tot["no_transcript"] += 1
            elif upd or cre or dele:
                tot["updated"] += upd; tot["created"] += cre; tot["deleted"] += dele
                if dele or args.dry_run:
                    print(f"  {cid}: {upd} rewritten, {cre} added, {dele} duplicate(s) removed")
            else:
                tot["untouched"] += 1
            if not args.dry_run and not args.only:
                done_ids.add(cid)
                if i % 25 == 0:
                    REFORMAT_FILE.write_text(json.dumps(sorted(done_ids)))
        except Exception as e:
            print(f"  ❌ {cid}: {e}")
            tot["failed"] += 1
        if i % 250 == 0:
            print(f"  … {i}/{len(pending)} — {tot['updated']} rewritten, {tot['deleted']} duplicates removed")
        time.sleep(0.3)

    if not args.dry_run and not args.only:
        REFORMAT_FILE.write_text(json.dumps(sorted(done_ids)))
    print(f"\n✅ {tot['updated']} rewritten, {tot['created']} added, {tot['deleted']} duplicates removed, "
          f"{tot['untouched']} already current, {tot['no_transcript']} without a local transcript, "
          f"{tot['failed']} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reformat", action="store_true",
                    help="rewrite existing transcript notes into the current format "
                         "and collapse any call that has more than one copy")
    ap.add_argument("--only", help="restrict to a single call id (for spot-checking)")
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY"); sys.exit(1)

    if args.reformat:
        return reformat_all(args)

    synced = load_synced()
    names = fetch_names()
    all_ids = [f.name.removesuffix(".mp3.json") for f in sorted(TDIR.glob("*.json"))]
    pending = [cid for cid in all_ids if cid not in synced]
    if args.limit:
        pending = pending[:args.limit]

    print(f"{'[dry-run] ' if args.dry_run else ''}{len(pending)} call(s) to process "
          f"({len(synced)} already synced)\n")
    if not pending:
        return

    auth = None if args.dry_run else ZohoAuth()
    done = failed = skipped = 0
    for i, cid in enumerate(pending, 1):
        notes = compose_notes(cid, names)
        if not notes:
            skipped += 1
            continue

        if args.dry_run:
            print(f"── {cid} ── {len(notes)} note(s), {sum(len(n) for n in notes)} chars total")
            continue

        if i % 200 == 0:
            # Best-effort: if Zoho is rate-limiting token refreshes right now,
            # keep using the current token rather than crashing the whole run —
            # zreq()'s reactive 401-retry still covers real expiry.
            try:
                auth.refresh()
            except Exception as e:
                print(f"  ⚠ proactive token refresh failed, continuing with current token: {e}")

        try:
            if has_our_transcript(cid, auth):
                mark_synced(cid, synced)
                continue
            for note in notes:
                r = zreq("post", f"Calls/{cid}/Notes", auth, json={"data": [{"Note_Content": note}]})
                r.raise_for_status()
            mark_synced(cid, synced)
            done += 1
            if done % 100 == 0:
                print(f"  {done} done...")
        except Exception as e:
            print(f"  ❌ {cid}: {e}")
            failed += 1
        time.sleep(0.3)

    if not args.dry_run:
        print(f"\n✅ {done} synced, {skipped} skipped (no transcript text), {failed} failed")


if __name__ == "__main__":
    main()
