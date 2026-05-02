"""
Popularoo Index — Proprietary scoring algorithm (0-100)
Confidential: coefficients and formula are never exposed publicly.

Components:
  - score_volume (20%): logarithmic scale of weighted votes
  - ratio_approbation (40%): approval ratio favoring positive engagement
  - momentum_24h (25%): delta of base_index over last 24h
  - regularity (15%): consistency of voting over 7 days
  + strikes_bonus: +5 per active strike (outsiders only)

Circularity resolution:
  base_index = volume*w_v + ratio*w_r + regularity*w_reg + strikes_bonus
  momentum = (base_index_now - base_index_24h_ago) * 5
  final_index = min(100, base_index + momentum * w_m)
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger("popularoo_index")

# ---- In-memory config cache ----
_config_cache: Optional[Dict[str, Any]] = None
_config_last_loaded: Optional[datetime] = None
CONFIG_CACHE_TTL_SECONDS = 300  # 5 minutes


def _utcnow() -> datetime:
    return datetime.utcnow()


# ==================== CONFIG ====================

DEFAULT_CONFIG = {
    "_id": "popularoo_index",
    "coefficients": {
        "volume": 0.20,
        "ratio": 0.40,
        "momentum": 0.25,
        "regularity": 0.15,
    },
    "strike_value": 5,  # points per active strike
    "low_vote_cap": 30,  # max index if weighted_votes < low_vote_threshold
    "low_vote_threshold": 10,  # weighted votes below which cap applies
    "momentum_multiplier": 5,  # momentum = delta * this
    "regularity_scale": 10,  # regularity normalized to 0-this
    "volume_scale": 20,  # score_volume = log10(wv+1) * this
    "ratio_scale": 10,  # ratio_approbation *= this
}


async def load_config(db) -> Dict[str, Any]:
    """Load algorithm config from MongoDB with in-memory caching."""
    global _config_cache, _config_last_loaded

    now = _utcnow()
    if _config_cache and _config_last_loaded:
        if (now - _config_last_loaded).total_seconds() < CONFIG_CACHE_TTL_SECONDS:
            return _config_cache

    try:
        doc = await db.algorithm_config.find_one({"_id": "popularoo_index"})
        if doc:
            _config_cache = doc
        else:
            # First run: seed default config
            await db.algorithm_config.insert_one(DEFAULT_CONFIG.copy())
            _config_cache = DEFAULT_CONFIG.copy()
            logger.info("📊 Seeded default algorithm_config")
    except Exception as e:
        logger.warning(f"Failed to load config from DB: {e}, using defaults")
        _config_cache = DEFAULT_CONFIG.copy()

    _config_last_loaded = now
    return _config_cache


def invalidate_config_cache():
    """Force reload config on next call."""
    global _config_cache, _config_last_loaded
    _config_cache = None
    _config_last_loaded = None


# ==================== COMPONENT CALCULATIONS ====================

def calc_score_volume(person: Dict, config: Dict) -> float:
    """
    score_volume = log10(weighted_votes + 1) * volume_scale
    weighted_votes = likes + (5 * superlikes) - dislikes
    """
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    scale = config.get("volume_scale", 20)

    weighted_votes = likes + (5 * superlikes) - dislikes
    weighted_votes = max(0, weighted_votes)  # Floor at 0
    return math.log10(weighted_votes + 1) * scale


def calc_ratio_approbation(person: Dict, config: Dict) -> float:
    """
    ratio_approbation = log10((weighted_likes² / (weighted_likes + dislikes + 1)) + 1) * ratio_scale
    Log normalization prevents explosion with large vote counts while preserving relative ranking.
    weighted_likes = likes + (5 * superlikes)
    """
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    scale = config.get("ratio_scale", 10)

    weighted_likes = likes + (5 * superlikes)
    if weighted_likes <= 0:
        return 0.0

    ratio_raw = (weighted_likes ** 2) / (weighted_likes + dislikes + 1)
    # Log normalization: keeps the ranking but prevents explosion
    return math.log10(ratio_raw + 1) * scale


def calc_regularity(daily_vote_counts: list, config: Dict) -> float:
    """
    regularity = consistency of votes over 7 days × regularity_scale
    Uses inverse coefficient of variation (1 - CV) clamped to [0, 1].
    Perfect consistency (same votes each day) → 1.0
    No votes or wildly inconsistent → 0.0
    """
    scale = config.get("regularity_scale", 10)

    if not daily_vote_counts or len(daily_vote_counts) == 0:
        return 0.0

    counts = [float(c) for c in daily_vote_counts]
    mean = sum(counts) / len(counts)

    if mean == 0:
        return 0.0

    # Standard deviation
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    std_dev = math.sqrt(variance)

    # Coefficient of variation (CV = std/mean)
    cv = std_dev / mean if mean > 0 else 0

    # Inverse: high consistency = low CV = high regularity
    regularity = max(0.0, min(1.0, 1.0 - cv))
    return regularity * scale


def calc_strikes_bonus(person: Dict, config: Dict) -> float:
    """
    strikes_bonus = active_strikes × strike_value
    Only for outsiders (source = "self_boosted").
    """
    if person.get("source") != "self_boosted":
        return 0.0

    active_strikes = person.get("active_strikes", 0)
    strike_value = config.get("strike_value", 5)
    return active_strikes * strike_value


# ==================== INDEX CALCULATION ====================

def compute_base_index(person: Dict, config: Dict, daily_votes: Optional[list] = None) -> float:
    """
    Compute base_index (without momentum) for a person.
    base_index = volume * w_v + ratio * w_r + regularity * w_reg + strikes_bonus
    """
    coeffs = config.get("coefficients", DEFAULT_CONFIG["coefficients"])
    w_v = coeffs.get("volume", 0.20)
    w_r = coeffs.get("ratio", 0.40)
    w_reg = coeffs.get("regularity", 0.15)

    volume = calc_score_volume(person, config)
    ratio = calc_ratio_approbation(person, config)
    regularity = calc_regularity(daily_votes or [], config)
    strikes = calc_strikes_bonus(person, config)

    base = (volume * w_v) + (ratio * w_r) + (regularity * w_reg) + strikes
    return base


def compute_popularoo_index(
    person: Dict,
    config: Dict,
    daily_votes: Optional[list] = None,
    base_index_24h_ago: Optional[float] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Compute the full Popularoo Index for a person.

    Returns:
        (index, components_dict)
        index: float 0-100
        components_dict: breakdown of each component (for debugging/admin)
    """
    coeffs = config.get("coefficients", DEFAULT_CONFIG["coefficients"])
    w_v = coeffs.get("volume", 0.20)
    w_r = coeffs.get("ratio", 0.40)
    w_m = coeffs.get("momentum", 0.25)
    w_reg = coeffs.get("regularity", 0.15)

    volume = calc_score_volume(person, config)
    ratio = calc_ratio_approbation(person, config)
    regularity = calc_regularity(daily_votes or [], config)
    strikes = calc_strikes_bonus(person, config)

    base = (volume * w_v) + (ratio * w_r) + (regularity * w_reg) + strikes

    # Momentum: delta of base_index over 24h
    momentum_mult = config.get("momentum_multiplier", 5)
    if base_index_24h_ago is not None:
        momentum_raw = (base - base_index_24h_ago) * momentum_mult
    else:
        momentum_raw = 0.0

    final = base + (momentum_raw * w_m)

    # Low-vote cap
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    weighted_votes = likes + (5 * superlikes) - dislikes
    low_cap = config.get("low_vote_cap", 30)
    low_threshold = config.get("low_vote_threshold", 10)

    if weighted_votes < low_threshold:
        final = min(final, low_cap)

    # Clamp to [0, 100]
    final = max(0.0, min(100.0, final))

    components = {
        "score_volume": round(volume, 2),
        "ratio_approbation": round(ratio, 2),
        "momentum_24h": round(momentum_raw, 2),
        "regularity": round(regularity, 2),
        "strikes_bonus": round(strikes, 2),
        "base_index": round(base, 2),
        "final_index": round(final, 2),
        "weighted_votes": weighted_votes,
    }

    return round(final, 1), components


