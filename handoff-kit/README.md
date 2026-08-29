# Sunrooof Call Intelligence — Handoff Kit

Give this folder (or the zip) to a fresh AI session to pick up this project
with all its context. Contains NO live secrets by design.

## Contents

- `PROJECT_CONTEXT.md` — **start here.** Everything important that isn't
  visible in the code: two dashboards (`dashboard/` + `ci-dashboard/`), how
  this project relates to its Magppie sibling projects on the same machine,
  exact current data state, what's blocked (Sarvam ran out of credits mid
  backfill) and how to resume it, account quirks, decisions and why, and
  measured costs.
- `.env.example` — annotated list of every env var the Python scripts and
  `dashboard/` need. Copy real values from the original machine's `.env` and
  `dashboard/.env.local` (folder: `/Users/UNICA/Desktop/call transcription
  sunrooof`). `ci-dashboard/` needs no env vars — it reads a build-time JSON
  snapshot instead of calling APIs directly.
- `claude-memory/` — the persistent memory files from the original AI
  sessions (working-style rules the user has stated explicitly, plus project
  facts). Place them in the new session's memory directory, or just ask the
  AI to read them.

## Quick start in a new session

1. Unzip somewhere, open a coding AI in an empty folder (or point it at the
   existing project folder directly).
2. Say: *"Read the handoff kit at <path>, then pick up the project it
   describes."*
3. Paste the real env values yourself when asked — never into the chat.

There is no GitHub remote for this project as of writing (unlike its Magppie
sibling, which is public). The kit is the only portable copy of this project's
non-code context.
