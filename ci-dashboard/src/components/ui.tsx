import { Fragment, useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { fmtDelta, fmtInt } from '../lib/format';
import { MIN_SAMPLE_SIZE } from '../config';
import { provOf, type ProvStatus } from '../lib/provenance';
import { useAppState } from '../state/AppState';

// ---------- Data provenance dot ----------
const PROV_LABEL: Record<ProvStatus, string> = {
  real: 'Real data',
  partial: 'Real data, with a gap',
  demo: 'Demo data — no real source',
};

/**
 * Small dot marking whether a surface is driven by real Sunrooof data (green),
 * real data with a declared gap (amber), or still demo content (red). Hover
 * gives the reason. Purely additive — it never changes the surrounding layout.
 */
export function Prov({ k }: { k: string }) {
  const entry = provOf(k);
  if (!entry) return null;
  return (
    <span
      className={`prov-dot ${entry.status}`}
      title={`${PROV_LABEL[entry.status]} — ${entry.note}`}
      aria-label={`${PROV_LABEL[entry.status]}: ${entry.note}`}
      role="img"
    />
  );
}

// ---------- Pills & labels ----------
export type PillTone = 'good' | 'warning' | 'serious' | 'critical' | 'info' | 'neutral';

export const Pill = ({ tone, children }: { tone: PillTone; children: ReactNode }) => (
  <span className={`pill ${tone}`}>{children}</span>
);

export const sentimentTone = (s: string): PillTone =>
  s === 'positive' ? 'good' : s === 'negative' ? 'critical' : 'neutral';

export const Conf = ({ value }: { value: number }) => (
  <span className="conf" title="AI confidence for this extracted insight">AI conf {(value * 100).toFixed(0)}%</span>
);

export const SampleNote = ({ n, label = 'analysed calls' }: { n: number; label?: string }) => (
  <span className="sample-note">n = {fmtInt(n)} {label}{n < MIN_SAMPLE_SIZE ? ' · low sample — interpret with caution' : ''}</span>
);

// ---------- Cards ----------
function SectionExplanation({ summary, metricLabel }: { summary?: ReactNode; metricLabel?: string }) {
  const { exploreMode } = useAppState();
  const [open, setOpen] = useState(false);
  if (!exploreMode) return null;
  return (
    <div className="section-explain" onClick={(e) => e.stopPropagation()}>
      <button className="section-explain-button" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? 'Hide explanation' : 'What does this section mean?'}
      </button>
      {open && (
        <div className="section-explain-content">
          {metricLabel ? <><strong>{metricLabel}</strong> is the main value shown in this card. </> : null}
          {summary ? <span>{summary} </span> : <span>This section summarizes the calls matching your current filters. </span>}
          Numbers without a % sign are counts. Numbers with a % sign are shares of the group described beside or below them. Clickable rows, bars and cells open the calls used to calculate that result.
        </div>
      )}
    </div>
  );
}

export function Card({ title, sub, right, children, style }: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  return (
    <div className="card" style={style}>
      {(title || right) && (
        <div className="card-head-row">
          <div>{title && <h3>{title}</h3>}{sub && <div className="card-sub">{sub}</div>}</div>
          {right}
        </div>
      )}
      {children}
      <SectionExplanation summary={sub} />
    </div>
  );
}

export function KpiCard({ label, value, prev, denomNote, accent = 'var(--s1)', onClick, format = fmtInt, invertDelta = false, extra, prov }: {
  label: string;
  value: number;
  prev?: number;
  denomNote?: string;
  accent?: string;
  onClick?: () => void;
  format?: (v: number) => string;
  /** For metrics where an increase is bad (overdue, complaints). */
  invertDelta?: boolean;
  extra?: ReactNode;
  /** Provenance key — renders the real/partial/demo dot beside the label. */
  prov?: string;
}) {
  const delta = prev !== undefined ? fmtDelta(value, prev) : null;
  const dir = delta && invertDelta ? (delta.dir === 'up' ? 'down' : delta.dir === 'down' ? 'up' : 'flat') : delta?.dir;
  return (
    <div className="card kpi" onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter') onClick(); } : undefined}>
      <div className="kpi-accent" style={{ background: accent }} />
      <div className="kpi-label">{label}{prov && <Prov k={prov} />}</div>
      <div className="kpi-value">{format(value)}</div>
      <div className="kpi-meta">
        {delta && <span className={`delta ${dir}`}>{delta.dir === 'up' ? '▲' : delta.dir === 'down' ? '▼' : '•'} {delta.text}</span>}
        {denomNote && <span>{denomNote}</span>}
        {extra}
      </div>
      <SectionExplanation summary={denomNote} metricLabel={label} />
    </div>
  );
}

