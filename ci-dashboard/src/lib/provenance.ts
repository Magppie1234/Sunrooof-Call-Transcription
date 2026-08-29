/**
 * Feature-level data provenance.
 *
 * Every insight surface declares where its numbers come from, so the UI can be
 * honest about what is real Sunrooof data and what is still demo content:
 *
 *   real    — computed from live Zoho calls + Sarvam transcripts + LLM extraction
 *   partial — real data, but a named part of the feature has no source yet
 *   demo    — no real source exists; the mock generator still supplies this
 *
 * Every number quoted below was measured against the current snapshot:
 * 6,253 calls, 1 June – 31 July 2026 (June 1,238 · July 5,015), all of them
 * transcribed. Keep this list in sync with what the pages render. `note` is
 * shown on hover and in the Data Quality coverage table.
 */
export type ProvStatus = 'real' | 'partial' | 'demo';

export interface ProvEntry {
  status: ProvStatus;
  note: string;
}

export const PROVENANCE: Record<string, ProvEntry> = {
  // ── Volumes & coverage ────────────────────────────────────────────────
  'kpi.volume': { status: 'real', note: 'Call count, duration and direction from Sunrooof’s Zoho CRM Calls module — 6,253 calls across June and July 2026.' },
  'kpi.coverage': { status: 'real', note: 'Transcription coverage: all 6,253 calls in this snapshot have a Sarvam Saaras v3 transcript stored. Roughly 5,400 further calls remain untranscribed because Sarvam credits are exhausted, and are not in this dataset at all.' },
  'kpi.customers': { status: 'real', note: 'Unique customers from the Zoho Lead/Contact linked to each call — every call in the snapshot resolves to a customer record.' },
  'kpi.meaningful': { status: 'real', note: 'Connected, longer than 60s, and the customer actually spoke — decided from real diarisation, not assumed. 3,751 of 6,253 calls (60%) qualify.' },

  // ── Sentiment & voice of customer ─────────────────────────────────────
  'sentiment.overall': { status: 'partial', note: 'Text-based sentiment extracted per call by gpt-4.1-mini from the real transcript, scored on 6,249 of 6,253 calls. Partial because no definition of positive/neutral/negative is given to the model — the labels come from its own reading, and a rubric is pending sign-off (docs/sentiment_definition_for_review.md). A second, independent sentiment field is written to the Zoho note and disagrees with this one on 21% of calls.' },
  'sentiment.journey': { status: 'real', note: 'Opening/mid/closing thirds scored separately on each real transcript; shift = closing − opening. The closing third is weighted 1.4× when the overall label is computed.' },
  'sentiment.emotions': { status: 'real', note: 'Emotions inferred from transcript wording only. No voice-tone or acoustic analysis is performed, so anger conveyed purely by tone is not captured.' },
  'voc.themes': { status: 'real', note: 'Appreciation, dissatisfaction, expectations and pain points extracted from real customer speech. Most calls legitimately carry none — dissatisfaction themes appear on 838 calls, appreciation on 1,082.' },
  'voc.featureRequests': { status: 'real', note: 'Feature requests taken from what customers actually asked for on the call — present on 499 calls.' },

  // ── FAQs ──────────────────────────────────────────────────────────────
  'faq.questions': { status: 'real', note: '12,349 real customer questions across 3,325 calls — each kept only when a verbatim transcript quote could be verified, so invented questions are dropped rather than shown.' },
  'faq.answerQuality': { status: 'real', note: 'Answered / partial / unanswered judged against what the agent actually said in the transcript.' },
  'faq.responseTime': { status: 'real', note: 'Measured from Sarvam word timestamps: end of the customer’s question → start of the agent’s next turn.' },
  'faq.category': { status: 'partial', note: 'The questions are real, but they are mapped onto this dashboard’s fixed 16-category taxonomy. Sunrooof-specific themes such as “showroom / experience-centre visit” and “company info” have no exact bucket and land on the nearest one.' },
  'faq.accuracy': { status: 'demo', note: 'Answer *correctness* cannot be assessed: Sunrooof has no approved knowledge base to check answers against. Only relevance and completeness are measured — a confidently wrong answer would still read as “answered clearly”. Unblocking this needs the approved product facts and price ranges listed in prompts/MISSING_DATA_REQUEST.md.' },

  // ── Regional ──────────────────────────────────────────────────────────
  'region.geo': { status: 'partial', note: 'City resolved from the linked Zoho Lead on 6,227 of 6,253 calls, but only 3,426 map to a named region — the remaining 2,827 sit in “Unknown” because the stored city is not one this dashboard’s lookup recognises. Spelling variants (Bangaluru/Bengaluru, NewDelhi) are normalised, and overseas enquiries (Dubai, Abu Dhabi) bucket to International rather than being dropped.' },

  // ── Sales & objections ────────────────────────────────────────────────
  'sales.readiness': { status: 'real', note: 'Purchase-readiness sub-scores extracted per call and weighted per the documented methodology (need fit 25%, explicit intent 20%, timeline 15%, next step 15%, authority 10%, budget 10%, sentiment 5%). Sub-scores are 0 where the topic never came up, rather than guessed.' },
  'sales.objections': { status: 'real', note: '1,269 objections detected across 907 calls, classified into the dashboard taxonomy with the customer’s own words kept as evidence. Each is timestamped by matching that quote back to the diarised turn it was said in; objections whose quote cannot be located show no timestamp rather than defaulting to the start of the call.' },
  'sales.competitors': { status: 'real', note: 'Competitor names only where the customer actually named one on the call — 63 calls.' },
  'sales.budget': { status: 'real', note: 'Budget and timeline recorded only when the customer stated them — the agent’s quoted console price is deliberately not counted as the customer’s budget. Budget appears on 56 calls, timeline on 1,135.' },
  'sales.funnelCrm': { status: 'partial', note: 'Lead stage is real Zoho data on 5,543 of 6,253 calls. “Opportunity created” counts leads that reached Raw Quote or beyond (Raw Quote, Raw, Drawings Received, Closure). The won-order end of the funnel is still not real: no stage in Sunrooof’s vocabulary unambiguously means a won order, so order counts and influenced revenue have no source and are not displayed.' },

  // ── Agent quality ─────────────────────────────────────────────────────
  'agent.quality': { status: 'real', note: 'Eight-parameter scorecard from the real per-call scorecard plus transcript-derived dimensions, across 17 real agents.' },
  'agent.talk': { status: 'real', note: 'Talk ratio from diarisation; interruptions and longest silence measured from real Sarvam word timestamps. 6,089 of 6,253 calls carry these — 164 are excluded because diarisation was judged unreliable on them.' },
  'agent.coaching': { status: 'real', note: 'Coaching notes generated per call from what the agent actually did and missed.' },
  'agent.compliance': { status: 'partial', note: 'Compliance flags are raised only where a breach is observable in the transcript, but the extraction found breaches on just 2 of 6,253 calls. That rate is low enough to suspect the detector rather than the sales floor — the enrichment prompt tells the model “empty is the correct answer for most calls”, which biases it towards finding nothing. Treat a zero here as unverified, not as a clean record.' },
  'agent.team': { status: 'demo', note: 'Agent names are real (Zoho call owners), but team and reporting-manager structure is not available — the Zoho Users module is outside this integration’s OAuth scope.' },

  // ── Actions ───────────────────────────────────────────────────────────
  'actions.list': { status: 'real', note: '10,907 next actions derived from commitments actually made on the calls — the reason text is what the agent or customer said they would do.' },
  'actions.sla': { status: 'partial', note: 'Due dates are real call time plus a priority-based SLA. Because no system reports completion back, every action whose date has passed counts as overdue — read the overdue total as “not confirmed done”, not as proven failure.' },
  'actions.crmSync': { status: 'demo', note: 'No task-system integration exists, so CRM task linkage and completed-vs-open status cannot be real. Every action starts as pending and any status change lives only in this browser session.' },

  // ── Calls & transcripts ───────────────────────────────────────────────
  'call.transcript': { status: 'real', note: 'Full diarised Sarvam Saaras v3 transcript with real per-turn timestamps, on all 6,253 calls.' },
  'call.summary': { status: 'real', note: 'Per-call summary generated from the real transcript, with quoted evidence verified against it and dropped when it does not match.' },
  'call.confidence': { status: 'partial', note: 'Transcript confidence is Sarvam’s own per-call figure, and it is genuinely low on a lot of this corpus: 2,808 of 6,253 calls fall below the 0.6 threshold used to exclude a call from management aggregates. There is no separate model-confidence score — an earlier “AI confidence” figure was a fixed 0.8 on every call and has been removed rather than left to look computed.' },
  'call.audio': { status: 'partial', note: 'Real playback, streamed via a local proxy (scripts/audio_proxy.mjs) that holds the Zoho session cookie server-side. Two real constraints: playback only works on the machine running the proxy, and the cookie expires every few days and needs a manual refresh. Zoho also keeps recordings for a rolling ~3 months, so the oldest calls in this window will lose their audio before the newest do.' },
  'call.entities': { status: 'real', note: 'People, places, products, money and dates extracted from the real transcript.' },

  // ── Quality audit ─────────────────────────────────────────────────────
  'qa.audit': { status: 'partial', note: 'The 100-point PSM scorecard, judged by gpt-4.1-mini and scored deterministically in Python. All 6,260 stored calls carry an audit, but only 4,342 produced a score — 1,918 came back NOT_SCORED. 54% of scored calls auto-zero on CM-5, a criterion that is still undefined (prompts/SCORECARD_QUESTIONS.md), so tier distributions currently say more about CM-5 than about the calls.' },

  // ── Alerts ───────────────────────────────────────────────────────────
  'alerts.rules': { status: 'real', note: 'Alert rules evaluated against real calls (negative sentiment, unanswered questions, overdue actions, compliance).' },
  'alerts.workflow': { status: 'demo', note: 'Acknowledging or resolving an alert is in-app only — there is no escalation or ticketing system to write back to, so nothing persists.' },

  // ── Period handling ───────────────────────────────────────────────────
  'period.comparison': { status: 'real', note: 'The snapshot spans two full months — June (1,238 calls) and July (5,015) — so period-over-period comparison is real. Read June comparisons with some care: it is a quarter the size of July, so small segments move sharply.' },
  'period.anchor': { status: 'partial', note: 'Period filters run relative to the snapshot end date (31 July 2026) rather than today, so “last 7/30 days” stay meaningful as the snapshot ages. A 30-day default therefore shows July only; widen the range to see June.' },

  // ── Misc dimensions ───────────────────────────────────────────────────
  'dim.leadSource': { status: 'real', note: 'Lead source from the Zoho Lead record on 5,530 of 6,253 calls — Meta Ads 2,938, Ecommerce 1,270, IVR 539, Typeform waitlist 377, website 171. The remaining 723 are “Not recorded” in Zoho rather than guessed.' },
  'dim.campaign': { status: 'partial', note: 'Campaign name is real Zoho data but present on only 2,916 of 6,253 leads; the rest show “None” rather than being attributed to a guessed campaign.' },
  'dim.crmStage': { status: 'real', note: 'Lead status from Zoho on 5,543 of 6,253 calls, using Sunrooof’s own stage vocabulary (Open, Prospect, Priority Prospect, Future Prospect, Not Interested, Non-Serviceable, Raw Quote, Drawings Received, Closure).' },
  'dim.customerType': { status: 'partial', note: 'Zoho’s client-type field is filled on a minority of Sunrooof leads, so most of this dimension is inferred from what was said on the call — 5,731 calls land on “New lead”, which is the fallback as much as it is a finding.' },
  'dim.spaceType': { status: 'partial', note: 'Space type from Zoho’s Type_of_Space field on 3,639 of 6,253 leads — Residential 2,309, Apartments 345, Office 227, Retail 105. The other 2,614 are “Not recorded”. Still Sunrooof’s strongest real segmentation dimension.' },
  'dim.product': { status: 'partial', note: 'Sunrooof sells a single console product line, so this dimension carries little signal: 3,225 calls name the console and 2,907 name no product at all. Variant spellings the model produced are normalised into one value rather than shown as separate products.' },
  'dim.language': { status: 'real', note: 'Language mix detected per call during transcription — Hindi/English 3,097, English 2,147, English/Hindi 290, plus Telugu, Kannada and Tamil mixes.' },
};

export const provOf = (key: string): ProvEntry | null => PROVENANCE[key] ?? null;

export function provCounts() {
  const vals = Object.values(PROVENANCE);
  return {
    real: vals.filter((v) => v.status === 'real').length,
    partial: vals.filter((v) => v.status === 'partial').length,
    demo: vals.filter((v) => v.status === 'demo').length,
    total: vals.length,
  };
}
