# SUNROOOF call-review rule book

The single source of truth for how calls are judged. Every rule here came from a
real call the user reviewed and corrected. `scripts/summarize_calls.py` reads this
file at runtime and appends it to the reviewer's instructions, so **adding a rule
here changes the review immediately — no code change needed.**

Working method: a rule is added when the user identifies it on a specific call, and
applied to that one call so it can be checked. The whole corpus is only re-run when
the user says the rule book is complete.

---

## R1 — Technical and company vocabulary is never "jargon"

These stay in English on every call, including Hindi calls. Saying them in Hindi
confuses the customer more, not less. **Never flag:**

> SUNROOOF · wellness · console · GPS · app · remote · catalogue · quotation ·
> serotonin · melatonin · circadian · optics · optic lens · diffuser · nano tech ·
> LED · driver · controller · IP40 · productivity · psychological · hormone ·
> vitamin D · UV · ultraviolet · frequency · sensor · modular · warranty · guarantee

Flag only genuinely difficult English with an easy everyday Hindi equivalent and no
connection to the product — "subsequently", "irrespective", "prerequisite". Rare.

*From: Vanshika Bhardwaj → Aviral Chhabra, where six correct terms were flagged.*

## R2 — Only judge language when the customer actually asked for Hindi

Indians mix Hindi and English constantly. A customer speaking mostly Hindi does
**not** mean they cannot follow English. Raise a language point only on an explicit
signal: they ask for Hindi, they say they do not understand, or they answer an
English opening in Hindi in a way that clearly requests the switch.

*From: Aparna's customer explicitly switched her to Hindi; Aviral never did.*

## R3 — Everyday English inside Hindi is normal speech

"how are you", "sorry", "ok", "thank you", "site", "price", "size", "time" are
ordinary Hinglish. Never strip them out. "Hello Aviral sir, how are you?" is good.

## R4 — Suggested lines must sound like a person, not a script

SUNROOOF is a luxury brand: warm, confident, conversational. Write natural Hinglish
the way people actually speak on the phone.

- ✗ "Ghar mein prakritik roshni ka anubhav deti hai" — stiff, textbook, scripted
- ✓ "ghar mein bilkul natural light jaisa feel aata hai"

Openings are a short exchange, not a monologue: "Hello Viral, kaise hain aap?" →
let them answer → "Vanshika bol rahi hoon Sunrooof se".

## R5 — Health claims: two shapes, only one is wrong

1. **WRONG — flag it.** The product is credited with a medical outcome: "our
   product prevents cancer", "isse bimari nahi hogi".
2. **CORRECT — never flag.** A harmful thing is *absent*, however phrased:
   "ordinary kitchens contain formaldehyde which causes cancer, ours does not",
   "isme woh chemical hai hi nahi", "there is no UV in our light". The customer
   may have raised the topic first.

Also never flag the trained pitch: psychological benefits, mood, stress, sleep and
sleep cycle, focus, productivity, serotonin, melatonin, the circadian explanation,
or that the light filters/blocks harmful rays.

## R6 — A follow-up call is not a first call

24% of calls (1,531) are contact #2 or later. On those:

- **No introduction is expected** — they already introduced themselves.
- **Do not demand repetition** of the value proposition, technical explanation or
  pricing already delivered on an earlier call. Mark those criteria not applicable
  and name the call that covered them.

Contact number comes from the CRM record each call is attached to, ordered by time
(`scripts/build_call_sequence.py`). The earlier calls' summaries are supplied.

*From: Anubhav Singh → Bhartpal Singh Kahlon, marked down for not introducing
himself on his second call in two days.*

## R7 — "End user" must never be said to the customer

"End user" is internal vocabulary for the office, PSMs, SMs and management. It is
not how you speak to the person themselves — it is impersonal and can wound.

The agent still needs to establish the same thing, but must ask it another way:
"Are you the owner of the house?", "Yeh aapka apna ghar hai?", "Aap architect hain
ya ghar aapka apna hai?"

**If the agent says "end user" to the customer, flag it** and give the better
wording. Identifying an architect, builder or contractor by those words is fine —
only "end user" is prohibited.

## R8 — Ask which city the PROJECT is in, not just where the customer lives

A customer can live in one city and be building in another. Asking only "aap kis
city mein based hain?" leaves the project location unknown, which drives everything
downstream — site visits, installation, timelines.

The agent must establish **both**: where the customer is based, and where the
project/site is. If they ask only where the customer lives, **flag it** and suggest:
"Aur sir, jahan sunroof lagwana hai, wo property kis city mein hai?"

*From: an Aparna call where the customer answered "Amritsar" to a based-in question
and the project city was never confirmed.*

---

## Enforced in code, not left to the model

These are checked mechanically in `scripts/summarize_calls.py` and
`scripts/call_quality.py`, because the model got them wrong often enough that a
written instruction was not enough. Listed here so the rule book is the full
picture.

**C1 — A finding must quote the agent, never the customer.** Any finding whose
quote is not something the PSM actually said is dropped. It once raised a CRITICAL
"agreed the product prevents cancer" while quoting a line the transcript labels
`Customer:`.

**C2 — A medical-claim finding needs a disease word in the agent's own quote.**
Otherwise "haan, filter karega" became a cancer claim. Supports R5.

**C3 — "End user" is detected by pattern match over the agent's turns**, and a
coaching point is inserted automatically when found. Supports R7.

**C4 — A call with no consultation is not scored at all.** Callback requests, wrong
numbers and customers who ended it early get conduct feedback and no mark. Scoring
them on a 5-point denominator produced numbers that swung 0 to 40 between identical
runs.

**C5 — N/A is only allowed on Objection Handling and CRM Disposition.** Anywhere
else the model used it to spare a weak call: on one 40-second call it marked 11 of
12 criteria N/A and the call scored 100% GOLD on the one criterion left.

**C6 — A script-read opening takes Criterion 1 to zero**, and not listening
(interrupting, or repeating something the customer already corrected) costs a
10-point red flag. Supports R4.

**C7 — Temperature 0 on every review call.** At the SDK default of 1.0 the same
call re-scored 18.8 points apart on average with 40% of tiers changing.

---

## Known defect, not yet fixed

**Speaker attribution is wrong on roughly 5% of calls.** `agent_speaker_id` treats
whoever mentions the company first as the agent, which breaks when the customer
says "Sunrooof se call aaya tha" first. On those calls the review judges the
customer's words as the agent's. Measured on a 151-call sample against a
brand-frequency test. Fix is to count brand mentions per speaker instead of taking
the first — cheap, local, no LLM. **Needs doing before the full re-run.**

---

## Still open, not yet decided

- Duration or engagement floor below which a call is not scored at all.
- Window-console price range (ceiling is ₹39,000–45,000; window unverified).
- Expected-disposition mapping for the CRM criterion.
