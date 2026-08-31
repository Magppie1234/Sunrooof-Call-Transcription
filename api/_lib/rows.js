/**
 * Reassembles a CallRecord from a dashboard_calls row.
 *
 * This is the exact inverse of TYPED in scripts/load_dashboard_tables.py, and it
 * has to be, field for field. The dashboard computes every metric from these
 * objects, so a single renamed or dropped key changes a number on a page rather
 * than raising an error — which is why H5 diffs both modes instead of trusting
 * this file.
 *
 * Not reconstructed, deliberately: sentiment_overall, compliance_flag_count,
 * qa_score, qa_tier and qa_status are COPIES lifted out of the payload so SQL
 * can filter on them. Their originals (payload.sentiment, payload.complianceFlags)
 * come back with the payload. Putting the copies back would add keys the
 * dataset.json shape never had.
 */

/** camelCase CallRecord field -> dashboard_calls column. */
export const TYPED = {
  id: 'call_id',
  dateTime: 'call_ts',
  employeeId: 'employee_id',
  customerId: 'customer_id',
  customerName: 'customer_name',
  customerType: 'customer_type',
  direction: 'direction',
  durationSec: 'duration_sec',
  language: 'language',
  connected: 'connected',
  meaningful: 'meaningful',
  transcribed: 'transcribed',
  transcriptionConfidence: 'transcription_confidence',
  diarizationReliable: 'diarization_reliable',
  region: 'region',
  state: 'state',
  city: 'city',
  productSeries: 'product_series',
  leadSource: 'lead_source',
  campaign: 'campaign',
  crmStage: 'crm_stage',
  outcome: 'outcome',
  intent: 'intent',
  summary: 'summary',
  topics: 'topics',
};

/** Columns a list query must select: the typed ones plus the payload. */
export const LIST_COLUMNS = [...Object.values(TYPED), 'payload'].join(',');

/**
 * Postgres returns timestamptz as +00:00; the snapshot stored the same. Kept as
 * a named step rather than an inline pass-through so that if the two ever drift,
 * the fix has one home instead of being scattered through the mapping.
 */
const toIso = (ts) => (ts == null ? null : String(ts));

export function rowToCall(row) {
  const call = { ...(row.payload ?? {}) };
  for (const [field, column] of Object.entries(TYPED)) {
    call[field] = field === 'dateTime' ? toIso(row[column]) : row[column];
  }
  return call;
}

/**
 * call_detail row -> the three CallRecord fields plus the audit, matching the
 * shape build_slim_dataset.py writes to public/data/detail/<id>.json so both
 * sources are interchangeable.
 */
export function rowToDetail(callId, row) {
  // qa_meta holds every audit field without a column of its own; the four
  // columns hold the heavy ones. Recombined they are the audit exactly as
  // qa_audits.json holds it, which is what the static detail files carry — so
  // the two sources are interchangeable and the client needs no branch.
  const meta = row?.qa_meta ?? null;
  const qa = meta === null && row?.qa_criteria == null ? null : {
    ...(meta ?? {}),
    criteria: row?.qa_criteria ?? null,
    conduct: row?.qa_conduct ?? null,
    redFlags: row?.qa_red_flags ?? null,
    reviewReasons: row?.qa_review_reasons ?? null,
  };

  return {
    callId,
    transcript: row?.transcript ?? null,
    entities: row?.entities ?? null,
    recordingUrl: row?.recording_url ?? null,
    qa,
  };
}

/**
 * dashboard_employees row -> the Employee shape the dashboard uses. Only the
 * key name changes (employee_id -> id); everything else is already camel-free.
 */
export function rowToEmployee(row) {
  return {
    id: row.employee_id,
    name: row.name,
    team: row.team,
    manager: row.manager,
    role: row.role,
  };
}

/**
 * dashboard_meta row -> CorpusMeta, the few kilobytes the app shell needs
 * before it can render: the filter bar's option lists, the dataset total, and
 * the bounds the period filters are measured from.
 *
 * min_ts and max_ts are passed through RAW rather than turned into dates here.
 * The client derives the anchor and the picker bounds from them with the same
 * function it uses over the static snapshot, so the two data modes cannot
 * disagree about which day "last 30 days" ends on. Deriving it here would put
 * that arithmetic in two places, and the whole date filter hangs off it.
 */
export function rowToMeta(row, employees) {
  return {
    generatedAt: row.generated_at,
    sourceLabel: row.source_label,
    callCount: Number(row.call_count),
    minTs: row.min_ts,
    maxTs: row.max_ts,
    employees,
    geo: row.geo ?? [],
    taxonomy: row.taxonomy ?? {},
  };
}
