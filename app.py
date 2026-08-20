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

    minima = round(
        float(close.min()),
        2
    )

    distancia_maxima = round(
        ((preco_atual - maxima) / maxima) * 100,
        2
    )

    posicao_historica = round(
        (
            (preco_atual - minima)
            /
            (maxima - minima)
        ) * 100,
        1
    )

    col1, col2, col3 = st.columns([0.8, 2.3, 1.1])

    with col1:

        st.subheader(ticker)

      
