"""
Strikes System — Exceptional amplifiers for Outsiders.
Each Strike = +5 points in Popularoo Index (via strikes_bonus).

3 trigger conditions (cumulative):
  - Strike Flash: 5 superlikes received in < 30 minutes
  - Strike Diversité: 10 superlikes from 10 unique users in 24h
  - Strike Série: 3 consecutive superlikes within the same 1-hour window

Nomenclature by active strikes count (24h rolling):
  1: 🔥 Heating Up
  2: ⚡ On Fire
  3: 🌟 Trending
  4: 💥 Going Viral
  5+: 👑 Legend Mode
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from bson import ObjectId

logger = logging.getLogger("strikes")


def _utcnow() -> datetime:
    return datetime.utcnow()


STRIKE_FLASH = "flash"        # 5 superlikes in 30 min
STRIKE_DIVERSITY = "diversity"  # 10 unique users in 24h
STRIKE_SERIES = "series"        # 3 consecutive superlikes in same 1h window
STRIKE_DURATION_HOURS = 24      # Strikes expire after 24h


async def check_and_trigger_strikes(db, person_id: ObjectId, email_service=None) -> Dict[str, Any]:
    """
    Event-driven strike detection. Called after each superlike.
    Checks all 3 conditions and creates strikes if triggered.
    
    Returns:
        {
            "new_strikes": ["flash", "series"],  # newly triggered
            "active_count": 3,                    # total active strikes
            "level_emoji": "🌟",
            "level_label": "Trending",
        }
    """
    now = _utcnow()
    new_strikes = []

    # ---- Check Strike Flash: 5 superlikes in 30 min ----
    flash_window = now - timedelta(minutes=30)
    flash_count = await db.superlike_events.count_documents({
        "person_id": person_id,
        "created_at": {"$gte": flash_window}
    })
    if flash_count >= 5:
        created = await _create_strike_if_new(db, person_id, STRIKE_FLASH, now)
        if created:
            new_strikes.append(STRIKE_FLASH)
            logger.info(f"⚡ Strike Flash triggered for person {person_id} ({flash_count} SL in 30min)")

    # ---- Check Strike Diversité: 10 unique users in 24h ----
    diversity_window = now - timedelta(hours=24)
    pipeline = [
        {"$match": {
            "person_id": person_id,
            "created_at": {"$gte": diversity_window}
        }},
        {"$group": {"_id": "$device_id"}},
        {"$count": "unique_users"}
    ]
    result = await db.superlike_events.aggregate(pipeline).to_list(1)
    unique_users = result[0]["unique_users"] if result else 0
    
    if unique_users >= 10:
        created = await _create_strike_if_new(db, person_id, STRIKE_DIVERSITY, now)
        if created:
            new_strikes.append(STRIKE_DIVERSITY)
            logger.info(f"🌍 Strike Diversité triggered for person {person_id} ({unique_users} unique users)")

    # ---- Check Strike Série: 3 consecutive superlikes in same 1h window ----
    recent_superlikes = await db.superlike_events.find(
        {"person_id": person_id},
        sort=[("created_at", -1)],
    ).to_list(3)
    
    if len(recent_superlikes) >= 3:
        oldest = recent_superlikes[-1]["created_at"]
        newest = recent_superlikes[0]["created_at"]
        if (newest - oldest).total_seconds() <= 3600:  # All 3 within 1 hour
            created = await _create_strike_if_new(db, person_id, STRIKE_SERIES, now)
            if created:
                new_strikes.append(STRIKE_SERIES)
                logger.info(f"🔥 Strike Série triggered for person {person_id} (3 SL in 1h)")

    # ---- Update person's active_strikes count ----
    previous_count = await db.persons.find_one({"_id": person_id}, {"active_strikes": 1})
    prev_active = previous_count.get("active_strikes", 0) if previous_count else 0

    active_count = await _count_active_strikes(db, person_id)
    
    from popularoo_index import get_strike_level
    emoji, label = get_strike_level(active_count)

    await db.persons.update_one(
        {"_id": person_id},
        {"$set": {
            "active_strikes": active_count,
            "strike_emoji": emoji if emoji else None,
            "strike_label": label if label else None,
            "strikes_updated_at": now,
        }}
    )

    # ---- Send strike milestone emails (3a Going Viral, 3b Legend Mode) ----
    if new_strikes and email_service:
        await _send_strike_emails(db, email_service, person_id, active_count, prev_active)

    return {
        "new_strikes": new_strikes,
        "active_count": active_count,
        "level_emoji": emoji,
        "level_label": label,
    }


async def _create_strike_if_new(db, person_id: ObjectId, strike_type: str, now: datetime) -> bool:
    """
    Create a strike if one of this type isn't already active.
    Returns True if a new strike was created.
    """
    # Check if this type of strike is already active (within last 24h)
    existing = await db.strikes.find_one({
        "person_id": person_id,
        "type": strike_type,
        "expires_at": {"$gt": now},
    })
    
    if existing:
        return False  # Already active, don't duplicate
    
    expires_at = now + timedelta(hours=STRIKE_DURATION_HOURS)
    await db.strikes.insert_one({
        "person_id": person_id,
        "type": strike_type,
        "triggered_at": now,
        "expires_at": expires_at,
    })
    return True


async def _count_active_strikes(db, person_id: ObjectId) -> int:
    """Count currently active (non-expired) strikes for a person."""
    now = _utcnow()
    return await db.strikes.count_documents({
        "person_id": person_id,
        "expires_at": {"$gt": now},
    })


async def get_active_strikes_detail(db, person_id: ObjectId) -> List[Dict]:
    """Get detailed list of active strikes for a person."""
    now = _utcnow()
    strikes = []
    async for s in db.strikes.find({
        "person_id": person_id,
        "expires_at": {"$gt": now},
    }).sort("triggered_at", -1):
        strikes.append({
            "type": s["type"],
            "triggered_at": s["triggered_at"],
            "expires_at": s["expires_at"],
            "remaining_hours": max(0, (s["expires_at"] - now).total_seconds() / 3600),
        })
    return strikes


async def cleanup_expired_strikes(db):
    """
    Background job: clean up expired strikes and update person counts.
    Run periodically (every 15 min).
    """
    now = _utcnow()
    
    # Find persons with expired strikes
    expired_person_ids = await db.strikes.distinct(
        "person_id",
        {"expires_at": {"$lte": now}}
    )
    
    # Delete expired strikes
    result = await db.strikes.delete_many({"expires_at": {"$lte": now}})
    
    if result.deleted_count > 0:
        logger.info(f"🧹 Cleaned {result.deleted_count} expired strikes")
    
    # Update active_strikes count for affected persons
    from popularoo_index import get_strike_level
    for pid in expired_person_ids:
        active = await _count_active_strikes(db, pid)
        emoji, label = get_strike_level(active)
        await db.persons.update_one(
            {"_id": pid},
            {"$set": {
                "active_strikes": active,
                "strike_emoji": emoji if emoji else None,
                "strike_label": label if label else None,
            }}
        )


async def _send_strike_emails(db, email_service, person_id: ObjectId, active_count: int, prev_count: int):
    """
    Send strike milestone emails when thresholds are crossed.
    - Email 3a (Going Viral): active_count crosses from <4 to >=4
    - Email 3b (Legend Mode): active_count crosses from <5 to >=5
    Includes a 6h cooldown to avoid duplicate sends.
    """
    try:
        from email_sender import send_strike_going_viral, send_strike_legend_mode
        now = _utcnow()

        # Find the outsider's active boost to get email
        boost = await db.active_boosts.find_one({
            "person_id": person_id,
            "end_time": {"$gt": now},
        })
        if not boost or not boost.get("email"):
            return  # No email → skip silently

        # Skip email if outsider is suspended
        person = await db.persons.find_one({"_id": person_id})
        if person and person.get("suspended"):
            return  # Suspended → skip emails silently

        email = boost["email"]
        user_id = boost.get("user_id", "")
        person = await db.persons.find_one({"_id": person_id})
        name = person.get("name", "User") if person else "User"

        # Email 3b: Legend Mode (5+ strikes) — check this first (higher priority)
        if active_count >= 5 and prev_count < 5:
            # Cooldown check: don't send if already sent in last 6h
            recent = await db.admin_notifications.find_one({
                "type": "strike_email_sent",
                "person_id": person_id,
                "email_type": "legend_mode",
                "timestamp": {"$gte": now - timedelta(hours=6)},
            })
            if not recent:
                await send_strike_legend_mode(db, email_service, email, user_id, name)
                await db.admin_notifications.insert_one({
                    "type": "strike_email_sent",
                    "person_id": person_id,
                    "email_type": "legend_mode",
                    "timestamp": now,
                })
                logger.info(f"📧 Legend Mode email sent to {email} for {name}")

        # Email 3a: Going Viral (4 strikes) — only if not already at Legend Mode
        elif active_count >= 4 and prev_count < 4:
            recent = await db.admin_notifications.find_one({
                "type": "strike_email_sent",
                "person_id": person_id,
                "email_type": "going_viral",
                "timestamp": {"$gte": now - timedelta(hours=6)},
            })
            if not recent:
                await send_strike_going_viral(db, email_service, email, user_id, name)
                await db.admin_notifications.insert_one({
                    "type": "strike_email_sent",
                    "person_id": person_id,
                    "email_type": "going_viral",
                    "timestamp": now,
                })
                logger.info(f"📧 Going Viral email sent to {email} for {name}")

    except Exception as e:
        logger.warning(f"Failed to send strike email: {e}")


async def ensure_strike_indexes(db):
    """Create MongoDB indexes for efficient strike queries."""
    await db.strikes.create_index([("person_id", 1), ("expires_at", 1)])
    await db.strikes.create_index([("person_id", 1), ("type", 1), ("expires_at", 1)])
    await db.strikes.create_index([("expires_at", 1)])  # For cleanup job
    logger.info("⚡ Strike indexes ensured")
