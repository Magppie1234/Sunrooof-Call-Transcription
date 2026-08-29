/**
 * ⚠️ MOCK DATA GENERATOR — produces deterministic, clearly-labelled demo data.
 * This module is only imported by services/mockService.ts. The live service
 * (services/liveService.ts) never touches it.
 */
import type {
  CallRecord, CallOutcome, CustomerType, FaqHit, IntentLevel, NextAction, ObjectionHit,
  QualityScores, SentimentLabel, TranscriptSegment,
} from '../../types/domain';
import { BRAND } from '../../config';
import {
  mulberry32, pick, pickN, int, chance, weighted, round, clamp, type Rng,
} from './random';
import {
  EMPLOYEES, GEO, PRODUCT_SERIES, LANGUAGES, LEAD_SOURCES, CAMPAIGNS, CRM_STAGES, COMPETITORS,
  CUSTOMER_FIRST, CUSTOMER_LAST, FAQ_TEMPLATES, OBJECTION_TEMPLATES, NEEDS, APPRECIATION,
  DISSATISFACTION, FEATURE_REQUESTS, EXPECTATIONS, PAIN_POINTS, BUYING_SIGNALS, RISK_POOL,
  COMPLIANCE_POOL, AGENT_OPENERS, CUSTOMER_OPENERS, DISCOVERY_QUESTIONS, CLOSERS_GOOD, CLOSERS_WEAK,
} from './taxonomies';

const CALL_COUNT = 620;
const DAYS_BACK = 90;

/** Per-agent skill bias so quality comparisons are meaningful, not noise. */
const AGENT_SKILL: Record<string, number> = {
  E01: 0.82, E02: 0.9, E03: 0.62, E04: 0.78, E05: 0.7, E06: 0.88, E07: 0.58, E08: 0.75, E09: 0.68, E10: 0.85,
};

const sentimentLabel = (v: number): SentimentLabel => (v > 0.15 ? 'positive' : v < -0.15 ? 'negative' : 'neutral');

