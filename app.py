import csv
import io
import json
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from pathlib import Path
from plotly.subplots import make_subplots

from indicators import calcular_rsi
from news import obter_noticias

st.set_page_config(page_title="Baldi Market Scanner", layout="wide")
st.title("📈 Baldi Market Scanner")

# ==================================================
# UTILIDADES
# ==================================================

def numero(valor):
    if pd.isna(valor):
        return 0.0
    texto = str(valor).strip()
    for antigo, novo in [("$", ""), ("%", ""), (",", ""), ("+", ""), ("(", "-"), (")", "")]:
        texto = texto.replace(antigo, novo)
    try:
        return float(texto) if texto not in ["", "--", "Processing"] else 0.0
    except ValueError:
        return 0.0


def texto_upload(arquivo):
    arquivo.seek(0)
    conteudo = arquivo.getvalue()
    return conteudo.decode("utf-8-sig", errors="ignore") if isinstance(conteudo, bytes) else conteudo


def serie_close(dados, ticker):
    if dados is None or dados.empty:
        return None
    try:
        serie = dados["Close"][ticker] if isinstance(dados.columns, pd.MultiIndex) else dados["Close"]
        return serie.dropna()
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def baixar_precos(ticker, periodo="6mo", inicio=None, fim=None):
    parametros = dict(progress=False, auto_adjust=False)
    if inicio is not None:
        return yf.download(ticker, start=inicio, end=fim, **parametros)
    return yf.download(ticker, period=periodo, **parametros)


def calcular_indicadores(close):
    atual = round(float(close.iloc[-1]), 2)
    maxima = round(float(close.max()), 2)
    minima = round(float(close.min()), 2)
    media = round(float(close.mean()), 2)
    rsi = calcular_rsi(close)
    distancia = round((atual - maxima) / maxima * 100, 2) if maxima else 0.0
    posicao = round((atual - minima) / (maxima - minima) * 100, 1) if maxima != minima else 0.0
    mm20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else media
    mm50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else media
    return {
        "atual": atual,
        "maxima": maxima,
        "minima": minima,
        "media": media,
        "rsi": rsi,
        "distancia": distancia,
        "posicao": posicao,
        "tendencia_alta": atual > mm20 > mm50
    }


def titulo_noticia(noticia):
    try:
        return noticia["content"]["title"]
    except Exception:
        return noticia.get("title", "Noticia") if isinstance(noticia, dict) else "Noticia"


def url_noticia(noticia):
    for tentativa in [
        lambda: noticia["content"]["clickThroughUrl"]["url"],
        lambda: noticia["content"]["canonicalUrl"]["url"],
        lambda: noticia["link"]
    ]:
        try:
            return tentativa()
        except Exception:
            pass
    return None


def mostrar_noticias(ticker):
    st.markdown("### 📰 Noticias")
    try:
        noticias = obter_noticias(ticker) or []
    except Exception:
        noticias = []
    exibidas = 0
    for noticia in noticias:
        titulo = titulo_noticia(noticia)
        url = url_noticia(noticia)
        curto = titulo[:45] + "..." if len(titulo) > 45 else titulo
        if url:
            st.markdown(f"- [{curto}]({url})")
        else:
            st.write("• " + curto)
        exibidas += 1
        if exibidas >= 3:
            break
    if exibidas == 0:
        st.info("NO NEWS")


# ==================================================
# LEITURA DOS CSVs DA FIDELITY
# ==================================================

def ler_positions(arquivo):
    linhas = list(csv.reader(io.StringIO(texto_upload(arquivo))))
    indice = next((i for i, linha in enumerate(linhas) if "Symbol" in [str(x).strip() for x in linha]), None)
    if indice is None:
        raise ValueError("Cabecalho Symbol nao encontrado no CSV Positions.")
    cabecalho = [str(x).strip() for x in linhas[indice]]
    posicoes = []
    for linha in linhas[indice + 1:]:
        linha += [""] * max(0, len(cabecalho) - len(linha))
        reg = dict(zip(cabecalho, linha))
        ticker = str(reg.get("Symbol", "")).strip().upper()
        if ticker in ["", "SPAXX", "SPAXX**", "FCASH", "CASH"]:
            continue
        if not ticker.replace(".", "").replace("-", "").isalpha():
            continue
        quantidade = numero(reg.get("Quantity", 0))
        if quantidade <= 0:
            continue
        posicoes.append({
            "Ticker": ticker,
            "Quantidade": quantidade,
            "PrecoFidelity": numero(reg.get("Last price", 0)),
            "ValorAtual": numero(reg.get("Current value", 0)),
            "GanhoDolar": numero(reg.get("Total gain/loss dollar", 0)),
            "GanhoPercentual": numero(reg.get("Total gain/loss percent", 0)),
            "CustoTotal": numero(reg.get("Cost basis total", 0)),
            "CustoMedio": numero(reg.get("Average cost basis", 0))
        })
    return pd.DataFrame(posicoes)


