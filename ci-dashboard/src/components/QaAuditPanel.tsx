import { Card, Pill, type PillTone } from './ui';
import qaData from '../data/real/qa_audits.json';

/**
 * The learning-and-development view of one call.
 *
 * Deliberately leads with what to improve and what to say instead, not the mark.
 * A manager reviewing an agent, and the agent reviewing themselves, both need to
 * know WHERE the call went wrong and the better line — a score out of 100 teaches
 * neither of them anything. The score is kept, but small and last.
 */

interface Improvement {
  area: string; what_went_wrong: string; what_they_said: string;
  timestamp: string; what_to_say_instead: string; severity: string;
}
interface Jargon { term: string; quote: string; suggestion: string }
interface Risk { claim: string; quote: string; timestamp: string; risk_level: string; why: string }
interface QaCriterion {
  id: number; name: string; max: number; label: string; points: number;
  applicable: boolean; reason: string;
  missed?: string[]; partial?: string[]; unverified?: string[];
  evidence?: { t: string | null; q: string }[];
}
interface QaCall {
  id: string; agent: string | null; customer: string | null;
  score: number | null; tier: string; autoZeroCodes: string[];
  needsReview: boolean; context?: string; contextReason?: string;
  criteria: QaCriterion[];
  redFlags?: { code: string; observed: string }[];
  conduct?: {
    customerLanguage?: string;
    improvements?: Improvement[];
    didWell?: { what: string; quote: string }[];
    risks?: Risk[];
    jargon?: Jargon[];
    languageCoaching?: string;
    listening?: { interrupted: boolean; ignoredStated: boolean; coaching: string };
    opening?: { rating?: string; coaching?: string };
    rapport?: { rating?: string; note?: string };
  };
}

const ALL = (qaData as unknown as { calls: QaCall[] }).calls;
const BY_ID = new Map(ALL.map((c) => [String(c.id), c]));

const SEV_TONE: Record<string, PillTone> = {
  critical: 'critical', important: 'warning', minor: 'neutral',
};
const TIER_TONE: Record<string, PillTone> = {
  GOLD: 'good', SILVER: 'good', BRONZE: 'warning',
  DEVELOPING: 'warning', AT_RISK: 'critical', NOT_SCORED: 'neutral',
};
const CONTEXT_LABEL: Record<string, string> = {
  full_consultation: 'Full consultation',
  follow_up: 'Follow-up call',
  callback_scheduling: 'Customer asked to be called back',
  not_a_lead: 'Customer had not enquired',
  customer_declined_early: 'Customer ended it early',
  no_contact: 'No conversation took place',
};

export function hasQaAudit(callId: string) {
  return BY_ID.has(String(callId));
}

