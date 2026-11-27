-- "bingo" gerava aviso à toa (ex.: bingo da escola); removido da lista de apostas.
create or replace function private.is_gambling(p_text text)
returns boolean language sql immutable set search_path = '' as $$
  select coalesce(lower(translate(p_text, 'ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç', 'AAAAEEIOOOUCaaaaeeiooouc')) ~
    '\m(bet|bets|aposta|apostas|apostei|apostar|cassino|casino|blaze|tigrinho|fortune ?tiger|roleta|betano|bet365|sportingbet|pixbet|estrela ?bet|esportes da sorte|superbet|novibet|f12 ?bet|betnacional|jogo do bicho|caca ?niquel)\M', false)
$$;
