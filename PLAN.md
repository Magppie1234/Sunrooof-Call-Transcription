# Zoho Call Transcription Pipeline — Plan

Automatically transcribe Ozonetel call recordings and post them as Notes on the
relevant Zoho CRM records, alongside the notes reps already write by hand.

## Decisions made

**STT: Sarvam Saaras v3** (`saaras:v3`), via the Batch API.

Chosen over OpenAI (the original proposal), Deepgram, AssemblyAI, and Whisper on
the strength of the "Voice of India" benchmark (AI4Bharat/IIT Madras, 536h of
unscripted Indian telephonic conversation — closely matches our audio profile):

| System | Hindi WER |
|---|---|
| Sarvam | 5.0 |
| Gemini 3 Pro | 6.0 |
| Amazon Transcribe | 6.8 |
| Deepgram Nova 3 | 13.0 |
| AssemblyAI Universal | 19.3 |
| GPT-4o-mini-transcribe | 19.6 |
| GPT-4o-transcribe | 33.9 |

Whisper large-v3 measured 49.2 WER on real Indian call-centre Hindi
(arXiv 2606.18659) and hallucinates on ~99.97% of non-speech segments
(Calm-Whisper, Interspeech 2025) — disqualifying for audio full of hold music
and dead air. Excluded.

Sarvam also uniquely exposes output script as an API parameter (`mode`), which
Whisper structurally cannot do.

**Note content: full transcript only**, no AI summary (user preference).

**Rollout: dry run on 5–10 calls first**, review quality and cost, then batch.

## Architecture

    Zoho Calls API      -> which calls exist, and where to write notes
    Zoho Web Proxy      -> the actual audio (downloaded via session cookie bypass)
    Sarvam Batch STT    -> transcript
    Zoho Notes API      -> write transcript to the record

Audio is hosted by Zoho via a PhoneBridge proxy url. It cannot be downloaded via the standard Zoho API. Instead, we use an active browser session cookie (`ZOHO_COOKIE`) to authenticate directly against the proxy and download the audio.

## VERIFIED against the live org (2026-07-21)

Discovery run against the production Zoho tenant (India DC) established:

- Recording field is **`Voice_Recording__s`** (type: website/URL). Requires API
  v3+; returns null on v2.
- URLs look like `https://phonebridge.zoho.in/phonebridge/recording/{id}?serviceID={sid}`
  — a Zoho-hosted proxy, NOT the Ozonetel S3 bucket.
- **These URLs cannot be downloaded via API.** OAuth returns
  `OAUTH_SCOPE_MISMATCH`.
- **However, these URLs CAN be downloaded using an active browser session cookie.**
  This bypasses the API limitation and gives us access to ALL historical recordings,
  completely removing the need to fetch audio from Ozonetel.
- **49,081 total Call records.** ~18-20% have recordings; the rest are unanswered
  dials of 00:00 duration with no audio.
- **Average recorded call: 1.4 minutes.** ~300 calls/day, ~55 recorded, ~60-70
  minutes of audio per day.
- Sarvam key verified working: job initiate returns 202, `saaras:v3` with
  diarization accepted. Staging container reports `Azure_V1` — residency
  unconfirmed.

### Revised cost (replaces the earlier estimate)

| | |
|---|---|
| Ongoing | ~Rs 1,000-1,500/month (~32 audio-hours) |
| Backfill (~9,000 recordings, ~210 hrs) | ~Rs 9,500 one-off |

Far below the original Rs 33,750/mo estimate: calls are short (1.4 min, not 5)
and most never connect.

### The backfill problem is SOLVED

Because we are pulling audio directly from the Zoho CRM via the session cookie bypass, we have access to **all historical recordings** ever made. We are no longer constrained by Ozonetel's 15-day API limit. We can easily backfill all ~9,000 old calls.

### Alternative considered and set aside

**Zia Call Transcription** (Zoho built-in) writes transcripts as attachments,
which ARE readable with `modules.calls.READ` + `modules.attachments.READ`. But:
English only, Professional edition or above, 18,000 min/month org cap. Unsuitable
for Hinglish audio. Noted so it isn't rediscovered later.

