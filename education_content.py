# -*- coding: utf-8 -*-
"""Curso de educação financeira do FinTrack: 4 níveis, 12 aulas, atividades interativas.
As respostas corretas ficam só no servidor; o navegador recebe apenas o enunciado.

Dificuldade progressiva: em cada módulo, a 1ª aula fixa os conceitos; as seguintes pedem cálculos de
mais de um passo, comparação de cenários e alternativas plausíveis, difíceis de acertar no chute."""
import math
import re

SRC = {
 "bcb": {"n": "Banco Central do Brasil — Cidadania Financeira", "u": "https://www.bcb.gov.br/cidadaniafinanceira"},
 "cvm": {"n": "Portal do Investidor (CVM)", "u": "https://www.investidor.gov.br"},
 "td": {"n": "Tesouro Direto", "u": "https://www.tesourodireto.com.br"},
}
REVIEWED = "2026-11"
PASS = 70  # % mínimo para concluir uma aula

def Q(q, opts, ans, why): return {"t": "quiz", "q": q, "opts": opts, "ans": ans, "why": why}
def M(q, opts, ans, why): return {"t": "multi", "q": q, "opts": opts, "ans": ans, "why": why}
def C(q, buckets, items, why): return {"t": "classify", "q": q, "buckets": buckets, "items": items, "why": why}
def N(q, ans, why, unit="R$"): return {"t": "calc", "q": q, "ans": ans, "unit": unit, "why": why}
def B(q, cats, total, rules, right, why): return {"t": "budget", "q": q, "cats": cats, "total": total, "rules": rules, "right": right, "why": why}
def L(key, title, goal, explain, example, acts, summary, src):
    return {"key": key, "title": title, "goal": goal, "explain": explain, "example": example,
            "acts": acts, "summary": summary, "sources": [SRC[s] for s in src], "reviewed": REVIEWED}

