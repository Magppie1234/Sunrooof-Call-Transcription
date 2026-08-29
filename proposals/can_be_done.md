# Assessing Calls Beyond the Transcript — What Can Be Done

**Investigation dated 2026-08-26. Covers all 6,253 usable transcripts.**
**Nothing in this document is implemented except §1, which is already merged.**

The question that started this: today a call is assessed only on *what was said*.
We also want to assess *how* it was said — tone of both parties, tone of the
conversation, politeness, volume, delivery, and how fast the caller speaks.

**Headline finding: the pipeline already knows it cannot hear tone, and says so
in its own prompt.** [`prompts/call_quality_audit.md:184`](../prompts/call_quality_audit.md)
instructs the model to judge "Upbeat, warm, professional tone. Not fast, flat or
monotonous" and then concedes "**you cannot hear tone**, so judge from word
choice, warmth markers and pacing cues in the text."
[`enrich_for_ci.py:180`](../scripts/enrich_for_ci.py) repeats the restriction:
"judged from words alone (no voice-tone claims)."

So criterion 1.2 has been guessing at pacing from text for the whole corpus.
Pacing is now measured. That gap closes for free.

---

## 1. Already built

[`scripts/speech_dynamics.py`](../scripts/speech_dynamics.py) —
[`scripts/test_speech_dynamics.py`](../scripts/test_speech_dynamics.py) (38 offline
assertions, no network).

```bash
.venv/bin/python scripts/test_speech_dynamics.py
.venv/bin/python scripts/speech_dynamics.py --review-set --report out/speech_dynamics.md
```

Everything comes from `diarized_transcript.entries`, which already carries
`speaker_id`, `start_time_seconds` and `end_time_seconds` per utterance. No audio,
no API calls, replayable over stored transcripts like `rescore_audits.py`.

Measured per side: articulation rate (words per minute **of speech**, pauses
excluded), pace spread, talk share, turn count, longest monologue, response
latency, directional interruptions, dead air, overlap.

Two definitions carry the weight, both because these are Hinglish sales calls:

- **Backchannels are not turns.** A customer says "haan ji" every few seconds
  while listening. Counted as turns they destroy turn counts, monologue detection
  and latency alike, so utterances of ≤3 words neither end nor open a turn. They
  still count toward speech time and overlap.
- **Speed is words per second of speech, not of call.** Pauses belong to dead
  air. Mixing them in measures how *much* someone talks, not how *fast*.

Deliberately absent: thresholds, tiers, pass/fail. "180 wpm is too fast" is a
scorecard rule, and the scorecard has seven open questions already. This emits
measurements only.

> **Caveat.** The Python was never executed — this is a Windows machine and the
> venv is macOS-built. Logic was validated through a line-by-line reference port
> that passes the same 38 assertions; the numbers in §2 and §3 come from that
> port. Run the test on the Mac to confirm the Python agrees.

---

## 2. The five asks, and what each actually needs

| Ask | Status | Corpus | Cost |
|---|---|---|---|
| Speed the caller speaks | **measurable now** | all 6,253 | ₹0 |
| The way callers speak (pace spread, monologues, interruptions, dead air) | **measurable now** | all 6,253 | ₹0 |
| Tone of the conversation (talk balance, who interrupts) | **measurable now** | all 6,253 | ₹0 |
| Politeness | needs a rubric — §5 | all 6,253 | ~₹1,000 |
| Tone of voice / volume | needs audio — §6 | 1,093 only | ₹0 compute |

Politeness and conversational tone are pragmatic, not acoustic — a text model
judges them well, and Hindi makes it easier than English because the markers are
grammatical: आप vs तुम, `-iye` imperatives, "ji" particles, honorifics. Those
belong in a rubric, not in an audio model.

Volume and pitch are the only asks that genuinely require the mp3.

---

## 3. What the measurements found on the 16 review-set calls

Run against the four contradiction cohorts in
[`review_scenarios.json`](../ci-dashboard/src/data/real/review_scenarios.json).

**a) Cohort 4 is not an AI error.** All four "not connected, yet minutes of
audio" calls are genuinely not-connected — the recording ran while the microphone
picked up ambient noise. Confirmed by reading the transcripts:

