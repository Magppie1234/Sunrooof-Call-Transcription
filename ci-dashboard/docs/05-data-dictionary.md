# 5 · Data Dictionary

Canonical types: `src/types/domain.ts`. ⚑ = must come from a live integration (mocked today).

## CallRecord

| Field | Type | Source | Notes |
|---|---|---|---|
| id | string | Telephony ⚑ | `CALL-####` |
| dateTime | ISO string | Telephony ⚑ | |
| direction | inbound \| outbound | Telephony ⚑ | |
| durationSec | number | Telephony ⚑ | |
| customerId / customerName / customerType | string | CRM ⚑ | PII masked per role |
| employeeId | string | Telephony↔HR map ⚑ | joins to Employee (team, manager) |
| region / state / city / pincode | string | **CRM fields only** ⚑ | never inferred from accent/name/language |
| productSeries, leadSource, campaign, crmStage | string | CRM ⚑ | |
| outcome | enum | Disposition + CRM ⚑ | `crm.verified` distinguishes AI-inferred vs CRM-verified |
| connected / meaningful | boolean | Derived | meaningful = connected ∧ >60s |
| transcribed, transcriptionConfidence, diarizationReliable | bool/number | ASR ⚑ | confidence 0–1 |
| language | string | ASR ⚑ | analysed in original language |
| sentiment | SentimentData \| null | AI extraction | opening/mid/closing (−1…1), label, shift, emotions[], unresolvedNegative. **Text-based.** |
| purchaseReadiness | PurchaseReadiness \| null | AI extraction | score + 7 weighted components; null for service calls |
| intent | high/medium/low/none | Derived from PR score | 70/50/30 cut-points |
| customerNeed, budgetMentioned, timelineMentioned | string \| null | AI extraction | null ⇒ displayed "Not mentioned" |
| decisionMaker | yes/no/unknown | AI extraction | "unknown" when not discussed |
| buyingSignals[], crossSell, discountRequested, competitorMentions[] | — | AI extraction | |
| topics[], appreciationThemes[], dissatisfactionThemes[], featureRequests[], expectations[], painPoints[] | string[] | AI extraction | |
| faqs[] | FaqHit[] | AI extraction | category, standardized, originalQuestion, status, responseTimeSec, sentimentAfter, escalationNeeded, t, confidence |
| objections[] | ObjectionHit[] | AI extraction | type, intensity, statement, employeeResponse, technique, resolution, customerReaction, t, confidence |
| quality | QualityScores \| null | AI scoring | 9 parameters + weighted overall + complianceFail (separate) + coachingNote |
| talk | TalkMetrics \| null | ASR diarisation ⚑ | null when diarisation unreliable — metrics then hidden |
| actions[] | NextAction[] | AI + user edits | see below |
| commitments[], risks[], complianceFlags[], entities[] | — | AI extraction | |
| summary | string | AI generation | |
| transcript[] | TranscriptSegment[] | ASR ⚑ | { t (sec), speaker, text } |
| aiConfidence | 0–1 | AI extraction | call-level composite |
| crm | CrmSignals | CRM/OMS ⚑ | opportunityCreated, orderConfirmed, complaintOpen, revenueInfluenced (₹, verified only), verified |
| hasRecording | boolean | Telephony ⚑ | |

## NextAction

id, callId, customerName, action (14-value enum), **source** (`committed` \| `ai_recommended`),
committedBy (employee/customer/null), ownerEmployeeId, priority (P1–P3), dueDate, channel,
reason, transcriptRef (sec), confidence, status (pending/approved/in_progress/completed/rejected),
slaStatus (on_track/due_today/overdue/met/breached), crmTaskLinked ⚑.

## AlertItem

id, severity (critical/high/medium), type, customerName?, callId?, ownerEmployeeId?, reason,
evidence, recommended, deadline, status (open/acknowledged/resolved).

## Employee

id, name, team, manager, role. (Live: HRIS/CRM user directory ⚑.)

## Not invented

Fields this dashboard **requires but does not fabricate** (declared on the Data Quality page):
task-system link state, approved-knowledge-base answers, audio streaming URLs, translation of
multilingual transcripts. These display as "integration required".