def ler_history(arquivo):
    linhas = list(csv.reader(io.StringIO(texto_upload(arquivo))))
    indice = next((i for i, linha in enumerate(linhas) if "Run Date" in linha and "Action" in linha), None)
    if indice is None:
        raise ValueError("Cabecalho Run Date/Action nao encontrado no CSV History.")
    cabecalho = [str(x).strip() for x in linhas[indice]]
    movimentos = []
    for linha in linhas[indice + 1:]:
        linha += [""] * max(0, len(cabecalho) - len(linha))
        reg = dict(zip(cabecalho, linha))
        data = pd.to_datetime(reg.get("Run Date", ""), errors="coerce")
        if pd.isna(data):
            continue
        movimentos.append({
            "Data": data.normalize(),
            "Acao": str(reg.get("Action", "")).upper(),
            "Ticker": str(reg.get("Symbol", "")).strip().upper(),
            "Quantidade": numero(reg.get("Quantity", 0)),
            "Valor": numero(reg.get("Amount ($)", 0))
        })
    colunas = ["Data", "Acao", "Ticker", "Quantidade", "Valor"]
    if not movimentos:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame(movimentos, columns=colunas).sort_values("Data").reset_index(drop=True)


@st.cache_data(ttl=21600, show_spinner=False)
def mapa_precos(tickers, inicio, fim):
    resultado = {}
    fim_yahoo = pd.Timestamp(fim) + timedelta(days=2)
    for ticker in tickers:
        dados = baixar_precos(
            ticker,
            inicio=pd.Timestamp(inicio).strftime("%Y-%m-%d"),
            fim=fim_yahoo.strftime("%Y-%m-%d")
        )
        close = serie_close(dados, ticker)
        if close is not None and not close.empty:
            close.index = pd.to_datetime(close.index).tz_localize(None)
            resultado[ticker] = close
    return resultado


def montar_evolucao(historico):
    tickers = sorted(
        ticker for ticker in historico["Ticker"].dropna().unique()
        if ticker and ticker not in ["SPAXX", "SPAXX**"]
    )
    inicio = historico["Data"].min()
    fim = max(historico["Data"].max(), pd.Timestamp.today().normalize())
    datas = pd.date_range(inicio, fim, freq="D")
    aportes = pd.Series(0.0, index=datas)
    dividendos = pd.Series(0.0, index=datas)
    quantidades = pd.DataFrame(0.0, index=datas, columns=tickers)

    for _, mov in historico.iterrows():
        data, acao = mov["Data"], mov["Acao"]
        ticker, quantidade, valor = mov["Ticker"], mov["Quantidade"], mov["Valor"]
        if "ELECTRONIC FUNDS TRANSFER RECEIVED" in acao:
            aportes.loc[data] += max(valor, 0)
        if "DIVIDEND RECEIVED" in acao and ticker not in ["", "SPAXX", "SPAXX**"]:
            dividendos.loc[data] += max(valor, 0)
        if ticker in tickers:
            if "YOU BOUGHT" in acao or "REINVESTMENT" in acao:
                quantidades.loc[data:, ticker] += quantidade
            elif "YOU SOLD" in acao:
                quantidades.loc[data:, ticker] -= quantidade

    precos = mapa_precos(tickers, inicio, fim)
    valor_carteira = pd.Series(0.0, index=datas)
    for ticker in tickers:
        if ticker in precos:
            preco = precos[ticker].reindex(datas).ffill().bfill()
            valor_carteira += quantidades[ticker] * preco

    evolucao = pd.DataFrame({
        "Capital aportado": aportes.cumsum(),
        "Valor da carteira": valor_carteira,
        "Dividendos acumulados": dividendos.cumsum()
    }, index=datas)
    return evolucao, quantidades, aportes, dividendos


def calcular_performance_mensal(evolucao, aportes, dividendos):
    linhas = []
    hoje = pd.Timestamp.today().normalize()
    ultimo_fechado = hoje.replace(day=1) - pd.Timedelta(days=1)
    primeiro_mes = evolucao.index.min().replace(day=1)
    meses = pd.date_range(primeiro_mes, ultimo_fechado.replace(day=1), freq="MS")

    for inicio_mes in meses:
        fim_mes = inicio_mes + pd.offsets.MonthEnd(0)
        anterior = inicio_mes - pd.Timedelta(days=1)
        inicio = float(evolucao.loc[:anterior, "Valor da carteira"].iloc[-1]) if not evolucao.loc[:anterior].empty else 0.0
        fim = float(evolucao.loc[:fim_mes, "Valor da carteira"].iloc[-1])
        aportes_mes = float(aportes.loc[inicio_mes:fim_mes].sum())
        dividendos_mes = float(dividendos.loc[inicio_mes:fim_mes].sum())
        ganho = fim - inicio - aportes_mes
        mercado = ganho - dividendos_mes

        dias_mes = max((fim_mes - inicio_mes).days + 1, 1)
        aportes_ponderados = 0.0
        fluxo_mes = aportes.loc[inicio_mes:fim_mes]
        for data, valor in fluxo_mes[fluxo_mes != 0].items():
            aportes_ponderados += valor * (((fim_mes - data).days + 1) / dias_mes)
        base = inicio + aportes_ponderados
        retorno = ganho / base if base > 0 else 0.0

        linhas.append({
            "MesData": inicio_mes,
            "Mes": inicio_mes.strftime("%b/%Y"),
            "Inicio": inicio,
            "Aportes": aportes_mes,
            "Dividendos": dividendos_mes,
            "Mercado": mercado,
            "Ganho": ganho,
            "Fim": fim,
            "FidelityPct": retorno * 100
        })
    return pd.DataFrame(linhas)


