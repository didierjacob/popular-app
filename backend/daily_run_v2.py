"""
Daily Run V2 — 24h rolling challenge replacing Bull Run.

An outsider picks a target (celebrity or other outsider) and tries to 
beat them within 24 hours. Victory conditions depend on the Index gap.

Tiers:
  < 20 points gap  → Standard Win (surpass target's 24h momentum for 30 consecutive min)
  20-50 points gap  → Underdog Win (reach 50% of target's 24h momentum)
  > 50 points gap   → Legendary Strike (trigger 3+ strikes during the 24h)

Booster integration:
  Booster (€0.99):       0 daily runs
  Super Booster (€9.99): 1 daily run during 24h visibility
  Golden Booster (€49.99): 7 daily runs (max 1 per 24h rolling)
"""

import logging
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
    elif gap < 50:
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


def can_activate_daily_run(user_doc: Dict) -> Tuple[bool, str]:
    """
    Check if a user can activate a Daily Run based on their booster tier.
    Returns: (can_activate, reason)
    """
    boosters = user_doc.get("boosters", 0)
    super_boosters = user_doc.get("super_boosters", 0)
    golden_boosters = user_doc.get("golden_boosters", 0)
    daily_runs_used = user_doc.get("daily_runs_used", 0)
    daily_runs_limit = user_doc.get("daily_runs_limit", 0)

    if golden_boosters > 0:
        # Golden: max 1 per 24h rolling, up to 7 total
        if daily_runs_used >= daily_runs_limit:
            return False, "All Daily Run slots used for this Golden Booster"
        return True, "Golden Booster — Daily Run available"

    if super_boosters > 0:
        # Super: 1 daily run total
        if daily_runs_used >= 1:
            return False, "Daily Run already used for this Super Booster"
        return True, "Super Booster — 1 Daily Run available"

    if boosters > 0:
        return False, "Basic Booster does not include Daily Runs. Upgrade to Super Booster!"

    return False, "No active Booster. Purchase a Super or Golden Booster to unlock Daily Runs!"


# ==================== ENDPOINTS LOGIC ====================

async def get_suggested_targets(db, person_id: ObjectId, limit: int = 10) -> List[Dict]:
    """
    Get suggested targets for a Daily Run.
    Returns persons with Index gap < 20 points from the outsider (realistic targets).
    """
    person = await db.persons.find_one({"_id": person_id})
    if not person:
        return []

    my_index = person.get("popularoo_index", 0)
    min_index = max(0, my_index - 5)   # Allow slightly below too
    max_index = my_index + 25           # Up to 25 points above

    cursor = db.persons.find({
        "_id": {"$ne": person_id},
        "popularoo_index": {"$gte": min_index, "$lte": max_index},
        "approved": True,
    }).sort("popularoo_index", -1).limit(limit)

    targets = []
    async for t in cursor:
        gap = abs(t.get("popularoo_index", 0) - my_index)
        tier, condition, reward = determine_tier(my_index, t.get("popularoo_index", 0))
        targets.append({
            "person_id": str(t["_id"]),
            "name": t.get("name"),
            "category": t.get("category", "other"),
            "popularoo_index": t.get("popularoo_index", 0),
            "source": t.get("source", "seed"),
            "index_gap": round(gap, 1),
            "tier": tier,
            "victory_condition": condition,
            "reward": reward,
        })

    return targets


