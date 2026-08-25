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
BATCH_SIZE = 150
MIN_PRICE = 2.00
MIN_AVG_DOLLAR_VOLUME = 1_000_000
MIN_HISTORY_DAYS = 120


def download_text(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_market_universe():
    sources = [
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "Symbol"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "ACT Symbol"),
    ]
    frames = []
    for url, symbol_col in sources:
        text = download_text(url)
        frame = pd.read_csv(io.StringIO(text), sep="|")
        frame = frame[frame[symbol_col].notna()].copy()
        frame["Ticker"] = frame[symbol_col].astype(str).str.strip().str.upper()
        if "Test Issue" in frame.columns:
            frame = frame[frame["Test Issue"].astype(str).str.upper() != "Y"]
        frames.append(frame[["Ticker"]])

    universe = pd.concat(frames, ignore_index=True).drop_duplicates("Ticker")
    universe = universe[
        universe["Ticker"].str.match(r"^[A-Z][A-Z0-9.-]{0,9}$", na=False)
    ]
    universe = universe[
        ~universe["Ticker"].str.contains(r"[.$]", regex=True, na=False)
    ]
    universe = universe[~universe["Ticker"].str.contains(r"\^", regex=True, na=False)]
    return universe["Ticker"].tolist()


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def rsi_last(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def field_frame(data, field, batch):
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        try:
            frame = data[field].copy()
        except KeyError:
            return pd.DataFrame(index=data.index)
        if isinstance(frame, pd.Series):
            frame = frame.to_frame(name=batch[0])
        return frame
    if len(batch) == 1 and field in data.columns:
        return data[[field]].rename(columns={field: batch[0]})
    return pd.DataFrame(index=data.index)


def score_swing(row):
    score = 0.0
    score += np.clip((55 - row["RSI"]) * 1.15, -18, 30)
    score += np.clip((45 - row["Position12m"]) * 0.55, -24, 25)
    score += np.clip((-row["DistanceHigh12m"] - 7) * 0.8, -12, 22)
    if row["Price"] > row["MA20"]:
        score += 10
    if row["MA20"] > row["MA50"]:
        score += 10
    if row["Return5d"] > 0:
        score += min(row["Return5d"] * 1.5, 10)
    if row["Volatility20d"] > 6:
        score -= min((row["Volatility20d"] - 6) * 1.5, 15)
    return float(np.clip(score + 35, 0, 100))


def frequency_from_count(count):
    if count <= 0:
        return "Nao paga"
    if count >= 10:
        return "Mensal"
    if count >= 3:
        return "Trimestral"
    if count == 2:
        return "Semestral"
    return "Anual/Irregular"


def score_dividends(row):
    yield_score = np.clip(row["Yield12m"] * 7.0, 0, 55)
    frequency_points = {
        "Mensal": 22,
        "Trimestral": 16,
        "Semestral": 8,
        "Anual/Irregular": 3,
        "Nao paga": 0,
    }.get(row["DividendFrequency"], 0)
    regularity_points = np.clip(row["DividendMonths12m"] / 12 * 18, 0, 18)
    price_points = np.clip((60 - row["Position12m"]) * 0.18, -8, 10)
    trend_penalty = -10 if row["MA20"] < row["MA50"] and row["Return20d"] < -8 else 0
    extreme_yield_penalty = -20 if row["Yield12m"] > 20 else 0
    return float(np.clip(yield_score + frequency_points + regularity_points + price_points + trend_penalty + extreme_yield_penalty, 0, 100))


def analyze_batch(batch):
    data = yf.download(
        tickers=batch,
        period="1y",
        interval="1d",
        group_by="column",
        auto_adjust=False,
        actions=True,
        progress=False,
        threads=True,
        timeout=45,
    )
    close = field_frame(data, "Close", batch)
    volume = field_frame(data, "Volume", batch)
    dividends = field_frame(data, "Dividends", batch)
    results = []

    for ticker in batch:
        if ticker not in close.columns:
            continue
        prices = close[ticker].dropna()
        if len(prices) < MIN_HISTORY_DAYS:
            continue
        vols = volume[ticker].reindex(prices.index).fillna(0) if ticker in volume.columns else pd.Series(0, index=prices.index)
        price = float(prices.iloc[-1])
        avg_dollar_volume = float((prices.tail(30) * vols.tail(30)).mean())
        if price < MIN_PRICE or avg_dollar_volume < MIN_AVG_DOLLAR_VOLUME:
            continue

        high = float(prices.max())
        low = float(prices.min())
        ma20 = float(prices.rolling(20).mean().iloc[-1])
        ma50 = float(prices.rolling(50).mean().iloc[-1])
        rsi = float(rsi_last(prices).iloc[-1])
        position = ((price - low) / (high - low) * 100) if high != low else 50.0
        distance_high = ((price - high) / high * 100) if high else 0.0
        return5 = (price / float(prices.iloc[-6]) - 1) * 100 if len(prices) >= 6 else 0.0
        return20 = (price / float(prices.iloc[-21]) - 1) * 100 if len(prices) >= 21 else 0.0
        volatility20 = float(prices.pct_change().tail(20).std() * np.sqrt(252) * 100)

        div_series = dividends[ticker].fillna(0) if ticker in dividends.columns else pd.Series(0, index=prices.index)
        div_series = div_series.reindex(prices.index, fill_value=0)
        dividend_per_share = float(div_series.sum())
        dividend_months = int(div_series[div_series > 0].groupby(div_series[div_series > 0].index.to_period("M")).size().shape[0])
        dividend_count = int((div_series > 0).sum())
        dividend_yield = dividend_per_share / price * 100 if price else 0.0
        frequency = frequency_from_count(dividend_count)

        row = {
            "Ticker": ticker,
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
            "DividendPerShare12m": round(dividend_per_share, 4),
            "Yield12m": round(dividend_yield, 2),
            "DividendPayments12m": dividend_count,
            "DividendMonths12m": dividend_months,
            "DividendFrequency": frequency,
            "IncomeAnnualPer100": round(dividend_yield, 2),
            "IncomeMonthlyEquivalentPer100": round(dividend_yield / 12, 2),
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
    for index, batch in enumerate(batches, start=1):
        print(f"Batch {index}/{len(batches)}: {len(batch)} symbols")
        try:
            all_results.extend(analyze_batch(batch))
        except Exception as error:
            failed_batches += 1
            print(f"Batch failed: {error}")
        time.sleep(1.0)

    ranking = pd.DataFrame(all_results)
    if ranking.empty:
        raise RuntimeError("No valid assets were analyzed. Existing rankings were preserved.")

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ranking["UpdatedAt"] = updated_at
    top_swing = ranking.sort_values(["ScoreSwing", "AvgDollarVolume30d"], ascending=False).head(50)
    dividend_candidates = ranking[ranking["Yield12m"] > 0].copy()
    top_dividends = dividend_candidates.sort_values(["ScoreDividendos", "AvgDollarVolume30d"], ascending=False).head(50)
    hybrid_candidates = ranking[(ranking["ScoreSwing"] >= 45) & (ranking["ScoreDividendos"] >= 45)].copy()
    top_hybrid = hybrid_candidates.sort_values(["ScoreHibrido", "AvgDollarVolume30d"], ascending=False).head(50)

    safe_write_csv(top_swing, TOP_SWING)
    safe_write_csv(top_dividends, TOP_DIVIDENDS)
    safe_write_csv(top_hybrid, TOP_HYBRID)

    status = {
        "status": "success",
        "updated_at_utc": updated_at,
        "universe_symbols": len(universe),
        "valid_assets_analyzed": len(ranking),
        "failed_batches": failed_batches,
        "top_swing_count": len(top_swing),
        "top_dividend_count": len(top_dividends),
        "top_hybrid_count": len(top_hybrid),
        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
    }
    temp_status = STATUS_FILE.with_suffix(".json.tmp")
    temp_status.write_text(json.dumps(status, indent=2), encoding="utf-8")
    temp_status.replace(STATUS_FILE)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
