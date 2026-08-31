/**
 * Data-service contract. Pages talk ONLY to this interface — swapping mock for
 * live integrations (telephony, transcription, CRM, task, order, complaint
 * systems) means implementing DataService against real APIs. See
 * docs/06-api-integrations.md for the required endpoints.
 */
import type { AlertItem, CallRecord, Employee, NextAction, ActionStatus } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';
import type { CorpusMeta } from '../data/corpusMeta';
import type { QaAuditSet } from '../data/qaAudits';

export interface DataService {
  /** Human-readable label of the backing source, shown in the UI. */
  sourceLabel: string;
  isMock: boolean;
  /**
   * The option lists, roster and date bounds the app shell needs before it can
   * render. Resolved once by CorpusMetaProvider; nothing else should call it.
   */
  getMeta(): Promise<CorpusMeta>;
  /**
   * The PSM scorecard audits. Its own dataset with its own generatedAt, kept
   * separate from the call dataset so it can be regenerated while the audit is
   * still running — and 6,260 rows against the call list's 6,253.
   */
  getQaAudits(): Promise<QaAuditSet>;
  lastRefresh(): Promise<string>;
  getFiltered(filters: FilterState): Promise<FilteredData>;
  getCall(id: string): Promise<CallRecord | null>;
  getEmployees(): Promise<Employee[]>;
  getAlerts(filters: FilterState): Promise<AlertItem[]>;
  updateAction(actionId: string, patch: Partial<Pick<NextAction, 'status' | 'ownerEmployeeId' | 'dueDate' | 'priority'>>): Promise<NextAction | null>;
  setAlertStatus(alertId: string, status: AlertItem['status']): Promise<void>;
  /** Manager correction of an AI output — audit-logged. */
  logCorrection(entry: { callId: string; field: string; oldValue: string; newValue: string; user: string }): Promise<void>;
  getAuditLog(): Promise<{ at: string; user: string; entry: string }[]>;
}

export type { ActionStatus };
