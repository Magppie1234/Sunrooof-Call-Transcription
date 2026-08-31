import { useNavigate } from 'react-router-dom';
import { PageHead, useDrill } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, RankBars, DataTable, Pill, exportCsv, type Column, EmptyState, SampleNote, Prov } from '../components/ui';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { objectionRows, avg, uniq, type ObjectionRow } from '../lib/metrics';
import { fmtInt, fmtPct, pctVal } from '../lib/format';

export default function Sales() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const drill = useDrill();
  const navigate = useNavigate();

  if (loading && !d) return <Loading label="Extracting sales signals…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const a = d.analysed;
  const salesCalls = a.filter((c) => c.purchaseReadiness !== null);
  const objs = objectionRows(a, d.analysedPrev);
  const withObjections = a.filter((c) => c.objections.length > 0);
  const quotes = a.filter((c) => c.outcome === 'Quotation requested' || c.actions.some((x) => x.action === 'Share quotation'));
  const demos = a.filter((c) => c.outcome === 'Demo scheduled');
  const siteVisits = a.filter((c) => c.outcome === 'Site visit scheduled' || c.actions.some((x) => x.action === 'Arrange site visit'));
  const drawings = a.filter((c) => c.actions.some((x) => x.action === 'Share design / drawings' || x.action === 'Arrange measurement'));
  const discounts = a.filter((c) => c.discountRequested);
  const crossSell = a.filter((c) => c.crossSell);

  const compCounts = new Map<string, number>();
  for (const c of a) for (const m of c.competitorMentions) compCounts.set(m, (compCounts.get(m) ?? 0) + 1);

  const signalCounts = new Map<string, number>();
  for (const c of a) for (const s of c.buyingSignals) signalCounts.set(s, (signalCounts.get(s) ?? 0) + 1);

  const budgetDist = new Map<string, number>();
  for (const c of salesCalls) budgetDist.set(c.budgetMentioned ?? 'Not mentioned', (budgetDist.get(c.budgetMentioned ?? 'Not mentioned') ?? 0) + 1);
  const timelineDist = new Map<string, number>();
  for (const c of salesCalls) timelineDist.set(c.timelineMentioned ?? 'Not mentioned', (timelineDist.get(c.timelineMentioned ?? 'Not mentioned') ?? 0) + 1);

  const needCounts = new Map<string, number>();
  for (const c of salesCalls) if (c.customerNeed) needCounts.set(c.customerNeed, (needCounts.get(c.customerNeed) ?? 0) + 1);

  const lost = a.filter((c) => c.outcome === 'Not interested');

  const objCols: Column<ObjectionRow>[] = [
    { key: 'type', label: 'Primary objection', render: (r) => <strong>{r.type}</strong>, sortVal: (r) => r.type },
    { key: 'calls', label: 'Calls', num: true, render: (r) => fmtInt(r.calls), sortVal: (r) => r.calls },
    {
      key: 'trend', label: 'vs prior', num: true, render: (r) => {
        const diff = r.calls - r.prevCalls;
        return <span className={`delta ${diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat'}`}>{diff > 0 ? '+' : ''}{diff}</span>;
      }, sortVal: (r) => r.calls - r.prevCalls,
    },
    { key: 'intensity', label: 'High intensity', num: true, render: (r) => `${r.highIntensity} (${fmtPct(r.highIntensity, r.calls)})`, sortVal: (r) => pctVal(r.highIntensity, r.calls) },
    {
      key: 'res', label: 'Resolution', render: (r) => (
        <div className="chip-row">
          {r.resolved > 0 && <Pill tone="good">{r.resolved} resolved</Pill>}
          {r.partial > 0 && <Pill tone="warning">{r.partial} partial</Pill>}
          {r.unresolved > 0 && <Pill tone="critical">{r.unresolved} unresolved</Pill>}
        </div>
      ), sortVal: (r) => pctVal(r.unresolved, r.calls),
    },
    { key: 'react', label: 'Positive reaction', num: true, render: (r) => `${r.positiveReactionPct.toFixed(0)}%`, sortVal: (r) => r.positiveReactionPct },
    { key: 'tech', label: 'Most-used technique', render: (r) => <span style={{ fontSize: 12 }}>{r.topTechnique}</span> },
  ];

  return (
    <>
      <PageHead title="Sales & Objection Intelligence"
        desc="Needs, buying signals, purchase readiness and the objection taxonomy — with how agents responded and how customers reacted. Objections are conversation evidence, not verified loss reasons: lost-deal attribution requires CRM confirmation."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Avg purchase-readiness score" prov="sales.readiness" value={avg(salesCalls.map((c) => c.purchaseReadiness!.score))} format={(v) => `${v.toFixed(0)} / 100`} denomNote={`n = ${fmtInt(salesCalls.length)} sales calls · not a validated conversion probability`} />
        <KpiCard label="High purchase readiness" prov="sales.readiness" value={salesCalls.filter((c) => c.intent === 'high').length} denomNote={`of ${fmtInt(salesCalls.length)} sales calls`} accent="var(--good)" onClick={() => drill({ intent: 'high' })} />
        <KpiCard label="Quotations requested" prov="actions.list" value={quotes.length} onClick={() => drill({ outcome: 'Quotation requested' })} />
        <KpiCard label="Demos scheduled" prov="actions.list" value={demos.length} onClick={() => drill({ outcome: 'Demo scheduled' })} />
        <KpiCard label="Site visits agreed" prov="actions.list" value={siteVisits.length} onClick={() => drill({ outcome: 'Site visit scheduled' })} />
        <KpiCard label="Design / measurement requests" prov="actions.list" value={drawings.length} />
        <KpiCard label="Discount requests" prov="sales.objections" value={discounts.length} denomNote={`${fmtPct(discounts.length, a.length)} of analysed`} accent="var(--warning)" onClick={() => drill({ objection: 'Price / discount' })} />
        <KpiCard label="Cross-sell / upsell openings" prov="sales.readiness" value={crossSell.length} accent="var(--s7)" />
        <KpiCard label="Calls mentioning competitors" prov="sales.competitors" value={a.filter((c) => c.competitorMentions.length > 0).length} denomNote={`of ${fmtInt(a.length)} analysed`} accent="var(--s2)" />
        <KpiCard label="Decision-maker confirmed on call" prov="sales.readiness" value={salesCalls.filter((c) => c.decisionMaker === 'yes').length} denomNote={`of ${fmtInt(salesCalls.length)} · “Unknown” when not mentioned`} />
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <Card title={<>Customer needs <Prov k="sales.readiness" /></>} sub={<>What customers are buying for · <SampleNote n={salesCalls.length} label="sales calls" /></>}>
          <RankBars items={[...needCounts.entries()].sort((x, y) => y[1] - x[1]).slice(0, 8).map(([label, value]) => ({ label, value }))} />
        </Card>
        <Card title={<>Buying signals <Prov k="sales.readiness" /></>} sub="Explicit signals captured from transcripts">
          <RankBars items={[...signalCounts.entries()].sort((x, y) => y[1] - x[1]).map(([label, value]) => ({ label, value, color: 'var(--good)' }))} />
        </Card>
        <Card title={<>Stated budget <Prov k="sales.budget" /></>} sub="“Not mentioned” is reported honestly — never assumed">
          <RankBars items={[...budgetDist.entries()].sort((x, y) => y[1] - x[1]).map(([label, value]) => ({
            label, value, sub: fmtPct(value, salesCalls.length),
            color: label === 'Not mentioned' ? 'var(--baseline)' : 'var(--s1)',
          }))} />
        </Card>
        <Card title={<>Expected purchase timeline <Prov k="sales.budget" /></>} sub="As stated by the customer on the call">
          <RankBars items={[...timelineDist.entries()].sort((x, y) => y[1] - x[1]).map(([label, value]) => ({
            label, value, sub: fmtPct(value, salesCalls.length),
            color: label === 'Not mentioned' ? 'var(--baseline)' : 'var(--s1)',
          }))} />
        </Card>
        <Card title={<>Competitor mentions <Prov k="sales.competitors" /></>} sub="Calls where each competitor came up">
          <RankBars items={[...compCounts.entries()].sort((x, y) => y[1] - x[1]).map(([label, value]) => ({ label, value, color: 'var(--s2)' }))}
            emptyMessage="No competitor mentions in this period." />
        </Card>
        <Card title={<>Hesitation & lost reasons (transcript evidence) <Prov k="sales.objections" /></>} sub="⚠ Not confirmed loss reasons — verify against CRM before acting">
          {lost.length === 0 ? <EmptyState message="No 'Not interested' outcomes this period." /> : (
            <RankBars items={(() => {
              const reasons = new Map<string, number>();
              for (const c of lost) {
                const key = c.objections[0]?.type ?? 'No stated reason';
                reasons.set(key, (reasons.get(key) ?? 0) + 1);
              }
              return [...reasons.entries()].sort((x, y) => y[1] - x[1]).map(([label, value]) => ({
                label, value, sub: fmtPct(value, lost.length), color: 'var(--serious)',
                onClick: label !== 'No stated reason' ? () => drill({ objection: label, outcome: 'Not interested' }) : undefined,
              }));
            })()} />
          )}
        </Card>
      </div>

      <div className="section-title">Objection taxonomy
        <button className="btn small" onClick={() => exportCsv('objections.csv',
          ['Objection', 'Calls', 'Prior period', 'High intensity', 'Resolved', 'Partial', 'Unresolved', 'Positive reaction %', 'Top technique'],
          objs.map((r) => [r.type, r.calls, r.prevCalls, r.highIntensity, r.resolved, r.partial, r.unresolved, r.positiveReactionPct.toFixed(0), r.topTechnique]))}>
          Export CSV
        </button>
        <span className="sub">{fmtInt(withObjections.length)} of {fmtInt(a.length)} analysed calls contained at least one objection · click a row for supporting calls & transcripts</span>
      </div>
      <Card>
        <DataTable columns={objCols} rows={objs} rowKey={(r) => r.type} initialSort={{ key: 'calls', dir: 'desc' }}
          onRow={(r) => drill({ objection: r.type })} />
      </Card>

      <div className="section-title">Recent high-intensity objections <span className="sub">with agent response — open the call for full transcript evidence</span></div>
      <Card>
        {(() => {
          const rows = a.flatMap((c) => c.objections.filter((o) => o.intensity === 'high').map((o) => ({ c, o }))).slice(0, 8);
          if (!rows.length) return <EmptyState message="No high-intensity objections this period." />;
          return rows.map(({ c, o }, i) => (
            <div key={`${c.id}-${i}`} className="rankbar-row clickable" style={{ gridTemplateColumns: '1fr auto' }} onClick={() => navigate(`/calls/${c.id}`)}>
              <div className="rankbar-label" style={{ whiteSpace: 'normal' }}>
                <Pill tone={o.resolution === 'resolved' ? 'good' : o.resolution === 'partial' ? 'warning' : 'critical'}>{o.type} · {o.resolution}</Pill>
                <div className="cell-sub" style={{ marginTop: 3 }}>“{o.statement}” — {c.customerName}, {c.city}. Technique: {o.technique}.</div>
              </div>
              <span className="cell-sub">{c.id} →</span>
            </div>
          ));
        })()}
      </Card>
      <div className="cell-sub" style={{ marginTop: 10 }}>
        Products discussed: {uniq(a.map((c) => c.productSeries)).length} series. Lead sources: {uniq(a.map((c) => c.leadSource)).length}. Purchase readiness is a weighted transcript score, not a conversion probability — see docs/08-scoring-methodology.md.
      </div>
    </>
  );
}
