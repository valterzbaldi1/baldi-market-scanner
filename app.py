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

st.set_page_config(page_title="Baldi Market Scanner", layout="wide")
st.title("📈 Baldi Market Scanner")

# ---------------- Helpers ----------------
def num(v):
    if pd.isna(v): return 0.0
    s = str(v).strip().replace("$", "").replace("%", "").replace(",", "").replace("+", "")
    s = s.replace("(", "-").replace(")", "")
    try: return float(s) if s not in ["", "--", "Processing"] else 0.0
    except: return 0.0

def upload_text(f):
    f.seek(0); x = f.getvalue()
    return x.decode("utf-8-sig", errors="ignore") if isinstance(x, bytes) else x

def close_series(df, ticker):
    if df is None or df.empty: return None
    try:
        return (df["Close"][ticker] if isinstance(df.columns, pd.MultiIndex) else df["Close"]).dropna()
    except: return None

@st.cache_data(ttl=21600, show_spinner=False)
def download_prices(ticker, period="6mo", start=None, end=None):
    kw = dict(progress=False, auto_adjust=False)
    if start is not None:
        return yf.download(ticker, start=start, end=end, **kw)
    return yf.download(ticker, period=period, **kw)

def indicators(close):
    p, hi, lo, avg = map(lambda x: round(float(x), 2), [close.iloc[-1], close.max(), close.min(), close.mean()])
    rsi = calcular_rsi(close)
    dist = round((p-hi)/hi*100, 2) if hi else 0.0
    pos = round((p-lo)/(hi-lo)*100, 1) if hi != lo else 0.0
    return dict(preco=p, maxima=hi, minima=lo, media=avg, rsi=rsi, distancia=dist, posicao=pos)

def news_title(n):
    try: return n["content"]["title"]
    except:
        try: return n["title"]
        except: return "Noticia"

def news_url(n):
    for getter in [
        lambda: n["content"]["clickThroughUrl"]["url"],
        lambda: n["content"]["canonicalUrl"]["url"],
        lambda: n["link"]
    ]:
        try: return getter()
        except: pass
    return None

def show_news(ticker):
    st.markdown("### 📰 Noticias")
    try: items = obter_noticias(ticker) or []
    except: items = []
    shown = 0
    for n in items:
        title, url = news_title(n), news_url(n)
        short = title[:45] + "..." if len(title) > 45 else title
        if url: st.markdown(f"- [{short}]({url})")
        else: st.write("• " + short)
        shown += 1
        if shown == 3: break
    if shown == 0: st.info("NO NEWS")

def read_positions(f):
    rows = list(csv.reader(io.StringIO(upload_text(f))))
    header_i = next((i for i, r in enumerate(rows) if "Symbol" in [str(x).strip() for x in r]), None)
    if header_i is None: raise ValueError("Cabecalho Symbol nao encontrado no Positions.")
    header = [str(x).strip() for x in rows[header_i]]
    out = []
    for r in rows[header_i+1:]:
        r += [""] * max(0, len(header)-len(r)); d = dict(zip(header, r))
        t = str(d.get("Symbol", "")).strip().upper()
        if t in ["", "SPAXX", "SPAXX**", "FCASH", "CASH"] or not t.replace(".", "").replace("-", "").isalpha(): continue
        q = num(d.get("Quantity", 0))
        if q <= 0: continue
        out.append({
            "Ticker": t, "Quantidade": q,
            "PrecoFidelity": num(d.get("Last price", 0)),
            "ValorAtual": num(d.get("Current value", 0)),
            "GanhoDolar": num(d.get("Total gain/loss dollar", 0)),
            "GanhoPercentual": num(d.get("Total gain/loss percent", 0)),
            "CustoTotal": num(d.get("Cost basis total", 0)),
            "CustoMedio": num(d.get("Average cost basis", 0))
        })
    return pd.DataFrame(out)

def read_history(f):
    rows = list(csv.reader(io.StringIO(upload_text(f))))
    header_i = next((i for i, r in enumerate(rows) if "Run Date" in r and "Action" in r), None)
    if header_i is None: raise ValueError("Cabecalho Run Date/Action nao encontrado no History.")
    header = [str(x).strip() for x in rows[header_i]]; out = []
    for r in rows[header_i+1:]:
        r += [""] * max(0, len(header)-len(r)); d = dict(zip(header, r))
        dt = pd.to_datetime(d.get("Run Date", ""), errors="coerce")
        if pd.isna(dt): continue
        out.append({
            "Data": dt.normalize(), "Acao": str(d.get("Action", "")).upper(),
            "Ticker": str(d.get("Symbol", "")).strip().upper(),
            "Quantidade": num(d.get("Quantity", 0)), "Valor": num(d.get("Amount ($)", 0))
        })
    return pd.DataFrame(out).sort_values("Data").reset_index(drop=True)

