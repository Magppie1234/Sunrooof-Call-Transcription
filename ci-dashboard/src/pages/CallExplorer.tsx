import { useNavigate } from 'react-router-dom';
import { PageHead } from '../components/layout';
import { Card, Loading, ErrorState, DataTable, Pill, exportCsv, sentimentTone, type Column } from '../components/ui';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { fmtDateTime, fmtDuration, fmtInt } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { CallRecord } from '../types/domain';

export default function CallExplorer() {
  const { data: d, loading, error } = useFilteredData();
  const { filters, setFilters } = useAppState();
  const navigate = useNavigate();

  if (loading && !d) return <Loading label="Loading calls…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const rows = d.current;

  const cols: Column<CallRecord>[] = [
    {
      key: 'id', label: 'Call', render: (c) => (
        <div>
          <strong>{c.id}</strong>
          <div className="cell-sub">{fmtDateTime(c.dateTime)} · {c.direction} · {fmtDuration(c.durationSec)}</div>
        </div>
      ), sortVal: (c) => c.dateTime,
    },
    {
      key: 'customer', label: 'Customer', render: (c) => (
        <div style={{ maxWidth: 180 }}>
          <span style={{ overflowWrap: 'anywhere' }}>{c.customerName}</span>
          <div className="cell-sub">{c.customerType} · {c.city}, {c.state}</div>
        </div>
      ), sortVal: (c) => c.customerName,
    },
    {
      key: 'employee', label: 'Employee / team', render: (c) => {
        const e = EMPLOYEES.find((x) => x.id === c.employeeId);
        return <div style={{ maxWidth: 160 }}><span style={{ overflowWrap: 'anywhere' }}>{e?.name ?? c.employeeId}</span><div className="cell-sub">{e?.team}</div></div>;
      }, sortVal: (c) => c.employeeId,
    },
    { key: 'lang', label: 'Language', render: (c) => c.language, sortVal: (c) => c.language },
    {
      key: 'sent', label: 'Sentiment', render: (c) => c.sentiment
        ? <Pill tone={sentimentTone(c.sentiment.overall)}>{c.sentiment.overall}{c.sentiment.shift > 0.2 ? ' ▲' : c.sentiment.shift < -0.2 ? ' ▼' : ''}</Pill>
        : <span className="cell-sub">not analysed</span>, sortVal: (c) => c.sentiment?.overall ?? 'zz',
    },
    {
      key: 'pr', label: 'Purchase readiness', num: true, render: (c) => c.purchaseReadiness
        ? <strong>{c.purchaseReadiness.score}</strong>
        : <span className="cell-sub">n/a</span>, sortVal: (c) => c.purchaseReadiness?.score ?? -1,
    },
    {
      key: 'topics', label: 'Topics / FAQs / objections', render: (c) => (
        <div style={{ maxWidth: 240, fontSize: 12 }}>
          {c.topics.slice(0, 3).join(', ') || '—'}
          <div className="cell-sub">{c.faqs.length} FAQ · {c.objections.length} objection{c.objections.length === 1 ? '' : 's'}{c.risks.length > 0 && <> · <span style={{ color: 'var(--critical)' }}>{c.risks.length} risk</span></>}</div>
        </div>
      ),
    },
    { key: 'outcome', label: 'Outcome', render: (c) => <span style={{ fontSize: 12 }}>{c.outcome}</span>, sortVal: (c) => c.outcome },
    { key: 'quality', label: 'Quality', num: true, render: (c) => c.quality ? <>{c.quality.overall}{c.quality.complianceFail && <div><Pill tone="critical">compliance</Pill></div>}</> : <span className="cell-sub">—</span>, sortVal: (c) => c.quality?.overall ?? -1 },
    { key: 'actions', label: 'Next actions', num: true, render: (c) => c.actions.length ? `${c.actions.length}${c.actions.some((a) => a.slaStatus === 'overdue') ? ' ⚠' : ''}` : '—', sortVal: (c) => c.actions.length },
    {
      key: 'conf', label: 'AI conf', num: true, render: (c) => c.transcribed
        ? <span className={c.transcriptionConfidence < 0.6 ? 'delta down' : ''}>{(c.aiConfidence * 100).toFixed(0)}%</span>
        : <Pill tone="neutral">no transcript</Pill>, sortVal: (c) => c.aiConfidence,
    },
  ];

  return (
    <>
      <PageHead title="Call Explorer"
        desc="Every call in the selected period, including failed and non-meaningful calls. Click a row for the full speaker-separated transcript, sentiment timeline, extracted insights and evidence timestamps."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <Card>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <input className="searchbox" placeholder="Search call ID, customer, summary, topic…" value={filters.search}
            onChange={(e) => setFilters({ search: e.target.value })} aria-label="Search calls" />
          <span className="sample-note">{fmtInt(rows.length)} calls match · {fmtInt(d.analysed.length)} analysed</span>
          <button className="btn small" style={{ marginLeft: 'auto' }} onClick={() => exportCsv('calls.csv',
            ['Call ID', 'Date', 'Customer', 'Employee', 'Team', 'Region', 'City', 'Language', 'Direction', 'Duration (s)', 'Sentiment', 'Purchase readiness', 'Outcome', 'Quality', 'Actions', 'AI confidence', 'Compliance flags'],
            rows.map((c) => [c.id, c.dateTime, c.customerName, EMPLOYEES.find((e) => e.id === c.employeeId)?.name ?? c.employeeId, EMPLOYEES.find((e) => e.id === c.employeeId)?.team ?? '', c.region, c.city, c.language, c.direction, c.durationSec, c.sentiment?.overall ?? 'not analysed', c.purchaseReadiness?.score ?? '', c.outcome, c.quality?.overall ?? '', c.actions.length, (c.aiConfidence * 100).toFixed(0) + '%', c.complianceFlags.join('; ')]))}>
            Export CSV
          </button>
        </div>
        <DataTable columns={cols} rows={rows} rowKey={(c) => c.id} pageSize={15}
          initialSort={{ key: 'id', dir: 'desc' }}
          onRow={(c) => navigate(`/calls/${c.id}`)}
          emptyMessage="No calls match the current filters. Try widening the period or resetting filters." />
      </Card>
    </>
  );
}
