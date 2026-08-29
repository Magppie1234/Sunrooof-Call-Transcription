# CRM Call Intelligence Dashboard — Executive Status Report

**Prepared for:** Senior Leadership
**Reporting date:** 28 August 2026
**Product:** Sunrooof Call Intelligence Dashboard (Zoho CRM–sourced)
**Basis of assessment:** Direct inspection of the codebase, git history, data snapshots and automated test suites in the working repository.

---

## 1. Executive Summary

The CRM Call Intelligence Dashboard is a **working, feature-complete analytics product** that turns Sunrooof's raw sales-call recordings into structured commercial intelligence. Every one of its twelve business views is built and renders live company data — not placeholders. Against a two-month corpus of **6,253 real customer calls** (June–July 2026), the platform has already surfaced 12,349 customer questions, 1,269 sales objections, and 10,907 follow-up commitments that would otherwise have remained locked inside audio files nobody had time to listen to.

The engineering quality underneath is above average for a product at this stage. The application compiles cleanly, passes its linter, and its two automated test suites — covering the highest-risk scoring logic — pass at 96 of 96 checks. The team has also built an unusual and commercially valuable discipline into the product: **every metric on every screen declares its own data lineage**, labelled as fully real, partially sourced, or demonstration content. Leadership can see, on screen, which numbers are safe to act on.

Two matters require decisions at leadership level, and both are addressable within days rather than months:

1. **Roughly three weeks of completed engineering work — including the entire quality-audit capability — has never been committed to the company's source control system.** It exists only on one workstation. This is the single largest risk in the programme, and it is operational, not technical.
2. **The Quality Audit scorecard is producing unusable scores** because one pass/fail rule ("CM-5") remains undefined by the business. That single undefined rule currently zeroes 78% of scored calls, dragging the average call score to 5.4 out of 100. The engine is correct; the rule it is enforcing has never been agreed.

The dashboard is ready to inform decisions today on customer voice, FAQs, objections, regional demand and follow-up discipline. It is **not yet ready** to be used for agent performance management, and it cannot yet report revenue influence.

---

## 2. Functional Capabilities (What's Working)

Twelve distinct business views are implemented and operating on live data, organised into three areas. All are reachable, filterable and exportable.

### Insights — understanding the market and the customer

| Capability | Business value delivered |
|---|---|
| **Executive Overview** | A single landing view of call volume, coverage, unique customers and sentiment movement, with period-over-period comparison across two full months. |
| **Customer Voice & Sentiment** | Sentiment measured at the opening, middle and close of each call, so leadership can see not just whether a customer was unhappy, but whether the agent turned the call around. Appreciation themes appear on 1,082 calls and dissatisfaction on 838 — with the customer's own words attached as evidence. |
| **FAQs & Knowledge Gaps** | 12,349 real customer questions across 3,325 calls, each verified word-for-word against the recording, graded as answered, partially answered or unanswered — and timed, so we know how long customers waited for an answer. A direct, evidence-backed input to sales training and website content. |
| **Regional Intelligence** | Demand and outcome patterns by city, state and region, including international enquiries, with spelling variants reconciled so a single city is not counted three ways. |
| **Sales & Objections** | 1,269 objections across 907 calls, classified and timestamped to the moment they were raised. Purchase-readiness is scored per call from need fit, stated intent, timeline, authority, budget and next step. Competitor mentions and customer-stated budgets are captured only where the customer actually said them. |

### Performance — managing the sales floor

| Capability | Business value delivered |
|---|---|
| **Agent Quality** | An eight-parameter scorecard across 17 named agents, combined with conversation mechanics measured from the recordings themselves — talk share, interruptions and dead air — available on 6,089 calls. Coaching notes are generated per call from what the agent actually did. |
| **Next-Action Tracker** | 10,907 commitments extracted from what was genuinely promised on calls, each with an owner, a due date and a service-level status. This converts verbal promises into a managed queue. |
| **Call Explorer & Call Detail** | Full search across the corpus, opening into a per-call view with the complete speaker-separated transcript, timestamped, alongside the summary, extracted entities and synchronised audio playback. |
| **Advanced QA** | The 100-point quality scorecard applied to all 6,260 audited calls, with per-criterion evidence, tier banding, and a side-by-side comparison of how scores change when scorecard rules are revised. |
| **Review Sets** | 979 pre-assembled calls grouped into named review scenarios (multi-call customer journeys with and without quotes, plus deliberate outlier cohorts) so quality reviewers work through a curated set rather than a random sample. |

