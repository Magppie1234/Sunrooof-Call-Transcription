# Call Quality Scorecard — decisions needed

Everything here is a **judgement call the scorecard doesn't settle**, found by running
it against 20 real calls. These are not missing data (that's in
`MISSING_DATA_REQUEST.md`) — they are places where two careful readers would score
the same call differently, so scores can't be defended until they're settled.

Ordered by how much score they move. **Q1 is the one that matters most.**

---

## Q1. Does a project timeline satisfy CM-5? (moves 100 points)

**The rule:** CM-5 zeroes the entire call if the PSM didn't capture "by when the
customer needs SUNROOOF installed and ready to use."

**The problem:** this was the *only* critical miss that ever fired in the pilot, and
it decided every single zero. Two models reading the same transcripts disagreed on
**10 of 19 calls**. The scorecard asks for two different dates and customers usually
give one:

- C2.3 (not mandatory): "when will the project be ready"
- C2.4 / CM-5 (mandatory, auto-zero): "by when do they need it installed and usable"

Real customer answers from the pilot that got scored both ways:

| Customer said | One reading | Other reading |
|---|---|---|
| "construction starts after the monsoon, will take about six months" | deadline captured | not captured → **0** |
| "another fifteen twenty days to start the flooring" | deadline captured | unclear |
| "possession maybe by Diwali" | deadline captured | not captured → **0** |

**Decide:**
1. Does a project-readiness answer ("ready in six months") satisfy CM-5, or must the
   PSM separately ask when they need it *installed and usable*?
2. Is an approximate answer enough ("after the monsoon", "around Diwali"), or is a
   month/date required?
3. **If the customer genuinely doesn't know their own timeline, and the PSM asks
   properly and records that — is the call still zeroed?** As written, yes. That
   punishes the agent for the customer's uncertainty, which is probably not intended.

---

## Q2. Is Criterion 6 meant to be near-impossible? (moves 10 points on most calls)

C6 has **six mandatory sub-points**, and missing any one scores the whole criterion
zero. In the pilot it scored zero on **15 of 20 calls**, and the misses were scattered
— no single sub-point is the culprit:

| Sub-point | Times missed (of 20) |
|---|---|
| 6.3 window-console price range stated separately | 7 |
| 6.6 avoided GST / installation / remote pricing | 6 |
| 6.4 measurements in BOTH feet-inches AND millimetres | 5 |
| 6.1 price per console, not just package total | 4 |
| 6.5 coverage-based quantity from the chart | 4 |
| 6.2 ceiling-console price range | 2 |

**Decide:** is a near-universal zero here the intended signal (i.e. almost nobody is
doing pricing correctly and that's the finding), or should some of these six be
non-mandatory? 6.4 in particular — is quoting both feet/inches *and* millimetres
genuinely expected on every call?

---

## Q3. Do red-flag deductions mean the same thing on every call? (moves up to 15 points)

Section 8 subtracts red-flag points from a **percentage**. When criteria are N/A the
adjusted maximum shrinks, so the same −15 flag bites differently:

- All 12 criteria apply → −15 is 15% of the score
- Objection Handling and CRM Disposition both N/A (adjusted max 85) → −15 is 17.6%

**Decide:** intended, or should deductions scale with the adjusted maximum? I've
implemented it exactly as written; this only needs changing if the effect surprises you.

---

## Q4. Who counts as the PSM on a call with more than two speakers?

The scorecard says to audit the PSM's conduct only. Transcripts are machine-diarised
and the speaker labelled "agent" is inferred, not certain. On transferred or
three-party calls the wrong person's words can be attributed to the PSM.

**Decide:** should calls with a transfer or a third speaker be excluded from scoring
and routed to human review instead?

---

## Q5. Should very short calls be scored at all?

A 40-second call cannot demonstrate value proposition, technical detail, pricing,
specialist priming or FOMO. Scored as written, it fails almost everything — but the
agent may have done nothing wrong if the customer hung up.

CM-2 ("Short Dial") exists but explicitly must not fire *just* because a call is
short. So a short call currently scores near zero without CM-2 firing.

**Decide:** below what duration should a call be marked not-scoreable rather than
scored zero? (For reference, we already skip anything under 30 seconds for
transcription.)

---

## Q6. What is "at least five distinct key benefits"? (C3, gates 10 points)

C3.2 is mandatory and requires five distinct benefits. "Better sleep", "improves
circadian rhythm" and "boosts serotonin" could be counted as three benefits or one.

**Decide:** an approved list of the benefits that count, so the threshold is
consistent. This overlaps with the approved-product-facts request.

---

## Q7. Which sentiment definition applies?

Separately from this scorecard, the pipeline already labels customer sentiment with
**no rubric given to the model at all**. A proposed definition is in
`docs/sentiment_definition_for_review.md` awaiting sign-off. The audit's qualitative
section will reference sentiment too, so both should use the same definition.

**Decide:** approve or amend that document, and I'll apply it to both passes together.

---

## What happens when you answer

Structural changes — whether CM-5 auto-zeroes, whether a C6 sub-point is mandatory,
how deductions are applied, duration cut-offs — can be **re-applied to already-audited
calls without paying for the LLM again**, because the model's per-sub-point judgements
and evidence are stored in the `call_quality_audit` column and the scoring is computed
separately in `scripts/call_quality.py`. I just re-run the scorer over stored data.

Changes to *what the model should look for* (Q1's evidence question, Q6's benefit
list) do need a re-run, because they change the judgement itself, not the arithmetic.
