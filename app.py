import streamlit as st

from market_live import obter_preco

st.title("📈 Teste Yahoo Finance")

preco_nvda = obter_preco("NVDA")

st.write("NVDA")

st.write(preco_nvda)
