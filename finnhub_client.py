import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta


def obter_preco(ticker):

    api_key = st.secrets["FINNHUB_API_KEY"]

    url = (
        f"https://finnhub.io/api/v1/quote"
        f"?symbol={ticker}"
        f"&token={api_key}"
    )

    resposta = requests.get(url)

    dados = resposta.json()

    return dados["c"]


def obter_historico(ticker):

    api_key = st.secrets["FINNHUB_API_KEY"]

    fim = int(datetime.now().timestamp())

    inicio = int(
        (datetime.now() - timedelta(days=180)).timestamp()
    )

    url = (
        f"https://finnhub.io/api/v1/stock/candle"
        f"?symbol={ticker}"
        f"&resolution=D"
        f"&from={inicio}"
        f"&to={fim}"
        f"&token={api_key}"
    )

    resposta = requests.get(url)

    dados = resposta.json()

    if dados["s"] != "ok":
        return None

    return pd.DataFrame({
        "close": dados["c"]
    })
