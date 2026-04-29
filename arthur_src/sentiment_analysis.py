"""
news_sentiment.py
-----------------
Fetches news headlines from GDELT for a given company name,
scores them with ProsusAI/finbert, and returns a tidy DataFrame.

Usage (standalone test):
    python news_sentiment.py
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from transformers import pipeline


# ── 1. Load FinBERT once (slow – keep this at module level) ──────────────────

print("Loading FinBERT model...")
_finbert = pipeline(
    "sentiment-analysis",
    model="ProsusAI/finbert",
    tokenizer="ProsusAI/finbert",
    top_k=None,          # return all 3 label probabilities
)
print("FinBERT ready.")


# ── 2. GDELT fetch ────────────────────────────────────────────────────────────

def fetch_gdelt_headlines(
    company_name: str,
    start_date: str,
    end_date: str,
    max_results: int = 50,
) -> pd.DataFrame:
    """
    Query the GDELT 2.0 Article Search API for headlines mentioning
    `company_name` within [start_date, end_date].

    Parameters
    ----------
    company_name : str   Company to search for, e.g. "Goldman Sachs"
    start_date   : str   Inclusive start date "YYYY-MM-DD"
    end_date     : str   Inclusive end date   "YYYY-MM-DD"
    max_results  : int   Max articles to return (GDELT cap: 250)

    Returns
    -------
    DataFrame with columns: title, url, seendate, domain, language
    """
    fmt = "%Y%m%d%H%M%S"
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").strftime(fmt)
    end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime(fmt)

    params = {
        "query":         f'"{company_name}" sourcelang:english',
        "mode":          "ArtList",
        "maxrecords":    max_results,
        "startdatetime": start_dt,
        "enddatetime":   end_dt,
        "sort":          "DateDesc",
        "format":        "json",
    }

    resp = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    articles = data.get("articles", [])
    if not articles:
        print(f"  [GDELT] No articles found for '{company_name}'.")
        return pd.DataFrame(columns=["title", "url", "seendate", "domain", "language"])

    df = pd.DataFrame(articles)[["title", "url", "seendate", "domain", "language"]]
    df["seendate"] = pd.to_datetime(df["seendate"], format="%Y%m%dT%H%M%SZ", errors="coerce")
    df = df.dropna(subset=["title"]).reset_index(drop=True)
    return df


# ── 3. FinBERT scoring ────────────────────────────────────────────────────────

def score_headline(text: str) -> dict:
    """
    Score a single headline with FinBERT.

    Returns a dict with keys:
        positive : float   P(positive), range [0, 1]
        negative : float   P(negative), range [0, 1]
        neutral  : float   P(neutral),  range [0, 1]
        score    : float   P(pos) - P(neg), range [-1, 1]
                           negative = bearish signal
                           positive = bullish signal
        label    : str     dominant class label
    """
    raw = _finbert(text[:512])[0]
    probs = {item["label"]: item["score"] for item in raw}

    return {
        "positive": round(probs.get("positive", 0.0), 4),
        "negative": round(probs.get("negative", 0.0), 4),
        "neutral":  round(probs.get("neutral",  0.0), 4),
        "score":    round(probs.get("positive", 0.0) - probs.get("negative", 0.0), 4),
        "label":    max(probs, key=probs.get),
    }


def score_headlines_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Scores every title in df and appends result columns.
    Adds: positive, negative, neutral, score, label
    """
    if df.empty:
        return df
    scores = df["title"].apply(score_headline).apply(pd.Series)
    return pd.concat([df, scores], axis=1)


# ── 4. Convenience function (fetch + score in one call) ───────────────────────

def get_company_sentiment(
    company_name: str,
    start_date: str,
    end_date: str,
    max_results: int = 50,
) -> pd.DataFrame:
    """
    Fetch GDELT headlines for `company_name` and score with FinBERT.

    Parameters
    ----------
    company_name : str   e.g. "Apple Inc" or "Goldman Sachs"
    start_date   : str   "YYYY-MM-DD"
    end_date     : str   "YYYY-MM-DD"
    max_results  : int   headlines to fetch (default 50, GDELT cap 250)

    Returns
    -------
    DataFrame with columns:
        title, url, seendate, domain, language,
        positive, negative, neutral, score, label
    """
    print(f"[{company_name}] Fetching headlines ({start_date} -> {end_date})...")
    df = fetch_gdelt_headlines(company_name, start_date, end_date, max_results)

    if df.empty:
        return df

    print(f"  Scoring {len(df)} headlines with FinBERT...")
    df = score_headlines_df(df)
    print(f"  Mean sentiment score: {df['score'].mean():+.4f}")
    return df


# ── 5. Standalone test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = get_company_sentiment(
        company_name="OpenAI",
        start_date="2026-03-01",
        end_date="2026-03-07",
        max_results=20,
    )

    if not results.empty:
        print("\n-- Sample Results (title | score | label) --")
        for _, row in results[["seendate", "title", "score", "label"]].iterrows():
            date_str = str(row["seendate"])[:10]
            title_short = row["title"]
            print(f"  {date_str}  [{row['score']:+.4f}] {row['label']:8s}  {title_short}")

        print("\n-- Summary --")
        print(f"  Total headlines : {len(results)}")
        print(f"  Mean score      : {results['score'].mean():+.4f}")
        print(f"  Labels          :\n{results['label'].value_counts().to_string()}")