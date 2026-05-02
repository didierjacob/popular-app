"""
Chantier 1B — Wikipedia-based auto-tagging for Popularoo personalities.

Queries Wikipedia API for each personality to determine:
1. Number of language versions (→ is_international if 20+)
2. Primary country based on known nationality data
3. Country tags (cumulative: can be FR + international)

Outputs a CSV file for human validation.
"""

import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tagger")

# ==================== KNOWN NATIONALITY DATABASE ====================
# Hand-verified for all 105+ personalities in the DB.
# Format: "Name" → (primary_country_code, [additional_country_codes])
# Country codes: US, FR, GB, CA, ES, MX, BR, AR, DE, IT, BE, CH, PT, IN, AU, etc.

KNOWN_NATIONALITIES = {
    # === POLITICS ===
    "Donald Trump":       ("US", []),
    "Joe Biden":          ("US", []),
    "Kamala Harris":      ("US", []),
    "Barack Obama":       ("US", []),
    "Hillary Clinton":    ("US", []),
    "Michelle Obama":     ("US", []),
    "Emmanuel Macron":    ("FR", []),
    "Vladimir Putin":     ("RU", []),
    "Xi Jinping":         ("CN", []),
    "Narendra Modi":      ("IN", []),
    "Justin Trudeau":     ("CA", []),
    "Rishi Sunak":        ("GB", []),
    "King Charles III":   ("GB", []),
    "Prince William":     ("GB", []),
    "Queen Elizabeth II":  ("GB", []),
    "Volodymyr Zelenskyy":("UA", []),
    "Ursula von der Leyen":("DE", []),
    "Olaf Scholz":        ("DE", []),
    "Giorgia Meloni":     ("IT", []),
    "Pedro Sánchez":      ("ES", []),
    "Lula da Silva":      ("BR", []),
    "Javier Milei":       ("AR", []),
    "Benjamin Netanyahu":  ("IL", []),
    "Pope Francis":       ("AR", ["IT"]),  # Born Argentina, based Vatican/Italy
    "Angela Merkel":      ("DE", []),

    # === BUSINESS ===
    "Elon Musk":          ("US", ["ZA"]),  # Born South Africa, based US
    "Jeff Bezos":         ("US", []),
    "Bill Gates":         ("US", []),
    "Mark Zuckerberg":    ("US", []),
    "Tim Cook":           ("US", []),
    "Sam Altman":         ("US", []),
    "Jensen Huang":       ("US", ["TW"]),  # Born Taiwan, based US
    "Sundar Pichai":      ("US", ["IN"]),  # Born India, based US
    "Satya Nadella":      ("US", ["IN"]),  # Born India, based US
    "Warren Buffett":     ("US", []),
    "Larry Ellison":      ("US", []),
    "Larry Page":         ("US", []),
    "Sergey Brin":        ("US", ["RU"]),  # Born Russia, based US
    "Bernard Arnault":    ("FR", []),
    "Bob Iger":           ("US", []),
    "Jack Ma":            ("CN", []),
    "Jamie Dimon":        ("US", []),
    "Michael Bloomberg":  ("US", []),
    "Reed Hastings":      ("US", []),
    "Sheryl Sandberg":    ("US", []),

    # === SPORT ===
    "Cristiano Ronaldo":  ("PT", []),
    "Lionel Messi":       ("AR", []),
    "Kylian Mbappé":      ("FR", []),
    "Neymar Jr.":         ("BR", []),
    "Erling Haaland":     ("NO", []),
    "Mohamed Salah":      ("EG", []),
    "LeBron James":       ("US", []),
    "Stephen Curry":      ("US", []),
    "Kevin Durant":       ("US", []),
    "Patrick Mahomes":    ("US", []),
    "Tom Brady":          ("US", []),
    "Serena Williams":    ("US", []),
    "Naomi Osaka":        ("JP", ["US"]),
    "Simone Biles":       ("US", []),
    "Usain Bolt":         ("JM", []),
    "Roger Federer":      ("CH", []),
    "Rafael Nadal":       ("ES", []),
    "Novak Djokovic":     ("RS", []),
    "Max Verstappen":     ("NL", ["BE"]),
    "Lewis Hamilton":     ("GB", []),
    "Tiger Woods":        ("US", []),
    "Conor McGregor":     ("IE", []),
    "Mike Tyson":         ("US", []),
    "Michael Phelps":     ("US", []),
    "Virat Kohli":        ("IN", []),

    # === CULTURE (Music, Film, TV, etc.) ===
    "Taylor Swift":       ("US", []),
    "Beyoncé":            ("US", []),
    "Rihanna":            ("BB", []),  # Barbados
    "Lady Gaga":          ("US", []),
    "Adele":              ("GB", []),
    "Drake":              ("CA", []),
    "Ed Sheeran":         ("GB", []),
    "Billie Eilish":      ("US", []),
    "Bad Bunny":          ("PR", []),  # Puerto Rico
    "Dua Lipa":           ("GB", ["AL"]),  # Albanian-British
    "Ariana Grande":      ("US", []),
    "The Weeknd":         ("CA", []),
    "Justin Bieber":      ("CA", []),
    "Kanye West":         ("US", []),
    "Bruno Mars":         ("US", []),
    "Shakira":            ("CO", []),
    "BTS":                ("KR", []),
    "Leonardo DiCaprio":  ("US", []),
    "Tom Cruise":         ("US", []),
    "Tom Hanks":          ("US", []),
    "Robert Downey Jr.":  ("US", []),
    "Scarlett Johansson":  ("US", []),
    "Dwayne Johnson":     ("US", []),
    "Jennifer Lawrence":  ("US", []),
    "Chris Hemsworth":    ("AU", []),
    "Meryl Streep":       ("US", []),
    "Denzel Washington":  ("US", []),
    "Brad Pitt":          ("US", []),
    "Angelina Jolie":     ("US", []),
    "Zendaya":            ("US", []),
    "Oprah Winfrey":      ("US", []),
    "Greta Thunberg":     ("SE", []),
    "Malala Yousafzai":   ("PK", ["GB"]),
    "Ada Lovelace":       ("GB", []),
}

