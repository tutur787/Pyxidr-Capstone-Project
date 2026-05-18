"""
BigQuery service — reads from the 'insurance-backed-securities.Securities' dataset.

Tables used:
  Agg_Fixed_Field   — bond metadata (CUSIP, coupon, maturity, rating, duration, sector)
  Agg_Spread_Long   — daily G-spread per CUSIP (Date, CUSIP, Spread in bps)

Authentication:
  Uses Application Default Credentials.  Before starting the backend run:
      gcloud auth application-default login
  or set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
"""

from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ID = "insurance-backed-securities"
DATASET    = "Securities"


@lru_cache(maxsize=1)
def _get_client():
    from google.cloud import bigquery
    return bigquery.Client(project=PROJECT_ID)


def _query(sql: str) -> pd.DataFrame:
    return _get_client().query(sql).to_dataframe()


# ── Portfolio KPIs ────────────────────────────────────────────────────────────

def get_portfolio_kpis(date: str) -> dict:
    """
    Return aggregate KPIs derived from bond metadata + latest spreads.

    Fields that require actual holdings / optimizer output (value, returns,
    CVaR, Sharpe, RBC usage) are left as stubs until the optimizer is wired up.
    """
    try:
        fixed = _query(f"""
            SELECT
                CUSIP,
                CAST(Cpn AS FLOAT64)           AS coupon,
                `Mac Dur _Ask_`                AS duration,
                `BBG Composite`                AS rating_sp,
                BICS_LEVEL_1_SECTOR_NAME       AS sector
            FROM `{PROJECT_ID}.{DATASET}.Agg_Fixed_Field`
            WHERE CUSIP IS NOT NULL
              AND Maturity > '{date}'
        """)

        n_bonds      = int(len(fixed))
        avg_duration = float(fixed["duration"].dropna().mean()) if n_bonds else 4.21
        avg_coupon   = float(fixed["coupon"].dropna().mean())   if n_bonds else 5.83

    except Exception as exc:
        logger.error("BQ fixed field query failed: %s", exc)
        return _stub_kpis()

    try:
        spread_df = _query(f"""
            WITH latest AS (
                SELECT MAX(Date) AS max_date
                FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long`
                WHERE Date <= '{date}'
            )
            SELECT s.CUSIP, s.Spread
            FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long` s
            JOIN latest l ON s.Date = l.max_date
        """)
        avg_spread_bps = float(spread_df["Spread"].dropna().mean()) if not spread_df.empty else 71.0

    except Exception as exc:
        logger.error("BQ spread query failed: %s", exc)
        avg_spread_bps = 71.0

    return {
        # Live from BQ
        "n_bonds":    n_bonds,
        "duration":   round(avg_duration, 2),
        "yield_pct":  round(avg_coupon,   2),
        "spread_bps": round(avg_spread_bps, 1),
        # Stubs — require optimizer output
        "value":        250_000_000,
        "total_return": 1.52,
        "cvar_pct":     2.87,
        "sharpe":       1.34,
        "ytd_return":   3.41,
        "rbc_c1_usage": 0.62,
    }


# ── Spread time series (for future use in charts) ─────────────────────────────

def get_spread_history(date: str, days_back: int = 90) -> list[dict]:
    """
    Return daily average spread across the universe for the `days_back` window.
    Each element: { date, avg_spread_bps }
    """
    try:
        df = _query(f"""
            SELECT Date, AVG(Spread) AS avg_spread
            FROM `{PROJECT_ID}.{DATASET}.Agg_Spread_Long`
            WHERE Date BETWEEN DATE_SUB(DATE '{date}', INTERVAL {days_back} DAY)
                           AND DATE '{date}'
            GROUP BY Date
            ORDER BY Date
        """)
        df["Date"] = df["Date"].astype(str)
        return [
            {"date": row["Date"], "avg_spread_bps": round(float(row["avg_spread"]), 2)}
            for _, row in df.iterrows()
        ]
    except Exception as exc:
        logger.error("BQ spread history query failed: %s", exc)
        return []


def _stub_kpis() -> dict:
    return {
        "value": 250_000_000, "total_return": 1.52, "yield_pct": 5.83,
        "duration": 4.21, "cvar_pct": 2.87, "sharpe": 1.34,
        "n_bonds": 104, "ytd_return": 3.41, "spread_bps": 71, "rbc_c1_usage": 0.62,
    }


# ── FABN list ─────────────────────────────────────────────────────────────────

_STUB_FABNS = [
    {"cusip": "FABN1", "coupon": None, "maturity": "", "rating": "", "sector": ""},
    {"cusip": "FABN2", "coupon": None, "maturity": "", "rating": "", "sector": ""},
    {"cusip": "FABN3", "coupon": None, "maturity": "", "rating": "", "sector": ""},
]


def get_fabn_list() -> list[dict]:
    """
    Return placeholder FABN entries for the selector.
    Real FABN identifiers will replace these once wired to the optimizer output.
    """
    return _STUB_FABNS

    try:  # noqa: unreachable — kept for when real FABN data is ready
        df = _query(f"""
            SELECT DISTINCT
                CUSIP,
                CAST(Cpn AS FLOAT64)          AS coupon,
                CAST(Maturity AS STRING)       AS maturity,
                `BBG Composite`               AS rating,
                BICS_LEVEL_1_SECTOR_NAME      AS sector
            FROM `{PROJECT_ID}.{DATASET}.Agg_Fixed_Field`
            WHERE CUSIP IS NOT NULL
            ORDER BY CUSIP
        """)
        if df.empty:
            return _STUB_FABNS
        return [
            {
                "cusip":    row["CUSIP"],
                "coupon":   round(float(row["coupon"]), 4) if pd.notna(row["coupon"]) else None,
                "maturity": str(row["maturity"])[:10] if pd.notna(row["maturity"]) else "",
                "rating":   str(row["rating"]) if pd.notna(row["rating"]) else "",
                "sector":   str(row["sector"]) if pd.notna(row["sector"]) else "",
            }
            for _, row in df.iterrows()
        ]
    except Exception as exc:
        logger.error("BQ FABN list query failed: %s", exc)
        return _STUB_FABNS
