/**
 * GET /api/calls?from=<iso>&to=<iso>[&region=&state=&city=&employee=&product=
 *                &direction=&language=&sentiment=&outcome=&leadSource=
 *                &campaign=&intent=&customerType=]
 *
 * Returns CallRecord objects for the window, reassembled from dashboard_calls.
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
import { selectAll } from './_lib/db.js';
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

    const rows = await selectAll('dashboard_calls', {
      select: LIST_COLUMNS,
      filters,
      order: 'call_ts.asc',
    });

    res.setHeader('Cache-Control', 'private, max-age=0, must-revalidate');
    return res.status(200).json({
      calls: rows.map(rowToCall),
      count: rows.length,
    });
  } catch (err) {
    console.error('[api/calls]', err);
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
}
