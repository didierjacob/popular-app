"""
Candidate Detection Service — Session 3
Auto-detects new celebrity candidates from Wikipedia Most Viewed Articles.

Workflow:
  1. Fetch WikiMedia Most Viewed Articles for 6 languages (EN, FR, DE, ES, IT, PT)
  2. Merge results across languages (union of names)
  3. Filter eligibility:
     a) Wikidata P31 = Q5 (human)
     b) Wikipedia pages in >= 2 languages
     c) Average daily views (sum 6 langs) > 1000 over 7 days
     d) Anti-faits-divers: exclude if description contains blacklisted words
     e) Anti-acronym: minimum 2 words, no digits, no ALL-CAPS words > 1 letter
  4. Infer category from Wikipedia short description (keyword mapping)
  5. Write eligible candidates to candidate_queue collection

Source API: WikiMedia REST API (no API key required)
"""

import asyncio
import httpx
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from unidecode import unidecode

logger = logging.getLogger("candidate_detection")

USER_AGENT = "Popularoo/1.0 (contact@popularoo.com)"
WIKI_LANGUAGES = ["en", "fr", "de", "es", "it", "pt"]

# ── Eligibility thresholds ──
MIN_LANGUAGES = 2         # Must have Wikipedia pages in at least 2 languages
MIN_DAILY_VIEWS_7D = 10000 # Sum of 7-day avg daily views across 6 langs must be > 10000
TOP_N_PER_LANG = 100      # Look at top 100 per language per day

# ── Anti-faits-divers blacklist (English descriptions) ──
BLACKLISTED_DESCRIPTION_WORDS = {
    "victim", "suspect", "accused", "killed", "murderer", "criminal",
    "missing person", "controversy", "scandal", "shooting", "attack",
    "massacre", "terrorist", "homicide", "rape", "assault", "kidnap",
    "death of", "suicide",
}

# ── Category inference from Wikipedia short description ──
CATEGORY_KEYWORDS = {
    "politics": [
        "politician", "president", "prime minister", "senator", "governor",
        "minister", "political", "diplomat", "chancellor", "mayor",
        "congressman", "congresswoman", "head of state", "king", "queen",
        "prince", "princess", "monarch", "royal", "pope", "pontiff",
    ],
    "sport": [
        "footballer", "soccer", "basketball", "tennis", "athlete", "swimmer",
        "runner", "boxer", "wrestler", "golfer", "cricket", "rugby",
        "racing driver", "formula one", "f1", "olympic", "skier", "cyclist",
        "martial art", "mma", "ufc", "baseball", "hockey", "gymnast",
        "volleyball", "surfer", "skater", "sprinter",
    ],
    "culture": [
        "actor", "actress", "singer", "musician", "rapper", "songwriter",
        "filmmaker", "director", "producer", "writer", "author", "poet",
        "composer", "comedian", "entertainer", "model", "dancer",
        "television", "tv host", "presenter", "artist", "painter",
        "sculptor", "photographer", "designer", "fashion",
    ],
    "business": [
        "entrepreneur", "business", "ceo", "founder", "investor",
        "billionaire", "executive", "industrialist", "magnate", "tycoon",
        "philanthropist", "venture capitalist",
    ],
    "influencer": [
        "youtuber", "streamer", "tiktoker", "influencer", "content creator",
        "social media", "internet personality", "vlogger", "blogger",
        "twitch", "podcaster",
    ],
}


# ==================== WIKIMEDIA MOST VIEWED ====================

