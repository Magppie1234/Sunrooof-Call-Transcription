import { useEffect, useMemo, useState } from 'react';
import { PageHead } from '../components/layout';
import { Card, KpiCard, Pill, DataTable, EmptyState, exportCsv, type Column, type PillTone } from '../components/ui';
import { fmtInt } from '../lib/format';
import qaData from '../data/real/qa_audits.slim.json';
import changeData from '../data/real/scorecard_change_review.json';

/**
 * Advanced QA — the 100-point SUNROOOF PSM scorecard.
 *
 * Deliberately independent of the global date/dimension filters. Audited calls
 * are processed in call-id order, which starts in June, while the global filter
 * defaults to the last 30 days — so every audited call would be filtered out
 * and the page would look empty. This reads its own dataset and filters itself.
 */

interface Evidence { t: string | null; q: string }
interface Criterion {
  id: number; name: string; max: number; label: string; points: number;
  applicable: boolean; reason: string; evidence: Evidence[];
  missed?: string[]; partial?: string[]; unverified?: string[];
}
interface Flag { code: string; observed: string; deduction?: number }
interface QaCall {
  id: string; agent: string | null; customer: string | null; date: string;
  durationSec: number; summary: string; sentiment: string | null; outcome: string | null;
  score: number | null; preDeduction: number | null; earned: number; adjustedMax: number;
  deduction: number; tier: string; autoZero: boolean; autoZeroCodes: string[];
  criticalMisses: Flag[]; redFlags: Flag[]; needsReview: boolean; reviewReasons: string[];
  status: string; /** Absent in the slim list payload; fetched per call by the drawer. */ criteria?: Criterion[];
  coaching: { strengths: unknown[]; improvements: unknown[]; summary: string };
}
interface QaData {
  generatedAt: string; corpusSize: number; auditedCount: number;
  model: string; scorecard: string; calls: QaCall[];
}

const DATA = qaData as unknown as QaData;

interface CritChange { criterion: number; name: string; before: number; after: number; max: number;
  verdict?: string; missed?: string[]; partial?: string[]; unknown?: string[];
  metCount?: number; totalPoints?: number;
  evidence: string; timestamp?: string | null }
interface ChangeCall {
  id: string; agent: string | null; customer: string | null; date: string; durationSec: number;
  summary: string; crmLink: string; delta: number | null;
  before: { score: number | null; tier: string; autoZero: string[] };
  after: { score: number | null; tier: string; autoZero: string[] };
  criterionChanges: CritChange[];
}
const CHANGES = changeData as unknown as { generatedAt: string; note: string; calls: ChangeCall[] };

const TIER_TONE: Record<string, PillTone> = {
  GOLD: 'good', SILVER: 'good', BRONZE: 'warning',
  DEVELOPING: 'warning', AT_RISK: 'critical', NOT_SCORED: 'neutral',
};
const TIER_ORDER = ['GOLD', 'SILVER', 'BRONZE', 'DEVELOPING', 'AT_RISK', 'NOT_SCORED'];

const mins = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const text = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));

