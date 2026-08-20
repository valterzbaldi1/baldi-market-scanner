import csv

def carregar_portfolio():

    portfolio = {}

    with open("portfolio.csv", "r") as arquivo:

        leitor = csv.DictReader(arquivo)

        for linha in leitor:

            ticker = linha["Ticker"]

            portfolio[ticker] = {
                "quantidade": float(linha["Quantidade"]),
                "custo": float(linha["CustoMedio"])
            }

    return portfolio