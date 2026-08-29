import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { BRAND } from '../config';
import { DIMENSION_KEYS, DIMENSION_LABELS, PRESET_LABEL, type DatePreset, type DimensionKey, type FilterState } from '../lib/filters';
import { EMPLOYEES, GEO, PRODUCT_SERIES, LANGUAGES, LEAD_SOURCES } from '../data/taxonomy';
import { useAppState, ROLE_PAGES, type Role } from '../state/AppState';
import { service, useAlerts } from '../state/useData';
import { fmtDate, fmtDateTime, shortName } from '../lib/format';
import { DATA_ANCHOR, DATASET_CALL_COUNT, DATASET_MIN_DATE, DATASET_MAX_DATE } from '../services/realService';

const isoDate = (d: Date) => d.toISOString().slice(0, 10);

const NAV: { path: string; label: string; icon: string; group: string }[] = [
  { path: '/', label: 'Executive Overview', icon: '◧', group: 'Insights' },
  { path: '/voice', label: 'Customer Voice & Sentiment', icon: '♡', group: 'Insights' },
  { path: '/faqs', label: 'FAQs & Knowledge Gaps', icon: '?', group: 'Insights' },
  { path: '/regions', label: 'Regional Intelligence', icon: '◉', group: 'Insights' },
  { path: '/sales', label: 'Sales & Objections', icon: '₹', group: 'Insights' },
  { path: '/agents', label: 'Agent Quality', icon: '★', group: 'Performance' },
  { path: '/actions', label: 'Next-Action Tracker', icon: '✓', group: 'Performance' },
  { path: '/calls', label: 'Call Explorer', icon: '≡', group: 'Performance' },
  { path: '/advanced-qa', label: 'Advanced QA', icon: '◆', group: 'Performance' },
  { path: '/review-sets', label: 'Review Sets', icon: '⊞', group: 'Performance' },
  { path: '/alerts', label: 'Alerts & Escalations', icon: '⚑', group: 'Operations' },
  { path: '/data', label: 'Data Quality & Config', icon: '⚙', group: 'Operations' },
];

const ROLES: Role[] = ['Management', 'Sales Manager', 'Service Manager', 'Quality Team', 'Agent'];

