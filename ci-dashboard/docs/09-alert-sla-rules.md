# 9 · Alert & SLA Rules

Engine: `src/lib/alerts.ts`. Every alert carries severity, customer, owner, reason, evidence,
recommended response and a resolution deadline. **Critical alerts require manual review** —
the system never auto-responds to customers.

## Per-call rules

| Rule | Severity | Trigger | Resolution SLA |
|---|---|---|---|
| High-intent, no follow-up | High | PR high AND no non-rejected action | 24h |
| Commitment overdue | High | Quotation/callback/meeting/site-visit action past due | 12h |
| Severe-negative customer | **Critical** | closing sentiment < −0.5 | 4h (manager callback) |
| Repeat-negative customer | High | negative across multiple calls | 24h |
| Unresolved complaint | **Critical** | complaint open + negative close + no resolution | 8h |
| Cancellation / refund risk | **Critical** | cancellation/refund indication in risks | 4h |
| Legal threat | **Critical** | legal action referenced | 2h → leadership + legal |
| Mis-selling / false commitment | High | compliance flag (overstated warranty, unchecked promise) | 48h |
| Unapproved discount | High | discount-beyond-policy flag | 48h |
| Sensitive-data / payment risk | **Critical** | payment-to-personal-number or PII exposure flag | 4h |
| High-value customer escalation | High | verified revenue > ₹10L AND negative call | 24h |
| Low transcription confidence | Medium | ASR confidence < 60% | 72h (pipeline hygiene) |

## Aggregate (trend) rules — volume-normalised vs comparison period

| Rule | Severity | Trigger |
|---|---|---|
| FAQ spike | Medium | ≥6 calls AND >1.6× prior period |
| Emerging unanswered question | High | ≥4 unanswered AND >35% unanswered share |
| Objection spike (region-filterable) | Medium | ≥8 calls AND >1.6× prior |
| Competitor mentions rising | Medium | ≥10 calls AND >1.5× prior |
| Region sentiment declining | High | reliable sample AND negative rate >1.5× prior AND ≥5 negative |

## Action SLA model

`on_track → due_today → overdue` for open actions; `met / breached` on completion (breached if
completed after due). Priorities: P1 = high-readiness customers, P2 = medium, P3 = rest.

## Lifecycle

`open → acknowledged → resolved`, all transitions audit-logged. Open critical count is badged on
the sidebar globally. Alert deadlines are computed from rule SLA at detection time.
