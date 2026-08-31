/**
 * PostgREST access for the serverless routes.
 *
 * The service-role key is read from the environment and never leaves the
 * function — that is the whole reason these routes exist rather than the browser
 * querying Supabase directly.
 */

const URL_ = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

/** Supabase caps a PostgREST response at 1,000 rows. */
const PAGE = 1000;

export function assertConfigured() {
  const missing = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'].filter((k) => !process.env[k]);
  if (missing.length) {
    throw new Error(
      `Missing environment variable(s): ${missing.join(', ')}. ` +
      `Set them in the Vercel project settings; the routes cannot reach the database without them.`);
  }
}

const headers = (extra) => ({ apikey: KEY, Authorization: `Bearer ${KEY}`, ...extra });

/**
 * Reads every matching row, paging to exhaustion.
 *
 * Two rules are enforced here rather than left to each caller, because this
 * project has been bitten by both:
 *
 * 1. `order` is appended with the table's unique key unconditionally. PostgREST paging
 *    needs an order that is UNIQUE, not merely present. Ordering on a tied
 *    column fails exactly like ordering on nothing: Postgres may return tied
 *    rows in any order per page, so some repeat and others never appear, and
 *    the total row count still looks right. That shipped a "6,260-row" export
 *    holding 4,965 unique calls.
 *
 * 2. The result is deduped by that key and a warning is logged if anything was
 *    dropped, so a paging fault is loud rather than silent.
 *
 * `key` defaults to call_id because most tables here are keyed on it, but it is
 * a parameter and not a constant: dashboard_employees has no call_id, and a
 * hardcoded one would both send an order on a column that does not exist and
 * dedupe every row down to one under the key `undefined`.
 */
export async function selectAll(table, { select, filters = {}, order = '', key = 'call_id' }) {
  assertConfigured();
  const params = new URLSearchParams();
  params.set('select', select);
  params.set('order', order ? `${order},${key}.asc` : `${key}.asc`);
  for (const [k, v] of Object.entries(filters)) {
    if (Array.isArray(v)) for (const one of v) params.append(k, one);
    else params.set(k, v);
  }

  const rows = [];
  for (let offset = 0; ; offset += PAGE) {
    const res = await fetch(`${URL_}/rest/v1/${table}?${params}`, {
      headers: headers({ Range: `${offset}-${offset + PAGE - 1}` }),
    });
    if (!res.ok) throw new Error(`${table}: ${res.status} ${(await res.text()).slice(0, 300)}`);
    const page = await res.json();
    rows.push(...page);
    if (page.length < PAGE) break;
  }

  const seen = new Set();
  const unique = rows.filter((r) => {
    const id = String(r[key]);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
  if (unique.length !== rows.length) {
    console.warn(`[db] ${table}: ${rows.length - unique.length} duplicate rows across pages — ` +
      `paging is not stable, results may also be missing rows`);
  }
  return unique;
}

/**
 * ONE page of rows, plus the total the filter matches.
 *
 * selectAll() pages to exhaustion inside the function, which is right for the
 * 17-row roster and wrong for the call list: measured against the real corpus,
 * one call to /api/calls with no filter took 82.5 SECONDS and produced 23.08 MB
 * of JSON. A serverless function has neither that long to run nor that much
 * room to answer in, so the paging has to be visible to the caller and the
 * client has to drive it. 3,871 bytes per call, measured — a 500-row page is
 * 1.85 MB raw and 0.25 MB over the wire once compressed.
 *
 * `total` comes from PostgREST's own count, so the client knows how many pages
 * to ask for without a second query.
 */
export async function selectPage(table, { select, filters = {}, order = '', key = 'call_id', limit, offset = 0 }) {
  assertConfigured();
  const params = new URLSearchParams();
  params.set('select', select);
  params.set('order', order ? `${order},${key}.asc` : `${key}.asc`);
  for (const [k, v] of Object.entries(filters)) {
    if (Array.isArray(v)) for (const one of v) params.append(k, one);
    else params.set(k, v);
  }
  const res = await fetch(`${URL_}/rest/v1/${table}?${params}`, {
    headers: headers({ Range: `${offset}-${offset + limit - 1}`, Prefer: 'count=exact' }),
  });
  if (!res.ok) throw new Error(`${table}: ${res.status} ${(await res.text()).slice(0, 300)}`);
  const rows = await res.json();
  // "0-499/6253" — the part after the slash is the count the filter matches,
  // which is what paginates; the range before it is only this page.
  const total = Number(String(res.headers.get('content-range') ?? '').split('/')[1]);
  return { rows, total: Number.isFinite(total) ? total : rows.length };
}


/**
 * The first matching row, or null.
 *
 * `filters` carries whole PostgREST predicates (`eq.887064000041661165`,
 * `not.is.null`) rather than bare values, so the operator is the caller's to
 * choose and this does not have to grow a parameter each time one is not eq.
 * Omitting filters entirely is legitimate for a view that returns one row.
 */
export async function selectOne(table, { select, filters = {} }) {
  assertConfigured();
  const params = new URLSearchParams({ select, limit: '1' });
  for (const [k, v] of Object.entries(filters)) params.set(k, v);
  const res = await fetch(`${URL_}/rest/v1/${table}?${params}`, { headers: headers() });
  if (!res.ok) throw new Error(`${table}: ${res.status} ${(await res.text()).slice(0, 300)}`);
  const rows = await res.json();
  return rows[0] ?? null;
}
