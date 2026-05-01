import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from transformers import pipeline
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest
import yfinance as yf

# ── 0. Helper functions ──────────────────────────────────────────────────────

TICKER_OVERRIDES = {
    "royal bank of canada": "RY",
    "toronto dominion": "TD",
    "bank of nova scotia": "BNS",
    # add as needed
}

def company_to_ticker(company_name: str) -> str | None:
    # Check manual overrides first
    override = TICKER_OVERRIDES.get(company_name.lower())
    if override:
        return override

    # Fall back to yfinance
    try:
        ticker = yf.Search(company_name, max_results=1).quotes
        if ticker:
            symbol = ticker[0]["symbol"]
            if "." not in symbol:   # skip foreign exchange
                return symbol
    except Exception as e:
        print(f"  [yfinance] Lookup failed for '{company_name}': {e}")
    return None

# ── 1. Load env vars ──────────────────────────────────────────────────────────

load_dotenv()
API_KEY    = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

if not API_KEY or not SECRET_KEY:
    raise EnvironmentError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in .env")


# ── 2. Load FinBERT once ──────────────────────────────────────────────────────

print("Loading FinBERT model...")
_finbert = pipeline(
    "sentiment-analysis",
    model="ProsusAI/finbert",
    tokenizer="ProsusAI/finbert",
    top_k=None,
)
print("FinBERT ready.")


# ── 3. Alpaca/Benzinga fetch ──────────────────────────────────────────────────

def fetch_alpaca_headlines(
    symbols: list[str],
    start_date: str,
    end_date: str,
    max_results: int = 50,
) -> pd.DataFrame:
    """
    Fetch news headlines from Alpaca/Benzinga for a list of ticker symbols.

    Args:
        symbols:     List of ticker symbols e.g. ["AAPL", "MSFT"]
        start_date:  "YYYY-MM-DD"
        end_date:    "YYYY-MM-DD"
        max_results: Max articles to fetch (default 50)

    Returns:
        DataFrame with columns: headline, url, created_at, author, source, symbols
    """
    client = NewsClient(api_key=API_KEY, secret_key=SECRET_KEY)

    all_articles = []
    for symbol in symbols:
        print(f"  [Alpaca] Fetching news for {symbol} ({start_date} -> {end_date})...")
        try:
            request = NewsRequest(
                symbols=symbol,
                start=datetime.strptime(start_date, "%Y-%m-%d"),
                end=datetime.strptime(end_date, "%Y-%m-%d"),
                limit=max_results,
            )
            news = client.get_news(request)

            for sym, articles in news.data.items():
                for article in articles:
                    all_articles.append({
                        "symbol":     sym,
                        "headline":   article.headline,
                        "url":        article.url,
                        "created_at": article.created_at,
                        "author":     getattr(article, "author", None),
                        "source":     getattr(article, "source", None),
                        "summary":    getattr(article, "summary", None),
                    })

        except Exception as e:
            print(f"  [Alpaca] Error fetching {symbol}: {e}")
            continue

    if not all_articles:
        print("  [Alpaca] No articles found.")
        return pd.DataFrame(columns=["symbol", "headline", "url", "created_at", "author", "source", "summary"])

    df = pd.DataFrame(all_articles)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df = df.drop_duplicates(subset="url").sort_values("created_at", ascending=False).reset_index(drop=True)

    print(f"  [Alpaca] Fetched {len(df)} articles total.")
    return df


# ── 4. FinBERT scoring ────────────────────────────────────────────────────────

def score_headline(text: str) -> dict:
    raw   = _finbert(text[:512])[0]
    probs = {item["label"]: item["score"] for item in raw}
    return {
        "positive": round(probs.get("positive", 0.0), 4),
        "negative": round(probs.get("negative", 0.0), 4),
        "neutral":  round(probs.get("neutral",  0.0), 4),
        "score":    round(probs.get("positive", 0.0) - probs.get("negative", 0.0), 4),
        "label":    max(probs, key=probs.get),
    }

def score_headlines_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    scores = df["headline"].apply(score_headline).apply(pd.Series)
    return pd.concat([df, scores], axis=1)


# ── 5. Convenience function ───────────────────────────────────────────────────

def get_sentiment(
    company_names: list[str],
    start_date: str,
    end_date: str,
    max_results: int = 50,
) -> pd.DataFrame:
    symbols = []
    for name in company_names:
        ticker = company_to_ticker(name)
        if ticker and "." not in ticker:
            print(f"  {name} → {ticker}")
            symbols.append(ticker)
        else:
            print(f"  {name} → not found, skipping")

    if not symbols:
        print("No valid tickers found.")
        return pd.DataFrame()

    df = fetch_alpaca_headlines(symbols, start_date, end_date, max_results)
    if df.empty:
        return df
    print(f"  Scoring {len(df)} headlines with FinBERT...")
    df = score_headlines_df(df)
    print(f"  Mean sentiment score: {df['score'].mean():+.4f}")
    return df


# ── 6. Standalone test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = get_sentiment(
        company_names=["Walt Disney"],
        start_date="2024-01-01",
        end_date="2024-01-07",
        max_results=20,
    )

    if not results.empty:
        print("\n-- Sample Results --")
        for _, row in results[["created_at", "symbol", "headline", "score", "label"]].iterrows():
            print(f"  {str(row['created_at'])[:10]}  {row['symbol']:6s}  [{row['score']:+.4f}] {row['label']:8s}  {row['headline']}")

        print("\n-- Summary --")
        print(f"  Total headlines : {len(results)}")
        print(f"  Mean score      : {results['score'].mean():+.4f}")
        print(f"  By symbol       :\n{results.groupby('symbol')['score'].mean().to_string()}")
        print(f"  Labels          :\n{results['label'].value_counts().to_string()}")