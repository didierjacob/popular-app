"""
Bull Run & Rally Cry Module for Popularoo — Momentum Edition
=============================================================
Premium features exclusive to Golden Booster users.
- Bull Run: 7-day momentum-based competitive game (net votes gained)
- Rally Cry: Social broadcast to get community votes
- Victory = user_momentum_net > 0 AND > celebrity_momentum_net for 30 min
"""

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timedelta
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

bull_run_router = APIRouter(prefix="/api")
db = None


def init_bull_run(database):
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
    person_id: str


class RallyCryCreateRequest(BaseModel):
    user_id: str
    bull_run_id: str
    target_celebrity_id: str
    message: Optional[str] = ""
    tone: Literal["fierce", "playful", "sincere", "custom"] = "fierce"


class RallyCryVoteRequest(BaseModel):
    value: Literal[1] = 1


class NotificationPreferencesRequest(BaseModel):
    receive_rally_cries: Optional[bool] = None
    bull_run_notifications: Optional[bool] = None
    muted_rally_cry_users: Optional[List[str]] = None


def verify_device_ownership(device_id, user_id):
    return device_id == user_id


# -------------------- Helpers --------------------

def now_utc():
    return datetime.utcnow()


def compute_rank_from_wins(cumulative_wins):
    for threshold, rank_id, _ in RANK_THRESHOLDS:
        if cumulative_wins >= threshold:
            return rank_id
    return "none"


def get_next_rank_info(cumulative_wins):
    for threshold, rank_id, display_name in reversed(RANK_THRESHOLDS):
        if cumulative_wins < threshold:
            return {
                "rank": rank_id,
                "display": display_name,
                "wins_needed": threshold - cumulative_wins,
                "threshold": threshold,
            }
    return {
        "rank": "legend",
        "display": "🌟 Legend",
        "wins_needed": None,
        "condition": "Reach top 10 weekly momentum",
    }


def calc_momentum(person_now, snapshot_at_t0):
    """
    Calculate momentum_net for a person.
    momentum_net = (likes_now - likes_at_t0) - (dislikes_now - dislikes_at_t0)
    """
    likes_now = person_now.get("likes", 0)
    dislikes_now = person_now.get("dislikes", 0)
    likes_t0 = snapshot_at_t0.get("likes", 0)
    dislikes_t0 = snapshot_at_t0.get("dislikes", 0)

    momentum_likes = likes_now - likes_t0
    momentum_dislikes = dislikes_now - dislikes_t0
    momentum_net = momentum_likes - momentum_dislikes

    return {
        "momentum_likes": momentum_likes,
        "momentum_dislikes": momentum_dislikes,
        "momentum_net": momentum_net,
    }


async def take_full_snapshot():
    """Snapshot likes/dislikes for ALL approved persons at activation time."""
    snapshot = {}
    cursor = db.persons.find({"approved": True}, {"likes": 1, "dislikes": 1})
    async for p in cursor:
        snapshot[str(p["_id"])] = {
            "likes": p.get("likes", 0),
            "dislikes": p.get("dislikes", 0),
        }
    return snapshot


async def get_person_momentum(person_id_str, snapshot_at_t0):
    """Get the momentum for a specific person using the Bull Run snapshot."""
    person = await db.persons.find_one({"_id": ObjectId(person_id_str)})
    if not person:
        return None, None

    t0 = snapshot_at_t0.get(person_id_str, {"likes": 0, "dislikes": 0})
    mom = calc_momentum(person, t0)
    return person, mom


