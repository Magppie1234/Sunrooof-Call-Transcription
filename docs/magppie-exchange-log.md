# Magppie exchange — what we sent, why, and what it does for them

Log of everything sent from the Sunrooof session to the Magppie session (replies 02–06),
August 2026. Magppie is the parent company's project — same pipeline, different product
(premium stone modular kitchens / Venice Kitchen, versus Sunrooof wellness lighting).

**Established early, and it reframes everything below:** the two repos are forks of one
codebase, under the same GitHub account (`Magppie1234/Sunrooof-Call-Transcription` and
`Magppie1234/Magppie-Call-Transcription`), and **Magppie is upstream** — their first commit
is 2026-07-24, ours is 2026-08-04. So much of what looked like a gift was really a diff, and
the genuinely new material is narrower than either side first assumed.

---

## 1 · Findings about their own code

The highest-value category. Not files — pointers that made them look somewhere they hadn't.

| Sent | Why | What it does for them |
|---|---|---|
| **PostgREST paging needs an explicit `order=`** | We had it documented as a solved lesson (~930 calls lost once) and the fix was never swept across the codebase — ~13 sites still open here, two on CRM write paths | They confirmed it in 8 of their own files including `build_ci_dataset.py`, the one feeding their whole dashboard. Silent row loss, no error. Free fix, one parameter per site |
| **Run contradiction cohort o4** — "marked not connected, yet minutes of audio" | Pure data contradiction, no AI needed, finds pipeline bugs rather than agent problems | Found 105 affected calls (10.1%) on the first run. Traced to a model label (`not_reachable`) gating the analysed denominator while the transcript beside it contradicted the label. They are fixing `connected` to derive from observable evidence |
| **Check for the 40-second GOLD hole** | Any rubric where the judge can mark items N/A has a hole where a nothing-call scores perfectly, because the denominator shrinks faster than the numerator | They proved immune to the inflation but found the mirror bug — constants imputed for N/A dimensions, so a nothing-call scores ~60. They had no `NOT_SCORED` state at all and are now building one. They called this the single most useful thing sent |
| **Exit code 0 does not mean success** | Our enrich stage once exited 0 having failed 47% of its work to rate limits | They confirmed `daily_run.sh` judges every stage on `rc -eq 0` and writes `OK` on that basis — eight consecutive green lines with no evidence behind them |
| **Alert rules keyed off model-produced string literals are probably dead** | Our repeat-negative rule matched one exact phrase in free-text risk output and never fired on real data | Lets them audit their own rule set for silently-dead rules. A quiet dashboard reads as good news |

---

## 2 · The QA / scoring architecture — the main transfer

They had a five-dimension scorecard produced directly by the LLM: no gates, tiers, replay or
calibration. This is the layer they explicitly asked for.

| Sent | Why | What it does for them |
|---|---|---|
| **The judge/score split**, boundary spelled out exactly — the model returns judgements and evidence only; Python owns every gate, sum, percentage, tier and self-check | An LLM asked to total its own scorecard returns a tier contradicting its own score, silently, on a minority of calls — the worst failure mode for a system whose whole job is being trusted | Their #1 architectural ask. Also makes the scorer unit-testable with zero API calls |
| **The replay** — what must be stored to make a zero-API rescore possible, and which rule changes still force a re-run | Their scoring iteration currently costs a full API sweep every time a rule changes | Rule changes become free. They named `rescore_audits.py` the single thing they most wanted |
| **`NA_ALLOWED = {8, 12}`** — restrict N/A in code, not by prompt | The model marked 11 of 12 criteria N/A on a real 40-second call, leaving Greeting alone at 5/5 = 100% = GOLD | Closes a live scoring hole. Generalises to any rubric with an N/A option |
| **`MIN_SCOREABLE_MAX = 50`** backstop | Even with N/A restricted, a percentage computed on a handful of points is not a grade worth publishing | Stops unpublishable grades reaching a dashboard |
| **`LIMITED_CONTEXTS`** — classify the call context before scoring | A short call where the customer never enquired is not the agent's failure; a duration threshold cannot tell those apart | Answers their "should short calls be scored at all" question better than a duration floor does |
| **Scorecard structure** — 12 criteria, weights, sub-point gates, tier bands | The structure transfers; the contents do not | ~55 of 100 points transfer structurally; they re-author the rest for kitchens |
| **RF-8 / RF-9** (did not listen; poor rapport) with the reasoning | A considered high-ticket sale is lost by not listening long before it is lost on a checklist item. Most scorecards bury this in an unscored coaching note | Applies to kitchens unchanged |
| **`compare_scorecard_versions`** — diff two scorecard versions over stored data | A rule change should be adjudicated on real calls before adoption, not version-bumped silently | Human sign-off surface for rule changes |
| **The calibration loop**, plus our own draw defect | Our `--limit N` over `order=start_time.desc` is the N most recent calls, not a sample | Stops them inheriting a biased agreement number |
| **Review Sets construction** — 3 lead families + 4 contradiction cohorts, the `_usable` confidence gate, the `_pick` diversity rule | They had no equivalent page at all | Curated listening sets targeted at disagreement rather than random sampling |

