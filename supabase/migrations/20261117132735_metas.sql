-- FinTrack · 0004 · Metas e reservas (separação lógica do saldo registrado; não move dinheiro).
-- Regras:
--   saldo total  = receitas até hoje − despesas até hoje
--   reservado    = Σ reservas − Σ retiradas das metas não excluídas
--   disponível   = saldo total − reservado
--   Reservar não cria despesa; retirar não cria receita; a reserva de uma meta nunca fica negativa.
--   Concluir: status 'concluida'; o valor continua reservado até ser retirado (nenhuma despesa é criada).
--   Excluir: status 'excluida' (histórico preservado); a reserva deixa de contar e volta ao disponível.
-- Toda escrita de reserva passa por RPC SECURITY DEFINER que trava a conta (FOR UPDATE no perfil),
-- recalcula saldo e reservado na mesma transação e recusa valor acima do disponível.

create table public.goals (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  title        text not null check (char_length(title) between 1 and 100),
  description  text check (char_length(description) <= 600),
  target_cents bigint not null check (target_cents > 0 and target_cents <= 100000000000),
  deadline     date not null,
  status       text not null default 'ativa' check (status in ('ativa', 'concluida', 'excluida')),
  completed_at timestamptz,
  deleted_at   timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint goals_id_user_uk unique (id, user_id),
  constraint goals_status_dates check (
    (status = 'concluida') = (completed_at is not null) or status = 'excluida')
);
create index goals_user_status_deadline_idx on public.goals (user_id, status, deadline);
create trigger goals_touch before update on public.goals for each row execute function private.touch_updated_at();

create or replace function private.goals_guard()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.title := private.clean_text(new.title);
  if new.title is null then perform private.http_error(422, 'Confira os campos: título.'); end if;
  if tg_op = 'INSERT' then
    if new.deadline < private.today_br() then perform private.http_error(422, 'O prazo precisa ser hoje ou uma data futura.'); end if;
  else
    if new.user_id <> old.user_id then perform private.http_error(422, 'Não é possível mudar o dono da meta.'); end if;
    if new.deadline <> old.deadline and new.deadline < private.today_br() then
      perform private.http_error(422, 'O novo prazo precisa ser hoje ou uma data futura.');
    end if;
  end if;
  return new;
end $$;
create trigger goals_guard before insert or update on public.goals for each row execute function private.goals_guard();

create table public.goal_reservation_events (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null,
  goal_id         uuid not null,
  kind            text not null check (kind in ('reserva', 'retirada')),
  amount_cents    bigint not null check (amount_cents > 0 and amount_cents <= 100000000000),
  idempotency_key text check (char_length(idempotency_key) between 8 and 100),
  created_at      timestamptz not null default now(),
  -- Meta e evento da MESMA conta: a FK composta prova a titularidade.
  constraint goal_events_goal_owner_fk foreign key (goal_id, user_id) references public.goals (id, user_id) on delete cascade,
  constraint goal_events_idempotency_uk unique (user_id, idempotency_key)
);
create index goal_events_goal_idx on public.goal_reservation_events (goal_id, user_id);
create index goal_events_user_idx on public.goal_reservation_events (user_id, goal_id);

-- Eventos são imutáveis (auditoria): nem o dono altera ou apaga.
create or replace function private.goal_events_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception 'Eventos de reserva são imutáveis.' using errcode = '42501';
end $$;
create trigger goal_events_no_update before update on public.goal_reservation_events
  for each row execute function private.goal_events_immutable();

create or replace function private.reserved_cents(p_user uuid, p_goal uuid default null)
returns bigint language sql stable security definer set search_path = '' as $$
  select coalesce(sum(case when e.kind = 'reserva' then e.amount_cents else -e.amount_cents end), 0)::bigint
    from public.goal_reservation_events e
    join public.goals g on g.id = e.goal_id and g.user_id = e.user_id
   where e.user_id = p_user and g.status <> 'excluida' and (p_goal is null or e.goal_id = p_goal)
$$;

