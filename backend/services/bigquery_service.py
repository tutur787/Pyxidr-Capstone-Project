"""
BigQuery service — reads from the 'insurance-backed-securities.Securities' dataset.

Tables used:
  Agg_Spread_Long   — daily G-spread per CUSIP (Date, CUSIP, Spread in bps)

  Note: Agg_Fixed_Field (bond metadata) is not currently queried by any live
  code path here — the bond collateral universe is read directly from
  Optimization/fabn_data_pipeline.py instead (see backend/services/bond_service.py).

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


# ── FABN list ─────────────────────────────────────────────────────────────────

_KNOWN_FABNS = [
    # The one real FABN this whole app is built around (FABN.xlsx "BB Fixed" sheet):
    # ATH 3.205 03/08/27, issued by Athene Global Funding.
    {
        "cusip":    "04685A3L3",
        "coupon":   0.03205,
        "maturity": "2027-03-08",
        "rating":   "A+",
        "sector":   "Athene Global Funding",
        "status":   "active",
    },
]


def get_fabn_list() -> list[dict]:
    """Return the known FABN entries for the selector."""
    return _KNOWN_FABNS
