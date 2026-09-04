-- ============================================================================
-- Master Prompters 2.0: per-category markdown evaluation criteria
-- ADDITIVE. Does not modify existing pc_* tables.
-- Each category (question) in a competition has one markdown rubric used to
-- score that category's prompts. Admin uploads via the admin panel.
-- Idempotent: safe to run more than once.
-- ============================================================================

create table if not exists public.pc_eval_criteria (
  competition_id   text not null references public.pc_competitions(id) on delete cascade,
  question_number  int  not null,
  file_name        text not null default 'criteria.md',
  content_md       text not null,
  content_hash     text not null,
  updated_at       timestamptz not null default now(),
  unique (competition_id, question_number)
);

create index if not exists idx_pc_eval_criteria_competition
  on public.pc_eval_criteria(competition_id);

alter table public.pc_eval_criteria enable row level security;

-- Only the backend (service role) reads/writes; no public access.
revoke all on table public.pc_eval_criteria from anon, authenticated;