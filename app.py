import streamlit as st
import yfinance as yf

from indicators import calcular_rsi
from news import obter_noticias

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Diagnóstico")

tickers = [
    "NVDA",
    "MSFT",
    "META"
]

for ticker in tickers:

    st.divider()

    st.write("Processando:", ticker)

    dados = yf.download(
        ticker,
        period="6mo",
        progress=False
    )

    st.write("Linhas carregadas:", len(dados))

    st.write("Colunas:")
    st.write(dados.columns)

    st.write("Primeiras linhas:")
    st.dataframe(dados.head())

    try:

        close = dados["Close"][ticker]

        st.success("Close encontrado")

        st.write("Último preço:")

        st.write(close.iloc[-1])

    except Exception as erro:

        st.error(str(erro))

        continue

    st.write("----------------------------")
