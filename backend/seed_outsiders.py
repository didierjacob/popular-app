"""
Chantier 1J — Seed Outsiders: Pre-created demo Outsiders for app launch.
49 seeds across 12 target countries, with automatic disable logic.

Thresholds for auto-disable (per country):
  - 20 real outsiders → disable 1 seed (least active)
  - 40 real outsiders → disable another seed
  - 60 real outsiders → disable 50% of remaining seeds
  - 100 real outsiders → disable ALL remaining seeds
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any
from bson import ObjectId

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 49 Seed Outsiders — Culturally appropriate names per country
# No professional descriptions (by design choice)
# ──────────────────────────────────────────────────────────

SEED_OUTSIDERS: List[Dict[str, Any]] = [
    # ── 🇺🇸 US (5 seeds) ──
    {"name": "Jordan Mitchell",  "country": "US", "tier": "super_booster",  "votes": 5200,  "index": 42},
    {"name": "Destiny Barnes",   "country": "US", "tier": "golden_booster", "votes": 12400, "index": 61},
    {"name": "Marcus Reed",      "country": "US", "tier": "super_booster",  "votes": 3800,  "index": 34},
    {"name": "Ava Sinclair",     "country": "US", "tier": "booster",        "votes": 1100,  "index": 19},
    {"name": "Tyler Caldwell",   "country": "US", "tier": "super_booster",  "votes": 6700,  "index": 48},

    # ── 🇫🇷 FR (5 seeds) ──
    {"name": "Léa Morin",        "country": "FR", "tier": "golden_booster", "votes": 11800, "index": 58},
    {"name": "Hugo Perrot",      "country": "FR", "tier": "super_booster",  "votes": 4500,  "index": 39},
    {"name": "Inès Fabre",       "country": "FR", "tier": "super_booster",  "votes": 7200,  "index": 50},
    {"name": "Maxime Lefèvre",   "country": "FR", "tier": "booster",        "votes": 900,   "index": 16},
    {"name": "Camille Duval",    "country": "FR", "tier": "golden_booster", "votes": 9800,  "index": 54},

    # ── 🇬🇧 GB (5 seeds) ──
    {"name": "Oscar Bennett",    "country": "GB", "tier": "super_booster",  "votes": 3400,  "index": 35},
    {"name": "Amelia Walsh",     "country": "GB", "tier": "golden_booster", "votes": 10500, "index": 56},
    {"name": "Jack Griffiths",   "country": "GB", "tier": "super_booster",  "votes": 5900,  "index": 44},
    {"name": "Freya Chapman",    "country": "GB", "tier": "booster",        "votes": 1400,  "index": 21},
    {"name": "Noah Hartley",     "country": "GB", "tier": "super_booster",  "votes": 4200,  "index": 37},

    # ── 🇩🇪 DE (5 seeds) ──
    {"name": "Lena Hoffmann",    "country": "DE", "tier": "super_booster",  "votes": 4100,  "index": 38},
    {"name": "Finn Schreiber",   "country": "DE", "tier": "golden_booster", "votes": 13200, "index": 63},
    {"name": "Mila Krause",      "country": "DE", "tier": "super_booster",  "votes": 6300,  "index": 46},
    {"name": "Jonas Baumann",    "country": "DE", "tier": "booster",        "votes": 1300,  "index": 20},
    {"name": "Emilia Vogt",      "country": "DE", "tier": "super_booster",  "votes": 7800,  "index": 51},

    # ── 🇪🇸 ES (4 seeds) ──
    {"name": "Sofía Herrera",    "country": "ES", "tier": "super_booster",  "votes": 6800,  "index": 47},
    {"name": "Pablo Navarro",    "country": "ES", "tier": "golden_booster", "votes": 10200, "index": 55},
    {"name": "Lucía Delgado",    "country": "ES", "tier": "super_booster",  "votes": 3600,  "index": 33},
    {"name": "Álvaro Ruiz",      "country": "ES", "tier": "booster",        "votes": 1500,  "index": 22},

    # ── 🇮🇹 IT (4 seeds) ──
    {"name": "Giulia Ferretti",  "country": "IT", "tier": "super_booster",  "votes": 4100,  "index": 38},
    {"name": "Alessandro Conti", "country": "IT", "tier": "golden_booster", "votes": 8900,  "index": 53},
    {"name": "Chiara Bianchi",   "country": "IT", "tier": "super_booster",  "votes": 5500,  "index": 43},
    {"name": "Marco Esposito",   "country": "IT", "tier": "booster",        "votes": 1000,  "index": 17},

    # ── 🇧🇷 BR (4 seeds) ──
    {"name": "Lucas Ferreira",   "country": "BR", "tier": "golden_booster", "votes": 9500,  "index": 52},
    {"name": "Isabela Santos",   "country": "BR", "tier": "super_booster",  "votes": 5800,  "index": 45},
    {"name": "Matheus Oliveira", "country": "BR", "tier": "super_booster",  "votes": 3200,  "index": 31},
    {"name": "Valentina Costa",  "country": "BR", "tier": "booster",        "votes": 1200,  "index": 19},

    # ── 🇨🇦 CA (4 seeds) ──
    {"name": "Ethan Campbell",   "country": "CA", "tier": "super_booster",  "votes": 4800,  "index": 40},
    {"name": "Sophie Tremblay",  "country": "CA", "tier": "golden_booster", "votes": 11200, "index": 57},
    {"name": "Liam Mackenzie",   "country": "CA", "tier": "super_booster",  "votes": 3500,  "index": 32},
    {"name": "Chloé Gagnon",     "country": "CA", "tier": "booster",        "votes": 800,   "index": 15},

    # ── 🇲🇽 MX (4 seeds) ──
    {"name": "Diego Ramírez",    "country": "MX", "tier": "super_booster",  "votes": 5100,  "index": 41},
    {"name": "Valeria Torres",   "country": "MX", "tier": "golden_booster", "votes": 8700,  "index": 52},
    {"name": "Andrés Morales",   "country": "MX", "tier": "super_booster",  "votes": 3900,  "index": 36},
    {"name": "Ximena Vega",      "country": "MX", "tier": "booster",        "votes": 700,   "index": 14},

    # ── 🇦🇷 AR (3 seeds) ──
    {"name": "Martina Lagos",    "country": "AR", "tier": "super_booster",  "votes": 4600,  "index": 39},
    {"name": "Tomás Aguirre",    "country": "AR", "tier": "golden_booster", "votes": 9100,  "index": 53},
    {"name": "Catalina Ponce",   "country": "AR", "tier": "booster",        "votes": 1100,  "index": 18},

    # ── 🇧🇪 BE (3 seeds) ──
    {"name": "Louise Claes",     "country": "BE", "tier": "super_booster",  "votes": 3700,  "index": 34},
    {"name": "Arthur Janssens",  "country": "BE", "tier": "golden_booster", "votes": 8500,  "index": 51},
    {"name": "Emma Peeters",     "country": "BE", "tier": "super_booster",  "votes": 5300,  "index": 42},

    # ── 🇨🇭 CH (3 seeds) ──
    {"name": "Noé Bonvin",       "country": "CH", "tier": "super_booster",  "votes": 4300,  "index": 37},
    {"name": "Elena Brunner",    "country": "CH", "tier": "golden_booster", "votes": 10800, "index": 56},
    {"name": "Lara Meier",       "country": "CH", "tier": "super_booster",  "votes": 6100,  "index": 45},
]


def generate_avatar_color(name: str) -> str:
    """
    Generate a deterministic hex color from a name.
    Uses Popularoo palette: deep greens, charcoal grays, with golden accents.
    """
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    # Palette of 12 Popularoo-compatible colors
    palette = [
        "#1C3A2C",  # Deep green (primary)
        "#2E6148",  # Forest green
        "#1A4A3A",  # Emerald dark
        "#3D7A5F",  # Sage green
        "#2C4A3E",  # Dark teal
        "#4A6B5D",  # Muted green
        "#1F3D2F",  # Hunter green
        "#355E4B",  # Moss green
        "#3A5A4A",  # Pine green
        "#2B5940",  # Jade dark
        "#4E6D5E",  # Fern green
        "#1E4434",  # Brunswick green
    ]
    return palette[h % len(palette)]


def get_initials(name: str) -> str:
    """Extract initials from a name (e.g., 'Jordan Mitchell' → 'JM')."""
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[0].upper()


def _generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a name."""
    import re
    slug = name.lower().strip()
    # Replace accented characters
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ô': 'o', 'ö': 'o',
        'î': 'i', 'ï': 'i',
        'ç': 'c', 'ñ': 'n', 'á': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u',
    }
    for k, v in replacements.items():
        slug = slug.replace(k, v)
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def _tier_config(tier: str) -> Dict[str, Any]:
    """Get tier configuration matching the purchase flow."""
    configs = {
        "booster": {"position": "outsiders", "duration_hours": 1, "name": "Booster"},
        "super_booster": {"position": "outsiders", "duration_hours": 24, "name": "Super Booster"},
        "golden_booster": {"position": "top", "duration_hours": 168, "name": "Golden Booster"},
    }
    return configs.get(tier, configs["booster"])


