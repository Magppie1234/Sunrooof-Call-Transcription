# Customer Sentiment — What Actually Decides Positive / Neutral / Negative

**Prepared for review and sign-off. Covers 5,028 real Sunrooof calls (Jun–Jul 2026) processed by the current pipeline.**

The purpose of this document is to expose, without softening, the exact basis on which every call in the dashboard is labelled Positive, Neutral or Negative — so that a decision can be taken on whether that basis is the one the business wants.

**Headline finding: no definition of "positive", "neutral" or "negative" is currently given to the model anywhere in the pipeline.** The labels are produced from the model's own general-purpose intuition, then converted to a label by a fixed arithmetic rule. Sections 1–4 document what exists today; Section 5 shows where it visibly diverges from what a human QA would say; Section 6 is a proposed rubric for approval.

---

## 1. There are two different sentiment fields, produced by two different passes

This matters because they do not always agree, and only one of them reaches the dashboard.

| | Field A — `customer_sentiment` | Field B — segmented sentiment |
| --- | --- | --- |
| Produced in | `scripts/summarize_calls.py` (summary pass) | `scripts/enrich_for_ci.py` (enrichment pass) |
| Form | one word: positive / neutral / negative | three numbers: opening, mid, closing, each −1.00 to +1.00 |
| Instruction given to the model | **none — see §2** | one sentence — see §3 |
| Where it is used | written into the Zoho CRM call note | **every sentiment figure on the dashboard** |
| Model | GPT‑4.1 mini | GPT‑4.1 mini |

The Positive/Neutral/Negative percentages leadership sees on the dashboard come from **Field B**, not Field A. Field A is what a salesperson reads in Zoho. The two are generated independently from the same transcript and are never reconciled against each other.

---

## 2. Field A: the model is given no definition at all

The summary pass sends the model a strict, detailed instruction sheet — nine numbered rules covering names, evidence quoting, budgets, scorecards. Sentiment is not one of them. The field is declared as nothing more than a list of permitted answers:

```python
customer_sentiment: Literal["positive", "neutral", "negative"]
```

Every neighbouring field carries an explicit definition. For comparison, the field right below it does:

```python
agent_politeness: int = Field(description="1 (rude) to 5 (very polite)")
```

Sentiment carries none. The model is told *which three words it may output* and nothing whatsoever about *when to use each*. The label therefore reflects GPT‑4.1 mini's generic training-data notion of sentiment, applied to a romanised Hinglish sales transcript — not any Sunrooof standard.

---

## 3. Field B: one sentence of guidance, then arithmetic

The enrichment pass gives the model exactly one instruction about sentiment:

> "Sentiment is about the CUSTOMER's feelings, judged from words alone (no voice-tone claims). Score the first/middle/final third separately."

Two things are defined here and are worth keeping: sentiment is the **customer's** feeling, not the agent's or the call's; and it is judged **from words only** — the pipeline reads a text transcript and cannot hear tone, so it is explicitly barred from claiming it can. Neither of these is stated for Field A.

What is *not* defined: what any number on the −1 to +1 scale means. There is no anchor for what earns +0.7 versus +0.3, and no rule for what counts as negative rather than merely unenthusiastic.

The three numbers are then converted to the final label by fixed code, with no model involvement:

```
weighted = (opening + mid + closing × 1.4) ÷ 3.4      # build_ci_dataset.py

label =  positive   if weighted >  +0.15
         negative   if weighted <  −0.15
         neutral    otherwise
```

Two business rules are embedded in that formula and have never been formally approved:

1. **The end of the call counts 40% more than the start.** A customer who begins annoyed and ends satisfied is Positive. This is defensible for a sales call — but it is a choice.
2. **The neutral band is ±0.15**, i.e. narrow. A weighted score of 0.16 is Positive; 0.14 is Neutral. In the current data, **35% of calls sit within 0.15 of a boundary** — a third of all labels could flip on a small change to either the threshold or the model's estimate.

Alongside the label the model also returns, from a fixed list, the customer emotions it observed — *frustration, confusion, hesitation, urgency, trust, interest, satisfaction* — and a flag, `unresolved_negative`, meaning the call ended with the customer still unhappy and nothing resolved. These are recorded but do **not** influence the Positive/Neutral/Negative label.

---

## 4. What the model actually does, measured on 5,011 calls

Since no rubric was given, the operative rubric is whatever the model settled on. Measured from the output:

**Label distribution**

| Label | Calls | Share |
| --- | --- | --- |
| Neutral | 2,889 | 57.7% |
| Positive | 1,641 | 32.7% |
| Negative | 481 | 9.6% |

**Neutral is overwhelmingly a non-answer, not a judgement.** Of the 15,033 individual thirds scored, **51.9% were scored exactly 0.00**. 1,749 calls (35% of the book) were scored 0.00 on all three thirds — the model declining to commit rather than assessing a genuinely balanced call. 171 of those are calls longer than two minutes, and 15 run over five minutes; 229 of them ended as *Interested — follow-up* and 17 as *Quotation requested*, so real conversations with real outcomes are being scored as flat zero.

**The scale is far coarser than it looks.** Although the field permits any value from −1 to +1, only 22 distinct values were ever used, clustered on multiples of 0.1. Reporting to two decimal places implies a precision the underlying judgement does not have.

**The model is markedly more willing to say positive than negative.** 38.9% of thirds were scored above zero against 9.1% below. Displeasure has to be considerably more explicit than enthusiasm before it registers.

**Sentiment tracks call outcome closely** — which is reassuring for face validity, but also means it is only partly independent information:

