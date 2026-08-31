/**
 * GET /api/calls?[from=<iso>&to=<iso>][&limit=&offset=][&region=&state=&city=
 *                &employee=&product=&direction=&language=&sentiment=&outcome=
 *                &leadSource=&campaign=&intent=&customerType=]
 *
 * ONE PAGE of CallRecord objects, reassembled from dashboard_calls, plus the
 * total the filter matches so the client knows how many more to ask for.
 *
 * IT PAGES BECAUSE THE WHOLE CORPUS DOES NOT FIT IN ONE ANSWER
 * Measured, not assumed: one unpaged call against the real 6,253-row corpus
 * took 82.5 seconds and produced 23.08 MB of JSON. Both numbers are past what a
 * serverless function can do — the duration exceeds the default maxDuration
 * several times over, and no plausible response cap admits 23 MB. At the
 * measured 3,871 bytes per call, the 500-row default is 1.85 MB raw and 0.25 MB
 * compressed, and one PostgREST round trip rather than seven.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 * It does not reimplement matchesDims(). Only the date window and the scalar
 * dimensions become SQL predicates — the ones with real indexed columns. The
 * array predicates (faqs, objections, actions), the compliance flag and the
 * free-text search stay in the client, where liveService runs the SAME
 * applyFilters() that realService runs.
 *
 * That is the point rather than a shortcut. If this route reimplemented the
 * filter semantics in SQL, the two modes could disagree for any input nobody
 * thought to test, and the disagreement would surface as a slightly different
 * number on a page rather than as an error. Sharing the filter code makes the
 * H5 diff empty by construction; the SQL predicates exist to move fewer bytes,
 * not to decide what matches.
 *
 * The service-role key stays in this function and never reaches a browser.
 */
import { selectPage } from './_lib/db.js';
import { rowToCall, LIST_COLUMNS } from './_lib/rows.js';

/** Query parameter -> dashboard_calls column, for the scalar dimensions only. */
const DIMENSIONS = {
  region: 'region',
  state: 'state',
  city: 'city',
  employee: 'employee_id',
  product: 'product_series',
  direction: 'direction',
  language: 'language',
  sentiment: 'sentiment_overall',
  outcome: 'outcome',
  leadSource: 'lead_source',
  campaign: 'campaign',
  intent: 'intent',
  customerType: 'customer_type',
};

const isIso = (s) => typeof s === 'string' && !Number.isNaN(Date.parse(s));

// 1,000 is Supabase's own per-response ceiling, so a larger page would be
// silently truncated — the failure mode that shipped a "6,260-row" export
// holding 4,965 unique calls. Ask for no more than can actually come back.
const MAX_LIMIT = 1000;
const DEFAULT_LIMIT = 500;

function intParam(v, fallback, min, max) {
  const n = Number(v);
  if (!Number.isInteger(n)) return fallback;
  return Math.min(Math.max(n, min), max);
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const q = req.query ?? {};
    const filters = {};

    // The window is optional: omitting it returns the whole corpus, which is
    // what the dashboard wants on first load since it anchors its own periods.
    if (q.from || q.to) {
      if (q.from && !isIso(q.from)) return res.status(400).json({ error: '`from` is not an ISO timestamp' });
      if (q.to && !isIso(q.to)) return res.status(400).json({ error: '`to` is not an ISO timestamp' });
      const bounds = [];
      if (q.from) bounds.push(`gte.${q.from}`);
      // Exclusive upper bound, matching applyFilters(): t >= start && t < end.
      if (q.to) bounds.push(`lt.${q.to}`);
      filters.call_ts = bounds;
    }

    for (const [param, column] of Object.entries(DIMENSIONS)) {
      const v = q[param];
      // '' means "all" in FilterState, so an empty value must not become a
      // predicate matching the empty string.
      if (typeof v === 'string' && v !== '') filters[column] = `eq.${v}`;
    }

    const limit = intParam(q.limit, DEFAULT_LIMIT, 1, MAX_LIMIT);
    const offset = intParam(q.offset, 0, 0, Number.MAX_SAFE_INTEGER);

    // call_ts.asc matches the order dataset.json is written in, and selectPage
    // appends call_id.asc — an order that is UNIQUE, not merely present. 6,244
    // distinct timestamps cover 6,253 calls, so nine of them are shared by two;
    // without the tiebreak Postgres may return those in any order per page, and
    // a row can repeat on one page while another never appears at all.
    const { rows, total } = await selectPage('dashboard_calls', {
      select: LIST_COLUMNS,
      filters,
      order: 'call_ts.asc',
      limit,
      offset,
    });

    const nextOffset = offset + rows.length;
    res.setHeader('Cache-Control', 'private, max-age=0, must-revalidate');
    return res.status(200).json({
      calls: rows.map(rowToCall),
      count: rows.length,
      total,
      offset,
      // null rather than an offset past the end, so the client's loop condition
      // is "is there a next page" and not arithmetic it has to get right.
      nextOffset: nextOffset < total ? nextOffset : null,
    });
  } catch (err) {
    console.error('[api/calls]', err);
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
}
