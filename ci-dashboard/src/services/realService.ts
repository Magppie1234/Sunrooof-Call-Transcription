/**
 * LIVE IMPLEMENTATION of DataService, backed by the real Sunrooof dataset.
 *
 * The dataset is a build-time snapshot (`src/data/real/dataset.slim.json`)
 * produced by `scripts/build_ci_dataset.py` and split by
 * `scripts/build_slim_dataset.py`, joining:
 *   Zoho CRM Calls + Leads · Sarvam Saaras v3 transcripts · gpt-4.1-mini
 *   extraction (summaries, sentiment, readiness, objections, FAQs).
 *
 * A snapshot rather than live API calls because this app started as a static
 * SPA with no server to hold Zoho/Supabase credentials — the same reason the
 * numbers are as of `generatedAt` rather than this second. That is what the
 * Supabase migration is undoing; liveService will be the other implementation
 * of this same interface, reading /api/* instead.
 *
 * THE SNAPSHOT IS LOADED WITH A DYNAMIC IMPORT
 * A static `import dataset from '...json'` puts the whole file in whatever
 * chunk references this module, and services/index.ts references it from the
 * main chunk. So the 21.5 MB arrived on first paint even in modes that never
 * touched it. Behind `await import()` it becomes its own chunk, fetched only
 * when a method actually needs the calls. Every DataService method is already
 * async, so nothing above had to change to accommodate it.
 *
 * Writes (action status, alert status, corrections) stay in memory: there is no
 * task or escalation system to persist them to. That limit is declared in
 * src/lib/provenance.ts and surfaced in the UI.
 */
import type { AlertItem, CallRecord, Employee, NextAction } from '../types/domain';
import type { FilterState, FilteredData } from '../lib/filters';
import { applyFilters } from '../lib/filters';
import { deriveAlerts } from '../lib/alerts';
import { corpusFromCalls, deriveCorpus, type Corpus, type CorpusMeta, type Taxonomy } from '../data/corpusMeta';
import type { DataService } from './types';

interface Dataset {
  generatedAt: string;
  sourceLabel: string;
  calls: CallRecord[];
  employees: Employee[];
  taxonomy: Taxonomy;
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

interface Loaded {
  calls: CallRecord[];
  meta: CorpusMeta;
  corpus: Corpus;
  generatedAt: string;
}

class RealService implements DataService {
  // Known before the snapshot loads, because the shell shows it in the banner
  // while getMeta() is still in flight. Replaced by the snapshot's own label
  // as soon as it arrives.
  sourceLabel = 'Live Sunrooof data (Zoho calls, Sarvam transcripts, gpt-4.1-mini extraction)';
  isMock = false;

  /** Merged records, so revisiting a call does not refetch its detail file. */
  private detailCache = new Map<string, CallRecord>();
  private alertOverrides = new Map<string, AlertItem['status']>();
  private alertCache = new Map<string, AlertItem[]>();
  private auditLog: { at: string; user: string; entry: string }[] = [];

  private loading: Promise<Loaded> | null = null;

  /** Loads the snapshot chunk once; every later call gets the same promise. */
  private load(): Promise<Loaded> {
    this.loading ??= import('../data/real/dataset.slim.json').then((mod) => {
      const data = (mod.default ?? mod) as unknown as Dataset;
      const meta = corpusFromCalls(data.calls, {
        generatedAt: data.generatedAt,
        sourceLabel: data.sourceLabel,
        employees: data.employees,
        taxonomy: data.taxonomy,
      });
      this.sourceLabel = data.sourceLabel;
      this.auditLog = [{
        at: data.generatedAt,
        user: 'system',
        entry: `Dataset built from Zoho CRM, Sarvam transcripts and gpt-4.1-mini extraction (${data.calls.length} calls).`,
      }];
      return { calls: data.calls, meta, corpus: deriveCorpus(meta), generatedAt: data.generatedAt };
    });
    return this.loading;
  }

  async getMeta(): Promise<CorpusMeta> { return (await this.load()).meta; }

  async lastRefresh() { return (await this.load()).generatedAt; }

  async getFiltered(filters: FilterState): Promise<FilteredData> {
    const { calls, corpus } = await this.load();
    return applyFilters(calls, filters, corpus.anchor);
  }

  /**
   * The list payload carries no transcript, entities, recordingUrl or QA
   * criteria — those are ~87 MB across the corpus and only ever render here, so
   * they live in one file per call under public/ and are fetched on demand.
   *
   * GET /api/call/[id] returns the same shape deliberately, so liveService
   * changes the URL and nothing else.
   */
  async getCall(id: string): Promise<CallRecord | null> {
    const { calls } = await this.load();
    const slim = calls.find((c) => c.id === id);
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

  async getEmployees(): Promise<Employee[]> { return (await this.load()).meta.employees; }

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

  async getAuditLog() { await this.load(); return this.auditLog; }
}

export const realService = new RealService();
