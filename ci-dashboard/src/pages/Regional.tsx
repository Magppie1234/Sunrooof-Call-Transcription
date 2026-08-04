import { useState } from 'react';
import { PageHead, useDrill } from '../components/layout';
import { Card, Loading, ErrorState, Heatmap, DataTable, exportCsv, Pill, type Column, RankBars, Prov } from '../components/ui';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { segmentRows, faqRows, uniq, type SegmentRow } from '../lib/metrics';
import { fmtInt, pctVal } from '../lib/format';
import { MIN_SAMPLE_SIZE } from '../config';
import type { CallRecord } from '../types/domain';

type Level = 'region' | 'state' | 'city';
const LEVEL_FN: Record<Level, (c: CallRecord) => string> = {
  region: (c) => c.region,
  state: (c) => c.state,
  city: (c) => c.city,
};

export default function Regional() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const drill = useDrill();
  const [level, setLevel] = useState<Level>('region');

  if (loading && !d) return <Loading label="Aggregating regional intelligence…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const segs = segmentRows(d.analysed, LEVEL_FN[level]);
  const faqs = faqRows(d.analysed, d.analysedPrev);
  const per100 = (n: number, den: number) => (den ? ((n / den) * 100).toFixed(1) : '—');

  const topFaqFor = (key: string) => {
    const calls = d.analysed.filter((c) => LEVEL_FN[level](c) === key);
    const counts = new Map<string, number>();
    for (const c of calls) for (const f of uniq(c.faqs.map((x) => x.standardized))) counts.set(f, (counts.get(f) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—';
  };
  const topObjectionFor = (key: string) => {
    const calls = d.analysed.filter((c) => LEVEL_FN[level](c) === key);
    const counts = new Map<string, number>();
    for (const c of calls) for (const o of uniq(c.objections.map((x) => x.type))) counts.set(o, (counts.get(o) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—';
  };
  const productDemandFor = (key: string) => {
    const calls = d.analysed.filter((c) => LEVEL_FN[level](c) === key && c.intent !== 'none');
    const counts = new Map<string, number>();
    for (const c of calls) counts.set(c.productSeries, (counts.get(c.productSeries) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—';
  };

  const drillLevel = (key: string) => {
    if (level === 'region') drill({ region: key });
    else if (level === 'state') drill({ state: key });
    else drill({ city: key });
  };

  const cols: Column<SegmentRow>[] = [
    {
      key: 'key', label: level === 'region' ? 'Region' : level === 'state' ? 'State' : 'City', render: (r) => (
        <div>
          <strong>{r.key}</strong>
          <div className="cell-sub">{r.reliable
            ? <Pill tone="good">reliable (n={r.analysed} ≥ {MIN_SAMPLE_SIZE})</Pill>
            : <Pill tone="warning">low sample (n={r.analysed} &lt; {MIN_SAMPLE_SIZE})</Pill>}</div>
        </div>
      ), sortVal: (r) => r.key,
    },
    { key: 'n', label: 'Calls analysed', num: true, render: (r) => fmtInt(r.analysed), sortVal: (r) => r.analysed },
    { key: 'cust', label: 'Unique customers', num: true, render: (r) => fmtInt(r.customers), sortVal: (r) => r.customers },
    { key: 'pos', label: 'Positive (raw · /100)', num: true, render: (r) => <>{r.positive} · <strong>{per100(r.positive, r.analysed)}</strong></>, sortVal: (r) => pctVal(r.positive, r.analysed) },
    { key: 'neg', label: 'Negative (raw · /100)', num: true, render: (r) => <>{r.negative} · <strong>{per100(r.negative, r.analysed)}</strong></>, sortVal: (r) => pctVal(r.negative, r.analysed) },
    { key: 'shift', label: 'Sentiment shift', num: true, render: (r) => <span className={`delta ${r.avgShift > 0.05 ? 'up' : r.avgShift < -0.05 ? 'down' : 'flat'}`}>{r.avgShift > 0 ? '+' : ''}{r.avgShift.toFixed(2)}</span>, sortVal: (r) => r.avgShift },
    { key: 'hi', label: 'High intent (raw · /100)', num: true, render: (r) => <>{r.highIntent} · <strong>{per100(r.highIntent, r.analysed)}</strong></>, sortVal: (r) => pctVal(r.highIntent, r.analysed) },
    { key: 'unans', label: 'Unanswered FAQ rate', num: true, render: (r) => `${per100(r.unansweredFaqs, r.totalFaqs)}%`, sortVal: (r) => pctVal(r.unansweredFaqs, r.totalFaqs) },
    { key: 'quality', label: 'Agent quality', num: true, render: (r) => r.avgQuality ? r.avgQuality.toFixed(0) : '—', sortVal: (r) => r.avgQuality },
    { key: 'done', label: 'Action completion', num: true, render: (r) => `${per100(r.completedActions, r.totalActions)}%`, sortVal: (r) => pctVal(r.completedActions, r.totalActions) },
    { key: 'overdue', label: 'Overdue actions', num: true, render: (r) => fmtInt(r.overdueActions), sortVal: (r) => r.overdueActions },
    { key: 'conv', label: 'Orders (raw · /100)', num: true, render: (r) => <>{r.orders} · <strong>{per100(r.orders, r.analysed)}</strong></>, sortVal: (r) => pctVal(r.orders, r.analysed) },
    { key: 'compl', label: 'Complaints', num: true, render: (r) => fmtInt(r.complaints), sortVal: (r) => r.complaints },
    { key: 'comp', label: 'Competitor mentions', num: true, render: (r) => fmtInt(r.competitorMentions), sortVal: (r) => r.competitorMentions },
    { key: 'faq', label: 'Top FAQ', render: (r) => <span style={{ fontSize: 12 }}>{topFaqFor(r.key)}</span> },
    { key: 'obj', label: 'Top objection', render: (r) => <span style={{ fontSize: 12 }}>{topObjectionFor(r.key)}</span> },
    { key: 'demand', label: 'Top product demand', render: (r) => <span style={{ fontSize: 12 }}>{productDemandFor(r.key)}</span> },
  ];

  const metricCols = ['Positive /100', 'Negative /100', 'High intent /100', 'Unanswered FAQ %', 'Orders /100', 'Complaints /100'];
  const metricVal = (rowLabel: string, col: string) => {
    const r = segs.find((s) => rowLabel.startsWith(s.key));
    if (!r || !r.analysed) return null;
    switch (col) {
      case 'Positive /100': return pctVal(r.positive, r.analysed);
      case 'Negative /100': return pctVal(r.negative, r.analysed);
      case 'High intent /100': return pctVal(r.highIntent, r.analysed);
      case 'Unanswered FAQ %': return pctVal(r.unansweredFaqs, r.totalFaqs);
      case 'Orders /100': return pctVal(r.orders, r.analysed);
      case 'Complaints /100': return pctVal(r.complaints, r.analysed);
      default: return null;
    }
  };

  return (
    <>
      <PageHead title="Regional Intelligence"
        desc="Geography comes from CRM region/state/city/pin-code fields only — never inferred from accent, language, name or any other sensitive characteristic. Every metric shows the raw count and the rate per 100 analysed calls; segments below the minimum sample size are flagged rather than presented as trends."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="tabs">
        {(['region', 'state', 'city'] as Level[]).map((l) => (
          <button key={l} className={`tab ${level === l ? 'active' : ''}`} onClick={() => setLevel(l)}>
            By {l[0].toUpperCase() + l.slice(1)}
          </button>
        ))}
      </div>

      <div className="two-col">
        <Card title={<>{`Metric heatmap by ${level}`} <Prov k="region.geo" /></>} sub="Rates per 100 analysed calls · low-sample rows are marked in the table below · click to drill">
          <Heatmap rows={segs.map((s) => `${s.key}${s.reliable ? '' : ' ⚠'}`)} cols={metricCols} value={metricVal}
            display={(v) => v.toFixed(0)}
            onCell={(rowLabel) => { const s = segs.find((x) => rowLabel.startsWith(x.key)); if (s) drillLevel(s.key); }} />
        </Card>
        <Card title={<>Where questions go unanswered <Prov k="region.geo" /></>} sub={`Unanswered FAQ occurrences per ${level} — knowledge-gap hotspots`}>
          <RankBars items={segs.filter((s) => s.unansweredFaqs > 0).map((s) => ({
            label: `${s.key}${s.reliable ? '' : ' ⚠ low sample'}`,
            value: s.unansweredFaqs,
            sub: `${per100(s.unansweredFaqs, s.totalFaqs)}% of ${s.totalFaqs} FAQ occurrences`,
            color: 'var(--serious)',
            onClick: () => drillLevel(s.key),
          }))} />
        </Card>
      </div>

      <div className="section-title">Comparison table
        <button className="btn small" onClick={() => exportCsv(`regional-${level}.csv`,
          [level, 'Calls analysed', 'Unique customers', 'Positive', 'Positive/100', 'Negative', 'Negative/100', 'High intent', 'Orders', 'Complaints', 'Sample OK'],
          segs.map((r) => [r.key, r.analysed, r.customers, r.positive, per100(r.positive, r.analysed), r.negative, per100(r.negative, r.analysed), r.highIntent, r.orders, r.complaints, r.reliable ? 'yes' : 'LOW SAMPLE']))}>
          Export CSV
        </button>
        <span className="sub">Sortable · click a row to open its calls · {fmtInt(faqs.length)} distinct FAQs feed the “Top FAQ” column</span>
      </div>
      <Card>
        <DataTable columns={cols} rows={segs} rowKey={(r) => r.key} pageSize={12}
          initialSort={{ key: 'n', dir: 'desc' }} onRow={(r) => drillLevel(r.key)} />
      </Card>
    </>
  );
}
