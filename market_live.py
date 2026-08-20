import yfinance as yf

def obter_dados(ticker):

    ativo = yf.Ticker(ticker)

    info = ativo.info

    try:
        return {
            "ticker": ticker,
            "preco": info.get("currentPrice", 0),
            "yield": info.get("dividendYield", 0)
        }
    except:
        return {
            "ticker": ticker,
            "preco": 0,
            "yield": 0
        }
