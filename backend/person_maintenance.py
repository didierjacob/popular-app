"""
Automated maintenance jobs for personality database.

Jobs:
- Daily deceased check for top 50 via Wikidata (P570 death_date)
- Weekly deceased check for remaining personalities via Wikidata
- Weekly country tag evolution based on vote patterns

Ajustements V2:
- Wikidata P570 (structured death_date) instead of Wikipedia extract parsing
- Tag evolution threshold raised to 25% + 100 absolute minimum votes
- Daily check for top 50 Index personalities, weekly for the rest
- Active Daily Runs cancelled on deceased detection + slot returned
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
from bson import ObjectId

logger = logging.getLogger("person_maintenance")

WIKIDATA_HEADERS = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com) httpx/0.27"}

# Tag evolution thresholds (Ajustement 1)
TAG_EVOLUTION_RATIO_THRESHOLD = 0.25     # 25% of votes from a country
TAG_EVOLUTION_ABSOLUTE_MIN = 100          # Minimum 100 votes from that country
TAG_EVOLUTION_INTL_COUNTRIES = 5          # Votes from 5+ different countries
TAG_EVOLUTION_INTL_MAX_DOMINANCE = 0.70   # No single country > 70%


# ==================== WIKIDATA DECEASED CHECK (Ajustement 2) ====================

async def _check_wikidata_death(name: str, client: httpx.AsyncClient) -> Optional[str]:
    """
    Check if a person is deceased using Wikidata structured data (P570).
    Returns the death date string if deceased, None if alive.
    
    Uses Wikidata API:
    1. Search for the entity by name
    2. Fetch the entity claims
    3. Check property P570 (date of death)
    
    This is binary and unambiguous — no false positives from text parsing.
    """
    try:
        # Step 1: Search Wikidata for the entity
        search_params = {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "type": "item",
            "limit": 3,
            "format": "json",
        }
        resp = await client.get(
            "https://www.wikidata.org/w/api.php",
            params=search_params,
            headers=WIKIDATA_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("search", [])
        if not results:
            return None

        # Take the first result (most relevant match)
        entity_id = results[0].get("id")
        if not entity_id:
            return None

        # Step 2: Fetch the entity's P570 (date of death) claim
        claims_params = {
            "action": "wbgetclaims",
            "entity": entity_id,
            "property": "P570",
            "format": "json",
        }
        resp2 = await client.get(
            "https://www.wikidata.org/w/api.php",
            params=claims_params,
            headers=WIKIDATA_HEADERS,
            timeout=10,
        )
        if resp2.status_code != 200:
            return None

        claims_data = resp2.json()
        death_claims = claims_data.get("claims", {}).get("P570", [])

        if death_claims:
            # P570 exists → person is deceased
            # Extract the date value
            try:
                time_value = death_claims[0]["mainsnak"]["datavalue"]["value"]["time"]
                # time_value format: "+2024-11-28T00:00:00Z"
                return time_value
            except (KeyError, IndexError):
                return "unknown_date"

        # No P570 → person is alive
        return None

    except Exception as e:
        logger.warning(f"Wikidata check error for '{name}': {e}")
        return None


# ==================== DECEASED CHECK JOB (Ajustement 3) ====================

async def check_deceased_top50(db):
    """
    Daily job: check top 50 personalities by Index for recent deaths.
    Fast, targeted, runs every 24h.
    """
    return await _run_deceased_check(db, top_n=50, check_interval_days=1)


async def check_deceased_all(db):
    """
    Weekly job: check ALL remaining personalities for deaths.
    Broader sweep, runs every 7 days.
    """
    return await _run_deceased_check(db, top_n=None, check_interval_days=7)


async def _run_deceased_check(db, top_n: Optional[int], check_interval_days: int):
    """
    Core deceased check logic using Wikidata P570.
    
    Session 3: Detected deceased are written to deceased_queue (status: "pending")
    for admin confirmation. NO automatic deactivation.
    Admin must confirm via /api/admin/deceased/{id}/confirm before removal.
    """
    now = datetime.utcnow()
    check_cutoff = now - timedelta(days=check_interval_days)
    checked = 0
    detected = 0

    # Build query
    query_filter = {
        "approved": True,
        "source": {"$ne": "self_boosted"},
        "is_deceased": {"$ne": True},
        "$or": [
            {"deceased_checked_at": {"$exists": False}},
            {"deceased_checked_at": {"$lt": check_cutoff}},
        ],
    }

    if top_n:
        cursor = db.persons.find(query_filter).sort("popularoo_index", -1).limit(top_n)
    else:
        cursor = db.persons.find(query_filter).limit(100)

    async with httpx.AsyncClient() as client:
        async for person in cursor:
            name = person.get("name", "")
            if not name:
                continue

            death_date = await _check_wikidata_death(name, client)

            # Always update the check timestamp
            await db.persons.update_one(
                {"_id": person["_id"]},
                {"$set": {"deceased_checked_at": now}}
            )

            if death_date is not None:
                detected += 1
                logger.warning(f"⚰️ DECEASED DETECTED: {name} (death_date={death_date})")

                # Check if already in deceased_queue (pending or rejected as false_positive)
                existing = await db.deceased_queue.find_one({
                    "person_id": person["_id"],
                    "status": {"$in": ["pending", "false_positive"]},
                })
                if not existing:
                    # Write to deceased_queue for admin confirmation
                    await db.deceased_queue.insert_one({
                        "person_id": person["_id"],
                        "name": name,
                        "category": person.get("category", "other"),
                        "death_date": death_date,
                        "wikidata_id": person.get("wikidata_id"),
                        "detected_at": now,
                        "status": "pending",
                    })
                    logger.info(f"📋 Added to deceased_queue: {name}")

            checked += 1
            await asyncio.sleep(0.3)

    if checked > 0 or detected > 0:
        logger.info(f"🔍 Deceased check: {checked} checked, {detected} detected → queue "
                    f"(top_n={'all' if not top_n else top_n})")

    # Store last run summary
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$set": {
            f"last_deceased_check_{'top50' if top_n else 'all'}": {
                "timestamp": now.isoformat(),
                "checked": checked,
                "detected": detected,
            }
        }},
        upsert=True,
    )

    return {"checked": checked, "detected": detected}


async def _cancel_daily_runs_for_deceased(db, person_id: ObjectId, person_name: str, now: datetime):
    """
    Cancel all active Daily Runs where the deceased person is either
    the outsider or the target. Return Daily Run slots to outsiders.
    """
    cancelled = 0

    # Find active runs where deceased is the target
    async for run in db.daily_runs.find({
        "target_id": person_id,
        "status": "active",
    }):
        await db.daily_runs.update_one(
            {"_id": run["_id"]},
            {"$set": {
                "status": "cancelled",
                "cancelled_reason": f"Target {person_name} deceased",
                "cancelled_at": now,
            }}
        )
        cancelled += 1
        logger.info(f"🎯 Daily Run cancelled: {run.get('outsider_name')} vs {person_name} "
                    f"(target deceased) — slot returned")

    # Find active runs where deceased is the outsider
    async for run in db.daily_runs.find({
        "person_id": person_id,
        "status": "active",
    }):
        await db.daily_runs.update_one(
            {"_id": run["_id"]},
            {"$set": {
                "status": "cancelled",
                "cancelled_reason": f"Outsider {person_name} deceased",
                "cancelled_at": now,
            }}
        )
        cancelled += 1

    if cancelled > 0:
        logger.info(f"🎯 {cancelled} Daily Run(s) cancelled due to {person_name} passing")


# ==================== TAG EVOLUTION (Ajustement 1) ====================

async def evolve_country_tags(db, min_votes: int = 100):
    """
    Dynamic tag evolution: analyze vote distribution by country
    and adjust tags if significant patterns emerge.

    Thresholds (Ajustement 1):
    - 25% of votes from a new country AND minimum 100 absolute votes → add country tag
    - Votes from 5+ countries, no single country >70% → promote to International
    - Only processes persons with 100+ total votes for statistical significance
    """
    now = datetime.utcnow()
    updated = 0

    cursor = db.persons.find({
        "approved": True,
        "total_votes": {"$gte": min_votes},
    })

    async for person in cursor:
        person_id = person["_id"]
        current_tags = person.get("country_tags", [])

        # Get vote distribution by country
        pipeline = [
            {"$match": {"person_id": person_id}},
            {"$lookup": {
                "from": "user_settings",
                "localField": "device_id",
                "foreignField": "device_id",
                "as": "user_info",
            }},
            {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
            {"$group": {
                "_id": "$user_info.country",
                "vote_count": {"$sum": 1},
            }},
        ]

        country_votes: Dict[str, int] = {}
        total_country_votes = 0
        try:
            async for doc in db.votes.aggregate(pipeline):
                country = doc["_id"]
                if country:
                    country_votes[country] = doc["vote_count"]
                    total_country_votes += doc["vote_count"]
        except Exception:
            continue

        if total_country_votes < min_votes:
            continue

        # Analyze distribution
        new_tags = list(current_tags)
        changed = False

        for country, votes in country_votes.items():
            ratio = votes / total_country_votes

            # Ajustement 1: 25% ratio AND 100+ absolute votes from the country
            if (ratio >= TAG_EVOLUTION_RATIO_THRESHOLD
                    and votes >= TAG_EVOLUTION_ABSOLUTE_MIN
                    and country not in new_tags
                    and country != "international"):
                new_tags.append(country)
                changed = True
                logger.info(f"🏷️ Tag evolution: {person.get('name')} gained tag {country} "
                           f"({ratio:.0%} of votes, {votes} absolute)")

        # International promotion: 5+ countries, no single country >70%
        if len(country_votes) >= TAG_EVOLUTION_INTL_COUNTRIES and "international" not in new_tags:
            max_ratio = max(v / total_country_votes for v in country_votes.values())
            if max_ratio < TAG_EVOLUTION_INTL_MAX_DOMINANCE:
                new_tags.append("international")
                changed = True
                logger.info(f"🌍 Tag evolution: {person.get('name')} promoted to International "
                           f"(votes from {len(country_votes)} countries)")

        if changed:
            await db.persons.update_one(
                {"_id": person_id},
                {"$set": {
                    "country_tags": new_tags,
                    "tags_evolved_at": now,
                }}
            )
            updated += 1

    if updated > 0:
        logger.info(f"🏷️ Tag evolution: {updated} persons updated")

    return {"updated": updated}
