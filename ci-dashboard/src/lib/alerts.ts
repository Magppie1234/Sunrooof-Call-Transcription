/**
 * Alert rules engine — rule definitions documented in docs/09-alert-sla-rules.md.
 * Alerts are DERIVED from call/action data; critical alerts require manual review
 * before any customer-facing response (see Data & AI Governance).
 */
import type { AlertItem, CallRecord } from '../types/domain';
import { faqRows, objectionRows, segmentRows, uniq } from './metrics';
import type { FilteredData } from './filters';

let seq = 0;
const mk = (
  severity: AlertItem['severity'], type: string, reason: string, evidence: string, recommended: string,
  deadlineHours: number, now: Date,
  opts: { customerName?: string | null; callId?: string | null; ownerEmployeeId?: string | null } = {},
): AlertItem => ({
  id: `AL-${String(++seq).padStart(3, '0')}`,
  severity, type, reason, evidence, recommended,
  customerName: opts.customerName ?? null,
  callId: opts.callId ?? null,
  ownerEmployeeId: opts.ownerEmployeeId ?? null,
  deadline: new Date(now.getTime() + deadlineHours * 3600_000).toISOString(),
  status: 'open',
});

export function deriveAlerts(d: FilteredData, now = new Date()): AlertItem[] {
  seq = 0;
  const alerts: AlertItem[] = [];
  const { analysed } = d;
  const ctx = (c: CallRecord) => ({ customerName: c.customerName, callId: c.id, ownerEmployeeId: c.employeeId });

  // Derived here rather than read off a risk label: the extraction emits
  // free-text risks, so relying on one exact phrase meant this rule never
  // fired on real data. A customer with 2+ negative calls in the window is
  // repeat-negative by definition.
  const negPerCustomer = new Map<string, number>();
  for (const c of analysed) {
    if (c.sentiment?.overall === 'negative') {
      negPerCustomer.set(c.customerId, (negPerCustomer.get(c.customerId) ?? 0) + 1);
    }
  }
  const repeatNegative = new Set(
    [...negPerCustomer.entries()].filter(([, n]) => n >= 2).map(([id]) => id),
  );
  const repeatNegativeSeen = new Set<string>();

  // --- Per-call rules ---
  for (const c of analysed) {
    if (c.intent === 'high' && !c.actions.some((a) => a.status !== 'rejected')) {
      alerts.push(mk('high', 'High-intent, no follow-up', 'High purchase-readiness customer has no follow-up action scheduled.', `Purchase readiness ${c.purchaseReadiness?.score}/100 on ${c.id}; no committed or approved action.`, 'Assign an owner and schedule a follow-up call within 24 hours.', 24, now, ctx(c)));
    }
    for (const a of c.actions) {
      if (a.slaStatus === 'overdue' && ['Share quotation', 'Call back', 'Schedule meeting', 'Arrange site visit'].includes(a.action)) {
        alerts.push(mk('high', 'Commitment overdue', `"${a.action}" promised to the customer is past its due date.`, `Action ${a.id} due ${new Date(a.dueDate).toLocaleDateString('en-IN')} — still ${a.status}.`, 'Complete today and apologise for the delay; manager to review workload.', 12, now, ctx(c)));
      }
    }
    if (c.sentiment && c.sentiment.closing < -0.5) {
      alerts.push(mk('critical', 'Severe-negative customer', 'Customer ended the call in a severely negative state.', `Closing sentiment ${c.sentiment.closing} (text-based) on ${c.id}. Themes: ${c.dissatisfactionThemes.join('; ') || 'see transcript'}.`, 'Manager to personally call back within 4 hours.', 4, now, ctx(c)));
    }
    // One alert per customer, not per negative call.
    if (repeatNegative.has(c.customerId) && !repeatNegativeSeen.has(c.customerId)) {
      repeatNegativeSeen.add(c.customerId);
      alerts.push(mk('high', 'Repeat-negative customer', 'Customer has been negative across multiple calls.', `Customer ${c.customerName} negative on ${negPerCustomer.get(c.customerId)} calls in this period, most recently ${c.id}.`, 'Escalate to retention owner; review full call history before contact.', 24, now, ctx(c)));
    }
    if (c.sentiment?.unresolvedNegative && c.crm.complaintOpen) {
      alerts.push(mk('critical', 'Unresolved complaint', 'Complaint call ended without resolution.', `${c.id}: complaint open in CRM, negative close, no resolution recorded.`, 'Service manager to own resolution; respond within SLA.', 8, now, ctx(c)));
    }
    if (c.risks.some((r) => r.includes('cancell') || r.includes('refund') || r.includes('Cancel'))) {
      alerts.push(mk('critical', 'Cancellation / refund risk', 'Customer indicated possible cancellation or refund.', `Risk noted on ${c.id}: ${c.risks.find((r) => r.toLowerCase().includes('cancel') || r.includes('refund'))}`, 'Retention call by senior manager within 4 hours; do not send templated replies.', 4, now, ctx(c)));
    }
    if (c.risks.some((r) => r.includes('legal'))) {
      alerts.push(mk('critical', 'Legal threat', 'Customer mentioned legal action.', `${c.id}: legal action referenced in conversation.`, 'Route to leadership + legal immediately. Manual transcript review required.', 2, now, ctx(c)));
    }
    for (const flag of c.complianceFlags) {
      const isCritical = flag.includes('personal number') || flag.includes('PII');
      alerts.push(mk(isCritical ? 'critical' : 'high', isCritical ? 'Sensitive-data / payment risk' : 'Compliance failure', flag, `Flagged on ${c.id} (agent ${c.employeeId}).`, 'Quality team to review recording and confirm; coaching or disciplinary action per policy.', isCritical ? 4 : 48, now, ctx(c)));
    }
    if (c.meaningful && c.transcribed && c.transcriptionConfidence < 0.6) {
      alerts.push(mk('medium', 'Low transcription confidence', 'Transcript confidence below the aggregation threshold.', `${c.id}: confidence ${(c.transcriptionConfidence * 100).toFixed(0)}%. Excluded from management aggregates.`, 'Check audio quality / language model coverage for this line.', 72, now, ctx(c)));
    }
  }

  // --- Aggregate rules (trend spikes) ---
  const faqs = faqRows(d.analysed, d.analysedPrev);
  for (const f of faqs) {
    if (f.calls >= 6 && f.prevCalls > 0 && f.calls > f.prevCalls * 1.6) {
      alerts.push(mk('medium', 'FAQ spike', `"${f.standardized}" is rising sharply.`, `${f.calls} calls this period vs ${f.prevCalls} in the prior period.`, 'Update website FAQ / scripts; brief the team in the next huddle.', 72, now));
    }
    if (f.unanswered >= 4 && f.unanswered / f.calls > 0.35) {
      alerts.push(mk('high', 'Emerging unanswered question', `Agents repeatedly cannot answer: "${f.standardized}".`, `${f.unanswered} of ${f.calls} occurrences went unanswered.`, 'Add an approved answer to the knowledge base and train the team this week.', 48, now));
    }
  }
  const objs = objectionRows(d.analysed, d.analysedPrev);
  for (const o of objs) {
    if (o.calls >= 8 && o.prevCalls > 0 && o.calls > o.prevCalls * 1.6) {
      alerts.push(mk('medium', 'Objection spike', `"${o.type}" objection is rising.`, `${o.calls} calls vs ${o.prevCalls} prior period.`, 'Review pricing/positioning; refresh objection-handling playbook.', 72, now));
    }
  }
  const compCur = analysed.filter((c) => c.competitorMentions.length).length;
  const compPrev = d.analysedPrev.filter((c) => c.competitorMentions.length).length;
  if (compCur >= 10 && compPrev > 0 && compCur > compPrev * 1.5) {
    alerts.push(mk('medium', 'Competitor mentions rising', 'Competitor mentions increased significantly vs the prior period.', `${compCur} calls vs ${compPrev} in prior period.`, 'Sales leadership to review competitive positioning and win/loss notes.', 96, now));
  }
  for (const seg of segmentRows(analysed, (c) => c.region)) {
    const prevSeg = segmentRows(d.analysedPrev, (c) => c.region).find((s) => s.key === seg.key);
    if (seg.reliable && prevSeg && prevSeg.analysed >= 10) {
      const negRate = seg.negative / seg.analysed;
      const prevNegRate = prevSeg.negative / prevSeg.analysed;
      if (negRate > prevNegRate * 1.5 && seg.negative >= 5) {
        alerts.push(mk('high', 'Region sentiment declining', `${seg.key} region shows a sharp rise in negative calls.`, `Negative rate ${(negRate * 100).toFixed(0)}% vs ${(prevNegRate * 100).toFixed(0)}% prior (n=${seg.analysed}).`, 'Regional manager to review negative calls and root causes this week.', 72, now));
      }
    }
  }
  const highValueNoEsc = analysed.filter((c) => (c.crm.revenueInfluenced ?? 0) > 1_000_000 && c.sentiment!.overall === 'negative');
  for (const c of uniq(highValueNoEsc)) {
    alerts.push(mk('high', 'High-value customer needs escalation', 'High-value (verified revenue) customer had a negative conversation.', `${c.customerName}: order value ${(c.crm.revenueInfluenced! / 100000).toFixed(1)}L, negative call ${c.id}.`, 'Escalate to business head; personal outreach within 24 hours.', 24, now, ctx(c)));
  }

  const order = { critical: 0, high: 1, medium: 2 };
  return alerts.sort((a, b) => order[a.severity] - order[b.severity]);
}
