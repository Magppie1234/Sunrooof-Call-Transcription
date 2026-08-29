---
name: transcripts-contain-customer-pii
description: "Call transcripts hold real customer names/PII; never commit them, and any NEW vendor needs the user's explicit yes"
metadata: 
  node_type: memory
  type: project
  originSessionId: 035b8b43-5741-4969-be98-65fc9a4bd4f7
  modified: 2026-07-31T05:44:44.229Z
---

Sunrooof call transcripts (`out/transcripts/`, Supabase `transcripts`) will contain
real customer PII — the summarizer deliberately injects the real customer name from
Zoho CRM so the model cannot invent one, so effectively every summarized call
carries a name; phones/addresses appear in some transcripts too. Never commit them
to git (`out/`, `*.mp3` are gitignored), and treat sending transcript content to
any NEW external service as a decision for the user, not an implementation detail.

**Why:** India's DPDP Act notice-and-consent obligations apply to handing customer
data to processors (especially abroad). Whether call-recording consent covers
"transcript sent to a US AI vendor" is the company's call, not something to assume.
Rule carried over from the original Magppie project (this repo is its Sunrooof
clone), where all 723 transcripts contained real names.

**How to apply:** Vendor chain approved in the original project — Zoho, Ozonetel,
Sarvam (audio — more identifying than text), OpenAI (transcript text), Supabase.
Re-confirm this chain is OK for Sunrooof's data on first run, and flag any
addition. To reduce exposure, the customer name can be stripped from the LLM
payload and joined back from Supabase for display.

Related: [[never-paste-api-keys-in-chat]], [[cloned-from-magppie-call-transcription]]
