-- FinTrack · 0008 · Lembretes no app, cache privado de indicadores do BCB, resumo semanal e painel.
-- Lembretes são internos ao app (sem push/e-mail). O resumo semanal por e-mail é enviado pelo backend
-- quando o SMTP está configurado; o banco só guarda o registro de envio (sem reenvio na mesma semana).

create table public.notifications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.profiles (id) on delete cascade,
  event_key   text not null check (char_length(event_key) <= 200),
  kind        text not null check (kind in ('goal', 'lesson', 'spending')),
  title       text not null check (char_length(title) <= 120),
  body        text not null check (char_length(body) <= 500),
  destination text not null check (destination in ('goals', 'education', 'classes', 'transactions')),
  created_at  timestamptz not null default now(),
  read_at     timestamptz,
  constraint notifications_event_uk unique (user_id, event_key)
);
create index notifications_user_created_idx on public.notifications (user_id, created_at desc, id desc);
create index notifications_unread_idx on public.notifications (user_id) where read_at is null;

create or replace function private.notifications_guard()
returns trigger language plpgsql set search_path = '' as $$
begin
  -- O cliente só marca como lido (não "desmarca" nem altera o horário de leitura).
  if old.read_at is not null then new.read_at := old.read_at; end if;
  if new.read_at is null then new.read_at := old.read_at; end if;
  if new.read_at is not null and old.read_at is null then new.read_at := now(); end if;
  return new;
end $$;
create trigger notifications_guard before update on public.notifications for each row execute function private.notifications_guard();

-- Porta de backend_services.generate_reminders (0.6.x). Idempotente pela chave (user_id, event_key).
create or replace function private.generate_reminders(p_user uuid)
returns int language plpgsql security definer set search_path = '' as $$
declare
  t date := private.today_br(); v_month text := to_char(private.today_br(), 'YYYY-MM');
  prefs public.reminder_preferences; v_goal_alerts boolean; g record; a record; n int := 0; k int;
  v_pending int; v_spent bigint; v_income bigint; v_stage text; v_title text; v_body text; v_iso text;
  function_events jsonb := '[]';
begin
  insert into public.reminder_preferences (user_id) values (p_user) on conflict do nothing;
  select * into prefs from public.reminder_preferences where user_id = p_user;
  select goal_alerts into v_goal_alerts from public.user_settings where user_id = p_user;

  if coalesce(v_goal_alerts, false) then
    for g in select o.* from public.goal_overview o where o.user_id = p_user and o.status = 'ativa' loop
      if g.reserved_cents >= g.target_cents or g.deadline <= t + 7 then
        v_stage := case when g.reserved_cents >= g.target_cents then 'ready' when g.deadline < t then 'overdue' else 'due' end;
        v_title := case v_stage when 'ready' then 'Meta pronta para concluir' when 'overdue' then 'Prazo da meta vencido' else 'Confira o prazo da sua meta' end;
        v_body := g.title || ' — ' || case v_stage
          when 'ready' then 'você já reservou o valor planejado.'
          when 'overdue' then 'o prazo era ' || to_char(g.deadline, 'DD/MM/YYYY') || '. Ajuste o prazo ou conclua a meta.'
          else 'prazo em ' || to_char(g.deadline, 'DD/MM/YYYY') || '.' end;
        function_events := function_events || jsonb_build_object('k', 'goal:' || g.id || ':' || g.deadline || ':' || v_stage,
          'kind', 'goal', 't', v_title, 'b', left(v_body, 500), 'd', 'goals');
      end if;
    end loop;
  end if;

  if prefs.lessons then
    select count(*) into v_pending from public.education_progress where user_id = p_user and status = 'em_andamento';
    if v_pending > 0 then
      v_iso := to_char(t, 'IYYY') || '-' || ltrim(to_char(t, 'IW'), '0');
      function_events := function_events || jsonb_build_object('k', 'lesson:' || v_iso, 'kind', 'lesson',
        't', 'Continue seu aprendizado', 'b', 'Você tem ' || v_pending || ' aula(s) em andamento. Reserve um momento para continuar.', 'd', 'education');
    end if;
    for a in select ap.assignment_id, x.due_date, c.name
               from public.assignment_progress ap
               join public.assignments x on x.id = ap.assignment_id
               join public.classes c on c.id = ap.class_id
              where ap.student_id = p_user and ap.status <> 'concluida' and x.due_date is not null and x.due_date <= t + 3 loop
      function_events := function_events || jsonb_build_object(
        'k', 'assignment:' || a.assignment_id || ':' || a.due_date || ':' || case when a.due_date < t then 'late' else 'due' end,
        'kind', 'lesson', 't', case when a.due_date < t then 'Atividade atrasada' else 'Atividade com prazo próximo' end,
        'b', left(a.name || ' — prazo ' || case when a.due_date < t then 'era' else 'em' end || ' ' || to_char(a.due_date, 'DD/MM/YYYY')
                  || '. Confira as atividades da turma.', 500), 'd', 'classes');
    end loop;
  end if;

  if prefs.spending then
    select coalesce(sum(amount_cents) filter (where type = 'despesa'), 0), coalesce(sum(amount_cents) filter (where type = 'receita'), 0)
      into v_spent, v_income
      from public.transactions where user_id = p_user and occurred_on between date_trunc('month', t)::date and t;
    if prefs.monthly_budget_cents > 0 and v_spent * 100 >= prefs.monthly_budget_cents * 80 then
      function_events := function_events || jsonb_build_object(
        'k', 'budget:' || v_month || ':' || prefs.monthly_budget_cents || ':' || case when v_spent >= prefs.monthly_budget_cents then '100' else '80' end,
        'kind', 'spending', 't', 'Atenção ao orçamento do mês',
        'b', 'Suas despesas atingiram ' || (v_spent * 100 / prefs.monthly_budget_cents) || '% do limite mensal definido por você.', 'd', 'transactions');
    elsif prefs.monthly_budget_cents = 0 and v_spent > v_income then
      function_events := function_events || jsonb_build_object('k', 'spending:' || v_month, 'kind', 'spending',
        't', 'Gastos acima das entradas',
        'b', 'As despesas registradas neste mês superam as receitas registradas. Confira seus lançamentos.', 'd', 'transactions');
    end if;
  end if;

  insert into public.notifications (user_id, event_key, kind, title, body, destination)
  select p_user, e ->> 'k', e ->> 'kind', e ->> 't', e ->> 'b', e ->> 'd' from jsonb_array_elements(function_events) e
  on conflict (user_id, event_key) do nothing;
  get diagnostics k = row_count; n := n + k;
  return n;
