-- ============================================================================
-- Dropped participants cannot log in. Uses existing pc_participants.status
-- DISQUALIFIED. Does not modify registrations / events / checkins.
-- ============================================================================

create or replace function public._pc_participant_from_session(p_session_token text)
returns public.pc_participants
language plpgsql
stable
security definer
set search_path = public, pg_catalog
as $$
declare
  v_row public.pc_participants;
  v_hash text;
begin
  if public._pc_norm_reg(p_session_token) = '' then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  v_hash := public._pc_hash_session(p_session_token);
  select * into v_row
  from public.pc_participants
  where session_token_hash = v_hash
  limit 1;
  if not found then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  if v_row.session_expires_at is not null and v_row.session_expires_at <= now() then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  if v_row.status = 'DISQUALIFIED' then
    raise exception 'This registration has been dropped from the competition.';
  end if;
  return v_row;
end;
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
  v_hash text;
  v_expires timestamptz;
  v_already boolean;
  v_sub_status text;
  v_done boolean;
  v_tester boolean;
  v_n int;
begin
  if p_participant.status = 'DISQUALIFIED' then
    raise exception 'This registration has been dropped from the competition.';
  end if;

  select s.status
  into v_sub_status
  from public.pc_submissions s
  where s.participant_id = p_participant.id
    and s.competition_id = p_competition_id
  limit 1;

  v_already := found;
  v_done := v_sub_status in ('SUBMITTED', 'COMPLETED')
    or p_participant.status = 'SUBMITTED';
  v_tester := coalesce(p_participant.is_pipeline_tester, false);

  v_token := 'pcs_' || replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
  v_hash := public._pc_hash_session(v_token);
  v_expires := now() + interval '8 hours';

  if v_tester or v_done then
    update public.pc_participants
    set
      session_token_hash = v_hash,
      session_expires_at = v_expires,
      login_count = coalesce(login_count, 0) + 1,
      last_login_at = now(),
      updated_at = now()
    where id = p_participant.id;
  else
    update public.pc_participants
    set
      session_token_hash = v_hash,
      session_expires_at = v_expires,
      login_count = coalesce(login_count, 0) + 1,
      last_login_at = now(),
      updated_at = now()
    where id = p_participant.id
      and (
        session_token_hash is null
        or session_expires_at is null
        or session_expires_at <= now()
      );
    get diagnostics v_n = row_count;
    if v_n = 0 then
      raise exception 'This registration is already signed in on another device. Continue there, or sign out first.';
    end if;
  end if;

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

create or replace function public.pc_login_registration(
  p_competition_id text,
  p_registration_number text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_comp public.pc_competitions;
  v_needle text;
  v_participant public.pc_participants;
  v_reg public.registrations;
  v_event text;
begin
  v_needle := public._pc_norm_reg(p_registration_number);
  if v_needle = '' then
    raise exception 'Please enter your registration number.';
  end if;

  select * into v_comp
  from public.pc_competitions
  where id = p_competition_id
  limit 1;
  if not found then
    raise exception 'Competition not found';
  end if;
  if v_comp.status not in ('OPEN', 'RESULTS_PUBLISHED') then
    raise exception 'Competition is not accepting logins right now';
  end if;

  select * into v_participant
  from public.pc_participants
  where competition_id = p_competition_id
    and lower(public._pc_norm_reg(registration_number)) = lower(v_needle)
  limit 1;

  if found and v_participant.status = 'DISQUALIFIED' then
    raise exception 'This registration has been dropped from the competition.';
  end if;

  if found and public._pc_can_skip_qr(v_participant) then
    return public._pc_issue_session(
      v_participant,
      p_competition_id,
      coalesce(v_participant.registration_number, v_needle)
    );
  end if;

  if found then
    return jsonb_build_object(
      'requires_qr', true,
      'token', null,
      'participant', null,
      'display_name', v_participant.display_name
    );
  end if;

  v_event := coalesce(v_comp.qr_event_id::text, '');

  select * into v_reg
  from public.registrations r
  where lower(public._pc_norm_reg(r.vit_registration_number)) = lower(v_needle)
    and (v_event = '' or r.event_id::text = v_event)
  limit 1;

  if not found then
    raise exception 'This registration number is not registered for this event.';
  end if;

  return jsonb_build_object(
    'requires_qr', true,
    'token', null,
    'participant', null,
    'display_name', nullif(trim(coalesce(v_reg.full_name, '')), '')
  );
end;
$$;
