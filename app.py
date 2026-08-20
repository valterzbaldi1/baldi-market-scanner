import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")

st.subheader("Top Compras")

market = pd.read_csv("market_data.csv")

st.dataframe(market)

st.subheader("Minha Carteira")

portfolio = pd.read_csv("portfolio.csv")

st.dataframe(portfolio)
