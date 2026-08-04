/**
 * Aggregation & metric formulas. Every formula here is documented in
 * docs/04-metric-definitions.md — keep the two in sync.
 */
import type { CallRecord, FaqCategory, NextAction, ObjectionType } from '../types/domain';
import type { FilteredData } from './filters';
import { EMPLOYEES } from '../data/taxonomy';
import { MIN_SAMPLE_SIZE } from '../config';

export const uniq = <T,>(arr: T[]) => [...new Set(arr)];

export const avg = (ns: number[]) => (ns.length ? ns.reduce((a, b) => a + b, 0) / ns.length : 0);

const isToday = (iso: string, now = new Date()) => new Date(iso).toDateString() === now.toDateString();

// ---------- KPI summary ----------
export interface KpiValue { value: number; prev: number; denom?: number }

export function kpiSummary(d: FilteredData, now = new Date()) {
  const { current, previous, analysed, analysedPrev } = d;
  const calc = (calls: CallRecord[], analysedCalls: CallRecord[]) => {
    const transcribedCalls = calls.filter((c) => c.transcribed);
    const meaningful = calls.filter((c) => c.meaningful);
    const actions = analysedCalls.flatMap((c) => c.actions);
    const withNextAction = analysedCalls.filter((c) => c.actions.some((a) => a.source === 'committed'));
    const orders = calls.filter((c) => c.crm.orderConfirmed);
    const opps = calls.filter((c) => c.crm.opportunityCreated);
    return {
      totalCalls: calls.length,
      transcribed: transcribedCalls.length,
      coveragePct: calls.length ? (transcribedCalls.length / calls.length) * 100 : 0,
      uniqueCustomers: uniq(calls.map((c) => c.customerId)).length,
      meaningful: meaningful.length,
      analysed: analysedCalls.length,
      positive: analysedCalls.filter((c) => c.sentiment!.overall === 'positive').length,
      neutral: analysedCalls.filter((c) => c.sentiment!.overall === 'neutral').length,
      negative: analysedCalls.filter((c) => c.sentiment!.overall === 'negative').length,
      sentimentImproved: analysedCalls.filter((c) => c.sentiment!.shift > 0.2).length,
      highIntent: uniq(analysedCalls.filter((c) => c.intent === 'high').map((c) => c.customerId)).length,
      avgQuality: avg(analysedCalls.filter((c) => c.quality).map((c) => c.quality!.overall)),
      withNextAction: withNextAction.length,
      actionsDueToday: actions.filter((a) => a.status !== 'completed' && a.status !== 'rejected' && isToday(a.dueDate, now)).length,
      actionsOverdue: actions.filter((a) => a.slaStatus === 'overdue').length,
      unansweredQuestions: analysedCalls.reduce((s, c) => s + c.faqs.filter((f) => f.status === 'unanswered').length, 0),
      criticalComplaints: analysedCalls.filter((c) => c.crm.complaintOpen && c.sentiment!.overall === 'negative').length,
      complianceAlerts: analysedCalls.filter((c) => c.complianceFlags.length > 0).length,
      opportunities: opps.length,
      orders: orders.length,
      revenue: orders.reduce((s, c) => s + (c.crm.revenueInfluenced ?? 0), 0),
      revenueVerifiedOrders: orders.filter((c) => c.crm.revenueInfluenced !== null).length,
    };
  };
  return { cur: calc(current, analysed), prev: calc(previous, analysedPrev) };
}

// ---------- Trend ----------
export interface DayPoint { date: string; label: string; calls: number; positive: number; neutral: number; negative: number; avgQuality: number }

export function dailyTrend(analysed: CallRecord[], start: Date, end: Date): DayPoint[] {
  const days: DayPoint[] = [];
  const byDay = new Map<string, CallRecord[]>();
  for (const c of analysed) {
    const k = new Date(c.dateTime).toISOString().slice(0, 10);
    (byDay.get(k) ?? byDay.set(k, []).get(k)!).push(c);
  }
  for (let t = new Date(start); t < end; t = new Date(t.getTime() + 86400_000)) {
    const k = t.toISOString().slice(0, 10);
    const calls = byDay.get(k) ?? [];
    days.push({
      date: k,
      label: t.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }),
      calls: calls.length,
      positive: calls.filter((c) => c.sentiment!.overall === 'positive').length,
      neutral: calls.filter((c) => c.sentiment!.overall === 'neutral').length,
      negative: calls.filter((c) => c.sentiment!.overall === 'negative').length,
      avgQuality: Math.round(avg(calls.filter((c) => c.quality).map((c) => c.quality!.overall))),
    });
  }
  return days;
}

// ---------- FAQs ----------
export interface FaqRow {
  category: FaqCategory;
  standardized: string;
  sampleQuestion: string;
  calls: number;
  customers: number;
  pctOfAnalysed: number;
  prevCalls: number;
  answered: number;
  partial: number;
  unanswered: number;
  avgResponseSec: number | null;
  positiveAfterPct: number;
  negativeAfterPct: number;
  escalations: number;
  avgConfidence: number;
  regions: string[];
  recommendation: string;
}

export function faqRows(analysed: CallRecord[], analysedPrev: CallRecord[]): FaqRow[] {
  const map = new Map<string, { row: FaqRow; customers: Set<string>; conf: number[]; resp: number[]; after: string[] }>();
  for (const c of analysed) {
    // FAQ counted once per call per standardised question (no intra-call inflation)
    const seen = new Set<string>();
    for (const f of c.faqs) {
      if (seen.has(f.standardized)) continue;
      seen.add(f.standardized);
      let e = map.get(f.standardized);
      if (!e) {
        e = {
          row: {
            category: f.category, standardized: f.standardized, sampleQuestion: f.originalQuestion,
            calls: 0, customers: 0, pctOfAnalysed: 0, prevCalls: 0, answered: 0, partial: 0, unanswered: 0,
            avgResponseSec: null, positiveAfterPct: 0, negativeAfterPct: 0, escalations: 0, avgConfidence: 0,
            regions: [], recommendation: '',
          },
          customers: new Set(), conf: [], resp: [], after: [],
        };
        map.set(f.standardized, e);
      }
      e.row.calls++;
      e.customers.add(c.customerId);
      e.row[f.status]++;
      if (f.responseTimeSec !== null) e.resp.push(f.responseTimeSec);
      e.after.push(f.sentimentAfter);
      if (f.escalationNeeded) e.row.escalations++;
      e.conf.push(f.confidence);
      if (!e.row.regions.includes(c.region)) e.row.regions.push(c.region);
    }
  }
  const prevCounts = new Map<string, number>();
  for (const c of analysedPrev) {
    for (const s of uniq(c.faqs.map((f) => f.standardized))) prevCounts.set(s, (prevCounts.get(s) ?? 0) + 1);
  }
  const rows = [...map.values()].map((e) => {
    const r = e.row;
    r.customers = e.customers.size;
    r.pctOfAnalysed = analysed.length ? (r.calls / analysed.length) * 100 : 0;
    r.prevCalls = prevCounts.get(r.standardized) ?? 0;
    r.avgResponseSec = e.resp.length ? Math.round(avg(e.resp)) : null;
    r.positiveAfterPct = e.after.length ? (e.after.filter((a) => a === 'positive').length / e.after.length) * 100 : 0;
    r.negativeAfterPct = e.after.length ? (e.after.filter((a) => a === 'negative').length / e.after.length) * 100 : 0;
    r.avgConfidence = avg(e.conf);
    const unansweredShare = r.calls ? r.unanswered / r.calls : 0;
    r.recommendation = unansweredShare > 0.3
      ? 'Add to knowledge base + run team training; high unanswered rate.'
      : r.calls >= 15
        ? 'Publish on website FAQ / first-call script to deflect volume.'
        : r.negativeAfterPct > 25
          ? 'Review answer script — customers react negatively after current answer.'
          : 'Monitor; include in monthly FAQ refresh.';
    return r;
  });
  return rows.sort((a, b) => b.calls - a.calls);
}

// ---------- Objections ----------
export interface ObjectionRow {
  type: ObjectionType;
  calls: number;
  prevCalls: number;
  resolved: number;
  partial: number;
  unresolved: number;
  highIntensity: number;
  positiveReactionPct: number;
  topTechnique: string;
}

