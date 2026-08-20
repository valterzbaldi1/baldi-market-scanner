import streamlit as st
import yfinance as yf

st.title("📈 Teste Histórico Yahoo")

ticker = "NVDA"

try:

    dados = yf.download(
        ticker,
        period="6mo",
        progress=False
    )

    st.success(
        f"{len(dados)} dias carregados."
    )

    st.line_chart(
        dados["Close"]
    )

except Exception as erro:

    st.error(str(erro))
