import requests
import streamlit as st

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
