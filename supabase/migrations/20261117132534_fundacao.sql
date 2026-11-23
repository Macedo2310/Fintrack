-- FinTrack · 0001 · Fundação: schemas, privilégios padrão, utilitários, limites e erros HTTP.
--
-- Camadas de acesso:
--   public  -> exposto pela Data API. Só tabelas/funções com GRANT explícito + RLS.
--   private -> NÃO exposto. Gabaritos, cache de indicadores, controle de jobs, limites,
--              configurações e as funções SECURITY DEFINER chamadas pelas RPCs públicas.
-- RLS controla LINHAS; GRANT controla se o papel alcança a tabela/coluna/função.

-- 1) Exposição opt-in: nada criado em public fica acessível sem GRANT explícito.
alter default privileges for role postgres in schema public
  revoke select, insert, update, delete, truncate, references, trigger on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke execute on functions from anon, authenticated, public;
alter default privileges for role postgres in schema public
  revoke usage, select on sequences from anon, authenticated;

-- 2) Schema privado.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
-- authenticated precisa de USAGE para executar as funções privadas chamadas pelas RPCs e
-- pelas políticas RLS. Nenhuma TABELA de private recebe GRANT para anon/authenticated.
grant usage on schema private to authenticated, service_role;
alter default privileges for role postgres in schema private revoke execute on functions from public;
alter default privileges for role postgres in schema private revoke all on tables from public;

-- 3) Configurações do servidor (não expostas).
create table private.app_settings (
  key        text primary key check (key ~ '^[a-z0-9_]{3,60}$'),
  value      jsonb not null,
  updated_at timestamptz not null default now()
);
comment on table private.app_settings is 'Configurações do servidor. education_pass_percent, email_delivery_ready, professor_signup_code_sha256, max_money_cents.';
insert into private.app_settings(key, value) values
  ('education_pass_percent', '70'),
  ('max_money_cents', '100000000000'),
  ('email_delivery_ready', 'false')
on conflict (key) do nothing;
grant select, insert, update, delete on private.app_settings to service_role;

-- 4) Utilitários.
create or replace function private.today_br()
returns date language sql stable set search_path = '' as $$
  -- "Hoje" financeiro segue America/Sao_Paulo; instantes continuam em timestamptz.
  select (now() at time zone 'America/Sao_Paulo')::date
$$;

create or replace function private.clean_text(t text)
returns text language sql immutable set search_path = '' as $$
  select nullif(regexp_replace(btrim(t), '\s+', ' ', 'g'), '')
$$;

create or replace function private.setting(p_key text)
returns jsonb language sql stable security definer set search_path = '' as $$
  select value from private.app_settings where key = p_key
$$;

create or replace function private.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Erro com status HTTP para a Data API (PostgREST >= 12): 4xx com mensagem em português.
create or replace function private.http_error(p_status int, p_message text, p_code text default null)
returns void language plpgsql set search_path = '' as $$
begin
  raise sqlstate 'PGRST' using
    message = json_build_object('code', coalesce(p_code, 'FT' || p_status), 'message', p_message)::text,
    detail  = json_build_object('status', p_status, 'headers', json_build_object())::text;
end $$;

create or replace function private.require_uid()
returns uuid language plpgsql stable set search_path = '' as $$
declare v uuid := auth.uid();
begin
  if v is null then
    perform private.http_error(401, 'Sessão necessária.');
  end if;
  return v;
end $$;

-- 5) Limite de tentativas persistido (equivale ao rate_limit da 0.6.1).
create table private.rate_limits (
  key text not null check (char_length(key) <= 200),
  at  timestamptz not null default now()
);
create index rate_limits_key_at_idx on private.rate_limits (key, at);
create index rate_limits_at_idx on private.rate_limits (at);

create or replace function private.hit_rate_limit(p_key text, p_limit int, p_window interval)
returns void language plpgsql security definer set search_path = '' as $$
declare v_n int; v_first timestamptz;
begin
  -- Serializa por chave para que chamadas simultâneas não ultrapassem o limite.
  perform pg_advisory_xact_lock(hashtextextended('ft:rl:' || p_key, 0));
  delete from private.rate_limits where key = p_key and at <= now() - p_window;
  select count(*), min(at) into v_n, v_first from private.rate_limits where key = p_key;
  if v_n >= p_limit then
    raise sqlstate 'PGRST' using
      message = json_build_object('code', 'FT429', 'message', 'Muitas tentativas. Aguarde um pouco e tente novamente.')::text,
      detail  = json_build_object('status', 429, 'headers',
                  json_build_object('Retry-After', greatest(1, ceil(extract(epoch from (v_first + p_window - now()))))::int::text))::text;
  end if;
  insert into private.rate_limits(key) values (p_key);
end $$;

-- 6) Monitoramento mínimo de jobs e de falhas no gatilho de cadastro.
create table private.job_runs (
  id          bigint generated always as identity primary key,
  job         text not null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      text not null default 'executando' check (status in ('executando', 'ok', 'erro')),
  affected    int,
  detail      text
);
create index job_runs_job_started_idx on private.job_runs (job, started_at desc);
create index job_runs_errors_idx on private.job_runs (started_at desc) where status = 'erro';

create table private.signup_trigger_errors (
  id         bigint generated always as identity primary key,
  user_id    uuid not null,
  sqlstate   text not null,
  message    text not null,
  created_at timestamptz not null default now()
);

grant select, insert, update, delete on private.rate_limits, private.job_runs, private.signup_trigger_errors to service_role;

revoke all on all functions in schema private from public, anon;
grant execute on function private.today_br(), private.clean_text(text), private.require_uid(),
  private.http_error(int, text, text)
  to authenticated, service_role;
-- setting() e hit_rate_limit() são usados só por funções SECURITY DEFINER (executam como dono).
grant execute on function private.setting(text), private.hit_rate_limit(text, int, interval) to service_role;
grant execute on function private.touch_updated_at() to authenticated, service_role;
