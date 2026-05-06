"""
Alpaca data service — news headlines, market quotes, and bond ETF rate proxies.

News:    Alpaca/Benzinga NewsClient.
Quotes:  StockHistoricalDataClient — 5 popular tickers, price at simulated date
         with 1-day change computed from the two most recent trading bars.
Rates:   Same client — SHY/IEF bars (kept for backwards compat).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()

logger = logging.getLogger(__name__)

# VADER loads once at import time — no model download, no latency
_vader = SentimentIntensityAnalyzer()


def _score(headline: str) -> dict:
    """Map VADER compound score to sentiment label + numeric score."""
    compound = _vader.polarity_scores(headline)["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return {"sentiment": label, "score": round(compound, 3)}

API_KEY    = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# Tickers relevant to FABN issuers (insurance / bank holding companies)
FABN_TICKERS = [
    "MET", "PRU", "AFL", "AIG", "LNC",   # US insurance
    "RY",  "TD",  "BNS", "BMO",          # Canadian banks (US-listed)
    "JPM", "GS",  "BAC", "WFC",          # US banks
    "TRV", "HIG",                         # P&C that issue IG bonds
]

# ETF proxies: SHY ≈ 1-3Y Treasury, IEF ≈ 7-10Y Treasury
RATE_SYMBOLS = ["SHY", "IEF"]


# ── News ──────────────────────────────────────────────────────────────────────

def fetch_news(date: str, limit: int = 25) -> list[dict]:
    """
    Return up to `limit` Alpaca/Benzinga headlines for FABN-relevant tickers
    on `date` (the simulated trading day).

    Strategy: try a 1-day window first so news is specific to that date.
    If Alpaca returns nothing (weekend / holiday / low coverage), widen to
    3 days, then 7 days — stopping as soon as we get at least one article.
    Falls back to [] on any error.
    """
    if not API_KEY or not SECRET_KEY:
        logger.warning("Alpaca credentials not set — returning empty news")
        return []

    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        end_dt = datetime.strptime(date, "%Y-%m-%d")
        client = NewsClient(api_key=API_KEY, secret_key=SECRET_KEY)

        articles: list[dict] = []
        for days_back in (1, 3, 7):
            start_dt = end_dt - timedelta(days=days_back)
            request  = NewsRequest(
                symbols=",".join(FABN_TICKERS),
                start=start_dt,
                end=end_dt,
                limit=limit,
            )
            result = client.get_news(request)

            articles = []
            for sym, items in result.data.items():
                for item in items:
                    scored = _score(item.headline)
                    articles.append({
                        "date":      str(item.created_at)[:10],
                        "headline":  item.headline,
                        "source":    getattr(item, "source", "Alpaca"),
                        "issuer":    sym,
                        "url":       getattr(item, "url", ""),
                        "sentiment": scored["sentiment"],
                        "score":     scored["score"],
                    })

            if articles:
                logger.info(
                    "Alpaca news: %d articles for date=%s (window=%dd)",
                    len(articles), date, days_back,
                )
                break

        articles.sort(key=lambda a: a["date"], reverse=True)
        logger.info("Alpaca news: %d articles for date=%s", len(articles), date)
        return articles[:limit]

    except Exception as exc:
        logger.error("Alpaca news fetch failed: %s", exc)
        return []


# ── Rates (ETF bars) ──────────────────────────────────────────────────────────

def fetch_rates(date: str, days_back: int = 90) -> list[dict]:
    """
    Return daily SHY / IEF close prices for the `days_back` window ending on
    `date`.  Prices are normalised to the first bar in the window (base = 100)
    so both series are comparable on the same axis.

    Each element: { date, rate_2y, rate_10y }
    where rate_2y = normalised SHY close, rate_10y = normalised IEF close.
    Falls back to [] on any error.
    """
    if not API_KEY or not SECRET_KEY:
        logger.warning("Alpaca credentials not set — returning empty rates")
        return []

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end_dt   = datetime.strptime(date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=days_back)

        client  = StockHistoricalDataClient(api_key=API_KEY, secret_key=SECRET_KEY)
        request = StockBarsRequest(
            symbol_or_symbols=RATE_SYMBOLS,
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
        )
        bars_resp = client.get_stock_bars(request)

        # Build { date -> { "SHY": price, "IEF": price } }
        date_map: dict[str, dict[str, float]] = {}
        for sym in RATE_SYMBOLS:
            if sym not in bars_resp.data:
                continue
            for bar in bars_resp.data[sym]:
                d = str(bar.timestamp)[:10]
                date_map.setdefault(d, {})[sym] = round(float(bar.close), 4)

        sorted_dates = sorted(date_map.keys())
        if not sorted_dates:
            return []

        # Normalise to first bar (base 100) so both ETFs plot on same scale
        base_shy = date_map[sorted_dates[0]].get("SHY", 1.0) or 1.0
        base_ief = date_map[sorted_dates[0]].get("IEF", 1.0) or 1.0

        result: list[dict] = []
        for d in sorted_dates:
            entry: dict = {"date": d}
            if "SHY" in date_map[d]:
                entry["rate_2y"] = round(date_map[d]["SHY"] / base_shy * 100, 3)
            if "IEF" in date_map[d]:
                entry["rate_10y"] = round(date_map[d]["IEF"] / base_ief * 100, 3)
            if len(entry) > 1:
                result.append(entry)

        logger.info("Alpaca rates: %d bars for date=%s", len(result), date)
        return result

    except Exception as exc:
        logger.error("Alpaca rates fetch failed: %s", exc)
        return []


# ── Market quotes (Bloomberg-style ticker) ────────────────────────────────────

# 5 highly recognisable names; mix of broad market, tech, and financials
MARKET_SYMBOLS = ["SPY", "AAPL", "MSFT", "NVDA", "JPM"]

SYMBOL_NAMES = {
    "SPY":  "S&P 500 ETF",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "JPM":  "JPMorgan Chase",
}


def fetch_market_quotes(date: str) -> list[dict]:
    """
    Return price and 1-day change for MARKET_SYMBOLS at (or just before) `date`.

    Fetches 10 calendar days of bars so weekends / holidays are handled — we
    take the two most-recent trading bars per symbol and compute the diff.

    Each element:
        { symbol, name, price, change, change_pct, direction }
    Falls back to [] on any error.
    """
    if not API_KEY or not SECRET_KEY:
        logger.warning("Alpaca credentials not set — returning empty quotes")
        return []

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end_dt   = datetime.strptime(date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=10)   # enough to straddle any holiday run

        client  = StockHistoricalDataClient(api_key=API_KEY, secret_key=SECRET_KEY)
        request = StockBarsRequest(
            symbol_or_symbols=MARKET_SYMBOLS,
            timeframe=TimeFrame.Day,
            start=start_dt,
            end=end_dt,
        )
        bars_resp = client.get_stock_bars(request)

        results: list[dict] = []
        for sym in MARKET_SYMBOLS:
            if sym not in bars_resp.data:
                continue
            bars = sorted(bars_resp.data[sym], key=lambda b: b.timestamp)
            if len(bars) < 2:
                continue

            prev_close = float(bars[-2].close)
            curr_close = float(bars[-1].close)
            change     = round(curr_close - prev_close, 2)
            change_pct = round(change / prev_close * 100, 2)

            results.append({
                "symbol":     sym,
                "name":       SYMBOL_NAMES.get(sym, sym),
                "price":      round(curr_close, 2),
                "change":     change,
                "change_pct": change_pct,
                "direction":  "up" if change >= 0 else "down",
                "date":       str(bars[-1].timestamp)[:10],
            })

        logger.info("Alpaca market quotes: %d symbols for date=%s", len(results), date)
        return results

    except Exception as exc:
        logger.error("Alpaca market quotes fetch failed: %s", exc)
        return []