| Call | Recording | What is actually in it |
|---|---|---|
| `…44954702` | 10.9 min | one word: "Aa" |
| `…46035965` | 10.0 min | one word: "Hello" |
| `…44952442` | 15.4 min | 94% silence, unrelated office chatter, no pitch |
| `…46007562` | 9.9 min | 69% silence, ambient Tamil/Kannada conversation |

Recording duration is not conversation duration. §4 proposes the gate.

**b) Agent dominance tracks the dead leads.** Mean agent talk share by cohort:

| Cohort | Agent share | Longest monologue | Customer pace |
|---|---|---|---|
| Quotation claimed, CRM disagrees | 45% | 80s | 206 wpm |
| Positive outcome, CRM not interested | 69% | 96s | 166 wpm |
| Positive sentiment, lead died | 69% | 180s | 159 wpm |

Where a quotation was genuinely discussed the conversation is balanced. Where the
lead died the agent held two-thirds of the floor and the customer went quiet and
slow — the exact pattern that reads as "positive sentiment" from text while the
lead goes nowhere, which is the concern already raised in
[`docs/sentiment_definition_for_review.md`](../docs/sentiment_definition_for_review.md).

**This is a hypothesis, not a finding.** n=4 per cohort, on calls selected for
being contradictory. Testing it means running across all 6,253 and checking
whether talk share predicts CRM outcome. That run is free.

**c) Pace band.** 175–223 wpm across the 12 real conversations, median 192.
Enough to see spread, not enough for a baseline. Note one agent owns all four
cohort-4 calls, so any per-agent average today measures her dead-air recordings
rather than her delivery.

---

## 4. Gate: `no_contact` made deterministic — **IMPLEMENTED 2026-08-27**

> Built as described below. `conversation_gate()` in `speech_dynamics.py`,
> wired into `summarize_calls.py` (skips before the model) and
> `build_ci_dataset.py` (`meaningful`). Measured over all 6,260 transcripts:
> **41 no_contact (0.65%), 5 sparse (0.08%), 6,214 ok.**
>
> The counts differ slightly from the analysis below because the gate handles
> files the metrics function rejected outright — 7 transcripts with no usable
> timestamps are now correctly `no_contact` rather than unreadable — and one
> call at 17 substantive words falls to the word floor before the density arm
> sees it. Verify any change with `--gate-scan`.