export function AppShell({ children }: { children: ReactNode }) {
  const { role, setRole } = useAppState();
  const { data: alerts } = useAlerts();
  const openCritical = alerts?.filter((a) => a.status === 'open' && a.severity === 'critical').length ?? 0;
  const allowed = ROLE_PAGES[role];
  const visible = NAV.filter((n) => allowed === 'all' || allowed.includes(n.path));
  const groups = [...new Set(visible.map((n) => n.group))];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="name">{BRAND.companyName}</div>
          <div className="sub">{BRAND.productLabel}</div>
        </div>
        {groups.map((g) => (
          <nav key={g} className="nav-group">
            <div className="nav-label">{g}</div>
            {visible.filter((n) => n.group === g).map((n) => (
              <NavLink key={n.path} to={n.path} end={n.path === '/'}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <span aria-hidden style={{ width: 14, textAlign: 'center' }}>{n.icon}</span>
                <span className="label">{n.label}</span>
                {n.path === '/alerts' && openCritical > 0 && <span className="badge-count">{openCritical}</span>}
              </NavLink>
            ))}
          </nav>
        ))}
        <div style={{ marginTop: 'auto', padding: 14, fontSize: 11, color: '#7d868e' }}>
          <div style={{ marginBottom: 6 }} className="label">Viewing as</div>
          <select className="filter-select" style={{ width: '100%', maxWidth: 'none' }} value={role}
            onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
      </aside>
      <div className="main">
        <TopBar />
        <main className="content">
          {service.isMock ? (
            <div className="mock-banner">
              <strong>Demo mode:</strong> {service.sourceLabel}. Insights are text-based (transcripts only — no voice-tone analysis). Connect live integrations to replace this data.
            </div>
          ) : (
            <div className="live-banner">
              <strong>Live data:</strong> {service.sourceLabel}. Insights are text-based (transcripts only — no voice-tone analysis).
              Periods run relative to the snapshot end date ({fmtDate(DATA_ANCHOR.toISOString())}), not today.
              <span className="prov-legend" style={{ marginLeft: 'auto' }}>
                <span className="item"><span className="prov-dot real" /> real</span>
                <span className="item"><span className="prov-dot partial" /> partial</span>
                <span className="item"><span className="prov-dot demo" /> demo data</span>
              </span>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

function Select({ value, onChange, options, placeholder, label }: {
  value: string; onChange: (v: string) => void; options: (string | [string, string])[]; placeholder: string; label?: string;
}) {
  return (
    <select className={`filter-select${value ? ' is-set' : ''}`} value={value} onChange={(e) => onChange(e.target.value)} aria-label={label ?? placeholder}>
      <option value="">{placeholder}</option>
      {options.map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return <option key={v} value={v}>{l}</option>;
      })}
    </select>
  );
}

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Filter values are stored as raw ids/codes; show what the user would recognise. */
function chipValue(k: DimensionKey, v: string): string {
  if (k === 'employee') return shortName(EMPLOYEES.find((e) => e.id === v)?.name ?? v);
  if (k === 'compliance') return v === 'flagged' ? 'flagged only' : v;
  if (k === 'search') return `“${truncate(v, 28)}”`;
  return truncate(v, 46);
}

/**
 * One chip per active filter, each clearable on its own.
 *
 * Drill-downs (useDrill) write straight into the global filter state and it
 * survives navigation, but several of the keys they set — city, outcome,
 * campaign, actionStatus, search — have no control in the bar above. Without
 * this row a drill leaves every page narrowed with no visible cause and, if it
 * is the only filter set, no way back short of reloading the page.
 */
function ActiveFilterChips() {
  const { filters, setFilters } = useAppState();
  const active = DIMENSION_KEYS.filter((k) => filters[k]);
  if (active.length === 0) return null;
  return (
    <div className="filter-chips">
      <span className="chips-label">Filtering by</span>
      {active.map((k) => (
        <button key={k} className="filter-chip" title={`Clear ${DIMENSION_LABELS[k]} filter`}
          onClick={() => setFilters({ [k]: '' } as Partial<FilterState>)}>
          <span className="chip-key">{DIMENSION_LABELS[k]}</span>
          <span className="chip-val">{chipValue(k, filters[k])}</span>
          <span className="chip-x" aria-hidden>✕</span>
        </button>
      ))}
    </div>
  );
}

export function TopBar() {
  const { filters, setFilters, resetFilters, role, savedViews, saveView, applyView, deleteView, exploreMode, setExploreMode } = useAppState();
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [showMore, setShowMore] = useState(false);
  useEffect(() => { service.lastRefresh().then(setRefreshedAt); }, []);

  const set = (k: keyof FilterState) => (v: string) => setFilters({ [k]: v } as Partial<FilterState>);
  const regions = [...new Set(GEO.map((g) => g.region))];
  const states = [...new Set(GEO.filter((g) => !filters.region || g.region === filters.region).map((g) => g.state))];
  const teams = [...new Set(EMPLOYEES.map((e) => e.team))];
  // Derived from DIMENSION_KEYS rather than a hand-kept list: a filter missing
  // from the count is one the Reset button never offers to clear.
  const activeCount = DIMENSION_KEYS.filter((k) => filters[k]).length;

  return (
    <div className="topbar">
      <div className="filterbar">
        <Select value={filters.preset} onChange={(v) => {
            const preset = (v || '30d') as DatePreset;
            // First time switching to Custom, seed sensible defaults (last 15
            // days of the dataset) rather than leaving the pickers empty.
            if (preset === 'custom' && !filters.customStart && !filters.customEnd) {
              const end = DATA_ANCHOR;
              const start = new Date(end.getTime() - 15 * 86400_000);
              setFilters({ preset, customStart: isoDate(start), customEnd: isoDate(end) });
            } else {
              setFilters({ preset });
            }
          }}
          options={Object.entries(PRESET_LABEL)} placeholder="Last 30 days" label="Period" />
        {filters.preset === 'custom' && (
          <>
            <input type="date" className="filter-select is-set" aria-label="From date"
              min={DATASET_MIN_DATE} max={filters.customEnd || DATASET_MAX_DATE}
              value={filters.customStart}
              onChange={(e) => setFilters({ customStart: e.target.value })} />
            <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>to</span>
            <input type="date" className="filter-select is-set" aria-label="To date"
              min={filters.customStart || DATASET_MIN_DATE} max={DATASET_MAX_DATE}
              value={filters.customEnd}
              onChange={(e) => setFilters({ customEnd: e.target.value })} />
          </>
        )}
        <Select value={filters.region} onChange={(v) => setFilters({ region: v, state: '', city: '' })} options={regions} placeholder="All regions" />
        <Select value={filters.state} onChange={set('state')} options={states} placeholder="All states" />
        <Select value={filters.team} onChange={(v) => setFilters({ team: v, employee: '' })} options={teams} placeholder="All teams" />
        <Select value={filters.employee} onChange={set('employee')} options={EMPLOYEES.map((e) => [e.id, shortName(e.name)] as [string, string])} placeholder="All employees" label="Employee" />
        <Select value={filters.product} onChange={set('product')} options={[...PRODUCT_SERIES]} placeholder="All products" />
        <button className="btn small" onClick={() => setShowMore(!showMore)}>{showMore ? 'Fewer filters' : `More filters${activeCount > 6 ? ` (${activeCount})` : ''}`}</button>
        {showMore && (
          <>
            <Select value={filters.direction} onChange={set('direction')} options={[['inbound', 'Inbound'], ['outbound', 'Outbound']]} placeholder="Direction" />
            <Select value={filters.language} onChange={set('language')} options={[...LANGUAGES]} placeholder="Language" />
            <Select value={filters.sentiment} onChange={set('sentiment')} options={[['positive', 'Positive'], ['neutral', 'Neutral'], ['negative', 'Negative']]} placeholder="Sentiment" />
            <Select value={filters.intent} onChange={set('intent')} options={[['high', 'High readiness'], ['medium', 'Medium'], ['low', 'Low'], ['none', 'None']]} placeholder="Purchase readiness" />
            <Select value={filters.customerType} onChange={set('customerType')} options={['New lead', 'Existing customer', 'Dealer', 'Architect/Designer']} placeholder="Customer type" />
            <Select value={filters.leadSource} onChange={set('leadSource')} options={[...LEAD_SOURCES]} placeholder="Lead source" />
            <Select value={filters.compliance} onChange={set('compliance')} options={[['flagged', 'Compliance-flagged only']]} placeholder="Compliance" />
            <label style={{ fontSize: 11.5, color: 'var(--ink-2)', display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              <input type="checkbox" checked={filters.includeLowConfidence} onChange={(e) => setFilters({ includeLowConfidence: e.target.checked })} />
              Include low-confidence transcripts
            </label>
          </>
        )}
        {activeCount > 0 && <button className="btn small danger" onClick={resetFilters}>Reset ({activeCount})</button>}
        <SavedViewsMenu savedViews={savedViews.map((v) => v.name)} onSave={saveView} onApply={applyView} onDelete={deleteView} />
      </div>
      <button className={`btn explain-button${exploreMode ? ' active' : ''}`} onClick={() => setExploreMode(!exploreMode)} aria-pressed={exploreMode}>
        {exploreMode ? '✓ Exit Explore mode' : '? Explore this page'}
      </button>
      <div className="refresh-note">
        {role !== 'Management' && <span style={{ marginRight: 8 }}>Role: <strong>{role}</strong></span>}
        <span className="dataset-total">Dataset: <strong>{DATASET_CALL_COUNT} total calls</strong></span>
        Last refresh: {refreshedAt ? fmtDateTime(refreshedAt) : '…'}
      </div>
      <ActiveFilterChips />
    </div>
  );
}

function SavedViewsMenu({ savedViews, onSave, onApply, onDelete }: {
  savedViews: string[]; onSave: (n: string) => void; onApply: (n: string) => void; onDelete: (n: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: 'relative' }}>
      <button className="btn small" onClick={() => setOpen(!open)}>Views ▾</button>
      {open && (
        <div style={{ position: 'absolute', top: '110%', right: 0, zIndex: 50, background: 'var(--surface)', border: '1px solid var(--grid)', borderRadius: 8, boxShadow: 'var(--shadow)', padding: 8, minWidth: 200 }}>
          {savedViews.length === 0 && <div style={{ fontSize: 11.5, color: 'var(--ink-3)', padding: '4px 6px' }}>No saved views yet.</div>}
          {savedViews.map((n) => (
            <div key={n} style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '3px 4px' }}>
              <button className="btn small" style={{ flex: 1, justifyContent: 'flex-start' }} onClick={() => { onApply(n); setOpen(false); }}>{n}</button>
              <button className="btn small danger" onClick={() => onDelete(n)} aria-label={`Delete view ${n}`}>✕</button>
            </div>
          ))}
          <button className="btn small primary" style={{ width: '100%', marginTop: 6, justifyContent: 'center' }}
            onClick={() => {
              const name = window.prompt('Name this view:');
              if (name) { onSave(name); setOpen(false); }
            }}>Save current filters…</button>
        </div>
      )}
    </span>
  );
}

export function PageHead({ title, desc, periodNote }: { title: string; desc?: string; periodNote?: string }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      {desc && <div className="desc">{desc}</div>}
      {periodNote && <div className="period-note">{periodNote}</div>}
    </div>
  );
}

/** Drill-down helper: set filters then land on Call Explorer. */
export function useDrill() {
  const navigate = useNavigate();
  const { setFilters } = useAppState();
  return (patch: Partial<FilterState>) => {
    const categoryOnly = Object.prototype.hasOwnProperty.call(patch, 'faqCategory') &&
      !Object.prototype.hasOwnProperty.call(patch, 'faqQuestion');
    setFilters(categoryOnly ? { ...patch, faqQuestion: '', faqStatus: '', faqSentimentAfter: '' } : patch);
    navigate('/calls');
  };
}