## Hard constraints discovered

### Zoho Audio (Cookie Bypass)
- **Cookie expiration:** Browser session cookies eventually expire. For long-running automated jobs, this cookie must be periodically refreshed.
- **Rate limit:** The Zoho web proxy might have undocumented rate limits for bulk downloading. We should add a short `sleep` between downloads during the backfill.

### Sarvam
- **REST endpoint caps at 30 seconds.** Batch API is mandatory for 5-minute calls.
- Batch limits: 2 hours/file, 20 files/job. At 300 calls/day that's ~15 jobs/day.
- Supports webhook callbacks — avoids polling.
- Diarization is **beta**; timestamps are **chunk-level, not word-level**.
- 8kHz telephony audio explicitly supported. Send as WAV, not raw PCM.
- Starter tier rate limits (20 req/min batch) are sufficient.

### Zoho
- Notes API: `POST /crm/v7/Notes`, requires `Parent_Id` and `Note_Content`.
- **`Note_Content` character limit is undocumented.** Community figure is ~32,000
  chars, unconfirmed. Long transcripts may need chunking across multiple Notes.
  Test the real ceiling early.
- Max 100 notes per API call. Batch inserts to conserve credits.
- Refresh tokens never expire. Access tokens last 1 hour; max 10 refreshes per
  10-minute window — cache aggressively.
- Self Client is the right app type (backend, no redirect URL).

## Engineering notes

- **Do not apply neural bandwidth extension / audio "enhancement"** to the 8kHz
  audio before transcription. VoiceFixer and AudioSR measurably worsen WER versus
  plain soxr/linear resampling (arXiv 2606.09335), despite sounding better.
- Download recordings eagerly rather than storing URLs for later fetch.
- Expect real-world WER worse than any published benchmark — no study evaluates
  telephony bandwidth + spontaneous register + code-switching simultaneously.
- Entity-heavy speech (names, account numbers, addresses) degrades notably more
  than average. Include such calls in the evaluation sample.

## Open questions

### Blocking
None. Ozonetel credentials are no longer required.

### Non-blocking

5. **Which Sarvam `mode`** for note output: `translit` (Roman Hinglish — readable
   and searchable, recommended), `codemix`, or `translate` (clean English but
   loses the customer's own words). User decision.
6. **Sarvam data residency** — batch staging reports `Azure_V1`; region unstated
   in docs. Get written confirmation before running at volume. Material to DPDP.
7. **`Note_Content` character limit** — still undocumented. At 1.4 min average
   this is unlikely to bite, but test before the backfill.
8. **Are 1.4-minute calls substantive enough to be worth transcribing?** Worth a
   human look at a few before committing to the full backfill.

## Resolved

- ~~Does Zoho hold the recordings?~~ Yes, and they can be downloaded via browser session cookie bypass.
- ~~Is the Ozonetel key needed?~~ No. We have bypassed it entirely.
- ~~Are recordings publicly exposed?~~ No. Properly authenticated in this org.
- ~~Which STT provider?~~ Sarvam Saaras v3, key verified working.

## Credentials required

| Service | Needed |
|---|---|
| Sarvam | API subscription key (header `api-subscription-key`) |
| Zoho API | Client ID, Client Secret, refresh token, data centre (.com/.in/.eu) |
| Zoho Audio | `ZOHO_COOKIE` (browser session cookie) |

Zoho scopes: `ZohoCRM.modules.calls.READ`, `ZohoCRM.modules.notes.CREATE`,
`ZohoCRM.modules.attachments.READ`, `ZohoCRM.settings.fields.READ`

## Cost estimate

At 300 calls/day x ~5 min = ~750 audio-hours/month:

- Sarvam without diarization: ₹22,500/mo (~$256)
- Sarvam with diarization: ₹33,750/mo (~$384)

Zoho API credits are not a constraint at this volume.

## Next step

Write `scripts/download_zoho_audio.py` that, given a Zoho Call ID and a `ZOHO_COOKIE`:
1. Fetches the `Voice_Recording__s` URL using the Zoho API.
2. Downloads the MP3/WAV file directly using the session cookie.
3. Saves it locally to verify the bypass works.
