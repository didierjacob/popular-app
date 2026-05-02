"""
Automated maintenance jobs for personality database.
- Weekly deceased check via Wikipedia
- Dynamic tag evolution based on vote patterns
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bson import ObjectId

logger = logging.getLogger("person_maintenance")

WIKI_HEADERS = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com) httpx/0.27"}


async def check_deceased_persons(db, batch_size: int = 50):
    """
    Weekly job: check if any active personalities have passed away.
    Uses Wikipedia extracts to detect death mentions.
    If deceased, sets status to 'inactive' (respectful, no deletion).
    
    Checks in batches to respect Wikipedia rate limits.
    """
    now = datetime.utcnow()
    checked = 0
    deactivated = 0

    # Only check persons who haven't been checked recently (last 7 days)
    check_cutoff = now - timedelta(days=7)
    
    cursor = db.persons.find({
        "approved": True,
        "source": {"$ne": "self_boosted"},
        "$or": [
            {"deceased_checked_at": {"$exists": False}},
            {"deceased_checked_at": {"$lt": check_cutoff}},
        ],
        "is_deceased": {"$ne": True},
    }).limit(batch_size)

    async with httpx.AsyncClient() as client:
        async for person in cursor:
            name = person.get("name", "")
            if not name:
                continue

            try:
                params = {
                    "action": "query",
                    "titles": name,
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "exsentences": 3,
                    "format": "json",
                }
                resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params=params,
                    headers=WIKI_HEADERS,
                    timeout=10,
                )
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                
                extract = ""
                for page_id, page_data in pages.items():
                    if page_id != "-1":
                        extract = page_data.get("extract", "").lower()
                
                # Check for death indicators in the extract
                death_patterns = [
                    r"was a[n]? ",  # "was a politician" (past tense = deceased)
                    r"died\s",
                    r"\(\d{4}\s*[-–]\s*\d{4}\)",  # (1940-2024) date range
                    r"death\s",
                ]
                
                is_deceased = False
                for pattern in death_patterns:
                    if re.search(pattern, extract):
                        # Double check: "was a" is common for deceased but also for retired
                        # Confirm with date range pattern
                        has_death_date = bool(re.search(r"\(\d{4}\s*[-–]\s*\d{4}\)", extract))
                        has_was = "was a" in extract or "was an" in extract
                        
                        if has_death_date or (has_was and "died" in extract):
                            is_deceased = True
                            break
                
                update = {"$set": {"deceased_checked_at": now}}
                
                if is_deceased:
                    update["$set"]["is_deceased"] = True
                    update["$set"]["approved"] = False  # Hide from feeds
                    update["$set"]["deactivated_reason"] = "deceased"
                    update["$set"]["deactivated_at"] = now
                    deactivated += 1
                    logger.info(f"⚰️ Deactivated deceased person: {name}")
                
                await db.persons.update_one({"_id": person["_id"]}, update)
                checked += 1

            except Exception as e:
                logger.warning(f"Error checking {name}: {e}")
            
            # Rate limit: 200ms between requests
            import asyncio
            await asyncio.sleep(0.2)

    if checked > 0 or deactivated > 0:
        logger.info(f"🔍 Deceased check: {checked} checked, {deactivated} deactivated")
    
    return {"checked": checked, "deactivated": deactivated}


async def evolve_country_tags(db, min_votes: int = 50):
    """
    Dynamic tag evolution: analyze vote distribution by country
    and adjust tags if patterns emerge.
    
    Rules:
    - If 90%+ votes from one country → reinforce that country tag
    - If significant votes from new countries → add those country tags
    - If votes are globally distributed → promote to international
    
    Only processes persons with enough votes for statistical significance.
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
        
        country_votes = {}
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
            
            # If 10%+ of votes from a country not yet tagged → add tag
            if ratio >= 0.10 and country not in new_tags and country != "international":
                new_tags.append(country)
                changed = True
                logger.info(f"🏷️ Tag evolution: {person.get('name')} gained tag {country} "
                           f"({ratio:.0%} of votes)")
        
        # If votes from 5+ different countries → consider international
        if len(country_votes) >= 5 and "international" not in new_tags:
            # Check that no single country dominates >70%
            max_ratio = max(v / total_country_votes for v in country_votes.values())
            if max_ratio < 0.70:
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
