# Sunrooof Call Intelligence — Reference Context

Single consolidated reference: what this project is, what it knows, how it judges a
call, and every parameter and rule involved. Assembled from the code and prompt files,
not from memory — file paths are given for everything so each claim can be checked.

Compiled 2026-08-27.

---

## 1 · What we are

A Zoho call-transcription and call-intelligence pipeline for **Sunrooof** (wellness
lighting, India — ceiling and window "consoles"). It downloads sales-call recordings,
transcribes them, extracts structured intelligence with an LLM, audits call quality
against a 100-point scorecard, and serves the result through a React dashboard.

Sunrooof is a subsidiary of **Magppie** (premium stone modular kitchens / Venice
Kitchen), which runs a sibling project on the same codebase. That repo is **upstream** —
its first commit is 2026-07-24, ours is 2026-08-04, both under the GitHub account
`Magppie1234`. See `docs/magppie-exchange-log.md` for what has been shared between them.

**Pipeline order:** Transcribe → sync → summarize → analytics → dashboard.

| Stage | Script | Notes |
|---|---|---|
| Transcribe | `batch_transcribe.py` (Zoho audio), `transcribe_ozonetel_july.py` (S3 via CSV match) | Sarvam Saaras v3, `--min-duration 30` |
| Sync | `sync_transcripts_to_supabase.py` | |
| Summarize + QA audit | `summarize_calls.py` | `--with-audit` adds the PSM scorecard |
| Analytics | `refresh_all.py` | enrich, FAQs, regions, dataset |
| Dashboard data | `build_ci_dataset.py`, `export_qa_audits_for_dashboard.py` | two separate files |

**Supabase `call_summaries` is the system of record.** The dashboard never reads
Supabase directly — it reads build-time JSON snapshots.

---

## 2 · What we know — current data state

| Fact | Value |
|---|---|
| Calls in the shipped dataset | **6,253** |
| Date range | 2026-06-01 → 2026-07-31 |
| Analysed population (the insight denominator) | 3,751 |
| Transcribed with zero customer speech | 164 |
| "Not connected" yet >60s of audio | 269 (4.3%) — see §10 |
| Total Call records in the CRM | ~49,000; only 18–20% have a recording |
| Untranscribed backlog | ~5,400 calls — Sarvam credits exhausted |
| Language mix | Hindi/English dominant, then English, plus Malayalam and Kannada mixes |
| Follow-up calls | ~24% (1,531) are contact #2 or later |

**Audio access is fragile.** Recordings sit behind Zoho's PhoneBridge web proxy and are
*not* fetchable over OAuth (`OAUTH_SCOPE_MISMATCH`). They are pulled with a pasted
browser session cookie (`ZOHO_COOKIE`) that expires every few days. Playback requires
the local proxy (`node scripts/audio_proxy.mjs`, port 3000). Zoho retention is a rolling
~3 months; past the cliff phonebridge returns HTTP 200 with an **empty body**, which is
indistinguishable from attrition. HTTP 400 means the cookie is dead, not that audio is
gone. The Ozonetel CDR API no longer authenticates with key+username — a CloudAgent CSV
export is the only route past the cliff.

---

## 3 · What the README currently says

From `ci-dashboard/README.md`, verbatim in substance:

> **Sunrooof · Call Intelligence & Voice of Customer Dashboard.** A production-ready,
> decision-focused dashboard that turns speaker-separated call transcripts into business
> insight: customer voice & sentiment, FAQs & knowledge gaps, regional intelligence,
> sales & objection intelligence, agent quality, next-action tracking, alerts and
> governance.
>
> **Live data.** The app runs on the real Sunrooof dataset: **100 Zoho CRM calls
> (30–31 July 2026)**, transcribed with Sarvam Saaras v3 and analysed with gpt-4.1-mini.
> `DATA_MODE = 'real'` in `src/config.ts` selects `src/services/realService.ts`, which
> reads the build-time snapshot at `src/data/real/dataset.json`. The original mock
> generator is still present and selectable with `DATA_MODE = 'mock'`.
>
> All insights are text-based (transcripts only — no voice-tone analysis). Every surface
> carries a **provenance dot** — 🟢 real · 🟠 real with a declared gap · 🔴 demo data with
> no real source — defined in `src/lib/provenance.ts` and listed in full on the Data
> Quality page. Features that cannot be backed by real data are kept and marked, never
> silently removed.

