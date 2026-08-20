import yfinance as yf


def obter_noticias(ticker):

    try:

        ativo = yf.Ticker(ticker)

        noticias = ativo.news

        return noticias[:5]

    except:

        return []
