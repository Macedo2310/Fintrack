-- Indicadores: considerados desatualizados após 15 minutos (antes: 1 hora), para o backend
-- buscar o boletim PTAX mais recente do dia com mais frequência.
create or replace function private.market_indicators_view()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'items', coalesce((select jsonb_agg(jsonb_build_object(
        'key', m.key, 'label', m.label, 'value', m.value, 'unit', m.unit, 'period_kind', m.period_kind,
        'observed_at', m.observed_on, 'reference', m.reference_label, 'source', m.source, 'source_url', m.source_url,
        'fetched_at', m.fetched_at, 'stale', m.fetched_at < now() - interval '15 minutes',
        'status', case when m.fetched_at < now() - interval '15 minutes' then 'antigo' else 'atualizado' end)
        order by array_position(array['USD','EUR','SELIC','IPCA'], m.key))
      from private.market_indicators m), '[]'),
    'unavailable', coalesce((select jsonb_agg(k) from unnest(array['USD','EUR','SELIC','IPCA']) k
                              where not exists (select 1 from private.market_indicators m where m.key = k)), '[]'))
$$;
revoke all on function private.market_indicators_view() from public, anon;
grant execute on function private.market_indicators_view() to authenticated;