export default function QaAuditPanel({ callId }: { callId: string }) {
  const qa = BY_ID.get(String(callId));
  if (!qa) {
    return (
      <Card title="Call quality review"
            sub="This call has not been audited yet — the review runs in batches.">
        <span style={{ color: 'var(--ink-3)', fontSize: 13 }}>No review available.</span>
      </Card>
    );
  }

  const c = qa.conduct ?? {};
  const imps = c.improvements ?? [];
  const order = { critical: 0, important: 1, minor: 2 } as Record<string, number>;
  const sorted = [...imps].sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
  const firstName = (qa.agent ?? 'the agent').split(' ')[0];
  const gaps = qa.criteria.filter(
    (k) => k.applicable && ((k.missed?.length ?? 0) || (k.partial?.length ?? 0)));

  return (
    <>
      <Card
        title={`What ${firstName} should improve on this call`}
        sub={qa.context
          ? `${CONTEXT_LABEL[qa.context] ?? qa.context}${qa.contextReason ? ' — ' + qa.contextReason : ''}`
          : 'Coaching points with the exact line to use next time'}>

        {sorted.length === 0 ? (
          <p style={{ color: 'var(--ink-3)', fontSize: 13, margin: 0 }}>
            No improvement points were raised for this call.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 100 }}>Priority</th>
                  <th style={{ width: 130 }}>Area</th>
                  <th>What went wrong</th>
                  <th>What {firstName} said</th>
                  <th>What to say instead</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((i, n) => (
                  <tr key={n}>
                    <td><Pill tone={SEV_TONE[i.severity] ?? 'neutral'}>{i.severity}</Pill></td>
                    <td>{i.area}</td>
                    <td style={{ fontSize: 12.5 }}>{i.what_went_wrong}</td>
                    <td style={{ fontSize: 12, fontStyle: 'italic', color: 'var(--ink-2)' }}>
                      {i.timestamp && <code style={{ fontSize: 10.5 }}>[{i.timestamp}] </code>}
                      {i.what_they_said ? `“${i.what_they_said}”` : '—'}
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      <strong>“{i.what_to_say_instead}”</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {(c.didWell?.length ?? 0) > 0 && (
          <>
            <div className="section-title">Did well</div>
            <ul style={{ paddingLeft: 18, margin: 0, fontSize: 12.5 }}>
              {c.didWell!.map((d, n) => (
                <li key={n}>
                  {d.what}
                  {d.quote && <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}> — “{d.quote}”</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      {((c.risks?.length ?? 0) > 0 || (c.jargon?.length ?? 0) > 0
        || c.listening?.interrupted || c.listening?.ignoredStated) && (
        <Card title="Flagged for review"
              sub="Communication and compliance issues a manager should see">

          {(c.risks?.length ?? 0) > 0 && (
            <>
              <div className="section-title">Claims to check</div>
              <ul style={{ paddingLeft: 18, margin: '0 0 8px', fontSize: 12.5 }}>
                {c.risks!.map((r, n) => (
                  <li key={n}>
                    <Pill tone={r.risk_level === 'high' ? 'critical' : 'warning'}>{r.risk_level}</Pill>{' '}
                    {r.claim}
                    {r.quote && <div style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>“{r.quote}”</div>}
                  </li>
                ))}
              </ul>
            </>
          )}

          {(c.listening?.interrupted || c.listening?.ignoredStated) && (
            <>
              <div className="section-title">Listening</div>
              <p style={{ fontSize: 12.5, margin: '0 0 8px' }}>
                {c.listening?.interrupted && <>Interrupted the customer. </>}
                {c.listening?.ignoredStated && <>Repeated something the customer had already corrected. </>}
                {c.listening?.coaching}
              </p>
            </>
          )}

          {(c.jargon?.length ?? 0) > 0 && (
            <>
              <div className="section-title">
                English words this customer may not have followed
                {c.customerLanguage && <> (customer spoke {c.customerLanguage})</>}
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th style={{ width: 140 }}>Word used</th><th>Say this instead</th></tr></thead>
                  <tbody>
                    {c.jargon!.map((j, n) => (
                      <tr key={n}>
                        <td><code>{j.term}</code></td>
                        <td style={{ fontSize: 12.5 }}>{j.suggestion}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {c.languageCoaching && (
                <p style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{c.languageCoaching}</p>)}
            </>
          )}
        </Card>
      )}

      <Card
        title="Scorecard detail"
        sub="Point-by-point, for reference. The coaching above is what to act on."
        right={
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Pill tone={TIER_TONE[qa.tier] ?? 'neutral'}>{qa.tier.replace('_', ' ')}</Pill>
            <strong>{qa.score === null ? 'not scored' : `${qa.score} / 100`}</strong>
          </span>
        }>
        {qa.score === null && (
          <p style={{ fontSize: 12.5, margin: '0 0 8px' }}>
            This call is <strong>not scored</strong>. {CONTEXT_LABEL[qa.context ?? ''] ?? 'No consultation took place'} —
            the 100-point scorecard does not apply, so no marks were deducted.
          </p>
        )}
        {gaps.length === 0 ? (
          <span style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>
            No gaps recorded against the scorecard.
          </span>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 220 }}>Area</th>
                  <th className="num" style={{ width: 80 }}>Marks</th>
                  <th>What was missed</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((k) => (
                  <tr key={k.id}>
                    <td>C{k.id} {k.name}</td>
                    <td className="num">{k.points} / {k.max}</td>
                    <td style={{ fontSize: 12.5 }}>
                      {k.missed && k.missed.length > 0 && (
                        <div><strong>
                          {k.points >= k.max ? 'Also worth covering: ' : 'Did not do: '}
                        </strong>{k.missed.join('; ')}</div>)}
                      {k.partial && k.partial.length > 0 && (
                        <div><strong>Only partly: </strong>{k.partial.join('; ')}</div>)}
                      {k.unverified && k.unverified.length > 0 && (
                        <div style={{ color: 'var(--ink-3)' }}>
                          <strong>Could not verify: </strong>{k.unverified.join('; ')}</div>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
