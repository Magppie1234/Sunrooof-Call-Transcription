/**
 * Taxonomy resolver — the single place the app asks "who are the employees,
 * what regions/products/languages exist?".
 *
 * In mock mode these come from the generated demo pools; in real mode they are
 * the distinct values actually present in the live Sunrooof dataset. Pages,
 * filters and metrics import from here so neither side reaches into the other's
 * data module.
 */
import { DATA_MODE } from '../config';
import type { Employee } from '../types/domain';
import {
  EMPLOYEES as MOCK_EMPLOYEES,
  GEO as MOCK_GEO,
  PRODUCT_SERIES as MOCK_PRODUCTS,
  LANGUAGES as MOCK_LANGUAGES,
  LEAD_SOURCES as MOCK_LEAD_SOURCES,
} from './mock/taxonomies';
import realDataset from './real/dataset.json';

const isReal = (DATA_MODE as string) === 'real';

interface RealShape {
  employees: Employee[];
  taxonomy: {
    regions: string[]; states: string[]; cities: string[]; products: string[];
    languages: string[]; leadSources: string[]; campaigns: string[]; teams: string[];
  };
}
const real = realDataset as unknown as RealShape;

export const EMPLOYEES: Employee[] = isReal ? real.employees : MOCK_EMPLOYEES;

/** Region → state pairs used by the cascading region/state filters. */
export const GEO: { region: string; state: string; city: string; pin: string }[] = isReal
  ? // Rebuilt from the real calls so the state list stays consistent with region.
    dedupeGeo()
  : MOCK_GEO.map((g) => ({ region: g.region, state: g.state, city: g.city, pin: g.pin }));

function dedupeGeo() {
  const seen = new Set<string>();
  const out: { region: string; state: string; city: string; pin: string }[] = [];
  for (const c of (realDataset as unknown as { calls: { region: string; state: string; city: string }[] }).calls) {
    const key = `${c.region}|${c.state}|${c.city}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ region: c.region, state: c.state, city: c.city, pin: '' });
  }
  return out.sort((a, b) => a.region.localeCompare(b.region) || a.state.localeCompare(b.state));
}

export const PRODUCT_SERIES: readonly string[] = isReal ? real.taxonomy.products : MOCK_PRODUCTS;
export const LANGUAGES: readonly string[] = isReal ? real.taxonomy.languages : MOCK_LANGUAGES;
export const LEAD_SOURCES: readonly string[] = isReal ? real.taxonomy.leadSources : MOCK_LEAD_SOURCES;
