-- ============================================================================
-- Master Prompters 2.0: pipeline tester flag
-- ADDITIVE. Does not modify registrations / events / checkins.
-- Pipeline testers can exercise the participant flow but are excluded from
-- leaderboards and the admin participants roster.
-- ============================================================================

alter table public.pc_participants
  add column if not exists is_pipeline_tester boolean not null default false;

create index if not exists idx_pc_participants_pipeline_tester
  on public.pc_participants (competition_id)
  where is_pipeline_tester = true;
