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
import { EMPLOYEES, GEO, PRODUCT_SERIES, LANGUAGES, LEAD_SOURCES } from '../data/mock/taxonomies';
import { corpusFromCalls, type CorpusMeta } from '../data/corpusMeta';
import { loadQaSnapshot } from '../data/real/qaSnapshot';
import type { QaAuditSet } from '../data/qaAudits';
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

  /**
   * Mock mode used to borrow the REAL dataset's constants: layout.tsx imported
   * DATA_ANCHOR and friends from realService unconditionally, so the demo
   * dashboard reported the live corpus's call total and seeded its custom date
   * range from the live corpus's newest call. Supplying its own meta ends that.
   */
  async getMeta(): Promise<CorpusMeta> {
    return corpusFromCalls(this.dataset.calls, {
      generatedAt: this.dataset.generatedAt,
      sourceLabel: this.sourceLabel,
      employees: EMPLOYEES,
      // The mock pools carry a real postcode per city; the geo list keeps it.
      geo: GEO.map((g) => ({ region: g.region, state: g.state, city: g.city, pin: g.pin })),
      taxonomy: {
        regions: [...new Set(GEO.map((g) => g.region))],
        states: [...new Set(GEO.map((g) => g.state))],
        cities: [...new Set(GEO.map((g) => g.city))],
        products: [...PRODUCT_SERIES],
        languages: [...LANGUAGES],
        leadSources: [...LEAD_SOURCES],
        campaigns: [],
        teams: [...new Set(EMPLOYEES.map((e) => e.team))],
      },
    });
  }

  // The mock generator produces no scorecard audits, and Advanced QA has always
  // read the real ones: the page is independent of the global filters and of the
  // mode by design. Left as it was rather than quietly emptied.
  getQaAudits(): Promise<QaAuditSet> { return loadQaSnapshot(); }

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
