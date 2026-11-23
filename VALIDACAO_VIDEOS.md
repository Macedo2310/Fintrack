# Versão 0.5 — módulos 3 e 4 — 27/10/2026

Os dois novos vídeos passaram pela reprodução real até o fim e pela liberação das respectivas atividades no Edge automatizado. Foram verificados bloqueio de salto, bloqueio de atividades pela API antes da conclusão, retomada da aula 3 e persistência das duas conclusões após recarregar. Nenhum erro de JavaScript; sem transbordamento horizontal em 320, 390, 768 e 1366 pixels. Capturas de celular revisadas visualmente. Os dois testes unitários de proteção também passaram.

Script: `tests/test_videos_34.cjs`. Resultado: `tests/video-34-results.json`. Os arquivos das aulas 3 e 4 foram comparados por SHA-256 com os originais enviados. Os vídeos 1 e 2 e suas versões de progresso foram preservados; sua reprodução completa não foi repetida nesta alteração. O teste original agora verifica a conclusão apenas dos módulos 1 e 2.

A aula 4 é um MP4 fragmentado: sua duração real de 40,05449 segundos foi medida pelo player do navegador e configurada no backend, sem converter ou alterar o arquivo original. As verificações são locais, com emulação de celular; não houve teste em aparelho físico nem publicação.

---

# Validação dos vídeos — 27/10/2026

Resultado final: aprovado nos testes locais abaixo.

- Reprodução real dos dois MP4 no Edge automatizado, até a liberação do botão Continuar e a abertura das respectivas aulas.
- Tentativa de saltar pela barra retorna ao trecho permitido; envio direto de uma posição final não conclui a introdução.
- Correção e envio de atividades bloqueados antes da introdução. Correção aceita depois da liberação, com resposta no formato da atividade.
- Saída e retorno à primeira introdução retomam o progresso confirmado.
- Conclusão das duas introduções permanece após recarregar a página.
- Vídeo exige autenticação e responde a requisições parciais HTTP 206.
- Nenhum erro de JavaScript no fluxo final.
- Sem transbordamento horizontal em 320, 390, 768 e 1366 pixels. Capturas de 390 pixels revisadas visualmente.
- Dois testes unitários verificam isolamento por conta e módulo, sessões substituídas, rejeição de salto/avanço acelerado e retomada.
- SHA-256 dos MP4 copiados igual aos arquivos enviados. Integridade do ZIP e bytes dos vídeos verificados no empacotamento.

Scripts: `tests/test_videos.cjs` e `tests/test_video_guard.py`. Resultado do navegador em `tests/video-results.json`. O teste de navegador usa dados descartáveis e exige servidor na porta 8019; nunca o execute contra uma instalação com dados reais. Para preparar o servidor, defina `FINTRACK_DATA_DIR` como `.work/video-qa`. Instale as dependências Python e o módulo Playwright, com Microsoft Edge disponível; `PLAYWRIGHT_MODULE` permite informar um caminho alternativo para o módulo.

A suíte anterior do backend não foi repetida integralmente nesta alteração; seus resultados históricos estão em `VALIDACAO.md`. Houve correções durante os testes, incluindo a sobreposição da coruja nos controles e o tratamento de busca na barra do vídeo. O teste final dos dois vídeos passou sem intervenção manual.

Limites: navegador desktop com emulação de tela e toque; sem teste em iPhone/Android físico e sem publicação em hospedagem. Os testes de reprodução usam áudio silenciado. O controle registra reprodução e tempo, não atenção humana nem resistência absoluta a um cliente modificado.
