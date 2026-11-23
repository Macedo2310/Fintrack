-- FinTrack · 0003 · Categorias, recorrências, transações, saldo e dashboard.
-- Dinheiro sempre em bigint (centavos). Datas financeiras em date. "Hoje" = America/Sao_Paulo.
-- Escolha CHECK x ENUM: usamos CHECK em text para tipos/estados. Acrescentar um valor em CHECK é um
-- ALTER simples e transacional; ENUM não permite remover valores e complica migrações futuras.

create table public.categories (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references public.profiles (id) on delete cascade,  -- NULL = categoria global
  type       text not null check (type in ('receita', 'despesa')),
  name       text not null check (char_length(name) between 2 and 50),
  position   int  not null default 100,
  active     boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint categories_id_type_uk unique (id, type)   -- alvo da FK composta (categoria x tipo)
);
-- Sem duplicar por caixa/espaços, nem entre as globais nem dentro da mesma conta.
create unique index categories_unique_name_idx on public.categories
  (coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid), type, lower(name));
create index categories_user_idx on public.categories (user_id, type) where user_id is not null;
create trigger categories_touch before update on public.categories for each row execute function private.touch_updated_at();

create or replace function private.categories_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  new.name := private.clean_text(new.name);
  if tg_op = 'UPDATE' and (new.user_id is distinct from old.user_id or new.type <> old.type) then
    perform private.http_error(422, 'Não é possível mudar o dono ou o tipo da categoria.');
  end if;
  if new.user_id is not null and exists (
      select 1 from public.categories g where g.user_id is null and g.type = new.type and lower(g.name) = lower(new.name)) then
    perform private.http_error(409, 'Essa categoria já existe.');
  end if;
  return new;
end $$;
create trigger categories_guard before insert or update on public.categories
  for each row execute function private.categories_guard();

-- Categorias iniciais (globais, dado real do produto).
insert into public.categories (user_id, type, name, position) values
  (null, 'receita', 'Mesada', 1), (null, 'receita', 'Salário', 2), (null, 'receita', 'Bolsa', 3),
  (null, 'receita', 'Trabalho eventual', 4), (null, 'receita', 'Vendas', 5), (null, 'receita', 'Presentes', 6),
  (null, 'receita', 'Outros', 99),
  (null, 'despesa', 'Alimentação', 1), (null, 'despesa', 'Transporte', 2), (null, 'despesa', 'Lazer', 3),
  (null, 'despesa', 'Contas', 4), (null, 'despesa', 'Saúde', 5), (null, 'despesa', 'Educação', 6),
  (null, 'despesa', 'Compras', 7), (null, 'despesa', 'Assinaturas', 8), (null, 'despesa', 'Outros', 99)
on conflict do nothing;

-- A categoria precisa ser global ou da MESMA conta. O tipo já é garantido pela FK composta.
create or replace function private.category_belongs_to_owner()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_owner uuid; v_found boolean;
begin
  select true, c.user_id into v_found, v_owner from public.categories c where c.id = new.category_id;
  if v_found is null or (v_owner is not null and v_owner <> new.user_id) then
    perform private.http_error(422, 'Categoria incompatível com o tipo selecionado.');
  end if;
  return new;
end $$;

create table public.recurrences (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  type         text not null check (type in ('receita', 'despesa')),
  category_id  uuid not null,
  description  text not null check (char_length(description) between 1 and 160),
  amount_cents bigint not null check (amount_cents > 0 and amount_cents <= 100000000000),
  frequency    text not null check (frequency in ('semanal', 'mensal', 'anual')),
  start_date   date not null,
  next_date    date not null,
  end_date     date,
  anchor_day   smallint not null check (anchor_day between 1 and 31),
  anchor_month smallint not null check (anchor_month between 1 and 12),
  note         text check (char_length(note) <= 1000),
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint recurrences_end_after_start check (end_date is null or end_date >= start_date),
  constraint recurrences_next_after_start check (next_date > start_date),
  constraint recurrences_id_user_uk unique (id, user_id),
  constraint recurrences_category_fk foreign key (category_id, type) references public.categories (id, type) on delete restrict
);
create index recurrences_due_idx on public.recurrences (next_date) where active;
create index recurrences_user_idx on public.recurrences (user_id);
create index recurrences_category_idx on public.recurrences (category_id);
create trigger recurrences_touch before update on public.recurrences for each row execute function private.touch_updated_at();
create trigger recurrences_category_owner before insert or update of category_id, user_id on public.recurrences
  for each row execute function private.category_belongs_to_owner();

