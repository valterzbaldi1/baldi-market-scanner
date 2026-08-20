def calcula_score_compra(rsi, dividend_yield, distancia):

    score = 0
    motivos = []

    if rsi < 35:
        score += 30
        motivos.append("+30 RSI abaixo de 35")

    if dividend_yield > 4:
        score += 20
        motivos.append("+20 Yield acima de 4%")

    if distancia <= -10:
        score += 25
        motivos.append("+25 Mais de 10% abaixo da máxima")

    return score, motivos