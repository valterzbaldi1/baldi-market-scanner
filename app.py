import streamlit as st

from finnhub_client import obter_preco
from finnhub_client import obter_historico

st.title("📈 Baldi Market Scanner")

ticker = "NVDA"

preco = obter_preco(ticker)

historico = obter_historico(ticker)

st.subheader(ticker)

st.write(f"Preço Atual: ${preco}")

if historico is not None:

    st.write(
        f"Dias carregados: {len(historico)}"
    )

    st.line_chart(
        historico["close"]
    )
