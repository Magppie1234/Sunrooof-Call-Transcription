/**
 * Taxonomy resolver — the single place the app asks "who are the employees,
 * what regions/products/languages exist?".
 *
 * These are no longer read out of a data module. Every DataService supplies
 * them as part of its CorpusMeta, and CorpusMetaProvider installs them here
 * once, before the app renders. So this module is mode-agnostic: it no longer
 * imports the real snapshot, the mock pools, or DATA_MODE.
 *
 * WHY THAT MATTERED
 * A JSON import pulls the whole file into whatever chunk references it, and
 * lib/filters.ts imports this module, so that chunk was the main one. Importing
 * dataset.slim.json here put all 6,253 call records into the first paint to
 * read seventeen employees and eight string arrays out of the top of it. The
 * previous fix pointed the import at the slim build; this removes it.
 *
 * THE EXPORTS ARE LET, NOT CONST, ON PURPOSE
 * ES module bindings are live: the nine modules that `import { EMPLOYEES }`
 * see whatever install() last assigned, with no call-site changes and no hook
 * threading through pure functions like filters.ts. The cost is a window
 * before install() where the values are unpopulated, which is why the initial
 * values THROW on access rather than sit there as empty arrays — an empty
 * EMPLOYEES would make empTeam() return '' and quietly narrow a filter to
 * nothing, which is exactly the class of silent wrongness this codebase keeps
 * paying for. CorpusMetaProvider renders nothing until install() has run, so
 * the only way to trip the guard is to read one of these during module
 * evaluation. Don't.
 */
import type { Employee } from '../types/domain';
import type { CorpusMeta, GeoRow } from './corpusMeta';

function unset<T extends object>(name: string): T {
  const fail = (): never => {
    throw new Error(
      `taxonomy.${name} was read before the corpus metadata loaded. It is populated ` +
      `by CorpusMetaProvider before the app renders, so this is a module-level read ` +
      `— move it inside a component or a function.`);
  };
  return new Proxy([] as unknown as T, { get: fail, has: fail, ownKeys: fail });
}

export let EMPLOYEES: Employee[] = unset('EMPLOYEES');

/** Region → state → city triples used by the cascading geography filters. */
export let GEO: GeoRow[] = unset('GEO');

export let PRODUCT_SERIES: readonly string[] = unset('PRODUCT_SERIES');
export let LANGUAGES: readonly string[] = unset('LANGUAGES');
export let LEAD_SOURCES: readonly string[] = unset('LEAD_SOURCES');

/** Called once by CorpusMetaProvider, before anything renders. */
export function installTaxonomy(meta: CorpusMeta): void {
  EMPLOYEES = meta.employees;
  GEO = meta.geo;
  PRODUCT_SERIES = meta.taxonomy.products;
  LANGUAGES = meta.taxonomy.languages;
  LEAD_SOURCES = meta.taxonomy.leadSources;
}
