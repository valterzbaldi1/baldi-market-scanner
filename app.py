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


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def converter_numero(valor):

    if pd.isna(valor):
        return 0.0

    texto = str(valor).strip()

    texto = texto.replace("$", "")
    texto = texto.replace("%", "")
    texto = texto.replace(",", "")
    texto = texto.replace("+", "")
    texto = texto.replace("(", "-")
    texto = texto.replace(")", "")

    if texto in ["", "--", "None", "nan"]:
        return 0.0

    try:
        return float(texto)

    except ValueError:
        return 0.0


def obter_serie_close(dados, ticker):

    if dados is None or dados.empty:
        return None

    try:

        if isinstance(dados.columns, pd.MultiIndex):
            return dados["Close"][ticker].dropna()

        return dados["Close"].dropna()

    except Exception:
        return None


@st.cache_data(ttl=21600)
def baixar_historico(ticker):

    return yf.download(
        ticker,
        period="6mo",
        progress=False,
        auto_adjust=False
    )


def obter_titulo_noticia(noticia):

    try:
        return noticia["content"]["title"]
    except Exception:
        pass

    try:
        return noticia["title"]
    except Exception:
        return "Notícia"


def obter_link_noticia(noticia):

    try:
        return noticia["content"]["clickThroughUrl"]["url"]
    except Exception:
        pass

    try:
        return noticia["content"]["canonicalUrl"]["url"]
    except Exception:
        pass

    try:
        return noticia["link"]
    except Exception:
        return None


def mostrar_noticias(ticker):

    st.markdown("### 📰 Notícias")

    try:
        noticias = obter_noticias(ticker)
    except Exception:
        noticias = []

    if not noticias:

        st.info("NO NEWS")
        return

    contador = 0

    for noticia in noticias:

        try:

            titulo = obter_titulo_noticia(noticia)
            url = obter_link_noticia(noticia)

            if len(titulo) > 45:
                titulo_curto = titulo[:45] + "..."
            else:
                titulo_curto = titulo

            if url:

                st.markdown(
                    f"• {url}"
                )

            else:

                st.write(
                    "• " + titulo_curto
                )

            contador += 1

            if contador >= 3:
                break

        except Exception:
            continue

    if contador == 0:
        st.info("NO NEWS")


def calcular_indicadores(close):

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

    if maxima != 0:

        distancia_maxima = round(
            (
                (preco_atual - maxima)
                / maxima
            ) * 100,
            2
        )

    else:

        distancia_maxima = 0.0

    if maxima != minima:

        posicao_historica = round(
            (
                (preco_atual - minima)
                / (maxima - minima)
            ) * 100,
            1
        )

    else:

        posicao_historica = 0.0

    return {
        "preco": preco_atual,
        "maxima": maxima,
        "minima": minima,
        "media": media,
        "rsi": rsi,
        "distancia_maxima": distancia_maxima,
        "posicao_historica": posicao_historica
    }


def calcular_sinal_compra(
    rsi,
    posicao_historica
):

    if (
        rsi < 40
        and posicao_historica < 40
    ):
        return "COMPRAR"

    if (
        rsi > 70
        or posicao_historica > 80
    ):
        return "NAO COMPRAR"

    return "DUVIDA"


def calcular_sinal_carteira(
    ganho_percentual,
    rsi,
    posicao_historica
):

    if (
        ganho_percentual >= 6
        and (
            rsi >= 65
            or posicao_historica >= 80
        )
    ):
        return "VENDA PARCIAL"

    if (
        rsi < 40
        and posicao_historica < 40
    ):
        return "COMPRAR MAIS"

    return "MANTER"


