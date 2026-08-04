import { useMemo, useState } from 'react';
import { PageHead, useDrill } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, DataTable, Pill, exportCsv, Heatmap, type Column, EmptyState, RankBars, Prov } from '../components/ui';
import { RelationScatter } from '../components/charts';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { agentRows, avg, segmentRows, type AgentRow } from '../lib/metrics';
import { fmtInt, fmtPct, pctVal } from '../lib/format';
import { MIN_SAMPLE_SIZE } from '../config';
import { EMPLOYEES } from '../data/taxonomy';

export default function Agents() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const drill = useDrill();
  const [compare, setCompare] = useState<'employee' | 'team' | 'manager'>('employee');

  const rows = useMemo(() => (d ? agentRows(d.analysed) : []), [d]);

  if (loading && !d) return <Loading label="Scoring conversations…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const a = d.analysed;
  const withQuality = a.filter((c) => c.quality);
  const complianceFails = withQuality.filter((c) => c.quality!.complianceFail);
  const diarOk = a.filter((c) => c.talk);
  const diarShare = a.length ? diarOk.length / a.length : 0;
  const talkReliable = diarShare >= 0.7;

  const dimNames = rows[0]?.scores.map((s) => s.label) ?? [];
  const orgDims = dimNames.map((label) => ({
    label,
    value: Math.round(avg(rows.flatMap((r) => r.scores.filter((s) => s.label === label).map((s) => s.value)))),
  })).sort((x, y) => y.value - x.value);

  const teamRows = compare === 'employee' ? [] : segmentRows(a, (c) => {
    const e = EMPLOYEES.find((x) => x.id === c.employeeId);
    return compare === 'team' ? e?.team ?? '—' : e?.manager ?? '—';
  });

  const cols: Column<AgentRow>[] = [
    {
      key: 'name', label: 'Employee', render: (r) => (
        <div style={{ maxWidth: 200 }}>
          <strong style={{ overflowWrap: 'anywhere' }}>{r.name}</strong>
          <div className="cell-sub">{r.team} · {r.manager}</div>
          {!r.reliable && <Pill tone="warning">low sample n={r.analysed}</Pill>}
        </div>
      ), sortVal: (r) => r.name,
    },
    { key: 'n', label: 'Analysed calls', num: true, render: (r) => fmtInt(r.analysed), sortVal: (r) => r.analysed },
    { key: 'quality', label: 'Quality score', num: true, render: (r) => <strong>{r.avgQuality.toFixed(0)}</strong>, sortVal: (r) => r.avgQuality },
    {
      key: 'compliance', label: 'Compliance', render: (r) => r.complianceFails > 0
        ? <Pill tone="critical">{r.complianceFails} critical failure{r.complianceFails > 1 ? 's' : ''}</Pill>
        : <Pill tone="good">clear</Pill>, sortVal: (r) => r.complianceFails,
    },
    {
      key: 'shift', label: 'Sentiment lift', num: true,
      render: (r) => <span className={`delta ${r.avgShift > 0.05 ? 'up' : r.avgShift < -0.05 ? 'down' : 'flat'}`}>{r.avgShift > 0 ? '+' : ''}{r.avgShift.toFixed(2)}</span>,
      sortVal: (r) => r.avgShift,
    },
    {
      key: 'talk', label: 'Talk ratio', num: true,
      render: (r) => r.avgTalkPct === null ? <span className="cell-sub" title="Diarisation sample too small for a reliable talk ratio">n/a</span> : `${r.avgTalkPct}%`,
      sortVal: (r) => r.avgTalkPct ?? -1,
    },
    { key: 'conv', label: 'Opportunity rate', num: true, render: (r) => fmtPct(r.opportunities, r.analysed), sortVal: (r) => pctVal(r.opportunities, r.analysed) },
    { key: 'orders', label: 'Orders', num: true, render: (r) => fmtInt(r.orders), sortVal: (r) => r.orders },
    { key: 'overdue', label: 'Overdue actions', num: true, render: (r) => fmtInt(r.overdueActions), sortVal: (r) => r.overdueActions },
    {
      key: 'strengths', label: 'Strongest / weakest', render: (r) => {
        const sorted = [...r.scores].sort((x, y) => y.value - x.value);
        return (
          <div style={{ fontSize: 12 }}>
            <span className="delta up">▲ {sorted[0]?.label} ({sorted[0]?.value})</span>
            <div className="delta down">▼ {sorted[sorted.length - 1]?.label} ({sorted[sorted.length - 1]?.value})</div>
          </div>
        );
      },
    },
    { key: 'coach', label: 'Coaching focus', render: (r) => <span style={{ fontSize: 12 }}>{r.coachingNotes[0] ?? '—'}</span> },
  ];

  return (
    <>
      <PageHead title="Agent Quality"
        desc="Conversation-quality scoring across 9 parameters with team and manager comparisons. Critical compliance failures are surfaced separately and never averaged away. Talk-time metrics appear only where speaker diarisation is reliable. A customer being negative is not, by itself, counted against the agent."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Average quality score" prov="agent.quality" value={avg(withQuality.map((c) => c.quality!.overall))} format={(v) => `${v.toFixed(0)} / 100`} denomNote={`n = ${fmtInt(withQuality.length)} scored calls`} />
        <KpiCard label="Critical compliance failures" prov="agent.compliance" value={complianceFails.length} denomNote="shown separately — never hidden in averages" accent="var(--critical)" invertDelta onClick={() => drill({ compliance: 'flagged' })} />
        <KpiCard label="Calls that improved sentiment" prov="sentiment.journey" value={a.filter((c) => c.sentiment!.shift > 0.2).length} denomNote={`of ${fmtInt(a.length)} analysed`} accent="var(--good)" />
        <KpiCard label="Clear next step set" prov="actions.list" value={pctVal(a.filter((c) => c.actions.some((x) => x.source === 'committed')).length, a.length)} format={(v) => `${v.toFixed(0)}%`} denomNote={`of ${fmtInt(a.length)} analysed`} />
        <KpiCard label="Diarisation-reliable calls" prov="agent.talk" value={diarOk.length} denomNote={`${fmtPct(diarOk.length, a.length)} of analysed — talk metrics limited to these`} />
        <KpiCard label="Coaching opportunities" prov="agent.coaching" value={rows.reduce((s, r) => s + r.coachingNotes.length, 0)} accent="var(--warning)" />
      </div>

      {!talkReliable && (
        <div className="low-conf-note" style={{ marginTop: 12 }}>
          Talk-to-listen ratio, interruptions and silence metrics are hidden for most calls in this view: only {fmtPct(diarOk.length, a.length)} of analysed calls have reliable speaker diarisation (threshold 70%).
        </div>
      )}

      <div className="two-col" style={{ marginTop: 14 }}>
        <Card title={<>Quality parameter profile <Prov k="agent.quality" /></>} sub="Organisation-wide average per parameter (0–100) — weighting in docs/08-scoring-methodology.md">
          <RankBars items={orgDims.map((x) => ({ label: x.label, value: x.value, color: x.value < 65 ? 'var(--serious)' : 'var(--s1)' }))} valueFmt={(v) => `${v}`} max={100} />
        </Card>
        <Card title={<>Quality vs sentiment lift <Prov k="agent.quality" /></>} sub={`Does better conversation quality move customers? Agents with ≥${MIN_SAMPLE_SIZE} calls`}>
          <RelationScatter xLabel="Avg quality score" yLabel="Avg sentiment shift" yUnit=""
            points={rows.filter((r) => r.reliable).map((r) => ({ name: r.name.split(' ')[0], x: r.avgQuality, y: r.avgShift * 100, n: r.analysed }))}
            onPoint={(name) => { const r = rows.find((x) => x.name.split(' ')[0] === name); if (r) drill({ employee: r.employeeId }); }} />
          <div className="cell-sub">Y-axis: average sentiment shift ×100 (text-based).</div>
        </Card>
      </div>

      <div className="section-title">Parameter heatmap by agent <span className="sub">click a cell to open that agent's calls</span></div>
      <Card>
        <Heatmap rows={rows.map((r) => `${r.name.split(' ')[0]} ${r.name.split(' ')[1]?.[0] ?? ''}.${r.reliable ? '' : ' ⚠'}`)}
          cols={dimNames}
          value={(rowLabel, col) => {
            const r = rows.find((x) => rowLabel.startsWith(x.name.split(' ')[0]));
            return r?.scores.find((s) => s.label === col)?.value ?? null;
          }}
          display={(v) => v.toFixed(0)} maxOverride={100}
          onCell={(rowLabel) => { const r = rows.find((x) => rowLabel.startsWith(x.name.split(' ')[0])); if (r) drill({ employee: r.employeeId }); }} />
        <div className="cell-sub" style={{ marginTop: 6 }}>⚠ = below minimum sample of {MIN_SAMPLE_SIZE} analysed calls; treat as indicative only.</div>
      </Card>

      <div className="section-title">Comparison
        <div className="tabs" style={{ margin: 0, borderBottom: 'none' }}>
          {(['employee', 'team', 'manager'] as const).map((c) => (
            <button key={c} className={`tab ${compare === c ? 'active' : ''}`} onClick={() => setCompare(c)}>By {c}</button>
          ))}
        </div>
        <button className="btn small" onClick={() => exportCsv('agent-quality.csv',
          ['Employee', 'Team', 'Manager', 'Analysed calls', 'Quality', 'Compliance failures', 'Sentiment lift', 'Opportunity rate %', 'Orders', 'Overdue actions'],
          rows.map((r) => [r.name, r.team, r.manager, r.analysed, r.avgQuality.toFixed(0), r.complianceFails, r.avgShift.toFixed(2), pctVal(r.opportunities, r.analysed).toFixed(1), r.orders, r.overdueActions]))}>
          Export CSV
        </button>
      </div>
      <Card>
        {compare === 'employee' ? (
          <DataTable columns={cols} rows={rows} rowKey={(r) => r.employeeId} initialSort={{ key: 'quality', dir: 'desc' }}
            onRow={(r) => drill({ employee: r.employeeId })} />
        ) : teamRows.length === 0 ? <EmptyState message="No data for this comparison." /> : (
          <DataTable rowKey={(r) => r.key} initialSort={{ key: 'quality', dir: 'desc' }} rows={teamRows} columns={[
            { key: 'key', label: compare === 'team' ? 'Team' : 'Manager', render: (r) => <strong>{r.key}</strong>, sortVal: (r) => r.key },
            { key: 'n', label: 'Analysed calls', num: true, render: (r) => fmtInt(r.analysed), sortVal: (r) => r.analysed },
            { key: 'quality', label: 'Avg quality', num: true, render: (r) => r.avgQuality.toFixed(0), sortVal: (r) => r.avgQuality },
            { key: 'pos', label: 'Positive rate', num: true, render: (r) => fmtPct(r.positive, r.analysed), sortVal: (r) => pctVal(r.positive, r.analysed) },
            { key: 'hi', label: 'High intent', num: true, render: (r) => fmtInt(r.highIntent), sortVal: (r) => r.highIntent },
            { key: 'conv', label: 'Opportunity rate', num: true, render: (r) => fmtPct(r.opportunities, r.analysed), sortVal: (r) => pctVal(r.opportunities, r.analysed) },
            { key: 'overdue', label: 'Overdue actions', num: true, render: (r) => fmtInt(r.overdueActions), sortVal: (r) => r.overdueActions },
          ]} />
        )}
      </Card>
    </>
  );
}
