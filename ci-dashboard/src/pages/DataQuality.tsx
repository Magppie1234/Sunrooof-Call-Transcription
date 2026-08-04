import { useEffect, useState } from 'react';
import { PageHead } from '../components/layout';
import { Card, KpiCard, Loading, ErrorState, RankBars, Pill, DataTable, type Column, Prov } from '../components/ui';
import { PROVENANCE, provCounts } from '../lib/provenance';
import { ScopeBanner, scopeNote } from '../components/ScopeBanner';
import { service, useFilteredData } from '../state/useData';
import { useAppState } from '../state/AppState';
import { fmtDateTime, fmtInt, fmtPct } from '../lib/format';
import { MIN_SAMPLE_SIZE, MIN_TRANSCRIPTION_CONFIDENCE, MODEL_VERSION, TAXONOMY_VERSION } from '../config';

interface IntegrationRow { system: string; purpose: string; status: 'live' | 'partial' | 'required'; fields: string }

const INTEGRATIONS: IntegrationRow[] = [
  { system: 'Zoho CRM — Calls', purpose: 'Call metadata: direction, duration, timestamp, owner, linked customer', status: 'live', fields: 'call_id, Call_Type, Call_Duration_in_seconds, Call_Start_Time, Owner, Who_Id/What_Id' },
  { system: 'Zoho CRM — Leads/Contacts', purpose: 'Customer identity, geography, lead source, campaign, lead stage, client type', status: 'partial', fields: 'Lead_Source ✓95% · Lead_Status ✓87% · Campaign_Name ✓77% · City ✓83% · Zip_Code ✗0% · Product_Requirement ✗1%' },
  { system: 'Sarvam Saaras v3 (ASR)', purpose: 'Speaker-separated transcripts with per-turn timestamps and language detection', status: 'live', fields: 'segments[], start/end_time_seconds, speaker_id, language_code, language_probability' },
  { system: 'gpt-4.1-mini extraction', purpose: 'Summaries, sentiment, purchase readiness, objections, FAQs, quality scorecard, VoC themes', status: 'live', fields: 'sentiment{}, readiness{}, objections[], faqs[], quality{}, entities[]' },
  { system: 'Call recording audio', purpose: 'In-page playback alongside the transcript', status: 'required', fields: 'recording_url — audio is reachable only via a Zoho session cookie, not wired into this app' },
  { system: 'Task / follow-up system', purpose: 'Two-way sync of next actions and SLA state', status: 'required', fields: 'task_id, owner, due, status' },
  { system: 'Order management / Deals', purpose: 'Verified conversion & revenue attribution', status: 'required', fields: 'No Deal records are linked to these calls and no CRM stage marks a won order' },
  { system: 'Complaint / ticketing', purpose: 'Complaint status for unresolved-complaint alerts', status: 'required', fields: 'ticket_id, status, severity — complaints are inferred from transcripts only' },
  { system: 'Approved knowledge base', purpose: 'Factual answer-accuracy assessment for FAQs', status: 'required', fields: 'faq_id, approved_answer, version' },
];

const GOVERNANCE: { control: string; state: string; ok: boolean }[] = [
  { control: 'AI-inferred vs CRM-verified outcomes distinguished', state: 'Outcome pills show “AI-inferred” vs “CRM-verified” on every call', ok: true },
  { control: 'AI confidence displayed per extracted insight', state: 'FAQ, objection, action and call-level confidence shown throughout', ok: true },
  { control: 'Low-confidence transcripts excluded from aggregates', state: `Threshold ${MIN_TRANSCRIPTION_CONFIDENCE * 100}% ASR confidence; excluded count shown on every page`, ok: true },
  { control: '“Not mentioned / Unknown” instead of assumptions', state: 'Budget, timeline, decision-maker default to Not mentioned/Unknown', ok: true },
  { control: 'Multilingual calls analysed in original language', state: 'Language stored per call; translation display is a required ASR-integration feature', ok: true },
  { control: 'Sensitive customer information masked', state: 'Phone/PII never stored in transcript views; masking enforced at ingestion (live mode)', ok: true },
  { control: 'Role-based access', state: '5 roles; agents see only their own calls (see docs/10-rbac.md)', ok: true },
  { control: 'Audit log maintained', state: 'Action updates, alert changes and corrections logged below', ok: true },
  { control: 'Taxonomy & model versions stored', state: `Taxonomy ${TAXONOMY_VERSION} · ${MODEL_VERSION}`, ok: true },
  { control: 'Managers can correct AI outputs', state: 'Correction controls on every call page; corrections audit-logged', ok: true },
  { control: 'Critical alerts manually reviewed', state: 'Critical alerts require acknowledge → resolve; never auto-actioned', ok: true },
  { control: 'No scoring on sensitive characteristics', state: 'Geography from CRM fields only; no accent/gender/community features anywhere in scoring', ok: true },
];

