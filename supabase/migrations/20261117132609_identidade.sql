-- FinTrack · 0002 · Identidade, perfis, preferências, avatar e lembretes.
-- Senhas, salts, sessões e tokens de recuperação ficam no Supabase Auth: nada disso existe em public.
-- O PAPEL (aluno/professor) fica em public.profiles.role, gravado UMA vez pela RPC complete_onboarding
-- (SECURITY DEFINER, valida código de professor) e sem GRANT de UPDATE para o cliente.
-- raw_user_meta_data (editável pelo usuário) só sugere o NOME inicial; nunca decide permissões.

create table public.profiles (
  id                uuid primary key references auth.users (id) on delete cascade,
  name              text not null check (char_length(name) between 2 and 100),
  role              text check (role in ('aluno', 'professor')),
  onboarding_status text not null default 'pendente'
                    check (onboarding_status in ('pendente', 'sem_avatar', 'concluido')),
  terms_accepted_at timestamptz,
  legacy_user_id    text unique,      -- id do SQLite 0.6.x (conferência da migração); null para contas novas
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint profiles_onboarding_consistente check (
    (onboarding_status = 'pendente') = (role is null)
    and (role is null or terms_accepted_at is not null))
);
comment on column public.profiles.role is 'Gravado somente por private.complete_onboarding ou pelo service_role. O cliente não tem GRANT de UPDATE nesta coluna.';
create trigger profiles_touch before update on public.profiles for each row execute function private.touch_updated_at();

create table public.user_settings (
  user_id      uuid primary key references public.profiles (id) on delete cascade,
  theme        text not null default 'dark' check (theme in ('dark', 'light')),
  chart_type   text not null default 'line' check (chart_type in ('line', 'bar', 'pie')),
  tips         boolean not null default true,
  goal_alerts  boolean not null default true,
  weekly_email boolean not null default false,
  updated_at   timestamptz not null default now()
);
comment on column public.user_settings.weekly_email is 'Preferência da pessoa. NÃO significa que o envio esteja configurado: só pode ser ativada se private.app_settings.email_delivery_ready = true.';
create trigger user_settings_touch before update on public.user_settings for each row execute function private.touch_updated_at();

create or replace function private.user_settings_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.weekly_email and (tg_op = 'INSERT' or not old.weekly_email)
     and coalesce((private.setting('email_delivery_ready'))::boolean, false) is not true then
    perform private.http_error(422, 'O envio de e-mails não está configurado neste servidor; o resumo semanal não pode ser ativado.');
  end if;
  return new;
end $$;
create trigger user_settings_guard before insert or update of weekly_email on public.user_settings
  for each row execute function private.user_settings_guard();

create table public.user_avatars (
  user_id    uuid primary key references public.profiles (id) on delete cascade,
  kind       text not null check (kind in ('preset', 'photo')),
  preset     text not null default 'coruja'
             check (preset in ('cacheada','longos','plumas','classico','aviador','coruja','cao','gato','raposa','urso')),
  bg         text not null default '#1DB954'
             check (bg in ('#1DB954','#7C5CFF','#3B82F6','#FF5C8A','#F5A524','#2A2A2A')),
  photo_path text,           -- caminho no bucket privado "avatars": <user_id>/<arquivo>
  photo_mime text check (photo_mime in ('image/jpeg', 'image/png', 'image/webp')),
  updated_at timestamptz not null default now(),
  constraint user_avatars_foto_consistente check (
    (kind = 'photo') = (photo_path is not null) and (photo_path is null) = (photo_mime is null)),
  constraint user_avatars_caminho_do_dono check (photo_path is null or photo_path like user_id::text || '/%')
);
create trigger user_avatars_touch before update on public.user_avatars for each row execute function private.touch_updated_at();

