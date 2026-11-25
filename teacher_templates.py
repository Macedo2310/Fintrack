"""Modelos prontos que o professor pode lançar para a turma (e editar antes de lançar).

Desafios são conferidos automaticamente pelo banco (private.refresh_challenges): contam só o que o
aluno fizer DEPOIS do lançamento. O professor vê se concluiu e quantas ações fez, nunca valores.
"""

CHALLENGE_KINDS = {
    "despesas": "Registrar despesas",
    "receitas": "Registrar receitas",
    "meta": "Criar metas de economia",
    "reserva": "Fazer reservas em metas",
    "comprovante": "Escanear comprovantes",
}

CHALLENGES = [
    {"key": "semana-registro", "title": "Semana do registro", "kind": "despesas", "target": 5,
     "instructions": "Durante a semana, registre no FinTrack pelo menos 5 despesas suas, com a categoria certa."},
    {"key": "entradas", "title": "Mapeie suas entradas", "kind": "receitas", "target": 1,
     "instructions": "Registre pelo menos uma entrada de dinheiro (mesada, salário, bico, venda)."},
    {"key": "primeira-meta", "title": "Minha primeira meta", "kind": "meta", "target": 1,
     "instructions": "Crie uma meta de economia com valor e prazo realistas para você."},
    {"key": "guardando", "title": "Guardando de verdade", "kind": "reserva", "target": 2,
     "instructions": "Faça 2 reservas em uma meta, mesmo que de valores pequenos. O hábito vale mais que o valor."},
    {"key": "comprovante", "title": "Comprovante na mão", "kind": "comprovante", "target": 1,
     "instructions": "Use o botão Escanear para registrar um gasto a partir de um comprovante ou nota fiscal."},
    {"key": "mes-organizado", "title": "Mês organizado", "kind": "despesas", "target": 15,
     "instructions": "Registre pelo menos 15 despesas ao longo do mês para enxergar para onde vai o seu dinheiro."},
]


def _q(q, options, answer, why):
    return {"q": q, "options": options, "answer": answer, "why": why}


QUIZZES = [
    {"key": "orcamento", "title": "Orçamento pessoal", "questions": [
        _q("Na regra 50-30-20, qual parte da renda vai para necessidades (moradia, comida, transporte)?",
           ["20%", "30%", "50%", "80%"], 2, "A regra sugere 50% para necessidades, 30% para desejos e 20% para poupar ou pagar dívidas."),
        _q("Qual destes é um gasto variável?", ["Aluguel", "Mensalidade fixa da escola", "Ida ao cinema", "Prestação do financiamento"], 2,
           "Gastos variáveis mudam de mês para mês; lazer como cinema é o exemplo típico."),
        _q("Sua renda é R$ 2.000 e seus gastos somam R$ 2.300. O que está acontecendo?",
           ["Sobram R$ 300", "Faltam R$ 300 no mês", "O orçamento está equilibrado", "Os gastos são 50% da renda"], 1,
           "Gastar mais do que se ganha gera um déficit de R$ 300, que vira dívida ou consome reservas."),
        _q("Qual é o primeiro passo para montar um orçamento?",
           ["Fazer um empréstimo", "Anotar quanto entra e quanto sai", "Cortar todo o lazer", "Investir em ações"], 1,
           "Sem saber o que entra e o que sai, não dá para planejar. Registrar é o ponto de partida."),
        _q("Para que serve separar os gastos por categoria?",
           ["Para pagar menos impostos", "Para descobrir onde dá para economizar", "Para aumentar a renda", "Não serve para nada"], 1,
           "Ver os gastos por categoria mostra onde está a maior parte do dinheiro e onde é possível ajustar."),
    ]},
    {"key": "reserva", "title": "Reserva de emergência", "questions": [
        _q("Para que serve a reserva de emergência?",
           ["Comprar coisas em promoção", "Cobrir imprevistos, como perda de renda ou saúde", "Viajar nas férias", "Investir em ações arriscadas"], 1,
           "Ela existe para imprevistos, evitando que você precise se endividar quando algo dá errado."),
        _q("Qual valor costuma ser recomendado para a reserva de emergência?",
           ["1 semana de gastos", "De 3 a 6 meses dos seus gastos mensais", "10 anos de salário", "Não existe recomendação"], 1,
           "A referência mais comum é de 3 a 6 meses de gastos; quem tem renda instável pode precisar de mais."),
        _q("Onde é mais adequado guardar a reserva de emergência?",
           ["Em aplicação segura e com resgate rápido", "Em ações de uma única empresa", "Em um imóvel", "Emprestada a um amigo"], 0,
           "A reserva precisa de segurança e liquidez: estar disponível rápido e sem risco de perder valor."),
        _q("Seus gastos mensais são R$ 1.500. Uma reserva de 4 meses seria de:",
           ["R$ 1.500", "R$ 4.000", "R$ 6.000", "R$ 15.000"], 2, "4 × R$ 1.500 = R$ 6.000."),
        _q("Usou parte da reserva num imprevisto. O que fazer depois?",
           ["Nada, ela acabou", "Reconstruir a reserva aos poucos", "Fazer um empréstimo para repor", "Gastar o resto"], 1,
           "Depois de usar, o ideal é voltar a guardar até recompor o valor planejado."),
    ]},
    {"key": "juros", "title": "Juros e dívidas", "questions": [
        _q("R$ 1.000 rendendo 10% ao ano em juros compostos viram quanto em 2 anos?",
           ["R$ 1.100", "R$ 1.200", "R$ 1.210", "R$ 2.000"], 2, "1º ano: 1.000 × 1,1 = 1.100. 2º ano: 1.100 × 1,1 = 1.210."),
        _q("O que acontece ao pagar só o valor mínimo da fatura do cartão?",
           ["A dívida some", "O restante entra no rotativo, com juros muito altos", "O banco perdoa a diferença", "Nada muda"], 1,
           "O saldo não pago entra no crédito rotativo, um dos juros mais caros do mercado."),
        _q("Qual é a diferença entre juros simples e compostos?",
           ["Não há diferença", "Nos compostos, os juros rendem sobre os juros anteriores", "Os simples são sempre maiores", "Os compostos só existem em dívidas"], 1,
           "Nos juros compostos, cada período calcula juros sobre o valor já acrescido dos juros anteriores."),
        _q("Uma compra de R$ 600 em 6x \"sem juros\" tem parcelas de:", ["R$ 60", "R$ 100", "R$ 120", "R$ 600"], 1,
           "R$ 600 ÷ 6 = R$ 100 por parcela."),
        _q("Antes de parcelar uma compra, o mais prudente é:",
           ["Ver se as parcelas cabem no orçamento dos próximos meses", "Parcelar no máximo de vezes sempre", "Ignorar as outras parcelas", "Usar o limite todo do cartão"], 0,
           "Parcelas somadas comprometem a renda futura; confira se cabem junto com os outros gastos."),
    ]},
    {"key": "consumo", "title": "Consumo consciente", "questions": [
        _q("Qual destas atitudes ajuda a evitar compras por impulso?",
           ["Comprar na hora para não perder a promoção", "Esperar alguns dias antes de comprar algo não planejado", "Usar sempre o cartão de crédito", "Seguir só a vontade do momento"], 1,
           "Dar um tempo antes de comprar ajuda a separar vontade passageira de necessidade real."),
        _q("Um produto custava R$ 100 e está \"de R$ 150 por R$ 100\". Isso significa que:",
           ["Você economiza R$ 50", "Você gasta R$ 100", "Você ganha R$ 50", "É sempre um bom negócio"], 1,
           "Se você não ia comprar, a \"economia\" é ilusória: o gasto real é de R$ 100."),
        _q("O que é custo de oportunidade?",
           ["O preço com desconto", "Aquilo que você deixa de fazer com o dinheiro ao escolher outra coisa", "A taxa do cartão", "O valor do frete"], 1,
           "Toda escolha tem uma renúncia: o dinheiro gasto em algo não pode ser usado para outra coisa."),
        _q("Qual é a forma mais justa de comparar dois tamanhos do mesmo produto?",
           ["Pela embalagem mais bonita", "Pelo preço por unidade (por kg ou por litro)", "Pelo preço total", "Pela marca mais famosa"], 1,
           "O preço por kg ou por litro mostra qual opção é realmente mais barata."),
        _q("Uma assinatura de R$ 30 por mês custa quanto em um ano?", ["R$ 30", "R$ 300", "R$ 360", "R$ 3.600"], 2,
           "12 × R$ 30 = R$ 360. Pequenos valores mensais pesam no ano."),
    ]},
]


def catalog() -> dict:
    return {"challenge_kinds": CHALLENGE_KINDS, "challenges": CHALLENGES, "quizzes": QUIZZES}
