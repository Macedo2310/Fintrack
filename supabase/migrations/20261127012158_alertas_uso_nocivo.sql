-- Avisos de uso nocivo:
--   bem-estar (wellbeing): gastos com apostas e gastos fora de controle (disparam ao registrar o gasto);
--   segurança (security): linguagem ofensiva bloqueada repetidamente (registrada pelo servidor).
-- Cada aviso tem chave por período (semana/dia/mês), então não se repete em excesso.

alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications drop constraint if exists notifications_destination_check;
alter table public.notifications
  add constraint notifications_kind_check check (kind in ('goal', 'lesson', 'spending', 'wellbeing', 'security')),
  add constraint notifications_destination_check check (destination in ('goals', 'education', 'classes', 'transactions', 'finbot'));

create or replace function private.notify(p_user uuid, p_key text, p_kind text, p_title text, p_body text, p_dest text)
returns void language sql security definer set search_path = '' as $$
  insert into public.notifications (user_id, event_key, kind, title, body, destination)
  values (p_user, left(p_key, 200), p_kind, left(p_title, 120), left(p_body, 500), p_dest)
  on conflict (user_id, event_key) do nothing
$$;

-- Termos comuns de apostas e jogos de azar (palavra inteira, sem acento/maiúscula).
create or replace function private.is_gambling(p_text text)
returns boolean language sql immutable set search_path = '' as $$
  select coalesce(lower(translate(p_text, 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc')) ~
    '\m(bet|bets|aposta|apostas|apostei|apostar|cassino|casino|blaze|tigrinho|fortune ?tiger|roleta|betano|bet365|sportingbet|pixbet|estrela ?bet|esportes da sorte|superbet|novibet|f12 ?bet|betnacional|jogo do bicho|caca ?niquel|bingo)\M', false)
$$;

create or replace function private.wellbeing_check()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  v_cat text; v_week text := to_char(private.today_br(), 'IYYY-IW'); v_day text := to_char(private.today_br(), 'YYYY-MM-DD');
  v_month text := to_char(private.today_br(), 'YYYY-MM'); v_spending boolean;
  v_bets bigint; v_income bigint; v_burst int; v_last7 bigint; v_prev bigint; v_weeks int; v_balance bigint;
begin
  if new.type <> 'despesa' then return null; end if;
  select name into v_cat from public.categories where id = new.category_id;

  -- 1) Apostas: sempre avisa (proteção), no máximo uma vez por semana; mais forte se pesar no mês.
  if private.is_gambling(new.description) or private.is_gambling(v_cat) or private.is_gambling(new.note) then
    perform private.notify(new.user_id, 'bet:' || v_week, 'wellbeing', 'Cuidado com as apostas',
      'Você registrou um gasto que parece ser com apostas. Apostas não são uma forma de ganhar dinheiro: no longo prazo, quem aposta tende a perder. '
      || 'Se estiver difícil parar, você não está sozinho: procure os Jogadores Anônimos ou converse com o CVV pelo 188 (ligação gratuita, 24 horas).', 'transactions');
    select coalesce(sum(t.amount_cents), 0) into v_bets from public.transactions t
      left join public.categories c on c.id = t.category_id
     where t.user_id = new.user_id and t.type = 'despesa' and t.occurred_on > private.today_br() - 30
       and (private.is_gambling(t.description) or private.is_gambling(c.name) or private.is_gambling(t.note));
    select coalesce(sum(amount_cents), 0) into v_income from public.transactions
     where user_id = new.user_id and type = 'receita' and occurred_on > private.today_br() - 30;
    if v_bets >= 5000 and (v_income = 0 or v_bets * 10 >= v_income) then
      perform private.notify(new.user_id, 'bet-heavy:' || v_month, 'wellbeing', 'As apostas estão pesando no seu orçamento',
        'Nos últimos 30 dias, os gastos com apostas somaram R$ ' || replace(to_char(v_bets / 100.0, 'FM999G999G990D00'), '.', ',')
        || case when v_income > 0 then ', cerca de ' || round(v_bets * 100.0 / v_income) || '% do que entrou.' else '.' end
        || ' Que tal definir um limite ou dar uma pausa? Jogadores Anônimos e o CVV (188) podem ajudar.', 'transactions');
    end if;
  end if;

  -- Os demais avisos respeitam a preferência "gastos" dos lembretes.
  select coalesce(spending, true) into v_spending from public.reminder_preferences where user_id = new.user_id;
  if not coalesce(v_spending, true) or new.recurrence_id is not null then return null; end if;

  -- 2) Muitos gastos em pouco tempo (possível impulso): 8+ despesas registradas em 24 horas.
  select count(*) into v_burst from public.transactions
   where user_id = new.user_id and type = 'despesa' and recurrence_id is null and created_at > now() - interval '24 hours';
  if v_burst >= 8 then
    perform private.notify(new.user_id, 'burst:' || v_day, 'wellbeing', 'Muitos gastos em pouco tempo',
      'Você registrou ' || v_burst || ' despesas nas últimas 24 horas. Antes da próxima compra, vale esperar um pouco e perguntar: eu preciso disso agora?', 'transactions');
  end if;

  -- 3) Gastos da semana bem acima do seu normal (comparado às 8 semanas anteriores).
  select coalesce(sum(amount_cents) filter (where occurred_on > private.today_br() - 7), 0),
         coalesce(sum(amount_cents) filter (where occurred_on <= private.today_br() - 7 and occurred_on > private.today_br() - 63), 0),
         count(distinct date_trunc('week', occurred_on)) filter (where occurred_on <= private.today_br() - 7 and occurred_on > private.today_br() - 63)
    into v_last7, v_prev, v_weeks
    from public.transactions where user_id = new.user_id and type = 'despesa' and occurred_on > private.today_br() - 63;
  if v_weeks >= 3 and v_prev > 0 and v_last7 * 80 > v_prev * 18 and v_last7 - v_prev / 8 >= 10000 then   -- > 1,8x a média e +R$ 100
    perform private.notify(new.user_id, 'spike:' || v_week, 'wellbeing', 'Seus gastos dispararam nesta semana',
      'Nos últimos 7 dias você gastou R$ ' || replace(to_char(v_last7 / 100.0, 'FM999G999G990D00'), '.', ',')
      || ', bem acima da sua média semanal (R$ ' || replace(to_char(v_prev / 8 / 100.0, 'FM999G999G990D00'), '.', ',') || '). Confira para onde o dinheiro foi.', 'transactions');
  end if;

  -- 4) Saldo total negativo (gastou mais do que entrou, somando tudo até hoje).
  select coalesce(sum(case when type = 'receita' then amount_cents else -amount_cents end), 0) into v_balance
    from public.transactions where user_id = new.user_id and occurred_on <= private.today_br();
  if v_balance < 0 then
    perform private.notify(new.user_id, 'negative:' || v_month, 'wellbeing', 'Seu saldo ficou negativo',
      'Somando tudo o que você registrou, as despesas passaram das receitas em R$ ' || replace(to_char(-v_balance / 100.0, 'FM999G999G990D00'), '.', ',')
      || '. Isso costuma virar dívida. Revise os gastos não essenciais e, se precisar, peça ajuda ao FinBot para montar um plano.', 'transactions');
  end if;
  return null;