function isoAt(day: Date, hour: number, minute: number): string {
  const d = new Date(day);
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

function buildQuality(rng: Rng, skill: number, hasObjection: boolean): QualityScores {
  const p = (base: number, spread = 18) => Math.round(clamp(base * 100 + (rng() - 0.5) * spread * 2, 20, 100));
  const opening = p(skill + 0.05);
  const discovery = p(skill - 0.05);
  const solutionRelevance = p(skill);
  const faqHandling = p(skill);
  const objectionHandling = hasObjection ? p(skill - 0.08) : p(skill);
  const nextStepClarity = p(skill - 0.02);
  const listening = p(skill + 0.02);
  const professionalism = p(skill + 0.08);
  // Weighted overall — weights documented in docs/08-scoring-methodology.md
  const overall = Math.round(
    discovery * 0.2 + solutionRelevance * 0.15 + faqHandling * 0.15 + objectionHandling * 0.15 +
    nextStepClarity * 0.15 + listening * 0.1 + opening * 0.05 + professionalism * 0.05,
  );
  const complianceFail = chance(rng, 0.04);
  const weakest = discovery < nextStepClarity ? 'discovery questioning' : 'next-step closure';
  return {
    opening, discovery, solutionRelevance, faqHandling, objectionHandling, nextStepClarity,
    listening, professionalism, overall,
    complianceFail,
    complianceNotes: complianceFail ? pick(rng, COMPLIANCE_POOL) : null,
    scriptAdherence: p(skill + 0.04),
    coachingNote: overall < 70 ? `Coach on ${weakest}; review call recording with manager.` : null,
  };
}

let actionSeq = 0;

function buildActions(
  rng: Rng, callId: string, customerName: string, employeeId: string, callDate: Date,
  intent: IntentLevel, outcome: CallOutcome, now: Date,
): NextAction[] {
  const actions: NextAction[] = [];
  const mk = (source: 'committed' | 'ai_recommended', action: NextAction['action'], dueOffsetDays: number, reason: string): NextAction => {
    const due = new Date(callDate);
    due.setDate(due.getDate() + dueOffsetDays);
    due.setHours(int(rng, 10, 18), 0, 0, 0);
    const overdue = due.getTime() < now.getTime();
    const dueToday = due.toDateString() === now.toDateString();
    const completed = overdue && chance(rng, 0.62);
    const status: NextAction['status'] = completed ? 'completed' : source === 'ai_recommended' && chance(rng, 0.5) ? 'pending' : 'approved';
    return {
      id: `A${String(++actionSeq).padStart(4, '0')}`,
      callId, customerName, action, source,
      committedBy: source === 'committed' ? (chance(rng, 0.8) ? 'employee' : 'customer') : null,
      ownerEmployeeId: employeeId,
      priority: intent === 'high' ? 'P1' : intent === 'medium' ? 'P2' : 'P3',
      dueDate: due.toISOString(),
      channel: pick(rng, ['Call', 'WhatsApp', 'Email', 'Visit'] as const),
      reason,
      transcriptRef: int(rng, 60, 400),
      status: completed ? 'completed' : status,
      slaStatus: completed ? (chance(rng, 0.8) ? 'met' : 'breached') : overdue ? 'overdue' : dueToday ? 'due_today' : 'on_track',
      crmTaskLinked: chance(rng, 0.55),
    };
  };

  if (outcome === 'Quotation requested') actions.push(mk('committed', 'Share quotation', int(rng, 1, 3), 'Customer explicitly asked for a quotation on this call.'));
  if (outcome === 'Site visit scheduled') actions.push(mk('committed', 'Arrange site visit', int(rng, 2, 6), 'Site visit agreed with the customer.'));
  if (outcome === 'Callback requested') actions.push(mk('committed', 'Call back', int(rng, 1, 4), 'Customer asked to be called back at an agreed time.'));
  if (outcome === 'Complaint raised') actions.push(mk('committed', 'Escalate complaint', 1, 'Open complaint must be escalated to service team.'));
  if (outcome === 'Demo scheduled') actions.push(mk('committed', 'Schedule demonstration', int(rng, 2, 5), 'Studio demonstration agreed with the customer.'));
  if (intent === 'high' && actions.length === 0 && chance(rng, 0.8)) {
    actions.push(mk('committed', pick(rng, ['Share quotation', 'Arrange measurement', 'Schedule meeting'] as const), int(rng, 1, 4), 'High purchase-intent customer; concrete next step agreed.'));
  }
  if (chance(rng, 0.45)) {
    actions.push(mk('ai_recommended', pick(rng, ['Send catalogue / brochure', 'Nurture the customer', 'Share design / drawings', 'Provide technical clarification', 'Assign a specialist'] as const), int(rng, 2, 7), 'Recommended by conversation analysis based on discussed topics and business rules.'));
  }
  return actions;
}

function buildTranscript(
  rng: Rng, agentName: string, customerName: string, faqs: FaqHit[], objections: ObjectionHit[],
  closingSent: number, durationSec: number,
): TranscriptSegment[] {
  const segs: TranscriptSegment[] = [];
  let t = 2;
  const push = (speaker: 'agent' | 'customer', text: string) => {
    segs.push({ t, speaker, text });
    t += int(rng, 12, 35);
  };
  push('agent', pick(rng, AGENT_OPENERS).replace('{agent}', agentName.split(' ')[0]).replace('{brand}', BRAND.companyName).replace('{customer}', customerName));
  push('customer', pick(rng, CUSTOMER_OPENERS));
  for (const q of pickN(rng, DISCOVERY_QUESTIONS, int(rng, 1, 3))) {
    push('agent', q);
    push('customer', pick(rng, ['We have a 10 by 8 kitchen, possession is next month.', 'It is a renovation — the current kitchen is quite old.', 'We are targeting completion in about two months.', 'I saw the Lumen display at your studio, liked it a lot.']));
  }
  for (const f of faqs) {
    f.t = t;
    push('customer', f.originalQuestion);
    const tpl = FAQ_TEMPLATES.find((x) => x.standardized === f.standardized);
    if (f.status !== 'unanswered') push('agent', (f.status === 'partial' ? 'I will need to double-check the exact details, but broadly — ' : '') + (tpl?.answer ?? 'Let me explain that.'));
    else push('agent', 'That I am not fully sure about — let me get back to you on it.');
  }
  for (const o of objections) {
    o.t = t;
    push('customer', o.statement);
    push('agent', o.employeeResponse);
    if (o.resolution === 'resolved') push('customer', 'Okay, that makes sense actually.');
    else if (o.resolution === 'partial') push('customer', 'Hmm, I see. I still need to think about it.');
    else push('customer', 'I am not convinced, honestly.');
  }
  const action = 'I will share the quotation by Thursday and we meet at the studio on Saturday 11am';
  if (closingSent > 0) push('agent', pick(rng, CLOSERS_GOOD).replace('{action}', action).replace('{customer}', customerName));
  else push('agent', pick(rng, CLOSERS_WEAK));
  push('customer', closingSent > 0.1 ? 'Sure, thank you. Speak soon.' : closingSent < -0.1 ? 'Fine. But please do not delay this time.' : 'Okay, fine.');
  // Scale timestamps into call duration
  const maxT = segs[segs.length - 1].t;
  const scale = (durationSec - 15) / maxT;
  for (const s of segs) s.t = Math.round(s.t * scale);
  for (const f of faqs) f.t = Math.round(f.t * scale);
  for (const o of objections) if (o.t !== null) o.t = Math.round(o.t * scale);
  return segs;
}

export interface MockDataset {
  calls: CallRecord[];
  generatedAt: string;
}

export function generateDataset(): MockDataset {
  const rng = mulberry32(20260730);
  const now = new Date();
  const calls: CallRecord[] = [];

  // Pre-build a pool of customers so repeat callers (and repeat-negative customers) exist.
  const customers = Array.from({ length: 420 }, (_, i) => ({
    id: `C${String(i + 1).padStart(4, '0')}`,
    name: `${pick(rng, CUSTOMER_FIRST)} ${pick(rng, CUSTOMER_LAST)}`,
    geo: weighted(rng, GEO.map((g) => [g, g.weight] as const)),
    type: weighted(rng, [['New lead', 62], ['Existing customer', 22], ['Dealer', 6], ['Architect/Designer', 10]] as const) as CustomerType,
    grumpy: chance(rng, 0.08), // tends to repeat-negative
  }));

  for (let i = 0; i < CALL_COUNT; i++) {
    const id = `CALL-${String(i + 1).padStart(4, '0')}`;
    const cust = pick(rng, customers);
    const emp = cust.type === 'Existing customer' && chance(rng, 0.5)
      ? pick(rng, EMPLOYEES.filter((e) => e.team === 'Service & Care'))
      : pick(rng, EMPLOYEES);
    const skill = AGENT_SKILL[emp.id];
    const dayOffset = Math.floor(rng() ** 1.15 * DAYS_BACK); // more recent-heavy
    const day = new Date(now);
    day.setDate(day.getDate() - dayOffset);
    const dateTime = isoAt(day, int(rng, 9, 19), int(rng, 0, 59));
    const direction = chance(rng, 0.58) ? 'outbound' : 'inbound';
    const connected = chance(rng, 0.9);
    const durationSec = connected ? int(rng, 45, 900) : int(rng, 0, 20);
    const meaningful = connected && durationSec > 60;
    const transcribed = connected && chance(rng, 0.93);
    const transcriptionConfidence = transcribed ? round(0.55 + rng() * 0.44, 2) : 0;
    const diarizationReliable = transcribed && chance(rng, 0.85);
    const language = pick(rng, LANGUAGES);
    const productSeries = pick(rng, PRODUCT_SERIES);
    const leadSource = pick(rng, LEAD_SOURCES);
    const campaign = leadSource.includes('ads') ? pick(rng, CAMPAIGNS.slice(0, 4)) : pick(rng, ['Architect Connect', 'None', 'None'] as const);

    if (!transcribed || !meaningful) {
      calls.push({
        id, dateTime, direction, durationSec,
        customerId: cust.id, customerName: cust.name, customerType: cust.type,
        employeeId: emp.id,
        region: cust.geo.region, state: cust.geo.state, city: cust.geo.city,
        productSeries, language, leadSource, campaign,
        crmStage: pick(rng, CRM_STAGES), outcome: connected ? 'No requirement' : 'Not connected',
        connected, meaningful, transcribed, transcriptionConfidence, diarizationReliable: false,
        sentiment: null, purchaseReadiness: null, intent: 'none',
        customerNeed: null, budgetMentioned: null, timelineMentioned: null, decisionMaker: 'unknown',
        buyingSignals: [], crossSell: null, discountRequested: false, competitorMentions: [],
        topics: [], appreciationThemes: [], dissatisfactionThemes: [], featureRequests: [], expectations: [], painPoints: [],
        faqs: [], objections: [], quality: null, talk: null, actions: [], commitments: [], risks: [],
        complianceFlags: [], entities: [], summary: transcribed ? 'Very short call — no meaningful conversation to analyse.' : 'Transcript unavailable (call not transcribed).',
        transcript: [],
        crm: { opportunityCreated: false, orderConfirmed: false, complaintOpen: false, revenueInfluenced: null, verified: false },
        hasRecording: connected,
      });
      continue;
    }

    // ---- Analysed call ----
    const baseMood = cust.grumpy ? -0.35 : (rng() - 0.42) * 0.9;
    const opening = round(clamp(baseMood + (rng() - 0.5) * 0.3, -1, 1), 2);
    const skillLift = (skill - 0.55) * 0.9;
    const closing = round(clamp(opening + skillLift + (rng() - 0.45) * 0.5, -1, 1), 2);
    const mid = round(clamp((opening + closing) / 2 + (rng() - 0.5) * 0.2, -1, 1), 2);
    const overallSent = sentimentLabel((opening + mid + closing * 1.4) / 3.4);
    const emotions: string[] = [];
    if (closing < -0.3) emotions.push('frustration');
    if (chance(rng, 0.18)) emotions.push('confusion');
    if (chance(rng, 0.2)) emotions.push('hesitation');
    if (chance(rng, 0.14)) emotions.push('urgency');
    if (closing > 0.3) emotions.push('trust', 'satisfaction');
    if (closing > 0.1 && chance(rng, 0.5)) emotions.push('interest');

    const isService = emp.team === 'Service & Care';
    const faqCount = weighted(rng, [[0, 12], [1, 30], [2, 32], [3, 18], [4, 8]] as const);
    const faqTpls = pickN(rng, FAQ_TEMPLATES, faqCount);
    const faqs: FaqHit[] = faqTpls.map((tpl) => {
      const status = weighted(rng, [['answered', skill * 100], ['partial', 28], ['unanswered', 34 - skill * 20]] as const);
      return {
        category: tpl.category,
        standardized: tpl.standardized,
        originalQuestion: pick(rng, tpl.variants),
        status,
        responseTimeSec: status === 'unanswered' ? null : int(rng, 3, 40),
        sentimentAfter: status === 'answered' ? (chance(rng, 0.7) ? 'positive' : 'neutral') : status === 'partial' ? 'neutral' : (chance(rng, 0.55) ? 'negative' : 'neutral'),
        escalationNeeded: status === 'unanswered' && chance(rng, 0.3),
        t: 0,
      };
    });

    const objCount = isService ? weighted(rng, [[0, 70], [1, 30]] as const) : weighted(rng, [[0, 38], [1, 42], [2, 20]] as const);
    const objections: ObjectionHit[] = pickN(rng, OBJECTION_TEMPLATES, objCount).map((tpl) => {
      const resolution = weighted(rng, [['resolved', skill * 100], ['partial', 40], ['unresolved', 45 - skill * 30]] as const);
      return {
        type: tpl.type,
        intensity: pick(rng, ['low', 'medium', 'high'] as const),
        statement: tpl.statement,
        employeeResponse: tpl.response,
        technique: tpl.technique,
        resolution,
        customerReaction: resolution === 'resolved' ? 'positive' : resolution === 'partial' ? 'neutral' : 'negative',
        t: 0,
      };
    });

    // Purchase readiness (weights per docs/08-scoring-methodology.md)
    const needFit = isService ? int(rng, 5, 40) : int(rng, 30, 100);
    const explicitIntent = clamp(needFit + int(rng, -30, 25), 0, 100);
    const timeline = int(rng, 0, 100);
    const nextStepCommitment = clamp(Math.round(skill * 60 + rng() * 40), 0, 100);
    const authority = pick(rng, [100, 100, 50, 0]);
    const budget = int(rng, 0, 100);
    const sentComp = Math.round((closing + 1) * 50);
    const prScore = Math.round(
      needFit * 0.25 + explicitIntent * 0.2 + timeline * 0.15 + nextStepCommitment * 0.15 +
      authority * 0.1 + budget * 0.1 + sentComp * 0.05,
    );
    const intent: IntentLevel = isService ? 'none' : prScore >= 70 ? 'high' : prScore >= 50 ? 'medium' : prScore >= 30 ? 'low' : 'none';

    const outcome: CallOutcome = isService
      ? weighted(rng, [['Complaint raised', 45], ['Interested — follow-up', 20], ['Callback requested', 20], ['No requirement', 15]] as const)
      : intent === 'high'
        ? weighted(rng, [['Quotation requested', 30], ['Site visit scheduled', 22], ['Demo scheduled', 14], ['Order confirmed', 12], ['Interested — follow-up', 22]] as const)
        : intent === 'medium'
          ? weighted(rng, [['Interested — follow-up', 40], ['Quotation requested', 18], ['Callback requested', 24], ['Demo scheduled', 8], ['Not interested', 10]] as const)
          : weighted(rng, [['Interested — follow-up', 18], ['Callback requested', 22], ['Not interested', 34], ['No requirement', 20], ['Complaint raised', 6]] as const);

    const quality = buildQuality(rng, skill, objections.length > 0);
    const actions = buildActions(rng, id, cust.name, emp.id, new Date(dateTime), intent, outcome, now);

    const competitorMentions = chance(rng, 0.22) ? pickN(rng, COMPETITORS, int(rng, 1, 2)) : [];
    const risks: string[] = [];
    if (closing < -0.4) risks.push('Severe negative sentiment at call end');
    if (cust.grumpy && overallSent === 'negative') risks.push('Repeat-negative customer');
    if (chance(rng, 0.07)) risks.push(pick(rng, RISK_POOL));
    if (outcome === 'Complaint raised' && chance(rng, 0.25)) risks.push('Customer indicated possible cancellation/refund');
    if (chance(rng, 0.012)) risks.push('Customer mentioned taking legal action');

    const complianceFlags = quality.complianceFail && quality.complianceNotes ? [quality.complianceNotes] : [];
    const orderConfirmed = outcome === 'Order confirmed';
    const opportunityCreated = orderConfirmed || (intent !== 'none' && chance(rng, intent === 'high' ? 0.6 : 0.25));
    const crmVerified = chance(rng, 0.7);

    const transcript = buildTranscript(rng, EMPLOYEES.find((e) => e.id === emp.id)!.name, cust.name, faqs, objections, closing, durationSec);

    const unansweredCount = faqs.filter((f) => f.status === 'unanswered').length;
    calls.push({
      id, dateTime, direction, durationSec,
      customerId: cust.id, customerName: cust.name, customerType: cust.type,
      employeeId: emp.id,
      region: cust.geo.region, state: cust.geo.state, city: cust.geo.city,
      productSeries, language, leadSource, campaign,
      crmStage: orderConfirmed ? 'Won' : pick(rng, CRM_STAGES.slice(0, 6)),
      outcome, connected, meaningful, transcribed, transcriptionConfidence, diarizationReliable,
      sentiment: {
        opening, mid, closing, overall: overallSent, shift: round(closing - opening, 2), emotions,
        unresolvedNegative: overallSent === 'negative' && closing < 0 && !chance(rng, 0.3),
      },
      purchaseReadiness: isService ? null : { score: prScore, needFit, explicitIntent, timeline, nextStepCommitment, authority, budget, sentiment: sentComp },
      intent,
      customerNeed: chance(rng, 0.85) ? pick(rng, NEEDS) : null,
      budgetMentioned: chance(rng, 0.4) ? pick(rng, ['₹3–4 lakh', '₹5–7 lakh', '₹8–12 lakh', 'Above ₹12 lakh'] as const) : null,
      timelineMentioned: chance(rng, 0.5) ? pick(rng, ['Within 1 month', '1–3 months', '3–6 months', 'After 6 months'] as const) : null,
      decisionMaker: authority === 100 ? 'yes' : authority === 50 ? 'unknown' : 'no',
      buyingSignals: intent === 'high' ? pickN(rng, BUYING_SIGNALS, int(rng, 2, 4)) : intent === 'medium' ? pickN(rng, BUYING_SIGNALS, int(rng, 0, 2)) : [],
      crossSell: chance(rng, 0.18) ? pick(rng, ['Wardrobe Pro upsell potential', 'Accessories & lighting add-on', 'Appliance package cross-sell'] as const) : null,
      discountRequested: objections.some((o) => o.type === 'Price / discount') || chance(rng, 0.1),
      competitorMentions,
      topics: [...new Set([productSeries.split(' ')[0], ...faqs.map((f) => f.category.split(' ')[0]), ...(competitorMentions.length ? ['Competitors'] : [])])],
      appreciationThemes: closing > 0.25 ? pickN(rng, APPRECIATION, int(rng, 1, 2)) : [],
      dissatisfactionThemes: closing < -0.2 || outcome === 'Complaint raised' ? pickN(rng, DISSATISFACTION, int(rng, 1, 2)) : [],
      featureRequests: chance(rng, 0.15) ? [pick(rng, FEATURE_REQUESTS)] : [],
      expectations: chance(rng, 0.3) ? [pick(rng, EXPECTATIONS)] : [],
      painPoints: chance(rng, 0.25) ? [pick(rng, PAIN_POINTS)] : [],
      faqs, objections, quality,
      talk: diarizationReliable ? {
        agentTalkPct: int(rng, 35, 78),
        interruptions: weighted(rng, [[0, 50], [1, 25], [2, 15], [3, 6], [5, 4]] as const),
        longestSilenceSec: int(rng, 2, 25),
      } : null,
      actions,
      commitments: actions.filter((a) => a.source === 'committed').map((a) => `${a.committedBy === 'customer' ? 'Customer' : 'Agent'}: ${a.action} by ${new Date(a.dueDate).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`),
      risks, complianceFlags,
      entities: [
        { text: productSeries, type: 'Product series' },
        ...competitorMentions.map((c) => ({ text: c, type: 'Competitor' })),
        ...(chance(rng, 0.3) ? [{ text: cust.geo.city, type: 'Location' }] : []),
      ],
      summary: `${cust.type === 'Existing customer' ? 'Existing customer' : 'Prospect'} ${cust.name} discussed ${productSeries} (${pick(rng, NEEDS)}). ` +
        `${faqCount ? `Asked ${faqCount} question(s), ${unansweredCount ? `${unansweredCount} left unanswered. ` : 'all addressed. '}` : ''}` +
        `${objections.length ? `Raised ${objections.length} objection(s), primary: ${objections[0].type}. ` : ''}` +
        `Call ended ${sentimentLabel(closing)}; outcome: ${outcome}.`,
      transcript,
      crm: {
        opportunityCreated, orderConfirmed, complaintOpen: outcome === 'Complaint raised',
        revenueInfluenced: orderConfirmed && crmVerified ? int(rng, 45, 180) * 10000 : null,
        verified: crmVerified,
      },
      hasRecording: true,
    });
  }

  calls.sort((a, b) => b.dateTime.localeCompare(a.dateTime));
  return { calls, generatedAt: now.toISOString() };
}
