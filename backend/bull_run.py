"""
Bull Run & Rally Cry Module for Popularoo
==========================================
Premium features exclusive to Golden Booster users.
- Bull Run: 7-day competitive game mode (climb the celebrity ladder)
- Rally Cry: Social broadcast to get community votes
"""

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

# Router with /api prefix
bull_run_router = APIRouter(prefix="/api")

# Will be set by server.py on startup
db = None


def init_bull_run(database):
    """Initialize the module with the database reference"""
    global db
    db = database


# -------------------- Constants --------------------

RANK_THRESHOLDS = [
    (500, "icon", "👑 Icon"),
    (100, "a_list", "🥇 A-List"),
    (20, "big_name", "🥈 Big Name"),
    (5, "rising_star", "🥉 Rising Star"),
]

RANK_DISPLAY = {
    "legend": {"emoji": "🌟", "name": "Legend", "color": "#FFD700"},
    "icon": {"emoji": "👑", "name": "Icon", "color": "#FF8C00"},
    "a_list": {"emoji": "🥇", "name": "A-List", "color": "#FFD700"},
    "big_name": {"emoji": "🥈", "name": "Big Name", "color": "#C0C0C0"},
    "rising_star": {"emoji": "🥉", "name": "Rising Star", "color": "#CD7F32"},
    "none": {"emoji": "", "name": "", "color": "#666666"},
}

RALLY_CRY_MAX_PER_DAY = 3
RALLY_CRY_DURATION_HOURS = 2
RALLY_CRY_COOLDOWN_MINUTES = 30
WIN_CONFIRMATION_MINUTES = 30


# -------------------- Pydantic Models --------------------

class BullRunActivateRequest(BaseModel):
    user_id: str
    person_id: str  # The outsider's person_id


class RallyCryCreateRequest(BaseModel):
    user_id: str
    bull_run_id: str
    target_celebrity_id: str
    message: Optional[str] = ""
    tone: Literal["fierce", "playful", "sincere", "custom"] = "fierce"


class RallyCryVoteRequest(BaseModel):
    value: Literal[1] = 1  # Rally Cry votes are always positive (likes)


class NotificationPreferencesRequest(BaseModel):
    receive_rally_cries: Optional[bool] = None
    bull_run_notifications: Optional[bool] = None
    muted_rally_cry_users: Optional[List[str]] = None


# -------------------- Helper Functions --------------------

def now_utc() -> datetime:
    return datetime.utcnow()


def compute_rank_from_wins(cumulative_wins: int) -> str:
    """Compute rank based on cumulative wins (excluding Legend which is dynamic)"""
    for threshold, rank_id, _ in RANK_THRESHOLDS:
        if cumulative_wins >= threshold:
            return rank_id
    return "none"


async def check_legend_status(person_id) -> bool:
    """Check if a person is in the top 10 by raw_score (Legend condition)"""
    # Get the person's raw_score
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        return False
    
    person_raw_score = person.get("raw_score", 0.0)
    
    # Count how many persons have a higher raw_score
    higher_count = await db.persons.count_documents({
        "raw_score": {"$gt": person_raw_score},
        "approved": True,
    })
    
    # If fewer than 10 persons are above, this person is in the top 10
    return higher_count < 10


async def get_effective_rank(bull_run_doc: dict) -> str:
    """Get the effective rank considering both wins-based and Legend status"""
    person_id = bull_run_doc.get("person_id")
    
    # Check Legend first (overrides everything)
    if person_id:
        is_legend = await check_legend_status(person_id)
        if is_legend:
            return "legend"
    
    # Fall back to wins-based rank
    cumulative_wins = bull_run_doc.get("cumulative_wins", 0)
    return compute_rank_from_wins(cumulative_wins)


