# Validação do pacote V6

Os testes usam um banco descartável em `.work/qa-data`, que não acompanha o ZIP.

- 11 grupos de regressão: autenticação, cadastro/avatar, login, cálculos financeiros, isolamento entre contas, metas/reservas, preferência de gráfico, educação, turmas, armazenamento de conversas e perfil/tema.
- 7 grupos do backend: autenticação dos endpoints novos, isolamento/deduplicação/leitura de lembretes, concorrência de reservas, orçamento/preferências, aulas, migração/índices/backup e cache em falhas da fonte externa.
- Teste responsivo: oito páginas nas larguras 320, 390, 768 e 1366 pixels; preferências, navegação e modal de transações.
- Autenticação pelo formulário real e seleção de avatar verificadas no navegador, sem fallback para contas locais.
- Assets e implementação do gráfico original comparados com o ZIP V5.

Os scripts estão em `tests/`. O teste Python usa o servidor na porta 8019 e exige `FINTRACK_DATA_DIR` apontando para `.work/qa-data` no processo do servidor. O teste de navegador usa Playwright e Edge; instale Playwright ou informe o caminho do módulo na variável `PLAYWRIGHT_MODULE`. Reinicie o servidor de QA entre a suíte de backend e o teste de cadastro pelo navegador: a proteção de cadastro permite cinco contas por IP por hora. Nunca execute esses testes contra um banco com dados reais.

Limites: emulação de telas, sem aparelho físico; sem implantação em produção. Os testes de falha de mercado usam respostas simuladas identificadas como tal. USD/EUR foram verificados externamente durante a implementação; SGS encontrou indisponibilidade.
