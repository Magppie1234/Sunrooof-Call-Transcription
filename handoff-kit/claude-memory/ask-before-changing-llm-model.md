---
name: ask-before-changing-llm-model
description: Never switch the LLM model used for call summarization without asking the user first
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 035b8b43-5741-4969-be98-65fc9a4bd4f7
  modified: 2026-07-31T05:44:37.205Z
---

Always ask before changing which LLM model runs the call summarization — including
"just to compare" test runs on a different model. The project standard is
gpt-4.1-mini (env overrides SUMMARY_MODEL / SUMMARY_PROVIDER exist; OpenRouter free
tier is a fallback only, 50 req/day).

**Why:** The model choice is the user's cost decision, not a technical detail. In
the original Magppie project (this repo is its Sunrooof clone) they said plainly:
"if you change models you always have to ask me", after an unasked nano-vs-mini
comparison run overwrote Supabase rows.

**How to apply:** Present model options with measured cost and quality evidence,
then wait. Per-token price is not the real cost — a weaker model can fail schema
validation and burn more tokens through the retry loop than a stronger one (nano
used 2x mini's input tokens on the same 3 calls). Before any bulk
re-summarization, back up the existing `call_summaries` rows so a bad run is
reversible.

Related: [[never-paste-api-keys-in-chat]]
