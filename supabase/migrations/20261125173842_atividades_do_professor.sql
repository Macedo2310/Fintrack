-- Atividades do professor além das aulas do curso:
--   desafio: tarefa prática no app (registrar despesas, criar meta, ...), conferida automaticamente.
--            O professor vê só se o aluno concluiu e quantas ações fez, nunca valores.
--   quiz:    perguntas de múltipla escolha escritas pelo professor (ou a partir de modelos).
--            O gabarito fica em private.assignment_quiz_keys, fora do alcance dos alunos.

alter table public.assignments drop constraint assignments_content_type_check;
alter table public.assignments alter column lesson_id drop not null;
alter table public.assignments add column title text, add column config jsonb not null default '{}'::jsonb;
alter table public.assignments
  add constraint assignments_content_type_check check (content_type in ('aula', 'desafio', 'quiz')),
  add constraint assignments_kind_shape check ((content_type = 'aula') = (lesson_id is not null)),
  add constraint assignments_title_check check (title is null or char_length(title) between 3 and 120),
  add constraint assignments_config_size check (pg_column_size(config) <= 32768);
grant select (title, config) on public.assignments to authenticated;

alter table public.assignment_progress
  add column progress smallint not null default 0,
  add column attempts smallint not null default 0;

create table private.assignment_quiz_keys (
  assignment_id uuid primary key references public.assignments (id) on delete cascade,
  answers jsonb not null
);
revoke all on private.assignment_quiz_keys from public, anon, authenticated;

create or replace view public.assignment_overview with (security_invoker = true) as
 select ap.assignment_id, ap.class_id, ap.student_id, ap.status, ap.score, ap.submitted_at,
        a.lesson_id, a.due_date, a.instructions, a.created_at,
        case when ap.status = 'concluida' then 'concluida'
             when a.due_date is not null and a.due_date < private.today_br() then 'atrasada'
             else 'pendente' end as state,
        a.content_type, a.title, a.config, ap.progress, ap.attempts
   from public.assignment_progress ap
   join public.assignments a on a.id = ap.assignment_id and a.class_id = ap.class_id;

-- Desafios e quizzes só entram pela função create_activity (que valida e separa o gabarito).
create or replace function private.assignments_before()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.due_date is not null and new.due_date < private.today_br() then
    perform private.http_error(422, 'O prazo precisa ser hoje ou uma data futura.');
  end if;
  if new.content_type = 'aula' then
    if not exists (select 1 from public.education_lessons where id = new.lesson_id and status = 'publicado') then
      perform private.http_error(422, 'Escolha uma aula do curso.');
    end if;
  elsif current_setting('fintrack.activity_rpc', true) is distinct from 'on' then
    perform private.http_error(422, 'Use o formulário de atividades para criar desafios e quizzes.');
  end if;
  new.instructions := private.clean_text(new.instructions);
  new.title := private.clean_text(new.title);
  return new;
end $$;

