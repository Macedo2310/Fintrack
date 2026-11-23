# Auditoria e plano — FinTrack 0.6

## 1. Arquivos e versões encontrados

| Material | Data | O que é |
|---|---|---|
| `FinTrack-GitHub-Pages-4-Videos.zip` (enviado) | 29/10/2026 | Edição **estática** para GitHub Pages. Mesmo front-end da 0.5, com camadas `pages-common.js`/`pages-services.js` que simulam a API no `localStorage`. Seu README diz: "A versão com backend foi preservada separadamente". |
| `Downloads/.../FinTrack-0.5-videos-introdutorios.zip` | 27/10/2026 | Versão **FastAPI + SQLite** com os mesmos 4 vídeos. |
| 0.4, 0.3, `fintrack-v6-backend`, `fintrack-recriado` | out/2026 | Versões anteriores da linha com backend. |

Os 4 MP4 são idênticos byte a byte nas duas versões (SHA-256 em `VERSAO.txt`/`LEIA_PRIMEIRO.md`).

**Base usada: FinTrack 0.5 (FastAPI + SQLite).** Motivo: os requisitos (persistência real, correção no servidor,
bloqueio de vídeo não burlável, permissões no backend) são impossíveis na edição estática. Da edição Pages
foram trazidas as melhorias que não dependem do `localStorage`: links reais de Termos/Privacidade no rodapé,
registro do vídeo ao sair da página (`pagehide`) e a menção aos vídeos na landing.

## 2. O que já funcionava na 0.5

Cadastro/login com scrypt e cookie HttpOnly, limite de tentativas, transações em centavos, recorrência com
índice anti-duplicidade, metas com reserva em `BEGIN IMMEDIATE`, curso 4×12 com correção no servidor e 70%,
vídeos com verificação de tempo no servidor, conversas do FinBot com chave anti-duplicidade, turmas com código,
compartilhamento por turma, lembretes deduplicados, indicadores do BCB com cache, migração v1 com backup, WAL.

## 3. Depende de configuração externa

IA do FinBot (OpenAI ou compatível), SMTP (recuperação de senha e resumo semanal), serviço de leitura de
comprovantes, hospedagem com Python + HTTPS + disco persistente. Indicadores do BCB dependem da disponibilidade da fonte.

## 4. Incompleto ou quebrado (encontrado na auditoria)

1. Recuperação de senha sem SMTP respondia como se fosse enviar e-mail.
2. FinBot: reusar a mesma chave com outro texto devolvia a resposta antiga (encontrado pelos testes).
3. Exclusão de lançamento recorrente não encerrava a recorrência; sem escopo explícito.
4. Ordenação só por data; busca sem escapar `%` e `_`.
5. Atividades de cálculo: `3.600` era lido como 3,6 (resposta certa marcada como errada); orçamento aceitava percentuais negativos.
6. Turmas: aluno que entrava depois não recebia as atividades; aula já concluída não contava; atribuição por texto livre sem validação; listas em `alert()`; aluno não podia sair da turma.
7. Metas: sem estado (vencida/pronta/concluída); "concluir" repetível; erros sem tratamento na tela.
8. Resumo semanal: o interruptor existia, mas não havia envio implementado.
9. Datas do navegador em UTC (após 21h aparecia o dia seguinte).
10. ~350 linhas de código morto da edição estática com respostas das atividades no JavaScript público.
11. Erros de validação chegavam à tela como `[object Object]`; erro de rede em inglês.
12. Código para Vercel com banco em `/tmp` (disco temporário).
13. Rodapé da landing com links `#` e e-mail de exemplo; FAQ dizia que o FinBot "altera dados com confirmação".
14. Rótulos de formulário não associados aos campos; chat do FinBot estourando a largura em 320 px; lista de conversas oculta no celular; menu móvel da landing sem "Entrar".
15. IPCA/Selic exibidos com "%" duplicado; data da Selic mostrada como vigência futura.
16. Teste antigo (`test_backend.py`) quebrado pela regra dos vídeos; scripts `.cjs` dependem de Node/Playwright.

## 5. Plano executado (preservando dados e rotas)

- Nenhuma rota existente removida; novos campos são aditivos. Migração **v2** versionada com backup automático
  antes (`data/backups/before-v2-*.db`): tabela `weekly_email_log`, índices e preenchimento das pendências de turma.
- Backend: itens 1–8 e 12 corrigidos; `/api/lessons`, `DELETE /api/assignments/{id}`, `DELETE /api/classes/{id}/membership`,
  escopo em `DELETE /api/transactions/{id}?scope=single|future`, estado das metas, saneamento do retorno de comprovantes,
  manipuladores de erro em português, logs sem dados sensíveis.
- Front-end: itens 9–11 e 13–15; modais de atribuição/participantes/resultados; status do FinBot e da análise;
  indicadores com "Atualizado / Antigo / Indisponível"; explicação de saldo total × reservado × disponível.
- Operação: `manage_db.py` com `check`, `backup` (banco + uploads + manifesto), `verify` e `restore`.
- Testes: nova suíte pytest (24 testes) + verificação no navegador. Testes antigos movidos para `tests/legado/`.

## 6. Arquivos alterados

Backend: `app.py`, `backend_services.py`, `education_content.py`, `manage_db.py`.
Front-end: `static/app.js`, `static/app.html`, `static/services.js`, `static/intro-video.js`, `static/mobile-services.css`,
`static/index.html`, `static/login.html`, `static/reset.html`, `static/terms.html`, `static/privacy.html`.
Novos: `tests/conftest.py`, `tests/test_fintrack.py`, `tests/test_backup_restore.py`, `pytest.ini`, `requirements-dev.txt`, `AUDITORIA.md`.
Reescritos: `LEIA_PRIMEIRO.md`, `VALIDACAO.md`, `VERSAO.txt`, `.env.example`, `.gitignore`.
Preservados sem alteração: vídeos, avatares, `coruja.gif`, `app.css`, `avatar.html`, `video_lessons.py`, conteúdo das 12 aulas.

## 7. Situação por recurso

| Recurso | Implementado | Testado localmente | Publicado |
|---|---|---|---|
| Landing, login, cadastro, avatar, perfil | Sim | Sim | Não |
| Recuperação de senha | Sim (exige SMTP) | Só o caminho sem SMTP | Não |
| Dashboard, gráficos, transações, recorrência | Sim | Sim | Não |
| Metas e reservas concorrentes | Sim | Sim | Não |
| Curso, correção, vídeos | Sim | Sim (vídeo completo só no servidor) | Não |
| Turmas, atribuições, privacidade | Sim | Sim | Não |
| FinBot | Sim (exige chave de IA) | Sim, com provedor simulado | Não |
| Indicadores BCB | Sim | Sim, com dados reais nesta data | Não |
| Lembretes no app | Sim | Sim | Não |
| Resumo semanal por e-mail | Sim (exige SMTP) | Sim, com envio simulado | Não |
| Leitura de comprovante | Sim (exige serviço externo) | Só o caminho sem serviço | Não |
| Backup/restauração | Sim | Sim, em ambiente isolado | Não |
| Login com Google | Sim (exige credenciais Google) | Sim, com Google simulado | Não |
