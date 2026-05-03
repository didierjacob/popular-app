from fastapi import FastAPI, APIRouter, HTTPException, Header, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
import uuid
from datetime import datetime, timedelta
from bson import ObjectId
import re
from trends_service import trends_service
from scheduler import init_scheduler, start_scheduler, shutdown_scheduler
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
    
    logger.info("✅ Scheduler initialized and started")
    logger.info("📅 Daily Google Trends refresh scheduled at 3:00 AM UTC")
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
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    s = s.strip('-')
    return s


def now_utc() -> datetime:
    return datetime.utcnow()


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
import os as _os
DECAY_START_DATE_STR = _os.environ.get("DECAY_START_DATE", "2026-07-28")  # ~90 days from now
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

    score = round(raw_score / 25) * 25
    score = max(0, min(100, score))

    return raw_score, score, effective_likes, effective_dislikes, effective_total


# -------------------- Pydantic Models --------------------
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=now_utc)


class StatusCheckCreate(BaseModel):
    client_name: str


Category = Literal["politics", "culture", "business", "sport", "other"]


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
SEED_PEOPLE = [
    # Business (20)
    {"name": "Elon Musk", "category": "business"},
    {"name": "Tim Cook", "category": "business"},
    {"name": "Sundar Pichai", "category": "business"},
    {"name": "Mark Zuckerberg", "category": "business"},
    {"name": "Satya Nadella", "category": "business"},
    {"name": "Warren Buffett", "category": "business"},
    {"name": "Jeff Bezos", "category": "business"},
    {"name": "Sheryl Sandberg", "category": "business"},
    {"name": "Reed Hastings", "category": "business"},
    {"name": "Bill Gates", "category": "business"},
    {"name": "Larry Page", "category": "business"},
    {"name": "Sergey Brin", "category": "business"},
    {"name": "Jensen Huang", "category": "business"},
    {"name": "Sam Altman", "category": "business"},
    {"name": "Bob Iger", "category": "business"},
    {"name": "Jamie Dimon", "category": "business"},
    {"name": "Bernard Arnault", "category": "business"},
    {"name": "Larry Ellison", "category": "business"},
    {"name": "Michael Bloomberg", "category": "business"},
    {"name": "Jack Ma", "category": "business"},
    # Culture (30)
    {"name": "Oprah Winfrey", "category": "culture"},
    {"name": "Taylor Swift", "category": "culture"},
    {"name": "Beyoncé", "category": "culture"},
    {"name": "Greta Thunberg", "category": "culture"},
    {"name": "Malala Yousafzai", "category": "culture"},
    {"name": "Kanye West", "category": "culture"},
    {"name": "Rihanna", "category": "culture"},
    {"name": "Drake", "category": "culture"},
    {"name": "Ariana Grande", "category": "culture"},
    {"name": "Ed Sheeran", "category": "culture"},
    {"name": "Billie Eilish", "category": "culture"},
    {"name": "Bad Bunny", "category": "culture"},
    {"name": "BTS", "category": "culture"},
    {"name": "Dua Lipa", "category": "culture"},
    {"name": "The Weeknd", "category": "culture"},
    {"name": "Lady Gaga", "category": "culture"},
    {"name": "Justin Bieber", "category": "culture"},
    {"name": "Shakira", "category": "culture"},
    {"name": "Adele", "category": "culture"},
    {"name": "Bruno Mars", "category": "culture"},
    {"name": "Tom Hanks", "category": "culture"},
    {"name": "Leonardo DiCaprio", "category": "culture"},
    {"name": "Meryl Streep", "category": "culture"},
    {"name": "Denzel Washington", "category": "culture"},
    {"name": "Jennifer Lawrence", "category": "culture"},
    {"name": "Chris Hemsworth", "category": "culture"},
    {"name": "Dwayne Johnson", "category": "culture"},
    {"name": "Scarlett Johansson", "category": "culture"},
    {"name": "Robert Downey Jr.", "category": "culture"},
    {"name": "Zendaya", "category": "culture"},
    # Sport (25)
    {"name": "Lionel Messi", "category": "sport"},
    {"name": "Cristiano Ronaldo", "category": "sport"},
    {"name": "Serena Williams", "category": "sport"},
    {"name": "LeBron James", "category": "sport"},
    {"name": "Kylian Mbappé", "category": "sport"},
    {"name": "Lewis Hamilton", "category": "sport"},
    {"name": "Roger Federer", "category": "sport"},
    {"name": "Tom Brady", "category": "sport"},
    {"name": "Novak Djokovic", "category": "sport"},
    {"name": "Rafael Nadal", "category": "sport"},
    {"name": "Neymar Jr.", "category": "sport"},
    {"name": "Erling Haaland", "category": "sport"},
    {"name": "Stephen Curry", "category": "sport"},
    {"name": "Kevin Durant", "category": "sport"},
    {"name": "Usain Bolt", "category": "sport"},
    {"name": "Michael Phelps", "category": "sport"},
    {"name": "Simone Biles", "category": "sport"},
    {"name": "Tiger Woods", "category": "sport"},
    {"name": "Naomi Osaka", "category": "sport"},
    {"name": "Max Verstappen", "category": "sport"},
    {"name": "Patrick Mahomes", "category": "sport"},
    {"name": "Conor McGregor", "category": "sport"},
    {"name": "Mike Tyson", "category": "sport"},
    {"name": "Mohamed Salah", "category": "sport"},
    {"name": "Virat Kohli", "category": "sport"},
    # Politics (25)
    {"name": "Barack Obama", "category": "politics"},
    {"name": "Donald Trump", "category": "politics"},
    {"name": "Joe Biden", "category": "politics"},
    {"name": "Kamala Harris", "category": "politics"},
    {"name": "Emmanuel Macron", "category": "politics"},
    {"name": "Rishi Sunak", "category": "politics"},
    {"name": "Angela Merkel", "category": "politics"},
    {"name": "Xi Jinping", "category": "politics"},
    {"name": "Vladimir Putin", "category": "politics"},
    {"name": "Volodymyr Zelenskyy", "category": "politics"},
    {"name": "Ursula von der Leyen", "category": "politics"},
    {"name": "Pope Francis", "category": "politics"},
    {"name": "Justin Trudeau", "category": "politics"},
    {"name": "Narendra Modi", "category": "politics"},
    {"name": "Benjamin Netanyahu", "category": "politics"},
    {"name": "Olaf Scholz", "category": "politics"},
    {"name": "Giorgia Meloni", "category": "politics"},
    {"name": "Pedro Sánchez", "category": "politics"},
    {"name": "Lula da Silva", "category": "politics"},
    {"name": "Javier Milei", "category": "politics"},
    {"name": "King Charles III", "category": "politics"},
    {"name": "Queen Elizabeth II", "category": "politics"},
    {"name": "Prince William", "category": "politics"},
    {"name": "Michelle Obama", "category": "politics"},
    {"name": "Hillary Clinton", "category": "politics"},
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
        return
    docs = []
    now = now_utc()
    for p in SEED_PEOPLE:
        slug = slugify(p["name"])
        docs.append({
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
        })
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


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_people()
    await migrate_raw_scores()
    await migrate_seed_votes()
    # Initialize Bull Run module with db reference
    init_bull_run(db)


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


def person_to_out(doc: Dict[str, Any]) -> PersonOut:
    # Apply seed decay for displayed score
    _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(doc)

    # Strike level
    active_strikes = doc.get("active_strikes", 0)
    s_emoji, s_label = get_strike_level(active_strikes)

    return PersonOut(
        id=str(doc["_id"]),
        name=doc.get("name"),
        category=doc.get("category", "other"),
        approved=bool(doc.get("approved", True)),
        score=float(eff_score),
        likes=int(eff_likes),
        dislikes=int(eff_dislikes),
        superlikes=int(doc.get("superlikes", 0)),
        total_votes=int(eff_total),
        popularoo_index=float(doc.get("popularoo_index", 0.0)),
        active_strikes=active_strikes,
        strike_emoji=s_emoji if s_emoji else None,
        strike_label=s_label if s_label else None,
        last_updated=doc.get("updated_at"),
        source=doc.get("source", "seed"),
        country_tags=doc.get("country_tags"),
        is_international=doc.get("is_international", False),
        primary_country=doc.get("primary_country"),
        social_links=doc.get("social_links") or None,
        avatar_initials=doc.get("avatar_initials"),
        avatar_color=doc.get("avatar_color"),
    )


@api_router.get("/people", response_model=List[PersonOut])
async def list_people(
    query: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    category: Optional[str] = Query(default=None),
    include_outsiders: bool = Query(default=False),
    country: Optional[str] = Query(default=None, description="User country code for 50/50 feed filtering"),
):
    """
    List personalities with optional 50/50 local/international feed.
    If country is provided, returns ~50% local + ~50% international.
    """
    filter_q: Dict[str, Any] = {"approved": True}
    
    # Exclude "outsiders" (self_boosted) from main lists unless explicitly requested
    if not include_outsiders:
        filter_q["source"] = {"$ne": "self_boosted"}
    
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
            elif cat not in {"politics", "culture", "business", "sport", "other"}:
                raise HTTPException(status_code=400, detail="Invalid category")
            else:
                filter_q["category"] = cat

    # 50/50 local/international feed when country is specified
    if country and not query:
        user_country = country.upper().strip()
        local_limit = limit // 2
        intl_limit = limit - local_limit

        # Fetch local personalities (tagged with user's country)
        local_filter = {**filter_q, "country_tags": user_country}
        local_cursor = db.persons.find(local_filter).sort([("popularoo_index", -1)]).limit(local_limit)
        local_docs = await local_cursor.to_list(length=local_limit)

        # If not enough local, fill with more international
        remaining = limit - len(local_docs)
        
        # Fetch international personalities (excluding already-fetched locals)
        local_ids = [d["_id"] for d in local_docs]
        intl_filter = {**filter_q, "is_international": True, "_id": {"$nin": local_ids}}
        intl_cursor = db.persons.find(intl_filter).sort([("popularoo_index", -1)]).limit(remaining)
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

        return [person_to_out(d) for d in merged[:limit]]
    
    cursor = db.persons.find(filter_q).sort([("total_votes", -1), ("score", -1)]).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [person_to_out(d) for d in docs]


@api_router.post("/people", response_model=PersonOut)
async def add_person(body: PersonCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    
    # Normalize name to Title Case (e.g., "trump" -> "Trump", "elon musk" -> "Elon Musk")
    name = name.title()
    
    slug = slugify(name)
    existing = await db.persons.find_one({"slug": slug})
    if existing:
        # return existing person to avoid duplicates
        return person_to_out(existing)
    now = now_utc()
    doc = {
        "name": name,
        "slug": slug,
        "category": body.category or "other",
        "approved": True,  # basic moderation on later
        "created_at": now,
        "updated_at": now,
        "score": 50,  # Neutral starting score
        "likes": 0,
        "dislikes": 0,
        "total_votes": 0,
        "source": "user_added",  # Mark as user-added personality
    }
    res = await db.persons.insert_one(doc)
    await db.person_ticks.insert_one({"person_id": res.inserted_id, "score": 50, "created_at": now})
    doc["_id"] = res.inserted_id
    return person_to_out(doc)


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
    try:
        oid = ObjectId(person_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person id")

    person = await db.persons.find_one({"_id": oid})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    new_val = int(body.value)
    is_outsider = person.get("source") == "self_boosted"

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
                    score=float(eff_score),
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
        await db.persons.update_one(
            {"_id": oid},
            {"$inc": inc_doc, "$set": {"updated_at": now_utc()}}
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
            score=float(eff_score),
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
                score=float(eff_score),
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
        new_score = round(raw_score / 25) * 25
        new_score = max(0, min(100, new_score))
    else:
        new_score = 0
    
    # Update person aggregates
    await db.persons.update_one(
        {"_id": oid},
        {"$inc": inc_doc, "$set": {"score": new_score, "raw_score": raw_score, "updated_at": now_utc()}}
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
        score=float(eff_score),
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
        import random
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
    
    # Fetch person details
    result = []
    for pid in sorted_ids:
        try:
            p = await db.persons.find_one({"_id": ObjectId(pid)})
            if p:
                result.append(person_to_out(p))
        except Exception:
            continue
    
    return result


@api_router.get("/controversial", response_model=List[PersonOut])
async def get_controversial(limit: int = Query(default=5, le=20)):
    """Get most controversial personalities (lots of opposing votes)"""
    # Find persons with both high likes AND high dislikes
    cursor = db.persons.find({
        "approved": True,
        "total_votes": {"$gte": 10}  # Minimum 10 votes
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
                                   "tennis", "author", "director", "entrepreneur", "ceo", "founder"]
                
                is_person = any(keyword in snippet for keyword in person_keywords)
                
                words = title.split()
                looks_like_name = 1 <= len(words) <= 5 and all(w[0].isupper() for w in words if w)
                
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
    """Search for people by name (case-insensitive, accent-insensitive, partial match)
    If not found locally, searches Wikipedia and adds the person to the database."""
    try:
        search_term = query.strip()
        search_term_normalized = remove_accents(search_term)
        
        # Build filter for approved personalities only
        filter_q: Dict[str, Any] = {"approved": True}
        
        # Split into words for multi-word search
        words = search_term_normalized.split()
        
        if len(words) == 1:
            # Single word: match anywhere in name (with or without accents)
            word = words[0]
            flexible_regex = ''.join([
                f"[{c}{get_accent_variants(c)}]" if c.isalpha() else re.escape(c)
                for c in word
            ])
            filter_q["name"] = {"$regex": flexible_regex, "$options": "i"}
        else:
            # Multiple words: match all words in any order
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
        
        # If no local results found, search Wikipedia
        if not results and len(search_term) >= 3:
            wiki_person = await search_wikipedia_person(search_term)
            
            if wiki_person:
                # Check if this person already exists (exact name match)
                existing = await db.persons.find_one({
                    "name": {"$regex": f"^{re.escape(wiki_person['name'])}$", "$options": "i"}
                })
                
                if existing:
                    results = [existing]
                else:
                    # Create the person in the database
                    import random
                    initial_votes = random.randint(100, 500)
                    like_ratio = random.uniform(0.45, 0.70)
                    initial_likes = int(initial_votes * like_ratio)
                    initial_dislikes = initial_votes - initial_likes
                    score = like_ratio * 100
                    
                    new_person = {
                        "name": wiki_person["name"],
                        "slug": slugify(wiki_person["name"]),
                        "category": wiki_person["category"],
                        "approved": True,
                        "created_at": now_utc(),
                        "updated_at": now_utc(),
                        "score": round(score, 2),
                        "likes": initial_likes,
                        "dislikes": initial_dislikes,
                        "total_votes": initial_votes,
                        "source": "wikipedia",
                    }
                    
                    result = await db.persons.insert_one(new_person)
                    new_person["_id"] = result.inserted_id
                    results = [new_person]
                    
                    logger.info(f"Added new personality from Wikipedia: {wiki_person['name']}")
        
        out = []
        for doc in results:
            _, eff_score, eff_likes, eff_dislikes, eff_total = compute_effective_score(doc)
            out.append({
                "id": str(doc["_id"]),
                "name": doc.get("name"),
                "category": doc.get("category", "other"),
                "score": eff_score,
                "total_votes": eff_total,
                "likes": eff_likes,
                "dislikes": eff_dislikes,
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
        active_boosts = await db.active_boosts.find(boost_filter).sort("start_time", -1).to_list(length=100)

        golden_outsiders = []
        regular_outsiders = []

        user_country = country.upper().strip() if country else None

        for boost in active_boosts:
            person = await db.persons.find_one({"_id": boost["person_id"]})
            if not person:
                continue

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

import re

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

        # Normalize and validate name
        name = request.name.strip().title()
        if not name or len(name) < 2:
            raise HTTPException(status_code=400, detail="Please enter a valid name (at least 2 characters)")

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
                    if cleaned:
                        if not _validate_social_username(platform, cleaned):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Invalid {platform} username format: {cleaned}"
                            )
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
                    if cleaned:
                        if not _validate_social_username(platform, cleaned):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Invalid {platform} username format: {cleaned}"
                            )
                        social[platform] = cleaned

            person_doc = {
                "name": name,
                "slug": slug,
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

            await db.active_boosts.update_one(
                {"_id": existing_boost["_id"]},
                {"$set": {
                    "end_time": new_end,
                    "tier": request.tier,
                    "position": new_position,
                    "updated_at": now,
                }}
            )
            end_time = new_end
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
            }
            await db.active_boosts.insert_one(boost_doc)

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
            "person_name": name,
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


# -------------------- Admin Endpoints --------------------

@api_router.get("/admin/stats")
async def get_admin_stats():
    """Get global statistics for admin dashboard"""
    try:
        # Total people
        total_people = await db.persons.count_documents({})
        
        # Total votes across all people
        pipeline_votes = [
            {
                "$group": {
                    "_id": None,
                    "total_votes": {"$sum": "$total_votes"},
                    "total_likes": {"$sum": "$likes"},
                    "total_dislikes": {"$sum": "$dislikes"},
                }
            }
        ]
        vote_result = await db.persons.aggregate(pipeline_votes).to_list(1)
        total_votes = vote_result[0]["total_votes"] if vote_result else 0
        
        # Active users 24h (count unique user_ids from credit_transactions in last 24h)
        yesterday = now_utc() - timedelta(days=1)
        active_users_pipeline = [
            {"$match": {"timestamp": {"$gte": yesterday}}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"}
        ]
        active_users_result = await db.credit_transactions.aggregate(active_users_pipeline).to_list(1)
        active_users_24h = active_users_result[0]["count"] if active_users_result else 0
        
        # Revenue 24h (sum of purchases in last 24h)
        revenue_pipeline = [
            {
                "$match": {
                    "type": "purchase",
                    "timestamp": {"$gte": yesterday}
                }
            },
            {
                "$lookup": {
                    "from": "credit_packs",
                    "let": {"pack_name": "$description"},
                    "pipeline": [],
                    "as": "pack_info"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": 0.99}  # Simple estimate for now
                }
            }
        ]
        revenue_result = await db.credit_transactions.aggregate(revenue_pipeline).to_list(1)
        # Count purchases and multiply by average price
        purchases_24h = await db.credit_transactions.count_documents({
            "type": "purchase",
            "timestamp": {"$gte": yesterday}
        })
        revenue_24h = round(purchases_24h * 0.99, 2)  # Assuming average is 0.99€
        
        # New people added in 24h
        new_people_24h = await db.persons.count_documents({
            "created_at": {"$gte": yesterday}
        })
        
        return {
            "total_people": total_people,
            "total_votes": total_votes,
            "active_users_24h": active_users_24h,
            "revenue_24h": f"{revenue_24h:.2f}",
            "new_people_24h": new_people_24h,
        }
        
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AdminBoostRequest(BaseModel):
    person_id: str
    amount: int
    type: Literal["likes", "dislikes"] = "likes"


@api_router.post("/admin/boost-votes")
async def admin_boost_votes(request: AdminBoostRequest):
    """Admin-only: Manually add votes to any personality"""
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
async def admin_delete_person(person_id: str):
    """Admin-only: Delete a personality completely"""
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
        
        return {
            "success": True,
            "message": f"'{person_name}' has been deleted permanently",
            "person_name": person_name,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin delete person error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/person/{person_id}/reset")
async def admin_reset_person(person_id: str):
    """Admin-only: Reset a personality's score to 50 (neutral)"""
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

@api_router.get("/admin/activity/recent")
async def admin_get_recent_activity():
    """Admin-only: Get recent activity (votes, new people, purchases)"""
    try:
        # Last 50 person additions (last 7 days)
        week_ago = now_utc() - timedelta(days=7)
        recent_people = await db.persons.find(
            {"created_at": {"$gte": week_ago}},
            {"name": 1, "source": 1, "created_at": 1, "score": 1}
        ).sort("created_at", -1).limit(50).to_list(50)
        
        # Last 50 credit transactions
        recent_purchases = await db.credit_transactions.find(
            {"type": "purchase"},
            {"user_id": 1, "amount": 1, "description": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        # Last 50 credit uses
        recent_uses = await db.credit_transactions.find(
            {"type": "use"},
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

@api_router.get("/admin/search")
async def admin_search_people(
    q: Optional[str] = None,
    category: Optional[Category] = None,
    source: Optional[str] = None,
    sort_by: str = "score",  # score, votes, name, date
    limit: int = 50
):
    """Admin-only: Advanced search with filters"""
    try:
        # Build query
        query = {}
        
        if q:
            query["name"] = {"$regex": q, "$options": "i"}  # Case-insensitive search
        
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
        
        return [
            {
                "id": str(p["_id"]),
                "name": p.get("name"),
                "category": p.get("category", "other"),
                "source": p.get("source", "seed"),
                "score": p.get("score", 50),
                "likes": p.get("likes", 0),
                "dislikes": p.get("dislikes", 0),
                "total_votes": p.get("total_votes", 0),
                "created_at": p.get("created_at").isoformat() if p.get("created_at") else None,
            }
            for p in results
        ]
        
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
async def admin_get_settings():
    """Admin-only: Get app settings"""
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
async def admin_update_settings(settings: AppSettings):
    """Admin-only: Update app settings"""
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
async def admin_refresh_trends():
    """
    Admin-only: Manually trigger Google Trends refresh
    Fetches trending personalities and updates the database
    """
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
async def admin_get_scheduler_status():
    """Admin-only: Get scheduler status and next run time"""
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
async def admin_fix_categories():
    """Admin-only: Fix category assignments for sports personalities and Pope Francis"""
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
async def admin_create_demo_outsider():
    """Admin-only: Create a demo outsider to show the feature"""
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
async def admin_add_missing_seeds():
    """Admin-only: Add any missing seed personalities to the database"""
    import random
    try:
        added_count = 0
        added_names = []
        
        for p in SEED_PEOPLE:
            # Check if personality already exists
            existing = await db.persons.find_one({
                "name": {"$regex": f"^{re.escape(p['name'])}$", "$options": "i"}
            })
            
            if not existing:
                # Generate random initial votes between 8000 and 15000
                initial_votes = random.randint(8000, 15000)
                like_ratio = random.uniform(0.40, 0.80)
                initial_likes = int(initial_votes * like_ratio)
                initial_dislikes = initial_votes - initial_likes
                raw_score = like_ratio * 100
                initial_score = round(raw_score / 25) * 25
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


@api_router.post("/admin/initialize-votes")
async def admin_initialize_votes():
    """Admin-only: Initialize existing personalities with realistic vote counts"""
    import random
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
            initial_score = round(raw_score / 25) * 25
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
    import random
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
async def admin_migrate_index():
    """
    One-time migration: Calculate initial Popularoo Index for all persons.
    Safe to run multiple times (idempotent).
    """
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
async def admin_recalculate_indices():
    """Force a full recalculation of Popularoo Index for all persons."""
    try:
        await recalculate_all_indices(db)
        return {"success": True, "message": "All indices recalculated"}
    except Exception as e:
        logger.error(f"Recalculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/index-config")
async def admin_get_index_config():
    """View current algorithm configuration (admin only)."""
    config = await load_index_config(db)
    safe = {k: v for k, v in config.items() if k != "_id"}
    return {"config": safe}


@api_router.post("/admin/index-config")
async def admin_update_index_config(body: Dict[str, Any]):
    """
    Update algorithm coefficients (admin only).
    Example: {"coefficients": {"volume": 0.25, "ratio": 0.35}}
    """
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
async def admin_apply_geo_tags():
    """
    Apply geo-tags from the pre-generated JSON file to all personalities.
    Idempotent: safe to run multiple times.
    """
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
async def admin_geo_tags_summary():
    """Get summary of geo-tag distribution across all personalities."""
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
async def admin_delete_duplicate(person_id: str):
    """Delete a duplicate/invalid personality entry. Admin only."""
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
async def admin_bulk_import_personalities():
    """
    Import new personalities from the validated personality_tags_v2.json file.
    Only inserts NEW entries (status='new') that don't already exist in the DB.
    Idempotent: safe to run multiple times.
    """
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

            # Insert new personality
            import random
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

    try:
        person_oid = ObjectId(person_id_str)
        target_oid = ObjectId(target_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid person_id or target_id")

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
from starlette.responses import StreamingResponse

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
    "privacy": "privacy.html",
    "privacy-fr": "privacy-fr.html",
    "terms": "terms.html",
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

@api_router.post("/admin/test-email")
async def test_email_endpoint(
    email_type: str = Query(..., description="Type: welcome, booster, victory_standard, victory_underdog, victory_legendary, going_viral, legend_mode, expiration"),
    to_email: str = Query(default="popularoo@popularoo.com"),
    lang: str = Query(default="fr"),
    password: str = Query(default=""),
):
    """Admin: test transactional emails manually. Requires admin password."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")

    # Create a temporary user setting for the test language
    test_user_id = f"test_email_{lang}"
    await db.user_settings.update_one(
        {"device_id": test_user_id},
        {"$set": {"device_id": test_user_id, "language": lang}},
        upsert=True,
    )

    try:
        if email_type == "welcome":
            await send_welcome(db, email_service, to_email, test_user_id, "Test User")
        elif email_type == "booster":
            await send_booster_confirmation(db, email_service, to_email, test_user_id,
                                            "Test User", "Super Booster", "24 hours", is_golden=False)
        elif email_type == "booster_golden":
            await send_booster_confirmation(db, email_service, to_email, test_user_id,
                                            "Test User", "Golden Booster", "1 week", is_golden=True)
        elif email_type == "victory_standard":
            await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                          "Test User", "Elon Musk", 12, "Standard Win", 847)
        elif email_type == "victory_underdog":
            await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                          "Test User", "Taylor Swift", 35, "Underdog Win", 2340,
                                          strikes_count=3, highest_strike="Trending")
        elif email_type == "victory_legendary":
            await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                          "Test User", "Cristiano Ronaldo", 72, "Legendary Strike", 8921,
                                          strikes_count=5, highest_strike="Legend Mode")
        elif email_type == "going_viral":
            await send_strike_going_viral(db, email_service, to_email, test_user_id, "Test User")
        elif email_type == "legend_mode":
            await send_strike_legend_mode(db, email_service, to_email, test_user_id, "Test User")
        elif email_type == "expiration":
            await send_booster_expiration(db, email_service, to_email, test_user_id,
                                          "Test User", "Super Booster", "3 hours",
                                          total_votes=1247, best_rank=3, daily_runs_count=2)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown email type: {email_type}")

        return {"success": True, "email_type": email_type, "lang": lang, "to": to_email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/test-all-emails")
async def test_all_emails_endpoint(
    to_email: str = Query(default="popularoo@popularoo.com"),
    lang: str = Query(default="fr"),
    password: str = Query(default=""),
):
    """Admin: Send ALL 9 transactional email variants at once for testing."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")

    email_types = [
        "welcome", "booster", "booster_golden",
        "victory_standard", "victory_underdog", "victory_legendary",
        "going_viral", "legend_mode", "expiration",
    ]

    results = []
    for etype in email_types:
        try:
            # Re-use the single-email endpoint logic inline
            test_user_id = f"test_email_{lang}"
            await db.user_settings.update_one(
                {"device_id": test_user_id},
                {"$set": {"device_id": test_user_id, "language": lang}},
                upsert=True,
            )
            if etype == "welcome":
                await send_welcome(db, email_service, to_email, test_user_id, "Test User")
            elif etype == "booster":
                await send_booster_confirmation(db, email_service, to_email, test_user_id,
                                                "Test User", "Super Booster", "24 hours", is_golden=False)
            elif etype == "booster_golden":
                await send_booster_confirmation(db, email_service, to_email, test_user_id,
                                                "Test User", "Golden Booster", "1 week", is_golden=True)
            elif etype == "victory_standard":
                await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                              "Test User", "Elon Musk", 12, "Standard Win", 847)
            elif etype == "victory_underdog":
                await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                              "Test User", "Taylor Swift", 35, "Underdog Win", 2340,
                                              strikes_count=3, highest_strike="Trending")
            elif etype == "victory_legendary":
                await send_daily_run_victory(db, email_service, to_email, test_user_id,
                                              "Test User", "Cristiano Ronaldo", 72, "Legendary Strike", 8921,
                                              strikes_count=5, highest_strike="Legend Mode")
            elif etype == "going_viral":
                await send_strike_going_viral(db, email_service, to_email, test_user_id, "Test User")
            elif etype == "legend_mode":
                await send_strike_legend_mode(db, email_service, to_email, test_user_id, "Test User")
            elif etype == "expiration":
                await send_booster_expiration(db, email_service, to_email, test_user_id,
                                              "Test User", "Super Booster", "3 hours",
                                              total_votes=1247, best_rank=3, daily_runs_count=2)
            results.append({"type": etype, "status": "sent"})
        except Exception as e:
            results.append({"type": etype, "status": "failed", "error": str(e)})

    sent_count = sum(1 for r in results if r["status"] == "sent")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    return {
        "success": failed_count == 0,
        "lang": lang,
        "to": to_email,
        "sent": sent_count,
        "failed": failed_count,
        "details": results,
    }


@api_router.get("/admin/email-errors")
async def get_email_errors(
    password: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin: View recent email delivery errors logged in admin_notifications."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")

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
async def download_emails_review(password: str = Query(default="")):
    """Admin: Download the EMAILS_REVIEW.md file for proofreading."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")
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
async def seed_outsiders_endpoint(password: str = Query(default="")):
    """Admin: Create all 49 seed Outsiders. Idempotent (skips existing)."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")
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
async def seed_outsiders_status(password: str = Query(default="")):
    """Admin: View seed Outsiders status per country."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")
    from seed_outsiders import get_seed_status
    return await get_seed_status(db)


@api_router.delete("/admin/seed-outsiders")
async def remove_seed_outsiders_endpoint(password: str = Query(default="")):
    """Admin: Remove ALL seed Outsiders from the database."""
    if password != "fab31230":
        raise HTTPException(status_code=403, detail="Invalid admin password")
    from seed_outsiders import remove_all_seeds
    result = await remove_all_seeds(db)
    return {"success": True, **result}


# Include API router AFTER all endpoints are defined on it
app.include_router(api_router)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