# ==================================================
# GRAFICO GERAL + TABELA MENSAL ALINHADA
# ==================================================

def grafico_e_tabela(evolucao, quantidades, mensal):
    if mensal.empty:
        return None

    rotulos = mensal["Mes"].tolist()
    meses_data = mensal["MesData"].tolist()
    fins_mes = [data + pd.offsets.MonthEnd(0) for data in meses_data]
    barras = quantidades.reindex(fins_mes, method="ffill").fillna(0)

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.67, 0.33],
        vertical_spacing=0.02,
        specs=[[{"secondary_y": True}], [{"type": "table"}]]
    )

    # Mantem a visao diaria para permitir leitura de tendencia ao longo do tempo.
    for nome, cor in [
        ("Capital aportado", "#1f77b4"),
        ("Valor da carteira", "#2ca02c"),
        ("Dividendos acumulados", "#ff7f0e")
    ]:
        fig.add_trace(
            go.Scatter(
                x=evolucao.index, y=evolucao[nome], name=nome,
                mode="lines", line=dict(color=cor, width=3)
            ),
            row=1, col=1, secondary_y=False
        )

    cores = ["#9467bd", "#8c564b", "#17becf", "#e377c2"]
    for i, ticker in enumerate(barras.columns):
        fig.add_trace(
            go.Bar(
                x=fins_mes, y=barras[ticker], name=ticker,
                marker_color=cores[i % len(cores)], opacity=0.38,
                width=18 * 24 * 60 * 60 * 1000
            ),
            row=1, col=1, secondary_y=True
        )

    nomes = ["Inicio", "Aportes", "Dividendos", "Mercado", "Ganho do mes", "Fim", "Fidelity"]
    valores = [nomes]
    for _, linha in mensal.iterrows():
        valores.append([
            f"${linha['Inicio']:,.2f}", f"${linha['Aportes']:,.2f}",
            f"${linha['Dividendos']:,.2f}", f"${linha['Mercado']:+,.2f}",
            f"${linha['Ganho']:+,.2f}", f"${linha['Fim']:,.2f}",
            f"{linha['FidelityPct']:+.2f}%"
        ])

    primeira = 1.45
    fig.add_trace(
        go.Table(
            columnwidth=[primeira] + [1.0] * len(rotulos),
            header=dict(
                values=["<b>Indicador</b>"] + [f"<b>{mes}</b>" for mes in rotulos],
                fill_color="#f3f5f8", align=["left"] + ["center"] * len(rotulos),
                height=30, line_color="#d9dee7"
            ),
            cells=dict(
                values=valores, fill_color=["#f8f9fb"] + ["white"] * len(rotulos),
                align=["left"] + ["right"] * len(rotulos), height=27,
                line_color="#e4e7ec"
            )
        ), row=2, col=1
    )

    # O grafico e a tabela reservam a mesma margem esquerda para os indicadores.
    inicio_dominio = primeira / (primeira + len(rotulos))
    fig.update_xaxes(
        domain=[inicio_dominio, 1.0],
        tickmode="array", tickvals=fins_mes, ticktext=rotulos,
        range=[evolucao.index.min(), fins_mes[-1] + pd.Timedelta(days=10)],
        row=1, col=1
    )
    fig.update_layout(
        height=760, barmode="stack", hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=10, r=15, t=70, b=10)
    )
    fig.update_yaxes(title_text="Valor ($)", tickprefix="$", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Acoes/cotas", row=1, col=1, secondary_y=True)
    return fig


# ==================================================
# DIVIDENDOS DO ATIVO + GRAFICO INDIVIDUAL COM TABELA
# ==================================================

@st.cache_data(ttl=21600, show_spinner=False)
def dados_dividendos(ticker, preco_atual, quantidade):
    try:
        dividendos = yf.Ticker(ticker).dividends
        if dividendos is None or dividendos.empty:
            return {"yield": 0.0, "frequencia": "Sem pagamento"}
        limite = pd.Timestamp.now(tz=dividendos.index.tz) - pd.DateOffset(years=1)
        ultimos = dividendos[dividendos.index >= limite]
        anual_acao = float(ultimos.sum())
        pagamentos = len(ultimos)
        frequencia = "Mensal" if pagamentos >= 10 else ("Trimestral" if pagamentos >= 3 else ("Semestral" if pagamentos == 2 else "Anual"))
        return {"yield": anual_acao / preco_atual * 100 if preco_atual else 0.0, "frequencia": frequencia}
    except Exception:
        return {"yield": 0.0, "frequencia": "Indisponivel"}


def tabela_dividendos_mensais(ticker, historico, quantidade_atual):
    hoje = pd.Timestamp.today().normalize()
    meses = pd.date_range(end=hoje.replace(day=1), periods=12, freq="MS")
    rotulos = [data.strftime("%b/%Y") for data in meses]

    try:
        serie = yf.Ticker(ticker).dividends
        if serie is None or serie.empty:
            por_acao = pd.Series(0.0, index=meses)
        else:
            indice_sem_tz = pd.to_datetime(serie.index).tz_localize(None)
            serie = pd.Series(serie.values, index=indice_sem_tz)
            por_acao = serie.resample("MS").sum().reindex(meses, fill_value=0.0)
    except Exception:
        por_acao = pd.Series(0.0, index=meses)

    total_recebido = pd.Series(0.0, index=meses)
    if historico is not None and not historico.empty:
        filtro = historico[
            (historico["Ticker"] == ticker) &
            (historico["Acao"].str.contains("DIVIDEND RECEIVED", na=False))
        ].copy()
        if not filtro.empty:
            filtro["Mes"] = filtro["Data"].dt.to_period("M").dt.to_timestamp()
            total_recebido = filtro.groupby("Mes")["Valor"].sum().reindex(meses, fill_value=0.0)

    acumulado = total_recebido.cumsum()
    return rotulos, por_acao, total_recebido, acumulado


def grafico_ativo_com_tabela(close, ticker, rotulos, por_acao, total_recebido, acumulado):
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.70, 0.30], vertical_spacing=0.02,
        specs=[[{"type": "xy"}], [{"type": "table"}]]
    )

    # O grafico usa exatamente os mesmos 12 meses da tabela.
    meses_data = pd.to_datetime(rotulos, format="%b/%Y")
    inicio_grafico = meses_data[0]
    fim_grafico = meses_data[-1] + pd.offsets.MonthEnd(1)
    close_12m = close[(close.index >= inicio_grafico) & (close.index <= fim_grafico)]

    fig.add_trace(
        go.Scatter(
            x=close_12m.index,
            y=close_12m.values,
            mode="lines",
            name=ticker,
            line=dict(color="#1f77b4", width=2)
        ),
        row=1, col=1
    )

    valores = [
        ["Dividendo por acao", "Total recebido no mes", "Recebido acumulado"],
        *[
            [
                f"${por_acao.iloc[i]:,.3f}",
                f"${total_recebido.iloc[i]:,.2f}",
                f"${acumulado.iloc[i]:,.2f}"
            ]
            for i in range(len(rotulos))
        ]
    ]

    primeira = 1.65
    fig.add_trace(
        go.Table(
            columnwidth=[primeira] + [1.0] * len(rotulos),
            header=dict(
                values=["<b>Dividendos</b>"] + [f"<b>{mes}</b>" for mes in rotulos],
                fill_color="#f3f5f8",
                align=["left"] + ["center"] * len(rotulos),
                height=28,
                line_color="#d9dee7"
            ),
            cells=dict(
                values=valores,
                fill_color=["#f8f9fb"] + ["white"] * len(rotulos),
                align=["left"] + ["right"] * len(rotulos),
                height=25,
                line_color="#e4e7ec"
            )
        ),
        row=2, col=1
    )

    # Reserva no grafico a mesma largura da coluna de descricoes da tabela.
    inicio_dominio = primeira / (primeira + len(rotulos))
    fig.update_xaxes(
        domain=[inicio_dominio, 1.0],
        range=[inicio_grafico, fim_grafico],
        tickmode="array",
        tickvals=meses_data,
        ticktext=rotulos,
        row=1,
        col=1
    )

    fig.update_layout(
        height=540,
        showlegend=False,
        hovermode="x unified",
        margin=dict(l=8, r=8, t=15, b=5)
    )
    fig.update_yaxes(tickprefix="$", row=1, col=1)
    return fig


