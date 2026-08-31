/**
 * Stands in for qaSnapshot.ts in a live build, exactly as
 * services/realService.live-stub.ts stands in for realService.
 *
 * vite.config.ts aliases './qaSnapshot' here when VITE_DATA_MODE=live, so
 * qa_audits.slim.json never enters the module graph and cannot be emitted. The
 * fold-and-tree-shake route was tried for realService and measurably did not
 * work: the bundler kept the module and emitted the data anyway.
 *
 * It throws rather than returning an empty audit set. An empty one would render
 * an Advanced QA page reporting "0 of 0 calls audited" — a plausible-looking
 * number for a scorecard that is still under review, and wrong.
 */
import type { QaAuditSet } from '../qaAudits';

export function loadQaSnapshot(): Promise<QaAuditSet> {
  throw new Error(
    'The QA snapshot is not available in a live build (VITE_DATA_MODE=live). It is ' +
    'deliberately excluded from the bundle; getQaAudits() should have gone to /api/qa. ' +
    'See ci-dashboard/src/data/real/qaSnapshot.live-stub.ts.');
}
