-- FinTrack · 0007 · Turmas, participantes, atividades atribuídas e resumo financeiro autorizado.
-- Professores NUNCA recebem SELECT em transactions, goals, receipts ou ai_messages dos alunos.
-- O resumo financeiro sai só pela RPC class_financial_summary, que confere a cada chamada:
-- professor dono da turma + vínculo atual + share_financial atual (revogar vale na hora, sem depender de JWT).
-- As funções is_class_teacher/is_class_member/shares_class são SECURITY DEFINER para evitar recursão
-- de RLS entre classes e class_memberships; ficam em private, com search_path fixo e auth.uid() interno.

create table public.classes (
  id          uuid primary key default gen_random_uuid(),
  teacher_id  uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name        text not null check (char_length(name) between 2 and 100),
  description text check (char_length(description) <= 500),
  join_code   text not null unique check (join_code ~ '^[0-9A-F]{6}$'),
  code_active boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint classes_id_teacher_uk unique (id, teacher_id)
);
create index classes_teacher_idx on public.classes (teacher_id, created_at desc);
create trigger classes_touch before update on public.classes for each row execute function private.touch_updated_at();

create table public.class_memberships (
  class_id        uuid not null references public.classes (id) on delete cascade,
  student_id      uuid not null references public.profiles (id) on delete cascade,
  share_financial boolean not null default false,
  joined_at       timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  primary key (class_id, student_id)
);
create index class_memberships_student_idx on public.class_memberships (student_id);
create trigger class_memberships_touch before update on public.class_memberships for each row execute function private.touch_updated_at();

create table public.assignments (
  id           uuid primary key default gen_random_uuid(),
  class_id     uuid not null,
  teacher_id   uuid not null default auth.uid(),
  lesson_id    uuid not null references public.education_lessons (id) on delete restrict,
  content_type text not null default 'aula' check (content_type in ('aula')),
  due_date     date,
  instructions text check (char_length(instructions) <= 1000),
  created_at   timestamptz not null default now(),
  constraint assignments_class_teacher_fk foreign key (class_id, teacher_id) references public.classes (id, teacher_id) on delete cascade,
  constraint assignments_id_class_uk unique (id, class_id)
);
create index assignments_class_idx on public.assignments (class_id, created_at desc);
create index assignments_teacher_idx on public.assignments (teacher_id, created_at desc);
create index assignments_lesson_idx on public.assignments (lesson_id);

create table public.assignment_progress (
  assignment_id uuid not null,
  class_id      uuid not null,
  student_id    uuid not null,
  status        text not null default 'pendente' check (status in ('pendente', 'concluida')),
  score         smallint check (score between 0 and 100),
  submitted_at  timestamptz,
  updated_at    timestamptz not null default now(),
  primary key (assignment_id, student_id),
  constraint assignment_progress_assignment_fk foreign key (assignment_id, class_id) references public.assignments (id, class_id) on delete cascade,
  -- Sair da turma remove as entregas daquela turma (mesmo comportamento da 0.6.x).
  constraint assignment_progress_membership_fk foreign key (class_id, student_id)
    references public.class_memberships (class_id, student_id) on delete cascade
);
create index assignment_progress_student_idx on public.assignment_progress (student_id, status);
create index assignment_progress_class_student_idx on public.assignment_progress (class_id, student_id);
create trigger assignment_progress_touch before update on public.assignment_progress for each row execute function private.touch_updated_at();

-- ===== Funções de apoio às políticas =====
create or replace function private.is_teacher()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles where id = (select auth.uid()) and role = 'professor')
$$;
create or replace function private.is_class_teacher(p_class_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.classes where id = p_class_id and teacher_id = (select auth.uid()))
$$;
create or replace function private.is_class_member(p_class_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.class_memberships where class_id = p_class_id and student_id = (select auth.uid()))
$$;
-- Professor e aluno da mesma turma (em qualquer direção) podem ver nome e avatar um do outro.
create or replace function private.shares_class(p_other uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.class_memberships m join public.classes c on c.id = m.class_id
                  where (c.teacher_id = (select auth.uid()) and m.student_id = p_other)
                     or (c.teacher_id = p_other and m.student_id = (select auth.uid())))
$$;