create table public.transactions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  type          text not null check (type in ('receita', 'despesa')),
  category_id   uuid not null,
  description   text not null check (char_length(description) between 1 and 160),
  amount_cents  bigint not null check (amount_cents > 0 and amount_cents <= 100000000000),
  occurred_on   date not null,
  note          text check (char_length(note) <= 1000),
  recurrence_id uuid,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint transactions_category_fk foreign key (category_id, type) references public.categories (id, type) on delete restrict,
  -- A recorrência precisa ser da mesma conta. Apagar a recorrência mantém os lançamentos (só solta o vínculo).
  constraint transactions_recurrence_fk foreign key (recurrence_id, user_id)
    references public.recurrences (id, user_id) on delete set null (recurrence_id)
);
-- Anti-duplicidade do job de recorrências.
create unique index transactions_recurrence_occurrence_uk on public.transactions (recurrence_id, occurred_on)
  where recurrence_id is not null;
-- Listagem paginada, saldo até hoje, resumo por período e gráfico de 6 meses.
create index transactions_user_date_idx on public.transactions (user_id, occurred_on desc, created_at desc);
-- Filtro por tipo e agregações por tipo/categoria.
create index transactions_user_type_date_idx on public.transactions (user_id, type, occurred_on);
-- FK de categoria (RESTRICT ao apagar categoria personalizada).
create index transactions_category_idx on public.transactions (category_id);
create trigger transactions_touch before update on public.transactions for each row execute function private.touch_updated_at();
create trigger transactions_category_owner before insert or update of category_id, user_id on public.transactions
  for each row execute function private.category_belongs_to_owner();

create or replace function private.transactions_guard()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.description := private.clean_text(new.description);
  if new.description is null then perform private.http_error(422, 'Confira os campos: descrição.'); end if;
  if tg_op = 'UPDATE' and new.user_id <> old.user_id then perform private.http_error(422, 'Não é possível mudar o dono do lançamento.'); end if;
  return new;
end $$;
create trigger transactions_guard before insert or update on public.transactions
  for each row execute function private.transactions_guard();

-- ===== Recorrência =====
create or replace function private.next_occurrence(p_date date, p_frequency text, p_day int, p_month int)
returns date language plpgsql immutable set search_path = '' as $$
declare y int; m int; last_day int;
begin
  if p_frequency = 'semanal' then return p_date + 7; end if;
  if p_frequency = 'mensal' then
    y := extract(year from p_date); m := extract(month from p_date) + 1;
    if m = 13 then y := y + 1; m := 1; end if;
  else
    y := extract(year from p_date) + 1; m := p_month;
  end if;
  last_day := extract(day from (make_date(y, m, 1) + interval '1 month - 1 day'));
  return make_date(y, m, least(p_day, last_day));
end $$;

-- Job idempotente: gera ocorrências vencidas. SKIP LOCKED evita que duas execuções processem
-- a mesma recorrência; o índice único impede duplicata mesmo assim.
create or replace function private.generate_due_recurrences(p_recurrence uuid default null)
returns int language plpgsql security definer set search_path = '' as $$
declare r public.recurrences; d date; t date := private.today_br(); n int := 0; k int;
begin
  for r in select * from public.recurrences
            where active and next_date <= t and (p_recurrence is null or id = p_recurrence)
            for update skip locked loop
    d := r.next_date;
    while d <= t and (r.end_date is null or d <= r.end_date) loop
      insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on, note, recurrence_id)
      values (r.user_id, r.type, r.category_id, r.description, r.amount_cents, d, r.note, r.id)
      on conflict (recurrence_id, occurred_on) where recurrence_id is not null do nothing;
      get diagnostics k = row_count; n := n + k;
      d := private.next_occurrence(d, r.frequency, r.anchor_day, r.anchor_month);
    end loop;
    update public.recurrences
       set next_date = d, active = not (r.end_date is not null and d > r.end_date)
     where id = r.id;
  end loop;
  return n;
end $$;

create or replace function private.validate_money(p_cents bigint)
returns bigint language plpgsql stable security definer set search_path = '' as $$
begin
  if p_cents is null or p_cents <= 0 then perform private.http_error(422, 'O valor deve ser maior que zero.'); end if;
  if p_cents > (private.setting('max_money_cents'))::bigint then perform private.http_error(422, 'O valor informado excede o limite permitido.'); end if;
  return p_cents;
end $$;

