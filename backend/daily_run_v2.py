"""
Daily Run V2 — 24h rolling challenge replacing Bull Run.

An outsider picks a target (celebrity or other outsider) and tries to 
beat them within 24 hours. Victory conditions depend on the Index gap.

Tiers:
  < 20 points gap  → Standard Win (surpass target's 24h momentum for 30 consecutive min)
  20-50 points gap  → Underdog Win (reach 50% of target's 24h momentum)
  > 50 points gap   → Legendary Strike (trigger 3+ strikes during the 24h)

Booster integration:
  Booster (€0.99):       0 daily runs (just 1h of visibility)
  Super Booster (€9.99): 1 daily run during 24h visibility
  Golden Booster (€49.99): 7 daily runs (max 1 per 24h rolling, lost if unused)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from bson import ObjectId

logger = logging.getLogger("daily_run")

TIER_STANDARD = "standard"
TIER_UNDERDOG = "underdog"
TIER_LEGENDARY = "legendary"

STATUS_ACTIVE = "active"
STATUS_WON = "won"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"

DAILY_RUN_DURATION_HOURS = 24
STANDARD_WIN_MINUTES = 30  # Must maintain momentum for 30 consecutive min

# Booster tier → allowed daily runs
BOOSTER_DAILY_RUNS = {
    "booster": 0,
    "super_booster": 1,
    "golden_booster": 7,
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def determine_tier(outsider_index: float, target_index: float) -> Tuple[str, str, str]:
    """
    Determine victory tier based on Index gap.
    Returns: (tier, victory_condition_text, reward_text)
    """
    gap = abs(target_index - outsider_index)

    if gap < 20:
        return (
            TIER_STANDARD,
            "Surpass the target's 24h momentum for 30 consecutive minutes",
            "Standard Win badge",
        )
    elif gap <= 50:
        return (
            TIER_UNDERDOG,
            "Reach 50% of the target's 24h momentum",
            "Underdog Win badge + 24h visibility bonus",
        )
    else:
        return (
            TIER_LEGENDARY,
            "Trigger 3 or more Strikes during the 24h challenge",
            "Legendary Strike badge + 48h featured on Home + premium share visual",
        )


# ==================== BOOSTER ELIGIBILITY ====================

async def can_activate_daily_run(db, user_id: str, person_id: ObjectId) -> Tuple[bool, str, Optional[Dict]]:
    """
    Check if a user can activate a Daily Run based on their active booster.
    Queries the active_boosts collection directly.
    
    Returns: (can_activate, reason, active_boost_doc)
    """
    now = _utcnow()

    # Find the active boost for this person
    active_boost = await db.active_boosts.find_one({
        "person_id": person_id,
        "user_id": user_id,
        "end_time": {"$gt": now},
    })

    if not active_boost:
        return False, "No active Booster. Purchase a Super or Golden Booster to unlock Daily Runs!", None

    tier = active_boost.get("tier", "booster")
    max_runs = BOOSTER_DAILY_RUNS.get(tier, 0)

    if max_runs == 0:
        return False, "Basic Booster does not include Daily Runs. Upgrade to Super or Golden Booster!", None

    boost_start = active_boost.get("start_time", active_boost.get("created_at", now))
    boost_id = active_boost["_id"]

    # Count daily runs already started during this booster's period
    daily_runs_used = await db.daily_runs.count_documents({
        "user_id": user_id,
        "boost_id": boost_id,
        "status": {"$in": [STATUS_ACTIVE, STATUS_WON, STATUS_EXPIRED]},
    })

    if tier == "super_booster":
        # Super Booster: exactly 1 daily run
        if daily_runs_used >= 1:
            return False, "Daily Run already used for this Super Booster.", None
        return True, "Super Booster — 1 Daily Run available", active_boost

    if tier == "golden_booster":
        # Golden Booster: max 7 total, max 1 per rolling 24h
        # But unused slots are lost (no cumulation)

        # Check total limit
        if daily_runs_used >= 7:
            return False, "All 7 Daily Run slots used for this Golden Booster.", None

        # Calculate how many slots have been "expired" (lost because unused)
        elapsed_seconds = (now - boost_start).total_seconds()
        elapsed_days = int(elapsed_seconds / 86400)  # full 24h periods that have passed
        # Slots that should have been used by now = elapsed_days + 1 (current day slot)
        max_slots_available_by_now = min(7, elapsed_days + 1)
        # Slots remaining = max(0, total_allowed - max(used, expired_if_unused))
        # Effectively: if they've used fewer than elapsed_days+1, some are lost
        wasted_slots = max(0, max_slots_available_by_now - daily_runs_used - 1)
        # -1 because the current day's slot is still available if not used
        remaining = 7 - daily_runs_used - wasted_slots
        if remaining <= 0:
            return False, f"No Daily Run slots remaining. {daily_runs_used} used, {wasted_slots} expired.", None

        # Check rolling 24h limit: no daily run started in last 24h
        last_24h = now - timedelta(hours=24)
        recent_run = await db.daily_runs.find_one({
            "user_id": user_id,
            "boost_id": boost_id,
            "started_at": {"$gte": last_24h},
            "status": {"$in": [STATUS_ACTIVE, STATUS_WON, STATUS_EXPIRED]},
        })
        if recent_run:
            # Calculate time until next slot
            next_available = recent_run["started_at"] + timedelta(hours=24)
            hours_left = max(0, (next_available - now).total_seconds() / 3600)
            return False, f"Maximum 1 Daily Run per 24h. Next slot in {hours_left:.1f}h.", None

        return True, f"Golden Booster — {remaining} Daily Run(s) remaining", active_boost

    return False, "Unknown booster tier.", None


# ==================== TARGET SELECTION ====================

async def get_suggested_targets(db, person_id: ObjectId, limit: int = 10) -> List[Dict]:
    """
    Get suggested targets for a Daily Run.
    Returns persons with Index gap < 20 points from the outsider (realistic targets).
    Sorted by closest gap first (most accessible).
    """
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        return []

    my_index = person.get("popularoo_index", 0)
    # Suggest targets slightly below AND above (gap < 20)
    min_index = max(0, my_index - 10)
    max_index = my_index + 25  # Up to 25 points above

    cursor = db.persons.find({
        "_id": {"$ne": person_id},
        "popularoo_index": {"$gte": min_index, "$lte": max_index},
        "approved": True,
    }).sort("popularoo_index", -1).limit(limit * 2)

    targets = []
    async for t in cursor:
        t_index = t.get("popularoo_index", 0)
        gap = abs(t_index - my_index)
        if gap > 25:
            continue
        tier, condition, reward = determine_tier(my_index, t_index)
        targets.append({
            "person_id": str(t["_id"]),
            "name": t.get("name"),
            "category": t.get("category", "other"),
            "popularoo_index": round(t_index, 1),
            "source": t.get("source", "seed"),
            "index_gap": round(gap, 1),
            "tier": tier,
            "victory_condition": condition,
            "reward": reward,
        })

    # Sort by gap ascending (closest first)
    targets.sort(key=lambda x: x["index_gap"])
    return targets[:limit]


async def search_target(db, person_id: ObjectId, query: str, limit: int = 10) -> List[Dict]:
    """
    Search for any person in the database as a potential Daily Run target.
    Used by the "Choose Anyone" feature.
    Returns persons matching the query with tier calculations.
    """
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        return []

    my_index = person.get("popularoo_index", 0)
    search_term = query.strip()
    if not search_term:
        return []

    # Build regex filter (case-insensitive, accent-friendly)
    import re
    words = search_term.split()
    filter_q: Dict[str, Any] = {
        "_id": {"$ne": person_id},
        "approved": True,
    }

    if len(words) == 1:
        filter_q["name"] = {"$regex": re.escape(words[0]), "$options": "i"}
    else:
        regex_list = [{"name": {"$regex": re.escape(w), "$options": "i"}} for w in words]
        filter_q["$and"] = regex_list

    cursor = db.persons.find(filter_q).sort("total_votes", -1).limit(limit)

    targets = []
    async for t in cursor:
        t_index = t.get("popularoo_index", 0)
        gap = abs(t_index - my_index)
        tier, condition, reward = determine_tier(my_index, t_index)
        targets.append({
            "person_id": str(t["_id"]),
            "name": t.get("name"),
            "category": t.get("category", "other"),
            "popularoo_index": round(t_index, 1),
            "source": t.get("source", "seed"),
            "index_gap": round(gap, 1),
            "tier": tier,
            "victory_condition": condition,
            "reward": reward,
        })

    return targets


# ==================== DAILY RUN LIFECYCLE ====================

async def activate_daily_run(
    db,
    user_id: str,
    person_id: ObjectId,
    target_id: ObjectId,
    rally_message: str = "",
) -> Dict[str, Any]:
    """
    Activate a new Daily Run.
    Validates booster eligibility, creates the run document,
    and tracks the boost_id for per-booster accounting.
    """
    now = _utcnow()

    # Get outsider and target
    outsider = await db.persons.find_one({"_id": person_id})
    target = await db.persons.find_one({"_id": target_id})

    if not outsider:
        return {"error": "Outsider not found"}
    if not target:
        return {"error": "Target not found"}
    if outsider.get("source") != "self_boosted":
        return {"error": "Only Outsiders can activate Daily Runs"}
    if person_id == target_id:
        return {"error": "You cannot challenge yourself!"}

    # Check if there's already an active daily run for this outsider
    existing = await db.daily_runs.find_one({
        "person_id": person_id,
        "status": STATUS_ACTIVE,
    })
    if existing:
        return {"error": "You already have an active Daily Run. Complete or wait for it to expire."}

    # Check booster eligibility
    can_activate, reason, active_boost = await can_activate_daily_run(db, user_id, person_id)
    if not can_activate:
        return {"error": reason}

    # Calculate tier
    outsider_index = outsider.get("popularoo_index", 0)
    target_index = target.get("popularoo_index", 0)
    index_gap = abs(target_index - outsider_index)
    tier, victory_condition, reward = determine_tier(outsider_index, target_index)

    expires_at = now + timedelta(hours=DAILY_RUN_DURATION_HOURS)

    daily_run = {
        "user_id": user_id,
        "person_id": person_id,             # outsider's person doc
        "target_id": target_id,             # target's person doc
        "boost_id": active_boost["_id"],    # link to the booster for accounting
        "outsider_name": outsider.get("name", "Unknown"),
        "target_name": target.get("name", "Unknown"),
        "outsider_index_at_start": round(outsider_index, 2),
        "target_index_at_start": round(target_index, 2),
        "index_gap": round(index_gap, 1),
        "tier": tier,
        "victory_condition": victory_condition,
        "reward": reward,
        "rally_message": rally_message,
        "started_at": now,
        "expires_at": expires_at,
        "status": STATUS_ACTIVE,
        "max_strikes_during_run": outsider.get("active_strikes", 0),
        "momentum_lead_since": None,        # For Standard Win tracking
        "won_at": None,
        "victory_type": None,
    }

    result = await db.daily_runs.insert_one(daily_run)
    daily_run["_id"] = result.inserted_id

    logger.info(f"🎯 Daily Run activated: {outsider.get('name')} vs {target.get('name')} "
                f"(gap={index_gap:.1f}, tier={tier}, boost={active_boost.get('tier')})")

    return {
        "success": True,
        "daily_run_id": str(result.inserted_id),
        "tier": tier,
        "index_gap": round(index_gap, 1),
        "victory_condition": victory_condition,
        "reward": reward,
        "expires_at": expires_at.isoformat() + "Z",
        "outsider_name": outsider.get("name"),
        "target_name": target.get("name"),
        "outsider_index": round(outsider_index, 2),
        "target_index": round(target_index, 2),
    }


# ==================== READ ENDPOINTS ====================

async def get_active_daily_run(db, user_id: str) -> Optional[Dict]:
    """Get the current active Daily Run for a user."""
    run = await db.daily_runs.find_one({
        "user_id": user_id,
        "status": STATUS_ACTIVE,
    })
    if not run:
        return None

    now = _utcnow()
    remaining = run["expires_at"] - now
    remaining_hours = max(0, remaining.total_seconds() / 3600)

    # Get current indices
    outsider = await db.persons.find_one({"_id": run["person_id"]})
    target = await db.persons.find_one({"_id": run["target_id"]})

    # Get current strike info
    from popularoo_index import get_strike_level
    active_strikes = outsider.get("active_strikes", 0) if outsider else 0
    strike_emoji, strike_label = get_strike_level(active_strikes)

    # Progress info based on tier
    progress = _compute_progress(run, outsider, target)

    return {
        "daily_run_id": str(run["_id"]),
        "tier": run["tier"],
        "victory_condition": run["victory_condition"],
        "reward": run["reward"],
        "outsider_name": run.get("outsider_name"),
        "target_name": run.get("target_name"),
        "outsider_index_at_start": run.get("outsider_index_at_start"),
        "target_index_at_start": run.get("target_index_at_start"),
        "outsider_index_now": round(outsider.get("popularoo_index", 0), 2) if outsider else 0,
        "target_index_now": round(target.get("popularoo_index", 0), 2) if target else 0,
        "index_gap": run.get("index_gap"),
        "started_at": run["started_at"].isoformat() + "Z",
        "expires_at": run["expires_at"].isoformat() + "Z",
        "remaining_hours": round(remaining_hours, 1),
        "status": run["status"],
        "max_strikes_during_run": run.get("max_strikes_during_run", 0),
        "current_strikes": active_strikes,
        "strike_emoji": strike_emoji,
        "strike_label": strike_label,
        "rally_message": run.get("rally_message", ""),
        "progress": progress,
    }


def _compute_progress(run: Dict, outsider: Optional[Dict], target: Optional[Dict]) -> Dict:
    """Compute progress toward victory for display in the UI."""
    tier = run.get("tier")
    if not outsider or not target:
        return {"percent": 0, "description": "Loading..."}

    o_momentum = outsider.get("index_components", {}).get("momentum_24h", 0)
    t_momentum = target.get("index_components", {}).get("momentum_24h", 0)

    if tier == TIER_STANDARD:
        # Progress = how long they've been leading
        lead_since = run.get("momentum_lead_since")
        if lead_since and o_momentum > t_momentum:
            now = _utcnow()
            minutes_leading = (now - lead_since).total_seconds() / 60
            percent = min(100, (minutes_leading / STANDARD_WIN_MINUTES) * 100)
            return {
                "percent": round(percent, 1),
                "description": f"Leading for {int(minutes_leading)}/{STANDARD_WIN_MINUTES} min",
                "outsider_momentum": round(o_momentum, 2),
                "target_momentum": round(t_momentum, 2),
            }
        else:
            return {
                "percent": 0,
                "description": "Need to surpass target's momentum",
                "outsider_momentum": round(o_momentum, 2),
                "target_momentum": round(t_momentum, 2),
            }

    elif tier == TIER_UNDERDOG:
        # Progress = ratio of outsider momentum to 50% of target momentum
        threshold = t_momentum * 0.5 if t_momentum > 0 else 1
        if threshold <= 0:
            percent = 100 if o_momentum > 0 else 0
        else:
            percent = min(100, (o_momentum / threshold) * 100)
        return {
            "percent": round(max(0, percent), 1),
            "description": f"Momentum: {round(o_momentum, 1)} / {round(threshold, 1)} needed",
            "outsider_momentum": round(o_momentum, 2),
            "target_momentum": round(t_momentum, 2),
        }

    elif tier == TIER_LEGENDARY:
        # Progress = strikes achieved out of 3 needed
        max_strikes = run.get("max_strikes_during_run", 0)
        percent = min(100, (max_strikes / 3) * 100)
        return {
            "percent": round(percent, 1),
            "description": f"Strikes: {max_strikes}/3 needed",
            "max_strikes": max_strikes,
        }

    return {"percent": 0, "description": ""}


async def get_daily_run_history(db, user_id: str, limit: int = 20) -> List[Dict]:
    """Get past Daily Runs for a user."""
    runs = []
    async for run in db.daily_runs.find(
        {"user_id": user_id}
    ).sort("started_at", -1).limit(limit):
        runs.append({
            "daily_run_id": str(run["_id"]),
            "tier": run["tier"],
            "outsider_name": run.get("outsider_name"),
            "target_name": run.get("target_name"),
            "index_gap": run.get("index_gap"),
            "started_at": run["started_at"].isoformat() + "Z",
            "status": run["status"],
            "victory_type": run.get("victory_type"),
            "won_at": run["won_at"].isoformat() + "Z" if run.get("won_at") else None,
            "max_strikes_during_run": run.get("max_strikes_during_run", 0),
        })
    return runs


async def get_live_daily_runs(db, limit: int = 10) -> List[Dict]:
    """
    Get all active Daily Runs sorted by excitement (Legendary > Underdog > Standard).
    Public endpoint for spectators ("🔥 Going Viral Now" on Home).
    """
    tier_priority = {TIER_LEGENDARY: 0, TIER_UNDERDOG: 1, TIER_STANDARD: 2}

    runs = []
    async for run in db.daily_runs.find(
        {"status": STATUS_ACTIVE}
    ).sort("started_at", -1).limit(limit * 2):

        now = _utcnow()
        remaining = run["expires_at"] - now
        remaining_hours = max(0, remaining.total_seconds() / 3600)

        outsider = await db.persons.find_one({"_id": run["person_id"]})
        target = await db.persons.find_one({"_id": run["target_id"]})

        from popularoo_index import get_strike_level
        active_strikes = outsider.get("active_strikes", 0) if outsider else 0
        emoji, label = get_strike_level(active_strikes)

        runs.append({
            "daily_run_id": str(run["_id"]),
            "tier": run["tier"],
            "tier_priority": tier_priority.get(run["tier"], 3),
            "outsider_name": run.get("outsider_name"),
            "target_name": run.get("target_name"),
            "outsider_index": round(outsider.get("popularoo_index", 0), 2) if outsider else 0,
            "target_index": round(target.get("popularoo_index", 0), 2) if target else 0,
            "index_gap": run.get("index_gap"),
            "remaining_hours": round(remaining_hours, 1),
            "max_strikes": run.get("max_strikes_during_run", 0),
            "current_strikes": active_strikes,
            "strike_emoji": emoji,
            "strike_label": label,
            "rally_message": run.get("rally_message", ""),
        })

    # Sort by tier priority (Legendary first), then by recency
    runs.sort(key=lambda r: (r["tier_priority"], -r["remaining_hours"]))
    return runs[:limit]


async def get_daily_run_status(db, user_id: str, person_id: ObjectId) -> Dict:
    """
    Get the Daily Run status including remaining slots for the user's active booster.
    Useful for the UI to show "X Daily Runs remaining".
    """
    now = _utcnow()

    # Check active boost
    active_boost = await db.active_boosts.find_one({
        "person_id": person_id,
        "user_id": user_id,
        "end_time": {"$gt": now},
    })

    if not active_boost:
        return {
            "has_booster": False,
            "can_activate": False,
            "daily_runs_available": 0,
            "daily_runs_used": 0,
            "daily_runs_total": 0,
            "booster_tier": None,
            "message": "No active booster",
        }

    tier = active_boost.get("tier", "booster")
    boost_start = active_boost.get("start_time", active_boost.get("created_at", now))

    # Count used runs for this booster
    runs_used = await db.daily_runs.count_documents({
        "user_id": user_id,
        "boost_id": active_boost["_id"],
        "status": {"$in": [STATUS_ACTIVE, STATUS_WON, STATUS_EXPIRED]},
    })

    # Check active run
    active_run = await db.daily_runs.find_one({
        "person_id": person_id,
        "status": STATUS_ACTIVE,
    })

    if tier == "booster":
        return {
            "has_booster": True,
            "can_activate": False,
            "daily_runs_available": 0,
            "daily_runs_used": 0,
            "daily_runs_total": 0,
            "booster_tier": tier,
            "has_active_run": active_run is not None,
            "message": "Basic Booster — no Daily Runs included",
        }

    if tier == "golden_booster":
        elapsed_seconds = (now - boost_start).total_seconds()
        elapsed_days = int(elapsed_seconds / 86400)
        max_slots_by_now = min(7, elapsed_days + 1)
        wasted = max(0, max_slots_by_now - runs_used - 1)
        remaining = max(0, 7 - runs_used - wasted)

        # Check 24h rolling
        last_24h = now - timedelta(hours=24)
        recent = await db.daily_runs.find_one({
            "user_id": user_id,
            "boost_id": active_boost["_id"],
            "started_at": {"$gte": last_24h},
            "status": {"$in": [STATUS_ACTIVE, STATUS_WON, STATUS_EXPIRED]},
        })
        cooldown_active = recent is not None

        return {
            "has_booster": True,
            "can_activate": remaining > 0 and not cooldown_active and not active_run,
            "daily_runs_available": remaining,
            "daily_runs_used": runs_used,
            "daily_runs_total": 7,
            "booster_tier": tier,
            "has_active_run": active_run is not None,
            "cooldown_active": cooldown_active,
            "message": f"Golden Booster — {remaining} slot(s) remaining" if remaining > 0 else "No slots remaining",
        }

    # Super Booster
    remaining = max(0, 1 - runs_used)
    return {
        "has_booster": True,
        "can_activate": remaining > 0 and not active_run,
        "daily_runs_available": remaining,
        "daily_runs_used": runs_used,
        "daily_runs_total": 1,
        "booster_tier": tier,
        "has_active_run": active_run is not None,
        "message": f"Super Booster — {remaining} Daily Run(s) remaining",
    }


# ==================== VICTORY DETECTION (Background Job) ====================

async def check_victories(db):
    """
    Background job: check all active Daily Runs for victory or expiration.
    Run every 5 minutes.
    
    IMPORTANT: A Daily Run runs for exactly 24h even if the booster expires.
    The booster expiration stops outsider visibility, but not the challenge.
    """
    now = _utcnow()
    victories = 0
    expirations = 0

    async for run in db.daily_runs.find({"status": STATUS_ACTIVE}):
        run_id = run["_id"]
        tier = run["tier"]
        expires_at = run["expires_at"]

        # Check expiration first (24h from activation, NOT from booster)
        if now >= expires_at:
            await db.daily_runs.update_one(
                {"_id": run_id},
                {"$set": {"status": STATUS_EXPIRED}}
            )
            expirations += 1
            logger.info(f"⏰ Daily Run expired: {run.get('outsider_name')} vs {run.get('target_name')}")
            continue

        # Get current data
        outsider = await db.persons.find_one({"_id": run["person_id"]})
        target = await db.persons.find_one({"_id": run["target_id"]})
        if not outsider or not target:
            continue

        # Update max_strikes_during_run
        current_strikes = outsider.get("active_strikes", 0)
        max_strikes = max(run.get("max_strikes_during_run", 0), current_strikes)
        if max_strikes > run.get("max_strikes_during_run", 0):
            await db.daily_runs.update_one(
                {"_id": run_id},
                {"$set": {"max_strikes_during_run": max_strikes}}
            )

        # Check victory based on tier
        won = False
        victory_type = None

        if tier == TIER_STANDARD:
            won, victory_type = await _check_standard_victory(db, run, outsider, target, now)
        elif tier == TIER_UNDERDOG:
            won, victory_type = _check_underdog_victory(run, outsider, target)
        elif tier == TIER_LEGENDARY:
            won, victory_type = _check_legendary_victory(max_strikes)

        if won:
            await db.daily_runs.update_one(
                {"_id": run_id},
                {"$set": {
                    "status": STATUS_WON,
                    "won_at": now,
                    "victory_type": victory_type,
                    "max_strikes_during_run": max_strikes,
                    "outsider_index_at_end": outsider.get("popularoo_index", 0),
                    "target_index_at_end": target.get("popularoo_index", 0),
                }}
            )
            victories += 1
            logger.info(f"🏆 VICTORY! {run.get('outsider_name')} achieved {victory_type} "
                       f"against {run.get('target_name')}")

            # Apply rewards
            await _apply_victory_rewards(db, run, victory_type)

    if victories > 0 or expirations > 0:
        logger.info(f"🎯 Daily Run check: {victories} victories, {expirations} expirations")


async def _check_standard_victory(db, run: Dict, outsider: Dict, target: Dict, now: datetime) -> Tuple[bool, Optional[str]]:
    """
    Standard Win: outsider's 24h momentum must exceed target's momentum
    for 30 consecutive minutes.
    """
    outsider_momentum = outsider.get("index_components", {}).get("momentum_24h", 0)
    target_momentum = target.get("index_components", {}).get("momentum_24h", 0)

    if outsider_momentum > target_momentum:
        # Outsider is currently leading in momentum
        lead_since = run.get("momentum_lead_since")
        if lead_since is None:
            # Just started leading — record the timestamp
            await db.daily_runs.update_one(
                {"_id": run["_id"]},
                {"$set": {"momentum_lead_since": now}}
            )
            return False, None
        else:
            # Check if 30 minutes have passed
            minutes_leading = (now - lead_since).total_seconds() / 60
            if minutes_leading >= STANDARD_WIN_MINUTES:
                return True, "Standard Win"
    else:
        # Not leading — reset the counter
        if run.get("momentum_lead_since") is not None:
            await db.daily_runs.update_one(
                {"_id": run["_id"]},
                {"$set": {"momentum_lead_since": None}}
            )

    return False, None


def _check_underdog_victory(run: Dict, outsider: Dict, target: Dict) -> Tuple[bool, Optional[str]]:
    """
    Underdog Win: outsider reaches 50% of the target's 24h momentum.
    """
    target_momentum = target.get("index_components", {}).get("momentum_24h", 0)
    outsider_momentum = outsider.get("index_components", {}).get("momentum_24h", 0)

    if target_momentum <= 0:
        # Target has no/negative momentum — outsider wins if they have ANY positive momentum
        if outsider_momentum > 0:
            return True, "Underdog Win"
        return False, None

    ratio = outsider_momentum / target_momentum
    if ratio >= 0.5:
        return True, "Underdog Win"

    return False, None


def _check_legendary_victory(max_strikes: int) -> Tuple[bool, Optional[str]]:
    """
    Legendary Strike: outsider must have achieved 3+ strikes at any point during the run.
    """
    if max_strikes >= 3:
        return True, "Legendary Strike"
    return False, None


async def _apply_victory_rewards(db, run: Dict, victory_type: str):
    """Apply rewards based on victory type."""
    person_id = run["person_id"]
    now = _utcnow()

    # Add badge to person
    badge = {
        "type": victory_type,
        "target_name": run.get("target_name"),
        "index_gap": run.get("index_gap"),
        "tier": run.get("tier"),
        "earned_at": now,
    }
    await db.persons.update_one(
        {"_id": person_id},
        {"$push": {"badges": badge}}
    )

    if victory_type == "Underdog Win":
        # 24h visibility bonus
        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {"visibility_bonus_until": now + timedelta(hours=24)}}
        )
        logger.info(f"🎁 Underdog Win reward: 24h visibility bonus for {run.get('outsider_name')}")

    elif victory_type == "Legendary Strike":
        # 48h featured on Home
        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {"featured_until": now + timedelta(hours=48)}}
        )
        logger.info(f"🎁 Legendary Strike reward: 48h featured for {run.get('outsider_name')}")


# ==================== INDEXES ====================

async def ensure_daily_run_indexes(db):
    """Create MongoDB indexes for Daily Runs."""
    await db.daily_runs.create_index([("user_id", 1), ("status", 1)])
    await db.daily_runs.create_index([("status", 1), ("expires_at", 1)])
    await db.daily_runs.create_index([("user_id", 1), ("started_at", -1)])
    await db.daily_runs.create_index([("user_id", 1), ("boost_id", 1)])
    await db.daily_runs.create_index([("person_id", 1), ("status", 1)])
    await db.daily_runs.create_index([("started_at", -1)])
    logger.info("🎯 Daily Run indexes ensured")