# Countries in Popularoo's launch scope
LAUNCH_COUNTRIES = {"FR", "GB", "US", "CA", "ES", "MX", "BR", "AR", "DE", "IT", "BE", "CH"}

# Threshold for "international" status
INTERNATIONAL_LANGLINKS_THRESHOLD = 20


async def fetch_wikipedia_langlinks(name: str, client: httpx.AsyncClient) -> Tuple[int, List[str]]:
    """
    Query Wikipedia API to get the number of language versions for a personality.
    Returns (langlinks_count, list_of_language_codes).
    """
    try:
        params = {
            "action": "query",
            "titles": name,
            "prop": "langlinks",
            "lllimit": "500",
            "format": "json",
        }
        headers = {
            "User-Agent": "Popularoo/1.0 (contact@popularoo.com) httpx/0.27",
        }
        resp = await client.get("https://en.wikipedia.org/w/api.php", params=params, headers=headers, timeout=15)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        
        for page_id, page_data in pages.items():
            if page_id == "-1":
                # Page not found, try with different formatting
                return 0, []
            langlinks = page_data.get("langlinks", [])
            langs = [ll.get("lang", "") for ll in langlinks]
            return len(langs), langs
        
        return 0, []
    except Exception as e:
        logger.warning(f"Wikipedia API error for '{name}': {e}")
        return 0, []


