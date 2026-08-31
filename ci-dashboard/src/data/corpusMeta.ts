/**
 * Corpus metadata: the few kilobytes the app shell needs before it can render
 * anything — the filter bar's option lists, the agent roster, the dataset
 * total, and the timestamps every period filter is measured from.
 *
 * WHY THIS MODULE EXISTS
 * components/layout.tsx imported DATA_ANCHOR, DATASET_CALL_COUNT,
 * DATASET_MIN_DATE and DATASET_MAX_DATE from realService, and data/taxonomy.ts
 * imported dataset.slim.json to build the dropdown lists. layout.tsx is the
 * always-loaded shell and filters.ts imports taxonomy.ts, so between them 21.5
 * MB of call data was pinned into the main chunk in every data mode. Four
 * numbers and eight lists cannot be worth that, and they are not: they are
 * 41 KB, which a service can hand over.
 *
 * Every DataService supplies this, so the shell never asks where the data came
 * from — the snapshot, the API, or the mock generator.
 */
import type { Employee } from '../types/domain';

export interface GeoRow {
  region: string;
  state: string;
  city: string;
  /** '' in real mode: Zoho does not carry a postcode per call. */
  pin: string;
}

export interface Taxonomy {
  regions: string[];
  states: string[];
  cities: string[];
  products: string[];
  languages: string[];
  leadSources: string[];
  campaigns: string[];
  teams: string[];
}

/**
 * The wire shape, identical to what GET /api/meta returns. minTs and maxTs are
 * raw timestamps rather than the anchor and the picker bounds: those are
 * DERIVED, by deriveCorpus() below, in one place for every mode.
 *
 * Putting that arithmetic behind the API instead would give the two modes two
 * definitions of which day "last 30 days" ends on, and the whole date filter
 * hangs off it. Same argument /api/calls makes for not reimplementing
 * matchesDims() in SQL.
 */
export interface CorpusMeta {
  generatedAt: string;
  sourceLabel: string;
  callCount: number;
  minTs: string;
  maxTs: string;
  employees: Employee[];
  geo: GeoRow[];
  taxonomy: Taxonomy;
}

export interface Corpus extends CorpusMeta {
  /**
   * The snapshot covers a fixed historical window. The period filters are
   * relative to "now", so anchoring to the newest call keeps "last 30 days"
   * meaningful instead of emptying the dashboard as the data ages. The UI
   * states this date next to every period label.
   *
   * Newest call PLUS ONE DAY, so that call sits inside the window rather than
   * on its edge — and note it is not midnight. The calendar-day version of the
   * default range returns 4,858 calls against the correct 4,655, which is close
   * enough to pass a glance and wrong.
   */
  anchor: Date;
  /** Bounds for the custom date-range picker, so no empty range is offered. */
  minDate: string;
  maxDate: string;
}

const isoDate = (t: number) => new Date(t).toISOString().slice(0, 10);

export function deriveCorpus(meta: CorpusMeta): Corpus {
  const min = new Date(meta.minTs).getTime();
  const max = new Date(meta.maxTs).getTime();
  const valid = Number.isFinite(min) && Number.isFinite(max);
  const today = isoDate(Date.now());
  return {
    ...meta,
    anchor: valid ? new Date(max + 86400_000) : new Date(),
    minDate: valid ? isoDate(min) : today,
    maxDate: valid ? isoDate(max) : today,
  };
}

/**
 * Builds CorpusMeta from a loaded call list. Used by the two services that hold
 * their calls in memory (real and mock); the live service reads /api/meta,
 * whose SQL side stores what the pipeline computed rather than re-deriving it.
 */
export function corpusFromCalls(
  calls: { dateTime: string; region: string; state: string; city: string }[],
  rest: Omit<CorpusMeta, 'callCount' | 'minTs' | 'maxTs' | 'geo'> & { geo?: GeoRow[] },
): CorpusMeta {
  let min = Infinity;
  let max = -Infinity;
  for (const c of calls) {
    const t = new Date(c.dateTime).getTime();
    if (t < min) min = t;
    if (t > max) max = t;
  }
  return {
    ...rest,
    callCount: calls.length,
    minTs: Number.isFinite(min) ? new Date(min).toISOString() : '',
    maxTs: Number.isFinite(max) ? new Date(max).toISOString() : '',
    geo: rest.geo ?? dedupeGeo(calls),
  };
}

/**
 * Distinct region/state/city triples, first occurrence winning, then a stable
 * sort on region and state — what the cascading region → state → city filters
 * offer. Mirrored in scripts/load_dashboard_tables.py so both modes list the
 * same options in the same order.
 */
export function dedupeGeo(calls: { region: string; state: string; city: string }[]): GeoRow[] {
  const seen = new Set<string>();
  const out: GeoRow[] = [];
  for (const c of calls) {
    const key = `${c.region}|${c.state}|${c.city}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ region: c.region, state: c.state, city: c.city, pin: '' });
  }
  return out.sort((a, b) => a.region.localeCompare(b.region) || a.state.localeCompare(b.state));
}
