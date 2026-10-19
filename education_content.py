# -*- coding: utf-8 -*-
"""Curso de educação financeira do FinTrack: 4 níveis, 12 aulas, atividades interativas.
As respostas corretas ficam só no servidor; o navegador recebe apenas o enunciado."""

SRC = {
 "bcb": {"n": "Banco Central do Brasil — Cidadania Financeira", "u": "https://www.bcb.gov.br/cidadaniafinanceira"},
 "cvm": {"n": "Portal do Investidor (CVM)", "u": "https://www.investidor.gov.br"},
 "td": {"n": "Tesouro Direto", "u": "https://www.tesourodireto.com.br"},
}
REVIEWED = "2026-09"
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
    [Q("Qual afirmação está correta?", ["Poupar e investir são exatamente a mesma coisa", "Poupar é o hábito de separar dinheiro; investir é aplicá-lo em um produto financeiro", "Só quem tem caderneta de poupança está poupando", "Investir nunca envolve risco"], 1,
       "Poupar é o hábito; investir é a decisão de onde aplicar. A caderneta é só um dos produtos possíveis."),
     C("Classifique cada situação:", ["Hábito de poupar", "Produto financeiro"],
       [["Separar R$ 30 da mesada todo mês", 0], ["Caderneta de poupança", 1], ["Guardar parte do pagamento de um trabalho eventual", 0], ["CDB", 1]],
       "O hábito vem primeiro. Produtos financeiros são os lugares onde o dinheiro separado pode ficar.")],
    ["Poupar é um hábito; investir é uma escolha de aplicação.", "A caderneta é um produto, não sinônimo de poupar.", "Todo produto tem risco, liquidez e rendimento próprios."], ["bcb", "cvm"]),
  L("vantagens", "Reserva de emergência",
    "Entender para que serve a reserva de emergência e quanto ela deve cobrir.",
    "Reserva de emergência é dinheiro guardado para imprevistos, como um conserto urgente ou uma perda de renda. Ela precisa estar disponível rápido (liquidez) e com baixo risco de perda. Uma referência comum é cobrir alguns meses de gastos essenciais.",
    "Se os gastos essenciais de Lucas são R$ 1.200 por mês e ele quer uma reserva de 3 meses, o alvo é R$ 3.600.",
    [M("Quais situações justificam usar a reserva de emergência?", ["Conserto urgente do celular que você usa para estudar", "Promoção de um jogo novo", "Perda temporária de renda", "Ingresso de show"], [0, 2],
       "Reserva é para imprevistos e necessidades urgentes, não para desejos ou promoções."),
     N("Gastos essenciais de R$ 1.200 por mês. Qual o valor de uma reserva de 3 meses?", 3600, "1.200 × 3 = 3.600. O número de meses é uma referência que você adapta à sua realidade."),
     Q("Qual característica é mais importante numa reserva de emergência?", ["Rentabilidade máxima", "Liquidez: poder usar o dinheiro rápido", "Ficar preso por anos", "Risco alto"], 1,
       "Num imprevisto, o dinheiro precisa estar disponível rapidamente.")],
    ["Reserva é para imprevistos, não para desejos.", "Liquidez e segurança vêm antes de rentabilidade.", "Uma referência: alguns meses de gastos essenciais."], ["bcb"]),
  L("dicas", "Começando com pouco",
    "Criar o hábito de guardar mesmo com valores pequenos.",
    "Consistência vale mais do que valor. Separar um valor possível assim que o dinheiro entra, antes de gastar, é mais eficaz do que tentar guardar o que sobra.",
    "Guardar R$ 25 por semana parece pouco, mas em 12 semanas soma R$ 300.",
    [N("R$ 25 por semana durante 12 semanas. Quanto você terá guardado?", 300, "25 × 12 = 300."),
     Q("Qual estratégia ajuda mais a manter o hábito?", ["Guardar só o que sobrar no fim do mês", "Separar um valor possível assim que o dinheiro entra", "Esperar ter um valor alto para começar", "Guardar só em datas especiais"], 1,
       "Separar primeiro reduz a chance de gastar tudo sem perceber e torna o hábito automático.")],
    ["Pequenos valores constantes somam bastante.", "Separe primeiro, gaste depois.", "Revise o valor quando sua renda mudar."], ["bcb"])]},

 {"key": "controle", "level": 2, "level_name": "Básico", "title": "Controle de gastos",
  "description": "Receitas e despesas, necessidades x desejos e organização mensal.", "topics": [
  L("organizacao", "Receitas e despesas",
    "Registrar e classificar receitas e despesas.",
    "Receita é todo dinheiro que entra. Despesa é todo dinheiro que sai. Registrar as duas mostra o resultado do mês: receitas menos despesas. Gastos fixos se repetem com valor parecido; variáveis mudam de mês a mês.",
    "Em setembro, Caio recebeu R$ 300 de mesada e vendeu bolos por R$ 120. Gastou R$ 260 com lanche e transporte. Resultado: 420 − 260 = R$ 160.",
    [C("Classifique cada item:", ["Receita", "Despesa"],
       [["Mesada", 0], ["Passagem de ônibus", 1], ["Venda de bolo", 0], ["Lanche na escola", 1], ["Assinatura de streaming", 1], ["Dinheiro de presente", 0]],
       "Entrou dinheiro: receita. Saiu dinheiro: despesa."),
     N("Receitas de R$ 420 e despesas de R$ 260. Qual o resultado do mês?", 160, "420 − 260 = 160. Resultado positivo significa que sobrou dinheiro."),
     Q("Um gasto fixo é aquele que...", ["Muda muito todo mês", "Se repete com valor parecido, como assinatura ou mensalidade", "Só acontece uma vez", "Sempre é um desejo"], 1,
       "Gastos fixos são previsíveis. Os variáveis, como lazer e lanches, mudam.")],
    ["Receita entra, despesa sai.", "Resultado do mês = receitas − despesas.", "Fixos são previsíveis; variáveis mudam."], ["bcb"]),
  L("erros", "Necessidades, desejos e impulso",
    "Separar necessidades de desejos e reconhecer compras por impulso.",
    "Necessidades são gastos essenciais, como alimentação, transporte para estudar e material escolar. Desejos trazem prazer, mas podem esperar. Compra por impulso é a que acontece sem planejamento, geralmente por emoção ou promoção.",
    "Você entra na loja para comprar um caderno e sai com um fone em promoção. O caderno era necessidade; o fone foi compra por impulso.",
    [C("Classifique cada gasto:", ["Necessidade", "Desejo"],
       [["Material escolar", 0], ["Passagem para ir à escola", 0], ["Jogo novo em lançamento", 1], ["Tênis de marca só por moda", 1], ["Conta de luz", 0]],
       "Necessidades são essenciais; desejos podem esperar. A fronteira varia de pessoa para pessoa, o importante é pensar antes de gastar."),
     M("Quais sinais indicam uma compra por impulso?", ["Estava na lista de compras planejada", "Comprei por pressa, por causa de uma promoção", "Comprei depois de comparar preços por alguns dias", "Comprei para me sentir melhor na hora, sem pensar"], [1, 3],
       "Pressa, emoção e falta de planejamento são sinais. Esperar 24 horas antes de comprar ajuda a decidir melhor.")],
    ["Necessidade é essencial; desejo pode esperar.", "Impulso = sem planejamento, por emoção ou pressa.", "Esperar 24 horas ajuda a decidir."], ["bcb"]),
  L("ferramentas", "Organização mensal",
    "Montar uma rotina simples de revisão mensal.",
    "Uma boa rotina tem três passos: registrar, categorizar e revisar. Comparar o que você planejou com o que gastou mostra onde ajustar. O melhor método é o que você consegue manter.",
    "No fim do mês, Rita vê que gastou R$ 150 com lazer, mas tinha planejado R$ 100. No mês seguinte, ela reduz as saídas ou aumenta o limite de forma consciente.",
    [Q("Qual é o objetivo da revisão mensal?", ["Se culpar pelos gastos", "Comparar o planejado com o realizado e ajustar", "Apagar os registros", "Gastar o que sobrou"], 1, "Revisar serve para aprender e ajustar, sem culpa."),
     N("Planejado para lazer: R$ 100. Gasto real: R$ 150. Quanto passou do planejado?", 50, "150 − 100 = 50."),
     Q("Qual método de controle é o melhor?", ["O mais complexo", "O que você consegue manter com consistência", "Somente planilhas", "Somente aplicativos"], 1, "Caderno, planilha ou app: vale o que você realmente usa.")],
    ["Registrar, categorizar e revisar.", "Compare planejado e realizado.", "O melhor método é o que você mantém."], ["bcb"])]},

 {"key": "planejamento", "level": 3, "level_name": "Intermediário", "title": "Planejamento financeiro",
  "description": "Metas com prazo, orçamento pessoal e a regra 50/30/20 como exemplo.", "topics": [
  L("metas", "Definindo metas",
    "Transformar um objetivo em valor, prazo e contribuição mensal.",
    "Uma meta clara tem objetivo, valor-alvo e prazo. Dividir o que falta pelos meses restantes dá uma referência de quanto guardar por mês. Em geral, curto prazo é até 1 ano, médio prazo de 1 a 5 anos e longo prazo acima disso.",
    "Para um notebook de R$ 3.000, já com R$ 900 guardados, faltam R$ 2.100. Em 7 meses, isso dá R$ 300 por mês.",
    [N("Meta de R$ 3.000 com R$ 900 já reservados. Quanto falta?", 2100, "3.000 − 900 = 2.100."),
     N("Faltam R$ 2.100 e você tem 7 meses. Quanto guardar por mês?", 300, "2.100 ÷ 7 = 300."),
     C("Classifique o prazo de cada objetivo:", ["Curto prazo", "Médio prazo", "Longo prazo"],
       [["Presente de aniversário daqui a 2 meses", 0], ["Notebook daqui a 2 anos", 1], ["Entrada da faculdade daqui a 8 anos", 2], ["Passeio no mês que vem", 0]],
       "Uma referência: até 1 ano é curto, de 1 a 5 é médio e acima de 5 é longo.")],
    ["Meta = objetivo + valor + prazo.", "Falta ÷ meses = valor mensal de referência.", "Prazos: curto, médio e longo."], ["bcb"]),
  L("plano", "Orçamento pessoal",
    "Montar um orçamento fictício usando a regra 50/30/20 como ponto de partida.",
    "A regra 50/30/20 sugere dividir a renda em 50% para necessidades, 30% para desejos e 20% para poupança e metas. É um exemplo adaptável: cada realidade pede ajustes. Revise o plano sempre que a renda ou os objetivos mudarem. Aqui você usa só valores fictícios.",
    "Com R$ 1.000 fictícios: R$ 500 em necessidades, R$ 300 em desejos e R$ 200 para poupar.",
    [B("Distribua a renda fictícia de R$ 1.000 entre as três categorias. Use pelo menos 10% para poupança e no máximo 60% para necessidades. A soma precisa fechar 100%.",
       ["Necessidades", "Desejos", "Poupança"], "R$ 1.000,00 (fictício)", {"sum": 100, "min": {"2": 10}, "max": {"0": 60}},
       "Uma distribuição possível é 50% / 30% / 20%.", "Vários planos servem, desde que fechem 100% e respeitem seus limites. A 50/30/20 é só um ponto de partida."),
     Q("Quando vale revisar o orçamento?", ["Nunca", "Quando renda, gastos ou objetivos mudam", "Só uma vez por ano", "Só quando o dinheiro acaba"], 1,
       "Um plano é vivo: revisar regularmente mantém o orçamento realista.")],
    ["50/30/20 é um exemplo, não uma regra fixa.", "O orçamento precisa fechar 100% da renda.", "Revise sempre que algo mudar."], ["bcb"])]},

 {"key": "investimentos", "level": 4, "level_name": "Avançado", "title": "Introdução aos investimentos",
  "description": "Juros, inflação, Selic, liquidez, risco e retorno, Tesouro Direto, CDB e fundos imobiliários.", "topics": [
  L("tesouro", "Tesouro Direto",
    "Entender o que é o Tesouro Direto e o que muda entre os títulos.",
    "O Tesouro Direto é um programa em que o governo federal vende títulos públicos a pessoas físicas. Há títulos com prazos e formas de remuneração diferentes, como Selic, prefixado e IPCA+. Consulte preços e regras atuais no site oficial.",
    "Ao comprar um título, você empresta dinheiro ao governo e recebe de volta com remuneração no prazo combinado.",
    [Q("Quem emite os títulos do Tesouro Direto?", ["Um banco privado", "O governo federal", "A bolsa de valores", "O Procon"], 1, "Os títulos são públicos, emitidos pelo governo federal."),
     Q("Vender um título antes do vencimento...", ["Sempre garante o mesmo valor", "Pode render menos ou mais, conforme o preço no momento", "É proibido", "Não tem custos"], 1,
       "Alguns títulos oscilam de preço ao longo do tempo. Por isso prazo e objetivo importam.")],
    ["Títulos públicos são emitidos pelo governo federal.", "Prazos e remuneração variam por título.", "Consulte regras atuais no site oficial."], ["td", "bcb"]),
  L("selic", "Selic, juros e inflação",
    "Relacionar Selic, juros e inflação.",
    "A Selic é a taxa básica de juros da economia e é definida periodicamente pelo Copom, do Banco Central. Juros são o preço do dinheiro no tempo, e os juros compostos incidem sobre o valor já acrescido. Inflação é o aumento geral dos preços, que reduz o poder de compra. Consulte a taxa vigente no Banco Central.",
    "Se um lanche custava R$ 10 e hoje custa R$ 11, houve inflação: o mesmo dinheiro compra menos.",
    [Q("Quem define a meta da Selic?", ["O Copom, do Banco Central", "O Tesouro Direto", "A CVM", "Cada banco"], 0, "O Copom se reúne periodicamente e define a meta da Selic."),
     Q("O que a inflação faz com o poder de compra?", ["Aumenta", "Reduz", "Não muda", "Zera"], 1, "Com preços mais altos, o mesmo dinheiro compra menos."),
     N("R$ 100 rendem 10% ao ano, com juros compostos, por 2 anos. Qual o total?", 121, "Ano 1: 110. Ano 2: 110 × 1,10 = 121. Os juros do segundo ano incidem sobre 110, não sobre 100.")],
    ["A Selic é a taxa básica e é definida pelo Copom.", "Juros compostos incidem sobre o valor já acrescido.", "Inflação reduz o poder de compra."], ["bcb"]),
  L("fii", "Fundos imobiliários",
    "Compreender risco e retorno nos fundos imobiliários.",
    "Fundos imobiliários reúnem dinheiro de vários investidores para aplicar em ativos do setor imobiliário. As cotas são negociadas em bolsa e o preço oscila. Rendimentos não são garantidos: dependem do desempenho do fundo.",
    "Uma cota comprada a R$ 100 pode valer R$ 92 ou R$ 108 dias depois, e o rendimento mensal também pode variar.",
    [Q("Sobre fundos imobiliários, é correto dizer:", ["O rendimento é garantido", "As cotas podem oscilar e o rendimento pode variar", "Não têm risco", "Só grandes investidores podem comprar"], 1, "Preço e rendimento variam. Não existe garantia de retorno."),
     Q("Que relação costuma existir entre risco e retorno?", ["Maior retorno esperado costuma vir com maior risco", "Não há relação", "Menor risco sempre rende mais", "O retorno é sempre garantido"], 0, "Quanto maior o retorno que se espera, em geral maior o risco assumido.")],
    ["Cotas oscilam e rendimentos variam.", "Retorno maior costuma vir com risco maior.", "Nada de lucro garantido."], ["cvm"]),
  L("outros", "Liquidez, risco e diversificação",
    "Comparar liquidez, risco e diversificação em produtos básicos, como o CDB.",
    "O CDB é um título emitido por bancos para captar dinheiro. Compare sempre risco, retorno esperado, liquidez, custos e tributação. Diversificar é não concentrar todo o dinheiro em um só investimento. Nenhum investimento deve ser tratado como lucro garantido.",
    "Marta deixa a reserva de emergência em algo de fácil resgate e coloca um objetivo distante em um produto de prazo maior.",
    [Q("O CDB é emitido por...", ["Governo federal", "Bancos", "Bolsa de valores", "Imobiliárias"], 1, "CDB é o Certificado de Depósito Bancário, emitido por bancos."),
     Q("O que significa liquidez?", ["Rapidez para transformar o investimento em dinheiro", "Lucro alto", "Risco baixo", "Isenção de imposto"], 0, "Liquidez é a facilidade e a rapidez de resgatar o dinheiro."),
     M("Quais cuidados ajudam a avaliar um investimento?", ["Comparar liquidez e prazo", "Confiar em promessa de lucro garantido", "Conferir custos e tributação", "Diversificar"], [0, 2, 3],
       "Desconfie de promessas de lucro garantido. Compare prazo, custos, tributação e diversifique.")],
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


def grade_item(a, x):
    """Retorna (fração 0..1, texto da resposta esperada). Levanta ValueError para entrada inválida."""
    t = a["t"]
    if t == "quiz":
        return (1.0 if int(x) == a["ans"] else 0.0), a["opts"][a["ans"]]
    if t == "multi":
        got = sorted(int(i) for i in x)
        return (1.0 if got == sorted(a["ans"]) else 0.0), "; ".join(a["opts"][i] for i in a["ans"])
    if t == "classify":
        if len(x) != len(a["items"]): raise ValueError
        ok = sum(1 for i, it in enumerate(a["items"]) if int(x[i]) == it[1])
        return ok / len(a["items"]), "; ".join(f'{it[0]}: {a["buckets"][it[1]]}' for it in a["items"])
    if t == "calc":
        v = float(str(x).replace(",", "."))
        return (1.0 if abs(v - a["ans"]) < 0.005 else 0.0), f'{a["unit"]} {a["ans"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".")
    if t == "budget":
        v = [int(i) for i in x]
        r = a["rules"]
        good = len(v) == len(a["cats"]) and sum(v) == r["sum"] \
            and all(v[int(k)] >= n for k, n in r["min"].items()) \
            and all(v[int(k)] <= n for k, n in r["max"].items())
        return (1.0 if good else 0.0), a["right"]
    raise ValueError
