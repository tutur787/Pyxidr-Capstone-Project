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
import urllib.request
import xml.etree.ElementTree as ET
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
            for item in result.news:
                scored = _score(item.headline)
                issuer = item.symbols[0] if item.symbols else "General"
                articles.append({
                    "date":      str(item.created_at)[:10],
                    "headline":  item.headline,
                    "source":    item.source,
                    "issuer":    issuer,
                    "url":       item.url or "",
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


# ── Bond market rates (US Treasury XML + stubs for Gilts/CAD) ────────────────

_BOND_STUB = [
    {"symbol": "US3M",  "name": "US T-Bill 3M",    "yield_pct": 5.25, "change_bps":  2, "direction": "up"},
    {"symbol": "US1Y",  "name": "US Treasury 1Y",   "yield_pct": 5.10, "change_bps": -1, "direction": "down"},
    {"symbol": "US5Y",  "name": "US Treasury 5Y",   "yield_pct": 4.35, "change_bps":  3, "direction": "up"},
    {"symbol": "GILTS", "name": "UK Gilts 10Y",     "yield_pct": 4.20, "change_bps": -2, "direction": "down"},
    {"symbol": "CAD5Y", "name": "CAD Govt 5Y",      "yield_pct": 3.75, "change_bps":  1, "direction": "up"},
]

_TREASURY_XML = (
    "https://home.treasury.gov/resource-center/data-chart-center"
    "/interest-rates/pages/xml?data=daily_treasury_yield_curve"
    "&field_tdr_date_value_month={ym}"
)
_NS = "http://schemas.microsoft.com/ado/2007/08/dataservices"


def _parse_treasury_xml(date: str) -> dict[str, float]:
    """Fetch US Treasury yield curve XML for the month containing `date`.
    Returns { '3M': yield, '1Y': yield, '5Y': yield } in percent, or {} on failure.
    """
    dt = datetime.strptime(date, "%Y-%m-%d")
    url = _TREASURY_XML.format(ym=dt.strftime("%Y%m"))
    req = urllib.request.Request(url, headers={"User-Agent": "fabn-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        tree = ET.parse(resp)

    target_date = dt.strftime("%Y-%m-%dT00:00:00")
    best_entry: dict[str, float] = {}
    best_diff = 999

    for entry in tree.iter():
        # Each <m:properties> block holds one trading day
        if not entry.tag.endswith("}properties"):
            continue
        date_el = entry.find(f"{{{_NS}}}NEW_DATE")
        if date_el is None or not date_el.text:
            continue
        entry_date = date_el.text[:10]
        diff = abs((datetime.strptime(entry_date, "%Y-%m-%d") - dt).days)
        if diff < best_diff:
            best_diff = diff
            row: dict[str, float] = {}
            for tag, key in [("BC_3MONTH", "3M"), ("BC_1YEAR", "1Y"), ("BC_5YEAR", "5Y")]:
                el = entry.find(f"{{{_NS}}}{tag}")
                if el is not None and el.text:
                    row[key] = float(el.text)
            best_entry = row

    return best_entry


def fetch_bond_rates(date: str) -> list[dict]:
    """
    Return reference rates for 5 fixed-income benchmarks at `date`.

    US rates come from the US Treasury yield curve feed (free, no API key).
    UK Gilts and CAD Govt use stub values (live integration pending).

    Each element: { symbol, name, yield_pct, change_bps, direction }
    Falls back to stubs on any error.
    """
    try:
        yields = _parse_treasury_xml(date)
        if not yields:
            logger.warning("Treasury XML returned no data for date=%s", date)
            return _BOND_STUB

        # Try to get previous trading day to compute day change
        prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")
        prev_yields = _parse_treasury_xml(prev_date)

        def bps_change(sym_key: str, curr: float) -> tuple[int, str]:
            if sym_key in prev_yields:
                delta = round((curr - prev_yields[sym_key]) * 100)
                return delta, "up" if delta >= 0 else "down"
            return 0, "up"

        results: list[dict] = []
        mapping = [
            ("US3M",  "US T-Bill 3M",   "3M"),
            ("US1Y",  "US Treasury 1Y", "1Y"),
            ("US5Y",  "US Treasury 5Y", "5Y"),
        ]
        for sym, name, key in mapping:
            if key not in yields:
                continue
            curr_yield = round(yields[key], 3)
            chg, direction = bps_change(key, yields[key])
            results.append({
                "symbol":     sym,
                "name":       name,
                "yield_pct":  curr_yield,
                "change_bps": chg,
                "direction":  direction,
            })

        # Gilts and CAD: stubs (no free unauthenticated API currently wired)
        for stub in _BOND_STUB[3:]:
            results.append(stub)

        logger.info("Bond rates: %d instruments for date=%s", len(results), date)
        return results

    except Exception as exc:
        logger.error("Bond rates fetch failed: %s", exc)
        return _BOND_STUB
