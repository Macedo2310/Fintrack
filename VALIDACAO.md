# Validação — FinTrack 0.6 (16/11/2026)

Tudo abaixo foi executado **localmente** (Windows 11, Python 3.14.8). Nada foi publicado.

## Testes automatizados — `python -m pytest` → 47 aprovados, 0 falhas

Banco e uploads em pasta temporária; worker desligado; serviços externos simulados quando indicado.

| # pedido | Teste | O que comprova |
|---|---|---|
| 1 | `test_signup_login_logout_and_expired_session` | Cadastro de aluno e professor, senha fraca/e-mail inválido/sem termos/papel inválido recusados, cookie `HttpOnly; SameSite=Lax`, login, logout, sessão expirada → 401 e `app.html` não é entregue |
| 1 | `test_login_rate_limit_and_honest_password_recovery`, `test_signup_rate_limit` | 11ª tentativa de login → 429; 6º cadastro/hora por IP → 429; sem SMTP a recuperação responde 503 igual para qualquer e-mail, sem simular envio |
| 2 | `test_accounts_cannot_read_or_change_each_other` | Outra conta recebe 404 ao editar/excluir lançamentos, metas e conversas alheias; listas e saldos isolados |
| 3 | `test_transactions_crud_search_filters_and_validation` | Valor zero, negativo, texto, acima do limite e categoria incompatível recusados; formato `1.234,56`; busca com `%`/`_` escapados; filtros, ordenação por valor, paginação; resumo igual aos filtros; categoria personalizada por conta |
| 3 | `test_recurrence_generates_without_duplicates_and_scoped_changes` | Início no passado gera as ocorrências na hora; rodar o gerador de novo não duplica; editar "esta e próximas"; excluir "esta e próximas" encerra a recorrência |
| 4, 6 | `test_balance_rules_and_goal_lifecycle` | Reserva não é despesa nem reduz saldo total; disponível = total − reservado; lançamento futuro fora do saldo; 6 meses no gráfico incluindo meses vazios; retirada maior que a reserva recusada; estados ativa/pronta/concluída; excluir libera a reserva |
| 5 | `test_simultaneous_reservations_cannot_spend_same_balance` | Servidor uvicorn real, 8 reservas simultâneas de R$ 80 com saldo de R$ 100 → exatamente 1 aprovada |
| 7 | `test_lessons_grading_server_side_and_progress`, `test_course_content_precision` | Respostas não chegam ao navegador; correção com explicação; nota mínima 70%; melhor nota e conclusão preservadas; tentativas contadas; `3.600` e `3600,00` aceitos; orçamento com percentual negativo recusado; 12 títulos e 5 tipos de atividade; frases obrigatórias de precisão |
| 8 | `test_video_gate_resume_and_skip_protection` (+ `test_video_guard.py`) | Aula bloqueada antes do vídeo; salto na barra não libera; nova aba invalida a anterior; retomada do ponto salvo; vídeo concluído continua concluído; progresso por conta; vídeo só com sessão e com suporte a `Range` |
| 9, 10 | `test_classes_assignments_and_financial_privacy` | Só professor cria turma/atribui; aula inválida ou prazo passado recusados; aluno que entra depois recebe as atividades; aula já concluída conta como entregue; resultados e pontuação; compartilhamento desligado por padrão; professor sem autorização ou de outra turma não vê resumo; com autorização vê só totais; nunca conversas nem lançamentos; renovar/desativar código; sair da turma |
| 11 | `test_finbot_configured_unconfigured_and_provider_error` | Sem IA: 503 e nenhuma resposta salva; erro do provedor: 502 com a mensagem do provedor e nada inventado; repetição da mesma chave não chama a IA de novo; mesma chave com outro texto → 409; análise envia só agregados (sem descrições); renomear e excluir conversa |
| 12 | `test_market_fresh_stale_and_unavailable` | Atualizado, antigo (último valor salvo) e indisponível sem número inventado; exige sessão |
| 13 | `test_reminders_per_account_without_duplicates`, `test_assignment_overdue_reminder` | Sem duplicar; marcar como lido não recria; isolamento; limite mensal (80/100%); despesas > receitas sem limite; preferência de alertas respeitada; atividade atrasada |
| 14 | `test_preferences_persist_after_relogin`, `test_weekly_summary_only_when_configured` | Tema, gráfico, dicas, alertas, limite e nome mantidos após sair e entrar; resumo semanal recusado sem SMTP, enviado uma vez por semana às segundas quando configurado (envio simulado) |
| — | `test_uploads_are_validated_and_private`, `test_cross_site_mutation_blocked_and_headers` | Arquivo falso com extensão `.png` recusado; foto e comprovante privados; limite de 5 MB; mutação de outra origem → 403; cabeçalhos de segurança |
| — | `test_auth_google_email.py` (6 testes) | Cadastro com senha entra direto, sem código, mesmo com SMTP; redefinir senha confirma o e-mail; Google: sem configuração o botão leva a aviso honesto; conta nova só após perfil + termos; token de uso único; conta Google não entra por senha; vínculo com conta confirmada mantém a senha; conta não confirmada é assumida pelo dono do Google com sessões antigas encerradas; `state`, `aud`, `iss`, `exp`, `nonce`, e-mail não verificado e cancelamento recusados. Google simulado. |
| — | `test_hardening.py` (17 testes, 0.6.1) | `X-Forwarded-For` forjado não escapa do limite de login; limite continua após reiniciar (gravado no banco) e registros antigos são limpos; `app.html`/`avatar.html` exigem sessão também por `/static/`, com maiúsculas, `./` ou `../`; app usa `lifespan` sem aviso de `on_event`; tipo de atividade validado e gravado; duração dos vídeos igual à leitura anterior, sem carregar o arquivo inteiro |
| 17 | `test_backup_restore.py` | Backup em processos isolados, verificação SHA-256, detecção de adulteração, restauração em outro diretório com caminhos de comprovantes ajustados, integridade `ok` |

