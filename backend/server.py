from fastapi import FastAPI, APIRouter, HTTPException, Header, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import logging
import bcrypt
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
import uuid
from datetime import datetime, timedelta
from bson import ObjectId
import re
import random
from collections import Counter
import asyncio
from unidecode import unidecode
from trends_service import trends_service
from scheduler import init_scheduler, start_scheduler, shutdown_scheduler, run_potd_rotation_job
from bull_run import bull_run_router, init_bull_run, bull_run_background_job
from share_system import (
    share_router, create_short_link, resolve_short_link,
    generate_rally_cry_image, get_share_messages,
    generate_rally_page_html, generate_user_page_html,
)
from popularoo_index import (
    load_config as load_index_config,
    quick_recalc_index, recalculate_all_indices,
    ensure_indexes as ensure_index_indexes,
    migrate_initial_index, get_strike_level,
    invalidate_config_cache,
)
from strikes import (
    check_and_trigger_strikes, get_active_strikes_detail,
    cleanup_expired_strikes, ensure_strike_indexes,
)
from daily_run_v2 import (
    get_suggested_targets, search_target, activate_daily_run,
    get_active_daily_run, get_daily_run_history, get_live_daily_runs,
    get_daily_run_status, check_victories,
    ensure_daily_run_indexes, determine_tier,
)


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# ── Rate Limiter for admin endpoints (5 attempts / 15 min / IP) ──
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# -------------------- Startup & Shutdown Events --------------------

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler and Popularoo Index on application startup"""
    logger.info("🚀 Starting Popularoo API...")
    
    # Connect email service to database for error logging
    email_service.set_db(db)
    logger.info("📧 Email service connected to DB for error logging")
    
    # Ensure admin_notifications collection has TTL index (auto-cleanup after 90 days)
    await db.admin_notifications.create_index(
        "timestamp", expireAfterSeconds=90 * 24 * 3600
    )
    
    # Ensure admin_audit_log collection has TTL index (auto-cleanup after 90 days)
    await db.admin_audit_log.create_index(
        "timestamp", expireAfterSeconds=90 * 24 * 3600
    )
    
    # Ensure Popularoo Index database indexes
    await ensure_index_indexes(db)
    
    # Ensure Strike indexes
    await ensure_strike_indexes(db)
    
    # Ensure Daily Run indexes
    await ensure_daily_run_indexes(db)
    
    # Seed algorithm config if not exists
    await load_index_config(db)
    
    # Initialize and start the scheduler
    init_scheduler(db, trends_service, email_service)
    start_scheduler()

    # Chantier C — prime the POTD immediately so the Home page doesn't wait
    # until the next XX:00 UTC tick to surface a featured profile. Fire-and-
    # forget: any failure logs internally and never blocks boot.
    asyncio.create_task(run_potd_rotation_job(db))

    logger.info("✅ Scheduler initialized and started")
    logger.info("📅 Daily Google Trends auto-ingestion DISABLED (Session 2 audit)")
    logger.info("📊 Popularoo Index recalculation scheduled every 15 minutes")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler gracefully"""
    logger.info("🛑 Shutting down Popularoo API...")
    shutdown_scheduler()
    logger.info("✅ Scheduler shut down successfully")


# -------------------- Utilities --------------------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


def slugify(name: str) -> str:
    # Normalize accented chars first so "Léa" → "lea" instead of being stripped to "la"
    s = unidecode(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    s = s.strip('-')
    return s


def now_utc() -> datetime:
    return datetime.utcnow()


# ==================== Anti-ghost blocklist (Lot 1) ====================
# A deleted *personality* (celebrity / auto-detected) must never silently
# re-appear via the Wikipedia detection job, seeds, imports or approvals.
# Storage = app_settings doc {"_id": "global"}:
#   - seed_blocklist           : list[slug]            (legacy, kept for retro-compat)
#   - seed_blocklist_names     : list[name_normalized] (PRIMARY key — accent-insensitive)
#   - seed_blocklist_wikidata  : list[wikidata QID]    (secondary key)
# NOTE: only personality creation paths consult this. Outsider / self-boost
# paths (boost_myself, admin_grant_booster, admin_create_demo_outsider) must
# NOT — a paying Outsider consents to their own name, they are not a revived
# celebrity.

def normalize_person_name(name: str) -> str:
    """Canonical, accent-insensitive blocklist key for a personality name.
    'Léa Seydoux' -> 'lea seydoux' (robust against the slugify accent bug)."""
    return unidecode(name or "").lower().strip()


async def is_person_blocklisted(name_normalized: str = "", wikidata_id: str = "", slug: str = "") -> bool:
    """True if a personality is on the anti-ghost blocklist.
    Match priority: name_normalized > wikidata_id > slug (legacy)."""
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    if name_normalized and name_normalized in set(settings.get("seed_blocklist_names", [])):
        return True
    if wikidata_id and wikidata_id in set(settings.get("seed_blocklist_wikidata", [])):
        return True
    if slug and slug in set(settings.get("seed_blocklist", [])):
        return True
    return False


async def add_person_to_blocklist(name: str = "", slug: str = "", wikidata_id: str = "") -> dict:
    """Register a deleted personality so it can never silently re-appear.
    Adds name_normalized (primary), slug (legacy) and wikidata_id (if present)."""
    name_norm = normalize_person_name(name)
    add: dict = {}
    if name_norm:
        add["seed_blocklist_names"] = name_norm
    if slug:
        add["seed_blocklist"] = slug
    if wikidata_id:
        add["seed_blocklist_wikidata"] = wikidata_id
    if add:
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$addToSet": add},
            upsert=True,
        )
    return {"name_normalized": name_norm, "slug": slug, "wikidata_id": wikidata_id}


def parse_window(window: str) -> timedelta:
    """Parse window string like '60m' or '24h' into timedelta"""
    m = re.match(r"^(\d+)([mhd])$", window)
    if not m:
        raise ValueError(f"Invalid window format: {window}")
    value, unit = int(m.group(1)), m.group(2)
    if unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    else:
        raise ValueError(f"Unsupported time unit: {unit}")


# -------------------- Seed Decay Configuration --------------------
# The decay starts 90 days after this date (configurable)
DECAY_START_DATE_STR = os.environ.get("DECAY_START_DATE", "2026-07-28")  # ~90 days from now
try:
    DECAY_START_DATE = datetime.strptime(DECAY_START_DATE_STR, "%Y-%m-%d")
except ValueError:
    DECAY_START_DATE = datetime(2026, 7, 28)


def compute_seed_weight():
    """
    Progressive seed decay: seed_weight goes from 1.0 to 0.0 over ~20 weeks.
    Before DECAY_START_DATE: seed_weight = 1.0 (no decay)
    After: loses 5% per week until 0.
    """
    now = now_utc()
    if now < DECAY_START_DATE:
        return 1.0
    weeks_since = max(0, (now - DECAY_START_DATE).days // 7)
    return max(0.0, 1.0 - 0.05 * weeks_since)


def compute_effective_score(person):
    """
    Calculate the effective score considering seed decay.
    seed_weight goes from 1.0 (before decay) to 0.0 (full decay).
    Before decay: effective = total likes (seed votes fully counted)
    After full decay: effective = only real votes (seed votes removed)
    Formula: effective_likes = likes - seed_votes_likes * (1 - seed_weight)
    """
    seed_weight = compute_seed_weight()
    decay_factor = 1.0 - seed_weight  # 0 before decay, 1 after full decay

    likes = person.get("likes", 0)
    dislikes = person.get("dislikes", 0)
    superlikes = person.get("superlikes", 0)
    seed_likes = person.get("seed_votes_likes", 0)
    seed_dislikes = person.get("seed_votes_dislikes", 0)

    effective_likes = max(0, likes - int(seed_likes * decay_factor))
    effective_dislikes = max(0, dislikes - int(seed_dislikes * decay_factor))
    # Total includes superlikes (not affected by seed decay)
    effective_total = effective_likes + effective_dislikes + superlikes

    if (effective_likes + effective_dislikes) > 0:
        raw_score = (effective_likes / (effective_likes + effective_dislikes)) * 100
    else:
        raw_score = 0.0

    score = round(raw_score, 1)  # Session 2: no more round-to-25
    score = max(0, min(100, score))

    return raw_score, score, effective_likes, effective_dislikes, effective_total


def _is_outsider_doc(doc) -> bool:
    """
    An Outsider = source 'self_boosted' OR category 'outsider' OR is_outsider flag.
    Covers seeded outsiders (seed_outsiders.py) which carry no `source` field at all
    (popularoo_index.py reads that absence as "unknown").
    """
    return (
        doc.get("source") == "self_boosted"
        or doc.get("category") == "outsider"
        or doc.get("is_outsider") is True
    )


def _displayed_score(doc, eff_score: float) -> float:
    """
    The score shown to users.
    - popularoo_index when it has been computed (> 0), else the vote-ratio eff_score.
    - Outsiders are hard-capped at 25 — Vague 4 hierarchy (Q5):
      Outsiders ≤ 25 < Nouveaux entrants 25-50 < Célébrités confirmées sans plafond.
      The cap applies to every outsider profile, not just source == "self_boosted".
    """
    pi = doc.get("popularoo_index")
    score = pi if (pi is not None and pi > 0) else eff_score
    if _is_outsider_doc(doc):
        score = min(score, 25.0)
    return score


# -------------------- Pydantic Models --------------------
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=now_utc)


class StatusCheckCreate(BaseModel):
    client_name: str


Category = Literal["politics", "culture", "business", "sport", "influencer", "other", "outsider"]


class PersonCreate(BaseModel):
    name: str
    category: Optional[Category] = "other"


class PersonOut(BaseModel):
    id: str
    name: str
    category: Optional[Category] = "other"
    approved: bool = True
    score: float = 100.0
    likes: int = 0
    dislikes: int = 0
    superlikes: int = 0
    total_votes: int = 0
    popularoo_index: float = 0.0
    active_strikes: int = 0
    strike_emoji: Optional[str] = None
    strike_label: Optional[str] = None
    last_updated: Optional[datetime] = None
    source: Optional[str] = "seed"  # "seed", "user_added", "self_boosted", "trending"
    is_trending: Optional[bool] = False
    # Multi-country fields (Chantier 1)
    country_tags: Optional[List[str]] = None       # ["FR", "US", "international"]
    is_international: Optional[bool] = False
    primary_country: Optional[str] = None           # Main country code (e.g. "FR")
    # Social links (Chantier 1I)
    social_links: Optional[Dict[str, str]] = None   # {"instagram": "user", "tiktok": "user", "x": "user"}
    avatar_initials: Optional[str] = None
    avatar_color: Optional[str] = None
    # External scores (Session 2)
    popularity_external_score: Optional[float] = None
    wiki_score_norm: Optional[float] = None
    wiki_score_brut: Optional[float] = None
    last_external_update: Optional[datetime] = None
    # Direction of the last vote received: "up" (like / superlike) or "down" (dislike).
    # None when no real vote has ever been recorded for this profile.
    vote_momentum: Optional[str] = None


class VoteIn(BaseModel):
    value: Literal[1, -1, 5]  # 1=like, -1=dislike, 5=superlike


class VoteOut(BaseModel):
    id: str
    score: float
    likes: int
    dislikes: int
    superlikes: int = 0
    total_votes: int
    popularoo_index: float = 0.0
    voted_value: Optional[int] = None
    already_voted: bool = False
    next_vote_time: Optional[str] = None


class ChartOut(BaseModel):
    id: str
    name: str
    points: List[Dict[str, Any]]


class TrendItem(BaseModel):
    person_id: str
    name: str
    delta: float


# -------------------- Startup Seed --------------------
# ~125 celebrities with primary_country — balanced across 6 target markets + global
SEED_PEOPLE = [
    # ══════════════════════════════════════════════════════
    # 🇺🇸 US — Global Icons only (28)
    # ══════════════════════════════════════════════════════
    # Business (5 — truly global figures only)
    {"name": "Elon Musk", "category": "business", "primary_country": "US"},
    {"name": "Mark Zuckerberg", "category": "business", "primary_country": "US"},
    {"name": "Jeff Bezos", "category": "business", "primary_country": "US"},
    {"name": "Bill Gates", "category": "business", "primary_country": "US"},
    {"name": "Sam Altman", "category": "business", "primary_country": "US"},
    # Culture (13 — globally recognized names)
    {"name": "Oprah Winfrey", "category": "culture", "primary_country": "US"},
    {"name": "Taylor Swift", "category": "culture", "primary_country": "US"},
    {"name": "Beyoncé", "category": "culture", "primary_country": "US"},
    {"name": "Kanye West", "category": "culture", "primary_country": "US"},
    {"name": "Rihanna", "category": "culture", "primary_country": "US"},
    {"name": "Ariana Grande", "category": "culture", "primary_country": "US"},
    {"name": "Billie Eilish", "category": "culture", "primary_country": "US"},
    {"name": "Lady Gaga", "category": "culture", "primary_country": "US"},
    {"name": "Leonardo DiCaprio", "category": "culture", "primary_country": "US"},
    {"name": "Dwayne Johnson", "category": "culture", "primary_country": "US"},
    {"name": "Zendaya", "category": "culture", "primary_country": "US"},
    {"name": "Tom Hanks", "category": "culture", "primary_country": "US"},
    {"name": "Robert Downey Jr.", "category": "culture", "primary_country": "US"},
    # Sport (5 — globally known)
    {"name": "LeBron James", "category": "sport", "primary_country": "US"},
    {"name": "Serena Williams", "category": "sport", "primary_country": "US"},
    {"name": "Simone Biles", "category": "sport", "primary_country": "US"},
    {"name": "Tiger Woods", "category": "sport", "primary_country": "US"},
    {"name": "Mike Tyson", "category": "sport", "primary_country": "US"},
    # Politics (5 — globally known)
    {"name": "Donald Trump", "category": "politics", "primary_country": "US"},
    {"name": "Barack Obama", "category": "politics", "primary_country": "US"},
    {"name": "Joe Biden", "category": "politics", "primary_country": "US"},
    {"name": "Kamala Harris", "category": "politics", "primary_country": "US"},
    {"name": "Michelle Obama", "category": "politics", "primary_country": "US"},

    # ══════════════════════════════════════════════════════
    # 🇫🇷 FR — France (12)
    # ══════════════════════════════════════════════════════
    {"name": "Emmanuel Macron", "category": "politics", "primary_country": "FR"},
    {"name": "Kylian Mbappé", "category": "sport", "primary_country": "FR"},
    {"name": "Bernard Arnault", "category": "business", "primary_country": "FR"},
    {"name": "Zinedine Zidane", "category": "sport", "primary_country": "FR"},
    {"name": "Antoine Griezmann", "category": "sport", "primary_country": "FR"},
    {"name": "Teddy Riner", "category": "sport", "primary_country": "FR"},
    {"name": "Omar Sy", "category": "culture", "primary_country": "FR"},
    {"name": "Marion Cotillard", "category": "culture", "primary_country": "FR"},
    {"name": "Aya Nakamura", "category": "culture", "primary_country": "FR"},
    {"name": "Squeezie", "category": "culture", "primary_country": "FR"},
    {"name": "Marine Le Pen", "category": "politics", "primary_country": "FR"},
    {"name": "Thomas Pesquet", "category": "culture", "primary_country": "FR"},

    # ══════════════════════════════════════════════════════
    # 🇩🇪 DE — Germany (10)
    # ══════════════════════════════════════════════════════
    {"name": "Angela Merkel", "category": "politics", "primary_country": "DE"},
    {"name": "Olaf Scholz", "category": "politics", "primary_country": "DE"},
    {"name": "Ursula von der Leyen", "category": "politics", "primary_country": "DE"},
    {"name": "Toni Kroos", "category": "sport", "primary_country": "DE"},
    {"name": "Manuel Neuer", "category": "sport", "primary_country": "DE"},
    {"name": "Thomas Müller", "category": "sport", "primary_country": "DE"},
    {"name": "Jürgen Klopp", "category": "sport", "primary_country": "DE"},
    {"name": "Boris Becker", "category": "sport", "primary_country": "DE"},
    {"name": "Heidi Klum", "category": "culture", "primary_country": "DE"},
    {"name": "Diane Kruger", "category": "culture", "primary_country": "DE"},

    # ══════════════════════════════════════════════════════
    # 🇪🇸 ES — Spain (10)
    # ══════════════════════════════════════════════════════
    {"name": "Rafael Nadal", "category": "sport", "primary_country": "ES"},
    {"name": "Pedro Sánchez", "category": "politics", "primary_country": "ES"},
    {"name": "Carlos Alcaraz", "category": "sport", "primary_country": "ES"},
    {"name": "Rosalía", "category": "culture", "primary_country": "ES"},
    {"name": "Penélope Cruz", "category": "culture", "primary_country": "ES"},
    {"name": "Javier Bardem", "category": "culture", "primary_country": "ES"},
    {"name": "Andrés Iniesta", "category": "sport", "primary_country": "ES"},
    {"name": "Enrique Iglesias", "category": "culture", "primary_country": "ES"},
    {"name": "Gavi", "category": "sport", "primary_country": "ES"},
    {"name": "Iker Casillas", "category": "sport", "primary_country": "ES"},

    # ══════════════════════════════════════════════════════
    # 🇮🇹 IT — Italy (10)
    # ══════════════════════════════════════════════════════
    {"name": "Giorgia Meloni", "category": "politics", "primary_country": "IT"},
    {"name": "Jannik Sinner", "category": "sport", "primary_country": "IT"},
    {"name": "Gianluigi Buffon", "category": "sport", "primary_country": "IT"},
    {"name": "Valentino Rossi", "category": "sport", "primary_country": "IT"},
    {"name": "Monica Bellucci", "category": "culture", "primary_country": "IT"},
    {"name": "Laura Pausini", "category": "culture", "primary_country": "IT"},
    {"name": "Måneskin", "category": "culture", "primary_country": "IT"},
    {"name": "Chiara Ferragni", "category": "business", "primary_country": "IT"},
    {"name": "Sergio Mattarella", "category": "politics", "primary_country": "IT"},
    {"name": "Francesco Totti", "category": "sport", "primary_country": "IT"},

    # ══════════════════════════════════════════════════════
    # 🇵🇹 PT — Portugal (8)
    # ══════════════════════════════════════════════════════
    {"name": "Cristiano Ronaldo", "category": "sport", "primary_country": "PT"},
    {"name": "José Mourinho", "category": "sport", "primary_country": "PT"},
    {"name": "Bernardo Silva", "category": "sport", "primary_country": "PT"},
    {"name": "Bruno Fernandes", "category": "sport", "primary_country": "PT"},
    # Diogo Jota removed — deceased (Session 3 cleanup)
    {"name": "Marcelo Rebelo de Sousa", "category": "politics", "primary_country": "PT"},
    {"name": "Sara Sampaio", "category": "culture", "primary_country": "PT"},
    {"name": "Daniela Ruah", "category": "culture", "primary_country": "PT"},

    # ══════════════════════════════════════════════════════
    # 🇧🇷 BR — Brazil (10)
    # ══════════════════════════════════════════════════════
    {"name": "Neymar Jr.", "category": "sport", "primary_country": "BR"},
    {"name": "Lula da Silva", "category": "politics", "primary_country": "BR"},
    {"name": "Vinicius Jr.", "category": "sport", "primary_country": "BR"},
    {"name": "Ronaldinho", "category": "sport", "primary_country": "BR"},
    {"name": "Anitta", "category": "culture", "primary_country": "BR"},
    {"name": "Gisele Bündchen", "category": "culture", "primary_country": "BR"},
    {"name": "Gabriel Medina", "category": "sport", "primary_country": "BR"},
    {"name": "Jair Bolsonaro", "category": "politics", "primary_country": "BR"},
    {"name": "Caetano Veloso", "category": "culture", "primary_country": "BR"},
    {"name": "Alisson Becker", "category": "sport", "primary_country": "BR"},

    # ══════════════════════════════════════════════════════
    # 🇬🇧 GB — United Kingdom (10)
    # ══════════════════════════════════════════════════════
    {"name": "King Charles III", "category": "politics", "primary_country": "GB"},
    {"name": "Prince William", "category": "politics", "primary_country": "GB"},
    {"name": "Rishi Sunak", "category": "politics", "primary_country": "GB"},
    {"name": "Lewis Hamilton", "category": "sport", "primary_country": "GB"},
    {"name": "David Beckham", "category": "sport", "primary_country": "GB"},
    {"name": "Ed Sheeran", "category": "culture", "primary_country": "GB"},
    {"name": "Adele", "category": "culture", "primary_country": "GB"},
    {"name": "Dua Lipa", "category": "culture", "primary_country": "GB"},
    {"name": "Harry Styles", "category": "culture", "primary_country": "GB"},
    # Queen Elizabeth II removed — deceased (Session 3 cleanup)

    # ══════════════════════════════════════════════════════
    # 🌍 Other countries (20)
    # ══════════════════════════════════════════════════════
    # 🇨🇦 Canada
    {"name": "Drake", "category": "culture", "primary_country": "CA"},
    {"name": "Justin Bieber", "category": "culture", "primary_country": "CA"},
    {"name": "The Weeknd", "category": "culture", "primary_country": "CA"},
    {"name": "Justin Trudeau", "category": "politics", "primary_country": "CA"},
    # 🇦🇷 Argentina
    {"name": "Lionel Messi", "category": "sport", "primary_country": "AR"},
    # Pope Francis removed — deceased (Session 3 cleanup)
    {"name": "Javier Milei", "category": "politics", "primary_country": "AR"},
    # 🇮🇳 India
    {"name": "Narendra Modi", "category": "politics", "primary_country": "IN"},
    {"name": "Virat Kohli", "category": "sport", "primary_country": "IN"},
    {"name": "Malala Yousafzai", "category": "culture", "primary_country": "PK"},
    # 🇨🇳 China
    {"name": "Xi Jinping", "category": "politics", "primary_country": "CN"},
    {"name": "Jack Ma", "category": "business", "primary_country": "CN"},
    # 🇷🇺 / 🇺🇦
    {"name": "Vladimir Putin", "category": "politics", "primary_country": "RU"},
    {"name": "Volodymyr Zelenskyy", "category": "politics", "primary_country": "UA"},
    # 🇰🇷 / 🇯🇵
    {"name": "BTS", "category": "culture", "primary_country": "KR"},
    {"name": "Naomi Osaka", "category": "sport", "primary_country": "JP"},
    # Other
    {"name": "Shakira", "category": "culture", "primary_country": "CO"},
    {"name": "Greta Thunberg", "category": "culture", "primary_country": "SE"},
    {"name": "Benjamin Netanyahu", "category": "politics", "primary_country": "IL"},
    {"name": "Mohamed Salah", "category": "sport", "primary_country": "EG"},
    {"name": "Novak Djokovic", "category": "sport", "primary_country": "RS"},
    {"name": "Roger Federer", "category": "sport", "primary_country": "CH"},
    {"name": "Erling Haaland", "category": "sport", "primary_country": "NO"},
    {"name": "Max Verstappen", "category": "sport", "primary_country": "NL"},
    {"name": "Conor McGregor", "category": "sport", "primary_country": "IE"},
    {"name": "Usain Bolt", "category": "sport", "primary_country": "JM"},
    {"name": "Chris Hemsworth", "category": "culture", "primary_country": "AU"},

    # ══════════════════════════════════════════════════════
    # 📱 Influencers — Top social media personalities (20)
    # ══════════════════════════════════════════════════════
    # 🇫🇷 France (7)
    {"name": "Léna Situations", "category": "influencer", "primary_country": "FR"},
    {"name": "Cyprien", "category": "influencer", "primary_country": "FR"},
    {"name": "Norman Thavaud", "category": "influencer", "primary_country": "FR"},
    {"name": "Tibo InShape", "category": "influencer", "primary_country": "FR"},
    {"name": "McFly et Carlito", "category": "influencer", "primary_country": "FR"},
    {"name": "Enjoy Phoenix", "category": "influencer", "primary_country": "FR"},
    {"name": "Inoxtag", "category": "influencer", "primary_country": "FR"},
    # 🇺🇸 US (7)
    {"name": "MrBeast", "category": "influencer", "primary_country": "US"},
    {"name": "Kylie Jenner", "category": "influencer", "primary_country": "US"},
    {"name": "Kim Kardashian", "category": "influencer", "primary_country": "US"},
    {"name": "Khaby Lame", "category": "influencer", "primary_country": "US"},
    {"name": "Addison Rae", "category": "influencer", "primary_country": "US"},
    {"name": "Emma Chamberlain", "category": "influencer", "primary_country": "US"},
    {"name": "Logan Paul", "category": "influencer", "primary_country": "US"},
    # 🇬🇧 UK (3)
    {"name": "KSI", "category": "influencer", "primary_country": "GB"},
    {"name": "Zoella", "category": "influencer", "primary_country": "GB"},
    {"name": "Molly-Mae Hague", "category": "influencer", "primary_country": "GB"},
    # 🇪🇸 Spain (1)
    {"name": "ElRubius", "category": "influencer", "primary_country": "ES"},
    # 🇧🇷 Brazil (1)
    {"name": "Whindersson Nunes", "category": "influencer", "primary_country": "BR"},
    # 🇩🇪 Germany (1)
    {"name": "Bibi Claßen", "category": "influencer", "primary_country": "DE"},
]


async def ensure_indexes():
    # persons
    await db.persons.create_index("slug", unique=True)
    await db.persons.create_index([("approved", 1), ("total_votes", -1), ("score", -1)])
    await db.persons.create_index([("approved", 1), ("raw_score", -1)])  # For Bull Run ladder
    await db.persons.create_index([("name", "text")])
    # votes (one per device/person)
    await db.votes.create_index([("person_id", 1), ("device_id", 1)], unique=True)
    # vote_events for time window aggregations
    await db.vote_events.create_index([("created_at", 1), ("person_id", 1)])
    # ticks for charts
    await db.person_ticks.create_index([("person_id", 1), ("created_at", 1)])
    # searches for suggestions
    await db.searches.create_index([("created_at", 1), ("query", 1)])
    # Bull Run indexes
    await db.bull_runs.create_index([("user_id", 1), ("is_active", 1)])
    await db.bull_runs.create_index([("user_id", 1), ("expires_at", -1)])
    await db.bull_run_wins.create_index([("bull_run_id", 1), ("confirmed", 1)])
    await db.bull_run_wins.create_index([("bull_run_id", 1), ("celebrity_id", 1)])
    # Rally Cry indexes
    await db.rally_cries.create_index([("user_id", 1), ("created_at", -1)])
    await db.rally_cries.create_index([("expires_at", 1), ("target_beaten", 1)])
    # User settings
    await db.user_settings.create_index("device_id", unique=True)


async def seed_people():
    count = await db.persons.count_documents({})
    if count > 0:
        # DB already has data — check for new seed entries (e.g., influencers added later)
        await seed_missing_people()
        return
    docs = []
    now = now_utc()
    for p in SEED_PEOPLE:
        slug = slugify(p["name"])
        doc = {
            "name": p["name"],
            "slug": slug,
            "category": p.get("category", "other"),
            "approved": True,
            "created_at": now,
            "updated_at": now,
            "score": 100.0,
            "likes": 0,
            "dislikes": 0,
            "total_votes": 0,
        }
        if p.get("primary_country"):
            doc["primary_country"] = p["primary_country"]
        docs.append(doc)
    if docs:
        res = await db.persons.insert_many(docs)
        # insert initial ticks
        tick_docs = [{
            "person_id": oid,
            "score": 100.0,
            "created_at": now
        } for oid in res.inserted_ids]
        if tick_docs:
            await db.person_ticks.insert_many(tick_docs)


async def seed_missing_people():
    """Insert any SEED_PEOPLE entries not yet in the database (e.g., new influencers).
    
    Session 3: Checks seed_blocklist before inserting. Names confirmed as deceased
    or manually blocked are never reinserted, even if present in SEED_PEOPLE.
    """
    import random
    now = now_utc()
    added = 0
    blocked = 0

    # Load blocklist from app_settings (structural anti-reinsertion mechanism)
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    blocked_slugs = set(settings.get("seed_blocklist", []))
    blocked_names = set(settings.get("seed_blocklist_names", []))

    for p in SEED_PEOPLE:
        slug = slugify(p["name"])

        # Check blocklist FIRST (covers deceased, manually removed, etc.).
        # name_normalized is the primary key (robust against the slugify accent bug).
        if slug in blocked_slugs or normalize_person_name(p["name"]) in blocked_names:
            blocked += 1
            continue

        existing = await db.persons.find_one({"slug": slug})
        if existing:
            continue
        # Give initial votes similar to other seeds (range 5000-15000)
        init_likes = random.randint(5000, 12000)
        init_dislikes = random.randint(1000, 4000)
        total = init_likes + init_dislikes
        score = round((init_likes / max(1, total)) * 200 - 100, 1)  # Convert to -100..+100 scale
        doc = {
            "name": p["name"],
            "slug": slug,
            "category": p.get("category", "other"),
            "approved": True,
            "created_at": now,
            "updated_at": now,
            "score": score,
            "likes": init_likes,
            "dislikes": init_dislikes,
            "total_votes": total,
            "seed_votes_likes": init_likes,
            "seed_votes_dislikes": init_dislikes,
            "source": "seed",
        }
        if p.get("primary_country"):
            doc["primary_country"] = p["primary_country"]
            # Set country_tags for geographic feed filtering
            doc["country_tags"] = [p["primary_country"], "international"]
            doc["is_international"] = True
        result = await db.persons.insert_one(doc)
        # Insert initial tick
        await db.person_ticks.insert_one({
            "person_id": result.inserted_id,
            "score": score,
            "created_at": now
        })
        added += 1
    if added > 0:
        logger.info(f"🌱 seed_missing_people: Added {added} new personalities")
    if blocked > 0:
        logger.info(f"🚫 seed_missing_people: Skipped {blocked} blocked names")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_people()
    await migrate_raw_scores()
    await migrate_seed_votes()
    await auto_seed_outsiders_on_startup()
    # Initialize Bull Run module with db reference
    init_bull_run(db)


async def auto_seed_outsiders_on_startup():
    """Auto-seed outsiders if none exist — ensures app is never empty at launch."""
    try:
        active_count = await db.active_boosts.count_documents({
            "end_time": {"$gt": now_utc()},
            "is_seed": True,
            "seed_active": True
        })
        if active_count == 0:
            logger.info("🌱 No active seed outsiders found — auto-seeding...")
            from seed_outsiders import create_seed_outsiders
            result = await create_seed_outsiders(db)
            logger.info(f"🌱 Auto-seed complete: {result.get('created', 0)} outsiders created")
        else:
            logger.info(f"🌱 {active_count} active seed outsiders already present")
    except Exception as e:
        logger.error(f"Auto-seed outsiders failed (non-fatal): {e}")


async def migrate_raw_scores():
    """Migration: Calculate raw_score for all existing persons that don't have it"""
    count = await db.persons.count_documents({"raw_score": {"$exists": False}})
    if count == 0:
        return
    
    logger.info(f"🔄 Migrating raw_score for {count} persons...")
    cursor = db.persons.find({"raw_score": {"$exists": False}})
    async for person in cursor:
        likes = person.get("likes", 0)
        total_votes = person.get("total_votes", 0)
        raw_score = (likes / total_votes * 100) if total_votes > 0 else 0.0
        await db.persons.update_one(
            {"_id": person["_id"]},
            {"$set": {"raw_score": raw_score}}
        )
    logger.info(f"✅ raw_score migration complete for {count} persons")


async def migrate_seed_votes():
    """
    Migration: For seeded persons (source=seed) that don't have seed_votes_likes,
    snapshot their current likes/dislikes as seed votes.
    For non-seeded persons, set seed_votes to 0.
    """
    count = await db.persons.count_documents({"seed_votes_likes": {"$exists": False}})
    if count == 0:
        return

    logger.info(f"🌱 Migrating seed_votes for {count} persons...")
    cursor = db.persons.find({"seed_votes_likes": {"$exists": False}})
    async for person in cursor:
        source = person.get("source", "seed")
        if source == "seed" and person.get("total_votes", 0) > 100:
            # This person was seeded with initial votes — snapshot them
            seed_likes = person.get("likes", 0)
            seed_dislikes = person.get("dislikes", 0)
        else:
            # Not seeded (outsiders, user_added, wikipedia, trending) = 0 seed
            seed_likes = 0
            seed_dislikes = 0

        await db.persons.update_one(
            {"_id": person["_id"]},
            {"$set": {"seed_votes_likes": seed_likes, "seed_votes_dislikes": seed_dislikes}}
        )
    logger.info(f"✅ seed_votes migration complete for {count} persons")


# -------------------- Routes --------------------
@api_router.get("/")
async def root():
    return {"message": "Popularoo API running"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.model_dump())
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    # compatibility with Pydantic models
    out: List[StatusCheck] = []
    for s in status_checks:
        out.append(StatusCheck(id=s.get("id"), client_name=s.get("client_name"), timestamp=s.get("timestamp")))
    return out


# -------------------- User Settings & Country Detection --------------------

SUPPORTED_COUNTRIES = ["FR", "GB", "US", "CA", "ES", "MX", "BR", "AR", "DE", "IT", "BE", "CH"]
SUPPORTED_LANGUAGES = ["en", "fr", "es", "pt", "de", "it"]

# Country → default language mapping
COUNTRY_LANGUAGE_MAP = {
    "FR": "fr", "BE": "fr", "CH": "fr",
    "US": "en", "GB": "en", "CA": "en", "AU": "en",
    "ES": "es", "MX": "es", "AR": "es",
    "BR": "pt", "PT": "pt",
    "DE": "de", "IT": "it",
}


