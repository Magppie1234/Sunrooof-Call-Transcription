# 1–3 · Information Architecture, UI & Navigation

## Product

**Sunrooof · Call Intelligence & Voice of Customer** — a decision-focused dashboard that turns
speaker-separated call transcripts into insights for management, sales managers, service managers,
quality teams and individual employees. Brand name is configurable in `src/config.ts`.

## Page map

| # | Route | Page | Primary users | Answers |
|---|---|---|---|---|
| 1 | `/` | Executive Overview | Management | What's happening, what needs action today |
| 2 | `/voice` | Customer Voice & Sentiment | Management, Quality | What customers feel, appreciate, complain about |
| 3 | `/faqs` | FAQs & Knowledge Gaps | Quality, Marketing, Training | What customers ask, where agents can't answer |
| 4 | `/regions` | Regional Intelligence | Management, Sales Managers | How insights differ by region/state/city |
| 5 | `/sales` | Sales & Objection Intelligence | Sales Managers | Needs, buying signals, objections, competitors |
| 6 | `/agents` | Agent Quality | Managers, Quality, Agents | How effectively employees handle conversations |
| 7 | `/actions` | Next-Action Tracker | Everyone | Commitments, AI recommendations, SLA state |
| 8 | `/calls`, `/calls/:id` | Call Explorer + Call Detail | Everyone | Search calls; full evidence per call |
| 9 | `/alerts` | Alerts & Escalations | Management, Managers | What requires immediate attention |
| 10 | `/data` | Data Quality & Configuration | Admin, Quality | Pipeline health, integrations, governance, audit |

## Drill-down model

Every KPI card and chart element is clickable and follows one path:

**Summary → segment (filter applied) → Call Explorer list → Call Detail → transcript segment @ timestamp.**

Implementation: `useDrill()` (src/components/layout.tsx) patches the global filter state and
navigates to `/calls`; the applied filters are visible and removable in the top filter bar.
Insight rows (FAQ hits, objections, actions) deep-link to `/calls/:id?t=<seconds>`, which
scrolls/highlights the nearest transcript utterance — the audio player will seek to the same
offset once the telephony integration is connected.

## Global filter bar (persistent, all pages)

Date preset (7/30/90 days, comparison = preceding window of equal length) · region · state ·
team · employee · product series · direction · language · sentiment · purchase readiness ·
customer type · lead source · compliance flag · low-confidence-transcript toggle · free-text
search (Call Explorer). Plus: saved views (localStorage), reset, CSV export per table, last-refresh
timestamp, role switcher ("Viewing as").

## Layout system

- Dark slate sidebar (identity + navigation, grouped: Insights / Performance / Operations, with
  open-critical-alert badge), light content plane.
- Responsive: ≤1080px sidebar collapses to icons; ≤760px it becomes a horizontal scrollable bar
  and all multi-column grids stack to one column. Verified at 1440, 834 and 390 px.
- States implemented everywhere: loading (spinner), empty (message + hint), error, and
  low-confidence banners; every percentage shows its denominator; every page shows its period
  and comparison period.