| Outcome | n | Positive | Neutral | Negative |
| --- | --- | --- | --- | --- |
| Demo scheduled | 6 | 100% | 0% | 0% |
| Site visit scheduled | 67 | 91% | 8% | 0% |
| Quotation requested | 399 | 76% | 23% | 0% |
| Interested — follow-up | 1,789 | 57% | 42% | 0% |
| Callback requested | 1,260 | 18% | 78% | 2% |
| No requirement | 155 | 0% | 76% | 23% |
| Not interested | 826 | 0% | 51% | 48% |
| Not connected | 503 | 0% | 98% | 1% |

**Sentiment is confounded with call length.** Median duration by label: Positive 269s, Neutral 61s, Negative 50s. Short calls are being labelled Neutral largely because they are short — including the 503 unconnected calls (98% Neutral), where there is no customer to have a sentiment at all.

---

## 5. Where this diverges from what a human QA would say

These are not hypothetical risks; each is present in the current dataset.

**a) Unconnected calls are counted as Neutral.** 503 calls where no conversation took place carry a Neutral label and are pooled into the reported percentages. A human QA would mark these Not Applicable. They currently inflate Neutral by roughly 10 points.

**b) Every confirmed order is labelled Neutral.** All five calls with outcome *Order confirmed* scored 0.00 / 0.00 / 0.00. A customer who has just placed an order is not neutral. This is the clearest illustration that a 0.00 means "not assessed", not "balanced".

**c) The system contradicts itself on 147 calls.** 147 calls are flagged `unresolved_negative` — the model's own judgement that the call ended with the customer still negative and nothing resolved — yet carry a Neutral or (in one case) Positive overall label, because the arithmetic never consults that flag.

**d) Observed frustration does not guarantee a negative label.** Frustration was recorded on 167 calls; 43 of them are labelled Neutral.

**e) Politeness is read as satisfaction.** With no rubric and a text-only view, a customer who says "haan haan theek hai, bhejiye" to end a call politely reads as mild positive. A human QA hearing the tone, or reading the brush-off in context, would often call it neutral or negative. This is the systematic bias behind the 39% vs 9% positive/negative asymmetry.

**f) Sarcasm, resigned agreement and polite refusal are not recoverable from text.** The pipeline is explicitly told it cannot claim tone. Any rubric approved should be read as a rubric for *words*, not for *how the customer sounded*.

---

## 6. Proposed rubric for approval

The following is a draft, not current behaviour. Nothing here is in force. It is written so it can be amended and then implemented literally — once approved, the wording goes into the model's instructions and into the code, and the calls are re-scored against it.

**Scope rule (proposed):** calls with no connected conversation — voicemail, IVR, no answer, wrong number — are labelled **Not Applicable** and excluded from all sentiment percentages. They are not Neutral.

| Label | Applies when | Typical markers |
| --- | --- | --- |
| **Positive** | The customer expresses interest, approval or satisfaction in their own words, or commits to a concrete next step. | Asks for a quote, price or catalogue; agrees to a visit or demo; asks unprompted product questions; praises the product or service; confirms an order. |
| **Neutral** | The customer engages without expressing either approval or displeasure — information exchanged, decision deferred, or the call too brief to read. | Answers questions factually; "send me details"; "call me later"; asks to be called back with no reason given. |
| **Negative** | The customer expresses displeasure, rejection or distrust, **or** the call ends with a complaint or concern unresolved. | Declines the offer; complains about price, quality or previous service; asks not to be called again; expresses irritation at being contacted; raises an objection the agent never addresses. |

**Tie-breaking rules (proposed, for decision):**

1. **Weight the end of the call.** Where sentiment shifts, the closing state decides. *(This is current behaviour, at a 1.4× weight — confirm or change.)*
2. **Unresolved negative overrides.** If the call ends with the customer still unhappy and nothing resolved, the label is Negative regardless of the score. *(Would reclassify the 147 calls in §5c.)*
3. **Confirmed outcome overrides.** An order confirmed, a demo booked or a site visit scheduled is Positive. A flat refusal is Negative. *(Would fix §5b.)*
4. **Politeness alone is not positive.** Courteous acknowledgement without interest is Neutral. *(Would correct the positive skew in §5e.)*
5. **Neutral must be earned.** The model should be required to justify a neutral label with a transcript quote, exactly as it must for budget and timeline today. *(Would attack the 1,749 default zeros in §4.)*

**Decisions requested:**

- Approve, amend or replace the three definitions above.
- Confirm whether unconnected calls should be excluded from the reported percentages.
- Confirm whether rules 2 and 3 should override the model's own reading.
- Confirm the closing-weighting (1.4×) and the ±0.15 neutral band, or set different values.

Once these are settled, the definitions will be added to both passes so Field A and Field B share one standard, and a sample of calls will be scored by a human QA and by the pipeline in parallel to measure agreement against the approved rubric.

---

### Sources

Every figure above is computed from the pipeline's own output, not estimated.

| Claim | Source |
| --- | --- |
| Field A has no definition | `scripts/summarize_calls.py:158` |
| Field A instruction sheet | `scripts/summarize_calls.py:263-304` |
| Field B instruction sentence | `scripts/enrich_for_ci.py:180` |
| Score-to-label formula and thresholds | `scripts/build_ci_dataset.py:226`, `:511-514` |
| Emotion list and unresolved-negative flag | `scripts/enrich_for_ci.py:63`, `:86` |
| All distributions, cross-tabs and contradictions | `ci-dashboard/src/data/real/dataset.json` (5,028 calls), `out/ci_enrichment/*.json` (5,011 files) |
