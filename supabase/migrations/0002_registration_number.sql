-- ============================================================================
-- Master Prompters 2.0: registration-number login + manual registration
-- ADDITIVE. Adds a `registration_number` column to pc_participants so admins
-- can register participants manually and they can sign in with their official
-- registration number (not just a QR code).
-- Idempotent: safe to run more than once.
-- ============================================================================

alter table public.pc_participants
  add column if not exists registration_number text;

-- A participant may sign in by reg number within a single competition.
create unique index if not exists uq_pc_participants_competition_regnum
  on public.pc_participants (competition_id, registration_number)
  where registration_number is not null;
