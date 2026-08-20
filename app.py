import streamlit as st
import yfinance as yf

from indicators import calcular_rsi
from news import obter_noticias

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")

tickers = [
    "NVDA",
    "MSFT",
    "META"
]

for ticker in tickers:

    st.divider()

    try:

        dados = yf.download(
            ticker,
            period="6mo",
            progress=False
        )

        close = dados["Close"][ticker]

        preco_atual = round(
            float(close.iloc[-1]),
            2
        )

        rsi = calcular_rsi(close)

        maxima = round(
            float(close.max()),
            2
        )