-- Criar lançamento recorrente: recorrência + 1ª ocorrência + ocorrências já vencidas (início no passado).
create or replace function private.create_recurring_transaction(
  p_type text, p_category_id uuid, p_description text, p_amount_cents bigint, p_start_date date,
  p_frequency text, p_end_date date, p_note text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_rec uuid; v_tx uuid;
begin
  perform private.validate_money(p_amount_cents);
  if p_frequency is null or p_frequency not in ('semanal', 'mensal', 'anual') then perform private.http_error(422, 'Frequência inválida.'); end if;
  if p_start_date is null then perform private.http_error(422, 'Data inválida.'); end if;
  if p_end_date is not null and p_end_date < p_start_date then
    perform private.http_error(422, 'A data de encerramento não pode ser anterior ao início.');
  end if;
  if coalesce(p_end_date, p_start_date) > private.today_br() + 366 * 5 then
    perform private.http_error(422, 'Use datas de até cinco anos à frente.');
  end if;
  insert into public.recurrences (user_id, type, category_id, description, amount_cents, frequency, start_date, next_date,
                                  end_date, anchor_day, anchor_month, note)
  values (v_uid, p_type, p_category_id, private.clean_text(p_description), p_amount_cents, p_frequency, p_start_date,
          private.next_occurrence(p_start_date, p_frequency, extract(day from p_start_date)::int, extract(month from p_start_date)::int),
          p_end_date, extract(day from p_start_date), extract(month from p_start_date), p_note)
  returning id into v_rec;
  insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on, note, recurrence_id)
  values (v_uid, p_type, p_category_id, p_description, p_amount_cents, p_start_date, p_note, v_rec)
  returning id into v_tx;
  perform private.generate_due_recurrences(v_rec);
  return v_tx;
end $$;

-- Editar "esta e as próximas": muda o modelo da recorrência e as ocorrências desta data em diante.
-- O histórico anterior não é tocado. A data da ocorrência escolhida pode mudar; as demais mantêm as suas.
create or replace function private.update_transaction_scoped(
  p_transaction_id uuid, p_scope text, p_type text, p_category_id uuid, p_description text,
  p_amount_cents bigint, p_occurred_on date, p_note text)
returns int language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_row public.transactions; n int := 0;
begin
  if p_scope not in ('single', 'future') then perform private.http_error(422, 'Escopo inválido.'); end if;
  perform private.validate_money(p_amount_cents);
  select * into v_row from public.transactions where id = p_transaction_id and user_id = v_uid for update;
  if not found then perform private.http_error(404, 'Registro não encontrado.'); end if;
  update public.transactions
     set type = p_type, category_id = p_category_id, description = p_description, amount_cents = p_amount_cents,
         occurred_on = p_occurred_on, note = p_note
   where id = p_transaction_id;
  n := 1;
  if p_scope = 'future' and v_row.recurrence_id is not null then
    update public.recurrences
       set type = p_type, category_id = p_category_id, description = private.clean_text(p_description),
           amount_cents = p_amount_cents, note = p_note
     where id = v_row.recurrence_id and user_id = v_uid;
    update public.transactions
       set type = p_type, category_id = p_category_id, description = p_description, amount_cents = p_amount_cents, note = p_note
     where recurrence_id = v_row.recurrence_id and user_id = v_uid and occurred_on >= v_row.occurred_on and id <> p_transaction_id;
    get diagnostics n = row_count; n := n + 1;
  end if;
  return n;
end $$;

-- Excluir "só esta" ou "esta e as próximas" (encerra a recorrência).
create or replace function private.delete_transaction_scoped(p_transaction_id uuid, p_scope text)
returns int language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_row public.transactions; n int;
begin
  if p_scope not in ('single', 'future') then perform private.http_error(422, 'Escopo inválido.'); end if;
  select * into v_row from public.transactions where id = p_transaction_id and user_id = v_uid for update;
  if not found then perform private.http_error(404, 'Registro não encontrado.'); end if;
  if p_scope = 'future' and v_row.recurrence_id is not null then
    update public.recurrences set active = false where id = v_row.recurrence_id and user_id = v_uid;
    delete from public.transactions
     where recurrence_id = v_row.recurrence_id and user_id = v_uid and occurred_on >= v_row.occurred_on;
  else
    delete from public.transactions where id = p_transaction_id and user_id = v_uid;
  end if;
  get diagnostics n = row_count;
  return n;
end $$;

