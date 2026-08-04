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
import dataset from '../data/real/dataset.json';
import type { DataService } from './types';

interface Dataset {
  generatedAt: string;
  sourceLabel: string;
  calls: CallRecord[];
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

class RealService implements DataService {
  sourceLabel = data.sourceLabel;
  isMock = false;

  private calls = data.calls;
  private alertOverrides = new Map<string, AlertItem['status']>();
  private alertCache = new Map<string, AlertItem[]>();
  private auditLog: { at: string; user: string; entry: string }[] = [
    { at: data.generatedAt, user: 'system', entry: `Dataset built from Zoho CRM, Sarvam transcripts and gpt-4.1-mini extraction (${data.calls.length} calls).` },
  ];

  async lastRefresh() { return data.generatedAt; }

  async getFiltered(filters: FilterState): Promise<FilteredData> {
    return applyFilters(this.calls, filters, DATA_ANCHOR);
  }

  async getCall(id: string): Promise<CallRecord | null> {
    return this.calls.find((c) => c.id === id) ?? null;
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