def avaliar_compra(indicadores, ticker):
    positivos, alertas = [], []
    if indicadores["posicao"] <= 25:
        positivos.append("Posicao historica baixa")
    elif indicadores["posicao"] >= 80:
        alertas.append("Preco proximo do topo da faixa")
    if indicadores["distancia"] <= -15:
        positivos.append("Desconto superior a 15% frente a maxima")
    elif indicadores["distancia"] > -5:
        alertas.append("Pouco desconto frente a maxima")
    if indicadores["rsi"] < 40:
        positivos.append("RSI em regiao atrativa")
    elif indicadores["rsi"] > 70:
        alertas.append("RSI em sobrecompra")
    if indicadores["tendencia_alta"]:
        positivos.append("Tendencia de alta confirmada pelas medias")
    else:
        alertas.append("Tendencia de curto prazo ainda nao confirmada")

    info_div = dados_dividendos(ticker, indicadores["atual"], 1.0)
    yield_pct = info_div["yield"]
    if yield_pct >= 4:
        positivos.append(f"Dividend yield historico atrativo: {yield_pct:.2f}%")
    elif yield_pct < 1:
        alertas.append(f"Dividend yield baixo: {yield_pct:.2f}%")

    score_valor = 50
    score_valor += 25 if indicadores["posicao"] < 30 else (-20 if indicadores["posicao"] > 80 else 0)
    score_valor += 20 if indicadores["distancia"] < -15 else (-10 if indicadores["distancia"] > -5 else 0)
    score_valor += 15 if indicadores["rsi"] < 45 else (-15 if indicadores["rsi"] > 70 else 0)
    score_valor = max(0, min(100, score_valor))
    score_renda = max(0, min(100, yield_pct * 12))

    if score_valor >= 70:
        sinal = "CANDIDATA A COMPRA"
    elif score_valor >= 45:
        sinal = "AGUARDAR CONFIRMACAO"
    else:
        sinal = "NAO COMPRAR"
    return positivos, alertas, score_valor, score_renda, sinal