def ler_csv_fidelity(arquivo):

    arquivo.seek(0)

    linhas = pd.read_csv(
        arquivo,
        header=None,
        dtype=str,
        engine="python",
        on_bad_lines="skip"
    )

    linhas = linhas.dropna(
        how="all"
    )

    linha_cabecalho = None

    for indice, linha in linhas.iterrows():

        valores = [
            str(valor).strip().lower()
            for valor in linha.tolist()
        ]

        if (
            "symbol" in valores
            or "ticker" in valores
        ):
            linha_cabecalho = indice
            break

    if linha_cabecalho is not None:

        cabecalho = [
            str(valor).strip()
            for valor in linhas.loc[
                linha_cabecalho
            ].tolist()
        ]

        dados = linhas.loc[
            linha_cabecalho + 1:
        ].copy()

        dados.columns = cabecalho

        mapa_colunas = {
            "ticker": [
                "Symbol",
                "Ticker"
            ],
            "quantidade": [
                "Quantity"
            ],
            "preco": [
                "Last Price",
                "Last price"
            ],
            "valor_atual": [
                "Current Value",
                "Current value"
            ],
            "ganho_dolar": [
                "Total Gain/Loss Dollar",
                "Total Gain/Loss $"
            ],
            "ganho_percentual": [
                "Total Gain/Loss Percent",
                "Total Gain/Loss %"
            ],
            "custo_total": [
                "Cost Basis Total",
                "Cost basis total"
            ],
            "custo_medio": [
                "Average Cost Basis",
                "Average cost basis"
            ]
        }

        colunas = {}

        for chave, possibilidades in mapa_colunas.items():

            colunas[chave] = None

            for possibilidade in possibilidades:

                if possibilidade in dados.columns:

                    colunas[chave] = possibilidade
                    break

        if colunas["ticker"] is None:

            raise ValueError(
                "A coluna Symbol não foi encontrada."
            )

        resultado = pd.DataFrame()

        resultado["Ticker"] = dados[
            colunas["ticker"]
        ]

        resultado["Quantidade"] = (
            dados[colunas["quantidade"]]
            if colunas["quantidade"]
            else 0
        )

        resultado["PrecoFidelity"] = (
            dados[colunas["preco"]]
            if colunas["preco"]
            else 0
        )

        resultado["ValorAtual"] = (
            dados[colunas["valor_atual"]]
            if colunas["valor_atual"]
            else 0
        )

        resultado["GanhoDolar"] = (
            dados[colunas["ganho_dolar"]]
            if colunas["ganho_dolar"]
            else 0
        )

        resultado["GanhoPercentual"] = (
            dados[colunas["ganho_percentual"]]
            if colunas["ganho_percentual"]
            else 0
        )

        resultado["CustoTotal"] = (
            dados[colunas["custo_total"]]
            if colunas["custo_total"]
            else 0
        )

        resultado["CustoMedio"] = (
            dados[colunas["custo_medio"]]
            if colunas["custo_medio"]
            else 0
        )

    else:

        if linhas.shape[1] < 15:

            raise ValueError(
                "O formato do CSV da Fidelity não foi reconhecido."
            )

        resultado = pd.DataFrame({
            "Ticker": linhas.iloc[:, 2],
            "Quantidade": linhas.iloc[:, 4],
            "PrecoFidelity": linhas.iloc[:, 5],
            "ValorAtual": linhas.iloc[:, 7],
            "GanhoDolar": linhas.iloc[:, 10],
            "GanhoPercentual": linhas.iloc[:, 11],
            "CustoTotal": linhas.iloc[:, 13],
            "CustoMedio": linhas.iloc[:, 14]
        })

    resultado["Ticker"] = (
        resultado["Ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    resultado = resultado[
        resultado["Ticker"].str.match(
            r"^[A-Z][A-Z.\-]{0,9}$",
            na=False
        )
    ]

    tickers_excluidos = [
        "SPAXX",
        "SPAXX**",
        "FCASH",
        "CASH",
        "PENDING",
        "NONE",
        "NAN"
    ]

    resultado = resultado[
        ~resultado["Ticker"].isin(
            tickers_excluidos
        )
    ]

    colunas_numericas = [
        "Quantidade",
        "PrecoFidelity",
        "ValorAtual",
        "GanhoDolar",
        "GanhoPercentual",
        "CustoTotal",
        "CustoMedio"
    ]

    for coluna in colunas_numericas:

        resultado[coluna] = resultado[
            coluna
        ].apply(
            converter_numero
        )

    resultado = resultado[
        resultado["Quantidade"] > 0
    ]

    resultado = resultado.drop_duplicates(
        subset=["Ticker"],
        keep="last"
    )

    return resultado.reset_index(
        drop=True
    )


def estimar_dividendos(
    ticker,
    quantidade
):

    try:

        ativo = yf.Ticker(ticker)

        dividendos = ativo.dividends

        if dividendos is None or dividendos.empty:
            return 0.0, 0.0

        agora = pd.Timestamp.now(
            tz=dividendos.index.tz
        )

        data_limite = (
            agora
            - pd.DateOffset(years=1)
        )

        dividendo_por_acao = float(
            dividendos[
                dividendos.index >= data_limite
            ].sum()
        )

        dividendo_anual = (
            dividendo_por_acao
            * quantidade
        )

        dividendo_mensal = (
            dividendo_anual
            / 12
        )

        return (
            dividendo_anual,
            dividendo_mensal
        )

    except Exception:

        return 0.0, 0.0


# ==================================================
# ABAS
# ==================================================

aba_compra, aba_carteira = st.tabs(
    [
        "📈 Compras",
        "💼 Minha Carteira"
    ]
)


# ==================================================
# ABA COMPRAS
# ==================================================

with aba_compra:

    st.header(
        "📈 Análise de Compras"
    )

    tickers_compra = [
        "NVDA",
        "MSFT",
        "META"
    ]

    for ticker in tickers_compra:

        st.divider()

        try:

            dados = baixar_historico(
                ticker
            )

            close = obter_serie_close(
                dados,
                ticker
            )

            if close is None or close.empty:

                st.warning(
                    f"Histórico indisponível para {ticker}"
                )

                continue

            indicadores = calcular_indicadores(
                close
            )

            sinal = calcular_sinal_compra(
                indicadores["rsi"],
                indicadores["posicao_historica"]
            )

            col1, col2, col3 = st.columns(
                [1, 3, 1.5]
            )

            with col1:

                st.subheader(ticker)

                st.write(
                    f"💵 Atual: "
                    f"**${indicadores['preco']:,.2f}**"
                )

                st.write(
                    f"🏔️ Max: "
                    f"**${indicadores['maxima']:,.2f}**"
                )

                st.write(
                    f"📉 Min: "
                    f"**${indicadores['minima']:,.2f}**"
                )

                st.write(
                    f"📊 Média: "
                    f"**${indicadores['media']:,.2f}**"
                )

                st.write(
                    f"📈 RSI: "
                    f"**{indicadores['rsi']:.2f}**"
                )

                st.write(
                    f"📍 Posição: "
                    f"**{indicadores['posicao_historica']:.1f}%**"
                )

                st.write(
                    f"📉 Dist. Máx: "
                    f"**{indicadores['distancia_maxima']:+.2f}%**"
                )

                if sinal == "COMPRAR":

                    st.success(
                        "🟢 ⬆ COMPRAR"
                    )

                elif sinal == "NAO COMPRAR":

                    st.error(
                        "🔴 ⬇ NÃO COMPRAR"
                    )

                else:

                    st.warning(
                        "🟨 ➖ DÚVIDA"
                    )

            with col2:

                st.line_chart(
                    close,
                    height=300
                )

            with col3:

                mostrar_noticias(
                    ticker
                )

        except Exception as erro:

            st.error(
                f"Erro carregando {ticker}: {erro}"
            )


# ==================================================
# ABA MINHA CARTEIRA
# ==================================================

with aba_carteira:

    st.header(
        "💼 Minha Carteira"
    )

    arquivo = st.file_uploader(
        "Upload do CSV exportado pela Fidelity",
        type=["csv"],
        key="fidelity_csv"
    )

    if arquivo is None:

        st.info(
            "Faça upload do CSV exportado "
            "da página Positions da Fidelity."
        )

    else:

        try:

            carteira = ler_csv_fidelity(
                arquivo
            )

            if carteira.empty:

                st.warning(
                    "Nenhuma posição válida foi encontrada."
                )

            else:

                st.success(
                    f"{len(carteira)} posições "
                    "carregadas da Fidelity."
                )

                valor_total = carteira[
                    "ValorAtual"
                ].sum()

                ganho_total = carteira[
                    "GanhoDolar"
                ].sum()

                custo_total = carteira[
                    "CustoTotal"
                ].sum()

                if custo_total > 0:

                    ganho_percentual_total = (
                        ganho_total
                        / custo_total
                    ) * 100

                else:

                    ganho_percentual_total = 0.0

                resumo1, resumo2, resumo3 = st.columns(
                    3
                )

                with resumo1:

                    st.metric(
                        "Valor atual da carteira",
                        f"${valor_total:,.2f}"
                    )

                with resumo2:

                    st.metric(
                        "Ganho de capital",
                        f"${ganho_total:+,.2f}"
                    )

                with resumo3:

                    st.metric(
                        "Retorno da carteira",
                        f"{ganho_percentual_total:+.2f}%"
                    )

                for _, posicao in carteira.iterrows():

                    ticker = posicao["Ticker"]

                    quantidade = posicao[
                        "Quantidade"
                    ]

                    preco_fidelity = posicao[
                        "PrecoFidelity"
                    ]

                    valor_atual = posicao[
                        "ValorAtual"
                    ]

                    ganho_dolar = posicao[
                        "GanhoDolar"
                    ]

                    ganho_percentual = posicao[
                        "GanhoPercentual"
                    ]

                    custo_medio = posicao[
                        "CustoMedio"
                    ]

                    st.divider()

                    try:

                        dados = baixar_historico(
                            ticker
                        )

                        close = obter_serie_close(
                            dados,
                            ticker
                        )

                        if close is None or close.empty:

                            st.warning(
                                f"Histórico indisponível "
                                f"para {ticker}"
                            )

                            continue

                        indicadores = calcular_indicadores(
                            close
                        )

                        sinal = calcular_sinal_carteira(
                            ganho_percentual,
                            indicadores["rsi"],
                            indicadores[
                                "posicao_historica"
                            ]
                        )

                        dividendo_anual, dividendo_mensal = (
                            estimar_dividendos(
                                ticker,
                                quantidade
                            )
                        )

                        retorno_total_dolar = (
                            ganho_dolar
                            + dividendo_anual
                        )

                        col1, col2, col3 = st.columns(
                            [1.3, 3, 1.5]
                        )

                        with col1:

                            st.subheader(ticker)

                            st.write(
                                f"📦 Quantidade: "
                                f"**{quantidade:,.3f}**"
                            )

                            st.write(
                                f"💰 Custo médio: "
                                f"**${custo_medio:,.2f}**"
                            )

                            st.write(
                                f"💵 Atual Fidelity: "
                                f"**${preco_fidelity:,.2f}**"
                            )

                            st.write(
                                f"🌐 Atual online: "
                                f"**${indicadores['preco']:,.2f}**"
                            )

                            st.write(
                                f"📊 Valor atual: "
                                f"**${valor_atual:,.2f}**"
                            )

                            st.write(
                                f"📈 Ganho de capital: "
                                f"**{ganho_percentual:+.2f}%**"
                            )

                            st.write(
                                f"💲 Ganho de capital: "
                                f"**${ganho_dolar:+,.2f}**"
                            )

                            st.write(
                                f"💸 Dividendos 12m: "
                                f"**${dividendo_anual:,.2f}**"
                            )

                            st.write(
                                f"📆 Média mensal: "
                                f"**${dividendo_mensal:,.2f}**"
                            )

                            st.write(
                                f"📊 Retorno total: "
                                f"**${retorno_total_dolar:+,.2f}**"
                            )

                            st.write(
                                f"📈 RSI: "
                                f"**{indicadores['rsi']:.2f}**"
                            )

                            st.write(
                                f"📍 Posição: "
                                f"**{indicadores['posicao_historica']:.1f}%**"
                            )

                            if sinal == "COMPRAR MAIS":

                                st.success(
                                    "🟢 ⬆ COMPRAR MAIS"
                                )

                            elif sinal == "VENDA PARCIAL":

                                st.error(
                                    "🔴 ⬇ VENDA PARCIAL"
                                )

                            else:

                                st.warning(
                                    "🟨 ➖ MANTER"
                                )

                        with col2:

                            st.line_chart(
                                close,
                                height=300
                            )

                        with col3:

                            mostrar_noticias(
                                ticker
                            )

                    except Exception as erro:

                        st.error(
                            f"Erro carregando "
                            f"{ticker}: {erro}"
                        )

        except Exception as erro:

            st.error(
                f"Erro lendo CSV da Fidelity: {erro}"
            )