async def check_legend_status_momentum(person_id_str, bull_run_started_at):
    """
    Check if a person is in the top 10 by weekly momentum_net.
    Uses a 7-day rolling window from now.
    """
    now = now_utc()
    window_start = now - timedelta(days=7)

    # We need a "global" snapshot for the 7-day window.
    # For simplicity, we approximate: get all vote_events in the last 7 days
    # and sum the delta per person.
    pipeline = [
        {"$match": {"created_at": {"$gte": window_start}}},
        {"$group": {
            "_id": "$person_id",
            "net_delta": {"$sum": "$delta"},
        }},
        {"$sort": {"net_delta": -1}},
        {"$limit": 10},
    ]

    top_10_ids = []
    async for doc in db.vote_events.aggregate(pipeline):
        if doc["net_delta"] > 0:
            top_10_ids.append(str(doc["_id"]))

    return person_id_str in [str(pid) for pid in top_10_ids]


async def build_ladder(person_id_str, bull_run):
    """
    Build the momentum-based ladder:
    - 3 closest persons ABOVE by momentum_net (targets)
    - 3 most recently out-rallied BELOW (confirmed wins)
    """
    snapshot = bull_run.get("snapshot_at_t0", {})

    # User momentum
    user_person, user_mom = await get_person_momentum(person_id_str, snapshot)
    if not user_person:
        return {"above": [], "below": [], "user": None}

    user_momentum_net = user_mom["momentum_net"]

    # Get ALL approved non-outsider persons' momentum
    candidates = []
    cursor = db.persons.find({"source": {"$ne": "self_boosted"}, "approved": True})
    async for p in cursor:
        pid = str(p["_id"])
        t0 = snapshot.get(pid, {"likes": 0, "dislikes": 0})
        mom = calc_momentum(p, t0)
        candidates.append({
            "id": pid,
            "name": p.get("name", ""),
            "category": p.get("category", "other"),
            "total_votes": p.get("total_votes", 0),
            "momentum_net": mom["momentum_net"],
            "momentum_likes": mom["momentum_likes"],
        })

    # Targets above: momentum_net > user's, sorted closest first
    above_all = [c for c in candidates if c["momentum_net"] > user_momentum_net]
    above_all.sort(key=lambda x: x["momentum_net"])
    above = above_all[:3]

    for a in above:
        a["gap"] = a["momentum_net"] - user_momentum_net
        a["status"] = "target"

    # Beaten below: confirmed wins, most recent first
    recent_wins_cursor = db.bull_run_wins.find({
        "bull_run_id": bull_run["_id"],
        "confirmed": True,
    }).sort("confirmed_at", -1).limit(3)

    below = []
    async for win in recent_wins_cursor:
        celeb = await db.persons.find_one({"_id": win["celebrity_id"]})
        if celeb:
            cid = str(celeb["_id"])
            t0 = snapshot.get(cid, {"likes": 0, "dislikes": 0})
            mom = calc_momentum(celeb, t0)
            below.append({
                "id": cid,
                "name": celeb.get("name", ""),
                "category": celeb.get("category", "other"),
                "total_votes": celeb.get("total_votes", 0),
                "momentum_net": mom["momentum_net"],
                "gap": user_momentum_net - mom["momentum_net"],
                "status": "out-rallied",
                "won_at": (win.get("confirmed_at") or win.get("won_at", "")).isoformat() + "Z" if win.get("confirmed_at") or win.get("won_at") else None,
            })

    user_data = {
        "id": str(user_person["_id"]),
        "name": user_person.get("name", ""),
        "total_votes": user_person.get("total_votes", 0),
        "momentum_net": user_momentum_net,
        "momentum_likes": user_mom["momentum_likes"],
    }

    return {"above": above, "below": below, "user": user_data}


# -------------------- Endpoints --------------------