create or replace function private.new_join_code()
returns text language plpgsql volatile security definer set search_path = '' as $$
declare v text;
begin
  for i in 1 .. 20 loop
    v := upper(encode(extensions.gen_random_bytes(3), 'hex'));
    if not exists (select 1 from public.classes where join_code = v) then return v; end if;
  end loop;
  perform private.http_error(500, 'Não foi possível gerar o código.');
end $$;
alter table public.classes alter column join_code set default private.new_join_code();

create or replace function private.classes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  new.name := private.clean_text(new.name);
  if new.name is null then perform private.http_error(422, 'Confira os campos: nome.'); end if;
  if tg_op = 'INSERT' and not exists (select 1 from public.profiles where id = new.teacher_id and role = 'professor') then
    perform private.http_error(403, 'Apenas professores podem criar turmas.');
  end if;
  if tg_op = 'UPDATE' and new.teacher_id <> old.teacher_id then perform private.http_error(422, 'Não é possível mudar o professor da turma.'); end if;
  return new;
end $$;
create trigger classes_guard before insert or update on public.classes for each row execute function private.classes_guard();

-- Nova atividade: valida prazo e cria a pendência de cada aluno (aula já concluída conta como entregue).
create or replace function private.seed_assignment_progress(p_assignment_id uuid, p_class_id uuid, p_lesson_id uuid, p_student uuid)
returns void language sql security definer set search_path = '' as $$
  insert into public.assignment_progress (assignment_id, class_id, student_id, status, score, submitted_at)
  select p_assignment_id, p_class_id, p_student,
         case when e.status = 'concluida' then 'concluida' else 'pendente' end,
         case when e.status = 'concluida' then e.best_score end,
         case when e.status = 'concluida' then e.completed_at end
    from (select 1) one
    left join public.education_progress e on e.user_id = p_student and e.lesson_id = p_lesson_id
  on conflict do nothing
$$;

create or replace function private.assignments_before()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.due_date is not null and new.due_date < private.today_br() then
    perform private.http_error(422, 'O prazo precisa ser hoje ou uma data futura.');
  end if;
  if not exists (select 1 from public.education_lessons where id = new.lesson_id and status = 'publicado') then
    perform private.http_error(422, 'Escolha uma aula do curso.');
  end if;
  new.instructions := private.clean_text(new.instructions);
  return new;
end $$;
create trigger assignments_before before insert on public.assignments for each row execute function private.assignments_before();

create or replace function private.assignments_after()
returns trigger language plpgsql security definer set search_path = '' as $$
declare s uuid;
begin
  for s in select student_id from public.class_memberships where class_id = new.class_id loop
    perform private.seed_assignment_progress(new.id, new.class_id, new.lesson_id, s);
  end loop;
  return null;
end $$;
create trigger assignments_after after insert on public.assignments for each row execute function private.assignments_after();

-- ===== RPCs de turma =====
create or replace function private.class_by_code(p_code text)
returns public.classes language plpgsql stable security definer set search_path = '' as $$
declare c public.classes;
begin
  select * into c from public.classes where join_code = upper(btrim(coalesce(p_code, ''))) and code_active;
  if not found then perform private.http_error(404, 'Código inválido ou desativado.'); end if;
  return c;
end $$;

create or replace function private.require_student()
returns uuid language plpgsql stable security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid();
begin
  if not exists (select 1 from public.profiles where id = v_uid and role = 'aluno') then
    perform private.http_error(403, 'Fluxo disponível para alunos.');
  end if;
  return v_uid;
end $$;

