import streamlit as st

from finnhub_client import obter_preco
from finnhub_client import obter_historico

st.title("📈 Baldi Market Scanner")

ticker = "NVDA"

preco = obter_preco(ticker)

st.subheader(ticker)

st.write(f"Preço Atual: ${preco}")

historico = obter_historico(ticker)

if historico is None:

    st.error("Histórico não retornado pelo Finnhub.")

else:

    st.success(
        f"{len(historico)} dias carregados."
    )

    st.line_chart(
        historico["close"]
    )
