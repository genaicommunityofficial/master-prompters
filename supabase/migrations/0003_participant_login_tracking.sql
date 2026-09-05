-- ============================================================================
-- Master Prompters 2.0: participation funnel tracking
-- ADDITIVE. Adds login tracking columns to pc_participants so the admin panel
-- can show the funnel: registered -> logged in -> submitted.
-- Idempotent: safe to run more than once.
-- ============================================================================

alter table public.pc_participants
  add column if not exists login_count int not null default 0;

alter table public.pc_participants
  add column if not exists last_login_at timestamptz;