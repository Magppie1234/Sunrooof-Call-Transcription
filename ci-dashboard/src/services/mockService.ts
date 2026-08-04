/**
 * ⚠️ MOCK IMPLEMENTATION of DataService — in-memory, deterministic demo data.
 * Clearly labelled in the UI via `isMock`. Keep all mock-only logic here or in
 * src/data/mock/*; production services must not import from those paths.
 */
import type { AlertItem, CallRecord, Employee, NextAction } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';
import { applyFilters } from '../lib/filters';
import { deriveAlerts } from '../lib/alerts';
import { generateDataset } from '../data/mock/generate';
import { EMPLOYEES } from '../data/mock/taxonomies';
import type { DataService } from './types';

const latency = () => new Promise<void>((r) => setTimeout(r, 120 + Math.random() * 180));

class MockService implements DataService {
  sourceLabel = 'Mock dataset (generated demo data — not customer records)';
  isMock = true;

  private dataset = generateDataset();
  private alertOverrides = new Map<string, AlertItem['status']>();
  private auditLog: { at: string; user: string; entry: string }[] = [
    { at: this.dataset.generatedAt, user: 'system', entry: 'Mock dataset generated (seed 20260730).' },
  ];
  private alertCache = new Map<string, AlertItem[]>();

  async lastRefresh() { return this.dataset.generatedAt; }

  async getFiltered(filters: FilterState): Promise<FilteredData> {
    await latency();
    return applyFilters(this.dataset.calls, filters);
  }

  async getCall(id: string): Promise<CallRecord | null> {
    await latency();
    return this.dataset.calls.find((c) => c.id === id) ?? null;
  }

  async getEmployees(): Promise<Employee[]> { return EMPLOYEES; }

  async getAlerts(filters: FilterState): Promise<AlertItem[]> {
    await latency();
    const key = JSON.stringify(filters);
    if (!this.alertCache.has(key)) {
      this.alertCache.set(key, deriveAlerts(applyFilters(this.dataset.calls, filters)));
    }
    return this.alertCache.get(key)!.map((a) => ({ ...a, status: this.alertOverrides.get(a.id) ?? a.status }));
  }

  async updateAction(actionId: string, patch: Partial<Pick<NextAction, 'status' | 'ownerEmployeeId' | 'dueDate' | 'priority'>>): Promise<NextAction | null> {
    await latency();
    for (const call of this.dataset.calls) {
      const a = call.actions.find((x) => x.id === actionId);
      if (a) {
        Object.assign(a, patch);
        if (patch.status === 'completed') a.slaStatus = a.slaStatus === 'overdue' ? 'breached' : 'met';
        if (patch.dueDate) {
          const due = new Date(patch.dueDate);
          const now = new Date();
          a.slaStatus = due < now ? 'overdue' : due.toDateString() === now.toDateString() ? 'due_today' : 'on_track';
        }
        this.auditLog.unshift({ at: new Date().toISOString(), user: 'demo-user', entry: `Action ${actionId} updated: ${JSON.stringify(patch)}` });
        this.alertCache.clear();
        return { ...a };
      }
    }
    return null;
  }

  async setAlertStatus(alertId: string, status: AlertItem['status']): Promise<void> {
    this.alertOverrides.set(alertId, status);
    this.auditLog.unshift({ at: new Date().toISOString(), user: 'demo-user', entry: `Alert ${alertId} marked ${status}` });
  }

  async logCorrection(entry: { callId: string; field: string; oldValue: string; newValue: string; user: string }): Promise<void> {
    this.auditLog.unshift({ at: new Date().toISOString(), user: entry.user, entry: `Correction on ${entry.callId}: ${entry.field} "${entry.oldValue}" → "${entry.newValue}"` });
  }

  async getAuditLog() { return this.auditLog; }
}

export const mockService = new MockService();