export default function AdvancedQa() {
  const [tier, setTier] = useState('');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<QaCall | null>(null);

  const calls = useMemo(() => {
    const q = search.trim().toLowerCase();
    return DATA.calls.filter((c) => {
      if (tier && c.tier !== tier) return false;
      if (!q) return true;
      return `${c.id} ${c.agent ?? ''} ${c.customer ?? ''} ${c.summary}`.toLowerCase().includes(q);
    });
  }, [tier, search]);

  const scored = DATA.calls.filter((c) => c.score !== null);
  const notScored = DATA.calls.length - scored.length;
  const mean = scored.length ? scored.reduce((a, c) => a + (c.score ?? 0), 0) / scored.length : 0;
  const autoZero = DATA.calls.filter((c) => c.autoZero).length;
  const tierCounts = TIER_ORDER
    .map((t) => ({ tier: t, n: DATA.calls.filter((c) => c.tier === t).length }))
    .filter((r) => r.n > 0);

  const columns: Column<QaCall>[] = [
    { key: 'id', label: 'Call ID', render: (c) => <code style={{ fontSize: 11 }}>{c.id}</code>, sortVal: (c) => c.id },
    { key: 'date', label: 'Date', render: (c) => c.date, sortVal: (c) => c.date },
    { key: 'agent', label: 'Agent', render: (c) => c.agent ?? '—', sortVal: (c) => c.agent ?? '' },
    { key: 'len', label: 'Length', num: true, render: (c) => mins(c.durationSec), sortVal: (c) => c.durationSec },
    {
      key: 'score', label: 'Score', num: true, sortVal: (c) => (c.score ?? -1),
      render: (c) => (c.score === null
        ? <span style={{ color: 'var(--ink-3)' }}>not scored</span>
        : <strong>{c.score.toFixed(1)}</strong>),
    },
    {
      key: 'tier', label: 'Tier', sortVal: (c) => c.tier,
      render: (c) => <Pill tone={TIER_TONE[c.tier] ?? 'neutral'}>{c.tier.replace('_', ' ')}</Pill>,
    },
    {
      key: 'autozero', label: 'Auto-zero', sortVal: (c) => c.autoZeroCodes.join(' '),
      render: (c) => (c.autoZeroCodes.length
        ? <Pill tone="critical">{c.autoZeroCodes.join(', ')}</Pill>
        : <span style={{ color: 'var(--ink-3)' }}>—</span>),
    },
    {
      key: 'redflags', label: 'Red flags',
      sortVal: (c) => c.redFlags.filter((f) => f.observed === 'yes').length,
      render: (c) => {
        const on = c.redFlags.filter((f) => f.observed === 'yes').map((f) => f.code);
        return on.length ? <Pill tone="warning">{on.join(', ')}</Pill>
          : <span style={{ color: 'var(--ink-3)' }}>—</span>;
      },
    },
    {
      key: 'review', label: 'Review', sortVal: (c) => (c.needsReview ? 1 : 0),
      render: (c) => (c.needsReview
        ? <span title={c.reviewReasons.join(' · ')} aria-label="Needs human review">⚑</span> : ''),
    },
  ];

  return (
    <>
      <PageHead
        title="Advanced QA — PSM Scorecard"
        desc={`${DATA.auditedCount} of ${DATA.corpusSize} calls audited against the 100-point SUNROOOF PSM / Wellness Consultant scorecard`}
        periodNote={`Not affected by the date filter · scored by ${DATA.model} · generated ${DATA.generatedAt.slice(0, 16).replace('T', ' ')}`}
      />

      <Card
        title="Provisional — not for agent appraisal yet"
        style={{ borderLeft: '3px solid var(--warning, #c08a00)' }}>
        <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.65, fontSize: 13 }}>
          <li>
            Scored against <strong>scorecard v2.1</strong>, rebuilt from Sameer's training
            voice notes, with technical facts taken from the brand catalogue and the
            console quantity chart.
          </li>
          <li>
            <strong>Short calls dominate the corpus.</strong> Only 431 of 5,021 July calls
            run 10 minutes or longer. A brief qualification call cannot demonstrate
            pricing, technical detail or specialist priming, so it scores near zero —
            that reflects the call's length, not necessarily the agent.
            Auto-zero rate falls from 74% across all calls to 21% on calls over 20 minutes.
          </li>
          <li>
            <strong>No duration floor is agreed yet.</strong> Whether very short calls should
            be marked not-scoreable instead of scored is the main open decision.
          </li>
          <li>
            <strong>Window-console prices are still unverified</strong>, so those sub-points
            are marked unknown rather than guessed. Ceiling consoles are checked against
            the approved ₹39,000–45,000 range.
          </li>
          <li>
            <strong>NOT SCORED means the call could not be assessed. It is not a zero</strong>
            and must never be read as a failing grade.
          </li>
        </ul>
      </Card>

      {CHANGES.calls.length > 0 && <ScorecardChangeReview />}

      <div className="kpi-grid">
        <KpiCard label="Calls audited" value={DATA.auditedCount} format={fmtInt}
          denomNote={`of ${fmtInt(DATA.corpusSize)} in the corpus`} />
        <KpiCard label="Scored" value={scored.length} format={fmtInt}
          denomNote={`${notScored} could not be assessed`} accent="var(--s2)" />
        <KpiCard label="Mean score" value={Number(mean.toFixed(1))} format={(v) => `${v}`}
          denomNote="scored calls only" accent="var(--s3)" />
        <KpiCard label="Auto-zeroed" value={autoZero} format={fmtInt}
          denomNote="one critical miss zeroes the call" accent="var(--critical, #b3261e)" />
      </div>

      <Card title="Tier distribution" sub="Click a tier to filter the table below">
        <div className="chip-row">
          {tierCounts.map((r) => (
            <button key={r.tier} className="pill-button"
              onClick={() => setTier(tier === r.tier ? '' : r.tier)}
              aria-pressed={tier === r.tier}
              style={{ opacity: tier && tier !== r.tier ? 0.45 : 1 }}>
              <Pill tone={TIER_TONE[r.tier] ?? 'neutral'}>{r.tier.replace('_', ' ')}</Pill>
              <strong style={{ marginLeft: 6 }}>{r.n}</strong>
            </button>
          ))}
          {tier && <button className="btn" onClick={() => setTier('')}>Clear filter</button>}
        </div>
      </Card>

      <Card
        title="Audited calls"
        sub="Select a row for the criterion-by-criterion breakdown with evidence"
        right={
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="filter-select is-set" placeholder="Search id, agent, customer…"
              value={search} onChange={(e) => setSearch(e.target.value)}
              aria-label="Search audited calls" style={{ minWidth: 210 }} />
            <button className="btn" onClick={() => exportCsv(
              'advanced-qa.csv',
              ['call_id', 'date', 'agent', 'duration_sec', 'score', 'tier', 'auto_zero', 'red_flags', 'needs_review'],
              calls.map((c) => [c.id, c.date, c.agent ?? '', c.durationSec, c.score ?? '',
                c.tier, c.autoZeroCodes.join(' '),
                c.redFlags.filter((f) => f.observed === 'yes').map((f) => f.code).join(' '),
                c.needsReview ? 'yes' : 'no']),
            )}>Export CSV</button>
          </div>
        }>
        {calls.length === 0
          ? <EmptyState message="No audited calls match." hint="Clear the tier filter or the search box." />
          : <DataTable columns={columns} rows={calls} rowKey={(c) => c.id}
              onRow={(c) => setOpen(c)} pageSize={20}
              initialSort={{ key: 'score', dir: 'desc' }} />}
      </Card>

      {open && <Detail call={open} onClose={() => setOpen(null)} />}
    </>
  );
}