async def create_seed_outsiders(db) -> Dict[str, Any]:
    """
    Create all 49 seed Outsiders in the database.
    Idempotent: skips seeds that already exist (by name + is_seed=True).
    Returns: summary of created/skipped seeds per country.
    """
    import random
    now = datetime.utcnow()
    results = {"created": 0, "skipped": 0, "by_country": {}}

    for seed in SEED_OUTSIDERS:
        country = seed["country"]
        if country not in results["by_country"]:
            results["by_country"][country] = {"created": 0, "skipped": 0}

        # Check if seed already exists
        existing = await db.persons.find_one({
            "name": seed["name"],
            "is_seed": True,
        })
        if existing:
            results["skipped"] += 1
            results["by_country"][country]["skipped"] += 1
            continue

        # Also check collision with real celebrities
        collision = await db.persons.find_one({
            "name": seed["name"],
            "is_seed": {"$ne": True},
        })
        if collision:
            logger.warning(f"⚠️ Seed name collision with real person: {seed['name']} — skipping")
            results["skipped"] += 1
            results["by_country"][country]["skipped"] += 1
            continue

        tier_conf = _tier_config(seed["tier"])

        # Simulate vote distribution (60-70% likes)
        like_ratio = random.uniform(0.58, 0.72)
        likes = int(seed["votes"] * like_ratio)
        dislikes = seed["votes"] - likes
        score = round((likes / max(seed["votes"], 1)) * 100, 1)

        # Create person document
        person_id = ObjectId()
        person_doc = {
            "_id": person_id,
            "name": seed["name"],
            "slug": _generate_slug(seed["name"]),
            "category": "outsider",
            "approved": True,
            "is_outsider": True,
            "is_seed": True,
            "seed_active": True,
            "country_tags": [country],
            "primary_country": country,
            "score": score,
            "likes": likes,
            "dislikes": dislikes,
            "total_votes": seed["votes"],
            "seed_votes_likes": likes,
            "seed_votes_dislikes": dislikes,
            "superlikes": random.randint(0, int(seed["votes"] * 0.05)),
            "active_strikes": 0,
            "popularoo_index": float(seed["index"]),
            "base_index": float(seed["index"]),
            "avatar_initials": get_initials(seed["name"]),
            "avatar_color": generate_avatar_color(seed["name"]),
            "created_at": now - timedelta(days=random.randint(3, 14)),
            "updated_at": now,
        }
        await db.persons.insert_one(person_doc)

        # Create active_boost document (far future end_time for seeds)
        seed_end_time = now + timedelta(days=365 * 10)  # 10 years — effectively permanent
        boost_doc = {
            "person_id": person_id,
            "person_name": seed["name"],
            "user_id": f"seed_{country.lower()}_{_generate_slug(seed['name'])}",
            "email": "",
            "tier": seed["tier"],
            "position": tier_conf["position"],
            "start_time": now - timedelta(days=random.randint(1, 7)),
            "end_time": seed_end_time,
            "reminder_sent": False,
            "is_seed": True,
            "seed_active": True,
            "country": country,
            "created_at": now,
            "updated_at": now,
        }
        await db.active_boosts.insert_one(boost_doc)

        # Simulate vote history over the last 7 days
        for days_ago in range(7, 0, -1):
            tick_time = now - timedelta(days=days_ago)
            daily_votes = int(seed["votes"] / 7 * random.uniform(0.5, 1.5))
            cumulative = int(seed["votes"] * (8 - days_ago) / 8)
            await db.person_ticks.insert_one({
                "person_id": person_id,
                "score": score + random.uniform(-3, 3),
                "total_votes": cumulative,
                "timestamp": tick_time,
            })

        results["created"] += 1
        results["by_country"][country]["created"] += 1
        logger.info(f"✅ Seed created: {seed['name']} ({country}, {tier_conf['name']}, "
                    f"{seed['votes']} votes, Index {seed['index']})")

    return results


