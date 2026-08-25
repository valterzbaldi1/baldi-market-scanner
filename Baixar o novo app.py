import csv
import io
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

from indicators import calcular_rsi
from news import obter_noticias


st.set_page_config(
    page_title="Baldi Market Scanner",
    layout="wide"
)

st.title("📈 Baldi Market Scanner")


# ==================================================
# FUNCOES AUXILIARES
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

    if texto in ["", "--", "None", "nan", "Processing"]:
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


@st.cache_data(ttl=21600, show_spinner=False)
def baixar_historico(ticker, period="6mo", start=None, end=None):
    if start is not None:
        return yf.download(
            ticker,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False
        )

    return yf.download(
        ticker,
        period=period,
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
        return "Noticia"


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
    st.markdown("### 📰 Noticias")

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
            titulo_curto = titulo[:45] + "..." if len(titulo) > 45 else titulo

            if url:
                st.markdown(f"- [{titulo_curto}]({url})")
            else:
                st.write("• " + titulo_curto)

            contador += 1
            if contador >= 3:
                break
        except Exception:
            continue

    if contador == 0:
        st.info("NO NEWS")


def calcular_indicadores(close):
    preco_atual = round(float(close.iloc[-1]), 2)
    maxima = round(float(close.max()), 2)
    minima = round(float(close.min()), 2)
    media = round(float(close.mean()), 2)
    rsi = calcular_rsi(close)

    distancia_maxima = (
        round(((preco_atual - maxima) / maxima) * 100, 2)
        if maxima != 0 else 0.0
    )

    posicao_historica = (
        round(((preco_atual - minima) / (maxima - minima)) * 100, 1)
        if maxima != minima else 0.0
    )

    return {
        "preco": preco_atual,
        "maxima": maxima,
        "minima": minima,
        "media": media,
        "rsi": rsi,
        "distancia_maxima": distancia_maxima,
        "posicao_historica": posicao_historica
    }


def calcular_sinal_compra(rsi, posicao_historica):
    if rsi < 40 and posicao_historica < 40:
        return "COMPRAR"
    if rsi > 70 or posicao_historica > 80:
        return "NAO COMPRAR"
    return "DUVIDA"


def calcular_sinal_carteira(ganho_percentual, rsi, posicao_historica):
    if ganho_percentual >= 6 and (rsi >= 65 or posicao_historica >= 80):
        return "VENDA PARCIAL"
    if rsi < 40 and posicao_historica < 40:
        return "COMPRAR MAIS"
    return "MANTER"


def ler_texto_upload(arquivo):
    arquivo.seek(0)
    conteudo = arquivo.getvalue()
    if isinstance(conteudo, bytes):
        return conteudo.decode("utf-8-sig", errors="ignore")
    return conteudo


def ler_csv_fidelity(arquivo):
    texto = ler_texto_upload(arquivo)
    linhas = list(csv.reader(io.StringIO(texto)))

    linha_cabecalho = None
    cabecalho = None

    for indice, linha in enumerate(linhas):
        linha_limpa = [str(valor).strip() for valor in linha]
        if "Symbol" in linha_limpa:
            linha_cabecalho = indice
            cabecalho = linha_limpa
            break

    if linha_cabecalho is None:
        raise ValueError("O cabecalho do CSV da Fidelity nao foi encontrado.")

    posicoes = []

    for linha in linhas[linha_cabecalho + 1:]:
        if len(linha) < len(cabecalho):
            linha = linha + [""] * (len(cabecalho) - len(linha))

        registro = dict(zip(cabecalho, linha))
        ticker = str(registro.get("Symbol", "")).strip().upper()

        if ticker in ["", "SPAXX", "SPAXX**", "FCASH", "CASH", "NAN", "NONE"]:
            continue

        if not ticker.replace(".", "").replace("-", "").isalpha():
            continue

        quantidade = converter_numero(registro.get("Quantity", 0))
        if quantidade <= 0:
            continue

        posicoes.append({
            "Ticker": ticker,
            "Quantidade": quantidade,
            "PrecoFidelity": converter_numero(registro.get("Last price", 0)),
            "ValorAtual": converter_numero(registro.get("Current value", 0)),
            "GanhoDolar": converter_numero(registro.get("Total gain/loss dollar", 0)),
            "GanhoPercentual": converter_numero(registro.get("Total gain/loss percent", 0)),
            "CustoTotal": converter_numero(registro.get("Cost basis total", 0)),
            "CustoMedio": converter_numero(registro.get("Average cost basis", 0))
        })

    return pd.DataFrame(posicoes)


def ler_historico_fidelity(arquivo):
    texto = ler_texto_upload(arquivo)
    linhas = list(csv.reader(io.StringIO(texto)))

    inicio = None
    cabecalho = None

    for indice, linha in enumerate(linhas):
        limpa = [str(v).strip() for v in linha]
        if "Run Date" in limpa and "Action" in limpa:
            inicio = indice
            cabecalho = limpa
            break

    if inicio is None:
        raise ValueError("O cabecalho Run Date/Action nao foi encontrado no CSV de History.")

    registros = []

    for linha in linhas[inicio + 1:]:
        if len(linha) < len(cabecalho):
            linha = linha + [""] * (len(cabecalho) - len(linha))

        registro = dict(zip(cabecalho, linha))
        data = pd.to_datetime(registro.get("Run Date", ""), errors="coerce")

        if pd.isna(data):
            continue

        registros.append({
            "Data": data,
            "Acao": str(registro.get("Action", "")).strip().upper(),
            "Ticker": str(registro.get("Symbol", "")).strip().upper(),
            "Preco": converter_numero(registro.get("Price ($)", 0)),
            "Quantidade": converter_numero(registro.get("Quantity", 0)),
            "Valor": converter_numero(registro.get("Amount ($)", 0))
        })

    historico = pd.DataFrame(registros)

    if historico.empty:
        return historico

    return historico.sort_values("Data").reset_index(drop=True)


@st.cache_data(ttl=21600, show_spinner=False)
def baixar_precos_intervalo(tickers, data_inicial, data_final):
    precos = {}
    data_fim_yahoo = pd.Timestamp(data_final) + timedelta(days=2)

    for ticker in tickers:
        dados = baixar_historico(
            ticker,
            start=pd.Timestamp(data_inicial).strftime("%Y-%m-%d"),
            end=data_fim_yahoo.strftime("%Y-%m-%d")
        )
        serie = obter_serie_close(dados, ticker)
        if serie is not None and not serie.empty:
            serie.index = pd.to_datetime(serie.index).tz_localize(None)
            precos[ticker] = serie

    return precos


def montar_evolucao_carteira(historico):
    if historico.empty:
        return pd.DataFrame(), pd.DataFrame()

    tickers = sorted([
        ticker for ticker in historico["Ticker"].dropna().unique()
        if ticker and ticker not in ["SPAXX", "SPAXX**"]
    ])

    data_inicial = historico["Data"].min().normalize()
    data_final = max(historico["Data"].max().normalize(), pd.Timestamp.today().normalize())
    datas = pd.date_range(data_inicial, data_final, freq="D")

    evolucao = pd.DataFrame(index=datas)
    evolucao["Capital aportado"] = 0.0
    evolucao["Dividendos acumulados"] = 0.0

    quantidades = pd.DataFrame(0.0, index=datas, columns=tickers)

    aportes_diarios = pd.Series(0.0, index=datas)
    dividendos_diarios = pd.Series(0.0, index=datas)

    for _, movimento in historico.iterrows():
        data = movimento["Data"].normalize()
        acao = movimento["Acao"]
        ticker = movimento["Ticker"]
        quantidade = movimento["Quantidade"]
        valor = movimento["Valor"]

        if "ELECTRONIC FUNDS TRANSFER RECEIVED" in acao:
            aportes_diarios.loc[data] += max(valor, 0)

        if "DIVIDEND RECEIVED" in acao and ticker not in ["SPAXX", "SPAXX**", ""]:
            dividendos_diarios.loc[data] += max(valor, 0)

        if ticker in tickers:
            if "YOU BOUGHT" in acao or "REINVESTMENT" in acao:
                quantidades.loc[data:, ticker] += quantidade
            elif "YOU SOLD" in acao:
                quantidades.loc[data:, ticker] -= quantidade

    evolucao["Capital aportado"] = aportes_diarios.cumsum()
    evolucao["Dividendos acumulados"] = dividendos_diarios.cumsum()

    precos = baixar_precos_intervalo(tickers, data_inicial, data_final)
    valor_carteira = pd.Series(0.0, index=datas)

    for ticker in tickers:
        if ticker not in precos:
            continue

        preco_diario = precos[ticker].reindex(datas).ffill().bfill()
        valor_carteira += quantidades[ticker] * preco_diario

    evolucao["Valor da carteira"] = valor_carteira

    # Barras mensais deixam o grafico legivel e mostram o crescimento das cotas.
    quantidades_mensais = quantidades.resample("ME").last()

    # Inclui o ponto atual caso o mes ainda nao tenha terminado.
    if quantidades_mensais.empty or quantidades_mensais.index[-1] != datas[-1]:
        quantidades_mensais.loc[datas[-1]] = quantidades.iloc[-1]
        quantidades_mensais = quantidades_mensais.sort_index()

    return evolucao, quantidades_mensais


def criar_grafico_evolucao(evolucao, quantidades_mensais):
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=evolucao.index,
            y=evolucao["Capital aportado"],
            name="Capital aportado",
            mode="lines",
            line=dict(color="#1f77b4", width=3)
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=evolucao.index,
            y=evolucao["Valor da carteira"],
            name="Valor da carteira",
            mode="lines",
            line=dict(color="#2ca02c", width=3)
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=evolucao.index,
            y=evolucao["Dividendos acumulados"],
            name="Dividendos acumulados",
            mode="lines",
            line=dict(color="#ff7f0e", width=3)
        ),
        secondary_y=False
    )

    cores = ["#9467bd", "#8c564b", "#17becf", "#e377c2", "#bcbd22"]

    for indice, ticker in enumerate(quantidades_mensais.columns):
        fig.add_trace(
            go.Bar(
                x=quantidades_mensais.index,
                y=quantidades_mensais[ticker],
                name=f"Cotas {ticker}",
                marker_color=cores[indice % len(cores)],
                opacity=0.38,
                hovertemplate=(
                    "%{x|%b %d, %Y}<br>"
                    + ticker
                    + ": %{y:.3f} cotas<extra></extra>"
                )
            ),
            secondary_y=True
        )

    fig.update_layout(
        height=520,
        barmode="stack",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=70, b=20)
    )

    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor ($)", tickprefix="$", secondary_y=False)
    fig.update_yaxes(title_text="Numero de acoes/cotas", secondary_y=True)

    return fig


