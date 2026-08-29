import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Card, Loading, ErrorState, Pill, sentimentTone, EmptyState, Prov } from '../components/ui';
import { SentimentJourney } from '../components/charts';
import { service } from '../state/useData';
import { fmtDateTime, fmtDuration, fmtINR, fmtTimestamp } from '../lib/format';
import { EMPLOYEES } from '../data/taxonomy';
import type { CallRecord } from '../types/domain';
import QaAuditPanel from '../components/QaAuditPanel';

// The audio proxy (scripts/audio_proxy.mjs) is a standalone Node process on
// localhost:3000 that holds the Zoho session cookie server-side — it never
// reaches the browser. This means playback only works when the dashboard is
// viewed on the same machine the proxy runs on, and only while the cookie
// hasn't expired (it does, every few days/weeks; see PROJECT_CONTEXT.md).
const AUDIO_PROXY_BASE = 'http://localhost:3000';
const proxiedAudioSrc = (recordingUrl: string) =>
  `${AUDIO_PROXY_BASE}/api/audio?url=${encodeURIComponent(recordingUrl)}`;

// Zoho Call_Result is a picklist — these are the only values the pipeline's
// outcome→disposition mapping ever sends (scripts/sync_notes_to_zoho.py
// OUTCOME_TO_RESULT). Free text would just get rejected by Zoho, so the
// dropdown is deliberately closed to this set rather than an open text field.
const CRM_RESULT_OPTIONS = [
  'Interested', 'Not interested', 'Requested call back',
  'No response/Busy', 'Invalid number', 'Requested more info',
];

