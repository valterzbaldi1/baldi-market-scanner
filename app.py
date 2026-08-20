import streamlit as st
import yfinance as yf

st.title("Diagnóstico Yahoo")

dados = yf.download(
    "NVDA",
    period="6mo",
    progress=False
)

st.write(type(dados))

st.write(dados.head())

st.write(dados.columns)
