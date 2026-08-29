---
name: cloned-from-magppie-call-transcription
description: "This repo is a Sunrooof rebrand of the Magppie call-transcription project — origin, preserved decisions, account quirks, and current plan"
metadata: 
  node_type: memory
  type: project
  originSessionId: 035b8b43-5741-4969-be98-65fc9a4bd4f7
  modified: 2026-07-31T08:32:21.262Z
---

This project (`/Users/UNICA/Desktop/call transcription sunrooof`) was cloned on
2026-07-31 from `/Users/UNICA/Desktop/call transcription` (Magppie's version,
public repo github.com/Magppie1234/Call-Transcription) and rebranded for
Sunrooof, an Indian company selling artificial-skylight LED ceiling panels
(user's description pending confirmation). No Magppie data, secrets, or git
history were carried over. Pipeline: Zoho CRM (← Ozonetel telephony) → Sarvam
Saaras v3 batch STT (`translit`, romanised Hinglish) → gpt-4.1-mini summaries /
FAQ extraction → Supabase → Next.js dashboard (`dashboard/`).

Rebrand changes beyond names: `kitchen_type` → `room_type` (schema + scripts +
dashboard), `scripts/clean_names.py` variant list re-seeded for "Sunrooof"
mishears (grow it from real transcripts; CONTEXT_RE disabled until a stable
Sunrooof brand phrase emerges), agent-detection regex in
`dashboard/src/app/calls/[id]/page.js` updated.

Decisions preserved from the original — keep unless the user says otherwise:
- STT is Sarvam Saaras v3 (chosen on Indian-telephony WER; Whisper disqualified
  for hallucinating on hold music). See PLAN.md.
- Evidence policy is load-bearing: every LLM-extracted claim carries a verbatim
  quote programmatically verified against the transcript; unverifiable quotes
  are nulled, FAQ questions without a verified quote are dropped (gpt-4.1-mini
  was caught inventing plausible questions).
- Region buckets come from `transcripts.city` via `CITY_REGION` in
  `scripts/aggregate_faqs.py`; city (not state) is the reliable field, backfilled
  by `scripts/backfill_call_states.py` from the Zoho Lead/Contact via the Call's
  `Who_Id`/`What_Id`.

Account quirks that bite (from the Magppie handoff kit, still true of Zoho
generally): one Self Client per Zoho account — reuse it, grant codes die in ~3
min, refresh tokens never expire and several can be live at once (root `.env`
and `dashboard/.env.local` intentionally hold different ones). India DC
(`accounts.zoho.in` / `zohoapis.in`). Call audio is fetched with a pasted
browser ZOHO_COOKIE because Ozonetel API creds were never obtained — the cookie
expires every few days/weeks and is the most fragile part; durable fix is an
Ozonetel support ticket. Expect ~$1 per full-corpus gpt-4.1-mini sweep and
~₹1,300 transcription per ~700 calls.

Verified 2026-07-31 against Sunrooof's live org: Zoho Self Client + refresh
token work (India DC, scopes ZohoCRM.modules.ALL + settings.ALL + coql.READ —
broader than Magppie's, COQL available). Recordings live in `Voice_Recording__s`
(phonebridge.zoho.in URLs) exactly like Magppie; ZOHO_COOKIE download confirmed
working — but ONLY with a browser User-Agent header (plain requests get HTTP
400; download_zoho_audio.py already sends one). v7 Calls API sorts only by
Modified_Time/Created_Time/id — use COQL for Call_Start_Time ordering.
`Record_Status__s` is not searchable/criteria-filterable. Scale: ~118k total
calls, 20,841 in July 2026 alone, ~25% with recordings (avg ~124s) — far bigger
than Magppie's 723; bulk transcription windows are a real cost decision, ask
first. OpenAI + Sarvam keys are reused from the Magppie project (user's
decision, pooled billing). Supabase project still not created as of 2026-07-31;
summaries/dashboard blocked on it.

Full pipeline live 2026-07-31: 100 transcripts + 100 gpt-4.1-mini summaries in
Supabase (project ulbzecyeeplkbgcmdffw, user's own account — MCP connector
cannot see it), regions backfilled (54/100 have state — better CRM hygiene
than Magppie), 73 canonical FAQs published to app_kv, dashboard verified on
localhost:3000. Measured pilot LLM cost $0.48 (summaries $0.34 + FAQs $0.14);
full-July would be ~4,840 calls. A 13-agent verification workflow found and I
fixed: (1) /api/audio SSRF — it proxied ANY url with the Zoho cookie attached;
now allowlisted to phonebridge.zoho.* only; (2) home page had hardcoded mock
stats (1,248 calls) — now fetches /api/analytics; (3) Header.jsx still showed
Magppie's "Nitya Sharma / Founder's Office"; (4) budget_detail prompt now
excludes agent-quoted prices. Known caveats (unfixed): summaries on long
garbled calls occasionally mishear numbers or miss objections (audit verdict
"mostly_accurate"); /api/regions city names are un-normalized
(Bengaluru/Bangaluru/Bangalore count separately); 2 of 5 ungrounded FAQ
answers lack [CONFIRM] markers, one asserts "no Bangalore showroom" which
other calls contradict — business should review before training use.
Notable: Sunrooof agents on real calls describe Magppie ("MacPie" in
transcripts) as the parent company with its Wellness Kitchen store — the two
businesses are related, so kitchen mentions in call content are legitimate.

Pilot run 2026-07-31: newest 100 calls >30s transcribed flawlessly (5.0 h
audio, out/transcripts/). Sarvam hears the company as plain "sunroof";
clean_names corrected 271 mentions, zero left. Real brand phrase discovered
("wellness lighting" — CONTEXT_RE in clean_names.py now uses it) and prompts
updated to Sunrooof's actual pitch: patented wellness lighting, ~4-foot
consoles, console-based pricing. Calls are majority English (61/100 en-IN,
19 hi-IN). batch_transcribe.py gained an early-stop scan for --limit runs
(full Zoho scan is ~590 pages at this org's size).

Related: [[transcripts-contain-customer-pii]], [[ask-before-changing-llm-model]],
[[never-paste-api-keys-in-chat]]
