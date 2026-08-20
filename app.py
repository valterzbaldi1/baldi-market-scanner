import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

market = pd.read_csv("market_data.csv")
portfolio = pd.read_csv("portfolio.csv")

st.title("📈 Baldi Market Scanner")

col1, col2 = st.columns(2)

with col1:

    st.subheader("🔥 Top Compras")

    market = market.sort_values(
        by=["RSI"],
        ascending=True
    )

    for _, linha in market.head(5).iterrows():

        st.markdown(
            f"""
### {linha['Ticker']}

📈 RSI: {linha['RSI']} pts

💰 Yield: {linha['Yield']}%

📉 Distância da Máxima: {linha['DistanciaMaxima']}%

✅ Lucro: {linha['Lucro']}%

---
"""
        )

with col2:

    st.subheader("💼 Minha Carteira")

    for _, linha in portfolio.iterrows():

        st.markdown(
            f"""
### {linha['Ticker']}

📦 Quantidade: {linha['Quantidade']} ações

💵 Custo Médio: ${linha['CustoMedio']}

---
"""
        )
``
