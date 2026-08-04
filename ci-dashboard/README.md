# Sunrooof · Call Intelligence & Voice of Customer Dashboard

A production-ready, decision-focused dashboard that turns speaker-separated call transcripts
into business insight: customer voice & sentiment, FAQs & knowledge gaps, regional intelligence,
sales & objection intelligence, agent quality, next-action tracking, alerts and governance.

> **Live data.** The app runs on the real Sunrooof dataset: **100 Zoho CRM calls (30–31 July 2026)**,
> transcribed with Sarvam Saaras v3 and analysed with gpt-4.1-mini. `DATA_MODE = 'real'` in
> `src/config.ts` selects `src/services/realService.ts`, which reads the build-time snapshot at
> `src/data/real/dataset.json` (regenerate with `scripts/build_ci_dataset.py` in the
> parent transcription project, which writes straight into this folder). The original mock generator is still present and selectable with
> `DATA_MODE = 'mock'`.
>
> All insights are text-based (transcripts only — no voice-tone analysis). Every surface carries a
> **provenance dot** — 🟢 real · 🟠 real with a declared gap · 🔴 demo data with no real source —
> defined in `src/lib/provenance.ts` and listed in full on the **Data Quality** page. Features that
> cannot be backed by real data are kept and marked, never silently removed.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production bundle
npm run preview
```

## Pages

Executive Overview · Customer Voice & Sentiment · FAQs & Knowledge Gaps · Regional Intelligence ·
Sales & Objection Intelligence · Agent Quality · Next-Action Tracker · Call Explorer (+ per-call
evidence view) · Alerts & Escalations · Data Quality & Configuration.

Every KPI and chart drills down: summary → segment → call list → transcript @ timestamp.
Global filters, saved views, CSV export, role-based views ("Viewing as" in the sidebar),
period-vs-comparison on every chart, denominators on every percentage.

## Architecture

```
src/
  config.ts          brand, thresholds, data mode, versions
  types/domain.ts    canonical data model (docs/05)
  services/          DataService contract + mock implementation (live impl plugs in here)
  data/mock/         ⚠ mock-only: seeded generator + taxonomies (never imported by live code)
  lib/               filters/windowing, metric formulas (docs/04), alert rules (docs/09)
  state/             global filters, roles, saved views, data hooks
  components/        layout/shell, UI kit (KPI cards, tables, heatmaps, funnel), charts
  pages/             the 10 dashboard pages + call detail
docs/                deliverables 1–12 (IA, metrics, dictionary, APIs, AI schema,
                     scoring, alerts/SLA, RBAC, assumptions, testing)
```

## Deliverables index

| # | Deliverable | Where |
|---|---|---|
| 1–3 | Information architecture, responsive UI, navigation & drill-downs | app + `docs/01` |
| 4 | Metric definitions & formulas | `docs/04` |
| 5 | Data dictionary | `docs/05` |
| 6 | API & integration requirements | `docs/06` |
| 7 | AI-extraction schema | `docs/07` |
| 8 | Scoring methodology | `docs/08` |
| 9 | Alert & SLA rules | `docs/09` |
| 10 | Role-based access structure | `docs/10` |
| 11 | Assumptions & missing dependencies | `docs/11` |
| 12 | Testing & validation results | `docs/12` |
