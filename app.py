import streamlit as st

from finnhub_client import obter_preco

st.title("📈 Teste Finnhub")

tickers = [
    "NVDA",
    "MSFT",
    "META",
    "AMZN"
]

for ticker in tickers:

    preco = obter_preco(ticker)

    st.write(f"{ticker} → ${preco}")
