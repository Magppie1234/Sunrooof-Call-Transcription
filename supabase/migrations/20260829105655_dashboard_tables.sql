-- ============================================================================
-- Dashboard read/write tables.
--
-- The dashboard currently reads two build-time JSON snapshots compiled into the
-- JS bundle (56.8 MB + 59.0 MB, 18.8 MB gzipped on every page load). These three
-- tables replace that: the pipeline writes here, an API reads here.
--
-- WHAT THE PIPELINE DOES NOT CHANGE
-- build_ci_dataset.py keeps its joins. It already reconciles Supabase
-- call_summaries and transcripts with the Zoho export, recording URLs, FAQ
-- analysis and per-call enrichment files; re-deriving that in SQL is where the
-- numbers would quietly stop agreeing with the reports. Only its final write
-- changes, from a .json file to an upsert against these tables.
--
-- call_summaries remains the system of record. Nothing here mutates it.
--
-- TO DRY-RUN THIS BEFORE APPLYING IT
-- Paste the body into the Supabase SQL editor wrapped in a transaction:
--     begin;  <everything below>  rollback;
-- Postgres executes DDL transactionally, so a syntax error surfaces and the
-- rollback leaves the database exactly as it was. That is a better check than a
-- scratch schema: nothing to remember to drop afterwards.
--
-- TO APPLY IT
--     npx supabase db push
-- ============================================================================


-- ============================================================================
-- 1. dashboard_calls — one row per call, everything the list views need
-- ============================================================================
--
-- WHY THE TYPED/JSONB SPLIT
-- A call record carries 57 fields. Giving all 57 their own column is DDL you
-- maintain forever for fields nothing ever queries; putting all 57 in one jsonb
-- blob makes every filter an untyped string comparison. So: a real column for
-- anything that is filtered, sorted, grouped, or referenced by a security
-- policy, and jsonb for the rest.
--
-- The typed list below is derived from what matchesDims() in
-- ci-dashboard/src/lib/filters.ts actually reads, not from guesswork. It came
-- out at 29 columns rather than the ~17 first estimated, because the filter bar
-- reaches into nested objects (sentiment.overall) and into array lengths
-- (complianceFlags) that are cheaper to flatten once here than to dig out of
-- jsonb on every query.
--
-- Getting the boundary slightly wrong is survivable: Postgres indexes
-- expressions, so a field that turns out to need one can get
--   create index on dashboard_calls ((payload ->> 'spaceType'));
-- without a migration. The fields that are genuinely expensive to move later
-- are the ones a security policy or a date range depends on, which is why
-- employee_id and call_ts are typed and will stay that way.

create table if not exists dashboard_calls (
  call_id                 text        primary key,

  -- Time. timestamptz, never text: the period filter is a range scan, and a
  -- text date sorts lexically, which silently breaks the moment the format
  -- drifts. Source field is dateTime, already ISO-8601 with an offset.
  call_ts                 timestamptz not null,

  -- Ownership. employee_id is referenced by the Agent-role RLS policy, so it
  -- must be a real, indexed, NOT NULL column — a policy written against a
  -- jsonb path returns zero rows on a typo instead of raising an error.
  employee_id             text        not null,

  -- Customer
  customer_id             text,
  customer_name           text,
  customer_type           text,

  -- Call shape
  direction               text,
  duration_sec            integer,
  language                text,
  connected               boolean     not null default false,
  meaningful              boolean     not null default false,
  transcribed             boolean     not null default false,
  transcription_confidence real,
  diarization_reliable    boolean     not null default false,

  -- Geography (filter bar cascades region -> state -> city)
  region                  text,
  state                   text,
  city                    text,

  -- Commercial
  product_series          text,
  lead_source             text,
  campaign                text,
  crm_stage               text,
  outcome                 text,
  intent                  text,

  -- Flattened out of nested objects because the filter bar reads them directly.
  -- The full sentiment and quality objects stay in payload.
  sentiment_overall       text,
  compliance_flag_count   integer     not null default 0,

  -- QA audit. Null is meaningful and common: ~1,918 calls returned no score,
  -- mostly for insufficient conversation. Do not default these to 0 — a zero
  -- score and an absent score mean different things and the tier bands treat
  -- them differently.
  qa_score                integer,
  qa_tier                 text,
  qa_status               text,

  -- Searched by the Call Explorer text box, so typed rather than buried.
  summary                 text,
  topics                  text[],

  -- Everything else: sentiment, purchaseReadiness, quality, talk, crm, faqs,
  -- actions, objections, commitments, risks, buyingSignals, painPoints,
  -- expectations, featureRequests, appreciationThemes, dissatisfactionThemes,
  -- competitorMentions, complianceFlags, spaceType, customerNeed,
  -- budgetMentioned, timelineMentioned, decisionMaker, discountRequested,
  -- crossSell, hasRecording, crmNoteSynced, crmTranscriptSynced.
  payload                 jsonb       not null default '{}'::jsonb,

  updated_at              timestamptz not null default now()
);