export default function CallDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [call, setCall] = useState<CallRecord | null | undefined>(undefined);
  const [highlightT, setHighlightT] = useState<number | null>(params.get('t') ? Number(params.get('t')) : null);
  const [audioError, setAudioError] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

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

  const jump = (t: number) => {
    setHighlightT(t);
    if (audioRef.current) {
      audioRef.current.currentTime = t;
      audioRef.current.play().catch(() => {});
    }
  };

  return (
    <>
      <div className="page-head" style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <button className="btn small" onClick={() => navigate(-1)}>← Back</button>
        <h1>{call.id}</h1>
        <span className="desc">{fmtDateTime(call.dateTime)} · {call.direction} · {fmtDuration(call.durationSec)} · {call.language}</span>
        {call.sentiment && <Pill tone={sentimentTone(call.sentiment.overall)}>{call.sentiment.overall}</Pill>}
        {call.complianceFlags.length > 0 && <Pill tone="critical">compliance flag</Pill>}
        <span className="conf">Transcript confidence {(call.transcriptionConfidence * 100).toFixed(0)}%</span>
      </div>

      <div className="two-col">
        <div style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <Card title={<>Recording & transcript <Prov k="call.transcript" /></>} sub={call.diarizationReliable ? 'Speaker-separated · timestamps synced' : 'Diarisation below reliability threshold — speaker labels are best-effort'}>
            <div className="audio-shell" style={{ marginBottom: 12, display: 'block' }}>
              {call.recordingUrl && !audioError ? (
                <>
                  <audio ref={audioRef} controls preload="none" style={{ width: '100%' }}
                    src={proxiedAudioSrc(call.recordingUrl)}
                    onError={() => setAudioError(true)} />
                  <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>
                    Streamed via local proxy <Prov k="call.audio" /> — click a transcript timestamp to seek.
                  </div>
                </>
              ) : (
                <>
                  <span aria-hidden>▶</span>
                  {call.hasRecording && !call.recordingUrl
                    ? <span>Recording URL unavailable for this call <Prov k="call.audio" />.</span>
                    : call.hasRecording && audioError
                    ? <span>Playback failed <Prov k="call.audio" /> — the Zoho session cookie has likely expired. Refresh it in .env and restart scripts/audio_proxy.mjs.</span>
                    : <span>No recording available for this call.</span>}
                </>
              )}
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
          <QaAuditPanel callId={call.id} />
          <UpdateCrmPanel callId={call.id} crmNoteSynced={call.crmNoteSynced} crmTranscriptSynced={call.crmTranscriptSynced} />
          <Card title={<>Customer & deal context <Prov k="dim.crmStage" /></>}>
            <dl className="kv">
              <dt>Customer</dt><dd style={{ overflowWrap: 'anywhere' }}>{call.customerName} ({call.customerType})</dd>
              <dt>Location (CRM)</dt><dd>{call.city}, {call.state} — {call.region}</dd>
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
                <div className="cell-sub">“{f.originalQuestion}” · <a style={{ cursor: 'pointer' }} onClick={() => jump(f.t)}>@ {fmtTimestamp(f.t)}</a> · sentiment after: {f.sentimentAfter}</div>
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
                <div className="cell-sub">Technique: {o.technique} · customer reaction: {o.customerReaction}
                  {o.t !== null
                    ? <> · <a style={{ cursor: 'pointer' }} onClick={() => jump(o.t!)}>@ {fmtTimestamp(o.t)}</a></>
                    : <> · moment not located in transcript</>}</div>
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
                <div className="cell-sub">{a.reason} · due {fmtDateTime(a.dueDate)} · {a.channel} · <a style={{ cursor: 'pointer' }} onClick={() => a.transcriptRef !== null && jump(a.transcriptRef)}>@ {fmtTimestamp(a.transcriptRef ?? 0)}</a></div>
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

type CrmFieldOutcome = string | null; // e.g. "wrote 'Interested'" / "skipped (already has ...)" / "failed: ..."
interface CrmUpdateResult { result: CrmFieldOutcome; note: CrmFieldOutcome; city: CrmFieldOutcome; error?: string }

// The whole point of this panel: nothing reaches Zoho automatically anymore
// (see PROJECT_CONTEXT.md — the auto-sync loop was retired). A person reviews
// the AI's draft note/disposition/city here, can edit any of them, and only
// this button's click ever writes to the live CRM. Result and City are also
// enforced write-only-if-empty server-side (scripts/sync_notes_to_zoho.py
// sync_one()) — a value already in Zoho is never silently overwritten, even
// from here.
function UpdateCrmPanel({ callId, crmNoteSynced, crmTranscriptSynced }: {
  callId: string; crmNoteSynced?: boolean; crmTranscriptSynced?: boolean;
}) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [result, setResult] = useState('');
  const [city, setCity] = useState('');
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<CrmUpdateResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setLoadError(null); setOutcome(null);
    fetch(`${AUDIO_PROXY_BASE}/api/crm-draft?callId=${encodeURIComponent(callId)}`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d.error) { setLoadError(d.error); return; }
        setNote(d.note ?? '');
        setResult(d.result ?? '');
        setCity(d.city ?? '');
      })
      .catch(() => { if (!cancelled) setLoadError('Local update server not reachable — is scripts/audio_proxy.mjs running on :3000?'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [callId]);

  const update = async () => {
    setBusy(true); setOutcome(null);
    try {
      const r = await fetch(`${AUDIO_PROXY_BASE}/api/update-crm`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ callId, note: note.trim() || undefined, result: result || undefined, city: city.trim() || undefined }),
      });
      setOutcome(await r.json());
    } catch {
      setOutcome({ result: null, note: null, city: null, error: 'Request failed — local update server not reachable.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Update CRM" sub="AI-drafted below — review, edit if needed, then push. Fields Zoho already has a value for are never overwritten.">
      <div className="chip-row" style={{ marginBottom: 8 }}>
        <Pill tone={crmNoteSynced ? 'good' : 'neutral'}>{crmNoteSynced ? '✓ note on Zoho' : 'no AI note on Zoho yet'}</Pill>
        <Pill tone={crmTranscriptSynced ? 'good' : 'neutral'}>{crmTranscriptSynced ? '✓ transcript on Zoho' : 'transcript not on Zoho yet'}</Pill>
      </div>
      {loading ? (
        <div className="cell-sub">Loading draft…</div>
      ) : loadError ? (
        <div className="cell-sub" style={{ color: 'var(--critical-text, #b42318)' }}>{loadError}</div>
      ) : (
        <div style={{ display: 'grid', gap: 8 }}>
          <div>
            <label className="cell-sub" style={{ display: 'block', marginBottom: 3 }}>Note (posted as an AI-labelled Zoho Note)</label>
            <textarea className="searchbox" style={{ width: '100%', minHeight: 90, fontFamily: 'inherit', fontSize: 12.5 }}
              value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 160 }}>
              <label className="cell-sub" style={{ display: 'block', marginBottom: 3 }}>Disposition (Call_Result)</label>
              <select className="filter-select" style={{ width: '100%' }} value={result} onChange={(e) => setResult(e.target.value)}>
                <option value="">— no change —</option>
                {CRM_RESULT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label className="cell-sub" style={{ display: 'block', marginBottom: 3 }}>City</label>
              <input className="searchbox" style={{ width: '100%' }} value={city} onChange={(e) => setCity(e.target.value)} />
            </div>
          </div>
          <div>
            <button className="btn small primary" disabled={busy} onClick={update}>
              {busy ? 'Updating…' : 'Update CRM'}
            </button>
          </div>
          {outcome && (
            <div className="cell-sub" style={{ marginTop: 2 }}>
              {outcome.error ? <span style={{ color: 'var(--critical-text, #b42318)' }}>{outcome.error}</span> : (
                <>
                  <div>Disposition: {outcome.result ?? '(not sent)'}</div>
                  <div>Note: {outcome.note ?? '(not sent)'}</div>
                  <div>City: {outcome.city ?? '(not sent)'}</div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
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