export default function DataQuality() {
  const { data: d, loading, error } = useFilteredData();
  const { filters } = useAppState();
  const [audit, setAudit] = useState<{ at: string; user: string; entry: string }[]>([]);

  useEffect(() => { service.getAuditLog().then(setAudit); }, [d]);

  if (loading && !d) return <Loading label="Checking data quality…" />;
  if (error) return <ErrorState message={error} />;
  if (!d) return null;

  const cur = d.current;
  const connected = cur.filter((c) => c.connected);
  const transcribed = cur.filter((c) => c.transcribed);
  const failed = connected.filter((c) => !c.transcribed);
  const lowConf = transcribed.filter((c) => c.meaningful && c.transcriptionConfidence < MIN_TRANSCRIPTION_CONFIDENCE);
  const diarUnreliable = transcribed.filter((c) => c.meaningful && !c.diarizationReliable);
  const bands = [
    { label: '≥ 90% confidence', n: transcribed.filter((c) => c.transcriptionConfidence >= 0.9).length, color: 'var(--good)' },
    { label: '75–89%', n: transcribed.filter((c) => c.transcriptionConfidence >= 0.75 && c.transcriptionConfidence < 0.9).length, color: 'var(--s1)' },
    { label: '60–74%', n: transcribed.filter((c) => c.transcriptionConfidence >= 0.6 && c.transcriptionConfidence < 0.75).length, color: 'var(--warning)' },
    { label: `< 60% (excluded from aggregates)`, n: lowConf.length, color: 'var(--critical)' },
  ];
  const langs = new Map<string, number>();
  for (const c of transcribed) langs.set(c.language, (langs.get(c.language) ?? 0) + 1);

  const intCols: Column<IntegrationRow>[] = [
    { key: 'system', label: 'System', render: (r) => <strong>{r.system}</strong> },
    { key: 'purpose', label: 'Purpose', render: (r) => <span style={{ fontSize: 12 }}>{r.purpose}</span> },
    { key: 'fields', label: 'Key fields', render: (r) => <span className="cell-sub">{r.fields}</span> },
    {
      key: 'status', label: 'Status', render: (r) => r.status === 'live'
        ? <Pill tone="good">live data</Pill>
        : r.status === 'partial'
          ? <Pill tone="warning">live, partially populated</Pill>
          : <Pill tone="critical">not available — integration required</Pill>,
    },
  ];

  const provTotals = provCounts();
  const provRows = Object.entries(PROVENANCE)
    .sort(([, a], [, b]) => {
      const rank = { demo: 0, partial: 1, real: 2 } as const;
      return rank[a.status] - rank[b.status];
    });

  return (
    <>
      <PageHead title="Data Quality & Configuration"
        desc="Pipeline health, what is and isn't backed by real integrations, governance controls, and the audit trail. Nothing on this dashboard invents missing source data — unavailable fields are declared here."
        periodNote={scopeNote(d, filters.preset)} />
      <ScopeBanner d={d} />

      <div className="kpi-grid">
        <KpiCard label="Total calls in period" prov="kpi.volume" value={cur.length} />
        <KpiCard label="Transcription coverage" prov="kpi.coverage" value={cur.length ? (transcribed.length / cur.length) * 100 : 0} format={(v) => `${v.toFixed(1)}%`} denomNote={`${fmtInt(transcribed.length)} of ${fmtInt(cur.length)} calls`} />
        <KpiCard label="Failed / missing transcripts" prov="kpi.coverage" value={failed.length + (cur.length - connected.length)} denomNote={`${fmtInt(failed.length)} ASR failures · ${fmtInt(cur.length - connected.length)} not connected`} accent="var(--serious)" invertDelta />
        <KpiCard label="Excluded: low confidence" prov="kpi.coverage" value={lowConf.length} denomNote={`below ${MIN_TRANSCRIPTION_CONFIDENCE * 100}% ASR confidence`} accent="var(--warning)" />
        <KpiCard label="Diarisation unreliable" prov="agent.talk" value={diarUnreliable.length} denomNote="talk-time metrics suppressed for these" accent="var(--warning)" />
        <KpiCard label="Analysed (aggregate denominator)" prov="kpi.meaningful" value={d.analysed.length} accent="var(--good)" denomNote={`min segment sample ${MIN_SAMPLE_SIZE}`} />
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <Card title={<>Transcription confidence distribution <Prov k="kpi.coverage" /></>} sub={`n = ${fmtInt(transcribed.length)} transcribed calls`}>
          <RankBars items={bands.map((b) => ({ label: b.label, value: b.n, color: b.color, sub: fmtPct(b.n, transcribed.length) }))} />
        </Card>
        <Card title={<>Language mix <Prov k="dim.language" /></>} sub="Calls are analysed in their original language; translation shown separately when the ASR integration provides it">
          <RankBars items={[...langs.entries()].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value, sub: fmtPct(value, transcribed.length) }))} />
        </Card>
      </div>

      <div className="section-title">
        Feature data provenance
        <span className="sub">every insight surface, and whether it runs on real Sunrooof data</span>
      </div>
      <Card>
        <div className="prov-legend" style={{ marginBottom: 10 }}>
          <span className="item"><span className="prov-dot real" /> <strong>{provTotals.real}</strong> real — live Zoho / transcript / extraction data</span>
          <span className="item"><span className="prov-dot partial" /> <strong>{provTotals.partial}</strong> partial — real, with a declared gap</span>
          <span className="item"><span className="prov-dot demo" /> <strong>{provTotals.demo}</strong> demo — no real source exists</span>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Feature</th><th>Status</th><th>Where the numbers come from</th></tr></thead>
            <tbody>
              {provRows.map(([key, entry]) => (
                <tr key={key}>
                  <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                    <span className={`prov-dot ${entry.status}`} style={{ marginLeft: 0, marginRight: 7 }} />{key}
                  </td>
                  <td>
                    <Pill tone={entry.status === 'real' ? 'good' : entry.status === 'partial' ? 'warning' : 'critical'}>
                      {entry.status}
                    </Pill>
                  </td>
                  <td style={{ fontSize: 12.5 }}>{entry.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="section-title">Integrations & data availability <span className="sub">source of truth for what is mock vs live</span></div>
      <Card>
        <DataTable columns={intCols} rows={INTEGRATIONS} rowKey={(r) => r.system} pageSize={10} />
        <div className="cell-sub" style={{ marginTop: 8 }}>
          Because no approved knowledge base is connected, FAQ answers are assessed for <strong>relevance and completeness only</strong> — not factual accuracy. Because the task system is not connected, action sync is one-way (in-app only).
        </div>
      </Card>

      <div className="section-title">Governance controls</div>
      <Card>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Control</th><th>Implementation</th><th>Status</th></tr></thead>
            <tbody>
              {GOVERNANCE.map((g) => (
                <tr key={g.control}>
                  <td style={{ fontWeight: 600, maxWidth: 260 }}>{g.control}</td>
                  <td style={{ fontSize: 12.5 }}>{g.state}</td>
                  <td>{g.ok ? <Pill tone="good">active</Pill> : <Pill tone="warning">pending</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="section-title">Audit log <span className="sub">most recent first · corrections, action updates, alert changes</span></div>
      <Card>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>When</th><th>User</th><th>Entry</th></tr></thead>
            <tbody>
              {audit.slice(0, 20).map((e, i) => (
                <tr key={i}><td style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(e.at)}</td><td>{e.user}</td><td style={{ fontSize: 12.5 }}>{e.entry}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
