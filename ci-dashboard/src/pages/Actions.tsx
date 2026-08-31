import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHead } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, DataTable, Pill, exportCsv, type Column, type PillTone } from '../components/ui';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { service, useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { allActions } from '../lib/metrics';
import { fmtDateTime, fmtInt, fmtTimestamp } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { NextAction, SlaStatus } from '../types/domain';

const SLA_TONE: Record<SlaStatus, PillTone> = {
  on_track: 'info', due_today: 'warning', overdue: 'critical', met: 'good', breached: 'serious',
};
const SLA_LABEL: Record<SlaStatus, string> = {
  on_track: 'On track', due_today: 'Due today', overdue: 'Overdue', met: 'SLA met', breached: 'SLA breached',
};

type Tab = 'all' | 'committed' | 'ai' | 'due_today' | 'overdue' | 'completed';

export default function Actions() {
  const { data: d, loading, error, refresh } = useFilteredData();
  const { filters } = useAppState();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('all');
  const [busy, setBusy] = useState<string | null>(null);

  const actions = useMemo(() => (d ? allActions(d.analysed) : []), [d]);

  if (loading && !d) return <Loading label="Loading commitments and actions…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const open = actions.filter((a) => a.status !== 'completed' && a.status !== 'rejected');
  const committed = actions.filter((a) => a.source === 'committed');
  const ai = actions.filter((a) => a.source === 'ai_recommended');
  const dueToday = open.filter((a) => a.slaStatus === 'due_today');
  const overdue = open.filter((a) => a.slaStatus === 'overdue');
  const completed = actions.filter((a) => a.status === 'completed');

  const visible = tab === 'all' ? actions
    : tab === 'committed' ? committed
    : tab === 'ai' ? ai
    : tab === 'due_today' ? dueToday
    : tab === 'overdue' ? overdue
    : completed;

  const mutate = async (id: string, patch: Parameters<typeof service.updateAction>[1]) => {
    setBusy(id);
    await service.updateAction(id, patch);
    setBusy(null);
    refresh();
  };

  const cols: Column<NextAction>[] = [
    {
      key: 'action', label: 'Action', render: (a) => (
        <div style={{ maxWidth: 250 }}>
          <strong>{a.action}</strong>
          <div className="cell-sub">{a.reason}</div>
          <div className="cell-sub">Channel: {a.channel}</div>
        </div>
      ), sortVal: (a) => a.action,
    },
    {
      key: 'source', label: 'Source', render: (a) => a.source === 'committed'
        ? <Pill tone="info">Committed · {a.committedBy}</Pill>
        : <Pill tone="neutral">AI-recommended</Pill>, sortVal: (a) => a.source,
    },
    {
      key: 'customer', label: 'Customer / call', render: (a) => (
        <div>
          <span style={{ overflowWrap: 'anywhere' }}>{a.customerName}</span>
          <div className="cell-sub">
            <a onClick={(e) => { e.stopPropagation(); navigate(`/calls/${a.callId}?t=${a.transcriptRef ?? 0}`); }} style={{ cursor: 'pointer' }}>
              {a.callId} @ {fmtTimestamp(a.transcriptRef ?? 0)} →
            </a>
          </div>
        </div>
      ), sortVal: (a) => a.customerName,
    },
    { key: 'owner', label: 'Owner', render: (a) => EMPLOYEES.find((e) => e.id === a.ownerEmployeeId)?.name ?? a.ownerEmployeeId, sortVal: (a) => a.ownerEmployeeId },
    { key: 'priority', label: 'Priority', render: (a) => <Pill tone={a.priority === 'P1' ? 'critical' : a.priority === 'P2' ? 'warning' : 'neutral'}>{a.priority}</Pill>, sortVal: (a) => a.priority },
    { key: 'due', label: 'Due', num: true, render: (a) => fmtDateTime(a.dueDate), sortVal: (a) => a.dueDate },
    { key: 'sla', label: 'SLA', render: (a) => <Pill tone={SLA_TONE[a.slaStatus]}>{SLA_LABEL[a.slaStatus]}</Pill>, sortVal: (a) => a.slaStatus },
    {
      key: 'status', label: 'Status', render: (a) => (
        <Pill tone={a.status === 'completed' ? 'good' : a.status === 'rejected' ? 'neutral' : a.status === 'pending' ? 'warning' : 'info'}>
          {a.status === 'pending' ? 'Pending approval' : a.status.replace('_', ' ')}
        </Pill>
      ), sortVal: (a) => a.status,
    },
    { key: 'crm', label: 'CRM task', render: (a) => a.crmTaskLinked ? <Pill tone="good">linked</Pill> : <span className="cell-sub">not linked</span>, sortVal: (a) => String(a.crmTaskLinked) },
    {
      key: 'controls', label: 'Manage', render: (a) => {
        if (a.status === 'completed' || a.status === 'rejected') return <span className="cell-sub">—</span>;
        const disabled = busy === a.id;
        return (
          <div className="chip-row" onClick={(e) => e.stopPropagation()}>
            {a.status === 'pending' && <button className="btn small primary" disabled={disabled} onClick={() => mutate(a.id, { status: 'approved' })}>Approve</button>}
            {a.status === 'pending' && <button className="btn small danger" disabled={disabled} onClick={() => mutate(a.id, { status: 'rejected' })}>Reject</button>}
            {a.status !== 'pending' && <button className="btn small" disabled={disabled} onClick={() => mutate(a.id, { status: 'completed' })}>Complete</button>}
            <button className="btn small" disabled={disabled} onClick={() => {
              const days = window.prompt('Reschedule: days from now?', '2');
              if (days && !Number.isNaN(+days)) {
                const due = new Date(); due.setDate(due.getDate() + +days); due.setHours(17, 0, 0, 0);
                mutate(a.id, { dueDate: due.toISOString() });
              }
            }}>Reschedule</button>
            <select className="filter-select" style={{ padding: '2px 22px 2px 6px', fontSize: 11 }} value={a.ownerEmployeeId} disabled={disabled}
              onChange={(e) => mutate(a.id, { ownerEmployeeId: e.target.value })} aria-label="Reassign owner">
              {EMPLOYEES.map((e) => <option key={e.id} value={e.id}>{e.name.split(' ')[0]}</option>)}
            </select>
          </div>
        );
      },
    },
  ];

  return (
    <>
      <PageHead title="Next-Action & Commitment Tracker"
        desc="Committed next actions (explicit promises on the call) are tracked separately from AI-recommended actions, which require human approval. The system never auto-applies discounts, closes or disqualifies leads, or changes CRM stages from transcript inference alone."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Open actions" prov="actions.list" value={open.length} denomNote={`of ${fmtInt(actions.length)} in period`}
          explain={<>Counts next steps extracted from the analysed calls whose status is <strong>pending, approved, or in progress</strong>. Completed and rejected actions are not included.</>} />
        <KpiCard label="Committed on calls" prov="actions.list" value={committed.length} accent="var(--s1)"
          explain={<>Counts actions based on an <strong>explicit promise made during the call</strong>, such as “I will send the quotation.” It includes committed actions in any status.</>} />
        <KpiCard label="AI-recommended (need approval)" prov="actions.list" value={ai.filter((a) => a.status === 'pending').length} denomNote={`of ${fmtInt(ai.length)} AI-suggested`} accent="var(--warning)"
          explain={<>Counts follow-ups suggested by the AI from the transcript that are still <strong>pending human approval</strong>. They are suggestions, not confirmed customer or agent commitments.</>} />
        <KpiCard label="Due today" prov="actions.sla" value={dueToday.length} accent="var(--warning)"
          explain={<>Counts open actions whose calculated or stated due date falls on the dashboard’s current reference date.</>} />
        <KpiCard label="Overdue" prov="actions.sla" value={overdue.length} accent="var(--critical)" invertDelta
          explain={<>Counts open actions whose due date has passed and which have not been completed or rejected.</>} />
        <KpiCard label="Completed in period" prov="actions.crmSync" value={completed.length} denomNote={`${completed.filter((a) => a.slaStatus === 'met').length} within SLA`} accent="var(--good)"
          explain={<>Counts extracted actions currently marked <strong>completed</strong>. “Within SLA” means they were completed by their deadline. In this static dashboard, status changes are stored only until the page is refreshed.</>} />
      </div>

      <div className="tabs" style={{ marginTop: 16 }}>
        {([['all', `All (${actions.length})`], ['committed', `Committed (${committed.length})`], ['ai', `AI-recommended (${ai.length})`], ['due_today', `Due today (${dueToday.length})`], ['overdue', `Overdue (${overdue.length})`], ['completed', `Completed (${completed.length})`]] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{label}</button>
        ))}
        <button className="btn small" style={{ marginLeft: 'auto', alignSelf: 'center' }} onClick={() => exportCsv('actions.csv',
          ['ID', 'Action', 'Source', 'Customer', 'Call', 'Owner', 'Priority', 'Due', 'SLA', 'Status', 'Channel', 'Reason'],
          visible.map((a) => [a.id, a.action, a.source, a.customerName, a.callId, EMPLOYEES.find((e) => e.id === a.ownerEmployeeId)?.name ?? a.ownerEmployeeId, a.priority, a.dueDate, SLA_LABEL[a.slaStatus], a.status, a.channel, a.reason]))}>
          Export CSV
        </button>
      </div>

      <Card explain={<>This table lists every extracted next action matching the selected tab and page filters. <strong>Source</strong> separates explicit call commitments from AI suggestions; <strong>due/SLA</strong> shows timing; and <strong>status</strong> shows whether the action is awaiting approval, active, completed, or rejected.</>}>
        <DataTable columns={cols} rows={visible} rowKey={(a) => a.id} pageSize={12}
          initialSort={{ key: 'due', dir: 'asc' }}
          onRow={(a) => navigate(`/calls/${a.callId}?t=${a.transcriptRef ?? 0}`)}
          emptyMessage="No actions in this bucket for the current filters." />
      </Card>
    </>
  );
}
