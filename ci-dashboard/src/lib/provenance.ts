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
 * Every number quoted below was measured against the current snapshot
 * (100 calls, 30–31 July 2026). Keep this list in sync with what the pages
 * render. `note` is shown on hover and in the Data Quality coverage table.
 */
export type ProvStatus = 'real' | 'partial' | 'demo';

export interface ProvEntry {
  status: ProvStatus;
  note: string;
}

export const PROVENANCE: Record<string, ProvEntry> = {
  // ── Volumes & coverage ────────────────────────────────────────────────
  'kpi.volume': { status: 'real', note: 'Call count, duration and direction from Sunrooof’s Zoho CRM Calls module.' },
  'kpi.coverage': { status: 'real', note: 'Transcription coverage: all 100 calls have a Sarvam Saaras v3 transcript stored.' },
  'kpi.customers': { status: 'real', note: 'Unique customers from the Zoho Lead/Contact linked to each call (96 of 100 calls are linked).' },
  'kpi.meaningful': { status: 'real', note: 'Connected, longer than 60s, and the customer actually spoke — decided from real diarisation, not assumed.' },

  // ── Sentiment & voice of customer ─────────────────────────────────────
  'sentiment.overall': { status: 'real', note: 'Text-based sentiment extracted per call by gpt-4.1-mini from the real transcript. All 100 calls scored.' },
  'sentiment.journey': { status: 'real', note: 'Opening/mid/closing thirds scored separately on each real transcript; shift = closing − opening.' },
  'sentiment.emotions': { status: 'real', note: 'Emotions inferred from transcript wording only. No voice-tone or acoustic analysis is performed, so anger conveyed purely by tone is not captured.' },
  'voc.themes': { status: 'real', note: 'Appreciation, dissatisfaction, expectations and pain points extracted from real customer speech.' },
  'voc.featureRequests': { status: 'real', note: 'Feature requests taken from what customers actually asked for on the call.' },

  // ── FAQs ──────────────────────────────────────────────────────────────
  'faq.questions': { status: 'real', note: '185 real customer questions across 53 calls — each kept only when a verbatim transcript quote could be verified, so invented questions are dropped rather than shown.' },
  'faq.answerQuality': { status: 'real', note: 'Answered / partial / unanswered judged against what the agent actually said in the transcript.' },
  'faq.responseTime': { status: 'real', note: 'Measured from Sarvam word timestamps: end of the customer’s question → start of the agent’s next turn.' },
  'faq.category': { status: 'partial', note: 'The questions are real, but they are mapped onto this dashboard’s fixed 16-category taxonomy. Sunrooof-specific themes such as “showroom / experience-centre visit” and “company info” have no exact bucket and land on the nearest one.' },
  'faq.accuracy': { status: 'demo', note: 'Answer *correctness* cannot be assessed: Sunrooof has no approved knowledge base to check answers against. Only relevance and completeness are measured — a confidently wrong answer would still read as “answered clearly”.' },

  // ── Regional ──────────────────────────────────────────────────────────
  'region.geo': { status: 'real', note: 'City resolved from the linked Zoho Lead on 96 of 100 calls; 86 map to a region. Spelling variants (Bangaluru/Bengaluru, NewDelhi) are normalised, and overseas enquiries (Dubai, Abu Dhabi) bucket to International rather than being dropped.' },
  'region.pincode': { status: 'demo', note: 'Zoho’s Zip_Code field is empty on every Sunrooof lead in this dataset (0 of 100), so pincode-level analysis has no real source. Fixing this means capturing pincode at lead entry, not in code.' },

  // ── Sales & objections ────────────────────────────────────────────────
  'sales.readiness': { status: 'real', note: 'Purchase-readiness sub-scores extracted per call and weighted per the documented methodology. Sub-scores are 0 where the topic never came up, rather than guessed.' },
  'sales.objections': { status: 'real', note: '21 objections detected across the calls, classified into the dashboard taxonomy with the customer’s own words kept as evidence.' },
  'sales.competitors': { status: 'real', note: 'Competitor names only where the customer actually named one on the call.' },
  'sales.budget': { status: 'real', note: 'Budget and timeline recorded only when the customer stated them — the agent’s quoted console price is deliberately not counted as the customer’s budget.' },
  'sales.revenue': { status: 'demo', note: 'Only 1 of these 100 calls links to a Zoho Deal, and that deal sits at “Raw Quote” with no amount received. Influenced revenue and order counts therefore have no real source and remain demo figures.' },
  'sales.funnelCrm': { status: 'partial', note: 'Lead stage is real Zoho data (Open / Prospect / Future Prospect / Not Interested / Non-Serviceable, on 93 of 100 calls). The order-confirmed end of the funnel is not real: no call in this window reached a won order.' },

  // ── Agent quality ─────────────────────────────────────────────────────
  'agent.quality': { status: 'real', note: 'Eight-parameter scorecard from the real per-call scorecard plus transcript-derived dimensions, across 13 real agents.' },
  'agent.talk': { status: 'real', note: 'Talk ratio from diarisation; interruptions and longest silence measured from real Sarvam word timestamps (99 of 100 calls — one call has a single speaker turn).' },
  'agent.coaching': { status: 'real', note: 'Coaching notes generated per call from what the agent actually did and missed.' },
  'agent.compliance': { status: 'real', note: 'Compliance flags are raised only where a breach is observable in the transcript. Across all 100 calls the extraction found none, so these counters legitimately read zero — the check ran, it did not fail to run.' },
  'agent.team': { status: 'demo', note: 'Agent names are real (Zoho call owners), but team and reporting-manager structure is not available — the Zoho Users module is outside this integration’s OAuth scope.' },

  // ── Actions ───────────────────────────────────────────────────────────
  'actions.list': { status: 'real', note: '153 next actions derived from commitments actually made on the calls — the reason text is what the agent or customer said they would do.' },
  'actions.sla': { status: 'partial', note: 'Due dates are real call time plus a priority-based SLA. Because no system reports completion back, every action whose date has passed counts as overdue — read the overdue total as “not confirmed done”, not as proven failure.' },
  'actions.crmSync': { status: 'demo', note: 'No task-system integration exists, so CRM task linkage and completed-vs-open status cannot be real. Every action starts as pending and any status change lives only in this browser session.' },

  // ── Calls & transcripts ───────────────────────────────────────────────
  'call.transcript': { status: 'real', note: 'Full diarised Sarvam Saaras v3 transcript with real per-turn timestamps, on all 100 calls.' },
  'call.summary': { status: 'real', note: 'Per-call summary generated from the real transcript, with quoted evidence verified against it.' },
  'call.audio': { status: 'demo', note: 'Recording playback is not wired into this app. All 100 calls do have a real Zoho recording URL, but audio needs a server to attach the Zoho session cookie — it plays in the Next.js dashboard in this project, not in this static SPA.' },
  'call.entities': { status: 'real', note: 'People, places, products, money and dates extracted from the real transcript.' },

  // ── Alerts ────────────────────────────────────────────────────────────
  'alerts.rules': { status: 'real', note: 'Alert rules evaluated against real calls (negative sentiment, unanswered questions, overdue actions, compliance).' },
  'alerts.workflow': { status: 'demo', note: 'Acknowledging or resolving an alert is in-app only — there is no escalation or ticketing system to write back to, so nothing persists.' },

  // ── Period handling ───────────────────────────────────────────────────
  'period.comparison': { status: 'demo', note: 'This snapshot is a 2-day pilot window (30–31 July 2026), so there is no previous period to compare against and every trend delta reads “no prior data”. Transcribing a longer history is what makes period-over-period real.' },
  'period.anchor': { status: 'partial', note: 'Period filters run relative to the snapshot end date (31 July 2026) rather than today, so “last 7/30 days” stay meaningful as the snapshot ages. With only 2 days of calls, every period filter currently returns the same 100 calls.' },

  // ── Misc dimensions ───────────────────────────────────────────────────
  'dim.leadSource': { status: 'real', note: 'Lead source from the Zoho Lead record — 93 of 100 calls (Meta Ads 59, IVR 11, Ecommerce 8, Typeform waitlist 6, plus website and Instagram).' },
  'dim.campaign': { status: 'partial', note: 'Campaign name is real Zoho data but present on only 58 of 100 leads; the rest show “None” rather than being attributed to a guessed campaign.' },
  'dim.crmStage': { status: 'real', note: 'Lead status from Zoho on 93 of 100 calls, using Sunrooof’s own stage vocabulary (Open, Prospect, Future Prospect, Not Interested, Non-Serviceable).' },
  'dim.customerType': { status: 'partial', note: 'Zoho’s client-type field is filled on only 19 of 100 Sunrooof leads, so most of this dimension is inferred from what was said on the call (new lead vs existing customer vs architect/designer) rather than read from CRM.' },
  'dim.spaceType': { status: 'real', note: 'Space type from Zoho’s Type_of_Space field on 71 of 100 leads — Residential 50, Apartments 8, Office 5, Retail 2, Hotel/Resort 2. Sunrooof’s strongest real segmentation dimension.' },
  'dim.product': { status: 'partial', note: 'Sunrooof sells a single console product line, so this dimension carries little signal: 50 calls name the console, 47 name no product at all. Variant spellings the model produced are normalised into one value rather than shown as separate products.' },
  'dim.language': { status: 'real', note: 'Language mix detected per call during transcription — 57 Hindi/English, 34 English, plus Malayalam and Kannada mixes.' },
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