end $$;

create or replace function private.my_notifications(p_page int)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_page int := greatest(1, least(coalesce(p_page, 1), 10000));
begin
  perform private.generate_reminders(v_uid);
  return jsonb_build_object(
    'items', coalesce((select jsonb_agg(to_jsonb(x) order by x.created_at desc, x.id desc) from (
        select id, event_key, kind, title, body, destination, created_at, read_at from public.notifications
         where user_id = v_uid order by created_at desc, id desc limit 30 offset (v_page - 1) * 30) x), '[]'),
    'unread', (select count(*) from public.notifications where user_id = v_uid and read_at is null),
    'total', (select count(*) from public.notifications where user_id = v_uid));
end $$;

create or replace function public.my_notifications(p_page int default 1)
returns jsonb language sql security invoker set search_path = '' as $$ select private.my_notifications(p_page) $$;
create or replace function public.mark_all_notifications_read()
returns int language sql security invoker set search_path = '' as $$
  with u as (update public.notifications set read_at = now() where user_id = (select auth.uid()) and read_at is null returning 1)
  select count(*)::int from u
$$;

-- ===== Indicadores (cache privado; escrito pelo backend com service_role) =====
create table private.market_indicators (
  key             text primary key check (key in ('USD', 'EUR', 'SELIC', 'IPCA')),
  label           text not null,
  value           numeric(18, 6) not null,          -- cotação/percentual (não é dinheiro do usuário)
  unit            text not null,                    -- 'BRL · PTAX venda' | '% ao ano' | '% no mês'
  period_kind     text not null check (period_kind in ('fechamento_diario', 'meta_vigente', 'variacao_mensal')),
  observed_on     date not null,                    -- data de referência da fonte
  reference_label text not null,                    -- ex.: "Variação mensal de 10/2026" (IPCA do MÊS, não 12 meses)
  source          text not null default 'Banco Central do Brasil',
  source_url      text not null,
  fetched_at      timestamptz not null,
  last_error_at   timestamptz,
  payload         jsonb check (payload is null or pg_column_size(payload) <= 20000)  -- retido só do último sucesso
);

create or replace function private.market_indicators_view()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'items', coalesce((select jsonb_agg(jsonb_build_object(
        'key', m.key, 'label', m.label, 'value', m.value, 'unit', m.unit, 'period_kind', m.period_kind,
        'observed_at', m.observed_on, 'reference', m.reference_label, 'source', m.source, 'source_url', m.source_url,
        'fetched_at', m.fetched_at, 'stale', m.fetched_at < now() - interval '1 hour',
        'status', case when m.fetched_at < now() - interval '1 hour' then 'antigo' else 'atualizado' end)
        order by array_position(array['USD','EUR','SELIC','IPCA'], m.key))
      from private.market_indicators m), '[]'),
    'unavailable', coalesce((select jsonb_agg(k) from unnest(array['USD','EUR','SELIC','IPCA']) k
                              where not exists (select 1 from private.market_indicators m where m.key = k)), '[]'))