**Run:** `npm install` · `npm run dev` (5173) · `npm run build` · `npm run preview`.

**Pages:** Executive Overview · Customer Voice & Sentiment · FAQs & Knowledge Gaps ·
Regional Intelligence · Sales & Objection Intelligence · Agent Quality · Next-Action
Tracker · Call Explorer (+ per-call evidence view) · Alerts & Escalations · Data Quality
& Configuration. Every KPI drills down: summary → segment → call list → transcript @
timestamp.

**Deliverables index** — `docs/01` information architecture, `04` metric definitions,
`05` data dictionary, `06` APIs, `07` AI-extraction schema, `08` scoring methodology,
`09` alert & SLA rules, `10` RBAC, `11` assumptions, `12` testing.

> ⚠️ **The README is stale on two counts, and so is `src/lib/provenance.ts`.**
> It states 100 calls over 30–31 July; the dataset is **6,253 calls over June–July**.
> It also indexes ten `docs/` deliverables that **do not exist in this repo** — they
> exist upstream in Magppie and were lost on our side of the fork. The dashboard's
> page list is also short by two: Advanced QA and Review Sets both ship now.

`handoff-kit/README.md` describes a portable context bundle (`PROJECT_CONTEXT.md`,
`.env.example`, `claude-memory/`) for starting a fresh AI session, containing no live
secrets.

---

## 4 · How we assess call quality

There are **two independent quality systems in this repo**, and they do not agree with
each other. Both are live.

### System 1 — the PSM scorecard (`scripts/call_quality.py` + `prompts/call_quality_audit.md`)

The rigorous one. 100 points, gates, tiers, replay, human-review flags. Feeds the
**Advanced QA** page and `qa_audits.json`.

**The governing architectural rule: the model judges, Python scores.**

| The model returns | Python computes |
|---|---|
| per sub-point: `met` / `partial` / `not_met` / `not_applicable` / `unknown` | which criteria are applicable |
| verbatim evidence quote + timestamp for every decision | `adjusted_max` = sum of max over applicable criteria |
| per critical miss: `observed` = yes / no / unknown | `earned` from sub-point labels via the gates |
| per red flag: `observed` = yes / no / unknown | `pre = round(earned / adjusted_max × 100, 1)` |
| `call_context` + reason | `deduction_total` from observed red flags |
| conduct assessment, qualitative ratings, coaching prose | `auto_zero` = any critical miss observed |
| | `final = 0.0 if auto_zero else max(0.0, pre − deduction_total)` |
| | `tier`, `audit_status`, and the Section-13 self-checks |

The prompt says so explicitly: *"Do not compute scores, percentages, totals, deductions
or tiers — those are calculated downstream and anything you put there is discarded."*

Two reasons this split exists:

1. An LLM asked to total its own scorecard occasionally returns a tier that disagrees
   with its own score — silently, on a minority of calls.
2. **Scoring-rule changes replay over stored data for free.** The model's judgements and
   evidence live in the `call_quality_audit` jsonb column, so `rescore_audits.py`
   re-applies changed rules with zero API calls. Only changes to *what the model looks
   for* need a re-run.

**Scoring method.** Each applicable criterion scores **Full**, **Half** or **Zero** only.

- Any mandatory sub-point `not_met` → the criterion is **Zero**
- No mandatory `not_met` but at least one `partial` → cannot exceed **Half**
- **Full** only when every mandatory sub-point is `met`
- **Silence is not credit.** On a complete transcript, no evidence that the PSM covered
  a required point means `not_met`, never `not_applicable`
- `unknown` forces human review

### System 2 — the dashboard quality score (`scorecard_to_quality` in `build_ci_dataset.py:234`)

The looser one. Feeds the **Agent Quality** page. Fixed eight-dimension weights, no
adjusted max, and **no NOT_SCORED state at all**. Dimensions the scorecard marked
not-applicable fall back to constants rather than dropping out:

```
opening 60 · discovery 55 · nextStepClarity 50 · professionalism 70
objectionHandling 70 (55 if objections exist) · faqHandling 70
solutionRelevance 60 · listening 65
```

Weights (`Q_WEIGHTS`): discovery .20 · solutionRelevance .15 · faqHandling .15, plus the
remainder across the other five.

