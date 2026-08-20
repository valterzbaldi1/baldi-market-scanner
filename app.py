import streamlit as st

from market_live import obter_dados

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")

st.subheader("Teste de Dados Reais")

tickers = [
    "NVDA",
    "MSFT",
    "SCHG",
    "MAIN",
    "JEPI"
]

for ticker in tickers:

    dados = obter_dados(ticker)

    st.markdown(
        f"""
### {dados['ticker']}

💵 Preço Atual: ${dados['preco']}

💰 Dividend Yield: {dados['yield']}
"""
    )

    st.divider()
