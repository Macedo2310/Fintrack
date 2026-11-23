-- FinTrack · 0013 · Funções de apoio ao backend FastAPI (app_supabase.py).
-- transaction_page e spending_aggregates: SECURITY INVOKER (o RLS de quem chama vale).
-- service_*: só service_role, para o que o backend faz em nome do sistema (indicadores, resumo semanal).

create or replace function public.transaction_page(
  p_type text default null, p_start date default null, p_end date default null, p_q text default null,
  p_sort text default 'date_desc', p_page int default 1, p_page_size int default 20)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare
  v_uid uuid := private.require_uid();
  v_page int := greatest(1, least(coalesce(p_page, 1), 100000));
  v_size int := greatest(1, least(coalesce(p_page_size, 20), 100));
  v_term text;
begin
  if p_start is not null and p_end is not null and p_start > p_end then
    perform private.http_error(422, 'A data inicial não pode ser posterior à final.');
  end if;
  if nullif(btrim(p_q), '') is not null then
    v_term := '%' || replace(replace(replace(left(btrim(p_q), 80), '\', '\\'), '%', '\%'), '_', '\_') || '%';
  end if;
  return (
    with f as (
      select t.*, c.name as category_name, r.frequency as recurrence_frequency, r.active as recurrence_active
        from public.transactions t
        join public.categories c on c.id = t.category_id
        left join public.recurrences r on r.id = t.recurrence_id and r.user_id = t.user_id
       where t.user_id = v_uid
         and (p_type is null or p_type not in ('receita', 'despesa') or t.type = p_type)
         and (p_start is null or t.occurred_on >= p_start)
         and (p_end is null or t.occurred_on <= p_end)
         and (v_term is null or t.description ilike v_term escape '\' or c.name ilike v_term escape '\')
    )
    select jsonb_build_object(
      'total', (select count(*) from f),
      'page', v_page, 'page_size', v_size,
      'summary', (select jsonb_build_object(
          'receitas', coalesce(sum(amount_cents) filter (where type = 'receita'), 0),
          'despesas', coalesce(sum(amount_cents) filter (where type = 'despesa'), 0),
          'resultado', coalesce(sum(case when type = 'receita' then amount_cents else -amount_cents end), 0)) from f),
      'items', coalesce((select jsonb_agg(jsonb_build_object(
          'id', x.id, 'type', x.type, 'category', x.category_name, 'category_id', x.category_id, 'description', x.description,
          'amount_cents', x.amount_cents, 'date', x.occurred_on, 'note', x.note, 'recurrence_id', x.recurrence_id,
          'recurrence_frequency', x.recurrence_frequency, 'recurrence_active', x.recurrence_active,
          'created_at', x.created_at, 'updated_at', x.updated_at) order by x.rn)
        from (select f.*, row_number() over (order by
                case when p_sort = 'amount_desc' then f.amount_cents end desc,
                case when p_sort = 'amount_asc' then f.amount_cents end asc,
                case when p_sort = 'date_asc' then f.occurred_on end asc,
                case when p_sort = 'date_asc' then f.created_at end asc,
                f.occurred_on desc, f.created_at desc) rn
                from f) x
       where x.rn > (v_page - 1) * v_size and x.rn <= v_page * v_size), '[]')));
end $$;

-- Agregados por categoria e tipo (sem descrições) para a análise de gastos com IA.
create or replace function public.spending_aggregates(p_start date, p_end date)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select coalesce(jsonb_agg(jsonb_build_object('category', c.name, 'type', s.type, 'amount_cents', s.total, 'count', s.n)), '[]')
    from (select category_id, type, sum(amount_cents)::bigint total, count(*)::int n
            from public.transactions
           where user_id = (select auth.uid()) and occurred_on between p_start and p_end
           group by category_id, type) s
    join public.categories c on c.id = s.category_id
$$;

-- ===== Somente service_role =====

create or replace function private.service_upsert_market_indicator(
  p_key text, p_label text, p_value numeric, p_unit text, p_period_kind text, p_observed_on date,
  p_reference text, p_source_url text, p_payload jsonb)
returns void language sql security definer set search_path = '' as $$
  insert into private.market_indicators (key, label, value, unit, period_kind, observed_on, reference_label, source_url, fetched_at, payload)
  values (p_key, p_label, p_value, p_unit, p_period_kind, p_observed_on, p_reference, p_source_url, now(), p_payload)
  on conflict (key) do update set label = excluded.label, value = excluded.value, unit = excluded.unit,
    period_kind = excluded.period_kind, observed_on = excluded.observed_on, reference_label = excluded.reference_label,
    source_url = excluded.source_url, fetched_at = excluded.fetched_at, payload = excluded.payload
$$;

create or replace function private.service_mark_market_error(p_key text)
returns void language sql security definer set search_path = '' as $$
  update private.market_indicators set last_error_at = now() where key = p_key
$$;

-- Quem ativou o resumo semanal e ainda não recebeu nesta semana, com os totais dos 7 dias anteriores.
create or replace function private.service_weekly_summary_candidates(p_week text, p_start date, p_end date)
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'user_id', p.id, 'name', p.name, 'email', u.email,
      'receitas', coalesce(t.r, 0), 'despesas', coalesce(t.d, 0), 'lancamentos', coalesce(t.n, 0),
      'metas_ativas', (select count(*) from public.goals g where g.user_id = p.id and g.status = 'ativa'))), '[]')
    from public.profiles p
    join public.user_settings s on s.user_id = p.id and s.weekly_email
    join auth.users u on u.id = p.id
    left join lateral (
      select sum(amount_cents) filter (where type = 'receita')::bigint r, sum(amount_cents) filter (where type = 'despesa')::bigint d, count(*)::int n
        from public.transactions x where x.user_id = p.id and x.occurred_on between p_start and p_end) t on true
   where not exists (select 1 from private.weekly_email_log w where w.user_id = p.id and w.iso_week = p_week)
$$;

create or replace function private.service_mark_weekly_sent(p_user uuid, p_week text)
returns void language sql security definer set search_path = '' as $$
  insert into private.weekly_email_log (user_id, iso_week) values (p_user, p_week) on conflict do nothing
$$;

-- Liga/desliga a permissão de ativar o resumo semanal conforme o SMTP do backend.
create or replace function private.service_set_email_ready(p_ready boolean)
returns void language sql security definer set search_path = '' as $$
  update private.app_settings set value = to_jsonb(p_ready), updated_at = now() where key = 'email_delivery_ready'
$$;


-- Wrappers públicos SECURITY INVOKER (as funções SECURITY DEFINER ficam em private, fora da Data API).
create or replace function public.service_upsert_market_indicator(
  p_key text, p_label text, p_value numeric, p_unit text, p_period_kind text, p_observed_on date,
  p_reference text, p_source_url text, p_payload jsonb default null)
returns void language sql security invoker set search_path = '' as $$
  select private.service_upsert_market_indicator(p_key, p_label, p_value, p_unit, p_period_kind, p_observed_on, p_reference, p_source_url, p_payload) $$;
create or replace function public.service_mark_market_error(p_key text)
returns void language sql security invoker set search_path = '' as $$ select private.service_mark_market_error(p_key) $$;
create or replace function public.service_weekly_summary_candidates(p_week text, p_start date, p_end date)
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.service_weekly_summary_candidates(p_week, p_start, p_end) $$;
create or replace function public.service_mark_weekly_sent(p_user uuid, p_week text)
returns void language sql security invoker set search_path = '' as $$ select private.service_mark_weekly_sent(p_user, p_week) $$;
create or replace function public.service_set_email_ready(p_ready boolean)
returns void language sql security invoker set search_path = '' as $$ select private.service_set_email_ready(p_ready) $$;

revoke all on function private.service_upsert_market_indicator(text, text, numeric, text, text, date, text, text, jsonb),
  private.service_mark_market_error(text), private.service_weekly_summary_candidates(text, date, date),
  private.service_mark_weekly_sent(uuid, text), private.service_set_email_ready(boolean) from public, anon, authenticated;
grant execute on function private.service_upsert_market_indicator(text, text, numeric, text, text, date, text, text, jsonb),
  private.service_mark_market_error(text), private.service_weekly_summary_candidates(text, date, date),
  private.service_mark_weekly_sent(uuid, text), private.service_set_email_ready(boolean) to service_role;

revoke all on function public.transaction_page(text, date, date, text, text, int, int), public.spending_aggregates(date, date),
  public.service_upsert_market_indicator(text, text, numeric, text, text, date, text, text, jsonb), public.service_mark_market_error(text),
  public.service_weekly_summary_candidates(text, date, date), public.service_mark_weekly_sent(uuid, text),
  public.service_set_email_ready(boolean) from public, anon, authenticated;
grant execute on function public.transaction_page(text, date, date, text, text, int, int), public.spending_aggregates(date, date) to authenticated;
grant execute on function public.service_upsert_market_indicator(text, text, numeric, text, text, date, text, text, jsonb),
  public.service_mark_market_error(text), public.service_weekly_summary_candidates(text, date, date),
  public.service_mark_weekly_sent(uuid, text), public.service_set_email_ready(boolean) to service_role;
