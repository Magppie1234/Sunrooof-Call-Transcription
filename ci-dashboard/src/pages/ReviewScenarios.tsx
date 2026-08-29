import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHead } from '../components/layout';
import { Card, KpiCard, Pill, EmptyState, exportCsv, type PillTone } from '../components/ui';
import { fmtInt } from '../lib/format';
import data from '../data/real/review_scenarios.json';

/**
 * Curated listening sets, in two families.
 *
 * The lead-level sets group by CRM record: a single call in isolation hides what
 * actually happened with a customer — the useful unit is the whole conversation
 * history, and whether it ended in a quotation. "Raw Quote" is the Zoho Deals
 * stage reached once the layout has been sent and a rough quotation given.
 *
 * The contradiction cohorts are call-level: four calls each where two systems
 * disagree about the same call, so one of them is provably wrong. They carry the
 * CRM stage and the QA audit result alongside the AI reading, because the point
 * of listening is to decide which side is at fault.
 *
 * Independent of the global date filter, like Advanced QA: these sets span June
 * and July and would otherwise be hidden by the 30-day default.
 */

interface Qa {
  audited: boolean; score: number | null; tier: string | null;
  auto_zero: boolean | null; needs_review: boolean | null;
}
interface ScenarioCall {
  call_id: string; agent: string | null; customer: string | null;
  date: string; minutes: number; outcome: string | null;
  contact_number: number; summary: string;
  // present on contradiction cohorts only
  crm_stage?: string | null; dataset_outcome?: string | null;
  sentiment?: string | null; confidence?: number | null; qa?: Qa | null;
}
interface Lead { lead: string; stage?: string; contradiction?: string; calls: ScenarioCall[] }
interface Data {
  scenario_1_multi_call_no_raw_quote: Lead[];
  scenario_2_multi_call_with_raw_quote: Lead[];
  scenario_3_single_long_call_with_raw_quote: Lead[];
  outlier_1_quotation_claimed_crm_disagrees: Lead[];
  outlier_2_positive_outcome_crm_not_interested: Lead[];
  outlier_3_positive_sentiment_lead_died: Lead[];
  outlier_4_not_connected_long_call: Lead[];
}
const D = data as unknown as Data;

interface Tab {
  key: string; label: string; rows: Lead[]; note: string; group: 'lead' | 'outlier';
}
const TABS: Tab[] = [
  {
    key: 's2', group: 'lead', label: 'Multiple calls → quotation',
    rows: D.scenario_2_multi_call_with_raw_quote,
    note: 'Two or three conversations that reached a Raw Quote. What a working sequence looks like.',
  },
  {
    key: 's3', group: 'lead', label: 'One long call → quotation',
    rows: D.scenario_3_single_long_call_with_raw_quote,
    note: 'A single call of 10+ minutes that reached a Raw Quote — one conversation doing the whole job.',
  },
  {
    key: 's1', group: 'lead', label: 'Multiple calls, no quotation',
    rows: D.scenario_1_multi_call_no_raw_quote,
    note: 'Two or three conversations that never reached a quotation. Where the learning is likely to be.',
  },
  {
    key: 'o1', group: 'outlier', label: 'Quotation claimed, CRM disagrees',
    rows: D.outlier_1_quotation_claimed_crm_disagrees,
    note: 'The call was read as a quotation request, but the CRM record never reached Raw Quote. '
      + 'Either the AI over-read the ask, or the stage was never moved.',
  },
  {
    key: 'o2', group: 'outlier', label: 'Positive outcome, CRM not interested',
    rows: D.outlier_2_positive_outcome_crm_not_interested,
    note: 'The call was read as interested, a site visit or a demo, and the CRM record is '
      + 'closed as Not Interested.',
  },
  {
    key: 'o3', group: 'outlier', label: 'Positive sentiment, lead died',
    rows: D.outlier_3_positive_sentiment_lead_died,
    note: 'Sentiment came out positive and the lead is closed Not Interested or Non-Serviceable. '
      + 'Tests whether sentiment tracks call tone rather than customer intent.',
  },
  {
    key: 'o4', group: 'outlier', label: 'Not connected, yet minutes of audio',
    rows: D.outlier_4_not_connected_long_call,
    note: 'Marked not connected, but the recording runs for minutes. A call that never connected '
      + 'cannot have a conversation in it.',
  },
];

const outcomeTone = (o: string | null): PillTone =>
  o === 'interested' ? 'good'
    : o === 'not_interested' ? 'critical'
      : o === 'not_reachable' ? 'neutral' : 'warning';

const tierTone = (t: string | null | undefined): PillTone =>
  t === 'GOLD' ? 'good'
    : t === 'SILVER' ? 'info'
      : t === 'BRONZE' ? 'warning'
        : t === 'DEVELOPING' ? 'serious'
          : t === 'AT_RISK' ? 'critical' : 'neutral';