/**
 * The list payload no longer carries `criteria` or `conduct` — 46 MB across the
 * corpus, read only here and on Call Detail. The drawer opens immediately on the
 * slim record it was given and swaps in the full audit when its detail file
 * arrives, so the header and score render with no wait and the criteria table
 * fills in. Sunday's GET /api/call/[id] changes this URL and nothing else.
 */
function Detail({ call: slim, onClose }: { call: QaCall; onClose: () => void }) {
  const [call, setCall] = useState<QaCall>(slim);
  useEffect(() => {
    let cancelled = false;
    setCall(slim);
    fetch(`${import.meta.env.BASE_URL}data/detail/${encodeURIComponent(slim.id)}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d?.qa) setCall(d.qa as QaCall); })
      .catch((e) => console.warn(`[AdvancedQa] detail ${slim.id}:`, e));
    return () => { cancelled = true; };
  }, [slim]);

  return (
    <Card
      title={call.score === null ? 'Not scored' : `${call.score.toFixed(1)} / 100`}
      sub={`${call.id} · ${call.date} · ${call.agent ?? '—'} · ${mins(call.durationSec)}`}
      right={<button className="btn" onClick={onClose}>Close</button>}>

      <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>{call.summary}</p>

      {call.score !== null && (
        <p style={{ fontSize: 12.5 }}>
          Earned <strong>{call.earned}</strong> of <strong>{call.adjustedMax}</strong> applicable
          points = <strong>{call.preDeduction}%</strong>
          {call.deduction > 0 && <> − {call.deduction} red-flag points</>}
          {' = '}<strong>{call.score.toFixed(1)}</strong>
          {call.autoZero && (
            <> · <span style={{ color: 'var(--critical, #b3261e)' }}>
              zeroed by {call.autoZeroCodes.join(', ')}</span></>
          )}
        </p>
      )}

      {call.needsReview && call.reviewReasons.length > 0 && (
        <p style={{ fontSize: 12.5 }}>
          <strong>Needs human review:</strong> {call.reviewReasons.join(' · ')}
        </p>
      )}

      <div className="section-title">Criteria</div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>Criterion</th><th className="num">Points</th>
              <th>Result</th><th>What was missed</th><th>Evidence from the call</th>
            </tr>
          </thead>
          <tbody>
            {(call.criteria ?? []).map((c) => (
              <tr key={c.id}>
                <td>C{c.id}</td>
                <td>{c.name}</td>
                <td className="num">{c.applicable ? `${c.points}/${c.max}` : `–/${c.max}`}</td>
                <td>
                  <Pill tone={c.label === 'full' ? 'good' : c.label === 'half' ? 'warning'
                    : c.label === 'zero' ? 'critical' : 'neutral'}>
                    {c.label === 'n_a' ? 'N/A' : c.label}
                  </Pill>
                </td>
                <td style={{ maxWidth: 300, fontSize: 12 }}>
                  {(c.missed?.length || c.partial?.length || c.unverified?.length)
                    ? <>
                        {/* A criterion with no mandatory gate can score full while a
                            sub-point is unmet. Calling that "did not do" next to
                            5/5 reads as a contradiction, so full marks get
                            developmental framing instead of a fault. */}
                        {c.missed && c.missed.length > 0 && (
                          <div><strong>
                            {c.applicable && c.points >= c.max
                              ? 'Also worth covering: ' : 'Did not do: '}
                          </strong>{c.missed.join('; ')}</div>)}
                        {c.partial && c.partial.length > 0 && (
                          <div><strong>Only partly: </strong>{c.partial.join('; ')}</div>)}
                        {c.unverified && c.unverified.length > 0 && (
                          <div style={{ color: 'var(--ink-3)' }}>
                            <strong>Could not verify: </strong>{c.unverified.join('; ')}</div>)}
                      </>
                    : c.applicable && c.points >= c.max
                      ? <span style={{ color: 'var(--ink-3)' }}>covered in full</span>
                      : <span style={{ color: 'var(--ink-3)' }}>{c.reason || '—'}</span>}
                </td>
                <td style={{ maxWidth: 340 }}>
                  {c.evidence.length > 0
                    ? c.evidence.map((e, i) => (
                        <div key={i} style={{ marginBottom: 3, color: 'var(--ink-2)', fontSize: 12 }}>
                          {e.t && <code style={{ fontSize: 10.5 }}>[{e.t}] </code>}“{e.q}”
                        </div>
                      ))
                    : <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{c.reason || '—'}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">Critical misses &amp; red flags</div>
      <div className="chip-row">
        {[...call.criticalMisses, ...call.redFlags].map((f) => (
          <Pill key={f.code}
            tone={f.observed === 'yes' ? 'critical' : f.observed === 'unknown' ? 'neutral' : 'good'}>
            {f.code}: {f.observed}
          </Pill>
        ))}
      </div>

      {(call.coaching.strengths.length > 0 || call.coaching.improvements.length > 0) && (
        <>
          <div className="section-title">Coaching</div>
          {call.coaching.summary && (
            <p style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{call.coaching.summary}</p>
          )}
          <div className="two-col" style={{ fontSize: 12.5 }}>
            <div>
              <strong>Strengths</strong>
              <ul style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                {call.coaching.strengths.map((s, i) => <li key={i}>{text(s)}</li>)}
              </ul>
            </div>
            <div>
              <strong>Priority improvements</strong>
              <ul style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                {call.coaching.improvements.map((s, i) => <li key={i}>{text(s)}</li>)}
              </ul>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}


/**
 * Structured before/after review, written for a reader who has not seen the
 * scorecard: every row names the agent, the customer, the area assessed, the
 * marks, and what the agent did or failed to do — not internal version numbers.
 */
function ScorecardChangeReview() {
  const calls = CHANGES.calls;
  const up = calls.filter((c) => (c.delta ?? 0) > 0).length;
  const down = calls.filter((c) => (c.delta ?? 0) < 0).length;

  return (
    <Card
      title="Review: old scoring vs corrected scoring"
      sub={`${calls.length} calls re-scored under both the original scorecard and the corrected one built from Sameer's training. ${up} scored higher, ${down} lower. Listen to any call and judge whether the new mark is right.`}
      style={{ borderLeft: '3px solid var(--s1)' }}>

      {calls.map((c) => {
        const d = c.delta ?? 0;
        const azAdded = c.after.autoZero.length > c.before.autoZero.length;
        const azRemoved = c.before.autoZero.length > c.after.autoZero.length;
        return (
          <div key={c.id} style={{ marginBottom: 26 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline',
                          gap: 10, marginBottom: 6, paddingBottom: 6,
                          borderBottom: '1px solid var(--line, #e3e3e7)' }}>
              <strong style={{ fontSize: 14 }}>{c.agent ?? 'Unknown agent'}</strong>
              <span style={{ color: 'var(--ink-2)' }}>→ customer: {c.customer || 'Unknown'}</span>
              <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>
                {c.date} · {mins(c.durationSec)} · call {c.id.slice(-8)}
              </span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 12.5 }}>
                  old <strong>{c.before.score ?? '—'}</strong> → new <strong>{c.after.score ?? '—'}</strong>
                </span>
                <Pill tone={d > 0 ? 'good' : d < 0 ? 'critical' : 'neutral'}>
                  {d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1)}
                </Pill>
                <Pill tone={TIER_TONE[c.after.tier] ?? 'neutral'}>
                  {c.after.tier.replace('_', ' ')}
                </Pill>
                <a href={c.crmLink} target="_blank" rel="noreferrer">▶ listen</a>
              </span>
            </div>

            {(azAdded || azRemoved) && (
              <p style={{ margin: '0 0 6px', fontSize: 12.5 }}>
                <strong>{azAdded ? 'Now marked a critical miss' : 'No longer a critical miss'}</strong>
                {' — '}
                {azAdded
                  ? `${c.agent ?? 'The agent'} never asked when the customer needs SUNROOOF installed, and never prompted with a muhurat or vacation date. A critical miss zeroes the whole call.`
                  : `${c.agent ?? 'The agent'} did ask about the install deadline; the customer simply had no date. The old scoring zeroed the entire call for that — the corrected scoring does not.`}
              </p>
            )}

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 200 }}>Area assessed</th>
                    <th className="num" style={{ width: 90 }}>Old</th>
                    <th className="num" style={{ width: 90 }}>New</th>
                    <th>What {(c.agent ?? 'the agent').split(' ')[0]} did / missed</th>
                    <th style={{ width: 300 }}>Evidence from the call</th>
                  </tr>
                </thead>
                <tbody>
                  {c.criterionChanges.map((k) => (
                    <tr key={k.criterion}>
                      <td>C{k.criterion} {k.name}</td>
                      <td className="num" style={{ color: 'var(--ink-3)' }}>{k.before} / {k.max}</td>
                      <td className="num">
                        <strong style={{ color: k.after > k.before ? 'var(--good, #1e7a3c)'
                                                                   : 'var(--critical, #b3261e)' }}>
                          {k.after} / {k.max}
                        </strong>
                      </td>
                      <td style={{ fontSize: 12.5 }}>
                        {(k.missed?.length || k.partial?.length || k.unknown?.length)
                          ? <>
                              {k.missed && k.missed.length > 0 && (
                                <div><strong>Did not do:</strong> {k.missed.join('; ')}</div>)}
                              {k.partial && k.partial.length > 0 && (
                                <div><strong>Only partly:</strong> {k.partial.join('; ')}</div>)}
                              {k.unknown && k.unknown.length > 0 && (
                                <div><strong>Could not verify:</strong> {k.unknown.join('; ')}</div>)}
                            </>
                          : k.after >= k.max
                            ? <>Covered every point in this area.</>
                            : <>Marks moved on the critical-miss or red-flag decision, not on a
                               specific point in this area.</>}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--ink-2)', fontStyle: 'italic' }}>
                        {k.evidence ? <>{k.timestamp ? `[${k.timestamp}] ` : ''}“{k.evidence}”</>
                                    : <span style={{ color: 'var(--ink-3)' }}>nothing said on this</span>}
                      </td>
                    </tr>
                  ))}
                  {c.criterionChanges.length === 0 && (
                    <tr><td colSpan={5} style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
                      No individual area changed — the score moved only because of the
                      critical-miss decision above.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </Card>
  );
}
