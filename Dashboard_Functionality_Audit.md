# Dashboard Functionality Audit

**Role:** Technical Product Analyst
**Audit date:** 29 August 2026
**Scope:** `ci-dashboard/` (React 19 + TypeScript SPA) and its supporting pipeline in `scripts/`
**Method:** Static code reading of every route, page, component, state container and service; plus direct inspection of the backing data files to verify that fields the UI renders are actually populated.

---

## Dashboard Overview

The application is a **single-page React 19 client with no backend of its own**. It is built with Vite, routed with `react-router-dom` v7 using `HashRouter`, and deployed to Vercel as a static bundle. There is no server, no API tier, and no database connection at runtime.

Data reaches the UI by a single mechanism: **build-time JSON imports**. Four snapshot files are compiled directly into the JavaScript bundle:

| File | Size | Consumed by |
|---|---|---|
| `dataset.json` | 56.9 MB | `services/realService.ts`, `data/taxonomy.ts` |
| `qa_audits.json` | 62.3 MB | `pages/AdvancedQa.tsx`, `components/QaAuditPanel.tsx` |
| `review_scenarios.json` | 0.8 MB | `pages/ReviewScenarios.tsx` |
| `scorecard_change_review.json` | 0.05 MB | `pages/AdvancedQa.tsx` |

