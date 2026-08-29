---
name: ci-dashboard-real-data-build
description: The Call Intelligence SPA at ci-dashboard/ runs on real Sunrooof data; how to rebuild it and which features are demo-only
metadata: 
  node_type: memory
  type: project
  originSessionId: 035b8b43-5741-4969-be98-65fc9a4bd4f7
  modified: 2026-08-01T19:53:01.532Z
---

`ci-dashboard/` in this project is a Vite/React "Call Intelligence & Voice of
Customer" SPA (10 pages), cloned 2026-07-31 from `~/Desktop/call transcription new`
and rewired to real Sunrooof data. `DATA_MODE='real'` in `src/config.ts` selects
`src/services/realService.ts`, which imports a build-time snapshot at
`src/data/real/dataset.json`. Serve with `npm run build && npm run preview --
--port 5199` (5173 is the sibling Magppie copy's port — keep them apart).

Rebuild pipeline (all in this project's `scripts/`, run in order):
`fetch_zoho_enrichment.py` (CRM fields) → `enrich_for_ci.py` (LLM: segmented
sentiment, readiness, objections, quality) → `build_ci_dataset.py` (joins
Supabase + Zoho + enrichment → dataset.json). `aggregate_faqs.py` must run
before the builder — it emits `out/faq_question_map.json`, without which FAQ
clustering silently degrades to word-overlap matching.

**`build_ci_dataset.py` used to hardcode its output into the sibling Magppie
project and overwrote that agent's dataset once.** It now writes to
`BASE/ci-dashboard/...`. Never point it outside this repo.

Sunrooof-specific adaptations vs the Magppie original: Zoho field names differ
(`Type_of_Space` not `Property_Type`; Deals carry `Total_Consoles` /
`Proposed_Order_Amount`); `room_type` not `kitchen_type`; CITY_REGION extended
for Sunrooof's spelling variants + an International bucket (Dubai/Abu Dhabi
leads); `product_series()` collapses the model's dozen namings of the single
console line. Agent names can be a single word (Pallavi, Shivalee) — that broke
a formatter assuming a surname, fixed via `shortName()` in `src/lib/format.ts`.

Feature provenance lives in `src/lib/provenance.ts` (45 surfaces: 30 real, 7
partial, 8 demo) and renders as green/amber/red dots beside every KPI, with the
reason on hover and a full table on the Data Quality page. Keep the notes'
numbers in sync with the dataset whenever it is rebuilt. The 8 demo surfaces
are structural gaps, not laziness: pincode (Zoho Zip_Code empty on all leads),
influenced revenue (only 1 linked Deal), agent team (Users module out of OAuth
scope), CRM task sync + alert workflow (no system to write back to), audio
playback (static SPA cannot hold the Zoho cookie), FAQ answer *correctness* (no
approved knowledge base), and period-over-period (snapshot window too short).

Related: [[cloned-from-magppie-call-transcription]], [[ask-before-changing-llm-model]]