> ⚠️ **The consequence:** a 40-second call where nothing happened scores **~60** on Agent
> Quality — not a failure, just "mediocre" — while the same call may be NOT_SCORED or
> auto-zeroed on Advanced QA. Nothing reconciles the two. The guard exists in System 1
> and is absent from System 2, which is the page a manager is more likely to open.

---

## 5 · The parameters — the 100-point scorecard

Source of truth for wording: **`prompts/call_quality_audit.md`**, read at runtime by
`summarize_calls.py`, so editing it changes the audit with no code change.
Schema version `sunrooof_psm_call_quality_v3.0`.

The scorecard was rebuilt from **Sameer's training voice notes**
(`out/voice_notes/ALL_VOICE_NOTES.md`), in which he walks each point and demonstrates it
with Bhavya playing the customer. **That mock call is the reference standard** — agents
are scored against how Sameer ran it, not a generic idea of a good sales call.

### The twelve criteria

| # | Criterion | Max | Mandatory sub-points |
|---|---|---|---|
| 1 | Greeting & Opening | 5 | none |
| 2 | KYC / Discovery | 5 | 2.4 install deadline |
| 3 | About SUNROOOF / Value Proposition | 10 | 3.1 world-first wellness lighting; 3.2 five wellness benefits |
| 4 | Requirement Gathering | 5 | 4.1 where to install; 4.2 ceiling vs window |
| 5 | Technical Details | 10 | none (but factual errors may trigger CM-1) |
| 6 | Pricing Communication & Console Specs | 10 | **all six** |
| 7 | Hype & Aspiration Building | 15 | none |
| 8 | Objection Handling | 10 | N/A permitted |
| 9 | Priming Customer for Specialist | 10 | **all four** |
| 10 | Process Clarity | 5 | none |
| 11 | FOMO Creation / Urgency | 10 | 11.1 use the customer's own deadline |
| 12 | Zoho CRM Disposition | 5 | N/A permitted |
| | **Total** | **100** | |

**C1 — Greeting & Opening.** (1) Well-paced, clear, **assumptive** opening — the PSM
assumes they are already speaking to the right person and talks, rather than verifying
identity. *"Hi Bhavya, my name is Sameer…"* is assumptive; **"Is this Bhavya speaking?"
is NOT**. *"Let's talk for two minutes"* is assumptive; *"Can I talk to you for two
minutes?"* is asking permission and is not. (2) Upbeat, warm, professional tone — judged
from word choice and pacing cues only, never claimed from audio. (3) Lead source
**confirmed or asked** — confirming a known source counts as met; asking is required
only when the source was unavailable.

**C2 — KYC / Discovery.** (1) Customer type — architect / contractor / designer vs
homeowner. (2) Project type and location — new or existing, independent home or
apartment, which city, where the customer resides. (3) Project readiness — possession
date or completion date. (4) **MANDATORY: by when the customer needs SUNROOOF installed
and ready**, distinct from project readiness. If the customer cannot answer, the PSM
**must prompt** — Vastu date or muhurat, before school reopens, summer vacations. Not
met *only* when the PSM never asks and never prompts. (5) Decision maker identified.
(6) If not the decision maker, ask who is and propose a joint call.

**C3 — About SUNROOOF.** (1) MANDATORY: world's first wellness lighting technology,
category invented by Sunrooof. (2) MANDATORY: **the five approved wellness benefits** in
Sameer's chain — (a) the space feels open, airy, less cluttered, less claustrophobic,
full of natural light; (b) that lifts mood; (c) which lowers stress; (d) the GPS chip
follows the sun/circadian cycle, improving sleep; (e) better focus, concentration,
productivity and social interaction. (3) Patent and origin — proudly Indian, patented,
only ones with the technology. (4) Credibility — **1000+** spaces transformed. (5)
**PROHIBITED: "Barton Bach"**, the old brand name — if the PSM says it, C3 is Zero and
CM-3 fires. The *customer* saying it does not count.

**C4 — Requirement Gathering.** (1) MANDATORY: where the customer wants it installed.
(2) MANDATORY: ceiling vs window consoles established, including offering window options
for walls without windows. Bathrooms: IP40, not waterproof — may go above a sink or WC,
**never** above a shower head or bathtub.