async def fetch_wikipedia_extract(name: str, client: httpx.AsyncClient) -> str:
    """Fetch short extract from Wikipedia for category justification."""
    try:
        params = {
            "action": "query",
            "titles": name,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "exsentences": 2,
            "format": "json",
        }
        resp = await client.get("https://en.wikipedia.org/w/api.php", params=params, timeout=15)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return ""
            return page_data.get("extract", "")
        
        return ""
    except Exception as e:
        logger.warning(f"Wikipedia extract error for '{name}': {e}")
        return ""


def determine_tags(name: str, langlinks_count: int, known_nat: Optional[Tuple]) -> Dict:
    """
    Determine country tags for a personality.
    
    Rules:
    - If 20+ Wikipedia language versions → is_international = True, add "international" tag
    - Primary country from KNOWN_NATIONALITIES
    - Additional countries from KNOWN_NATIONALITIES
    - All launch-scope countries where the person is known get tagged
    """
    tags = []
    primary_country = None
    is_international = langlinks_count >= INTERNATIONAL_LANGLINKS_THRESHOLD
    
    if known_nat:
        primary_country = known_nat[0]
        tags.append(primary_country)
        for extra in known_nat[1]:
            if extra not in tags:
                tags.append(extra)
    
    if is_international:
        tags.append("international")
    
    return {
        "country_tags": tags,
        "primary_country": primary_country,
        "is_international": is_international,
        "langlinks_count": langlinks_count,
    }


async def run_tagging():
    """Main tagging process: query Wikipedia for all personalities and generate CSV."""
    
    # Connect to DB
    client_mongo = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client_mongo[os.getenv("DB_NAME", "test_database")]
    
    # Fetch all non-outsider approved personalities
    persons = []
    async for p in db.persons.find({
        "source": {"$ne": "self_boosted"},
        "approved": True,
    }).sort("name", 1):
        persons.append(p)
    
    logger.info(f"Found {len(persons)} personalities to tag")
    
    results = []
    
    async with httpx.AsyncClient() as http_client:
        for i, person in enumerate(persons):
            name = person.get("name", "")
            category = person.get("category", "other")
            
            # Query Wikipedia
            langlinks_count, langs = await fetch_wikipedia_langlinks(name, http_client)
            
            # If no result, try common alternate names
            if langlinks_count == 0:
                alt_names = {
                    "Neymar Jr.": "Neymar",
                    "King Charles III": "Charles III",
                    "Queen Elizabeth II": "Elizabeth II",
                    "BTS": "BTS (band)",
                    "The Weeknd": "The Weeknd",
                    "Lula da Silva": "Luiz Inácio Lula da Silva",
                    "Bad Bunny": "Bad Bunny",
                    "Pope Francis": "Pope Francis",
                    "Prince William": "William, Prince of Wales",
                }
                alt = alt_names.get(name)
                if alt and alt != name:
                    langlinks_count, langs = await fetch_wikipedia_langlinks(alt, http_client)
            
            # Determine tags
            known_nat = KNOWN_NATIONALITIES.get(name)
            tag_info = determine_tags(name, langlinks_count, known_nat)
            
            # Build justification string
            justification_parts = []
            if langlinks_count > 0:
                justification_parts.append(f"{langlinks_count} Wikipedia languages")
            if known_nat:
                justification_parts.append(f"Known nationality: {known_nat[0]}")
            if tag_info["is_international"]:
                justification_parts.append("International (20+ langs)")
            justification = " | ".join(justification_parts) if justification_parts else "No Wikipedia data"
            
            result = {
                "name": name,
                "category": category,
                "primary_country": tag_info["primary_country"] or "??",
                "country_tags": ", ".join(tag_info["country_tags"]),
                "is_international": "YES" if tag_info["is_international"] else "NO",
                "langlinks_count": langlinks_count,
                "justification": justification,
                "validation": "",  # Empty for human review
                "person_id": str(person["_id"]),
            }
            results.append(result)
            
            logger.info(f"[{i+1}/{len(persons)}] {name}: {tag_info['country_tags']} "
                        f"({langlinks_count} langs, international={tag_info['is_international']})")
            
            # Respect Wikipedia rate limits (be nice)
            await asyncio.sleep(0.3)
    
    # Write CSV
    csv_path = "/app/backend/static/personality_tags.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "category", "primary_country", "country_tags",
            "is_international", "langlinks_count", "justification", "validation", "person_id"
        ])
        writer.writeheader()
        writer.writerows(results)
    
    logger.info(f"\n✅ CSV written to {csv_path}")
    logger.info(f"Total: {len(results)} personalities tagged")
    
    # Also write JSON for easy import
    json_path = "/app/backend/static/personality_tags.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ JSON written to {json_path}")
    
    # Print summary statistics
    international_count = sum(1 for r in results if r["is_international"] == "YES")
    no_country = sum(1 for r in results if r["primary_country"] == "??")
    by_country = {}
    for r in results:
        pc = r["primary_country"]
        by_country[pc] = by_country.get(pc, 0) + 1
    
    print(f"\n{'='*60}")
    print(f"TAGGING SUMMARY")
    print(f"{'='*60}")
    print(f"Total personalities:  {len(results)}")
    print(f"International:        {international_count}")
    print(f"No country assigned:  {no_country}")
    print(f"\nBy primary country:")
    for country, count in sorted(by_country.items(), key=lambda x: -x[1]):
        flag = {"US": "🇺🇸", "FR": "🇫🇷", "GB": "🇬🇧", "CA": "🇨🇦", "ES": "🇪🇸", 
                "BR": "🇧🇷", "AR": "🇦🇷", "DE": "🇩🇪", "IT": "🇮🇹", "PT": "🇵🇹",
                "IN": "🇮🇳", "RU": "🇷🇺", "CN": "🇨🇳", "AU": "🇦🇺", "CH": "🇨🇭",
                "NL": "🇳🇱", "SE": "🇸🇪", "CO": "🇨🇴", "KR": "🇰🇷", "JP": "🇯🇵",
                "IL": "🇮🇱", "UA": "🇺🇦", "IE": "🇮🇪", "RS": "🇷🇸", "NO": "🇳🇴",
                "JM": "🇯🇲", "EG": "🇪🇬", "BB": "🇧🇧", "PK": "🇵🇰", "PR": "🇵🇷",
                "MX": "🇲🇽", "TW": "🇹🇼", "ZA": "🇿🇦", "AL": "🇦🇱",
                "??": "❓"}.get(country, "🏳️")
        print(f"  {flag} {country}: {count}")
    
    return results


