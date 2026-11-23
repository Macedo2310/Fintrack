-- FinTrack · 0012 · Ajustes apontados pelos advisors do Supabase após a primeira aplicação.
-- 1) Índices que cobrem as FKs compostas (também usados nas consultas reais).
-- 2) Chave primária em private.rate_limits.
-- 3) Uma única política de SELECT por tabela em profiles e user_avatars (menos avaliação por linha).

drop index if exists public.transactions_category_idx;
create index transactions_category_type_idx on public.transactions (category_id, type);
drop index if exists public.recurrences_category_idx;
create index recurrences_category_type_idx on public.recurrences (category_id, type);
-- Edição/exclusão "esta e as próximas" filtra por recorrência + dono + data.
create index transactions_recurrence_user_date_idx on public.transactions (recurrence_id, user_id, occurred_on)
  where recurrence_id is not null;

drop index if exists public.ai_messages_conversation_created_idx;
create index ai_messages_conversation_user_created_idx on public.ai_messages (conversation_id, user_id, created_at);

create index assignments_class_teacher_idx on public.assignments (class_id, teacher_id);
create index assignment_progress_assignment_class_idx on public.assignment_progress (assignment_id, class_id);
create index receipt_analyses_user_idx on private.receipt_analyses (user_id);

alter table private.rate_limits add column id bigint generated always as identity primary key;

drop policy profiles_select_own on public.profiles;
drop policy profiles_select_classmates on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
  using (id = (select auth.uid()) or private.shares_class(id));

drop policy user_avatars_select_own on public.user_avatars;
drop policy user_avatars_select_classmates on public.user_avatars;
create policy user_avatars_select on public.user_avatars for select to authenticated
  using (user_id = (select auth.uid()) or private.shares_class(user_id));
