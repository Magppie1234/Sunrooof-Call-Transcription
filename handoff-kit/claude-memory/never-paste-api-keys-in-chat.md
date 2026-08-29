---
name: never-paste-api-keys-in-chat
description: API keys go directly into .env by the user; never accept or echo a key in chat
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 035b8b43-5741-4969-be98-65fc9a4bd4f7
  modified: 2026-07-31T05:44:31.982Z
---

Never accept an API key pasted into the conversation, and never print a key value.
The user pastes it into `.env` / `dashboard/.env.local` themselves and says "done";
verification is by presence, length and prefix only (e.g. `len(k)`, `k[:8]`).

**Why:** Anything in the chat transcript is stored and may be replayed. This rule
was set by the user in the original Magppie project (this repo is its Sunrooof
clone) after keys were offered in chat more than once.

**How to apply:** Append an empty `KEY_NAME=` placeholder to the right env file,
tell the user which file and line, and have them save it. `.env` and
`dashboard/.env.local` are gitignored; `.env.example` is committed and must only
ever hold empty placeholders — a real key in it once tripped GitHub push
protection. Scan every diff for secret-shaped strings before committing.

Related: [[ask-before-changing-llm-model]], [[transcripts-contain-customer-pii]]