async def build_ladder(person_id, bull_run_id) -> dict:
    """
    Build the Bull Run ladder:
    - 3 closest celebrities ABOVE the user (targets)
    - 3 most recently beaten BELOW (confirmed wins)
    """
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        return {"above": [], "below": [], "user": None}
    
    user_raw_score = person.get("raw_score", 0.0)
    
    # Get 3 closest celebrities ABOVE (targets)
    # Must be non-outsider persons with raw_score > user's raw_score
    above_cursor = db.persons.find({
        "raw_score": {"$gt": user_raw_score},
        "source": {"$ne": "self_boosted"},
        "approved": True,
    }).sort("raw_score", 1).limit(3)  # Sort ascending to get closest first
    
    above_docs = await above_cursor.to_list(length=3)
    
    above = []
    for doc in above_docs:
        above.append({
            "id": str(doc["_id"]),
            "name": doc.get("name", ""),
            "category": doc.get("category", "other"),
            "raw_score": doc.get("raw_score", 0.0),
            "score": doc.get("score", 0),
            "total_votes": doc.get("total_votes", 0),
            "gap": round(doc.get("raw_score", 0.0) - user_raw_score, 2),
            "status": "target",
        })
    
    # Get 3 most recently beaten celebrities (confirmed wins from this bull_run)
    recent_wins_cursor = db.bull_run_wins.find({
        "bull_run_id": bull_run_id,
        "confirmed": True,
    }).sort("confirmed_at", -1).limit(3)
    
    recent_wins = await recent_wins_cursor.to_list(length=3)
    
    below = []
    for win in recent_wins:
        celebrity = await db.persons.find_one({"_id": win["celebrity_id"]})
        if celebrity:
            below.append({
                "id": str(celebrity["_id"]),
                "name": celebrity.get("name", ""),
                "category": celebrity.get("category", "other"),
                "raw_score": celebrity.get("raw_score", 0.0),
                "score": celebrity.get("score", 0),
                "total_votes": celebrity.get("total_votes", 0),
                "gap": round(user_raw_score - celebrity.get("raw_score", 0.0), 2),
                "status": "beaten",
                "won_at": win.get("confirmed_at", win.get("won_at")).isoformat() + "Z" if win.get("confirmed_at") or win.get("won_at") else None,
            })
    
    user_data = {
        "id": str(person["_id"]),
        "name": person.get("name", ""),
        "raw_score": user_raw_score,
        "score": person.get("score", 0),
        "total_votes": person.get("total_votes", 0),
    }
    
    return {"above": above, "below": below, "user": user_data}


# -------------------- Endpoints --------------------