@st.cache_data(ttl=21600, show_spinner=False)
def price_map(tickers, start, end):
    out = {}; end2 = pd.Timestamp(end) + timedelta(days=2)
    for t in tickers:
        s = close_series(download_prices(t, start=pd.Timestamp(start).strftime("%Y-%m-%d"), end=end2.strftime("%Y-%m-%d")), t)
        if s is not None and not s.empty:
            s.index = pd.to_datetime(s.index).tz_localize(None); out[t] = s
    return out

def build_evolution(hist):
    tickers = sorted(t for t in hist.Ticker.unique() if t and t not in ["SPAXX", "SPAXX**"])
    start, end = hist.Data.min(), max(hist.Data.max(), pd.Timestamp.today().normalize())
    dates = pd.date_range(start, end, freq="D")
    contrib = pd.Series(0.0, index=dates); divs = pd.Series(0.0, index=dates)
    qty = pd.DataFrame(0.0, index=dates, columns=tickers)
    for _, m in hist.iterrows():
        d, a, t, q, v = m.Data, m.Acao, m.Ticker, m.Quantidade, m.Valor
        if "ELECTRONIC FUNDS TRANSFER RECEIVED" in a: contrib.loc[d] += max(v, 0)
        if "DIVIDEND RECEIVED" in a and t not in ["", "SPAXX", "SPAXX**"]: divs.loc[d] += max(v, 0)
        if t in tickers:
            if "YOU BOUGHT" in a or "REINVESTMENT" in a: qty.loc[d:, t] += q
            elif "YOU SOLD" in a: qty.loc[d:, t] -= q
    prices = price_map(tickers, start, end); mv = pd.Series(0.0, index=dates)
    for t in tickers:
        if t in prices: mv += qty[t] * prices[t].reindex(dates).ffill().bfill()
    evo = pd.DataFrame({"Capital aportado": contrib.cumsum(), "Valor da carteira": mv, "Dividendos acumulados": divs.cumsum()}, index=dates)
    bars = qty.resample("MS").last()
    if bars.empty or bars.index[-1] != dates[-1]: bars.loc[dates[-1]] = qty.iloc[-1]
    return evo, qty, bars.sort_index(), contrib, divs

def evolution_chart(evo, bars):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for name, color in [("Capital aportado", "#1f77b4"), ("Valor da carteira", "#2ca02c"), ("Dividendos acumulados", "#ff7f0e")]:
        fig.add_trace(go.Scatter(x=evo.index, y=evo[name], name=name, mode="lines", line=dict(color=color, width=3)), secondary_y=False)
    colors = ["#9467bd", "#8c564b", "#17becf", "#e377c2"]
    for i, t in enumerate(bars.columns):
        fig.add_trace(go.Bar(x=bars.index, y=bars[t], name=t, marker_color=colors[i % len(colors)], opacity=.38), secondary_y=True)
    fig.update_layout(height=500, barmode="stack", hovermode="x unified", legend=dict(orientation="h", y=1.03), margin=dict(l=20,r=20,t=65,b=20))
    fig.update_xaxes(title="Data"); fig.update_yaxes(title="Valor ($)", tickprefix="$", secondary_y=False); fig.update_yaxes(title="Acoes/cotas", secondary_y=True)
    return fig

def monthly_performance(evo, contrib, divs, fia_annual):
    rows = []
    first = evo.index.min().normalize(); today = pd.Timestamp.today().normalize()
    last_closed = (today.replace(day=1) - pd.Timedelta(days=1)).normalize()
    month_starts = pd.date_range(first.replace(day=1), last_closed.replace(day=1), freq="MS")
    fia_month = (1 + fia_annual/100) ** (1/12) - 1

    for ms in month_starts:
        me = ms + pd.offsets.MonthEnd(0)
        period_dates = evo.loc[ms:me].index
        if len(period_dates) == 0: continue
        prev = ms - pd.Timedelta(days=1)
        begin = float(evo.loc[:prev, "Valor da carteira"].iloc[-1]) if not evo.loc[:prev].empty else 0.0
        end = float(evo.loc[:me, "Valor da carteira"].iloc[-1])
        cflows = contrib.loc[ms:me]
        contribution = float(cflows.sum())
        dividends = float(divs.loc[ms:me].sum())
        total_gain = end - begin - contribution
        market_gain = total_gain - dividends

        days = max((me-ms).days + 1, 1)
        weighted_cf = 0.0
        for d, cf in cflows[cflows != 0].items():
            weight = ((me-d).days + 1) / days
            weighted_cf += cf * weight
        denominator = begin + weighted_cf
        fidelity_return = total_gain / denominator if denominator > 0 else 0.0

        rows.append({
            "Mes": ms.strftime("%b/%Y"), "Inicio": begin, "Aportes": contribution,
            "Dividendos": dividends, "Mercado": market_gain, "Ganho": total_gain,
            "Fim": end, "FidelityPct": fidelity_return*100,
            "FIAPct": fia_month*100, "Diferenca": (fidelity_return-fia_month)*100
        })
    return pd.DataFrame(rows)