async def fetch_most_viewed_articles(
    lang: str,
    date: datetime,
    client: httpx.AsyncClient,
) -> List[Dict]:
    """
    Fetch top viewed articles for a given Wikipedia language and date.
    Returns list of {"article": "Name", "views": 123456}.
    """
    year = date.strftime("%Y")
    month = date.strftime("%m")
    day = date.strftime("%d")

    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        f"{lang}.wikipedia/all-access/{year}/{month}/{day}"
    )

    try:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"WikiMedia {lang} {date.strftime('%Y-%m-%d')}: HTTP {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("items", [{}])
        articles = items[0].get("articles", []) if items else []

        # Filter out special pages and very short names
        results = []
        for a in articles[:TOP_N_PER_LANG]:
            title = a.get("article", "")
            views = a.get("views", 0)

            # Skip Wikipedia internal pages
            if title.startswith(("Special:", "Main_Page", "Wikipedia:", "Portal:",
                                 "File:", "Template:", "Category:", "Help:",
                                 "Talk:", "User:", "Module:", "MediaWiki:")):
                continue

            # Convert underscores to spaces
            name = title.replace("_", " ")
            results.append({"article": name, "views": views, "lang": lang})

        return results
    except Exception as e:
        logger.warning(f"WikiMedia fetch error {lang} {date.strftime('%Y-%m-%d')}: {e}")
        return []


async def fetch_most_viewed_7days(
    lang: str,
    client: httpx.AsyncClient,
) -> Dict[str, float]:
    """
    Fetch average daily views over 7 days for a language.
    Returns {article_name: avg_daily_views}.
    """
    now = datetime.now(timezone.utc)
    totals: Dict[str, int] = {}
    days_ok = 0

    for i in range(1, 8):  # yesterday to 7 days ago
        date = now - timedelta(days=i)
        articles = await fetch_most_viewed_articles(lang, date, client)
        if articles:
            days_ok += 1
            for a in articles:
                name = a["article"]
                totals[name] = totals.get(name, 0) + a["views"]
        await asyncio.sleep(0.15)  # Rate limiting

    if days_ok == 0:
        return {}

    # Average daily views
    return {name: total / days_ok for name, total in totals.items()}


# ==================== WIKIDATA CHECKS ====================