/** The QA audit cell: whether it was scored at all, then the score it landed on. */
function QaCell({ qa }: { qa?: Qa | null }) {
  if (!qa) return <span style={{ color: 'var(--ink-3)' }}>—</span>;
  if (!qa.audited) return <Pill tone="neutral">not audited</Pill>;
  return (
    <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
      <Pill tone={tierTone(qa.tier)}>{qa.score ?? '—'} {qa.tier ?? ''}</Pill>
      {qa.auto_zero && <Pill tone="critical">auto-zero</Pill>}
    </span>
  );
}

/** A small labelled value — the unit the contradiction card is built from. */
const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <div style={{ display: 'grid', gap: 3, alignContent: 'end' }}>
    <span style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.04em',
                   color: 'var(--ink-3)', fontWeight: 650, whiteSpace: 'nowrap' }}>{label}</span>
    {children}
  </div>
);

/**
 * One call from a contradiction cohort.
 *
 * Deliberately not a table row. These calls carry eight short values and one
 * long sentence; in a nine-column table the sentence gets whatever width is
 * left over and wraps into a ladder of single words, while every other cell
 * sits in a tall column of whitespace. Here the two disagreeing values get top
 * billing side by side — that comparison is the entire reason the call is on
 * the list — and the summary runs the full width of the card.
 */
function OutlierCard({ call, onOpen }: { call: ScenarioCall; onOpen: () => void }) {
  return (
    <div className="outlier-card" onClick={onOpen} role="button" tabIndex={0}
         onKeyDown={(e) => {
           if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); }
         }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap',
                    fontSize: 12.5, color: 'var(--ink-2)' }}>
        <strong style={{ color: 'var(--ink)', fontSize: 13.5 }}>{call.agent ?? 'Unknown agent'}</strong>
        {call.customer && <span style={{ color: 'var(--ink-3)' }}>→ {call.customer}</span>}
        <span style={{ color: 'var(--ink-3)' }}>·</span>
        <span>{call.date}</span>
        <span style={{ color: 'var(--ink-3)' }}>·</span>
        <span>{call.minutes} min</span>
        <code style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ink-3)' }}>{call.call_id}</code>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap',
                    padding: '10px 12px', borderRadius: 8, background: 'var(--surface-2)' }}>
        <Field label="AI read the call as">
          <Pill tone="info">{call.dataset_outcome ?? call.outcome ?? '—'}</Pill>
        </Field>
        <span style={{ fontSize: 12, color: 'var(--ink-3)', paddingBottom: 4, fontStyle: 'italic' }}>
          but
        </span>
        <Field label="CRM record says">
          <Pill tone="warning">{call.crm_stage ?? '—'}</Pill>
        </Field>
        <Field label="Quality audit"><QaCell qa={call.qa} /></Field>
        <Field label="Sentiment">
          <span style={{ fontSize: 12.5 }}>{call.sentiment ?? '—'}</span>
        </Field>
        <Field label="Transcript conf.">
          <span style={{ fontSize: 12.5, fontVariantNumeric: 'tabular-nums' }}>
            {call.confidence ?? '—'}
          </span>
        </Field>
      </div>

      <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>
        {call.summary}
      </p>
    </div>
  );
}

