import csv

from rules.buy_rules import calcula_score_compra
from recommendation import recomendacao
from recommendation import prioridade
from portfolio_reader import carregar_portfolio

portfolio = carregar_portfolio()

compras = []

with open("market_data.csv", "r") as arquivo:

    leitor = csv.DictReader(arquivo)

    for linha in leitor:

        ticker = linha["Ticker"]
        rsi = float(linha["RSI"])
        dividend_yield = float(linha["Yield"])
        distancia = float(linha["DistanciaMaxima"])

        score_compra, motivos_compra = calcula_score_compra(
            rsi,
            dividend_yield,
            distancia
        )

        possui = ticker in portfolio

        if possui:
            status = "COMPRAR MAIS"
            quantidade = portfolio[ticker]["quantidade"]
            custo = portfolio[ticker]["custo"]
        else:
            status = "INICIAR POSICAO"
            quantidade = 0
            custo = 0

        compras.append({
            "ticker": ticker,
            "score": score_compra,
            "motivos": motivos_compra,
            "recomendacao": recomendacao(score_compra),
            "prioridade": prioridade(score_compra),
            "status": status,
            "quantidade": quantidade,
            "custo": custo
        })

compras.sort(
    key=lambda acao: acao["score"],
    reverse=True
)

print()
print("====================================")
print("      BALDI MARKET SCANNER")
print("====================================")

ranking = 1

for acao in compras:

    if acao["score"] > 0:

        print()
        print("#", ranking, "-", acao["ticker"])

        print("Score:", acao["score"])

        print("Recomendacao:", acao["recomendacao"])

        print("Prioridade:", acao["prioridade"])

        print("Acao Sugerida:", acao["status"])

        if acao["quantidade"] > 0:

            print("Quantidade Atual:", acao["quantidade"])

            print("Custo Medio:", acao["custo"])

        print("Motivos:")

        for motivo in acao["motivos"]:
            print(" ", motivo)

        print("------------------------------------")

        ranking += 1