The category already exists — `no_contact` ("Voicemail, IVR, no answer — Not
scoreable") in [`call_quality_audit.md:72`](../prompts/call_quality_audit.md),
already in `LIMITED_CONTEXTS`. **Do not add a new bucket.** The problem is that
the *model* decides it, and on a 10-minute recording of office chatter the model
sees conversation-shaped text and picks something scoreable.

Evidence it fails: in [`out/logs/cohort16-audit.log`](../out/logs/cohort16-audit.log),
of the four dead recordings two returned `not_reachable` (correct) and two
returned `follow_up_needed` with politeness grades of **3/5 and 4/5**. The model
invents a plausible assessment on roughly half of them.

"Did a conversation happen" is arithmetic on timestamps, not judgement. It belongs
on the Python side of the split, the same argument that put scoring in
`call_quality.py` instead of the prompt.

### Thresholds, derived from the corpus

Speech density = union of speech time ÷ recording span, over all 6,253:

| | p1 | p5 | p25 | p50 | p90 |
|---|---|---|---|---|---|
| density | 0.32 | 0.58 | 0.80 | 0.88 | 0.95 |
| substantive words | 27 | 43 | 96 | 201 | 1,709 |

**Arm A — drop deterministically.** `substantive_words < 20` (substantive excludes
≤3-word backchannels). Flags **34 calls, 0.5%**. Every bucket was sampled and
read: hold music, "hello hello can you hear me" dropped lines, voicemail
greetings. No false positives found.

**Arm B — flag, do not drop.** `span >= 120s and density < 0.35`. Flags **6
calls, 0.1%**, catching the two long ambient recordings.

> **Known false positive.** `…44550301` is a **real inbound call** — the customer
> asks about Sunrooof ceiling prices and the agent promises a callback — sitting
> behind 90 seconds of hold music that drags density to 0.30. A word floor does
> not separate it; the margin does not exist:
>
> | Call | Substantive words | Verdict |
> |---|---|---|
> | `…44952442` | 119 | dead — office chatter |
> | `…44550301` | 143 | **real conversation** |
> | `…46007562` | 150 | dead — ambient chatter |
>
> So Arm B routes to a "sparse audio, needs an eyeball" queue. At 6 calls
> corpus-wide that costs nothing.

**Root-cause fix that would make Arm B safe:** strip IVR/hold boilerplate before
measuring density. Prevalence was checked first — 777 transcripts contain
boilerplate ("we value your call", "forwarded to voicemail", "after the tone")
and **178 of those are real calls**, so the phrases can never themselves be a drop
rule. Useful only for excluding those segments from the measurement.

### Three places to change

1. **`speech_dynamics.py`** — add `conversation_gate(entries)` returning
   `{"verdict": "no_contact" | "sparse" | "ok", "reason": ...}`. Pure function.
2. **`summarize_calls.py`** — call it before `summarize()`. On `no_contact`, write
   the summary with that context and skip `--with-audit`. Those calls never reach
   the model.
3. **`build_ci_dataset.py:570`** — make `meaningful` depend on density rather than
   on the LLM-derived `outcome`. `build_review_scenarios.py` then stops generating
   cohort 4, because `_usable()` will correctly reject it.

### Honest scoping

This is a **data-quality fix, not a cost saving**. See §5 — it saves $0.47 a pass.
Its value is that today's protection is LLM-dependent and observed to fail on half
this class, and that 4 of 16 human review slots (25%) went to recordings with no
call in them. Reviewer attention is the scarce resource: one hour of it is worth
roughly 300 audits.

---

## 5. Cost

Measured from [`out/logs/qa-audit-run.log`](../out/logs/qa-audit-run.log) — three
completed runs, 6,930 audit-calls, 82.1M input + 32.0M output tokens, **$84.04**.

**$0.0121 per audit** (11,854 input + 4,616 output tokens). Where that penny goes:

| | Share |
|---|---|
| The model **writing its answer** | **61%** |
| The scorecard instructions, re-sent every call | 35% |
| The call transcript itself | 4% |

Two facts that drive every decision below:

- **The transcript is almost free.** Calls average ~1,150 tokens of text against a
  ~10,700-token scorecard. We re-send a 23,000-character rulebook 6,253 times to
  analyse about one page of conversation.
- **Writing costs 4x reading** ($1.60 vs $0.40 per million). The expensive part of
  adding criteria is not longer instructions — it is that the model then has more
  to *write* per call.

### Options

| Option | Per call | All 6,253 | ≈ INR |
|---|---|---|---|
| Do nothing (today's scorecard) | $0.0121 | $75.83 | ₹6,700 |
| **1.** Add 2 criteria to the 100-point scorecard | $0.0136 | **$85** | ₹7,500 |
| **2.** Separate tone/politeness pass | $0.0018 | **$11.40** | ₹1,000 |
| **3.** Speech dynamics | $0 | **$0** | ₹0 |

*(INR at ₹88/$ — adjust to the real rate. Option 1 assumes ~15% growth in both
instructions and answer; the true figure lands between $80 and $95.)*

**Recommended: Option 2 + Option 3.** Option 2 is 7x cheaper because it drops the
10,700-token rulebook and asks for three fields instead of forty. It stays clear
of the frozen scorecard, and at ₹1,000 a pass you can re-run it while tuning the
rubric — which matters, because the Hindi politeness rubric will not be right
first time.

**Option 1 is not primarily a money problem.** It reopens a scorecard with
[7 unresolved questions](../prompts/SCORECARD_QUESTIONS.md), where CM-5 alone
currently auto-zeroes ~76% of audited calls. Adding criteria to a rulebook that is
still moving is the real cost.

Note `agent_politeness: int` (1 = rude, 5 = very polite) **already exists** at
[`summarize_calls.py:162`](../scripts/summarize_calls.py), alongside
`agent_professionalism`, with a one-line description and no rubric. This is the
same defect documented for sentiment: a field with permitted answers but no
definition. Option 2 is best understood as *defining an existing field*, not
adding a new one. Re-running the summary pass to improve it would also regenerate
the frozen sentiment fields — which is why a separate pass is cleaner than editing
the existing one.

### One free saving to check first

Since 90% of input is an identical prefix repeated 6,253 times, that is exactly
what OpenAI's automatic prompt caching targets. The cost readout at
[`summarize_calls.py:1586`](../scripts/summarize_calls.py) multiplies raw token
counts by list price and knows nothing about cached tokens, so **the $84.04
figure may overstate what was actually charged.** Run `openai_usage.py` for the
same dates and compare. If they differ, every number above is high.

### Model switch

Not recommended, and per [`CLAUDE.md`](../CLAUDE.md) it is the user's decision.
For reference `gpt-4.1` is 5x `gpt-4.1-mini`: a full re-audit would be ~$425
(₹37,400).

---

## 6. Audio — the deadline

Acoustic features (volume, pitch, energy) are the only asks needing the mp3.

- **1,093 mp3s survive**, 885 MB in `out/` — roughly 800 KB per call.
- **6,253 transcripts exist.** The other ~5,160 have no audio.
- [`transcribe_ozonetel_july.py:131`](../scripts/transcribe_ozonetel_july.py)
  deletes each mp3 after transcription: `path.unlink(missing_ok=True)`.
- Ozonetel audio is re-fetchable from S3. **Zoho audio past the rolling ~3-month
  retention cliff is gone permanently.**

**Add a `--keep-audio` flag.** Five-minute change. Retaining the full corpus costs
about 5 GB. Every day that line runs, calls that could have carried acoustic
features become permanently text-only.

What acoustic analysis would then give, using ffmpeg + numpy locally, sliced by the
diarisation timestamps — no vendor, no PII exposure, CPU only:

- **Pitch range (F0)** — catches flat, disengaged delivery. This is what criterion
  1.2 is really reaching for.
- **Volume (RMS dBFS)** — with a caveat: telephony AGC normalises gain per call, so
  absolute volume is not comparable *across* calls. Only agent-vs-customer within
  one call, and an agent against their own baseline, mean anything.

Suggested first step: run it on the 1,093 and check whether pitch range correlates
with existing quality tiers before committing further.

**Deferred: audio-native LLMs** (Gemini / GPT-4o-audio). They would genuinely hear
tone, but it means sending customer-call audio to a new vendor — which
[`CLAUDE.md`](../CLAUDE.md) requires explicit approval for — and covers only 1,093
calls. Local open SER models avoid the vendor question but are trained on acted
English/Mandarin emotion corpora and transfer poorly to 8 kHz Hindi telephony.

---

## 7. Open decisions

| # | Decision | Needed from |
|---|---|---|
| 1 | Approve `--keep-audio`. Time-sensitive — audio is being lost daily | — |
| 2 | Spend ~₹1,000 on the tone/politeness rubric (Option 2) | budget |
| 3 | Sign off the Hindi politeness rubric wording once drafted | QA owner |
| 4 | ~~Implement the `no_contact` gate (§4)~~ — done 2026-08-27 | — |
| 4b | Eyeball the 5 `sparse` calls listed by `--gate-scan`; two are confirmed dead, one is a real call behind hold music | QA owner |
| 5 | Run speech dynamics over all 6,253 to build a real pace baseline. Free | — |
| 6 | Whether acoustic features are worth it for 1,093 calls | after §6 experiment |

Nothing here touches the seven open scorecard questions or the frozen sentiment
prompts. Both remain blocked on their own sign-offs.

---

## 8. Corrections to earlier analysis

Recorded because both were stated with more confidence than they deserved.

1. **"The `meaningful` gate cannot catch these" — wrong.** All 39 flagged calls
   are already `meaningful: false`: 33 because `outcome == "Not connected"` makes
   `connected` false, and 6 because `durationSec <= 60`. Dashboard analytics were
   never polluted. The error was checking `customer_spoke` in isolation and
   asserting the whole conjunction passed. The gate in §4 is still worth building,
   but for the reasons in "Honest scoping", not this one.

2. **Arm B was first proposed without a false-positive check.** `…44550301`, a
   real inbound call behind hold music, would have been silently dropped. Found
   only by reading the flagged transcripts. Hence flag-not-drop.