### Operations — governance and trust

| Capability | Business value delivered |
|---|---|
| **Alerts & Escalations** | Automated flags for negative sentiment, unanswered customer questions, overdue commitments and compliance concerns. |
| **Data Quality & Config** | An honest self-audit: transcription confidence bands, integration status for all nine upstream systems, and a twelve-point AI-governance checklist covering PII handling, human correction rights, and the rule that no scoring uses sensitive personal characteristics. |

### Cross-cutting capabilities

- **Role-based access for five roles** (Management, Sales Manager, Service Manager, Quality Team, Agent), enforced at both the navigation and page level. Agents see only their own calls.
- **Saved views** — managers can store and recall their own filter combinations across sessions.
- **CSV export** from the data tables, so findings move into existing reporting workflows without engineering involvement.
- **Data-lineage labelling on 45 distinct metric areas** — 27 fully sourced from real data, 14 partially sourced with the gap named explicitly, and 4 openly marked as demonstration content pending an upstream system. This is a governance strength, and it is why the numbers in this report can be stated with confidence.

---

## 3. Recent Accomplishments

### Shipped and version-controlled (4–5 August 2026)

Seventeen changes were committed over two days by a single engineer, taking the product from nothing to a deployed dashboard:

- **Initial launch of the full call-intelligence dashboard** with all core insight and performance views.
- **Cloud hosting configured**, making the dashboard shareable by link rather than requiring a developer to run it.
- **Self-service usability improvements** — plain-language explanations on every page, an inline "explore mode" replacing an intrusive help pop-up, the total dataset size shown in the header, and metric definitions surfaced directly beside the numbers they describe. These reduce the need for an analyst to sit beside each new user.
- **Accuracy fixes** to the FAQ drill-downs and regional heatmap, ensuring that clicking a headline number returns exactly the calls behind it.
- **A resumable transcription and analysis pipeline for July**, with automatic retry against CRM outages and protection against paying twice for the same analysis. Long jobs now resume where they stopped instead of restarting.

### Built since, but not yet committed (5–27 August 2026)

A substantial second phase has been completed and is running locally. It is materially larger than the committed phase — approximately **13,600 lines of changed and new code across 60+ files** — and includes:

- **The entire Quality Audit capability**: the 100-point scorecard engine, the Advanced QA screen, the per-call audit panel, and scorecard version comparison.
- **The Review Sets capability** and its curated reviewer cohorts.
- **Conversation-dynamics measurement** — speaking pace, interruptions, talk share and dead air measured from timestamps rather than inferred from text. This closes a known blind spot where the system was guessing at delivery and pacing from words alone.
- **A quality-review workbook** that exports audit results for human reviewers and imports their corrections back in.
- **Reconciliation and audit tooling** for CRM data integrity, plus write-back capability to push AI-generated notes into customer records (gated behind explicit approval each time).
- **Windows developer support**, allowing the project to be worked on outside the original macOS environment.

**This work is real, functional and tested — but it is not backed up, not reviewed, and not deployed.** See Risk 1.

---

## 4. Active Development & Risks

Risks are ordered by business exposure.

### Risk 1 — Three weeks of completed work exists in only one place

**Severity: High · Likelihood of loss: Material · Effort to resolve: Hours**

The last commit to the company repository was **5 August**. The local branch is exactly level with the shared repository, confirming that **nothing built in the last 23 days has been saved to source control or pushed to GitHub**. The work lives in a single synced desktop folder on one machine. A disk failure, a sync conflict or a lost laptop erases the entire quality-audit programme.