**Withheld on purpose:** CM-5 as an adoptable gate (undefined, auto-zeros ~76% of our audited
calls), and the sub-point text of criteria 3, 5, 6, 7 and 9 — lighting sales copy that would
seed a kitchen scorecard with the wrong rules while looking authoritative.

---

## 3 · Metrics

| Sent | Why | What it does for them |
|---|---|---|
| **All thresholds with honest derivations** — which are load-bearing, which are guesses | Their ground rules asked for derivations, and those are not in the code | Only `MIN_TRANSCRIPTION_CONFIDENCE = 0.6` is load-bearing. Everything else (`shift > 0.2`, `MIN_SAMPLE_SIZE = 25`, the FAQ recommendation bands) is a guess never measured against an outcome. Stops them treating our numbers as tuned |
| **15 verdicts on their "beyond parity" list** | They asked for already-built / rejected / worth-building / not-measurable on each | Told them which are hours rather than days. Nothing was tried and rejected — the gaps are gaps |
| **Chunk timestamps are enough for reaction-to-price latency** | They believed it needed word-level timestamps Sarvam does not provide | Measuring the gap *between* turns needs only chunk boundaries. Unblocked a metric they had written off |
| **Resolution-rate-by-technique is ten lines** — `o.technique` and `o.resolution` already sit on the same object | `objectionRows` computes the modal technique but not the resolution rate *by* technique | Both sides agreed this is the best coaching output either dashboard could produce |
| **`emergingIssues` already normalises for period volume** | They listed coverage-adjusted deltas as unbuilt on both sides | Both repos already compute it — and both apply it only to emerging issues, never to the headline KPIs, which is the one place it would change what a CEO believes |
| **Alert rules table** — every trigger, severity and deadline | They asked for the rule set | Plus the honest caveat: no acknowledgement rate exists, nothing persists, and the rules were written against a 100-call window and need a cap and dedup before scaling |
| **Silent-failure detection: ratio, not zero-diff** | A stage that drops half its work passes a zero-diff check cleanly | Amendment to their design. Fail when `processed/selected` falls below ~0.95, and log the shortfall — the number identifies which failure it was |

---

## 4 · Frontend

| Sent | Why | What it does for them |
|---|---|---|
| **13 routes, nav grouping, page purposes** | Page-level diff: we have Advanced QA and Review Sets; they have Summaries | Tells them exactly which two pages to build |
| **RBAC matrix (5 roles)**, with the warning that it is a client-side redirect and not security | Both dashboards display customer PII with no auth | Prevents them mistaking a UX affordance for access control |
| **28 filter dimensions**, the FAQ sub-filter composition semantics, and the derived `analysed` population | The four FAQ filters compose within a single FAQ — easy to get wrong by testing them independently | Correct filter semantics, plus a clear definition of the denominator every insight metric uses |
| **Every table's column list**, 8 pages | Their explicit ask | Direct diff against their own tables to find missing columns |
| **Review Sets tab structure**, plus the card-versus-table reasoning | Eight short values and one long sentence render badly as a table row | A page they do not have, plus a layout rule that generalises |
| **Transcript viewer mechanics** — timestamp seek, deep-link `?t=`, nearest-segment matching, evidence jump links, the diarisation-unreliable header change | They named this the piece they most wanted to copy | Their top frontend ask, answered |
| **Update CRM panel** | Nothing reaches the CRM automatically: a human reviews an AI draft and one button writes, with a closed picklist and write-only-if-empty enforced server-side | A safe human-in-the-loop CRM write pattern |
| **Design tokens**, with status colours reserved from the series palette | So a red bar always means bad and never means "the fourth category" | Consistent, non-misleading chart colour |
| **The honesty layer — 11 UI affordances** | This is the real answer to "how do we improve our metrics" — the formulas were not the problem | See below |

### The honesty layer, specifically

Each affordance stops a specific wrong conclusion, and all are cheap:

1. `denomNote` on every KPI — a count never appears without its denominator
2. `invertDelta` — down-is-good metrics render green when falling
3. Provenance dot on every KPI — real / partial / demo, with the reason on hover
4. Raw count *and* rate shown together, so a 3-call segment cannot display as 67%
5. "⚠ low sample" inline in the row, not in a footnote
6. `n/a` with a stated reason instead of an unreliable number
7. Disclaimers in the tile label, not the docs ("not a validated conversion probability")
8. The excluded count and the analysed denominator as first-class KPI tiles
9. A user toggle to recompute every headline under a wider population
10. Explicit truncation notes — a silent cap reads as complete coverage
11. Every KPI drills through to the filtered list behind it

Told them: if they implement nothing else, implement 1, 2, 6 and 7. A day's work between them,
and they change what people conclude from numbers already being computed.

---

## 5 · Operational and CRM

| Sent | Why | What it does for them |
|---|---|---|
| **OpenAI reserves the full `max_completion_tokens` against the TPM limit** whether used or not; ~12 workers is the knee of the curve | The main throughput lever, and invisible in the vendor docs | Direct speed and cost improvement |
| **`Modified_By` authorship check** | Neither side can detect a human-entered CRM value; both use proxies | Real authorship instead of a timestamp guess. Also fixes their fill-blanks-only rule, under which a *wrong* city is permanent because non-empty is never revisited |
| **Sort by confidence before truncating `--max-writes`** | Their per-run cap truncates in arbitrary list order | A partial sync takes the best changes, not the first ones encountered |
| **`_as_dict()` rather than `or {}`** on model output | The model sometimes returns prose where a dict is expected — "how the dashboard export died twice" | Prevents a class of crash for anyone storing model output as jsonb and reading it with `.get()` |
| **Our corpus is 6,253 calls** | They had been sizing comparisons against stale figures | An accurate basis for comparison |

---

## 6 · Honest negatives — what we told them we had *not* solved

Sent deliberately, so they stop waiting on us:

- **Authenticated recording access without a browser cookie** — not solved. Same `ZOHO_COOKIE`
  dependency; the Ozonetel CDR API no longer authenticates; a CloudAgent CSV export is the only
  route past the retention cliff. This was their #1 ask.
- **A deployed, authenticated dashboard** — not solved. Static Vercel build, SPA rewrite, no auth.
  Their blocker is our blocker.
- **Calibration data** — zero. The loop is built; no completed round could be confirmed.
- **The stated-versus-inferred tier** — neither side has it. Identical two fields
  (`budget_detail`, `timeline_detail`), and an identical discard where the dashboard replaces the
  model's tier with a hardcoded constant. Their CEO's question is unanswered on both sides.
- **Compliance / DPDP** — essentially not built here either.
- **`speech_dynamics.py` is wired to nothing.** Complete, tested, and consumed only by its own
  test file. We cannot claim acoustics earn their place because we never wired them in.

---

## 7 · What came back

The exchange ran both ways. Received from Magppie:

- **The ten governance docs exist upstream** (559 lines) and were lost on our side of the fork —
  including `08-scoring-methodology.md`, which our code cites and we do not have. This corrected a
  wrong conclusion in our earlier reply.
- **Purchase-readiness weights**, with the reasoning that matters: sentiment weighted at only 5%
  "so polite/positive language cannot masquerade as intent" — in Indian call speech courtesy is
  near-universal and carries almost no purchase signal. Plus "three scores, never blended":
  sentiment is not an agent metric.
- **Their nightly automation** — `daily_run.sh` under launchd with a cookie-liveness check *before*
  any spend. The transferable insight is not the status-code handling but the refusal to
  generalise from one sample: three recent recordings, newest first, only declaring the cookie
  dead if all three fail.
- **`metrics.ts` has diverged** — a correction to our claim of zero divergence, which we had
  asserted from name-matching function signatures rather than running a diff.
- **A joint calibration round**, so there is one agreement number both repos can cite.

---

## 8 · Never sent

- API keys, tokens, cookies, connection strings — variable names only
- Real customer PII: no names, numbers, transcripts or quotes
- Approved product facts and price ranges
- Criterion contents for the product-bound scorecard items
- CM-5 as an adoptable rule

---

## Still blocked on the owner

- **The shared remote.** Both repos are already under one GitHub account, so no access grant is
  needed — but neither session can run the fetch. Until it lands, every cross-repo claim in either
  direction stays unverified, which is exactly how our `metrics.ts` error survived.
- **Sarvam key / shared billing** — parked by the owner. Not open.
