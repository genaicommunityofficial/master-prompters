-- ============================================================================
-- Master Prompters 2.0: session tokens without pgcrypto
-- ADDITIVE. Does not modify registrations / events / checkins.
--
-- Symptom: login still fails with
--   function gen_random_bytes(integer) does not exist
-- Cause: _pc_issue_session called pgcrypto even after search_path tweaks.
-- Fix: mint tokens with gen_random_uuid() (core Postgres).
-- ============================================================================

create or replace function public._pc_hash_session(p_token text)
returns text
language sql
immutable
set search_path = public, pg_catalog
as $$
  select md5(p_token) || md5('pc-session|' || p_token);
$$;

create or replace function public._pc_issue_session(
  p_participant public.pc_participants,
  p_competition_id text,
  p_registration_number text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_token text;
  v_already boolean;
begin
  v_token := 'pcs_' || replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');

  update public.pc_participants
  set
    session_token_hash = public._pc_hash_session(v_token),
    login_count = coalesce(login_count, 0) + 1,
    last_login_at = now(),
    updated_at = now()
  where id = p_participant.id;

  select exists (
    select 1
    from public.pc_submissions s
    where s.participant_id = p_participant.id
      and s.competition_id = p_competition_id
  ) into v_already;

  return jsonb_build_object(
    'requires_qr', false,
    'token', v_token,
    'participant', jsonb_build_object(
      'competition_id', p_competition_id,
      'participant_id', p_participant.id,
      'display_name', coalesce(p_participant.display_name, 'Participant'),
      'email', p_participant.email,
      'vit_registration_number', coalesce(
        nullif(public._pc_norm_reg(p_registration_number), ''),
        p_participant.registration_number
      ),
      'already_submitted', v_already
    ),
    'display_name', coalesce(p_participant.display_name, 'Participant')
  );
end;
$$;

revoke all on function public._pc_hash_session(text) from public;
revoke all on function public._pc_issue_session(public.pc_participants, text, text) from public;

notify pgrst, 'reload schema';
