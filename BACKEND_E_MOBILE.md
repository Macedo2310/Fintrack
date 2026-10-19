# FinTrack — backend, indicadores e celular

Implementação aplicada ao ZIP V5 na pasta `fintrack-v6-backend`. Veja `LEIA_PRIMEIRO.md` para iniciar esta versão.

## Banco de dados

- SQLite com WAL, chaves estrangeiras, espera de 30 segundos por bloqueios e `synchronous=FULL`.
- Conexões são fechadas ao sair de cada transação, inclusive em erro.
- Migração versionada e transacional, com backup SQLite consistente e verificação de integridade antes da migração v1. A migração é aplicada na próxima inicialização.
- Índices para transações por conta/tipo/data, reservas, metas, sessões, turmas, atividades, conversas e notificações.
- Reservas e retiradas validam o saldo sob bloqueio de escrita; requisições simultâneas não aprovam duas reservas usando o mesmo saldo disponível.
- Recorrências consultam somente itens vencidos, com transação para coordenar concorrência. Datas financeiras seguem Brasília.
- `FINTRACK_DATA_DIR` permite escolher um diretório persistente ou isolar os testes. Sem configuração, o banco local continua em `data/fintrack.db`.

Não copie apenas o arquivo `.db` enquanto o servidor estiver gravando. Use a API de backup:

```powershell
python manage_db.py check
python manage_db.py backup D:\Backups\fintrack-2026-10-18.db
```

Use um destino novo. O backup do banco não inclui fotos e comprovantes: preserve também `data/uploads`. Para restaurar, pare o aplicativo, preserve o diretório atual completo e restaure uma cópia verificada do banco e seus uploads em um diretório novo; aponte `FINTRACK_DATA_DIR` para ele. Nunca substitua um banco aberto nem misture arquivos WAL antigos com um banco restaurado.

SQLite local não transforma `/tmp` da Vercel em armazenamento persistente. Para produção use servidor com volume persistente e backups externos, ou planeje uma migração para PostgreSQL conforme a hospedagem escolhida. Não foi criado serviço de produção nem agendamento externo de backups.

## Cotações e indicadores

`GET /api/market` exige sessão e consulta exclusivamente dados públicos do Banco Central pelo backend:

- Dólar e euro: PTAX de venda do último fechamento disponível nos últimos 14 dias.
- Meta Selic: série SGS 432, percentual ao ano.
- IPCA: série SGS 433, percentual do mês, sem confundir com acumulado em 12 meses.

Fontes: [documentação PTAX](https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/documentacao) e [dados abertos do Banco Central](https://www.bcb.gov.br/acessoinformacao/dadosabertos).

Cache persistente por uma hora, consultas paralelas com timeout de oito segundos, intervalo de cinco minutos antes de repetir falhas, validação dos valores e fallback sinalizado para o último dado salvo. Sem valor salvo, a interface indica indisponibilidade. Nenhum dado financeiro pessoal é enviado ao provedor. O botão Atualizar respeita o cache e o intervalo de falha.

Validação externa em 18/10/2026: USD e EUR retornaram fechamentos reais de 16/10. SGS/ Selic e IPCA responderam com erro interno ou timeout, inclusive na tentativa de consulta por intervalo; os dois indicadores estão implementados, mas o retorno real não pôde ser confirmado nesta sessão. O fallback foi testado com falhas simuladas em banco isolado.

## Lembretes

Nova página Lembretes e contador na barra superior. Histórico persistente por conta, leitura individual/em lote e paginação de 30 itens.

- Metas ativas: prazo em até sete dias, prazo vencido ou reserva suficiente para concluir.
- Aulas: lembrete semanal para aulas em andamento. Atividades de turma: prazo em até três dias ou vencido, enquanto pendentes.
- Gastos: alertas em 80% e 100% do limite mensal escolhido; sem limite, avisa quando despesas do mês superam receitas registradas até hoje.
- Preferências para aulas e gastos; metas respeitam também a preferência existente de alertas de metas.
- Unicidade de evento por usuário evita duplicação. Ler um aviso não o recria no próximo polling. Alterar o limite ou prazo pode gerar um novo evento correspondente à nova configuração.
- Preferências desativam novos avisos; o histórico antigo permanece visível.

Os avisos são calculados ao consultar a central, ao entrar/voltar ao app e a cada minuto enquanto a página está visível. Não há Web Push, envio de e-mail nem execução com o navegador fechado nesta entrega.

## Celular

Inputs de pelo menos 16px em telas de toque, controles principais de pelo menos 44px, suporte a áreas seguras, viewport dinâmico para diálogos, menu rolável, contenção de scroll e layout responsivo para indicadores e lembretes.

Para abrir no celular pela mesma rede, execute com `HOST=0.0.0.0`, `PORT=8010` e acesse o IP local do computador. A porta padrão continua restrita a `127.0.0.1`. Fotos e notificações do sistema podem exigir HTTPS conforme o navegador. Não foi feita publicação.

## Verificação

- 11 grupos de regressão existentes aprovados em banco isolado.
- 7 grupos novos: autenticação, isolamento/leitura/deduplicação, concorrência de reservas, orçamento/preferências, aulas, migração/índices/backup e cache/falhas da API.
- Edge automatizado em 320, 390, 768 e 1366px: oito páginas em cada largura, sem overflow horizontal ou exceções JavaScript; preferências salvas, menu móvel e modal de transação verificados.
- Scripts e resultados em `tests/test_backend.py`, `tests/test_mobile.cjs`, `tests/backend-results.json` e `tests/mobile-test-results.json`.

Emulação não valida teclado virtual, notch, toque e comportamento do Safari em um aparelho físico. Esses pontos ainda precisam de teste real em Android/iPhone antes de afirmar compatibilidade perfeita.