EDUCATION = [
 {"key": "poupanca", "level": 1, "level_name": "Iniciante", "title": "Poupança e hábito de guardar",
  "description": "Poupar x investir, começar com pouco e montar sua reserva de emergência.", "topics": [
  L("o-que-e", "Poupar, investir e caderneta",
    "Diferenciar poupar, investir e a caderneta de poupança.",
    "Poupar é separar parte do dinheiro de hoje para o futuro. Investir é aplicar esse dinheiro em produtos financeiros buscando retorno, aceitando algum nível de risco. A caderneta de poupança é apenas um desses produtos: não é sinônimo de poupar.",
    "Bia recebe R$ 200 de mesada e separa R$ 30 todo mês. Ela já está poupando, mesmo antes de escolher onde deixar esse dinheiro.",
    [Q("Ana guarda R$ 50 por mês numa gaveta. Beto aplica R$ 50 por mês num CDB. Qual afirmação é correta?",
       ["Só Beto está poupando, porque aplicou o dinheiro", "Os dois estão poupando, mas só Beto está investindo", "Os dois estão investindo", "Nenhum dos dois está poupando, porque os valores são pequenos"], 1,
       "Poupar é separar o dinheiro; os dois fazem isso. Investir é aplicar em um produto financeiro, o que só Beto fez."),
     C("Classifique cada situação:", ["Hábito de poupar", "Produto financeiro"],
       [["Separar 10% da mesada assim que recebe", 0], ["Caderneta de poupança", 1], ["Tesouro Selic", 1],
        ["Deixar de pedir delivery e guardar a diferença", 0], ["CDB", 1], ["Guardar o troco do lanche num cofrinho", 0]],
       "Atitudes de separar dinheiro são hábitos. Caderneta, Tesouro Selic e CDB são produtos onde o dinheiro separado pode ficar."),
     M("Quais afirmações são verdadeiras? Marque todas.",
       ["A caderneta é um produto financeiro, não sinônimo de poupar", "A caderneta é o único jeito seguro de poupar",
        "Todo produto tem rendimento, liquidez e risco próprios", "O rendimento da caderneta nunca fica abaixo da inflação",
        "Guardar dinheiro sem aplicar também é poupar"], [0, 2, 4],
       "Poupar é o hábito; a caderneta é só um dos produtos. Ela pode, sim, render menos que a inflação em alguns períodos.")],
    ["Poupar é um hábito; investir é uma escolha de aplicação.", "A caderneta é um produto, não sinônimo de poupar.", "Todo produto tem risco, liquidez e rendimento próprios."], ["bcb", "cvm"]),
  L("vantagens", "Reserva de emergência",
    "Entender para que serve a reserva de emergência e quanto ela deve cobrir.",
    "Reserva de emergência é dinheiro guardado para imprevistos, como um conserto urgente ou uma perda de renda. Ela precisa estar disponível rápido (liquidez) e com baixo risco de perda. Uma referência comum é cobrir alguns meses de gastos essenciais — só os essenciais, sem lazer ou desejos.",
    "Se os gastos essenciais de Lucas são R$ 1.200 por mês e ele quer uma reserva de 3 meses, o alvo é R$ 3.600.",
    [M("Quais situações justificam usar a reserva de emergência? Marque todas.",
       ["Conserto urgente do celular que você usa para estudar", "Promoção de um jogo novo", "Perda temporária de renda",
        "Ingresso de show", "Remédio que não estava previsto", "Trocar de celular porque saiu um modelo novo"], [0, 2, 4],
       "Reserva é para imprevistos e necessidades urgentes. Promoções, lançamentos e lazer são desejos: podem esperar ou virar uma meta."),
     N("Os gastos de Lucas por mês: aluguel R$ 700, alimentação R$ 450, transporte R$ 150, contas R$ 200 e lazer R$ 300. Qual o valor de uma reserva de 3 meses, considerando só os gastos essenciais?", 4500,
       "Lazer não entra: 700 + 450 + 150 + 200 = 1.500 por mês de gastos essenciais; 1.500 × 3 = 4.500."),
     N("Lucas já tem R$ 1.800 guardados e consegue separar R$ 300 por mês. Em quantos meses ele completa a reserva de R$ 4.500?", 9,
       "Faltam 4.500 − 1.800 = 2.700. Com R$ 300 por mês: 2.700 ÷ 300 = 9 meses.", unit="meses"),
     Q("Onde faz mais sentido deixar a reserva de emergência?",
       ["Em ações de uma única empresa, que podem render mais", "Em um investimento de baixo risco e resgate rápido, como Tesouro Selic ou CDB com liquidez diária",
        "Em um título que só pode ser resgatado daqui a 5 anos", "Emprestado a um amigo, que prometeu devolver com juros"], 1,
       "Num imprevisto o dinheiro precisa estar disponível e sem grandes perdas. Ações oscilam, prazos longos travam o dinheiro e empréstimos informais podem não voltar.")],
    ["Reserva é para imprevistos, não para desejos.", "Liquidez e segurança vêm antes de rentabilidade.", "Uma referência: alguns meses de gastos essenciais."], ["bcb"]),
  L("dicas", "Começando com pouco",
    "Criar o hábito de guardar mesmo com valores pequenos.",
    "Consistência vale mais do que valor. Separar um valor possível assim que o dinheiro entra, antes de gastar, é mais eficaz do que tentar guardar o que sobra. Uma porcentagem fixa da renda ajuda o valor guardado a crescer junto com ela.",
    "Guardar R$ 25 por semana parece pouco, mas em 12 semanas soma R$ 300.",
    [N("Júlia recebe R$ 800 por mês e guarda 15% assim que o dinheiro entra. Quanto ela terá separado em 12 meses, sem contar rendimentos?", 1440,
       "15% de 800 = 120 por mês; 120 × 12 = 1.440."),
     N("Pedro guarda R$ 20 por semana. Se passar a guardar R$ 35 por semana, quanto ele guarda A MAIS em 12 semanas?", 180,
       "A diferença é 35 − 20 = 15 por semana; 15 × 12 = 180. Repare que a pergunta é a diferença, não o total."),
     Q("Duas estratégias por 6 meses. A: guardar R$ 100 no fim do mês, se sobrar (nos últimos 6 meses, sobrou em só 2). B: separar R$ 60 todo mês no dia em que recebe. Qual guarda mais?",
       ["A, porque o valor mensal é maior", "B: guarda R$ 360 contra R$ 200, porque separar primeiro não depende de sobrar",
        "As duas guardam o mesmo valor", "A, porque guardar no fim do mês evita faltar dinheiro"], 1,
       "A guardou 2 × 100 = 200; B guardou 6 × 60 = 360. Um valor menor e constante venceu um valor maior e incerto."),
     C("Classifique cada atitude:", ["Ajuda a manter o hábito", "Atrapalha o hábito"],
       [["Transferência automática no dia do pagamento", 0], ["Guardar só o que sobrar no fim do mês", 1], ["Ajustar o valor quando a renda muda", 0],
        ["Esperar juntar um valor alto para começar", 1], ["Ter uma meta com valor e prazo", 0], ["Usar o dinheiro guardado em compras por impulso", 1]],
       "Automatizar, ajustar e ter um objetivo sustentam o hábito. Depender da sobra, adiar o começo e mexer no guardado sem motivo o enfraquecem.")],
    ["Pequenos valores constantes somam bastante.", "Separe primeiro, gaste depois.", "Revise o valor quando sua renda mudar."], ["bcb"])]},

 {"key": "controle", "level": 2, "level_name": "Básico", "title": "Controle de gastos",
  "description": "Receitas e despesas, necessidades x desejos e organização mensal.", "topics": [
  L("organizacao", "Receitas e despesas",
    "Registrar e classificar receitas e despesas.",
    "Receita é todo dinheiro que entra. Despesa é todo dinheiro que sai. Registrar as duas mostra o resultado do mês: receitas menos despesas. Gastos fixos se repetem com valor parecido; variáveis mudam de mês a mês. A parcela de uma compra também é despesa do mês em que é paga.",
    "Em setembro, Caio recebeu R$ 300 de mesada e vendeu bolos por R$ 120. Gastou R$ 260 com lanche e transporte. Resultado: 420 − 260 = R$ 160.",
    [C("Classifique cada item:", ["Receita", "Despesa"],
       [["Mesada", 0], ["Passagem de ônibus", 1], ["Venda de bolo", 0], ["Assinatura de streaming", 1], ["Dinheiro recebido de presente", 0], ["Parcela do celular", 1]],
       "Entrou dinheiro: receita. Saiu dinheiro: despesa — inclusive a parcela de uma compra feita antes."),
     N("Em outubro, Caio recebeu R$ 300 de mesada e R$ 180 vendendo bolos. Gastou R$ 120 com lanche, R$ 90 com transporte e pagou R$ 150 da parcela de uma compra. Qual foi o resultado do mês?", 120,
       "Receitas: 300 + 180 = 480. Despesas: 120 + 90 + 150 = 360. Resultado: 480 − 360 = 120."),
     C("Classifique cada gasto:", ["Gasto fixo", "Gasto variável"],
       [["Mensalidade do curso de inglês", 0], ["Lanches na escola", 1], ["Assinatura de streaming", 0], ["Cinema com amigos", 1], ["Plano de celular", 0], ["Presentes de aniversário", 1]],
       "Fixos se repetem com valor parecido todo mês (mensalidades, assinaturas, planos). Variáveis mudam conforme o uso.")],
    ["Receita entra, despesa sai.", "Resultado do mês = receitas − despesas.", "Fixos são previsíveis; variáveis mudam."], ["bcb"]),
  L("erros", "Necessidades, desejos e impulso",
    "Separar necessidades de desejos e reconhecer compras por impulso.",
    "Necessidades são gastos essenciais, como alimentação, transporte para estudar e material escolar. Desejos trazem prazer, mas podem esperar. Compra por impulso é a que acontece sem planejamento, geralmente por emoção ou promoção. Parcelar 'sem juros' também merece conta: compare o total parcelado com o preço à vista.",
    "Você entra na loja para comprar um caderno e sai com um fone em promoção. O caderno era necessidade; o fone foi compra por impulso.",
    [C("Classifique cada gasto:", ["Necessidade", "Desejo"],
       [["Material escolar", 0], ["Passagem para ir à escola", 0], ["Jogo novo em lançamento", 1], ["Tênis de marca só por moda", 1], ["Conta de luz", 0], ["Trocar um celular que ainda funciona bem", 1]],
       "Necessidades são essenciais; desejos podem esperar. A fronteira varia de pessoa para pessoa, o importante é pensar antes de gastar."),
     M("Quais sinais indicam uma compra por impulso? Marque todos.",
       ["Estava na lista de compras planejada", "Comprei com pressa, por causa de uma promoção 'só hoje'", "Comprei depois de comparar preços por alguns dias",
        "Comprei para me sentir melhor na hora, sem pensar", "Parcelei sem somar as parcelas que já tinha no mês", "Esperei 24 horas e ainda achava a compra necessária"], [1, 3, 4],
       "Pressa, emoção e parcelar sem fazer a conta são sinais. Planejar, comparar e esperar 24 horas são o oposto."),
     N("Um fone custa R$ 200 à vista ou 10× de R$ 24 'sem juros' na promoção. Quanto você paga A MAIS escolhendo o parcelado?", 40,
       "Parcelado: 10 × 24 = 240. À vista: 200. A diferença é 240 − 200 = 40 — o 'sem juros' escondia um preço maior."),
     Q("Bruna tem R$ 100 livres no mês. Viu um tênis de R$ 90 em promoção que acaba hoje, mas a mochila da escola rasgou e uma nova custa R$ 70. Qual decisão segue melhor o que você aprendeu?",
       ["Comprar o tênis, porque a promoção acaba hoje", "Comprar a mochila e planejar o tênis para quando couber no orçamento",
        "Parcelar o tênis e a mochila juntos para levar os dois", "Não comprar nada, porque todo gasto é ruim"], 1,
       "A mochila é necessidade; o tênis é desejo com pressão de promoção. Parcelar os dois compromete os próximos meses, e deixar a necessidade sem resolver também não ajuda.")],
    ["Necessidade é essencial; desejo pode esperar.", "Impulso = sem planejamento, por emoção ou pressa.", "Esperar 24 horas ajuda a decidir."], ["bcb"]),
  L("ferramentas", "Organização mensal",
    "Montar uma rotina simples de revisão mensal.",
    "Uma boa rotina tem três passos: registrar, categorizar e revisar. Comparar o que você planejou com o que gastou, categoria por categoria, mostra onde ajustar. O melhor método é o que você consegue manter.",
    "No fim do mês, Rita vê que gastou R$ 150 com lazer, mas tinha planejado R$ 100. No mês seguinte, ela reduz as saídas ou aumenta o limite de forma consciente.",
    [C("Em qual passo da rotina está cada ação?", ["Registrar", "Categorizar", "Revisar"],
       [["Anotar o lanche no app logo depois de pagar", 0], ["Marcar a compra do caderno como Educação", 1], ["Comparar o gasto de lazer com o planejado no fim do mês", 2],
        ["Lançar o valor da passagem de ônibus", 0], ["Separar os gastos do mês entre fixos e variáveis", 1], ["Decidir reduzir o delivery no mês seguinte", 2]],
       "Registrar é anotar cada valor; categorizar é dar um grupo a ele; revisar é comparar e decidir o que muda."),
     N("Rita planejou: lazer R$ 100, transporte R$ 120 e alimentação R$ 250. Gastou: lazer R$ 150, transporte R$ 110 e alimentação R$ 270. Somando as três categorias, quanto ela passou do total planejado?", 60,
       "Planejado: 100 + 120 + 250 = 470. Gasto: 150 + 110 + 270 = 530. Passou 530 − 470 = 60."),
     Q("Pelos números de Rita, qual ajuste é mais coerente para o próximo mês?",
       ["Cortar transporte, porque foi a categoria que mais estourou", "Rever o lazer, que passou R$ 50 do planejado e explica a maior parte do excesso",
        "Não mudar nada, porque R$ 60 é pouco", "Parar de registrar, porque os números só trazem preocupação"], 1,
       "Transporte ficou R$ 10 abaixo; alimentação passou R$ 20; lazer passou R$ 50. O maior desvio é o primeiro lugar para olhar."),
     N("Rita recebe R$ 1.000 por mês. Com as despesas de R$ 530, que porcentagem da renda sobrou?", 47,
       "Sobrou 1.000 − 530 = 470. 470 ÷ 1.000 = 0,47, ou seja, 47%.", unit="%")],
    ["Registrar, categorizar e revisar.", "Compare planejado e realizado.", "O melhor método é o que você mantém."], ["bcb"])]},

 {"key": "planejamento", "level": 3, "level_name": "Intermediário", "title": "Planejamento financeiro",
  "description": "Metas com prazo, orçamento pessoal e a regra 50/30/20 como exemplo.", "topics": [
  L("metas", "Definindo metas",
    "Transformar um objetivo em valor, prazo e contribuição mensal.",
    "Uma meta clara tem objetivo, valor-alvo e prazo. Dividir o que falta pelos meses em que você realmente vai conseguir guardar dá uma referência de quanto separar por mês. Em geral, curto prazo é até 1 ano, médio prazo de 1 a 5 anos e longo prazo acima disso.",
    "Para um notebook de R$ 3.000, já com R$ 900 guardados, faltam R$ 2.100. Em 7 meses, isso dá R$ 300 por mês.",
    [N("Meta de R$ 3.000 com R$ 900 já reservados. Quanto falta?", 2100, "3.000 − 900 = 2.100."),
     N("Faltam R$ 2.100 e o prazo é de 7 meses, mas Paulo sabe que em um desses meses não vai conseguir guardar nada. Quanto ele precisa guardar em cada um dos outros meses?", 350,
       "Ele guarda em 7 − 1 = 6 meses: 2.100 ÷ 6 = 350. Planejar com os meses reais evita ficar para trás."),
     C("Classifique o prazo de cada objetivo:", ["Curto prazo", "Médio prazo", "Longo prazo"],
       [["Presente de aniversário daqui a 2 meses", 0], ["Notebook daqui a 2 anos", 1], ["Entrada da faculdade daqui a 8 anos", 2], ["Viagem de formatura daqui a 3 anos", 1], ["Passeio no mês que vem", 0]],
       "Uma referência: até 1 ano é curto, de 1 a 5 é médio e acima de 5 é longo."),
     Q("Qual destas é uma meta bem definida?",
       ["Quero guardar dinheiro", "Quero juntar R$ 1.200 para um curso até dezembro, guardando R$ 150 por mês", "Quero ficar rico", "Vou guardar quando sobrar"], 1,
       "Só a segunda tem objetivo, valor, prazo e contribuição mensal. As outras não permitem saber se você está no caminho.")],
    ["Meta = objetivo + valor + prazo.", "Falta ÷ meses em que você guarda = valor mensal.", "Prazos: curto, médio e longo."], ["bcb"]),
  L("plano", "Orçamento pessoal",
    "Montar um orçamento fictício usando a regra 50/30/20 como ponto de partida.",
    "A regra 50/30/20 sugere dividir a renda em 50% para necessidades, 30% para desejos e 20% para poupança e metas. É um exemplo adaptável: cada realidade pede ajustes. Quando as necessidades passam de 50%, o espaço para desejos diminui se você quiser manter a poupança. Revise o plano sempre que a renda ou os objetivos mudarem. Aqui você usa só valores fictícios.",
    "Com R$ 1.000 fictícios: R$ 500 em necessidades, R$ 300 em desejos e R$ 200 para poupar.",
    [B("Distribua a renda fictícia de R$ 1.200. Regras: no mínimo 15% para poupança, no máximo 55% para necessidades e no máximo 30% para desejos. A soma precisa fechar 100%.",
       ["Necessidades", "Desejos", "Poupança"], "R$ 1.200,00 (fictício)", {"sum": 100, "min": {"2": 15}, "max": {"0": 55, "1": 30}},
       "Distribuições possíveis: 50% / 30% / 20% ou 55% / 30% / 15%.", "Vários planos servem, desde que fechem 100% e respeitem os três limites. A 50/30/20 é só um ponto de partida."),
     N("A renda de Maria é R$ 1.200 e as necessidades dela somam R$ 720. Se ela mantiver 20% da renda para poupança, quanto sobra por mês para desejos?", 240,
       "Poupança: 20% de 1.200 = 240. Desejos: 1.200 − 720 − 240 = 240."),
     Q("Pelos números de Maria, que fatia da renda as necessidades ocupam e o que isso indica?",
       ["40%: abaixo da referência de 50%", "60%: acima da referência de 50%, então vale rever gastos essenciais ou aceitar menos desejos",
        "50%: exatamente na referência", "72%: o orçamento é impossível"], 1,
       "720 ÷ 1.200 = 0,6, ou seja, 60%. Acima de 50%, algo precisa ceder para manter a poupança.")],
    ["50/30/20 é um exemplo, não uma regra fixa.", "O orçamento precisa fechar 100% da renda.", "Revise sempre que algo mudar."], ["bcb"])]},

 {"key": "investimentos", "level": 4, "level_name": "Avançado", "title": "Introdução aos investimentos",
  "description": "Juros, inflação, Selic, liquidez, risco e retorno, Tesouro Direto, CDB e fundos imobiliários.", "topics": [
  L("tesouro", "Tesouro Direto",
    "Entender o que é o Tesouro Direto e o que muda entre os títulos.",
    "O Tesouro Direto é um programa em que o governo federal vende títulos públicos a pessoas físicas. Há títulos com prazos e formas de remuneração diferentes: o Tesouro Selic acompanha a taxa básica de juros e oscila pouco; o prefixado tem a taxa combinada na compra; o IPCA+ paga a inflação mais uma taxa. Consulte preços e regras atuais no site oficial.",
    "Ao comprar um título, você empresta dinheiro ao governo e recebe de volta com remuneração no prazo combinado.",
    [Q("Quem emite os títulos do Tesouro Direto?", ["Um banco privado", "O governo federal", "A bolsa de valores", "O Procon"], 1, "Os títulos são públicos, emitidos pelo governo federal."),
     C("Relacione cada característica ao título:", ["Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"],
       [["Rende de acordo com a taxa básica de juros", 0], ["Você sabe a taxa exata no momento da compra", 1], ["Paga a inflação do período mais uma taxa", 2],
        ["Costuma ser usado para reserva de emergência, por oscilar pouco", 0], ["Protege o poder de compra em objetivos longos", 2]],
       "Selic: segue os juros básicos e oscila pouco. Prefixado: taxa travada na compra. IPCA+: inflação mais uma taxa, pensado para o longo prazo."),
     Q("Vender um título prefixado antes do vencimento...", ["Sempre garante o valor combinado na compra", "Pode render menos ou mais, conforme o preço do título no dia da venda", "É proibido", "Não tem nenhum custo nem imposto"], 1,
       "A taxa combinada só é garantida se você levar até o vencimento. Antes disso, vale o preço de mercado do dia.")],
    ["Títulos públicos são emitidos pelo governo federal.", "Selic, prefixado e IPCA+ remuneram de formas diferentes.", "Consulte regras atuais no site oficial."], ["td", "bcb"]),
  L("selic", "Selic, juros e inflação",
    "Relacionar Selic, juros e inflação.",
    "A Selic é a taxa básica de juros da economia e é definida periodicamente pelo Copom, do Banco Central. Juros são o preço do dinheiro no tempo, e os juros compostos incidem sobre o valor já acrescido. Inflação é o aumento geral dos preços, que reduz o poder de compra. Uma aproximação útil: ganho real ≈ rendimento − inflação. Consulte a taxa vigente no Banco Central.",
    "Se um lanche custava R$ 10 e hoje custa R$ 11, houve inflação: o mesmo dinheiro compra menos.",
    [Q("Quem define a meta da Selic?", ["O Copom, do Banco Central", "O Tesouro Direto", "A CVM", "Cada banco"], 0, "O Copom se reúne periodicamente e define a meta da Selic."),
     N("R$ 100 rendem 10% ao ano, com juros compostos, por 2 anos. Qual o total?", 121,
       "Ano 1: 110. Ano 2: 110 × 1,10 = 121. Os juros do segundo ano incidem sobre 110, não sobre 100."),
     N("Um investimento rendeu 10% em um ano e a inflação do período foi 4%. Pela aproximação rendimento − inflação, qual foi o ganho real, em %?", 6,
       "10 − 4 = 6. O saldo cresceu 10%, mas como os preços subiram 4%, o poder de compra cresceu cerca de 6%.", unit="%"),
     Q("Um produto rendeu 5% no ano e a inflação foi 6%. O que aconteceu com quem investiu?",
       ["Ganhou poder de compra, porque o saldo aumentou", "Perdeu cerca de 1% de poder de compra, mesmo com saldo maior", "Ficou exatamente igual", "Perdeu 5% do dinheiro"], 1,
       "5 − 6 = −1. O número na conta subiu, mas os preços subiram mais: dá para comprar um pouco menos do que antes.")],
    ["A Selic é a taxa básica e é definida pelo Copom.", "Juros compostos incidem sobre o valor já acrescido.", "Ganho real ≈ rendimento − inflação."], ["bcb"]),
  L("fii", "Fundos imobiliários",
    "Compreender risco e retorno nos fundos imobiliários.",
    "Fundos imobiliários reúnem dinheiro de vários investidores para aplicar em ativos do setor imobiliário. As cotas são negociadas em bolsa e o preço oscila. Rendimentos não são garantidos: dependem do desempenho do fundo, por exemplo de imóveis alugados ou vagos. Fundos imobiliários não têm a garantia do FGC. O resultado de quem investe soma os rendimentos recebidos e a variação do preço da cota.",
    "Uma cota comprada a R$ 100 pode valer R$ 92 ou R$ 108 dias depois, e o rendimento mensal também pode variar.",
    [Q("Sobre fundos imobiliários, é correto dizer:", ["O rendimento é garantido", "As cotas podem oscilar e o rendimento pode variar", "Não têm risco", "Só grandes investidores podem comprar"], 1, "Preço e rendimento variam. Não existe garantia de retorno."),
     M("Quais riscos existem em fundos imobiliários? Marque todos.",
       ["Queda no preço da cota", "Imóveis vagos reduzirem os rendimentos", "Perder a garantia do FGC, que cobre o valor investido",
        "Não conseguir vender a cota rápido pelo preço desejado", "Receber um rendimento fixo menor que o combinado na compra"], [0, 1, 3],
       "Preço, vacância e liquidez são riscos reais. Não existe garantia do FGC para fundos, nem rendimento fixo combinado."),
     N("Uma cota foi comprada por R$ 100, pagou R$ 0,80 de rendimento por mês durante 12 meses e no fim do ano valia R$ 92. Somando rendimentos e variação da cota, qual foi o resultado, em reais, por cota?", 1.6,
       "Rendimentos: 0,80 × 12 = 9,60. Variação da cota: 92 − 100 = −8,00. Resultado: 9,60 − 8,00 = 1,60."),
     Q("Que relação costuma existir entre risco e retorno?", ["Maior retorno esperado costuma vir com maior risco", "Não há relação", "Menor risco sempre rende mais", "O retorno é sempre garantido"], 0, "Quanto maior o retorno que se espera, em geral maior o risco assumido.")],
    ["Cotas oscilam e rendimentos variam.", "Resultado = rendimentos + variação da cota.", "Nada de lucro garantido."], ["cvm"]),
  L("outros", "Liquidez, risco e diversificação",
    "Comparar liquidez, risco e diversificação em produtos básicos, como o CDB.",
    "O CDB é um título emitido por bancos para captar dinheiro. Compare sempre risco, retorno esperado, liquidez, custos e tributação. Diversificar é não concentrar todo o dinheiro em um só investimento: o resultado total é a soma do que cada parte rendeu ou perdeu. Nenhum investimento deve ser tratado como lucro garantido, e promessas de retorno alto 'sem risco' são sinal de golpe.",
    "Marta deixa a reserva de emergência em algo de fácil resgate e coloca um objetivo distante em um produto de prazo maior.",
    [M("Quais cuidados ajudam a avaliar um investimento? Marque todos.",
       ["Comparar liquidez e prazo", "Confiar em promessa de lucro garantido", "Conferir custos e tributação", "Diversificar",
        "Colocar tudo no produto que mais rendeu no ano passado", "Verificar se a instituição é autorizada pela CVM ou pelo Banco Central"], [0, 2, 3, 5],
       "Desconfie de lucro garantido e de rentabilidade passada como promessa. Compare prazo, custos e tributação, diversifique e confira a autorização da instituição."),
     C("Para cada objetivo, qual tipo de aplicação combina mais?", ["Resgate rápido e baixo risco", "Prazo longo, pode oscilar"],
       [["Reserva de emergência", 0], ["Aposentadoria daqui a 30 anos", 1], ["Conserto que pode surgir a qualquer momento", 0], ["Entrada de um imóvel daqui a 10 anos", 1], ["Viagem do mês que vem", 0]],
       "Dinheiro que pode ser necessário logo pede liquidez e pouco risco. Objetivos distantes aguentam oscilações em busca de mais retorno."),
     N("Marta tem R$ 10.000: 60% num CDB que rendeu 10% no ano e 40% num fundo que perdeu 5%. Qual foi o resultado total, em reais?", 400,
       "CDB: 6.000 × 10% = +600. Fundo: 4.000 × (−5%) = −200. Total: 600 − 200 = 400. Diversificar reduziu o impacto da perda."),
     Q("Alguém oferece 'rendimento garantido de 5% ao mês, sem risco', pedindo PIX para uma pessoa física. O que fazer?",
       ["Investir pouco para testar", "Desconfiar: retorno alto, garantido e sem risco é sinal clássico de golpe; verificar a autorização na CVM",
        "Investir, porque 5% ao mês é ótimo", "Pedir para um amigo investir primeiro"], 1,
       "Não existe retorno alto garantido sem risco. Pagamento para pessoa física e pressa são outros alertas.")],
    ["CDB é emitido por bancos.", "Compare liquidez, risco, custos e tributação.", "Diversificar reduz a dependência de um só produto."], ["cvm", "td"])]},
]