// ---------- States ----------
export const Loading = ({ label = 'Loading data…' }: { label?: string }) => (
  <div className="loading-block"><div className="spinner" />{label}</div>
);

export const ErrorState = ({ message }: { message: string }) => (
  <div className="empty-state"><div className="icon">⚠️</div>Something went wrong loading this view.<div className="cell-sub">{message}</div></div>
);

export const EmptyState = ({ message, hint }: { message: string; hint?: string }) => (
  <div className="empty-state"><div className="icon">◫</div>{message}{hint && <div className="cell-sub" style={{ marginTop: 4 }}>{hint}</div>}</div>
);

// ---------- Ranked horizontal bars ----------
export interface RankItem { label: string; value: number; sub?: string; color?: string; onClick?: () => void }

export function RankBars({ items, max, valueFmt = fmtInt, emptyMessage = 'No data in the selected period.' }: {
  items: RankItem[]; max?: number; valueFmt?: (v: number) => string; emptyMessage?: string;
}) {
  if (!items.length) return <EmptyState message={emptyMessage} />;
  const m = max ?? Math.max(...items.map((i) => i.value), 1);
  return (
    <div>
      {items.map((i) => (
        <div key={i.label} className={`rankbar-row${i.onClick ? ' clickable' : ''}`} onClick={i.onClick}
          title={i.sub ? `${i.label} — ${i.sub}` : i.label}>
          <div className="rankbar-label">{i.label}{i.sub && <div className="cell-sub">{i.sub}</div>}</div>
          <div className="rankbar-track"><div className="rankbar-fill" style={{ width: `${(i.value / m) * 100}%`, background: i.color ?? 'var(--s1)' }} /></div>
          <div className="rankbar-val">{valueFmt(i.value)}</div>
        </div>
      ))}
    </div>
  );
}

// ---------- Heatmap (two-dimensional comparison) ----------
export interface HeatmapProps {
  rows: string[];
  cols: string[];
  value: (row: string, col: string) => number | null;
  display?: (v: number) => string;
  /** Sequential blue ramp by default; pass diverging=true for polarity data. */
  diverging?: boolean;
  onCell?: (row: string, col: string) => void;
  maxOverride?: number;
}

const SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];
const DIV_NEG = ['#e34948', '#ee9392', '#f8d3d2'];
const DIV_POS = ['#d3e3f7', '#86b6ef', '#2a78d6'];

