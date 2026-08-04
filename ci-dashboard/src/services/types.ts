/**
 * Data-service contract. Pages talk ONLY to this interface — swapping mock for
 * live integrations (telephony, transcription, CRM, task, order, complaint
 * systems) means implementing DataService against real APIs. See
 * docs/06-api-integrations.md for the required endpoints.
 */
import type { AlertItem, CallRecord, Employee, NextAction, ActionStatus } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';

export interface DataService {
  /** Human-readable label of the backing source, shown in the UI. */
  sourceLabel: string;
  isMock: boolean;
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