def public_module(m):
    """Versão enviada ao navegador: sem respostas nem correções."""
    out = {k: m[k] for k in ("key", "level", "level_name", "title", "description")}
    out["topics"] = []
    for t in m["topics"]:
        acts = []
        for a in t["acts"]:
            p = {"t": a["t"], "q": a["q"]}
            if a["t"] in ("quiz", "multi"): p["opts"] = a["opts"]
            elif a["t"] == "classify": p["buckets"] = a["buckets"]; p["items"] = [i[0] for i in a["items"]]
            elif a["t"] == "calc": p["unit"] = a["unit"]
            elif a["t"] == "budget": p["cats"] = a["cats"]; p["total"] = a["total"]
            acts.append(p)
        pt = {k: t[k] for k in ("key", "title", "goal", "explain", "example", "summary", "sources", "reviewed")}
        pt["acts"] = acts
        out["topics"].append(pt)
    return out


def parse_number(x):
    """Aceita 3600, 3.600, 3600,00, 1.200,50 e R$ 121. Levanta ValueError se não for número."""
    if isinstance(x, bool):
        raise ValueError
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        s = str(x).strip().replace("R$", "").replace(" ", "")
        if not re.fullmatch(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?|-?\d+\.\d+", s):
            raise ValueError
        v = float(s.replace(".", "").replace(",", ".") if "," in s or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s) else s)
    if not math.isfinite(v):
        raise ValueError
    return v


