import { DATA_MODE } from '../config';
import { mockService } from './mockService';
import { realService } from './realService';
import type { DataService } from './types';

/**
 * Service resolver.
 *
 * 'real'  — the live Sunrooof dataset: Zoho CRM calls, Sarvam transcripts and
 *           LLM extraction, snapshotted at build time (see realService.ts).
 * 'mock'  — the original clearly-labelled demo generator.
 * 'live'  — reserved for a streaming backend that aggregates server-side; not
 *           built (see docs/06-api-integrations.md).
 */
export function getService(): DataService {
  const mode = DATA_MODE as string;
  if (mode === 'live') {
    throw new Error('Streaming live integrations are not configured. See docs/06-api-integrations.md.');
  }
  return mode === 'real' ? realService : mockService;
}