create table public.reminder_preferences (
  user_id              uuid primary key references public.profiles (id) on delete cascade,
  lessons              boolean not null default true,
  spending             boolean not null default true,
  -- 0 = sem limite definido (mesma convenção da 0.6.x). NULL não é usado.
  monthly_budget_cents bigint not null default 0 check (monthly_budget_cents between 0 and 100000000000),
  updated_at           timestamptz not null default now()
);
create trigger reminder_preferences_touch before update on public.reminder_preferences for each row execute function private.touch_updated_at();

-- Ao escolher avatar, o onboarding termina.
create or replace function private.avatar_finishes_onboarding()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  update public.profiles set onboarding_status = 'concluido'
   where id = new.user_id and onboarding_status = 'sem_avatar';
  return new;
end $$;
create trigger user_avatars_onboarding after insert or update on public.user_avatars
  for each row execute function private.avatar_finishes_onboarding();

-- Trocar para avatar padrão limpa a foto (o arquivo antigo é apagado pelo backend).
create or replace function private.user_avatars_preset_clears_photo()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.kind = 'preset' then new.photo_path := null; new.photo_mime := null; end if;
  return new;
end $$;
create trigger user_avatars_preset before insert or update on public.user_avatars
  for each row execute function private.user_avatars_preset_clears_photo();

-- Gatilho de cadastro: cria perfil e preferências. Nunca bloqueia o cadastro: em erro, registra em
-- private.signup_trigger_errors e a RPC complete_onboarding recria o que faltar.
create or replace function private.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_name text;
begin
  begin
    v_name := left(coalesce(
      private.clean_text(new.raw_user_meta_data ->> 'name'),
      private.clean_text(new.raw_user_meta_data ->> 'full_name'),
      private.clean_text(split_part(coalesce(new.email, ''), '@', 1)),
      'Usuário'), 100);
    if char_length(v_name) < 2 then v_name := 'Usuário'; end if;
    insert into public.profiles (id, name) values (new.id, v_name) on conflict (id) do nothing;
    insert into public.user_settings (user_id) values (new.id) on conflict (user_id) do nothing;
    insert into public.reminder_preferences (user_id) values (new.id) on conflict (user_id) do nothing;
  exception when others then
    begin
      insert into private.signup_trigger_errors (user_id, sqlstate, message) values (new.id, sqlstate, left(sqlerrm, 500));
    exception when others then
      raise warning 'FinTrack: falha ao registrar erro do gatilho de cadastro (%).', sqlstate;
    end;
  end;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function private.handle_new_user();