async def check_is_human_alive(name: str, client: httpx.AsyncClient) -> Tuple[bool, bool, Optional[str], Optional[str]]:
    """
    Check if a name corresponds to a living human via Wikidata P31 + P570.
    Returns (is_human, is_deceased, wikidata_id, description).
    - is_human: True if P31 = Q5
    - is_deceased: True if P570 (date of death) exists
    """
    try:
        # Search Wikidata
        params = {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "type": "item",
            "limit": 3,
            "format": "json",
        }
        resp = await client.get(
            "https://www.wikidata.org/w/api.php",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return False, False, None, None

        data = resp.json()
        results = data.get("search", [])

        for result in results:
            entity_id = result.get("id")
            description = result.get("description", "")

            # Check P31 (instance of: human)
            claims_params = {
                "action": "wbgetclaims",
                "entity": entity_id,
                "property": "P31",
                "format": "json",
            }
            claims_resp = await client.get(
                "https://www.wikidata.org/w/api.php",
                params=claims_params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            if claims_resp.status_code != 200:
                continue

            claims_data = claims_resp.json()
            p31_claims = claims_data.get("claims", {}).get("P31", [])

            is_human = False
            for claim in p31_claims:
                val = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if val.get("id") == "Q5":  # Q5 = human
                    is_human = True
                    break

            if not is_human:
                continue

            # Check P570 (date of death) — same entity, one extra API call
            p570_params = {
                "action": "wbgetclaims",
                "entity": entity_id,
                "property": "P570",
                "format": "json",
            }
            p570_resp = await client.get(
                "https://www.wikidata.org/w/api.php",
                params=p570_params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            is_deceased = False
            if p570_resp.status_code == 200:
                p570_data = p570_resp.json()
                p570_claims = p570_data.get("claims", {}).get("P570", [])
                if p570_claims:
                    is_deceased = True

            return True, is_deceased, entity_id, description

        return False, False, None, None
    except Exception as e:
        logger.debug(f"Wikidata check failed for '{name}': {e}")
        return False, False, None, None


async def check_multi_lang_pages(name: str, client: httpx.AsyncClient) -> List[str]:
    """
    Check which Wikipedia languages have a page for this person.
    Returns list of language codes.
    """
    langs_found = []
    title = name.replace(" ", "_")

    for lang in WIKI_LANGUAGES:
        try:
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            resp = await client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=8,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                langs_found.append(lang)
            await asyncio.sleep(0.1)
        except Exception:
            pass

    return langs_found


async def get_wikipedia_pageviews(name: str, lang: str, client: httpx.AsyncClient) -> int:
    """
    Get average daily pageviews for a Wikipedia article over the last 30 days.
    Returns 0 on failure.
    """
    title = name.replace(" ", "_")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia.org/all-access/all-agents/{title}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    try:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            total = sum(item.get("views", 0) for item in items)
            return total // max(len(items), 1)  # avg daily
        return 0
    except Exception:
        return 0


def compute_celebrity_confidence(
    is_human: bool,
    is_deceased: bool,
    wikidata_id: Optional[str],
    langs: List[str],
    pageviews_fr: int = 0,
    pageviews_en: int = 0,
) -> int:
    """
    Correction B (Vague 2): Confidence scoring for celebrity validation.
    Replaces the rigid `len(langs) < 2` check.

    Score components:
      - FR Wikipedia exists: +30
      - EN Wikipedia exists: +25
      - Wikidata P31=Q5 confirmed: +20
      - Not deceased: +10
      - FR pageviews > 1000: +15 (> 200: +8)
      - EN pageviews > 500: +10 (> 100: +5)
      - 3+ languages: +20

    Thresholds:
      >= 65: immediate creation
      30-64: polite refusal ("not enough visibility for now")
      < 30: refusal ("not recognized")
    """
    score = 0
    if "fr" in langs:
        score += 30
    if "en" in langs:
        score += 25
    if is_human and wikidata_id:
        score += 20
    if not is_deceased:
        score += 10
    if pageviews_fr > 1000:
        score += 15
    elif pageviews_fr > 200:
        score += 8
    if pageviews_en > 500:
        score += 10
    elif pageviews_en > 100:
        score += 5
    if len(langs) >= 3:
        score += 20
    return min(score, 100)


# ==================== ELIGIBILITY FILTERS ====================

def passes_name_filter(name: str) -> bool:
    """
    Anti-acronym/object filter:
    - Minimum 2 words
    - No digits
    - No ALL-CAPS words longer than 1 letter
    """
    words = name.strip().split()
    if len(words) < 2:
        return False
    if any(char.isdigit() for char in name):
        return False
    for word in words:
        if len(word) > 1 and word == word.upper() and word.isalpha():
            return False
    return True


def passes_description_filter(description: str) -> bool:
    """
    Anti-faits-divers filter:
    Check if description contains any blacklisted words.
    """
    if not description:
        return True  # No description = let it through (Wikidata may lack one)
    desc_lower = description.lower()
    for word in BLACKLISTED_DESCRIPTION_WORDS:
        if word in desc_lower:
            return False
    return True


def infer_category(description: str) -> Tuple[str, str]:
    """
    Infer category from Wikipedia/Wikidata short description.
    Returns (category, confidence).
    confidence: "high" if 1 clear match, "medium" if multiple, "low" if none.
    """
    if not description:
        return "other", "low"

    desc_lower = description.lower()
    matches = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                matches.append(category)
                break  # One match per category is enough

    if len(matches) == 1:
        return matches[0], "high"
    elif len(matches) > 1:
        return matches[0], "medium"  # First match wins
    else:
        return "other", "low"


# ==================== SINGLE-NAME VALIDATION (Vague 4) ====================

async def validate_single_name(name: str) -> dict:
    """
    Validate a single celebrity name against Wikipedia / Wikidata.

    Vague 4: factorises the validation sequence
    ``is_human → is_deceased → confidence_score`` (followed by category
    inference + external score) that used to be duplicated across the
    now-removed ``/api/create-from-search`` endpoint and the
    ``_background_create_from_search`` background task in ``server.py``.

    This helper is **side-effect free**: it only performs read-only HTTP
    calls to Wikipedia / Wikidata / WikiMedia plus pure computations. It
    never reads from nor writes to the database — callers are responsible
    for any persistence and for DB-relative score normalisation.

    Pipeline:
      1. Wikidata P31 (instance of: human) + P570 (date of death) lookup.
      2. Reject if not a human (covers disambiguation pages, fictional
         characters, organisations, unknown names…), or if deceased.
      3. Collect the set of Wikipedia language pages + FR/EN pageviews.
      4. Compute the celebrity confidence score (0-100).
      5. Reject if confidence < 65 (see thresholds below).
      6. Infer the category and compute the external popularity score.

    Confidence thresholds (mirrors the removed endpoint logic):
      * ``>= 65`` : valid, name accepted.
      * ``30-64`` : rejected — ``low_confidence`` ("not enough visibility").
      * ``< 30``  : rejected — ``not_recognized`` ("this person is not recognised").

    Args:
        name: The raw celebrity name to validate. The caller is expected to
            have trimmed it already.

    Returns:
        A ``dict`` that ALWAYS contains, at minimum, the following keys:
          * ``is_human`` (bool): True if Wikidata P31 = Q5.
          * ``is_deceased`` (bool): True if Wikidata P570 (date of death) exists.
          * ``confidence`` (int): celebrity confidence score, 0-100.
          * ``wiki_langs`` (List[str]): Wikipedia language codes with a page.
          * ``wiki_score_norm`` (float): normalised Wikipedia score, 0-100
            (self-normalised here — see note below).
          * ``popularity_external_score`` (float): combined external score, 0-100.
          * ``error_code`` (Optional[str]): ``None`` when valid, otherwise one
            of ``wikipedia_not_found``, ``deceased``, ``not_recognized``,
            ``low_confidence``, ``wikipedia_check_failed``.
          * ``error_message`` (Optional[str]): human-readable French message,
            ``None`` when valid.
        Plus extra context fields useful to callers: ``valid`` (bool),
        ``name``, ``wikidata_id``, ``description``, ``category``,
        ``category_confidence``, ``pageviews_fr``, ``pageviews_en``,
        ``wiki_score_brut``.

    Note:
        ``wiki_score_norm`` / ``popularity_external_score`` are computed with
        ``max_wiki_in_db=None``, i.e. the score is self-normalised against the
        person's own raw Wikipedia score. Callers that need normalisation
        relative to the DB population must recompute with their own
        ``max_wiki_in_db``.
    """
    # Default result — every key the contract promises is always present,
    # whatever branch we exit through.
    result = {
        "valid": False,
        "name": name,
        "is_human": False,
        "is_deceased": False,
        "confidence": 0,
        "wiki_langs": [],
        "wiki_score_norm": 0.0,
        "popularity_external_score": 0.0,
        "wiki_score_brut": 0.0,
        "pageviews_fr": 0,
        "pageviews_en": 0,
        "wikidata_id": None,
        "description": None,
        "category": "other",
        "category_confidence": "low",
        "error_code": None,
        "error_message": None,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ── Step 1: Wikidata P31 (human) + P570 (deceased) ──
            is_human, is_deceased, wikidata_id, description = await check_is_human_alive(name, client)
            result["is_human"] = is_human
            result["is_deceased"] = is_deceased
            result["wikidata_id"] = wikidata_id
            result["description"] = description

            # ── Step 2: Reject non-humans (disambiguation pages, fictional
            #    characters, organisations, unknown names…) ──
            if not is_human:
                result["error_code"] = "wikipedia_not_found"
                result["error_message"] = "Cette personnalité est introuvable sur Wikipédia."
                return result

            # ── Step 2b: Reject deceased people ──
            if is_deceased:
                result["error_code"] = "deceased"
                result["error_message"] = "Cette personnalité est décédée."
                return result

            # ── Step 3: Wikipedia language pages + FR/EN pageviews ──
            langs = await check_multi_lang_pages(name, client)
            pageviews_fr = await get_wikipedia_pageviews(name, "fr", client)
            pageviews_en = await get_wikipedia_pageviews(name, "en", client)
            result["wiki_langs"] = langs
            result["pageviews_fr"] = pageviews_fr
            result["pageviews_en"] = pageviews_en

            # ── Step 4: Celebrity confidence score (0-100) ──
            confidence = compute_celebrity_confidence(
                is_human=is_human,
                is_deceased=is_deceased,
                wikidata_id=wikidata_id,
                langs=langs,
                pageviews_fr=pageviews_fr,
                pageviews_en=pageviews_en,
            )
            result["confidence"] = confidence

            # ── Step 5: Apply confidence thresholds ──
            if confidence < 30:
                result["error_code"] = "not_recognized"
                result["error_message"] = "Cette personnalité n'est pas reconnue."
                return result
            if confidence < 65:
                result["error_code"] = "low_confidence"
                result["error_message"] = "Cette personnalité n'a pas assez de visibilité pour le moment."
                return result

        # ── Step 6: Category inference (pure, from the Wikidata description) ──
        category, category_confidence = infer_category(description or "")
        result["category"] = category
        result["category_confidence"] = category_confidence

        # ── Step 7: External popularity score (Wikipedia pageviews based) ──
        #    No DB access here: max_wiki_in_db is left to None, so the score is
        #    self-normalised. A non-fatal failure here keeps the name valid.
        try:
            from external_scores import compute_external_score_for_person
            ext_result = await compute_external_score_for_person(name, max_wiki_in_db=None)
            result["popularity_external_score"] = ext_result.get("popularity_external_score", 0.0)
            result["wiki_score_norm"] = ext_result.get("wiki_score_norm", 0.0)
            result["wiki_score_brut"] = ext_result.get("wiki_score_brut", 0.0)
        except Exception as e:
            logger.warning(f"[validate_single_name] external score failed for '{name}': {e}")

        # All guards passed.
        result["valid"] = True
        return result

    except Exception as e:
        logger.error(f"[validate_single_name] validation failed for '{name}': {e}")
        result["error_code"] = "wikipedia_check_failed"
        result["error_message"] = str(e)
        return result


# ==================== MAIN DETECTION PIPELINE ====================

async def detect_candidates(db, target_date: Optional[datetime] = None) -> Dict:
    """
    Main pipeline: detect new celebrity candidates from Wikipedia Most Viewed.

    Steps:
      1. Fetch Most Viewed for 6 languages (7-day average)
      2. Merge across languages
      3. Filter out names already in DB (persons collection)
      4. Filter out names already in candidate_queue
      5. Apply eligibility checks (human, multi-lang, views, name, description)
      6. Write eligible candidates to candidate_queue

    Returns execution summary.
    """
    import time as _time
    start_time = _time.time()
    now = datetime.now(timezone.utc)

    logger.info(f"🔍 [Candidates] Detection started at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    async with httpx.AsyncClient(timeout=15) as client:

        # ── Step 1: Fetch Most Viewed across 6 languages ──
        all_views: Dict[str, Dict[str, float]] = {}  # name -> {lang: avg_views}
        raw_candidates_count = 0

        for lang in WIKI_LANGUAGES:
            lang_views = await fetch_most_viewed_7days(lang, client)
            for name, avg_views in lang_views.items():
                if name not in all_views:
                    all_views[name] = {}
                all_views[name][lang] = avg_views
            raw_candidates_count += len(lang_views)
            logger.info(f"🔍 [Candidates] {lang}: {len(lang_views)} articles fetched")

        # ── Step 2: Compute total views and language count ──
        merged: List[Dict] = []
        for name, lang_views in all_views.items():
            total_views = sum(lang_views.values())
            langs = list(lang_views.keys())
            merged.append({
                "name": name,
                "total_avg_daily_views": total_views,
                "langs": langs,
                "lang_count": len(langs),
            })

        merged.sort(key=lambda x: x["total_avg_daily_views"], reverse=True)
        logger.info(f"🔍 [Candidates] {len(merged)} unique names across 6 languages")

        # ── Step 3: Filter out names already in DB ──
        existing_slugs = set()
        cursor = db.persons.find({}, {"slug": 1, "name": 1})
        async for doc in cursor:
            slug = doc.get("slug", "")
            if slug:
                existing_slugs.add(slug)
            # Also add normalized name
            name_norm = unidecode(doc.get("name", "")).lower().strip()
            existing_slugs.add(name_norm)

        # ── Step 4: Filter out names already in candidate_queue (pending) ──
        pending_slugs = set()
        pending_cursor = db.candidate_queue.find(
            {"status": "pending"},
            {"name_normalized": 1}
        )
        async for doc in pending_cursor:
            pending_slugs.add(doc.get("name_normalized", ""))

        # ── Step 5: Apply eligibility filters ──
        eligible = []
        checked_count = 0
        filtered_reasons = {
            "already_in_db": 0,
            "already_in_queue": 0,
            "name_filter": 0,
            "too_few_views": 0,
            "too_few_langs": 0,
            "not_human": 0,
            "deceased": 0,
            "description_filter": 0,
        }

        for candidate in merged:
            name = candidate["name"]
            name_norm = unidecode(name).lower().strip()
            name_slug = re.sub(r"[^a-z0-9\s-]", "", name_norm)
            name_slug = re.sub(r"[\s-]+", "-", name_slug).strip("-")

            # Quick filters first (no API calls)
            if name_slug in existing_slugs or name_norm in existing_slugs:
                filtered_reasons["already_in_db"] += 1
                continue

            if name_norm in pending_slugs:
                filtered_reasons["already_in_queue"] += 1
                continue

            if not passes_name_filter(name):
                filtered_reasons["name_filter"] += 1
                continue

            if candidate["total_avg_daily_views"] < MIN_DAILY_VIEWS_7D:
                filtered_reasons["too_few_views"] += 1
                continue

            if candidate["lang_count"] < MIN_LANGUAGES:
                filtered_reasons["too_few_langs"] += 1
                continue

            # Expensive API checks (rate limited)
            checked_count += 1
            if checked_count > 80:  # Cap at 80 API checks per run
                break

            is_human, is_deceased, wikidata_id, description = await check_is_human_alive(name, client)
            await asyncio.sleep(0.3)

            if not is_human:
                filtered_reasons["not_human"] += 1
                continue

            if is_deceased:
                filtered_reasons["deceased"] += 1
                logger.info(f"🔍 [Candidates] Filtered deceased: {name}")
                continue

            if not passes_description_filter(description or ""):
                filtered_reasons["description_filter"] += 1
                continue

            # Infer category
            category, confidence = infer_category(description or "")

            eligible.append({
                "name": name,
                "name_normalized": name_norm,
                "slug": name_slug,
                "category_suggested": category,
                "confidence": confidence,
                "wiki_score": round(candidate["total_avg_daily_views"], 0),
                "wiki_langs": candidate["langs"],
                "wiki_lang_count": candidate["lang_count"],
                "wiki_description": description or "",
                "wikidata_id": wikidata_id,
                "detected_at": now,
                "status": "pending",
            })

        # ── Step 6: Write to candidate_queue ──
        inserted_count = 0
        for c in eligible:
            # Double-check not already in queue (race condition guard)
            exists = await db.candidate_queue.find_one({
                "name_normalized": c["name_normalized"],
                "status": "pending",
            })
            if not exists:
                await db.candidate_queue.insert_one(c)
                inserted_count += 1

    elapsed = round(_time.time() - start_time, 1)

    summary = {
        "job": "daily_candidate_detection",
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration_seconds": elapsed,
        "raw_articles_fetched": raw_candidates_count,
        "unique_names_merged": len(merged),
        "api_checks_performed": checked_count,
        "eligible_candidates": len(eligible),
        "inserted_to_queue": inserted_count,
        "filtered_reasons": filtered_reasons,
        "candidates": [
            {"name": c["name"], "category": c["category_suggested"],
             "confidence": c["confidence"], "wiki_score": c["wiki_score"],
             "langs": c["wiki_lang_count"]}
            for c in eligible
        ],
    }

    logger.info(
        f"🔍 [Candidates] Detection complete in {elapsed}s — "
        f"{len(eligible)} eligible, {inserted_count} inserted, "
        f"filtered: {filtered_reasons}"
    )

    # Store last run summary
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$set": {"last_candidate_detection_run": summary}},
        upsert=True,
    )

    return summary
