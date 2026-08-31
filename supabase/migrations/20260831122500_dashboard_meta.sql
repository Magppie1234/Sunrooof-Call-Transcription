-- ============================================================================
-- Corpus metadata: what the app shell needs before it can render anything.
--
-- WHY THIS EXISTS
-- components/layout.tsx — the always-loaded shell — imported four constants
-- from realService (DATA_ANCHOR, DATASET_CALL_COUNT, DATASET_MIN_DATE,
-- DATASET_MAX_DATE), and data/taxonomy.ts imported the snapshot to build the
-- employee, region, state, product, language and lead-source lists for the
-- filter bar. Both are static edges from the main chunk into
-- dataset.slim.json, so the 21.5 MB of call data stayed in the bundle no matter
-- what mode the app ran in. Serving these few kilobytes is what severs that.
--
-- WHY THE TAXONOMY IS STORED RATHER THAN DERIVED IN SQL
-- `select distinct region from dashboard_calls` looks like the obvious way to
-- build the region list, and it is the wrong one. build_ci_dataset.py already
-- computes these lists while it joins Zoho, Sarvam and the enrichment files,
-- with its own normalisation and exclusions; re-deriving them here would give
-- two definitions of "the products list" that agree today and drift the first
-- time the Python changes. This is the same reasoning the original migration
-- gave for not re-deriving the joins in SQL. So the pipeline writes what it
-- computed, and the API hands it back unchanged.
--
-- The three values that ARE derived live — count, min and max timestamp — are
-- derived from dashboard_calls on purpose: they describe what is actually in
-- the table, so if the table and the snapshot ever disagree, the dashboard
-- shows the table's truth rather than a stale stamp.
-- ============================================================================


-- ============================================================================
-- 1. dashboard_employees — 17 rows of reference data
-- ============================================================================
--
-- A table rather than another jsonb blob in the snapshot row, because
-- employee_id is the column the Agent-role RLS policy will read. A policy
-- cannot join against a jsonb array, and the id is already a real column on
-- dashboard_calls.
--
-- team, manager and role are frequently the literal string 'Not mapped in CRM'
-- — Zoho does not carry them. That is data, not a defect, and it is stored as
-- it comes rather than nulled, so the dashboard keeps showing the same text it
-- shows today. Never substitute a guess: see the naming rule in CLAUDE.md.

create table if not exists dashboard_employees (
  employee_id text        primary key,
  name        text        not null,
  team        text,
  manager     text,
  role        text,
  updated_at  timestamptz not null default now()
);

comment on table dashboard_employees is
  'Agent roster from Zoho, as resolved by build_ci_dataset.py. Read by /api/meta; employee_id joins dashboard_calls.employee_id.';


-- ============================================================================
-- 2. dashboard_snapshot — exactly one row
-- ============================================================================
--
-- The single-row constraint is enforced by the primary key, not by convention:
-- `id boolean primary key default true check (id)` admits precisely one row,
-- so a second insert fails loudly instead of leaving the API to pick between
-- two rows and the reader to wonder which one it got.

create table if not exists dashboard_snapshot (
  id           boolean     primary key default true check (id),
  generated_at timestamptz not null,
  source_label text        not null,
  taxonomy     jsonb       not null default '{}'::jsonb,
  geo          jsonb       not null default '[]'::jsonb,
  updated_at   timestamptz not null default now()
);

comment on table dashboard_snapshot is
  'One row. Stamp of the last pipeline run plus the facet lists it computed.';
comment on column dashboard_snapshot.taxonomy is
  'The taxonomy object from dataset.json verbatim: regions, states, cities, products, languages, leadSources, campaigns, teams.';
comment on column dashboard_snapshot.geo is
  'Distinct region/state/city triples, in the order data/taxonomy.ts built them, so the cascading region -> state filter offers the same options it does today.';


-- ============================================================================
-- 3. dashboard_meta — one row, one round trip
-- ============================================================================
--
-- security_invoker is not optional. A view defaults to the PRIVILEGES OF ITS
-- OWNER, so a view over RLS-protected tables owned by a superuser hands every
-- row to anyone who can select from it — the loophole already found and fixed
-- on call_action_state. Setting it here means the view is subject to the
-- caller's policies, which is what the base tables' RLS is for.
--
-- min_ts and max_ts are returned raw. The client derives the anchor date and
-- the picker bounds from them using the SAME function in both data modes, so
-- the two cannot disagree about which day "last 30 days" ends on — the same
-- argument /api/calls makes for not reimplementing matchesDims() in SQL.

create or replace view dashboard_meta
with (security_invoker = true) as
select
  s.generated_at,
  s.source_label,
  s.taxonomy,
  s.geo,
  (select count(*)      from dashboard_calls) as call_count,
  (select min(call_ts)  from dashboard_calls) as min_ts,
  (select max(call_ts)  from dashboard_calls) as max_ts
from dashboard_snapshot s
where s.id;

comment on view dashboard_meta is
  'Everything the app shell needs before first render. One row, a few KB. Read by /api/meta.';


-- ============================================================================
-- Row-level security
-- ============================================================================
-- Same default as the other dashboard tables: enabled, no policies yet, so
-- anon and authenticated read nothing while service_role (the API) bypasses.
-- The roster is not public data — it is the names of real employees.

alter table dashboard_employees enable row level security;
alter table dashboard_snapshot  enable row level security;


-- ============================================================================
-- Verification
-- ============================================================================
--   select count(*) from dashboard_employees;   -- 17
--   select count(*) from dashboard_snapshot;    -- 1
--   select call_count, min_ts, max_ts from dashboard_meta;
--       -- 6253, and max_ts must be 2026-07-31T13:20:23+00: the dashboard's
--       -- default period ends one day after it, at 2026-08-01T13:20:23+00,
--       -- which is the bound the 4,655-call check in the first migration uses.
--   select jsonb_array_length(geo) from dashboard_snapshot;   -- 456