# ==================================================
# SCANNER AUTOMATICO E CARDS DE COMPRA
# ==================================================

UNIVERSO_PILOTO = [
    "NVDA", "MSFT", "META", "AMZN", "GOOGL", "AVGO", "AMD", "CRM",
    "JPM", "KO", "PEP", "JNJ", "PG", "VZ", "T", "O", "MAIN", "JEPI", "SCHD"
]


def analisar_ticker_compra(ticker):
    ticker = ticker.strip().upper()
    if not ticker:
        return None

    close = serie_close(baixar_precos(ticker, periodo="1y"), ticker)
    if close is None or close.empty:
        return None

    x = calcular_indicadores(close)
    positivos, alertas, score_valor, score_renda, sinal = avaliar_compra(x, ticker)
    info_div = dados_dividendos(ticker, x["atual"], 1.0)

    renda_anual_100 = info_div["yield"]
    renda_mensal_100 = renda_anual_100 / 12
    quantidade_100 = 100 / x["atual"] if x["atual"] else 0.0

    return {
        "ticker": ticker,
        "close": close,
        "indicadores": x,
        "positivos": positivos,
        "alertas": alertas,
        "score_swing": int(score_valor),
        "score_renda": int(round(score_renda)),
        "sinal": sinal,
        "frequencia": info_div["frequencia"],
        "yield": info_div["yield"],
        "renda_anual_100": renda_anual_100,
        "renda_mensal_100": renda_mensal_100,
        "quantidade_100": quantidade_100
    }


