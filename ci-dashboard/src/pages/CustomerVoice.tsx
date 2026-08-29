import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHead, useDrill } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, RankBars, Pill, SampleNote, DataTable, type Column, EmptyState, Prov } from '../components/ui';
import { SentimentTrend, SentimentSplit } from '../components/charts';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { dailyTrend, segmentRows, avg, uniq, type SegmentRow } from '../lib/metrics';
import { fmtInt, fmtPct, pctVal } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { CallRecord } from '../types/domain';

const EMOTIONS = ['frustration', 'confusion', 'hesitation', 'urgency', 'trust', 'interest', 'satisfaction'] as const;

const DIMS: { key: string; label: string; fn: (c: CallRecord) => string }[] = [
  { key: 'region', label: 'Region', fn: (c) => c.region },
  { key: 'state', label: 'State', fn: (c) => c.state },
  { key: 'city', label: 'City', fn: (c) => c.city },
  { key: 'product', label: 'Product series', fn: (c) => c.productSeries },
  { key: 'employee', label: 'Employee', fn: (c) => EMPLOYEES.find((e) => e.id === c.employeeId)?.name ?? c.employeeId },
  { key: 'team', label: 'Team', fn: (c) => EMPLOYEES.find((e) => e.id === c.employeeId)?.team ?? '—' },
  { key: 'stage', label: 'Lead stage', fn: (c) => c.crmStage },
  { key: 'campaign', label: 'Campaign', fn: (c) => c.campaign },
  { key: 'source', label: 'Lead source', fn: (c) => c.leadSource },
  { key: 'ctype', label: 'Customer type', fn: (c) => c.customerType },
  { key: 'direction', label: 'Call direction', fn: (c) => c.direction },
  { key: 'language', label: 'Language', fn: (c) => c.language },
  { key: 'outcome', label: 'Call outcome', fn: (c) => c.outcome },
];

function themeCounts(calls: CallRecord[], pickFn: (c: CallRecord) => string[]): { label: string; value: number }[] {
  const m = new Map<string, number>();
  for (const c of calls) for (const t of pickFn(c)) m.set(t, (m.get(t) ?? 0) + 1);
  return [...m.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).slice(0, 8);
}

interface ThemeDrillState { title: string; matches: CallRecord[] }

/** Every theme bar across this page drills into the same overlay: the exact
 * calls behind that count, each linking straight to its record. */