create or replace function private.preview_class(p_code text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_student(); c public.classes;
begin
  perform private.hit_rate_limit('class-code:' || v_uid, 20, interval '10 minutes');
  c := private.class_by_code(p_code);
  return jsonb_build_object('class', jsonb_build_object('id', c.id, 'name', c.name, 'description', c.description,
           'teacher_name', (select name from public.profiles where id = c.teacher_id)),
         'already_member', exists (select 1 from public.class_memberships where class_id = c.id and student_id = v_uid));
end $$;

create or replace function private.join_class(p_code text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_student(); c public.classes; a record;
begin
  perform private.hit_rate_limit('class-join:' || v_uid, 10, interval '10 minutes');
  c := private.class_by_code(p_code);
  insert into public.class_memberships (class_id, student_id) values (c.id, v_uid) on conflict do nothing;
  if not found then perform private.http_error(409, 'Você já participa dessa turma.'); end if;
  for a in select id, lesson_id from public.assignments where class_id = c.id loop
    perform private.seed_assignment_progress(a.id, c.id, a.lesson_id, v_uid);
  end loop;
  return jsonb_build_object('status', 'ok', 'class_id', c.id);
end $$;

create or replace function private.renew_class_code(p_class_id uuid)
returns text language plpgsql security definer set search_path = '' as $$
declare v text;
begin
  perform private.require_uid();
  if not private.is_class_teacher(p_class_id) then perform private.http_error(404, 'Turma não encontrada.'); end if;
  v := private.new_join_code();
  update public.classes set join_code = v, code_active = true where id = p_class_id;
  return v;
end $$;

create or replace function private.class_participants(p_class_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.require_uid();
  if not private.is_class_teacher(p_class_id) then perform private.http_error(403, 'Sem permissão.'); end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
      'id', p.id, 'name', p.name, 'email', u.email, 'share_financial', m.share_financial, 'joined_at', m.joined_at,
      'avatar_kind', a.kind, 'avatar_preset', a.preset, 'avatar_bg', a.bg, 'avatar_v', a.updated_at) order by p.name)
    from public.class_memberships m
    join public.profiles p on p.id = m.student_id
    join auth.users u on u.id = m.student_id
    left join public.user_avatars a on a.user_id = m.student_id
   where m.class_id = p_class_id), '[]');
end $$;

-- Resumo financeiro autorizado: só totais do período, só de quem autorizou AGORA. Período máximo de 366 dias.
create or replace function private.class_financial_summary(p_class_id uuid, p_start date, p_end date)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_start date := coalesce(p_start, date_trunc('month', private.today_br())::date);
        v_end date := coalesce(p_end, private.today_br());
begin
  perform private.require_uid();
  if not private.is_class_teacher(p_class_id) then perform private.http_error(403, 'Sem permissão.'); end if;
  if v_start > v_end then perform private.http_error(422, 'A data inicial não pode ser posterior à final.'); end if;
  if v_end - v_start > 366 then perform private.http_error(422, 'Escolha um período de até 1 ano.'); end if;
  return jsonb_build_object('period', jsonb_build_object('start', v_start, 'end', v_end),
    'privacy', 'Somente alunos que autorizaram o compartilhamento desta turma.',
    'items', coalesce((select jsonb_agg(jsonb_build_object(
        'student_id', p.id, 'student_name', p.name, 'receitas', t.r, 'despesas', t.d, 'resultado', t.r - t.d, 'registros', t.n)
        order by p.name)
      from public.class_memberships m
      join public.profiles p on p.id = m.student_id
      cross join lateral (
        select coalesce(sum(amount_cents) filter (where type = 'receita'), 0)::bigint r,
               coalesce(sum(amount_cents) filter (where type = 'despesa'), 0)::bigint d, count(*)::int n
          from public.transactions x where x.user_id = m.student_id and x.occurred_on between v_start and v_end) t
     where m.class_id = p_class_id and m.share_financial), '[]'));
end $$;

create or replace function public.preview_class(p_code text)
returns jsonb language sql security invoker set search_path = '' as $$ select private.preview_class(p_code) $$;
create or replace function public.join_class(p_code text)
returns jsonb language sql security invoker set search_path = '' as $$ select private.join_class(p_code) $$;
create or replace function public.renew_class_code(p_class_id uuid)
returns text language sql security invoker set search_path = '' as $$ select private.renew_class_code(p_class_id) $$;
create or replace function public.class_participants(p_class_id uuid)
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.class_participants(p_class_id) $$;
create or replace function public.class_financial_summary(p_class_id uuid, p_start date default null, p_end date default null)
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.class_financial_summary(p_class_id, p_start, p_end) $$;

-- Visão das entregas com o estado "atrasada" calculado (security_invoker: RLS do chamador).
create view public.assignment_overview with (security_invoker = true) as
select ap.assignment_id, ap.class_id, ap.student_id, ap.status, ap.score, ap.submitted_at,
       a.lesson_id, a.due_date, a.instructions, a.created_at,
       case when ap.status = 'concluida' then 'concluida'
            when a.due_date is not null and a.due_date < private.today_br() then 'atrasada'
            else 'pendente' end as state
  from public.assignment_progress ap
  join public.assignments a on a.id = ap.assignment_id and a.class_id = ap.class_id;