**C5 — Technical Details.** Console dimensions; design styles (catalogue reference is
fine); **minimum quantity with the reason** — four consoles on a **ceiling**, but only
**two** on a wall/window install, because natural light is seen coming from a *cut-out*,
never a hole; technology (LEDs, lenses, optics, nanotech diffuser, GPS chip, drivers,
controllers, app — the lamp-shade analogy for the diffuser is the model answer); ceiling
height and drop; life span; power; timeline (2–2.5 months standard, 7–15 days possible in
genuine urgency); manufacturing — electronics in **Germany**, woodwork in **Manesar,
Haryana**; **not sensor-based — a GPS-based preset**, controlled by app *and* remote
together.

**C6 — Pricing.** All six mandatory: (1) per-console price, **never a package total**;
(2) ceiling console price range; (3) window console price stated separately; (4)
measurements in **any two of four units** — feet-and-inches, millimetres, centimetres,
inches-only; (5) coverage-based quantity from the chart; (6) **PROHIBITED: no GST,
delivery, installation or total cost** — a total would require adding ~₹50,000
delivery/assembly and 18% GST, which loses the customer.

Coverage depends on **why** the customer wants it: **wellness only** (other lights
exist) → chart minimum, roughly 10–20% coverage, often 4–6 consoles, and recommending
the minimum is correct advice, not under-selling. **Wellness + illumination** (sole light
source) → 50–80% coverage, never above 80%.

**C7 — Hype & Aspiration.** Positioned as a **need, not a want**; wellness benefits
reiterated; one-time investment over a 12–14 year life; lower power draw within approved
figures; **modularity** — on moving home the consoles come with you, only the frames are
rebought.

**C8 — Objection Handling.** Only objections actually raised. The **approved
price-objection technique** is to spread cost over life: ~₹1.6 lakh over 15 years ≈ 180
months ≈ **₹800–900 per month**. **Budget qualification:** workable minimum **₹2–2.2
lakh**. A customer stating less should be asked to stretch to ₹2–2.5 lakh with pricing
authority handed to the Wellness Specialist. A customer who will not move above ₹50,000
should not be pushed — but the stretch attempt must still be made.

**C9 — Priming for Specialist.** All four mandatory: built the Specialist's importance;
explained they are a helper not a seller; explained they are the pricing and design
authority; explained the importance of answering their calls and messages.

**C10 — Process Clarity.** Next steps (measure, design, cost, order, install); timeline;
when the Specialist makes contact. If asked about **payment structure**, the approved
answer is four equal 25% parts — on booking; after the drawing is finalised and before
production; before rafter installation; before console installation and automation
handover. Explaining this is a **credit, not a pricing breach** — it is process, not cost.

**C11 — FOMO / Urgency.** MANDATORY: used the customer's **own stated deadline** (from
C2.4) to describe the package and price-locking timeline, and obtained a YES to explore.
No fake deadlines or invented scarcity — if used, C11 is Zero and RF-6 applies.

**C12 — Zoho CRM Disposition.** Correct disposition type and date from CRM metadata. N/A
when the data is unavailable. Do not infer an expected disposition without an authorised
mapping.

### Critical misses — any `yes` zeroes the entire call

| Code | Condition |
|---|---|
| **CM-1** | Miss-sell — false information, unsupported claims, misrepresentation, judged against `product_facts.md` **only**. If unverifiable → `unknown`, never `yes` |
| **CM-2** | Short Dial — disconnected prematurely with no genuine attempt. **Never fires merely because a call is short** |
| **CM-3** | "Barton Bach" spoken by the PSM |
| **CM-4** | Handover WhatsApp group created on the RAW-quote date. Requires CRM metadata; `unknown` when unavailable |
| **CM-5** | Install deadline not captured — fires **only** when the PSM neither asked nor prompted. A customer who does not know their own date is not the agent's failure |

### Red flags — deducted from the percentage

| Code | Category | Deduction | Condition |
|---|---|---|---|
| RF-1 | CRITICAL | −15 | Suggested fewer consoles than the minimum for that surface — below four on a ceiling, or below two on a wall. **Two for a wall install is correct and must NOT fire this** |
| RF-2 | CRITICAL | −15 | Wrong CRM disposition marked |
| RF-3 | MAJOR | −10 | Decision maker not identified |
| RF-4 | MAJOR | −10 | Timeline vague or not discussed |
| RF-5 | MAJOR | −10 | Ceiling height/type not verified (9 ft) |
| RF-6 | PROCESS | −10 | Artificial urgency or false deadlines |
| RF-7 | MINOR | −5 | Mentioned GST, installation, delivery or total cost |
| RF-8 | MAJOR | −10 | Did not listen — interrupted, or repeated an assumption the customer had corrected |
| RF-9 | MAJOR | −10 | Poor rapport — brusque, impatient or transactional |

