import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
TOP_SWING = BASE_DIR / "top50_swing.csv"
TOP_DIVIDENDS = BASE_DIR / "top50_dividendos.csv"
TOP_HYBRID = BASE_DIR / "top50_hibridas.csv"
STATUS_FILE = BASE_DIR / "scanner_status.json"

BATCH_SIZE = 120
MIN_PRICE = 3.00
MIN_AVG_DOLLAR_VOLUME = 2_000_000
MIN_HISTORY_DAYS = 180

# Produtos que podem produzir distribuicoes altas, mas nao sao comparaveis
# a uma acao, REIT, BDC ou ETF de renda tradicional.
EXCLUDED_NAME_TERMS = (
    "2X ", "3X ", "ULTRA ", "ULTRAPRO", "INVERSE", "SHORT ",
    "BITCOIN", "ETHER", "ETHEREUM", "CRYPTO", "DAILY TARGET",
    "LEV SHARES", "-2X", "-3X", "PROSHARES ULTRA", "DIREXION DAILY"
)


def download_text(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_market_universe():
    sources = [
        (
            "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
            "Symbol",
            "Security Name",
            "ETF",
            "NASDAQ",
        ),
        (
            "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
            "ACT Symbol",
            "Security Name",
            "ETF",
            "OTHER",
        ),
    ]

    frames = []
    for url, symbol_col, name_col, etf_col, exchange in sources:
        text = download_text(url)
        frame = pd.read_csv(io.StringIO(text), sep="|")
        frame = frame[frame[symbol_col].notna()].copy()
        frame["Ticker"] = frame[symbol_col].astype(str).str.strip().str.upper()
        frame["SecurityName"] = frame.get(name_col, "").astype(str).str.strip()
        frame["IsETF"] = frame.get(etf_col, "N").astype(str).str.upper().eq("Y")
        frame["ExchangeSource"] = exchange

        if "Test Issue" in frame.columns:
            frame = frame[frame["Test Issue"].astype(str).str.upper() != "Y"]

        frames.append(frame[["Ticker", "SecurityName", "IsETF", "ExchangeSource"]])

    universe = pd.concat(frames, ignore_index=True).drop_duplicates("Ticker")
    universe = universe[
        universe["Ticker"].str.match(r"^[A-Z][A-Z0-9.-]{0,9}$", na=False)
    ]
    universe = universe[
        ~universe["Ticker"].str.contains(r"[.$^]", regex=True, na=False)
    ]

    upper_names = universe["SecurityName"].str.upper()
    excluded = pd.Series(False, index=universe.index)
    for term in EXCLUDED_NAME_TERMS:
        excluded |= upper_names.str.contains(term, regex=False, na=False)
    universe = universe[~excluded].copy()

    return universe.reset_index(drop=True)


def chunks(frame, size):
    for start in range(0, len(frame), size):
        yield frame.iloc[start:start + size].copy()


def rsi_last(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def field_frame(data, field, tickers):
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        try:
            frame = data[field].copy()
        except KeyError:
            return pd.DataFrame(index=data.index)
        if isinstance(frame, pd.Series):
            frame = frame.to_frame(name=tickers[0])
        return frame

    if len(tickers) == 1 and field in data.columns:
        return data[[field]].rename(columns={field: tickers[0]})

    return pd.DataFrame(index=data.index)


def frequency_from_events(event_count, month_count):
    if event_count <= 0:
        return "Nao paga"
    if month_count >= 10:
        return "Mensal"
    if month_count >= 3:
        return "Trimestral"
    if month_count == 2:
        return "Semestral"
    return "Anual/Irregular"


def classify_asset(security_name, is_etf):
    name = str(security_name).upper()
    if is_etf:
        return "ETF"
    if "CLOSED END" in name or "CLOSED-END" in name or " FUND" in name:
        return "Fundo Fechado"
    if "REIT" in name or "REALTY" in name or "REAL ESTATE" in name:
        return "REIT"
    if "CAPITAL CORPORATION" in name or "CAPITAL CORP" in name:
        return "Acao/BDC"
    return "Acao"


def score_swing(row):
    score = 40.0

    # Desconto e posicao historica ajudam, mas nao bastam sem reversao.
    score += np.clip((50 - row["RSI"]) * 0.75, -15, 18)
    score += np.clip((50 - row["Position12m"]) * 0.30, -15, 15)
    score += np.clip((-row["DistanceHigh12m"] - 8) * 0.45, -8, 14)

    # Confirmacao de reversao/tendencia.
    if row["Price"] > row["MA20"]:
        score += 10
    if row["MA20"] > row["MA50"]:
        score += 10
    if row["Return5d"] > 0:
        score += min(row["Return5d"] * 1.2, 8)
    if row["Return20d"] < -12:
        score -= 10

    # Evita ativos praticamente parados ou excessivamente violentos.
    if row["Volatility20d"] < 8:
        score -= 5
    elif row["Volatility20d"] > 80:
        score -= 18
    elif row["Volatility20d"] > 55:
        score -= 8

    return float(np.clip(score, 0, 100))


def yield_points(yield_12m):
    # Curva sem saturacao precoce. Yield extremo nao ganha nota maxima.
    if yield_12m <= 0:
        return 0
    if yield_12m < 2:
        return yield_12m * 3
    if yield_12m < 4:
        return 6 + (yield_12m - 2) * 4
    if yield_12m < 7:
        return 14 + (yield_12m - 4) * 5
    if yield_12m <= 12:
        return 29 + (yield_12m - 7) * 3.2
    if yield_12m <= 15:
        return 45 - (yield_12m - 12) * 2
    return max(10, 30 - (yield_12m - 15) * 3)


def score_dividends(row):
    score = yield_points(row["Yield12m"])

    frequency_points = {
        "Mensal": 16,
        "Trimestral": 12,
        "Semestral": 6,
        "Anual/Irregular": 2,
        "Nao paga": 0,
    }.get(row["DividendFrequency"], 0)
    score += frequency_points

    # Regularidade e estabilidade do valor pago.
    score += np.clip(row["DividendMonths12m"] / 12 * 14, 0, 14)
    score += np.clip((1 - row["DividendCV"]) * 12, 0, 12)

    # Crescimento ou reducao do dividendo.
    score += np.clip(row["DividendGrowth6mPct"] * 0.15, -12, 10)

    # Preco de entrada e risco do ativo.
    score += np.clip((55 - row["Position12m"]) * 0.12, -6, 7)
    if row["Return20d"] < -12 and row["MA20"] < row["MA50"]:
        score -= 8
    if row["DistanceHigh12m"] < -40:
        score -= 12
    if row["Volatility20d"] > 55:
        score -= 10

    # Fundos fechados e ETFs continuam elegiveis, mas nao dominam o ranking
    # apenas por distribuicao muito alta.
    if row["AssetType"] == "Fundo Fechado":
        score -= 10
    if row["AssetType"] == "ETF" and row["Yield12m"] > 15:
        score -= 12

    return float(np.clip(score, 0, 100))


def dividend_statistics(div_series, price):
    div_series = div_series.fillna(0)
    positive = div_series[div_series > 0]
    annual_per_share = float(positive.sum())
    event_count = int(len(positive))
    month_count = int(positive.groupby(positive.index.to_period("M")).size().shape[0]) if event_count else 0
    frequency = frequency_from_events(event_count, month_count)
    yield_12m = annual_per_share / price * 100 if price else 0.0

    monthly = div_series.resample("MS").sum()
    recent6 = float(monthly.tail(6).sum())
    previous6 = float(monthly.tail(12).head(6).sum()) if len(monthly) >= 12 else 0.0
    if previous6 > 0:
        growth6 = (recent6 / previous6 - 1) * 100
    elif recent6 > 0:
        growth6 = 0.0
    else:
        growth6 = -100.0

    positive_values = positive.values
    if len(positive_values) >= 2 and float(np.mean(positive_values)) != 0:
        cv = float(np.std(positive_values) / np.mean(positive_values))
    else:
        cv = 1.0 if event_count else 2.0

    return {
        "DividendPerShare12m": round(annual_per_share, 4),
        "Yield12m": round(yield_12m, 2),
        "DividendPayments12m": event_count,
        "DividendMonths12m": month_count,
        "DividendFrequency": frequency,
        "DividendGrowth6mPct": round(growth6, 2),
        "DividendCV": round(cv, 3),
        "IncomeAnnualPer100": round(yield_12m, 2),
        "IncomeMonthlyEquivalentPer100": round(yield_12m / 12, 2),
    }


def analyze_batch(batch_frame):
    tickers = batch_frame["Ticker"].tolist()
    metadata = batch_frame.set_index("Ticker").to_dict("index")

    data = yf.download(
        tickers=tickers,
        period="1y",
        interval="1d",
        group_by="column",
        auto_adjust=False,
        actions=True,
        progress=False,
        threads=True,
        timeout=45,
    )

    close = field_frame(data, "Close", tickers)
    volume = field_frame(data, "Volume", tickers)
    dividends = field_frame(data, "Dividends", tickers)
    results = []

    for ticker in tickers:
        if ticker not in close.columns:
            continue

        prices = close[ticker].dropna()
        if len(prices) < MIN_HISTORY_DAYS:
            continue

        vols = (
            volume[ticker].reindex(prices.index).fillna(0)
            if ticker in volume.columns
            else pd.Series(0, index=prices.index)
        )
        price = float(prices.iloc[-1])
        avg_dollar_volume = float((prices.tail(30) * vols.tail(30)).mean())
        if price < MIN_PRICE or avg_dollar_volume < MIN_AVG_DOLLAR_VOLUME:
            continue

        high = float(prices.max())
        low = float(prices.min())
        ma20 = float(prices.rolling(20).mean().iloc[-1])
        ma50 = float(prices.rolling(50).mean().iloc[-1])
        rsi = float(rsi_last(prices).iloc[-1])
        if not np.isfinite(rsi):
            continue

        position = ((price - low) / (high - low) * 100) if high != low else 50.0
        distance_high = ((price - high) / high * 100) if high else 0.0
        return5 = (price / float(prices.iloc[-6]) - 1) * 100 if len(prices) >= 6 else 0.0
        return20 = (price / float(prices.iloc[-21]) - 1) * 100 if len(prices) >= 21 else 0.0
        volatility20 = float(prices.pct_change().tail(20).std() * np.sqrt(252) * 100)

        div_series = (
            dividends[ticker].reindex(prices.index).fillna(0)
            if ticker in dividends.columns
            else pd.Series(0, index=prices.index)
        )
        div_stats = dividend_statistics(div_series, price)
        meta = metadata[ticker]
        asset_type = classify_asset(meta["SecurityName"], meta["IsETF"])

        row = {
            "Ticker": ticker,
            "SecurityName": meta["SecurityName"],
            "AssetType": asset_type,
            "IsETF": bool(meta["IsETF"]),
            "Price": round(price, 2),
            "High12m": round(high, 2),
            "Low12m": round(low, 2),
            "MA20": round(ma20, 2),
            "MA50": round(ma50, 2),
            "RSI": round(rsi, 2),
            "Position12m": round(position, 1),
            "DistanceHigh12m": round(distance_high, 2),
            "Return5d": round(return5, 2),
            "Return20d": round(return20, 2),
            "Volatility20d": round(volatility20, 2),
            "AvgDollarVolume30d": round(avg_dollar_volume, 0),
            **div_stats,
        }

        row["ScoreSwing"] = round(score_swing(row), 1)
        row["ScoreDividendos"] = round(score_dividends(row), 1)
        row["ScoreHibrido"] = round(
            0.4 * row["ScoreSwing"]
            + 0.4 * row["ScoreDividendos"]
            + 0.2 * min(row["ScoreSwing"], row["ScoreDividendos"]),
            1,
        )
        results.append(row)

    return results


def safe_write_csv(frame, path):
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False)
    temp.replace(path)


def main():
    started = datetime.now(timezone.utc)
    universe = load_market_universe()
    all_results = []
    failed_batches = 0

    print(f"Universe loaded: {len(universe)} symbols")
    batches = list(chunks(universe, BATCH_SIZE))

    for index, batch_frame in enumerate(batches, start=1):
        print(f"Batch {index}/{len(batches)}: {len(batch_frame)} symbols")
        try:
            all_results.extend(analyze_batch(batch_frame))
        except Exception as error:
            failed_batches += 1
            print(f"Batch failed: {error}")
        time.sleep(1.0)

    ranking = pd.DataFrame(all_results)
    if ranking.empty:
        raise RuntimeError("No valid assets were analyzed. Existing rankings were preserved.")

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ranking["UpdatedAt"] = updated_at

    top_swing = ranking.sort_values(
        ["ScoreSwing", "AvgDollarVolume30d"], ascending=False
    ).head(50)

    dividend_candidates = ranking[
        (ranking["Yield12m"] >= 1.0)
        & (ranking["DividendMonths12m"] >= 2)
        & (ranking["ScoreDividendos"] > 0)
    ].copy()
    top_dividends = dividend_candidates.sort_values(
        ["ScoreDividendos", "ScoreHibrido", "AvgDollarVolume30d"],
        ascending=False,
    ).head(50)

    hybrid_candidates = ranking[
        (ranking["ScoreSwing"] >= 45)
        & (ranking["ScoreDividendos"] >= 40)
    ].copy()
    top_hybrid = hybrid_candidates.sort_values(
        ["ScoreHibrido", "AvgDollarVolume30d"], ascending=False
    ).head(50)

    safe_write_csv(top_swing, TOP_SWING)
    safe_write_csv(top_dividends, TOP_DIVIDENDS)
    safe_write_csv(top_hybrid, TOP_HYBRID)

    tracked = {}
    for ticker in ["PSEC", "MAIN", "O", "JEPI"]:
        match = ranking[ranking["Ticker"] == ticker]
        if not match.empty:
            item = match.iloc[0]
            tracked[ticker] = {
                "score_swing": float(item["ScoreSwing"]),
                "score_dividendos": float(item["ScoreDividendos"]),
                "score_hibrido": float(item["ScoreHibrido"]),
                "yield_12m": float(item["Yield12m"]),
                "asset_type": item["AssetType"],
                "rank_dividendos": int(
                    dividend_candidates["ScoreDividendos"].rank(
                        method="min", ascending=False
                    ).loc[match.index[0]]
                ) if match.index[0] in dividend_candidates.index else None,
            }

    status = {
        "status": "success",
        "updated_at_utc": updated_at,
        "universe_symbols": len(universe),
        "valid_assets_analyzed": len(ranking),
        "dividend_candidates": len(dividend_candidates),
        "hybrid_candidates": len(hybrid_candidates),
        "failed_batches": failed_batches,
        "top_swing_count": len(top_swing),
        "top_dividend_count": len(top_dividends),
        "top_hybrid_count": len(top_hybrid),
        "tracked_assets": tracked,
        "duration_seconds": round(
            (datetime.now(timezone.utc) - started).total_seconds(), 1
        ),
    }

    temp_status = STATUS_FILE.with_suffix(".json.tmp")
    temp_status.write_text(json.dumps(status, indent=2), encoding="utf-8")
    temp_status.replace(STATUS_FILE)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