**There are exactly two live network calls in the entire frontend**, both in [CallDetail.tsx](ci-dashboard/src/pages/CallDetail.tsx#L256-L273), and both pointing at a developer's own machine (`http://localhost:3000`). Everything else — every KPI, chart, table, filter and drill-down — is computed in the browser from the imported snapshots.

**State of the build:** compiles clean (`tsc -b && vite build`), lints clean (7 advisory warnings, 0 errors). 13 routes registered, 12 in the navigation, all reachable. Roughly 4,900 lines of application code.

**Verdict:** functionally rich and genuinely working, but architecturally a *read-only reporting client over a static export*, not a connected dashboard. The distinction drives most of the findings below.

---

## Core Functionalities (The Targets)

### A note on feature naming

Two of the three requested features do not exist under those names in the codebase. Rather than guess, here is the mapping I verified, with the ambiguity stated:

| Requested | Maps to | Confidence |
|---|---|---|
| **Executive summary** | `ExecutiveOverview` at route `/` | **Certain** — the page's own loading state reads "Computing executive summary…" |
| **All summary** | **No feature by this name exists.** Three distinct candidates documented below. | **Unresolved — needs your confirmation** |
| **Agent tracker** | Splits across **two** pages: `Agents` (`/agents`) and `Actions` (`/actions`) | **Ambiguous — both documented** |

---

### 1. Executive Summary — `/` — [ExecutiveOverview.tsx](ci-dashboard/src/pages/ExecutiveOverview.tsx)

**Status: Fully working.** The most data-dense page in the product.

#### Data fetch path

```
useFilteredData()  →  service.getFiltered(filters)  →  RealService.getFiltered()
                   →  applyFilters(calls, filters, DATA_ANCHOR)
                   →  in-memory array filter over 6,253 records
```

No network request. [useData.ts](ci-dashboard/src/state/useData.ts#L16) wraps a synchronous in-memory filter in a `Promise`, so the page *looks* asynchronous (it has loading and error states) but resolves on the same tick. `useAlerts()` follows the identical pattern, with results memoised per filter-key in a `Map` inside `RealService`.

Critically, period filters are **not** relative to today. [realService.ts](ci-dashboard/src/services/realService.ts#L36) computes a `DATA_ANCHOR` — the newest call in the snapshot plus one day (1 August 2026) — and all "last 7/30 days" windows run backwards from there. Without this the default view would be empty, since the data ends 31 July 2026.

#### Metrics displayed — 18 KPI cards

All computed by `kpiSummary()` in [metrics.ts](ci-dashboard/src/lib/metrics.ts#L19), each returning a current and prior-period value for delta arrows:

Total calls · Successfully transcribed · Transcription coverage % · Unique customers · Connected & meaningful conversations · Positive / Neutral / Negative sentiment calls · Sentiment improvement rate · High purchase-intent customers · Average agent quality score · Calls with a clear next action · Actions due today · Overdue actions · Unanswered customer questions · Critical complaints · Compliance alerts · Call → opportunity conversion

Every card is click-through: it either navigates to a page or applies a global filter via the `useDrill()` hook.

#### Charts and panels — 8 cards + 3 attention panels

Volume trend (current vs comparison) · Sentiment trend · Top 7 FAQs · Top 7 objections · Region-wise sentiment heatmap (click any cell to drill) · Call-to-order funnel · Agent quality vs conversion scatter · Action completion & overdue breakdown. Below those: Emerging customer issues (volume-normalised rise detection), High-priority opportunities (top 6 by purchase-readiness), Critical risk panel (open critical alerts).

#### Data verification

| Metric group | Source | Verified state |
|---|---|---|
| Volume, coverage, customers | Zoho CRM Calls via snapshot | **Real** — 6,253 calls, 100% transcribed |
| Meaningful conversations | Diarisation-derived | **Real** — 3,751 of 6,253 |
| Sentiment | gpt-4.1-mini per transcript | **Real but undefined rubric** — present on 6,249 of 6,253 |
| Agent quality | 9-dimension per-call scorecard | **Real** — present on all 6,253 |
| Unanswered questions | FAQ extraction | **Real** — 12,349 questions total |
| Critical complaints | `crm.complaintOpen` | **Effectively dead — only 1 call in 6,253 has this flag set** |
| Compliance alerts | `complianceFlags[]` | **Effectively dead — only 2 calls in 6,253** |
| Call → opportunity conversion | `crm.opportunityCreated` | **Real but very sparse — 72 of 6,253 (1.2%)** |
| Overdue actions | Computed SLA | **Structurally saturated — see below** |

**Finding — the "Action completion & overdue" card is not measuring anything.** I confirmed directly against the dataset that **all 10,907 actions carry `slaStatus: "overdue"`, with zero exceptions.** Every due date sits in June–July 2026, all before the 1 August anchor. The card therefore renders 100% overdue / 0% completed / 0% on track / 0% due today on every load, permanently. The same is true of the "Actions due today" KPI, which is always 0.

---

### 2. "All Summary" — no such feature exists

I searched the full source tree for `all summary`, `allSummary`, `summaryAll` and every `*Summary` identifier. **No page, route, component or navigation entry by that name exists.** The word "summary" resolves to exactly three things:

**Candidate A — `kpiSummary()`, the aggregate KPI engine.** [metrics.ts](ci-dashboard/src/lib/metrics.ts#L19). This is the closest match to "a summary of all calls": one function producing all 18 headline numbers over the whole filtered corpus, current period and prior period. It is the engine behind the Executive Overview KPI grid, and it is fully working. If "All summary" means *the summary of everything*, this is it — and it is already documented in §1.

**Candidate B — per-call summaries.** Every call record carries a `summary` string generated by gpt-4.1-mini from its transcript, with quoted evidence verified word-for-word and dropped on mismatch. Surfaced in the Call Explorer table and the Call Detail page. Present on all 6,253 calls. Fully working.

**Candidate C — the `summaries` pipeline stage.** [summarize_calls.py](scripts/summarize_calls.py#L171) defines a `CallSummary` model and writes to the Supabase `call_summaries` table — the system of record. This is backend, not dashboard: the SPA never reads Supabase. It reads the exported snapshot.

**Recommendation:** confirm which of these you meant. If you are thinking of a screen listing every call summary in one place, the nearest built thing is **Call Explorer** (`/calls`) — a filterable, sortable, exportable table of all calls with their summaries, documented under Additional Working Features.

---

### 3. Agent Tracker — two separate pages

The name maps ambiguously. Both are audited.

#### 3a. Agent Quality — `/agents` — [Agents.tsx](ci-dashboard/src/pages/Agents.tsx)

**Status: Working, with two dead comparison modes.**

**Data fetch:** identical to Executive Overview — `useFilteredData()` → in-memory filter. Rows built by `agentRows()` in [metrics.ts](ci-dashboard/src/lib/metrics.ts#L310), which groups analysed calls by `employeeId` and joins against the `EMPLOYEES` list from [taxonomy.ts](ci-dashboard/src/data/taxonomy.ts). In real mode that list is **not hardcoded** — it is the `employees` array inside `dataset.json`, containing 17 real Zoho call owners.

**Metrics displayed.** Six KPI cards (average quality, critical compliance failures, sentiment-improving calls, clear-next-step rate, diarisation-reliable calls, coaching opportunities), then:

- **A 9-parameter quality profile** — Opening, Discovery, Solution relevance, FAQ handling, Objection handling, Next-step clarity, Listening, Professionalism, Script adherence. *(Note: the provenance file describes this as an "eight-parameter scorecard"; the code implements nine. The code is authoritative — I have corrected this from my earlier report.)*
- **Quality vs sentiment-lift scatter**, agents with ≥25 analysed calls only.
- **Per-agent parameter heatmap**, click-through to that agent's calls.
- **A sortable agent table** with 11 columns and CSV export.

**Data verification — three columns are structurally empty:**

| Column | Backing field | Verified state |
|---|---|---|
| Quality score, Sentiment lift, Coaching focus | LLM extraction | **Real** — quality on all 6,253 calls |
| Talk ratio | Diarisation | **Real** — on 6,089 of 6,253; suppressed below a 5-call sample per agent |
| Compliance | `quality.complianceFail` | **Near-dead** — 2 flagged calls corpus-wide |
| **Orders** | `crm.orderConfirmed` | **Permanently zero — 0 of 6,253 calls have this set** |
| Opportunity rate | `crm.opportunityCreated` | Real but sparse — 72 corpus-wide |
| Overdue actions | Computed SLA | Saturated — every action is overdue |

**Finding — the "By team" and "By manager" comparison tabs return nothing usable.** The UI offers three comparison modes. I verified that **all 17 employee records carry the literal string `"Not mapped in CRM"` in both the `team` and `manager` fields**, and `taxonomy.teams` has a length of 1. Selecting either tab therefore collapses every agent into a single row labelled "Not mapped in CRM". The feature is built and wired; the upstream data does not exist because the Zoho Users module is outside this integration's OAuth scope.

#### 3b. Next-Action & Commitment Tracker — `/actions` — [Actions.tsx](ci-dashboard/src/pages/Actions.tsx)

**Status: UI fully working; persistence entirely absent.**

**Data fetch:** `useFilteredData()` → `allActions(d.analysed)` flattens the `actions[]` array off each call record. Mutations go through `service.updateAction()` → [realService.ts](ci-dashboard/src/services/realService.ts#L88), which mutates the in-memory object and appends to an in-memory audit log.

**Metrics and controls.** Six KPI cards (open, committed-on-call, AI-recommended pending, due today, overdue, completed-in-period), six filter tabs, CSV export, and a 10-column table with per-row Approve / Reject / Complete / Reschedule / Reassign-owner controls.

**Data verification — this is where the audit found the most divergence between UI and data.** Against all 10,907 actions:

| UI element | Expected behaviour | Actual verified state |
|---|---|---|
| "Committed on calls" tab | Subset of actions | **10,907 — i.e. 100%.** Every action has `source: "committed"` |
| **"AI-recommended" tab** | Actions needing approval | **Always empty — 0 of 10,907.** No action in the corpus has `source: "ai_recommended"` |
| **"Completed" tab** | Finished actions | **Always empty — 0 of 10,907.** Every action is `status: "pending"` |
| **"Due today" tab** | Actions due today | **Always empty — 0.** All due dates precede the anchor |
| "Overdue" tab | Late actions | **10,907 — i.e. 100%** |
| **"CRM task" column** | Link to a CRM task | **Always "not linked" — 0 of 10,907 have `crmTaskLinked: true`** |
| Approve / Complete / Reassign buttons | Update the action | **Work visually, then vanish on refresh.** Memory-only |

So of six tabs, **three are permanently empty and one holds everything.** The Approve/Reject controls in particular imply an approval workflow that has no queue to operate on, because no AI-recommended actions are ever generated.

---

## Additional Working Features

Every item below was verified as reachable, rendering real data, and free of placeholder content.

- **Customer Voice & Sentiment** (`/voice`) — opening/mid/closing sentiment per call with shift calculation, emotion inference, appreciation and dissatisfaction themes (1,082 and 838 calls respectively), pain points and feature requests (499 calls). Text-derived only; no acoustic analysis.
- **FAQs & Knowledge Gaps** (`/faqs`) — 12,349 verified customer questions across 3,325 calls, deduplicated one-per-call-per-question to prevent inflation, graded answered/partial/unanswered, with response latency measured from Sarvam word timestamps. Drill-down to source calls.
- **Regional Intelligence** (`/regions`) — segment rows by region/state/city with reliability gating at a 25-call minimum sample. 387 cities and 36 states in the taxonomy.
- **Sales & Objections** (`/sales`) — 1,269 objections across 907 calls, timestamped by matching the customer's quote back to its diarised turn; weighted purchase-readiness scoring; competitor mentions (63 calls); customer-stated budget (56) and timeline (1,135).
- **Call Explorer** (`/calls`) — sortable, paginated, CSV-exportable table across all filtered calls. The de-facto "all summaries" view.
- **Call Detail** (`/calls/:id`) — full diarised transcript with per-turn timestamps, deep-linkable to a timestamp via `?t=`, alongside summary, entities, sentiment journey chart, and the embedded QA audit panel.
- **Advanced QA** (`/advanced-qa`) — the 100-point PSM scorecard across 6,260 audited calls with per-criterion evidence, tier filtering, search, and a before/after scorecard-version comparison. Deliberately bypasses the global date filter, which is correct: audited calls start in June and the 30-day default would hide all of them.
- **QA Audit Panel** (component, embedded in Call Detail) — coaching-first presentation: what went wrong, the exact quote, and the better line to have used. Score shown last and small, by design.
- **Review Sets** (`/review-sets`) — 979 calls across three lead-level journey cohorts and four contradiction cohorts (where two systems provably disagree about the same call). Also bypasses the global filter.
- **Alerts & Escalations** (`/alerts`) — 15 distinct rules in [alerts.ts](ci-dashboard/src/lib/alerts.ts), spanning per-call triggers (severe-negative close, repeat-negative customer, cancellation/refund risk, legal threat, compliance flags, low transcription confidence) and aggregate trend spikes (FAQ spike, emerging unanswered question, objection spike, competitor mentions rising, regional sentiment decline). Severity filtering and CSV export work.
- **Data Quality & Config** (`/data`) — transcription confidence bands, a nine-system integration status table, a twelve-point AI-governance checklist, and the live audit log.
- **Role-based access control** — five roles enforced by a `Guard` wrapper in [App.tsx](ci-dashboard/src/App.tsx#L20) plus navigation filtering. Selecting the Agent role auto-locks the employee filter to that agent's own calls and releases it on role change.
- **Global filter bar** — 17 filter dimensions with cascading region→state behaviour, date presets anchored to the snapshot.
- **Saved views** — persisted to `localStorage` under `ci-saved-views-v1`, with defensive merging against `DEFAULT_FILTERS` so a stale saved view cannot break the app.
- **Explore mode** — inline per-page explanations, toggled globally.
- **CSV export** — implemented once in `ui.tsx` and reused across Agents, Actions, Alerts, Advanced QA and Review Sets.
- **Provenance labelling** — 45 metric areas each declaring real / partial / demo status, surfaced as hover dots throughout the UI and tabulated on the Data Quality page.

---

## WIP / Incomplete Features

Ordered by how visible the gap is to a user.

### 1. Every write operation is discarded on refresh
`RealService` stores action mutations, alert acknowledgements and manager corrections in instance fields — `alertOverrides`, `auditLog`, and direct object mutation. Nothing is persisted anywhere. The audit-log entries the service writes even say so, appending "(in-app only — no task system connected)" to their own text. **Affected:** Actions page controls, Alerts acknowledge/resolve, Call Detail correction controls.

### 2. `DATA_MODE: 'live'` is declared but not implemented
[services/index.ts](ci-dashboard/src/services/index.ts#L18) resolves three modes. Setting `'live'` **throws immediately** with a pointer to the integration docs. The `DataService` interface in [types.ts](ci-dashboard/src/services/types.ts) is explicitly designed as the seam for a real backend — the contract exists, the implementation does not.

### 3. The AI-recommended action approval workflow has no input
Approve/Reject buttons, a pending state, a dedicated tab and a KPI card are all built for `source: 'ai_recommended'` actions. **Zero exist in the data.** The pipeline currently emits only `committed` actions. This is a complete UI feature waiting on an upstream generator.

### 4. Team and manager comparison have no reference data
Described in §3a. Built, wired, and returns one meaningless bucket because all 17 employees read "Not mapped in CRM".

### 5. Order and revenue attribution are structurally impossible
`crm.orderConfirmed` is false on all 6,253 calls and `crm.revenueInfluenced` is null on all 6,253. Consequences: the Agent table's Orders column is always 0; the funnel's won-order stage is deliberately not rendered; and the **"High-value customer needs escalation" alert rule can never fire**, because its trigger requires `revenueInfluenced > 1,000,000`. That is a dead rule in the live rule set.

### 6. `crm.verified` is false on every record
The UI distinguishes "AI-inferred" from "CRM-verified" outcomes — a genuine governance feature — but **no call in the corpus is currently marked verified**, so the distinction has only one side in practice.

### 7. The CRM write-back depends on a developer's laptop
The one real integration (§ Data Architecture below) points at `http://localhost:3000`. For any user not running `scripts/audio_proxy.mjs` locally, both the audio player and the Update-CRM card fail. The code handles this gracefully — it renders "Local update server not reachable — is scripts/audio_proxy.mjs running on :3000?" — but it is a hardcoded localhost dependency in a deployed web app.

### 8. Mock generator retained alongside live data
`data/mock/` (generator, taxonomies, random) and `mockService.ts` remain in the tree and are bundled. Not dead code — `DATA_MODE` can still select them, and the demo banner is wired — but it is a second full data path being maintained in parallel.

---

## Data Architecture

**There is no frontend-to-backend communication for reporting data.** This is the single most important architectural fact in this audit.

### The read path

```
Zoho CRM ─┐
Sarvam    ├─► Python pipeline ─► Supabase `call_summaries` ─► build_ci_dataset.py
gpt-4.1   ─┘   (scripts/)         (system of record)         export_qa_audits_for_dashboard.py
                                                                        │
                                                              dataset.json + qa_audits.json
                                                                        │
                                                              ▼ imported at BUILD time
                                                    Vite bundles JSON into the JS
                                                                        │
                                                              ▼ at RUNTIME
                          realService ─► applyFilters() ─► metrics.ts ─► React pages
```

The Supabase database is the system of record, but **the dashboard never talks to it.** A Python export writes JSON files into `src/data/real/`; Vite compiles them into the bundle; the browser filters them in memory. Refreshing the dashboard's data requires re-running the exporters and rebuilding the app.

The consequence is measurable: the production bundle is **110 MB uncompressed, 19.5 MB gzipped**, because the entire two-month corpus ships inside the JavaScript. Every visitor downloads all 6,253 calls and all 6,260 audits before the first screen paints.

### The abstraction seam

Pages never touch data modules directly. They call `useFilteredData()` / `useAlerts()`, which call the `DataService` interface. That interface declares ten methods and is documented as the swap point for real APIs. The architecture is *ready* for a backend; it simply has not been given one.

### The one real integration

Two endpoints, both on `http://localhost:3000`, served by the standalone Node process `scripts/audio_proxy.mjs`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/audio?url=…` | GET | Streams call recordings, holding the Zoho session cookie server-side so it never reaches the browser |
| `/api/crm-draft?callId=…` | GET | Fetches an AI-drafted note, call result and city for review |
| `/api/update-crm` | POST | **Writes back to the live Zoho CRM record** |

The write-back is a genuine, functioning two-way integration and the only one in the product. It is sensibly constrained: the disposition field is a closed picklist matching Zoho's own values rather than free text, fields Zoho already has a value for are never overwritten, and the note is labelled as AI-generated. Sync state is visible per call — 5,015 of 6,253 calls already have an AI note on Zoho, and 6,185 have a transcript.

Worth flagging for governance: this endpoint modifies live customer records, and the project's own working agreement requires explicit go-ahead for each write-back rather than standing consent.

### Client-side persistence

Only `localStorage`, and only for saved filter views. No session state, no user identity, no server-side storage of any kind.

---

## Summary Table

| Area | Working | Partly working | Not wired |
|---|---|---|---|
| Routes | 13 of 13 | — | — |
| Insight pages | 5 of 5 | — | — |
| Performance pages | 5 of 5 | — | — |
| Operations pages | 2 of 2 | — | — |
| Read path | Build-time snapshot | — | Live API (`DATA_MODE: 'live'` throws) |
| Write path | Zoho CRM note/result/city via local proxy | — | Actions, alerts, corrections (memory only) |
| Action tabs | 3 of 6 populated | — | AI-recommended, Completed, Due today all permanently empty |
| Agent comparison | By employee | — | By team, by manager (no source data) |
| Commercial metrics | Opportunity rate (sparse) | — | Orders, revenue (structurally zero) |

---

*Every quantitative claim in this document was verified by direct inspection of the source files and by parsing the backing JSON snapshots on 29 August 2026. Where a feature's UI is complete but its data is absent, both facts are stated.*
