import streamlit as st
import pandas as pd

from rules.buy_rules import calcula_score_compra
from recommendation import recomendacao

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

market = pd.read_csv("market_data.csv")
portfolio = pd.read_csv("portfolio.csv")

compras = []

for _, linha in market.iterrows():

    score, motivos = calcula_score_compra(
        float(linha["RSI"]),
        float(linha["Yield"]),
        float(linha["DistanciaMaxima"])
    )

    compras.append({
        "ticker": linha["Ticker"],
        "score": score,
        "motivos": motivos,
        "recomendacao": recomendacao(score),
        "rsi": linha["RSI"],
        "yield": linha["Yield"],
        "distancia": linha["DistanciaMaxima"],
        "lucro": linha["Lucro"]
    })

compras = sorted(
    compras,
    key=lambda x: x["score"],
    reverse=True
)

st.title("📈 Baldi Market Scanner")

col1, col2 = st.columns([2,1])

with col1:

    st.subheader("🔥 Top Compras")

    ranking = 1

    for acao in compras[:5]:

        st.markdown(
            f"""
### #{ranking} - {acao['ticker']}

🎯 **Score:** {acao['score']}/100

✅ **Recomendação:** {acao['recomendacao']}

📈 RSI: {acao['rsi']} pts

💰 Yield: {acao['yield']}%

📉 Distância da Máxima: {acao['distancia']}%

💵 Lucro Atual: {acao['lucro']}%

**Motivos:**
"""
        )

        for motivo in acao["motivo"]:
