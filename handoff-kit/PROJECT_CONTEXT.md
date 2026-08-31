# Sunrooof Call Transcription & Intelligence — Full Context Handoff

Everything a fresh Claude Code (or other AI) session needs to know about this
project that is NOT obvious from reading the code. Written 2026-08-04.

## What this is

Two things sharing one Python/Zoho/Supabase backend:

1. **`dashboard/`** — a Next.js app: per-call summaries, analytics, caller
   regions, customer-FAQ training page. This is the original, "operational"
   dashboard.
2. **`ci-dashboard/`** — a separate Vite/React SPA, "Call Intelligence & Voice
   of Customer": 10 pages (Executive Overview, Customer Voice, FAQs, Regional,
   Sales & Objections, Agent Quality, Next-Action Tracker, Call Explorer,
   Alerts, Data Quality). This was cloned from a **hand-designed demo UI**
   (`~/Desktop/call transcription new`, a sibling project built for **Magppie**,
   a different company on the same machine) and rewired to Sunrooof's real
   data. Every KPI/chart on this one carries a small green/amber/red dot
   showing whether it's real, partially real, or still demo — see
   `ci-dashboard/src/lib/provenance.ts`, 45 entries, notes kept in sync with
   measured coverage.

Both read the same pipeline: Zoho CRM (calls + leads) → Sarvam Saaras v3
STT (romanised Hindi/Hinglish transcripts) → gpt-4.1-mini (summaries, FAQs,
sentiment/readiness/objections) → Supabase → the two frontends.

**Sunrooof sells "wellness lighting"** — patented artificial-skylight LED
ceiling consoles (~4 ft each, console-based pricing) that recreate natural
daylight indoors. Agents pitch it as "Sunrooof wellness lighting" on calls.
This is NOT a kitchen company — this project was itself cloned from a Magppie
(stone modular kitchens) project and rebranded; see below.

## Origin: cloned from Magppie, twice

This project (`call transcription sunrooof`) is a rebrand of
`~/Desktop/call transcription`, Magppie's call-transcription pipeline
(different company, different Zoho org, different Supabase project — no data
overlap). The rebrand replaced `kitchen_type` with `room_type` throughout,
re-seeded the phonetic name-cleanup list (Sarvam mishears "Sunrooof" as plain
"sunroof" — see `scripts/clean_names.py`), and rewrote every LLM prompt's
company description.

`ci-dashboard/` is a **second**, independent clone: of a hand-built demo UI
(`~/Desktop/call transcription new`) that a *different agent session*, working
in parallel on the SAME machine, was simultaneously wiring up for Magppie's
data. **Both clones point their dataset builder at their own project folder
now** (`scripts/build_ci_dataset.py`'s `DEFAULT_OUT` is a path inside THIS
repo) — earlier there was a close call where this script's output path was
hardcoded into the Magppie sibling folder and briefly overwrote that agent's
dataset; it was restored and the path fixed. If a new session ever touches
`build_ci_dataset.py`, verify `DEFAULT_OUT` still resolves inside
`call transcription sunrooof/ci-dashboard/`, never outside it.

## Current data state (2026-08-04)

- **300 calls transcribed** locally (`out/transcripts/*.mp3.json`): the
  original 100-call pilot (30–31 Jul) + 200 more from a July backfill run that
  was interrupted (see "What's blocked" below).
- **Only the first 100 are synced to Supabase** (`transcripts`, `call_summaries`
  tables) and therefore the only ones visible in `dashboard/` or reflected in
  `ci-dashboard/`'s `dataset.json`. The 200 newer transcripts are sitting on
  disk, transcribed but not yet summarized/enriched/synced.
- `out/faq_analysis.json` — 73–75 canonical FAQs from the 100-call pilot,
  published to Supabase `app_kv` key `faq_analysis`.
- `out/ci_enrichment/*.json` — 100 files, the CI-dashboard-specific LLM pass
  (segmented sentiment, purchase readiness, objections, quality) for the pilot
  only.
- `ci-dashboard/src/data/real/dataset.json` — built from those 100 calls.
  **Stale relative to the 200 extra transcripts** until `refresh_all.py` runs.

### What's blocked

The July backfill (targeting ~4,922 calls >30s across July) **stopped itself
at 200/4,922 calls because Sarvam returned HTTP 402 "No credits available."**
It was killed cleanly (no corrupt files; 299/300 local transcripts have real
content, 1 is empty). **Nothing downstream will move until the user tops up
Sarvam credits** at dashboard.sarvam.ai — the Sarvam key is shared with
another of the user's projects, so balance drains from both.

Measured costs so far: the 100-call pilot cost ~₹290 (₹226 Sarvam @ ~₹45/hr +
$0.74 LLM across summarize+FAQ+CI-enrichment). The 200-call partial July run
added ~13.6 more audio-hours (~₹610 Sarvam). As of this writing, a **10-day
window** (1,645 calls >30s, 1,346 not yet transcribed) would cost ~₹3,624 to
transcribe+summarize (not counting FAQ/CI-enrichment); a ₹1,500 cap buys
roughly 557 of those calls. Full July (~4,922 calls, minus the 200 already
done) is roughly ₹11,000–15,000 depending on exactly what's re-measured.
**Always re-derive these from a fresh Zoho COQL query before quoting a number
— call volume changes daily and Sarvam's real per-hour rate has only been
cross-checked against PLAN.md's estimate, never against an actual Sarvam
invoice.**

### Resume checklist once Sarvam has credits

1. `python scripts/batch_transcribe.py --since 2026-07-01 --until 2026-07-31`
   (or a narrower `--since/--until` window if the user wants to spend less —
   see `.env` for how date filtering works). Already-done calls are skipped
   automatically, so re-running never pays twice.
2. `python scripts/refresh_all.py` — this is the ONE orchestrator script that
   runs the entire post-transcription chain in the right order (region
   backfill → name cleanup → summaries → FAQ extraction+aggregation → Zoho
   CRM enrichment → CI enrichment → dataset build). Read its docstring; two
   ordering traps are already encoded (FAQ aggregation must precede the
   dataset build, or FAQ clustering silently degrades to fuzzy matching;
   region backfill must precede it too, or every call becomes "Unknown").
   `--dry-run` shows the plan without spending anything; `--from <step>`
   resumes a failed run without repeating finished steps.
3. Rebuild+serve `ci-dashboard/`: `cd ci-dashboard && npm run build && npm run
   preview -- --port 5199` (or `npm run dev` for a live-reload dev server —
   currently what's running, on port 5173, since `vite dev` was faster to
   launch than a full preview build for verification purposes).
4. **Update `ci-dashboard/src/lib/provenance.ts`'s notes** — every note
   quotes exact coverage numbers ("96 of 100 calls", "58 of 100 leads") that
   will change once the dataset grows past 100 calls. Recompute and rewrite
   them; do not leave 100-call-pilot numbers describing a bigger dataset.

## Account topology (the part that bites)

- **Zoho**: India data centre (`accounts.zoho.in` / `www.zohoapis.in`,
  `ZOHO_DC=in`). Self Client (Zoho allows exactly ONE per account — reuse it,
  never create a second; grant codes expire in ~3 min, refresh tokens never
  expire). Scopes are BROADER than the Magppie project's were — this org's
  token includes `ZohoCRM.modules.ALL`, `ZohoCRM.settings.ALL`, and
  `ZohoCRM.coql.READ` (COQL queries work here; they didn't on Magppie's
  narrower scope). Sunrooof's Zoho field names differ from Magppie's:
  `Type_of_Space` (not `Property_Type`), Deals carry `Total_Consoles` /
  `Proposed_Order_Amount` / `Total_Amount_Received`.
- **v7 Calls API only sorts by `Modified_Time`/`Created_Time`/`id`** — anything
  needing `Call_Start_Time` order must use COQL instead
  (`crm/v7/coql`, POST, `select_query`). COQL offset paging caps around
  9,800–10,000 rows per query; a full-month scan needs id-range paging beyond
  that (see the COQL loops in various scripts using `order by id asc`).
- **Supabase**: project `ulbzecyeeplkbgcmdffw` (its own — separate from
  Magppie's). URL and service-role key live in both `.env` (Python scripts)
  and `dashboard/.env.local` (Next.js) — these CAN and do differ in which
  Zoho refresh token they hold (multiple refresh tokens can be live on one
  Self Client simultaneously; this is intentional, not a bug).
- **Audio**: recordings live behind Zoho's phonebridge
  (`phonebridge.zoho.in`), fetched with a pasted browser session cookie
  (`ZOHO_COOKIE` — no real Ozonetel API creds were ever obtained). The cookie
  **expires every few days/weeks**; refresh from a logged-in Zoho CRM tab →
  DevTools → Network → copy the request `Cookie` header. Two different proxy
  mechanisms exist to work around phonebridge rejecting Python's HTTP client
  directly: `dashboard/src/app/api/audio/route.js` (Next.js route, used when
  `dashboard/` is running) and the newer, lighter-weight
  `scripts/audio_proxy.mjs` (a standalone Node http server, no framework —
  used when only `batch_transcribe.py` needs the proxy and the full Next.js
  dashboard isn't worth starting). Both hold the cookie and forward only to
  known phonebridge hosts — `audio_proxy.mjs`'s docstring explains why this
  allowlisting matters (an earlier version of the Next.js route had no host
  allowlist at all and would proxy ANY url with the cookie attached — an SSRF
  + credential-leak bug, since fixed in `api/audio/route.js`; the standalone
  proxy was written allowlisted from the start).
- **GitHub**: no remote configured for this project as of writing (unlike the
  Magppie original, which has a public GitHub repo).

## Decisions & policies (with the why) — mostly inherited from Magppie, verify still true

- **STT: Sarvam Saaras v3**, batch API, `translit` mode (romanised Hinglish),
  diarization on. Chosen (in the Magppie project) over Whisper/Deepgram/
  AssemblyAI/GPT-4o on Indian-telephony WER; Whisper hallucinates on hold
  music/dead air.
- **Summaries/enrichment model: gpt-4.1-mini via OpenAI.** OpenRouter free-tier
  fallback exists but unused in practice. **Never switch models — even for a
  test run — without asking the user first**; this was a hard rule set by the
  user on the Magppie project and re-saved to this project's memory.
- **Evidence policy (load-bearing for trust)**: every LLM-extracted claim
  carries a verbatim quote programmatically verified against the transcript.
  Unverifiable quotes are nulled; in FAQ extraction a customer question with
  NO verified quote is dropped entirely (gpt-4.1-mini was caught inventing
  plausible-sounding questions on calls where nobody asked). Keep this bar in
  any extension.
- **Never accept API keys pasted into chat.** The user pastes directly into
  `.env` / `dashboard/.env.local`; verify only by length/prefix
  (`len(k)`, `k[:8]`), never echo a full value. This has been asked for
  explicitly, more than once, across sessions.
- **Transcripts contain real customer PII** on essentially every call (the
  summarizer deliberately injects the real customer name from Zoho so the
  model can't invent one). Never commit `out/` to git. Sending transcript
  content to any NEW external vendor beyond the already-approved chain
  (Zoho, Sarvam, OpenAI, Supabase) needs the user's explicit yes.
- **Product taxonomy note for `ci-dashboard`**: Sunrooof sells essentially one
  product line, so the model names it a dozen ways ("Sunrooof",
  "wellness lighting", "Sunrooof light console", …). `product_series()` in
  `scripts/build_ci_dataset.py` collapses these into one canonical value —
  don't let a future rebuild re-fragment this dimension.
- **Duration filter**: `batch_transcribe.py` defaults to skipping calls ≤30s
  (`--min-duration`). Measured: raising the threshold barely saves money
  (Sarvam bills by audio DURATION not call count, and short calls are cheap
  precisely because they're short) but throws away a large fraction of real
  conversational data. Keep the >30s default unless the user asks otherwise.

## Costs (measured, not estimated, unless flagged)

- 100-call pilot: ~₹290 total (₹226 Sarvam + $0.74 LLM across
  summarize+FAQ+CI-enrichment, measured exactly from run logs: 1.16M input /
  172K output tokens on gpt-4.1-mini).
- Sarvam rate used for projections: ₹45/audio-hour, sourced from this
  project's own `PLAN.md`, NOT independently verified against a Sarvam
  invoice — cross-check before quoting a large number to the user.
- LLM cost scales roughly $0.0034/call for summarize-only,
  ~$0.0074/call if also running the full CI-enrichment pass.

## Bootstrap checklist for a fresh clone/session

1. Copy `.env` and `dashboard/.env.local` from the original machine (or refill
   from this kit's `.env.example` — real values are deliberately NOT in this
   kit; paste them into the files directly, never into chat).
2. Python: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. `dashboard/`: `cd dashboard && npm install && npm run dev` (port 3000).
4. `ci-dashboard/`: `cd ci-dashboard && npm install && npm run dev` (port
   5173) or `npm run build && npm run preview -- --port 5199` for a
   production-like serve.
5. If Sarvam has credits and the user wants more data: run
   `scripts/batch_transcribe.py` with the desired `--since/--until`, then
   `scripts/refresh_all.py`.
6. Drop `claude-memory/` into the new session's memory directory (or just ask
   the AI to read it) so the working-style rules and project history carry
   over without having to be re-discovered.