There is a secondary consequence: because the quality-audit dataset was never committed, **the hosted build would now fail** — the Advanced QA screen references a data file that does not exist in the shared repository. The publicly deployed dashboard therefore reflects the 5 August product, not what the team has actually built.

**Recommendation:** commit and push immediately, and establish a standing expectation of daily commits. This is a process fix, not an engineering project.

### Risk 2 — The quality scorecard cannot yet be used to manage people

**Severity: High · Owner: Business, not engineering**

The audit engine has run against all 6,260 calls and works correctly. The results are nonetheless unusable for performance management:

- **3,399 of 4,342 scored calls (78%) are automatically zeroed** by a single rule, CM-5, which requires the agent to capture the customer's required installation deadline. That rule has never been formally defined.
- The average call score is consequently **5.4 out of 100**, and **4,158 calls sit in the lowest "At Risk" tier**. These figures describe an unresolved definition, not the sales floor.
- The system knows this: **every single audited call is flagged as requiring human review.** The engine is not claiming these scores are final.
- A further **1,918 calls (31%) returned no score at all**, mostly because there was insufficient conversation to assess.

Seven scorecard ambiguities are documented and awaiting sign-off; CM-5 is the one that moves all 100 points. Two competent reviewers scored the same calls differently on 10 of 19 pilot cases. **Until CM-5 is defined by the business, agent scores must not be circulated.**

Notably, the architecture makes this cheap to fix: scoring rules are applied in code, not by the AI model, so **once CM-5 is agreed the entire corpus can be re-scored without re-running any paid analysis.** The decision is the only blocker.

### Risk 3 — Approximately half the known call volume is not yet analysed

**Severity: Medium · Cost-driven**

The dashboard covers 6,253 calls with complete transcription. A further **~5,400 calls remain untranscribed because the speech-to-text vendor's credits are exhausted.** Every insight in the product is therefore drawn from roughly half the available conversations. Restoring coverage is a purchasing decision.

### Risk 4 — The dashboard has outgrown its delivery method

**Severity: Medium · Effort to resolve: Days**

The data is compiled directly into the application, so a user's browser downloads the **entire two-month corpus — roughly 20 MB compressed, 110 MB uncompressed — before the first screen appears.** This is workable for a small internal audience on good connections, but it will not survive a wider rollout or a longer date range. Moving the data behind a lightweight service is the standard remedy and should be scheduled before the user base expands.

### Risk 5 — The dashboard reads but does not write

**Severity: Medium · Blocked on integrations**

Marking a follow-up complete, resolving an alert, or correcting an AI output **changes nothing outside the current browser session and is lost on refresh.** There is no task system, ticketing system or order-management integration connected. Practical consequences:

- Every follow-up whose date has passed shows as overdue. This should be read as *"not confirmed done"*, not as proven failure.
- **Revenue influence cannot be reported.** No CRM stage unambiguously identifies a won order, so the commercial end of the funnel is deliberately left blank rather than estimated. This is the correct call, but it caps what the dashboard can prove about its own value.

### Risk 6 — Data currency is a manual, fragile process

**Severity: Medium**

The dashboard reads a snapshot, refreshed by hand. Two specific fragilities:

- **Audio playback only works on the machine running a local helper service**, and depends on a CRM session credential that expires every few days. The recording provider also deletes recordings after roughly three months, so the oldest calls in the window will lose their audio first.
- The operational log shows the audit pipeline **stalling twice mid-run** (leaving 74 and then 2,014 calls unprocessed) and one analytics stage failing outright. These were recovered, but they confirm the refresh chain needs supervision rather than running unattended.

### Risk 7 — Four known measurement caveats

**Severity: Low-to-Medium · Already disclosed in-product**

To the team's credit these are labelled on screen rather than hidden:

