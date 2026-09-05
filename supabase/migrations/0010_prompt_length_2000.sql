-- ============================================================================
-- Master Prompters 2.0: raise prompt max length to 2000 characters
-- ADDITIVE. Updates pc_questions only. Does not modify registrations / events.
-- ============================================================================

alter table public.pc_questions
  alter column max_length set default 2000;

update public.pc_questions
set
  min_length = 20,
  max_length = 2000
where competition_id in ('competition_2026', 'competition_test');