create or replace function private.balance_of(p_user uuid)
returns bigint language sql stable security definer set search_path = '' as $$
  select coalesce(sum(case when type = 'receita' then amount_cents else -amount_cents end), 0)::bigint
    from public.transactions where user_id = p_user and occurred_on <= private.today_br()
$$;

create or replace function private.goal_move(p_goal_id uuid, p_kind text, p_amount_cents bigint, p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_uid();
  v_goal public.goals;
  v_prev public.goal_reservation_events;
  v_balance bigint; v_reserved bigint;
begin
  perform private.validate_money(p_amount_cents);
  -- Serializa TODAS as operações de reserva/retirada da mesma conta.
  perform 1 from public.profiles where id = v_uid for update;

  if p_idempotency_key is not null then
    select * into v_prev from public.goal_reservation_events where user_id = v_uid and idempotency_key = p_idempotency_key;
    if found then
      if v_prev.goal_id <> p_goal_id or v_prev.kind <> p_kind or v_prev.amount_cents <> p_amount_cents then
        perform private.http_error(409, 'Esta tentativa já foi usada para outra operação.');
      end if;
      return jsonb_build_object('status', 'ok', 'duplicate', true, 'event_id', v_prev.id);
    end if;
  end if;

  select * into v_goal from public.goals where id = p_goal_id and user_id = v_uid for update;
  if not found then perform private.http_error(404, 'Registro não encontrado.'); end if;

  if p_kind = 'reserva' then
    if v_goal.status <> 'ativa' then perform private.http_error(422, 'A meta precisa estar ativa para receber reservas.'); end if;
    v_balance := private.balance_of(v_uid);
    v_reserved := private.reserved_cents(v_uid);
    if p_amount_cents > v_balance - v_reserved then perform private.http_error(422, 'O valor excede seu saldo disponível.'); end if;
  elsif p_kind = 'retirada' then
    if v_goal.status = 'excluida' then perform private.http_error(422, 'A meta não está disponível para retirada.'); end if;
    if p_amount_cents > private.reserved_cents(v_uid, p_goal_id) then
      perform private.http_error(422, 'A retirada não pode ser maior que a reserva atual.');
    end if;
  else
    perform private.http_error(422, 'Operação inválida.');
  end if;

  insert into public.goal_reservation_events (user_id, goal_id, kind, amount_cents, idempotency_key)
  values (v_uid, p_goal_id, p_kind, p_amount_cents, p_idempotency_key)
  returning * into v_prev;
  return jsonb_build_object('status', 'ok', 'duplicate', false, 'event_id', v_prev.id);
end $$;

create or replace function private.goal_complete(p_goal_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid();
begin
  update public.goals set status = 'concluida', completed_at = now()
   where id = p_goal_id and user_id = v_uid and status = 'ativa';
  if not found then perform private.http_error(422, 'A meta já foi concluída ou não está disponível.'); end if;
  return jsonb_build_object('status', 'ok', 'message',
    'Meta concluída. O valor reservado continua separado até você retirá-lo; nenhuma despesa foi criada.');
end $$;

create or replace function private.goal_delete(p_goal_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid();
begin
  perform 1 from public.profiles where id = v_uid for update;
  update public.goals set status = 'excluida', deleted_at = now()
   where id = p_goal_id and user_id = v_uid and status <> 'excluida';
  if not found then perform private.http_error(404, 'Registro não encontrado.'); end if;
  return jsonb_build_object('status', 'ok', 'message', 'A reserva foi liberada para o saldo disponível; o saldo total não mudou.');
end $$;

create or replace function public.reserve_goal(p_goal_id uuid, p_amount_cents bigint, p_idempotency_key text default null)
returns jsonb language sql security invoker set search_path = '' as $$ select private.goal_move(p_goal_id, 'reserva', p_amount_cents, p_idempotency_key) $$;
create or replace function public.withdraw_goal(p_goal_id uuid, p_amount_cents bigint, p_idempotency_key text default null)
returns jsonb language sql security invoker set search_path = '' as $$ select private.goal_move(p_goal_id, 'retirada', p_amount_cents, p_idempotency_key) $$;
create or replace function public.complete_goal(p_goal_id uuid)
returns jsonb language sql security invoker set search_path = '' as $$ select private.goal_complete(p_goal_id) $$;
create or replace function public.delete_goal(p_goal_id uuid)
returns jsonb language sql security invoker set search_path = '' as $$ select private.goal_delete(p_goal_id) $$;

-- Sempre da conta autenticada: balance_of/reserved_cents (que aceitam qualquer conta) NÃO têm GRANT para authenticated.
create or replace function private.my_balance_summary()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_bal bigint; v_res bigint;
begin
  v_bal := private.balance_of(v_uid); v_res := private.reserved_cents(v_uid);
  return jsonb_build_object('balance_total', v_bal, 'reserved', v_res, 'available', v_bal - v_res);
end $$;
create or replace function public.balance_summary()
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.my_balance_summary() $$;

-- Visão com o estado exibido (concluída, pronta, vencida, ativa). security_invoker: respeita o RLS do chamador.
create view public.goal_overview with (security_invoker = true) as
select g.id, g.user_id, g.title, g.description, g.target_cents, g.deadline, g.status, g.completed_at, g.created_at, g.updated_at,
       r.reserved_cents,
       greatest(0, g.target_cents - r.reserved_cents) as remaining_cents,
       least(100, (r.reserved_cents * 100) / g.target_cents)::int as percent,
       (g.deadline - private.today_br()) as days_left,
       case when g.status = 'concluida' then 'concluida'
            when r.reserved_cents >= g.target_cents then 'pronta'
            when g.deadline < private.today_br() then 'vencida'
            else 'ativa' end as state
  from public.goals g
  cross join lateral (
    select coalesce(sum(case when e.kind = 'reserva' then e.amount_cents else -e.amount_cents end), 0)::bigint as reserved_cents
      from public.goal_reservation_events e where e.goal_id = g.id and e.user_id = g.user_id) r
 where g.status <> 'excluida';

-- ===== Privilégios =====
alter table public.goals enable row level security;
alter table public.goal_reservation_events enable row level security;
revoke all on public.goals, public.goal_reservation_events, public.goal_overview from anon, authenticated;
grant select on public.goals to authenticated;
grant insert (user_id, title, description, target_cents, deadline) on public.goals to authenticated;
grant update (title, description, target_cents, deadline) on public.goals to authenticated;  -- status só por RPC
grant select on public.goal_reservation_events to authenticated;                              -- escrita só por RPC
grant select on public.goal_overview to authenticated;
grant all on public.goals, public.goal_reservation_events to service_role;
grant select on public.goal_overview to service_role;

create policy goals_select_own on public.goals for select to authenticated using (user_id = (select auth.uid()));
create policy goals_insert_own on public.goals for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'ativa');
create policy goals_update_own_active on public.goals for update to authenticated
  using (user_id = (select auth.uid()) and status = 'ativa')
  with check (user_id = (select auth.uid()) and status = 'ativa');
create policy goal_events_select_own on public.goal_reservation_events for select to authenticated
  using (user_id = (select auth.uid()));

revoke all on function private.goals_guard(), private.goal_events_immutable(), private.reserved_cents(uuid, uuid),
  private.balance_of(uuid), private.goal_move(uuid, text, bigint, text), private.goal_complete(uuid), private.goal_delete(uuid) from public, anon;
revoke all on function private.my_balance_summary() from public, anon;
grant execute on function private.goal_move(uuid, text, bigint, text), private.goal_complete(uuid), private.goal_delete(uuid),
  private.my_balance_summary() to authenticated;
grant execute on function private.reserved_cents(uuid, uuid), private.balance_of(uuid) to service_role;
revoke all on function public.reserve_goal(uuid, bigint, text), public.withdraw_goal(uuid, bigint, text),
  public.complete_goal(uuid), public.delete_goal(uuid), public.balance_summary() from public, anon;
grant execute on function public.reserve_goal(uuid, bigint, text), public.withdraw_goal(uuid, bigint, text),
  public.complete_goal(uuid), public.delete_goal(uuid), public.balance_summary() to authenticated;
