# Call Quality Audit — data we need before the scorecard can run properly

The 100-point PSM scorecard is ready to run against our transcripts. Nine inputs it
expects do not exist anywhere in our current data. This lists each one, what it
blocks, and the format needed.

Items are ordered by how much scoring they unblock. **Items 1–4 are the ones that
matter most** — together they unblock 25 of the 100 points plus two of the five
critical misses.

---

## Priority 1 — Reference data (unblocks 20 points + CM-1)

### 1. Approved product facts
**Blocks:** Criterion 5 – Technical Details (10 pts), CM-1 Miss-sell
**Why:** The scorecard forbids judging technical truth from general knowledge
(Section 3 rule 12). Without an approved fact sheet, every technical claim the PSM
makes is marked `unknown` instead of correct/incorrect, and we cannot detect
miss-selling — which is a critical miss that zeroes the whole call.

**Needed:** confirmation of the values already named in the scorecard, plus anything
else a PSM is expected to state correctly:
- Product life: is 12–15 years current?
- Power consumption: is 0.03 kW/hr current? Is the "lower than a 15W LED in
  Circadian Cycle Mode" comparison still approved?
- Minimum ceiling height: is 9 ft current?
- Console minimum: is 4 consoles current?
- Manufacturing location
- Patent status and history wording
- Project count: the scorecard says "900+" — is that still the approved number?
- Approved wording for health/wellness claims (circadian rhythm, serotonin/melatonin)

**Format:** a simple list of fact → approved value. Plain text or a spreadsheet is fine.

### 2. Approved price ranges
**Blocks:** Criterion 6 – Pricing Communication (10 pts)
**Why:** Criterion 6 has six mandatory sub-points; failing any one scores the whole
criterion zero. We can check whether the PSM quoted a *format* correctly, but not
whether the *numbers* were right.

**Needed:**
- Ceiling console price range per console (scorecard example: ₹39,000–₹45,000 — confirm or update)
- Window console price range per console, stated separately
- Effective date of these ranges, and any earlier ranges with their date windows, since
  we are auditing calls back to May 2026 and must not judge a June call against an
  August price list

### 3. Minimum console quantity chart
**Blocks:** Criterion 6 sub-point 5 (part of the same 10 pts)
**Why:** The scorecard requires coverage-based quantity "according to the chart" and
explicitly forbids inventing chart values.

**Needed:** the actual chart — area or room size → minimum console count.

### 4. WhatsApp handover group creation date
**Blocks:** CM-4 — and this one currently flags **100% of calls for human review**
**Why:** CM-4 fires when a client handover WhatsApp group is created on the same date
the lead was marked RAW quote. The spec says that when this data is missing we must
record `unknown`, and any `unknown` forces `requires_human_review: true` on that call.
So with no source for this field, **every single audited call self-flags for manual
review**, which defeats auditing thousands of calls automatically.

**Needed, per lead:** the WhatsApp handover group creation date, and the date the lead
was marked RAW quote. If neither is tracked in a queryable system, the practical
options are: (a) start recording them, (b) accept universal review flags, or (c)
formally scope CM-4 out of the AI pass and check it separately in CRM.

---

## Priority 1b — A definition, not data: what counts as capturing the deadline (CM-5)

**Blocks:** every auto-zero decision in the entire scorecard.

A 20-call pilot run through two models found that **CM-5 was the only critical
miss that ever fired** — and the two models disagreed on it for **10 of 19 calls**,
which is worse than a coin flip. Because CM-5 zeroes the whole 100 points, that one
judgement swung scores by an average of 33 points and by as much as 71.

The cause is visible in the evidence they cited. The scorecard asks for two
different timelines, and real customers usually volunteer only one:

- **C2.3 (not mandatory):** "Asked when the project will be ready"
- **C2.4 / CM-5 (mandatory, auto-zero):** "captured by when the customer needs
  SUNROOOF installed and ready to use"

Real examples from the pilot, all judged differently by the two models:

| What the customer actually said | Model A | Model B |
|---|---|---|
| "baarish khatam hogi, uske baad construction shuru hoga… chhah mahine toh lage jaayenge" (construction starts after the monsoon, will take a good six months) | deadline captured | **not captured → call zeroed** |
| "another fifteen twenty days… to start that flooring" | deadline captured | unknown |
| *(no timeline quoted at all)* | deadline captured, **no evidence cited** | **not captured → call zeroed** |

