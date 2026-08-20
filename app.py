import streamlit as st
import yfinance as yf

from indicators import calcular_rsi
from news import obter_noticias

st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")

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

        rsi = calcular_rsi(close)

        maxima = round(
            float(close.max()),
            2
        )

        minima = round(
            float(close.min()),
            2
        )

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

        col1, col2 = st.columns([0.8, 2.2])

        with col1:

            st.subheader(ticker)

            st.write(f"💵 ${preco_atual}")

            st.write(f"📈 RSI: {rsi}")

            st.write(
                f"📍 Posição: {posicao_historica}%"
            )

            st.write(
                f"📉 Dist. Máx: {distancia_maxima}%"
            )

            if rsi < 40 and posicao_historica < 40:

                st.success("🟢 COMPRAR")

            elif rsi > 70 or posicao_historica > 80:

                st.error("🔴 NÃO COMPRAR")

            else:

                st.warning("🟨 DÚVIDA")

        with col2:

            st.line_chart(close)

            st.markdown("### 📰 Notícias")

            noticias = obter_noticias(ticker)

            if len(noticias) == 0:

                st.info("NO NEWS")

            else:

                contador = 0

                for noticia in noticias:

                    try:

                        titulo = noticia["content"]["title"]

                        if len(titulo) > 50:
                            titulo = titulo[:50] + "..."

                        st.write("• " + titulo)

                        contador += 1

                        if contador >= 3:
                            break

                    except:

                        pass

    except Exception as erro:

        st.error(
            f"Erro carregando {ticker}: {erro}"
        )