-- ===== Wrappers públicos (SECURITY INVOKER; a lógica privilegiada fica em private) =====
create or replace function public.create_recurring_transaction(
  p_type text, p_category_id uuid, p_description text, p_amount_cents bigint, p_start_date date,
  p_frequency text, p_end_date date default null, p_note text default null)
returns uuid language sql security invoker set search_path = '' as $$
  select private.create_recurring_transaction(p_type, p_category_id, p_description, p_amount_cents, p_start_date, p_frequency, p_end_date, p_note)
$$;
create or replace function public.update_transaction_scoped(
  p_transaction_id uuid, p_scope text, p_type text, p_category_id uuid, p_description text,
  p_amount_cents bigint, p_occurred_on date, p_note text default null)
returns int language sql security invoker set search_path = '' as $$
  select private.update_transaction_scoped(p_transaction_id, p_scope, p_type, p_category_id, p_description, p_amount_cents, p_occurred_on, p_note)
$$;
create or replace function public.delete_transaction_scoped(p_transaction_id uuid, p_scope text default 'single')
returns int language sql security invoker set search_path = '' as $$
  select private.delete_transaction_scoped(p_transaction_id, p_scope)
$$;

-- Saldo: SECURITY INVOKER, filtra pela conta autenticada (e o RLS também filtra).
create or replace function public.balance_cents()
returns bigint language sql stable security invoker set search_path = '' as $$
  select coalesce(sum(case when type = 'receita' then amount_cents else -amount_cents end), 0)::bigint
    from public.transactions
   where user_id = (select auth.uid()) and occurred_on <= private.today_br()
$$;

-- ===== Privilégios =====
alter table public.categories enable row level security;
alter table public.recurrences enable row level security;
alter table public.transactions enable row level security;
revoke all on public.categories, public.recurrences, public.transactions from anon, authenticated;

grant select, delete on public.categories to authenticated;
grant insert (type, name, user_id) on public.categories to authenticated;
grant update (name, active, position) on public.categories to authenticated;
grant select on public.recurrences to authenticated;          -- escrita só por RPC
grant select, delete on public.transactions to authenticated;
-- recurrence_id NÃO entra: o cliente não vincula lançamentos a recorrências.
grant insert (user_id, type, category_id, description, amount_cents, occurred_on, note) on public.transactions to authenticated;
grant update (type, category_id, description, amount_cents, occurred_on, note) on public.transactions to authenticated;
grant all on public.categories, public.recurrences, public.transactions to service_role;

create policy categories_select on public.categories for select to authenticated
  using (user_id is null or user_id = (select auth.uid()));
create policy categories_insert_own on public.categories for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy categories_update_own on public.categories for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy categories_delete_own on public.categories for delete to authenticated
  using (user_id = (select auth.uid()));  -- FK RESTRICT impede apagar categoria em uso

create policy recurrences_select_own on public.recurrences for select to authenticated
  using (user_id = (select auth.uid()));

create policy transactions_select_own on public.transactions for select to authenticated
  using (user_id = (select auth.uid()));
create policy transactions_insert_own on public.transactions for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy transactions_update_own on public.transactions for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy transactions_delete_own on public.transactions for delete to authenticated
  using (user_id = (select auth.uid()));

revoke all on function private.categories_guard(), private.category_belongs_to_owner(), private.transactions_guard(),
  private.next_occurrence(date, text, int, int), private.generate_due_recurrences(uuid), private.validate_money(bigint),
  private.create_recurring_transaction(text, uuid, text, bigint, date, text, date, text),
  private.update_transaction_scoped(uuid, text, text, uuid, text, bigint, date, text),
  private.delete_transaction_scoped(uuid, text) from public, anon;
grant execute on function private.create_recurring_transaction(text, uuid, text, bigint, date, text, date, text),
  private.update_transaction_scoped(uuid, text, text, uuid, text, bigint, date, text),
  private.delete_transaction_scoped(uuid, text), private.next_occurrence(date, text, int, int) to authenticated;
grant execute on function private.generate_due_recurrences(uuid) to service_role;
revoke all on function public.create_recurring_transaction(text, uuid, text, bigint, date, text, date, text),
  public.update_transaction_scoped(uuid, text, text, uuid, text, bigint, date, text),
  public.delete_transaction_scoped(uuid, text), public.balance_cents() from public, anon;
grant execute on function public.create_recurring_transaction(text, uuid, text, bigint, date, text, date, text),
  public.update_transaction_scoped(uuid, text, text, uuid, text, bigint, date, text),
  public.delete_transaction_scoped(uuid, text), public.balance_cents() to authenticated;
