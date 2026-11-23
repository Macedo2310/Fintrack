-- FinTrack · 0006 · FinBot (conversas) e comprovantes.
-- Privados: só o dono lê. Professores NÃO têm acesso, mesmo com resumo financeiro autorizado.
-- A resposta da IA é gravada pelo backend (service_role): o cliente só insere mensagens com papel 'user'.
-- Chaves de IA/OCR ficam no ambiente do backend, nunca no banco nem no navegador.

create table public.ai_conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  title      text not null default 'Nova conversa' check (char_length(title) between 1 and 80),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ai_conversations_id_user_uk unique (id, user_id)
);
create index ai_conversations_user_updated_idx on public.ai_conversations (user_id, updated_at desc);
create trigger ai_conversations_touch before update on public.ai_conversations for each row execute function private.touch_updated_at();

create table public.ai_messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  user_id         uuid not null default auth.uid(),
  role            text not null default 'user' check (role in ('user', 'assistant')),
  content         text not null check (char_length(content) between 1 and 20000),
  -- Chave de idempotência: a mesma tentativa não gera duas mensagens nem duas chamadas à IA.
  request_key     text check (char_length(request_key) between 8 and 120),
  created_at      timestamptz not null default now(),
  constraint ai_messages_user_content_limit check (role = 'assistant' or char_length(content) <= 4000),
  constraint ai_messages_conversation_owner_fk foreign key (conversation_id, user_id)
    references public.ai_conversations (id, user_id) on delete cascade,
  constraint ai_messages_request_key_uk unique (user_id, request_key)
);
create index ai_messages_conversation_created_idx on public.ai_messages (conversation_id, created_at);

create or replace function private.ai_message_touch_conversation()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  update public.ai_conversations set updated_at = now() where id = new.conversation_id and user_id = new.user_id;
  return new;
end $$;
create trigger ai_messages_touch_conversation after insert on public.ai_messages
  for each row execute function private.ai_message_touch_conversation();

create table public.receipts (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (id) on delete cascade,
  storage_bucket text not null default 'receipts' check (storage_bucket = 'receipts'),
  storage_path   text not null unique,
  mime           text not null check (mime in ('image/jpeg', 'image/png', 'image/webp')),
  original_name  text not null check (char_length(original_name) between 1 and 200),
  size_bytes     int not null check (size_bytes between 1 and 5242880),
  sha256         text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  created_at     timestamptz not null default now(),
  constraint receipts_path_of_owner check (storage_path like user_id::text || '/%'),
  constraint receipts_user_sha_uk unique (user_id, sha256)
);
create index receipts_user_created_idx on public.receipts (user_id, created_at desc);

-- Resultado da leitura automática: sugestão para revisão, nunca vira transação sozinho.
-- raw_payload é retido por 30 dias (private.purge_receipt_payloads).
create table private.receipt_analyses (
  id          uuid primary key default gen_random_uuid(),
  receipt_id  uuid not null references public.receipts (id) on delete cascade,
  user_id     uuid not null references public.profiles (id) on delete cascade,
  provider    text not null,
  status      text not null check (status in ('ok', 'erro')),
  suggestion  jsonb not null default '{}',
  raw_payload jsonb check (raw_payload is null or pg_column_size(raw_payload) <= 200000),
  created_at  timestamptz not null default now()
);
create index receipt_analyses_receipt_idx on private.receipt_analyses (receipt_id);
create index receipt_analyses_payload_age_idx on private.receipt_analyses (created_at) where raw_payload is not null;

create or replace function private.purge_receipt_payloads()
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  update private.receipt_analyses set raw_payload = null where raw_payload is not null and created_at < now() - interval '30 days';
  get diagnostics n = row_count; return n;
end $$;

-- ===== Privilégios =====
alter table public.ai_conversations enable row level security;
alter table public.ai_messages enable row level security;
alter table public.receipts enable row level security;
alter table private.receipt_analyses enable row level security;
revoke all on public.ai_conversations, public.ai_messages, public.receipts from anon, authenticated;
revoke all on private.receipt_analyses from public, anon, authenticated;

grant select, delete on public.ai_conversations to authenticated;
grant insert (user_id, title) on public.ai_conversations to authenticated;
grant update (title) on public.ai_conversations to authenticated;
grant select on public.ai_messages to authenticated;
grant insert (conversation_id, user_id, content, request_key) on public.ai_messages to authenticated;  -- role fica 'user'
grant select, delete on public.receipts to authenticated;   -- inclusão só pelo backend após validar a imagem
grant all on public.ai_conversations, public.ai_messages, public.receipts to service_role;
grant all on private.receipt_analyses to service_role;

create policy ai_conversations_select_own on public.ai_conversations for select to authenticated using (user_id = (select auth.uid()));
create policy ai_conversations_insert_own on public.ai_conversations for insert to authenticated with check (user_id = (select auth.uid()));
create policy ai_conversations_update_own on public.ai_conversations for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy ai_conversations_delete_own on public.ai_conversations for delete to authenticated using (user_id = (select auth.uid()));

create policy ai_messages_select_own on public.ai_messages for select to authenticated using (user_id = (select auth.uid()));
create policy ai_messages_insert_own_user_role on public.ai_messages for insert to authenticated
  with check (user_id = (select auth.uid()) and role = 'user');

create policy receipts_select_own on public.receipts for select to authenticated using (user_id = (select auth.uid()));
create policy receipts_delete_own on public.receipts for delete to authenticated using (user_id = (select auth.uid()));

revoke all on function private.ai_message_touch_conversation(), private.purge_receipt_payloads() from public, anon;
grant execute on function private.ai_message_touch_conversation() to authenticated, service_role;
grant execute on function private.purge_receipt_payloads() to service_role;