**The question for sign-off:** does a project-readiness timeline satisfy CM-5, or
must the PSM separately establish an install-ready deadline? Concretely:

1. Does "construction finishes in six months" count as capturing the deadline?
2. Does an approximate answer ("after the monsoon", "end of the year") count, or is
   a specific month/date required?
3. If the customer genuinely cannot give a date, can the PSM satisfy C2.4 by asking
   properly and recording that — or is the call zeroed regardless of PSM conduct?

Question 3 matters most: as written, a PSM who does everything right scores zero when
the customer simply doesn't know their own timeline. That penalises the agent for the
customer's uncertainty, which is unlikely to be the intent.

Until this is settled, **no agent should be graded on these scores.** A filled-in
worksheet for a human to score the same 20 calls is at
`out/qa_calibration_worksheet.csv`, with the 10 disputed calls listed first and each
model's cited evidence alongside, so a reviewer can resolve the rule against real
examples rather than in the abstract.

## Priority 2 — CRM rules (unblocks 5 points + RF-2)

### 5. Expected disposition mapping
**Blocks:** Criterion 12 – Zoho CRM Disposition (5 pts), RF-2 (−15 red flag)
**Why:** We can read what disposition *was* marked (`Call_Result` in Zoho), but we have
no authorised rule for what *should* have been marked. The scorecard forbids inferring
it. Without this, Criterion 12 is permanently N/A and RF-2 permanently unknown.

**Needed:** the rule connecting call outcome → correct disposition, e.g. "customer
agreed to specialist call → Convert", "customer declined → NI". Plus the rule for what
counts as the correct disposition *date*.

### 6. Disposition date
**Blocks:** Criterion 12 sub-point 2
**Needed:** confirmation of which Zoho field records when the call was disposed. We
currently pull `Call_Result` but no disposition timestamp.

### 7. RAW quote marked date
**Blocks:** CM-4 (see item 4)
**Needed:** which field or system records this.

---

## Priority 3 — Reporting dimensions (no scoring impact, dashboard filters only)

### 8. Org structure per agent
**Blocks:** nothing in the score — these are filter dimensions only.
The scorecard wants filtering by **zone, branch, team, department, queue, country**.
None exist in Zoho Calls, which carries only 38 fields (of which just `Call_Result`
and `Call_Type` are scorecard-relevant).

**Needed:** a mapping of agent/PSM name → team, branch, department, zone. A one-off
spreadsheet is enough; it changes rarely. Without it these filters stay empty (null,
not "Unknown" — the spec forbids substituting a placeholder).

We already have from CRM: call owner, city, state, lead source, campaign, property
type, lead ID, call direction, duration, and call date.

### 9. Evaluator identity convention
**Blocks:** nothing — needs a decision, not data.
The scorecard has `evaluator_id` / `evaluator_name` fields designed for a human QA
auditor. Since the AI is the evaluator, we should record something consistent, e.g.
`evaluator_id: "ai-gpt-4.1-mini"`, `evaluator_name: "Automated QA v1.0"`, so that
later human re-scores are distinguishable from AI ones.

**Needed:** confirmation of that convention, or your preferred alternative.

---

## Summary of impact if nothing is supplied

| Scorecard element | Points | Status without the data |
|---|---|---|
| C5 Technical Details | 10 | Scored on coverage only; accuracy unverifiable |
| C6 Pricing & Console Specs | 10 | Scored on format only; figures unverifiable |
| C12 Zoho CRM Disposition | 5 | Permanently N/A |
| CM-1 Miss-sell | auto-zero | Only blatant cases detectable |
| CM-4 WhatsApp/RAW quote | auto-zero | Permanently unknown → **every call flagged for review** |
| RF-2 Wrong disposition | −15 | Permanently unknown |
| Zone/branch/team/dept/queue filters | — | Empty |

The remaining 75 points — greeting, KYC, value proposition, requirement gathering,
hype/aspiration, objection handling, specialist priming, process clarity, and FOMO —
are fully auditable from the transcript today and need nothing from this list.
