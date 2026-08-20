import streamlit as st
import yfinance as yf

from indicators import calcular_rsi

st.title("📈 Baldi Market Scanner")

ticker = "NVDA"

dados = yf.download(
    ticker,
    period="6mo",
    progress=False
)

# Ajuste para MultiIndex
close = dados["Close"][ticker]

preco_atual = round(
    float(close.iloc[-1]),
    2
)

rsi = calcular_rsi(close)

maxima = round(
    float(close.max()),
    2
)

distancia_maxima = round(
    (
        (preco_atual - maxima)
        / maxima
    ) * 100,
    2
)

st.subheader(ticker)

st.write(f"💵 Preço Atual: ${preco_atual}")

st.write(f"📈 RSI: {rsi}")

st.write(f"🏔️ Máxima 6 meses: ${maxima}")

st.write(
    f"📉 Distância da Máxima: {distancia_maxima}%"
)

st.line_chart(close)
