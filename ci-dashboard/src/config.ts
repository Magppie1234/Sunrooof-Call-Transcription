/** Global app configuration. Change BRAND to rebrand the dashboard. */
export const BRAND = {
  companyName: 'Sunrooof',
  productLabel: 'Call Intelligence & Voice of Customer',
  shortName: 'CI',
};

/** Minimum analysed calls before a segment (region/agent/product) is shown as a reliable trend. */
export const MIN_SAMPLE_SIZE = 25;

/** Transcripts below this confidence are excluded from management aggregates. */
export const MIN_TRANSCRIPTION_CONFIDENCE = 0.6;

/**
 * Data source mode.
 *   'real' — the live Sunrooof dataset (Zoho CRM + Sarvam transcripts + LLM
 *            extraction), snapshotted into src/data/real/dataset.slim.json.
 *   'mock' — the original generated demo data.
 *   'live' — Supabase through the /api/* serverless routes (see liveService).
 */
const MODES = ['mock', 'real', 'live'] as const;
type DataMode = (typeof MODES)[number];

/**
 * Set at build time with VITE_DATA_MODE, defaulting to 'real'.
 *
 * An env var rather than an edited constant because H5 has to build BOTH modes
 * from the same commit and diff every number: a mode you have to hand-edit into
 * the source is one where the two builds differ by more than the mode.
 * An unrecognised value falls back to 'real' with a warning rather than
 * throwing, so a typo in a deployment setting degrades to the snapshot instead
 * of serving a blank dashboard.
 */
function resolveMode(): DataMode {
  const raw = import.meta.env.VITE_DATA_MODE;
  if (raw == null || raw === '') return 'real';
  if ((MODES as readonly string[]).includes(raw)) return raw as DataMode;
  console.warn(`[config] VITE_DATA_MODE="${raw}" is not one of ${MODES.join(', ')}; using 'real'.`);
  return 'real';
}

export const DATA_MODE: DataMode = resolveMode();

export const TAXONOMY_VERSION = '2026.07.1';
export const MODEL_VERSION = 'gpt-4.1-mini extraction (text-based sentiment)';
