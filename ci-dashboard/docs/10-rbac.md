# 10 · Role-Based Access Structure

Demo implementation: role switcher in the sidebar ("Viewing as") + route guard
(`src/state/AppState.tsx`, `src/App.tsx`). In production, roles come from SSO claims and are
**enforced server-side** in the DataService; the client mirror is UX only.

| Capability | Management | Sales Manager | Service Manager | Quality Team | Agent |
|---|---|---|---|---|---|
| Executive Overview | ✔ | ✔ | ✔ | — | — |
| Customer Voice / FAQs | ✔ | ✔ | ✔ | ✔ | ✔ (own calls) |
| Regional Intelligence | ✔ | ✔ | — | — | — |
| Sales & Objections | ✔ | ✔ | — | — | — |
| Agent Quality | ✔ | ✔ (own teams) | ✔ (own teams) | ✔ | — (sees own scores via Voice/Calls) |
| Next-Action Tracker | ✔ | ✔ | ✔ | — | ✔ (own actions) |
| Call Explorer + transcripts | ✔ | ✔ | ✔ | ✔ | ✔ (own calls only — enforced by pinned employee filter) |
| Alerts & Escalations | ✔ | ✔ | ✔ | ✔ | — |
| Data Quality & Config | ✔ | — | — | ✔ | — |
| Approve/reject AI actions | ✔ | ✔ | ✔ | — | own only |
| Correct AI outputs | ✔ | ✔ | ✔ | ✔ | — |
| Revenue & CRM financials | ✔ | ✔ (own funnel) | — | — | — |
| Raw customer PII | masked by default; unmask permission is a separate grant with audit log | | | | |

Additional production requirements: per-team data scoping for managers, audit log of transcript
reads, export permission gate, and admin-only taxonomy/threshold configuration.
