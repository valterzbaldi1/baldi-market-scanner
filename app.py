import streamlit as st
import yfinance as yf

from indicators import calcular_rsi
from news import obter_noticias

st.title("📈 Baldi Market Scanner")

ticker = "NVDA"

dados = yf.download(
    ticker,
    period="6mo",
    progress=False
)

close = dados["Close"][ticker]

preco_atual = round(float(close.iloc[-1]), 2)

rsi = calcular_rsi(close)

maxima = round(float(close.max()), 2)

minima = round(float(close.min()), 2)

media = round(float(close.mean()), 2)

distancia_maxima = round(
    ((preco_atual - maxima) / maxima) * 100,
    2
)

st.subheader(ticker)

st.write(f"💵 Preço Atual: ${preco_atual}")
st.write(f"📈 RSI: {rsi}")
st.write(f"🏔️ Máxima 6 meses: ${maxima}")
st.write(f"📉 Mínima 6 meses: ${minima}")
st.write(f"📊 Média 6 meses: ${media}")
st.write(f"📉 Distância da Máxima: {distancia_maxima}%")

st.subheader("📊 Histórico de Preços")

st.line_chart(close)
st.subheader("📰 Últimas Notícias")

noticias = obter_noticias(ticker)

if len(noticias) == 0:

    st.info("NO NEWS")

else:

    for noticia in noticias:

        try:

            titulo = noticia["content"]["title"]

            url = noticia["content"]["clickThroughUrl"]["url"]

            st.markdown(f"• {titulo}")

            st.markdown(🔗 Abrir</a>',
                unsafe_allow_html=True
            )

            st.write("")

        except:

            pass
