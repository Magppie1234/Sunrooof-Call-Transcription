/**
 * Read straight from import.meta.env, and deliberately NOT from config's
 * DATA_MODE, which resolves the same variable.
 *
 * Vite substitutes import.meta.env.VITE_DATA_MODE with a string literal at
 * build time, so the comparisons below fold to a constant and the branches not
 * taken become unreachable — which is what lets a live build drop realService,
 * and with it the 21.2 MB dataset chunk. Routed through config's resolveMode()
 * it is a function call no bundler can fold, and the snapshot is emitted into
 * dist and uploaded in every build, reachable at a hashed URL to anyone past
 * Deployment Protection.
 *
 * The fallback order matches resolveMode(): anything unrecognised, including
 * unset, is 'real'. DATA_MODE stays the value every other module should read;
 * this is the one place that needs the literal.
 */
const BUILD_MODE = import.meta.env.VITE_DATA_MODE;
import { mockService } from './mockService';
import { realService } from './realService';
import { liveService } from './liveService';
import type { DataService } from './types';

/**
 * Service resolver.
 *
 * 'real'  — the live Sunrooof dataset: Zoho CRM calls, Sarvam transcripts and
 *           LLM extraction, snapshotted at build time (see realService.ts).
 * 'mock'  — the original clearly-labelled demo generator.
 * 'live'  — the same data out of Supabase through /api/*, with the
 *           service-role key held in the serverless functions rather than
 *           shipped to the browser (see liveService.ts).
 *
 * Selected by VITE_DATA_MODE at build time. 'real' and 'live' read the same
 * records and run the same applyFilters() over them, so they are expected to
 * agree on every number; H5 diffs them to show that they do.
 */
export function getService(): DataService {
  if (BUILD_MODE === 'live') return liveService;
  if (BUILD_MODE === 'mock') return mockService;
  return realService;
}