RF-8 and RF-9 are conduct flags carried at real weight rather than left in an unscored
coaching note, because *a luxury sale is lost by not listening long before it is lost on
a checklist item*.

### Tiers

| Band | Tier |
|---|---|
| ≥ 85 | GOLD |
| ≥ 75 | SILVER |
| ≥ 60 | BRONZE |
| ≥ 50 | DEVELOPING |
| < 50 | AT_RISK |
| `None` | NOT_SCORED |

**NOT_SCORED is not a zero.** It means the call could not be assessed, and must never be
read as a failing grade. All four band edges are unvalidated judgement calls.

### Call context — classified before scoring

`call_context` governs which criteria can fairly be assessed:

| Context | How to score |
|---|---|
| `full_consultation` | Full scorecard applies |
| `follow_up` | **Do not penalise for not repeating** benefits, technical detail or pricing already given on an earlier call |
| `callback_scheduling` | Greeting, courtesy and whether a specific callback time was agreed. Everything else N/A |
| `not_a_lead` | Greeting and how gracefully it was closed. Offering to remove the number is **correct handling and scores well** |
| `customer_declined_early` | Do not penalise for content the customer refused to hear |
| `no_contact` | Not scoreable |

*"A customer who has no time, is not interested, or simply wants to buy without a
wellness explanation is not an agent failure."*

### The N/A guards — the most important mechanism here

- **`NA_ALLOWED = {8, 12}`** — only Objection Handling and CRM Disposition may be N/A.
- **`LIMITED_CONTEXTS`** widen it legitimately: `callback_scheduling` → {1, 10},
  `not_a_lead` → {1}, `customer_declined_early` → {1, 2, 10}, `no_contact` → {}.
- **`MIN_SCOREABLE_MAX = 50`** — if fewer than 50 of 100 points are applicable, the call
  returns `not_scored` rather than a grade.

**Why:** on a real 40-second call the model marked **11 of 12 criteria N/A** — "No
pricing discussed", "No priming occurred" — leaving Greeting alone scored 5/5 = **100% =
GOLD**. Excluding unmet criteria from the denominator turns a call where nothing happened
into a perfect score, which is far more damaging than an unfair zero.

### Conduct assessment — what the point scale does not capture

Returned alongside the criteria: `customer_language`, `language_fit` (with
`flagged_terms` and coaching), `unsupported_claims` (with `risk_level`), `listening`
(`interrupted`, `ignored_stated_information`), `opening_quality` (warm / acceptable /
robotic), `rapport` (excellent / good / neutral / poor), `callback_commitment`.

**Health claims are the brand's biggest exposure.** Any claim beyond `product_facts.md`
is flagged with a risk level — linking the product to preventing disease, even indirectly
("UV causes cancer and we filter UV"), is a liability regardless of the physics. Recorded
as a **risk to review, phrased factually**, never as an accusation against the agent.

**Coaching is developmental, addressed to the agent.** *"Try 'aaram se neend aati hai'
instead of 'circadian rhythm' when the customer is speaking Hindi"* — not *"the agent
failed to use Hindi"*. Management sees the risk framing; the agent sees the improvement.

---

## 6 · Approved product facts — the fact-checking ground truth

`prompts/reference/product_facts.md`. **Precedence rule (set 2026-08-17): when a
technical detail or price differs between sources, the catalogue wins.** Sameer's voice
notes are authoritative for *how to run a call*; technical numbers spoken in them may be
wrong. Order of authority: brand catalogue → console quantity chart → spec sheet → voice
notes. Anything not covered is **unverifiable — mark `unknown`, never guess**.

