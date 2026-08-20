def recomendacao(score):

    if score >= 70:
        return "COMPRA FORTE"

    elif score >= 50:
        return "COMPRA"

    elif score >= 20:
        return "OBSERVAR"

    else:
        return "IGNORAR"


def prioridade(score):

    if score >= 70:
        return "ALTA"

    elif score >= 50:
        return "MEDIA"

    elif score >= 20:
        return "BAIXA"

    else:
        return "NENHUMA"
