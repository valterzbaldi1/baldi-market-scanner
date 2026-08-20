import yfinance as yf


def obter_noticias(ticker):

    try:

        ativo = yf.Ticker(ticker)

        noticias = ativo.news

        if noticias is None:
            return []

        return noticias[:5]

    except:

        return []