comment on table dashboard_calls is
  'One row per call: the slim list payload. Written by build_ci_dataset.py, read by /api/calls. Not the system of record — that is call_summaries.';
comment on column dashboard_calls.payload is
  'Fields no query filters on. Index with an expression index if that changes.';
comment on column dashboard_calls.qa_score is
  'Null means not scored (insufficient conversation), which is distinct from a score of 0.';

-- Indexes: every column the filter bar can narrow on. At 6,253 rows Postgres
-- would happily sequential-scan all of these — they are here for the next 10x,
-- and because creating them now is free while backfilling them later is not.
create index if not exists dashboard_calls_ts_idx          on dashboard_calls (call_ts desc);
create index if not exists dashboard_calls_employee_idx    on dashboard_calls (employee_id);
create index if not exists dashboard_calls_region_idx      on dashboard_calls (region);
create index if not exists dashboard_calls_state_idx       on dashboard_calls (state);
create index if not exists dashboard_calls_city_idx        on dashboard_calls (city);
create index if not exists dashboard_calls_outcome_idx     on dashboard_calls (outcome);
create index if not exists dashboard_calls_sentiment_idx   on dashboard_calls (sentiment_overall);
create index if not exists dashboard_calls_intent_idx      on dashboard_calls (intent);
create index if not exists dashboard_calls_qa_tier_idx     on dashboard_calls (qa_tier);
create index if not exists dashboard_calls_topics_idx      on dashboard_calls using gin (topics);

-- The analysed-set predicate (meaningful AND transcribed AND confidence above
-- threshold) is the denominator behind most insight metrics, so it gets its own
-- partial index rather than three separate ones.
create index if not exists dashboard_calls_analysed_idx
  on dashboard_calls (call_ts desc)
  where meaningful and transcribed;


-- ============================================================================
-- 2. call_detail — the heavy per-call fields, read one row at a time
-- ============================================================================
--
-- These four fields are 79 MB of the 116 MB currently shipped to every browser
-- on first paint, and grep confirms transcript, entities and recordingUrl are
-- read only by CallDetail.tsx. Separating them is what takes the initial
-- payload from 18.8 MB gzipped to 3.5 MB.

create table if not exists call_detail (
  call_id           text        primary key references dashboard_calls (call_id) on delete cascade,
  transcript        jsonb,      -- speaker-separated turns with timestamps (~30.8 MB corpus-wide)
  entities          jsonb,
  recording_url     text,
  qa_criteria       jsonb,      -- per-criterion judgements and evidence (~33.0 MB)
  qa_conduct        jsonb,      -- (~15.4 MB)
  qa_red_flags      jsonb,
  qa_review_reasons jsonb,
  updated_at        timestamptz not null default now()
);

comment on table call_detail is
  'Heavy per-call fields, fetched by /api/call/[id] only when a call is opened. Never selected in list queries.';

-- KNOWN DATA INCONSISTENCY, surfaced by writing this foreign key.
-- qa_audits.json holds 6,260 unique audit records against 6,253 calls. Every
-- call has an audit, but seven audits reference call_ids absent from the
-- dataset:
--   887064000042182035  887064000044564591  887064000044968321
--   887064000045149336  887064000045269324  887064000047428241
--   887064000047613440
-- The FK will reject those seven rather than let them in unnoticed, which is
-- the point of having it. Before loading, decide which is true: these calls
-- were audited and later dropped by build_ci_dataset.py's filters (skip them,
-- log the count), or the dataset is missing calls it should contain (fix the
-- builder). Do not silently ON CONFLICT DO NOTHING them away — the "6,260-row
-- file holding 4,965 unique calls" incident began exactly this way, with a
-- count that looked plausible.


