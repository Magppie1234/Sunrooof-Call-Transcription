/**
 * Stands in for realService.ts in a live build.
 *
 * WHY A STUB AND NOT TREE-SHAKING
 * services/index.ts resolves the mode from a literal Vite substitutes at build
 * time, so the `realService` branch folds to unreachable code — and the bundler
 * still keeps the module. Measured: with the fold in place, a live build's entry
 * chunk still contained realService in full and still referenced the 21.2 MB
 * dataset chunk, which was still emitted into dist and would still be uploaded.
 * Tree-shaking a module that instantiates a class at import time is a judgement
 * the bundler is entitled to decline, so this does not ask it to.
 *
 * vite.config.ts aliases './realService' here when VITE_DATA_MODE=live. The
 * snapshot never enters the module graph, so it cannot be emitted.
 *
 * IT THROWS RATHER THAN RETURNING AN EMPTY DATASET
 * The obvious alternative — alias the JSON to `{"calls":[]}` — leaves a working
 * realService that reports a corpus of zero. Every total on every page would be
 * 0, correct-looking and wrong. Nothing should reach this in a live build; if
 * something does, it should say so.
 */
import type { DataService } from './types';

const unavailable = (): never => {
  throw new Error(
    'realService is not available in a live build (VITE_DATA_MODE=live). The snapshot ' +
    'is deliberately excluded from the bundle; getService() should have returned ' +
    'liveService. See ci-dashboard/src/services/realService.live-stub.ts.');
};

export const realService = new Proxy({} as DataService, { get: unavailable });
