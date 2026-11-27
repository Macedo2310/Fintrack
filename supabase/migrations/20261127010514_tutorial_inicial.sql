-- Tutorial de boas-vindas: aparece uma vez para contas novas; fica registrado na conta (vale em qualquer aparelho).
alter table public.user_settings add column tour_done boolean not null default false;
update public.user_settings set tour_done = true;   -- contas já existentes não veem o tutorial
grant select (tour_done), update (tour_done) on public.user_settings to authenticated;
