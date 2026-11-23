-- FinTrack · 0005 · Curso, atividades, gabaritos privados, correção no banco, progresso e vídeos.
-- O conteúdo PÚBLICO (enunciados, opções) fica em public; gabaritos, explicações e resposta esperada
-- ficam em private.education_answer_keys, sem GRANT para anon/authenticated.
-- Conteúdo das aulas e atividades só é legível depois do vídeo introdutório do módulo (como na 0.6.x).
-- Títulos das aulas ficam sempre visíveis (catálogo, atribuições de turma).

create table public.education_modules (
  id          uuid primary key default gen_random_uuid(),
  key         text not null unique check (key ~ '^[a-z0-9-]{2,40}$'),
  title       text not null check (char_length(title) between 2 and 120),
  level       smallint not null unique check (level between 1 and 20),
  level_name  text not null check (char_length(level_name) between 2 and 40),
  description text not null check (char_length(description) <= 500),
  position    smallint not null,
  status      text not null default 'publicado' check (status in ('rascunho', 'publicado', 'arquivado')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger education_modules_touch before update on public.education_modules for each row execute function private.touch_updated_at();

create table public.education_lessons (
  id         uuid primary key default gen_random_uuid(),
  module_id  uuid not null references public.education_modules (id) on delete restrict,
  key        text not null check (key ~ '^[a-z0-9-]{2,40}$'),
  title      text not null check (char_length(title) between 2 and 120),
  position   smallint not null,
  status     text not null default 'publicado' check (status in ('rascunho', 'publicado', 'arquivado')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint education_lessons_module_key_uk unique (module_id, key),
  constraint education_lessons_module_position_uk unique (module_id, position)
);
create trigger education_lessons_touch before update on public.education_lessons for each row execute function private.touch_updated_at();

-- Corpo da aula (liberado após o vídeo do módulo).
create table public.education_lesson_contents (
  lesson_id   uuid primary key references public.education_lessons (id) on delete cascade,
  goal        text not null,
  explanation text not null,
  example     text not null,
  summary     text[] not null default '{}',
  sources     jsonb not null default '[]' check (jsonb_typeof(sources) = 'array'),
  reviewed_on date not null,   -- precisão de mês (a 0.6.x guarda "2026-09"; gravamos o dia 1)
  updated_at  timestamptz not null default now()
);
create trigger education_lesson_contents_touch before update on public.education_lesson_contents for each row execute function private.touch_updated_at();

create table public.education_activities (
  id          uuid primary key default gen_random_uuid(),
  lesson_id   uuid not null references public.education_lessons (id) on delete cascade,
  position    smallint not null check (position >= 0),
  kind        text not null check (kind in ('quiz', 'multi', 'classify', 'calc', 'budget')),
  prompt      text not null,
  -- Só o que o navegador precisa: opts | buckets+items (sem a resposta) | unit | cats+total.
  public_data jsonb not null default '{}' check (jsonb_typeof(public_data) = 'object'),
  constraint education_activities_position_uk unique (lesson_id, position)
);

create table private.education_answer_keys (
  activity_id   uuid primary key references public.education_activities (id) on delete cascade,
  answer        jsonb not null,  -- quiz: int | multi: [int] | classify: [int] | calc: número | budget: {sum,min,max}
  expected_text text not null,   -- texto da resposta esperada exibido após corrigir
  explanation   text not null    -- "por quê", exibido após corrigir
);

-- ===== Vídeos introdutórios =====
create table public.education_video_assets (
  id               uuid primary key default gen_random_uuid(),
  module_id        uuid not null references public.education_modules (id) on delete restrict,
  version          text not null check (version ~ '^[0-9A-Za-z._-]{1,20}$'),
  storage_bucket   text not null default 'education-videos',
  storage_path     text not null,
  duration_seconds numeric(10, 5) not null check (duration_seconds > 0),
  size_bytes       bigint not null check (size_bytes > 0),
  sha256           text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  status           text not null default 'publicado' check (status in ('rascunho', 'publicado', 'arquivado')),
  published_at     timestamptz,
  created_at       timestamptz not null default now(),
  constraint education_video_assets_version_uk unique (module_id, version)
);
create unique index education_video_assets_one_published_idx on public.education_video_assets (module_id) where status = 'publicado';

create table public.education_video_progress (
  user_id            uuid not null references public.profiles (id) on delete cascade,
  video_id           uuid not null references public.education_video_assets (id) on delete cascade,
  watched_seconds    numeric(10, 5) not null default 0 check (watched_seconds >= 0),
  completed          boolean not null default false,
  completed_at       timestamptz,
  -- Sessão de reprodução (proteção contra avanço artificial). O token bruto só vai ao navegador.
  position_seconds   numeric(10, 5),
  session_token_hash text check (session_token_hash ~ '^[0-9a-f]{64}$'),
  session_started_at timestamptz,
  session_origin     numeric(10, 5),
  last_ping_at       timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  primary key (user_id, video_id),
  constraint education_video_progress_completed check (completed = (completed_at is not null))
);
create index education_video_progress_video_idx on public.education_video_progress (video_id);
create trigger education_video_progress_touch before update on public.education_video_progress for each row execute function private.touch_updated_at();

-- Vídeo do módulo concluído pela conta autenticada (ou módulo sem vídeo publicado).
create or replace function private.intro_completed(p_module_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select not exists (select 1 from public.education_video_assets v where v.module_id = p_module_id and v.status = 'publicado')
      or exists (select 1 from public.education_video_assets v
                   join public.education_video_progress p on p.video_id = v.id
                  where v.module_id = p_module_id and v.status = 'publicado'
                    and p.user_id = (select auth.uid()) and p.completed)
$$;

create or replace function private.require_intro(p_module_id uuid)
returns void language plpgsql stable set search_path = '' as $$
begin
  if not private.intro_completed(p_module_id) then
    perform private.http_error(403, 'Assista ao vídeo introdutório completo para liberar esta aula.');
  end if;
end $$;

create or replace function private.video_for(p_module_key text)
returns public.education_video_assets language plpgsql stable security definer set search_path = '' as $$
declare v public.education_video_assets;
begin
  select a.* into v from public.education_video_assets a join public.education_modules m on m.id = a.module_id
   where m.key = p_module_key and a.status = 'publicado';
  if not found then perform private.http_error(404, 'Vídeo não encontrado.'); end if;
  return v;
end $$;

create or replace function private.video_start(p_module_key text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); v public.education_video_assets; p public.education_video_progress; v_token text;
begin
  v := private.video_for(p_module_key);
  v_token := encode(extensions.gen_random_bytes(32), 'hex');
  insert into public.education_video_progress (user_id, video_id) values (v_uid, v.id) on conflict do nothing;
  update public.education_video_progress
     set session_token_hash = encode(extensions.digest(v_token, 'sha256'), 'hex'),
         position_seconds = watched_seconds, session_origin = watched_seconds,
         session_started_at = clock_timestamp(), last_ping_at = clock_timestamp()
   where user_id = v_uid and video_id = v.id
  returning * into p;
  return jsonb_build_object('module', p_module_key, 'version', v.version, 'duration', v.duration_seconds,
    'storage_bucket', v.storage_bucket, 'storage_path', v.storage_path,
    'watched', p.watched_seconds, 'completed', p.completed, 'token', v_token);
end $$;

-- Mesmas regras da 0.6.x: avanço de no máximo 8 s por marca, nunca além do tempo real decorrido
-- desde o início da sessão (+0,35 s), nem além do já assistido +8 s. Nova sessão invalida a anterior.
create or replace function private.video_tick(p_module_key text, p_token text, p_position numeric)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_uid(); v public.education_video_assets; p public.education_video_progress;
  v_now timestamptz := clock_timestamp(); v_valid boolean; v_watched numeric; v_done boolean;
begin
  if p_position is null or p_position < 0 or p_position = 'NaN'::numeric then perform private.http_error(422, 'Posição inválida.'); end if;
  v := private.video_for(p_module_key);
  select * into p from public.education_video_progress where user_id = v_uid and video_id = v.id for update;
  if not found or p.session_token_hash is null or coalesce(p_token, '') = ''
     or p.session_token_hash <> encode(extensions.digest(p_token, 'sha256'), 'hex') then
    perform private.http_error(409, 'O vídeo foi aberto em outra aba. Reabra esta aula para continuar.');
  end if;
  v_valid := p_position - p.position_seconds between 0 and 8
             and p_position <= v.duration_seconds + 0.2
             and p_position - p.session_origin <= extract(epoch from (v_now - p.session_started_at)) + 0.35
             and p_position <= p.watched_seconds + 8;
  v_watched := case when v_valid then greatest(p.watched_seconds, least(p_position, v.duration_seconds)) else p.watched_seconds end;
  v_done := p.completed or v_watched >= v.duration_seconds - 0.15;
  update public.education_video_progress
     set watched_seconds = v_watched, completed = v_done, completed_at = coalesce(completed_at, case when v_done then now() end),
         position_seconds = case when v_valid then p_position else v_watched end, last_ping_at = v_now
   where user_id = v_uid and video_id = v.id;
  return jsonb_build_object('watched', v_watched, 'completed', v_done, 'accepted', v_valid);
end $$;

create or replace function public.video_start(p_module_key text)
returns jsonb language sql security invoker set search_path = '' as $$ select private.video_start(p_module_key) $$;
create or replace function public.video_tick(p_module_key text, p_token text, p_position numeric)
returns jsonb language sql security invoker set search_path = '' as $$ select private.video_tick(p_module_key, p_token, p_position) $$;

-- ===== Progresso e tentativas =====
create table public.education_progress (
  user_id      uuid not null references public.profiles (id) on delete cascade,
  lesson_id    uuid not null references public.education_lessons (id) on delete restrict,
  status       text not null default 'em_andamento' check (status in ('em_andamento', 'concluida')),
  best_score   smallint check (best_score between 0 and 100),
  last_score   smallint check (last_score between 0 and 100),
  attempts     int not null default 0 check (attempts >= 0),
  last_answers jsonb check (last_answers is null or pg_column_size(last_answers) <= 16384),
  started_at   timestamptz not null default now(),
  completed_at timestamptz,
  updated_at   timestamptz not null default now(),
  primary key (user_id, lesson_id),
  constraint education_progress_completed check ((status = 'concluida') = (completed_at is not null))
);
create index education_progress_lesson_idx on public.education_progress (lesson_id);
create index education_progress_in_progress_idx on public.education_progress (user_id) where status = 'em_andamento';
create trigger education_progress_touch before update on public.education_progress for each row execute function private.touch_updated_at();

-- Histórico de envios. Retenção: 24 meses (private.purge_old_education_attempts). Até 16 KB por resposta.
create table public.education_attempts (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles (id) on delete cascade,
  lesson_id    uuid not null references public.education_lessons (id) on delete restrict,
  answers      jsonb not null check (jsonb_typeof(answers) = 'array' and pg_column_size(answers) <= 16384),
  score        smallint not null check (score between 0 and 100),
  results      jsonb not null check (pg_column_size(results) <= 65536),
  submitted_at timestamptz not null default now()
);
create index education_attempts_user_lesson_idx on public.education_attempts (user_id, lesson_id, submitted_at desc);
create index education_attempts_lesson_idx on public.education_attempts (lesson_id);
create index education_attempts_submitted_idx on public.education_attempts (submitted_at);

-- ===== Correção (porta fiel de education_content.grade_item da 0.6.x) =====
create or replace function private.json_int(p jsonb)
returns int language plpgsql immutable set search_path = '' as $$
declare v numeric;
begin
  if p is null or jsonb_typeof(p) not in ('number', 'string') then raise exception 'invalid' using errcode = '22023'; end if;
  if jsonb_typeof(p) = 'string' then
    if (p #>> '{}') !~ '^\s*-?\d+\s*$' then raise exception 'invalid' using errcode = '22023'; end if;
    return btrim(p #>> '{}')::int;
  end if;
  v := (p #>> '{}')::numeric;
  if v <> trunc(v) then raise exception 'invalid' using errcode = '22023'; end if;
  return v::int;
end $$;

-- Aceita 3600, 3.600, 3600,00, 1.200,50 e "R$ 121".
create or replace function private.parse_number(p jsonb)
returns numeric language plpgsql immutable set search_path = '' as $$
declare s text;
begin
  if p is null or jsonb_typeof(p) not in ('number', 'string') then raise exception 'invalid' using errcode = '22023'; end if;
  if jsonb_typeof(p) = 'number' then return (p #>> '{}')::numeric; end if;
  s := replace(replace(p #>> '{}', 'R$', ''), ' ', '');
  if s !~ '^(-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?|-?\d+\.\d+)$' then raise exception 'invalid' using errcode = '22023'; end if;
  if position(',' in s) > 0 or s ~ '^-?\d{1,3}(\.\d{3})+$' then
    s := replace(replace(s, '.', ''), ',', '.');
  end if;
  return s::numeric;
end $$;

create or replace function private.grade_activity(p_activity_id uuid, p_answer jsonb, out fraction double precision, out expected text, out explanation text)
language plpgsql stable security definer set search_path = '' as $$
declare a public.education_activities; k private.education_answer_keys; n_opts int; v_int int; v_arr int[]; v_key int[];
        i int; ok int := 0; v_num numeric; v_sum int; r jsonb; good boolean;
begin
  select * into a from public.education_activities where id = p_activity_id;
  select * into k from private.education_answer_keys where activity_id = p_activity_id;
  if a.id is null or k.activity_id is null then raise exception 'invalid' using errcode = '22023'; end if;
  expected := k.expected_text; explanation := k.explanation;
  if a.kind = 'quiz' then
    n_opts := jsonb_array_length(a.public_data -> 'opts');
    v_int := private.json_int(p_answer);
    if v_int < 0 or v_int >= n_opts then raise exception 'invalid' using errcode = '22023'; end if;
    fraction := case when v_int = (k.answer #>> '{}')::int then 1.0 else 0.0 end;
  elsif a.kind = 'multi' then
    if jsonb_typeof(p_answer) <> 'array' then raise exception 'invalid' using errcode = '22023'; end if;
    n_opts := jsonb_array_length(a.public_data -> 'opts');
    select array_agg(distinct private.json_int(x) order by private.json_int(x)) into v_arr from jsonb_array_elements(p_answer) x;
    if v_arr is null or exists (select 1 from unnest(v_arr) u where u < 0 or u >= n_opts) then raise exception 'invalid' using errcode = '22023'; end if;
    select array_agg(x::int order by x::int) into v_key from jsonb_array_elements_text(k.answer) x;
    fraction := case when v_arr = v_key then 1.0 else 0.0 end;
  elsif a.kind = 'classify' then
    if jsonb_typeof(p_answer) <> 'array' or jsonb_array_length(p_answer) <> jsonb_array_length(k.answer) then
      raise exception 'invalid' using errcode = '22023';
    end if;
    for i in 0 .. jsonb_array_length(k.answer) - 1 loop
      if private.json_int(p_answer -> i) = (k.answer ->> i)::int then ok := ok + 1; end if;
    end loop;
    fraction := ok::double precision / jsonb_array_length(k.answer);
  elsif a.kind = 'calc' then
    v_num := private.parse_number(p_answer);
    fraction := case when abs(v_num - (k.answer #>> '{}')::numeric) < 0.005 then 1.0 else 0.0 end;
  elsif a.kind = 'budget' then
    if jsonb_typeof(p_answer) <> 'array' then raise exception 'invalid' using errcode = '22023'; end if;
    select array_agg(private.json_int(x) order by o) into v_arr from jsonb_array_elements(p_answer) with ordinality t(x, o);
    r := k.answer;
    good := coalesce(array_length(v_arr, 1), 0) = jsonb_array_length(a.public_data -> 'cats')
            and not exists (select 1 from unnest(v_arr) u where u < 0 or u > 100);
    if good then
      select sum(u) into v_sum from unnest(v_arr) u;
      good := v_sum = (r ->> 'sum')::int
        and not exists (select 1 from jsonb_each_text(r -> 'min') m where v_arr[m.key::int + 1] < m.value::int)
        and not exists (select 1 from jsonb_each_text(r -> 'max') m where v_arr[m.key::int + 1] > m.value::int);
    end if;
    fraction := case when good then 1.0 else 0.0 end;
  else
    raise exception 'invalid' using errcode = '22023';
  end if;
end $$;

create or replace function private.lesson_by_key(p_module_key text, p_lesson_key text)
returns public.education_lessons language plpgsql stable security definer set search_path = '' as $$
declare l public.education_lessons;
begin
  select l2.* into l from public.education_lessons l2 join public.education_modules m on m.id = l2.module_id
   where m.key = p_module_key and l2.key = p_lesson_key and l2.status = 'publicado' and m.status = 'publicado';
  if not found then perform private.http_error(404, 'Conteúdo não encontrado.'); end if;
  return l;
end $$;

-- Abrir a aula: só registra "em andamento". Conclusão exige submit_lesson.
create or replace function private.start_lesson(p_module_key text, p_lesson_key text)
returns void language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); l public.education_lessons;
begin
  l := private.lesson_by_key(p_module_key, p_lesson_key);
  perform private.require_intro(l.module_id);
  insert into public.education_progress (user_id, lesson_id) values (v_uid, l.id) on conflict do nothing;
end $$;

create or replace function private.check_activity(p_module_key text, p_lesson_key text, p_index int, p_answer jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid(); l public.education_lessons; v_act uuid; g record;
begin
  perform private.hit_rate_limit('edu-check:' || v_uid, 600, interval '1 hour');
  l := private.lesson_by_key(p_module_key, p_lesson_key);
  perform private.require_intro(l.module_id);
  select id into v_act from public.education_activities where lesson_id = l.id and position = p_index;
  if not found then perform private.http_error(404, 'Atividade não encontrada.'); end if;
  begin
    g := private.grade_activity(v_act, p_answer);
  exception when invalid_parameter_value or invalid_text_representation or numeric_value_out_of_range or array_subscript_error then
    perform private.http_error(422, 'Resposta inválida.');
  end;
  return jsonb_build_object('ok', g.fraction = 1.0, 'fraction', g.fraction, 'right', g.expected, 'why', g.explanation);
end $$;

create or replace function private.submit_lesson(p_module_key text, p_lesson_key text, p_answers jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := private.require_uid(); l public.education_lessons; v_role text; v_pass int := (private.setting('education_pass_percent'))::int;
  act record; g record; v_results jsonb := '[]'; v_sum double precision := 0; v_n int := 0; v_score int;
  prev public.education_progress; v_best int; v_done boolean; v_attempts int;
begin
  perform private.hit_rate_limit('edu-submit:' || v_uid, 120, interval '1 hour');
  l := private.lesson_by_key(p_module_key, p_lesson_key);
  perform private.require_intro(l.module_id);
  if p_answers is null or jsonb_typeof(p_answers) <> 'array' or pg_column_size(p_answers) > 16384 then
    perform private.http_error(422, 'Responda todas as atividades.');
  end if;
  if jsonb_array_length(p_answers) <> (select count(*) from public.education_activities where lesson_id = l.id) then
    perform private.http_error(422, 'Responda todas as atividades.');
  end if;
  for act in select id, position from public.education_activities where lesson_id = l.id order by position loop
    begin
      g := private.grade_activity(act.id, p_answers -> v_n);
    exception when invalid_parameter_value or invalid_text_representation or numeric_value_out_of_range or array_subscript_error then
      perform private.http_error(422, 'Resposta inválida.');
    end;
    v_sum := v_sum + g.fraction; v_n := v_n + 1;
    v_results := v_results || jsonb_build_object('ok', g.fraction = 1.0, 'fraction', g.fraction, 'right', g.expected, 'why', g.explanation);
  end loop;
  -- round() de double precision arredonda "meio para par", igual ao round() do Python da 0.6.x.
  v_score := round(100 * v_sum / v_n)::int;

  select * into prev from public.education_progress where user_id = v_uid and lesson_id = l.id for update;
  v_attempts := coalesce(prev.attempts, 0) + 1;
  v_best := greatest(v_score, coalesce(prev.best_score, 0));
  v_done := v_score >= v_pass or coalesce(prev.status = 'concluida', false);
  insert into public.education_progress as e (user_id, lesson_id, status, best_score, last_score, attempts, last_answers, completed_at)
  values (v_uid, l.id, case when v_done then 'concluida' else 'em_andamento' end, v_best, v_score, v_attempts, p_answers,
          case when v_done then now() end)
  on conflict (user_id, lesson_id) do update
     set status = excluded.status, best_score = excluded.best_score, last_score = excluded.last_score,
         attempts = excluded.attempts, last_answers = excluded.last_answers,
         completed_at = coalesce(e.completed_at, excluded.completed_at);
  insert into public.education_attempts (user_id, lesson_id, answers, score, results)
  values (v_uid, l.id, p_answers, v_score, v_results);

  select role into v_role from public.profiles where id = v_uid;
  if v_role = 'aluno' and v_done then
    update public.assignment_progress ap
       set status = 'concluida', score = v_best, submitted_at = coalesce(ap.submitted_at, now())
     where ap.student_id = v_uid and ap.assignment_id in (select id from public.assignments where lesson_id = l.id);
  end if;
  return jsonb_build_object('score', v_score, 'best', v_best, 'passed', v_score >= v_pass, 'completed', v_done,
                            'attempts', v_attempts, 'results', v_results);
end $$;

-- Catálogo para a tela: módulos, títulos, estado do vídeo e quantidade de atividades (sempre visível).
create or replace function private.education_outline()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_uid uuid := private.require_uid();
begin
  return jsonb_build_object('pass', (private.setting('education_pass_percent'))::int, 'modules', coalesce((
    select jsonb_agg(jsonb_build_object(
      'key', m.key, 'level', m.level, 'level_name', m.level_name, 'title', m.title, 'description', m.description,
      'unlocked', private.intro_completed(m.id),
      'intro', (select jsonb_build_object('version', v.version, 'duration', v.duration_seconds,
                       'watched', coalesce(p.watched_seconds, 0), 'completed', coalesce(p.completed, false))
                  from public.education_video_assets v
                  left join public.education_video_progress p on p.video_id = v.id and p.user_id = v_uid
                 where v.module_id = m.id and v.status = 'publicado'),
      'topics', (select coalesce(jsonb_agg(jsonb_build_object('key', l.key, 'title', l.title,
                         'activity_count', (select count(*) from public.education_activities a where a.lesson_id = l.id))
                         order by l.position), '[]')
                   from public.education_lessons l where l.module_id = m.id and l.status = 'publicado'))
      order by m.position)
      from public.education_modules m where m.status = 'publicado'), '[]'));
end $$;

create or replace function public.education_outline()
returns jsonb language sql stable security invoker set search_path = '' as $$ select private.education_outline() $$;
create or replace function public.start_lesson(p_module_key text, p_lesson_key text)
returns void language sql security invoker set search_path = '' as $$ select private.start_lesson(p_module_key, p_lesson_key) $$;
create or replace function public.check_activity(p_module_key text, p_lesson_key text, p_index int, p_answer jsonb)
returns jsonb language sql security invoker set search_path = '' as $$ select private.check_activity(p_module_key, p_lesson_key, p_index, p_answer) $$;
create or replace function public.submit_lesson(p_module_key text, p_lesson_key text, p_answers jsonb)
returns jsonb language sql security invoker set search_path = '' as $$ select private.submit_lesson(p_module_key, p_lesson_key, p_answers) $$;

create or replace function private.purge_old_education_attempts()
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  delete from public.education_attempts where submitted_at < now() - interval '24 months';
  get diagnostics n = row_count; return n;
end $$;

-- ===== Privilégios =====
alter table public.education_modules enable row level security;
alter table public.education_lessons enable row level security;
alter table public.education_lesson_contents enable row level security;
alter table public.education_activities enable row level security;
alter table public.education_video_assets enable row level security;
alter table public.education_video_progress enable row level security;
alter table public.education_progress enable row level security;
alter table public.education_attempts enable row level security;
alter table private.education_answer_keys enable row level security;  -- sem políticas: só service_role/definer

revoke all on public.education_modules, public.education_lessons, public.education_lesson_contents, public.education_activities,
  public.education_video_assets, public.education_video_progress, public.education_progress, public.education_attempts from anon, authenticated;
revoke all on private.education_answer_keys from public, anon, authenticated;

grant select on public.education_modules, public.education_lessons, public.education_lesson_contents,
  public.education_activities, public.education_video_assets, public.education_progress, public.education_attempts to authenticated;
-- Sem o hash do token de sessão do vídeo.
grant select (user_id, video_id, watched_seconds, completed, completed_at, created_at, updated_at) on public.education_video_progress to authenticated;
grant all on public.education_modules, public.education_lessons, public.education_lesson_contents, public.education_activities,
  public.education_video_assets, public.education_video_progress, public.education_progress, public.education_attempts to service_role;
grant all on private.education_answer_keys to service_role;

create policy education_modules_read on public.education_modules for select to authenticated using (status = 'publicado');
create policy education_lessons_read on public.education_lessons for select to authenticated using (status = 'publicado');
create policy education_lesson_contents_read_unlocked on public.education_lesson_contents for select to authenticated
  using (exists (select 1 from public.education_lessons l where l.id = lesson_id and l.status = 'publicado'
                  and private.intro_completed(l.module_id)));
create policy education_activities_read_unlocked on public.education_activities for select to authenticated
  using (exists (select 1 from public.education_lessons l where l.id = lesson_id and l.status = 'publicado'
                  and private.intro_completed(l.module_id)));
create policy education_video_assets_read on public.education_video_assets for select to authenticated using (status = 'publicado');
create policy education_video_progress_own on public.education_video_progress for select to authenticated using (user_id = (select auth.uid()));
create policy education_progress_own on public.education_progress for select to authenticated using (user_id = (select auth.uid()));
create policy education_attempts_own on public.education_attempts for select to authenticated using (user_id = (select auth.uid()));

revoke all on function private.intro_completed(uuid), private.require_intro(uuid), private.video_for(text), private.video_start(text),
  private.video_tick(text, text, numeric), private.json_int(jsonb), private.parse_number(jsonb), private.grade_activity(uuid, jsonb),
  private.lesson_by_key(text, text), private.start_lesson(text, text), private.check_activity(text, text, int, jsonb),
  private.submit_lesson(text, text, jsonb), private.education_outline(), private.purge_old_education_attempts() from public, anon;
grant execute on function private.intro_completed(uuid), private.video_start(text), private.video_tick(text, text, numeric),
  private.start_lesson(text, text), private.check_activity(text, text, int, jsonb), private.submit_lesson(text, text, jsonb),
  private.education_outline() to authenticated;
grant execute on function private.purge_old_education_attempts(), private.grade_activity(uuid, jsonb) to service_role;
revoke all on function public.video_start(text), public.video_tick(text, text, numeric), public.education_outline(),
  public.start_lesson(text, text), public.check_activity(text, text, int, jsonb), public.submit_lesson(text, text, jsonb) from public, anon;
grant execute on function public.video_start(text), public.video_tick(text, text, numeric), public.education_outline(),
  public.start_lesson(text, text), public.check_activity(text, text, int, jsonb), public.submit_lesson(text, text, jsonb) to authenticated;