def estimar_dividendos(ticker, quantidade):
    try:
        dividendos = yf.Ticker(ticker).dividends
        if dividendos is None or dividendos.empty:
            return 0.0, 0.0

        agora = pd.Timestamp.now(tz=dividendos.index.tz)
        data_limite = agora - pd.DateOffset(years=1)
        dividendo_por_acao = float(dividendos[dividendos.index >= data_limite].sum())
        anual = dividendo_por_acao * quantidade
        return anual, anual / 12
    except Exception:
        return 0.0, 0.0


# ==================================================
# ABAS
# ==================================================

aba_compra, aba_carteira = st.tabs(["📈 Compras", "💼 Minha Carteira"])


# ==================================================
# ABA COMPRAS
# ==================================================

with aba_compra:
    st.header("📈 Analise de Compras")

    tickers_compra = ["NVDA", "MSFT", "META"]

    for ticker in tickers_compra:
        st.divider()

        try:
            dados = baixar_historico(ticker)
            close = obter_serie_close(dados, ticker)

            if close is None or close.empty:
                st.warning(f"Historico indisponivel para {ticker}")
                continue

            indicadores = calcular_indicadores(close)
            sinal = calcular_sinal_compra(
                indicadores["rsi"],
                indicadores["posicao_historica"]
            )

            col1, col2, col3 = st.columns([1, 3, 1.5])

            with col1:
                st.subheader(ticker)
                st.write(f"💵 Atual: **${indicadores['preco']:,.2f}**")
                st.write(f"🏔️ Max: **${indicadores['maxima']:,.2f}**")
                st.write(f"📉 Min: **${indicadores['minima']:,.2f}**")
                st.write(f"📊 Media: **${indicadores['media']:,.2f}**")
                st.write(f"📈 RSI: **{indicadores['rsi']:.2f}**")
                st.write(f"📍 Posicao: **{indicadores['posicao_historica']:.1f}%**")
                st.write(f"📉 Dist. Max: **{indicadores['distancia_maxima']:+.2f}%**")

                if sinal == "COMPRAR":
                    st.success("🟢 ⬆ COMPRAR")
                elif sinal == "NAO COMPRAR":
                    st.error("🔴 ⬇ NAO COMPRAR")
                else:
                    st.warning("🟨 ➖ DUVIDA")

            with col2:
                st.line_chart(close, height=300)

            with col3:
                mostrar_noticias(ticker)

        except Exception as erro:
            st.error(f"Erro carregando {ticker}: {erro}")


