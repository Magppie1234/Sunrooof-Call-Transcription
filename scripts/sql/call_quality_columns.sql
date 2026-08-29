-- Columns the call-quality audit writes into the existing call_summaries table.
-- Additive only: nothing existing is altered or dropped, so the current
-- summary pipeline and dashboard keep working unchanged.
-- Run once in the Supabase SQL editor before the first `--with-audit` run.

alter table call_summaries
  add column if not exists call_quality_audit        jsonb,
  -- Lifted out of the jsonb so list views can filter and sort without
  -- opening the blob on every row.
  add column if not exists qa_final_score            numeric(5,1),
  add column if not exists qa_tier                   text,
  add column if not exists qa_auto_zero              boolean,
  add column if not exists qa_requires_human_review  boolean,
  add column if not exists qa_critical_miss_codes    text[],
  add column if not exists qa_red_flag_codes         text[];

create index if not exists call_summaries_qa_tier_idx
  on call_summaries (qa_tier);
create index if not exists call_summaries_qa_review_idx
  on call_summaries (qa_requires_human_review)
  where qa_requires_human_review;
create index if not exists call_summaries_qa_score_idx
  on call_summaries (qa_final_score);