end $$;

create trigger transactions_wellbeing after insert on public.transactions
  for each row execute function private.wellbeing_check();

-- Uso abusivo: o servidor registra cada conteúdo bloqueado; repetições geram aviso na conta.
create table private.abuse_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  kind text not null check (char_length(kind) <= 40),
  created_at timestamptz not null default now()
);
create index abuse_events_user_time on private.abuse_events (user_id, created_at desc);
alter table private.abuse_events enable row level security;
revoke all on private.abuse_events from public, anon, authenticated;

create or replace function private.report_abuse(p_kind text)
returns int language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v_n int; v_day text := to_char(private.today_br(), 'YYYY-MM-DD');
begin
  insert into private.abuse_events (user_id, kind) values (v_uid, left(coalesce(p_kind, 'outro'), 40));
  select count(*) into v_n from private.abuse_events where user_id = v_uid and created_at > now() - interval '24 hours';
  if v_n >= 3 then
    perform private.notify(v_uid, 'abuse:' || v_day, 'security', 'Conteúdo ofensivo bloqueado',
      'Algumas mensagens suas foram bloqueadas por linguagem ofensiva. O FinTrack é um espaço de aprendizado e respeito para todos.', 'finbot');
  end if;
  if v_n >= 6 then
    perform private.notify(v_uid, 'abuse-final:' || v_day, 'security', 'Aviso: uso inadequado da plataforma',
      'Você teve várias mensagens bloqueadas hoje. Se isso continuar, a conta pode ser suspensa conforme os Termos de Uso.', 'finbot');
  end if;
  delete from private.abuse_events where created_at < now() - interval '90 days';
  return v_n;
end $$;

create or replace function public.report_abuse(p_kind text)
returns int language sql security invoker set search_path = '' as $$ select private.report_abuse(p_kind) $$;

revoke all on function private.notify(uuid, text, text, text, text, text), private.wellbeing_check(), private.report_abuse(text) from public, anon, authenticated;
grant execute on function private.report_abuse(text) to authenticated;
revoke all on function public.report_abuse(text) from public, anon;
grant execute on function public.report_abuse(text) to authenticated;