def grade_item(a, x):
    """Retorna (fração 0..1, texto da resposta esperada). Levanta ValueError para entrada inválida."""
    t = a["t"]
    if t == "quiz":
        if isinstance(x, bool) or int(x) not in range(len(a["opts"])): raise ValueError
        return (1.0 if int(x) == a["ans"] else 0.0), a["opts"][a["ans"]]
    if t == "multi":
        got = sorted(set(int(i) for i in x))
        if not got or any(i not in range(len(a["opts"])) for i in got): raise ValueError
        return (1.0 if got == sorted(a["ans"]) else 0.0), "; ".join(a["opts"][i] for i in a["ans"])
    if t == "classify":
        if len(x) != len(a["items"]): raise ValueError
        ok = sum(1 for i, it in enumerate(a["items"]) if int(x[i]) == it[1])
        return ok / len(a["items"]), "; ".join(f'{it[0]}: {a["buckets"][it[1]]}' for it in a["items"])
    if t == "calc":
        v = parse_number(x)
        if a["unit"] == "R$":
            right = f'R$ {a["ans"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            right = f'{a["ans"]:g}'.replace(".", ",") + ("%" if a["unit"] == "%" else " " + a["unit"])
        return (1.0 if abs(v - a["ans"]) < 0.005 else 0.0), right
    if t == "budget":
        v = [int(i) for i in x]
        r = a["rules"]
        good = len(v) == len(a["cats"]) and all(0 <= i <= 100 for i in v) and sum(v) == r["sum"] \
            and all(v[int(k)] >= n for k, n in r["min"].items()) \
            and all(v[int(k)] <= n for k, n in r["max"].items())
        return (1.0 if good else 0.0), a["right"]
    raise ValueError