async def activate_daily_run(
    db,
    user_id: str,
    person_id: ObjectId,
    target_id: ObjectId,
    rally_message: str = "",
) -> Dict[str, Any]:
    """
    Activate a new Daily Run.
    Returns the created daily_run document.
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

    # Check if there's already an active daily run for this user
    existing = await db.daily_runs.find_one({
        "user_id": user_id,
        "status": STATUS_ACTIVE,
    })
    if existing:
        return {"error": "You already have an active Daily Run. Complete or wait for it to expire."}

    # Check booster eligibility
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        return {"error": "User not found"}

    # Check 24h rolling limit for Golden Booster
    if user.get("golden_boosters", 0) > 0:
        last_24h = now - timedelta(hours=24)
        recent_run = await db.daily_runs.find_one({
            "user_id": user_id,
            "started_at": {"$gte": last_24h},
        })
        if recent_run:
            return {"error": "Golden Booster: maximum 1 Daily Run per 24h. Try again later."}

    can_activate, reason = can_activate_daily_run(user)
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
        "person_id": person_id,           # outsider's person doc
        "target_id": target_id,           # target's person doc
        "outsider_name": outsider.get("name", "Unknown"),
        "target_name": target.get("name", "Unknown"),
        "outsider_index_at_start": outsider_index,
        "target_index_at_start": target_index,
        "index_gap": round(index_gap, 1),
        "tier": tier,
        "victory_condition": victory_condition,
        "reward": reward,
        "rally_message": rally_message,
        "started_at": now,
        "expires_at": expires_at,
        "status": STATUS_ACTIVE,
        "max_strikes_during_run": outsider.get("active_strikes", 0),
        "momentum_lead_since": None,      # For Standard Win tracking
        "won_at": None,
        "victory_type": None,
    }

    result = await db.daily_runs.insert_one(daily_run)
    daily_run["_id"] = result.inserted_id

    # Increment user's daily_runs_used
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"daily_runs_used": 1}}
    )

    logger.info(f"🎯 Daily Run activated: {outsider.get('name')} vs {target.get('name')} "
                f"(gap={index_gap:.1f}, tier={tier})")

    return {
        "success": True,
        "daily_run_id": str(result.inserted_id),
        "tier": tier,
        "index_gap": round(index_gap, 1),
        "victory_condition": victory_condition,
        "reward": reward,
        "expires_at": expires_at.isoformat() + "Z",
        "outsider_index": outsider_index,
        "target_index": target_index,
    }


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

    return {
        "daily_run_id": str(run["_id"]),
        "tier": run["tier"],
        "victory_condition": run["victory_condition"],
        "reward": run["reward"],
        "outsider_name": run.get("outsider_name"),
        "target_name": run.get("target_name"),
        "outsider_index_at_start": run.get("outsider_index_at_start"),
        "target_index_at_start": run.get("target_index_at_start"),
        "outsider_index_now": outsider.get("popularoo_index", 0) if outsider else 0,
        "target_index_now": target.get("popularoo_index", 0) if target else 0,
        "index_gap": run.get("index_gap"),
        "started_at": run["started_at"].isoformat() + "Z",
        "expires_at": run["expires_at"].isoformat() + "Z",
        "remaining_hours": round(remaining_hours, 1),
        "status": run["status"],
        "max_strikes_during_run": run.get("max_strikes_during_run", 0),
        "rally_message": run.get("rally_message", ""),
    }


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
        })
    return runs


async def get_live_daily_runs(db, limit: int = 10) -> List[Dict]:
    """
    Get all active Daily Runs sorted by excitement (Legendary > Underdog > Standard).
    Public endpoint for spectators.
    """
    # Priority order for tiers
    tier_priority = {TIER_LEGENDARY: 0, TIER_UNDERDOG: 1, TIER_STANDARD: 2}

    runs = []
    async for run in db.daily_runs.find(
        {"status": STATUS_ACTIVE}
    ).sort("started_at", -1).limit(limit * 2):  # Fetch extra to sort

        now = _utcnow()
        remaining = run["expires_at"] - now
        remaining_hours = max(0, remaining.total_seconds() / 3600)

        outsider = await db.persons.find_one({"_id": run["person_id"]})
        target = await db.persons.find_one({"_id": run["target_id"]})

        runs.append({
            "daily_run_id": str(run["_id"]),
            "tier": run["tier"],
            "tier_priority": tier_priority.get(run["tier"], 3),
            "outsider_name": run.get("outsider_name"),
            "target_name": run.get("target_name"),
            "outsider_index": outsider.get("popularoo_index", 0) if outsider else 0,
            "target_index": target.get("popularoo_index", 0) if target else 0,
            "index_gap": run.get("index_gap"),
            "remaining_hours": round(remaining_hours, 1),
            "max_strikes": run.get("max_strikes_during_run", 0),
            "rally_message": run.get("rally_message", ""),
        })

    # Sort by tier priority (Legendary first), then by recency
    runs.sort(key=lambda r: (r["tier_priority"], -r["remaining_hours"]))
    return runs[:limit]


# ==================== VICTORY DETECTION (Background Job) ====================

async def check_victories(db):
    """
    Background job: check all active Daily Runs for victory or expiration.
    Run every 5 minutes.
    """
    now = _utcnow()
    victories = 0
    expirations = 0

    async for run in db.daily_runs.find({"status": STATUS_ACTIVE}):
        run_id = run["_id"]
        tier = run["tier"]
        expires_at = run["expires_at"]

        # Check expiration first
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
    Standard Win: outsider's base_index momentum must exceed target's momentum
    for 30 consecutive minutes.
    """
    outsider_momentum = outsider.get("index_components", {}).get("momentum_24h", 0)
    target_momentum = target.get("index_components", {}).get("momentum_24h", 0)

    if outsider_momentum > target_momentum:
        # Outsider is currently leading in momentum
        lead_since = run.get("momentum_lead_since")
        if lead_since is None:
            # Just started leading
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

    ratio = outsider_momentum / target_momentum if target_momentum != 0 else 0
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


async def ensure_daily_run_indexes(db):
    """Create MongoDB indexes for Daily Runs."""
    await db.daily_runs.create_index([("user_id", 1), ("status", 1)])
    await db.daily_runs.create_index([("status", 1), ("expires_at", 1)])
    await db.daily_runs.create_index([("user_id", 1), ("started_at", -1)])
    await db.daily_runs.create_index([("started_at", -1)])
    logger.info("🎯 Daily Run indexes ensured")
