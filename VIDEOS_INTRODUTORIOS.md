# Vídeos introdutórios — FinTrack 0.5

Os MP4 enviados estão incluídos no pacote, sem depender de YouTube:

- `media/education/poupanca.mp4`: Aula 1, 36,5 segundos. Abre o módulo Poupança e hábito de guardar.
- `media/education/controle.mp4`: Aula 2, 40,078 segundos. Abre o módulo Controle de gastos.

- `media/education/planejamento.mp4`: Aula 3, 40 segundos. Abre o módulo Planejamento financeiro.
- `media/education/investimentos.mp4`: Aula 4, aproximadamente 40,05 segundos. Abre o módulo Introdução aos investimentos.

Ao abrir qualquer aula desses módulos, a introdução aparece primeiro. O botão Continuar para a aula libera o conteúdo e as tarefas somente depois da reprodução completa. A barra não permite avançar para trechos ainda não assistidos. O progresso confirmado é salvo por conta no SQLite; ao voltar, o player retoma esse ponto. Uma pequena fração final ainda não sincronizada pode ser repetida.

O backend também bloqueia abertura, correção e envio de atividades antes da conclusão. Progresso de uma conta não libera outra conta nem outro módulo. Ao abrir o mesmo vídeo em outra aba, a sessão anterior deixa de poder registrar progresso. A reprodução pausa quando a aba fica oculta. Não há reprodução automática: toque em play.

Os vídeos são servidos por rota autenticada, com suporte a requisições parciais para celulares. Foram preservados os arquivos originais. A verificação acompanha posição, sequência e tempo de reprodução; não comprova atenção humana e não é proteção DRM contra um cliente deliberadamente modificado.

## Instalação e atualização

Para uma instalação nova, extraia o ZIP e execute `INICIAR_FINTRACK.bat`, conforme `LEIA_PRIMEIRO.md`. Inclua a pasta `media` ao hospedar o backend Python. Não é uma versão estática para GitHub Pages.

Para atualizar uma instalação existente, faça backup e preserve sua pasta `data` ou o diretório definido por `FINTRACK_DATA_DIR`. Atualize o código e inclua `media`. A nova tabela é criada automaticamente, sem apagar progresso de atividades, contas ou lançamentos anteriores. As novas introduções serão exigidas também de contas antigas na próxima abertura dos módulos.

Caso substitua um MP4 no futuro, atualize também sua `version` em `video_lessons.py` para exigir a nova introdução. A duração é lida do próprio arquivo durante a inicialização. Exceção: a aula 4 é um MP4 fragmentado com duração zero no cabeçalho; sua duração real, medida no navegador, está em `DURATION_OVERRIDES`. Ao substituir esse vídeo, atualize também essa duração.
