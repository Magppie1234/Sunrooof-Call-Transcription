/**
 * GET /api/call/<call_id>
 *
 * One call_detail row: transcript, entities, recording URL and the full QA
 * audit. Fetched only when someone opens a call, which is why these fields were
 * lifted out of the list payload in the first place — 87 MB across the corpus.
 *
 * The response shape is identical to public/data/detail/<id>.json, written by
 * scripts/build_slim_dataset.py, so the two are interchangeable and the client
 * needs no branch. Those static files are never deployed: served from public/
 * they would be readable at a guessable URL by anyone, signed in or not. This
 * route is the deployed path, and it is where an RLS check belongs once
 * accounts exist.
 */
import { selectOne } from '../_lib/db.js';
import { rowToDetail } from '../_lib/rows.js';

// Call ids are Zoho numeric strings. Constraining the shape keeps arbitrary
// input out of the filter, and rejects a scan of the table by pattern.
const VALID_ID = /^[0-9]{1,32}$/;

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const id = String(req.query?.id ?? '');
  if (!VALID_ID.test(id)) return res.status(400).json({ error: 'Invalid call id' });

  try {
    const row = await selectOne('call_detail', {
      select: 'call_id,transcript,entities,recording_url,qa_criteria,qa_conduct,qa_red_flags,qa_review_reasons,qa_meta',
      filters: { call_id: `eq.${id}` },
    });
    if (!row) return res.status(404).json({ error: 'No detail for that call' });

    res.setHeader('Cache-Control', 'private, max-age=0, must-revalidate');
    return res.status(200).json(rowToDetail(id, row));
  } catch (err) {
    console.error('[api/call/[id]]', err);
    return res.status(500).json({ error: String(err?.message ?? err) });
  }
}
