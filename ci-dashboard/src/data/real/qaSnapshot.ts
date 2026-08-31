/**
 * The QA audit set, out of the build-time snapshot.
 *
 * Behind a dynamic import for the same reason realService's dataset is: a
 * static JSON import lands in whatever chunk references the module, and this is
 * 9.98 MB. Loading it only when the Advanced QA page is actually opened is what
 * the lazy route was for; a static import here would undo that for every module
 * that touched this one.
 *
 * Shared by realService and mockService. Mock mode has always shown the real
 * audits — the page reads its own dataset and is independent of the global
 * filters by design — and this does not change that.
 */
import type { QaAuditSet } from '../qaAudits';

let cache: Promise<QaAuditSet> | null = null;

export function loadQaSnapshot(): Promise<QaAuditSet> {
  cache ??= import('./qa_audits.slim.json').then(
    (mod) => (mod.default ?? mod) as unknown as QaAuditSet);
  return cache;
}
