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


# -------------------- Pydantic Models --------------------
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=now_utc)


class StatusCheckCreate(BaseModel):
    client_name: str


Category = Literal["politics", "culture", "business", "other"]


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
    await seed_people()


# -------------------- Routes --------------------
@api_router.get("/")
async def root():
    return {"message": "Popularity API running"}


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
async def list_people(query: Optional[str] = Query(default=None), limit: int = Query(default=20, le=50)):
    filter_q: Dict[str, Any] = {"approved": True}
    if query:
        regex = re.escape(query.strip())
        filter_q["name"] = {"$regex": regex, "$options": "i"}
    cursor = db.persons.find(filter_q).sort([("total_votes", -1), ("score", -1)]).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [person_to_out(d) for d in docs]


@api_router.post("/people", response_model=PersonOut)
async def add_person(body: PersonCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
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
        "score": 100.0,
        "likes": 0,
        "dislikes": 0,
        "total_votes": 0,
    }
    res = await db.persons.insert_one(doc)
    await db.person_ticks.insert_one({"person_id": res.inserted_id, "score": 100.0, "created_at": now})
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

    # update person aggregates
    new_score = float(person.get("score", 100.0)) + float(delta)
    await db.persons.update_one(
        {"_id": oid},
        {"$inc": {"score": float(delta), **inc_doc}, "$set": {"updated_at": now_utc()}}
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


@api_router.get("/trends")
async def get_trends(window: str = Query(default="60m"), limit: int = Query(default=20, le=50)):
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
        {"$group": {"_id": "$person_id", "delta": {"$sum": "$delta"}}},
        {"$sort": {"delta": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "persons",
            "localField": "_id",
            "foreignField": "_id",
            "as": "person"
        }},
        {"$unwind": "$person"},
        {"$project": {
            "_id": 0,
            "id": {"$toString": "$person._id"},
            "name": "$person.name",
            "category": "$person.category",
            "delta": 1,
            "score": "$person.score"
        }}
    ]
    results = await db.vote_events.aggregate(pipeline).to_list(length=limit)
    return results


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
