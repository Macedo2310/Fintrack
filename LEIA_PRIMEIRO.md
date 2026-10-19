# FinTrack V6 — versão com backend

Este pacote aplica as melhorias de banco de dados, indicadores financeiros, lembretes e celular à versão **fintrack-github-pages-release-v5-grafico-linha-completo.zip** fornecida por você.

O visual, as imagens e o código de desenho do gráfico V5 foram preservados. O gráfico continua mostrando seis meses, inclusive meses sem lançamentos. O menu do celular foi adaptado para acomodar a nova central de lembretes.

## Abrir no Windows

1. Extraia o ZIP em uma pasta.
2. Tenha Python 3.12 ou superior instalado, com acesso à internet para instalar as dependências.
3. Execute `INICIAR_FINTRACK.bat`.
4. Quando aparecer a mensagem do servidor, abra **http://127.0.0.1:8010**.
5. Crie sua conta. O banco será criado vazio em `data/fintrack.db`.

Alternativa manual, executada dentro da pasta:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

## O que foi integrado

- **Banco SQLite:** índices, transações, fechamento de conexões, backup consistente antes da migração, validação de integridade e proteção contra reservas simultâneas do mesmo saldo.
- **Backend real:** cadastro, sessão, transações, metas, educação e turmas usam FastAPI. Não há fallback para autenticação ou gravação financeira em localStorage quando a API falha.
- **Moedas e indicadores:** dólar/euro PTAX, meta Selic e IPCA, com cache, data de referência e indicação de indisponibilidade. Dados públicos do Banco Central, sem chave para essa integração.
- **Lembretes:** metas próximas do prazo, metas prontas para concluir, aulas em andamento, atividades pendentes e atenção aos gastos. Preferências e histórico por conta.
- **Celular:** navegação em menu lateral, campos maiores, controles de toque, safe areas e diálogos que respeitam a altura da tela.

## Hospedagem e dados antigos

**Este ZIP não deve ser enviado diretamente ao GitHub Pages como substituto da versão V5.** GitHub Pages não executa Python ou banco de dados. Para publicar esta versão, use hospedagem com Python e disco persistente, HTTPS e `COOKIE_SECURE=1`.

Os cadastros e lançamentos da V5 ficaram no navegador/domínio em que foram criados. Este pacote não apaga nem importa esses dados automaticamente. A conta V6 deve ser criada no backend; uma eventual transferência dos dados antigos exige uma exportação e importação específica. Não limpe os dados do navegador antigo.

O ZIP não contém contas de teste, senhas, chaves, comprovantes nem banco preenchido. A pasta `referencia-v5` contém somente a documentação histórica do ZIP original; as instruções de GitHub Pages ali não se aplicam à V6.

## Usar no celular

No computador servidor, dentro da pasta:

```powershell
$env:HOST = '0.0.0.0'
.venv\Scripts\python.exe run.py
```

Conecte o celular à mesma rede e abra `http://IP-DO-COMPUTADOR:8010`. O firewall precisa permitir acesso à porta. No computador e no celular, use a mesma conta no mesmo servidor para acessar o mesmo banco. Abrir o arquivo HTML diretamente não inicia o sistema.

## Limites desta entrega

- Lembretes aparecem dentro do app; não há push nem envio com ele fechado.
- Selic e IPCA estão integrados, mas o serviço SGS apresentou timeout/erro interno nas consultas reais desta sessão. A interface mostra indisponibilidade ou o último valor salvo, sem criar números fictícios.
- IA remota, recuperação por e-mail e OCR dependem das configurações opcionais em `.env.example`. O assistente local da V5 foi substituído pelo fluxo de backend; sem configurar a IA, a interface informa que ela está indisponível.
- Testes de navegador não substituem validação de teclado, toque e Safari em aparelho real.
- Não houve publicação em produção.

Consulte `BACKEND_E_MOBILE.md` para detalhes de manutenção, backup, APIs e regras dos avisos. Consulte `VALIDACAO.md` para os testes deste pacote.