@api_router.get("/detect-country")
async def detect_country(request: Request):
    """
    Detect user country from request headers (X-Forwarded-For → IP geolocation fallback).
    Primary source should be App Store/Google Play country, set by the client.
    This endpoint provides a server-side fallback via IP.
    """
    # Try to get country from header (set by frontend from device locale/store)
    client_country = request.headers.get("X-User-Country", "").upper().strip()
    if client_country in SUPPORTED_COUNTRIES:
        return {
            "country": client_country,
            "source": "client_header",
            "language": COUNTRY_LANGUAGE_MAP.get(client_country, "en"),
        }

    # IP-based fallback using free ipapi.co service
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None

    if client_ip and client_ip not in ("127.0.0.1", "localhost", "::1"):
        try:
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.get(
                    f"https://ipapi.co/{client_ip}/json/",
                    headers={"User-Agent": "Popularoo/1.0"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    detected = data.get("country_code", "").upper()
                    if detected in SUPPORTED_COUNTRIES:
                        return {
                            "country": detected,
                            "source": "ip_geolocation",
                            "language": COUNTRY_LANGUAGE_MAP.get(detected, "en"),
                            "ip_country_name": data.get("country_name", ""),
                        }
        except Exception as e:
            logger.warning(f"IP geolocation failed: {e}")

    # Default fallback
    return {
        "country": "US",
        "source": "default_fallback",
        "language": "en",
    }


@api_router.post("/user-settings")
async def save_user_settings(body: Dict[str, Any]):
    """
    Save user preferences (country, language).
    Stored by device_id for anonymous users.
    """
    device_id = body.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")

    now = now_utc()
    update_fields = {"updated_at": now}

    if "country" in body:
        c = body["country"].upper().strip()
        if c in SUPPORTED_COUNTRIES:
            update_fields["country"] = c
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported country: {c}")

    if "language" in body:
        lang = body["language"].lower().strip()
        if lang in SUPPORTED_LANGUAGES:
            update_fields["language"] = lang
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    await db.user_settings.update_one(
        {"device_id": device_id},
        {"$set": update_fields, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    doc = await db.user_settings.find_one({"device_id": device_id})
    return {
        "success": True,
        "country": doc.get("country"),
        "language": doc.get("language"),
    }


@api_router.get("/user-settings/{device_id}")
async def get_user_settings(device_id: str):
    """Get saved user preferences."""
    doc = await db.user_settings.find_one({"device_id": device_id})
    if not doc:
        return {"country": None, "language": None}
    return {
        "country": doc.get("country"),
        "language": doc.get("language"),
    }


def _safe_int(val, default=0) -> int:
    """Safely convert to int, returning default if conversion fails."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _safe_float(val, default=0.0) -> float:
    """Safely convert to float, returning default if conversion fails."""
    if val is None:
        return default
    try:
        result = float(val)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default

def person_to_out(doc: Dict[str, Any]) -> Optional[PersonOut]:
    """Convert a DB document to PersonOut. Returns None if data is fatally corrupt."""
    try:
        # Apply seed decay for displayed score (fallback for outsiders / legacy)
        _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(doc)

        # Session 2 / Vague 4: the displayed score IS the popularoo_index when computed.
        # Outsiders are additionally hard-capped at 25 (see _displayed_score).
        displayed_score = _displayed_score(doc, eff_score)

        # Strike level
        active_strikes = _safe_int(doc.get("active_strikes", 0))
        s_emoji, s_label = get_strike_level(active_strikes)

        # Validate category against allowed values
        raw_cat = doc.get("category", "other")
        valid_cats = {"politics", "culture", "business", "sport", "influencer", "other", "outsider"}
        category = raw_cat if raw_cat in valid_cats else "other"

        name = doc.get("name")
        if not name or not isinstance(name, str):
            logger.warning(f"⚠️ Skipping person {doc.get('_id')} — missing or invalid name: {name!r}")
            return None

        return PersonOut(
            id=str(doc["_id"]),
            name=name,
            category=category,
            approved=bool(doc.get("approved", True)),
            score=_safe_float(displayed_score),
            likes=_safe_int(eff_likes),
            dislikes=_safe_int(eff_dislikes),
            superlikes=_safe_int(doc.get("superlikes", 0)),
            total_votes=_safe_int(eff_total),
            popularoo_index=_safe_float(doc.get("popularoo_index", 0.0)),
            active_strikes=active_strikes,
            strike_emoji=s_emoji if s_emoji else None,
            strike_label=s_label if s_label else None,
            last_updated=doc.get("updated_at"),
            source=doc.get("source", "seed"),
            country_tags=doc.get("country_tags"),
            is_international=bool(doc.get("is_international", False)),
            primary_country=doc.get("primary_country"),
            social_links=doc.get("social_links") or None,
            avatar_initials=doc.get("avatar_initials"),
            avatar_color=doc.get("avatar_color"),
            popularity_external_score=_safe_float(doc.get("popularity_external_score")) if doc.get("popularity_external_score") is not None else None,
            wiki_score_norm=_safe_float(doc.get("wiki_score_norm")) if doc.get("wiki_score_norm") is not None else None,
            wiki_score_brut=_safe_float(doc.get("wiki_score_brut")) if doc.get("wiki_score_brut") is not None else None,
            last_external_update=doc.get("last_external_update"),
            vote_momentum=(doc.get("vote_momentum") if doc.get("vote_momentum") in ("up", "down") else None),
        )
    except Exception as e:
        logger.error(f"❌ person_to_out CRASH for id={doc.get('_id')}, name={doc.get('name')!r}: {e}")
        return None


@api_router.get("/personality-of-the-day", response_model=PersonOut)
async def get_personality_of_the_day():
    """
    Chantier C — Returns the current Personality of the Day.

    Read from app_settings.potd_current (updated hourly by run_potd_rotation_job).
    Fallback: if no rotation has ever run, return the profile with the highest
    popularoo_index among approved non-outsider celebrities. 404 only if even
    the fallback is empty (DB has no eligible profile at all).
    """
    settings = await db.app_settings.find_one({"_id": "potd_current"})
    person_oid = settings.get("potd_person_id") if settings else None

    person = None
    if person_oid is not None:
        try:
            person = await db.persons.find_one({"_id": person_oid})
        except Exception:
            person = None

    if not person:
        # Fallback: pick current top-1 by popularoo_index.
        person = await db.persons.find_one(
            {
                "approved": True,
                "suspended": {"$ne": True},
                "category": {"$ne": "outsider"},
                "source": {"$ne": "self_boosted"},
            },
            sort=[("popularoo_index", -1), ("total_votes", -1)],
        )

    if not person:
        raise HTTPException(status_code=404, detail="No eligible Personality of the Day available")

    out = person_to_out(person)
    if out is None:
        raise HTTPException(status_code=500, detail="POTD profile failed serialization")
    return out


@api_router.get("/people", response_model=List[PersonOut])
async def list_people(
    query: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=300),
    category: Optional[str] = Query(default=None),
    include_outsiders: bool = Query(default=False),
    country: Optional[str] = Query(default=None, description="User country code for 60/40 feed filtering"),
):
    """
    List personalities with optional 60/40 local/international feed.
    If country is provided, returns ~60% local + ~40% international.
    Among local: prioritizes culture, sport, and influencer categories.
    """
    filter_q: Dict[str, Any] = {"approved": True, "suspended": {"$ne": True}, "visible_in_rankings": {"$ne": False}}
    
    # Exclude ALL outsiders (self_boosted + seeds) from main lists unless explicitly requested
    # Triple protection: category + is_outsider + source
    if not include_outsiders:
        filter_q["category"] = {"$ne": "outsider"}
        filter_q["is_outsider"] = {"$ne": True}
        filter_q["source"] = {"$nin": ["self_boosted"]}
    
    if query:
        # Search for partial matches in name (case-insensitive)
        search_term = query.strip()
        words = search_term.split()
        if len(words) == 1:
            regex = re.escape(words[0])
            filter_q["name"] = {"$regex": regex, "$options": "i"}
        else:
            regexes = [{"name": {"$regex": re.escape(word), "$options": "i"}} for word in words]
            filter_q["$and"] = regexes
    if category:
        cat = category.strip().lower()
        if cat != "all":
            if cat == "outsider":
                # Special category for self-boosted users
                filter_q["source"] = "self_boosted"
            elif cat not in {"politics", "culture", "business", "sport", "influencer", "other"}:
                raise HTTPException(status_code=400, detail="Invalid category")
            else:
                filter_q["category"] = cat

    # 60/40 local/international feed when country is specified
    if country and not query:
        user_country = country.upper().strip()
        local_limit = int(limit * 0.6)  # 60% local
        intl_limit = limit - local_limit  # 40% international

        # Fetch local personalities (tagged with user's country)
        # Prioritize culture, sport, influencers (50%+ of local)
        local_filter = {**filter_q, "country_tags": user_country}
        
        # Priority categories for local results
        priority_cats = ["culture", "sport", "influencer"]
        priority_filter = {**local_filter, "category": {"$in": priority_cats}}
        priority_limit = max(1, local_limit // 2)  # At least 50% of local slots
        
        priority_cursor = db.persons.find(priority_filter).sort([("popularoo_index", -1), ("total_votes", -1)]).limit(priority_limit)
        priority_docs = await priority_cursor.to_list(length=priority_limit)
        
        # Fill remaining local slots with any category
        remaining_local = local_limit - len(priority_docs)
        priority_ids = [d["_id"] for d in priority_docs]
        other_local_filter = {**local_filter, "_id": {"$nin": priority_ids}}
        other_local_cursor = db.persons.find(other_local_filter).sort([("popularoo_index", -1)]).limit(remaining_local)
        other_local_docs = await other_local_cursor.to_list(length=remaining_local)
        
        local_docs = priority_docs + other_local_docs

        # If not enough local, fill with more international
        remaining = limit - len(local_docs)
        
        # Fetch remaining personalities (any country except already-fetched)
        local_ids = [d["_id"] for d in local_docs]
        intl_filter = {**filter_q, "_id": {"$nin": local_ids}}
        intl_cursor = db.persons.find(intl_filter).sort([("popularoo_index", -1), ("total_votes", -1)]).limit(remaining)
        intl_docs = await intl_cursor.to_list(length=remaining)

        # Interleave: local, intl, local, intl...
        merged = []
        li, ii = 0, 0
        while li < len(local_docs) or ii < len(intl_docs):
            if li < len(local_docs):
                merged.append(local_docs[li])
                li += 1
            if ii < len(intl_docs):
                merged.append(intl_docs[ii])
                ii += 1

        return [p for p in (person_to_out(d) for d in merged[:limit]) if p is not None]
    
    cursor = db.persons.find(filter_q).sort([("total_votes", -1), ("score", -1)]).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [p for p in (person_to_out(d) for d in docs) if p is not None]


@api_router.post("/people", response_model=PersonOut)
async def add_person(body: PersonCreate):
    # DISABLED (Lot 1, Task 1.2) — anti-backdoor.
    # This endpoint allowed ANYONE (no auth) to create an immediately-visible
    # `approved: True` personality, bypassing the candidate-queue moderation and
    # the anti-ghost blocklist. It is not called anywhere in the app (the client
    # only ever GETs /people; user additions go through /submit-celebrity-request).
    # Closed for good: always 403. Legitimate creation paths are the admin
    # endpoints and the moderated candidate queue.
    raise HTTPException(
        status_code=403,
        detail="This endpoint is disabled. Personalities are added via the moderated candidate queue.",
    )


@api_router.get("/people/{person_id}", response_model=PersonOut)
async def get_person(person_id: str):
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")
    doc = await db.persons.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Person not found")
    return person_to_out(doc)


async def write_vote_event(person_oid: ObjectId, device_id: str, delta: int):
    await db.vote_events.insert_one({
        "person_id": person_oid,
        "device_id": device_id,
        "delta": int(delta),
        "created_at": now_utc(),
    })


@api_router.post("/people/{person_id}/vote", response_model=VoteOut)
async def vote_person(person_id: str, body: VoteIn, x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID")):
    if not x_device_id:
        raise HTTPException(status_code=400, detail="X-Device-ID header is required for anonymous voting")
    
    # ── Ban enforcement ──
    await _check_device_not_banned(x_device_id)
    
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # ── Suspension enforcement ──
    await _check_person_not_suspended(person)

    new_val = int(body.value)
    # An Outsider is a self-boosted profile OR a seed explicitly categorized "outsider".
    # NOT every seed — that bug blocked dislikes on all seed celebrities and allowed
    # superlikes on them. Outsiders = self_boosted OR category == "outsider".
    is_outsider = person.get("source") == "self_boosted" or person.get("category") == "outsider"

    # Block dislikes on outsiders (anti-harassment protection)
    if new_val == -1 and is_outsider:
        raise HTTPException(status_code=403, detail="Dislikes are not available for Outsiders. You can only support them!")

    # Block superlikes on non-outsiders
    if new_val == 5 and not is_outsider:
        raise HTTPException(status_code=403, detail="Superlikes are only available for Outsiders")

    # ---- SUPERLIKE PATH (value=5) ----
    if new_val == 5:
        # Separate cooldown tracking for superlikes
        existing_sl = await db.superlike_votes.find_one({
            "person_id": oid, "device_id": x_device_id
        })
        if existing_sl:
            last_sl_time = existing_sl.get("created_at")
            time_since = now_utc() - last_sl_time if last_sl_time else timedelta(days=2)
            if time_since < timedelta(hours=24):
                next_vote_time = (last_sl_time + timedelta(hours=24)).isoformat() + "Z" if last_sl_time else None
                _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(person)
                return VoteOut(
                    id=str(person["_id"]),
                    score=float(_displayed_score(person, eff_score)),
                    likes=int(eff_likes),
                    dislikes=int(eff_dislikes),
                    superlikes=int(person.get("superlikes", 0)),
                    total_votes=int(eff_total),
                    popularoo_index=float(person.get("popularoo_index", 0.0)),
                    voted_value=5,
                    already_voted=True,
                    next_vote_time=next_vote_time,
                )
            # 24h passed, update existing record
            await db.superlike_votes.update_one(
                {"_id": existing_sl["_id"]},
                {"$set": {"created_at": now_utc()}}
            )
        else:
            await db.superlike_votes.insert_one({
                "person_id": oid, "device_id": x_device_id, "created_at": now_utc()
            })

        # Record superlike event (for strike detection in Phase B)
        await db.superlike_events.insert_one({
            "person_id": oid, "device_id": x_device_id, "created_at": now_utc()
        })

        # Increment superlikes counter + total_votes
        inc_doc = {"superlikes": 1, "total_votes": 1}
        _now = now_utc()
        await db.persons.update_one(
            {"_id": oid},
            {"$inc": inc_doc, "$set": {
                "updated_at": _now,
                "vote_momentum": "up",  # superlike is a positive signal
                "last_vote_at": _now,
            }}
        )

        # Write vote event (delta=5 for superlike weight)
        await write_vote_event(oid, x_device_id, 5)

        # Quick recalculate Popularoo Index
        updated = await db.persons.find_one({"_id": oid})
        try:
            config = await load_index_config(db)
            new_index = await quick_recalc_index(db, updated, config)
            updated = await db.persons.find_one({"_id": oid})
        except Exception as e:
            logger.warning(f"Quick index recalc failed: {e}")

        # ---- Strike detection (event-driven) ----
        strike_result = None
        try:
            strike_result = await check_and_trigger_strikes(db, oid, email_service=email_service)
            if strike_result and strike_result.get("new_strikes"):
                logger.info(f"⚡ Strikes triggered for {updated.get('name')}: {strike_result['new_strikes']} "
                           f"(total active: {strike_result['active_count']})")
                # Re-read updated person (strikes modified it)
                updated = await db.persons.find_one({"_id": oid})
                # Recalc index with new strikes bonus
                await quick_recalc_index(db, updated, config)
                updated = await db.persons.find_one({"_id": oid})
        except Exception as e:
            logger.warning(f"Strike detection failed: {e}")

        # Record tick
        await db.person_ticks.insert_one({
            "person_id": oid,
            "score": updated.get("score", 0),
            "total_votes": updated.get("total_votes", 0),
            "created_at": now_utc()
        })

        _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(updated)
        return VoteOut(
            id=str(updated["_id"]),
            score=float(_displayed_score(updated, eff_score)),
            likes=int(eff_likes),
            dislikes=int(eff_dislikes),
            superlikes=int(updated.get("superlikes", 0)),
            total_votes=int(eff_total),
            popularoo_index=float(updated.get("popularoo_index", 0.0)),
            voted_value=5,
        )

    # ---- LIKE/DISLIKE PATH (value=1 or -1) ----
    existing_vote = await db.votes.find_one({"person_id": oid, "device_id": x_device_id})

    delta = new_val
    inc_doc: Dict[str, Any] = {"total_votes": 0}

    if existing_vote:
        old_val = int(existing_vote.get("value", 0))
        last_vote_time = existing_vote.get("updated_at") or existing_vote.get("created_at")
        
        # Check if 24 hours have passed since last vote
        time_since_last_vote = now_utc() - last_vote_time if last_vote_time else timedelta(days=2)
        
        if time_since_last_vote < timedelta(hours=24):
            # Less than 24h - cannot vote again
            next_vote_time = (last_vote_time + timedelta(hours=24)).isoformat() + "Z" if last_vote_time else None
            _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(person)
            return VoteOut(
                id=str(person["_id"]),
                score=float(_displayed_score(person, eff_score)),
                likes=int(eff_likes),
                dislikes=int(eff_dislikes),
                superlikes=int(person.get("superlikes", 0)),
                total_votes=int(eff_total),
                popularoo_index=float(person.get("popularoo_index", 0.0)),
                voted_value=old_val,
                already_voted=True,
                next_vote_time=next_vote_time,
            )
        
        # 24h passed - can vote again
        if new_val == 1:
            inc_doc["likes"] = 1
        else:
            inc_doc["dislikes"] = 1
        inc_doc["total_votes"] = 1
        
        await db.votes.update_one(
            {"_id": existing_vote["_id"]},
            {"$set": {"value": new_val, "updated_at": now_utc()}}
        )
    else:
        # first vote from this device for this person
        if new_val == 1:
            inc_doc["likes"] = 1
            inc_doc["dislikes"] = 0
        else:
            inc_doc["likes"] = 0
            inc_doc["dislikes"] = 1
        inc_doc["total_votes"] = 1
        await db.votes.insert_one({
            "person_id": oid,
            "device_id": x_device_id,
            "value": new_val,
            "created_at": now_utc(),
            "updated_at": now_utc(),
        })

    # Calculate new score based on likes and dislikes ratio
    new_likes = int(person.get("likes", 0)) + inc_doc.get("likes", 0)
    new_dislikes = int(person.get("dislikes", 0)) + inc_doc.get("dislikes", 0)
    new_total_votes = int(person.get("total_votes", 0)) + inc_doc.get("total_votes", 0)
    
    if new_total_votes > 0:
        raw_score = (new_likes / new_total_votes) * 100
    else:
        raw_score = 0.0
    
    if new_total_votes > 0:
        new_score = round(raw_score, 1)  # Session 2: no more round-to-25
        new_score = max(0, min(100, new_score))
    else:
        new_score = 0
    
    # Update person aggregates (do NOT overwrite score here — quick_recalc_index handles it)
    _now = now_utc()
    await db.persons.update_one(
        {"_id": oid},
        {"$inc": inc_doc, "$set": {
            "raw_score": raw_score,
            "updated_at": _now,
            "vote_momentum": "up" if new_val == 1 else "down",
            "last_vote_at": _now,
        }}
    )
    
    # Write vote event
    await write_vote_event(oid, x_device_id, int(delta))

    # Quick recalculate Popularoo Index
    updated = await db.persons.find_one({"_id": oid})
    try:
        config = await load_index_config(db)
        await quick_recalc_index(db, updated, config)
        updated = await db.persons.find_one({"_id": oid})
    except Exception as e:
        logger.warning(f"Quick index recalc failed: {e}")

    # Record tick
    total_votes_now = updated.get("total_votes", 0) if updated else 0
    await db.person_ticks.insert_one({
        "person_id": oid, 
        "score": new_score, 
        "total_votes": total_votes_now,
        "created_at": now_utc()
    })

    _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(updated)
    return VoteOut(
        id=str(updated["_id"]),
        score=float(_displayed_score(updated, eff_score)),
        likes=int(eff_likes),
        dislikes=int(eff_dislikes),
        superlikes=int(updated.get("superlikes", 0)),
        total_votes=int(eff_total),
        popularoo_index=float(updated.get("popularoo_index", 0.0)),
        voted_value=new_val,
    )


@api_router.get("/people/{person_id}/chart", response_model=ChartOut)
async def get_chart(person_id: str, window: str = Query(default="24h")):
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # parse window
    m = re.match(r"^(\d+)([mh])$", window)
    if not m:
        raise HTTPException(status_code=400, detail="Invalid window; use like '60m' or '24h'")
    value, unit = int(m.group(1)), m.group(2)
    if unit == 'm':
        start = now_utc() - timedelta(minutes=value)
    else:
        start = now_utc() - timedelta(hours=value)

    cursor = db.person_ticks.find({
        "person_id": oid,
        "created_at": {"$gte": start}
    }).sort("created_at", 1)
    ticks = await cursor.to_list(length=2000)

    # Ensure we have at least 2 points for a line chart
    if len(ticks) < 2:
        # Get the current score
        current_score = float(person.get("score", 50.0))
        
        # Create synthetic historical data points for visualization
        now = now_utc()
        points = []
        
        # Generate points over the last 24 hours with slight variations
        for i in range(24, 0, -4):  # Every 4 hours
            time_point = now - timedelta(hours=i)
            # Add small random variation (±5 points) for visual effect
            variation = random.uniform(-5, 5)
            point_score = max(0, min(100, current_score + variation))
            points.append({
                "t": time_point.isoformat() + "Z",
                "score": round(point_score, 2)
            })
        
        # Add current point
        points.append({
            "t": now.isoformat() + "Z",
            "score": current_score
        })
        
        return ChartOut(id=str(person["_id"]), name=person.get("name"), points=points)

    points = [{"t": t["created_at"].isoformat() + "Z", "score": float(t.get("score", person.get("score", 100.0)))} for t in ticks]
    return ChartOut(id=str(person["_id"]), name=person.get("name"), points=points)


class VotesChartPoint(BaseModel):
    t: str
    total_votes: int

class VotesChartOut(BaseModel):
    id: str
    name: str
    points: List[VotesChartPoint]

@api_router.get("/people/{person_id}/votes-chart", response_model=VotesChartOut)
async def get_votes_chart(person_id: str, window: str = Query(default="24h")):
    """Get vote count history for a person over time"""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # parse window
    m = re.match(r"^(\d+)([mhd])$", window)
    if not m:
        raise HTTPException(status_code=400, detail="Invalid window; use like '60m', '24h', or '7d'")
    value, unit = int(m.group(1)), m.group(2)
    if unit == 'm':
        start = now_utc() - timedelta(minutes=value)
    elif unit == 'h':
        start = now_utc() - timedelta(hours=value)
    else:  # 'd'
        start = now_utc() - timedelta(days=value)

    cursor = db.person_ticks.find({
        "person_id": oid,
        "created_at": {"$gte": start}
    }).sort("created_at", 1)
    ticks = await cursor.to_list(length=2000)

    # Build points from ticks that have total_votes
    points = []
    current_total = person.get("total_votes", 0)
    
    for t in ticks:
        votes = t.get("total_votes")
        if votes is not None:
            points.append({
                "t": t["created_at"].isoformat() + "Z", 
                "total_votes": int(votes)
            })
    
    # If no historical data with votes, create synthetic data points
    if not points:
        # Just show current value as a single point
        points = [{"t": now_utc().isoformat() + "Z", "total_votes": current_total}]
    
    return VotesChartOut(id=str(person["_id"]), name=person.get("name"), points=points)


@api_router.get("/trends", response_model=List[TrendItem])
async def get_trends(window: str = Query(default="60m"), limit: int = Query(default=20, le=50)):
    # window: e.g. "60m", "24h", "7d"
    now = now_utc()
    delta = parse_window(window)
    cutoff = now - delta
    cursor = db.person_ticks.find({"created_at": {"$gte": cutoff}}).sort("created_at", 1)
    ticks = await cursor.to_list(length=100000)
    # build map of person_id -> [scores over time]
    person_map: Dict[str, List[float]] = {}
    for t in ticks:
        pid = str(t["person_id"])
        person_map.setdefault(pid, []).append(float(t["score"]))
    # compute deltas
    out = []
    for pid, scores in person_map.items():
        if len(scores) < 2:
            continue
        delta_val = scores[-1] - scores[0]
        p = await db.persons.find_one({"_id": ObjectId(pid)})
        if p:
            out.append(TrendItem(person_id=pid, name=p["name"], delta=delta_val))
    out.sort(key=lambda x: abs(x.delta), reverse=True)
    return out[:limit]


@api_router.get("/trending-now", response_model=List[PersonOut])
async def get_trending_now(limit: int = Query(default=5, le=10)):
    """Get top personalities with fastest rising scores in last 24h"""
    now = now_utc()
    cutoff = now - timedelta(hours=24)
    
    # Get all ticks in last 24h
    cursor = db.person_ticks.find({"created_at": {"$gte": cutoff}}).sort("created_at", 1)
    ticks = await cursor.to_list(length=100000)
    
    # Calculate score increase for each person
    person_deltas: Dict[str, float] = {}
    person_first: Dict[str, float] = {}
    person_last: Dict[str, float] = {}
    
    for t in ticks:
        pid = str(t["person_id"])
        score = float(t["score"])
        if pid not in person_first:
            person_first[pid] = score
        person_last[pid] = score
    
    # Calculate deltas (only positive growth)
    for pid in person_first:
        delta = person_last[pid] - person_first[pid]
        if delta > 0:  # Only rising personalities
            person_deltas[pid] = delta
    
    # Sort by delta and get top
    sorted_ids = sorted(person_deltas.keys(), key=lambda x: person_deltas[x], reverse=True)[:limit]
    
    # Fetch person details — filter out invisible rankings
    result = []
    for pid in sorted_ids:
        try:
            p = await db.persons.find_one({"_id": ObjectId(pid)})
            if p and p.get("visible_in_rankings") is not False:
                po = person_to_out(p)
                if po:
                    result.append(po)
        except Exception:
            continue
    
    return result


@api_router.get("/controversial", response_model=List[PersonOut])
async def get_controversial(limit: int = Query(default=5, le=20)):
    """Get most controversial personalities (lots of opposing votes)"""
    # Find persons with both high likes AND high dislikes
    cursor = db.persons.find({
        "approved": True,
        "total_votes": {"$gte": 10},  # Minimum 10 votes
        "visible_in_rankings": {"$ne": False},
    })
    persons = await cursor.to_list(length=1000)
    
    # Calculate controversy score: min(likes, dislikes) / total_votes
    # Higher score = more balanced opposition
    controversial = []
    for p in persons:
        likes = int(p.get("likes", 0))
        dislikes = int(p.get("dislikes", 0))
        total = int(p.get("total_votes", 0))
        
        if total >= 10:
            # Controversy = how close to 50/50 split
            controversy_score = min(likes, dislikes) / total
            controversial.append({
                "person": p,
                "controversy": controversy_score
            })
    
    # Sort by controversy score
    controversial.sort(key=lambda x: x["controversy"], reverse=True)
    
    # Return top N
    result = []
    for item in controversial[:limit]:
        result.append(person_to_out(item["person"]))
    
    return result


class SearchIn(BaseModel):
    query: str


@api_router.post("/searches")
async def record_search(body: SearchIn, x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID")):
    q = body.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    await db.searches.insert_one({
        "query": q,
        "device_id": x_device_id,
        "created_at": now_utc(),
    })
    return {"ok": True}


# ==================== VAGUE 4 — SOUS-TÂCHE 5: User Celebrity Request ====================

@api_router.post("/submit-celebrity-request")
async def submit_celebrity_request(body: Dict[str, Any]):
    """
    Vague 4, sous-tâche 5 — A user asks for a celebrity that isn't in Popularoo yet.

    Normalizes the name, runs 4 dedup/blocklist checks, and (if none match)
    enqueues a 'user_search' entry in candidate_queue. There is NO synchronous
    Wikipedia/Wikidata validation here — the response must stay fast (< 200ms).
    The heavy validation runs 24h later in process_user_submissions_job via
    validate_single_name (sous-tâche 4).

    Body: { "name": str, "device_id": str }  — both required.
    """
    from candidate_detection import process_celebrity_request

    name = (body.get("name") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")

    result = await process_celebrity_request(db, name, device_id)
    status = result["status"]

    if status == "already_exists":
        return {"status": "already_exists", "person_id": result["person_id"]}

    if status == "already_pending":
        return {
            "status": "already_pending",
            "process_after": result["process_after"],
            "message_key": "search.queued_message",
        }

    # "rejected" (slug in seed_blocklist) is masked as "queued": the user still
    # gets the standard 24h waiting message so the blocklist stays invisible.
    process_after = result.get("process_after")
    if status == "rejected":
        process_after = (now_utc() + timedelta(hours=24)).isoformat()

    return {
        "status": "queued",
        "process_after": process_after,
        "message_key": "search.queued_message",
    }


import unicodedata
import httpx

def remove_accents(text: str) -> str:
    """Remove accents from text for search matching"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

async def search_wikipedia_person(query: str) -> Optional[Dict[str, Any]]:
    """Search Wikipedia for a person and return their info if found.
    Filters out deceased persons (checks for death_date in Wikidata).
    """
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{query}",
            "format": "json",
            "srlimit": 5,
        }
        headers = {
            "User-Agent": "PopularooApp/1.0 (https://popularoo.com; contact@popularoo.com)"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(search_url, params=params, headers=headers)
            if response.status_code != 200:
                logger.warning(f"Wikipedia API returned {response.status_code}")
                return None
            
            data = response.json()
            search_results = data.get("query", {}).get("search", [])
            
            if not search_results:
                return None
            
            for result in search_results:
                title = result.get("title", "")
                snippet = result.get("snippet", "").lower()
                
                person_keywords = ["born", "politician", "actor", "actress", "singer", "player", 
                                   "athlete", "businessman", "businesswoman", "president", "minister",
                                   "celebrity", "artist", "musician", "footballer", "basketball",
                                   "tennis", "author", "director", "entrepreneur", "ceo", "founder",
                                   "rapper", "comedian", "model", "journalist", "host"]
                
                is_person = any(keyword in snippet for keyword in person_keywords)
                
                words = title.split()
                # Name heuristic: 2-4 capitalized words, no digits, no all-caps words (acronyms)
                looks_like_name = (
                    2 <= len(words) <= 4
                    and all(w[0].isupper() for w in words if w)
                    and not any(w.isupper() and len(w) > 1 for w in words)  # Exclude "BDHS", "XXX"
                    and not any(c.isdigit() for c in title)  # Exclude "Super Bowl 30"
                )
                
                if is_person or looks_like_name:
                    # Check for deceased — look for "died" or death year in snippet
                    death_keywords = ["died", "death", "deceased", "was a ", "was an "]
                    is_deceased = any(dk in snippet for dk in death_keywords)
                    
                    if is_deceased:
                        logger.info(f"⚰️ Skipping deceased person: {title}")
                        continue
                    
                    # Determine category
                    category = "other"
                    if any(k in snippet for k in ["politician", "president", "minister", "senator", "governor", "pope"]):
                        category = "politics"
                    elif any(k in snippet for k in ["footballer", "basketball", "tennis", "athlete", "player", "olympic", "sport"]):
                        category = "sport"
                    elif any(k in snippet for k in ["businessman", "businesswoman", "ceo", "entrepreneur", "founder", "investor"]):
                        category = "business"
                    elif any(k in snippet for k in ["actor", "actress", "singer", "musician", "artist", "director", "author"]):
                        category = "culture"
                    
                    return {
                        "name": title,
                        "category": category,
                        "source": "wikipedia",
                    }
            
            return None
            
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        return None

@api_router.get("/search")
async def search_people(query: str = Query(..., min_length=1), limit: int = Query(default=10, le=50)):
    """Search for people by name (case-insensitive, accent-insensitive, partial match).

    Returns ALL approved (non-deceased, non-blocklisted) profiles matching the query.
    NOTE (Vague 4): the legacy async auto-creation path has been removed — a search
    for an unknown name simply returns []. The replacement creation flow lands in a
    later Vague 4 sub-task (/api/submit-celebrity-request).
    """
    try:
        search_term = query.strip()
        search_term_normalized = remove_accents(search_term)
        
        # Build filter: approved, not deceased
        # NOTE: visible_in_rankings is intentionally NOT filtered here.
        # /api/search must return ALL approved profiles (including user_search ones)
        # so users can find them. Only /api/people (rankings) filters on visible_in_rankings.
        filter_q: Dict[str, Any] = {"approved": True, "is_deceased": {"$ne": True}}
        
        # Check blocklist to filter results
        settings = await db.app_settings.find_one({"_id": "global"}) or {}
        blocked_slugs = set(settings.get("seed_blocklist", []))
        
        # Split into words for multi-word search
        words = search_term_normalized.split()
        
        if len(words) == 1:
            word = words[0]
            flexible_regex = ''.join([
                f"[{c}{get_accent_variants(c)}]" if c.isalpha() else re.escape(c)
                for c in word
            ])
            filter_q["name"] = {"$regex": flexible_regex, "$options": "i"}
        else:
            regex_list = []
            for word in words:
                flexible_regex = ''.join([
                    f"[{c}{get_accent_variants(c)}]" if c.isalpha() else re.escape(c)
                    for c in word
                ])
                regex_list.append({"name": {"$regex": flexible_regex, "$options": "i"}})
            filter_q["$and"] = regex_list
        
        cursor = db.persons.find(filter_q).sort([("total_votes", -1), ("score", -1)]).limit(limit)
        results = await cursor.to_list(length=limit)
        
        out = []
        for doc in results:
            # Filter out blocked persons from search results
            doc_slug = doc.get("slug", slugify(doc.get("name", "")))
            if doc_slug in blocked_slugs:
                continue
            po = person_to_out(doc)
            if po:
                out.append({
                    "id": po.id,
                    "name": po.name,
                    "category": po.category,
                    "score": po.score,
                    "total_votes": po.total_votes,
                    "likes": po.likes,
                    "dislikes": po.dislikes,
                    "source": doc.get("source", "unknown"),
                })

        return out
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def get_accent_variants(char: str) -> str:
    """Get common accent variants for a character"""
    variants = {
        'a': 'àáâãäåæ', 'A': 'ÀÁÂÃÄÅÆ',
        'e': 'èéêëẽ', 'E': 'ÈÉÊËẼ',
        'i': 'ìíîïĩ', 'I': 'ÌÍÎÏĨ',
        'o': 'òóôõöø', 'O': 'ÒÓÔÕÖØ',
        'u': 'ùúûüũ', 'U': 'ÙÚÛÜŨ',
        'c': 'ç', 'C': 'Ç',
        'n': 'ñ', 'N': 'Ñ',
        'y': 'ýÿ', 'Y': 'ÝŸ',
    }
    return variants.get(char, '')


@api_router.get("/search-suggestions")
async def search_suggestions(window: str = Query(default="24h"), limit: int = Query(default=10, le=20)):
    m = re.match(r"^(\d+)([mh])$", window)
    if not m:
        raise HTTPException(status_code=400, detail="Invalid window; use like '60m' or '24h'")
    value, unit = int(m.group(1)), m.group(2)
    if unit == 'm':
        start = now_utc() - timedelta(minutes=value)
    else:
        start = now_utc() - timedelta(hours=value)

    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": "$query", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "term": "$_id"}}
    ]
    rows = await db.searches.aggregate(pipeline).to_list(length=limit)
    terms = [r["term"] for r in rows]
    return {"terms": terms}


@api_router.get("/search-suggestions/by-category")
async def search_suggestions_by_category(window: str = Query(default="24h"), perCatLimit: int = Query(default=8, le=20)):
    """
    Returns top searched names within window, joined to persons, split by category.
    Shape: { politics: ["..."], culture: ["..."], business: ["..."] }
    """
    m = re.match(r"^(\d+)([mh])$", window)
    if not m:
        raise HTTPException(status_code=400, detail="Invalid window; use like '60m' or '24h'")
    value, unit = int(m.group(1)), m.group(2)
    if unit == 'm':
        start = now_utc() - timedelta(minutes=value)
    else:
        start = now_utc() - timedelta(hours=value)

    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": "$query", "count": {"$sum": 1}}},
        {"$lookup": {
            "from": "persons",
            "localField": "_id",
            "foreignField": "name",
            "as": "person"
        }},
        {"$unwind": "$person"},
        {"$group": {"_id": "$person.category", "items": {"$push": {"name": "$person.name", "count": "$count"}}}},
        {"$project": {"category": "$_id", "items": 1, "_id": 0}},
    ]

    docs = await db.searches.aggregate(pipeline).to_list(length=1000)
    result = {"politics": [], "culture": [], "business": []}
    for d in docs:
        cat = d.get("category")
        items = d.get("items", [])
        # sort by count desc and unique by name
        items_sorted = sorted(items, key=lambda x: x.get("count", 0), reverse=True)
        seen = set()
        out = []
        for it in items_sorted:
            nm = it.get("name")
            if nm and nm not in seen:
                seen.add(nm)
                out.append(nm)
            if len(out) >= perCatLimit:
                break
        if cat in result:
            result[cat] = out
    return result


@api_router.get("/outsiders")
async def get_outsiders(
    limit: int = Query(default=20, le=50),
    country: Optional[str] = Query(default=None, description="User country code — outsiders restricted to same country"),
):
    """Get active outsiders with visibility boosts, split by position (golden=top, regular=bottom).
    If country is provided, only show outsiders boosted from the same country."""
    try:
        now = now_utc()

        # Get all active boosts (not expired, excluding disabled seeds)
        boost_filter: Dict[str, Any] = {
            "end_time": {"$gt": now},
            "$or": [
                {"is_seed": {"$ne": True}},            # Real outsiders
                {"is_seed": True, "seed_active": True}, # Active seeds only
            ],
        }
        # Aggregation pipeline : remplace l'ancien pattern N+1
        # (1 find + 100 find_one) par 1 seule round-trip Mongo avec $lookup.
        # Gain attendu sur Render : 8s -> ~1-2s pour /api/outsiders.
        pipeline: List[Dict[str, Any]] = [
            {"$match": boost_filter},
            {"$sort": {"start_time": -1}},
            {"$limit": 100},
            {
                "$lookup": {
                    "from": "persons",
                    "localField": "person_id",
                    "foreignField": "_id",
                    "as": "person",
                }
            },
            {"$unwind": {"path": "$person", "preserveNullAndEmptyArrays": False}},
        ]
        boosts_with_person = await db.active_boosts.aggregate(pipeline).to_list(length=100)

        golden_outsiders = []
        regular_outsiders = []

        user_country = country.upper().strip() if country else None

        for boost in boosts_with_person:
            person = boost["person"]

            # Country restriction: outsiders visible only to same-country users
            if user_country:
                boost_country = boost.get("country") or person.get("primary_country")
                if boost_country and boost_country.upper() != user_country:
                    continue

            time_remaining = (boost["end_time"] - now).total_seconds()
            hours_remaining = max(0, time_remaining / 3600)

            outsider_data = {
                "id": str(person["_id"]),
                "boost_id": str(boost["_id"]),
                "user_id": boost.get("user_id", ""),
                "name": person.get("name", ""),
                "category": person.get("category", "other"),
                "score": person.get("score", 50.0),
                "total_votes": person.get("total_votes", 0),
                "likes": person.get("likes", 0),
                "dislikes": person.get("dislikes", 0),
                "tier": boost.get("tier", "booster"),
                "tier_name": BOOSTER_TIERS.get(boost.get("tier", "booster"), {}).get("name", "Booster"),
                "position": boost.get("position", "bottom"),
                "end_time": boost["end_time"].isoformat(),
                "hours_remaining": round(hours_remaining, 1),
                "social_links": person.get("social_links", {}),
                "avatar_initials": person.get("avatar_initials", ""),
                "avatar_color": person.get("avatar_color", "#1C3A2C"),
                "popularoo_index": person.get("popularoo_index", 0),
                "active_strikes": person.get("active_strikes", 0),
                "strike_emoji": person.get("strike_emoji"),
                "strike_label": person.get("strike_label"),
                "is_seed": bool(boost.get("is_seed", False)),
                "vote_momentum": person.get("vote_momentum") if person.get("vote_momentum") in ("up", "down") else None,
            }

            if boost.get("position") == "top":
                golden_outsiders.append(outsider_data)
            else:
                regular_outsiders.append(outsider_data)

        return {
            "golden": golden_outsiders[:limit],
            "regular": regular_outsiders[:limit],
            "total_active": len(golden_outsiders) + len(regular_outsiders),
        }
    except Exception as e:
        logger.error(f"Failed to get outsiders: {e}")
        return {"golden": [], "regular": [], "total_active": 0}


@api_router.get("/onboarding/top3")
async def get_onboarding_top3(country: Optional[str] = Query(default=None)):
    """
    Returns top 3 personalities for onboarding, ordered by Popularoo Index.
    Uses curated overrides per target country for editorial control,
    then falls back to DB-based selection.
    """
    # ── Curated top3 per target country (editorial override) ──
    CURATED_TOP3 = {
        "FR": ["Kylian Mbappé", "Squeezie", "Emmanuel Macron"],      # sport, culture, politics
        "DE": ["Toni Kroos", "Heidi Klum", "Olaf Scholz"],           # sport, culture, politics
        "ES": ["Carlos Alcaraz", "Rosalía", "Rafael Nadal"],         # sport, culture, sport
        "IT": ["Jannik Sinner", "Monica Bellucci", "Giorgia Meloni"],# sport, culture, politics
        "PT": ["Cristiano Ronaldo", "Sara Sampaio", "José Mourinho"],# sport, culture, sport
        "BR": ["Vinicius Jr.", "Anitta", "Lula da Silva"],           # sport, culture, politics
        "GB": ["Lewis Hamilton", "Adele", "King Charles III"],       # sport, culture, politics
        "US": ["Elon Musk", "Taylor Swift", "Donald Trump"],         # business, culture, politics
    }

    try:
        country_code = country.strip().upper() if country else None

        # ── Try curated override first ──
        if country_code and country_code in CURATED_TOP3:
            curated_names = CURATED_TOP3[country_code]
            result = []
            for name in curated_names:
                person = await db.persons.find_one(
                    {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
                )
                if person:
                    result.append({
                        "name": person.get("name", name),
                        "category": person.get("category", "other"),
                        "popularoo_index": round(person.get("popularoo_index", 50.0), 1),
                    })
                else:
                    # Name not in DB yet: return placeholder
                    result.append({
                        "name": name,
                        "category": "other",
                        "popularoo_index": 50.0,
                    })
            if len(result) == 3:
                return {"top3": result, "country": country_code}

        # ── Fallback: DB-based selection ──
        if country_code:
            persons = await db.persons.find(
                {"primary_country": country_code}
            ).sort("popularoo_index", -1).to_list(length=20)
        else:
            persons = []

        # Pick diverse categories: one politics, one culture, one sport
        result = []
        categories_wanted = ["politics", "sport", "culture"]
        categories_found = set()

        for p in persons:
            cat = p.get("category", "other")
            if cat in categories_wanted and cat not in categories_found:
                result.append({
                    "name": p.get("name", ""),
                    "category": cat,
                    "popularoo_index": round(p.get("popularoo_index", 0), 1),
                })
                categories_found.add(cat)
                if len(result) == 3:
                    break

        # Fill remaining slots from same country (any category)
        if len(result) < 3:
            existing_names = {r["name"] for r in result}
            for p in persons:
                if p.get("name") not in existing_names:
                    result.append({
                        "name": p.get("name", ""),
                        "category": p.get("category", "other"),
                        "popularoo_index": round(p.get("popularoo_index", 0), 1),
                    })
                    existing_names.add(p.get("name"))
                    if len(result) == 3:
                        break

        # Still less than 3? Fill with global top
        if len(result) < 3:
            global_top = await db.persons.find({}).sort("popularoo_index", -1).to_list(length=10)
            existing_names = {r["name"] for r in result}
            for p in global_top:
                if p.get("name") not in existing_names:
                    result.append({
                        "name": p.get("name", ""),
                        "category": p.get("category", "other"),
                        "popularoo_index": round(p.get("popularoo_index", 0), 1),
                    })
                    if len(result) == 3:
                        break

        # Sort result by popularoo_index descending
        result.sort(key=lambda x: x["popularoo_index"], reverse=True)

        return {"top3": result, "country": country_code or "global"}

    except Exception as e:
        logger.error(f"Onboarding top3 error: {e}")
        return {"top3": [], "country": country or "global"}



@api_router.get("/outsiders/paginated")
async def get_outsiders_paginated(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=50, description="Items per page"),
    sort_by: str = Query(default="index", description="Sort: index | momentum | tier | votes"),
    search: Optional[str] = Query(default=None, description="Search outsider by name"),
    country: Optional[str] = Query(default=None, description="Country filter"),
):
    """
    Chantier 1L — Paginated Outsiders list supporting 1000+ active outsiders.
    Supports sorting by Popularoo Index, 24h momentum, Booster tier, or total votes.
    Supports search by name. Returns paginated results with metadata.
    """
    try:
        now = now_utc()

        # Build base filter for active boosts (not expired, including active seeds)
        boost_filter: Dict[str, Any] = {
            "end_time": {"$gt": now},
            "suspended": {"$ne": True},
            "$or": [
                {"is_seed": {"$ne": True}},
                {"is_seed": True, "seed_active": True},
            ],
        }

        # Country filter
        if country:
            boost_filter["country"] = country.upper().strip()

        # Get ALL active boosts (up to 1000)
        active_boosts = await db.active_boosts.find(boost_filter).to_list(length=1000)

        # Build outsider data for all active boosts
        outsider_list = []
        for boost in active_boosts:
            person = await db.persons.find_one({"_id": boost["person_id"]})
            if not person:
                continue
            # Skip suspended persons
            if person.get("suspended"):
                continue

            time_remaining = (boost["end_time"] - now).total_seconds()
            hours_remaining = max(0, time_remaining / 3600)

            # Calculate 24h momentum: votes gained in last 24h
            momentum_24h = 0
            try:
                yesterday = now - timedelta(hours=24)
                recent_ticks = await db.person_ticks.find({
                    "person_id": boost["person_id"],
                    "timestamp": {"$gte": yesterday},
                }).sort("timestamp", 1).to_list(length=50)
                if len(recent_ticks) >= 2:
                    momentum_24h = recent_ticks[-1].get("total_votes", 0) - recent_ticks[0].get("total_votes", 0)
                elif len(recent_ticks) == 1:
                    momentum_24h = person.get("total_votes", 0) - recent_ticks[0].get("total_votes", 0)
            except Exception:
                pass

            # Tier priority for sorting (golden=3, super=2, regular=1)
            tier = boost.get("tier", "booster")
            tier_priority = {"golden_booster": 3, "super_booster": 2, "booster": 1}.get(tier, 0)

            outsider_data = {
                "id": str(person["_id"]),
                "boost_id": str(boost["_id"]),
                "user_id": boost.get("user_id", ""),
                "name": person.get("name", ""),
                "category": person.get("category", "other"),
                "score": person.get("score", 50.0),
                "total_votes": person.get("total_votes", 0),
                "likes": person.get("likes", 0),
                "dislikes": person.get("dislikes", 0),
                "tier": tier,
                "tier_name": BOOSTER_TIERS.get(tier, {}).get("name", "Booster"),
                "tier_priority": tier_priority,
                "position": boost.get("position", "bottom"),
                "end_time": boost["end_time"].isoformat(),
                "hours_remaining": round(hours_remaining, 1),
                "social_links": person.get("social_links", {}),
                "avatar_initials": person.get("avatar_initials", ""),
                "avatar_color": person.get("avatar_color", "#1C3A2C"),
                "popularoo_index": person.get("popularoo_index", 0),
                "momentum_24h": momentum_24h,
                "active_strikes": person.get("active_strikes", 0),
                "strike_emoji": person.get("strike_emoji"),
                "strike_label": person.get("strike_label"),
                "is_seed": bool(boost.get("is_seed", False)),
                "country": boost.get("country") or person.get("primary_country", ""),
                "vote_momentum": person.get("vote_momentum") if person.get("vote_momentum") in ("up", "down") else None,
            }
            outsider_list.append(outsider_data)

        # Apply search filter (case-insensitive, accent-insensitive partial match)
        if search and search.strip():
            query_normalized = unidecode(search.strip().lower())
            outsider_list = [o for o in outsider_list if query_normalized in unidecode(o["name"].lower())]

        # Apply sorting
        if sort_by == "index":
            outsider_list.sort(key=lambda x: x["popularoo_index"], reverse=True)
        elif sort_by == "momentum":
            outsider_list.sort(key=lambda x: x["momentum_24h"], reverse=True)
        elif sort_by == "tier":
            outsider_list.sort(key=lambda x: (x["tier_priority"], x["popularoo_index"]), reverse=True)
        elif sort_by == "votes":
            outsider_list.sort(key=lambda x: x["total_votes"], reverse=True)
        else:
            outsider_list.sort(key=lambda x: x["popularoo_index"], reverse=True)

        # Pagination
        total = len(outsider_list)
        total_pages = max(1, (total + limit - 1) // limit)
        page = min(page, total_pages)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_items = outsider_list[start_idx:end_idx]

        return {
            "outsiders": page_items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "sort_by": sort_by,
        }

    except Exception as e:
        logger.error(f"Failed to get paginated outsiders: {e}")
        return {
            "outsiders": [],
            "pagination": {"page": 1, "limit": limit, "total": 0, "total_pages": 0, "has_next": False, "has_prev": False},
            "sort_by": sort_by,
        }


@api_router.get("/last-searches")
async def last_searches(limit: int = Query(default=5, le=20)):
    """Return the last unique searches (most recent first)."""
    pipeline = [
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$query", "created_at": {"$first": "$created_at"}}},
        {"$sort": {"created_at": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "term": "$_id"}}
    ]
    rows = await db.searches.aggregate(pipeline).to_list(length=limit)
    return {"terms": [r["term"] for r in rows]}


# -------------------- Booster Visibility System --------------------

# Booster tiers: visibility in the Outsiders ranking (Golden = priority placement + Home page rotation)
BOOSTER_TIERS = {
    "booster": {
        "name": "Booster",
        "price": 0.99,
        "duration_hours": 1,
        "position": "bottom",
        "description": "Get a spot in the Outsiders ranking for 1 hour. Get noticed by the community.",
    },
    "super_booster": {
        "name": "Super Booster",
        "price": 9.99,
        "duration_hours": 24,
        "position": "bottom",
        "description": "Get a spot in the Outsiders ranking for 24 hours. More time = more votes = better climb.",
    },
    "golden_booster": {
        "name": "Golden Booster",
        "price": 49.99,
        "duration_hours": 24 * 7,  # 1 week
        "position": "top",  # Priority placement in Outsiders + Home page rotation as Outsider of the Day
        "description": "Priority placement in Outsiders + Home page rotation + exclusive Bull Run access.",
    },
}

# ── Chantier 1I: Social accounts validation ──
SOCIAL_REGEX = {
    "instagram": re.compile(r'^@?[a-zA-Z0-9._]{1,30}$'),   # 1-30 chars, letters/digits/dots/underscores
    "tiktok": re.compile(r'^@?[a-zA-Z0-9._]{2,24}$'),      # 2-24 chars, same rules
    "x": re.compile(r'^@?[a-zA-Z0-9_]{4,15}$'),             # 4-15 chars, no dots
}

def _clean_username(username: str) -> str:
    """Strip @ prefix and whitespace from a social username."""
    if not username:
        return ""
    return username.strip().lstrip("@")

def _validate_social_username(platform: str, username: str) -> bool:
    """Validate a social username against platform-specific rules."""
    if not username:
        return True  # Empty = valid (optional)
    cleaned = _clean_username(username)
    pattern = SOCIAL_REGEX.get(platform)
    return bool(pattern and pattern.match(cleaned))


class SocialLinks(BaseModel):
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    x: Optional[str] = None

class BoostMyselfRequest(BaseModel):
    user_id: str
    name: str
    email: Optional[str] = None
    tier: Literal["booster", "super_booster", "golden_booster"] = "booster"
    social_links: Optional[SocialLinks] = None
    category: Optional[str] = "other"
    receipt: Optional[str] = None
    platform: Optional[str] = None
    country: Optional[str] = None  # Country code for geo-restriction

class ExtendBoostRequest(BaseModel):
    user_id: str
    boost_id: str
    tier: Literal["booster", "super_booster", "golden_booster"]

@api_router.get("/booster-tiers")
async def get_booster_tiers():
    """Get available booster tiers and their pricing"""
    return {
        "tiers": [
            {
                "id": tid,
                "name": t["name"],
                "price": t["price"],
                "duration_hours": t["duration_hours"],
                "position": t["position"],
                "description": t["description"],
            }
            for tid, t in BOOSTER_TIERS.items()
        ]
    }


@api_router.get("/credits/balance/{user_id}")
async def get_credit_balance(user_id: str):
    """Get user's active boosts with full details"""
    now = now_utc()
    active_boosts = await db.active_boosts.find({
        "user_id": user_id,
        "end_time": {"$gt": now},
    }).sort("end_time", -1).to_list(100)

    boost_details = []
    for b in active_boosts:
        # Fetch social_links from the person doc
        person_social = {}
        if b.get("person_id"):
            person_doc = await db.persons.find_one({"_id": b["person_id"]})
            if person_doc:
                person_social = person_doc.get("social_links", {})
        detail = {
            "id": str(b["_id"]),
            "person_id": str(b["person_id"]) if b.get("person_id") else None,
            "tier": b.get("tier", "booster"),
            "name": b.get("name", ""),
            "start_time": b.get("start_time", "").isoformat() if hasattr(b.get("start_time", ""), "isoformat") else str(b.get("start_time", "")),
            "end_time": b.get("end_time", "").isoformat() if hasattr(b.get("end_time", ""), "isoformat") else str(b.get("end_time", "")),
            "daily_runs_used": b.get("daily_runs_used", 0),
            "daily_runs_total": b.get("daily_runs_total", 0),
            "social_links": person_social or {},
        }
        boost_details.append(detail)

    return {
        "active_boosts": len(active_boosts),
        "boost_details": boost_details,
        "boosters": 0,
        "super_boosters": 0,
        "balance": 0,
        "is_premium": len(active_boosts) > 0,
    }


@api_router.get("/credits/history/{user_id}")
async def get_credit_history(user_id: str, limit: int = Query(default=20, le=50)):
    """Get user's boost transaction history"""
    transactions = await db.credit_transactions.find(
        {"user_id": user_id}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)

    for t in transactions:
        t["_id"] = str(t["_id"])

    return {"transactions": transactions}


@api_router.post("/boost-myself")
async def boost_myself(request: BoostMyselfRequest):
    """Purchase a visibility boost and appear in the Outsiders ranking (Golden: + priority placement + Home page rotation)"""
    try:
        # ── Ban enforcement ──
        await _check_device_not_banned(request.user_id)
        
        # Require a valid receipt from Apple/Google for payment verification
        if not request.receipt or len(request.receipt) < 10:
            raise HTTPException(
                status_code=400,
                detail="Payment receipt required. Please complete the purchase through the App Store or Google Play."
            )

        # Validate tier
        if request.tier not in BOOSTER_TIERS:
            raise HTTPException(status_code=400, detail="Invalid booster tier")

        tier_info = BOOSTER_TIERS[request.tier]

        # ── Idempotency (R2) ──
        # A successful Apple/Google payment can be re-delivered by the store: app killed
        # mid-flight, a lost 200 response, or the client startup catch-up replaying the
        # store queue. Each store transaction carries a unique receipt/token, so we dedupe
        # on it: if this exact receipt already produced a boost, return that SAME boost
        # (200) without creating or replacing anything — no double boost, no duplicate
        # transaction record, no duplicate email.
        #
        # NON-REGRESSION: boosts created before the "receipt" field existed simply do not
        # have the key, so this query never matches them (absence of field = no match, not
        # an error). request.receipt is guaranteed non-empty (len >= 10) by the check
        # above, and store tokens are unique, so a new payment can never collide with an
        # old receipt-less boost. The short-circuit runs BEFORE any name/social handling,
        # so a name-less replay (startup catch-up) never overwrites the original name.
        existing_by_receipt = await db.active_boosts.find_one(
            {"receipt": request.receipt},
            sort=[("created_at", -1)],
        )
        if existing_by_receipt:
            person_doc = await db.persons.find_one({"_id": existing_by_receipt["person_id"]})
            person_name = (person_doc or {}).get(
                "name", existing_by_receipt.get("person_name", "Outsider")
            )
            name_provisional = bool((person_doc or {}).get("name_provisional", False))
            stored_tier = existing_by_receipt.get("tier", request.tier)
            stored_tier_info = BOOSTER_TIERS.get(stored_tier, tier_info)
            logger.info(
                f"Idempotent boost-myself: receipt already processed → returning "
                f"existing boost {existing_by_receipt.get('_id')} for '{person_name}'"
            )
            return {
                "success": True,
                "person_id": str(existing_by_receipt["person_id"]),
                "boost_id": str(existing_by_receipt["_id"]),
                "person_name": person_name,
                "name_provisional": name_provisional,
                "tier": stored_tier,
                "tier_name": stored_tier_info["name"],
                "price": stored_tier_info["price"],
                "end_time": existing_by_receipt["end_time"].isoformat(),
                "duration_hours": stored_tier_info["duration_hours"],
                "position": existing_by_receipt.get("position", stored_tier_info["position"]),
                "message": f"🎉 {stored_tier_info['name']} already active! '{person_name}' is in the Outsiders ranking.",
                "idempotent": True,
            }

        # Normalize name. Name is OPTIONAL (Apple 5.1.1(v)): an empty or too-short name
        # must NOT block the purchase. In that case we assign a provisional "Outsider"
        # display name and a slug derived from user_id, so each nameless buyer keeps a
        # distinct, stable profile (no merging of different users under one shared slug).
        raw_name = request.name.strip()
        name_provisional = len(raw_name) < 2
        if name_provisional:
            name = "Outsider"
            slug = slugify(f"outsider-{request.user_id}")
        else:
            name = raw_name.title()
            slug = slugify(name)
        now = now_utc()

        # Check if this person already exists as an outsider
        existing = await db.persons.find_one({"slug": slug, "source": "self_boosted"})

        if existing:
            person_id = existing["_id"]
            # Update social links if provided
            update_fields = {"updated_at": now}
            if request.social_links:
                clean_social = {}
                for platform in ["instagram", "tiktok", "x"]:
                    raw = getattr(request.social_links, platform, None) or ""
                    cleaned = _clean_username(raw)
                    # R1: a malformed social handle must NEVER block a paid boost. Silently
                    # drop the invalid handle and still create/update the boost; the user can
                    # add or correct the link later via the account edit screen.
                    if cleaned and _validate_social_username(platform, cleaned):
                        clean_social[platform] = cleaned
                update_fields["social_links"] = clean_social
            if request.email:
                update_fields["email"] = request.email
            await db.persons.update_one({"_id": person_id}, {"$set": update_fields})
        else:
            # Check if a celebrity with this name exists
            celebrity = await db.persons.find_one({"slug": slug, "source": {"$ne": "self_boosted"}})
            if celebrity:
                raise HTTPException(status_code=400, detail=f"{name} is already a public personality in our database.")

            # Create new outsider person
            social = {}
            if request.social_links:
                for platform in ["instagram", "tiktok", "x"]:
                    raw = getattr(request.social_links, platform, None) or ""
                    cleaned = _clean_username(raw)
                    # R1: a malformed social handle must NEVER block a paid boost. Silently
                    # drop the invalid handle and still create the boost; the user can add or
                    # correct the link later via the account edit screen.
                    if cleaned and _validate_social_username(platform, cleaned):
                        social[platform] = cleaned

            person_doc = {
                "name": name,
                "slug": slug,
                "name_provisional": name_provisional,
                "category": "other",
                "approved": True,
                "created_at": now,
                "updated_at": now,
                "score": 50.0,
                "likes": 0,
                "dislikes": 0,
                "total_votes": 0,
                "source": "self_boosted",
                "social_links": social,
                "email": request.email or "",
                # Auto-boost counts as a positive signal — surface an up arrow at creation.
                "vote_momentum": "up",
            }

            result = await db.persons.insert_one(person_doc)
            person_id = result.inserted_id

        # Check if there's already an active boost for this person
        existing_boost = await db.active_boosts.find_one({
            "person_id": person_id,
            "end_time": {"$gt": now},
        })

        if existing_boost:
            # Extend the existing boost from its current end_time
            new_end = existing_boost["end_time"] + timedelta(hours=tier_info["duration_hours"])
            # Upgrade position if new tier is golden
            new_position = tier_info["position"]
            if existing_boost.get("position") == "top" and new_position != "top":
                new_position = "top"  # Keep golden position

            # B5: Replace old boost — mark as replaced and create new one
            await db.active_boosts.update_one(
                {"_id": existing_boost["_id"]},
                {"$set": {
                    "status": "replaced",
                    "replaced_at": now,
                    "replaced_by_tier": request.tier,
                    "end_time": now,  # Immediately expire old boost
                    "updated_at": now,
                }}
            )
            # Create new boost with fresh timing
            end_time = now + timedelta(hours=tier_info["duration_hours"])
            replace_doc = {
                "person_id": person_id,
                "person_name": name,
                "user_id": request.user_id,
                "email": request.email or "",
                "tier": request.tier,
                "position": new_position,
                "country": getattr(request, 'country', None),
                "start_time": now,
                "end_time": end_time,
                "reminder_sent": False,
                "created_at": now,
                "updated_at": now,
                "replaces": str(existing_boost["_id"]),
                # Idempotency key (R2): store the payment receipt so a re-delivery of the
                # same transaction is detected and short-circuited at the top of the handler.
                "receipt": request.receipt or "",
            }
            replace_result = await db.active_boosts.insert_one(replace_doc)
            active_boost_id = str(replace_result.inserted_id)
        else:
            # Create new active boost
            end_time = now + timedelta(hours=tier_info["duration_hours"])
            boost_doc = {
                "person_id": person_id,
                "person_name": name,
                "user_id": request.user_id,
                "email": request.email or "",
                "tier": request.tier,
                "position": tier_info["position"],
                "country": getattr(request, 'country', None),  # Country for geo-restriction
                "start_time": now,
                "end_time": end_time,
                "reminder_sent": False,
                "created_at": now,
                "updated_at": now,
                # Idempotency key (R2): store the payment receipt so a re-delivery of the
                # same transaction is detected and short-circuited at the top of the handler.
                "receipt": request.receipt or "",
            }
            insert_result = await db.active_boosts.insert_one(boost_doc)
            active_boost_id = str(insert_result.inserted_id)

        # Record transaction
        await db.credit_transactions.insert_one({
            "user_id": request.user_id,
            "type": "purchase",
            "pack": request.tier,
            "price": tier_info["price"],
            "person_name": name,
            "description": f"{tier_info['name']} for '{name}' - {tier_info['description']}",
            "timestamp": now,
            "status": "completed",
            "receipt": request.receipt or "",
            "platform": request.platform or "",
        })

        # Send confirmation email if email provided
        if request.email:
            try:
                from email_sender import send_welcome, send_booster_confirmation
                duration_text = "1 hour" if tier_info["duration_hours"] == 1 else \
                    "24 hours" if tier_info["duration_hours"] == 24 else "1 week"
                is_golden = (request.tier == "golden_booster")

                # Check if this is the user's first purchase → Welcome email
                prev_purchases = await db.credit_transactions.count_documents({
                    "user_id": request.user_id,
                    "type": "purchase",
                    "status": "completed",
                })
                # prev_purchases includes the one we just inserted above, so first purchase = 1
                if prev_purchases <= 1:
                    await send_welcome(db, email_service, request.email, request.user_id, name)
                else:
                    await send_booster_confirmation(
                        db, email_service, request.email, request.user_id,
                        name, tier_info["name"], duration_text, is_golden=is_golden
                    )
            except Exception as email_err:
                logger.warning(f"Failed to send confirmation email: {email_err}")

        # Auto-disable seed Outsiders if real outsider count crosses thresholds
        boost_country = getattr(request, 'country', None)
        if boost_country:
            try:
                from seed_outsiders import auto_disable_seeds_for_country
                disable_result = await auto_disable_seeds_for_country(db, boost_country)
                if disable_result.get("disabled", 0) > 0:
                    logger.info(f"🌱 Auto-disabled {disable_result['disabled']} seed(s) in {boost_country} "
                               f"({disable_result['real_count']} real outsiders, {disable_result['remaining']} seeds remaining)")
            except Exception as seed_err:
                logger.warning(f"Seed auto-disable check failed: {seed_err}")

        success_msg = f"🎉 {tier_info['name']} activated! '{name}' is now in the Outsiders ranking."
        if tier_info["position"] == "top":
            success_msg += " With priority placement and Home page rotation as Outsider of the Day."

        return {
            "success": True,
            "person_id": str(person_id),
            "boost_id": active_boost_id,
            "person_name": name,
            "name_provisional": name_provisional,
            "tier": request.tier,
            "tier_name": tier_info["name"],
            "price": tier_info["price"],
            "end_time": end_time.isoformat(),
            "duration_hours": tier_info["duration_hours"],
            "position": tier_info["position"],
            "message": success_msg,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Boost myself error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/boost-myself/extend")
async def extend_boost(request: ExtendBoostRequest):
    """Extend an existing boost"""
    try:
        # ── Ban enforcement ──
        await _check_device_not_banned(request.user_id)
        
        if request.tier not in BOOSTER_TIERS:
            raise HTTPException(status_code=400, detail="Invalid booster tier")

        tier_info = BOOSTER_TIERS[request.tier]
        now = now_utc()

        try:
            boost_oid = ObjectId(request.boost_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid boost ID")

        boost = await db.active_boosts.find_one({"_id": boost_oid, "user_id": request.user_id})
        if not boost:
            raise HTTPException(status_code=404, detail="Boost not found")

        # Extend from current end_time or now (whichever is later)
        base_time = max(boost["end_time"], now)
        new_end = base_time + timedelta(hours=tier_info["duration_hours"])

        new_position = tier_info["position"]
        if boost.get("position") == "top" or new_position == "top":
            new_position = "top"

        await db.active_boosts.update_one(
            {"_id": boost_oid},
            {"$set": {
                "end_time": new_end,
                "tier": request.tier,
                "position": new_position,
                "reminder_sent": False,
                "updated_at": now,
            }}
        )

        # Record transaction
        await db.credit_transactions.insert_one({
            "user_id": request.user_id,
            "type": "purchase",
            "pack": request.tier,
            "price": tier_info["price"],
            "person_name": boost["person_name"],
            "description": f"Extended {tier_info['name']} for '{boost['person_name']}'",
            "timestamp": now,
            "status": "completed",
        })

        # Send renewal email
        if boost.get("email"):
            try:
                duration_text = "1 hour" if tier_info["duration_hours"] == 1 else \
                    "24 hours" if tier_info["duration_hours"] == 24 else "1 week"
                html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #0F2F22; color: #EAEAEA;">
                    <h1 style="color: #FFD700; text-align: center;">🔄 Boost Extended!</h1>
                    <div style="background: #1C3A2C; border-radius: 12px; padding: 24px; margin: 20px 0; border: 2px solid #2E6148;">
                        <h2 style="color: #EAEAEA; margin-top: 0;">Hello {boost['person_name']}!</h2>
                        <p style="color: #C9D8D2;">Your boost has been extended with a <strong style="color: #FFD700;">{tier_info['name']}</strong>.</p>
                        <p style="color: #C9D8D2;">New expiration: <strong>{new_end.strftime('%B %d, %Y at %H:%M UTC')}</strong></p>
                    </div>
                </div>
                """
                await email_service.send_email(boost["email"], f"🔄 Your boost has been extended!", html)
            except Exception as email_err:
                logger.warning(f"Failed to send extension email: {email_err}")

        return {
            "success": True,
            "new_end_time": new_end.isoformat(),
            "tier": request.tier,
            "message": f"Boost extended until {new_end.strftime('%B %d at %H:%M UTC')}!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extend boost error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin Authentication --------------------

import secrets

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or ""

# Hash the password at startup for bcrypt comparison (timing-attack resistant)
_ADMIN_PASSWORD_HASH = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()) if ADMIN_PASSWORD else b""

def _require_admin_password(password: str):
    """
    Verify admin password using bcrypt. Raises 503 if not configured, 403 if incorrect.
    SECURITY: Uses bcrypt.checkpw() to resist timing attacks.
    """
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Admin authentication not configured on this server"
        )
    if not bcrypt.checkpw(password.encode("utf-8"), _ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=403, detail="Invalid admin password")


def _get_admin_password_from_header(request: Request) -> str:
    """
    Extract admin password from X-Admin-Password header.
    Falls back to deprecated query param 'password' for backward compatibility.
    SECURITY: Header is preferred because query params are logged in server logs and proxies.
    """
    header_pw = request.headers.get("X-Admin-Password", "")
    if header_pw:
        return header_pw
    # Backward compat: also check query param (deprecated, will be removed in V2)
    return request.query_params.get("password", "")


def _require_admin_auth(request: Request, body_password: str = ""):
    """
    Unified admin auth: accepts X-Admin-Token header, X-Admin-Password header,
    or legacy body/query password.
    Priority: X-Admin-Token > X-Admin-Password header > body password > query param.
    """
    # Try token first
    token = request.headers.get("X-Admin-Token", "")
    if token and verify_admin_token(token):
        return
    # Then try header password
    header_pw = request.headers.get("X-Admin-Password", "")
    if header_pw:
        _require_admin_password(header_pw)
        return
    # Then try body password (POST endpoints backward compat)
    if body_password:
        _require_admin_password(body_password)
        return
    # Then try query param (deprecated fallback)
    query_pw = request.query_params.get("password", "")
    if query_pw:
        _require_admin_password(query_pw)
        return
    raise HTTPException(status_code=403, detail="Admin authentication required. Use X-Admin-Password or X-Admin-Token header.")

# In-memory token store (simple approach: tokens expire after 4 hours)
_admin_tokens: dict = {}  # {token: expiry_datetime}

def _cleanup_expired_tokens():
    """Remove expired tokens from memory."""
    now = datetime.utcnow()
    expired = [t for t, exp in _admin_tokens.items() if exp < now]
    for t in expired:
        del _admin_tokens[t]

def verify_admin_token(token: str) -> bool:
    """Verify that a token is valid and not expired."""
    _cleanup_expired_tokens()
    if token in _admin_tokens:
        return _admin_tokens[token] > datetime.utcnow()
    return False

class AdminAuthRequest(BaseModel):
    password: str

class AdminAuthResponse(BaseModel):
    success: bool
    token: str = ""
    expires_in_hours: int = 4

@api_router.post("/admin/auth")
@limiter.limit("5/15minutes")
async def admin_auth(request: Request, body: AdminAuthRequest):
    """Authenticate admin and return a session token (valid 4 hours).
    SECURITY: If ADMIN_PASSWORD env var is not set, returns 503.
    Rate limited: 5 attempts per 15 minutes per IP."""
    _require_admin_password(body.password)
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    _admin_tokens[token] = datetime.utcnow() + timedelta(hours=4)
    
    logger.info("🔐 Admin session created (expires in 4h)")
    return {"success": True, "token": token, "expires_in_hours": 4}

@api_router.get("/admin/verify-token")
async def admin_verify_token(token: str = Header(None, alias="X-Admin-Token")):
    """Verify if an admin token is still valid."""
    if not token or not verify_admin_token(token):
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    return {"valid": True}

# -------------------- Admin Endpoints --------------------

class AdminBoostRequest(BaseModel):
    person_id: str
    amount: int
    type: Literal["likes", "dislikes"] = "likes"


@api_router.post("/admin/boost-votes")
async def admin_boost_votes(req: Request, request: AdminBoostRequest):
    """Admin-only: Manually add votes to any personality"""
    _require_admin_auth(req)
    try:
        person_id = ObjectId(request.person_id)
        person = await db.persons.find_one({"_id": person_id})
        
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        
        # Update votes
        if request.type == "likes":
            new_likes = person.get("likes", 0) + request.amount
            new_dislikes = person.get("dislikes", 0)
        else:
            new_likes = person.get("likes", 0)
            new_dislikes = person.get("dislikes", 0) + request.amount
        
        new_total = new_likes + new_dislikes
        new_score = (new_likes / new_total * 100) if new_total > 0 else 100.0
        
        await db.persons.update_one(
            {"_id": person_id},
            {
                "$set": {
                    "likes": new_likes,
                    "dislikes": new_dislikes,
                    "total_votes": new_total,
                    "score": new_score,
                    "updated_at": now_utc(),
                }
            }
        )
        
        # Add tick for chart
        await db.person_ticks.insert_one({
            "person_id": person_id,
            "score": new_score,
            "created_at": now_utc()
        })
        
        return {
            "success": True,
            "person_name": person.get("name"),
            "new_likes": new_likes,
            "new_dislikes": new_dislikes,
            "new_score": new_score,
            "new_total_votes": new_total,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin boost error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin: Moderation --------------------

@api_router.delete("/admin/person/{person_id}")
async def admin_delete_person(request: Request, person_id: str):
    """Admin-only: Delete a personality completely"""
    _require_admin_auth(request)
    try:
        obj_id = ObjectId(person_id)
        person = await db.persons.find_one({"_id": obj_id})
        
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        
        person_name = person.get("name")

        # Delete the person
        await db.persons.delete_one({"_id": obj_id})

        # Delete all their ticks
        await db.person_ticks.delete_many({"person_id": obj_id})

        # Anti-ghost: register in the blocklist so the Wikipedia job / seeds /
        # imports / approvals can never silently re-create this personality.
        blocked = await add_person_to_blocklist(
            name=person_name or "",
            slug=person.get("slug", ""),
            wikidata_id=person.get("wikidata_id", ""),
        )
        logger.info(f"🚫 [Anti-ghost] Blocklisted on delete: {blocked}")

        return {
            "success": True,
            "message": f"'{person_name}' has been deleted permanently",
            "person_name": person_name,
            "blocklisted": blocked,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin delete person error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/person/{person_id}/reset")
async def admin_reset_person(request: Request, person_id: str):
    """Admin-only: Reset a personality's score to 50 (neutral)"""
    _require_admin_auth(request)
    try:
        obj_id = ObjectId(person_id)
        person = await db.persons.find_one({"_id": obj_id})
        
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        
        person_name = person.get("name")
        
        # Reset to neutral state
        await db.persons.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "likes": 0,
                    "dislikes": 0,
                    "total_votes": 0,
                    "score": 50.0,
                    "updated_at": now_utc(),
                }
            }
        )
        
        # Add reset tick
        await db.person_ticks.insert_one({
            "person_id": obj_id,
            "score": 50.0,
            "created_at": now_utc()
        })
        
        return {
            "success": True,
            "message": f"'{person_name}' has been reset to neutral (50)",
            "person_name": person_name,
            "new_score": 50.0,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin reset person error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin: Activity Feed --------------------

# ── Admin Audit Log helper ──

async def _log_admin_action(action: str, target: str, details: dict = None, token: str = "", success: bool = True):
    """Record every admin action for traceability."""
    await db.admin_audit_log.insert_one({
        "action": action,
        "target": target,
        "details": details or {},
        "token_prefix": token[:8] if token else "",
        "success": success,
        "timestamp": now_utc(),
    })


# ── Device Ban Enforcement helper ──

async def _check_device_not_banned(device_id: str):
    """
    Check if a device_id is banned. Raises HTTP 403 if banned.
    Call this at the beginning of all critical endpoints (vote, purchase, daily run).
    """
    if not device_id:
        return
    banned = await db.banned_devices.find_one({"device_id": device_id})
    if banned:
        raise HTTPException(
            status_code=403,
            detail="This device has been suspended. Contact popularoo@popularoo.com for more information."
        )


# ── Outsider Suspension check helper ──

async def _check_person_not_suspended(person: dict):
    """
    Check if a person/outsider is suspended. Raises HTTP 403 if suspended.
    Call before allowing votes or interactions with a suspended outsider.
    """
    if person and person.get("suspended"):
        raise HTTPException(
            status_code=403,
            detail="This profile is temporarily suspended. Contact popularoo@popularoo.com for more information."
        )


# ── 1. Suspend / Unsuspend Outsider ──

class SuspendRequest(BaseModel):
    reason: str = ""
    password: str

@api_router.post("/admin/outsider/{person_id}/suspend")
async def admin_suspend_outsider(req: Request, person_id: str, request: SuspendRequest):
    """Suspend an Outsider — hides them from all public lists without deleting."""
    _require_admin_auth(req)
    _require_admin_password(request.password)
    obj_id = ObjectId(person_id)
    person = await db.persons.find_one({"_id": obj_id})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    await db.persons.update_one({"_id": obj_id}, {"$set": {
        "suspended": True,
        "suspended_at": now_utc(),
        "suspended_reason": request.reason,
    }})
    # Also mark any active boost as suspended
    await db.active_boosts.update_many(
        {"person_id": obj_id, "end_time": {"$gt": now_utc()}},
        {"$set": {"suspended": True}}
    )
    await _log_admin_action("suspend_outsider", person.get("name", ""), {"reason": request.reason})
    return {"success": True, "message": f"'{person.get('name')}' suspended"}

@api_router.post("/admin/outsider/{person_id}/unsuspend")
async def admin_unsuspend_outsider(req: Request, person_id: str, request: SuspendRequest):
    """Unsuspend an Outsider — restores visibility."""
    _require_admin_auth(req)
    _require_admin_password(request.password)
    obj_id = ObjectId(person_id)
    person = await db.persons.find_one({"_id": obj_id})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    await db.persons.update_one({"_id": obj_id}, {"$unset": {
        "suspended": "",
        "suspended_at": "",
        "suspended_reason": "",
    }})
    await db.active_boosts.update_many(
        {"person_id": obj_id},
        {"$unset": {"suspended": ""}}
    )
    await _log_admin_action("unsuspend_outsider", person.get("name", ""))
    return {"success": True, "message": f"'{person.get('name')}' unsuspended"}


# ── Rename Outsider (shared core for admin + user-facing "set my name") ──

async def _apply_outsider_rename(person_id: str, new_name: str) -> dict:
    """Single mechanic for renaming an Outsider's DISPLAY NAME.

    Changes ONLY persons.name (+ clears name_provisional) and syncs the boosts'
    display copy of the name. The slug (technical identity, e.g. outsider-<user_id>)
    is intentionally NOT regenerated, to avoid duplicate-profile collisions.
    Never touches score/PI, votes, payment, or boost timing.
    Returns {old_name, new_name, person_id}. Raises HTTPException on invalid input.
    """
    cleaned = new_name.strip().title()
    if len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters")
    obj_id = ObjectId(person_id)
    person = await db.persons.find_one({"_id": obj_id})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    old_name = person.get("name", "")
    await db.persons.update_one({"_id": obj_id}, {"$set": {
        "name": cleaned,
        "name_provisional": False,
        "updated_at": now_utc(),
    }})
    # Display-only copy on boosts (history/admin/email) — not payment/score/timing.
    await db.active_boosts.update_many({"person_id": obj_id}, {"$set": {"person_name": cleaned}})
    return {"old_name": old_name, "new_name": cleaned, "person_id": person_id}


class RenameOutsiderRequest(BaseModel):
    new_name: str

@api_router.post("/admin/outsider/{person_id}/rename")
async def admin_rename_outsider(req: Request, person_id: str, request: RenameOutsiderRequest):
    """Admin: correct an Outsider's display name (e.g. a user who paid without a name).
    Slug is left untouched; score/votes/payment are not affected."""
    _require_admin_auth(req)
    result = await _apply_outsider_rename(person_id, request.new_name)
    await _log_admin_action("rename_outsider", result["new_name"],
                            {"person_id": person_id, "old_name": result["old_name"]})
    return {"success": True, **result}


class SetMyNameRequest(BaseModel):
    user_id: str
    person_id: str
    new_name: str

@api_router.post("/me/outsider/set-name")
async def set_my_outsider_name(request: SetMyNameRequest):
    """User-facing: set the display name of one's OWN freshly-purchased Outsider.

    Ownership check (belt + suspenders):
      1. the caller's user_id must own an Outsider boost (resolves the person_id server-side);
      2. the client-supplied person_id must match that boost → otherwise 403.
    Reuses the same _apply_outsider_rename mechanic as admin: slug is NOT regenerated,
    and score/PI, votes, payment and boost timing are never touched.
    """
    now = now_utc()
    boost = await db.active_boosts.find_one(
        {"user_id": request.user_id, "end_time": {"$gt": now}}, sort=[("start_time", -1)]
    ) or await db.active_boosts.find_one(
        {"user_id": request.user_id}, sort=[("start_time", -1)]
    )
    if not boost:
        raise HTTPException(status_code=404, detail="No outsider profile for this user")
    if str(boost.get("person_id")) != request.person_id:
        raise HTTPException(status_code=403, detail="This profile does not belong to you")
    result = await _apply_outsider_rename(str(boost["person_id"]), request.new_name)
    return {"success": True, **result}


# ── 2. Ban device_id ──

class BanDeviceRequest(BaseModel):
    device_id: str
    reason: str = ""
    password: str

@api_router.post("/admin/ban-device")
async def admin_ban_device(req: Request, request: BanDeviceRequest):
    """Ban a device_id from voting and purchasing."""
    _require_admin_auth(req)
    _require_admin_password(request.password)
    
    await db.banned_devices.update_one(
        {"device_id": request.device_id},
        {"$set": {
            "device_id": request.device_id,
            "reason": request.reason,
            "banned_at": now_utc(),
            "banned_by_admin": request.password[:4] + "****",  # Partial trace for audit
        }},
        upsert=True,
    )
    await _log_admin_action("ban_device", request.device_id, {"reason": request.reason})
    return {"success": True, "message": f"Device '{request.device_id}' banned"}

@api_router.post("/admin/unban-device/{device_id}")
async def admin_unban_device(device_id: str, request: SuspendRequest):
    """Unban a device_id. Body: {password}"""
    _require_admin_password(request.password)
    
    result = await db.banned_devices.delete_one({"device_id": device_id})
    await _log_admin_action("unban_device", device_id)
    return {"success": True, "deleted": result.deleted_count > 0}

@api_router.get("/admin/banned-devices")
@limiter.limit("10/15minutes")
async def admin_list_banned_devices(request: Request):
    """List all banned devices."""
    _require_admin_auth(request)
    
    devices = await db.banned_devices.find({}).sort("banned_at", -1).to_list(200)
    return [
        {
            "device_id": d.get("device_id"),
            "reason": d.get("reason", ""),
            "banned_at": d.get("banned_at").isoformat() if d.get("banned_at") else None,
        }
        for d in devices
    ]


# ── 3. Grant Booster manually (commercial gesture) ──

class GrantBoosterRequest(BaseModel):
    device_id: str
    name: str
    tier: str  # booster, super_booster, golden_booster
    duration_hours: int = 0  # 0 = use tier default
    email: str = ""  # Optional: email for confirmation
    password: str

@api_router.post("/admin/grant-booster")
async def admin_grant_booster(req: Request, request: GrantBoosterRequest):
    """Create an active Booster without IAP payment (commercial gesture)."""
    _require_admin_auth(req)
    _require_admin_password(request.password)
    
    TIER_DEFAULTS = {
        "booster": {"name": "Booster", "hours": 1, "position": "normal"},
        "super_booster": {"name": "Super Booster", "hours": 24, "position": "normal"},
        "golden_booster": {"name": "Golden Booster", "hours": 168, "position": "top"},
    }
    if request.tier not in TIER_DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Use: {list(TIER_DEFAULTS.keys())}")
    
    tier_info = TIER_DEFAULTS[request.tier]
    duration = request.duration_hours if request.duration_hours > 0 else tier_info["hours"]
    now = now_utc()
    
    # Find or create the person
    person = await db.persons.find_one({"name": {"$regex": f"^{request.name}$", "$options": "i"}, "source": "self_boosted"})
    if not person:
        # Create the outsider profile
        slug = request.name.lower().replace(" ", "-").replace("'", "")
        person_doc = {
            "name": request.name,
            "slug": slug,
            "category": "other",
            "approved": True,
            "source": "self_boosted",
            "score": 50.0,
            "likes": 0,
            "dislikes": 0,
            "superlikes": 0,
            "total_votes": 0,
            "popularoo_index": 15,
            "created_at": now,
            "updated_at": now,
            "vote_momentum": "up",
        }
        result = await db.persons.insert_one(person_doc)
        person_id = result.inserted_id
    else:
        person_id = person["_id"]

    # Create the active boost
    boost_doc = {
        "person_id": person_id,
        "person_name": request.name,
        "user_id": request.device_id,
        "email": request.email,
        "tier": request.tier,
        "position": tier_info["position"],
        "country": "FR",
        "start_time": now,
        "end_time": now + timedelta(hours=duration),
        "created_at": now,
        "updated_at": now,
        "source": "admin_grant",
        "granted_manually": True,
    }
    boost_result = await db.active_boosts.insert_one(boost_doc)
    
    # Send confirmation email if email provided
    if request.email:
        try:
            from email_sender import send_booster_confirmation
            duration_str = f"{duration} hours" if duration < 48 else f"{duration // 24} days"
            await send_booster_confirmation(
                db, email_service, request.email, request.device_id,
                request.name, tier_info["name"], duration_str,
                is_golden=(request.tier == "golden_booster"),
            )
        except Exception as e:
            logger.warning(f"Failed to send grant email: {e}")
    
    await _log_admin_action("grant_booster", request.name, {
        "device_id": request.device_id,
        "tier": request.tier,
        "duration_hours": duration,
        "email_sent": bool(request.email),
    })
    return {
        "success": True,
        "boost_id": str(boost_result.inserted_id),
        "tier": request.tier,
        "duration_hours": duration,
        "expires_at": (now + timedelta(hours=duration)).isoformat(),
    }


# ── 4. Expire Booster manually ──

class ExpireBoosterRequest(BaseModel):
    password: str

@api_router.post("/admin/expire-booster/{boost_id}")
async def admin_expire_booster(req: Request, boost_id: str, request: ExpireBoosterRequest):
    """Force-expire a Booster immediately (emergency revocation)."""
    _require_admin_auth(req)
    _require_admin_password(request.password)
    
    obj_id = ObjectId(boost_id)
    boost = await db.active_boosts.find_one({"_id": obj_id})
    if not boost:
        raise HTTPException(status_code=404, detail="Boost not found")
    
    now = now_utc()
    await db.active_boosts.update_one({"_id": obj_id}, {"$set": {
        "end_time": now,
        "expired_by_admin": True,
        "expired_at": now,
    }})
    
    # Send expiration email if email exists on the boost
    email = boost.get("email", "")
    if email:
        try:
            from email_sender import send_booster_expiration
            tier = boost.get("tier", "booster")
            tier_name = BOOSTER_TIERS.get(tier, {}).get("name", "Booster")
            person_name = boost.get("person_name", "User")
            await send_booster_expiration(
                db, email_service, email, boost.get("user_id", ""),
                person_name, tier_name, "0 hours",
                total_votes=0, best_rank=0, daily_runs_count=0,
            )
        except Exception as e:
            logger.warning(f"Failed to send admin expiration email: {e}")
    
    await _log_admin_action("expire_booster", boost.get("person_name", ""), {
        "boost_id": boost_id,
        "original_end_time": boost.get("end_time").isoformat() if boost.get("end_time") else None,
        "email_sent": bool(email),
    })
    return {"success": True, "message": f"Booster for '{boost.get('person_name')}' expired immediately"}


# ── 5. Activity feed with device_id filter ──

@api_router.get("/admin/activity/recent")
@limiter.limit("10/15minutes")
async def admin_get_recent_activity(request: Request, device_id: Optional[str] = None):
    """Admin-only: Get recent activity. Optional ?device_id=xxx to filter by user."""
    _require_admin_auth(request)
    try:
        # Last 50 person additions (last 7 days)
        week_ago = now_utc() - timedelta(days=7)
        people_query = {"created_at": {"$gte": week_ago}}
        purchases_query: dict = {"type": "purchase"}
        uses_query: dict = {"type": "use"}
        
        # Filter by device_id if provided
        if device_id:
            purchases_query["user_id"] = device_id
            uses_query["user_id"] = device_id
        
        recent_people = await db.persons.find(
            people_query,
            {"name": 1, "source": 1, "created_at": 1, "score": 1}
        ).sort("created_at", -1).limit(50).to_list(50)
        
        # Last 50 credit transactions
        recent_purchases = await db.credit_transactions.find(
            purchases_query,
            {"user_id": 1, "amount": 1, "description": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        # Last 50 credit uses
        recent_uses = await db.credit_transactions.find(
            uses_query,
            {"user_id": 1, "description": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        return {
            "recent_people": [
                {
                    "id": str(p["_id"]),
                    "name": p.get("name"),
                    "source": p.get("source", "seed"),
                    "score": p.get("score", 50),
                    "created_at": p.get("created_at").isoformat() if p.get("created_at") else None,
                }
                for p in recent_people
            ],
            "recent_purchases": [
                {
                    "user_id": t.get("user_id"),
                    "amount": t.get("amount"),
                    "description": t.get("description"),
                    "timestamp": t.get("timestamp").isoformat() if t.get("timestamp") else None,
                }
                for t in recent_purchases
            ],
            "recent_uses": [
                {
                    "user_id": t.get("user_id"),
                    "description": t.get("description"),
                    "timestamp": t.get("timestamp").isoformat() if t.get("timestamp") else None,
                }
                for t in recent_uses
            ],
        }
        
    except Exception as e:
        logger.error(f"Admin activity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin: Advanced Search --------------------

# ── 6. Audit Log consultation ──

@api_router.get("/admin/audit-log")
@limiter.limit("10/15minutes")
async def admin_get_audit_log(
    request: Request,
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0),
    action_type: Optional[str] = Query(default=None, description="Filter by action type"),
    from_date: Optional[str] = Query(default=None, alias="from", description="Start date ISO format"),
    to_date: Optional[str] = Query(default=None, alias="to", description="End date ISO format"),
    admin_token: Optional[str] = Query(default=None, description="Filter by admin token prefix"),
):
    """Get admin audit log with pagination and filters."""
    _require_admin_auth(request)
    
    # Build filter
    query: Dict[str, Any] = {}
    if action_type:
        query["action"] = action_type
    if admin_token:
        query["token_prefix"] = {"$regex": f"^{admin_token}"}
    if from_date or to_date:
        date_filter: Dict[str, Any] = {}
        if from_date:
            try:
                date_filter["$gte"] = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        if to_date:
            try:
                date_filter["$lte"] = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        if date_filter:
            query["timestamp"] = date_filter
    
    total = await db.admin_audit_log.count_documents(query)
    logs = await db.admin_audit_log.find(query).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "logs": [
            {
                "action": log.get("action"),
                "target": log.get("target"),
                "details": log.get("details", {}),
                "token_prefix": log.get("token_prefix", ""),
                "success": log.get("success", True),
                "timestamp": log.get("timestamp").isoformat() if log.get("timestamp") else None,
            }
            for log in logs
        ],
    }


# ────────────────────────────────────────────────────────────────

# ── 7. Selective Vote Invalidation ──

class InvalidateVotesRequest(BaseModel):
    password: str
    device_id: Optional[str] = None  # If set, only invalidate votes from this device
    from_date: Optional[str] = None  # ISO format, start of period
    to_date: Optional[str] = None    # ISO format, end of period

@api_router.post("/admin/person/{person_id}/invalidate-votes")
async def admin_invalidate_votes(req: Request, person_id: str, request: InvalidateVotesRequest):
    """
    Selective vote invalidation for a person.
    - No params (besides password): full reset (like reset)
    - device_id: only invalidate votes from that device
    - from/to: only invalidate votes in that time range
    - Both: combined filter
    """
    _require_admin_auth(req)
    _require_admin_password(request.password)
    
    try:
        obj_id = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")
    
    person = await db.persons.find_one({"_id": obj_id})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # If no selective params → full reset (existing behavior)
    if not request.device_id and not request.from_date and not request.to_date:
        await db.persons.update_one({"_id": obj_id}, {"$set": {
            "likes": 0, "dislikes": 0, "superlikes": 0,
            "total_votes": 0, "score": 50.0, "updated_at": now_utc(),
        }})
        await db.votes.delete_many({"person_id": obj_id})
        await db.superlike_votes.delete_many({"person_id": obj_id})
        await _log_admin_action("invalidate_votes_full", person.get("name", ""), {
            "person_id": person_id,
        })
        return {"success": True, "mode": "full_reset", "message": f"All votes reset for '{person.get('name')}'"}
    
    # Build selective filter
    vote_filter: Dict[str, Any] = {"person_id": obj_id}
    if request.device_id:
        vote_filter["device_id"] = request.device_id
    
    date_filter: Dict[str, Any] = {}
    if request.from_date:
        try:
            date_filter["$gte"] = datetime.fromisoformat(request.from_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format (use ISO)")
    if request.to_date:
        try:
            date_filter["$lte"] = datetime.fromisoformat(request.to_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format (use ISO)")
    if date_filter:
        vote_filter["created_at"] = date_filter
    
    # Count and delete matching votes
    deleted_votes = await db.votes.delete_many(vote_filter)
    deleted_superlikes = await db.superlike_votes.delete_many(vote_filter)
    
    total_deleted = deleted_votes.deleted_count + deleted_superlikes.deleted_count
    
    # Recalculate person's vote counters from remaining votes
    remaining_likes = await db.votes.count_documents({"person_id": obj_id, "value": 1})
    remaining_dislikes = await db.votes.count_documents({"person_id": obj_id, "value": -1})
    remaining_superlikes = await db.superlike_votes.count_documents({"person_id": obj_id})
    remaining_total = remaining_likes + remaining_dislikes + remaining_superlikes
    
    # Recalculate score
    if remaining_total > 0:
        new_score = 50.0 + ((remaining_likes + remaining_superlikes * 5 - remaining_dislikes) / remaining_total) * 50
        new_score = max(0.0, min(100.0, new_score))
    else:
        new_score = 50.0
    
    await db.persons.update_one({"_id": obj_id}, {"$set": {
        "likes": remaining_likes,
        "dislikes": remaining_dislikes,
        "superlikes": remaining_superlikes,
        "total_votes": remaining_total,
        "score": new_score,
        "updated_at": now_utc(),
    }})
    
    await _log_admin_action("invalidate_votes_selective", person.get("name", ""), {
        "person_id": person_id,
        "device_id": request.device_id,
        "from_date": request.from_date,
        "to_date": request.to_date,
        "votes_deleted": total_deleted,
    })
    
    return {
        "success": True,
        "mode": "selective",
        "votes_deleted": total_deleted,
        "remaining_total": remaining_total,
        "new_score": round(new_score, 2),
        "message": f"{total_deleted} votes invalidated for '{person.get('name')}'",
    }


# ── 8 & 9. Extended Stats + Lifetime Revenue ──

@api_router.get("/admin/stats")
@limiter.limit("10/15minutes")
async def get_admin_stats(request: Request):
    """Get global statistics for admin dashboard — extended with 7d/30d users and lifetime revenue."""
    _require_admin_auth(request)
    try:
        now = now_utc()
        yesterday = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Total people
        total_people = await db.persons.count_documents({})
        
        # Total votes across all people
        pipeline_votes = [
            {"$group": {"_id": None, "total_votes": {"$sum": "$total_votes"}, "total_likes": {"$sum": "$likes"}, "total_dislikes": {"$sum": "$dislikes"}}}
        ]
        vote_result = await db.persons.aggregate(pipeline_votes).to_list(1)
        total_votes = vote_result[0]["total_votes"] if vote_result else 0
        
        # Active users 24h
        active_24h_pipeline = [
            {"$match": {"timestamp": {"$gte": yesterday}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"}
        ]
        active_24h_result = await db.credit_transactions.aggregate(active_24h_pipeline).to_list(1)
        active_users_24h = active_24h_result[0]["count"] if active_24h_result else 0
        
        # Active users 7d
        active_7d_pipeline = [
            {"$match": {"timestamp": {"$gte": week_ago}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"}
        ]
        active_7d_result = await db.credit_transactions.aggregate(active_7d_pipeline).to_list(1)
        active_users_7d = active_7d_result[0]["count"] if active_7d_result else 0
        
        # Active users 30d
        active_30d_pipeline = [
            {"$match": {"timestamp": {"$gte": month_ago}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"}
        ]
        active_30d_result = await db.credit_transactions.aggregate(active_30d_pipeline).to_list(1)
        active_users_30d = active_30d_result[0]["count"] if active_30d_result else 0
        
        # Revenue 24h — by actual tier pricing
        TIER_PRICES = {"booster": 0.99, "super_booster": 9.99, "golden_booster": 49.99}
        
        revenue_24h_pipeline = [
            {"$match": {"created_at": {"$gte": yesterday}, "source": {"$ne": "admin_grant"}}},
            {"$group": {"_id": "$tier", "count": {"$sum": 1}}},
        ]
        revenue_24h_data = await db.active_boosts.aggregate(revenue_24h_pipeline).to_list(10)
        revenue_24h = sum(TIER_PRICES.get(r["_id"], 0.99) * r["count"] for r in revenue_24h_data)
        
        # Revenue 24h breakdown
        revenue_24h_breakdown = {r["_id"]: {"count": r["count"], "revenue": round(TIER_PRICES.get(r["_id"], 0.99) * r["count"], 2)} for r in revenue_24h_data}
        
        # Revenue TOTAL LIFETIME — by tier
        revenue_lifetime_pipeline = [
            {"$match": {"source": {"$ne": "admin_grant"}}},
            {"$group": {"_id": "$tier", "count": {"$sum": 1}}},
        ]
        revenue_lifetime_data = await db.active_boosts.aggregate(revenue_lifetime_pipeline).to_list(10)
        revenue_total_lifetime = sum(TIER_PRICES.get(r["_id"], 0.99) * r["count"] for r in revenue_lifetime_data)
        
        # Lifetime breakdown by tier
        revenue_lifetime_breakdown = {
            r["_id"]: {"count": r["count"], "revenue": round(TIER_PRICES.get(r["_id"], 0.99) * r["count"], 2)}
            for r in revenue_lifetime_data
        }
        
        # New people added in 24h
        new_people_24h = await db.persons.count_documents({"created_at": {"$gte": yesterday}})
        
        return {
            "total_people": total_people,
            "total_votes": total_votes,
            "active_users_24h": active_users_24h,
            "active_users_7d": active_users_7d,
            "active_users_30d": active_users_30d,
            "revenue_24h": f"{revenue_24h:.2f}",
            "revenue_24h_breakdown": revenue_24h_breakdown,
            "revenue_total_lifetime": f"{revenue_total_lifetime:.2f}",
            "revenue_lifetime_breakdown": revenue_lifetime_breakdown,
            "new_people_24h": new_people_24h,
        }
        
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/search")
async def admin_search_people(
    request: Request,
    q: Optional[str] = None,
    category: Optional[Category] = None,
    source: Optional[str] = None,
    sort_by: str = "score",  # score, votes, name, date
    limit: int = 50
):
    """Admin-only: Advanced search with filters"""
    _require_admin_auth(request)
    try:
        # Build query
        query = {}
        
        if q:
            # Match by name OR email — admin needs to find a nameless "Outsider" by the
            # email entered at purchase. Name search behaviour is preserved (still matches).
            query["$or"] = [
                {"name":  {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}},
            ]

        if category:
            query["category"] = category
        
        if source and source in ["seed", "user_added", "self_boosted"]:
            query["source"] = source
        
        # Sort mapping
        sort_field = {
            "score": ("score", -1),
            "votes": ("total_votes", -1),
            "name": ("name", 1),
            "date": ("created_at", -1),
        }.get(sort_by, ("score", -1))
        
        # Execute search
        results = await db.persons.find(query).sort(*sort_field).limit(limit).to_list(limit)

        now = now_utc()
        enriched = []
        for p in results:
            # Additive: surface the active boost (tier + time left) so admin sees what
            # they're renaming and whether the boost is still live. Read-only lookup —
            # does not affect filtering or sorting.
            boost = await db.active_boosts.find_one(
                {"person_id": p["_id"], "end_time": {"$gt": now}},
                sort=[("start_time", -1)],
            )
            tier = boost.get("tier") if boost else None
            hours_remaining = (
                round(max(0, (boost["end_time"] - now).total_seconds() / 3600), 1) if boost else 0
            )
            enriched.append({
                "id": str(p["_id"]),
                "name": p.get("name"),
                "email": p.get("email", ""),
                "category": p.get("category", "other"),
                "source": p.get("source", "seed"),
                "score": p.get("score", 50),
                "likes": p.get("likes", 0),
                "dislikes": p.get("dislikes", 0),
                "total_votes": p.get("total_votes", 0),
                "created_at": p.get("created_at").isoformat() if p.get("created_at") else None,
                "boost_active": bool(boost),
                "tier": tier,
                "tier_name": BOOSTER_TIERS.get(tier, {}).get("name") if tier else None,
                "hours_remaining": hours_remaining,
            })
        return enriched
        
    except Exception as e:
        logger.error(f"Admin search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin: Settings --------------------

class AppSettings(BaseModel):
    allow_user_additions: bool = True
    booster_price: float = 0.99
    super_booster_price: float = 4.99
    booster_votes: int = 100
    super_booster_votes: int = 1000
    maintenance_mode: bool = False


@api_router.get("/admin/settings")
async def admin_get_settings(request: Request):
    """Admin-only: Get app settings"""
    _require_admin_auth(request)
    try:
        settings = await db.app_settings.find_one({"_id": "global"})
        
        if not settings:
            # Create default settings
            default_settings = {
                "_id": "global",
                "allow_user_additions": True,
                "booster_price": 0.99,
                "super_booster_price": 4.99,
                "booster_votes": 100,
                "super_booster_votes": 1000,
                "maintenance_mode": False,
                "updated_at": now_utc(),
            }
            await db.app_settings.insert_one(default_settings)
            settings = default_settings
        
        return {
            "allow_user_additions": settings.get("allow_user_additions", True),
            "booster_price": settings.get("booster_price", 0.99),
            "super_booster_price": settings.get("super_booster_price", 4.99),
            "booster_votes": settings.get("booster_votes", 100),
            "super_booster_votes": settings.get("super_booster_votes", 1000),
            "maintenance_mode": settings.get("maintenance_mode", False),
        }
        
    except Exception as e:
        logger.error(f"Admin get settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/settings")
async def admin_update_settings(request: Request, settings: AppSettings):
    """Admin-only: Update app settings"""
    _require_admin_auth(request)
    try:
        await db.app_settings.update_one(
            {"_id": "global"},
            {
                "$set": {
                    "allow_user_additions": settings.allow_user_additions,
                    "booster_price": settings.booster_price,
                    "super_booster_price": settings.super_booster_price,
                    "booster_votes": settings.booster_votes,
                    "super_booster_votes": settings.super_booster_votes,
                    "maintenance_mode": settings.maintenance_mode,
                    "updated_at": now_utc(),
                }
            },
            upsert=True
        )
        
        return {
            "success": True,
            "message": "Settings updated successfully",
            "settings": settings.dict(),
        }
        
    except Exception as e:
        logger.error(f"Admin update settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Google Trends Integration --------------------

@api_router.post("/admin/refresh-trends")
async def admin_refresh_trends(request: Request):
    """
    Admin-only: Manually trigger Google Trends refresh
    Fetches trending personalities and updates the database
    """
    _require_admin_auth(request)
    try:
        logger.info("Starting manual trends refresh...")
        
        # Fetch trending personalities from Google Trends
        trending_names = trends_service.get_trending_personalities(limit=20)
        
        if not trending_names:
            return {
                "success": True,
                "message": "No trending personalities found",
                "added": 0,
                "updated": 0,
            }
        
        added_count = 0
        updated_count = 0
        now = now_utc()
        
        # First, unmark all existing trending personalities
        await db.persons.update_many(
            {"is_trending": True},
            {"$set": {"is_trending": False}}
        )
        
        for name in trending_names:
            slug = slugify(name)
            
            # Check if person already exists
            existing = await db.persons.find_one({"slug": slug})
            
            if existing:
                # Mark as trending
                await db.persons.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "is_trending": True,
                            "trending_since": now,
                            "updated_at": now,
                        }
                    }
                )
                updated_count += 1
                logger.info(f"Marked as trending: {name}")
            elif await is_person_blocklisted(name_normalized=normalize_person_name(name), slug=slug):
                # Anti-ghost: a deleted personality must not re-appear via trends.
                logger.info(f"🚫 [Anti-ghost] Trends skipped blocklisted '{name}'")
                continue
            else:
                # Auto-add new trending personality
                person_doc = {
                    "name": name,
                    "slug": slug,
                    "category": "other",  # Default category
                    "approved": True,
                    "created_at": now,
                    "updated_at": now,
                    "score": 50.0,
                    "likes": 0,
                    "dislikes": 0,
                    "total_votes": 0,
                    "source": "trending",  # Mark as auto-added from trends
                    "is_trending": True,
                    "trending_since": now,
                }
                
                result = await db.persons.insert_one(person_doc)
                
                # Add initial tick
                await db.person_ticks.insert_one({
                    "person_id": result.inserted_id,
                    "score": 50.0,
                    "created_at": now
                })
                
                added_count += 1
                logger.info(f"Auto-added trending personality: {name}")
        
        # Update last refresh timestamp
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$set": {"last_trends_refresh": now}},
            upsert=True
        )
        
        return {
            "success": True,
            "message": f"Trends refreshed: {added_count} added, {updated_count} updated",
            "trending_names": trending_names,
            "added": added_count,
            "updated": updated_count,
            "timestamp": now.isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Trends refresh error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/trending-personalities")
async def get_trending_personalities():
    """Public endpoint: Get list of currently trending personalities"""
    try:
        trending = await db.persons.find(
            {"is_trending": True},
            {"name": 1, "slug": 1, "score": 1, "total_votes": 1, "trending_since": 1}
        ).sort("score", -1).limit(20).to_list(20)
        
        return [
            {
                "id": str(p["_id"]),
                "name": p.get("name"),
                "slug": p.get("slug"),
                "score": p.get("score", 50),
                "total_votes": p.get("total_votes", 0),
                "trending_since": p.get("trending_since").isoformat() if p.get("trending_since") else None,
            }
            for p in trending
        ]
        
    except Exception as e:
        logger.error(f"Get trending personalities error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/scheduler-status")
async def admin_get_scheduler_status(request: Request):
    """Admin-only: Get scheduler status and next run time"""
    _require_admin_auth(request)
    try:
        from scheduler import scheduler
        
        if not scheduler or not scheduler.running:
            return {
                "running": False,
                "message": "Scheduler is not running"
            }
        
        jobs = scheduler.get_jobs()
        job_info = []
        
        for job in jobs:
            next_run = job.next_run_time
            job_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            })
        
        # Get last refresh time
        settings = await db.app_settings.find_one({"_id": "global"})
        last_refresh = settings.get("last_trends_refresh") if settings else None
        
        return {
            "running": True,
            "jobs": job_info,
            "last_trends_refresh": last_refresh.isoformat() if last_refresh else None,
        }
        
    except Exception as e:
        logger.error(f"Scheduler status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mapping of sports personalities that need category correction
SPORTS_PERSONALITIES = [
    "Lionel Messi", "Cristiano Ronaldo", "Serena Williams", "LeBron James",
    "Kylian Mbappé", "Lewis Hamilton", "Roger Federer", "Tom Brady",
    "Michael Jordan", "Usain Bolt", "Tiger Woods", "Rafael Nadal",
    "Novak Djokovic", "Mike Tyson", "Neymar", "Mohamed Salah"
]

@api_router.post("/admin/fix-categories")
async def admin_fix_categories(request: Request):
    """Admin-only: Fix category assignments for sports personalities and Pope Francis"""
    _require_admin_auth(request)
    try:
        fixed_count = 0
        fixed_names = []
        
        # Fix sports personalities
        for name in SPORTS_PERSONALITIES:
            result = await db.persons.update_one(
                {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
                {"$set": {"category": "sport", "updated_at": now_utc()}}
            )
            if result.modified_count > 0:
                fixed_count += 1
                fixed_names.append(f"{name} → sport")
        
        # Fix Pope Francis to politics
        pope_result = await db.persons.update_one(
            {"name": {"$regex": "^Pope Francis$", "$options": "i"}},
            {"$set": {"category": "politics", "updated_at": now_utc()}}
        )
        if pope_result.modified_count > 0:
            fixed_count += 1
            fixed_names.append("Pope Francis → politics")
        
        return {
            "success": True,
            "message": f"Fixed {fixed_count} personality categories",
            "fixed_names": fixed_names,
        }
        
    except Exception as e:
        logger.error(f"Fix categories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/create-demo-outsider")
async def admin_create_demo_outsider(request: Request):
    """Admin-only: Create a demo outsider to show the feature"""
    _require_admin_auth(request)
    try:
        # Check if demo outsider already exists
        existing = await db.persons.find_one({"name": "Alex Martin", "source": "self_boosted"})
        if existing:
            # Update to zero votes if it exists
            await db.persons.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "likes": 0,
                    "dislikes": 0,
                    "total_votes": 0,
                    "score": 50.0,  # Neutral starting score
                    "updated_at": now_utc(),
                }}
            )
            return {
                "success": True,
                "message": "Demo outsider reset to zero votes",
                "outsider": {
                    "id": str(existing["_id"]),
                    "name": existing["name"],
                }
            }
        
        # Create demo outsider with ZERO votes (unknown person)
        doc = {
            "name": "Alex Martin",
            "slug": "alex-martin",
            "category": "other",
            "approved": True,
            "created_at": now_utc(),
            "updated_at": now_utc(),
            "score": 50.0,  # Neutral starting score
            "likes": 0,
            "dislikes": 0,
            "total_votes": 0,
            "source": "self_boosted",  # This makes it an "outsider"
            "vote_momentum": "up",
        }
        
        result = await db.persons.insert_one(doc)
        
        return {
            "success": True,
            "message": "Demo outsider 'Alex Martin' created with zero votes",
            "outsider": {
                "id": str(result.inserted_id),
                "name": "Alex Martin",
            }
        }
        
    except Exception as e:
        logger.error(f"Create demo outsider error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/add-missing-seeds")
async def admin_add_missing_seeds(request: Request):
    """Admin-only: Add any missing seed personalities to the database"""
    _require_admin_auth(request)
    try:
        added_count = 0
        added_names = []
        
        for p in SEED_PEOPLE:
            # Check if personality already exists
            existing = await db.persons.find_one({
                "name": {"$regex": f"^{re.escape(p['name'])}$", "$options": "i"}
            })
            
            # Anti-ghost: never re-create a blocklisted (deleted) personality.
            if not existing and await is_person_blocklisted(
                name_normalized=normalize_person_name(p["name"]), slug=slugify(p["name"])
            ):
                logger.info(f"🚫 [Anti-ghost] add-missing-seeds skipped blocklisted '{p['name']}'")
                continue

            if not existing:
                # Generate random initial votes between 8000 and 15000
                initial_votes = random.randint(8000, 15000)
                like_ratio = random.uniform(0.40, 0.80)
                initial_likes = int(initial_votes * like_ratio)
                initial_dislikes = initial_votes - initial_likes
                raw_score = like_ratio * 100
                initial_score = round(raw_score, 1)  # Session 2: no more round-to-25
                initial_score = max(0, min(100, initial_score))
                
                doc = {
                    "name": p["name"],
                    "slug": slugify(p["name"]),
                    "category": p.get("category", "other"),
                    "approved": True,
                    "created_at": now_utc(),
                    "updated_at": now_utc(),
                    "score": float(initial_score),
                    "likes": initial_likes,
                    "dislikes": initial_dislikes,
                    "total_votes": initial_votes,
                    "source": "seed",
                }
                if p.get("primary_country"):
                    doc["primary_country"] = p["primary_country"]
                
                await db.persons.insert_one(doc)
                added_count += 1
                added_names.append(p["name"])
        
        return {
            "success": True,
            "message": f"Added {added_count} new personalities",
            "added_count": added_count,
            "added_names": added_names,
        }
        
    except Exception as e:
        logger.error(f"Add missing seeds error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@api_router.post("/admin/update-celebrity-countries")
async def admin_update_celebrity_countries(request: Request):
    """Admin-only: Update primary_country for existing celebrities based on SEED_PEOPLE"""
    _require_admin_auth(request)
    try:
        updated_count = 0
        updated_names = []
        not_found = []

        # Build a lookup dict from SEED_PEOPLE
        country_map = {p["name"]: p.get("primary_country") for p in SEED_PEOPLE if p.get("primary_country")}

        for name, country in country_map.items():
            result = await db.persons.update_one(
                {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
                {"$set": {"primary_country": country, "updated_at": now_utc()}}
            )
            if result.modified_count > 0:
                updated_count += 1
                updated_names.append(f"{name} → {country}")
            elif result.matched_count == 0:
                not_found.append(name)

        return {
            "success": True,
            "message": f"Updated {updated_count} celebrities with primary_country",
            "updated_count": updated_count,
            "updated_names": updated_names[:30],
            "not_found_count": len(not_found),
            "not_found": not_found[:20],
        }

    except Exception as e:
        logger.error(f"Update celebrity countries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/initialize-votes")
async def admin_initialize_votes(request: Request):
    """Admin-only: Initialize existing personalities with realistic vote counts"""
    _require_admin_auth(request)
    try:
        # Find all personalities with 0 or very low votes
        low_vote_persons = await db.persons.find({
            "total_votes": {"$lt": 100},
            "source": {"$ne": "self_boosted"}  # Don't touch self-boosted
        }).to_list(1000)
        
        updated_count = 0
        for person in low_vote_persons:
            # Generate random initial votes between 8000 and 15000
            initial_votes = random.randint(8000, 15000)
            like_ratio = random.uniform(0.40, 0.80)
            initial_likes = int(initial_votes * like_ratio)
            initial_dislikes = initial_votes - initial_likes
            raw_score = like_ratio * 100
            initial_score = round(raw_score, 1)  # Session 2: no more round-to-25
            initial_score = max(0, min(100, initial_score))
            
            await db.persons.update_one(
                {"_id": person["_id"]},
                {
                    "$set": {
                        "likes": initial_likes,
                        "dislikes": initial_dislikes,
                        "total_votes": initial_votes,
                        "score": float(initial_score),
                        "updated_at": now_utc(),
                    }
                }
            )
            updated_count += 1
        
        return {
            "success": True,
            "message": f"Initialized vote counts for {updated_count} personalities",
            "updated_count": updated_count,
        }
        
    except Exception as e:
        logger.error(f"Initialize votes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


        logger.error(f"Admin update settings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))






# -------------------- Daily Report --------------------

from email_service import email_service

@api_router.post("/reports/daily")
async def send_daily_report(to_email: str = Query(default="didier@coffeeandfilms.com")):
    """Génère et envoie le rapport quotidien par email"""
    try:
        # Calculer la période (dernières 24h)
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        # 1. Stats générales
        total_people = await db.people.count_documents({})
        new_people_24h = await db.people.count_documents({
            "created_at": {"$gte": yesterday}
        })
        
        # 2. Votes des dernières 24h
        votes_24h = await db.ticks.count_documents({
            "created_at": {"$gte": yesterday}
        })
        
        # 3. Utilisateurs actifs (basé sur les device_ids dans votes)
        active_users_pipeline = [
            {"$match": {"created_at": {"$gte": yesterday}}},
            {"$group": {"_id": "$person_id"}},
            {"$count": "count"}
        ]
        active_users_result = await db.votes.aggregate(active_users_pipeline).to_list(length=1)
        active_users_24h = active_users_result[0]["count"] if active_users_result else 0
        
        # 4. Monétisation
        credits_sold_pipeline = [
            {"$match": {
                "timestamp": {"$gte": yesterday},
                "type": "purchase"
            }},
            {"$group": {
                "_id": None,
                "total_credits": {"$sum": "$amount"},
                "total_revenue": {"$sum": "$price"}
            }}
        ]
        monetization = await db.credit_transactions.aggregate(credits_sold_pipeline).to_list(length=1)
        
        credits_sold_24h = monetization[0]["total_credits"] if monetization else 0
        revenue_24h = f"{monetization[0]['total_revenue']:.2f}" if monetization else "0.00"
        
        # Votes premium utilisés
        premium_votes_24h = await db.credit_transactions.count_documents({
            "timestamp": {"$gte": yesterday},
            "type": "use"
        })
        
        # 5. Top 5 personnalités (par votes dans les dernières 24h)
        top_people_pipeline = [
            {"$match": {"created_at": {"$gte": yesterday}}},
            {"$group": {
                "_id": "$person_id",
                "votes_count": {"$sum": 1}
            }},
            {"$sort": {"votes_count": -1}},
            {"$limit": 5}
        ]
        top_people_ids = await db.ticks.aggregate(top_people_pipeline).to_list(length=5)
        
        top_people = []
        for item in top_people_ids:
            person = await db.people.find_one({"_id": ObjectId(item["_id"])})
            if person:
                top_people.append({
                    "name": person.get("name", "Unknown"),
                    "votes_24h": item["votes_count"],
                    "score": int(person.get("score", 0))
                })
        
        # Préparer les données pour le template
        stats = {
            "date": now.strftime("%d/%m/%Y"),
            "total_people": total_people,
            "votes_24h": votes_24h,
            "new_people_24h": new_people_24h,
            "active_users_24h": active_users_24h,
            "credits_sold_24h": credits_sold_24h,
            "revenue_24h": revenue_24h,
            "premium_votes_24h": premium_votes_24h,
            "top_people": top_people
        }
        
        # Envoyer l'email
        await email_service.send_daily_report(to_email, stats)
        
        return {
            "success": True,
            "message": f"Rapport quotidien envoyé à {to_email}",
            "stats": stats
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to send daily report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send report: {str(e)}")

@api_router.get("/reports/stats")
async def get_daily_stats():
    """Retourne les stats quotidiennes sans envoyer d'email (pour prévisualisation)"""
    try:
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        # Stats générales
        total_people = await db.people.count_documents({})
        new_people_24h = await db.people.count_documents({
            "created_at": {"$gte": yesterday}
        })
        votes_24h = await db.ticks.count_documents({
            "created_at": {"$gte": yesterday}
        })
        
        active_users_pipeline = [
            {"$match": {"created_at": {"$gte": yesterday}}},
            {"$group": {"_id": "$person_id"}},
            {"$count": "count"}
        ]
        active_users_result = await db.votes.aggregate(active_users_pipeline).to_list(length=1)
        active_users_24h = active_users_result[0]["count"] if active_users_result else 0
        
        # Monétisation
        credits_sold_pipeline = [
            {"$match": {
                "timestamp": {"$gte": yesterday},
                "type": "purchase"
            }},
            {"$group": {
                "_id": None,
                "total_credits": {"$sum": "$amount"},
                "total_revenue": {"$sum": "$price"}
            }}
        ]
        monetization = await db.credit_transactions.aggregate(credits_sold_pipeline).to_list(length=1)
        
        credits_sold_24h = monetization[0]["total_credits"] if monetization else 0
        revenue_24h = monetization[0]["total_revenue"] if monetization else 0.0
        
        premium_votes_24h = await db.credit_transactions.count_documents({
            "timestamp": {"$gte": yesterday},
            "type": "use"
        })
        
        # Top 5
        top_people_pipeline = [
            {"$match": {"created_at": {"$gte": yesterday}}},
            {"$group": {
                "_id": "$person_id",
                "votes_count": {"$sum": 1}
            }},
            {"$sort": {"votes_count": -1}},
            {"$limit": 5}
        ]
        top_people_ids = await db.ticks.aggregate(top_people_pipeline).to_list(length=5)
        
        top_people = []
        for item in top_people_ids:
            person = await db.people.find_one({"_id": ObjectId(item["_id"])})
            if person:
                top_people.append({
                    "name": person.get("name", "Unknown"),
                    "votes_24h": item["votes_count"],
                    "score": int(person.get("score", 0))
                })
        
        return {
            "date": now.strftime("%d/%m/%Y"),
            "total_people": total_people,
            "votes_24h": votes_24h,
            "new_people_24h": new_people_24h,
            "active_users_24h": active_users_24h,
            "credits_sold_24h": credits_sold_24h,
            "revenue_24h": f"{revenue_24h:.2f}",
            "premium_votes_24h": premium_votes_24h,
            "top_people": top_people
        }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/init-votes")
async def init_votes():
    """Initialize all personalities with random votes (8,500-12,000) to make the app look active"""
    try:
        # Get all persons
        persons = await db.persons.find({}).to_list(length=1000)
        
        updated_count = 0
        now = now_utc()
        
        # Generate unique vote counts for each person
        used_votes = set()
        
        for person in persons:
            # Generate unique random votes between 8,500 and 12,000
            while True:
                base_votes = random.randint(8500, 12000)
                if base_votes not in used_votes:
                    used_votes.add(base_votes)
                    break
            
            # Random like ratio between 45% and 75%
            like_ratio = random.uniform(0.45, 0.75)
            likes = int(base_votes * like_ratio)
            dislikes = base_votes - likes
            
            # Calculate score
            score = (likes / base_votes) * 100 if base_votes > 0 else 50.0
            
            # Update the person
            await db.persons.update_one(
                {"_id": person["_id"]},
                {
                    "$set": {
                        "likes": likes,
                        "dislikes": dislikes,
                        "total_votes": base_votes,
                        "score": score,
                        "updated_at": now
                    }
                }
            )
            
            # Add a tick for the chart
            await db.person_ticks.insert_one({
                "person_id": person["_id"],
                "score": score,
                "created_at": now
            })
            
            updated_count += 1
        
        return {
            "success": True,
            "message": f"Initialized {updated_count} personalities with random votes (8,500-12,000)",
            "updated_count": updated_count
        }
        
    except Exception as e:
        logger.error(f"Failed to init votes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Popularoo Index Admin Endpoints --------------------

@api_router.post("/admin/migrate-popularoo-index")
async def admin_migrate_index(request: Request):
    """
    One-time migration: Calculate initial Popularoo Index for all persons.
    Safe to run multiple times (idempotent).
    """
    _require_admin_auth(request)
    try:
        count = await migrate_initial_index(db)
        return {
            "success": True,
            "message": f"Popularoo Index migrated for {count} persons",
            "count": count,
        }
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/recalculate-all-indices")
async def admin_recalculate_indices(request: Request):
    """
    Force immediate recalculation of Popularoo Index for ALL persons.
    Session 2: Uses current α and existing popularity_external_score.
    Updates BOTH score and popularoo_index fields.
    """
    _require_admin_auth(request)
    import time as _time
    start = _time.time()

    try:
        from popularoo_index import get_alpha
        alpha = await get_alpha(db)
        count = await recalculate_all_indices(db)
        elapsed = round(_time.time() - start, 2)

        # Spot check 5 persons
        spot_check = []
        for name in ["Donald Trump", "Cristiano Ronaldo", "Squeezie", "Brad Pitt", "Emmanuel Macron"]:
            doc = await db.persons.find_one({"name": name})
            if doc:
                spot_check.append({
                    "name": name,
                    "score": doc.get("score"),
                    "popularoo_index": doc.get("popularoo_index"),
                    "ext": doc.get("popularity_external_score"),
                })

        return {
            "success": True,
            "alpha": alpha,
            "persons_recalculated": count,
            "elapsed_seconds": elapsed,
            "spot_check": spot_check,
        }
    except Exception as e:
        logger.error(f"Recalculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/fix-visible-user-search")
async def admin_fix_visible_user_search(request: Request):
    """Admin-only: Migrate existing user_search profiles to visible_in_rankings=True.
    
    Targets profiles matching ALL 4 criteria:
    - source: "user_search"
    - approved: true
    - popularity_external_score >= 65
    - visible_in_rankings: false
    """
    _require_admin_auth(request)
    try:
        # Find matching profiles
        query_filter = {
            "source": "user_search",
            "approved": True,
            "popularity_external_score": {"$gte": 65},
            "visible_in_rankings": False,
        }

        # Collect names before update
        cursor = db.persons.find(query_filter, {"name": 1})
        migrated_names = []
        async for doc in cursor:
            migrated_names.append(doc.get("name", "???"))

        if not migrated_names:
            return {
                "success": True,
                "message": "No profiles to migrate",
                "migrated_count": 0,
                "migrated_names": [],
            }

        # Apply update
        result = await db.persons.update_many(
            query_filter,
            {"$set": {"visible_in_rankings": True, "updated_at": now_utc()}}
        )

        logger.info(f"✅ [Admin] fix-visible-user-search: migrated {result.modified_count} profiles: {migrated_names}")

        return {
            "success": True,
            "message": f"Migrated {result.modified_count} profiles to visible_in_rankings=true",
            "migrated_count": result.modified_count,
            "migrated_names": migrated_names,
        }

    except Exception as e:
        logger.error(f"fix-visible-user-search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/migrate-user-search-v4")
async def admin_migrate_user_search_v4(request: Request):
    """
    Vague 4, sous-tâche 9 — One-time migration of legacy user_search profiles
    to the deferred-V4 formula.

    Recomputes the V4 initial PI (clamp 25..40, 25 + ext_score*0.15) and grafts
    ~40 simulated votes onto profiles with source in
    {"user_search", "user_search_confirmed"} + approved, so the old profiles
    (PI ~10-15, 0 votes) sit coherently next to the new deferred_v4 ones.

    - Defensive guard: category == "outsider" is skipped.
    - Idempotent: a profile with a non-null `migrated_v4_at` is skipped, so the
      endpoint can be re-run safely.
    - Real existing votes are preserved and the simulated votes added on top.

    Triggered manually via curl (NOT automatic at deploy):
      curl -X POST https://<host>/api/admin/migrate-user-search-v4 \\
           -H "X-Admin-Password: <password>"
    """
    _require_admin_auth(request)
    try:
        from candidate_detection import migrate_user_search_v4
        result = await migrate_user_search_v4(db)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"migrate-user-search-v4 error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@api_router.get("/admin/index-config")
async def admin_get_index_config(request: Request):
    """View current algorithm configuration (admin only)."""
    _require_admin_auth(request)
    config = await load_index_config(db)
    safe = {k: v for k, v in config.items() if k != "_id"}
    return {"config": safe}


@api_router.post("/admin/index-config")
async def admin_update_index_config(request: Request, body: Dict[str, Any]):
    """
    Update algorithm coefficients (admin only).
    Example: {"coefficients": {"volume": 0.25, "ratio": 0.35}}
    """
    _require_admin_auth(request)
    try:
        update_fields = {}
        if "coefficients" in body:
            for k, v in body["coefficients"].items():
                if k in ("volume", "ratio", "momentum", "regularity"):
                    update_fields[f"coefficients.{k}"] = float(v)
        for key in ("strike_value", "low_vote_cap", "low_vote_threshold",
                     "momentum_multiplier", "regularity_scale", "volume_scale", "ratio_scale"):
            if key in body:
                update_fields[key] = float(body[key])

        if not update_fields:
            return {"success": False, "message": "No valid fields to update"}

        update_fields["last_updated"] = now_utc()
        await db.algorithm_config.update_one(
            {"_id": "popularoo_index"},
            {"$set": update_fields},
        )
        invalidate_config_cache()
        new_config = await load_index_config(db)
        safe = {k: v for k, v in new_config.items() if k != "_id"}
        return {"success": True, "config": safe}
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Admin: Geo-Tagging Endpoints --------------------

@api_router.post("/admin/apply-geo-tags")
async def admin_apply_geo_tags(request: Request):
    """
    Apply geo-tags from the pre-generated JSON file to all personalities.
    Idempotent: safe to run multiple times.
    """
    _require_admin_auth(request)
    import json as json_lib
    json_path = os.path.join(os.path.dirname(__file__), "static", "personality_tags.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Tags file not found. Run tag_personalities.py first.")

    with open(json_path, "r", encoding="utf-8") as f:
        tags_data = json_lib.load(f)

    updated = 0
    for entry in tags_data:
        person_id = entry.get("person_id")
        if not person_id:
            continue
        country_tags = [t.strip() for t in entry["country_tags"].split(",") if t.strip()]
        is_international = entry["is_international"] == "YES"
        primary_country = entry["primary_country"] if entry["primary_country"] != "??" else None

        result = await db.persons.update_one(
            {"_id": ObjectId(person_id)},
            {"$set": {
                "country_tags": country_tags,
                "is_international": is_international,
                "primary_country": primary_country,
            }}
        )
        if result.modified_count > 0:
            updated += 1

    return {"success": True, "updated": updated, "total": len(tags_data)}


@api_router.get("/admin/geo-tags-summary")
async def admin_geo_tags_summary(request: Request):
    """Get summary of geo-tag distribution across all personalities."""
    _require_admin_auth(request)
    pipeline = [
        {"$match": {"approved": True, "source": {"$ne": "self_boosted"}}},
        {"$group": {
            "_id": "$primary_country",
            "count": {"$sum": 1},
            "names": {"$push": "$name"},
        }},
        {"$sort": {"count": -1}},
    ]
    by_country = []
    async for doc in db.persons.aggregate(pipeline):
        by_country.append({
            "country": doc["_id"] or "untagged",
            "count": doc["count"],
            "sample_names": doc["names"][:5],
        })

    intl_count = await db.persons.count_documents({"is_international": True, "approved": True})
    tagged_count = await db.persons.count_documents({"country_tags": {"$exists": True, "$ne": []}, "approved": True})
    total = await db.persons.count_documents({"approved": True, "source": {"$ne": "self_boosted"}})

    return {
        "total_personalities": total,
        "tagged": tagged_count,
        "international": intl_count,
        "by_country": by_country,
    }


@api_router.post("/admin/delete-duplicate/{person_id}")
async def admin_delete_duplicate(request: Request, person_id: str):
    """Delete a duplicate/invalid personality entry. Admin only."""
    _require_admin_auth(request)
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    # Delete the person and their associated data
    name = person.get("name", "Unknown")
    await db.persons.delete_one({"_id": oid})
    await db.votes.delete_many({"person_id": oid})
    await db.person_ticks.delete_many({"person_id": oid})

    logger.info(f"🗑️ Admin deleted personality: {name} ({person_id})")
    return {"success": True, "deleted": name, "person_id": person_id}


@api_router.post("/admin/bulk-import-personalities")
async def admin_bulk_import_personalities(request: Request):
    """
    Import new personalities from the validated personality_tags_v2.json file.
    Only inserts NEW entries (status='new') that don't already exist in the DB.
    Idempotent: safe to run multiple times.
    """
    _require_admin_auth(request)
    import json as json_lib
    json_path = os.path.join(os.path.dirname(__file__), "static", "personality_tags_v2.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Tags V2 file not found.")

    with open(json_path, "r", encoding="utf-8") as f:
        tags_data = json_lib.load(f)

    inserted = 0
    skipped = 0
    updated_tags = 0
    now = now_utc()

    for entry in tags_data:
        name = entry.get("name", "").strip()
        if not name:
            continue

        # Parse tags
        country_tags = [t.strip() for t in entry.get("tags", "").split(",") if t.strip()]
        is_international = entry.get("is_international") == "YES"
        primary_country = entry.get("primary_country")
        if primary_country == "??":
            primary_country = None
        category = entry.get("category", "other")
        validation = entry.get("validation", "").strip()

        # Skip entries explicitly rejected by human reviewer
        if validation == "❌":
            skipped += 1
            continue

        if entry.get("status") == "new":
            # Check if already exists
            existing = await db.persons.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
            if existing:
                # Update tags on existing entry
                await db.persons.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "country_tags": country_tags,
                        "is_international": is_international,
                        "primary_country": primary_country,
                    }}
                )
                updated_tags += 1
                continue

            # Anti-ghost: never re-create a blocklisted (deleted) personality.
            if await is_person_blocklisted(name_normalized=normalize_person_name(name), slug=slugify(name)):
                logger.info(f"🚫 [Anti-ghost] bulk-import skipped blocklisted '{name}'")
                skipped += 1
                continue

            # Insert new personality
            base_votes = random.randint(8000, 15000)
            likes_ratio = random.uniform(0.55, 0.75)
            likes = int(base_votes * likes_ratio)
            dislikes = base_votes - likes

            # Generate unique slug
            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while await db.persons.find_one({"slug": slug}):
                slug = f"{base_slug}-{counter}"
                counter += 1

            person_doc = {
                "name": name,
                "slug": slug,
                "category": category,
                "approved": True,
                "score": round(100 * (likes / max(1, base_votes)), 2),
                "likes": likes,
                "dislikes": dislikes,
                "superlikes": 0,
                "total_votes": base_votes,
                "popularoo_index": 0.0,
                "active_strikes": 0,
                "source": "seed",
                "country_tags": country_tags,
                "is_international": is_international,
                "primary_country": primary_country,
                "created_at": now,
                "updated_at": now,
            }
            await db.persons.insert_one(person_doc)
            inserted += 1

        elif entry.get("status") == "existing" and entry.get("person_id"):
            # Update geo-tags on existing personality
            try:
                oid = ObjectId(entry["person_id"])
                await db.persons.update_one(
                    {"_id": oid},
                    {"$set": {
                        "country_tags": country_tags,
                        "is_international": is_international,
                        "primary_country": primary_country,
                        "category": category,
                    }}
                )
                updated_tags += 1
            except Exception:
                pass

    logger.info(f"📦 Bulk import: {inserted} new, {updated_tags} updated, {skipped} skipped")
    return {
        "success": True,
        "inserted": inserted,
        "updated_tags": updated_tags,
        "skipped": skipped,
        "total_processed": len(tags_data),
    }


@api_router.get("/people/{person_id}/index-detail")
async def get_person_index_detail(person_id: str):
    """Get detailed Popularoo Index breakdown for a person."""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    return {
        "person_id": str(person["_id"]),
        "name": person.get("name"),
        "popularoo_index": person.get("popularoo_index", 0.0),
        "base_index": person.get("base_index", 0.0),
        "components": person.get("index_components", {}),
        "likes": person.get("likes", 0),
        "dislikes": person.get("dislikes", 0),
        "superlikes": person.get("superlikes", 0),
        "active_strikes": person.get("active_strikes", 0),
        "last_index_calc": person.get("last_index_calc"),
    }


# -------------------- Daily Run V2 Endpoints --------------------

@api_router.get("/daily-run/suggested-targets/{person_id}")
async def api_get_suggested_targets(person_id: str, limit: int = 10):
    """Get suggested targets for a Daily Run (persons with similar Index)."""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")
    targets = await get_suggested_targets(db, oid, limit=limit)
    return {"targets": targets}


@api_router.post("/daily-run/activate")
async def api_activate_daily_run(body: Dict[str, Any]):
    """
    Activate a new Daily Run.
    Body: {user_id, person_id, target_id, rally_message?}
    """
    user_id = body.get("user_id")
    person_id_str = body.get("person_id")
    target_id_str = body.get("target_id")
    rally_message = body.get("rally_message", "")

    if not user_id or not person_id_str or not target_id_str:
        raise HTTPException(status_code=400, detail="user_id, person_id, and target_id are required")

    # ── Ban enforcement ──
    await _check_device_not_banned(user_id)

    try:
        person_oid = ObjectId(person_id_str)
        target_oid = ObjectId(target_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id or target_id")

    # ── Suspension enforcement ──
    person = await db.persons.find_one({"_id": person_oid})
    await _check_person_not_suspended(person)

    result = await activate_daily_run(db, user_id, person_oid, target_oid, rally_message)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@api_router.get("/daily-run/{user_id}/active")
async def api_get_active_daily_run(user_id: str):
    """Get the current active Daily Run for a user."""
    run = await get_active_daily_run(db, user_id)
    if not run:
        return {"active": False, "daily_run": None}
    return {"active": True, "daily_run": run}


@api_router.get("/daily-run/{user_id}/history")
async def api_get_daily_run_history(user_id: str, limit: int = 20):
    """Get past Daily Runs for a user."""
    runs = await get_daily_run_history(db, user_id, limit=limit)
    return {"runs": runs}


@api_router.get("/daily-run/live")
async def api_get_live_daily_runs(limit: int = 10):
    """Get all active Daily Runs sorted by excitement (public endpoint)."""
    runs = await get_live_daily_runs(db, limit=limit)
    return {"live_runs": runs}


@api_router.get("/daily-run/preview-tier")
async def api_preview_tier(person_id: str, target_id: str):
    """Preview what tier/conditions would apply before activating a Daily Run."""
    try:
        p_oid = ObjectId(person_id)
        t_oid = ObjectId(target_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid IDs")

    person = await db.persons.find_one({"_id": p_oid})
    target = await db.persons.find_one({"_id": t_oid})
    if not person or not target:
        raise HTTPException(status_code=404, detail="Person or target not found")

    p_idx = person.get("popularoo_index", 0)
    t_idx = target.get("popularoo_index", 0)
    gap = abs(t_idx - p_idx)
    tier, condition, reward = determine_tier(p_idx, t_idx)

    return {
        "person_index": p_idx,
        "target_index": t_idx,
        "index_gap": round(gap, 1),
        "tier": tier,
        "victory_condition": condition,
        "reward": reward,
    }


@api_router.get("/daily-run/search-target/{person_id}")
async def api_search_target(person_id: str, q: str = Query(..., min_length=1), limit: int = 10):
    """
    Search for any person as a potential Daily Run target ('Choose Anyone' feature).
    Returns matching persons with tier/victory condition calculated.
    """
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")
    targets = await search_target(db, oid, q, limit=limit)
    return {"targets": targets}


@api_router.get("/daily-run/status/{user_id}/{person_id}")
async def api_daily_run_status(user_id: str, person_id: str):
    """
    Get Daily Run slot status for a user's outsider profile.
    Returns: available slots, used slots, cooldown info, active run info.
    """
    try:
        p_oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")
    status = await get_daily_run_status(db, user_id, p_oid)
    return status


# -------------------- Strikes Endpoints --------------------

@api_router.get("/people/{person_id}/strikes")
async def api_get_person_strikes(person_id: str):
    """Get active strikes for a person."""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    strikes = await get_active_strikes_detail(db, oid)
    active_count = person.get("active_strikes", 0)
    emoji, label = get_strike_level(active_count)

    return {
        "person_id": str(oid),
        "name": person.get("name"),
        "active_strikes": active_count,
        "level_emoji": emoji,
        "level_label": label,
        "strikes": strikes,
    }


# Include the router in the main app
# Include Bull Run / Rally Cry router
app.include_router(bull_run_router)
app.include_router(share_router)


# -------------------- Share System Endpoints --------------------

@api_router.get("/share/rally/{rally_id}")
async def get_rally_share_data(rally_id: str):
    """Get share data for a Rally Cry (short link, messages, image URLs)"""
    try:
        oid = ObjectId(rally_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rally_id")

    rally = await db.rally_cries.find_one({"_id": oid})
    if not rally:
        raise HTTPException(status_code=404, detail="Rally Cry not found")

    # Get user and celebrity data
    user_person = await db.persons.find_one({"_id": ObjectId(rally["person_id"])})
    celebrity = await db.persons.find_one({"_id": ObjectId(rally["target_celebrity_id"])})

    if not user_person or not celebrity:
        raise HTTPException(status_code=404, detail="Person data not found")

    user_name = user_person.get("name", "Unknown")
    celeb_name = celebrity.get("name", "Unknown")
    user_score = user_person.get("likes", 0)
    celeb_score = celebrity.get("likes", 0)
    gap = celeb_score - user_score

    # Create short link
    short_id = await create_short_link(db, "rally_cry", rally_id)
    short_url = f"https://popularoo.com/r/{short_id}"

    # Generate share messages
    messages = get_share_messages(user_name, celeb_name, gap, short_url)

    return {
        "short_url": short_url,
        "short_id": short_id,
        "share_image_square": f"/api/share/rally-image/{rally_id}/square",
        "share_image_vertical": f"/api/share/rally-image/{rally_id}/vertical",
        "messages": messages,
        "user_name": user_name,
        "celebrity_name": celeb_name,
        "gap": gap,
    }


@api_router.get("/share/rally-image/{rally_id}/{format_type}")
async def get_rally_share_image(rally_id: str, format_type: str):
    """Generate and return a Rally Cry share image (square or vertical)"""
    if format_type not in ("square", "vertical"):
        raise HTTPException(status_code=400, detail="format must be 'square' or 'vertical'")

    try:
        oid = ObjectId(rally_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rally_id")

    rally = await db.rally_cries.find_one({"_id": oid})
    if not rally:
        raise HTTPException(status_code=404, detail="Rally Cry not found")

    user_person = await db.persons.find_one({"_id": ObjectId(rally["person_id"])})
    celebrity = await db.persons.find_one({"_id": ObjectId(rally["target_celebrity_id"])})

    if not user_person or not celebrity:
        raise HTTPException(status_code=404, detail="Person data not found")

    # Get Bull Run info for rank
    bull_run = await db.bull_runs.find_one({"user_id": rally.get("user_id"), "active": True})
    rank = bull_run.get("rank", "Challenger") if bull_run else "Challenger"

    # Calculate time remaining
    expires_at = rally.get("expires_at")
    if expires_at:
        from datetime import timezone
        remaining = expires_at - now_utc()
        days_left = max(0, remaining.days)
        hours_left = max(0, remaining.seconds // 3600)
        time_remaining = f"{days_left}d {hours_left}h" if days_left > 0 else f"{hours_left}h"
    else:
        time_remaining = "LIVE"

    # Get short URL if available
    short_link = await db.short_links.find_one({"target_type": "rally_cry", "target_id": str(rally["_id"])})
    short_url = f"popularoo.com/r/{short_link['short_id']}" if short_link else "popularoo.com"

    buffer = generate_rally_cry_image(
        user_name=user_person.get("name", "Unknown"),
        celebrity_name=celebrity.get("name", "Unknown"),
        user_score=user_person.get("likes", 0),
        celebrity_score=celebrity.get("likes", 0),
        gap=celebrity.get("likes", 0) - user_person.get("likes", 0),
        rank=rank,
        format_type=format_type,
        time_remaining=time_remaining,
        short_url=short_url,
    )

    return StreamingResponse(buffer, media_type="image/png")


@api_router.get("/public/r/{short_id}", response_class=HTMLResponse)
async def public_rally_page(short_id: str):
    """Server-rendered public page for a Rally Cry"""
    link = await resolve_short_link(db, short_id)
    if not link or link.get("target_type") != "rally_cry":
        return HTMLResponse("<h1>Rally Cry not found</h1>", status_code=404)

    rally_id = link["target_id"]
    try:
        rally = await db.rally_cries.find_one({"_id": ObjectId(rally_id)})
    except Exception:
        return HTMLResponse("<h1>Invalid link</h1>", status_code=404)

    if not rally:
        return HTMLResponse("<h1>Rally Cry not found</h1>", status_code=404)

    user_person = await db.persons.find_one({"_id": ObjectId(rally["person_id"])})
    celebrity = await db.persons.find_one({"_id": ObjectId(rally["target_celebrity_id"])})

    if not user_person or not celebrity:
        return HTMLResponse("<h1>Data not found</h1>", status_code=404)

    bull_run = await db.bull_runs.find_one({"user_id": rally.get("user_id"), "active": True})
    rank = bull_run.get("rank", "Challenger") if bull_run else "Challenger"

    user_name = user_person.get("name", "Unknown")
    celeb_name = celebrity.get("name", "Unknown")
    user_score = user_person.get("likes", 0)
    celeb_score = celebrity.get("likes", 0)
    gap = celeb_score - user_score

    html = generate_rally_page_html(
        user_name=user_name,
        celebrity_name=celeb_name,
        user_score=user_score,
        celebrity_score=celeb_score,
        gap=gap,
        rank=rank,
        short_id=short_id,
        rally_id=rally_id,
    )
    return HTMLResponse(html)


@api_router.get("/public/u/{short_id}", response_class=HTMLResponse)
async def public_user_page(short_id: str):
    """Server-rendered public profile page for a boosted user"""
    link = await resolve_short_link(db, short_id)
    if not link or link.get("target_type") != "user":
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    person_id = link["target_id"]
    try:
        person = await db.persons.find_one({"_id": ObjectId(person_id)})
    except Exception:
        return HTMLResponse("<h1>Invalid link</h1>", status_code=404)

    if not person:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    # Get Bull Run info
    # Find any bull_run for this person
    bull_run = await db.bull_runs.find_one({"person_id": person_id})
    rank = bull_run.get("rank", "Newcomer") if bull_run else "Newcomer"

    # Get recent wins
    wins_cursor = db.bull_run_wins.find(
        {"user_person_id": person_id}
    ).sort("won_at", -1).limit(5)
    wins = []
    async for w in wins_cursor:
        celeb = await db.persons.find_one({"_id": ObjectId(w.get("celebrity_id", ""))})
        if celeb:
            wins.append(celeb.get("name", "Unknown"))

    html = generate_user_page_html(
        user_name=person.get("name", "Unknown"),
        rank=rank,
        total_votes=person.get("likes", 0),
        wins=wins,
        short_id=short_id,
        person_id=person_id,
    )
    return HTMLResponse(html)


@api_router.get("/share/user/{person_id}")
async def get_user_share_data(person_id: str):
    """Get share data for a user profile page"""
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    short_id = await create_short_link(db, "user", person_id)
    short_url = f"https://popularoo.com/u/{short_id}"

    user_name = person.get("name", "Unknown")

    return {
        "short_url": short_url,
        "short_id": short_id,
        "user_name": user_name,
        "messages": {
            "generic": f"Check out {user_name} on Popularoo — The Stock Market of Fame!\n\nVote here: {short_url}",
            "whatsapp": f"🏆 {user_name} is on Popularoo!\n\nVote for them 👉 {short_url}",
            "twitter": f"Vote for {user_name} on @Popularoo — The Stock Market of Fame 🏆\n\n{short_url}",
        },
    }

# Serve Instagram images
import zipfile
from io import BytesIO

INSTAGRAM_DIR = os.path.join(os.path.dirname(__file__), "static", "instagram")

@app.get("/api/instagram/download")
async def download_instagram_zip():
    """Download all Instagram images as a ZIP file"""
    if not os.path.exists(INSTAGRAM_DIR):
        raise HTTPException(status_code=404, detail="No Instagram images found")
    
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(INSTAGRAM_DIR)):
            if fname.endswith('.png'):
                fpath = os.path.join(INSTAGRAM_DIR, fname)
                zf.write(fpath, fname)
    
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=popularoo_instagram.zip"}
    )

@app.get("/api/instagram/{filename}")
async def get_instagram_image(filename: str):
    """Serve individual Instagram image"""
    fpath = os.path.join(INSTAGRAM_DIR, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(fpath, media_type="image/png")

# ─── Legal Pages ───────────────────────────────────────────────
LEGAL_DIR = os.path.join(os.path.dirname(__file__), "static", "legal")

LEGAL_PAGES = {
    # V2 legal files - all use popularoo@popularoo.com
    # For DE/ES/IT/PT-BR: fallback to EN versions in V1.0, native translations in V1.5
    "privacy": "privacy-en.html",
    "privacy-en": "privacy-en.html",
    "privacy-fr": "privacy-fr.html",
    "terms": "terms-en.html",
    "terms-en": "terms-en.html",
    "terms-fr": "terms-fr.html",
    "legal-notice": "legal-notice.html",
    "mentions-legales": "mentions-legales.html",
}

@app.get("/api/legal/{page_name}")
async def serve_legal_page(page_name: str):
    """Serve legal HTML pages (privacy, terms, legal notices)"""
    filename = LEGAL_PAGES.get(page_name)
    if not filename:
        raise HTTPException(status_code=404, detail=f"Legal page '{page_name}' not found")
    fpath = os.path.join(LEGAL_DIR, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Page file not found")
    return FileResponse(fpath, media_type="text/html")


# ─── Static Assets (screenshots, etc.) ───────────────────────────────
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/api/static/{filename:path}")
async def serve_static_asset(filename: str):
    """Serve static image/asset files (supports subdirectories)"""
    # Security: prevent path traversal
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path")
    fpath = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(fpath) or not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "image/png" if filename.endswith(".png") else \
                 "text/html" if filename.endswith(".html") else \
                 "application/json" if filename.endswith(".json") else \
                 "application/octet-stream"
    # Don't force download for images, HTML, and JSON - inline display
    if filename.endswith((".png", ".jpg", ".html", ".json")):
        return FileResponse(fpath, media_type=media_type)
    return FileResponse(fpath, media_type=media_type, filename=filename)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Compression gzip pour les payloads JSON > 1KB (typiquement /api/people et
# /api/outsiders). Économie ~70% sur les réponses listes — gain perçu majeur
# côté client mobile sur 4G/5G.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# -------------------- Admin Email Test Endpoint --------------------
from email_sender import (
    send_booster_confirmation, send_welcome, send_daily_run_victory,
    send_strike_going_viral, send_strike_legend_mode, send_booster_expiration,
)

@api_router.get("/admin/email-errors")
@limiter.limit("10/15minutes")
async def get_email_errors(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin: View recent email delivery errors logged in admin_notifications."""
    _require_admin_auth(request)

    errors = await db.admin_notifications.find(
        {"type": "email_error"}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)

    # Serialize ObjectId
    for err in errors:
        err["_id"] = str(err["_id"])
        if err.get("timestamp"):
            err["timestamp"] = err["timestamp"].isoformat()

    return {
        "total": len(errors),
        "errors": errors,
    }


@api_router.get("/admin/download-emails-review")
@limiter.limit("10/15minutes")
async def download_emails_review(request: Request):
    """Admin: Download the EMAILS_REVIEW.md file for proofreading."""
    _require_admin_auth(request)
    file_path = os.path.join(os.path.dirname(__file__), "EMAILS_REVIEW.md")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=file_path,
        filename="EMAILS_REVIEW.md",
        media_type="text/markdown",
    )


# ── Chantier 1J: Seed Outsiders Admin Endpoints ──

@api_router.post("/admin/seed-outsiders")
@limiter.limit("5/15minutes")
async def seed_outsiders_endpoint(request: Request):
    """Admin: Create all 49 seed Outsiders. Idempotent (skips existing)."""
    _require_admin_auth(request)
    from seed_outsiders import create_seed_outsiders
    result = await create_seed_outsiders(db)
    return result


# ── Chantier 1I: Social Links Management ──

class UpdateSocialLinksRequest(BaseModel):
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    x: Optional[str] = None


@api_router.put("/outsiders/{boost_id}/social-links")
async def update_outsider_social_links(boost_id: str, request: UpdateSocialLinksRequest):
    """Update social links for an active Outsider boost."""
    try:
        boost_oid = ObjectId(boost_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid boost ID")

    boost = await db.active_boosts.find_one({"_id": boost_oid})
    if not boost:
        raise HTTPException(status_code=404, detail="Boost not found")

    now = datetime.utcnow()
    if boost.get("end_time", now) < now:
        raise HTTPException(status_code=400, detail="Boost has expired")

    # Validate and clean each platform username
    clean_social = {}
    for platform in ["instagram", "tiktok", "x"]:
        raw = getattr(request, platform, None) or ""
        cleaned = _clean_username(raw)
        if cleaned:
            if not _validate_social_username(platform, cleaned):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid {platform} username: '{cleaned}'"
                )
            clean_social[platform] = cleaned

    # Update both active_boosts and persons collections
    await db.active_boosts.update_one(
        {"_id": boost_oid},
        {"$set": {"social_links": clean_social, "updated_at": now}}
    )
    if boost.get("person_id"):
        await db.persons.update_one(
            {"_id": boost["person_id"]},
            {"$set": {"social_links": clean_social, "updated_at": now}}
        )

    return {
        "success": True,
        "social_links": clean_social,
    }


@api_router.get("/admin/seed-outsiders/status")
@limiter.limit("10/15minutes")
async def seed_outsiders_status(request: Request):
    """Admin: View seed Outsiders status per country."""
    _require_admin_auth(request)
    from seed_outsiders import get_seed_status
    return await get_seed_status(db)


@api_router.delete("/admin/seed-outsiders")
@limiter.limit("5/15minutes")
async def remove_seed_outsiders_endpoint(request: Request):
    """Admin: Remove ALL seed Outsiders from the database."""
    _require_admin_auth(request)
    from seed_outsiders import remove_all_seeds
    result = await remove_all_seeds(db)
    return {"success": True, **result}


@api_router.post("/admin/calibrate-outsider-votes")
@limiter.limit("5/15minutes")
async def calibrate_outsider_votes(request: Request):
    """
    Admin: Reset outsider vote counts to realistic levels.
    Accepts optional JSON body with { calibration: [{id, name, tier, new_total, new_likes}...] }
    """
    import random
    from bson import ObjectId
    _require_admin_auth(request)
    
    body = await request.json()
    calibration_data = body.get("calibration", None)
    
    results = {"updated": 0, "details": []}
    
    if calibration_data:
        for item in calibration_data:
            oid = item["id"]
            new_total = item["new_total"]
            new_likes = item["new_likes"]
            new_dislikes = new_total - new_likes
            await db.persons.update_one(
                {"_id": ObjectId(oid)},
                {"$set": {
                    "total_votes": new_total,
                    "likes": new_likes,
                    "dislikes": new_dislikes,
                    "score": new_likes - new_dislikes,
                }}
            )
            results["details"].append({
                "name": item.get("name", "?"),
                "tier": item.get("tier", "?"),
                "new_total": new_total,
                "new_likes": new_likes,
            })
            results["updated"] += 1
    else:
        # Calibrate ALL outsiders: category=outsider OR source=self_boosted OR is_seed=True with category outsider
        outsiders = await db.persons.find({
            "$or": [
                {"category": "outsider"},
                {"source": "self_boosted"},
                {"is_seed": True, "category": "outsider"},
            ]
        }).to_list(length=1000)
        
        for o in outsiders:
            # Realistic distribution: majority 15-60, some up to 200
            # Use weighted random: 70% chance low (10-60), 25% mid (60-130), 5% high (130-200)
            roll = random.random()
            if roll < 0.70:
                new_total = random.randint(10, 60)
            elif roll < 0.95:
                new_total = random.randint(60, 130)
            else:
                new_total = random.randint(130, 200)
            
            new_likes = random.randint(int(new_total * 0.55), int(new_total * 0.85))
            new_dislikes = new_total - new_likes
            await db.persons.update_one(
                {"_id": o["_id"]},
                {"$set": {
                    "total_votes": new_total,
                    "likes": new_likes,
                    "dislikes": new_dislikes,
                    "score": new_likes - new_dislikes,
                    "seed_votes_likes": 0,
                    "seed_votes_dislikes": 0,
                }}
            )
            results["details"].append({"name": o.get("name","?"), "new_total": new_total, "new_likes": new_likes})
            results["updated"] += 1
    
    logger.info(f"🎯 Calibrated {results['updated']} outsider vote counts")
    return {"success": True, **results}


@api_router.post("/admin/audit-data-integrity")
@limiter.limit("5/15minutes")
async def admin_audit_data_integrity(request: Request):
    """
    Admin: Audit ALL persons in the DB for corrupt/invalid data.
    Returns a list of all problematic entries with details.
    Idempotent: read-only, doesn't modify anything.
    """
    _require_admin_auth(request)
    
    valid_categories = {"politics", "culture", "business", "sport", "influencer", "other", "outsider"}
    
    all_persons = await db.persons.find({}).to_list(length=5000)
    
    issues = []
    for doc in all_persons:
        person_issues = []
        pid = str(doc.get("_id", "?"))
        name = doc.get("name", None)
        
        # Check name
        if not name or not isinstance(name, str):
            person_issues.append(f"name is {name!r} (expected non-empty string)")
        
        # Check category
        cat = doc.get("category")
        if cat not in valid_categories:
            person_issues.append(f"category is {cat!r} (expected one of {valid_categories})")
        
        # Check numeric fields
        for field in ["likes", "dislikes", "total_votes", "superlikes", "score"]:
            val = doc.get(field)
            if val is not None:
                try:
                    int(val)
                except (ValueError, TypeError):
                    person_issues.append(f"{field} is {val!r} (expected int)")
        
        for field in ["popularoo_index"]:
            val = doc.get(field)
            if val is not None:
                try:
                    f = float(val)
                    if f != f:  # NaN
                        person_issues.append(f"{field} is NaN")
                except (ValueError, TypeError):
                    person_issues.append(f"{field} is {val!r} (expected float)")
        
        # Check for None in required fields
        if doc.get("approved") is None:
            person_issues.append("approved is None")
        
        if person_issues:
            issues.append({
                "id": pid,
                "name": name or "MISSING_NAME",
                "category": doc.get("category"),
                "source": doc.get("source"),
                "total_votes": doc.get("total_votes"),
                "issues": person_issues,
            })
    
    return {
        "success": True,
        "total_persons_audited": len(all_persons),
        "total_with_issues": len(issues),
        "corrupt_entries": issues,
    }


@api_router.post("/admin/fix-corrupt-data")
@limiter.limit("5/15minutes")
async def admin_fix_corrupt_data(request: Request):
    """
    Admin: Auto-fix all corrupt data found by the audit.
    Sets missing/invalid numeric fields to 0, invalid categories to "other".
    Deletes entries with no name.
    Idempotent: safe to run multiple times.
    """
    _require_admin_auth(request)
    
    valid_categories = {"politics", "culture", "business", "sport", "influencer", "other", "outsider"}
    
    all_persons = await db.persons.find({}).to_list(length=5000)
    
    fixed = 0
    deleted = 0
    details = []
    
    for doc in all_persons:
        pid = doc["_id"]
        name = doc.get("name")
        
        # Delete entries with no name
        if not name or not isinstance(name, str):
            await db.persons.delete_one({"_id": pid})
            await db.person_ticks.delete_many({"person_id": pid})
            await db.votes.delete_many({"person_id": str(pid)})
            deleted += 1
            details.append({"id": str(pid), "action": "DELETED", "reason": f"name was {name!r}"})
            continue
        
        updates = {}
        
        # Fix category
        if doc.get("category") not in valid_categories:
            updates["category"] = "other"
        
        # Fix numeric fields
        for field, default in [("likes", 0), ("dislikes", 0), ("total_votes", 0), ("superlikes", 0), ("score", 0)]:
            val = doc.get(field)
            if val is None:
                updates[field] = default
            else:
                try:
                    int(val)
                except (ValueError, TypeError):
                    updates[field] = default
        
        # Fix float fields
        for field, default in [("popularoo_index", 0.0)]:
            val = doc.get(field)
            if val is None:
                updates[field] = default
            else:
                try:
                    f = float(val)
                    if f != f:  # NaN
                        updates[field] = default
                except (ValueError, TypeError):
                    updates[field] = default
        
        # Fix approved
        if doc.get("approved") is None:
            updates["approved"] = True
        
        if updates:
            await db.persons.update_one({"_id": pid}, {"$set": updates})
            fixed += 1
            details.append({"name": name, "action": "FIXED", "fields": list(updates.keys())})
    
    return {
        "success": True,
        "total_audited": len(all_persons),
        "fixed": fixed,
        "deleted": deleted,
        "details": details,
    }


# ==================== ADMIN: Secure Data Maintenance Endpoints ====================

@api_router.post("/admin/update-person-category")
@limiter.limit("10/15minutes")
async def admin_update_person_category(request: Request):
    """
    Admin: Update a person's category by name.
    Body: { "name": "Ted Sarandos", "new_category": "business" }
    Idempotent: safe to call multiple times.
    """
    _require_admin_auth(request)
    body = await request.json()
    name = body.get("name", "").strip()
    new_category = body.get("new_category", "").strip().lower()
    
    valid_categories = {"politics", "culture", "business", "sport", "influencer", "other", "outsider"}
    if new_category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category '{new_category}'. Valid: {', '.join(valid_categories)}")
    
    result = await db.persons.update_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"$set": {"category": new_category, "updated_at": now_utc()}}
    )
    
    if result.matched_count == 0:
        return {"success": False, "error": f"Person '{name}' not found in database"}
    
    logger.info(f"🏷️ Admin: Updated category for '{name}' → {new_category}")
    return {"success": True, "name": name, "new_category": new_category, "modified": result.modified_count}


@api_router.post("/admin/update-person-category-batch")
@limiter.limit("5/15minutes")
async def admin_update_person_category_batch(request: Request):
    """
    Admin: Update category for multiple persons at once.
    Body: { "updates": [{"name": "Jean Louis", "new_category": "outsider"}, ...] }
    Idempotent: safe to call multiple times.
    """
    _require_admin_auth(request)
    body = await request.json()
    updates = body.get("updates", [])
    
    valid_categories = {"politics", "culture", "business", "sport", "influencer", "other", "outsider"}
    results = {"success": True, "processed": 0, "modified": 0, "not_found": [], "details": []}
    
    for item in updates:
        name = item.get("name", "").strip()
        new_category = item.get("new_category", "").strip().lower()
        
        if not name or new_category not in valid_categories:
            results["details"].append({"name": name, "status": "skipped", "reason": f"invalid category '{new_category}'"})
            continue
        
        result = await db.persons.update_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"$set": {"category": new_category, "updated_at": now_utc()}}
        )
        
        results["processed"] += 1
        if result.matched_count == 0:
            results["not_found"].append(name)
            results["details"].append({"name": name, "status": "not_found"})
        else:
            results["modified"] += 1
            results["details"].append({"name": name, "status": "updated", "new_category": new_category})
    
    logger.info(f"🏷️ Admin batch: {results['modified']}/{results['processed']} updated")
    return results


@api_router.post("/admin/init-vote-momentum")
@limiter.limit("1/hour")
async def admin_init_vote_momentum(request: Request):
    """
    One-shot migration for the vote_momentum field (Chantier B).

    - Vague 4 profiles (source=user_search OR created_via=deferred_v4)
      → set vote_momentum="up" if not already set (implicit +1 like at creation).
    - Self-boosted outsiders (source=self_boosted)
      → set vote_momentum="up" if not already set (boost counts as positive).
    - Historical seeds with no real vote yet → left as-is (None).
    Idempotent: only writes when the field is missing.
    """
    _require_admin_auth(request)

    v4_filter = {
        "$and": [
            {"$or": [{"source": "user_search"}, {"created_via": "deferred_v4"}]},
            {"$or": [{"vote_momentum": {"$exists": False}}, {"vote_momentum": None}]},
        ]
    }
    v4_res = await db.persons.update_many(v4_filter, {"$set": {"vote_momentum": "up"}})

    outsider_filter = {
        "$and": [
            {"source": "self_boosted"},
            {"$or": [{"vote_momentum": {"$exists": False}}, {"vote_momentum": None}]},
        ]
    }
    outsider_res = await db.persons.update_many(outsider_filter, {"$set": {"vote_momentum": "up"}})

    summary = {
        "v4_updated": int(v4_res.modified_count),
        "outsiders_updated": int(outsider_res.modified_count),
        "seeds_skipped": "left as-is (vote_momentum stays None until first real vote)",
    }
    logger.info(
        f"🟢 [vote_momentum init] V4 updated={summary['v4_updated']} "
        f"outsiders updated={summary['outsiders_updated']}"
    )
    return summary


@api_router.post("/admin/recompute-total-votes")
@limiter.limit("5/15minutes")
async def admin_recompute_total_votes(request: Request):
    """
    Admin: Recalculate total_votes = likes + dislikes for ALL persons.
    Fixes historical inconsistencies from migrations/calibrations.
    Idempotent: safe to run multiple times (produces same result).
    """
    _require_admin_auth(request)
    
    all_persons = await db.persons.find({}).to_list(length=5000)
    
    fixed = 0
    already_ok = 0
    details = []
    
    for doc in all_persons:
        likes = doc.get("likes", 0) or 0
        dislikes = doc.get("dislikes", 0) or 0
        expected_total = likes + dislikes
        current_total = doc.get("total_votes", 0) or 0
        
        if current_total != expected_total:
            await db.persons.update_one(
                {"_id": doc["_id"]},
                {"$set": {"total_votes": expected_total, "score": likes - dislikes}}
            )
            fixed += 1
            details.append({
                "name": doc.get("name", "?"),
                "old_total": current_total,
                "new_total": expected_total,
                "likes": likes,
                "dislikes": dislikes,
            })
        else:
            already_ok += 1
    
    logger.info(f"🔢 Admin: Recomputed total_votes for {fixed} persons ({already_ok} already correct)")
    return {
        "success": True,
        "fixed": fixed,
        "already_ok": already_ok,
        "total_audited": len(all_persons),
        "details": details[:50],  # Limit response size
    }


@api_router.delete("/admin/delete-person-by-name")
@limiter.limit("10/15minutes")
async def admin_delete_person_by_name(request: Request):
    """
    Admin: Delete a person by exact name (case-insensitive).
    Body: { "name": "Test" }
    Also removes associated ticks and votes.
    """
    _require_admin_auth(request)
    body = await request.json()
    name = body.get("name", "").strip()
    
    person = await db.persons.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
    if not person:
        return {"success": False, "error": f"Person '{name}' not found in database"}
    
    person_id = person["_id"]
    person_name = person.get("name", name)
    
    # Delete person
    await db.persons.delete_one({"_id": person_id})
    # Delete associated ticks
    ticks_deleted = await db.person_ticks.delete_many({"person_id": person_id})
    # Delete associated votes
    votes_deleted = await db.votes.delete_many({"person_id": str(person_id)})

    # Anti-ghost: register in the blocklist so this personality can never
    # silently re-appear via detection / seeds / imports / approvals.
    blocked = await add_person_to_blocklist(
        name=person_name or "",
        slug=person.get("slug", ""),
        wikidata_id=person.get("wikidata_id", ""),
    )

    logger.info(f"🗑️ Admin: Deleted person '{person_name}' (ticks={ticks_deleted.deleted_count}, votes={votes_deleted.deleted_count}) + blocklisted {blocked}")
    return {
        "success": True,
        "deleted_person": person_name,
        "ticks_deleted": ticks_deleted.deleted_count,
        "votes_deleted": votes_deleted.deleted_count,
        "blocklisted": blocked,
    }


# ==================== BLOC 3.4: Test Email Endpoint (Temporary) ====================

@api_router.post("/admin/test-email")
@limiter.limit("5/15minutes")
async def admin_test_email(request: Request):
    """
    Admin-only: Send a test Welcome email via Brevo SMTP.
    This endpoint is TEMPORARY and should be removed after validation.
    """
    _require_admin_auth(request)
    
    body = await request.json()
    to_email = body.get("to_email", "popularoo@popularoo.com")
    template = body.get("template", "welcome")  # welcome, booster_confirmation
    lang = body.get("lang", "fr")
    
    try:
        if template == "welcome":
            from email_sender import send_welcome
            await send_welcome(db, email_service, to_email, "test_user_admin", "Testeur Admin")
        elif template == "booster_confirmation":
            from email_sender import send_booster_confirmation
            await send_booster_confirmation(
                db, email_service, to_email, "test_user_admin",
                person_name="Test Personnalité",
                tier="golden_booster",
                duration_label="7 jours",
                price="€49.99",
            )
        elif template == "raw":
            # Simplest test: just send a raw HTML email directly
            html = """
            <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:20px;">
              <h1 style="color:#FFD700;">🎉 Popularoo — Test Email</h1>
              <p>Cet email confirme que la configuration SMTP Brevo fonctionne correctement.</p>
              <p style="color:#888;font-size:12px;">Envoyé depuis l'endpoint /api/admin/test-email</p>
            </div>
            """
            await email_service.send_email(to_email, "🧪 Popularoo — Test SMTP Brevo", html)
        else:
            return {"success": False, "error": f"Unknown template: {template}"}
        
        return {
            "success": True,
            "message": f"Test email '{template}' sent to {to_email} (lang={lang})",
            "smtp_host": os.getenv("SMTP_HOST", "N/A"),
            "from": os.getenv("SMTP_FROM_EMAIL", "N/A"),
        }
    except Exception as e:
        logger.error(f"Test email failed: {e}")
        return {"success": False, "error": str(e)}


# ==================== BLOC 3.6: GDPR "Mes données" — Data Deletion ====================

class GDPRDeleteRequest(BaseModel):
    device_id: str
    confirm: bool = False  # Must be True to actually delete


@api_router.post("/gdpr/my-data")
async def gdpr_get_my_data(request: Request, x_device_id: str = Header(alias="X-Device-ID")):
    """
    GDPR: Returns a summary of all data associated with a device_id.
    The user can see what data we hold about them.
    """
    device_id = x_device_id
    
    # Count data in each collection
    votes_count = await db.votes.count_documents({"device_id": device_id})
    superlike_votes_count = await db.superlike_votes.count_documents({"device_id": device_id})
    boosts_count = await db.active_boosts.count_documents({"user_id": device_id})
    transactions_count = await db.credit_transactions.count_documents({"user_id": device_id})
    settings_doc = await db.user_settings.find_one({"device_id": device_id})
    daily_runs_count = await db.daily_runs.count_documents({"user_id": device_id})
    
    # Get email if any boost has one
    boost_with_email = await db.active_boosts.find_one(
        {"user_id": device_id, "email": {"$ne": "", "$exists": True}},
        {"email": 1}
    )
    email_on_file = boost_with_email.get("email") if boost_with_email else None
    
    return {
        "device_id": device_id,
        "email_on_file": email_on_file,
        "data_summary": {
            "votes": votes_count,
            "superlikes": superlike_votes_count,
            "boosters_purchased": boosts_count,
            "transactions": transactions_count,
            "daily_runs": daily_runs_count,
            "has_settings": bool(settings_doc),
            "country": settings_doc.get("country") if settings_doc else None,
            "language": settings_doc.get("language") if settings_doc else None,
        },
        "legal_notice": "Conformément à la loi française, les données financières (active_boosts, credit_transactions) "
                        "seront anonymisées mais conservées 10 ans. Les votes seront conservés comme orphelins."
    }


@api_router.delete("/gdpr/delete-my-data")
async def gdpr_delete_my_data(
    request: Request,
    x_device_id: str = Header(alias="X-Device-ID"),
):
    """
    GDPR: Delete / anonymize all data for a device_id.
    
    Legal compliance (French commercial law - 10 year retention):
    - persons (self_boosted only): FULLY DELETED
    - active_boosts: ANONYMIZED (email→null, person_name→"Utilisateur supprimé", user_id→"GDPR_DELETED")
    - credit_transactions: ANONYMIZED (email→null, user_id→"GDPR_DELETED", description anonymized)
    - votes: LEFT AS ORPHANS (person_id still valid, device_id removed)
    - superlike_votes: DELETED
    - user_settings: DELETED
    - daily_runs: ANONYMIZED (user_id→"GDPR_DELETED")
    - superlike_events: DELETED
    """
    body = await request.json()
    if not body.get("confirm"):
        return {"success": False, "error": "You must set confirm=true to delete your data."}
    
    device_id = x_device_id
    now = now_utc()
    results = {}
    
    # 1. Persons created by this user (self_boosted outsiders) → FULLY DELETE
    outsiders_deleted = await db.persons.delete_many({
        "source": "self_boosted",
        "$or": [
            {"created_by": device_id},
            {"user_id": device_id},
        ]
    })
    results["persons_deleted"] = outsiders_deleted.deleted_count
    
    # 2. active_boosts → ANONYMIZE (preserve financial record, remove PII)
    boosts_anonymized = await db.active_boosts.update_many(
        {"user_id": device_id},
        {"$set": {
            "user_id": "GDPR_DELETED",
            "email": None,
            "person_name": "Utilisateur supprimé",
            "gdpr_anonymized_at": now,
        }}
    )
    results["active_boosts_anonymized"] = boosts_anonymized.modified_count
    
    # 3. credit_transactions → ANONYMIZE (preserve financial record, remove PII)
    transactions_anonymized = await db.credit_transactions.update_many(
        {"user_id": device_id},
        {"$set": {
            "user_id": "GDPR_DELETED",
            "email": None,
            "description": "Transaction anonymisée (RGPD)",
            "gdpr_anonymized_at": now,
        }}
    )
    results["credit_transactions_anonymized"] = transactions_anonymized.modified_count
    
    # 4. votes → ANONYMIZE device_id (keep vote data as orphans for integrity)
    votes_anonymized = await db.votes.update_many(
        {"device_id": device_id},
        {"$set": {
            "device_id": "GDPR_DELETED",
            "gdpr_anonymized_at": now,
        }}
    )
    results["votes_anonymized"] = votes_anonymized.modified_count
    
    # 5. superlike_votes → DELETE
    sl_deleted = await db.superlike_votes.delete_many({"device_id": device_id})
    results["superlike_votes_deleted"] = sl_deleted.deleted_count
    
    # 6. superlike_events → DELETE
    sle_deleted = await db.superlike_events.delete_many({"device_id": device_id})
    results["superlike_events_deleted"] = sle_deleted.deleted_count
    
    # 7. user_settings → DELETE
    settings_deleted = await db.user_settings.delete_many({"device_id": device_id})
    results["user_settings_deleted"] = settings_deleted.deleted_count
    
    # 8. daily_runs → ANONYMIZE
    dr_anonymized = await db.daily_runs.update_many(
        {"user_id": device_id},
        {"$set": {
            "user_id": "GDPR_DELETED",
            "gdpr_anonymized_at": now,
        }}
    )
    results["daily_runs_anonymized"] = dr_anonymized.modified_count
    
    logger.info(f"🔒 GDPR deletion completed for device_id={device_id[:12]}... — Results: {results}")
    
    return {
        "success": True,
        "message": "Toutes vos données personnelles ont été supprimées ou anonymisées conformément au RGPD.",
        "details": results,
        "legal_notice": "Les données financières (achats, transactions) ont été anonymisées et seront conservées "
                        "10 ans conformément à la loi française (Code de commerce Art. L123-22).",
    }


# ==================== LOT C: Identify Deceased via Wikidata ====================

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

async def _wikidata_search(name: str, limit: int = 3) -> list:
    """Search Wikidata for a person name, return top `limit` candidates with QID + description."""
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "format": "json",
        "limit": limit,
        "type": "item",
    }
    try:
        headers = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"}
        async with httpx.AsyncClient(timeout=15) as client_http:
            resp = await client_http.get(WIKIDATA_API, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("search", []):
                results.append({
                    "qid": item.get("id", ""),
                    "label": item.get("label", ""),
                    "description": item.get("description", ""),
                })
            return results
    except Exception as e:
        logger.warning(f"Wikidata search failed for '{name}': {e}")
        return []


async def _wikidata_check_deceased(qid: str) -> dict:
    """Check if a Wikidata entity has P570 (date of death). Returns death_date or None."""
    return (await _wikidata_check_deceased_batch([qid])).get(qid, {"is_deceased": False, "death_date": None})


async def _wikidata_check_deceased_batch(qids: list) -> dict:
    """Batch check P570 for multiple QIDs in a single request. Returns {qid: {is_deceased, death_date}}."""
    if not qids:
        return {}
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "claims",
        "format": "json",
    }
    try:
        headers = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"}
        async with httpx.AsyncClient(timeout=15) as client_http:
            resp = await client_http.get(WIKIDATA_API, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results = {}
            for qid in qids:
                entity = data.get("entities", {}).get(qid, {})
                claims = entity.get("claims", {})
                p570 = claims.get("P570")
                if p570:
                    try:
                        time_value = p570[0]["mainsnak"]["datavalue"]["value"]["time"]
                        death_date = time_value.lstrip("+").split("T")[0]
                        results[qid] = {"is_deceased": True, "death_date": death_date}
                    except (KeyError, IndexError):
                        results[qid] = {"is_deceased": True, "death_date": "unknown"}
                else:
                    results[qid] = {"is_deceased": False, "death_date": None}
            return results
    except Exception as e:
        logger.warning(f"Wikidata batch P570 check failed for {qids}: {e}")
        return {qid: {"is_deceased": False, "death_date": None} for qid in qids}


@api_router.post("/admin/identify-deceased")
@limiter.limit("3/15minutes")
async def admin_identify_deceased(request: Request):
    """
    Lot C: For each non-outsider personality, query Wikidata to detect deceased (P570).
    Returns top 3 Wikidata candidates per person for manual validation.
    """
    _require_admin_auth(request)
    import asyncio as _asyncio

    all_persons = await db.persons.find(
        {"source": {"$ne": "self_boosted"}, "category": {"$ne": "outsider"}}
    ).to_list(length=5000)

    deceased_list = []
    alive_count = 0
    not_found = []
    errors = []

    for idx, doc in enumerate(all_persons):
        name = doc.get("name", "")
        db_id = str(doc["_id"])

        # Rate limiting: small delay between persons
        if idx > 0 and idx % 10 == 0:
            await _asyncio.sleep(0.5)

        # Step 1: Search Wikidata for top 3 candidates
        candidates = await _wikidata_search(name, limit=3)
        if not candidates:
            not_found.append({"name": name, "db_id": db_id})
            continue

        # Step 2: Batch check P570 for all candidates in 1 request
        all_qids = [c["qid"] for c in candidates]
        p570_results = await _wikidata_check_deceased_batch(all_qids)

        enriched_candidates = []
        for cand in candidates:
            qid = cand["qid"]
            check = p570_results.get(qid, {"is_deceased": False, "death_date": None})
            enriched_candidates.append({
                "qid": qid,
                "description": cand["description"],
                "is_deceased": check["is_deceased"],
                "death_date": check.get("death_date"),
            })

        # Selection logic: pick the FIRST candidate (best Wikidata match)
        selected_qid = enriched_candidates[0]["qid"]
        selected_is_deceased = enriched_candidates[0]["is_deceased"]
        selected_death_date = enriched_candidates[0].get("death_date")

        if selected_is_deceased:
            deceased_list.append({
                "name": name,
                "db_id": db_id,
                "category": doc.get("category", "unknown"),
                "wikidata_candidates": enriched_candidates,
                "selected_qid": selected_qid,
                "selected_is_deceased": True,
                "selected_death_date": selected_death_date,
            })
        else:
            alive_count += 1

    logger.info(f"☠️ Lot C: Checked {len(all_persons)} persons — {len(deceased_list)} deceased, {alive_count} alive, {len(not_found)} not found")

    return {
        "total_checked": len(all_persons),
        "deceased_count": len(deceased_list),
        "alive_count": alive_count,
        "not_found_count": len(not_found),
        "deceased": deceased_list,
        "not_found_on_wikidata": not_found,
        "errors": errors,
    }


# ==================== LOT C bis: Batch Delete Persons ====================

@api_router.post("/admin/identify-historical")
@limiter.limit("3/15minutes")
async def admin_identify_historical(request: Request):
    """
    Quick check: find persons born before 1900 via Wikidata P569 (date of birth).
    These are historical figures that probably don't belong in a modern popularity app.
    """
    _require_admin_auth(request)
    import asyncio as _asyncio

    all_persons = await db.persons.find(
        {"source": {"$ne": "self_boosted"}, "category": {"$ne": "outsider"}}
    ).to_list(length=5000)

    historical = []
    modern = 0
    errors_list = []

    for idx, doc in enumerate(all_persons):
        name = doc.get("name", "")
        db_id = str(doc["_id"])

        if idx > 0 and idx % 10 == 0:
            await _asyncio.sleep(0.5)

        # Search Wikidata for first match
        candidates = await _wikidata_search(name, limit=1)
        if not candidates:
            continue

        qid = candidates[0]["qid"]
        desc = candidates[0].get("description", "")

        # Check P569 (date of birth)
        try:
            headers = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"}
            async with httpx.AsyncClient(timeout=15) as client_http:
                resp = await client_http.get(WIKIDATA_API, params={
                    "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"
                }, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                entity = data.get("entities", {}).get(qid, {})
                p569 = entity.get("claims", {}).get("P569")
                if p569:
                    time_value = p569[0]["mainsnak"]["datavalue"]["value"]["time"]
                    birth_year = int(time_value.lstrip("+").split("-")[0])
                    if birth_year < 1900:
                        historical.append({
                            "name": name,
                            "db_id": db_id,
                            "category": doc.get("category", "unknown"),
                            "birth_year": birth_year,
                            "wikidata_description": desc,
                            "qid": qid,
                        })
                    else:
                        modern += 1
                else:
                    modern += 1
        except Exception as e:
            errors_list.append({"name": name, "error": str(e)})
            modern += 1

    logger.info(f"📜 Historical check: {len(historical)} born before 1900, {modern} modern")
    return {
        "total_checked": len(all_persons),
        "historical_count": len(historical),
        "modern_count": modern,
        "historical": historical,
        "errors": errors_list[:10],
    }


@api_router.post("/admin/delete-persons-batch")
@limiter.limit("3/15minutes")
async def admin_delete_persons_batch(request: Request):
    """
    Lot C: Delete multiple persons by name (case-insensitive).
    Also removes associated ticks and votes.
    Body: { "names": ["Queen Elizabeth II", "Pope Benedict XVI", ...] }
    """
    _require_admin_auth(request)
    body = await request.json()
    names = body.get("names", [])

    results = {"success": True, "deleted": [], "not_found": [], "total_deleted": 0}

    for name in names:
        name = name.strip()
        if not name:
            continue
        person = await db.persons.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
        if not person:
            results["not_found"].append(name)
            continue

        person_id = person["_id"]
        person_name = person.get("name", name)

        await db.persons.delete_one({"_id": person_id})
        ticks_del = await db.person_ticks.delete_many({"person_id": person_id})
        votes_del = await db.votes.delete_many({"person_id": str(person_id)})

        results["deleted"].append({
            "name": person_name,
            "ticks_removed": ticks_del.deleted_count,
            "votes_removed": votes_del.deleted_count,
        })
        results["total_deleted"] += 1

    logger.info(f"🗑️ Lot C batch: Deleted {results['total_deleted']} persons, {len(results['not_found'])} not found")
    return results


# ==================== LOT D: Audit Categories via Wikipedia ====================

WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"

# Mapping keywords → category (order matters: first match wins)
# ⚠️ Synchronisé avec backend/candidate_detection.py:47 (CATEGORY_KEYWORDS).
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
CATEGORY_KEYWORD_MAP = [
    ("politics", [
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
    ]),
    ("sport", [
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
    ]),
    ("culture", [
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
    ]),
    ("influencer", [
        "youtuber", "youtube personality", "youtube channel", "streamer",
        "twitch streamer", "kick streamer", "tiktoker", "tiktok",
        "instagram", "instagrammer", "influencer", "content creator",
        "social media", "media personality", "social media personality",
        "internet personality", "online personality", "web personality",
        "vlogger", "blogger", "twitch", "podcaster",
    ]),
    ("business", [
        "entrepreneur", "business", "businessman", "businesswoman",
        "businessperson", "ceo", "cfo", "cto of", "chief technology officer",
        "chief executive", "chief financial", "chief operating",
        "chairman", "chairwoman",
        "founder", "co-founder", "cofounder", "investor", "billionaire",
        "executive", "industrialist", "magnate", "tycoon", "philanthropist",
        "venture capitalist", "venture capital", "hedge fund",
        "banker", "financier", "real estate developer",
    ]),
]


def _infer_category_from_description(description: str) -> tuple:
    """
    Infer category from Wikipedia short description.
    Returns (category, matched_keywords) or (None, []) if no match.
    """
    if not description:
        return None, []
    desc_lower = description.lower()
    for category, keywords in CATEGORY_KEYWORD_MAP:
        matched = [kw for kw in keywords if kw in desc_lower]
        if matched:
            return category, matched
    return None, []


def _clean_name_parentheses(name: str) -> tuple:
    """
    Detect and clean Wikipedia-style parenthetical suffixes.
    "Robert Smith (musician)" → ("Robert Smith", "(musician)")
    "Elon Musk" → ("Elon Musk", None)
    """
    match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', name)
    if match:
        return match.group(1).strip(), f"({match.group(2)})"
    return name, None


@api_router.post("/admin/audit-categories")
@limiter.limit("3/15minutes")
async def admin_audit_categories(request: Request):
    """
    Lot D: For each non-outsider personality, query Wikipedia short description
    and compare with current DB category. Returns divergences for manual validation.
    """
    _require_admin_auth(request)
    import asyncio as _asyncio

    all_persons = await db.persons.find(
        {"source": {"$ne": "self_boosted"}, "category": {"$ne": "outsider"}}
    ).to_list(length=5000)

    divergences = []
    names_with_parentheses = []
    not_found = []
    unchanged = 0
    unresolved = []

    for idx, doc in enumerate(all_persons):
        name = doc.get("name", "")
        db_id = str(doc["_id"])
        current_cat = doc.get("category", "other")

        # Check for parenthetical suffix
        clean_name, suffix = _clean_name_parentheses(name)
        if suffix:
            names_with_parentheses.append({
                "name": name,
                "db_id": db_id,
                "clean_name": clean_name,
                "suffix": suffix,
            })

        # Rate limiting
        if idx > 0 and idx % 5 == 0:
            await _asyncio.sleep(1.0)

        # Query Wikipedia for short description
        wiki_title = clean_name.replace(" ", "_")
        wikipedia_description = ""
        try:
            async with httpx.AsyncClient(timeout=15) as client_http:
                resp = await client_http.get(
                    f"{WIKIPEDIA_API}/page/summary/{wiki_title}",
                    headers={"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    wikipedia_description = data.get("description", "")
                elif resp.status_code == 404:
                    not_found.append({"name": name, "db_id": db_id})
                    continue
                else:
                    logger.warning(f"Wikipedia API {resp.status_code} for '{name}'")
                    continue
        except Exception as e:
            logger.warning(f"Wikipedia API error for '{name}': {e}")
            continue

        # Infer category
        suggested_cat, matched_keywords = _infer_category_from_description(wikipedia_description)

        if suggested_cat is None:
            # No keyword match → unresolved
            unresolved.append({
                "name": name,
                "db_id": db_id,
                "current_category": current_cat,
                "wikipedia_description": wikipedia_description,
                "reason": "no keyword match in description",
            })
            continue

        if suggested_cat != current_cat:
            divergences.append({
                "name": name,
                "db_id": db_id,
                "current_category": current_cat,
                "suggested_category": suggested_cat,
                "wikipedia_description": wikipedia_description,
                "matched_keywords": matched_keywords,
                "reason": f"keyword match: {', '.join(matched_keywords)}",
            })
        else:
            unchanged += 1

    logger.info(f"🏷️ Lot D: Audited {len(all_persons)} — {len(divergences)} divergences, {unchanged} unchanged, {len(unresolved)} unresolved, {len(not_found)} not found")

    return {
        "total_audited": len(all_persons),
        "divergences_count": len(divergences),
        "unchanged_count": unchanged,
        "unresolved_count": len(unresolved),
        "not_found_count": len(not_found),
        "names_with_parentheses_count": len(names_with_parentheses),
        "divergences": divergences,
        "unresolved": unresolved,
        "not_found_on_wikipedia": not_found,
        "names_with_parentheses": names_with_parentheses,
    }


# ==================== LOT D bis: Batch Rename Persons ====================

@api_router.post("/admin/rename-persons-batch")
@limiter.limit("5/15minutes")
async def admin_rename_persons_batch(request: Request):
    """
    Lot D bonus: Rename persons (e.g. remove parenthetical suffixes).
    Body: { "renames": [{"old_name": "Robert Smith (musician)", "new_name": "Robert Smith"}, ...] }
    """
    _require_admin_auth(request)
    body = await request.json()
    renames = body.get("renames", [])

    results = {"success": True, "renamed": [], "not_found": [], "total_renamed": 0}

    for item in renames:
        old_name = item.get("old_name", "").strip()
        new_name = item.get("new_name", "").strip()
        if not old_name or not new_name:
            continue

        result = await db.persons.update_one(
            {"name": {"$regex": f"^{re.escape(old_name)}$", "$options": "i"}},
            {"$set": {"name": new_name, "updated_at": now_utc()}}
        )

        if result.matched_count == 0:
            results["not_found"].append(old_name)
        else:
            results["renamed"].append({"old_name": old_name, "new_name": new_name})
            results["total_renamed"] += 1

    logger.info(f"✏️ Lot D rename: {results['total_renamed']} renamed, {len(results['not_found'])} not found")
    return results


# ==================== LOT 3: Alpha Management Endpoints ====================

@api_router.get("/admin/get-alpha")
async def admin_get_alpha(request: Request):
    """Get current alpha coefficient. α = blend weight: index = α×external + (1-α)×votes."""
    _require_admin_auth(request)
    settings = await db.app_settings.find_one({"_id": "global"})
    alpha = settings.get("alpha", 1.0) if settings else 1.0
    last_updated = settings.get("alpha_last_updated") if settings else None
    return {"alpha": alpha, "last_updated": last_updated}


@api_router.post("/admin/set-alpha")
@limiter.limit("10/15minutes")
async def admin_set_alpha(request: Request):
    """Set alpha coefficient. Body: {"alpha": 0.7}. Must be 0 ≤ α ≤ 1."""
    _require_admin_auth(request)
    body = await request.json()
    new_alpha = body.get("alpha")
    if new_alpha is None or not isinstance(new_alpha, (int, float)):
        return {"error": "alpha must be a number"}
    new_alpha = float(new_alpha)
    if new_alpha < 0 or new_alpha > 1:
        return {"error": "alpha must be between 0 and 1"}

    now = now_utc()
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$set": {"alpha": new_alpha, "alpha_last_updated": now}},
        upsert=True
    )

    # Invalidate the alpha cache in popularoo_index
    from popularoo_index import _alpha_cache, _alpha_last_loaded
    import popularoo_index
    popularoo_index._alpha_cache = None
    popularoo_index._alpha_last_loaded = None

    logger.info(f"⚖️ Alpha set to {new_alpha} by admin")
    return {
        "success": True,
        "alpha": new_alpha,
        "last_updated": now,
        "note": "Scores will update within 15 minutes (next recalculation cycle). Use /admin/recalculate-all-indices for immediate effect."
    }


# NOTE: Route /admin/recalculate-all-indices is defined earlier (line ~4338).
# Duplicate removed during Session 2 cleanup.


# ==================== LOT 2: Manual External Scores Recalculation ====================

@api_router.post("/admin/recalculate-external-scores")
@limiter.limit("2/15minutes")
async def admin_recalculate_external_scores(request: Request):
    """
    Lot 2: Manually trigger the daily external scores job.
    Fetches Wikipedia pageviews for ALL non-outsider celebrities,
    normalizes (log scale), and saves popularity_external_score to each person.
    Returns execution summary.
    """
    _require_admin_auth(request)
    from scheduler import run_daily_external_scores_job
    summary = await run_daily_external_scores_job(db)
    return summary


# ==================== LOT 4: Diagnose External Scores ====================

@api_router.post("/admin/diagnose-external-scores")
async def admin_diagnose_external_scores(request: Request):
    """
    Lot 4: Read-only diagnostic of external scores health.
    Returns stats, top/bottom 10, and high-divergence anomalies.
    """
    _require_admin_auth(request)
    from popularoo_index import compute_score_votes_users

    now = now_utc()
    cutoff_48h = now - timedelta(hours=48)

    # Fetch all non-outsider persons
    all_persons = await db.persons.find(
        {"source": {"$ne": "self_boosted"}, "category": {"$ne": "outsider"}}
    ).to_list(length=5000)

    total_persons = len(all_persons)
    with_ext = 0
    without_ext = 0
    updated_within_48h = 0
    updated_older = 0
    ext_scores = []
    high_divergence = []

    for doc in all_persons:
        ext = doc.get("popularity_external_score")
        last_update = doc.get("last_external_update")

        if ext is not None:
            with_ext += 1
            ext_scores.append({"name": doc.get("name", "?"), "ext": ext, "doc": doc})

            if last_update and last_update >= cutoff_48h:
                updated_within_48h += 1
            else:
                updated_older += 1
        else:
            without_ext += 1

    # Compute average, min, max
    ext_values = [e["ext"] for e in ext_scores]
    avg_ext = round(sum(ext_values) / len(ext_values), 1) if ext_values else 0.0
    max_ext = round(max(ext_values), 1) if ext_values else 0.0
    min_ext = round(min(ext_values), 1) if ext_values else 0.0

    # Top 10 and Bottom 10 by external score
    sorted_by_ext = sorted(ext_scores, key=lambda x: x["ext"], reverse=True)
    top_10 = [{"name": e["name"], "external_score": round(e["ext"], 1)} for e in sorted_by_ext[:10]]
    bottom_10 = [{"name": e["name"], "external_score": round(e["ext"], 1)} for e in sorted_by_ext[-10:]]

    # High divergence: |external - votes_score| > 50
    for e in ext_scores:
        votes_score = compute_score_votes_users(e["doc"])
        diff = abs(e["ext"] - votes_score)
        if diff > 50:
            high_divergence.append({
                "name": e["name"],
                "external_score": round(e["ext"], 1),
                "votes_score": round(votes_score, 1),
                "diff": round(diff, 1),
            })

    high_divergence.sort(key=lambda x: x["diff"], reverse=True)

    return {
        "total_persons": total_persons,
        "with_external_score": with_ext,
        "without_external_score": without_ext,
        "updated_within_48h": updated_within_48h,
        "updated_older_than_48h": updated_older,
        "average_external_score": avg_ext,
        "max_external_score": max_ext,
        "min_external_score": min_ext,
        "top_10_external": top_10,
        "bottom_10_external": bottom_10,
        "high_divergence": high_divergence,
    }


# ==================== LOT 1: Test External Score (Temporary) ====================

@api_router.post("/admin/test-external-score")
@limiter.limit("10/15minutes")
async def admin_test_external_score(request: Request):
    """
    Lot 1 test endpoint: compute external score for one or multiple celebrities.
    Single: { "name": "Donald Trump" }
    Batch:  { "names": ["Donald Trump", "Squeezie", "Brad Pitt"] }
    Batch mode normalizes across the group (simulates full DB batch).
    """
    _require_admin_auth(request)
    body = await request.json()

    single_name = body.get("name", "").strip()
    names = body.get("names", [])

    if single_name and not names:
        # Single mode
        from external_scores import compute_external_score_for_person
        result = await compute_external_score_for_person(single_name)
        return result
    elif names:
        # Batch mode with cross-normalization
        from external_scores import compute_external_scores_batch
        result = await compute_external_scores_batch(names)
        return result
    else:
        return {"error": "Provide 'name' (single) or 'names' (batch list)"}


# ==================== LOT D ter: Add Celebrities Batch ====================

@api_router.post("/admin/add-celebrities-batch")
@limiter.limit("5/15minutes")
async def admin_add_celebrities_batch(request: Request):
    """
    Add multiple celebrities to the database in one batch.
    Skips duplicates (by slug). Initializes with realistic vote counts.
    Body: { "celebrities": [{"name": "Brad Pitt", "category": "culture"}, ...] }
    """
    _require_admin_auth(request)
    import random
    body = await request.json()
    celebrities = body.get("celebrities", [])

    now = now_utc()
    results = {"added": [], "skipped_duplicates": [], "skipped_blocklisted": [], "errors": [], "total_added": 0}

    for celeb in celebrities:
        name = celeb.get("name", "").strip()
        category = celeb.get("category", "culture").strip().lower()
        if not name:
            results["errors"].append({"name": name, "error": "empty name"})
            continue

        slug = slugify(name)

        # Anti-ghost: never re-create a blocklisted (deleted) personality.
        if await is_person_blocklisted(name_normalized=normalize_person_name(name), slug=slug):
            results["skipped_blocklisted"].append(name)
            logger.info(f"🚫 [Anti-ghost] batch-add skipped blocklisted '{name}'")
            continue

        existing = await db.persons.find_one({"slug": slug})
        if existing:
            results["skipped_duplicates"].append(name)
            continue

        # Realistic initial votes (similar to existing seeds)
        init_likes = random.randint(6000, 12000)
        init_dislikes = random.randint(1500, 4000)
        total = init_likes + init_dislikes
        score = round((init_likes / max(1, total)) * 200 - 100, 1)

        doc = {
            "name": name,
            "slug": slug,
            "category": category,
            "approved": True,
            "created_at": now,
            "updated_at": now,
            "score": score,
            "likes": init_likes,
            "dislikes": init_dislikes,
            "total_votes": total,
            "seed_votes_likes": init_likes,
            "seed_votes_dislikes": init_dislikes,
            "source": "seed",
            "is_international": True,
            "country_tags": ["international"],
        }

        try:
            result = await db.persons.insert_one(doc)
            # Insert initial tick
            await db.person_ticks.insert_one({
                "person_id": result.inserted_id,
                "score": score,
                "total_votes": total,
                "created_at": now,
            })
            results["added"].append({"name": name, "category": category, "votes": total})
            results["total_added"] += 1
        except Exception as e:
            results["errors"].append({"name": name, "error": str(e)})

    logger.info(f"🌟 Batch add: {results['total_added']} added, {len(results['skipped_duplicates'])} duplicates skipped")
    return results


# ==================== SESSION 3 — LOT 1: Candidate Detection ====================

@api_router.post("/admin/run-candidate-detection")
@limiter.limit("2/60minutes")
async def admin_run_candidate_detection(request: Request):
    """
    Session 3 Lot 1: Manually trigger candidate detection.
    Scans WikiMedia Most Viewed across 6 languages, filters eligible humans,
    writes to candidate_queue for admin review.
    """
    _require_admin_auth(request)
    from candidate_detection import detect_candidates
    summary = await detect_candidates(db)
    return summary


@api_router.get("/admin/candidates")
async def admin_list_candidates(request: Request, status: str = "pending"):
    """
    List candidates from the queue.
    ?status=pending (default) | approved | rejected | all
    """
    _require_admin_auth(request)

    filt = {} if status == "all" else {"status": status}
    candidates = await db.candidate_queue.find(filt).sort("wiki_score", -1).to_list(500)

    return [
        {
            "id": str(c["_id"]),
            "name": c.get("name"),
            "category_suggested": c.get("category_suggested", "other"),
            "confidence": c.get("confidence", "low"),
            "wiki_score": c.get("wiki_score", 0),
            "wiki_langs": c.get("wiki_langs", []),
            "wiki_lang_count": c.get("wiki_lang_count", 0),
            "wiki_description": c.get("wiki_description", ""),
            "wikidata_id": c.get("wikidata_id"),
            "detected_at": c.get("detected_at", "").isoformat() if c.get("detected_at") else None,
            "status": c.get("status", "pending"),
        }
        for c in candidates
    ]


@api_router.post("/admin/candidates/{candidate_id}/approve")
async def admin_approve_candidate(candidate_id: str, request: Request):
    """
    Approve a candidate: creates person in DB with realistic initial votes,
    marks candidate as approved.
    Optional body: { "category": "sport" } to override suggested category.
    """
    _require_admin_auth(request)
    import random

    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    candidate = await db.candidate_queue.find_one({"_id": oid, "status": "pending"})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")

    # ── Vague 4, sous-tâche 6: user_search candidates use the deferred-V4 flow ──
    # (fresh re-validation + Q1 PI + Q4 simulated votes + Q3 implicit like).
    if candidate.get("source") == "user_search":
        from candidate_detection import approve_user_search_candidate
        outcome = await approve_user_search_candidate(db, candidate)
        if outcome["status"] == "rejected":
            return {
                "success": False,
                "error": "rejected",
                "error_code": outcome.get("error_code"),
                "name": outcome["name"],
            }
        if outcome["status"] == "duplicate":
            return {
                "success": False,
                "error": "duplicate",
                "name": outcome["name"],
                "person_id": outcome.get("person_id"),
            }
        logger.info(f"✅ Candidate approved (user_search): {outcome['name']} PI={outcome['initial_pi']:.2f}")
        return {
            "success": True,
            "name": outcome["name"],
            "category": outcome["category"],
            "person_id": outcome["person_id"],
            "initial_pi": outcome["initial_pi"],
            "source": "user_search",
        }

    # Allow category override from body
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    category = body.get("category", candidate.get("category_suggested", "other"))

    name = candidate["name"]
    name_slug = candidate.get("slug") or slugify(name)
    now = now_utc()

    # Anti-ghost: never re-create a deleted personality, even via admin approval.
    if await is_person_blocklisted(
        name_normalized=candidate.get("name_normalized") or normalize_person_name(name),
        wikidata_id=candidate.get("wikidata_id", ""),
        slug=name_slug,
    ):
        await db.candidate_queue.update_one({"_id": oid}, {"$set": {"status": "blocklisted", "updated_at": now}})
        logger.info(f"🚫 [Anti-ghost] Approval blocked for blocklisted candidate '{name}'")
        return {"success": False, "error": "blocklisted", "message": f"'{name}' is blocklisted and cannot be re-created"}

    # Check duplicate in persons
    existing = await db.persons.find_one({"slug": name_slug})
    if existing:
        await db.candidate_queue.update_one({"_id": oid}, {"$set": {"status": "duplicate", "updated_at": now}})
        return {"success": False, "error": "duplicate", "message": f"'{name}' already exists in DB"}

    # Create person with realistic initial votes
    init_likes = random.randint(6000, 12000)
    init_dislikes = random.randint(1500, 4000)
    total = init_likes + init_dislikes

    person_doc = {
        "name": name,
        "slug": name_slug,
        "category": category,
        "approved": True,
        "created_at": now,
        "updated_at": now,
        "score": 50.0,
        "likes": init_likes,
        "dislikes": init_dislikes,
        "total_votes": total,
        "seed_votes_likes": init_likes,
        "seed_votes_dislikes": init_dislikes,
        "source": "auto_detected",
        "wiki_description": candidate.get("wiki_description", ""),
        "wikidata_id": candidate.get("wikidata_id"),
        "wiki_langs": candidate.get("wiki_langs", []),
    }

    result = await db.persons.insert_one(person_doc)
    person_id = result.inserted_id

    # Initial tick
    await db.person_ticks.insert_one({
        "person_id": person_id,
        "score": person_doc["score"],
        "total_votes": total,
        "created_at": now,
    })

    # Mark candidate as approved
    await db.candidate_queue.update_one(
        {"_id": oid},
        {"$set": {"status": "approved", "approved_at": now, "person_id": str(person_id)}}
    )

    logger.info(f"✅ Candidate approved: {name} ({category})")
    return {
        "success": True,
        "name": name,
        "category": category,
        "person_id": str(person_id),
    }


@api_router.post("/admin/candidates/{candidate_id}/reject")
async def admin_reject_candidate(candidate_id: str, request: Request):
    """Reject a candidate. Marks as rejected in queue."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    result = await db.candidate_queue.update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "rejected", "rejected_at": now_utc()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")

    return {"success": True, "candidate_id": candidate_id, "status": "rejected"}


@api_router.post("/admin/candidates/approve-all-high")
async def admin_approve_all_high(request: Request):
    """Batch approve all pending candidates with confidence='high'."""
    _require_admin_auth(request)
    import random

    high_candidates = await db.candidate_queue.find(
        {"status": "pending", "confidence": "high"}
    ).to_list(500)

    results = {"approved": 0, "duplicates": 0, "errors": 0, "blocklisted": 0}
    now = now_utc()

    for candidate in high_candidates:
        name = candidate["name"]
        name_slug = candidate.get("slug") or slugify(name)

        # Anti-ghost: skip candidates matching a deleted personality.
        if await is_person_blocklisted(
            name_normalized=candidate.get("name_normalized") or normalize_person_name(name),
            wikidata_id=candidate.get("wikidata_id", ""),
            slug=name_slug,
        ):
            await db.candidate_queue.update_one(
                {"_id": candidate["_id"]},
                {"$set": {"status": "blocklisted", "updated_at": now}}
            )
            results["blocklisted"] += 1
            logger.info(f"🚫 [Anti-ghost] Batch-approve skipped blocklisted '{name}'")
            continue

        existing = await db.persons.find_one({"slug": name_slug})
        if existing:
            await db.candidate_queue.update_one(
                {"_id": candidate["_id"]},
                {"$set": {"status": "duplicate", "updated_at": now}}
            )
            results["duplicates"] += 1
            continue

        category = candidate.get("category_suggested", "other")
        init_likes = random.randint(6000, 12000)
        init_dislikes = random.randint(1500, 4000)
        total = init_likes + init_dislikes

        person_doc = {
            "name": name,
            "slug": name_slug,
            "category": category,
            "approved": True,
            "created_at": now,
            "updated_at": now,
            "score": 50.0,
            "likes": init_likes,
            "dislikes": init_dislikes,
            "total_votes": total,
            "seed_votes_likes": init_likes,
            "seed_votes_dislikes": init_dislikes,
            "source": "auto_detected",
            "wiki_description": candidate.get("wiki_description", ""),
            "wikidata_id": candidate.get("wikidata_id"),
            "wiki_langs": candidate.get("wiki_langs", []),
        }

        try:
            result = await db.persons.insert_one(person_doc)
            await db.person_ticks.insert_one({
                "person_id": result.inserted_id,
                "score": person_doc["score"],
                "total_votes": total,
                "created_at": now,
            })
            await db.candidate_queue.update_one(
                {"_id": candidate["_id"]},
                {"$set": {"status": "approved", "approved_at": now, "person_id": str(result.inserted_id)}}
            )
            results["approved"] += 1
        except Exception as e:
            logger.error(f"Error approving {name}: {e}")
            results["errors"] += 1

    return {"success": True, **results}


@api_router.post("/admin/propose-celebrity-to-queue")
async def admin_propose_celebrity_to_queue(request: Request):
    """
    Session 3 Lot 1 (legacy): Manual celebrity proposal → candidate_queue.
    Replaced by Lot 3 POST /admin/propose-celebrity which creates directly.
    Kept for backward compatibility (queue-based flow).
    Body: { "name": "Full Name" }
    """
    _require_admin_auth(request)
    body = await request.json()
    name = body.get("name", "").strip()

    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters")

    name_slug = slugify(name)
    existing = await db.persons.find_one({"slug": name_slug})
    if existing:
        return {"success": False, "error": "already_exists", "message": f"'{name}' already in database"}

    from unidecode import unidecode as _unidecode
    name_norm = _unidecode(name).lower().strip()
    existing_q = await db.candidate_queue.find_one({"name_normalized": name_norm, "status": "pending"})
    if existing_q:
        return {"success": False, "error": "already_in_queue", "message": f"'{name}' already pending in queue"}

    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        from candidate_detection import check_is_human_alive, check_multi_lang_pages, infer_category
        is_human, is_deceased, wikidata_id, description = await check_is_human_alive(name, client)
        if not is_human:
            return {"success": False, "error": "not_human", "message": f"'{name}' not identified as a human in Wikidata."}
        if is_deceased:
            return {"success": False, "error": "deceased", "message": f"'{name}' is marked as deceased in Wikidata (P570)."}
        langs = await check_multi_lang_pages(name, client)
        category, confidence = infer_category(description or "")

    now = now_utc()
    candidate_doc = {
        "name": name, "name_normalized": name_norm, "slug": name_slug,
        "category_suggested": category, "confidence": confidence,
        "wiki_score": 0, "wiki_langs": langs, "wiki_lang_count": len(langs),
        "wiki_description": description or "", "wikidata_id": wikidata_id,
        "detected_at": now, "status": "pending", "source": "manual_proposal",
    }
    result = await db.candidate_queue.insert_one(candidate_doc)
    return {
        "success": True, "candidate_id": str(result.inserted_id), "name": name,
        "category_suggested": category, "confidence": confidence,
        "wiki_description": description or "", "wiki_langs": langs,
        "message": f"'{name}' added to candidate queue for review",
    }


# ==================== SESSION 3 — LOT 2: Deceased Queue ====================

@api_router.get("/admin/deceased-queue")
async def admin_list_deceased_queue(request: Request, status: str = "pending"):
    """List deceased detections from queue. ?status=pending|confirmed|false_positive|all"""
    _require_admin_auth(request)

    filt = {} if status == "all" else {"status": status}
    items = await db.deceased_queue.find(filt).sort("detected_at", -1).to_list(500)

    return [
        {
            "id": str(d["_id"]),
            "person_id": str(d.get("person_id", "")),
            "name": d.get("name", ""),
            "category": d.get("category", "other"),
            "death_date": d.get("death_date", ""),
            "wikidata_id": d.get("wikidata_id"),
            "detected_at": d.get("detected_at", "").isoformat() if d.get("detected_at") else None,
            "status": d.get("status", "pending"),
        }
        for d in items
    ]


@api_router.post("/admin/deceased/{item_id}/confirm")
async def admin_confirm_deceased(item_id: str, request: Request):
    """
    Confirm a deceased detection: deactivates the person, cancels Daily Runs,
    marks queue item as confirmed.
    """
    _require_admin_auth(request)
    from person_maintenance import _cancel_daily_runs_for_deceased

    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid item ID")

    item = await db.deceased_queue.find_one({"_id": oid, "status": "pending"})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found or not pending")

    person_id = item.get("person_id")
    name = item.get("name", "")
    now = now_utc()

    # Deactivate the person
    await db.persons.update_one(
        {"_id": person_id},
        {"$set": {
            "is_deceased": True,
            "approved": False,
            "deactivated_reason": "deceased",
            "deactivated_at": now,
            "death_date_wikidata": item.get("death_date"),
        }}
    )

    # Cancel active Daily Runs
    await _cancel_daily_runs_for_deceased(db, person_id, name, now)

    # Mark queue item as confirmed
    await db.deceased_queue.update_one(
        {"_id": oid},
        {"$set": {"status": "confirmed", "confirmed_at": now}}
    )

    # Session 3: Add slug to seed_blocklist (structural anti-reinsertion)
    name_slug = slugify(name)
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$addToSet": {"seed_blocklist": name_slug}},
        upsert=True,
    )
    logger.info(f"🚫 Added '{name_slug}' to seed_blocklist")

    logger.info(f"⚰️ Deceased confirmed by admin: {name}")
    return {"success": True, "name": name, "action": "deactivated", "blocked_from_seed": name_slug}


@api_router.post("/admin/deceased/{item_id}/reject")
async def admin_reject_deceased(item_id: str, request: Request):
    """Reject a deceased detection (false positive)."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid item ID")

    result = await db.deceased_queue.update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "false_positive", "rejected_at": now_utc()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found or not pending")

    return {"success": True, "item_id": item_id, "status": "false_positive"}


@api_router.post("/admin/deceased/confirm-all")
async def admin_confirm_all_deceased(request: Request):
    """Batch confirm all pending deceased detections."""
    _require_admin_auth(request)
    from person_maintenance import _cancel_daily_runs_for_deceased

    pending = await db.deceased_queue.find({"status": "pending"}).to_list(500)
    now = now_utc()
    confirmed = 0

    for item in pending:
        person_id = item.get("person_id")
        name = item.get("name", "")

        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {
                "is_deceased": True,
                "approved": False,
                "deactivated_reason": "deceased",
                "deactivated_at": now,
                "death_date_wikidata": item.get("death_date"),
            }}
        )
        await _cancel_daily_runs_for_deceased(db, person_id, name, now)
        await db.deceased_queue.update_one(
            {"_id": item["_id"]},
            {"$set": {"status": "confirmed", "confirmed_at": now}}
        )

        # Session 3: Add slug to seed_blocklist (structural anti-reinsertion)
        name_slug = slugify(name)
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$addToSet": {"seed_blocklist": name_slug}},
            upsert=True,
        )

        confirmed += 1

    return {"success": True, "confirmed": confirmed}


@api_router.post("/admin/run-deceased-check")
@limiter.limit("2/60minutes")
async def admin_run_deceased_check(request: Request):
    """Manually trigger deceased check for all personalities."""
    _require_admin_auth(request)
    from person_maintenance import check_deceased_all
    result = await check_deceased_all(db)
    return {"success": True, **result}


# ==================== SESSION 3 — LOT 2: Category Reviews ====================

@api_router.post("/admin/run-category-review")
@limiter.limit("2/60minutes")
async def admin_run_category_review(request: Request):
    """
    Manually trigger category re-inference for all personalities.
    Compares current category with Wikipedia-inferred category,
    writes divergences to category_reviews collection.
    """
    _require_admin_auth(request)

    import httpx as _httpx
    from candidate_detection import infer_category

    now = now_utc()
    reviewed = 0
    divergences = 0

    # Aligné sur admin_audit_categories (server.py:6410) : pas de filtre approved.
    # Les profils non-approved peuvent aussi avoir une catégorie incorrecte.
    persons = await db.persons.find({
        "source": {"$ne": "self_boosted"},
        "category": {"$ne": "outsider"},
    }).to_list(5000)

    async with _httpx.AsyncClient(timeout=10) as client:
        for person in persons:
            name = person.get("name", "")
            current_cat = person.get("category", "other")

            # Nettoyage parenthèses Wikipedia ("Robert Smith (musician)" → "Robert Smith")
            # pour éviter les 404 sur le REST API.
            clean_name, _suffix = _clean_name_parentheses(name)
            title = clean_name.replace(" ", "_")
            description = ""
            try:
                resp = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                    headers={"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    description = data.get("description", "")
                await asyncio.sleep(0.1)
            except Exception:
                pass

            if not description:
                reviewed += 1
                continue

            suggested_cat, confidence = infer_category(description)

            if suggested_cat != current_cat and suggested_cat != "other":
                # Only flag if the suggestion is NOT "other" (we don't want to downgrade)
                existing = await db.category_reviews.find_one({
                    "person_id": person["_id"],
                    "status": "pending",
                })
                if not existing:
                    await db.category_reviews.insert_one({
                        "person_id": person["_id"],
                        "name": name,
                        "current_category": current_cat,
                        "suggested_category": suggested_cat,
                        "confidence": confidence,
                        "wiki_description": description,
                        "created_at": now,
                        "status": "pending",
                    })
                    divergences += 1
                elif existing.get("suggested_category") != suggested_cat:
                    # Mapping enrichi : la suggestion a changé → on update la review
                    # pending sans créer de doublon (idempotence + fraîcheur).
                    await db.category_reviews.update_one(
                        {"_id": existing["_id"]},
                        {"$set": {
                            "suggested_category": suggested_cat,
                            "confidence": confidence,
                            "wiki_description": description,
                            "last_updated_at": now,
                        }},
                    )
                    divergences += 1

            reviewed += 1

    # Store last run summary
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$set": {"last_category_review_run": {
            "timestamp": now.isoformat(),
            "reviewed": reviewed,
            "divergences": divergences,
        }}},
        upsert=True,
    )

    return {"success": True, "reviewed": reviewed, "divergences": divergences}


@api_router.get("/admin/category-reviews")
async def admin_list_category_reviews(request: Request, status: str = "pending"):
    """List category review suggestions. ?status=pending|applied|rejected|all"""
    _require_admin_auth(request)

    filt = {} if status == "all" else {"status": status}
    items = await db.category_reviews.find(filt).sort("created_at", -1).to_list(500)

    return [
        {
            "id": str(r["_id"]),
            "person_id": str(r.get("person_id", "")),
            "name": r.get("name", ""),
            "current_category": r.get("current_category", ""),
            "suggested_category": r.get("suggested_category", ""),
            "confidence": r.get("confidence", "low"),
            "wiki_description": r.get("wiki_description", ""),
            "created_at": r.get("created_at", "").isoformat() if r.get("created_at") else None,
            "status": r.get("status", "pending"),
        }
        for r in items
    ]


@api_router.post("/admin/category-reviews/{review_id}/apply")
async def admin_apply_category_review(review_id: str, request: Request):
    """Apply a category suggestion: updates the person's category."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review ID")

    review = await db.category_reviews.find_one({"_id": oid, "status": "pending"})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found or not pending")

    person_id = review.get("person_id")
    new_cat = review.get("suggested_category")

    await db.persons.update_one(
        {"_id": person_id},
        {"$set": {"category": new_cat, "category_updated_at": now_utc()}}
    )

    await db.category_reviews.update_one(
        {"_id": oid},
        {"$set": {"status": "applied", "applied_at": now_utc()}}
    )

    return {"success": True, "name": review.get("name"), "new_category": new_cat}


@api_router.post("/admin/category-reviews/{review_id}/reject")
async def admin_reject_category_review(review_id: str, request: Request):
    """Reject a category suggestion: keep current category."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review ID")

    result = await db.category_reviews.update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "rejected", "rejected_at": now_utc()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Review not found or not pending")

    return {"success": True, "review_id": review_id, "status": "rejected"}


# ==================== SESSION 3 — LOT 2: Dashboard Stats ====================

@api_router.get("/admin/dashboard-stats")
async def admin_dashboard_stats(request: Request):
    """
    Enriched dashboard stats for the admin panel.
    Returns: total celebrities, category breakdown, alpha, last job dates, top 5.
    """
    _require_admin_auth(request)
    from popularoo_index import get_alpha

    # Total celebrities (non-outsider, approved)
    total = await db.persons.count_documents({
        "approved": True,
        "source": {"$ne": "self_boosted"},
        "category": {"$ne": "outsider"},
    })

    # Category breakdown
    pipeline = [
        {"$match": {
            "approved": True,
            "source": {"$ne": "self_boosted"},
            "category": {"$ne": "outsider"},
        }},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    cat_breakdown = {}
    async for doc in db.persons.aggregate(pipeline):
        cat_breakdown[doc["_id"] or "other"] = doc["count"]

    # Alpha
    alpha = await get_alpha(db)

    # Last job dates from app_settings
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    last_ext_scores = settings.get("last_external_scores_run", {})
    last_candidate = settings.get("last_candidate_detection_run", {})
    last_deceased_top50 = settings.get("last_deceased_check_top50", {})
    last_deceased_all = settings.get("last_deceased_check_all", {})
    last_cat_review = settings.get("last_category_review_run", {})

    # Top 5 by popularoo_index
    top5_cursor = db.persons.find({
        "approved": True,
        "source": {"$ne": "self_boosted"},
        "category": {"$ne": "outsider"},
    }).sort("popularoo_index", -1).limit(5)

    top5 = []
    async for doc in top5_cursor:
        top5.append({
            "name": doc.get("name"),
            "category": doc.get("category"),
            "popularoo_index": round(doc.get("popularoo_index", 0), 1),
        })

    # Queue sizes
    pending_candidates = await db.candidate_queue.count_documents({"status": "pending"})
    pending_deceased = await db.deceased_queue.count_documents({"status": "pending"})
    pending_cat_reviews = await db.category_reviews.count_documents({"status": "pending"})

    return {
        "total_celebrities": total,
        "category_breakdown": cat_breakdown,
        "alpha": alpha,
        "queues": {
            "pending_candidates": pending_candidates,
            "pending_deceased": pending_deceased,
            "pending_category_reviews": pending_cat_reviews,
        },
        "last_jobs": {
            "external_scores": last_ext_scores.get("timestamp") if isinstance(last_ext_scores, dict) else None,
            "candidate_detection": last_candidate.get("timestamp") if isinstance(last_candidate, dict) else None,
            "deceased_check_top50": last_deceased_top50.get("timestamp") if isinstance(last_deceased_top50, dict) else None,
            "deceased_check_all": last_deceased_all.get("timestamp") if isinstance(last_deceased_all, dict) else None,
            "category_review": last_cat_review.get("timestamp") if isinstance(last_cat_review, dict) else None,
        },
        "top5": top5,
    }


# ==================== SESSION 3 — LOT 2: Admin User Creations ====================

@api_router.get("/admin/user-creations")
async def admin_list_user_creations(request: Request):
    """List profiles created via user search in the last 72h."""
    _require_admin_auth(request)

    cutoff_72h = now_utc() - timedelta(hours=72)
    items = await db.persons.find({
        "source": "user_search",
        "created_at": {"$gte": cutoff_72h},
    }).sort("created_at", -1).to_list(500)

    return [
        {
            "id": str(p["_id"]),
            "name": p.get("name"),
            "category": p.get("category", "other"),
            "category_confidence": p.get("category_confidence", "low"),
            "score": round(p.get("score", 0), 1),
            "popularoo_index": round(p.get("popularoo_index", 0), 1),
            "popularity_external_score": round(p.get("popularity_external_score", 0), 1),
            "total_votes": p.get("total_votes", 0),
            "visible_in_rankings": p.get("visible_in_rankings", True),
            "wiki_description": p.get("wiki_description", ""),
            "created_at": p.get("created_at", "").isoformat() if p.get("created_at") else None,
        }
        for p in items
    ]


@api_router.post("/admin/user-creations/{person_id}/validate")
async def admin_validate_user_creation(person_id: str, request: Request):
    """Immediately promote a user-created profile to visible in rankings."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person ID")

    result = await db.persons.update_one(
        {"_id": oid, "source": "user_search"},
        {"$set": {"visible_in_rankings": True, "promoted_at": now_utc()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found or not a user_search profile")

    return {"success": True, "person_id": person_id, "visible_in_rankings": True}


@api_router.post("/admin/user-creations/{person_id}/update-category")
async def admin_update_user_creation_category(person_id: str, request: Request):
    """Update the category of a user-created profile. Body: {"category": "sport"}"""
    _require_admin_auth(request)

    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person ID")

    body = await request.json()
    new_cat = body.get("category", "").lower()
    valid_cats = {"politics", "culture", "business", "sport", "influencer", "other"}
    if new_cat not in valid_cats:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {valid_cats}")

    result = await db.persons.update_one(
        {"_id": oid},
        {"$set": {"category": new_cat, "category_updated_at": now_utc()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {"success": True, "person_id": person_id, "new_category": new_cat}


@api_router.post("/admin/user-creations/{person_id}/delete-block")
async def admin_delete_block_user_creation(person_id: str, request: Request):
    """Delete a user-created profile and add to blocklist."""
    _require_admin_auth(request)

    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person ID")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Profile not found")

    name = person.get("name", "")
    name_slug = person.get("slug", slugify(name))

    # Delete the person
    await db.persons.delete_one({"_id": oid})

    # Add to blocklist
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$addToSet": {"seed_blocklist": name_slug}},
        upsert=True,
    )

    logger.info(f"🚫 [Admin] Deleted + blocked user-created profile: {name}")
    return {"success": True, "name": name, "blocked_slug": name_slug}


# ==================== VAGUE 4 — Lot 4 sous-tache 1: Pending Candidate Queue (admin) ====================

@api_router.get("/admin/pending-candidate-queue")
async def admin_list_pending_candidate_queue(request: Request):
    """
    Vague 4 — List user_search candidate_queue entries still waiting for the
    24h auto-validation. These are the real submissions admin can intervene on
    before the scheduled process_after.

    Filter: source="user_search" AND status="pending".
    Sort: requested_at ASC (oldest first — they'll be processed first).
    No limit (the queue stays small in V1).
    """
    _require_admin_auth(request)

    items = await db.candidate_queue.find({
        "source": "user_search",
        "status": "pending",
    }).sort("requested_at", 1).to_list(None)

    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else v

    return [
        {
            "id": str(c["_id"]),
            "name": c.get("name"),
            "slug": c.get("slug"),
            "requested_at": _iso(c.get("requested_at")),
            "process_after": _iso(c.get("process_after")),
            "requested_by_device_id": c.get("requested_by_device_id"),
            "pending_vote_value": c.get("pending_vote_value", 0),
            # validation_error is set when a previous approve attempt failed (rare for pending,
            # but kept for visibility if a retry left the entry in pending state).
            "last_error": c.get("validation_error"),
        }
        for c in items
    ]


@api_router.post("/admin/candidate-queue/{candidate_id}/force-validate")
async def admin_force_validate_candidate(candidate_id: str, request: Request):
    """
    Vague 4 — Force-validate a pending user_search candidate BEFORE the 24h delay.
    Re-uses approve_user_search_candidate (sous-tache 6) which handles fresh
    re-validation, dedup, PI computation, simulated votes, and queue status update.
    """
    _require_admin_auth(request)

    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    candidate = await db.candidate_queue.find_one({
        "_id": oid,
        "source": "user_search",
        "status": "pending",
    })
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")

    from candidate_detection import approve_user_search_candidate
    outcome = await approve_user_search_candidate(db, candidate)

    if outcome["status"] == "approved":
        return {
            "success": True,
            "person_id": outcome["person_id"],
            "initial_pi": outcome["initial_pi"],
            "category": outcome["category"],
            "name": outcome["name"],
        }
    if outcome["status"] == "duplicate":
        return {
            "success": False,
            "error_code": "duplicate",
            "error_message": f"'{outcome['name']}' already exists in DB",
            "person_id": outcome.get("person_id"),
        }
    # rejected
    return {
        "success": False,
        "error_code": outcome.get("error_code") or "unknown",
        "error_message": f"Validation failed: {outcome.get('error_code')}",
        "name": outcome.get("name"),
    }


@api_router.post("/admin/candidate-queue/{candidate_id}/reject")
async def admin_reject_candidate_queue(candidate_id: str, request: Request):
    """
    Vague 4 — Reject a pending user_search candidate BEFORE the 24h delay.
    Marks the queue entry as rejected (admin_manual_reject) and adds the slug
    to the seed_blocklist so the same submission cannot be re-queued.
    """
    _require_admin_auth(request)

    try:
        oid = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate ID")

    candidate = await db.candidate_queue.find_one({
        "_id": oid,
        "source": "user_search",
        "status": "pending",
    })
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found or not pending")

    now = now_utc()
    slug = candidate.get("slug") or slugify(candidate.get("name", ""))

    await db.candidate_queue.update_one(
        {"_id": oid},
        {"$set": {
            "status": "rejected",
            "validated_at": now,
            "validation_error": "admin_manual_reject",
        }},
    )

    if slug:
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$addToSet": {"seed_blocklist": slug}},
            upsert=True,
        )

    logger.info(f"🚫 [Admin] Rejected pending user_search candidate '{candidate.get('name')}' + blocklisted slug='{slug}'")
    return {"success": True, "candidate_id": candidate_id, "blocked_slug": slug}


# ==================== SESSION 3 — LOT 3: Outsider Moderation + Manual Proposal ====================

# ── Family 1: POST /api/admin/propose-celebrity — Manual admin celebrity addition ──

@api_router.post("/admin/propose-celebrity")
async def admin_propose_celebrity(request: Request):
    """
    Session 3 Lot 3: Manual celebrity addition by admin.
    Validates name (≥2 words, no digits), category, then runs full Wikipedia/Wikidata
    guard-fous pipeline. Creates the person IMMEDIATELY with visibility=true.
    """
    _require_admin_auth(request)
    body = await request.json()

    name = (body.get("name") or "").strip()
    category = (body.get("category") or "").strip().lower()

    # ── Validate name ──
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    words = name.split()
    if len(words) < 2:
        raise HTTPException(status_code=400, detail="Name must contain at least 2 words")
    # No digits
    import re as _re
    if _re.search(r"\d", name):
        raise HTTPException(status_code=400, detail="Name must not contain digits")
    # No abusive acronyms (all-caps words longer than 1 char that aren't names)
    for w in words:
        if len(w) > 1 and w == w.upper() and not w.isalpha():
            raise HTTPException(status_code=400, detail=f"Suspicious acronym in name: {w}")

    # ── Validate category ──
    valid_categories = {"politics", "culture", "sport", "business", "influencer", "other"}
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {sorted(valid_categories)}")

    # ── Check if already in DB ──
    name_slug = slugify(name)
    existing = await db.persons.find_one({"slug": name_slug})
    if existing:
        return {"success": False, "error": "already_exists", "person_id": str(existing["_id"])}

    # ── Check blocklist (anti-ghost: name_normalized primary key + legacy slug) ──
    if await is_person_blocklisted(name_normalized=normalize_person_name(name), slug=name_slug):
        return {"success": False, "error": "blocked"}

    # ── Wikipedia / Wikidata guard-fous ──
    import httpx as _httpx
    from candidate_detection import check_is_human_alive, check_multi_lang_pages, compute_celebrity_confidence, get_wikipedia_pageviews

    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            is_human, is_deceased, wikidata_id, description = await check_is_human_alive(name, client)

            if not is_human:
                return {"success": False, "error": "wikipedia_not_found"}

            if is_deceased:
                return {"success": False, "error": "deceased"}

            # Anti-ghost: re-check once the wikidata_id is known (a renamed
            # celebrity keeps the same QID even if the typed name differs).
            if wikidata_id and await is_person_blocklisted(wikidata_id=wikidata_id):
                return {"success": False, "error": "blocked"}

            langs = await check_multi_lang_pages(name, client)

            # Correction B: Confidence scoring
            pageviews_fr = await get_wikipedia_pageviews(name, "fr", client)
            pageviews_en = await get_wikipedia_pageviews(name, "en", client)
            confidence_score = compute_celebrity_confidence(
                is_human=is_human, is_deceased=is_deceased, wikidata_id=wikidata_id,
                langs=langs, pageviews_fr=pageviews_fr, pageviews_en=pageviews_en,
            )
            if confidence_score < 65:
                return {"success": False, "error": "low_confidence",
                        "message": "Cette personnalité n'a pas assez de visibilité pour le moment.",
                        "confidence_score": confidence_score}

    except Exception as e:
        logger.error(f"[propose-celebrity] Wikipedia check failed for '{name}': {e}")
        return {"success": False, "error": "wikipedia_check_failed", "detail": str(e)}

    # ── Get canonical name from Wikipedia ──
    canonical_name = name
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            title = name.replace(" ", "_")
            resp = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                headers={"User-Agent": "Popularoo/1.0 (contact@popularoo.com)"},
                follow_redirects=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                canonical_name = data.get("title", name)
    except Exception:
        pass

    final_slug = slugify(canonical_name)
    # Double-check with canonical slug
    existing = await db.persons.find_one({"slug": final_slug})
    if existing:
        return {"success": False, "error": "already_exists", "person_id": str(existing["_id"])}

    # ── Compute Wikipedia external score ──
    ext_score = 0.0
    wiki_brut = 0
    wiki_norm = 0.0
    try:
        from external_scores import compute_external_score_for_person as _compute_ext
        max_doc = await db.persons.find_one(
            {"wiki_score_brut": {"$exists": True}},
            sort=[("wiki_score_brut", -1)]
        )
        max_wiki_in_db = max_doc.get("wiki_score_brut", 1.0) if max_doc else None
        ext_result = await _compute_ext(canonical_name, max_wiki_in_db=max_wiki_in_db)
        ext_score = ext_result.get("popularity_external_score", 0)
        wiki_brut = ext_result.get("wiki_score_brut", 0)
        wiki_norm = ext_result.get("wiki_score_norm", 0)
    except Exception as e:
        logger.warning(f"[propose-celebrity] External score failed for '{canonical_name}': {e}")

    # ── Compute popularoo_index ──
    from popularoo_index import get_alpha
    alpha = await get_alpha(db)
    pi = round(alpha * ext_score, 2)  # 0 votes → index = alpha * ext

    now = now_utc()
    person_doc = {
        "name": canonical_name,
        "slug": final_slug,
        "category": category,  # Admin override
        "approved": True,
        "created_at": now,
        "updated_at": now,
        "score": pi,
        "likes": 0,
        "dislikes": 0,
        "total_votes": 0,
        "source": "admin_manual",
        "visible_in_rankings": True,  # Immediate visibility
        "wiki_description": description or "",
        "wikidata_id": wikidata_id,
        "wiki_langs": langs,
        "popularity_external_score": ext_score,
        "wiki_score_brut": wiki_brut,
        "wiki_score_norm": wiki_norm,
        "last_external_update": now,
        "popularoo_index": pi,
    }

    result = await db.persons.insert_one(person_doc)
    person_id = str(result.inserted_id)

    # Initial tick
    await db.person_ticks.insert_one({
        "person_id": result.inserted_id,
        "score": pi,
        "total_votes": 0,
        "created_at": now,
    })

    await _log_admin_action("propose_celebrity", canonical_name, {
        "category": category,
        "popularoo_index": pi,
        "ext_score": ext_score,
    })

    logger.info(f"✅ [Admin] Proposed celebrity '{canonical_name}' cat={category} PI={pi}")

    return {
        "success": True,
        "person_id": person_id,
        "name": canonical_name,
        "category": category,
        "popularity_external_score": ext_score,
        "popularoo_index": pi,
        "wikipedia_langs": langs,
    }


# ── Family 2: User self-management of outsider profile ──

@api_router.get("/me/my-outsider-profile")
async def get_my_outsider_profile(device_id: str = Query(...)):
    """
    Returns the outsider profile owned by this device_id.
    Looks up active_boosts by user_id == device_id, then fetches the person.
    """
    if not device_id or len(device_id) < 5:
        raise HTTPException(status_code=400, detail="Invalid device_id")

    # Find the most recent active boost for this device
    now = now_utc()
    boost = await db.active_boosts.find_one(
        {"user_id": device_id, "end_time": {"$gt": now}},
        sort=[("start_time", -1)]
    )

    if not boost:
        # Maybe expired but still has a person
        boost = await db.active_boosts.find_one(
            {"user_id": device_id},
            sort=[("start_time", -1)]
        )

    if not boost:
        return {"found": False, "message": "No outsider profile found for this device"}

    person = await db.persons.find_one({"_id": boost["person_id"]})
    if not person:
        return {"found": False, "message": "Outsider profile not found in database"}

    is_active = boost.get("end_time", now) > now
    hours_remaining = max(0, (boost["end_time"] - now).total_seconds() / 3600) if is_active else 0

    return {
        "found": True,
        "person_id": str(person["_id"]),
        "name": person.get("name", ""),
        "slug": person.get("slug", ""),
        "category": person.get("category", "other"),
        "source": person.get("source", ""),
        "score": person.get("score", 0),
        "likes": person.get("likes", 0),
        "dislikes": person.get("dislikes", 0),
        "superlikes": person.get("superlikes", 0),
        "total_votes": person.get("total_votes", 0),
        "social_links": person.get("social_links", {}),
        "email": person.get("email", ""),
        "boost_active": is_active,
        "boost_tier": boost.get("tier", ""),
        "hours_remaining": round(hours_remaining, 1),
        "boost_end_time": boost["end_time"].isoformat() if is_active else None,
    }


@api_router.delete("/me/my-outsider-profile")
async def delete_my_outsider_profile(device_id: str = Query(...)):
    """
    User self-deletion of their outsider profile.
    Deletes the person from DB, expires all active boosts, and adds slug to blocklist
    to prevent re-creation via search.
    """
    if not device_id or len(device_id) < 5:
        raise HTTPException(status_code=400, detail="Invalid device_id")

    # Find any boost owned by this device
    boost = await db.active_boosts.find_one(
        {"user_id": device_id},
        sort=[("start_time", -1)]
    )
    if not boost:
        raise HTTPException(status_code=404, detail="No outsider profile found for this device")

    person_id = boost["person_id"]
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        raise HTTPException(status_code=404, detail="Outsider profile not found")

    # Only allow deletion of self_boosted profiles
    if person.get("source") != "self_boosted":
        raise HTTPException(status_code=403, detail="Can only delete outsider (self_boosted) profiles")

    name = person.get("name", "")
    name_slug = person.get("slug", slugify(name))
    now = now_utc()

    # 1. Delete the person document
    await db.persons.delete_one({"_id": person_id})

    # 2. Expire all active boosts for this person
    await db.active_boosts.update_many(
        {"person_id": person_id, "end_time": {"$gt": now}},
        {"$set": {"end_time": now, "status": "user_deleted", "updated_at": now}}
    )

    # 3. Add slug to blocklist to prevent re-creation
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$addToSet": {"seed_blocklist": name_slug}},
        upsert=True,
    )

    # 4. Clean up related data
    await db.vote_events.delete_many({"person_id": person_id})
    await db.person_ticks.delete_many({"person_id": person_id})

    logger.info(f"🗑️ [User Self-Delete] Outsider '{name}' deleted by device {device_id[:8]}...")

    return {
        "success": True,
        "deleted_name": name,
        "deleted_slug": name_slug,
        "message": f"Your outsider profile '{name}' has been permanently deleted."
    }


# ── Family 3: POST /api/report-outsider — User reporting with anti-spam ──

class ReportOutsiderRequest(BaseModel):
    outsider_person_id: str
    reason: str  # e.g. "spam", "inappropriate", "fake", "other"
    comment: str = ""  # Optional free-text

@api_router.post("/report-outsider")
async def report_outsider(request: Request, body: ReportOutsiderRequest):
    """
    Report an outsider profile. Anti-spam: 1 report per device per profile per 24h.
    """
    device_id = request.headers.get("X-Device-ID", "")
    if not device_id or len(device_id) < 5:
        raise HTTPException(status_code=400, detail="X-Device-ID header required")

    # Validate reason
    valid_reasons = {"spam", "inappropriate", "fake", "offensive", "other"}
    if body.reason not in valid_reasons:
        raise HTTPException(status_code=400, detail=f"Invalid reason. Must be one of: {sorted(valid_reasons)}")

    # Validate person exists and is an outsider
    try:
        person_oid = ObjectId(body.outsider_person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid outsider_person_id")

    person = await db.persons.find_one({"_id": person_oid})
    if not person:
        raise HTTPException(status_code=404, detail="Outsider profile not found")
    if person.get("source") != "self_boosted":
        raise HTTPException(status_code=400, detail="Can only report outsider (self_boosted) profiles")

    # Anti-spam: 1 report per device per profile per 24h
    now = now_utc()
    cutoff_24h = now - timedelta(hours=24)
    existing_report = await db.outsider_reports.find_one({
        "outsider_person_id": body.outsider_person_id,
        "device_id": device_id,
        "created_at": {"$gte": cutoff_24h},
    })
    if existing_report:
        raise HTTPException(
            status_code=429,
            detail="You have already reported this profile in the last 24 hours"
        )

    # Create report
    report_doc = {
        "outsider_person_id": body.outsider_person_id,
        "outsider_name": person.get("name", ""),
        "reason": body.reason,
        "comment": body.comment[:500] if body.comment else "",  # Limit comment length
        "device_id": device_id,
        "status": "pending",  # pending, ignored, warned, deleted
        "created_at": now,
    }

    result = await db.outsider_reports.insert_one(report_doc)

    # Count total pending reports for this outsider
    total_reports = await db.outsider_reports.count_documents({
        "outsider_person_id": body.outsider_person_id,
        "status": "pending",
    })

    logger.info(f"🚩 [Report] Outsider '{person.get('name')}' reported by {device_id[:8]}... reason={body.reason} (total pending: {total_reports})")

    return {
        "success": True,
        "report_id": str(result.inserted_id),
        "total_pending_reports": total_reports,
        "message": "Report submitted. Our team will review it shortly."
    }


# ── Family 4: Admin Outsider Moderation ──

@api_router.get("/admin/outsider-reports")
async def admin_list_outsider_reports(request: Request, status: str = Query(default="pending")):
    """
    List outsider reports, grouped by outsider, with report count.
    """
    _require_admin_auth(request)

    valid_statuses = {"pending", "ignored", "warned", "deleted", "all"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status filter. Use: {sorted(valid_statuses)}")

    match_stage = {}
    if status != "all":
        match_stage["status"] = status

    # Aggregate reports grouped by outsider
    pipeline = [
        {"$match": match_stage},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$outsider_person_id",
            "outsider_name": {"$first": "$outsider_name"},
            "report_count": {"$sum": 1},
            "reasons": {"$push": "$reason"},
            "latest_report": {"$first": "$$ROOT"},
            "all_reports": {"$push": {
                "report_id": {"$toString": "$_id"},
                "reason": "$reason",
                "comment": "$comment",
                "device_id": "$device_id",
                "status": "$status",
                "created_at": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$created_at"}},
            }},
        }},
        {"$sort": {"report_count": -1}},
    ]

    results = await db.outsider_reports.aggregate(pipeline).to_list(200)

    output = []
    for r in results:
        # Get person details
        person = None
        try:
            person = await db.persons.find_one({"_id": ObjectId(r["_id"])})
        except Exception:
            pass

        output.append({
            "outsider_person_id": r["_id"],
            "outsider_name": r.get("outsider_name", ""),
            "report_count": r["report_count"],
            "reasons_summary": dict(Counter(r["reasons"])),
            "person_exists": person is not None,
            "person_source": person.get("source", "") if person else None,
            "person_email": person.get("email", "") if person else None,
            "reports": r["all_reports"],
        })

    return {"total_outsiders_reported": len(output), "reports": output}


@api_router.post("/admin/outsider-reports/{report_id}/ignore")
async def admin_ignore_outsider_report(report_id: str, request: Request):
    """Mark a report (or all pending reports for the outsider) as ignored."""
    _require_admin_auth(request)

    try:
        report_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report_id")

    report = await db.outsider_reports.find_one({"_id": report_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    outsider_person_id = report["outsider_person_id"]

    # Mark ALL pending reports for this outsider as ignored
    result = await db.outsider_reports.update_many(
        {"outsider_person_id": outsider_person_id, "status": "pending"},
        {"$set": {"status": "ignored", "resolved_at": now_utc()}}
    )

    await _log_admin_action("ignore_outsider_report", report.get("outsider_name", ""), {
        "report_id": report_id,
        "reports_ignored": result.modified_count,
    })

    return {
        "success": True,
        "reports_ignored": result.modified_count,
        "outsider_name": report.get("outsider_name", ""),
    }


@api_router.post("/admin/outsider-reports/{report_id}/warn")
async def admin_warn_outsider(report_id: str, request: Request):
    """
    Send a warning email to the outsider owner. Marks reports as 'warned'.
    The email is bilingual (FR + EN) as specified.
    """
    _require_admin_auth(request)

    try:
        report_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report_id")

    report = await db.outsider_reports.find_one({"_id": report_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    outsider_person_id = report["outsider_person_id"]

    # Find the person
    try:
        person = await db.persons.find_one({"_id": ObjectId(outsider_person_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid outsider person ID in report")

    if not person:
        raise HTTPException(status_code=404, detail="Outsider profile no longer exists")

    # Find the owner's email via the boost
    boost = await db.active_boosts.find_one(
        {"person_id": person["_id"]},
        sort=[("start_time", -1)]
    )

    owner_email = person.get("email", "") or (boost.get("email", "") if boost else "")
    if not owner_email:
        raise HTTPException(
            status_code=422,
            detail=f"No email found for outsider '{person.get('name', '')}'. Cannot send warning."
        )

    # ── Build warning email (bilingual FR + EN) ──
    outsider_name = person.get("name", "")
    subject = "Popularoo — Signalement de votre profil Outsider"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 560px; margin: 0 auto; padding: 32px 24px;
                background: #0F2F22; color: #EAEAEA; border-radius: 12px;">
        <div style="text-align:center;margin-bottom:24px;">
            <span style="font-size:28px;font-weight:800;color:#2ECC71;">Popularoo</span>
        </div>
        <div style="line-height:1.6;font-size:15px;">
            <p>Bonjour,</p>
            <p>Nous avons reçu plusieurs signalements concernant votre profil Outsider <b>{outsider_name}</b> sur Popularoo. Après examen, nous souhaitons attirer votre attention sur le fait que certains éléments de votre profil pourraient ne pas respecter pleinement nos conditions d'utilisation.</p>
            <p>Nous vous invitons à vérifier votre profil et à le modifier si nécessaire. Si votre profil ne respecte pas nos règles communautaires, nous pourrons être amenés à le supprimer définitivement.</p>
            <p>Vous pouvez consulter nos conditions d'utilisation sur <a href="https://popularoo.com/cgu" style="color:#2ECC71;">popularoo.com/cgu</a>.</p>
            <p>Cordialement,<br>L'équipe Popularoo</p>

            <hr style="border:none;border-top:1px solid #2E6148;margin:24px 0;">

            <p>Hello,</p>
            <p>We have received multiple reports regarding your Outsider profile <b>{outsider_name}</b> on Popularoo. After review, we want to draw your attention to the fact that some elements of your profile may not fully comply with our terms of use.</p>
            <p>We invite you to verify your profile and modify it if necessary. If your profile does not respect our community guidelines, we may have to delete it permanently.</p>
            <p>You can review our terms of use at <a href="https://popularoo.com/cgu" style="color:#2ECC71;">popularoo.com/cgu</a>.</p>
            <p>Best regards,<br>The Popularoo Team</p>
        </div>
        <div style="margin-top:32px;padding-top:16px;border-top:1px solid #2E6148;
                    text-align:center;font-size:12px;color:#C9D8D2;">
            © {datetime.utcnow().year} Popularoo App
        </div>
    </div>
    """

    # Send email
    try:
        await email_service.send_email(owner_email, subject, html_body)
    except Exception as e:
        logger.error(f"[warn-outsider] Email send failed for {owner_email}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send warning email: {str(e)}")

    # Mark all pending reports for this outsider as 'warned'
    result = await db.outsider_reports.update_many(
        {"outsider_person_id": outsider_person_id, "status": "pending"},
        {"$set": {"status": "warned", "resolved_at": now_utc(), "warned_email": owner_email}}
    )

    await _log_admin_action("warn_outsider", outsider_name, {
        "report_id": report_id,
        "email_sent_to": owner_email,
        "reports_warned": result.modified_count,
    })

    logger.info(f"⚠️ [Admin] Warning sent to '{outsider_name}' at {owner_email}")

    return {
        "success": True,
        "outsider_name": outsider_name,
        "email_sent_to": owner_email,
        "reports_warned": result.modified_count,
    }


@api_router.post("/admin/outsider-reports/{report_id}/delete")
async def admin_delete_reported_outsider(report_id: str, request: Request):
    """
    Delete the reported outsider, send deletion email, add to blocklist.
    """
    _require_admin_auth(request)

    try:
        report_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report_id")

    report = await db.outsider_reports.find_one({"_id": report_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    outsider_person_id = report["outsider_person_id"]

    # Find the person
    try:
        person = await db.persons.find_one({"_id": ObjectId(outsider_person_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid outsider person ID in report")

    if not person:
        # Already deleted — just mark reports
        await db.outsider_reports.update_many(
            {"outsider_person_id": outsider_person_id, "status": {"$in": ["pending", "warned"]}},
            {"$set": {"status": "deleted", "resolved_at": now_utc()}}
        )
        return {"success": True, "message": "Outsider already deleted. Reports marked as resolved."}

    outsider_name = person.get("name", "")
    name_slug = person.get("slug", slugify(outsider_name))
    person_oid = person["_id"]
    now = now_utc()

    # Find the owner's email
    boost = await db.active_boosts.find_one(
        {"person_id": person_oid},
        sort=[("start_time", -1)]
    )
    owner_email = person.get("email", "") or (boost.get("email", "") if boost else "")

    # ── 1. Delete the person ──
    await db.persons.delete_one({"_id": person_oid})

    # ── 2. Expire all active boosts ──
    await db.active_boosts.update_many(
        {"person_id": person_oid, "end_time": {"$gt": now}},
        {"$set": {"end_time": now, "status": "admin_deleted", "updated_at": now}}
    )

    # ── 3. Add slug to blocklist ──
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$addToSet": {"seed_blocklist": name_slug}},
        upsert=True,
    )

    # ── 4. Clean up related data ──
    await db.vote_events.delete_many({"person_id": person_oid})
    await db.person_ticks.delete_many({"person_id": person_oid})

    # ── 5. Add device to blocklist for outsider creation ──
    if boost and boost.get("user_id"):
        await db.outsider_blocklist.update_one(
            {"device_id": boost["user_id"]},
            {"$set": {
                "device_id": boost["user_id"],
                "reason": f"Outsider '{outsider_name}' deleted after reports",
                "blocked_at": now,
                "outsider_name": outsider_name,
            }},
            upsert=True,
        )

    # ── 6. Send deletion email ──
    email_sent = False
    if owner_email:
        subject = "Popularoo — Suppression de votre profil Outsider"
        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 560px; margin: 0 auto; padding: 32px 24px;
                    background: #0F2F22; color: #EAEAEA; border-radius: 12px;">
            <div style="text-align:center;margin-bottom:24px;">
                <span style="font-size:28px;font-weight:800;color:#2ECC71;">Popularoo</span>
            </div>
            <div style="line-height:1.6;font-size:15px;">
                <p>Bonjour,</p>
                <p>Suite à plusieurs signalements et à l'examen de votre profil Outsider <b>{outsider_name}</b>, nous avons procédé à sa suppression définitive de Popularoo. Cette décision a été prise au regard de nos conditions d'utilisation et règles communautaires.</p>
                <p>Aucun remboursement de votre Booster n'est possible, conformément aux conditions générales que vous avez acceptées lors de l'achat.</p>
                <p>Si vous estimez que cette décision est injustifiée, vous pouvez nous contacter à <a href="mailto:popularoo@popularoo.com" style="color:#2ECC71;">popularoo@popularoo.com</a> en précisant le nom du profil concerné. Nous étudierons votre demande.</p>
                <p>Cordialement,<br>L'équipe Popularoo</p>

                <hr style="border:none;border-top:1px solid #2E6148;margin:24px 0;">

                <p>Hello,</p>
                <p>Following multiple reports and a review of your Outsider profile <b>{outsider_name}</b>, we have permanently deleted it from Popularoo. This decision was made in accordance with our terms of use and community guidelines.</p>
                <p>No refund of your Booster is possible, in accordance with the general terms you accepted at the time of purchase.</p>
                <p>If you believe this decision is unjustified, you can contact us at <a href="mailto:popularoo@popularoo.com" style="color:#2ECC71;">popularoo@popularoo.com</a> and provide the name of the affected profile. We will review your request.</p>
                <p>Best regards,<br>The Popularoo Team</p>
            </div>
            <div style="margin-top:32px;padding-top:16px;border-top:1px solid #2E6148;
                        text-align:center;font-size:12px;color:#C9D8D2;">
                © {datetime.utcnow().year} Popularoo App
            </div>
        </div>
        """
        try:
            await email_service.send_email(owner_email, subject, html_body)
            email_sent = True
        except Exception as e:
            logger.error(f"[delete-outsider] Email send failed for {owner_email}: {e}")

    # ── 7. Mark ALL reports for this outsider as 'deleted' ──
    reports_result = await db.outsider_reports.update_many(
        {"outsider_person_id": outsider_person_id, "status": {"$in": ["pending", "warned"]}},
        {"$set": {"status": "deleted", "resolved_at": now}}
    )

    await _log_admin_action("delete_reported_outsider", outsider_name, {
        "report_id": report_id,
        "email_sent": email_sent,
        "email_to": owner_email or "N/A",
        "blocked_slug": name_slug,
        "reports_resolved": reports_result.modified_count,
    })

    logger.info(f"🚫 [Admin] Deleted reported outsider '{outsider_name}', blocked slug='{name_slug}', email_sent={email_sent}")

    return {
        "success": True,
        "deleted_name": outsider_name,
        "blocked_slug": name_slug,
        "email_sent": email_sent,
        "email_to": owner_email or None,
        "reports_resolved": reports_result.modified_count,
    }


# ==================== VAGUE 1 — Sujets B+C+D: Virtual Vote Config ====================

# ── Cas 1 celebrities admin CRUD ──

@api_router.get("/admin/cas1-celebrities")
async def admin_get_cas1(request: Request):
    """Get the Cas 1 mega-star celebrity slug list from app_settings."""
    _require_admin_auth(request)
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    return {"cas1_celebrities": settings.get("cas1_celebrities", [])}


@api_router.post("/admin/cas1-celebrities")
async def admin_update_cas1(request: Request):
    """
    Add/remove slugs from the Cas 1 mega-star list.
    Body: { "add": ["slug1", ...], "remove": ["slug2", ...] }
    """
    _require_admin_auth(request)
    body = await request.json()
    add_slugs = body.get("add", [])
    remove_slugs = body.get("remove", [])

    if not add_slugs and not remove_slugs:
        raise HTTPException(status_code=400, detail="Provide 'add' and/or 'remove' arrays")

    ops = {}
    if add_slugs:
        ops["$addToSet"] = {"cas1_celebrities": {"$each": [s.strip().lower() for s in add_slugs if s.strip()]}}
    if remove_slugs:
        ops["$pull"] = {"cas1_celebrities": {"$in": [s.strip().lower() for s in remove_slugs if s.strip()]}}

    # MongoDB doesn't allow $addToSet and $pull in same update, so split
    if add_slugs:
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$addToSet": {"cas1_celebrities": {"$each": [s.strip().lower() for s in add_slugs if s.strip()]}}},
            upsert=True,
        )
    if remove_slugs:
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$pull": {"cas1_celebrities": {"$in": [s.strip().lower() for s in remove_slugs if s.strip()]}}},
        )

    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    final_list = settings.get("cas1_celebrities", [])

    await _log_admin_action("update_cas1_celebrities", "cas1_list", {
        "added": add_slugs, "removed": remove_slugs, "final_count": len(final_list),
    })

    return {"success": True, "cas1_celebrities": final_list, "count": len(final_list)}


# ── Admin: Recalculate dominant_language for all persons ──

COUNTRY_TO_LANG = {
    "FR": "fr", "BE": "fr", "CH": "fr", "CA": "fr", "MA": "fr", "SN": "fr",
    "TN": "fr", "DZ": "fr", "CI": "fr", "CM": "fr", "CD": "fr", "MG": "fr",
    "US": "en", "GB": "en", "UK": "en", "AU": "en", "NZ": "en", "IE": "en",
    "ZA": "en", "NG": "en", "KE": "en", "GH": "en", "IN": "en", "PH": "en",
    "ES": "es", "MX": "es", "AR": "es", "CO": "es", "CL": "es", "PE": "es",
    "VE": "es", "EC": "es", "CU": "es", "BO": "es", "GT": "es", "HN": "es",
    "DE": "de", "AT": "de", "LI": "de",
    "IT": "it", "SM": "it",
    "PT": "pt", "BR": "pt", "AO": "pt", "MZ": "pt",
}


def compute_dominant_language_from_pageviews(per_lang_data: list, primary_country: str = "") -> str:
    """
    Given per_lang data from Wikipedia pageviews, return the dominant language.
    Priority: primary_country mapping > highest non-English pageviews (if >15% of total) > English.
    This ensures Cristiano Ronaldo → "pt" (not "en") and Emmanuel Macron → "fr".
    """
    # 1. If we have primary_country, use that as the strong signal
    if primary_country:
        country_lang = COUNTRY_TO_LANG.get(primary_country.upper().strip(), "")
        if country_lang:
            return country_lang

    if not per_lang_data:
        return "en"

    # 2. Calculate total views excluding English
    total_views = sum(r.get("avg_daily_views", 0) for r in per_lang_data)
    if total_views <= 0:
        return "en"

    # Sort by views descending
    sorted_langs = sorted(per_lang_data, key=lambda x: x.get("avg_daily_views", 0), reverse=True)

    # 3. If the top language is not English, use it
    top = sorted_langs[0]
    top_lang = top.get("lang", "en")
    if top_lang != "en" and top_lang in {"fr", "de", "es", "it", "pt"}:
        return top_lang

    # 4. If top is English, check if any non-English lang has >15% share
    # This catches cases like Macron where French is significant but smaller than English
    for item in sorted_langs:
        lang = item.get("lang", "")
        if lang == "en" or lang not in {"fr", "de", "es", "it", "pt"}:
            continue
        share = item.get("avg_daily_views", 0) / total_views
        if share >= 0.15:
            return lang

    return "en"


def compute_dominant_language_from_country(primary_country: str) -> str:
    """Fallback: derive dominant language from primary_country code."""
    if not primary_country:
        return "en"
    return COUNTRY_TO_LANG.get(primary_country.upper().strip(), "en")


@api_router.post("/admin/recalculate-dominant-languages")
async def admin_recalculate_dominant_languages(request: Request):
    """
    Batch recalculate dominant_language for all persons.
    Strategy (optimized):
    1. Use primary_country mapping first (instant, no API call)
    2. Only fetch Wikipedia pageviews for profiles WITHOUT primary_country
    """
    _require_admin_auth(request)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    force_wiki = body.get("force_wikipedia", False)  # If true, fetch Wikipedia for ALL

    cursor = db.persons.find({}, {"name": 1, "slug": 1, "source": 1, "primary_country": 1,
                                   "dominant_language": 1})
    persons = await cursor.to_list(length=1000)

    updated = 0
    results = []
    wiki_needed = []

    # Pass 1: Set dominant_language from primary_country (instant)
    for p in persons:
        name = p.get("name", "")
        source = p.get("source", "")
        pid = p["_id"]
        country = p.get("primary_country", "")

        if country and not force_wiki:
            lang = compute_dominant_language_from_country(country)
            await db.persons.update_one({"_id": pid}, {"$set": {"dominant_language": lang}})
            results.append({"name": name, "dominant_language": lang, "method": "primary_country"})
            updated += 1
        elif source == "self_boosted":
            # Outsiders: use country if available, else "en"
            lang = compute_dominant_language_from_country(country) if country else "en"
            await db.persons.update_one({"_id": pid}, {"$set": {"dominant_language": lang}})
            results.append({"name": name, "dominant_language": lang, "method": "outsider_fallback"})
            updated += 1
        else:
            wiki_needed.append(p)

    # Pass 2: For profiles without primary_country, fetch Wikipedia (slower)
    from external_scores import fetch_wikipedia_pageviews
    import asyncio as _asyncio
    errors = []

    for p in wiki_needed:
        name = p.get("name", "")
        pid = p["_id"]
        try:
            wiki_data = await fetch_wikipedia_pageviews(name)
            per_lang = wiki_data.get("per_lang", [])
            lang = compute_dominant_language_from_pageviews(per_lang, p.get("primary_country", ""))
            active_langs = [r["lang"] for r in per_lang if r.get("avg_daily_views", 0) > 0]
            await db.persons.update_one({"_id": pid}, {"$set": {"dominant_language": lang, "wiki_langs": active_langs}})
            results.append({"name": name, "dominant_language": lang, "method": "wikipedia_pageviews"})
            updated += 1
            await _asyncio.sleep(0.3)
        except Exception as e:
            await db.persons.update_one({"_id": pid}, {"$set": {"dominant_language": "en"}})
            errors.append(f"{name}: {e}")
            updated += 1

    await _log_admin_action("recalculate_dominant_languages", "batch", {
        "total": len(persons), "updated": updated, "errors": len(errors),
        "wiki_fetched": len(wiki_needed),
    })

    return {
        "success": True,
        "total_persons": len(persons),
        "updated": updated,
        "via_country": len(persons) - len(wiki_needed),
        "via_wikipedia": len(wiki_needed),
        "errors_count": len(errors),
        "errors": errors[:10],
        "sample_results": results[:20],
    }


# ── Admin: Recalculate Popularoo Index for ALL profiles (C1 migration) ──

@api_router.post("/admin/recalculate-all-pi")
async def admin_recalculate_all_pi(request: Request):
    """
    Correction 1 (Vague 2): Recalculate popularoo_index for ALL profiles using the new 3-branch formula.
    - self_boosted → 3 + (net_votes/10)*1.0, cap 25
    - user_search / user_search_confirmed → meritocratic base + progression
    - seed / unknown → α-blended (unchanged)
    Run once after deployment to apply new scoring system.
    """
    _require_admin_auth(request)

    from popularoo_index import recalculate_index_for_person, DEFAULT_CONFIG

    cursor = db.persons.find({}, {"name": 1, "slug": 1, "source": 1, "likes": 1, "dislikes": 1,
                                   "total_votes": 1, "popularity_external_score": 1, "popularoo_index": 1,
                                   "category": 1})
    persons = await cursor.to_list(length=10000)
    config = DEFAULT_CONFIG

    results = {"self_boosted": [], "user_search": [], "seed": [], "total": len(persons)}
    errors = []

    for p in persons:
        try:
            old_pi = p.get("popularoo_index", 0) or 0
            new_pi = await recalculate_index_for_person(db, p, config)
            source = p.get("source", "unknown")
            bucket = "self_boosted" if source == "self_boosted" else "user_search" if source in ("user_search", "user_search_confirmed") else "seed"
            if abs(new_pi - old_pi) > 0.1:  # Only log significant changes
                results[bucket].append({
                    "name": p.get("name"),
                    "source": source,
                    "old_pi": round(old_pi, 1),
                    "new_pi": round(new_pi, 1),
                    "delta": round(new_pi - old_pi, 1),
                })
        except Exception as e:
            errors.append({"name": p.get("name", "?"), "error": str(e)})

    return {
        "success": True,
        "total_persons": len(persons),
        "outsiders_changed": len(results["self_boosted"]),
        "user_search_changed": len(results["user_search"]),
        "seed_changed": len(results["seed"]),
        "errors": len(errors),
        "sample_outsiders": results["self_boosted"][:10],
        "sample_user_search": results["user_search"][:10],
        "sample_seed": results["seed"][:10],
        "errors_detail": errors[:5],
    }


# ── Virtual vote config endpoint ──

@api_router.get("/virtual-vote-config/{person_id}")
async def get_virtual_vote_config(person_id: str):
    """
    Returns the virtual vote display configuration for a personality.
    Determines tier (cas1/cas2/cas3) and returns interval + geo coefficient.
    """
    try:
        person_oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id")

    person = await db.persons.find_one({"_id": person_oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    slug = person.get("slug", "")
    ext_score = person.get("popularity_external_score", 0) or 0
    source = person.get("source", "")
    dominant_lang = person.get("dominant_language", "en")

    # Load cas1 list
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    cas1_slugs = set(settings.get("cas1_celebrities", []))

    # Determine tier
    if slug in cas1_slugs:
        tier = "cas1"
        interval_min = 2500
        interval_max = 4500
        geo = {"local": 0.0, "international": 1.0}
        initial_feed = 8
    elif ext_score >= 50 and source != "self_boosted":
        tier = "cas2"
        interval_min = 300000    # 5 minutes
        interval_max = 900000    # 15 minutes
        geo = {"local": 0.8, "international": 0.2}
        initial_feed = 5
    else:
        # Cas 3: newcomers, low score, outsiders
        tier = "cas3"
        interval_min = 7200000   # 2 hours
        interval_max = 43200000  # 12 hours
        geo = {"local": 1.0, "international": 0.0}
        initial_feed = 3

    # ── C2: Grace period 24h for user-created profiles ──
    grace_active = False
    grace_ends = None
    if source in ("user_search", "user_search_confirmed"):
        created_at = person.get("created_at")
        if created_at:
            from datetime import timedelta
            grace_ends = created_at + timedelta(hours=24)
            if now_utc() < grace_ends:
                grace_active = True
            else:
                grace_ends = None  # Grace period over, don't expose end date

    return {
        "person_id": person_id,
        "tier": tier,
        "interval_min_ms": interval_min,
        "interval_max_ms": interval_max,
        "dominant_language": dominant_lang,
        "geo_coefficient": geo,
        "initial_feed_count": initial_feed,
        "grace_period_active": grace_active,
        "grace_period_ends_at": grace_ends.isoformat() if grace_ends else None,
    }


# ==================== VAGUE 2 — Sujet A: Contributor ====================


@api_router.get("/me/is-contributor")
async def is_contributor(
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """
    Check if a device_id has contributed (created) at least one celebrity profile.
    device_id is read from X-Device-ID header (convention app).
    """
    device_id = (x_device_id or "").strip()
    if not device_id or len(device_id) < 5:
        raise HTTPException(status_code=400, detail="X-Device-ID header required")

    doc = await db.user_settings.find_one({"device_id": device_id})
    contributed = doc.get("contributed_person_ids", []) if doc else []

    return {
        "is_contributor": len(contributed) > 0,
        "contributed_count": len(contributed),
        "contributed_person_ids": contributed,
    }


# Include API router AFTER all endpoints are defined on it
app.include_router(api_router)

# Serve static screenshots for validation
app.mount("/api/screenshots", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static", "screenshots"), html=True), name="screenshots")
app.mount("/api/screenshots-1l", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static", "screenshots_1L"), html=True), name="screenshots_1l")
app.mount("/api/assets", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static_assets")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