async def apply_tags_to_db(json_path: str = "/app/backend/static/personality_tags.json"):
    """
    Apply validated tags from JSON file to MongoDB.
    Called after human validation.
    """
    client_mongo = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client_mongo[os.getenv("DB_NAME", "test_database")]
    
    with open(json_path, "r", encoding="utf-8") as f:
        tags_data = json.load(f)
    
    updated = 0
    for entry in tags_data:
        person_id = entry.get("person_id")
        if not person_id:
            continue
        
        country_tags = [t.strip() for t in entry["country_tags"].split(",") if t.strip()]
        is_international = entry["is_international"] == "YES"
        primary_country = entry["primary_country"] if entry["primary_country"] != "??" else None
        
        from bson import ObjectId
        result = await db.persons.update_one(
            {"_id": ObjectId(person_id)},
            {"$set": {
                "country_tags": country_tags,
                "is_international": is_international,
                "primary_country": primary_country,
            }}
        )
        if result.modified_count > 0:
            updated += 1
    
    logger.info(f"✅ Applied tags to {updated} personalities in MongoDB")
    return updated


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        # Apply validated tags
        json_path = sys.argv[2] if len(sys.argv) > 2 else "/app/backend/static/personality_tags.json"
        asyncio.run(apply_tags_to_db(json_path))
    else:
        # Generate tags
        asyncio.run(run_tagging())