def exibir_card_compra(analise, criterio, posicao_ranking=None):
    ticker = analise["ticker"]
    x = analise["indicadores"]

    st.divider()

    if posicao_ranking is not None:
        st.markdown(f"### #{posicao_ranking} - {ticker}")

    col1, col2, col3 = st.columns([1.28, 3, 1.5])

    with col1:
        if posicao_ranking is None:
            st.subheader(ticker)

        st.write(f"💵 Atual: **${x['atual']:,.2f}**")
        st.write(f"🏔️ Max 12m: **${x['maxima']:,.2f}**")
        st.write(f"📉 Min 12m: **${x['minima']:,.2f}**")
        st.write(f"📊 Media 12m: **${x['media']:,.2f}**")
        st.write(f"📈 RSI: **{x['rsi']:.2f}**")
        st.write(f"📍 Posicao: **{x['posicao']:.1f}%**")
        st.write(f"📉 Dist. Max: **{x['distancia']:+.2f}%**")

        st.markdown("**Estrategias**")
        st.write(f"🔄 Swing: **{analise['score_swing']}/100**")
        st.write(f"💸 Dividendos: **{analise['score_renda']}/100**")
        if "score_hibrido" in analise:
            st.write(f"🔄💸 Hibrido: **{analise['score_hibrido']}/100**")
        if analise.get("asset_type"):
            st.write(f"🏷️ Tipo: **{analise['asset_type']}**")
        st.write(f"📆 Frequencia: **{analise['frequencia']}**")
        st.write(f"💵 Yield 12m: **{analise['yield']:.2f}%**")
        st.write(f"🧾 $100 compram: **{analise['quantidade_100']:.3f} acoes/cotas**")
        st.write(f"💰 Renda anual por $100: **${analise['renda_anual_100']:.2f}**")
        st.write(f"📅 Renda mensal equivalente: **${analise['renda_mensal_100']:.2f}**")

        if criterio == "swing":
            if analise["score_swing"] >= 70:
                st.success("🟢 CANDIDATA A SWING")
            elif analise["score_swing"] >= 45:
                st.warning("🟨 AGUARDAR CONFIRMACAO")
            else:
                st.error("🔴 FRACA PARA SWING")
        elif criterio == "dividendos":
            if analise["score_renda"] >= 70:
                st.success("🟢 CANDIDATA PARA RENDA")
            elif analise["score_renda"] >= 45:
                st.warning("🟨 RENDA MODERADA")
            else:
                st.error("🔴 FRACA PARA RENDA")
        elif criterio == "hibrido":
            if analise.get("score_hibrido", 0) >= 70:
                st.success("🟢 CANDIDATA HIBRIDA")
            elif analise.get("score_hibrido", 0) >= 50:
                st.warning("🟨 HIBRIDA MODERADA")
            else:
                st.error("🔴 HIBRIDA FRACA")
        else:
            perfil = "HIBRIDA" if analise["score_swing"] >= 60 and analise["score_renda"] >= 60 else (
                "SWING" if analise["score_swing"] > analise["score_renda"] else "DIVIDENDOS"
            )
            st.info(f"Perfil predominante: **{perfil}**")

        with st.expander("Por que este sinal?"):
            st.markdown("**Pontos positivos**")
            if analise["positivos"]:
                for item in analise["positivos"]:
                    st.write("✅ " + item)
            else:
                st.write("Nenhum fator positivo forte identificado.")

            st.markdown("**Pontos de atencao**")
            if analise["alertas"]:
                for item in analise["alertas"]:
                    st.write("⚠️ " + item)
            else:
                st.write("Nenhum alerta relevante identificado.")

            st.caption(
                "Os scores de swing e dividendos sao independentes. "
                "A classificacao serve para triagem e nao e uma ordem automatica."
            )

    with col2:
        st.line_chart(analise["close"], height=340)

    with col3:
        mostrar_noticias(ticker)


# ==================================================
# LEITURA DOS RANKINGS DIARIOS
# ==================================================

def carregar_ranking(caminho):
    arquivo = Path(caminho)
    if not arquivo.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(arquivo)
    except Exception:
        return pd.DataFrame()


def carregar_status_scanner():
    arquivo = Path("scanner_status.json")
    if not arquivo.exists():
        return {}
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        return {}


def analise_do_ranking(linha):
    ticker = str(linha["Ticker"]).strip().upper()
    close = serie_close(baixar_precos(ticker, periodo="1y"), ticker)
    if close is None or close.empty:
        return None

    x = calcular_indicadores(close)
    score_swing = int(round(float(linha.get("ScoreSwing", 0))))
    score_renda = int(round(float(linha.get("ScoreDividendos", 0))))
    yield_12m = float(linha.get("Yield12m", 0))
    frequencia = str(linha.get("DividendFrequency", "Indisponivel"))
    renda_anual_100 = float(linha.get("IncomeAnnualPer100", yield_12m))
    renda_mensal_100 = float(
        linha.get("IncomeMonthlyEquivalentPer100", yield_12m / 12)
    )
    quantidade_100 = 100 / x["atual"] if x["atual"] else 0.0

    positivos = []
    alertas = []

    if x["posicao"] <= 30:
        positivos.append("Preco na parte inferior da faixa de 12 meses")
    elif x["posicao"] >= 80:
        alertas.append("Preco proximo do topo da faixa de 12 meses")

    if x["rsi"] < 40:
        positivos.append("RSI em regiao atrativa")
    elif x["rsi"] > 70:
        alertas.append("RSI elevado")

    if x["tendencia_alta"]:
        positivos.append("Tendencia de alta confirmada pelas medias")
    else:
        alertas.append("Tendencia de curto prazo ainda nao confirmada")

    if yield_12m >= 5:
        positivos.append(f"Yield de 12 meses: {yield_12m:.2f}%")
    elif yield_12m <= 1:
        alertas.append(f"Yield baixo: {yield_12m:.2f}%")

    asset_type = str(linha.get("AssetType", "Ativo"))
    security_name = str(linha.get("SecurityName", ticker))

    return {
        "ticker": ticker,
        "security_name": security_name,
        "asset_type": asset_type,
        "close": close,
        "indicadores": x,
        "positivos": positivos,
        "alertas": alertas,
        "score_swing": score_swing,
        "score_renda": score_renda,
        "score_hibrido": int(round(float(linha.get("ScoreHibrido", 0)))),
        "frequencia": frequencia,
        "yield": yield_12m,
        "renda_anual_100": renda_anual_100,
        "renda_mensal_100": renda_mensal_100,
        "quantidade_100": quantidade_100,
    }


