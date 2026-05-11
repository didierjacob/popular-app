"""
External Scores Service — Session 2
Calculates Popularity External Score from Wikipedia Pageviews + Google Trends.

Formula:
  popularity_external_score = 0.7 × wiki_score_norm + 0.3 × trends_score_norm

Wikipedia: 6 languages (EN, FR, DE, ES, IT, PT), avg daily views over 7 days, summed.
Google Trends: worldwide interest over 7 days (0-100 scale).

This module contains pure service functions, testable in isolation.
"""

import httpx
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("external_scores")

# ── Configuration ──────────────────────────────────────────────────────────
WIKI_LANGUAGES = ["en", "fr", "de", "es", "it", "pt"]
WIKIMEDIA_PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
USER_AGENT = "Popularoo/1.0 (contact@popularoo.com)"

# Rate limiting (seconds between requests)
WIKI_REQUEST_DELAY = 0.2   # 200ms between Wikipedia requests

# ── V1.0 Weighting ────────────────────────────────────────────────────────
# 100% Wikipedia for V1.0. Google Trends disabled (see fetch_google_trends).
# These defaults are overridden at runtime by app_settings flags:
#   external_score_use_trends, external_score_wiki_weight, external_score_trends_weight
DEFAULT_WIKI_WEIGHT = 1.0
DEFAULT_TRENDS_WEIGHT = 0.0
DEFAULT_USE_TRENDS = False


# ── Wikipedia Pageviews ────────────────────────────────────────────────────

async def fetch_wikipedia_pageviews_single_lang(
    name: str,
    lang: str,
    days: int = 7,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict:
    """
    Fetch average daily pageviews for a person in a single Wikipedia language.

    Returns:
        {"lang": "en", "avg_daily_views": 12345.6, "total_views": 86419, "days": 7, "error": None}
    """
    # Wikipedia article titles use underscores
    title = name.replace(" ", "_")

    # Calculate date range (7 days ending yesterday — today's data is often incomplete)
    end_date = datetime.utcnow() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    url = f"{WIKIMEDIA_PAGEVIEWS_API}/{lang}.wikipedia/all-access/all-agents/{title}/daily/{start_str}/{end_str}"

    result = {
        "lang": lang,
        "avg_daily_views": 0.0,
        "total_views": 0,
        "days": days,
        "error": None,
    }

    try:
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=15)
            should_close = True

        resp = await client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            total = sum(item.get("views", 0) for item in items)
            result["total_views"] = total
            result["avg_daily_views"] = round(total / max(len(items), 1), 1)
        elif resp.status_code == 404:
            # No article in this language — expected, not an error
            result["error"] = "no_article"
        else:
            result["error"] = f"http_{resp.status_code}"

        if should_close:
            await client.aclose()

    except Exception as e:
        result["error"] = str(e)

    return result


async def fetch_wikipedia_pageviews(
    name: str,
    langs: Optional[List[str]] = None,
    days: int = 7,
) -> Dict:
    """
    Fetch pageviews across all configured languages and sum them.

    Returns:
        {
            "name": "Donald Trump",
            "per_lang": [{"lang": "en", "avg_daily_views": 50000, ...}, ...],
            "wiki_score_brut": 65432.1,  # sum of avg_daily_views across all langs
            "total_views_all_langs": 458025,
            "errors": ["de: no_article"],
        }
    """
    if langs is None:
        langs = WIKI_LANGUAGES

    per_lang = []
    errors = []

    async with httpx.AsyncClient(timeout=15) as client:
        for i, lang in enumerate(langs):
            if i > 0:
                import asyncio
                await asyncio.sleep(WIKI_REQUEST_DELAY)

            result = await fetch_wikipedia_pageviews_single_lang(name, lang, days, client)
            per_lang.append(result)

            if result["error"] and result["error"] != "no_article":
                errors.append(f"{lang}: {result['error']}")

    wiki_score_brut = sum(r["avg_daily_views"] for r in per_lang)
    total_views = sum(r["total_views"] for r in per_lang)

    return {
        "name": name,
        "per_lang": per_lang,
        "wiki_score_brut": round(wiki_score_brut, 1),
        "total_views_all_langs": total_views,
        "errors": errors,
    }