- **Sentiment has no agreed definition.** The AI applies its own reading, and a second sentiment field disagrees with it on 21% of calls. A definition document is awaiting sign-off.
- **Compliance detection is almost certainly under-reporting** — it found breaches on just 2 of 6,253 calls. A zero here should be treated as unverified, not as a clean record.
- **Answer correctness cannot be assessed.** Without an approved product fact sheet and price list, a confidently wrong answer still reads as "answered clearly". Nine specific data items are documented as blocking this.
- **Regional coverage is incomplete** — 2,827 of 6,253 calls (45%) cannot be mapped to a named region because the stored city is unrecognised.

---

## 5. System Health

### Stability: Strong

| Check | Result |
|---|---|
| Production build | **Passes cleanly.** Compiles in 41 seconds with no type errors. |
| Code linting | **Passes.** 7 advisory warnings, zero errors — all cosmetic developer-experience notes, none affecting users. |
| Automated tests | **All pass.** 96 of 96 assertions across two suites. |

### Test coverage: Deep where it matters, absent elsewhere

Testing is deliberately concentrated on the highest-consequence logic, which is the right prioritisation:

- **The scoring engine (47 checks)** verifies tier boundaries, mandatory-item handling, automatic-zero triggers, not-applicable arithmetic, and the rule that an "unknown" judgement forces human review without penalising the agent.
- **Conversation measurement (49 checks)** verifies speaking pace, interruption attribution, and — importantly — the gate that recognises when a "call" is actually a phone left on a desk. Without it, ambient office noise was being graded as a polite conversation.

The gap: **the dashboard interface itself has no automated tests.** Around 4,900 lines of user-facing code, and 41 of the 43 data-pipeline scripts, are verified only by manual inspection. A regression in a chart or filter would not be caught automatically.

### Technical debt: Modest and largely deliberate

The codebase is well-documented and comes with a complete, version-controlled specification set — information architecture, metric definitions, data dictionary, integration map, scoring methodology, alert rules, access model and testing plan — kept alongside the code that implements it. Four items warrant scheduling:

1. **Data delivery architecture** (Risk 4) — the one piece of genuine architectural debt, and the one that constrains growth.
2. **No frontend test coverage** — acceptable at current scale, increasingly risky as more people depend on the numbers.
3. **Single-contributor concentration** — all committed and uncommitted work comes from one engineer. Combined with Risk 1, this is a meaningful continuity exposure. A handover pack and project-context documentation exist, which mitigates but does not remove it.
4. **A stale duplicate of the dashboard is still on disk.** An earlier eleven-page variant of the product occupies 209 MB in the working folder, untracked and continuously syncing to cloud storage. Housekeeping rather than risk, but it should be removed to avoid future confusion over which copy is authoritative.

### Architectural strengths worth protecting

Three decisions are materially better than typical for a product of this age and should survive any future rework:

- **The AI judges; the code scores.** Scoring rules live in tested code rather than in the AI's output, because an AI asked to total its own scorecard occasionally contradicts itself. The commercial payoff is direct: rule changes replay across the entire history at no cost.
- **Nothing is invented.** Names, quotes, dates and CRM values are taken from source systems or recorded as unknown. Evidence quotes are checked word-for-word against the transcript and discarded if they do not match.
- **Limitations are visible in the product**, not buried in documentation.

---

## 6. Recommended Decisions

| # | Decision required | Owner | Urgency |
|---|---|---|---|
| 1 | Commit and push all outstanding work; adopt daily commits | Engineering | **Immediate** |
| 2 | Define scorecard rule CM-5, then re-score the corpus at no cost | Business / Quality | **This week** |
| 3 | Approve replenishment of transcription credits for the remaining ~5,400 calls | Finance | This month |
| 4 | Supply the approved product fact sheet and price ranges | Product | This month |
| 5 | Sign off the sentiment definition currently awaiting review | Business | This month |
| 6 | Schedule the data-delivery rework before broadening the user base | Engineering | Next cycle |
| 7 | Decide whether follow-up actions should write back to a real task system | Operations | Next cycle |

---

*All figures in this report were measured directly from the current data snapshot and repository state on 28 August 2026. Where a capability is incomplete, it is described as incomplete.*