| Attribute | Approved value |
|---|---|
| Console size | 1200 × 400 mm (4 ft × 1.4 ft) |
| Footprint | 5.6 sq ft |
| Drop-down depth | 13 in / ~330 mm from the RCC slab |
| Illumination coverage | one console lights 5 ft × 5 ft |
| Ideal ceiling height | 9 ft (spec sheet: 9–9.5 ft) |
| Lumen output | 4500–5300 per console |
| Colour temperature | 2700 K – 6500 K · CRI 98 · dimming 0–100% |
| Drivers / controller / sensor | DALI DT-8 (EU chips) · Casambi · **geolocation** |
| Power | **20–40 W per console, max 50 W** |
| Life span | **12–14 years** at 9–12 h/day |
| Guarantee | 2 years, electronics and rafters |
| Materials | Frames pine, teak, raw wood, HDHMR · console tempered glass |
| Track record | **1000+** spaces transformed |

**Variants.** Ceiling: The Classical (min 330 mm), The Greens (315), The Minimalist
(315), Atrium (diagonal). Wall: French Window, Louvered Window (fixed 1265 × 465 mm),
Arch Window (single = 4 consoles, double = 8; custom 12 ft on request).

**Minimum console quantity chart.** 100–120 sq ft → 4 · 121–150 → 6 · 151–450 → 8 ·
451–550 → 10 · 551–774 → 12 · **775+ → 10% minimum coverage**, i.e. `(area × 0.10) ÷ 5.6`.
Worked: 775 sq ft → 77.5 ÷ 5.6 = **14 consoles**. **Absolute minimum 4.** Maximum
coverage **60–80%** — quantity must never exceed that.

**Corrections the catalogue forces on the scorecard:** "900+ projects" → **1000+**;
"12–15 years" → **12–14**; "0.03 kW/hr" → **20–40 W** (and kW is already a rate, so the
unit was wrong); **"lower consumption than a 15 W LED" is unsupported anywhere** — a
20–40 W console cannot draw less than a 15 W LED, so it must not be required, and an
agent asserting it is a **potential miss-sell**.

---

## 7 · The review rule book

`prompts/RULEBOOK.md`, read at runtime by `summarize_calls.py`. **Every rule came from a
real call the user reviewed and corrected**, applied to that one call so it can be
checked; the corpus is only re-run when the user says the book is complete.

| Rule | Substance |
|---|---|
| **R1** | Technical and company vocabulary is **never** jargon — SUNROOOF, wellness, console, GPS, app, remote, catalogue, quotation, serotonin, melatonin, circadian, optics, diffuser, nanotech, LED, driver, controller, IP40, productivity, psychological, hormone, vitamin D, UV, frequency, sensor, modular, warranty, guarantee. Flag only genuinely difficult English with an easy Hindi equivalent and no product connection — "subsequently", "irrespective". |
| **R2** | Only judge language when the customer **actually asked** for Hindi. Indians mix constantly; mostly-Hindi speech does not mean English is not followed. |
| **R3** | Everyday English inside Hindi is normal speech — "how are you", "sorry", "ok", "site", "price", "size", "time". Never strip these. |
| **R4** | Suggested lines must sound like a person, not a script. ✗ *"Ghar mein prakritik roshni ka anubhav deti hai"* ✓ *"ghar mein bilkul natural light jaisa feel aata hai"*. Openings are a short exchange, not a monologue. |
| **R5** | Health claims have **two shapes, only one wrong.** WRONG: the product credited with a medical outcome ("prevents cancer"). CORRECT, never flag: a harmful thing is *absent* ("there is no UV in our light"). Never flag the trained pitch — mood, stress, sleep, focus, serotonin, melatonin, circadian. |
| **R6** | A follow-up call is not a first call. No introduction expected; do not demand repetition of value proposition, technical detail or pricing already delivered. |
| **R7** | **"End user" must never be said to the customer** — internal vocabulary, impersonal, can wound. Ask "Yeh aapka apna ghar hai?" instead. Identifying an architect or contractor by those words is fine. |
| **R8** | Ask which city the **project** is in, not just where the customer lives. A customer can live in one city and build in another, and it drives site visits, installation and timelines. |

### Enforced in code, not left to the model

Because the model got these wrong often enough that a written instruction was not enough:

- **C1** — a finding must quote the **agent**, never the customer. It once raised a
  CRITICAL "agreed the product prevents cancer" while quoting a line labelled `Customer:`.
- **C2** — a medical-claim finding needs a disease word in the agent's own quote.
  Otherwise *"haan, filter karega"* became a cancer claim.
- **C3** — "end user" detected by pattern match over the agent's turns.
- **C4** — a call with no consultation is **not scored at all**. Scoring them on a
  5-point denominator produced numbers swinging 0 to 40 between identical runs.
