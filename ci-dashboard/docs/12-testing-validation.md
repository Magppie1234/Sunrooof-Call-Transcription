# 12 · Testing & Validation Results

Performed on the delivered build (2026-07-31). Commands: `npm run build` (tsc + vite),
`npm run dev` / `vite preview`, headless-Chrome screenshots + CDP layout measurement.

## Build & static checks

| Check | Result |
|---|---|
| TypeScript strict build (`tsc -b`) | ✔ 0 errors |
| Production build (`vite build`) | ✔ succeeds |
| Chart palette | Validated dataviz reference palette (fixed slot order); status colours reserved; text labels accompany all colour encodings |

## Formula validation (spot-checked against rendered UI)

| Validation | Result |
|---|---|
| KPI denominators (analysed vs total vs meaningful) sum correctly (e.g. 72+54+31 = 157 analysed) | ✔ |
| Transcription coverage = transcribed/total (193/237 = 81.4%) | ✔ |
| Failed + not-connected + transcribed = total (15+29+193 = 237) | ✔ |
| Confidence bands sum to transcribed (40+66+57+29 ≈ 193 incl. <60% band split) | ✔ |
| FAQ counted once per call (dedupe in `faqRows`) | ✔ code-enforced |
| Per-100 rates show raw count alongside (Regional) | ✔ |
| Funnel monotonic, CRM stages labelled | ✔ |
| Action SLA states (overdue/due-today/met/breached) recompute on reschedule/complete | ✔ exercised via mock service |
| Low-sample segments flagged at n<25 everywhere | ✔ |

## Visual inspection (screenshots reviewed)

All 10 pages + call detail at 1440px; Executive Overview at 834px (tablet) and 390px (mobile).
Verified: no clipping/overlap/horizontal page scroll (a mobile sidebar overflow bug was found
via CDP measurement and fixed — `min-width:0; max-width:100vw` on the collapsed sidebar), chart
legends and labels readable, periods and denominators visible, empty/low-sample/low-confidence
states rendering.

Note: raw `chrome --headless --window-size=390` screenshots show fake overflow because headless
Chrome enforces a ~500px minimum window; genuine 390px device emulation (CDP viewport) confirms
zero horizontal overflow (`body.scrollWidth === 390`).

## Edge cases exercised by the mock dataset (by construction)

- Long names: "Meera Krishnamurthy-Raghunathan", "Venkatasubramanian Srinivasan-Venkataraghavan" — wrap, no clipping.
- Failed transcriptions (~7%) and non-connected calls — excluded from insights, listed in Explorer with "no transcript" state.
- Low-confidence transcripts (15%) — excluded from aggregates with visible banner + toggle.
- Unreliable diarisation (~15%) — talk metrics suppressed ("n/a") per governance rule.
- "Not mentioned" budget/timeline/decision-maker — rendered honestly, never imputed.
- Empty result sets (aggressive filter combos) — every chart/table has an empty state.
- Multiple languages incl. Hinglish/Marathi/Kannada mock utterances.
- Repeat-negative customers, legal threats, compliance flags (rare) — alert rules fire.

## Not tested (requires live systems)

Live API latency/pagination, audio seek, CRM writebacks, SSO/RBAC enforcement, translation
display, real ASR accuracy. These are declared in doc 11 and on the Data Quality page —
no claim of completion is made for untested integrations.