$$;
create or replace function public.market_indicators()
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.market_indicators_view() $$;

-- ===== Resumo semanal: controle de envio (backend envia; isto impede reenvio após reinícios) =====
create table private.weekly_email_log (
  user_id  uuid not null references public.profiles (id) on delete cascade,
  iso_week text not null check (iso_week ~ '^\d{4}-W\d{2}$'),
  sent_at  timestamptz not null default now(),
  primary key (user_id, iso_week)
);

-- ===== Painel (mesmo formato do /api/dashboard da 0.6.x) =====
create or replace function public.dashboard(p_start date default null, p_end date default null)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare
  v_uid uuid := private.require_uid(); t date := private.today_br();
  v_start date := coalesce(p_start, date_trunc('month', private.today_br())::date);
  v_end date := coalesce(p_end, private.today_br());
  v_bal jsonb; v_r bigint; v_d bigint; v_first date;
begin
  if v_start > v_end then perform private.http_error(422, 'A data inicial não pode ser posterior à final.'); end if;
  v_bal := public.balance_summary();
  select coalesce(sum(amount_cents) filter (where type = 'receita'), 0), coalesce(sum(amount_cents) filter (where type = 'despesa'), 0)
    into v_r, v_d from public.transactions where user_id = v_uid and occurred_on between v_start and v_end;
  v_first := (date_trunc('month', v_end::timestamp) - interval '5 months')::date;
  return jsonb_build_object(
    'period', jsonb_build_object('start', v_start, 'end', v_end),
    'balance_total', v_bal -> 'balance_total', 'reserved', v_bal -> 'reserved', 'available', v_bal -> 'available',
    'receitas', v_r, 'despesas', v_d, 'resultado', v_r - v_d,
    'categories', coalesce((select jsonb_agg(jsonb_build_object('category', c.name, 'category_id', c.id, 'amount_cents', s.total) order by s.total desc)
        from (select category_id, sum(amount_cents)::bigint total from public.transactions
               where user_id = v_uid and type = 'despesa' and occurred_on between v_start and v_end group by category_id) s
        join public.categories c on c.id = s.category_id), '[]'),
    'months', (select jsonb_agg(jsonb_build_object('month', to_char(m, 'YYYY-MM'),
                  'receitas', coalesce(x.r, 0), 'despesas', coalesce(x.d, 0)) order by m)
                 from generate_series(v_first::timestamp, date_trunc('month', v_end::timestamp), interval '1 month') m
                 left join (select date_trunc('month', occurred_on::timestamp) mm,
                                   sum(amount_cents) filter (where type = 'receita')::bigint r,
                                   sum(amount_cents) filter (where type = 'despesa')::bigint d
                              from public.transactions
                             where user_id = v_uid and occurred_on between v_first and (date_trunc('month', v_end::timestamp) + interval '1 month - 1 day')::date
                             group by 1) x on x.mm = m),
    'recent', coalesce((select jsonb_agg(to_jsonb(r)) from (
        select x.id, x.type, x.category_id, c.name category, x.description, x.amount_cents, x.occurred_on, x.note, x.recurrence_id
          from public.transactions x join public.categories c on c.id = x.category_id
         where x.user_id = v_uid and x.occurred_on between v_start and v_end
         order by x.occurred_on desc, x.created_at desc limit 5) r), '[]'),
    'goals', coalesce((select jsonb_agg(to_jsonb(g)) from (
        select * from public.goal_overview where user_id = v_uid and status = 'ativa' order by deadline limit 4) g), '[]'));
end $$;

-- ===== Privilégios =====
alter table public.notifications enable row level security;
alter table private.market_indicators enable row level security;
alter table private.weekly_email_log enable row level security;
revoke all on public.notifications from anon, authenticated;
revoke all on private.market_indicators, private.weekly_email_log from public, anon, authenticated;
grant select on public.notifications to authenticated;
grant update (read_at) on public.notifications to authenticated;
grant all on public.notifications to service_role;
grant all on private.market_indicators, private.weekly_email_log to service_role;

create policy notifications_select_own on public.notifications for select to authenticated using (user_id = (select auth.uid()));
create policy notifications_mark_read_own on public.notifications for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on function private.notifications_guard(), private.generate_reminders(uuid), private.my_notifications(int),
  private.market_indicators_view() from public, anon;
grant execute on function private.my_notifications(int), private.market_indicators_view() to authenticated;
grant execute on function private.generate_reminders(uuid) to service_role;
revoke all on function public.my_notifications(int), public.mark_all_notifications_read(), public.market_indicators(),
  public.dashboard(date, date) from public, anon;
grant execute on function public.my_notifications(int), public.mark_all_notifications_read(), public.market_indicators(),
  public.dashboard(date, date) to authenticated;
