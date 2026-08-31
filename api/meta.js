/**
 * GET /api/meta
 *
 * Corpus metadata: the option lists behind the filter bar, the agent roster,
 * the dataset total, and the first/last call timestamps the period filters are
 * measured from. A few kilobytes, and the reason this route exists.
 *
 * WHAT IT REPLACES
 * components/layout.tsx is the always-loaded app shell, and it imported four
 * constants from realService, which imports dataset.slim.json. data/taxonomy.ts
 * imported the same file to build the employee, region, state, product,
 * language and lead-source lists, and filters.ts imports taxonomy.ts. Between
 * them, 21.5 MB of call data was pinned into the main chunk no matter which
 * data mode the app ran in — the front end could not stop shipping the
 * snapshot while four numbers and eight dropdowns came from inside it.
 *
 * Serving them makes both edges cuttable, which is the only reason the live
 * build can drop the snapshot at all.
 */
import { selectAll, selectOne } from './_lib/db.js';
import { rowToEmployee, rowToMeta } from './_lib/rows.js';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // dashboard_meta is a view over the single dashboard_snapshot row, so this
    // reads one row however many calls there are, and needs no filter: the
    // snapshot table's primary key admits exactly one row.
    //
    // `key` is not optional on the employees read. selectAll defaults it to
    // call_id, which dashboard_employees does not have — that would order on a
    // missing column and then dedupe all 17 rows down to one.
    const [row, empRows] = await Promise.all([
      selectOne('dashboard_meta', {
        select: 'generated_at,source_label,taxonomy,geo,call_count,min_ts,max_ts',
      }),
      selectAll('dashboard_employees', {
        select: 'employee_id,name,team,manager,role',
        key: 'employee_id',
      }),
    ]);

    // No row means the pipeline has loaded calls but never stamped a snapshot.
    // 503 rather than 404: the resource is expected to exist, the load is
    // incomplete, and a 404 would read to a caller as "no such route".
    if (!row) {
      return res.status(503).json({
        error: 'No dashboard_snapshot row. Run scripts/load_dashboard_tables.py --only meta.',
      });
    }

    res.setHeader('Cache-Control', 'private, max-age=0, must-revalidate');
    return res.status(200).json(rowToMeta(row, empRows.map(rowToEmployee)));
  } catch (err) {
    console.error('[api/meta]', err);
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
}