-- Onboarding: papel + termos, uma única vez.
create or replace function private.complete_onboarding(p_name text, p_role text, p_accept_terms boolean, p_professor_code text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_uid();
  v_name text := private.clean_text(p_name);
  v_code_hash text := private.setting('professor_signup_code_sha256') #>> '{}';
  v_profile public.profiles;
begin
  perform private.hit_rate_limit('onboarding:' || v_uid, 10, interval '1 hour');
  if p_role is null or p_role not in ('aluno', 'professor') then perform private.http_error(422, 'Perfil inválido.'); end if;
  if p_accept_terms is not true then perform private.http_error(422, 'Aceite os termos e a política de privacidade.'); end if;
  if v_name is null or char_length(v_name) not between 2 and 100 then perform private.http_error(422, 'Confira os campos: nome.'); end if;
  if p_role = 'professor' and coalesce(v_code_hash, '') <> '' and
     encode(extensions.digest(coalesce(p_professor_code, ''), 'sha256'), 'hex') <> v_code_hash then
    perform private.http_error(403, 'Cadastro de professor requer autorização.');
  end if;

  insert into public.profiles (id, name) values (v_uid, v_name) on conflict (id) do nothing;
  insert into public.user_settings (user_id) values (v_uid) on conflict (user_id) do nothing;
  insert into public.reminder_preferences (user_id) values (v_uid) on conflict (user_id) do nothing;

  select * into v_profile from public.profiles where id = v_uid for update;
  if v_profile.role is not null then
    perform private.http_error(409, 'O perfil desta conta já foi definido.');
  end if;
  update public.profiles
     set name = v_name, role = p_role, terms_accepted_at = now(),
         onboarding_status = case when exists (select 1 from public.user_avatars a where a.user_id = v_uid)
                                  then 'concluido' else 'sem_avatar' end
   where id = v_uid
  returning * into v_profile;
  return jsonb_build_object('role', v_profile.role, 'onboarding_status', v_profile.onboarding_status,
                            'next', case when v_profile.onboarding_status = 'concluido' then '/app.html' else '/avatar.html' end);
end $$;

create or replace function public.complete_onboarding(p_name text, p_role text, p_accept_terms boolean, p_professor_code text default null)
returns jsonb language sql security invoker set search_path = '' as $$
  select private.complete_onboarding(p_name, p_role, p_accept_terms, p_professor_code)
$$;

-- "Pular" avatar: usa o padrão (coruja, verde), igual à 0.6.x.
create or replace function public.skip_avatar()
returns void language plpgsql security invoker set search_path = '' as $$
declare v_uid uuid := private.require_uid();
begin
  insert into public.user_avatars (user_id, kind, preset, bg) values (v_uid, 'preset', 'coruja', '#1DB954')
  on conflict (user_id) do nothing;
end $$;

-- ===== Privilégios =====
alter table public.profiles enable row level security;
alter table public.user_settings enable row level security;
alter table public.user_avatars enable row level security;
alter table public.reminder_preferences enable row level security;

revoke all on public.profiles, public.user_settings, public.user_avatars, public.reminder_preferences from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (name) on public.profiles to authenticated;
grant select on public.user_settings to authenticated;
grant update (theme, chart_type, tips, goal_alerts, weekly_email) on public.user_settings to authenticated;
grant select on public.user_avatars to authenticated;
grant insert (user_id, kind, preset, bg) on public.user_avatars to authenticated;
grant update (kind, preset, bg) on public.user_avatars to authenticated;
grant select on public.reminder_preferences to authenticated;
grant insert (user_id, lessons, spending, monthly_budget_cents) on public.reminder_preferences to authenticated;
grant update (lessons, spending, monthly_budget_cents) on public.reminder_preferences to authenticated;
grant all on public.profiles, public.user_settings, public.user_avatars, public.reminder_preferences to service_role;

-- profiles: a política de leitura entre professor e aluno da mesma turma é criada na migração de turmas.
create policy profiles_select_own on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy profiles_update_own on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy user_settings_select_own on public.user_settings for select to authenticated
  using (user_id = (select auth.uid()));
create policy user_settings_update_own on public.user_settings for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy user_avatars_select_own on public.user_avatars for select to authenticated
  using (user_id = (select auth.uid()));
-- Cliente só grava avatar PADRÃO. Foto: backend valida o conteúdo e grava com service_role.
create policy user_avatars_insert_preset on public.user_avatars for insert to authenticated
  with check (user_id = (select auth.uid()) and kind = 'preset');
create policy user_avatars_update_preset on public.user_avatars for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and kind = 'preset');

create policy reminder_preferences_select_own on public.reminder_preferences for select to authenticated
  using (user_id = (select auth.uid()));
create policy reminder_preferences_insert_own on public.reminder_preferences for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy reminder_preferences_update_own on public.reminder_preferences for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on function private.complete_onboarding(text, text, boolean, text), private.handle_new_user(),
  private.user_settings_guard(), private.avatar_finishes_onboarding(), private.user_avatars_preset_clears_photo() from public, anon;
grant execute on function private.complete_onboarding(text, text, boolean, text) to authenticated;
grant execute on function private.user_settings_guard(), private.avatar_finishes_onboarding(),
  private.user_avatars_preset_clears_photo() to authenticated, service_role;
revoke all on function public.complete_onboarding(text, text, boolean, text), public.skip_avatar() from public, anon;
grant execute on function public.complete_onboarding(text, text, boolean, text), public.skip_avatar() to authenticated;