- **C5** — N/A restricted to Objection Handling and CRM Disposition (§5).
- **C6** — a script-read opening takes Criterion 1 to zero; not listening costs a
  10-point red flag.
- **C7** — **temperature 0 on every review call.** At the SDK default of 1.0 the same
  call re-scored **18.8 points apart on average, with 40% of tiers changing.**

---

## 8 · The other scoring systems

**Sentiment** — text-based only, no acoustic analysis, so anger conveyed purely by tone
is not captured. Scored per third: `opening`, `mid`, `closing` on −1..+1, plus `overall`
label, `shift` (closing − opening), `emotions[]` and `unresolvedNegative`. Sentiment
prompts are **frozen** in `summarize_calls.py`, `enrich_for_ci.py` and
`build_ci_dataset.py` pending sign-off of `docs/sentiment_definition_for_review.md`.
Sentiment is deliberately **not** an agent metric.

**Purchase readiness** — 0–100 from seven sub-scores: `needFit`, `explicitIntent`,
`timeline`, `nextStepCommitment`, `authority`, `budget`, `sentiment`. Weights from the
upstream methodology doc: need & fit 25% · explicit intent 20% · timeline 15% ·
next-step commitment 15% · authority 10% · budget 10% · **sentiment 5%**. Bands ≥70 high,
50–69 medium, 30–49 low, <30 none. Sentiment is weighted low **so polite language cannot
masquerade as intent** — in Indian call speech courtesy is near-universal and carries
almost no purchase signal. Named *readiness*, not conversion probability, because it has
never been validated against historical conversions.

**Analysed population** — the denominator for every insight metric:
`meaningful AND transcribed AND sentiment present AND transcriptionConfidence ≥ 0.6`,
where `meaningful = connected AND >60s AND the customer actually spoke`.

**Thresholds and their honesty.** Only `MIN_TRANSCRIPTION_CONFIDENCE = 0.6` is
load-bearing. `shift > 0.2` (sentiment improved), `MIN_SAMPLE_SIZE = 25`, and the FAQ
recommendation bands (unanswered >30%, calls ≥15, negative-after >25%) are **guesses,
never measured against an outcome.**

---

## 9 · Conventions

- **Never invent a name, quote, date or CRM value.** Names come from Zoho; anything
  absent is null or "unknown", never a guess. Evidence quotes are verified verbatim
  against the transcript and dropped if they do not match (`verify_evidence`).
- **Ask before changing the LLM model.** Model choice is the user's cost decision,
  including for test runs. Default `gpt-4.1-mini` via `SUMMARY_MODEL`.
- **Transcripts contain real customer PII.** Any new vendor or destination needs explicit
  approval.
- **Zoho write-back is an external action** — pushing AI notes to live customer records
  needs explicit go-ahead each time, not standing consent.
- Prefer fixing root causes in the scripts over working around them in a shell. Failing
  stages log to `out/logs/deferred-errors.log` and let the chain continue.
- **Exit code 0 does not mean success.** `enrich` once exited 0 having failed 47% of its
  work to rate limits. Check each stage's own output counts.
- **PostgREST paging needs an explicit `order=`.** Without it, pages shift while another
  process writes and rows are silently skipped. This lost ~930 calls once.
- **OpenAI reserves the full `max_completion_tokens`** against the 200k/min TPM limit,
  used or not. ~12 workers is the knee of the curve (~490 audits/hour, ~6% retryable 429s).

---

## 10 · Known conflicts and defects

**Two rule files contradict each other on jargon.** `call_quality_audit.md` instructs the
model to flag `circadian · psychological · optics · diffuser · serotonin · melatonin ·
productivity · frequency · modular` on Hindi calls. `RULEBOOK.md` R1 says **never flag**
those same nine terms. Both are read at runtime, by different passes. Unresolved.

**The ceiling price range is asserted but unverifiable.** The scorecard requires
₹39,000–45,000 per ceiling console and the Advanced QA page says figures are "checked
against the approved range" — but `product_facts.md` states plainly that *nothing in the
catalogue or spec sheet states price*, so C6's price sub-points must be scored `unknown`.