-- ===== Privilégios =====
alter table public.classes enable row level security;
alter table public.class_memberships enable row level security;
alter table public.assignments enable row level security;
alter table public.assignment_progress enable row level security;
revoke all on public.classes, public.class_memberships, public.assignments, public.assignment_progress, public.assignment_overview from anon, authenticated;

grant select, delete on public.classes to authenticated;
grant insert (teacher_id, name, description) on public.classes to authenticated;
grant update (name, description, code_active) on public.classes to authenticated;   -- código novo só por RPC
grant select, delete on public.class_memberships to authenticated;                  -- entrar só por RPC
grant update (share_financial) on public.class_memberships to authenticated;
grant select, delete on public.assignments to authenticated;
grant insert (class_id, teacher_id, lesson_id, content_type, due_date, instructions) on public.assignments to authenticated;
grant select on public.assignment_progress to authenticated;                        -- escrita só por RPC/gatilho
grant select on public.assignment_overview to authenticated;
grant all on public.classes, public.class_memberships, public.assignments, public.assignment_progress to service_role;
grant select on public.assignment_overview to service_role;

create policy classes_select on public.classes for select to authenticated
  using (teacher_id = (select auth.uid()) or private.is_class_member(id));
create policy classes_insert_teacher on public.classes for insert to authenticated
  with check (teacher_id = (select auth.uid()) and private.is_teacher());
create policy classes_update_teacher on public.classes for update to authenticated
  using (teacher_id = (select auth.uid())) with check (teacher_id = (select auth.uid()));
create policy classes_delete_teacher on public.classes for delete to authenticated
  using (teacher_id = (select auth.uid()));

create policy memberships_select on public.class_memberships for select to authenticated
  using (student_id = (select auth.uid()) or private.is_class_teacher(class_id));
-- Só o próprio aluno muda o consentimento; o professor não altera share_financial.
create policy memberships_update_student on public.class_memberships for update to authenticated
  using (student_id = (select auth.uid())) with check (student_id = (select auth.uid()));
create policy memberships_delete_student on public.class_memberships for delete to authenticated
  using (student_id = (select auth.uid()));

create policy assignments_select on public.assignments for select to authenticated
  using (teacher_id = (select auth.uid()) or private.is_class_member(class_id));
create policy assignments_insert_teacher on public.assignments for insert to authenticated
  with check (teacher_id = (select auth.uid()) and private.is_class_teacher(class_id));
create policy assignments_delete_teacher on public.assignments for delete to authenticated
  using (teacher_id = (select auth.uid()));

create policy assignment_progress_select on public.assignment_progress for select to authenticated
  using (student_id = (select auth.uid()) or private.is_class_teacher(class_id));

-- Professor e aluno da mesma turma veem nome e avatar (sem e-mail; e-mail só via class_participants).
create policy profiles_select_classmates on public.profiles for select to authenticated
  using (private.shares_class(id));
create policy user_avatars_select_classmates on public.user_avatars for select to authenticated
  using (private.shares_class(user_id));

revoke all on function private.is_teacher(), private.is_class_teacher(uuid), private.is_class_member(uuid), private.shares_class(uuid),
  private.new_join_code(), private.classes_guard(), private.seed_assignment_progress(uuid, uuid, uuid, uuid),
  private.assignments_before(), private.assignments_after(), private.class_by_code(text), private.require_student(),
  private.preview_class(text), private.join_class(text), private.renew_class_code(uuid), private.class_participants(uuid),
  private.class_financial_summary(uuid, date, date) from public, anon;
grant execute on function private.is_teacher(), private.is_class_teacher(uuid), private.is_class_member(uuid), private.shares_class(uuid),
  private.new_join_code(), private.preview_class(text), private.join_class(text), private.renew_class_code(uuid),
  private.class_participants(uuid), private.class_financial_summary(uuid, date, date) to authenticated;
grant execute on function private.is_teacher(), private.is_class_teacher(uuid), private.is_class_member(uuid), private.shares_class(uuid),
  private.new_join_code() to service_role;
revoke all on function public.preview_class(text), public.join_class(text), public.renew_class_code(uuid),
  public.class_participants(uuid), public.class_financial_summary(uuid, date, date) from public, anon;
grant execute on function public.preview_class(text), public.join_class(text), public.renew_class_code(uuid),
  public.class_participants(uuid), public.class_financial_summary(uuid, date, date) to authenticated;