create or replace function private.create_activity(p_class_id uuid, p_type text, p_title text, p_config jsonb,
                                                   p_due date, p_instructions text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_uid(); v_pub jsonb; v_keys jsonb := '[]'; q jsonb; v_opts jsonb;
  v_ans int; v_target int; v_kind text; v_id uuid; i int := 0;
begin
  perform private.hit_rate_limit('activity-new:' || v_uid, 60, interval '1 hour');
  if not exists (select 1 from public.classes where id = p_class_id and teacher_id = v_uid) then
    perform private.http_error(403, 'Sem permissão.');
  end if;
  if p_title is null or char_length(btrim(p_title)) not between 3 and 120 then
    perform private.http_error(422, 'Dê um título à atividade (de 3 a 120 caracteres).');
  end if;
  if p_config is null or jsonb_typeof(p_config) <> 'object' or pg_column_size(p_config) > 32768 then
    perform private.http_error(422, 'Atividade inválida.');
  end if;

  if p_type = 'desafio' then
    v_kind := p_config ->> 'kind';
    if v_kind is null or v_kind not in ('despesas', 'receitas', 'meta', 'reserva', 'comprovante') then
      perform private.http_error(422, 'Escolha um tipo de desafio.');
    end if;
    begin v_target := (p_config ->> 'target')::int; exception when others then v_target := null; end;
    if v_target is null or v_target not between 1 and 50 then
      perform private.http_error(422, 'A quantidade do desafio deve ser de 1 a 50.');
    end if;
    v_pub := jsonb_build_object('kind', v_kind, 'target', v_target);

  elsif p_type = 'quiz' then
    if jsonb_typeof(p_config -> 'questions') is distinct from 'array'
       or jsonb_array_length(p_config -> 'questions') not between 1 and 15 then
      perform private.http_error(422, 'O quiz precisa ter de 1 a 15 perguntas.');
    end if;
    v_pub := jsonb_build_object('questions', '[]'::jsonb);
    for q in select value from jsonb_array_elements(p_config -> 'questions') with ordinality t(value, n) order by n loop
      i := i + 1;
      v_opts := q -> 'options';
      if jsonb_typeof(q -> 'q') is distinct from 'string' or char_length(btrim(q ->> 'q')) not between 3 and 300 then
        perform private.http_error(422, format('Pergunta %s: escreva o enunciado (de 3 a 300 caracteres).', i));
      end if;
      if jsonb_typeof(v_opts) is distinct from 'array' or jsonb_array_length(v_opts) not between 2 and 5
         or exists (select 1 from jsonb_array_elements(v_opts) o
                     where jsonb_typeof(o) <> 'string' or char_length(btrim(o #>> '{}')) not between 1 and 150) then
        perform private.http_error(422, format('Pergunta %s: preencha de 2 a 5 alternativas (até 150 caracteres cada).', i));
      end if;
      begin v_ans := (q ->> 'answer')::int; exception when others then v_ans := null; end;
      if v_ans is null or v_ans < 0 or v_ans >= jsonb_array_length(v_opts) then
        perform private.http_error(422, format('Pergunta %s: marque a alternativa correta.', i));
      end if;
      if char_length(coalesce(q ->> 'why', '')) > 300 then
        perform private.http_error(422, format('Pergunta %s: a explicação pode ter até 300 caracteres.', i));
      end if;
      v_pub := jsonb_set(v_pub, '{questions}', (v_pub -> 'questions') || jsonb_build_array(jsonb_build_object(
                 'q', btrim(q ->> 'q'),
                 'options', (select jsonb_agg(btrim(o #>> '{}') order by n) from jsonb_array_elements(v_opts) with ordinality t(o, n)))));
      v_keys := v_keys || jsonb_build_array(jsonb_build_object('a', v_ans, 'why', private.clean_text(q ->> 'why')));
    end loop;
  else
    perform private.http_error(422, 'Tipo de atividade inválido.');
  end if;

  perform set_config('fintrack.activity_rpc', 'on', true);
  insert into public.assignments (class_id, teacher_id, content_type, title, config, due_date, instructions)
  values (p_class_id, v_uid, p_type, p_title, v_pub, p_due, p_instructions)
  returning id into v_id;
  perform set_config('fintrack.activity_rpc', 'off', true);
  if p_type = 'quiz' then
    insert into private.assignment_quiz_keys (assignment_id, answers) values (v_id, v_keys);
  end if;
  return jsonb_build_object('id', v_id);
end $$;

-- Correção do quiz no servidor. Enquanto o aluno não atinge a nota mínima, só diz quais acertou
-- (sem revelar a alternativa certa), para a pessoa estudar em vez de chutar.
create or replace function private.submit_quiz(p_assignment_id uuid, p_answers jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_student(); a public.assignments; p public.assignment_progress; k jsonb;
  n int; v_ans int; v_right int; v_ok int := 0; v_results jsonb := '[]'; v_score int; v_done boolean;
  v_pass int := (private.setting('education_pass_percent'))::int;
begin
  perform private.hit_rate_limit('quiz-submit:' || v_uid, 60, interval '1 hour');
  select * into a from public.assignments where id = p_assignment_id and content_type = 'quiz';
  if not found then perform private.http_error(404, 'Atividade não encontrada.'); end if;
  select * into p from public.assignment_progress where assignment_id = a.id and student_id = v_uid for update;
  if not found then perform private.http_error(403, 'Você não participa desta turma.'); end if;
  select answers into k from private.assignment_quiz_keys where assignment_id = a.id;
  n := jsonb_array_length(k);
  if jsonb_typeof(p_answers) is distinct from 'array' or jsonb_array_length(p_answers) <> n then
    perform private.http_error(422, 'Responda todas as perguntas.');
  end if;
  for i in 0 .. n - 1 loop
    begin v_ans := (p_answers ->> i)::int; exception when others then v_ans := null; end;
    if v_ans is null then perform private.http_error(422, 'Responda todas as perguntas.'); end if;
    v_right := (k -> i ->> 'a')::int;
    if v_ans = v_right then v_ok := v_ok + 1; end if;
    v_results := v_results || jsonb_build_array(jsonb_build_object('ok', v_ans = v_right));
  end loop;
  v_score := round(100.0 * v_ok / n);
  v_done := p.status = 'concluida' or v_score >= v_pass;
  update public.assignment_progress
     set attempts = least(attempts + 1, 32767), score = greatest(coalesce(score, 0), v_score),
         status = case when v_done then 'concluida' else 'pendente' end,
         submitted_at = case when v_done then coalesce(submitted_at, now()) else submitted_at end
   where assignment_id = a.id and student_id = v_uid
  returning * into p;
  if v_done then   -- concluiu: mostra o gabarito com as explicações
    select jsonb_agg(r.value || jsonb_build_object('right', (k -> (r.n - 1)::int ->> 'a')::int, 'why', k -> (r.n - 1)::int -> 'why') order by r.n)
      into v_results from jsonb_array_elements(v_results) with ordinality r(value, n);
  end if;
  return jsonb_build_object('score', v_score, 'best', p.score, 'passed', v_score >= v_pass, 'completed', v_done,
                            'attempts', p.attempts, 'pass', v_pass, 'results', v_results);
end $$;

-- Recalcula os desafios pendentes de um aluno (chamado pelos gatilhos das tabelas do app).
create or replace function private.refresh_challenges(p_user uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare r record; v_count int;
begin
  for r in select ap.assignment_id, a.config ->> 'kind' as kind, (a.config ->> 'target')::int as target, a.created_at
             from public.assignment_progress ap
             join public.assignments a on a.id = ap.assignment_id
            where ap.student_id = p_user and a.content_type = 'desafio' and ap.status = 'pendente' loop
    v_count := case r.kind
      when 'despesas' then (select count(*) from public.transactions where user_id = p_user and type = 'despesa' and created_at >= r.created_at)
      when 'receitas' then (select count(*) from public.transactions where user_id = p_user and type = 'receita' and created_at >= r.created_at)
      when 'meta' then (select count(*) from public.goals where user_id = p_user and deleted_at is null and created_at >= r.created_at)
      when 'reserva' then (select count(*) from public.goal_reservation_events where user_id = p_user and kind = 'reserva' and created_at >= r.created_at)
      when 'comprovante' then (select count(*) from public.receipts where user_id = p_user and created_at >= r.created_at)
      else 0 end;
    update public.assignment_progress
       set progress = least(v_count, 32767),
           status = case when v_count >= r.target then 'concluida' else status end,
           score = case when v_count >= r.target then 100 else score end,
           submitted_at = case when v_count >= r.target then now() else submitted_at end
     where assignment_id = r.assignment_id and student_id = p_user and progress is distinct from least(v_count, 32767);
  end loop;
end $$;

create or replace function private.challenge_touch()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if exists (select 1 from public.assignment_progress ap join public.assignments a on a.id = ap.assignment_id
              where ap.student_id = new.user_id and a.content_type = 'desafio' and ap.status = 'pendente') then
    perform private.refresh_challenges(new.user_id);
  end if;
  return null;
end $$;

create trigger transactions_challenges after insert on public.transactions for each row execute function private.challenge_touch();
create trigger goals_challenges after insert on public.goals for each row execute function private.challenge_touch();
create trigger reservations_challenges after insert on public.goal_reservation_events for each row execute function private.challenge_touch();
create trigger receipts_challenges after insert on public.receipts for each row execute function private.challenge_touch();

create or replace function public.create_activity(p_class_id uuid, p_type text, p_title text, p_config jsonb,
                                                  p_due date default null, p_instructions text default null)
returns jsonb language sql security invoker set search_path = '' as $$
  select private.create_activity(p_class_id, p_type, p_title, p_config, p_due, p_instructions) $$;
create or replace function public.submit_quiz(p_assignment_id uuid, p_answers jsonb)
returns jsonb language sql security invoker set search_path = '' as $$ select private.submit_quiz(p_assignment_id, p_answers) $$;

revoke all on function private.create_activity(uuid, text, text, jsonb, date, text), private.submit_quiz(uuid, jsonb),
  private.refresh_challenges(uuid), private.challenge_touch() from public, anon, authenticated;
grant execute on function private.create_activity(uuid, text, text, jsonb, date, text), private.submit_quiz(uuid, jsonb) to authenticated;
revoke all on function public.create_activity(uuid, text, text, jsonb, date, text), public.submit_quiz(uuid, jsonb) from public, anon;
grant execute on function public.create_activity(uuid, text, text, jsonb, date, text), public.submit_quiz(uuid, jsonb) to authenticated;
