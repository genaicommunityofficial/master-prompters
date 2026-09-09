-- ============================================================================
-- Participant sign-in completes from registration number alone.
-- Event QR is no longer required after the number is accepted.
-- Does not modify registrations / events / checkins.
-- ============================================================================

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
  v_status text;
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

  if found then
    return public._pc_issue_session(
      v_participant,
      p_competition_id,
      coalesce(v_participant.registration_number, v_needle)
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

  v_status := lower(coalesce(v_reg.registration_status, ''));
  if v_status <> '' and v_status not in ('verified', 'confirmed', 'approved') then
    raise exception 'Registration is not verified yet';
  end if;

  if coalesce(v_reg.qr_token, '') = '' then
    raise exception 'This registration number is not registered for this event.';
  end if;

  v_participant := public._pc_ensure_participant_from_reg(p_competition_id, v_reg);
  return public._pc_issue_session(
    v_participant,
    p_competition_id,
    coalesce(nullif(public._pc_norm_reg(v_reg.vit_registration_number), ''), v_needle)
  );
end;
$$;