**Speaker attribution is wrong on ~5% of calls.** `agent_speaker_id` treats whoever
mentions the company first as the agent, which breaks when the customer says *"Sunrooof
se call aaya tha"* first. On those calls the review judges the customer's words as the
agent's. Measured on a 151-call sample. Fix is to count brand mentions per speaker —
cheap, local, no LLM. **Needs doing before the full re-run.**

**A model label gates the analysed denominator.** `build_ci_dataset.py:568` sets
`connected = dur > 0 and outcome != "Not connected"`, where `outcome` traces to the LLM's
`not_reachable`. 269 calls (4.3%) are marked not-connected while carrying >60s of audio;
142 have real customer speech and are excluded from every insight metric.

**~13 paged Supabase reads still lack `order=`**, including `build_ci_dataset.py:186`
(the whole dashboard feed), `rescore_audits.py:93`, and two CRM **write** paths.

**`provenance.ts` is stale**, certifying numbers against a "100 calls, 30–31 July" pilot.

**`speech_dynamics.py` is wired to nothing** — complete and tested, consumed only by its
own test file. Signals available but unused: silence share, overlap, long pauses, talk
share, interruptions per minute, response-latency medians.

---

## 11 · Open decisions

From `prompts/SCORECARD_QUESTIONS.md` — seven ambiguities found by running the scorecard
against 20 real calls. **None are answered.** Scores cannot be defended until they are.

1. **CM-5 (moves 100 points).** Does a project-readiness answer satisfy it, or must the
   deadline be asked separately? Is "after the monsoon" enough? **If the customer
   genuinely does not know and the PSM asks properly — is the call still zeroed?** As
   written, yes. Two models reading the same 19 transcripts disagreed on 10.
2. **C6 has six mandatory sub-points** and scored zero on 15 of 20 pilot calls. Intended
   signal, or should some be non-mandatory?
3. **Red-flag deductions subtract from a percentage**, so when criteria are N/A the same
   −15 bites harder (15% vs 17.6%). Intended?
4. **Who counts as the PSM** on a transferred or three-party call?
5. **Should very short calls be scored at all?** No duration floor agreed.
6. **What counts as "five distinct benefits"?** Needs an approved list.
7. **Which sentiment definition applies** — `docs/sentiment_definition_for_review.md`
   awaits sign-off.

Also outstanding: `prompts/MISSING_DATA_REQUEST.md` — approved product facts, price
ranges and the console quantity chart, without which criteria 5, 6 and CM-1 cannot be
fully fact-checked. And the window-console price range, still unverified.

**Current effect:** auto-zero runs at ~74% across all calls, falling to 21% on calls over
20 minutes — only 431 of 5,021 July calls run 10 minutes or longer. The Advanced QA page
carries a standing "**Provisional — not for agent appraisal yet**" banner for this reason.

---

## 12 · Where things live

```
prompts/
  call_quality_audit.md        the 100-point scorecard — source of truth, read at runtime
  RULEBOOK.md                  review rules, read at runtime by summarize_calls.py
  SCORECARD_QUESTIONS.md       7 open ambiguities awaiting sign-off
  MISSING_DATA_REQUEST.md      product facts and prices still needed
  reference/product_facts.md   approved facts — the fact-checking ground truth
  reference/brand_catalogue.txt
  _archive_v1_scorecard.md     retired v1, kept for auditability

scripts/
  call_quality.py              schema, deterministic scorer, validator
  rescore_audits.py            zero-API replay of scoring-rule changes
  compare_scorecard_versions.py  diff two scorecard versions over stored data
  export/import_qa_review_workbook.py  the human calibration loop
  test_call_quality.py         scorer tests, no API calls
  summarize_calls.py           summary + audit; reads both prompt files at runtime
  build_ci_dataset.py          the dashboard snapshot (and System 2 scoring)
  export_qa_audits_for_dashboard.py
  build_review_scenarios.py    the curated listening cohorts
  speech_dynamics.py           acoustic signals (unused)

ci-dashboard/src/data/real/
  dataset.json                 ~58 MB main snapshot
  qa_audits.json               QA audits only — separate so it can be regenerated in
                               seconds while the audit runs and its rules are unapproved
  review_scenarios.json
  scorecard_change_review.json
```

Supabase `call_summaries` holds the model's judgements in the `call_quality_audit` jsonb
column plus `qa_final_score` and `qa_tier`. **The `qa_*` columns are not in
`dataset.json`** — only in Supabase and on the Advanced QA page.
