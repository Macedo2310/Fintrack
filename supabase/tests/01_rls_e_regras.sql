-- FinTrack · testes de RLS, permissões e regras de negócio.
-- Roda inteiro num único bloco DO e SEMPRE termina com uma exceção, o que desfaz tudo:
--   sucesso  -> erro "TESTES_OK: <n> verificações"
--   falha    -> erro "FALHOU: <descrição>"
-- Nada (contas, transações, turmas) permanece no banco. Execute como postgres (SQL Editor ou MCP).
do $test$
declare
  a1 constant uuid := '11111111-1111-4111-8111-111111111111';  -- aluno 1
  a2 constant uuid := '22222222-2222-4222-8222-222222222222';  -- aluno 2
  p1 constant uuid := '33333333-3333-4333-8333-333333333333';  -- professor 1
  p2 constant uuid := '44444444-4444-4444-8444-444444444444';  -- professor 2
  n int := 0; v int; v_big bigint; v_txt text; v_json jsonb; v_uuid uuid; v_ok boolean;
  cat_alim uuid; cat_mesada uuid; cat_a2 uuid; tx1 uuid; tx_rec uuid; g1 uuid; g_a2 uuid; cls uuid; cls2 uuid; code text;
  lesson_poup uuid; aid uuid; conv uuid; v_token text; v_state text; v_errors int; v_pos numeric;