async def get_seed_status(db) -> Dict[str, Any]:
    """Get the status of seed Outsiders per country."""
    pipeline = [
        {"$match": {"is_seed": True}},
        {"$group": {
            "_id": "$country",
            "total": {"$sum": 1},
            "active": {"$sum": {"$cond": ["$seed_active", 1, 0]}},
            "disabled": {"$sum": {"$cond": ["$seed_active", 0, 1]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    results = await db.active_boosts.aggregate(pipeline).to_list(50)

    # Also count real outsiders per country
    real_pipeline = [
        {"$match": {
            "is_seed": {"$ne": True},
            "end_time": {"$gt": datetime.utcnow()},
        }},
        {"$lookup": {
            "from": "persons",
            "localField": "person_id",
            "foreignField": "_id",
            "as": "person",
        }},
        {"$unwind": "$person"},
        {"$match": {"person.is_outsider": True}},
        {"$group": {
            "_id": "$country",
            "real_count": {"$sum": 1},
        }},
    ]
    real_results = await db.active_boosts.aggregate(real_pipeline).to_list(50)
    real_map = {r["_id"]: r["real_count"] for r in real_results}

    countries = []
    for r in results:
        country = r["_id"]
        real_count = real_map.get(country, 0)
        countries.append({
            "country": country,
            "seeds_total": r["total"],
            "seeds_active": r["active"],
            "seeds_disabled": r["disabled"],
            "real_outsiders": real_count,
            "next_disable_at": _next_disable_threshold(real_count, r["active"]),
        })

    return {
        "total_seeds": sum(c["seeds_total"] for c in countries),
        "total_active": sum(c["seeds_active"] for c in countries),
        "total_disabled": sum(c["seeds_disabled"] for c in countries),
        "countries": countries,
    }


def _next_disable_threshold(real_count: int, active_seeds: int) -> str:
    """Determine when the next seed disable will trigger."""
    if active_seeds == 0:
        return "All seeds already disabled"
    if real_count < 20:
        return f"At {20} real outsiders ({20 - real_count} more needed)"
    if real_count < 40:
        return f"At {40} real outsiders ({40 - real_count} more needed)"
    if real_count < 60:
        return f"At {60} real outsiders ({60 - real_count} more needed)"
    if real_count < 100:
        return f"At {100} real outsiders ({100 - real_count} more needed)"
    return "Threshold 100 reached — all should be disabled"


async def auto_disable_seeds_for_country(db, country: str) -> Dict[str, Any]:
    """
    Check if seed Outsiders should be disabled based on real outsider count.
    Called after every real Booster purchase.

    Thresholds:
      ≥20 real → disable 1 seed
      ≥40 real → disable 1 more seed (2 total)
      ≥60 real → disable 50% of remaining seeds
      ≥100 real → disable ALL remaining seeds
    """
    now = datetime.utcnow()

    # Count real (non-seed) active outsiders in this country
    real_count = await db.active_boosts.count_documents({
        "is_seed": {"$ne": True},
        "country": country,
        "end_time": {"$gt": now},
    })

    # Count active seeds in this country
    active_seeds = await db.active_boosts.find(
        {"is_seed": True, "seed_active": True, "country": country},
        sort=[("created_at", 1)],  # oldest first (disable least active)
    ).to_list(100)

    if not active_seeds:
        return {"country": country, "real_count": real_count, "disabled": 0, "remaining": 0}

    to_disable = 0
    total_active = len(active_seeds)

    if real_count >= 100:
        to_disable = total_active  # Disable all
    elif real_count >= 60:
        # How many should have been disabled by now: 2 + ceil(50% of remaining)
        import math
        target_disabled = 2 + max(0, math.ceil((total_active) / 2))
        already_disabled = await db.active_boosts.count_documents({
            "is_seed": True, "seed_active": False, "country": country,
        })
        to_disable = max(0, target_disabled - already_disabled)
    elif real_count >= 40:
        already_disabled = await db.active_boosts.count_documents({
            "is_seed": True, "seed_active": False, "country": country,
        })
        to_disable = max(0, 2 - already_disabled)
    elif real_count >= 20:
        already_disabled = await db.active_boosts.count_documents({
            "is_seed": True, "seed_active": False, "country": country,
        })
        to_disable = max(0, 1 - already_disabled)

    # Disable the calculated number of seeds
    disabled_count = 0
    for i in range(min(to_disable, len(active_seeds))):
        seed = active_seeds[i]
        await db.active_boosts.update_one(
            {"_id": seed["_id"]},
            {"$set": {"seed_active": False, "end_time": now, "updated_at": now}}
        )
        # Also disable the person
        await db.persons.update_one(
            {"_id": seed["person_id"]},
            {"$set": {"seed_active": False, "updated_at": now}}
        )
        disabled_count += 1
        logger.info(f"🚫 Seed disabled: {seed['person_name']} ({country}) — "
                    f"{real_count} real outsiders in country")

    return {
        "country": country,
        "real_count": real_count,
        "disabled": disabled_count,
        "remaining": total_active - disabled_count,
    }


async def remove_all_seeds(db) -> Dict[str, int]:
    """Admin: Remove all seed Outsiders from the database."""
    # Get all seed person_ids
    seed_boosts = await db.active_boosts.find({"is_seed": True}).to_list(100)
    person_ids = [s["person_id"] for s in seed_boosts]

    # Delete from all collections
    boosts_deleted = await db.active_boosts.delete_many({"is_seed": True})
    persons_deleted = await db.persons.delete_many({"is_seed": True})
    ticks_deleted = await db.person_ticks.delete_many({"person_id": {"$in": person_ids}})

    return {
        "boosts_deleted": boosts_deleted.deleted_count,
        "persons_deleted": persons_deleted.deleted_count,
        "ticks_deleted": ticks_deleted.deleted_count,
    }
