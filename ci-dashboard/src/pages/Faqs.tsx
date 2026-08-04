import { useMemo, useState } from 'react';
import { PageHead, useDrill } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, RankBars, Heatmap, DataTable, exportCsv, Pill, type Column, EmptyState, Prov } from '../components/ui';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { faqRows, uniq, type FaqRow } from '../lib/metrics';
import { fmtInt, fmtPct, pctVal } from '../lib/format';

export default function Faqs() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const drill = useDrill();
  const [tab, setTab] = useState<'table' | 'matrix'>('table');

  const rows = useMemo(() => (d ? faqRows(d.analysed, d.analysedPrev) : []), [d]);

  if (loading && !d) return <Loading label="Clustering customer questions…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const totalFaqCalls = rows.reduce((s, r) => s + r.calls, 0);
  const unansweredTotal = rows.reduce((s, r) => s + r.unanswered, 0);
  const partialTotal = rows.reduce((s, r) => s + r.partial, 0);
  const emergent = rows.filter((r) => r.calls >= 4 && r.calls > r.prevCalls * 1.5).slice(0, 6);
  const unansweredBoard = [...rows].filter((r) => r.unanswered > 0).sort((a, b) => b.unanswered - a.unanswered).slice(0, 8);
  const categories = uniq(rows.map((r) => r.category));
  const regions = uniq(d.analysed.map((c) => c.region));
  const products = uniq(d.analysed.map((c) => c.productSeries));

  const catRegion = (cat: string, region: string) => {
    const calls = d.analysed.filter((c) => c.region === region);
    if (!calls.length) return null;
    const n = calls.filter((c) => c.faqs.some((f) => f.category === cat)).length;
    return (n / calls.length) * 100;
  };
  const catProduct = (cat: string, product: string) => {
    const calls = d.analysed.filter((c) => c.productSeries === product);
    if (!calls.length) return null;
    const n = calls.filter((c) => c.faqs.some((f) => f.category === cat)).length;
    return (n / calls.length) * 100;
  };

  const cols: Column<FaqRow>[] = [
    {
      key: 'q', label: 'Standardised FAQ', render: (r) => (
        <div style={{ maxWidth: 340 }}>
          <strong>{r.standardized}</strong>
          <div className="cell-sub">e.g. “{r.sampleQuestion}” · {r.category}</div>
        </div>
      ), sortVal: (r) => r.standardized,
    },
    { key: 'calls', label: 'Calls', num: true, render: (r) => fmtInt(r.calls), sortVal: (r) => r.calls },
    { key: 'cust', label: 'Customers', num: true, render: (r) => fmtInt(r.customers), sortVal: (r) => r.customers },
    { key: 'pct', label: '% of analysed', num: true, render: (r) => `${r.pctOfAnalysed.toFixed(1)}%`, sortVal: (r) => r.pctOfAnalysed },
    {
      key: 'trend', label: 'vs prior', num: true, render: (r) => {
        const diff = r.calls - r.prevCalls;
        return <span className={`delta ${diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat'}`}>{diff > 0 ? '+' : ''}{diff} <span className="cell-sub">({r.prevCalls})</span></span>;
      }, sortVal: (r) => r.calls - r.prevCalls,
    },
    {
      key: 'ans', label: 'Answer status', render: (r) => (
        <div className="chip-row">
          {r.answered > 0 && <Pill tone="good">{r.answered} answered</Pill>}
          {r.partial > 0 && <Pill tone="warning">{r.partial} partial</Pill>}
          {r.unanswered > 0 && <Pill tone="critical">{r.unanswered} unanswered</Pill>}
        </div>
      ), sortVal: (r) => pctVal(r.unanswered, r.calls),
    },
    { key: 'resp', label: 'Avg response', num: true, render: (r) => r.avgResponseSec === null ? '—' : `${r.avgResponseSec}s`, sortVal: (r) => r.avgResponseSec ?? 999 },
    {
      key: 'after', label: 'Sentiment after answer', render: (r) => (
        <span>
          <span className="delta up">▲ {r.positiveAfterPct.toFixed(0)}%</span>{' · '}
          <span className="delta down">▼ {r.negativeAfterPct.toFixed(0)}%</span>
        </span>
      ), sortVal: (r) => r.positiveAfterPct,
    },
    { key: 'esc', label: 'Escalations', num: true, render: (r) => r.escalations || '—', sortVal: (r) => r.escalations },
    { key: 'reco', label: 'Recommended action', render: (r) => <span style={{ fontSize: 12, maxWidth: 220, display: 'inline-block' }}>{r.recommendation}</span> },
    { key: 'conf', label: 'AI conf', num: true, render: (r) => `${(r.avgConfidence * 100).toFixed(0)}%`, sortVal: (r) => r.avgConfidence },
  ];

  return (
    <>
      <PageHead title="FAQs & Knowledge Gaps"
        desc="Explicit and implicit customer questions, grouped into standardised FAQs (counted once per call — repeats within a call are not inflated). No approved knowledge base is connected yet, so answers are assessed for relevance and completeness only, not factual accuracy."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Distinct FAQs identified" prov="faq.questions" value={rows.length} />
        <KpiCard label="FAQ occurrences (call-level)" prov="faq.questions" value={totalFaqCalls} denomNote={`across ${fmtInt(d.analysed.length)} analysed calls`} />
        <KpiCard label="Unanswered occurrences" prov="faq.answerQuality" value={unansweredTotal} denomNote={`${fmtPct(unansweredTotal, totalFaqCalls)} of occurrences`} accent="var(--critical)" invertDelta />
        <KpiCard label="Partially answered" prov="faq.answerQuality" value={partialTotal} denomNote={`${fmtPct(partialTotal, totalFaqCalls)} of occurrences`} accent="var(--warning)" />
        <KpiCard label="Emerging FAQs" prov="faq.questions" value={emergent.length} denomNote="rising ≥50% vs prior period" accent="var(--warning)" />
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <Card title={<>Unanswered-question leaderboard <Prov k="faq.answerQuality" /></>} sub="Questions agents most often could not answer — knowledge-base priorities">
          <RankBars items={unansweredBoard.map((r) => ({
            label: r.standardized, value: r.unanswered,
            sub: `${fmtPct(r.unanswered, r.calls)} of ${r.calls} occurrences · ${r.category}`,
            color: 'var(--serious)', onClick: () => drill({ faqCategory: r.category }),
          }))} emptyMessage="No unanswered questions in this period." />
        </Card>
        <Card title={<>Emerging FAQs <Prov k="faq.questions" /></>} sub="Volume rising vs comparison period — get ahead of these">
          {emergent.length === 0 ? <EmptyState message="No FAQ is rising unusually this period." /> : (
            <RankBars items={emergent.map((r) => ({
              label: r.standardized, value: r.calls,
              sub: `was ${r.prevCalls} in prior period · ${r.category}`,
              color: 'var(--warning)', onClick: () => drill({ faqCategory: r.category }),
            }))} />
          )}
        </Card>
        <Card title={<>FAQ impact on sentiment & conversion <Prov k="faq.accuracy" /></>} sub="Occurrences with negative sentiment right after the answer — fix scripts here first">
          <RankBars items={[...rows].filter((r) => r.calls >= 5).sort((a, b) => b.negativeAfterPct - a.negativeAfterPct).slice(0, 6).map((r) => ({
            label: r.standardized, value: Math.round(r.negativeAfterPct),
            sub: `${r.calls} occurrences · ${fmtPct(r.unanswered, r.calls)} unanswered`,
            color: r.negativeAfterPct > 25 ? 'var(--critical)' : 'var(--s1)',
            onClick: () => drill({ faqCategory: r.category }),
          }))} valueFmt={(v) => `${v}% neg`} />
        </Card>
        <Card title={<>FAQ trend by category <Prov k="faq.category" /></>} sub="Share of analysed calls containing each category (top 8)">
          <RankBars items={categories.map((cat) => {
            const cur = d.analysed.filter((c) => c.faqs.some((f) => f.category === cat)).length;
            return { label: cat, value: cur, sub: `${fmtPct(cur, d.analysed.length)} of analysed calls`, onClick: () => drill({ faqCategory: cat }) };
          }).sort((a, b) => b.value - a.value).slice(0, 8)} />
        </Card>
      </div>

      <div className="section-title">
        Category matrices
        <div className="tabs" style={{ margin: 0, borderBottom: 'none' }}>
          <button className={`tab ${tab === 'table' ? 'active' : ''}`} onClick={() => setTab('table')}>Region × FAQ</button>
          <button className={`tab ${tab === 'matrix' ? 'active' : ''}`} onClick={() => setTab('matrix')}>Product × FAQ</button>
        </div>
        <span className="sub">Cell = % of that segment's analysed calls containing the category · click to drill</span>
      </div>
      <Card>
        {tab === 'table' ? (
          <Heatmap rows={categories} cols={regions} value={catRegion} display={(v) => `${v.toFixed(0)}%`}
            onCell={(cat, region) => drill({ faqCategory: cat, region })} />
        ) : (
          <Heatmap rows={categories} cols={products.map((p) => p.replace(' Kitchen', ''))}
            value={(cat, p) => catProduct(cat, products.find((x) => x.startsWith(p)) ?? p)}
            display={(v) => `${v.toFixed(0)}%`}
            onCell={(cat, p) => drill({ faqCategory: cat, product: products.find((x) => x.startsWith(p)) ?? '' })} />
        )}
      </Card>

      <div className="section-title">Ranked FAQ table
        <button className="btn small" onClick={() => exportCsv('faqs.csv',
          ['Standardised FAQ', 'Category', 'Sample question', 'Calls', 'Customers', '% of analysed', 'Prior period', 'Answered', 'Partial', 'Unanswered', 'Avg response (s)', 'Positive after %', 'Negative after %', 'Escalations', 'AI confidence', 'Recommendation'],
          rows.map((r) => [r.standardized, r.category, r.sampleQuestion, r.calls, r.customers, r.pctOfAnalysed.toFixed(1), r.prevCalls, r.answered, r.partial, r.unanswered, r.avgResponseSec, r.positiveAfterPct.toFixed(0), r.negativeAfterPct.toFixed(0), r.escalations, (r.avgConfidence * 100).toFixed(0) + '%', r.recommendation]))}>
          Export CSV
        </button>
        <span className="sub">Click a row to open matching calls with supporting transcripts</span>
      </div>
      <Card>
        <DataTable columns={cols} rows={rows} rowKey={(r) => r.standardized} pageSize={12}
          initialSort={{ key: 'calls', dir: 'desc' }} onRow={(r) => drill({ faqCategory: r.category })} />
      </Card>
    </>
  );
}
