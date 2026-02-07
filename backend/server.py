from fastapi import FastAPI, APIRouter, HTTPException, Header, Query
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
    """Initialize scheduler on application startup"""
    logger.info("🚀 Starting Popular API...")
    
    # Initialize and start the scheduler
    init_scheduler(db, trends_service)
    start_scheduler()
    
    logger.info("✅ Scheduler initialized and started")
    logger.info("📅 Daily Google Trends refresh scheduled at 3:00 AM UTC")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler gracefully"""
    logger.info("🛑 Shutting down Popular API...")
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
    total_votes: int = 0
    last_updated: Optional[datetime] = None
    source: Optional[str] = "seed"  # "seed", "user_added", "self_boosted", "trending"
    is_trending: Optional[bool] = False


class VoteIn(BaseModel):
    value: Literal[1, -1]


class VoteOut(BaseModel):
    id: str
    score: float
    likes: int
    dislikes: int
    total_votes: int
    voted_value: int


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
    # Business
    {"name": "Elon Musk", "category": "business"},
    {"name": "Tim Cook", "category": "business"},
    {"name": "Sundar Pichai", "category": "business"},
    {"name": "Mark Zuckerberg", "category": "business"},
    {"name": "Satya Nadella", "category": "business"},
    {"name": "Warren Buffett", "category": "business"},
    {"name": "Jeff Bezos", "category": "business"},
    {"name": "Sheryl Sandberg", "category": "business"},
    {"name": "Reed Hastings", "category": "business"},
    # Culture
    {"name": "Oprah Winfrey", "category": "culture"},
    {"name": "Taylor Swift", "category": "culture"},
    {"name": "Beyoncé", "category": "culture"},
    {"name": "Greta Thunberg", "category": "culture"},
    {"name": "Malala Yousafzai", "category": "culture"},
    {"name": "Pope Francis", "category": "culture"},
    {"name": "Kanye West", "category": "culture"},
    {"name": "Rihanna", "category": "culture"},
    # Sport
    {"name": "Lionel Messi", "category": "sport"},
    {"name": "Cristiano Ronaldo", "category": "sport"},
    {"name": "Serena Williams", "category": "sport"},
    {"name": "LeBron James", "category": "sport"},
    {"name": "Kylian Mbappé", "category": "sport"},
    {"name": "Lewis Hamilton", "category": "sport"},
    {"name": "Roger Federer", "category": "sport"},
    {"name": "Tom Brady", "category": "sport"},
    # Politics
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
]


async def ensure_indexes():
    # persons
    await db.persons.create_index("slug", unique=True)
    await db.persons.create_index([("approved", 1), ("total_votes", -1), ("score", -1)])
    await db.persons.create_index([("name", "text")])
    # votes (one per device/person)
    await db.votes.create_index([("person_id", 1), ("device_id", 1)], unique=True)
    # vote_events for time window aggregations
    await db.vote_events.create_index([("created_at", 1), ("person_id", 1)])
    # ticks for charts
    await db.person_ticks.create_index([("person_id", 1), ("created_at", 1)])
    # searches for suggestions
    await db.searches.create_index([("created_at", 1), ("query", 1)])


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


# -------------------- Routes --------------------
@api_router.get("/")
async def root():
    return {"message": "Popular API running"}


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


def person_to_out(doc: Dict[str, Any]) -> PersonOut:
    return PersonOut(
        id=str(doc["_id"]),
        name=doc.get("name"),
        category=doc.get("category", "other"),
        approved=bool(doc.get("approved", True)),
        score=float(doc.get("score", 100.0)),
        likes=int(doc.get("likes", 0)),
        dislikes=int(doc.get("dislikes", 0)),
        total_votes=int(doc.get("total_votes", 0)),
        last_updated=doc.get("updated_at"),
        source=doc.get("source", "seed"),
    )


@api_router.get("/people", response_model=List[PersonOut])
async def list_people(query: Optional[str] = Query(default=None), limit: int = Query(default=20, le=50), category: Optional[str] = Query(default=None), include_outsiders: bool = Query(default=False)):
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

    existing_vote = await db.votes.find_one({"person_id": oid, "device_id": x_device_id})

    new_val = int(body.value)
    delta = new_val
    inc_doc: Dict[str, Any] = {"total_votes": 0}

    if existing_vote:
        old_val = int(existing_vote.get("value", 0))
        if old_val == new_val:
            # no change; just return current state
            return VoteOut(
                id=str(person["_id"]),
                score=float(person.get("score", 100.0)),
                likes=int(person.get("likes", 0)),
                dislikes=int(person.get("dislikes", 0)),
                total_votes=int(person.get("total_votes", 0)),
                voted_value=new_val,
            )
        delta = new_val - old_val
        # adjust likes/dislikes counters
        if new_val == 1 and old_val == -1:
            inc_doc["likes"] = 1
            inc_doc["dislikes"] = -1
        elif new_val == -1 and old_val == 1:
            inc_doc["likes"] = -1
            inc_doc["dislikes"] = 1
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
    # Simple system with scores in multiples of 25: 0, 25, 50, 75, 100
    new_likes = int(person.get("likes", 0)) + inc_doc.get("likes", 0)
    new_dislikes = int(person.get("dislikes", 0)) + inc_doc.get("dislikes", 0)
    new_total_votes = int(person.get("total_votes", 0)) + inc_doc.get("total_votes", 0)
    
    # Calculate score based on like ratio, rounded to nearest 25
    if new_total_votes > 0:
        # Calculate percentage of likes (0 to 1)
        like_ratio = new_likes / new_total_votes
        
        # Convert to 0-100 scale
        raw_score = like_ratio * 100
        
        # Round to nearest 25 (0, 25, 50, 75, 100)
        new_score = round(raw_score / 25) * 25
        
        # Ensure score stays within bounds
        new_score = max(0, min(100, new_score))
    else:
        new_score = 50  # Neutral starting score
    
    # Update person aggregates with calculated score
    await db.persons.update_one(
        {"_id": oid},
        {"$inc": inc_doc, "$set": {"score": new_score, "updated_at": now_utc()}}
    )
    await db.person_ticks.insert_one({"person_id": oid, "score": new_score, "created_at": now_utc()})
    await write_vote_event(oid, x_device_id, int(delta))

    # fetch updated person
    updated = await db.persons.find_one({"_id": oid})
    return VoteOut(
        id=str(updated["_id"]),
        score=float(updated.get("score", 100.0)),
        likes=int(updated.get("likes", 0)),
        dislikes=int(updated.get("dislikes", 0)),
        total_votes=int(updated.get("total_votes", 0)),
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

    # Ensure we at least return the latest point if none in window
    if not ticks:
        latest = await db.person_ticks.find({"person_id": oid}).sort("created_at", -1).limit(1).to_list(1)
        ticks = latest or []

    points = [{"t": t["created_at"].isoformat() + "Z", "score": float(t.get("score", person.get("score", 100.0)))} for t in ticks]
    return ChartOut(id=str(person["_id"]), name=person.get("name"), points=points)


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


@api_router.get("/search")
async def search_people(query: str = Query(..., min_length=1), limit: int = Query(default=10, le=50)):
    """Search for people by name (case-insensitive)"""
    try:
        # Case-insensitive regex search
        regex_pattern = {"$regex": query, "$options": "i"}
        
        cursor = db.persons.find({"name": regex_pattern}).sort("score", -1).limit(limit)
        results = await cursor.to_list(length=limit)
        
        return [
            {
                "id": str(doc["_id"]),
                "name": doc.get("name"),
                "category": doc.get("category", "other"),
                "score": doc.get("score", 50.0),
                "total_votes": doc.get("total_votes", 0),
                "likes": doc.get("likes", 0),
                "dislikes": doc.get("dislikes", 0),
                "source": doc.get("source", "unknown"),
            }
            for doc in results
        ]
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


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
async def get_outsiders(limit: int = Query(default=3, le=10)):
    """Get outsiders - people who received premium boosts (non-celebrities trying to become popular)"""
    try:
        # Find people who have received premium votes or were added by users (not seed)
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"source": {"$ne": "seed"}},
                        {"source": {"$exists": False}},
                        {"boosted": True}
                    ]
                }
            },
            {"$sort": {"total_votes": -1}},
            {"$limit": limit}
        ]
        
        outsiders = await db.persons.aggregate(pipeline).to_list(length=limit)
        
        # If no outsiders found, return some random low-vote personalities as potential outsiders
        if len(outsiders) == 0:
            outsiders = await db.persons.find({}).sort("total_votes", 1).limit(limit).to_list(length=limit)
        
        return [
            {
                "id": str(doc["_id"]),
                "name": doc.get("name"),
                "category": doc.get("category", "other"),
                "score": doc.get("score", 50.0),
                "total_votes": doc.get("total_votes", 0),
                "likes": doc.get("likes", 0),
                "dislikes": doc.get("dislikes", 0),
            }
            for doc in outsiders
        ]
    except Exception as e:
        logger.error(f"Failed to get outsiders: {e}")
        return []


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


# -------------------- Premium / Credits System --------------------

class CreditPurchase(BaseModel):
    user_id: str
    pack: Literal["booster", "super_booster"]
    amount: int  # Number of credits
    price: float  # Price in euros

class CreditTransaction(BaseModel):
    user_id: str
    type: Literal["purchase", "use", "refund"]
    amount: int
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class PremiumVote(BaseModel):
    person_id: str
    person_name: str
    vote: int  # 1 for like, -1 for dislike
    multiplier: int = 100  # Premium vote = x100

CREDIT_PACKS = {
    "booster": {"credits": 100, "price": 0.99},
    "super_booster": {"credits": 1000, "price": 4.99}
}

@api_router.post("/credits/purchase")
async def purchase_credits(purchase: CreditPurchase):
    """Simulate credit purchase (MVP - no real payment)"""
    try:
        # Validate pack
        if purchase.pack not in CREDIT_PACKS:
            raise HTTPException(status_code=400, detail="Invalid pack")
        
        pack_info = CREDIT_PACKS[purchase.pack]
        
        # Validate amount and price
        if purchase.amount != pack_info["credits"] or purchase.price != pack_info["price"]:
            raise HTTPException(status_code=400, detail="Invalid pack configuration")
        
        # Create transaction record
        transaction = {
            "user_id": purchase.user_id,
            "type": "purchase",
            "amount": purchase.amount,
            "price": purchase.price,
            "pack": purchase.pack,
            "description": f"Purchased {purchase.amount} premium vote(s)",
            "timestamp": datetime.utcnow(),
            "status": "completed"
        }
        
        await db.credit_transactions.insert_one(transaction)
        
        # Update user balance
        user_credits = await db.user_credits.find_one({"user_id": purchase.user_id})
        
        if user_credits:
            new_balance = user_credits["balance"] + purchase.amount
            await db.user_credits.update_one(
                {"user_id": purchase.user_id},
                {"$set": {"balance": new_balance, "updated_at": datetime.utcnow()}}
            )
        else:
            await db.user_credits.insert_one({
                "user_id": purchase.user_id,
                "balance": purchase.amount,
                "is_premium": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
        
        return {
            "success": True,
            "transaction_id": str(transaction.get("_id")),
            "new_balance": user_credits["balance"] + purchase.amount if user_credits else purchase.amount,
            "message": f"Successfully purchased {purchase.amount} credit(s)!"
        }
        
    except Exception as e:
        logger.error(f"Credit purchase error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/credits/balance/{user_id}")
async def get_credit_balance(user_id: str):
    """Get user's credit balance"""
    user_credits = await db.user_credits.find_one({"user_id": user_id})
    
    if not user_credits:
        return {
            "balance": 0,
            "is_premium": False
        }
    
    return {
        "balance": user_credits.get("balance", 0),
        "is_premium": user_credits.get("is_premium", False)
    }