export function Heatmap({ rows, cols, value, display = (v) => String(Math.round(v)), diverging = false, onCell, maxOverride }: HeatmapProps) {
  const vals = rows.flatMap((r) => cols.map((c) => value(r, c))).filter((v): v is number => v !== null);
  if (!vals.length) return <EmptyState message="No data for this comparison." />;
  const maxAbs = maxOverride ?? Math.max(...vals.map(Math.abs), 0.001);
  const cellStyle = (v: number | null): CSSProperties => {
    if (v === null) return { background: 'var(--surface-2)', color: 'var(--ink-3)' };
    if (diverging) {
      if (Math.abs(v) < maxAbs * 0.12) return { background: '#f0efec', color: 'var(--ink-2)' };
      const ramp = v < 0 ? DIV_NEG : DIV_POS;
      const idx = Math.min(ramp.length - 1, Math.floor((Math.abs(v) / maxAbs) * ramp.length));
      const bg = v < 0 ? ramp[ramp.length - 1 - idx] : ramp[idx];
      const strong = idx >= ramp.length - 1;
      return { background: bg, color: strong ? '#fff' : 'var(--ink)' };
    }
    const idx = Math.min(SEQ.length - 1, Math.floor((v / maxAbs) * SEQ.length));
    return { background: SEQ[idx], color: idx >= 3 ? '#fff' : 'var(--ink)' };
  };
  return (
    <div className="table-wrap">
      <div className="heatmap" style={{ gridTemplateColumns: `minmax(110px, 1.3fr) repeat(${cols.length}, minmax(58px, 1fr))`, minWidth: cols.length * 64 + 120 }}>
        <div />
        {cols.map((c) => <div key={c} className="hm-head" title={c}>{c}</div>)}
        {rows.map((r) => (
          <Fragment key={r}>
            <div className="hm-rowlabel" title={r}>{r}</div>
            {cols.map((c) => {
              const v = value(r, c);
              return (
                <div key={c} className="hm-cell" style={cellStyle(v)} title={`${r} × ${c}: ${v === null ? 'no data' : display(v)}`}
                  onClick={v !== null && onCell ? () => onCell(r, c) : undefined}>
                  {v === null ? '–' : display(v)}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

// ---------- Funnel ----------
export function Funnel({ stages }: { stages: { label: string; count: number; source?: string }[] }) {
  if (!stages.length || stages[0].count === 0) return <EmptyState message="No calls in the selected period." />;
  const max = stages[0].count;
  // Ordinal blue ramp, no lighter than step 250 per palette rules
  const ramp = ['#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab'];
  return (
    <div>
      {stages.map((s, i) => (
        <div key={s.label} className="funnel-stage">
          <div style={{ color: 'var(--ink-2)', fontWeight: 550 }}>{s.label}{s.source === 'crm' && <div className="cell-sub">CRM-verified</div>}</div>
          <div><div className="funnel-bar" style={{ width: `${Math.max(3, (s.count / max) * 100)}%`, background: ramp[Math.min(i, ramp.length - 1)] }}>{fmtInt(s.count)}</div></div>
          <div className="cell-sub" style={{ textAlign: 'right' }}>
            {i === 0 ? '100%' : `${((s.count / max) * 100).toFixed(1)}% of calls`}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------- Sortable, paged table ----------
export interface Column<T> {
  key: string;
  label: string;
  num?: boolean;
  render: (row: T) => ReactNode;
  sortVal?: (row: T) => string | number;
}

export function DataTable<T>({ columns, rows, rowKey, onRow, pageSize = 15, initialSort, emptyMessage = 'No rows match the current filters.' }: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (r: T) => string;
  onRow?: (r: T) => void;
  pageSize?: number;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
  emptyMessage?: string;
}) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortVal) return rows;
    const sv = col.sortVal;
    return [...rows].sort((a, b) => {
      const va = sv(a); const vb = sv(b);
      const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb));
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const clampedPage = Math.min(page, pages - 1);
  const slice = sorted.slice(clampedPage * pageSize, (clampedPage + 1) * pageSize);

  if (!rows.length) return <EmptyState message={emptyMessage} />;

  return (
    <div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={c.num ? 'num' : ''} onClick={() => {
                  if (!c.sortVal) return;
                  setSort((s) => s?.key === c.key ? { key: c.key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: 'desc' });
                  setPage(0);
                }}>
                  {c.label}{sort?.key === c.key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={rowKey(r)} className={onRow ? 'clickable' : ''} onClick={onRow ? () => onRow(r) : undefined}>
                {columns.map((c) => <td key={c.key} className={c.num ? 'num' : ''}>{c.render(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <span>{fmtInt(sorted.length)} rows</span>
          <button className="btn small" disabled={clampedPage === 0} onClick={() => setPage(clampedPage - 1)}>← Prev</button>
          <span>Page {clampedPage + 1} of {pages}</span>
          <button className="btn small" disabled={clampedPage >= pages - 1} onClick={() => setPage(clampedPage + 1)}>Next →</button>
        </div>
      )}
    </div>
  );
}

// ---------- CSV export ----------
export function exportCsv(filename: string, header: string[], rows: (string | number | null)[][]) {
  const esc = (v: string | number | null) => {
    const s = v === null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [header, ...rows].map((r) => r.map(esc).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