export default function ReviewScenarios() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<string>('s2');
  const [search, setSearch] = useState('');

  const active = TABS.find((t) => t.key === tab) ?? TABS[0];
  const isOutlier = active.group === 'outlier';

  const leads = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return active.rows;
    return active.rows.filter((l) =>
      l.calls.some((c) => `${c.call_id} ${c.agent ?? ''} ${c.customer ?? ''}`
        .toLowerCase().includes(q)));
  }, [active, search]);

  const totalCalls = active.rows.reduce((a, l) => a + l.calls.length, 0);
  const contradiction = active.rows[0]?.contradiction;
  const flat = leads.flatMap((l) => l.calls);

  const kpiRow = (group: 'lead' | 'outlier') => (
    <div className="kpi-grid">
      {TABS.filter((t) => t.group === group).map((t) => (
        <KpiCard key={t.key} label={t.label} value={t.rows.length} format={fmtInt}
          denomNote={group === 'lead'
            ? `${t.rows.reduce((a, l) => a + l.calls.length, 0)} calls`
            : `${t.rows.reduce((a, l) => a + l.calls.length, 0)} calls to listen to`}
          accent={t.key === tab ? 'var(--s1)' : 'var(--baseline)'}
          onClick={() => setTab(t.key)} />
      ))}
    </div>
  );

  const sectionLabel = (text: string, sub: string) => (
    <div style={{ margin: '18px 0 8px' }}>
      <h2 style={{ fontSize: 14, letterSpacing: 0.3, textTransform: 'uppercase',
                   color: 'var(--ink-3)', margin: 0 }}>{text}</h2>
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: '2px 0 0' }}>{sub}</p>
    </div>
  );

  return (
    <>
      <PageHead
        title="Review sets — calls to listen to"
        desc="Leads grouped by what actually happened, plus call-level cohorts where two systems disagree."
        periodNote="Not affected by the date filter · grouped by the CRM record each call is attached to"
      />

      {sectionLabel('By lead', 'How many conversations there were, and whether they reached a quotation.')}
      {kpiRow('lead')}

      {sectionLabel('Contradiction cohorts',
        'Four calls each where two systems disagree about the same call, so one of them is wrong.')}
      {kpiRow('outlier')}

      <Card
        title={active.label}
        sub={`${active.note}  ·  ${isOutlier ? `${totalCalls} calls` : `${active.rows.length} leads, ${totalCalls} calls`}`}
        right={
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="filter-select is-set" placeholder="Search agent, customer, id…"
              value={search} onChange={(e) => setSearch(e.target.value)}
              aria-label="Search review sets" style={{ minWidth: 210 }} />
            <button className="btn" onClick={() => (isOutlier
              ? exportCsv(
                `review-${active.key}.csv`,
                ['call_id', 'date', 'agent', 'customer', 'minutes', 'ai_outcome',
                  'crm_stage', 'sentiment', 'confidence', 'qa_audited', 'qa_score', 'qa_tier',
                  'qa_auto_zero'],
                flat.map((c) => [
                  c.call_id, c.date, c.agent ?? '', c.customer ?? '', c.minutes,
                  c.dataset_outcome ?? c.outcome ?? '', c.crm_stage ?? '', c.sentiment ?? '',
                  c.confidence ?? '', c.qa?.audited ? 'yes' : 'no', c.qa?.score ?? '',
                  c.qa?.tier ?? '', c.qa?.auto_zero ? 'yes' : 'no']),
              )
              : exportCsv(
                `review-${active.key}.csv`,
                ['lead', 'contact_number', 'call_id', 'date', 'minutes', 'agent', 'customer', 'outcome'],
                leads.flatMap((l) => l.calls.map((c) => [
                  l.lead, c.contact_number, c.call_id, c.date, c.minutes,
                  c.agent ?? '', c.customer ?? '', c.outcome ?? ''])),
              ))}>Export CSV</button>
          </div>
        }>
        {leads.length === 0
          ? <EmptyState message="No calls match." hint="Clear the search box." />
          : isOutlier
            ? (
              <>
                {contradiction && (
                  <p style={{ fontSize: 12.5, color: 'var(--ink-2)', margin: '0 0 12px' }}>
                    <strong>What disagrees:</strong> {contradiction}
                  </p>
                )}
                <div style={{ display: 'grid', gap: 12 }}>
                  {flat.map((c) => (
                    <OutlierCard key={c.call_id} call={c}
                      onOpen={() => navigate(`/calls/${c.call_id}`)} />
                  ))}
                </div>
              </>
            )
            : (
              <div style={{ display: 'grid', gap: 14 }}>
                {leads.slice(0, 60).map((l) => {
                  const head = l.calls[0];
                  const total = l.calls.reduce((a, c) => a + c.minutes, 0);
                  return (
                    <div key={l.lead}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8,
                                    alignItems: 'baseline', marginBottom: 4 }}>
                        <strong>{head.agent ?? 'Unknown agent'}</strong>
                        <span style={{ color: 'var(--ink-2)' }}>→ {head.customer || 'Unknown'}</span>
                        {l.stage && <Pill tone="good">{l.stage}</Pill>}
                        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--ink-3)' }}>
                          {l.calls.length} call{l.calls.length > 1 ? 's' : ''} · {total.toFixed(1)} min total
                        </span>
                      </div>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th style={{ width: 50 }}>Call</th>
                              <th style={{ width: 190 }}>Call ID</th>
                              <th style={{ width: 100 }}>Date</th>
                              <th className="num" style={{ width: 80 }}>Length</th>
                              <th style={{ width: 150 }}>Outcome</th>
                              <th>What happened</th>
                            </tr>
                          </thead>
                          <tbody>
                            {l.calls.map((c) => (
                              <tr key={c.call_id} style={{ cursor: 'pointer' }}
                                  onClick={() => navigate(`/calls/${c.call_id}`)}>
                                <td>#{c.contact_number}</td>
                                <td><code style={{ fontSize: 11 }}>{c.call_id}</code></td>
                                <td>{c.date}</td>
                                <td className="num">{c.minutes} min</td>
                                <td><Pill tone={outcomeTone(c.outcome)}>{c.outcome ?? '—'}</Pill></td>
                                <td style={{ fontSize: 12, color: 'var(--ink-2)' }}>{c.summary}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })}
                {leads.length > 60 && (
                  <p style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                    Showing the 60 longest of {leads.length} leads. Export the CSV for the full set.
                  </p>
                )}
              </div>
            )}
      </Card>
    </>
  );
}