function ThemeDrillOverlay({ drill, onClose, onNavigate }: {
  drill: ThemeDrillState; onClose: () => void; onNavigate: (callId: string) => void;
}) {
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 50, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 16px', overflowY: 'auto' }}
      onClick={onClose}
    >
      <div style={{ width: 'min(640px, 100%)' }} onClick={(e) => e.stopPropagation()}>
        <Card title={drill.title} sub={`${drill.matches.length} call${drill.matches.length === 1 ? '' : 's'} — click any row to open the full record`}
          right={<button className="btn small" onClick={onClose}>✕ Close</button>}>
          {drill.matches.length === 0 ? <EmptyState message="No calls matched." /> : (
            <div>
              {drill.matches.map((c) => (
                <div key={c.id} className="rankbar-row clickable" style={{ gridTemplateColumns: '1fr auto' }} onClick={() => onNavigate(c.id)}>
                  <div className="rankbar-label">
                    {c.customerName}
                    <div className="cell-sub">{c.id} · {c.city || '—'} · {c.outcome}</div>
                  </div>
                  <Pill tone={sentimentToneFor(c)}>{c.sentiment ? c.sentiment.overall : 'n/a'}</Pill>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function sentimentToneFor(c: CallRecord): 'good' | 'critical' | 'neutral' {
  if (!c.sentiment) return 'neutral';
  return c.sentiment.overall === 'positive' ? 'good' : c.sentiment.overall === 'negative' ? 'critical' : 'neutral';
}

export default function CustomerVoice() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const drill = useDrill();
  const navigate = useNavigate();
  const [dim, setDim] = useState('region');
  const [themeDrill, setThemeDrill] = useState<ThemeDrillState | null>(null);

  if (loading && !d) return <Loading label="Analysing customer sentiment…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const a = d.analysed;
  const pos = a.filter((c) => c.sentiment!.overall === 'positive').length;
  const neg = a.filter((c) => c.sentiment!.overall === 'negative').length;
  const neu = a.length - pos - neg;
  const improved = a.filter((c) => c.sentiment!.shift > 0.2).length;
  const deteriorated = a.filter((c) => c.sentiment!.shift < -0.2).length;
  const unresolvedNeg = a.filter((c) => c.sentiment!.unresolvedNegative);
  const repeatNegCustomers = (() => {
    const negByCust = new Map<string, number>();
    for (const c of a) if (c.sentiment!.overall === 'negative') negByCust.set(c.customerId, (negByCust.get(c.customerId) ?? 0) + 1);
    return [...negByCust.values()].filter((n) => n >= 2).length;
  })();
  const trend = dailyTrend(a, d.windows.currentStart, d.windows.currentEnd);
  const dimDef = DIMS.find((x) => x.key === dim)!;
  const segs = segmentRows(a, dimDef.fn);

  const openTheme = (cardTitle: string, pickFn: (c: CallRecord) => string[], label: string) =>
    setThemeDrill({ title: `${cardTitle}: "${label}"`, matches: a.filter((c) => pickFn(c).includes(label)) });
  const themeBarItems = (cardTitle: string, pickFn: (c: CallRecord) => string[], color?: string) =>
    themeCounts(a, pickFn).map((i) => ({ ...i, color, onClick: () => openTheme(cardTitle, pickFn, i.label) }));

  const segCols: Column<SegmentRow>[] = [
    { key: 'key', label: dimDef.label, render: (r) => <strong>{r.key}</strong>, sortVal: (r) => r.key },
    { key: 'n', label: 'Analysed', num: true, render: (r) => <>{fmtInt(r.analysed)}{!r.reliable && <div className="cell-sub">⚠ low sample</div>}</>, sortVal: (r) => r.analysed },
    { key: 'pos', label: 'Positive / 100', num: true, render: (r) => pctVal(r.positive, r.analysed).toFixed(0), sortVal: (r) => pctVal(r.positive, r.analysed) },
    { key: 'neg', label: 'Negative / 100', num: true, render: (r) => pctVal(r.negative, r.analysed).toFixed(0), sortVal: (r) => pctVal(r.negative, r.analysed) },
    { key: 'shift', label: 'Avg shift', num: true, render: (r) => <span className={`delta ${r.avgShift > 0.05 ? 'up' : r.avgShift < -0.05 ? 'down' : 'flat'}`}>{r.avgShift > 0 ? '+' : ''}{r.avgShift.toFixed(2)}</span>, sortVal: (r) => r.avgShift },
    { key: 'hi', label: 'High intent', num: true, render: (r) => fmtInt(r.highIntent), sortVal: (r) => r.highIntent },
    { key: 'complaints', label: 'Complaints', num: true, render: (r) => fmtInt(r.complaints), sortVal: (r) => r.complaints },
  ];

  return (
    <>
      <PageHead title="Customer Voice & Sentiment"
        desc="Customer-side sentiment only — agent sentiment is never mixed in, and a negative customer is not treated as evidence of poor agent performance. All scores are text-based (transcript analysis); no voice-tone or acoustic emotion analysis is performed."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Positive calls" prov="sentiment.overall" value={pos} denomNote={`of ${fmtInt(a.length)} analysed`} accent="var(--good)" onClick={() => drill({ sentiment: 'positive' })} />
        <KpiCard label="Neutral calls" prov="sentiment.overall" value={neu} denomNote={`of ${fmtInt(a.length)} analysed`} accent="var(--baseline)" onClick={() => drill({ sentiment: 'neutral' })} />
        <KpiCard label="Negative calls" prov="sentiment.overall" value={neg} denomNote={`of ${fmtInt(a.length)} analysed`} accent="var(--critical)" invertDelta onClick={() => drill({ sentiment: 'negative' })} />
        <KpiCard label="Avg opening sentiment" prov="sentiment.journey" value={avg(a.map((c) => c.sentiment!.opening))} format={(v) => v.toFixed(2)} denomNote="scale −1 to +1 · text-based" />
        <KpiCard label="Avg mid-call sentiment" prov="sentiment.journey" value={avg(a.map((c) => c.sentiment!.mid))} format={(v) => v.toFixed(2)} denomNote="scale −1 to +1 · text-based" />
        <KpiCard label="Avg closing sentiment" prov="sentiment.journey" value={avg(a.map((c) => c.sentiment!.closing))} format={(v) => v.toFixed(2)} denomNote="scale −1 to +1 · text-based" />
        <KpiCard label="Improved during call" prov="sentiment.journey" value={improved} denomNote={`${fmtPct(improved, a.length)} of analysed`} accent="var(--good)" />
        <KpiCard label="Deteriorated during call" prov="sentiment.journey" value={deteriorated} denomNote={`${fmtPct(deteriorated, a.length)} of analysed`} accent="var(--serious)" invertDelta />
        <KpiCard label="Repeat-negative customers" prov="sentiment.overall" value={repeatNegCustomers} denomNote="≥2 negative calls in period" accent="var(--critical)" invertDelta onClick={() => drill({ sentiment: 'negative' })} />
        <KpiCard label="Negative & unresolved at call end" prov="sentiment.overall" value={unresolvedNeg.length} denomNote={`of ${fmtInt(neg)} negative calls`} accent="var(--critical)" invertDelta onClick={() => drill({ sentiment: 'negative' })} />
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <Card title={<>Sentiment mix <Prov k="sentiment.overall" /></>} sub={<SampleNote n={a.length} />}>
          <SentimentSplit positive={pos} neutral={neu} negative={neg} />
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 12.5, marginBottom: 6 }}>Emotional signals detected (text-based)</h3>
            <RankBars items={EMOTIONS.map((e) => ({
              label: e[0].toUpperCase() + e.slice(1),
              value: a.filter((c) => c.sentiment!.emotions.includes(e)).length,
              color: ['frustration', 'confusion'].includes(e) ? 'var(--serious)' : ['trust', 'satisfaction', 'interest'].includes(e) ? 'var(--good)' : 'var(--s1)',
            })).filter((i) => i.value > 0)} valueFmt={(v) => `${fmtInt(v)} (${fmtPct(v, a.length)})`} />
          </div>
        </Card>
        <Card title={<>Sentiment trend <Prov k="sentiment.overall" /></>} sub="Daily share of analysed calls · current period">
          <SentimentTrend days={trend} />
        </Card>
      </div>

      <div className="section-title">What customers are telling us</div>
      <div className="three-col">
        <Card title={<>Top appreciation themes <Prov k="voc.themes" /></>} sub="Calls where customers explicitly appreciated something — click a theme to see the calls">
          <RankBars items={themeBarItems('Appreciation', (c) => c.appreciationThemes, 'var(--good)')} />
        </Card>
        <Card title={<>Top dissatisfaction themes <Prov k="voc.themes" /></>} sub="Calls with explicit dissatisfaction — click a theme to see the calls">
          <RankBars items={themeBarItems('Dissatisfaction', (c) => c.dissatisfactionThemes, 'var(--serious)')} />
        </Card>
        <Card title={<>Product & feature requests <Prov k="voc.featureRequests" /></>} sub="Explicit asks captured from transcripts — click a request to see the calls">
          <RankBars items={themeBarItems('Feature request', (c) => c.featureRequests, 'var(--s7)')} />
        </Card>
        <Card title={<>Customer expectations <Prov k="voc.themes" /></>} sub="Stated expectations about process & timelines — click one to see the calls">
          <RankBars items={themeBarItems('Expectation', (c) => c.expectations)} />
        </Card>
        <Card title={<>Customer pain points <Prov k="voc.themes" /></>} sub="Problems customers described — click a pain point to see the calls">
          <RankBars items={themeBarItems('Pain point', (c) => c.painPoints, 'var(--serious)')} />
        </Card>
        <Card title={<>Unresolved negative conversations <Prov k="sentiment.overall" /></>} sub="Ended negative with no resolution — protect these relationships">
          {unresolvedNeg.length === 0 ? <EmptyState message="None in this period." /> : (
            <div>
              {unresolvedNeg.slice(0, 8).map((c) => (
                <div key={c.id} className="rankbar-row clickable" style={{ gridTemplateColumns: '1fr auto' }} onClick={() => navigate(`/calls/${c.id}`)}>
                  <div className="rankbar-label">{c.customerName}<div className="cell-sub">{c.dissatisfactionThemes.join('; ') || c.outcome} · {c.city}</div></div>
                  <Pill tone="critical">closing {c.sentiment!.closing.toFixed(2)}</Pill>
                </div>
              ))}
              {unresolvedNeg.length > 8 && <div className="cell-sub" style={{ paddingTop: 6 }}>+{unresolvedNeg.length - 8} more — drill via Call Explorer</div>}
            </div>
          )}
        </Card>
      </div>

      <div className="section-title">Sentiment by segment
        <select className="filter-select" value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Break down by">
          {DIMS.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
        </select>
        <span className="sub">Rates shown per 100 analysed calls · segments under {fmtInt(25)} calls are flagged as low-sample</span>
      </div>
      <Card>
        <DataTable columns={segCols} rows={segs} rowKey={(r) => r.key} initialSort={{ key: 'n', dir: 'desc' }}
          onRow={dim === 'region' ? (r) => drill({ region: r.key }) : dim === 'employee' ? (r) => {
            const emp = EMPLOYEES.find((e) => e.name === r.key);
            if (emp) drill({ employee: emp.id });
          } : undefined} />
        <div className="cell-sub" style={{ marginTop: 8 }}>
          {fmtInt(uniq(a.map((c) => c.customerId)).length)} unique customers across {fmtInt(a.length)} analysed calls. Sentiment labels are computed from transcripts only.
        </div>
      </Card>

      {themeDrill && (
        <ThemeDrillOverlay drill={themeDrill} onClose={() => setThemeDrill(null)} onNavigate={(callId) => navigate(`/calls/${callId}`)} />
      )}
    </>
  );
}
