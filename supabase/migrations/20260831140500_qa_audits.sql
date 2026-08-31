-- ============================================================================
-- qa_audits — the Advanced QA list, out of the bundle.
--
-- ci-dashboard/src/pages/AdvancedQa.tsx imports qa_audits.slim.json directly:
-- 9.98 MB, the last large file left in the build. It is a lazy route so it is
-- not in the first paint, but it is still uploaded and still served to whoever
-- opens the page.
--
-- WHY THIS IS ITS OWN TABLE AND NOT A JOIN ON call_detail
-- Two reasons, and the first is not negotiable:
--
-- 1. THE AUDIT SET IS 6,260 ROWS AND dashboard_calls IS 6,253. The seven extra
--    are calls where Sarvam returned an empty transcript; build_ci_dataset.py
--    drops them at `if not entries: continue`, while the audit pipeline's
--    conversation gate recorded them as context=no_contact, tier=NOT_SCORED,
--    score=null. Both systems are right and the difference is deliberate — see
--    the note in 20260829105655_dashboard_tables.sql, which lists the same
--    seven ids. call_detail has a foreign key to dashboard_calls, so those
--    seven CANNOT live there. The page's own header reads "6,260 rows"; a
--    table that could only hold 6,253 would silently drop them.
--
-- 2. The list query has no business touching call_detail, whose rows average
--    15 KB because they carry transcripts and per-criterion evidence.
--
-- WHAT THIS TABLE DOES NOT HOLD
-- `criteria` and `conduct` — 46 MB across the corpus, read only when a single
-- audit is opened. Those stay in call_detail, which is what /api/call/[id]
-- already reads. The split here is the same one build_slim_dataset.py makes.
-- ============================================================================

create table if not exists qa_audits (
  -- No foreign key, on purpose. See reason 1 above: seven of these audits
  -- describe calls that dashboard_calls does not and should not contain.
  call_id     text        primary key,

  -- numeric, never integer. 596 of these scores are fractional, and rounding
  -- them moved at least one call across a tier floor (887064000041661165,
  -- 74.5 -> 75, SILVER where the stored tier says BRONZE). Null is meaningful
  -- and distinct from zero: NOT SCORED means the call could not be assessed,
  -- which the page states in bold and must never render as a failing grade.
  score       numeric,
  tier        text,
  status      text,

  -- Everything else the list view reads: agent, customer, date, durationSec,
  -- summary, sentiment, outcome, preDeduction, earned, adjustedMax, deduction,
  -- autoZero, autoZeroCodes, criticalMisses, redFlags, needsReview,
  -- reviewReasons, context, contextReason, coaching.
  --
  -- Deliberately not spread across twenty columns. Nothing filters on them in
  -- SQL — the page holds the whole list in memory and does its own tier
  -- filtering, search, sort and CSV export, because it is independent of the
  -- global date filter by design. Typing columns nothing queries is DDL you
  -- maintain forever; score, tier and status are typed because they mirror
  -- dashboard_calls and are the ones a future query would narrow on.
  payload     jsonb       not null default '{}'::jsonb,

  updated_at  timestamptz not null default now()
);

comment on table qa_audits is
  'One row per audited call, 6,260 of them - seven more than dashboard_calls. The slim audit: everything except criteria and conduct, which stay in call_detail.';
comment on column qa_audits.call_id is
  'No FK to dashboard_calls: seven audits describe calls with empty transcripts that the dataset deliberately excludes.';
comment on column qa_audits.score is
  'Null means the call could not be assessed. That is not a zero and the tier bands treat it differently.';

create index if not exists qa_audits_tier_idx   on qa_audits (tier);
create index if not exists qa_audits_score_idx  on qa_audits (score);
create index if not exists qa_audits_status_idx on qa_audits (status);


-- ============================================================================
-- qa_audit_run — one row, the stamp on the audit as a whole
-- ============================================================================
--
-- generated_at IS TEXT, NOT timestamptz, AND THAT IS THE POINT.
-- The value is "2026-08-27T14:50:44+0530" — a +0530 offset with no colon — and
-- AdvancedQa.tsx renders it with `.slice(0, 16).replace('T', ' ')`, i.e. it
-- prints the first sixteen characters of the raw string. Stored as timestamptz
-- it comes back normalised to UTC, so the page would display "2026-08-27 09:20"
-- where it has always displayed "2026-08-27 14:50". Nothing would error; the
-- date on the page would just quietly be five and a half hours early. Kept as
-- text, it survives the round trip exactly.

create table if not exists qa_audit_run (
  id            boolean     primary key default true check (id),
  generated_at  text        not null,
  corpus_size   integer     not null,
  audited_count integer     not null,
  model         text        not null,
  scorecard     text        not null,
  updated_at    timestamptz not null default now()
);

comment on column qa_audit_run.generated_at is
  'Text, not timestamptz: the page prints the raw string and a UTC normalisation would silently shift the displayed time by the +0530 offset.';


-- Same default as every other dashboard table: RLS on, no policies yet, so
-- anon and authenticated read nothing and service_role bypasses. These are
-- graded assessments of named employees against named customers.
alter table qa_audits    enable row level security;
alter table qa_audit_run enable row level security;


-- ============================================================================
-- Verification
-- ============================================================================
--   select count(*) from qa_audits;                          -- 6260
--   select count(*) from qa_audits where score is not null;  -- 4342
--   select count(*) from qa_audit_run;                       -- 1
--   select count(*) from qa_audits a
--    where not exists (select 1 from dashboard_calls d where d.call_id = a.call_id);
--                                                            -- exactly 7