def exibir_linhas_ranking(ranking, quantidade, criterio):
    limite = min(quantidade, len(ranking))
    for posicao in range(limite):
        linha = ranking.iloc[posicao]
        try:
            analise = analise_do_ranking(linha)
            if analise is not None:
                exibir_card_compra(
                    analise,
                    criterio=criterio,
                    posicao_ranking=posicao + 1,
                )
        except Exception as erro:
            st.warning(
                f"Nao foi possivel exibir {linha.get('Ticker', 'ticker')}: {erro}"
            )


# ==================================================
# ABAS
# ==================================================

aba_compras, aba_carteira = st.tabs(["📈 Compras", "💼 Minha Carteira"])

with aba_compras:
    st.header("📈 Oportunidades de Compra")

    ranking_swing = carregar_ranking("top50_swing.csv")
    ranking_dividendos = carregar_ranking("top50_dividendos.csv")
    ranking_hibridas = carregar_ranking("top50_hibridas.csv")
    status_scanner = carregar_status_scanner()

    if status_scanner:
        atualizado = status_scanner.get("updated_at_utc", "Indisponivel")
        universo = status_scanner.get("universe_symbols", 0)
        analisados = status_scanner.get("valid_assets_analyzed", 0)
        falhas = status_scanner.get("failed_batches", 0)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Ultima atualizacao", atualizado)
        s2.metric("Universo encontrado", f"{universo:,}")
        s3.metric("Ativos validos", f"{analisados:,}")
        s4.metric("Lotes com falha", falhas)
    else:
        st.warning(
            "scanner_status.json nao foi encontrado. "
            "Execute o Daily Market Scanner no GitHub Actions."
        )

    opcoes_top = [3, 5, 10, 20]
    quantidade_exibida = st.selectbox(
        "Quantidade de oportunidades por categoria",
        options=opcoes_top,
        index=0,
        key="quantidade_top_dashboard",
    )

    if ranking_swing.empty:
        st.error("top50_swing.csv nao foi encontrado ou esta vazio.")
    else:
        st.subheader(f"🔄 Top {quantidade_exibida} para Swing Trade")
        st.caption(
            "Ranking diario baseado em RSI, posicao na faixa de 12 meses, "
            "tendencia, retorno recente, volatilidade e liquidez."
        )
        exibir_linhas_ranking(
            ranking_swing,
            quantidade_exibida,
            criterio="swing",
        )

    if ranking_dividendos.empty:
        st.error("top50_dividendos.csv nao foi encontrado ou esta vazio.")
    else:
        st.subheader(f"💸 Top {quantidade_exibida} para Dividendos")
        st.caption(
            "Ranking diario baseado em yield, frequencia, regularidade, "
            "crescimento da distribuicao, preco de entrada e risco."
        )
        exibir_linhas_ranking(
            ranking_dividendos,
            quantidade_exibida,
            criterio="dividendos",
        )

    if ranking_hibridas.empty:
        st.info("Nenhuma candidata hibrida foi gerada na ultima execucao.")
    else:
        st.subheader(f"🔄💸 Top {quantidade_exibida} Hibridas")
        st.caption(
            "Ativos com equilibrio entre potencial de valorizacao e renda."
        )
        exibir_linhas_ranking(
            ranking_hibridas,
            quantidade_exibida,
            criterio="hibrido",
        )

    st.divider()
    st.subheader("🔎 Analise Manual")
    st.caption(
        "Digite ate dois tickers. A analise manual usa a mesma regua visual, "
        "mas consulta os dados atuais diretamente."
    )

    manual_col1, manual_col2 = st.columns(2)
    with manual_col1:
        ticker_manual_1 = st.text_input(
            "Ticker manual 1",
            placeholder="Ex.: PSEC",
            key="ticker_manual_1",
        ).strip().upper()
    with manual_col2:
        ticker_manual_2 = st.text_input(
            "Ticker manual 2",
            placeholder="Ex.: ARCC",
            key="ticker_manual_2",
        ).strip().upper()

    tickers_manuais = []
    for ticker in [ticker_manual_1, ticker_manual_2]:
        if ticker and ticker not in tickers_manuais:
            tickers_manuais.append(ticker)

    for ticker in tickers_manuais:
        try:
            analise_manual = analisar_ticker_compra(ticker)
            if analise_manual is None:
                st.warning(f"Nao foi possivel encontrar historico para {ticker}.")
            else:
                exibir_card_compra(
                    analise_manual,
                    criterio="manual",
                    posicao_ranking=None,
                )
        except Exception as erro:
            st.warning(f"Nao foi possivel analisar {ticker}: {erro}")

