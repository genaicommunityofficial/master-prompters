-- ============================================================================
-- Master Prompters 2.0: make pgcrypto visible to login RPCs
-- ADDITIVE. Does not modify registrations / events / checkins.
--
-- Symptom: login with abhinavkumarsaksena fails with
--   function gen_random_bytes(integer) does not exist
-- Cause: 0005 SECURITY DEFINER functions used search_path = public only.
-- On Supabase, pgcrypto is installed in the extensions schema.
-- ============================================================================

create extension if not exists pgcrypto;

alter function public._pc_hash_session(text)
  set search_path = public, extensions;

alter function public._pc_issue_session(public.pc_participants, text, text)
  set search_path = public, extensions;

alter function public._pc_participant_from_session(text)
  set search_path = public, extensions;

alter function public._pc_ensure_participant_from_reg(text, public.registrations)
  set search_path = public, extensions;

alter function public.pc_login_registration(text, text)
  set search_path = public, extensions;

alter function public.pc_login_qr(text, text, text)
  set search_path = public, extensions;

alter function public.pc_submission_exists(text)
  set search_path = public, extensions;

alter function public.pc_submit(text, text, jsonb)
  set search_path = public, extensions;

alter function public.pc_submit_one(text, text, text, text)
  set search_path = public, extensions;

alter function public.pc_public_leaderboard(text)
  set search_path = public, extensions;

notify pgrst, 'reload schema';
