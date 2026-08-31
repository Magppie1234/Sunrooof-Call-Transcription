/**
 * GET /api/qa?[limit=&offset=]
 *
 * One page of the Advanced QA list, plus the run stamp its header reads.
 *
 * This is the last large file to come out of the bundle: AdvancedQa.tsx
 * imported qa_audits.slim.json, 9.98 MB, directly. A lazy route, so never in
 * the first paint — but still uploaded, and still served in full to anyone who
 * opens the page.
 *
 * IT RETURNS 6,260 ROWS, NOT 6,253
 * qa_audits has no foreign key to dashboard_calls precisely so it can. Seven
 * audits describe calls where Sarvam returned an empty transcript, which
 * build_ci_dataset.py drops and the audit pipeline records as
 * context=no_contact / NOT_SCORED. The page's header says "6,260 rows"; a route
 * that joined dashboard_calls would quietly return seven fewer.
 *
 * Paged for the same measured reason /api/calls is: one response cannot carry
 * the corpus. At 1,670 bytes per audit the 1,000-row default is 1.6 MB.
 */
import { selectOne, selectPage } from './_lib/db.js';
import { rowToAudit, rowToAuditRun } from './_lib/rows.js';

const MAX_LIMIT = 1000;
const DEFAULT_LIMIT = 1000;

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
    const limit = intParam(q.limit, DEFAULT_LIMIT, 1, MAX_LIMIT);
    const offset = intParam(q.offset, 0, 0, Number.MAX_SAFE_INTEGER);

    // The run row is a few hundred bytes and every page carries it, so the
    // client needs no special case for its first request.
    const [run, page] = await Promise.all([
      selectOne('qa_audit_run', {
        select: 'generated_at,corpus_size,audited_count,model,scorecard',
      }),
      // call_id is the primary key, so this order is unique and the paging is
      // stable. The page sorts by score itself, in the browser, over the whole
      // list — which is exactly why ordering here on score would be wrong:
      // thousands of audits share a score and ~1,900 are null.
      selectPage('qa_audits', {
        select: 'call_id,score,tier,status,payload',
        limit,
        offset,
      }),
    ]);

    if (!run) {
      return res.status(503).json({
        error: 'No qa_audit_run row. Run scripts/load_dashboard_tables.py --only qa.',
      });
    }

    const nextOffset = offset + page.rows.length;
    res.setHeader('Cache-Control', 'private, max-age=0, must-revalidate');
    return res.status(200).json({
      run: rowToAuditRun(run),
      audits: page.rows.map(rowToAudit),
      count: page.rows.length,
      total: page.total,
      offset,
      nextOffset: nextOffset < page.total ? nextOffset : null,
    });
  } catch (err) {
    console.error('[api/qa]', err);
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
}
