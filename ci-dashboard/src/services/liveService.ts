/**
 * LIVE IMPLEMENTATION of DataService, backed by Supabase through /api/*.
 *
 * The same interface realService implements, reading the same data from
 * Postgres instead of a JSON snapshot compiled into the bundle. The
 * service-role key lives in the serverless functions and never reaches the
 * browser, which is the whole reason the routes exist.
 *
 * IT RUNS THE SAME applyFilters() realService RUNS
 * This is the design decision the whole migration rests on. Only the date
 * window and the thirteen scalar dimensions become SQL predicates; the array
 * predicates, the compliance flag and the free-text search stay here, in
 * matchesDims(), shared with the snapshot path. If the SQL reimplemented the
 * filter semantics the two modes could disagree for any input nobody thought
 * to test, and the disagreement would surface as a slightly different number on
 * a page rather than as an error. Sharing the code makes the diff empty by
 * construction; the SQL predicates exist to move fewer bytes.
 *
 * WHY IT FETCHES THE WHOLE CORPUS ONCE
 * The default period is 30 days against 60 days of comparison window, and the
 * data spans June–July, so the default view already needs ~96% of the rows. Per
 * window fetching would buy almost nothing and would re-fetch every time the
 * period changed. One paged load, cached, makes every later filter instant and
 * — more to the point — identical to what the snapshot path computes, because
 * both then run the same function over the same records.
 *
 * Writes still stay in memory. call_actions exists and is append-only, but
 * wiring the UI to it is the Zoho write-back work, which is deferred. Nothing
 * here claims to persist.
 */
import type { AlertItem, CallRecord, Employee, NextAction } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';
import { applyFilters } from '../lib/filters';
import { deriveAlerts } from '../lib/alerts';
import { deriveCorpus, type Corpus, type CorpusMeta } from '../data/corpusMeta';
import type { DataService } from './types';

/** Shape of GET /api/call/[id] — identical to public/data/detail/<id>.json. */
interface CallDetailFile {
  callId: string;
  transcript: CallRecord['transcript'] | null;
  entities: CallRecord['entities'] | null;
  recordingUrl: string | null;
  qa: unknown | null;
}

interface CallsPage {
  calls: CallRecord[];
  count: number;
  total: number;
  offset: number;
  nextOffset: number | null;
}

/**
 * Rows per request. The route caps at 1,000 (Supabase's own per-response
 * ceiling); 500 keeps a page at the measured 1.85 MB raw / 0.25 MB compressed.
 */
const PAGE = 500;

/**
 * Pages fetched at once after the first. Sequential paging over 13 pages is 13
 * round trips end to end; four at a time is four waves. Not unbounded — the
 * functions share a connection pool with everything else hitting the database.
 */
const CONCURRENCY = 4;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    // Read the body: the routes answer with {error} and that message is the
    // difference between "the env vars are not set in Vercel" and a bug.
    let detail = '';
    try {
      const body = await res.json() as { error?: string };
      detail = body?.error ? ` — ${body.error}` : '';
    } catch { /* non-JSON error body; the status is what matters */ }
    throw new Error(`${path}: HTTP ${res.status}${detail}`);
  }
  return res.json() as Promise<T>;
}

class LiveService implements DataService {
  // Replaced by the corpus's own label once /api/meta answers. Shown in the
  // banner while that is still in flight.
  sourceLabel = 'Live Sunrooof data (Supabase)';
  isMock = false;

  private metaPromise: Promise<CorpusMeta> | null = null;
  private corpusPromise: Promise<{ calls: CallRecord[]; corpus: Corpus }> | null = null;
  private detailCache = new Map<string, CallRecord>();
  private alertOverrides = new Map<string, AlertItem['status']>();
  private alertCache = new Map<string, AlertItem[]>();
  private auditLog: { at: string; user: string; entry: string }[] = [];

  getMeta(): Promise<CorpusMeta> {
    this.metaPromise ??= getJson<CorpusMeta>('/api/meta').then((meta) => {
      this.sourceLabel = meta.sourceLabel;
      this.auditLog = [{
        at: meta.generatedAt,
        user: 'system',
        entry: `Loaded from Supabase: ${meta.callCount} calls, snapshot generated ${meta.generatedAt}.`,
      }];
      return meta;
    });
    return this.metaPromise;
  }