export function objectionRows(analysed: CallRecord[], analysedPrev: CallRecord[]): ObjectionRow[] {
  const map = new Map<ObjectionType, ObjectionRow & { techniques: Map<string, number>; reactions: string[] }>();
  for (const c of analysed) {
    for (const o of c.objections) {
      let e = map.get(o.type);
      if (!e) {
        e = { type: o.type, calls: 0, prevCalls: 0, resolved: 0, partial: 0, unresolved: 0, highIntensity: 0, positiveReactionPct: 0, topTechnique: '', techniques: new Map(), reactions: [] };
        map.set(o.type, e);
      }
      e.calls++;
      e[o.resolution]++;
      if (o.intensity === 'high') e.highIntensity++;
      e.techniques.set(o.technique, (e.techniques.get(o.technique) ?? 0) + 1);
      e.reactions.push(o.customerReaction);
    }
  }
  for (const c of analysedPrev) {
    for (const t of uniq(c.objections.map((o) => o.type))) {
      const e = map.get(t);
      if (e) e.prevCalls++;
    }
  }
  return [...map.values()].map((e) => ({
    type: e.type, calls: e.calls, prevCalls: e.prevCalls, resolved: e.resolved, partial: e.partial,
    unresolved: e.unresolved, highIntensity: e.highIntensity,
    positiveReactionPct: e.reactions.length ? (e.reactions.filter((r) => r === 'positive').length / e.reactions.length) * 100 : 0,
    topTechnique: [...e.techniques.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—',
  })).sort((a, b) => b.calls - a.calls);
}

// ---------- Generic segment breakdown ----------
export interface SegmentRow {
  key: string;
  analysed: number;
  customers: number;
  positive: number;
  negative: number;
  avgShift: number;
  avgQuality: number;
  highIntent: number;
  unansweredFaqs: number;
  totalFaqs: number;
  overdueActions: number;
  totalActions: number;
  completedActions: number;
  orders: number;
  opportunities: number;
  complaints: number;
  competitorMentions: number;
  reliable: boolean;
}

export function segmentRows(analysed: CallRecord[], keyFn: (c: CallRecord) => string): SegmentRow[] {
  const map = new Map<string, CallRecord[]>();
  for (const c of analysed) {
    const k = keyFn(c);
    (map.get(k) ?? map.set(k, []).get(k)!).push(c);
  }
  return [...map.entries()].map(([key, calls]) => {
    const actions = calls.flatMap((c) => c.actions);
    return {
      key,
      analysed: calls.length,
      customers: uniq(calls.map((c) => c.customerId)).length,
      positive: calls.filter((c) => c.sentiment!.overall === 'positive').length,
      negative: calls.filter((c) => c.sentiment!.overall === 'negative').length,
      avgShift: avg(calls.map((c) => c.sentiment!.shift)),
      avgQuality: avg(calls.filter((c) => c.quality).map((c) => c.quality!.overall)),
      highIntent: calls.filter((c) => c.intent === 'high').length,
      unansweredFaqs: calls.reduce((s, c) => s + c.faqs.filter((f) => f.status === 'unanswered').length, 0),
      totalFaqs: calls.reduce((s, c) => s + c.faqs.length, 0),
      overdueActions: actions.filter((a) => a.slaStatus === 'overdue').length,
      totalActions: actions.length,
      completedActions: actions.filter((a) => a.status === 'completed').length,
      orders: calls.filter((c) => c.crm.orderConfirmed).length,
      opportunities: calls.filter((c) => c.crm.opportunityCreated).length,
      complaints: calls.filter((c) => c.crm.complaintOpen).length,
      competitorMentions: calls.filter((c) => c.competitorMentions.length > 0).length,
      reliable: calls.length >= MIN_SAMPLE_SIZE,
    };
  }).sort((a, b) => b.analysed - a.analysed);
}

// ---------- Funnel ----------
export interface FunnelStage { label: string; count: number; source: 'transcript' | 'crm' }

export function callFunnel(current: CallRecord[], analysed: CallRecord[]): FunnelStage[] {
  return [
    { label: 'Total calls', count: current.length, source: 'transcript' },
    { label: 'Connected', count: current.filter((c) => c.connected).length, source: 'transcript' },
    { label: 'Meaningful (>60s)', count: current.filter((c) => c.meaningful).length, source: 'transcript' },
    { label: 'Interest shown', count: analysed.filter((c) => c.intent === 'medium' || c.intent === 'high').length, source: 'transcript' },
    { label: 'High purchase readiness', count: analysed.filter((c) => c.intent === 'high').length, source: 'transcript' },
    { label: 'Opportunity (CRM)', count: current.filter((c) => c.crm.opportunityCreated).length, source: 'crm' },
    { label: 'Order confirmed (CRM)', count: current.filter((c) => c.crm.orderConfirmed).length, source: 'crm' },
  ];
}

// ---------- Emerging issues ----------
export interface EmergingItem { label: string; kind: string; current: number; previous: number; risePct: number }

export function emergingIssues(d: FilteredData): EmergingItem[] {
  const items: EmergingItem[] = [];
  const scale = d.analysedPrev.length ? d.analysed.length / d.analysedPrev.length : 1;
  const add = (label: string, kind: string, cur: number, prevRaw: number) => {
    const prev = prevRaw * scale; // normalise for period volume
    if (cur >= 4 && cur > prev * 1.4) {
      items.push({ label, kind, current: cur, previous: prevRaw, risePct: prev ? ((cur - prev) / prev) * 100 : 100 });
    }
  };
  const faqs = faqRows(d.analysed, d.analysedPrev);
  for (const f of faqs) add(f.standardized, 'FAQ rising', f.calls, f.prevCalls);
  const objs = objectionRows(d.analysed, d.analysedPrev);
  for (const o of objs) add(o.type, 'Objection rising', o.calls, o.prevCalls);
  const dissat = new Map<string, number>();
  const dissatPrev = new Map<string, number>();
  for (const c of d.analysed) for (const t of c.dissatisfactionThemes) dissat.set(t, (dissat.get(t) ?? 0) + 1);
  for (const c of d.analysedPrev) for (const t of c.dissatisfactionThemes) dissatPrev.set(t, (dissatPrev.get(t) ?? 0) + 1);
  for (const [t, n] of dissat) add(t, 'Dissatisfaction rising', n, dissatPrev.get(t) ?? 0);
  return items.sort((a, b) => b.risePct - a.risePct).slice(0, 8);
}

// ---------- Actions ----------
export function allActions(calls: CallRecord[]): NextAction[] {
  return calls.flatMap((c) => c.actions);
}

// ---------- Agent rows ----------
export interface AgentRow extends SegmentRow {
  employeeId: string;
  name: string;
  team: string;
  manager: string;
  scores: { label: string; value: number }[];
  complianceFails: number;
  avgTalkPct: number | null;
  talkSample: number;
  coachingNotes: string[];
}

export function agentRows(analysed: CallRecord[]): AgentRow[] {
  return segmentRows(analysed, (c) => c.employeeId).map((seg) => {
    const emp = EMPLOYEES.find((e) => e.id === seg.key)!;
    const calls = analysed.filter((c) => c.employeeId === seg.key && c.quality);
    const dims: [string, (c: CallRecord) => number][] = [
      ['Opening', (c) => c.quality!.opening],
      ['Discovery', (c) => c.quality!.discovery],
      ['Solution relevance', (c) => c.quality!.solutionRelevance],
      ['FAQ handling', (c) => c.quality!.faqHandling],
      ['Objection handling', (c) => c.quality!.objectionHandling],
      ['Next-step clarity', (c) => c.quality!.nextStepClarity],
      ['Listening', (c) => c.quality!.listening],
      ['Professionalism', (c) => c.quality!.professionalism],
      ['Script adherence', (c) => c.quality!.scriptAdherence],
    ];
    const talkCalls = calls.filter((c) => c.talk);
    return {
      ...seg,
      employeeId: seg.key,
      name: emp?.name ?? seg.key,
      team: emp?.team ?? '—',
      manager: emp?.manager ?? '—',
      scores: dims.map(([label, fn]) => ({ label, value: Math.round(avg(calls.map(fn))) })),
      complianceFails: calls.filter((c) => c.quality!.complianceFail).length,
      avgTalkPct: talkCalls.length >= 5 ? Math.round(avg(talkCalls.map((c) => c.talk!.agentTalkPct))) : null,
      talkSample: talkCalls.length,
      coachingNotes: uniq(calls.map((c) => c.quality!.coachingNote).filter(Boolean) as string[]).slice(0, 2),
    };
  });
}