# ── Google Trends ──────────────────────────────────────────────────────────
# DISABLED in V1.0: pytrends blocked by Google from cloud IPs (Render, AWS, etc.).
# Google returns HTTP 429 (Too Many Requests) silently.
# Reactivable via app_settings flag: external_score_use_trends = true
#
# Reactivation plan for V2:
#   Option 1: Residential proxy (e.g. ScraperAPI, Bright Data)
#   Option 2: Alternative API (SerpAPI Google Trends endpoint, ~$50/month)
#   Option 3: Non-cloud hosting for the trends fetch job
#
# The code below is kept intact and functional for when Trends is re-enabled.

async def fetch_google_trends(name: str, days: int = 7) -> Dict:
    """
    Fetch Google Trends interest for a person name (worldwide, last 7 days).
    Uses pytrends library.

    Returns:
        {
            "name": "Donald Trump",
            "trends_score_brut": 87,  # 0-100 scale from Google
            "error": None,
        }
    """
    result = {
        "name": name,
        "trends_score_brut": 0.0,
        "error": None,
    }

    try:
        # pytrends is synchronous — run in thread to avoid blocking async loop
        import asyncio
        loop = asyncio.get_event_loop()
        score = await loop.run_in_executor(None, _fetch_trends_sync, name, days)
        result["trends_score_brut"] = score
    except Exception as e:
        result["error"] = str(e)
        logger.warning(f"Google Trends failed for '{name}': {e}")

    return result


