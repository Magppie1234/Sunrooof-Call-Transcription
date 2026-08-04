import { useNavigate } from 'react-router-dom';
import { PageHead, useDrill } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, RankBars, Heatmap, Funnel, Pill, SampleNote, EmptyState, Prov } from '../components/ui';
import { VolumeTrend, SentimentTrend, RelationScatter } from '../components/charts';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useAlerts, useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import {
  kpiSummary, dailyTrend, faqRows, objectionRows, segmentRows, callFunnel, emergingIssues, agentRows, allActions,
} from '../lib/metrics';
import { fmtINR, fmtInt, fmtPct, pctVal } from '../lib/format';
import { MIN_SAMPLE_SIZE } from '../config';

const pctFmt = (v: number) => `${v.toFixed(1)}%`;

export default function ExecutiveOverview() {
  const { data: d, loading, error } = useFilteredData();
  const { data: alerts } = useAlerts();
  const { filters } = useAppState();
  const drill = useDrill();
  const navigate = useNavigate();

  if (loading && !d) return <Loading label="Computing executive summary…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const k = kpiSummary(d);
  const cur = k.cur; const prev = k.prev;
  const curTrend = dailyTrend(d.analysed, d.windows.currentStart, d.windows.currentEnd);
  const prevTrend = dailyTrend(d.analysedPrev, d.windows.prevStart, d.windows.prevEnd);
  const faqs = faqRows(d.analysed, d.analysedPrev).slice(0, 7);
  const objections = objectionRows(d.analysed, d.analysedPrev).slice(0, 7);
  const regions = segmentRows(d.analysed, (c) => c.region);
  const funnel = callFunnel(d.current, d.analysed);
  const emerging = emergingIssues(d);
  const agents = agentRows(d.analysed).filter((a) => a.analysed >= MIN_SAMPLE_SIZE);
  const actions = allActions(d.analysed);
  const actionsDone = actions.filter((a) => a.status === 'completed').length;
  const highIntentCalls = d.analysed
    .filter((c) => c.intent === 'high')
    .sort((a, b) => (b.purchaseReadiness?.score ?? 0) - (a.purchaseReadiness?.score ?? 0))
    .slice(0, 6);
  const criticalAlerts = (alerts ?? []).filter((a) => a.severity === 'critical' && a.status === 'open').slice(0, 6);

  const sentCols = ['Positive', 'Neutral', 'Negative', 'High intent'];
  const nAnalysed = `of ${fmtInt(cur.analysed)} analysed`;

  return (
    <>
      <PageHead title="Executive Overview"
        desc="What customers are saying, where opportunities and risks sit, how the team is performing, and what needs action today. Click any card or chart to drill into the underlying calls."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Total calls" prov="kpi.volume" value={cur.totalCalls} prev={prev.totalCalls} onClick={() => navigate('/calls')} />
        <KpiCard label="Successfully transcribed" prov="kpi.coverage" value={cur.transcribed} prev={prev.transcribed} denomNote={`of ${fmtInt(cur.totalCalls)} calls`} onClick={() => navigate('/data')} />
        <KpiCard label="Transcription coverage" prov="kpi.coverage" value={cur.coveragePct} prev={prev.coveragePct} format={pctFmt} onClick={() => navigate('/data')} />
        <KpiCard label="Unique customers" prov="kpi.customers" value={cur.uniqueCustomers} prev={prev.uniqueCustomers} onClick={() => navigate('/calls')} />
        <KpiCard label="Connected & meaningful conversations" prov="kpi.meaningful" value={cur.meaningful} prev={prev.meaningful} denomNote={`of ${fmtInt(cur.totalCalls)} calls`} onClick={() => navigate('/calls')} />
        <KpiCard label="Positive sentiment calls" prov="sentiment.overall" value={cur.positive} prev={prev.positive} denomNote={nAnalysed} accent="var(--good)" onClick={() => drill({ sentiment: 'positive' })} />
        <KpiCard label="Neutral sentiment calls" prov="sentiment.overall" value={cur.neutral} prev={prev.neutral} denomNote={nAnalysed} accent="var(--baseline)" onClick={() => drill({ sentiment: 'neutral' })} />
        <KpiCard label="Negative sentiment calls" prov="sentiment.overall" value={cur.negative} prev={prev.negative} denomNote={nAnalysed} accent="var(--critical)" invertDelta onClick={() => drill({ sentiment: 'negative' })} />
        <KpiCard label="Sentiment improvement rate" prov="sentiment.journey" value={pctVal(cur.sentimentImproved, cur.analysed)} prev={pctVal(prev.sentimentImproved, prev.analysed)} format={pctFmt} denomNote={nAnalysed} accent="var(--good)" onClick={() => navigate('/voice')} />
        <KpiCard label="High purchase-intent customers" prov="sales.readiness" value={cur.highIntent} prev={prev.highIntent} accent="var(--good)" onClick={() => drill({ intent: 'high' })} />
        <KpiCard label="Average agent quality score" prov="agent.quality" value={cur.avgQuality} prev={prev.avgQuality} format={(v) => v ? v.toFixed(0) + ' / 100' : '—'} denomNote={nAnalysed} onClick={() => navigate('/agents')} />
        <KpiCard label="Calls with a clear next action" prov="actions.list" value={pctVal(cur.withNextAction, cur.analysed)} prev={pctVal(prev.withNextAction, prev.analysed)} format={pctFmt} denomNote={nAnalysed} onClick={() => navigate('/actions')} />
        <KpiCard label="Actions due today" prov="actions.sla" value={cur.actionsDueToday} accent="var(--warning)" onClick={() => navigate('/actions')} />
        <KpiCard label="Overdue actions" prov="actions.sla" value={cur.actionsOverdue} prev={prev.actionsOverdue} accent="var(--critical)" invertDelta onClick={() => navigate('/actions')} />
        <KpiCard label="Unanswered customer questions" prov="faq.answerQuality" value={cur.unansweredQuestions} prev={prev.unansweredQuestions} accent="var(--serious)" invertDelta onClick={() => navigate('/faqs')} />
        <KpiCard label="Critical complaints" prov="alerts.rules" value={cur.criticalComplaints} prev={prev.criticalComplaints} accent="var(--critical)" invertDelta onClick={() => drill({ outcome: 'Complaint raised', sentiment: 'negative' })} />
        <KpiCard label="Compliance alerts" prov="agent.compliance" value={cur.complianceAlerts} prev={prev.complianceAlerts} accent="var(--critical)" invertDelta onClick={() => drill({ compliance: 'flagged' })} />
        <KpiCard label="Call → opportunity conversion" prov="sales.funnelCrm" value={pctVal(cur.opportunities, cur.meaningful)} prev={pctVal(prev.opportunities, prev.meaningful)} format={pctFmt} denomNote={`of ${fmtInt(cur.meaningful)} meaningful · CRM-verified`} onClick={() => navigate('/sales')} />
        <KpiCard label="Call → order conversion" prov="sales.revenue" value={pctVal(cur.orders, cur.meaningful)} prev={pctVal(prev.orders, prev.meaningful)} format={pctFmt} denomNote={`of ${fmtInt(cur.meaningful)} meaningful · CRM-verified`} accent="var(--good)" onClick={() => drill({ outcome: 'Order confirmed' })} />
        <KpiCard label="Revenue influenced (verified CRM)" prov="sales.revenue" value={cur.revenue} prev={prev.revenue} format={fmtINR} denomNote={`${cur.revenueVerifiedOrders} verified orders`} accent="var(--good)" onClick={() => drill({ outcome: 'Order confirmed' })} />
      </div>

      <div className="section-title">Trends & drivers <span className="sub">{scopeNote(d, filters.preset)}</span></div>
      <div className="two-col">
        <Card title={<>Call volume trend <Prov k="kpi.volume" /></>} sub="Analysed calls per day, current vs comparison period">
          <VolumeTrend current={curTrend} previous={prevTrend} />
        </Card>
        <Card title={<>Sentiment trend <Prov k="sentiment.overall" /></>} sub="Share of analysed calls per day (text-based sentiment)">
          <SentimentTrend days={curTrend} />
        </Card>
        <Card title={<>Top FAQs <Prov k="faq.questions" /></>} sub={<>Calls containing each question · <SampleNote n={d.analysed.length} /></>}
          right={<a onClick={() => navigate('/faqs')} style={{ fontSize: 12, cursor: 'pointer' }}>All FAQs →</a>}>
          <RankBars items={faqs.map((f) => ({
            label: f.standardized, value: f.calls,
            sub: `${fmtPct(f.unanswered, f.calls)} unanswered · ${f.customers} customers`,
            color: f.unanswered / Math.max(f.calls, 1) > 0.3 ? 'var(--serious)' : 'var(--s1)',
            onClick: () => drill({ faqCategory: f.category }),
          }))} />
        </Card>
        <Card title={<>Top objections <Prov k="sales.objections" /></>} sub="Calls where the objection was raised"
          right={<a onClick={() => navigate('/sales')} style={{ fontSize: 12, cursor: 'pointer' }}>Objection intelligence →</a>}>
          <RankBars items={objections.map((o) => ({
            label: o.type, value: o.calls,
            sub: `${fmtPct(o.unresolved, o.calls)} unresolved`,
            color: o.unresolved / Math.max(o.calls, 1) > 0.35 ? 'var(--serious)' : 'var(--s1)',
            onClick: () => drill({ objection: o.type }),
          }))} />
        </Card>
        <Card title={<>Region-wise sentiment heatmap <Prov k="region.geo" /></>} sub="Rate per 100 analysed calls in each region · click a cell to drill">
          <Heatmap rows={regions.map((r) => `${r.key} (n=${r.analysed}${r.reliable ? '' : ' ⚠ low sample'})`)} cols={sentCols}
            value={(rowLabel, col) => {
              const r = regions.find((x) => rowLabel.startsWith(x.key));
              if (!r || r.analysed === 0) return null;
              const v = col === 'Positive' ? r.positive : col === 'Neutral' ? r.analysed - r.positive - r.negative : col === 'Negative' ? r.negative : r.highIntent;
              return (v / r.analysed) * 100;
            }}
            display={(v) => v.toFixed(0)}
            onCell={(rowLabel, col) => {
              const r = regions.find((x) => rowLabel.startsWith(x.key));
              if (!r) return;
              drill({ region: r.key, ...(col === 'High intent' ? { intent: 'high' } : { sentiment: col.toLowerCase() }) });
            }} />
        </Card>
        <Card title={<>Call-to-order funnel <Prov k="sales.funnelCrm" /></>} sub="Transcript-inferred stages vs CRM-verified stages, labelled per bar">
          <Funnel stages={funnel} />
        </Card>
        <Card title={<>Agent quality vs conversion <Prov k="agent.quality" /></>} sub={`Each dot is an agent with ≥${MIN_SAMPLE_SIZE} analysed calls · quadrant lines at the mean`}>
          <RelationScatter xLabel="Avg quality score" yLabel="Opportunity rate" xUnit=""
            points={agents.map((a) => ({ name: a.name.split(' ')[0], x: a.avgQuality, y: pctVal(a.opportunities, a.analysed), n: a.analysed }))}
            onPoint={(name) => {
              const a = agents.find((x) => x.name.split(' ')[0] === name);
              if (a) drill({ employee: a.employeeId });
            }} />
        </Card>
        <Card title={<>Action completion & overdue <Prov k="actions.sla" /></>} sub={`${fmtInt(actions.length)} actions created from analysed calls in this period`}>
          {actions.length === 0 ? <EmptyState message="No actions in this period." /> : (
            <RankBars max={actions.length} valueFmt={(v) => `${fmtInt(v)} (${fmtPct(v, actions.length)})`} items={[
              { label: 'Completed', value: actionsDone, color: 'var(--good)', onClick: () => navigate('/actions') },
              { label: 'On track', value: actions.filter((a) => a.slaStatus === 'on_track').length, color: 'var(--s1)', onClick: () => navigate('/actions') },
              { label: 'Due today', value: actions.filter((a) => a.slaStatus === 'due_today').length, color: 'var(--warning)', onClick: () => navigate('/actions') },
              { label: 'Overdue', value: actions.filter((a) => a.slaStatus === 'overdue').length, color: 'var(--critical)', onClick: () => navigate('/actions') },
            ]} />
          )}
        </Card>
      </div>

      <div className="section-title">Needs attention now</div>
      <div className="three-col">
        <Card title={<>Emerging customer issues <Prov k="voc.themes" /></>} sub="Rising vs comparison period (volume-normalised)">
          {emerging.length === 0 ? <EmptyState message="No unusual rises detected this period." /> : (
            <div>
              {emerging.map((e) => (
                <div key={e.kind + e.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0', borderBottom: '1px solid #eeede8', fontSize: 12.5 }}>
                  <div><Pill tone="warning">{e.kind}</Pill> <span style={{ marginLeft: 6 }}>{e.label}</span></div>
                  <div className="rankbar-val">{e.current} <span className="cell-sub">vs {e.previous}</span></div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title={<>High-priority opportunities <Prov k="sales.readiness" /></>} sub="Highest purchase-readiness customers this period">
          {highIntentCalls.length === 0 ? <EmptyState message="No high-readiness calls in this period." /> : (
            <div>
              {highIntentCalls.map((c) => (
                <div key={c.id} className="rankbar-row clickable" style={{ gridTemplateColumns: '1fr auto' }} onClick={() => navigate(`/calls/${c.id}`)}>
                  <div className="rankbar-label">{c.customerName}<div className="cell-sub">{c.productSeries} · {c.city} · {c.outcome}</div></div>
                  <Pill tone="good">PR {c.purchaseReadiness?.score}/100</Pill>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title={<>Critical risk panel <Prov k="alerts.rules" /></>} sub="Open critical alerts (manual review required)"
          right={<a onClick={() => navigate('/alerts')} style={{ fontSize: 12, cursor: 'pointer' }}>All alerts →</a>}>
          {criticalAlerts.length === 0 ? <EmptyState message="No open critical alerts. " hint="Alerts appear here when severity rules trigger." /> : (
            <div>
              {criticalAlerts.map((a) => (
                <div key={a.id} className="rankbar-row clickable" style={{ gridTemplateColumns: '1fr auto' }}
                  onClick={() => a.callId ? navigate(`/calls/${a.callId}`) : navigate('/alerts')}>
                  <div className="rankbar-label"><Pill tone="critical">{a.type}</Pill><div className="cell-sub">{a.customerName ?? 'Aggregate'} — {a.reason}</div></div>
                  <span className="cell-sub">due {new Date(a.deadline).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