@bull_run_router.post("/bull-run/activate")
async def activate_bull_run(request: BullRunActivateRequest):
    """
    Activate or extend a Bull Run session.
    Called when a Golden Booster is purchased/renewed.
    """
    try:
        user_id = request.user_id
        person_id_str = request.person_id
        
        try:
            person_oid = ObjectId(person_id_str)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid person_id")
        
        # Verify the person exists and is an outsider
        person = await db.persons.find_one({"_id": person_oid})
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        if person.get("source") != "self_boosted":
            raise HTTPException(status_code=400, detail="Bull Run is only available for outsiders (self-boosted profiles)")
        
        # Verify user has an active Golden Booster for this person
        now = now_utc()
        active_golden = await db.active_boosts.find_one({
            "user_id": user_id,
            "person_id": person_oid,
            "tier": "golden_booster",
            "end_time": {"$gt": now},
        })
        
        if not active_golden:
            raise HTTPException(
                status_code=403,
                detail="Active Golden Booster required. Purchase a Golden Booster to access Bull Run."
            )
        
        # Check if there's already an active Bull Run for this user
        existing_bull_run = await db.bull_runs.find_one({
            "user_id": user_id,
            "is_active": True,
            "expires_at": {"$gt": now},
        })
        
        if existing_bull_run:
            # Case A: Renewal before expiration — extend
            new_expires = existing_bull_run["expires_at"] + timedelta(days=7)
            await db.bull_runs.update_one(
                {"_id": existing_bull_run["_id"]},
                {"$set": {"expires_at": new_expires, "updated_at": now}}
            )
            
            rank = await get_effective_rank(existing_bull_run)
            
            return {
                "success": True,
                "action": "extended",
                "bull_run_id": str(existing_bull_run["_id"]),
                "expires_at": new_expires.isoformat() + "Z",
                "current_rank": rank,
                "wins_count": existing_bull_run.get("wins_count", 0),
                "cumulative_wins": existing_bull_run.get("cumulative_wins", 0),
                "message": "Bull Run extended! Your winning streak continues.",
            }
        else:
            # Check for previous Bull Run (Case B: gap then new Golden)
            previous_bull_run = await db.bull_runs.find_one(
                {"user_id": user_id},
                sort=[("expires_at", -1)]
            )
            
            # Inherit cumulative_wins from previous Bull Run (if any)
            inherited_cumulative = 0
            if previous_bull_run:
                inherited_cumulative = previous_bull_run.get("cumulative_wins", 0)
            
            # Determine starting rank from cumulative wins
            starting_rank = compute_rank_from_wins(inherited_cumulative)
            
            # Create new Bull Run
            expires_at = now + timedelta(days=7)
            bull_run_doc = {
                "user_id": user_id,
                "person_id": person_oid,
                "boost_id": active_golden["_id"],
                "started_at": now,
                "expires_at": expires_at,
                "current_rank": starting_rank,
                "wins_count": 0,
                "cumulative_wins": inherited_cumulative,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            
            result = await db.bull_runs.insert_one(bull_run_doc)
            bull_run_id = result.inserted_id
            
            # Check Legend status right away
            rank = starting_rank
            if await check_legend_status(person_oid):
                rank = "legend"
                await db.bull_runs.update_one(
                    {"_id": bull_run_id},
                    {"$set": {"current_rank": "legend"}}
                )
            
            return {
                "success": True,
                "action": "created",
                "bull_run_id": str(bull_run_id),
                "started_at": now.isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z",
                "current_rank": rank,
                "wins_count": 0,
                "cumulative_wins": inherited_cumulative,
                "message": "Bull Run activated! Start climbing the ladder.",
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bull Run activation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/bull-run/{user_id}")
async def get_bull_run_status(user_id: str):
    """Get the current Bull Run status for a user"""
    try:
        now = now_utc()
        
        # Find active Bull Run
        bull_run = await db.bull_runs.find_one({
            "user_id": user_id,
            "is_active": True,
            "expires_at": {"$gt": now},
        })
        
        if not bull_run:
            # Check if user ever had a Bull Run
            last_bull_run = await db.bull_runs.find_one(
                {"user_id": user_id},
                sort=[("expires_at", -1)]
            )
            
            return {
                "active": False,
                "has_history": last_bull_run is not None,
                "last_rank": last_bull_run.get("current_rank", "none") if last_bull_run else "none",
                "cumulative_wins": last_bull_run.get("cumulative_wins", 0) if last_bull_run else 0,
                "message": "No active Bull Run. Purchase a Golden Booster to start!",
            }
        
        # Get effective rank (includes Legend check)
        rank = await get_effective_rank(bull_run)
        
        # Calculate time remaining
        time_remaining = (bull_run["expires_at"] - now).total_seconds()
        days_remaining = int(time_remaining // 86400)
        hours_remaining = int((time_remaining % 86400) // 3600)
        
        # Get pending wins (not yet confirmed)
        pending_wins = await db.bull_run_wins.count_documents({
            "bull_run_id": bull_run["_id"],
            "confirmed": False,
        })
        
        # Get confirmed wins this period
        confirmed_wins = await db.bull_run_wins.find({
            "bull_run_id": bull_run["_id"],
            "confirmed": True,
        }).sort("confirmed_at", -1).to_list(length=50)
        
        beaten_celebrities = []
        for win in confirmed_wins:
            celebrity = await db.persons.find_one({"_id": win["celebrity_id"]})
            if celebrity:
                beaten_celebrities.append({
                    "id": str(celebrity["_id"]),
                    "name": celebrity.get("name", ""),
                    "category": celebrity.get("category", "other"),
                    "won_at": win.get("confirmed_at", win.get("won_at")).isoformat() + "Z",
                })
        
        return {
            "active": True,
            "bull_run_id": str(bull_run["_id"]),
            "person_id": str(bull_run["person_id"]),
            "started_at": bull_run["started_at"].isoformat() + "Z",
            "expires_at": bull_run["expires_at"].isoformat() + "Z",
            "time_remaining": {
                "days": days_remaining,
                "hours": hours_remaining,
                "total_seconds": int(time_remaining),
            },
            "current_rank": rank,
            "rank_display": RANK_DISPLAY.get(rank, RANK_DISPLAY["none"]),
            "wins_count": bull_run.get("wins_count", 0),
            "cumulative_wins": bull_run.get("cumulative_wins", 0),
            "pending_wins": pending_wins,
            "beaten_celebrities": beaten_celebrities,
            "next_rank": get_next_rank_info(bull_run.get("cumulative_wins", 0)),
        }
    
    except Exception as e:
        logger.error(f"Bull Run status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_next_rank_info(cumulative_wins: int) -> Optional[dict]:
    """Get info about the next rank to achieve"""
    for threshold, rank_id, display_name in RANK_THRESHOLDS:
        if cumulative_wins < threshold:
            continue
        # User has already reached this rank, skip
    
    # Find the next rank the user hasn't reached
    for threshold, rank_id, display_name in reversed(RANK_THRESHOLDS):
        if cumulative_wins < threshold:
            return {
                "rank": rank_id,
                "display": display_name,
                "wins_needed": threshold - cumulative_wins,
                "threshold": threshold,
            }
    
    # User has reached Icon — next is Legend (dynamic)
    return {
        "rank": "legend",
        "display": "🌟 Legend",
        "wins_needed": None,
        "threshold": None,
        "condition": "Reach top 10 in Popularoo global rankings",
    }


@bull_run_router.get("/bull-run/{user_id}/ladder")
async def get_bull_run_ladder(user_id: str):
    """Get the Bull Run ladder: 3 targets above + 3 beaten below"""
    try:
        now = now_utc()
        
        # Find active Bull Run
        bull_run = await db.bull_runs.find_one({
            "user_id": user_id,
            "is_active": True,
            "expires_at": {"$gt": now},
        })
        
        if not bull_run:
            raise HTTPException(status_code=404, detail="No active Bull Run found")
        
        ladder = await build_ladder(bull_run["person_id"], bull_run["_id"])
        
        return {
            "bull_run_id": str(bull_run["_id"]),
            "ladder": ladder,
            "current_rank": await get_effective_rank(bull_run),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bull Run ladder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Rally Cry Endpoints --------------------

@bull_run_router.post("/rally-cry/create")
async def create_rally_cry(request: RallyCryCreateRequest):
    """Create a new Rally Cry broadcast"""
    try:
        now = now_utc()
        user_id = request.user_id
        
        # Validate bull_run_id
        try:
            bull_run_oid = ObjectId(request.bull_run_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid bull_run_id")
        
        # Check Bull Run is active
        bull_run = await db.bull_runs.find_one({
            "_id": bull_run_oid,
            "user_id": user_id,
            "is_active": True,
            "expires_at": {"$gt": now},
        })
        
        if not bull_run:
            raise HTTPException(status_code=404, detail="No active Bull Run found")
        
        # Check not in final hour of Bull Run
        time_to_expiry = (bull_run["expires_at"] - now).total_seconds()
        if time_to_expiry < 3600:  # Less than 1 hour remaining
            raise HTTPException(
                status_code=400,
                detail="Rally Cry is disabled in the last hour of your Bull Run week."
            )
        
        # Check daily limit (max 3 per day)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await db.rally_cries.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": today_start},
        })
        
        if today_count >= RALLY_CRY_MAX_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {RALLY_CRY_MAX_PER_DAY} Rally Cries per day reached. Try again tomorrow!"
            )
        
        # Check cooldown (30 min since last Rally Cry)
        last_rally_cry = await db.rally_cries.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
        
        if last_rally_cry:
            time_since_last = (now - last_rally_cry["created_at"]).total_seconds()
            if time_since_last < RALLY_CRY_COOLDOWN_MINUTES * 60:
                remaining_mins = int((RALLY_CRY_COOLDOWN_MINUTES * 60 - time_since_last) / 60)
                raise HTTPException(
                    status_code=429,
                    detail=f"Cooldown active. Wait {remaining_mins} more minutes before your next Rally Cry."
                )
        
        # Validate target celebrity
        try:
            target_oid = ObjectId(request.target_celebrity_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid target_celebrity_id")
        
        target = await db.persons.find_one({"_id": target_oid})
        if not target:
            raise HTTPException(status_code=404, detail="Target celebrity not found")
        
        # Validate target is actually above the user
        user_person = await db.persons.find_one({"_id": bull_run["person_id"]})
        if not user_person:
            raise HTTPException(status_code=404, detail="User's profile not found")
        
        if target.get("raw_score", 0) <= user_person.get("raw_score", 0):
            raise HTTPException(
                status_code=400,
                detail="Target must have a higher score than you. You've already beaten this celebrity!"
            )
        
        # Validate message length
        message = (request.message or "").strip()
        if len(message) > 100:
            message = message[:100]
        
        # Create the Rally Cry
        expires_at = now + timedelta(hours=RALLY_CRY_DURATION_HOURS)
        rally_cry_doc = {
            "bull_run_id": bull_run_oid,
            "user_id": user_id,
            "person_id": bull_run["person_id"],  # The outsider
            "target_celebrity_id": target_oid,
            "message": message,
            "tone": request.tone,
            "created_at": now,
            "expires_at": expires_at,
            "votes_received": 0,
            "target_beaten": False,
            "external_share_count": 0,
        }
        
        result = await db.rally_cries.insert_one(rally_cry_doc)
        
        # Calculate votes needed
        score_gap = target.get("raw_score", 0) - user_person.get("raw_score", 0)
        
        return {
            "success": True,
            "rally_cry_id": str(result.inserted_id),
            "expires_at": expires_at.isoformat() + "Z",
            "duration_hours": RALLY_CRY_DURATION_HOURS,
            "target": {
                "id": str(target["_id"]),
                "name": target.get("name", ""),
                "raw_score": target.get("raw_score", 0),
            },
            "user_score": user_person.get("raw_score", 0),
            "score_gap": round(score_gap, 2),
            "remaining_today": RALLY_CRY_MAX_PER_DAY - today_count - 1,
            "message": f"Rally Cry launched! Community has {RALLY_CRY_DURATION_HOURS}h to help you beat {target.get('name', '')}!",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rally Cry creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/rally-cries/active")
async def get_active_rally_cries(limit: int = Query(default=10, le=20)):
    """Get active Rally Cries for the community to vote on"""
    try:
        now = now_utc()
        
        # Get active (non-expired) Rally Cries
        cursor = db.rally_cries.find({
            "expires_at": {"$gt": now},
            "target_beaten": False,
        }).sort("created_at", -1).limit(limit)
        
        rally_cries = await cursor.to_list(length=limit)
        
        results = []
        for rc in rally_cries:
            # Get the outsider (person requesting votes)
            person = await db.persons.find_one({"_id": rc["person_id"]})
            # Get the target celebrity
            target = await db.persons.find_one({"_id": rc["target_celebrity_id"]})
            
            if not person or not target:
                continue
            
            time_remaining = (rc["expires_at"] - now).total_seconds()
            minutes_remaining = int(time_remaining / 60)
            
            score_gap = target.get("raw_score", 0) - person.get("raw_score", 0)
            
            results.append({
                "id": str(rc["_id"]),
                "user_id": rc["user_id"],
                "person": {
                    "id": str(person["_id"]),
                    "name": person.get("name", ""),
                    "raw_score": person.get("raw_score", 0),
                    "score": person.get("score", 0),
                },
                "target": {
                    "id": str(target["_id"]),
                    "name": target.get("name", ""),
                    "raw_score": target.get("raw_score", 0),
                    "score": target.get("score", 0),
                },
                "message": rc.get("message", ""),
                "tone": rc.get("tone", "fierce"),
                "votes_received": rc.get("votes_received", 0),
                "score_gap": round(max(0, score_gap), 2),
                "minutes_remaining": minutes_remaining,
                "expires_at": rc["expires_at"].isoformat() + "Z",
                "created_at": rc["created_at"].isoformat() + "Z",
            })
        
        return {"rally_cries": results, "total": len(results)}
    
    except Exception as e:
        logger.error(f"Active Rally Cries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.post("/rally-cry/{rally_cry_id}/vote")
async def vote_rally_cry(
    rally_cry_id: str,
    body: RallyCryVoteRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """
    Vote for a Rally Cry (uses standard Popularoo vote mechanism).
    Respects 24h cooldown. Gracefully handles already-voted case.
    """
    try:
        if not x_device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header required")
        
        # Validate rally_cry_id
        try:
            rc_oid = ObjectId(rally_cry_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid rally_cry_id")
        
        now = now_utc()
        
        # Get the Rally Cry
        rally_cry = await db.rally_cries.find_one({"_id": rc_oid})
        if not rally_cry:
            raise HTTPException(status_code=404, detail="Rally Cry not found")
        
        # Check if Rally Cry is still active
        if rally_cry["expires_at"] < now:
            return {
                "success": False,
                "already_voted": False,
                "expired": True,
                "message": "This Rally Cry has expired.",
            }
        
        # Check if target already beaten
        if rally_cry.get("target_beaten"):
            return {
                "success": False,
                "already_voted": False,
                "target_beaten": True,
                "message": "Target already beaten! This Rally Cry is complete.",
            }
        
        # The person to vote for is the outsider (rally_cry.person_id)
        person_oid = rally_cry["person_id"]
        
        # Check existing vote (24h cooldown) — same logic as standard vote
        existing_vote = await db.votes.find_one({
            "person_id": person_oid,
            "device_id": x_device_id,
        })
        
        if existing_vote:
            last_vote_time = existing_vote.get("updated_at") or existing_vote.get("created_at")
            if last_vote_time:
                time_since = now - last_vote_time
                if time_since < timedelta(hours=24):
                    # Already voted within 24h — graceful response
                    person = await db.persons.find_one({"_id": person_oid})
                    person_name = person.get("name", "this person") if person else "this person"
                    
                    next_vote_time = (last_vote_time + timedelta(hours=24)).isoformat() + "Z"
                    hours_left = int((timedelta(hours=24) - time_since).total_seconds() / 3600)
                    
                    return {
                        "success": False,
                        "already_voted": True,
                        "message": f"✓ You already supported {person_name} today",
                        "next_vote_time": next_vote_time,
                        "hours_remaining": hours_left,
                    }
        
        # Execute the vote (standard Popularoo like)
        person = await db.persons.find_one({"_id": person_oid})
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        
        # Update vote record
        if existing_vote:
            # Update existing vote (24h has passed)
            await db.votes.update_one(
                {"_id": existing_vote["_id"]},
                {"$set": {"value": 1, "updated_at": now}}
            )
        else:
            # New vote
            await db.votes.insert_one({
                "person_id": person_oid,
                "device_id": x_device_id,
                "value": 1,
                "created_at": now,
                "updated_at": now,
            })
        
        # Update person's scores
        new_likes = person.get("likes", 0) + 1
        new_total = person.get("total_votes", 0) + 1
        new_raw_score = (new_likes / new_total * 100) if new_total > 0 else 0.0
        new_score = round(new_raw_score / 25) * 25
        new_score = max(0, min(100, new_score))
        
        await db.persons.update_one(
            {"_id": person_oid},
            {
                "$inc": {"likes": 1, "total_votes": 1},
                "$set": {
                    "raw_score": new_raw_score,
                    "score": new_score,
                    "updated_at": now,
                }
            }
        )
        
        # Record tick for charts
        await db.person_ticks.insert_one({
            "person_id": person_oid,
            "score": new_score,
            "total_votes": new_total,
            "created_at": now,
        })
        
        # Record vote event
        await db.vote_events.insert_one({
            "person_id": person_oid,
            "device_id": x_device_id,
            "delta": 1,
            "created_at": now,
            "source": "rally_cry",
            "rally_cry_id": rc_oid,
        })
        
        # Increment rally cry votes_received counter
        await db.rally_cries.update_one(
            {"_id": rc_oid},
            {"$inc": {"votes_received": 1}}
        )
        
        person_name = person.get("name", "")
        
        return {
            "success": True,
            "already_voted": False,
            "message": f"🎉 Vote counted for {person_name}!",
            "new_score": new_score,
            "new_raw_score": round(new_raw_score, 2),
            "votes_received": rally_cry.get("votes_received", 0) + 1,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rally Cry vote error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Notification Preferences --------------------

@bull_run_router.patch("/users/{user_id}/notification-preferences")
async def update_notification_preferences(user_id: str, request: NotificationPreferencesRequest):
    """Update user notification preferences (GDPR compliant opt-in)"""
    try:
        now = now_utc()
        
        update_fields = {"updated_at": now}
        
        if request.receive_rally_cries is not None:
            update_fields["receive_rally_cries"] = request.receive_rally_cries
        
        if request.bull_run_notifications is not None:
            update_fields["bull_run_notifications"] = request.bull_run_notifications
        
        if request.muted_rally_cry_users is not None:
            update_fields["muted_rally_cry_users"] = request.muted_rally_cry_users
        
        # Upsert user settings
        await db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": update_fields, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        
        # Fetch updated settings
        settings = await db.user_settings.find_one({"user_id": user_id})
        
        return {
            "success": True,
            "preferences": {
                "receive_rally_cries": settings.get("receive_rally_cries", False),
                "bull_run_notifications": settings.get("bull_run_notifications", True),
                "muted_rally_cry_users": settings.get("muted_rally_cry_users", []),
            }
        }
    
    except Exception as e:
        logger.error(f"Notification preferences error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/users/{user_id}/notification-preferences")
async def get_notification_preferences(user_id: str):
    """Get user notification preferences"""
    try:
        settings = await db.user_settings.find_one({"user_id": user_id})
        
        if not settings:
            return {
                "receive_rally_cries": False,
                "bull_run_notifications": True,
                "muted_rally_cry_users": [],
            }
        
        return {
            "receive_rally_cries": settings.get("receive_rally_cries", False),
            "bull_run_notifications": settings.get("bull_run_notifications", True),
            "muted_rally_cry_users": settings.get("muted_rally_cry_users", []),
        }
    
    except Exception as e:
        logger.error(f"Get notification preferences error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Background Job --------------------

async def bull_run_background_job(database):
    """
    Background job that runs every 5 minutes:
    1. Check pending wins (score maintained > 30 min)
    2. Recalculate Legend status for all active Bull Runs
    3. Detect new potential wins
    """
    try:
        now = now_utc()
        
        # ---- Step 1: Confirm pending wins ----
        pending_wins = await database.bull_run_wins.find({
            "confirmed": False,
            "won_at": {"$lte": now - timedelta(minutes=WIN_CONFIRMATION_MINUTES)},
        }).to_list(length=100)
        
        for win in pending_wins:
            # Re-check that the user's score is still above the celebrity's
            bull_run = await database.bull_runs.find_one({"_id": win["bull_run_id"]})
            if not bull_run or not bull_run.get("is_active"):
                # Bull Run expired, delete the pending win
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                continue
            
            user_person = await database.persons.find_one({"_id": bull_run["person_id"]})
            celebrity = await database.persons.find_one({"_id": win["celebrity_id"]})
            
            if not user_person or not celebrity:
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                continue
            
            user_raw = user_person.get("raw_score", 0)
            celeb_raw = celebrity.get("raw_score", 0)
            
            if user_raw > celeb_raw:
                # WIN CONFIRMED! Score maintained for 30+ minutes
                await database.bull_run_wins.update_one(
                    {"_id": win["_id"]},
                    {"$set": {"confirmed": True, "confirmed_at": now}}
                )
                
                # Update Bull Run counters
                await database.bull_runs.update_one(
                    {"_id": win["bull_run_id"]},
                    {
                        "$inc": {"wins_count": 1, "cumulative_wins": 1},
                        "$set": {"updated_at": now},
                    }
                )
                
                # Recalculate rank
                updated_br = await database.bull_runs.find_one({"_id": win["bull_run_id"]})
                if updated_br:
                    new_rank = compute_rank_from_wins(updated_br.get("cumulative_wins", 0))
                    await database.bull_runs.update_one(
                        {"_id": win["bull_run_id"]},
                        {"$set": {"current_rank": new_rank}}
                    )
                
                logger.info(f"🏆 Win confirmed: {user_person.get('name')} beat {celebrity.get('name')}")
            else:
                # Score dropped back below — cancel the pending win
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                logger.info(f"❌ Pending win cancelled: {user_person.get('name')} dropped below {celebrity.get('name')}")
        
        # ---- Step 2: Detect new potential wins ----
        active_bull_runs = await database.bull_runs.find({
            "is_active": True,
            "expires_at": {"$gt": now},
        }).to_list(length=100)
        
        for br in active_bull_runs:
            user_person = await database.persons.find_one({"_id": br["person_id"]})
            if not user_person:
                continue
            
            user_raw = user_person.get("raw_score", 0)
            
            # Find celebrities below the user that haven't been recorded as wins yet
            # Get all confirmed wins for this bull_run to know which celebs are already beaten
            existing_wins = await database.bull_run_wins.find({
                "bull_run_id": br["_id"],
            }).to_list(length=1000)
            
            beaten_ids = {w["celebrity_id"] for w in existing_wins}
            
            # Find celebrities whose raw_score is now below user's
            potential_beats = await database.persons.find({
                "raw_score": {"$lt": user_raw},
                "source": {"$ne": "self_boosted"},
                "approved": True,
                "_id": {"$nin": list(beaten_ids)},
            }).to_list(length=100)
            
            for celeb in potential_beats:
                # Create a pending win record
                await database.bull_run_wins.insert_one({
                    "bull_run_id": br["_id"],
                    "user_id": br["user_id"],
                    "celebrity_id": celeb["_id"],
                    "won_at": now,
                    "user_score_at_win": user_raw,
                    "celebrity_score_at_win": celeb.get("raw_score", 0),
                    "confirmed": False,
                })
                logger.info(f"📈 Potential win detected: {user_person.get('name')} vs {celeb.get('name')}")
        
        # ---- Step 3: Recalculate Legend status ----
        for br in active_bull_runs:
            person_id = br["person_id"]
            person = await database.persons.find_one({"_id": person_id})
            if not person:
                continue
            
            person_raw_score = person.get("raw_score", 0)
            higher_count = await database.persons.count_documents({
                "raw_score": {"$gt": person_raw_score},
                "approved": True,
            })
            
            is_legend = higher_count < 10
            current_rank = br.get("current_rank", "none")
            
            if is_legend and current_rank != "legend":
                # Promote to Legend
                await database.bull_runs.update_one(
                    {"_id": br["_id"]},
                    {"$set": {"current_rank": "legend", "updated_at": now}}
                )
                logger.info(f"🌟 Legend status granted: {person.get('name')}")
            elif not is_legend and current_rank == "legend":
                # Demote from Legend back to wins-based rank
                wins_rank = compute_rank_from_wins(br.get("cumulative_wins", 0))
                await database.bull_runs.update_one(
                    {"_id": br["_id"]},
                    {"$set": {"current_rank": wins_rank, "updated_at": now}}
                )
                logger.info(f"📉 Legend status removed: {person.get('name')} → {wins_rank}")
        
        # ---- Step 4: Expire old Bull Runs ----
        expired = await database.bull_runs.update_many(
            {"is_active": True, "expires_at": {"$lte": now}},
            {"$set": {"is_active": False, "updated_at": now}}
        )
        if expired.modified_count > 0:
            logger.info(f"⏰ {expired.modified_count} Bull Run(s) expired")
        
        # ---- Step 5: Mark Rally Cries as beaten if target beaten ----
        active_cries = await database.rally_cries.find({
            "expires_at": {"$gt": now},
            "target_beaten": False,
        }).to_list(length=100)
        
        for cry in active_cries:
            person = await database.persons.find_one({"_id": cry["person_id"]})
            target = await database.persons.find_one({"_id": cry["target_celebrity_id"]})
            
            if person and target:
                if person.get("raw_score", 0) > target.get("raw_score", 0):
                    await database.rally_cries.update_one(
                        {"_id": cry["_id"]},
                        {"$set": {"target_beaten": True}}
                    )
                    logger.info(f"🎯 Rally Cry target beaten: {person.get('name')} beat {target.get('name')}")
        
    except Exception as e:
        logger.error(f"❌ Bull Run background job error: {e}")
