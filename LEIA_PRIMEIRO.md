# FinTrack 0.6

Plataforma brasileira de organização e educação financeira para estudantes e professores.
Backend FastAPI + SQLite, com contas, transações, metas, curso de 4 níveis e 12 aulas,
quatro vídeos introdutórios, FinBot, turmas, lembretes e indicadores do Banco Central.

A FinTrack **não é banco, carteira digital nem corretora**: não guarda nem movimenta dinheiro.
Os valores são os que cada pessoa registra.

## Iniciar no Windows

Requisito: Python 3.12 ou superior (testado com 3.14.8).

Opção 1: dê dois cliques em `INICIAR_FINTRACK.bat` e abra **http://127.0.0.1:8010**.

Opção 2, no PowerShell dentro desta pasta:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

O banco é criado vazio em `data/fintrack.db` na primeira execução. Não há contas de demonstração.

### Usar no celular da mesma rede

```powershell
$env:HOST = '0.0.0.0'
.venv\Scripts\python.exe run.py
```

Abra `http://IP-DO-COMPUTADOR:8010` no celular (o firewall precisa liberar a porta).

## Variáveis de ambiente

Veja `.env.example`. Copie para `.env` só no desenvolvimento. Nenhuma chave vai para o JavaScript público.

| Variável | Obrigatória? | Para quê |
|---|---|---|
| `FINTRACK_DATA_DIR` | Em produção | Pasta em disco persistente para banco e uploads |
| `COOKIE_SECURE=1` | Em produção (HTTPS) | Cookie de sessão só por HTTPS |
| `APP_BASE_URL` | Para e-mail | Endereço público usado no link de redefinição de senha |
| `OPENAI_API_KEY` ou `AI_PROVIDER_URL` + `AI_API_KEY` + `AI_MODEL` | Opcional | Respostas do FinBot e análise de gastos |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Opcional | Recuperação de senha e resumo semanal |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (+ `APP_BASE_URL`) | Opcional | Botão “Continuar com Google” |
| `RECEIPT_ANALYZER_URL`, `RECEIPT_ANALYZER_KEY` | Opcional | Leitura automática de comprovantes |
| `PROFESSOR_SIGNUP_CODE` | Opcional | Exige código para cadastro de professor |
| `FORWARDED_ALLOW_IPS` | Atrás de proxy | IP do proxy reverso (padrão `127.0.0.1`); só dele o `X-Forwarded-For` é aceito |
| `LOG_LEVEL` | Opcional | Nível de log (padrão `INFO`) |

Sem as opcionais, a interface informa honestamente que o recurso está indisponível: o FinBot
não inventa respostas, a recuperação de senha avisa que não há e-mail configurado e não simula envio,
o resumo semanal não pode ser ativado e o comprovante é preenchido à mão.

## Login com Google

1. No [Google Cloud Console](https://console.cloud.google.com/apis/credentials), crie um projeto e configure a
   **Tela de consentimento OAuth** (tipo externo, escopos `openid`, `email` e `profile`).
2. Em **Credenciais → Criar credenciais → ID do cliente OAuth**, escolha **Aplicativo da Web**.
3. Em **URIs de redirecionamento autorizados**, adicione exatamente `APP_BASE_URL/api/auth/google/callback`
   (local: `http://localhost:8010/api/auth/google/callback` com `APP_BASE_URL=http://localhost:8010`;
   produção: `https://seu-dominio/api/auth/google/callback`).
4. Coloque `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env` (nunca no código) e reinicie.
5. Enquanto o app estiver em modo "Teste" no Google, só os e-mails cadastrados como testadores conseguem entrar.

Como funciona: o servidor redireciona para o Google com `state`, `nonce` e PKCE; o Google devolve um código que o
servidor troca diretamente pelo `id_token` e valida emissor, público, validade, `nonce` e e-mail verificado.
- Primeira vez: a pessoa escolhe aluno/professor e aceita os termos (tela “Quase lá”).
- E-mail que já tem conta confirmada: o Google é vinculado e a senha continua valendo.
- E-mail de conta com senha ainda **não confirmada** (o cadastro com senha não confirma o e-mail; só a redefinição de senha confirma): o dono comprovado pelo Google assume; a senha antiga e as
  sessões abertas deixam de valer (evita que alguém “reserve” o e-mail de outra pessoa).
- Contas só Google não têm senha; podem criar uma em “Esqueci minha senha”.
- Sem as variáveis, o botão aparece desativado com o aviso “não configurado neste servidor”.

## Backup, verificação e restauração

```powershell
# integridade e vínculos do banco em uso
.venv\Scripts\python.exe manage_db.py check
# backup consistente do banco (API de backup do SQLite) + ZIP separado dos uploads + manifesto SHA-256
.venv\Scripts\python.exe manage_db.py backup D:\backups\fintrack-2026-11-16
# confere um backup sem tocar no banco em uso
.venv\Scripts\python.exe manage_db.py verify D:\backups\fintrack-2026-11-16
# restaura: PARE O SERVIDOR antes
.venv\Scripts\python.exe manage_db.py restore D:\backups\fintrack-2026-11-16
```

- O destino do backup precisa ser uma pasta nova. Guarde cópias fora do computador do servidor.
- A restauração recusa backups adulterados ou corrompidos, guarda o estado atual em
  `data/backups/antes-da-restauracao-*` e ajusta os caminhos dos arquivos privados.
- Para ensaiar a restauração em ambiente isolado, defina `FINTRACK_DATA_DIR` para uma pasta vazia
  antes de rodar `restore` (é o que o teste automatizado faz).
- Cada migração de esquema (`schema_migrations`, versões 1 a 4) cria antes um backup em `data/backups/before-v*.db`.
  Reverter uma migração = parar o servidor e restaurar esse backup.

## Testes

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

Os testes usam pasta temporária própria e nunca tocam em `data/`. Veja `VALIDACAO.md`.

## Hospedagem

**GitHub Pages não executa esta versão** (é só para arquivos estáticos). Use uma hospedagem com
Python, HTTPS e disco persistente montado em `FINTRACK_DATA_DIR`, por exemplo:

- VPS (qualquer provedor) com `uvicorn` atrás de Nginx/Caddy com HTTPS;
- Railway, Render (plano pago com disco), Fly.io com volume, ou similar que ofereça volume persistente.

Rode **uma única instância** por banco SQLite (o worker de recorrências e resumos roda no processo).
Disco temporário de plataformas serverless apaga contas e dados a cada publicação: não use.
Passos mínimos: `COOKIE_SECURE=1`, `APP_BASE_URL=https://seu-dominio`, `FINTRACK_DATA_DIR` no volume,
`HOST=0.0.0.0`, `PORT` conforme a plataforma, `FORWARDED_ALLOW_IPS` com o IP do proxy reverso, e backups agendados com `manage_db.py backup`.

Esta versão **não foi publicada** em nenhum servidor; foi testada apenas localmente.

## Dados da edição GitHub Pages

Contas e lançamentos criados na edição estática ficaram no `localStorage` do navegador usado.
Este pacote não os apaga nem os importa. Não limpe os dados daquele navegador se quiser preservá-los.