@api_router.post("/credits/use")
async def use_credit(vote: PremiumVote, user_id: str = Header(...)):
    """Use a premium credit for a x100 vote"""
    try:
        # Check user balance
        user_credits = await db.user_credits.find_one({"user_id": user_id})
        
        if not user_credits or user_credits.get("balance", 0) < 1:
            raise HTTPException(status_code=400, detail="Insufficient credits")
        
        # Get person
        person_doc = await db.people.find_one({"_id": ObjectId(vote.person_id)})
        if not person_doc:
            raise HTTPException(status_code=404, detail="Person not found")
        
        # Apply x100 vote
        multiplied_vote = vote.vote * vote.multiplier
        
        # Update person stats
        current_likes = person_doc.get("likes", 0)
        current_dislikes = person_doc.get("dislikes", 0)
        
        if vote.vote > 0:
            current_likes += vote.multiplier
        else:
            current_dislikes += vote.multiplier
        
        total = current_likes + current_dislikes
        raw_score = (current_likes / total * 100) if total > 0 else 50.0
        rounded = round(raw_score / 25) * 25
        
        await db.people.update_one(
            {"_id": ObjectId(vote.person_id)},
            {
                "$set": {
                    "likes": current_likes,
                    "dislikes": current_dislikes,
                    "total_votes": total,
                    "score": float(rounded),
                    "last_updated": datetime.utcnow()
                }
            }
        )
        
        # Record tick (x100 votes)
        for _ in range(vote.multiplier):
            await db.ticks.insert_one({
                "person_id": vote.person_id,
                "vote": vote.vote,
                "score": float(rounded),
                "created_at": datetime.utcnow()
            })
        
        # Deduct credit
        new_balance = user_credits["balance"] - 1
        await db.user_credits.update_one(
            {"user_id": user_id},
            {"$set": {"balance": new_balance, "updated_at": datetime.utcnow()}}
        )
        
        # Record transaction
        await db.credit_transactions.insert_one({
            "user_id": user_id,
            "type": "use",
            "amount": -1,
            "description": f"Premium vote x{vote.multiplier} for {vote.person_name}",
            "person_id": vote.person_id,
            "timestamp": datetime.utcnow(),
            "status": "completed"
        })
        
        return {
            "success": True,
            "new_balance": new_balance,
            "votes_applied": vote.multiplier,
            "new_score": float(rounded)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Credit use error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/credits/history/{user_id}")
async def get_credit_history(user_id: str, limit: int = Query(default=20, le=50)):
    """Get user's credit transaction history"""
    transactions = await db.credit_transactions.find(
        {"user_id": user_id}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    
    # Convert ObjectId to string
    for t in transactions:
        t["_id"] = str(t["_id"])
    
    return {"transactions": transactions}

class BoostMyselfRequest(BaseModel):
    user_id: str
    name: str
    category: Optional[Category] = "other"

@api_router.post("/boost-myself")
async def boost_myself(request: BoostMyselfRequest):
    """Create a new personality for yourself and apply 1 booster (100 votes) - costs 1 credit"""
    try:
        # Check user balance
        user_credits = await db.user_credits.find_one({"user_id": request.user_id})
        
        if not user_credits or user_credits.get("balance", 0) < 1:
            raise HTTPException(status_code=400, detail="Insufficient credits. You need at least 1 credit to boost yourself.")
        
        # Normalize and validate name
        name = request.name.strip().title()
        if not name or len(name) < 2:
            raise HTTPException(status_code=400, detail="Please enter a valid name (at least 2 characters)")
        
        # Check if person already exists
        slug = slugify(name)
        existing = await db.persons.find_one({"slug": slug})
        
        if existing:
            raise HTTPException(status_code=400, detail=f"{name} already exists in the database")
        
        # Create the new person with boosted stats (100 likes from the booster)
        now = now_utc()
        person_doc = {
            "name": name,
            "slug": slug,
            "category": request.category or "other",
            "approved": True,
            "created_at": now,
            "updated_at": now,
            "score": 100.0,  # 100% likes = 100 score
            "likes": 100,  # Booster applies 100 likes
            "dislikes": 0,
            "total_votes": 100,
            "source": "self_boosted",  # Mark as self-boosted user
        }
        
        result = await db.persons.insert_one(person_doc)
        person_id = result.inserted_id
        
        # Create initial tick with boosted score
        await db.person_ticks.insert_one({
            "person_id": person_id,
            "score": 100.0,
            "created_at": now
        })
        
        # Deduct 1 credit from user balance
        new_balance = user_credits["balance"] - 1
        await db.user_credits.update_one(
            {"user_id": request.user_id},
            {"$set": {"balance": new_balance, "updated_at": now_utc()}}
        )
        
        # Record transaction
        await db.credit_transactions.insert_one({
            "user_id": request.user_id,
            "type": "use",
            "amount": -1,
            "description": f"Boosted myself as '{name}' with 100 votes",
            "person_id": str(person_id),
            "timestamp": now_utc(),
            "status": "completed"
        })
        
        return {
            "success": True,
            "person_id": str(person_id),
            "person_name": name,
            "new_balance": new_balance,
            "message": f"🎉 Success! You've been added to Popular as '{name}' with 100 votes!",
            "initial_score": 100.0,
            "votes_applied": 100
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Boost myself error: {e}")
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


# Include the router in the main app
app.include_router(api_router)

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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
