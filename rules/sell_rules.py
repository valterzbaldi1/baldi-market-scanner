def calcula_score_venda(lucro, rsi):

    score = 0
    motivos = []

    if lucro >= 6:
        score += 50
        motivos.append("+50 Meta de lucro atingida")

    if rsi > 70:
        score += 30
        motivos.append("+30 RSI sobrecomprado")

    if lucro >= 10:
        score += 20
        motivos.append("+20 Lucro acima de 10%")

    return score, motivos