# ==================================================
# ABA MINHA CARTEIRA
# ==================================================

with aba_carteira:
    st.header("💼 Minha Carteira")

    col_upload1, col_upload2 = st.columns(2)

    with col_upload1:
        arquivo_positions = st.file_uploader(
            "1. Upload do CSV Positions da Fidelity",
            type=["csv"],
            key="positions_csv"
        )

    with col_upload2:
        arquivo_history = st.file_uploader(
            "2. Upload do CSV History da Fidelity",
            type=["csv"],
            key="history_csv"
        )

    if arquivo_positions is None:
        st.info("Carregue o CSV Positions para visualizar sua carteira atual.")

    else:
        try:
            carteira = ler_csv_fidelity(arquivo_positions)

            if carteira.empty:
                st.warning("Nenhuma posicao valida foi encontrada.")
            else:
                st.success(f"{len(carteira)} posicoes carregadas da Fidelity.")

                valor_total = carteira["ValorAtual"].sum()
                ganho_total = carteira["GanhoDolar"].sum()
                custo_total = carteira["CustoTotal"].sum()
                ganho_percentual_total = (ganho_total / custo_total) * 100 if custo_total > 0 else 0.0

                resumo1, resumo2, resumo3 = st.columns(3)
                resumo1.metric("Valor atual da carteira", f"${valor_total:,.2f}")
                resumo2.metric("Ganho de capital", f"${ganho_total:+,.2f}")
                resumo3.metric("Retorno da carteira", f"{ganho_percentual_total:+.2f}%")

                if arquivo_history is not None:
                    try:
                        historico = ler_historico_fidelity(arquivo_history)
                        evolucao, quantidades_mensais = montar_evolucao_carteira(historico)

                        if evolucao.empty:
                            st.warning("Nenhum movimento valido foi encontrado no CSV History.")
                        else:
                            st.subheader("📊 Evolucao da Carteira")

                            aportado = evolucao["Capital aportado"].iloc[-1]
                            dividendos_reais = evolucao["Dividendos acumulados"].iloc[-1]
                            valor_reconstruido = evolucao["Valor da carteira"].iloc[-1]

                            met1, met2, met3, met4 = st.columns(4)
                            met1.metric("Capital aportado", f"${aportado:,.2f}")
                            met2.metric("Valor reconstruido", f"${valor_reconstruido:,.2f}")
                            met3.metric("Dividendos recebidos", f"${dividendos_reais:,.2f}")
                            met4.metric("Cotas atuais", f"{quantidades_mensais.iloc[-1].sum():,.3f}")

                            st.plotly_chart(
                                criar_grafico_evolucao(evolucao, quantidades_mensais),
                                use_container_width=True
                            )

                            st.caption(
                                "Dividendos acumulados ja estao incorporados ao valor da carteira quando reinvestidos. "
                                "A linha laranja mostra a origem do crescimento e nao deve ser somada novamente ao patrimonio."
                            )

                    except Exception as erro:
                        st.error(f"Erro lendo o CSV History: {erro}")
                else:
                    st.info(
                        "Carregue tambem o CSV History para ver capital aportado, valor historico, "
                        "dividendos reais e crescimento das quantidades."
                    )

                for _, posicao in carteira.iterrows():
                    ticker = posicao["Ticker"]
                    quantidade = posicao["Quantidade"]
                    preco_fidelity = posicao["PrecoFidelity"]
                    valor_atual = posicao["ValorAtual"]
                    ganho_dolar = posicao["GanhoDolar"]
                    ganho_percentual = posicao["GanhoPercentual"]
                    custo_medio = posicao["CustoMedio"]

                    st.divider()

                    try:
                        dados = baixar_historico(ticker)
                        close = obter_serie_close(dados, ticker)

                        if close is None or close.empty:
                            st.warning(f"Historico indisponivel para {ticker}")
                            continue

                        indicadores = calcular_indicadores(close)
                        sinal = calcular_sinal_carteira(
                            ganho_percentual,
                            indicadores["rsi"],
                            indicadores["posicao_historica"]
                        )

                        dividendo_anual, dividendo_mensal = estimar_dividendos(ticker, quantidade)
                        retorno_potencial = ganho_dolar + dividendo_anual

                        col1, col2, col3 = st.columns([1.3, 3, 1.5])

                        with col1:
                            st.subheader(ticker)
                            st.write(f"📦 Quantidade: **{quantidade:,.3f}**")
                            st.write(f"💰 Custo medio: **${custo_medio:,.2f}**")
                            st.write(f"💵 Atual Fidelity: **${preco_fidelity:,.2f}**")
                            st.write(f"🌐 Atual online: **${indicadores['preco']:,.2f}**")
                            st.write(f"📊 Valor atual: **${valor_atual:,.2f}**")
                            st.write(f"📈 Ganho de capital: **{ganho_percentual:+.2f}%**")
                            st.write(f"💲 Ganho de capital: **${ganho_dolar:+,.2f}**")
                            st.write(f"💸 Dividendo anual projetado: **${dividendo_anual:,.2f}**")
                            st.write(f"📆 Dividendo mensal projetado: **${dividendo_mensal:,.2f}**")
                            st.write(f"📊 Retorno potencial: **${retorno_potencial:+,.2f}**")
                            st.write(f"📈 RSI: **{indicadores['rsi']:.2f}**")
                            st.write(f"📍 Posicao: **{indicadores['posicao_historica']:.1f}%**")

                            if sinal == "COMPRAR MAIS":
                                st.success("🟢 ⬆ COMPRAR MAIS")
                            elif sinal == "VENDA PARCIAL":
                                st.error("🔴 ⬇ VENDA PARCIAL")
                            else:
                                st.warning("🟨 ➖ MANTER")

                        with col2:
                            st.line_chart(close, height=300)

                        with col3:
                            mostrar_noticias(ticker)

                    except Exception as erro:
                        st.error(f"Erro carregando {ticker}: {erro}")

        except Exception as erro:
            st.error(f"Erro lendo CSV Positions: {erro}")
