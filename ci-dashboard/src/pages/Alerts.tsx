import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHead } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, Pill, exportCsv, EmptyState, type PillTone } from '../components/ui';
import { useAlerts, service, useFilteredData } from '../state/useData';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { useAppState } from '../state/AppState';
import { fmtDateTime, fmtInt } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { AlertSeverity } from '../types/domain';

const SEV_TONE: Record<AlertSeverity, PillTone> = { critical: 'critical', high: 'serious', medium: 'warning' };

export default function Alerts() {
  const { data: alerts, loading, error, refresh } = useAlerts();
  const { data: d } = useFilteredData();
  const { filters } = useAppState();
  const navigate = useNavigate();
  const [sev, setSev] = useState<'all' | AlertSeverity>('all');
  const [showResolved, setShowResolved] = useState(false);

  if (loading && !alerts) return <Loading label="Evaluating alert rules…" />;
  if (error) return <ErrorState message={error} />;
  if (!alerts) return null;

  const open = alerts.filter((a) => a.status !== 'resolved');
  const visible = alerts
    .filter((a) => (showResolved ? true : a.status !== 'resolved'))
    .filter((a) => (sev === 'all' ? true : a.severity === sev));

  return (
    <>
      <PageHead title="Alerts & Escalations"
        desc="Rule-driven alerts with severity, owner, evidence, recommended response and a resolution deadline. Critical alerts require manual review before any customer-facing action — see docs/09-alert-sla-rules.md for every rule."
        periodNote={d ? scopeNote(d, filters.preset) : undefined} />
      {d && <ScopeBanner d={d} />}

      <div className="kpi-grid">
        <KpiCard label="Open alerts" prov="alerts.rules" value={open.length} denomNote={`of ${fmtInt(alerts.length)} raised this period`} />
        <KpiCard label="Critical (manual review)" prov="alerts.rules" value={open.filter((a) => a.severity === 'critical').length} accent="var(--critical)" invertDelta onClick={() => setSev('critical')} />
        <KpiCard label="High" prov="alerts.rules" value={open.filter((a) => a.severity === 'high').length} accent="var(--serious)" onClick={() => setSev('high')} />
        <KpiCard label="Medium" prov="alerts.rules" value={open.filter((a) => a.severity === 'medium').length} accent="var(--warning)" onClick={() => setSev('medium')} />
        <KpiCard label="Past resolution deadline" prov="alerts.workflow" value={open.filter((a) => new Date(a.deadline) < new Date()).length} accent="var(--critical)" invertDelta />
      </div>

      <div className="tabs" style={{ marginTop: 16 }}>
        {(['all', 'critical', 'high', 'medium'] as const).map((s) => (
          <button key={s} className={`tab ${sev === s ? 'active' : ''}`} onClick={() => setSev(s)}>
            {s === 'all' ? `All (${open.length})` : `${s[0].toUpperCase()}${s.slice(1)} (${open.filter((a) => a.severity === s).length})`}
          </button>
        ))}
        <label style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 12, color: 'var(--ink-2)', display: 'inline-flex', gap: 5, alignItems: 'center' }}>
          <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} /> Show resolved
        </label>
        <button className="btn small" style={{ alignSelf: 'center', marginLeft: 8 }} onClick={() => exportCsv('alerts.csv',
          ['ID', 'Severity', 'Type', 'Customer', 'Owner', 'Reason', 'Evidence', 'Recommended response', 'Deadline', 'Status'],
          visible.map((a) => [a.id, a.severity, a.type, a.customerName, a.ownerEmployeeId ? EMPLOYEES.find((e) => e.id === a.ownerEmployeeId)?.name ?? a.ownerEmployeeId : 'Management', a.reason, a.evidence, a.recommended, a.deadline, a.status]))}>
          Export CSV
        </button>
      </div>

      {visible.length === 0 ? (
        <Card><EmptyState message="No alerts in this bucket." hint="Alerts are recomputed whenever filters or data change." /></Card>
      ) : (
        <div className="grid" style={{ gap: 10 }}>
          {visible.map((a) => {
            const overdue = a.status !== 'resolved' && new Date(a.deadline) < new Date();
            return (
              <Card key={a.id}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Pill tone={SEV_TONE[a.severity]}>{a.severity.toUpperCase()}</Pill>
                  <strong>{a.type}</strong>
                  {a.customerName && <span className="cell-sub">· {a.customerName}</span>}
                  <span className="cell-sub">· Owner: {a.ownerEmployeeId ? EMPLOYEES.find((e) => e.id === a.ownerEmployeeId)?.name ?? a.ownerEmployeeId : 'Management'}</span>
                  <span className={`cell-sub ${overdue ? 'delta down' : ''}`} style={{ marginLeft: 'auto' }}>
                    {overdue ? '⚠ past deadline: ' : 'resolve by '}{fmtDateTime(a.deadline)}
                  </span>
                </div>
                <div style={{ fontSize: 13, marginTop: 6 }}>{a.reason}</div>
                <div className="cell-sub" style={{ marginTop: 3 }}><strong>Evidence:</strong> {a.evidence}</div>
                <div className="cell-sub" style={{ marginTop: 2 }}><strong>Recommended response:</strong> {a.recommended}</div>
                <div className="chip-row" style={{ marginTop: 8 }}>
                  {a.callId && <button className="btn small" onClick={() => navigate(`/calls/${a.callId}`)}>Open call →</button>}
                  {a.status === 'open' && <button className="btn small" onClick={async () => { await service.setAlertStatus(a.id, 'acknowledged'); refresh(); }}>Acknowledge</button>}
                  {a.status !== 'resolved'
                    ? <button className="btn small primary" onClick={async () => { await service.setAlertStatus(a.id, 'resolved'); refresh(); }}>Mark resolved</button>
                    : <Pill tone="good">resolved</Pill>}
                  {a.status === 'acknowledged' && <Pill tone="info">acknowledged</Pill>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
