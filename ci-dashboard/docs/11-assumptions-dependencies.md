# 11 · Assumptions & Missing Dependencies

> **Updated for live data (July 2026).** The dashboard now runs on 722 real Zoho calls rather than
> the mock generator. The dependency table below is superseded by `src/lib/provenance.ts`, which
> declares provenance per feature and is rendered on the Data Quality page. What actually became
> real: call metadata, transcripts and timestamps, sentiment, purchase readiness, objections, FAQs,
> agent quality, VoC themes, lead source, campaign, CRM stage and client type. What did not:
> pincode, product series, deal revenue/orders, agent team & manager, task-system sync, audio
> playback, FAQ answer *accuracy*, and period-over-period comparison (the dataset is a single
> 24-day window).

## Context found at build time

The project folder was **empty** (fresh git repo, no commits, no existing code), so there was no
existing codebase, component library or design system to preserve — the instruction to "inspect
and preserve the existing codebase" resolved to building a fresh, self-contained stack
(Vite + React 19 + TypeScript + Recharts) with a clean service layer designed for the existing
transcription capability to plug into.

## Assumptions (each is configurable)

1. **Brand**: "Sunrooof" (from the workspace email domain); one constant in `src/config.ts`.
2. **Domain**: premium modular kitchens/wardrobes — drives mock products, FAQ examples and
   scripts. Taxonomies are data, not code; swap `src/data/mock/taxonomies.ts` / live taxonomy.
3. **Thresholds**: analysed-call ASR confidence ≥ 0.60; minimum segment sample 25; meaningful
   call > 60s; sentiment label cut-points ±0.15; PR bands 70/50/30. All in `src/config.ts` or
   documented formulas.
4. **Sentiment is text-based** — stated in the UI. No acoustic/voice-tone claims anywhere.
5. **Comparison period** = preceding window of equal length.
6. Currency ₹ (Indian formatting, lakh/crore).

## Missing dependencies (declared, not faked)

| Dependency | Impact today | Where declared |
|---|---|---|
| Telephony audio streaming | Audio player is a labelled placeholder; timestamp links highlight transcript only | Call Detail, Data Quality |
| Live ASR pipeline | All transcripts are mock; coverage numbers are demo | Demo banner, Data Quality |
| CRM (live) | Outcomes/revenue marked CRM-verified only within mock semantics | Data Quality |
| Task system | Action sync is in-app only | Data Quality, doc 06 |
| Approved knowledge base | Answer accuracy NOT assessed — relevance/completeness only | FAQs page, Data Quality |
| Translation service | Original-language transcripts only | Data Quality |
| PR-score validation vs historical conversions | Score labelled "Purchase Readiness", never "conversion probability" | Sales page, doc 08 |
| SSO / server-side RBAC | Client-side role simulation only | doc 10 |

## Known limitations / future work

- Mock aggregation is client-side; the service contract already takes filters so a live backend
  can aggregate server-side without UI changes.
- Bundle is a single chunk (~770 KB min); code-split routes before production deploy.
- Saved views are localStorage; move to user profile service when auth lands.
- City-level filter exists in state but is exposed via Regional drill rather than the top bar
  (kept the bar uncluttered).
