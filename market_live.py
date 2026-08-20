import yfinance as yf

def obter_preco(ticker):

    try:

        dados = yf.download(
            ticker,
            period="5d",
            progress=False
        )

        preco = round(
            float(dados["Close"].iloc[-1]),
            2
        )

        return preco

    except:

        return "Erro"