with aba_carteira:
    st.header("💼 Minha Carteira")
    u1, u2 = st.columns(2)
    with u1:
        arq_positions = st.file_uploader("1. CSV Positions da Fidelity", type=["csv"], key="positions")
    with u2:
        arq_history = st.file_uploader("2. CSV History da Fidelity", type=["csv"], key="history")

    if arq_positions is None:
        st.info("Carregue o CSV Positions para visualizar sua carteira.")
    else:
        try:
            carteira = ler_positions(arq_positions)
            st.success(f"{len(carteira)} posicoes carregadas da Fidelity.")
            total_valor = carteira["ValorAtual"].sum()
            total_ganho = carteira["GanhoDolar"].sum()
            total_custo = carteira["CustoTotal"].sum()
            m1, m2, m3 = st.columns(3)
            m1.metric("Valor atual", f"${total_valor:,.2f}")
            m2.metric("Ganho de capital", f"${total_ganho:+,.2f}")
            m3.metric("Retorno", f"{(total_ganho / total_custo * 100 if total_custo else 0):+.2f}%")

            historico = None
            if arq_history is not None:
                historico = ler_history(arq_history)
                evolucao, quantidades, aportes, dividendos = montar_evolucao(historico)
                mensal = calcular_performance_mensal(evolucao, aportes, dividendos)
                st.subheader("📊 Evolucao da Carteira")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Capital aportado", f"${evolucao['Capital aportado'].iloc[-1]:,.2f}")
                k2.metric("Valor reconstruido", f"${evolucao['Valor da carteira'].iloc[-1]:,.2f}")
                k3.metric("Dividendos recebidos", f"${evolucao['Dividendos acumulados'].iloc[-1]:,.2f}")
                k4.metric("Cotas atuais", f"{quantidades.iloc[-1].sum():,.3f}")
                figura = grafico_e_tabela(evolucao, quantidades, mensal)
                if figura is not None:
                    st.plotly_chart(figura, use_container_width=True)
                st.caption("Dividendos reinvestidos ja estao incorporados ao valor da carteira.")
            else:
                st.info("Carregue tambem o CSV History para ver evolucao e desempenho mensal.")

            for _, posicao in carteira.iterrows():
                st.divider()
                ticker = posicao["Ticker"]
                try:
                    close = serie_close(baixar_precos(ticker, periodo="1y"), ticker)
                    if close is None or close.empty:
                        continue
                    x = calcular_indicadores(close)
                    ganho_pct = float(posicao["GanhoPercentual"])
                    if ganho_pct >= 6 and (x["rsi"] >= 65 or x["posicao"] >= 80):
                        sinal = "VENDA PARCIAL"
                    elif x["rsi"] < 40 and x["posicao"] < 40:
                        sinal = "COMPRAR MAIS"
                    else:
                        sinal = "MANTER"

                    info_div = dados_dividendos(ticker, x["atual"], float(posicao["Quantidade"]))
                    rotulos_div, por_acao, total_recebido, acumulado = tabela_dividendos_mensais(
                        ticker, historico, float(posicao["Quantidade"])
                    )
                    c1, c2, c3 = st.columns([1.2, 3.2, 1.4])
                    with c1:
                        st.subheader(ticker)
                        st.write(f"📦 Quantidade: **{posicao['Quantidade']:,.3f}**")
                        st.write(f"💰 Custo medio: **${posicao['CustoMedio']:,.2f}**")
                        st.write(f"💵 Atual Fidelity: **${posicao['PrecoFidelity']:,.2f}**")
                        st.write(f"🌐 Atual online: **${x['atual']:,.2f}**")
                        st.write(f"📊 Valor atual: **${posicao['ValorAtual']:,.2f}**")
                        st.write(f"📈 Ganho: **{ganho_pct:+.2f}%**")
                        st.write(f"💲 Ganho: **${posicao['GanhoDolar']:+,.2f}**")
                        st.write(f"📈 RSI: **{x['rsi']:.2f}**")
                        st.write(f"📍 Posicao: **{x['posicao']:.1f}%**")
                        st.write(f"💸 Yield 12m: **{info_div['yield']:.2f}%**")
                        st.write(f"📆 Frequencia: **{info_div['frequencia']}**")
                        if sinal == "COMPRAR MAIS":
                            st.success("🟢 ⬆ COMPRAR MAIS")
                        elif sinal == "VENDA PARCIAL":
                            st.error("🔴 ⬇ VENDA PARCIAL")
                        else:
                            st.warning("🟨 ➖ MANTER")
                    with c2:
                        st.plotly_chart(
                            grafico_ativo_com_tabela(
                                close, ticker, rotulos_div, por_acao, total_recebido, acumulado
                            ),
                            use_container_width=True,
                            key=f"grafico_{ticker}"
                        )
                    with c3:
                        mostrar_noticias(ticker)
                except Exception as erro:
                    st.warning(f"Nao foi possivel concluir a analise de {ticker}: {erro}")
        except Exception as erro:
            st.error(f"Erro lendo arquivos Fidelity: {erro}")