# ==================== STRIKE LEVELS ====================

STRIKE_LEVELS = {
    0: ("", ""),
    1: ("🔥", "Heating Up"),
    2: ("⚡", "On Fire"),
    3: ("🌟", "Trending"),
    4: ("💥", "Going Viral"),
}
# 5+ → Legend Mode
LEGEND_MODE = ("👑", "Legend Mode")


def get_strike_level(strike_count: int) -> Tuple[str, str]:
    """
    Returns (emoji, label) for the given strike count.
    """
    if strike_count <= 0:
        return STRIKE_LEVELS[0]
    if strike_count >= 5:
        return LEGEND_MODE
    return STRIKE_LEVELS.get(strike_count, LEGEND_MODE)


# ==================== BACKGROUND JOBS ====================

async def get_daily_vote_counts(db, person_id, days: int = 7) -> list:
    """
    Aggregate vote counts per day for the last N days.
    Returns a list of N integers (one per day).
    """
    from bson import ObjectId
    now = _utcnow()
    start = now - timedelta(days=days)

    pipeline = [
        {"$match": {
            "person_id": ObjectId(str(person_id)) if not isinstance(person_id, ObjectId) else person_id,
            "created_at": {"$gte": start, "$lte": now}
        }},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "count": {"$sum": 1}
        }}
    ]

    cursor = db.vote_events.aggregate(pipeline)
    results = {}
    async for doc in cursor:
        results[doc["_id"]] = doc["count"]

    # Build array for all N days (0 for missing days)
    daily = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append(results.get(day, 0))

    return daily


