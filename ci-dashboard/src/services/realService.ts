/**
 * LIVE IMPLEMENTATION of DataService, backed by the real Sunrooof dataset.
 *
 * The dataset is a build-time snapshot (`src/data/real/dataset.json`) produced
 * by `scripts/build_ci_dataset.py` in the transcription repo, which joins:
 *   Zoho CRM Calls + Leads · Sarvam Saaras v3 transcripts · gpt-4.1-mini
 *   extraction (summaries, sentiment, readiness, objections, FAQs).
 *
 * A snapshot rather than live API calls because this app is a static SPA with
 * no server to hold Zoho/Supabase credentials — the same reason the numbers are
 * as of `generatedAt` rather than this second. Re-run the builder to refresh.
 *
 * Writes (action status, alert status, corrections) stay in memory: there is no
 * task or escalation system to persist them to. That limit is declared in
 * src/lib/provenance.ts and surfaced in the UI.
 */
import type { AlertItem, CallRecord, Employee, NextAction } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';
import { applyFilters } from '../lib/filters';
import { deriveAlerts } from '../lib/alerts';
import { EMPLOYEES } from '../data/taxonomy';
import dataset from '../data/real/dataset.slim.json';
import type { DataService } from './types';

interface Dataset {
  generatedAt: string;
  sourceLabel: string;
  calls: CallRecord[];
}

/**
 * One file per call under public/data/detail/, written by
 * scripts/build_slim_dataset.py. Mirrors the call_detail row in Postgres, with
 * the whole QA audit rather than only its heavy fields, so neither caller
 * (QaAuditPanel, the AdvancedQa drawer) has to combine two sources.
 */
interface CallDetailFile {
  callId: string;
  transcript: CallRecord['transcript'] | null;
  entities: CallRecord['entities'] | null;
  recordingUrl: string | null;
  qa: unknown | null;
}
const data = dataset as unknown as Dataset;
export const DATASET_CALL_COUNT = data.calls.length;

/**
 * The snapshot covers a fixed historical window (July 2026). The dashboard's
 * period filters are relative to "now", so anchoring to the newest call keeps
 * "last 30 days" meaningful instead of returning an empty dashboard once the
 * snapshot ages. The UI states the snapshot date next to every period label.
 */
export const DATA_ANCHOR: Date = (() => {
  let newest = 0;
  for (const c of data.calls) {
    const t = new Date(c.dateTime).getTime();
    if (t > newest) newest = t;
  }
  // +1 day so the newest call sits inside the window rather than on its edge.
  return newest ? new Date(newest + 86400_000) : new Date();
})();

const toIsoDate = (d: Date) => d.toISOString().slice(0, 10);

/** Bounds for the custom date-range picker — the actual first/last call date
 * in the loaded dataset, so users can't pick an empty range outside it. */
export const [DATASET_MIN_DATE, DATASET_MAX_DATE]: [string, string] = (() => {
  let min = Infinity, max = -Infinity;
  for (const c of data.calls) {
    const t = new Date(c.dateTime).getTime();
    if (t < min) min = t;
    if (t > max) max = t;
  }
  if (!Number.isFinite(min)) {
    const today = toIsoDate(new Date());
    return [today, today];
  }
  return [toIsoDate(new Date(min)), toIsoDate(new Date(max))];
})();

class RealService implements DataService {
  sourceLabel = data.sourceLabel;
  isMock = false;

  private calls = data.calls;
  /** Merged records, so revisiting a call does not refetch its detail file. */
  private detailCache = new Map<string, CallRecord>();
  private alertOverrides = new Map<string, AlertItem['status']>();
  private alertCache = new Map<string, AlertItem[]>();
  private auditLog: { at: string; user: string; entry: string }[] = [
    { at: data.generatedAt, user: 'system', entry: `Dataset built from Zoho CRM, Sarvam transcripts and gpt-4.1-mini extraction (${data.calls.length} calls).` },
  ];

  async lastRefresh() { return data.generatedAt; }

  async getFiltered(filters: FilterState): Promise<FilteredData> {
    return applyFilters(this.calls, filters, DATA_ANCHOR);
  }

  /**
   * The list payload carries no transcript, entities, recordingUrl or QA
   * criteria — those are ~87 MB across the corpus and only ever render here, so
   * they live in one file per call under public/ and are fetched on demand.
   *
   * Sunday's GET /api/call/[id] replaces the fetch URL and nothing else: the
   * detail file's shape is the call_detail row's shape, deliberately.
   */
  async getCall(id: string): Promise<CallRecord | null> {
    const slim = this.calls.find((c) => c.id === id);
    if (!slim) return null;
    if (this.detailCache.has(id)) return this.detailCache.get(id)!;

    // A failed detail fetch degrades to the slim record rather than to null.
    // Returning null would render "call not found" for a call that plainly
    // exists in the list the user just clicked from — the transcript is missing,
    // which the page already handles, but the call is not.
    let detail: CallDetailFile | null = null;
    try {
      const res = await fetch(`${import.meta.env.BASE_URL}data/detail/${encodeURIComponent(id)}.json`);
      if (res.ok) detail = (await res.json()) as CallDetailFile;
      else console.warn(`[realService] detail ${id}: HTTP ${res.status}`);
    } catch (e) {
      console.warn(`[realService] detail ${id} unreachable:`, e);
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

  async getEmployees(): Promise<Employee[]> { return EMPLOYEES; }

  async getAlerts(filters: FilterState): Promise<AlertItem[]> {
    const key = JSON.stringify(filters);
    if (!this.alertCache.has(key)) {
      this.alertCache.set(key, deriveAlerts(applyFilters(this.calls, filters, DATA_ANCHOR)));
    }
    return this.alertCache.get(key)!.map((a) => ({ ...a, status: this.alertOverrides.get(a.id) ?? a.status }));
  }

  async updateAction(actionId: string, patch: Partial<Pick<NextAction, 'status' | 'ownerEmployeeId' | 'dueDate' | 'priority'>>): Promise<NextAction | null> {
    for (const call of this.calls) {
      const a = call.actions.find((x) => x.id === actionId);
      if (!a) continue;
      Object.assign(a, patch);
      if (patch.status === 'completed') a.slaStatus = a.slaStatus === 'overdue' ? 'breached' : 'met';
      if (patch.dueDate) {
        const due = new Date(patch.dueDate);
        a.slaStatus = due < DATA_ANCHOR ? 'overdue'
          : due.toDateString() === DATA_ANCHOR.toDateString() ? 'due_today' : 'on_track';
      }
      this.auditLog.unshift({ at: new Date().toISOString(), user: 'demo-user', entry: `Action ${actionId} updated: ${JSON.stringify(patch)} (in-app only — no task system connected)` });
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

  async getAuditLog() { return this.auditLog; }
}

export const realService = new RealService();
