# 4 · Metric Definitions & Formulas

Source of truth: `src/lib/metrics.ts`, `src/lib/filters.ts`. Notation: **P** = current period,
**P′** = comparison period (preceding window of equal length).

## Denominators (the three call populations)

| Population | Definition |
|---|---|
| **Total calls** | All call records in P matching the active filters |
| **Meaningful** | `connected AND duration > 60s` |
| **Analysed** | `meaningful AND transcribed AND asr_confidence ≥ 0.60` (threshold in `src/config.ts`; low-confidence calls can be included via an explicit toggle, with a warning banner) |

All insight metrics (sentiment, FAQs, objections, scores) use **Analysed** as denominator.
Coverage/volume metrics use **Total**. Conversion metrics use **Meaningful**.

## Executive KPIs

| Metric | Formula |
|---|---|
| Transcription coverage | transcribed ÷ total calls |
| Unique customers | distinct `customer_id` in P |
| Positive / neutral / negative | count of analysed calls by overall sentiment label |
| Sentiment improvement rate | calls with `closing − opening > +0.20` ÷ analysed |
| High purchase-intent customers | distinct customers with ≥1 call scoring PR ≥ 70 |
| Avg agent quality | mean weighted quality score over analysed scored calls |
| Calls with a clear next action | calls with ≥1 **committed** action ÷ analysed |
| Actions due today / overdue | open actions with due date today / past |
| Unanswered customer questions | Σ FAQ occurrences with status `unanswered` |
| Critical complaints | analysed calls with open CRM complaint AND negative sentiment |
| Compliance alerts | analysed calls with ≥1 compliance flag |
| Call → opportunity / order | CRM-verified opportunities / orders ÷ meaningful calls |
| Revenue influenced | Σ CRM-verified `revenueInfluenced` (never inferred) |

## Sentiment (text-based only)

Numeric scores −1…+1 at opening / mid / closing. Label: > +0.15 positive, < −0.15 negative,
else neutral. Shift = closing − opening. Emotions (frustration, confusion, hesitation, urgency,
trust, interest, satisfaction) are classifier outputs from transcript text.
**Rules enforced:** customer sentiment is computed separately from agent speech; polite language
is not treated as purchase intent (intent comes from the Purchase Readiness weights, in which
sentiment is only 5%); a negative customer does not lower agent quality directly.

## FAQs

Counted **once per call per standardised question** (intra-call repeats ignored — see
`faqRows()`). Per FAQ: calls, unique customers, % of analysed, P vs P′, answered/partial/
unanswered, avg response seconds, sentiment-after-answer split, escalations, AI confidence,
recommendation. Emerging FAQ: `calls ≥ 4 AND calls > 1.5 × prev` (volume-normalised for
aggregate emerging panel).

## Objections

Per type: calls, P vs P′, high-intensity count, resolved/partial/unresolved,
positive-reaction %, most-used technique. Objections are evidence, not verified loss reasons.

## Regional

Every metric shown as raw count **and** rate per 100 analysed calls. Reliability flag:
`n ≥ MIN_SAMPLE_SIZE (25)`; below that the row is labelled "low sample" and excluded from
trend claims.

## Funnel

Total → connected → meaningful → interest (PR med/high) → high readiness → opportunity (CRM) →
order (CRM). Transcript-inferred and CRM-verified stages are labelled per bar.

## Delta convention

Period-over-period deltas: `(P − P′) ÷ |P′|`; "no prior data" when P′ = 0. Metrics where an
increase is bad (negative calls, overdue, complaints, compliance) invert the delta colour.