async def get_base_index_24h_ago(db, person_id) -> Optional[float]:
    """Get the base_index snapshot from ~24h ago."""
    from bson import ObjectId
    pid = ObjectId(str(person_id)) if not isinstance(person_id, ObjectId) else person_id
    target_time = _utcnow() - timedelta(hours=24)

    # Find snapshot closest to 24h ago
    snapshot = await db.index_snapshots.find_one(
        {
            "person_id": pid,
            "timestamp": {"$lte": target_time}
        },
        sort=[("timestamp", -1)]
    )
    if snapshot:
        return snapshot.get("base_index", None)
    return None


async def recalculate_index_for_person(db, person: Dict, config: Dict) -> float:
    """
    Full recalculation of Popularoo Index for a single person.
    Updates the person document and creates a snapshot.
    Returns the new index.
    """
    from bson import ObjectId

    person_id = person["_id"]
    daily_votes = await get_daily_vote_counts(db, person_id)
    base_24h = await get_base_index_24h_ago(db, person_id)

    index_val, components = compute_popularoo_index(
        person, config, daily_votes, base_24h
    )

    base = components["base_index"]
    now = _utcnow()

    # Update person document
    await db.persons.update_one(
        {"_id": person_id},
        {"$set": {
            "popularoo_index": index_val,
            "base_index": base,
            "index_components": components,
            "last_index_calc": now,
        }}
    )

    # Store snapshot
    await db.index_snapshots.insert_one({
        "person_id": person_id,
        "base_index": base,
        "popularoo_index": index_val,
        "timestamp": now,
    })

    return index_val


async def quick_recalc_index(db, person: Dict, config: Dict) -> float:
    """
    Quick recalculation after a vote — uses cached regularity & momentum.
    Only recalculates volume and ratio (the instant components).
    """
    coeffs = config.get("coefficients", DEFAULT_CONFIG["coefficients"])
    w_v = coeffs.get("volume", 0.20)
    w_r = coeffs.get("ratio", 0.40)
    w_m = coeffs.get("momentum", 0.25)
    w_reg = coeffs.get("regularity", 0.15)

    volume = calc_score_volume(person, config)
    ratio = calc_ratio_approbation(person, config)
    strikes = calc_strikes_bonus(person, config)

    # Use cached regularity from last full recalc
    cached_components = person.get("index_components", {})
    regularity = cached_components.get("regularity", 0.0)
    momentum_raw = cached_components.get("momentum_24h", 0.0)

    base = (volume * w_v) + (ratio * w_r) + (regularity * w_reg) + strikes
    final = base + (momentum_raw * w_m)

    # Low-vote cap
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    weighted_votes = likes + (5 * superlikes) - dislikes
    low_cap = config.get("low_vote_cap", 30)
    low_threshold = config.get("low_vote_threshold", 10)

    if weighted_votes < low_threshold:
        final = min(final, low_cap)

    final = max(0.0, min(100.0, final))
    final = round(final, 1)

    # Update person document
    components = {
        "score_volume": round(volume, 2),
        "ratio_approbation": round(ratio, 2),
        "momentum_24h": round(momentum_raw, 2),
        "regularity": round(regularity, 2),
        "strikes_bonus": round(strikes, 2),
        "base_index": round(base, 2),
        "final_index": round(final, 2),
        "weighted_votes": weighted_votes,
    }

    await db.persons.update_one(
        {"_id": person["_id"]},
        {"$set": {
            "popularoo_index": final,
            "base_index": round(base, 2),
            "index_components": components,
        }}
    )

    return final


