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
 *            extraction), snapshotted into src/data/real/dataset.json.
 *   'mock' — the original generated demo data.
 *   'live' — a streaming backend that aggregates server-side; not built.
 */
export const DATA_MODE: 'mock' | 'real' | 'live' = 'real';

export const TAXONOMY_VERSION = '2026.07.1';
export const MODEL_VERSION = 'gpt-4.1-mini extraction (text-based sentiment)';
