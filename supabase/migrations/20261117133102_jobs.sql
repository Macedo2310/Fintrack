-- FinTrack · 0010 · Jobs idempotentes e manutenção.
-- Executados pelo pg_cron quando disponível; o backend também pode chamá-los com service_role
-- (uma única instância). Cada execução fica registrada em private.job_runs (monitoramento mínimo).

create or replace function private.run_job(p_job text)
returns int language plpgsql security definer set search_path = '' as $$
declare v_id bigint; n int := 0; k int;
begin
  insert into private.job_runs (job) values (p_job) returning id into v_id;
  begin
    if p_job = 'recorrencias' then
      n := private.generate_due_recurrences(null);
    elsif p_job = 'manutencao' then
      delete from private.rate_limits where at < now() - interval '1 day'; get diagnostics k = row_count; n := n + k;
      n := n + private.purge_receipt_payloads();
      n := n + private.purge_old_education_attempts();
      delete from private.job_runs where started_at < now() - interval '90 days'; get diagnostics k = row_count; n := n + k;
    else
      raise exception 'Job desconhecido: %', p_job;
    end if;
    update private.job_runs set finished_at = clock_timestamp(), status = 'ok', affected = n where id = v_id;
  exception when others then
    update private.job_runs set finished_at = clock_timestamp(), status = 'erro', detail = left(sqlstate || ' ' || sqlerrm, 500) where id = v_id;
  end;
  return n;
end $$;
revoke all on function private.run_job(text) from public, anon, authenticated;
grant execute on function private.run_job(text) to service_role;

-- Público só para o service_role (o backend chama via Data API com a chave secreta).
create or replace function public.run_job(p_job text)
returns int language sql security invoker set search_path = '' as $$ select private.run_job(p_job) $$;
revoke all on function public.run_job(text) from public, anon, authenticated;
grant execute on function public.run_job(text) to service_role;

-- Agenda no pg_cron, se a extensão existir no projeto. Sem pg_cron, o worker do backend chama public.run_job.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    create extension if not exists pg_cron with schema pg_catalog;
    perform cron.schedule('fintrack-recorrencias', '*/15 * * * *', $job$select private.run_job('recorrencias')$job$);
    perform cron.schedule('fintrack-manutencao', '17 3 * * *', $job$select private.run_job('manutencao')$job$);
  else
    raise notice 'pg_cron indisponível: agende public.run_job pelo backend.';
  end if;
end $$;