def show_monthly_cards(monthly):
    st.subheader("📅 Performance mensal - meses fechados")
    st.caption(
        "Aportes nao contam como ganho. Mercado = ganho total do mes menos dividendos recebidos."
    )

    if monthly.empty:
        st.info("Ainda nao ha mes fechado suficiente para a comparacao.")
        return

    tabela = monthly.copy()

    # Os meses ficam nas colunas; as descricoes ficam fixas na esquerda.
    tabela = tabela.set_index("Mes").T

    # Mantem uma ordem logica e compacta para leitura.
    tabela = tabela.reindex([
        "Inicio",
        "Aportes",
        "Dividendos",
        "Mercado",
        "Ganho",
        "Fim",
        "FidelityPct",
        "FIAPct",
        "Diferenca"
    ])

    tabela.index = [
        "Inicio",
        "Aportes",
        "Dividendos",
        "Mercado",
        "Ganho do mes",
        "Fim",
        "Fidelity",
        "FIA",
        "Diferenca vs FIA"
    ]

    def formatar_valor(nome_linha, valor):
        if nome_linha in ["Fidelity", "FIA"]:
            return f"{valor:+.2f}%"

        if nome_linha == "Diferenca vs FIA":
            simbolo = "🟢" if valor >= 0 else "🔴"
            return f"{simbolo} {valor:+.2f} pp"

        return f"${valor:+,.2f}" if nome_linha in ["Mercado", "Ganho do mes"] else f"${valor:,.2f}"

    tabela_formatada = tabela.copy().astype(object)

    for linha in tabela_formatada.index:
        for mes in tabela_formatada.columns:
            tabela_formatada.loc[linha, mes] = formatar_valor(
                linha,
                float(tabela.loc[linha, mes])
            )

    # HTML permite manter a primeira coluna fixa visualmente e alinhar os meses.
    html = tabela_formatada.to_html(
        escape=False,
        border=0,
        classes="monthly-performance-table"
    )

    st.markdown(
        """
        <style>
        .monthly-performance-wrapper {
            overflow-x: auto;
            width: 100%;
            margin-top: 0.4rem;
            margin-bottom: 1.2rem;
        }

        table.monthly-performance-table {
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            min-width: 900px;
            font-size: 0.88rem;
        }

        table.monthly-performance-table th,
        table.monthly-performance-table td {
            padding: 0.46rem 0.72rem;
            text-align: right;
            white-space: nowrap;
            border-bottom: 1px solid rgba(128, 128, 128, 0.18);
        }

        table.monthly-performance-table thead th {
            font-weight: 700;
            text-align: center;
            border-bottom: 2px solid rgba(128, 128, 128, 0.35);
        }

        table.monthly-performance-table tbody th {
            position: sticky;
            left: 0;
            z-index: 2;
            text-align: left;
            font-weight: 700;
            background: var(--background-color, white);
            border-right: 1px solid rgba(128, 128, 128, 0.22);
        }

        table.monthly-performance-table thead th:first-child {
            position: sticky;
            left: 0;
            z-index: 3;
            background: var(--background-color, white);
        }

        table.monthly-performance-table tbody tr:nth-child(4),
        table.monthly-performance-table tbody tr:nth-child(5),
        table.monthly-performance-table tbody tr:nth-child(9) {
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div class="monthly-performance-wrapper">{html}</div>',
        unsafe_allow_html=True
    )

# ---------------- Tabs ----------------
buy_tab, portfolio_tab = st.tabs(["📈 Compras", "💼 Minha Carteira"])

with buy_tab:
    st.header("📈 Analise de Compras")
    for ticker in ["NVDA", "MSFT", "META"]:
        st.divider()
        try:
            close = close_series(download_prices(ticker), ticker)
            if close is None or close.empty: st.warning(f"Historico indisponivel para {ticker}"); continue
            x = indicators(close); signal = "COMPRAR" if x["rsi"] < 40 and x["posicao"] < 40 else ("NAO COMPRAR" if x["rsi"] > 70 or x["posicao"] > 80 else "DUVIDA")
            c1,c2,c3 = st.columns([1,3,1.5])
            with c1:
                st.subheader(ticker); st.write(f"💵 Atual: **${x['preco']:,.2f}**"); st.write(f"🏔️ Max: **${x['maxima']:,.2f}**"); st.write(f"📉 Min: **${x['minima']:,.2f}**"); st.write(f"📊 Media: **${x['media']:,.2f}**"); st.write(f"📈 RSI: **{x['rsi']:.2f}**"); st.write(f"📍 Posicao: **{x['posicao']:.1f}%**"); st.write(f"📉 Dist. Max: **{x['distancia']:+.2f}%**")
                st.success("🟢 ⬆ COMPRAR") if signal=="COMPRAR" else (st.error("🔴 ⬇ NAO COMPRAR") if signal=="NAO COMPRAR" else st.warning("🟨 ➖ DUVIDA"))
            with c2: st.line_chart(close, height=300)
            with c3: show_news(ticker)
        except Exception as e: st.error(f"Erro carregando {ticker}: {e}")

with portfolio_tab:
    st.header("💼 Minha Carteira")
    u1,u2 = st.columns(2)
    with u1: positions_file = st.file_uploader("1. CSV Positions da Fidelity", type=["csv"], key="positions")
    with u2: history_file = st.file_uploader("2. CSV History da Fidelity", type=["csv"], key="history")

    fia_rate = st.number_input("Taxa anual do FIA para benchmark (%)", min_value=0.0, max_value=20.0, value=3.75, step=0.05)

    if positions_file is None:
        st.info("Carregue o CSV Positions para visualizar sua carteira atual.")
    else:
        try:
            portfolio = read_positions(positions_file)
            st.success(f"{len(portfolio)} posicoes carregadas da Fidelity.")
            total_value, total_gain, total_cost = portfolio.ValorAtual.sum(), portfolio.GanhoDolar.sum(), portfolio.CustoTotal.sum()
            m1,m2,m3 = st.columns(3)
            m1.metric("Valor atual", f"${total_value:,.2f}"); m2.metric("Ganho de capital", f"${total_gain:+,.2f}"); m3.metric("Retorno", f"{(total_gain/total_cost*100 if total_cost else 0):+.2f}%")

            if history_file is not None:
                hist = read_history(history_file)
                evo, qty, bars, contrib, divs = build_evolution(hist)
                st.subheader("📊 Evolucao da Carteira")
                k1,k2,k3,k4 = st.columns(4)
                k1.metric("Capital aportado", f"${evo['Capital aportado'].iloc[-1]:,.2f}"); k2.metric("Valor reconstruido", f"${evo['Valor da carteira'].iloc[-1]:,.2f}"); k3.metric("Dividendos recebidos", f"${evo['Dividendos acumulados'].iloc[-1]:,.2f}"); k4.metric("Cotas atuais", f"{qty.iloc[-1].sum():,.3f}")
                st.plotly_chart(evolution_chart(evo, bars), use_container_width=True)
                st.caption("Dividendos reinvestidos ja estao incorporados ao valor da carteira. A linha laranja mostra sua contribuicao, sem ser somada novamente ao patrimonio.")
                monthly = monthly_performance(evo, contrib, divs, fia_rate)
                show_monthly_cards(monthly)
            else:
                st.info("Carregue tambem o CSV History para ver evolucao e performance mensal.")

            for _, p in portfolio.iterrows():
                st.divider(); ticker = p.Ticker
                try:
                    close = close_series(download_prices(ticker), ticker)
                    if close is None or close.empty: continue
                    x = indicators(close)
                    signal = "VENDA PARCIAL" if p.GanhoPercentual >= 6 and (x['rsi'] >= 65 or x['posicao'] >= 80) else ("COMPRAR MAIS" if x['rsi'] < 40 and x['posicao'] < 40 else "MANTER")
                    c1,c2,c3 = st.columns([1.3,3,1.5])
                    with c1:
                        st.subheader(ticker); st.write(f"📦 Quantidade: **{p.Quantidade:,.3f}**"); st.write(f"💰 Custo medio: **${p.CustoMedio:,.2f}**"); st.write(f"💵 Atual Fidelity: **${p.PrecoFidelity:,.2f}**"); st.write(f"🌐 Atual online: **${x['preco']:,.2f}**"); st.write(f"📊 Valor atual: **${p.ValorAtual:,.2f}**"); st.write(f"📈 Ganho: **{p.GanhoPercentual:+.2f}%**"); st.write(f"💲 Ganho: **${p.GanhoDolar:+,.2f}**"); st.write(f"📈 RSI: **{x['rsi']:.2f}**"); st.write(f"📍 Posicao: **{x['posicao']:.1f}%**")
                        st.success("🟢 ⬆ COMPRAR MAIS") if signal=="COMPRAR MAIS" else (st.error("🔴 ⬇ VENDA PARCIAL") if signal=="VENDA PARCIAL" else st.warning("🟨 ➖ MANTER"))
                    with c2: st.line_chart(close, height=300)
                    with c3: show_news(ticker)
                except Exception as e: st.error(f"Erro carregando {ticker}: {e}")
        except Exception as e:
            st.error(f"Erro lendo arquivos Fidelity: {e}")
