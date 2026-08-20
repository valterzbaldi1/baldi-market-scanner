import streamlit as st
import yfinance as yf
import pandas as pd

from indicators import calcular_rsi
from news import obter_noticias

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")

aba_compra, aba_carteira = st.tabs(
    [
        "📈 Compras",
        "💼 Carteira"
    ]
)

# ==================================================
# ABA COMPRAS
# ==================================================

with aba_compra:

    tickers = [
        "NVDA",
        "MSFT",
        "META"
    ]

    for ticker in tickers:

        st.divider()

        try:

            dados = yf.download(
                ticker,
                period="6mo",
                progress=False
            )

            close = dados["Close"][ticker]

            preco_atual = round(
                float(close.iloc[-1]),
                2
            )

            maxima = round(
                float(close.max()),
                2
            )

            minima = round(
                float(close.min()),
                2
            )

            media = round(
                float(close.mean()),
                2
            )

            rsi = calcular_rsi(close)

            distancia_maxima = round(
                ((preco_atual - maxima) / maxima) * 100,
                2
            )

            posicao_historica = round(
                (
                    (preco_atual - minima)
                    /
                    (maxima - minima)
                ) * 100,
                1
            )

            col1, col2, col3 = st.columns(
                [1, 3, 1.5]
            )

            # ==========================
            # INDICADORES
            # ==========================

            with col1:

                st.subheader(ticker)

                st.write(
                    f"💵 Atual: ${preco_atual}"
                )

                st.write(
                    f"🏔️ Max: ${maxima}"
                )

                st.write(
                    f"📉 Min: ${minima}"
                )

                st.write(
                    f"📊 Média: ${media}"
                )

                st.write(
                    f"📈 RSI: {rsi}"
                )

                st.write(
                    f"📍 Posição: {posicao_historica}%"
                )

                st.write(
                    f"📉 Dist. Máx: {distancia_maxima}%"
                )

                if (
                    rsi < 40
                    and posicao_historica < 40
                ):

                    st.success(
                        "🟢 COMPRAR"
                    )

                elif (
                    rsi > 70
                    or posicao_historica > 80
                ):

                    st.error(
                        "🔴 NÃO COMPRAR"
                    )

                else:

                    st.warning(
                        "🟨 DÚVIDA"
                    )

            # ==========================
            # GRÁFICO
            # ==========================

            with col2:

                st.line_chart(close)

            # ==========================
            # NOTÍCIAS
            # ==========================

            with col3:

                st.markdown(
                    "### 📰 Notícias"
                )

                noticias = obter_noticias(
                    ticker
                )

                if len(noticias) == 0:

                    st.info("NO NEWS")

                else:

                    contador = 0

                    for noticia in noticias:

                        try:

                            titulo = noticia[
                                "content"
                            ]["title"]

                            if len(titulo) > 45:
                                titulo = (
                              
