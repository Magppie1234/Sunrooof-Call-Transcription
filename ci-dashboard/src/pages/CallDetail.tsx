import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Card, Loading, ErrorState, Pill, sentimentTone, Conf, EmptyState, Prov } from '../components/ui';
import { SentimentJourney } from '../components/charts';
import { service } from '../state/useData';
import { fmtDateTime, fmtDuration, fmtINR, fmtTimestamp } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { CallRecord } from '../types/domain';

export default function CallDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [call, setCall] = useState<CallRecord | null | undefined>(undefined);
  const [highlightT, setHighlightT] = useState<number | null>(params.get('t') ? Number(params.get('t')) : null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    service.getCall(id ?? '').then((c) => { if (!cancelled) setCall(c); });
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => {
    if (highlightT !== null && call && transcriptRef.current) {
      const idx = nearestSegmentIndex(call, highlightT);
      const el = transcriptRef.current.querySelector(`[data-seg="${idx}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightT, call]);

  if (call === undefined) return <Loading label="Loading call…" />;
  if (call === null) return <ErrorState message={`Call ${id} was not found.`} />;

  const emp = EMPLOYEES.find((e) => e.id === call.employeeId);
  const highlightIdx = highlightT !== null ? nearestSegmentIndex(call, highlightT) : -1;

  const jump = (t: number) => setHighlightT(t);

  return (
    <>
      <div className="page-head" style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <button className="btn small" onClick={() => navigate(-1)}>← Back</button>
        <h1>{call.id}</h1>
        <span className="desc">{fmtDateTime(call.dateTime)} · {call.direction} · {fmtDuration(call.durationSec)} · {call.language}</span>
        {call.sentiment && <Pill tone={sentimentTone(call.sentiment.overall)}>{call.sentiment.overall}</Pill>}
        {call.complianceFlags.length > 0 && <Pill tone="critical">compliance flag</Pill>}
        <span className="conf">Overall AI confidence {(call.aiConfidence * 100).toFixed(0)}%</span>
      </div>

      <div className="two-col">
        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <Card title={<>Recording & transcript <Prov k="call.transcript" /></>} sub={call.diarizationReliable ? 'Speaker-separated · timestamps synced' : 'Diarisation below reliability threshold — speaker labels are best-effort'}>
            <div className="audio-shell" style={{ marginBottom: 12 }}>
              <span aria-hidden>▶</span>
              {call.hasRecording
                ? <span>Audio playback is not connected in this app <Prov k="call.audio" /> — the recording exists but is only reachable through a Zoho session cookie. Timestamps below are real and will seek the audio once streaming is wired up.</span>
                : <span>No recording available for this call.</span>}
            </div>
            {call.transcript.length === 0 ? (
              <EmptyState message={call.transcribed ? 'Call too short for meaningful transcript analysis.' : 'Transcript unavailable — this call was not transcribed.'}
                hint={call.transcribed ? undefined : 'Check telephony recording status on the Data Quality page.'} />
            ) : (
              <div className="transcript" ref={transcriptRef}>
                {call.transcript.map((s, i) => (
                  <div key={i} data-seg={i} className={`utterance ${s.speaker}${i === highlightIdx ? ' highlight' : ''}`}>
                    <span className="u-time" onClick={() => jump(s.t)} title="Seek to this moment">{fmtTimestamp(s.t)}</span>
                    <div className="u-bubble">
                      <div className="u-speaker">{s.speaker === 'agent' ? (emp?.name ?? 'Agent') : call.customerName}</div>
                      {s.text}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
          {call.sentiment && (
            <Card title={<>Sentiment timeline <Prov k="sentiment.journey" /></>} sub="Text-based sentiment (−1 to +1) at opening, mid-call and closing — customer side only">
              <SentimentJourney opening={call.sentiment.opening} mid={call.sentiment.mid} closing={call.sentiment.closing} />
              <div className="chip-row" style={{ marginTop: 6 }}>
                <Pill tone={call.sentiment.shift > 0.2 ? 'good' : call.sentiment.shift < -0.2 ? 'critical' : 'neutral'}>
                  shift {call.sentiment.shift > 0 ? '+' : ''}{call.sentiment.shift.toFixed(2)}
                </Pill>
                {call.sentiment.emotions.map((e) => <Pill key={e} tone={['frustration', 'confusion'].includes(e) ? 'serious' : ['trust', 'satisfaction', 'interest'].includes(e) ? 'good' : 'neutral'}>{e}</Pill>)}
                {call.sentiment.unresolvedNegative && <Pill tone="critical">unresolved negative at call end</Pill>}
              </div>
            </Card>
          )}
        </div>

        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <Card title={<>AI summary <Prov k="call.summary" /></>} sub="Generated from transcript — verify against evidence before acting">
            <p style={{ margin: 0, fontSize: 13 }}>{call.summary}</p>
          </Card>
          <Card title={<>Customer & deal context <Prov k="dim.crmStage" /></>}>
            <dl className="kv">
              <dt>Customer</dt><dd style={{ overflowWrap: 'anywhere' }}>{call.customerName} ({call.customerType})</dd>
              <dt>Location (CRM)</dt><dd>{call.city}, {call.state} — {call.region} · PIN {call.pincode}</dd>
              <dt>Employee</dt><dd style={{ overflowWrap: 'anywhere' }}>{emp?.name} · {emp?.team} · Mgr: {emp?.manager}</dd>
              <dt>Lead source</dt><dd>{call.leadSource} · {call.campaign}</dd>
              <dt>CRM stage</dt><dd>{call.crmStage} <a style={{ fontSize: 11, cursor: 'pointer' }} title="CRM link placeholder — requires CRM integration">Open in CRM ↗</a></dd>
              <dt>Customer need</dt><dd>{call.customerNeed ?? 'Not mentioned'}</dd>
              <dt>Product interest</dt><dd>{call.productSeries}</dd>
              <dt>Budget</dt><dd>{call.budgetMentioned ?? 'Not mentioned'}</dd>
              <dt>Timeline</dt><dd>{call.timelineMentioned ?? 'Not mentioned'}</dd>
              <dt>Decision-maker</dt><dd>{call.decisionMaker === 'yes' ? 'On call / confirmed' : call.decisionMaker === 'no' ? 'Not the decision-maker' : 'Unknown'}</dd>
              {call.purchaseReadiness && <><dt>Purchase readiness</dt><dd>{call.purchaseReadiness.score} / 100 (weighted transcript score — not a conversion probability)</dd></>}
              <dt>Outcome</dt><dd>{call.outcome} {call.crm.verified ? <Pill tone="good">CRM-verified</Pill> : <Pill tone="warning">AI-inferred</Pill>}</dd>
              {call.crm.revenueInfluenced !== null && <><dt>Revenue (CRM)</dt><dd>{fmtINR(call.crm.revenueInfluenced)}</dd></>}
            </dl>
          </Card>

          <Card title={`Questions asked (${call.faqs.length})`}>
            {call.faqs.length === 0 ? <EmptyState message="No customer questions detected." /> : call.faqs.map((f, i) => (
              <div key={i} style={{ padding: '7px 0', borderBottom: '1px solid #eeede8', fontSize: 12.5 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Pill tone={f.status === 'answered' ? 'good' : f.status === 'partial' ? 'warning' : 'critical'}>{f.status}</Pill>
                  <strong>{f.standardized}</strong>
                </div>
                <div className="cell-sub">“{f.originalQuestion}” · <a style={{ cursor: 'pointer' }} onClick={() => jump(f.t)}>@ {fmtTimestamp(f.t)}</a> · sentiment after: {f.sentimentAfter} · <Conf value={f.confidence} /></div>
              </div>
            ))}
          </Card>

          <Card title={`Objections (${call.objections.length})`}>
            {call.objections.length === 0 ? <EmptyState message="No objections detected." /> : call.objections.map((o, i) => (
              <div key={i} style={{ padding: '7px 0', borderBottom: '1px solid #eeede8', fontSize: 12.5 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Pill tone={o.resolution === 'resolved' ? 'good' : o.resolution === 'partial' ? 'warning' : 'critical'}>{o.type} · {o.resolution}</Pill>
                  <Pill tone={o.intensity === 'high' ? 'serious' : 'neutral'}>{o.intensity} intensity</Pill>
                </div>
                <div className="cell-sub">Technique: {o.technique} · customer reaction: {o.customerReaction} · <a style={{ cursor: 'pointer' }} onClick={() => jump(o.t)}>@ {fmtTimestamp(o.t)}</a> · <Conf value={o.confidence} /></div>
              </div>
            ))}
          </Card>

          <Card title={`Commitments & next actions (${call.actions.length})`}>
            {call.actions.length === 0 ? <EmptyState message="No next actions captured for this call." /> : call.actions.map((a) => (
              <div key={a.id} style={{ padding: '7px 0', borderBottom: '1px solid #eeede8', fontSize: 12.5 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  {a.source === 'committed' ? <Pill tone="info">Committed · {a.committedBy}</Pill> : <Pill tone="neutral">AI-recommended</Pill>}
                  <strong>{a.action}</strong>
                  <Pill tone={a.slaStatus === 'overdue' ? 'critical' : a.slaStatus === 'due_today' ? 'warning' : a.status === 'completed' ? 'good' : 'neutral'}>
                    {a.status === 'completed' ? 'completed' : a.slaStatus.replace('_', ' ')}
                  </Pill>
                </div>
                <div className="cell-sub">{a.reason} · due {fmtDateTime(a.dueDate)} · {a.channel} · <a style={{ cursor: 'pointer' }} onClick={() => a.transcriptRef !== null && jump(a.transcriptRef)}>@ {fmtTimestamp(a.transcriptRef ?? 0)}</a> · <Conf value={a.confidence} /></div>
              </div>
            ))}
          </Card>

          {(call.risks.length > 0 || call.complianceFlags.length > 0) && (
            <Card title={<>Risks & compliance flags <Prov k="agent.compliance" /></>}>
              <div className="chip-row">
                {call.risks.map((r) => <Pill key={r} tone="serious">{r}</Pill>)}
                {call.complianceFlags.map((r) => <Pill key={r} tone="critical">⚠ {r}</Pill>)}
              </div>
              <div className="cell-sub" style={{ marginTop: 8 }}>Compliance flags require manual review by the quality team before action.</div>
            </Card>
          )}

          <Card title={<>Extracted entities & corrections <Prov k="call.entities" /></>}>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              {call.entities.length === 0 ? <span className="cell-sub">No entities extracted.</span>
                : call.entities.map((e, i) => <Pill key={i} tone="neutral">{e.type}: {e.text}</Pill>)}
            </div>
            <CorrectionBox callId={call.id} />
          </Card>
        </div>
      </div>
    </>
  );
}

function nearestSegmentIndex(call: CallRecord, t: number): number {
  let best = 0;
  let bestDist = Infinity;
  call.transcript.forEach((s, i) => {
    const dist = Math.abs(s.t - t);
    if (dist < bestDist) { bestDist = dist; best = i; }
  });
  return best;
}

function CorrectionBox({ callId }: { callId: string }) {
  const [field, setField] = useState('Sentiment');
  const [value, setValue] = useState('');
  const [saved, setSaved] = useState(false);
  return (
    <div>
      <div className="cell-sub" style={{ marginBottom: 6 }}>Manager correction — audit-logged; corrected values override AI output in future aggregates.</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <select className="filter-select" value={field} onChange={(e) => setField(e.target.value)} aria-label="Field to correct">
          {['Sentiment', 'Purchase readiness', 'Outcome', 'FAQ classification', 'Objection classification', 'Next action'].map((f) => <option key={f}>{f}</option>)}
        </select>
        <input className="searchbox" style={{ minWidth: 140, flex: 1 }} placeholder="Corrected value" value={value} onChange={(e) => { setValue(e.target.value); setSaved(false); }} />
        <button className="btn small primary" disabled={!value} onClick={async () => {
          await service.logCorrection({ callId, field, oldValue: '(AI value)', newValue: value, user: 'demo-user' });
          setSaved(true); setValue('');
        }}>Save correction</button>
      </div>
      {saved && <div className="cell-sub" style={{ color: 'var(--good-text)', marginTop: 4 }}>✓ Correction recorded in the audit log.</div>}
    </div>
  );
}
