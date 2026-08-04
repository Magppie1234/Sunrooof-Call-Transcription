# 8 · Scoring Methodology

Three **independent** scores — never blended, per business rule. Implementation:
`src/data/mock/generate.ts` (mock), `src/lib/metrics.ts` (aggregation).

## A. Customer Sentiment Score (how the customer felt)

- Opening / mid / closing scores on −1…+1, **text-based** (transcript only; the UI never claims
  voice-tone analysis).
- Overall label from weighted mean (closing weighted 1.4× — the end state matters most).
- Shift = closing − opening; improvement > +0.2, deterioration < −0.2.
- Explicitly *not* an agent metric: a customer who arrives angry does not mark the agent down.

## B. Purchase Readiness Score (0–100)

Named "Purchase Readiness", **not** conversion probability — it has not been validated against
historical conversions (listed as future work in doc 11).

| Component | Weight |
|---|---|
| Need & product fit | 25% |
| Explicit buying intent | 20% |
| Purchase timeline | 15% |
| Next-step commitment | 15% |
| Decision-making authority | 10% |
| Budget readiness | 10% |
| Sentiment | 5% |

Bands: ≥70 high · 50–69 medium · 30–49 low · <30 none. Sentiment is deliberately only 5% so
polite/positive language cannot masquerade as intent. Service calls get no PR score (n/a).

## C. Agent Quality Score (0–100)

| Parameter | Weight |
|---|---|
| Discovery & need identification | 20% |
| Solution relevance | 15% |
| Product & FAQ handling | 15% |
| Objection handling | 15% |
| Next-step clarity | 15% |
| Listening behaviour | 10% |
| Opening & introduction | 5% |
| Professionalism & empathy | 5% |

Also captured outside the average: script adherence, talk-to-listen ratio, interruptions,
longest silence (all **only when diarisation is reliable**, threshold 70% of calls in view),
and coaching notes.

**Critical compliance failures are a separate boolean** — displayed as their own KPI, column and
alert; never absorbed into the average. One compliance failure on an otherwise-90 call still
shows "1 critical failure" beside the score.

## Aggregation guardrails

- Segment minimums: `MIN_SAMPLE_SIZE = 25` analysed calls before a segment (region, agent,
  product) is presented as a reliable trend; below that every surface shows "low sample".
- Transcripts under 60% ASR confidence are excluded from aggregates (visible toggle to include,
  with warning banner).
- All scores displayed with n (denominator) and AI confidence where item-level.