begin
  -- ---------- preparação (postgres) ----------
  insert into auth.users (instance_id, id, aud, role, email, encrypted_password, raw_user_meta_data, raw_app_meta_data, created_at, updated_at)
  values ('00000000-0000-0000-0000-000000000000', a1, 'authenticated', 'authenticated', 'aluno1@teste.invalid', '', '{"name":"Aluno Um"}', '{}', now(), now()),
         ('00000000-0000-0000-0000-000000000000', a2, 'authenticated', 'authenticated', 'aluno2@teste.invalid', '', '{"name":"Aluno Dois"}', '{}', now(), now()),
         ('00000000-0000-0000-0000-000000000000', p1, 'authenticated', 'authenticated', 'prof1@teste.invalid', '', '{"full_name":"Prof Um"}', '{}', now(), now()),
         ('00000000-0000-0000-0000-000000000000', p2, 'authenticated', 'authenticated', 'prof2@teste.invalid', '', '{}', '{}', now(), now());
  select count(*) into v from public.profiles where id in (a1, a2, p1, p2) and role is null and onboarding_status = 'pendente';
  if v <> 4 then raise exception 'FALHOU: gatilho de cadastro não criou 4 perfis pendentes (%)', v; end if; n := n + 1;
  select name into v_txt from public.profiles where id = p2;
  if v_txt <> 'prof2' then raise exception 'FALHOU: nome padrão a partir do e-mail (%)', v_txt; end if; n := n + 1;
  select count(*) into v from public.user_settings where user_id in (a1, a2, p1, p2);
  if v <> 4 then raise exception 'FALHOU: user_settings não criados'; end if; n := n + 1;

  -- Gatilho com erro NÃO bloqueia cadastro (erro registrado em private.signup_trigger_errors).
  alter table public.profiles add constraint tmp_falha check (name <> 'Quebra Gatilho');
  insert into auth.users (instance_id, id, aud, role, email, encrypted_password, raw_user_meta_data, raw_app_meta_data, created_at, updated_at)
  values ('00000000-0000-0000-0000-000000000000', '55555555-5555-4555-8555-555555555555', 'authenticated', 'authenticated',
          'quebra@teste.invalid', '', '{"name":"Quebra Gatilho"}', '{}', now(), now());
  alter table public.profiles drop constraint tmp_falha;
  select count(*) into v from private.signup_trigger_errors where user_id = '55555555-5555-4555-8555-555555555555';
  if v <> 1 then raise exception 'FALHOU: erro do gatilho de cadastro não registrado'; end if; n := n + 1;

  select id into lesson_poup from public.education_lessons l where l.key = 'o-que-e';
  update private.app_settings set value = 'false' where key = 'email_delivery_ready';

  -- ---------- anon não alcança nada ----------
  execute 'set local role anon';
  begin perform 1 from public.transactions limit 1; raise exception 'FALHOU: anon leu transactions';
  exception when insufficient_privilege then n := n + 1; end;
  begin perform 1 from public.profiles limit 1; raise exception 'FALHOU: anon leu profiles';
  exception when insufficient_privilege then n := n + 1; end;
  begin perform public.balance_summary(); raise exception 'FALHOU: anon executou RPC';
  exception when insufficient_privilege then n := n + 1; end;
  execute 'reset role';

  -- ---------- aluno 1: onboarding, gabarito inacessível ----------
  perform set_config('request.jwt.claims', json_build_object('sub', a1, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
  begin perform 1 from private.education_answer_keys limit 1; raise exception 'FALHOU: cliente leu gabaritos';
  exception when insufficient_privilege then n := n + 1; end;
  begin perform 1 from private.market_indicators limit 1; raise exception 'FALHOU: cliente leu cache privado';
  exception when insufficient_privilege then n := n + 1; end;
  begin update public.profiles set role = 'professor' where id = a1; raise exception 'FALHOU: cliente alterou o próprio papel';
  exception when insufficient_privilege then n := n + 1; end;
  v_json := public.complete_onboarding('Aluno Um', 'aluno', true);
  if v_json ->> 'role' <> 'aluno' or v_json ->> 'next' <> '/avatar.html' then raise exception 'FALHOU: onboarding aluno %', v_json; end if; n := n + 1;
  begin perform public.complete_onboarding('Aluno Um', 'professor', true); raise exception 'FALHOU: papel redefinido';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  perform public.skip_avatar();
  select onboarding_status into v_txt from public.profiles where id = a1;
  if v_txt <> 'concluido' then raise exception 'FALHOU: avatar não concluiu onboarding (%)', v_txt; end if; n := n + 1;
  begin insert into public.user_avatars (user_id, kind, preset, bg) values (a2, 'preset', 'gato', '#1DB954');
        raise exception 'FALHOU: aluno gravou avatar de outra conta';
  exception when insufficient_privilege then n := n + 1; end;
  begin update public.user_settings set weekly_email = true where user_id = a1; raise exception 'FALHOU: resumo semanal sem SMTP';
  exception when sqlstate 'PGRST' then n := n + 1; end;

  -- ---------- categorias e transações ----------
  select id into cat_alim from public.categories where user_id is null and type = 'despesa' and name = 'Alimentação';
  select id into cat_mesada from public.categories where user_id is null and type = 'receita' and name = 'Mesada';
  begin insert into public.categories (user_id, type, name) values (a1, 'despesa', '  alimentação ');
        raise exception 'FALHOU: duplicou categoria global por caixa/espaço';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  insert into public.categories (user_id, type, name) values (a1, 'despesa', '  Cursos   online ') returning id into v_uuid;
  select name into v_txt from public.categories where id = v_uuid;
  if v_txt <> 'Cursos online' then raise exception 'FALHOU: nome de categoria não normalizado (%)', v_txt; end if; n := n + 1;
  begin insert into public.categories (user_id, type, name) values (a1, 'despesa', 'CURSOS ONLINE'); raise exception 'FALHOU: duplicou categoria pessoal';
  exception when unique_violation then n := n + 1; end;
  begin update public.categories set name = 'Hack' where id = cat_alim; get diagnostics v = row_count;
        if v <> 0 then raise exception 'FALHOU: aluno alterou categoria global'; end if; n := n + 1; end;

  insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
  values (a1, 'receita', cat_mesada, 'Mesada', 10000, private.today_br()) returning id into tx1;
  begin insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
        values (a1, 'receita', cat_alim, 'Tipo errado', 100, private.today_br()); raise exception 'FALHOU: categoria incompatível aceita';
  exception when foreign_key_violation then n := n + 1; end;
  begin insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
        values (a1, 'despesa', cat_alim, 'Zero', 0, private.today_br()); raise exception 'FALHOU: valor zero aceito';
  exception when check_violation then n := n + 1; end;
  begin insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
        values (a2, 'despesa', cat_alim, 'Em nome de outro', 100, private.today_br()); raise exception 'FALHOU: transação em nome de outra conta';
  exception when insufficient_privilege then n := n + 1; end;
  begin insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on, recurrence_id)
        values (a1, 'despesa', cat_alim, 'Vínculo', 100, private.today_br(), gen_random_uuid()); raise exception 'FALHOU: cliente vinculou recorrência';
  exception when insufficient_privilege then n := n + 1; end;
  -- lançamento futuro não entra no saldo
  insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
  values (a1, 'receita', cat_mesada, 'Futuro', 99999, private.today_br() + 10);
  v_json := public.balance_summary();
  if (v_json ->> 'balance_total')::bigint <> 10000 then raise exception 'FALHOU: saldo com lançamento futuro %', v_json; end if; n := n + 1;

  -- recorrência: início no passado gera ocorrências; rodar o job de novo não duplica
  tx_rec := public.create_recurring_transaction('despesa', cat_alim, 'Lanche semanal', 100, private.today_br() - 21, 'semanal', null, null);
  select count(*) into v from public.transactions where user_id = a1 and description = 'Lanche semanal';
  if v <> 4 then raise exception 'FALHOU: recorrência semanal gerou % ocorrências (esperado 4)', v; end if; n := n + 1;
  execute 'reset role';
  perform private.generate_due_recurrences(null); perform private.generate_due_recurrences(null);
  execute 'set local role authenticated';
  select count(*) into v from public.transactions where user_id = a1 and description = 'Lanche semanal';
  if v <> 4 then raise exception 'FALHOU: job duplicou ocorrências (%)', v; end if; n := n + 1;
  select id into v_uuid from public.transactions where user_id = a1 and description = 'Lanche semanal' and occurred_on = private.today_br() - 7;
  v := public.update_transaction_scoped(v_uuid, 'future', 'despesa', cat_alim, 'Lanche novo', 150, private.today_br() - 7, null);
  select count(*) into v from public.transactions where user_id = a1 and description = 'Lanche semanal' and amount_cents = 100;
  if v <> 2 then raise exception 'FALHOU: editar "esta e próximas" mexeu no histórico (% antigas)', v; end if; n := n + 1;
  v := public.delete_transaction_scoped(v_uuid, 'future');
  select count(*) into v from public.transactions where user_id = a1 and description in ('Lanche semanal', 'Lanche novo');
  if v <> 2 or exists (select 1 from public.recurrences where user_id = a1 and active) then
    raise exception 'FALHOU: excluir "esta e próximas" (% restantes)', v; end if; n := n + 1;
  -- saldo agora: 10000 - 2*100 = 9800
  v_json := public.balance_summary();
  if (v_json ->> 'balance_total')::bigint <> 9800 then raise exception 'FALHOU: saldo após recorrência %', v_json; end if; n := n + 1;

  -- ---------- metas e reservas ----------
  insert into public.goals (user_id, title, target_cents, deadline) values (a1, 'Fone', 5000, private.today_br() + 30) returning id into g1;
  begin insert into public.goals (user_id, title, target_cents, deadline) values (a1, 'Passado', 100, private.today_br() - 1);
        raise exception 'FALHOU: meta com prazo no passado';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin insert into public.goal_reservation_events (user_id, goal_id, kind, amount_cents) values (a1, g1, 'reserva', 100);
        raise exception 'FALHOU: cliente inseriu evento de reserva direto';
  exception when insufficient_privilege then n := n + 1; end;
  begin update public.goals set status = 'concluida' where id = g1; raise exception 'FALHOU: cliente mudou status direto';
  exception when insufficient_privilege then n := n + 1; end;
  v_json := public.reserve_goal(g1, 3000, 'chave-reserva-0001');
  v_json := public.reserve_goal(g1, 3000, 'chave-reserva-0001');   -- repetição idempotente
  if not (v_json ->> 'duplicate')::boolean then raise exception 'FALHOU: idempotência da reserva'; end if; n := n + 1;
  begin perform public.reserve_goal(g1, 999, 'chave-reserva-0001'); raise exception 'FALHOU: chave reaproveitada com outro valor';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  v_json := public.balance_summary();
  if (v_json ->> 'balance_total')::bigint <> 9800 or (v_json ->> 'reserved')::bigint <> 3000 or (v_json ->> 'available')::bigint <> 6800 then
    raise exception 'FALHOU: reservar alterou saldo total ou cálculo errado %', v_json; end if; n := n + 1;
  begin perform public.reserve_goal(g1, 6801); raise exception 'FALHOU: reserva acima do disponível';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin perform public.withdraw_goal(g1, 3001); raise exception 'FALHOU: retirada maior que a reserva';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  perform public.reserve_goal(g1, 2000);
  select state into v_state from public.goal_overview where id = g1;
  if v_state <> 'pronta' then raise exception 'FALHOU: estado da meta (%)', v_state; end if; n := n + 1;
  perform public.complete_goal(g1);
  begin perform public.complete_goal(g1); raise exception 'FALHOU: concluiu duas vezes';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  if (public.balance_summary() ->> 'reserved')::bigint <> 5000 then raise exception 'FALHOU: concluir liberou reserva'; end if; n := n + 1;
  perform public.withdraw_goal(g1, 1000);
  perform public.delete_goal(g1);
  v_json := public.balance_summary();
  if (v_json ->> 'reserved')::bigint <> 0 or (v_json ->> 'balance_total')::bigint <> 9800 then raise exception 'FALHOU: excluir meta %', v_json; end if; n := n + 1;

  -- ---------- FinBot e comprovantes ----------
  insert into public.ai_conversations (user_id) values (a1) returning id into conv;
  insert into public.ai_messages (conversation_id, user_id, content, request_key) values (conv, a1, 'Oi', 'req-0000001');
  begin insert into public.ai_messages (conversation_id, user_id, role, content) values (conv, a1, 'assistant', 'Forjada');
        raise exception 'FALHOU: cliente forjou resposta da IA';
  exception when insufficient_privilege then n := n + 1; end;
  begin insert into public.ai_messages (conversation_id, user_id, content, request_key) values (conv, a1, 'Outro texto', 'req-0000001');
        raise exception 'FALHOU: chave de idempotência repetida';
  exception when unique_violation then n := n + 1; end;

  -- ---------- educação: gabarito e vídeo ----------
  begin perform public.submit_lesson('poupanca', 'o-que-e', '[1, [0,1,1,0,1,0], [0,2,4]]'); raise exception 'FALHOU: aula liberada sem vídeo';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  select count(*) into v from public.education_activities;
  if v <> 0 then raise exception 'FALHOU: atividades visíveis antes do vídeo (%)', v; end if; n := n + 1;
  select count(*) into v from public.education_lessons;
  if v <> 12 then raise exception 'FALHOU: títulos das aulas deveriam ser visíveis (%)', v; end if; n := n + 1;
  v_json := public.video_start('poupanca'); v_token := v_json ->> 'token';
  v_json := public.video_tick('poupanca', v_token, 30);   -- salto na barra: recusado
  if (v_json ->> 'accepted')::boolean or (v_json ->> 'completed')::boolean then raise exception 'FALHOU: salto no vídeo aceito %', v_json; end if; n := n + 1;
  begin perform public.video_tick('poupanca', 'token-falso-000000000000000000', 1); raise exception 'FALHOU: token falso aceito';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  -- simula reprodução real: recua o início da sessão (o tempo de parede é conferido no banco)
  execute 'reset role';
  update public.education_video_progress set session_started_at = session_started_at - interval '60 seconds' where user_id = a1;
  execute 'set local role authenticated';
  v_pos := 0;
  while v_pos < 36.5 loop
    v_pos := least(36.5, v_pos + 5);
    v_json := public.video_tick('poupanca', v_token, v_pos);
  end loop;
  if not (v_json ->> 'completed')::boolean then raise exception 'FALHOU: vídeo assistido não concluiu %', v_json; end if; n := n + 1;
  select count(*) into v from public.education_activities a join public.education_lessons l on l.id = a.lesson_id
    join public.education_modules m on m.id = l.module_id where m.key = 'poupanca';
  if v <> 11 then raise exception 'FALHOU: atividades do módulo liberado (%)', v; end if; n := n + 1;
  v_json := public.check_activity('poupanca', 'vantagens', 1, '"4.500"');
  if not (v_json ->> 'ok')::boolean then raise exception 'FALHOU: "4.500" deveria valer 4500 %', v_json; end if; n := n + 1;
  v_json := public.check_activity('poupanca', 'vantagens', 1, '"4500,00"');
  if not (v_json ->> 'ok')::boolean then raise exception 'FALHOU: "4500,00"'; end if; n := n + 1;
  begin perform public.check_activity('poupanca', 'vantagens', 1, '"abc"'); raise exception 'FALHOU: resposta inválida aceita';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  v_json := public.submit_lesson('poupanca', 'o-que-e', '[0, [0,1,1,0,1,0], [0,2,4]]');   -- 1ª errada, 2 certas: 67%
  if (v_json ->> 'score')::int <> 67 or (v_json ->> 'completed')::boolean then raise exception 'FALHOU: nota 67 %', v_json; end if; n := n + 1;
  v_json := public.submit_lesson('poupanca', 'o-que-e', '[1, [0,1,1,0,1,0], [0,2,4]]');
  if (v_json ->> 'score')::int <> 100 or not (v_json ->> 'completed')::boolean or (v_json ->> 'attempts')::int <> 2 then
    raise exception 'FALHOU: aprovação %', v_json; end if; n := n + 1;
  v_json := public.submit_lesson('poupanca', 'o-que-e', '[0, [1,1,1,1,1,1], [1]]');   -- nota baixa depois não desfaz conclusão
  select status, best_score into v_txt, v from public.education_progress where user_id = a1 and lesson_id = lesson_poup;
  if v_txt <> 'concluida' or v <> 100 then raise exception 'FALHOU: melhor nota/conclusão preservadas (%/%)', v_txt, v; end if; n := n + 1;
  begin insert into public.education_progress (user_id, lesson_id, status) values (a1, lesson_poup, 'concluida');
        raise exception 'FALHOU: cliente gravou progresso direto';
  exception when insufficient_privilege then n := n + 1; end;
  -- orçamento: percentual negativo recusado
  execute 'reset role';
  update public.education_video_progress p set completed = true, completed_at = now(), watched_seconds = 40
   where user_id = a1 and video_id <> (select v2.id from public.education_video_assets v2 join public.education_modules m on m.id = v2.module_id where m.key = 'poupanca');
  insert into public.education_video_progress (user_id, video_id, completed, completed_at, watched_seconds)
  select a1, v2.id, true, now(), v2.duration_seconds from public.education_video_assets v2 on conflict do nothing;
  execute 'set local role authenticated';
  v_json := public.check_activity('planejamento', 'plano', 0, '[110, -10, 0]');
  if (v_json ->> 'ok')::boolean then raise exception 'FALHOU: orçamento com percentual negativo aceito'; end if; n := n + 1;
  v_json := public.check_activity('planejamento', 'plano', 0, '[50, 30, 20]');
  if not (v_json ->> 'ok')::boolean then raise exception 'FALHOU: orçamento 50/30/20'; end if; n := n + 1;

  -- ---------- aluno 2 não vê nada do aluno 1 ----------
  perform set_config('request.jwt.claims', json_build_object('sub', a2, 'role', 'authenticated')::text, true);
  perform public.complete_onboarding('Aluno Dois', 'aluno', true);
  select count(*) into v from public.transactions; if v <> 0 then raise exception 'FALHOU: aluno 2 viu transações do aluno 1'; end if; n := n + 1;
  select count(*) into v from public.goals; if v <> 0 then raise exception 'FALHOU: aluno 2 viu metas'; end if; n := n + 1;
  select count(*) into v from public.ai_messages; if v <> 0 then raise exception 'FALHOU: aluno 2 viu mensagens'; end if; n := n + 1;
  select count(*) into v from public.profiles where id = a1; if v <> 0 then raise exception 'FALHOU: aluno 2 viu perfil do aluno 1'; end if; n := n + 1;
  select count(*) into v from public.categories where user_id = a1; if v <> 0 then raise exception 'FALHOU: aluno 2 viu categoria pessoal'; end if; n := n + 1;
  update public.transactions set amount_cents = 1 where id = tx1; get diagnostics v = row_count;
  if v <> 0 then raise exception 'FALHOU: aluno 2 alterou transação alheia'; end if; n := n + 1;
  delete from public.transactions where id = tx1; get diagnostics v = row_count;
  if v <> 0 then raise exception 'FALHOU: aluno 2 apagou transação alheia'; end if; n := n + 1;
  begin perform public.reserve_goal(g1, 1); raise exception 'FALHOU: aluno 2 reservou na meta alheia';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin perform public.delete_transaction_scoped(tx1, 'single'); raise exception 'FALHOU: aluno 2 apagou via RPC';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin insert into public.ai_messages (conversation_id, user_id, content) values (conv, a2, 'invasão');
        raise exception 'FALHOU: aluno 2 escreveu na conversa do aluno 1';
  exception when foreign_key_violation or insufficient_privilege then n := n + 1; end;
  execute 'reset role';
  select id into cat_a2 from public.categories where user_id = a1 limit 1;
  execute 'set local role authenticated';
  begin insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
        values (a2, 'despesa', cat_a2, 'Categoria alheia', 100, private.today_br());
        raise exception 'FALHOU: usou categoria pessoal de outra conta';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  insert into public.goals (user_id, title, target_cents, deadline) values (a2, 'Meta A2', 1000, private.today_br() + 5) returning id into g_a2;
  begin perform public.reserve_goal(g_a2, 1); raise exception 'FALHOU: reservou sem saldo';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin insert into public.classes (teacher_id, name) values (a2, 'Turma falsa'); raise exception 'FALHOU: aluno criou turma';
  exception when insufficient_privilege or sqlstate 'PGRST' then n := n + 1; end;

  -- ---------- professores e turmas ----------
  perform set_config('request.jwt.claims', json_build_object('sub', p1, 'role', 'authenticated')::text, true);
  perform public.complete_onboarding('Prof Um', 'professor', true);
  insert into public.classes (teacher_id, name) values (p1, 'Turma A') returning id, join_code into cls, code;
  insert into public.assignments (class_id, teacher_id, lesson_id, due_date) values (cls, p1, lesson_poup, private.today_br() + 2) returning id into aid;
  begin insert into public.assignments (class_id, teacher_id, lesson_id, content_type) values (cls, p1, lesson_poup, 'video');
        raise exception 'FALHOU: tipo de atividade inválido';
  exception when check_violation then n := n + 1; end;
  begin insert into public.assignments (class_id, teacher_id, lesson_id, due_date) values (cls, p1, lesson_poup, private.today_br() - 1);
        raise exception 'FALHOU: prazo passado aceito';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin perform public.join_class(code); raise exception 'FALHOU: professor entrou como aluno';
  exception when sqlstate 'PGRST' then n := n + 1; end;

  perform set_config('request.jwt.claims', json_build_object('sub', p2, 'role', 'authenticated')::text, true);
  perform public.complete_onboarding('Prof Dois', 'professor', true);
  insert into public.classes (teacher_id, name) values (p2, 'Turma B') returning id into cls2;
  select count(*) into v from public.classes where id = cls; if v <> 0 then raise exception 'FALHOU: professor 2 viu turma do professor 1'; end if; n := n + 1;
  update public.classes set name = 'Invadida' where id = cls; get diagnostics v = row_count;
  if v <> 0 then raise exception 'FALHOU: professor 2 editou turma alheia'; end if; n := n + 1;
  begin insert into public.assignments (class_id, teacher_id, lesson_id) values (cls, p2, lesson_poup); raise exception 'FALHOU: atribuiu em turma alheia';
  exception when insufficient_privilege or foreign_key_violation then n := n + 1; end;

  -- alunos entram (aluno 1 já concluiu a aula: conta como entregue; aluno 2 fica pendente)
  perform set_config('request.jwt.claims', json_build_object('sub', a1, 'role', 'authenticated')::text, true);
  v_json := public.preview_class(lower(code));
  if (v_json -> 'class' ->> 'name') <> 'Turma A' then raise exception 'FALHOU: prévia da turma %', v_json; end if; n := n + 1;
  perform public.join_class(code);
  begin perform public.join_class(code); raise exception 'FALHOU: entrou duas vezes';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  select status into v_txt from public.assignment_progress where assignment_id = aid and student_id = a1;
  if v_txt <> 'concluida' then raise exception 'FALHOU: aula já concluída não contou (%)', v_txt; end if; n := n + 1;
  perform set_config('request.jwt.claims', json_build_object('sub', a2, 'role', 'authenticated')::text, true);
  perform public.join_class(code);
  select count(*) into v from public.assignment_progress; if v <> 1 then raise exception 'FALHOU: aluno 2 vê entregas alheias (%)', v; end if; n := n + 1;
  select count(*) into v from public.class_memberships; if v <> 1 then raise exception 'FALHOU: aluno 2 vê vínculos alheios (%)', v; end if; n := n + 1;
  select count(*) into v from public.profiles where id = a1; if v <> 0 then raise exception 'FALHOU: colega de turma viu perfil de colega'; end if; n := n + 1;
  select count(*) into v from public.profiles where id = p1; if v <> 1 then raise exception 'FALHOU: aluno não vê nome do professor'; end if; n := n + 1;

  -- professor 1: resultados educativos sim; dados financeiros nunca diretamente
  perform set_config('request.jwt.claims', json_build_object('sub', p1, 'role', 'authenticated')::text, true);
  select count(*) into v from public.assignment_progress where class_id = cls; if v <> 2 then raise exception 'FALHOU: professor não vê entregas (%)', v; end if; n := n + 1;
  select count(*) into v from public.transactions; if v <> 0 then raise exception 'FALHOU: professor leu transações'; end if; n := n + 1;
  select count(*) into v from public.goals; if v <> 0 then raise exception 'FALHOU: professor leu metas'; end if; n := n + 1;
  select count(*) into v from public.ai_messages; if v <> 0 then raise exception 'FALHOU: professor leu conversas'; end if; n := n + 1;
  select count(*) into v from public.receipts; if v <> 0 then raise exception 'FALHOU: professor leu comprovantes'; end if; n := n + 1;
  v_json := public.class_participants(cls);
  if jsonb_array_length(v_json) <> 2 then raise exception 'FALHOU: participantes %', v_json; end if; n := n + 1;
  v_json := public.class_financial_summary(cls);
  if jsonb_array_length(v_json -> 'items') <> 0 then raise exception 'FALHOU: resumo sem consentimento %', v_json; end if; n := n + 1;
  update public.class_memberships set share_financial = true where class_id = cls; get diagnostics v = row_count;
  if v <> 0 then raise exception 'FALHOU: professor alterou consentimento'; end if; n := n + 1;

  perform set_config('request.jwt.claims', json_build_object('sub', a1, 'role', 'authenticated')::text, true);
  update public.class_memberships set share_financial = true where class_id = cls and student_id = a1;
  perform set_config('request.jwt.claims', json_build_object('sub', p1, 'role', 'authenticated')::text, true);
  v_json := public.class_financial_summary(cls, private.today_br() - 60, private.today_br());
  if jsonb_array_length(v_json -> 'items') <> 1 or (v_json -> 'items' -> 0 ->> 'receitas')::bigint <> 10000
     or (v_json -> 'items' -> 0 ->> 'despesas')::bigint <> 200 or (v_json -> 'items' -> 0) ? 'description' then
    raise exception 'FALHOU: resumo autorizado %', v_json; end if; n := n + 1;
  select count(*) into v from public.transactions; if v <> 0 then raise exception 'FALHOU: consentimento abriu SELECT em transações'; end if; n := n + 1;
  -- revogação: efeito imediato na próxima chamada (mesmo "JWT")
  perform set_config('request.jwt.claims', json_build_object('sub', a1, 'role', 'authenticated')::text, true);
  update public.class_memberships set share_financial = false where class_id = cls and student_id = a1;
  perform set_config('request.jwt.claims', json_build_object('sub', p1, 'role', 'authenticated')::text, true);
  v_json := public.class_financial_summary(cls);
  if jsonb_array_length(v_json -> 'items') <> 0 then raise exception 'FALHOU: revogação não imediata'; end if; n := n + 1;
  perform set_config('request.jwt.claims', json_build_object('sub', p2, 'role', 'authenticated')::text, true);
  begin perform public.class_financial_summary(cls); raise exception 'FALHOU: professor de outra turma viu resumo';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  begin perform public.class_participants(cls); raise exception 'FALHOU: professor de outra turma viu participantes';
  exception when sqlstate 'PGRST' then n := n + 1; end;

  -- código renovado/desativado; aluno sai da turma
  perform set_config('request.jwt.claims', json_build_object('sub', p1, 'role', 'authenticated')::text, true);
  v_txt := public.renew_class_code(cls);
  update public.classes set code_active = false where id = cls;
  perform set_config('request.jwt.claims', json_build_object('sub', a2, 'role', 'authenticated')::text, true);
  begin perform public.preview_class(v_txt); raise exception 'FALHOU: código desativado aceito';
  exception when sqlstate 'PGRST' then n := n + 1; end;
  delete from public.class_memberships where class_id = cls and student_id = a2;
  select count(*) into v from public.assignment_progress; if v <> 0 then raise exception 'FALHOU: sair não removeu entregas'; end if; n := n + 1;

  -- ---------- lembretes sem duplicar ----------
  perform set_config('request.jwt.claims', json_build_object('sub', a2, 'role', 'authenticated')::text, true);
  insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
  values (a2, 'despesa', cat_alim, 'Gasto', 500, private.today_br());
  v_json := public.my_notifications(1); v_json := public.my_notifications(1);
  select count(*) into v from public.notifications where event_key like 'spending:%';
  if v <> 1 then raise exception 'FALHOU: lembrete de gastos duplicado ou ausente (%)', v; end if; n := n + 1;
  perform public.mark_all_notifications_read(); v_json := public.my_notifications(1);
  if (v_json ->> 'unread')::int <> 0 then raise exception 'FALHOU: marcar como lido recriou aviso %', v_json; end if; n := n + 1;
  update public.notifications set read_at = null; select count(*) into v from public.notifications where read_at is null;
  if v <> 0 then raise exception 'FALHOU: cliente desmarcou leitura'; end if; n := n + 1;

  -- ---------- indicadores ----------
  v_json := public.market_indicators();
  if jsonb_array_length(v_json -> 'unavailable') <> 4 then raise exception 'FALHOU: indicadores sem dados deveriam ser indisponíveis %', v_json; end if; n := n + 1;

  -- ---------- painel ----------
  perform set_config('request.jwt.claims', json_build_object('sub', a1, 'role', 'authenticated')::text, true);
  v_json := public.dashboard();
  if jsonb_array_length(v_json -> 'months') <> 6 or (v_json ->> 'balance_total')::bigint <> 9800 then raise exception 'FALHOU: painel %', v_json; end if; n := n + 1;

  execute 'reset role';
  select count(*) into v_errors from private.job_runs where status = 'erro';
  raise exception 'TESTES_OK: % verificações aprovadas', n;
end
$test$;
