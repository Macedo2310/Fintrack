import moderation as m


def test_bloqueia_ofensas_e_variacoes():
    for t in ["Você é um filho da puta", "porrrra de app", "vsf", "V1AD0", "vou te matar", "Puta merda"]:
        assert m.offensive(t), t


def test_nao_bloqueia_texto_comum():
    for t in ["computador novo", "Bettina comprou cuscuz", "sou burro com dinheiro", "disputa de preços",
              "rola uma promoção amanhã", "a planta vai morrer sem água", "curso de finanças"]:
        assert not m.offensive(t), t


def test_reconhece_pedido_de_socorro_sem_bloquear():
    assert m.self_harm("não quero mais viver") and not m.offensive("não quero mais viver")
    assert not m.self_harm("quero matar a saudade")
    assert "188" in m.SUPPORT_REPLY
