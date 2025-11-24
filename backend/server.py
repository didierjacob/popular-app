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
    {"name": "Elon Musk", "category": "business"},
    {"name": "Tim Cook", "category": "business"},
    {"name": "Sundar Pichai", "category": "business"},
    {"name": "Mark Zuckerberg", "category": "business"},
    {"name": "Satya Nadella", "category": "business"},
    {"name": "Warren Buffett", "category": "business"},
    {"name": "Oprah Winfrey", "category": "culture"},
    {"name": "Taylor Swift", "category": "culture"},
    {"name": "Beyoncé", "category": "culture"},
    {"name": "Lionel Messi", "category": "culture"},
    {"name": "Cristiano Ronaldo", "category": "culture"},
    {"name": "Greta Thunberg", "category": "culture"},
    {"name": "Barack Obama", "category": "politics"},
    {"name": "Donald Trump", "category": "politics"},
    {"name": "Joe Biden", "category": "politics"},
    {"name": "Kamala Harris", "category": "politics"},
    {"name": "Emmanuel Macron", "category": "politics"},
    {"name": "Rishi Sunak", "category": "politics"},
    {"name": "Angela Merkel", "category": "politics"},
    {"name": "Xi Jinping", "category": "politics"},
    {"name": "Jeff Bezos", "category": "business"},
    {"name": "Sheryl Sandberg", "category": "business"},
    {"name": "Reed Hastings", "category": "business"},
    {"name": "Serena Williams", "category": "culture"},
    {"name": "LeBron James", "category": "culture"},
    {"name": "Malala Yousafzai", "category": "culture"},
    {"name": "Pope Francis", "category": "culture"},
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
    )


@api_router.get("/people", response_model=List[PersonOut])
async def list_people(query: Optional[str] = Query(default=None), limit: int = Query(default=20, le=50), category: Optional[str] = Query(default=None)):
    filter_q: Dict[str, Any] = {"approved": True}
    if query:
        # Search for partial matches in name (case-insensitive)
        # This allows "trump" to match "Donald Trump", "elon" to match "Elon Musk", etc.
        search_term = query.strip()
        # Split the search term into words and create a regex that matches any part of the name
        words = search_term.split()
        if len(words) == 1:
            # Single word search: match anywhere in the name
            regex = re.escape(words[0])
            filter_q["name"] = {"$regex": regex, "$options": "i"}
        else:
            # Multiple words: match all words in any order
            regexes = [{"name": {"$regex": re.escape(word), "$options": "i"}} for word in words]
            filter_q["$and"] = regexes
    if category:
        cat = category.strip().lower()
        if cat != "all":
            if cat not in {"politics", "culture", "business", "sport", "other"}:
                raise HTTPException(status_code=400, detail="Invalid category")
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
    pack: Literal["starter", "basic", "pro", "elite"]
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
    "starter": {"credits": 1, "price": 5.0},
    "basic": {"credits": 5, "price": 20.0},
    "pro": {"credits": 10, "price": 35.0},
    "elite": {"credits": 25, "price": 75.0}
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