## Testes no navegador (painel do app, Chromium) — servidor local na porta 8031, banco descartável

- Cadastro pela interface: senha sem número barrada no cliente; cadastro válido → escolha de avatar → dashboard.
- Receita de `1.500,00` cadastrada pela interface; resumo, metas e saldo atualizados.
- Todas as 8 telas internas carregadas sem erro de console.
- Indicadores **reais** do Banco Central retornaram nesta data: dólar e euro (PTAX de 13/11/2026), meta Selic e IPCA de 10/2026.
- Vídeo 1 reproduzido de verdade por ~10 s: progresso salvo no servidor, botão de continuar bloqueado, salto para 30 s devolvido à posição assistida, retomada a partir do valor salvo.
- Larguras 320, 768 e 1366 px nas 8 telas internas; 320 px na landing e no login: sem rolagem horizontal
  (dois defeitos encontrados e corrigidos: cabeçalho do FinBot estourando em 320 px e menu móvel da landing sem "Entrar/Criar conta").
- Teclado: Tab percorre a navegação com contorno de foco visível; regra `prefers-reduced-motion` ativa; botão "Pausar animações" presente.

## Login com Google no navegador (16/11/2026)

- Botão “Continuar com Google” desativado com aviso quando não há credenciais.
- Retorno do Google simulado: tela “Quase lá”, conta criada vinculada ao Google e sem senha.
- Login e cadastro em 320 px sem estouro.
- A etapa de código por e-mail foi retirada a pedido; cadastro com senha vai direto ao avatar.

## Não testado / limites

- Login com uma conta Google real (exige criar o ID do cliente no Google Cloud com o seu endereço).

- Reprodução completa até o fim dos 4 vídeos no navegador nesta versão (a regra de conclusão foi testada no servidor; a 0.5 registrou reprodução completa dos 4).
- Envio real de e-mail, IA real (OpenAI/compatível) e serviço real de comprovantes: dependem de chaves que não foram fornecidas; testados com simulação.
- Aparelho físico, Safari/iOS, teclado virtual real e leitor de tela.
- Publicação em servidor com HTTPS.