def _fetch_trends_sync(name: str, days: int = 7) -> float:
    """
    Synchronous Google Trends fetch. Called via run_in_executor.
    Returns average interest score (0-100).
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        pytrends.build_payload([name], timeframe=f"now {days}-d", geo="")

        interest_df = pytrends.interest_over_time()

        if interest_df is not None and not interest_df.empty and name in interest_df.columns:
            values = interest_df[name].tolist()
            avg = sum(values) / max(len(values), 1)
            return round(avg, 1)
        return 0.0
    except Exception as e:
        logger.warning(f"pytrends error for '{name}': {e}")
        return 0.0


# ── Normalization & Combined Score ─────────────────────────────────────────

def normalize_wiki_score(wiki_brut: float, max_wiki_in_db: float) -> float:
    """
    Normalize Wikipedia score to 0-100 scale using LOGARITHMIC normalization.
    Spreads scores across a wider visual range (30-100 instead of 1-100).

    Formula:
        wiki_score_log = log10(wiki_brut + 1)
        max_wiki_log   = log10(max_wiki + 1)
        wiki_score_norm = (wiki_score_log / max_wiki_log) × 100

    Example with Trump=62201, Brad Pitt=15836, Squeezie=826:
        Trump:     log10(62202) / log10(62202) × 100 = 100.0
        Brad Pitt: log10(15837) / log10(62202) × 100 ≈ 87.7
        Squeezie:  log10(827)   / log10(62202) × 100 ≈ 60.9
    """
    import math
    if not max_wiki_in_db or max_wiki_in_db <= 0 or wiki_brut <= 0:
        return 0.0
    wiki_log = math.log10(wiki_brut + 1)
    max_log = math.log10(max_wiki_in_db + 1)
    if max_log <= 0:
        return 0.0
    normalized = (wiki_log / max_log) * 100
    return round(min(100.0, max(0.0, normalized)), 1)


def compute_external_score(
    wiki_norm: float,
    trends_norm: float,
    use_trends: bool = DEFAULT_USE_TRENDS,
    wiki_weight: float = DEFAULT_WIKI_WEIGHT,
    trends_weight: float = DEFAULT_TRENDS_WEIGHT,
) -> float:
    """
    Combined external score. Weights are configurable via app_settings.
    V1.0 default: 100% Wikipedia, 0% Trends.
    """
    if use_trends and trends_weight > 0:
        score = (wiki_weight * wiki_norm) + (trends_weight * trends_norm)
    else:
        # V1.0: pure Wikipedia
        score = wiki_norm
    return round(min(100.0, max(0.0, score)), 1)


# ── Full Pipeline for One Person ───────────────────────────────────────────

async def compute_external_score_for_person(
    name: str,
    max_wiki_in_db: Optional[float] = None,
    use_trends: bool = DEFAULT_USE_TRENDS,
    wiki_weight: float = DEFAULT_WIKI_WEIGHT,
    trends_weight: float = DEFAULT_TRENDS_WEIGHT,
) -> Dict:
    """
    Full pipeline: Wikipedia (+ optionally Trends) → normalized → combined score.
    Used for testing individual persons.

    Returns complete breakdown for debugging/validation.
    """
    import time as _time
    start = _time.time()

    # Step 1: Wikipedia pageviews
    wiki_result = await fetch_wikipedia_pageviews(name)

    # Step 2: Google Trends (only if enabled)
    trends_brut = 0.0
    trends_error = "disabled_v1"
    if use_trends:
        trends_result = await fetch_google_trends(name)
        trends_brut = trends_result["trends_score_brut"]
        trends_error = trends_result["error"]

    # Step 3: Normalize
    wiki_brut = wiki_result["wiki_score_brut"]

    # If max_wiki not provided, use wiki_brut as its own max (score = 100)
    effective_max = max_wiki_in_db if max_wiki_in_db and max_wiki_in_db > 0 else wiki_brut
    wiki_norm = normalize_wiki_score(wiki_brut, effective_max)
    trends_norm = trends_brut  # Already 0-100

    # Step 4: Combined (respects use_trends flag)
    external_score = compute_external_score(wiki_norm, trends_norm, use_trends, wiki_weight, trends_weight)

    elapsed = round(_time.time() - start, 2)

    return {
        "name": name,
        "wiki_pageviews": wiki_result["per_lang"],
        "wiki_score_brut": wiki_brut,
        "wiki_score_norm": wiki_norm,
        "wiki_max_used_for_norm": effective_max,
        "wiki_errors": wiki_result["errors"],
        "trends_score_brut": trends_brut,
        "trends_error": trends_error,
        "trends_enabled": use_trends,
        "popularity_external_score": external_score,
        "elapsed_seconds": elapsed,
    }


async def compute_external_scores_batch(
    names: List[str],
    use_trends: bool = DEFAULT_USE_TRENDS,
    wiki_weight: float = DEFAULT_WIKI_WEIGHT,
    trends_weight: float = DEFAULT_TRENDS_WEIGHT,
) -> Dict:
    """
    Batch pipeline: fetch wiki scores for multiple persons, normalize against
    the group's max, then compute final external score.

    Returns all results plus the global max_wiki used for normalization.
    """
    import time as _time
    import asyncio
    start = _time.time()

    # Pass 1: Collect all wiki_score_brut
    raw_results = []
    for i, name in enumerate(names):
        if i > 0:
            await asyncio.sleep(WIKI_REQUEST_DELAY)
        wiki_result = await fetch_wikipedia_pageviews(name)
        trends_brut = 0.0
        trends_error = "disabled_v1"
        if use_trends:
            trends_result = await fetch_google_trends(name)
            trends_brut = trends_result["trends_score_brut"]
            trends_error = trends_result["error"]
        raw_results.append({
            "name": name,
            "wiki_result": wiki_result,
            "wiki_brut": wiki_result["wiki_score_brut"],
            "trends_brut": trends_brut,
            "trends_error": trends_error,
        })

    # Pass 2: Find global max_wiki
    max_wiki = max((r["wiki_brut"] for r in raw_results), default=1.0)
    if max_wiki <= 0:
        max_wiki = 1.0

    # Pass 3: Normalize and compute final scores
    results = []
    for r in raw_results:
        wiki_norm = normalize_wiki_score(r["wiki_brut"], max_wiki)
        trends_norm = r["trends_brut"]
        external_score = compute_external_score(wiki_norm, trends_norm, use_trends, wiki_weight, trends_weight)
        results.append({
            "name": r["name"],
            "wiki_score_brut": r["wiki_brut"],
            "wiki_score_norm": wiki_norm,
            "trends_score_brut": r["trends_brut"],
            "popularity_external_score": external_score,
            "wiki_per_lang": r["wiki_result"]["per_lang"],
            "wiki_errors": r["wiki_result"]["errors"],
        })

    elapsed = round(_time.time() - start, 2)

    return {
        "max_wiki_in_batch": max_wiki,
        "total_processed": len(results),
        "trends_enabled": use_trends,
        "results": sorted(results, key=lambda x: -x["popularity_external_score"]),
        "elapsed_seconds": elapsed,
    }