-- ============================================================================
-- 3. call_actions — the write side (Tuesday)
-- ============================================================================
--
-- APPEND-ONLY, ON PURPOSE. This is the only table holding data the pipeline
-- cannot regenerate: a human marking a call, flagging it, or recording that a
-- quotation went out. Storing current state in a mutable row would lose who
-- changed what and when — and the project's governance position on CRM
-- write-back requires exactly that trail. So every action is an event, and
-- "current state" is the latest event per (call_id, kind), materialised by the
-- view below.
--
-- The zoho_* columns make the two-sided write explicit: the row lands here
-- immediately so the UI never waits on Zoho, and the push is recorded (or its
-- failure is) separately. A Zoho outage delays the sync; it never loses the
-- user's input.

create table if not exists call_actions (
  id             bigint      generated always as identity primary key,
  call_id        text        not null references dashboard_calls (call_id) on delete cascade,

  kind           text        not null check (kind in (
                               'marked',            -- reviewed / handled
                               'flagged',           -- needs attention
                               'quotation_shared',  -- quotation sent to the customer
                               'call_result',       -- Zoho Call_Result picklist value
                               'note',              -- note pushed to the Zoho record
                               'correction'         -- manager correcting an AI output
                             )),
  value          text,        -- the picklist value, note body, or corrected text
  previous_value text,        -- what it replaced, for corrections

  created_by     uuid        references auth.users (id),
  created_at     timestamptz not null default now(),

  -- Zoho push state. Null synced_at with null error = queued, never attempted.
  zoho_synced_at timestamptz,
  zoho_error     text
);

comment on table call_actions is
  'Append-only event log of human actions on a call. Never UPDATE a row here — insert a new event. Current state comes from call_action_state.';
comment on column call_actions.zoho_synced_at is
  'Set when the push to Zoho CRM succeeded. Null with a null zoho_error means not yet attempted.';

create index if not exists call_actions_call_idx    on call_actions (call_id, kind, created_at desc);
create index if not exists call_actions_pending_idx on call_actions (created_at)
  where zoho_synced_at is null;

-- Current state per call and kind: the newest event wins.
create or replace view call_action_state as
select distinct on (call_id, kind)
  call_id, kind, value, created_by, created_at, zoho_synced_at, zoho_error
from call_actions
order by call_id, kind, created_at desc;

comment on view call_action_state is
  'Latest event per (call_id, kind). Read this for current state; write to call_actions.';


-- ============================================================================
-- Row-level security
-- ============================================================================
--
-- Enabled now, with no policies yet. That is the safe default rather than an
-- oversight: with RLS on and no policy, anon and authenticated roles read
-- nothing, while service_role (which the loader and the API use today) bypasses
-- RLS entirely. So an accidentally exposed anon key leaks nothing before
-- Monday's policies land.
--
-- Monday adds, in outline:
--   Management / Sales Manager / Quality Team -> full select
--   Agent -> select where employee_id = auth.jwt() ->> 'employee_id'
-- enforced here rather than in the client Guard, which today is a dropdown
-- anyone can change.

alter table dashboard_calls enable row level security;
alter table call_detail     enable row level security;
alter table call_actions    enable row level security;


-- ============================================================================
-- Verification — run after loading, before trusting anything
-- ============================================================================
-- Exit code 0 is not evidence. Every value below was measured against the
-- 29 Aug 2026 snapshot, not estimated:
--
--   select count(*) from dashboard_calls;                            -- 6253
--   select count(distinct call_id) from dashboard_calls;             -- 6253
--   select count(*) from call_detail;                                -- 6253
--   select count(*) from dashboard_calls where qa_score is not null;  -- 4342
--
-- The default period window. Note the exact timestamps: the dashboard anchors
-- its periods to the newest call plus one day (2026-08-01T13:20:23Z), NOT to
-- midnight. The calendar-day version of this range returns 4858, which would
-- look close enough to pass a glance and be wrong.
--
--   select count(*) from dashboard_calls
--    where call_ts >= '2026-07-02T13:20:23+00'
--      and call_ts <  '2026-08-01T13:20:23+00';                      -- 4655
--
-- 4655 is what the current build shows as Total calls on the Executive
-- Overview. If this query disagrees, the load is wrong — stop and find out why.