@bull_run_router.post("/bull-run/activate")
async def activate_bull_run(
    request: BullRunActivateRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """Activate or extend a Bull Run. Takes a full snapshot at T0."""
    try:
        if not x_device_id:
            raise HTTPException(status_code=401, detail="X-Device-ID header required")
        if not verify_device_ownership(x_device_id, request.user_id):
            raise HTTPException(status_code=403, detail="Unauthorized: device does not match user")

        user_id = request.user_id
        try:
            person_oid = ObjectId(request.person_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid person_id")

        person = await db.persons.find_one({"_id": person_oid})
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        if person.get("source") != "self_boosted":
            raise HTTPException(status_code=400, detail="Bull Run is only for outsiders")

        now = now_utc()

        active_golden = await db.active_boosts.find_one({
            "user_id": user_id, "person_id": person_oid,
            "tier": "golden_booster", "end_time": {"$gt": now},
        })
        if not active_golden:
            raise HTTPException(status_code=403, detail="Active Golden Booster required")

        # Check existing active Bull Run
        existing = await db.bull_runs.find_one({
            "user_id": user_id, "is_active": True, "expires_at": {"$gt": now},
        })

        if existing:
            # Case A: Renewal — extend, keep snapshot, keep wins
            new_expires = existing["expires_at"] + timedelta(days=7)
            await db.bull_runs.update_one(
                {"_id": existing["_id"]},
                {"$set": {"expires_at": new_expires, "updated_at": now}}
            )
            return {
                "success": True, "action": "extended",
                "bull_run_id": str(existing["_id"]),
                "expires_at": new_expires.isoformat() + "Z",
                "wins_count": existing.get("wins_count", 0),
                "cumulative_wins": existing.get("cumulative_wins", 0),
                "message": "Bull Run extended! Your momentum continues.",
            }
        else:
            # Case B: New (or gap re-activation)
            previous = await db.bull_runs.find_one(
                {"user_id": user_id}, sort=[("expires_at", -1)]
            )
            inherited_cumulative = previous.get("cumulative_wins", 0) if previous else 0

            # Take full snapshot of all persons' likes/dislikes at T0
            snapshot = await take_full_snapshot()

            bull_run_doc = {
                "user_id": user_id,
                "person_id": person_oid,
                "boost_id": active_golden["_id"],
                "started_at": now,
                "expires_at": now + timedelta(days=7),
                "current_rank": compute_rank_from_wins(inherited_cumulative),
                "wins_count": 0,
                "cumulative_wins": inherited_cumulative,
                "snapshot_at_t0": snapshot,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }

            result = await db.bull_runs.insert_one(bull_run_doc)

            return {
                "success": True, "action": "created",
                "bull_run_id": str(result.inserted_id),
                "started_at": now.isoformat() + "Z",
                "expires_at": (now + timedelta(days=7)).isoformat() + "Z",
                "current_rank": bull_run_doc["current_rank"],
                "wins_count": 0,
                "cumulative_wins": inherited_cumulative,
                "message": "Bull Run activated! Start building momentum.",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bull Run activation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/bull-run/{user_id}")
async def get_bull_run_status(user_id: str):
    """Get current Bull Run status with momentum data."""
    try:
        now = now_utc()

        bull_run = await db.bull_runs.find_one({
            "user_id": user_id, "is_active": True, "expires_at": {"$gt": now},
        })

        if not bull_run:
            last = await db.bull_runs.find_one(
                {"user_id": user_id}, sort=[("expires_at", -1)]
            )
            return {
                "active": False,
                "has_history": last is not None,
                "last_rank": last.get("current_rank", "none") if last else "none",
                "cumulative_wins": last.get("cumulative_wins", 0) if last else 0,
            }

        person_id_str = str(bull_run["person_id"])
        snapshot = bull_run.get("snapshot_at_t0", {})
        user_person, user_mom = await get_person_momentum(person_id_str, snapshot)

        time_remaining = (bull_run["expires_at"] - now).total_seconds()
        rank = bull_run.get("current_rank", "none")

        pending_wins = await db.bull_run_wins.count_documents({
            "bull_run_id": bull_run["_id"], "confirmed": False,
        })

        confirmed_wins = await db.bull_run_wins.find({
            "bull_run_id": bull_run["_id"], "confirmed": True,
        }).sort("confirmed_at", -1).to_list(length=50)

        out_rallied = []
        for win in confirmed_wins:
            celeb = await db.persons.find_one({"_id": win["celebrity_id"]})
            if celeb:
                out_rallied.append({
                    "id": str(celeb["_id"]),
                    "name": celeb.get("name", ""),
                    "category": celeb.get("category", "other"),
                    "won_at": (win.get("confirmed_at") or win.get("won_at")).isoformat() + "Z",
                })

        return {
            "active": True,
            "bull_run_id": str(bull_run["_id"]),
            "person_id": person_id_str,
            "started_at": bull_run["started_at"].isoformat() + "Z",
            "expires_at": bull_run["expires_at"].isoformat() + "Z",
            "time_remaining": {
                "days": int(time_remaining // 86400),
                "hours": int((time_remaining % 86400) // 3600),
                "total_seconds": int(time_remaining),
            },
            "current_rank": rank,
            "rank_display": RANK_DISPLAY.get(rank, RANK_DISPLAY["none"]),
            "wins_count": bull_run.get("wins_count", 0),
            "cumulative_wins": bull_run.get("cumulative_wins", 0),
            "pending_wins": pending_wins,
            "out_rallied_celebrities": out_rallied,
            "momentum": user_mom if user_mom else {"momentum_net": 0, "momentum_likes": 0, "momentum_dislikes": 0},
            "next_rank": get_next_rank_info(bull_run.get("cumulative_wins", 0)),
        }

    except Exception as e:
        logger.error(f"Bull Run status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/bull-run/{user_id}/ladder")
async def get_bull_run_ladder(user_id: str):
    """Get the momentum-based ladder."""
    try:
        now = now_utc()
        bull_run = await db.bull_runs.find_one({
            "user_id": user_id, "is_active": True, "expires_at": {"$gt": now},
        })
        if not bull_run:
            raise HTTPException(status_code=404, detail="No active Bull Run")

        ladder = await build_ladder(str(bull_run["person_id"]), bull_run)

        return {
            "bull_run_id": str(bull_run["_id"]),
            "ladder": ladder,
            "current_rank": bull_run.get("current_rank", "none"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ladder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Rally Cry --------------------

@bull_run_router.post("/rally-cry/create")
async def create_rally_cry(
    request: RallyCryCreateRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """Create a Rally Cry broadcast."""
    try:
        now = now_utc()
        user_id = request.user_id

        if not x_device_id:
            raise HTTPException(status_code=401, detail="X-Device-ID header required")
        if not verify_device_ownership(x_device_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized")

        try:
            bull_run_oid = ObjectId(request.bull_run_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid bull_run_id")

        bull_run = await db.bull_runs.find_one({
            "_id": bull_run_oid, "user_id": user_id,
            "is_active": True, "expires_at": {"$gt": now},
        })
        if not bull_run:
            raise HTTPException(status_code=404, detail="No active Bull Run")

        # Disabled in final hour
        if (bull_run["expires_at"] - now).total_seconds() < 3600:
            raise HTTPException(status_code=400, detail="Rally Cry disabled in the last hour")

        # Daily limit
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await db.rally_cries.count_documents({
            "user_id": user_id, "created_at": {"$gte": today_start},
        })
        if today_count >= RALLY_CRY_MAX_PER_DAY:
            raise HTTPException(status_code=429, detail=f"Max {RALLY_CRY_MAX_PER_DAY} Rally Cries/day")

        # Cooldown
        last_cry = await db.rally_cries.find_one(
            {"user_id": user_id}, sort=[("created_at", -1)]
        )
        if last_cry:
            secs_since = (now - last_cry["created_at"]).total_seconds()
            if secs_since < RALLY_CRY_COOLDOWN_MINUTES * 60:
                remaining = int((RALLY_CRY_COOLDOWN_MINUTES * 60 - secs_since) / 60)
                raise HTTPException(status_code=429, detail=f"Wait {remaining} more minutes")

        try:
            target_oid = ObjectId(request.target_celebrity_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid target_celebrity_id")

        target = await db.persons.find_one({"_id": target_oid})
        if not target:
            raise HTTPException(status_code=404, detail="Target not found")

        # Validate target is actually above user in momentum
        snapshot = bull_run.get("snapshot_at_t0", {})
        user_person, user_mom = await get_person_momentum(str(bull_run["person_id"]), snapshot)
        target_t0 = snapshot.get(str(target_oid), {"likes": 0, "dislikes": 0})
        target_mom = calc_momentum(target, target_t0)

        if target_mom["momentum_net"] <= user_mom["momentum_net"]:
            raise HTTPException(status_code=400, detail="Target must have higher momentum than you")

        message = (request.message or "").strip()[:100]
        expires_at = now + timedelta(hours=RALLY_CRY_DURATION_HOURS)

        result = await db.rally_cries.insert_one({
            "bull_run_id": bull_run_oid,
            "user_id": user_id,
            "person_id": bull_run["person_id"],
            "target_celebrity_id": target_oid,
            "message": message,
            "tone": request.tone,
            "created_at": now,
            "expires_at": expires_at,
            "votes_received": 0,
            "target_out_rallied": False,
            "external_share_count": 0,
        })

        momentum_gap = target_mom["momentum_net"] - user_mom["momentum_net"]

        return {
            "success": True,
            "rally_cry_id": str(result.inserted_id),
            "expires_at": expires_at.isoformat() + "Z",
            "target": {"id": str(target_oid), "name": target.get("name", ""), "momentum_net": target_mom["momentum_net"]},
            "user_momentum": user_mom["momentum_net"],
            "momentum_gap": momentum_gap,
            "remaining_today": RALLY_CRY_MAX_PER_DAY - today_count - 1,
            "message": f"Rally Cry launched! {RALLY_CRY_DURATION_HOURS}h to out-rally {target.get('name', '')}!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rally Cry create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/rally-cries/active")
async def get_active_rally_cries(limit: int = Query(default=10, le=20)):
    """Get active Rally Cries for community voting."""
    try:
        now = now_utc()
        cursor = db.rally_cries.find({
            "expires_at": {"$gt": now}, "target_out_rallied": False,
        }).sort("created_at", -1).limit(limit)

        results = []
        async for rc in cursor:
            person = await db.persons.find_one({"_id": rc["person_id"]})
            target = await db.persons.find_one({"_id": rc["target_celebrity_id"]})
            if not person or not target:
                continue

            mins_left = int((rc["expires_at"] - now).total_seconds() / 60)

            results.append({
                "id": str(rc["_id"]),
                "user_id": rc["user_id"],
                "person": {"id": str(person["_id"]), "name": person.get("name", "")},
                "target": {"id": str(target["_id"]), "name": target.get("name", "")},
                "message": rc.get("message", ""),
                "tone": rc.get("tone", "fierce"),
                "votes_received": rc.get("votes_received", 0),
                "minutes_remaining": mins_left,
                "expires_at": rc["expires_at"].isoformat() + "Z",
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
    """Vote on a Rally Cry. Standard 24h cooldown. Graceful already-voted handling."""
    try:
        if not x_device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID header required")

        try:
            rc_oid = ObjectId(rally_cry_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid rally_cry_id")

        now = now_utc()
        rally_cry = await db.rally_cries.find_one({"_id": rc_oid})
        if not rally_cry:
            raise HTTPException(status_code=404, detail="Rally Cry not found")

        if rally_cry["expires_at"] < now:
            return {"success": False, "expired": True, "message": "This Rally Cry has expired."}

        if rally_cry.get("target_out_rallied"):
            return {"success": False, "target_out_rallied": True, "message": "Target already out-rallied!"}

        person_oid = rally_cry["person_id"]

        # 24h cooldown check
        existing_vote = await db.votes.find_one({
            "person_id": person_oid, "device_id": x_device_id,
        })

        if existing_vote:
            last_vote_time = existing_vote.get("updated_at") or existing_vote.get("created_at")
            if last_vote_time and (now - last_vote_time) < timedelta(hours=24):
                person = await db.persons.find_one({"_id": person_oid})
                name = person.get("name", "this person") if person else "this person"
                hours_left = int((timedelta(hours=24) - (now - last_vote_time)).total_seconds() / 3600)
                return {
                    "success": False, "already_voted": True,
                    "message": f"✓ You already supported {name} today",
                    "hours_remaining": hours_left,
                }

        # Execute the vote (standard Popularoo like)
        person = await db.persons.find_one({"_id": person_oid})
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        if existing_vote:
            await db.votes.update_one(
                {"_id": existing_vote["_id"]},
                {"$set": {"value": 1, "updated_at": now}}
            )
        else:
            await db.votes.insert_one({
                "person_id": person_oid, "device_id": x_device_id,
                "value": 1, "created_at": now, "updated_at": now,
            })

        new_likes = person.get("likes", 0) + 1
        new_total = person.get("total_votes", 0) + 1
        new_raw_score = (new_likes / new_total * 100) if new_total > 0 else 0.0
        new_score = round(new_raw_score / 25) * 25
        new_score = max(0, min(100, new_score))

        await db.persons.update_one(
            {"_id": person_oid},
            {"$inc": {"likes": 1, "total_votes": 1},
             "$set": {"raw_score": new_raw_score, "score": new_score, "updated_at": now}}
        )

        await db.person_ticks.insert_one({
            "person_id": person_oid, "score": new_score,
            "total_votes": new_total, "likes": new_likes,
            "dislikes": person.get("dislikes", 0),
            "created_at": now,
        })

        await db.vote_events.insert_one({
            "person_id": person_oid, "device_id": x_device_id,
            "delta": 1, "created_at": now,
            "source": "rally_cry", "rally_cry_id": rc_oid,
        })

        await db.rally_cries.update_one({"_id": rc_oid}, {"$inc": {"votes_received": 1}})

        return {
            "success": True, "already_voted": False,
            "message": f"🎉 Vote counted for {person.get('name', '')}!",
            "new_score": new_score,
            "votes_received": rally_cry.get("votes_received", 0) + 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rally Cry vote error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Notification Preferences --------------------

@bull_run_router.patch("/users/{user_id}/notification-preferences")
async def update_notification_preferences(
    user_id: str,
    request: NotificationPreferencesRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    try:
        if not x_device_id:
            raise HTTPException(status_code=401, detail="X-Device-ID header required")
        if not verify_device_ownership(x_device_id, user_id):
            raise HTTPException(status_code=403, detail="Unauthorized")

        now = now_utc()
        update_fields = {"updated_at": now}

        if request.receive_rally_cries is not None:
            update_fields["receive_rally_cries"] = request.receive_rally_cries
        if request.bull_run_notifications is not None:
            update_fields["bull_run_notifications"] = request.bull_run_notifications
        if request.muted_rally_cry_users is not None:
            update_fields["muted_rally_cry_users"] = request.muted_rally_cry_users

        await db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": update_fields, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        settings = await db.user_settings.find_one({"user_id": user_id})
        return {
            "success": True,
            "preferences": {
                "receive_rally_cries": settings.get("receive_rally_cries", False),
                "bull_run_notifications": settings.get("bull_run_notifications", True),
                "muted_rally_cry_users": settings.get("muted_rally_cry_users", []),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notification prefs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@bull_run_router.get("/users/{user_id}/notification-preferences")
async def get_notification_preferences(user_id: str):
    try:
        settings = await db.user_settings.find_one({"user_id": user_id})
        if not settings:
            return {"receive_rally_cries": False, "bull_run_notifications": True, "muted_rally_cry_users": []}
        return {
            "receive_rally_cries": settings.get("receive_rally_cries", False),
            "bull_run_notifications": settings.get("bull_run_notifications", True),
            "muted_rally_cry_users": settings.get("muted_rally_cry_users", []),
        }
    except Exception as e:
        logger.error(f"Get prefs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- Background Job --------------------

async def bull_run_background_job(database):
    """
    Every 5 minutes:
    1. Detect new potential wins (user_momentum_net > 0 AND > celebrity)
    2. Confirm wins held for 30+ min
    3. Recalculate Legend status (top 10 weekly momentum)
    4. Expire old Bull Runs
    5. Mark Rally Cries as out-rallied
    """
    try:
        now = now_utc()

        # ---- 1. Confirm pending wins ----
        pending = await database.bull_run_wins.find({
            "confirmed": False,
            "won_at": {"$lte": now - timedelta(minutes=WIN_CONFIRMATION_MINUTES)},
        }).to_list(length=100)

        for win in pending:
            br = await database.bull_runs.find_one({"_id": win["bull_run_id"]})
            if not br or not br.get("is_active"):
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                continue

            snapshot = br.get("snapshot_at_t0", {})
            person_id_str = str(br["person_id"])
            celeb_id_str = str(win["celebrity_id"])

            user_person, user_mom = await _get_momentum(database, person_id_str, snapshot)
            celeb_person, celeb_mom = await _get_momentum(database, celeb_id_str, snapshot)

            if not user_person or not celeb_person:
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                continue

            # Victory condition: user_momentum_net > 0 AND > celebrity_momentum_net
            if user_mom["momentum_net"] > 0 and user_mom["momentum_net"] > celeb_mom["momentum_net"]:
                await database.bull_run_wins.update_one(
                    {"_id": win["_id"]},
                    {"$set": {"confirmed": True, "confirmed_at": now}}
                )
                await database.bull_runs.update_one(
                    {"_id": win["bull_run_id"]},
                    {"$inc": {"wins_count": 1, "cumulative_wins": 1}, "$set": {"updated_at": now}}
                )
                updated_br = await database.bull_runs.find_one({"_id": win["bull_run_id"]})
                if updated_br:
                    new_rank = compute_rank_from_wins(updated_br.get("cumulative_wins", 0))
                    await database.bull_runs.update_one(
                        {"_id": win["bull_run_id"]},
                        {"$set": {"current_rank": new_rank}}
                    )
                logger.info(f"🏆 Win confirmed: {user_person.get('name')} out-rallied {celeb_person.get('name')}")
            else:
                await database.bull_run_wins.delete_one({"_id": win["_id"]})
                logger.info(f"❌ Pending win cancelled: momentum dropped")

        # ---- 2. Detect new potential wins ----
        active_brs = await database.bull_runs.find({
            "is_active": True, "expires_at": {"$gt": now},
        }).to_list(length=100)

        for br in active_brs:
            snapshot = br.get("snapshot_at_t0", {})
            person_id_str = str(br["person_id"])
            user_person, user_mom = await _get_momentum(database, person_id_str, snapshot)
            if not user_person or user_mom["momentum_net"] <= 0:
                continue  # No wins possible if momentum <= 0

            existing_win_celeb_ids = set()
            async for w in database.bull_run_wins.find({"bull_run_id": br["_id"]}):
                existing_win_celeb_ids.add(str(w["celebrity_id"]))

            # Check all non-outsider persons
            async for celeb in database.persons.find({"source": {"$ne": "self_boosted"}, "approved": True}):
                cid = str(celeb["_id"])
                if cid in existing_win_celeb_ids:
                    continue

                t0 = snapshot.get(cid, {"likes": 0, "dislikes": 0})
                celeb_mom = calc_momentum(celeb, t0)

                if user_mom["momentum_net"] > celeb_mom["momentum_net"]:
                    await database.bull_run_wins.insert_one({
                        "bull_run_id": br["_id"],
                        "user_id": br["user_id"],
                        "celebrity_id": celeb["_id"],
                        "won_at": now,
                        "user_momentum_at_win": user_mom["momentum_net"],
                        "celebrity_momentum_at_win": celeb_mom["momentum_net"],
                        "confirmed": False,
                    })
                    logger.info(f"📈 Potential win: {user_person.get('name')} vs {celeb.get('name')} ({user_mom['momentum_net']} vs {celeb_mom['momentum_net']})")

        # ---- 3. Legend recalculation (top 10 weekly momentum via vote_events) ----
        window_start = now - timedelta(days=7)
        pipeline = [
            {"$match": {"created_at": {"$gte": window_start}}},
            {"$group": {"_id": "$person_id", "net_delta": {"$sum": "$delta"}}},
            {"$match": {"net_delta": {"$gt": 0}}},
            {"$sort": {"net_delta": -1}},
            {"$limit": 10},
        ]
        top_10_person_ids = set()
        async for doc in database.vote_events.aggregate(pipeline):
            top_10_person_ids.add(doc["_id"])

        for br in active_brs:
            person_oid = br["person_id"]
            is_legend = person_oid in top_10_person_ids
            current_rank = br.get("current_rank", "none")

            if is_legend and current_rank != "legend":
                await database.bull_runs.update_one(
                    {"_id": br["_id"]},
                    {"$set": {"current_rank": "legend", "updated_at": now}}
                )
                p = await database.persons.find_one({"_id": person_oid})
                logger.info(f"🌟 Legend: {p.get('name') if p else '?'}")
            elif not is_legend and current_rank == "legend":
                wins_rank = compute_rank_from_wins(br.get("cumulative_wins", 0))
                await database.bull_runs.update_one(
                    {"_id": br["_id"]},
                    {"$set": {"current_rank": wins_rank, "updated_at": now}}
                )
                p = await database.persons.find_one({"_id": person_oid})
                logger.info(f"📉 Lost Legend: {p.get('name') if p else '?'} → {wins_rank}")

        # ---- 4. Expire old Bull Runs ----
        expired = await database.bull_runs.update_many(
            {"is_active": True, "expires_at": {"$lte": now}},
            {"$set": {"is_active": False, "updated_at": now}}
        )
        if expired.modified_count > 0:
            logger.info(f"⏰ {expired.modified_count} Bull Run(s) expired")

        # ---- 5. Mark Rally Cries as out-rallied ----
        active_cries = await database.rally_cries.find({
            "expires_at": {"$gt": now}, "target_out_rallied": False,
        }).to_list(length=100)

        for cry in active_cries:
            # Find the bull_run to get the snapshot
            br = await database.bull_runs.find_one({"_id": cry["bull_run_id"]})
            if not br:
                continue

            snapshot = br.get("snapshot_at_t0", {})
            person_id_str = str(cry["person_id"])
            target_id_str = str(cry["target_celebrity_id"])

            _, user_mom = await _get_momentum(database, person_id_str, snapshot)
            target = await database.persons.find_one({"_id": cry["target_celebrity_id"]})
            if not target or not user_mom:
                continue

            t0 = snapshot.get(target_id_str, {"likes": 0, "dislikes": 0})
            target_mom = calc_momentum(target, t0)

            if user_mom["momentum_net"] > 0 and user_mom["momentum_net"] > target_mom["momentum_net"]:
                await database.rally_cries.update_one(
                    {"_id": cry["_id"]},
                    {"$set": {"target_out_rallied": True}}
                )
                logger.info(f"🎯 Rally Cry target out-rallied!")

    except Exception as e:
        logger.error(f"❌ Bull Run background job error: {e}")


async def _get_momentum(database, person_id_str, snapshot):
    """Helper for background job (uses database param instead of global db)."""
    try:
        person = await database.persons.find_one({"_id": ObjectId(person_id_str)})
    except Exception:
        return None, None
    if not person:
        return None, None
    t0 = snapshot.get(person_id_str, {"likes": 0, "dislikes": 0})
    mom = calc_momentum(person, t0)
    return person, mom
