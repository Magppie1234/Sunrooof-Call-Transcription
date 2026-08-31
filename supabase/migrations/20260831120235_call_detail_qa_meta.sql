-- ============================================================================
-- call_detail.qa_meta — the rest of the QA audit
--
-- WHY
-- call_detail carries four audit columns (criteria, conduct, red flags, review
-- reasons) and nothing else from the audit. QaAuditPanel reads seven fields, and
-- three of them are not stored anywhere in these tables:
--
--     qa.context          x4 in the panel — the Card subtitle
--     qa.contextReason    x2
--     qa.agent            x1 — the first name in every heading
--
-- The static detail files under public/data/detail/ carry the whole audit, so
-- Call Detail renders a complete panel locally and would render a degraded one
-- through GET /api/call/[id] — the same page, quietly different depending on
-- where the data came from. Nothing would error; the subtitle explaining WHY a
-- call scored as it did ("Customer had not enquired") would simply be absent.
--
-- WHY ONE jsonb AND NOT THREE COLUMNS
-- Three text columns would fix today's gap and invite a fourth migration the
-- next time the panel reads another field. qa_meta holds every audit field that
-- does not already have a column of its own, which is the same split
-- dashboard_calls already makes with `payload`: real columns for what SQL
-- filters on, one jsonb for what is only ever read back whole. Nothing filters
-- on the audit scalars.
--
-- SAFE TO RUN ON A LOADED TABLE
-- Additive and nullable, so it takes no rewrite and no long lock. Rows written
-- before the loader is re-run simply have qa_meta null, which the route treats
-- the same as an audit with no extra fields.
--
-- TO APPLY
--     npx supabase db push
-- then re-run scripts/load_dashboard_tables.py to populate it.
-- ============================================================================

alter table call_detail
  add column if not exists qa_meta jsonb;

comment on column call_detail.qa_meta is
  'Every QA audit field without a column of its own — score, tier, agent, customer, context, contextReason, autoZeroCodes, needsReview, criticalMisses, coaching. Read back whole; nothing filters on it. Combined with qa_criteria/qa_conduct/qa_red_flags/qa_review_reasons it reconstructs the audit exactly as qa_audits.json holds it, so GET /api/call/[id] and the static detail files are interchangeable.';

-- ============================================================================
-- Verification — run after applying, then after re-running the loader
-- ============================================================================
--   select column_name, data_type from information_schema.columns
--    where table_name = 'call_detail' and column_name = 'qa_meta';
--   -- qa_meta | jsonb
--
--   select count(*) from call_detail where qa_meta is not null;   -- 6253
--
--   select qa_meta->>'context', qa_meta->>'agent'
--     from call_detail where call_id = '887064000041219263';
--   -- both non-null
-- ============================================================================
