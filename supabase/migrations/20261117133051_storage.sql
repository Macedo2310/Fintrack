-- FinTrack · 0009 · Storage: buckets privados e políticas.
-- Caminho por usuário: <user_id>/<arquivo>. Nenhum bucket é público.
-- Upload, substituição e exclusão de fotos e comprovantes são feitos SOMENTE pelo backend (service_role),
-- depois de decodificar a imagem com Pillow (o MIME declarado não basta). Por isso não há políticas de
-- INSERT/UPDATE/DELETE para authenticated nesses buckets: sem política, o Storage recusa.
-- Leitura: comprovante só pelo dono; foto de avatar pelo dono e por professor/aluno da mesma turma;
-- vídeos do curso por qualquer conta autenticada (a liberação das aulas é controlada no banco).
-- Assets públicos da marca continuam servidos pelo próprio app (pasta static); não há bucket público.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
  ('avatars', 'avatars', false, 614400, array['image/jpeg', 'image/png', 'image/webp']),
  ('receipts', 'receipts', false, 5242880, array['image/jpeg', 'image/png', 'image/webp']),
  ('education-videos', 'education-videos', false, 20971520, array['video/mp4'])
on conflict (id) do update
  set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

create or replace function private.try_uuid(p text)
returns uuid language plpgsql immutable set search_path = '' as $$
begin
  return p::uuid;
exception when invalid_text_representation then
  return null;
end $$;
revoke all on function private.try_uuid(text) from public, anon;
grant execute on function private.try_uuid(text) to authenticated, service_role;

create policy "fintrack_avatars_read_own_or_classmate" on storage.objects for select to authenticated
  using (bucket_id = 'avatars' and (
    (storage.foldername(name))[1] = (select auth.uid())::text
    or private.shares_class(private.try_uuid((storage.foldername(name))[1]))));

create policy "fintrack_receipts_read_own" on storage.objects for select to authenticated
  using (bucket_id = 'receipts' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "fintrack_videos_read_authenticated" on storage.objects for select to authenticated
  using (bucket_id = 'education-videos');
