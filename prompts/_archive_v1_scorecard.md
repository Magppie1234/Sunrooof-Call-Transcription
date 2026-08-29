# SUNROOOF PSM Call Quality — Master Prompt (v1, ARCHIVED)

Kept only so the v1-vs-v2 comparison is a real A/B rather than a description of one.
Not used in production. Reconstructed verbatim from the original scorecard supplied
on 2026-08-12, before Sameer's training notes were available.

## Evidence and audit rules

1. Audit the PSM's conduct, not the customer's.
2. Use the transcript for spoken behaviour, CRM metadata for disposition and dates.
3. Every Full/Half/Zero decision needs an exact short quote and timestamp.
4. A complete transcript with no evidence that the PSM covered a required point means
   the point was not met.
5. Mark a criterion N/A only when genuinely not applicable or unassessable.
6. Customer speech alone does not count as the PSM fulfilling a requirement.

## Criterion 1 — Greeting & Opening — 5 points
1. Well-paced, clear, assumptive opening.
2. Upbeat and professional tone.
3. Asked "How did you get to know about us?" or clearly confirmed the lead source.

## Criterion 2 — KYC / Discovery — 5 points
1. Identified the customer type: end-user, architect, or builder.
2. Identified project type and location.
3. Asked when the project will be ready.
4. MANDATORY: captured by when the customer needs SUNROOOF installed and ready to
   use. If this deadline is not captured, also trigger CM-5 and make the entire
   final call score zero.
5. Identified whether the customer is the decision maker.
6. If not, attempted to identify the decision maker.

## Criterion 3 — About SUNROOOF / Value Proposition — 10 points
1. MANDATORY: explained SUNROOOF's uniqueness as the world's first wellness lighting
   technology.
2. MANDATORY: explained at least five distinct key benefits of SUNROOOF.
3. Explained SUNROOOF's history and patent.
4. Mentioned 900+ projects completed, market response, and/or credibility.
5. PROHIBITED: the PSM mentioned "Barton Bach".

## Criterion 4 — Requirement Gathering — 5 points
1. MANDATORY: identified the areas where the customer wants SUNROOOF installed.
2. MANDATORY: identified whether Window or Ceiling consoles are needed.

## Criterion 5 — Technical Details — 10 points
1. Explained console dimensions.
2. Explained design styles and size restrictions.
3. Explained the minimum quantity and why; the scorecard specifies a four-console
   minimum.
4. Explained relevant technology: LEDs, lenses, optics, Nano Tech Diffuser, GPS chip,
   drivers, controllers, and app.
5. Covered ceiling height and drop, plus window protrusion as relevant.
6. Explained product life of 12-15 years.
7. Explained power consumption as 0.03 kW/hr and lower consumption than a 15W LED
   when run in Circadian Cycle Mode.
8. Provided timeline clarity.
9. Explained where the product is manufactured.
10. If needed, clarified that SUNROOOF is not sensor-based; it is preset-based
    technology that works on GPS.

## Criterion 6 — Pricing Communication & Console Specifications — 10 points
1. MANDATORY: gave pricing per console, not only a total package cost.
2. MANDATORY: gave the complete ceiling-console price range per console
   (example ₹39,000-₹45,000).
3. MANDATORY: stated the complete window-console price range separately.
4. MANDATORY: gave console measurements in both formats: feet/inches AND millimetres.
5. MANDATORY: gave coverage-based quantity according to the minimum-console quantity
   chart.
6. MANDATORY/PROHIBITED: avoided discussing GST, installation charges, or remote
   pricing.

## Criterion 7 — Hype & Aspiration Building — 15 points
1. Positioned SUNROOOF as a need, not merely a want.
2. Reiterated health and wellness benefits including circadian rhythm and
   serotonin/melatonin benefits.
3. Positioned longevity and one-time investment value.
4. Explained lower power consumption versus regular lighting.
5. Explained the modular nature of the product.

## Criterion 8 — Objection Handling — 10 points
1. Answered all objections accurately.
2. Reframed price against health/wellness value.
3. Secured the customer's willingness/YES to explore or stretch.
N/A if no objection was raised.

## Criterion 9 — Priming Customer for Specialist — 10 points
1. Built the importance of the Wellness Specialist.
2. Explained that the specialist is a helper, not a seller.
3. Explained that the specialist is the pricing and design authority.
4. Explained the importance of answering the specialist's calls/messages.

## Criterion 10 — Process Clarity — 5 points
1. Clearly explained the next steps: measure, design, cost, order, and install.
2. Gave clarity on timelines and each step.
3. Explained when the specialist will call or message.

## Criterion 11 — FOMO Creation / Urgency — 10 points
1. MANDATORY: described the special package for future projects and price locking
   according to the given timeline, and obtained a YES to explore.
2. Did not use fake deadlines or artificial scarcity.

## Criterion 12 — Zoho CRM Disposition — 5 points
1. Disposed correctly in Zoho CRM using the correct type.
2. Disposed on the correct date.

## Critical misses — any Yes zeroes the call
- CM-1 Miss-sell.
- CM-2 Short Dial.
- CM-3 The PSM mentioned "Barton Bach".
- CM-4 Handover WhatsApp group created on the RAW-quote date.
- CM-5 The PSM did not capture by when the customer needs SUNROOOF installed and
  ready to use during KYC.

## Red flags
RF-1 −15 suggested a single console or two or fewer consoles could work ·
RF-2 −15 wrong CRM disposition · RF-3 −10 decision maker not identified ·
RF-4 −10 timeline vague or not discussed · RF-5 −10 ceiling height/type not verified
(9 ft minimum) · RF-6 −10 artificial urgency · RF-7 −5 mentioned GST, installation
charges or remote pricing.

## Output
Return judgements only under `call_quality_audit`: all 12 criteria with every
sub-point, all 5 critical misses, all 7 red flags, with verbatim quotes and
timestamps.
