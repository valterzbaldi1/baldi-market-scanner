import streamlit as st
import requests

api_key = st.secrets["FINNHUB_API_KEY"]

url = (
    f"https://finnhub.io/api/v1/stock/candle"
    f"?symbol=NVDA"
    f"&resolution=D"
    f"&from=1700000000"
    f"&to=1800000000"
    f"&token={api_key}"
)

resposta = requests.get(url)

st.title("Diagnóstico Finnhub")

st.json(resposta.json())
