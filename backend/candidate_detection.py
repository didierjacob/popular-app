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
# ⚠️ Synchronisé avec backend/server.py:6303 (CATEGORY_KEYWORD_MAP).
# Modifier les deux ensemble pour éviter divergence audit.
#
# Ordre d'évaluation (premier match gagne) :
#   politics → sport → culture → influencer → business
#
# Justification produit (validée Didier 2026-05) :
# Popularoo classe selon la PERCEPTION POPULAIRE dominante, pas selon la réalité
# entrepreneuriale. Une YouTubeuse devenue businesswoman (Kylie Jenner, Kim K, Zoella)
# reste "influencer" aux yeux du public. influencer est donc évalué AVANT business.
# Modifier cet ordre nécessite une validation produit.
#
# Note hybrides : les profils acteur/wrestler comme Dwayne Johnson tomberont en sport
# (cohérent avec leur description Wikipedia primaire "American actor and former
# professional wrestler"). Idem hybrides YouTuber/boxer (KSI, Logan Paul) → sport.
#
# Note tokens courts : tous les tokens ≤ 4 lettres ont été audités pour éviter les
# matches en sous-chaîne (ex: "king" matchait "working", "earl" matchait "early").
# Toujours préférer des n-grams explicites ("king of", "earl of") aux tokens nus.
CATEGORY_KEYWORDS = {
    "politics": [
        "politician", "president", "vice president", "prime minister",
        "deputy prime minister", "senator", "governor", "governor of",
        "minister", "secretary of state", "political", "political activist",
        "diplomat", "ambassador", "chancellor", "mayor", "premier of",
        "congressman", "congresswoman", "congressm", "representative",
        "member of parliament", "parliament", "mp ", "chairperson",
        "head of state", "head of government",
        "king of", "kings of", "king consort", "queen", "prince", "princess",
        "monarch", "royal",
        "emperor", "empress", "tsar", "sultan", "emir of", "emirate", "sheikh",
        "duke", "duchess", "earl of", "the earl", "earldom",
        "baron", "baroness", "archduke", "viceroy",
        "pope", "pontiff", "cardinal", "archbishop", "dalai lama", "ayatollah",
        "revolutionary", "first lady",
    ],
    "sport": [
        "footballer", "football player", "football manager", "football coach",
        "soccer", "soccer player", "basketball", "basketball player",
        "tennis", "tennis player", "rugby", "rugby player", "athlete",
        "athletics", "swimmer", "runner", "boxer", "wrestler", "wrestling",
        "golfer", "cricket", "racing", "racing driver", "motor racing",
        "motorsport", "formula one", "f1", "f1 driver", "olympic", "paralympic",
        "skier", "cyclist", "martial", "martial art", "mma fighter", "ufc",
        "baseball", "hockey", "gymnast", "volleyball", "handball", "surfer",
        "skater", "snowboarder", "sprinter", "head coach", "coach",
        "manager of", "national team", "fighter", "kickboxer", "judoka",
        "taekwondo", "karate", "fencer", "weightlifter", "rower",
        "darts", "snooker", "esports", "sportsperson", "sportsman",
        "sportswoman", "striker", "goalkeeper", "midfielder", "defender",
        "quarterback", "pitcher", "entraîneur", "sélectionneur",
    ],
    "culture": [
        "actor", "actress", "voice actor", "singer", "singer-songwriter",
        "musician", "instrumentalist", "rapper", "songwriter", "lyricist",
        "filmmaker", "director", "producer", "record producer", "screenwriter",
        "writer", "author", "novelist", "playwright", "poet", "composer",
        "comedian", "stand-up", "entertainer", "model", "dancer",
        "choreographer", "television", "tv host", "tv presenter",
        "television presenter", "talk show host", "radio host", "presenter",
        "news anchor", "journalist", "artist", "painter",
        "sculptor", "photographer", "designer", "fashion", "fashion designer",
        "theatre", "theater", "opera", "magician", "chef", "drag queen",
        "dj ", "dj and", "dj producer",
        "cartoonist", "illustrator", "animator", "guitarist", "drummer",
        "pianist", "violinist", "cellist", "saxophonist", "bassist",
        "conductor", "record label", "youtube creator", "k-pop", "boy group",
        "girl group", "rock band", "pop star", "hip hop",
    ],
    "influencer": [
        "youtuber", "youtube personality", "youtube channel", "streamer",
        "twitch streamer", "kick streamer", "tiktoker", "tiktok",
        "instagram", "instagrammer", "influencer", "content creator",
        "social media", "media personality", "social media personality",
        "internet personality", "online personality", "web personality",
        "vlogger", "blogger", "twitch", "podcaster",
    ],
    "business": [
        "entrepreneur", "business", "businessman", "businesswoman",
        "businessperson", "ceo", "cfo", "cto of", "chief technology officer",
        "chief executive", "chief financial", "chief operating",
        "chairman", "chairwoman",
        "founder", "co-founder", "cofounder", "investor", "billionaire",
        "executive", "industrialist", "magnate", "tycoon", "philanthropist",
        "venture capitalist", "venture capital", "hedge fund",
        "banker", "financier", "real estate developer",
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


# ==================== VAGUE 4 — SOUS-TÂCHE 5: User Celebrity Request Enqueue ====================

# Delay before a user-submitted name becomes eligible for processing by
# process_user_submissions_job (heavy Wikipedia/Wikidata validation at T+24h).
USER_SUBMISSION_PROCESS_DELAY = timedelta(hours=24)

# Implicit "like" attached to a user search — decided in Q3: searching for a
# celebrity counts as an implicit like. The job applies this vote at T+24h.
USER_SUBMISSION_PENDING_VOTE_VALUE = 1


def slugify_name(name: str) -> str:
    """Slug for dedup. Mirrors server.slugify so persons-collection lookups match."""
    # Normalize accented chars first so "Léa" → "lea" instead of being stripped to "la"
    s = unidecode(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


async def process_celebrity_request(db, name: str, device_id: str) -> dict:
    """
    Vague 4, sous-tâche 5 — Core logic for POST /api/submit-celebrity-request.

    Normalizes the submitted name, runs the 4 dedup/blocklist checks, and (if
    none match) enqueues a 'user_search' entry in candidate_queue. The heavy
    validation (Wikipedia, Wikidata, scoring) is NOT done here — it runs later
    in process_user_submissions_job via validate_single_name. The enqueue must
    stay fast (< 200ms), so this only touches the local DB.

    Returns a dict with a 'status' key:
      - already_exists   + person_id      → slug already in persons
      - already_pending  + process_after  → same slug already queued (user_search)
      - rejected                          → slug in seed_blocklist (caller masks
                                            this as 'queued' to the user)
      - queued           + process_after  → new entry inserted in candidate_queue

    Raises ValueError on empty name / device_id (caller maps to HTTP 400).
    """
    # ── Normalisation: trim + collapse whitespace + clean capitalization ──
    clean_name = re.sub(r"\s+", " ", (name or "").strip()).title()
    clean_device_id = (device_id or "").strip()
    if not clean_name:
        raise ValueError("name is required")
    if not clean_device_id:
        raise ValueError("device_id is required")

    slug = slugify_name(clean_name)
    name_norm = unidecode(clean_name).lower().strip()
    now = datetime.now(timezone.utc)

    # ── Check 1: strict duplicate against real persons ──
    existing_person = await db.persons.find_one({"slug": slug})
    if existing_person:
        return {"status": "already_exists", "person_id": str(existing_person["_id"])}

    # ── Check 2: duplicate against a still-pending user_search entry ──
    existing_pending = await db.candidate_queue.find_one({
        "source": "user_search",
        "slug": slug,
        "status": "pending",
    })
    if existing_pending:
        original = existing_pending.get("process_after")
        return {
            "status": "already_pending",
            "process_after": original.isoformat() if hasattr(original, "isoformat") else original,
        }

    # ── Check 3: blocklist — silent rejection (caller still shows the 24h wait) ──
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    blocked_slugs = set(settings.get("seed_blocklist", []))
    if slug in blocked_slugs:
        return {"status": "rejected"}

    # ── Enqueue: no synchronous validation, just the normalized name ──
    process_after = now + USER_SUBMISSION_PROCESS_DELAY
    candidate_doc = {
        # Préliminaires habituels
        "name": clean_name,
        "name_normalized": name_norm,
        "slug": slug,
        # Champs user_search (plan Vague 4)
        "source": "user_search",
        "requested_by_device_id": clean_device_id,
        "requested_at": now,
        "process_after": process_after,
        "pending_vote_value": USER_SUBMISSION_PENDING_VOTE_VALUE,
        "status": "pending",
    }
    await db.candidate_queue.insert_one(candidate_doc)
    logger.info(f"📥 [UserRequest] Enqueued '{clean_name}' (device={clean_device_id[:8]}…), process_after={process_after.isoformat()}")
    return {"status": "queued", "process_after": process_after.isoformat()}


# ==================== VAGUE 4 — SOUS-TÂCHE 6: Approve a user_search candidate ====================

# Q1 — Initial Popularoo Index for a deferred user_search creation.
# initial_pi = clamp(25..40, 25 + ext_score * 0.15), ext_score being the
# already log-normalised external popularity score (0-100).
USER_SEARCH_PI_MIN = 25.0
USER_SEARCH_PI_MAX = 40.0
USER_SEARCH_PI_SLOPE = 0.15

# Q4 — chantier « cœur honnête » (2026-07) : PLUS AUCUN vote simulé.
# Un nouvel entrant démarre à 0 vote réel ; seul le +1 implicite (Q3) peut
# s'ajouter si la recherche valait un vote. Les compteurs affichés reflètent
# désormais la seule réalité. `initial_pi` (25-40) reste la valeur de départ de
# l'indice — inchangée par ce retrait, car la branche 2 nette déjà les seeds.
USER_SEARCH_LIKES_RANGE = (0, 0)
USER_SEARCH_DISLIKES_RANGE = (0, 0)


async def approve_user_search_candidate(db, candidate: dict, validate_fn=None) -> dict:
    """
    Vague 4, sous-tâche 6 — Approve a 'user_search' candidate from candidate_queue.

    This is the third branch of the admin approve_candidate flow (the first two
    handle auto_detection / manual_proposal). It is called by
    admin_approve_candidate in server.py when ``candidate["source"] == "user_search"``.

    Unlike the seed branches, a user_search candidate sat 24h in the queue, so:
      1. It is re-validated *fresh* via validate_single_name (sous-tâche 4) —
         e.g. the person may have died in the meantime.
      2. If invalid → candidate_queue status 'rejected' + validation_error, NO
         person is created.
      3. If a profile with the same slug appeared meanwhile (admin manual path,
         etc.) → candidate_queue status 'duplicate', NO person is created.
      4. Otherwise the person is created with the deferred-V4 formulas:
         - initial PI         : Q1 clamp(25..40, 25 + ext_score*0.15)
         - simulated votes    : chantier « cœur honnête » → 0 (aucun faux vote)
         - implicit like      : Q3 +1 like if candidate.pending_vote_value == 1
         and the contributor (requested_by_device_id) is credited.

    Args:
        db: the Mongo-like database handle (real or fake).
        candidate: the full candidate_queue document (must have ``_id``,
            ``name``, ``slug``, ``source == "user_search"``; usually also
            ``name_normalized``, ``requested_by_device_id``, ``pending_vote_value``).
        validate_fn: injection point for tests; defaults to validate_single_name.

    Returns:
        dict with a ``status`` key:
          - ``rejected``  + error_code           → fresh validation failed
          - ``duplicate`` + person_id            → slug already in persons
          - ``approved``  + person_id, initial_pi, category, likes, dislikes,
            total_votes                          → person created
    """
    import random

    if validate_fn is None:
        validate_fn = validate_single_name

    oid = candidate["_id"]
    name = candidate["name"]
    slug = candidate.get("slug") or slugify_name(name)
    now = datetime.now(timezone.utc)

    # ── Step 1: fresh re-validation (24h later — death, disambiguation, …) ──
    result = await validate_fn(name)
    if not result.get("valid"):
        error_code = result.get("error_code") or "unknown"
        await db.candidate_queue.update_one(
            {"_id": oid},
            {"$set": {
                "status": "rejected",
                "validated_at": now,
                "validation_error": error_code,
            }},
        )
        logger.info(f"🚫 [UserSearch] Rejected '{name}' on approve: {error_code}")
        return {"status": "rejected", "name": name, "error_code": error_code}

    # ── Step 2: dedup — a profile may have been created by another path ──
    existing = await db.persons.find_one({"slug": slug})
    if existing:
        await db.candidate_queue.update_one(
            {"_id": oid},
            {"$set": {
                "status": "duplicate",
                "validated_at": now,
                "person_id": str(existing["_id"]),
            }},
        )
        logger.info(f"♻️  [UserSearch] '{name}' already exists (slug={slug}) → duplicate")
        return {"status": "duplicate", "name": name, "person_id": str(existing["_id"])}

    # ── Step 2b: anti-ghost blocklist — never re-create a deleted personality ──
    bl_settings = await db.app_settings.find_one({"_id": "global"}) or {}
    name_norm = candidate.get("name_normalized") or unidecode(name).lower().strip()
    wikidata_id = result.get("wikidata_id")
    if (
        name_norm in set(bl_settings.get("seed_blocklist_names", []))
        or slug in set(bl_settings.get("seed_blocklist", []))
        or (wikidata_id and wikidata_id in set(bl_settings.get("seed_blocklist_wikidata", [])))
    ):
        await db.candidate_queue.update_one(
            {"_id": oid},
            {"$set": {"status": "blocklisted", "validated_at": now}},
        )
        logger.info(f"🚫 [Anti-ghost] UserSearch approve blocked for blocklisted '{name}'")
        return {"status": "rejected", "name": name, "error_code": "blocklisted"}

    # ── Step 3: initial Popularoo Index (Q1) ──
    ext_score = result["popularity_external_score"]
    initial_pi = max(
        USER_SEARCH_PI_MIN,
        min(USER_SEARCH_PI_MAX, USER_SEARCH_PI_MIN + ext_score * USER_SEARCH_PI_SLOPE),
    )

    # ── Step 4: aucun vote simulé (chantier « cœur honnête », Q4 révisé) ──
    # Ranges à (0, 0) → likes_sim = dislikes_sim = 0. On garde randint pour ne
    # pas casser la forme du code si les ranges venaient à être rouverts.
    likes_sim = random.randint(*USER_SEARCH_LIKES_RANGE)
    dislikes_sim = random.randint(*USER_SEARCH_DISLIKES_RANGE)

    # ── Step 5: implicit like — searching a name counts as a +1 (Q3) ──
    pending_vote = candidate.get("pending_vote_value", 0)
    if pending_vote == 1:
        likes_final = likes_sim + 1
        dislikes_final = dislikes_sim
    else:
        likes_final = likes_sim
        dislikes_final = dislikes_sim
    total_votes = likes_final + dislikes_final

    # ── Step 6: create the persons document ──
    person_doc = {
        "name": name,
        "name_normalized": candidate.get("name_normalized"),
        "slug": slug,
        "source": "user_search",
        "created_via": "deferred_v4",
        "visible_in_rankings": True,
        "approved": True,
        "suspended": False,
        "category": result["category"],
        "score": initial_pi,
        "popularoo_index": initial_pi,
        "initial_pi": initial_pi,  # frozen reference value (sous-tâche 8)
        "popularity_external_score": ext_score,
        "wiki_score_norm": result["wiki_score_norm"],
        "wiki_score_brut": result["wiki_score_brut"],
        "wiki_langs": result["wiki_langs"],
        "wikidata_id": result["wikidata_id"],
        "likes": likes_final,
        "dislikes": dislikes_final,
        "superlikes": 0,
        "total_votes": total_votes,
        "seed_votes_likes": likes_sim,      # without the implicit +1 (distinguishable later)
        "seed_votes_dislikes": dislikes_sim,
        "active_strikes": 0,
        "created_at": now,
        "last_updated": now,
        "last_external_update": now,
        # Horloge d'érosion par inactivité (branche 2) : armée à la création.
        # Réarmée à chaque VRAI vote positif (server.vote_person, new_val == 1).
        "last_real_vote_at": now,
        "created_by_device_id": candidate.get("requested_by_device_id"),
        # User-submitted profile + implicit +1 like (Q3) ⇒ surface an up arrow at creation.
        "vote_momentum": "up",
    }
    insert_res = await db.persons.insert_one(person_doc)
    person_id = insert_res.inserted_id

    # ── Step 7: initial tick (coherence with the other profiles) ──
    await db.person_ticks.insert_one({
        "person_id": person_id,
        "score": initial_pi,
        "total_votes": total_votes,
        "created_at": now,
    })

    # ── Step 8: contributor tracking — credit the device that submitted ──
    device_id = candidate.get("requested_by_device_id")
    if device_id:
        await db.user_settings.update_one(
            {"device_id": device_id},
            {
                "$addToSet": {"contributed_person_ids": str(person_id)},
                "$setOnInsert": {"created_at": now},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    # ── Step 9: mark the candidate approved ──
    await db.candidate_queue.update_one(
        {"_id": oid},
        {"$set": {
            "status": "approved",
            "validated_at": now,
            "person_id": str(person_id),
            "initial_pi": initial_pi,
            "validation_confidence": result["confidence"],
        }},
    )

    logger.info(
        f"✅ [UserSearch] Created '{name}' PI={initial_pi:.2f} "
        f"votes={likes_final}+{dislikes_final} (device={str(device_id)[:8]}…)"
    )
    return {
        "status": "approved",
        "name": name,
        "person_id": str(person_id),
        "initial_pi": initial_pi,
        "category": result["category"],
        "likes": likes_final,
        "dislikes": dislikes_final,
        "total_votes": total_votes,
    }


# ============ VAGUE 4 — SOUS-TÂCHE 9: Migrate legacy user_search profiles ============


async def migrate_user_search_v4(db) -> dict:
    """
    Vague 4, sous-tâche 9 — One-time migration of legacy user_search profiles
    to the deferred-V4 formula.

    Several profiles already exist with source "user_search" /
    "user_search_confirmed", created by the pre-Vague-4 paths with a stale PI
    (~10-15) and 0 real votes. Without migration they look visually dead next
    to the new deferred_v4 profiles (PI 25-40 + ~40 simulated votes). This
    helper recomputes the V4 initial PI and grafts ~40 simulated votes onto
    them.

    Targets persons matching:
      - source in {"user_search", "user_search_confirmed"}
      - approved == True

    For each match:
      - Defensive guard: category == "outsider" → skipped (Outsiders keep their
        own scoring), counted in ``skipped_outsider``.
      - Idempotence: a non-null ``migrated_v4_at`` → skipped, counted in
        ``skipped_already_migrated``. The endpoint can be re-run safely.
      - Otherwise:
          initial_pi   = clamp(25..40, 25 + ext_score * 0.15)
          likes_sim    = randint(26, 30)
          dislikes_sim = randint(10, 14)
        Real votes are preserved: any existing likes/dislikes are kept and the
        simulated votes are *added* on top.

    Args:
        db: the Mongo-like database handle (real motor db or test fake).

    Returns:
        dict matching the endpoint JSON schema (without the ``success`` key,
        which the endpoint adds): total_eligible, migrated,
        skipped_already_migrated, skipped_outsider, errors, migrated_sample
        (10 first migrated profiles), errors_detail.
    """
    import random

    now = datetime.now(timezone.utc)
    query_filter = {
        "source": {"$in": ["user_search", "user_search_confirmed"]},
        "approved": True,
    }

    total_eligible = 0
    migrated = 0
    skipped_already_migrated = 0
    skipped_outsider = 0
    errors = 0
    migrated_sample: list = []
    errors_detail: list = []

    cursor = db.persons.find(query_filter)
    async for person in cursor:
        total_eligible += 1
        pid = person.get("_id")
        name = person.get("name", "???")
        try:
            # ── Defensive guard: never touch Outsiders ──
            if person.get("category") == "outsider":
                skipped_outsider += 1
                continue

            # ── Idempotence: already migrated → skip ──
            if person.get("migrated_v4_at"):
                skipped_already_migrated += 1
                continue

            # ── V4 formula ──
            ext_score = person.get("popularity_external_score") or 0
            initial_pi = max(25.0, min(40.0, 25.0 + ext_score * 0.15))

            likes_sim = random.randint(26, 30)
            dislikes_sim = random.randint(10, 14)

            # ── Preserve real existing votes, add simulated on top ──
            existing_likes = person.get("likes", 0) or 0
            existing_dislikes = person.get("dislikes", 0) or 0
            new_likes = existing_likes + likes_sim
            new_dislikes = existing_dislikes + dislikes_sim
            new_total = new_likes + new_dislikes

            old_pi = person.get("popularoo_index")

            await db.persons.update_one(
                {"_id": pid},
                {"$set": {
                    "score": initial_pi,
                    "popularoo_index": initial_pi,
                    "initial_pi": initial_pi,          # frozen reference value
                    "likes": new_likes,
                    "dislikes": new_dislikes,
                    "total_votes": new_total,
                    "seed_votes_likes": likes_sim,     # distinguishable later
                    "seed_votes_dislikes": dislikes_sim,
                    "migrated_v4_at": now,
                    "created_via": "deferred_v4_migrated",
                    "last_updated": now,
                }},
            )
            migrated += 1
            if len(migrated_sample) < 10:
                migrated_sample.append({
                    "name": name,
                    "old_pi": old_pi,
                    "new_pi": initial_pi,
                    "ext_score": float(ext_score),
                })
        except Exception as e:  # pragma: no cover - defensive
            errors += 1
            errors_detail.append({
                "name": name,
                "person_id": str(pid),
                "error": str(e),
            })
            logger.error(f"🚫 [MigrateV4] error on '{name}': {e}")

    logger.info(
        f"✅ [MigrateV4] eligible={total_eligible} migrated={migrated} "
        f"skipped_migrated={skipped_already_migrated} "
        f"skipped_outsider={skipped_outsider} errors={errors}"
    )

    return {
        "total_eligible": total_eligible,
        "migrated": migrated,
        "skipped_already_migrated": skipped_already_migrated,
        "skipped_outsider": skipped_outsider,
        "errors": errors,
        "migrated_sample": migrated_sample,
        "errors_detail": errors_detail,
    }


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

        # ── Step 4b: Load the anti-ghost blocklist (deleted personalities) ──
        # A deleted celebrity must never re-enter the queue. Primary key =
        # name_normalized; secondary = wikidata_id; legacy = slug.
        bl_settings = await db.app_settings.find_one({"_id": "global"}) or {}
        blocked_slugs = set(bl_settings.get("seed_blocklist", []))
        blocked_names = set(bl_settings.get("seed_blocklist_names", []))
        blocked_wikidata = set(bl_settings.get("seed_blocklist_wikidata", []))

        # ── Step 5: Apply eligibility filters ──
        eligible = []
        checked_count = 0
        filtered_reasons = {
            "already_in_db": 0,
            "already_in_queue": 0,
            "blocklisted": 0,
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

            # Anti-ghost (pre-API): skip deleted personalities by name/slug.
            if name_norm in blocked_names or name_slug in blocked_slugs:
                filtered_reasons["blocklisted"] += 1
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

            # Anti-ghost (post-API): a deleted celebrity keeps the same wikidata
            # QID even under a slightly different name spelling.
            if wikidata_id and wikidata_id in blocked_wikidata:
                filtered_reasons["blocklisted"] += 1
                logger.info(f"🚫 [Anti-ghost] Filtered blocklisted (wikidata={wikidata_id}): {name}")
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