async def recalculate_all_indices(db):
    """
    Background job: recalculate Popularoo Index for all active persons.
    Run every 15 minutes.
    """
    config = await load_config(db)
    now = _utcnow()

    # Find all persons with votes or active boosts
    cursor = db.persons.find({
        "$or": [
            {"total_votes": {"$gt": 0}},
            {"superlikes": {"$gt": 0}},
            {"source": "self_boosted"},
        ]
    })

    count = 0
    async for person in cursor:
        try:
            await recalculate_index_for_person(db, person, config)
            count += 1
        except Exception as e:
            logger.warning(f"Failed to recalculate index for {person.get('name')}: {e}")

    # Clean old snapshots (keep only last 48h)
    cutoff = now - timedelta(hours=48)
    result = await db.index_snapshots.delete_many({"timestamp": {"$lt": cutoff}})
    if result.deleted_count > 0:
        logger.debug(f"🗑️ Cleaned {result.deleted_count} old index snapshots")

    logger.info(f"📊 Recalculated Popularoo Index for {count} persons")


async def ensure_indexes(db):
    """Create MongoDB indexes for efficient queries."""
    try:
        # Index snapshots: fast lookup by person + timestamp
        await db.index_snapshots.create_index(
            [("person_id", 1), ("timestamp", -1)]
        )
        # Superlike events: for strike detection
        await db.superlike_events.create_index(
            [("person_id", 1), ("created_at", -1)]
        )
        await db.superlike_events.create_index(
            [("person_id", 1), ("device_id", 1), ("created_at", -1)]
        )
        # Superlike votes: for cooldown tracking
        await db.superlike_votes.create_index(
            [("person_id", 1), ("device_id", 1)]
        )
        # Strikes
        await db.strikes.create_index(
            [("person_id", 1), ("expires_at", 1)]
        )
        # Vote events (for regularity)
        await db.vote_events.create_index(
            [("person_id", 1), ("created_at", -1)]
        )
        logger.info("📊 Popularoo Index database indexes ensured")
    except Exception as e:
        logger.warning(f"Failed to create indexes: {e}")


# ==================== MIGRATION ====================

async def migrate_initial_index(db):
    """
    One-time migration: calculate initial Popularoo Index for all persons.
    Adds superlikes=0 and computes initial index based on existing votes.
    """
    config = await load_config(db)

    # Add superlikes field if missing
    await db.persons.update_many(
        {"superlikes": {"$exists": False}},
        {"$set": {"superlikes": 0}}
    )

    # Add active_strikes field if missing
    await db.persons.update_many(
        {"active_strikes": {"$exists": False}},
        {"$set": {"active_strikes": 0}}
    )

    # Calculate index for all persons
    cursor = db.persons.find({})
    count = 0
    async for person in cursor:
        try:
            daily_votes = await get_daily_vote_counts(db, person["_id"])
            index_val, components = compute_popularoo_index(
                person, config, daily_votes, None  # No 24h snapshot yet
            )
            base = components["base_index"]

            await db.persons.update_one(
                {"_id": person["_id"]},
                {"$set": {
                    "popularoo_index": index_val,
                    "base_index": base,
                    "index_components": components,
                    "last_index_calc": _utcnow(),
                    "superlikes": person.get("superlikes", 0),
                    "active_strikes": person.get("active_strikes", 0),
                }}
            )

            # Initial snapshot
            await db.index_snapshots.insert_one({
                "person_id": person["_id"],
                "base_index": base,
                "popularoo_index": index_val,
                "timestamp": _utcnow(),
            })

            count += 1
        except Exception as e:
            logger.warning(f"Migration failed for {person.get('name')}: {e}")

    logger.info(f"✅ Popularoo Index migration complete: {count} persons indexed")
    return count
