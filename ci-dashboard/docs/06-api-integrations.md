# 6 · API & Integration Requirements

The UI talks only to the `DataService` interface (`src/services/types.ts`). Going live =
implementing `LiveService` against these systems and switching `DATA_MODE` in `src/config.ts`.
Mock data lives exclusively under `src/data/mock/` + `src/services/mockService.ts` and is
labelled in the UI.

## Required integrations

### 1. Telephony / dialer
- `GET /calls?from&to&cursor` → call metadata (id, ts, direction, duration, agent, connected)
- `GET /calls/:id/recording` → signed audio URL (range requests for seek-to-timestamp)
- Webhook `call.completed` → triggers transcription pipeline

### 2. Transcription (ASR)
- `POST /transcribe` (audio URL) → job; webhook on completion
- Payload: `segments[{start,end,speaker,text,confidence}]`, `language`, `asr_confidence`,
  `diarization_quality`. Multilingual: original text mandatory; `translation` optional and
  displayed separately.

### 3. AI extraction service
- `POST /extract` (transcript + metadata + taxonomy version) → the AI-extraction schema
  (doc 07). Must return per-insight confidence and transcript offsets.

### 4. CRM (e.g. Zoho CRM — a Sunrooof/Zoho connector is already available in this workspace)
- Read: customer identity, region/state/city/pincode, segment, lead stage, source, campaign,
  opportunity & order status, revenue, owner.
- Write (only via approved user actions, never automatic): task creation, note attachment.

### 5. Task / follow-up system
- Two-way sync of NextAction ↔ task (create on approve, status webhooks back). Until connected,
  action management is in-app only (declared on Data Quality page).

### 6. Order management — verified conversion + revenue attribution (order ↔ customer ↔ call window).

### 7. Complaint / ticketing — open-complaint status for alert rules.

### 8. Approved knowledge base
- Versioned approved answers per FAQ. Until connected, the dashboard assesses answer
  **relevance/completeness only, never factual accuracy** (enforced in UI copy).

## Service contract (already defined)

```ts
interface DataService {
  getFiltered(filters): Promise<FilteredData>   // server-side filtering + windowing
  getCall(id): Promise<CallRecord | null>
  getEmployees(): Promise<Employee[]>
  getAlerts(filters): Promise<AlertItem[]>
  updateAction(id, patch): Promise<NextAction | null>   // audit-logged
  setAlertStatus(id, status): Promise<void>             // audit-logged
  logCorrection(entry): Promise<void>                   // manager corrections
  getAuditLog(): Promise<AuditEntry[]>
}
```

Live implementation notes: paginate server-side (cursor), cache aggregates per filter-hash,
enforce RBAC server-side (doc 10), mask PII before it reaches the client, log every read of a
transcript for audit.
