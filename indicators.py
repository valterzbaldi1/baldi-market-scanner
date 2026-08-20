import pandas as pd


def calcular_rsi(series, periodo=14):

    delta = series.diff()

    ganho = delta.where(delta > 0, 0)

    perda = -delta.where(delta < 0, 0)

    media_ganhos = ganho.rolling(periodo).mean()

    media_perdas = perda.rolling(periodo).mean()

    rs = media_ganhos / media_perdas

    rsi = 100 - (100 / (1 + rs))

    return round(float(rsi.iloc[-1]), 2)