  /**
   * Every call, paged. The first request also reports the total, so the rest
   * are issued in parallel waves rather than discovered one at a time.
   */
  private load(): Promise<{ calls: CallRecord[]; corpus: Corpus }> {
    this.corpusPromise ??= (async () => {
      const meta = await this.getMeta();
      const first = await getJson<CallsPage>(`/api/calls?limit=${PAGE}&offset=0`);

      const offsets: number[] = [];
      for (let o = first.count; o < first.total; o += PAGE) offsets.push(o);

      const pages: CallRecord[][] = [first.calls];
      for (let i = 0; i < offsets.length; i += CONCURRENCY) {
        const wave = await Promise.all(offsets.slice(i, i + CONCURRENCY).map((o) =>
          getJson<CallsPage>(`/api/calls?limit=${PAGE}&offset=${o}`)));
        for (const p of wave) pages.push(p.calls);
      }
      const calls = pages.flat();

      // Loud, not silent. A short read here would not throw — it would render a
      // dashboard whose every total is quietly low, which is the exact failure
      // that shipped a "6,260-row" export holding 4,965 unique calls.
      const unique = new Set(calls.map((c) => c.id)).size;
      if (calls.length !== first.total || unique !== first.total) {
        throw new Error(
          `/api/calls returned ${calls.length} rows (${unique} unique) for a stated total of ` +
          `${first.total}. Paging is not stable; refusing to report totals from an incomplete read.`);
      }

      return { calls, corpus: deriveCorpus(meta) };
    })();
    return this.corpusPromise;
  }

  async lastRefresh() { return (await this.getMeta()).generatedAt; }

  async getFiltered(filters: FilterState): Promise<FilteredData> {
    const { calls, corpus } = await this.load();
    return applyFilters(calls, filters, corpus.anchor);
  }

  /**
   * The list row plus its detail. GET /api/call/[id] returns exactly the shape
   * build_slim_dataset.py writes to public/data/detail/<id>.json, so this merge
   * is the same one realService does.
   */
  async getCall(id: string): Promise<CallRecord | null> {
    const { calls } = await this.load();
    const slim = calls.find((c) => c.id === id);
    if (!slim) return null;
    if (this.detailCache.has(id)) return this.detailCache.get(id)!;

    // As in realService: a failed detail fetch degrades to the slim record, not
    // to null. Null renders "call not found" for a call the user just clicked.
    let detail: CallDetailFile | null = null;
    try {
      detail = await getJson<CallDetailFile>(`/api/call/${encodeURIComponent(id)}`);
    } catch (e) {
      console.warn(`[liveService] detail ${id} unavailable:`, e);
    }

    const merged: CallRecord = {
      ...slim,
      transcript: detail?.transcript ?? [],
      entities: detail?.entities ?? [],
      recordingUrl: detail?.recordingUrl ?? null,
      qaAudit: detail?.qa ?? null,
    };
    this.detailCache.set(id, merged);
    return merged;
  }

  async getEmployees(): Promise<Employee[]> { return (await this.getMeta()).employees; }

  async getAlerts(filters: FilterState): Promise<AlertItem[]> {
    const { calls, corpus } = await this.load();
    const key = JSON.stringify(filters);
    if (!this.alertCache.has(key)) {
      this.alertCache.set(key, deriveAlerts(applyFilters(calls, filters, corpus.anchor)));
    }
    return this.alertCache.get(key)!.map((a) => ({ ...a, status: this.alertOverrides.get(a.id) ?? a.status }));
  }

  async updateAction(actionId: string, patch: Partial<Pick<NextAction, 'status' | 'ownerEmployeeId' | 'dueDate' | 'priority'>>): Promise<NextAction | null> {
    const { calls, corpus } = await this.load();
    for (const call of calls) {
      const a = call.actions.find((x) => x.id === actionId);
      if (!a) continue;
      Object.assign(a, patch);
      if (patch.status === 'completed') a.slaStatus = a.slaStatus === 'overdue' ? 'breached' : 'met';
      if (patch.dueDate) {
        const due = new Date(patch.dueDate);
        a.slaStatus = due < corpus.anchor ? 'overdue'
          : due.toDateString() === corpus.anchor.toDateString() ? 'due_today' : 'on_track';
      }
      this.auditLog.unshift({ at: new Date().toISOString(), user: 'demo-user', entry: `Action ${actionId} updated: ${JSON.stringify(patch)} (in-app only — not written to call_actions yet)` });
      this.alertCache.clear();
      return { ...a };
    }
    return null;
  }

  async setAlertStatus(alertId: string, status: AlertItem['status']): Promise<void> {
    this.alertOverrides.set(alertId, status);
    this.auditLog.unshift({ at: new Date().toISOString(), user: 'demo-user', entry: `Alert ${alertId} marked ${status} (in-app only)` });
  }

  async logCorrection(entry: { callId: string; field: string; oldValue: string; newValue: string; user: string }): Promise<void> {
    this.auditLog.unshift({ at: new Date().toISOString(), user: entry.user, entry: `Correction on ${entry.callId}: ${entry.field} "${entry.oldValue}" → "${entry.newValue}"` });
  }

  async getAuditLog() { await this.getMeta(); return this.auditLog; }
}

export const liveService = new LiveService();
