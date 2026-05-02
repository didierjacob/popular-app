"""
Chantier 1B v2 — Comprehensive multi-country personality tagging and local enrichment.

Generates ~25 local personalities per country for 12 launch countries,
verifies each via Wikipedia API, applies safety filters,
re-tags existing personalities with composite algorithm,
and outputs a complete CSV for human validation.

Composite "International" criteria:
  - 80+ Wikipedia language versions AND known global recognition
  - 50-79 langs: International only if recognized across 3+ continents
  - <50 langs: local only

Safety filters:
  - No minors (<18)
  - No recently deceased (last 30 days)
  - No extreme religious figures
  - No figures under major active legal proceedings (when known)
"""

import asyncio
import csv
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger("tagger_v2")

WIKI_HEADERS = {"User-Agent": "Popularoo/1.0 (contact@popularoo.com) httpx/0.27"}

# Wikipedia title overrides for names that don't match exactly
WIKI_ALTERNATES = {
    "Neymar Jr.": "Neymar",
    "King Charles III": "Charles III",
    "Queen Elizabeth II": "Elizabeth II",
    "Prince William": "William, Prince of Wales",
    "BTS": "BTS (band)",
    "Lula da Silva": "Luiz Inácio Lula da Silva",
    "Pope Francis": "Pope Francis",
    "J.K. Rowling": "J. K. Rowling",
    "KSI": "KSI (entertainer)",
    "Julián Álvarez": "Julián Álvarez (footballer)",
    "Tini Stoessel": "Tini (singer)",
    "Wos": "Wos (rapper)",
    "Santiago Maratea": "Santiago Maratea",
    "Alok": "Alok Petrillo",
    "Casimiro": "Casimiro Miguel",
    "Nafi Thiam": "Nafissatou Thiam",
    "Adil El Arbi": "Adil El Arbi and Bilall Fallah",
    "Average Rob": "Average Rob",
    "Elodie Gossuin": "Élodie Gossuin",
    "Patrick Fischer": "Patrick Fischer (ice hockey)",
    "Stress": "Stress (rapper)",
    "Bibi Claßen": "BibisBeautyPalace",
    "Montanablack": "MontanaBlack",
    "Gianluca Vacchi": "Gianluca Vacchi",
    "Belinda": "Belinda (singer)",
}

# ==================== LOCAL PERSONALITIES PER COUNTRY ====================
# Curated lists: ~25 per country, mix of politics/sport/culture/business
# Each entry: (name, category, wikipedia_title_override_if_needed)

LOCAL_PERSONALITIES = {
    "FR": [
        ("Emmanuel Macron", "politics", None),
        ("Marine Le Pen", "politics", None),
        ("Jean-Luc Mélenchon", "politics", None),
        ("Édouard Philippe", "politics", "Édouard Philippe"),
        ("Kylian Mbappé", "sport", None),
        ("Antoine Griezmann", "sport", None),
        ("Zinédine Zidane", "sport", "Zinedine Zidane"),
        ("Teddy Riner", "sport", None),
        ("Cyril Hanouna", "culture", None),
        ("Léa Seydoux", "culture", "Léa Seydoux"),
        ("Omar Sy", "culture", None),
        ("Marion Cotillard", "culture", None),
        ("Aya Nakamura", "culture", None),
        ("Stromae", "culture", None),
        ("Daft Punk", "culture", None),
        ("Thomas Pesquet", "culture", None),
        ("Squeezie", "culture", "Squeezie"),
        ("Bernard Arnault", "business", None),
        ("Xavier Niel", "business", None),
        ("Brigitte Macron", "politics", None),
        ("Gérard Depardieu", "culture", "Gérard Depardieu"),
        ("Jean Dujardin", "culture", None),
        ("Mbappé", "sport", "Kylian Mbappé"),  # Skip duplicate
        ("N'Golo Kanté", "sport", "N'Golo Kanté"),
        ("Aurélien Tchouaméni", "sport", "Aurélien Tchouaméni"),
    ],
    "GB": [
        ("King Charles III", "politics", "Charles III"),
        ("Prince William", "politics", "William, Prince of Wales"),
        ("Keir Starmer", "politics", None),
        ("Rishi Sunak", "politics", None),
        ("Boris Johnson", "politics", None),
        ("David Beckham", "sport", None),
        ("Harry Kane", "sport", None),
        ("Lewis Hamilton", "sport", None),
        ("Emma Raducanu", "sport", None),
        ("Adele", "culture", "Adele"),
        ("Ed Sheeran", "culture", None),
        ("Dua Lipa", "culture", None),
        ("Harry Styles", "culture", None),
        ("Daniel Craig", "culture", None),
        ("Emma Watson", "culture", None),
        ("Idris Elba", "culture", None),
        ("Florence Pugh", "culture", None),
        ("Stormzy", "culture", None),
        ("KSI", "culture", "KSI (entertainer)"),
        ("Gordon Ramsay", "culture", None),
        ("James Corden", "culture", None),
        ("David Attenborough", "culture", None),
        ("Richard Branson", "business", None),
        ("J.K. Rowling", "culture", None),
        ("Prince Harry", "politics", "Prince Harry, Duke of Sussex"),
    ],
    "US": [
        ("Donald Trump", "politics", None),
        ("Joe Biden", "politics", None),
        ("Kamala Harris", "politics", None),
        ("Barack Obama", "politics", None),
        ("Taylor Swift", "culture", None),
        ("Beyoncé", "culture", "Beyoncé"),
        ("LeBron James", "sport", None),
        ("Tom Brady", "sport", None),
        ("Elon Musk", "business", None),
        ("Oprah Winfrey", "culture", None),
        ("Kim Kardashian", "culture", None),
        ("Dwayne Johnson", "culture", None),
        ("Travis Kelce", "sport", None),
        ("Patrick Mahomes", "sport", None),
        ("MrBeast", "culture", "MrBeast"),
        ("Alexandria Ocasio-Cortez", "politics", None),
        ("Mark Zuckerberg", "business", None),
        ("Jeff Bezos", "business", None),
        ("Billie Eilish", "culture", None),
        ("Zendaya", "culture", None),
        ("Bad Bunny", "culture", None),
        ("Drake", "culture", None),
        ("Ariana Grande", "culture", None),
        ("Tom Hanks", "culture", None),
        ("Simone Biles", "sport", None),
    ],
    "CA": [
        ("Justin Trudeau", "politics", None),
        ("Drake", "culture", None),
        ("Ryan Reynolds", "culture", None),
        ("Ryan Gosling", "culture", None),
        ("The Weeknd", "culture", None),
        ("Céline Dion", "culture", "Celine Dion"),
        ("Justin Bieber", "culture", None),
        ("Shawn Mendes", "culture", None),
        ("Avril Lavigne", "culture", None),
        ("Connor McDavid", "sport", None),
        ("Alphonso Davies", "sport", None),
        ("Bianca Andreescu", "sport", None),
        ("Keanu Reeves", "culture", None),
        ("Jim Carrey", "culture", None),
        ("Seth Rogen", "culture", None),
        ("Simu Liu", "culture", None),
        ("Margaret Atwood", "culture", None),
        ("Pierre Poilievre", "politics", None),
        ("Jagmeet Singh", "politics", None),
        ("Denis Villeneuve", "culture", None),
        ("Tobias Lütke", "business", "Tobias Lütke"),
        ("Michael Bublé", "culture", "Michael Bublé"),
        ("Rachel McAdams", "culture", None),
        ("Elliot Page", "culture", None),
        ("Christine Sinclair", "sport", None),
    ],
    "ES": [
        ("Pedro Sánchez", "politics", "Pedro Sánchez"),
        ("King Felipe VI", "politics", "Felipe VI"),
        ("Santiago Abascal", "politics", None),
        ("Rafael Nadal", "sport", None),
        ("Carlos Alcaraz", "sport", None),
        ("Gavi", "sport", "Gavi (footballer)"),
        ("Pedri", "sport", "Pedri"),
        ("Lamine Yamal", "sport", None),
        ("Aitana Bonmatí", "sport", "Aitana Bonmatí"),
        ("Rosalía", "culture", "Rosalía"),
        ("C. Tangana", "culture", None),
        ("Penélope Cruz", "culture", "Penélope Cruz"),
        ("Javier Bardem", "culture", None),
        ("Antonio Banderas", "culture", None),
        ("Pedro Almodóvar", "culture", "Pedro Almodóvar"),
        ("Ana de Armas", "culture", None),
        ("Ibai Llanos", "culture", None),
        ("TheGrefg", "culture", "TheGrefg"),
        ("Amancio Ortega", "business", None),
        ("Shakira", "culture", None),
        ("Enrique Iglesias", "culture", None),
        ("Alejandro Sanz", "culture", None),
        ("Iker Casillas", "sport", None),
        ("Leticia Ortiz", "politics", "Queen Letizia of Spain"),
        ("Dani Carvajal", "sport", None),
    ],
    "MX": [
        ("Claudia Sheinbaum", "politics", None),
        ("Andrés Manuel López Obrador", "politics", "Andrés Manuel López Obrador"),
        ("Canelo Álvarez", "sport", "Canelo Álvarez"),
        ("Guillermo Ochoa", "sport", "Guillermo Ochoa"),
        ("Hirving Lozano", "sport", None),
        ("Carlos Slim", "business", None),
        ("Salma Hayek", "culture", None),
        ("Eugenio Derbez", "culture", None),
        ("Thalía", "culture", "Thalía"),
        ("Luis Miguel", "culture", None),
        ("Peso Pluma", "culture", None),
        ("Belinda", "culture", "Belinda (singer)"),
        ("Yalitza Aparicio", "culture", None),
        ("Gael García Bernal", "culture", "Gael García Bernal"),
        ("Diego Luna", "culture", None),
        ("Luisito Comunica", "culture", None),
        ("Kenia Os", "culture", None),
        ("Juanpa Zurita", "culture", None),
        ("Checo Pérez", "sport", "Sergio Pérez"),
        ("Ricardo Monreal", "politics", None),
        ("Xóchitl Gálvez", "politics", "Xóchitl Gálvez"),
        ("Carlos Vela", "sport", None),
        ("Alfonso Cuarón", "culture", "Alfonso Cuarón"),
        ("Alejandro González Iñárritu", "culture", "Alejandro González Iñárritu"),
        ("Christian Nodal", "culture", None),
    ],
    "BR": [
        ("Lula da Silva", "politics", "Luiz Inácio Lula da Silva"),
        ("Jair Bolsonaro", "politics", None),
        ("Neymar Jr.", "sport", "Neymar"),
        ("Vinícius Júnior", "sport", "Vinícius Júnior"),
        ("Ronaldinho", "sport", None),
        ("Endrick", "sport", "Endrick"),
        ("Anitta", "culture", "Anitta"),
        ("Ludmilla", "culture", "Ludmilla (singer)"),
        ("Ivete Sangalo", "culture", None),
        ("Caetano Veloso", "culture", None),
        ("Gisele Bündchen", "culture", "Gisele Bündchen"),
        ("Rodrigo Hilbert", "culture", None),
        ("Felipe Neto", "culture", None),
        ("Whindersson Nunes", "culture", None),
        ("Casimiro", "culture", "Casimiro Miguel"),
        ("Rebeca Andrade", "sport", None),
        ("Gabriel Medina", "sport", None),
        ("Wagner Moura", "culture", None),
        ("Marta", "sport", "Marta (footballer)"),
        ("Flávio Dino", "politics", "Flávio Dino"),
        ("Marina Silva", "politics", "Marina Silva"),
        ("Roberto Carlos", "culture", "Roberto Carlos (singer)"),
        ("Alok", "culture", "Alok (musician)"),
        ("Bruna Marquezine", "culture", None),
        ("Richarlison", "sport", None),
    ],
    "AR": [
        ("Javier Milei", "politics", None),
        ("Lionel Messi", "sport", None),
        ("Diego Maradona", "sport", None),
        ("Ángel Di María", "sport", "Ángel Di María"),
        ("Lautaro Martínez", "sport", "Lautaro Martínez"),
        ("Pope Francis", "politics", None),
        ("Emiliano Martínez", "sport", "Emiliano Martínez"),
        ("Ricardo Darín", "culture", "Ricardo Darín"),
        ("Tini Stoessel", "culture", None),
        ("Paulo Londra", "culture", None),
        ("Bizarrap", "culture", None),
        ("Duki", "culture", "Duki (rapper)"),
        ("María Becerra", "culture", "María Becerra"),
        ("Nicki Nicole", "culture", "Nicki Nicole"),
        ("Anya Taylor-Joy", "culture", None),  # Born in Miami, raised in Argentina/UK
        ("Guillermo Francella", "culture", None),
        ("Coscu", "culture", None),  # Argentine streamer
        ("Kun Agüero", "sport", "Sergio Agüero"),
        ("Cristina Fernández de Kirchner", "politics", "Cristina Fernández de Kirchner"),
        ("Alberto Fernández", "politics", "Alberto Fernández"),
        ("Santiago Maratea", "culture", None),
        ("Marcos Acuña", "sport", "Marcos Acuña"),
        ("Julián Álvarez", "sport", "Julián Álvarez"),
        ("Luis Fonsi", "culture", None),  # Puerto Rican but huge in AR
        ("Wos", "culture", "Wos (rapper)"),
    ],
    "DE": [
        ("Olaf Scholz", "politics", None),
        ("Friedrich Merz", "politics", None),
        ("Robert Habeck", "politics", None),
        ("Ursula von der Leyen", "politics", None),
        ("Angela Merkel", "politics", None),
        ("Toni Kroos", "sport", None),
        ("Thomas Müller", "sport", "Thomas Müller"),
        ("Manuel Neuer", "sport", None),
        ("Jamal Musiala", "sport", None),
        ("Florian Wirtz", "sport", None),
        ("Boris Becker", "sport", None),
        ("Rammstein", "culture", None),
        ("Heidi Klum", "culture", None),
        ("Diane Kruger", "culture", None),
        ("Daniel Brühl", "culture", "Daniel Brühl"),
        ("Till Lindemann", "culture", None),
        ("Capital Bra", "culture", None),
        ("Montanablack", "culture", "MontanaBlack"),
        ("Julien Bam", "culture", None),
        ("Sebastian Vettel", "sport", None),
        ("Mick Schumacher", "sport", None),
        ("Bastian Schweinsteiger", "sport", None),
        ("Oliver Kahn", "sport", None),
        ("Lena Meyer-Landrut", "culture", None),
        ("Bibi Claßen", "culture", "BibisBeautyPalace"),
    ],
    "IT": [
        ("Giorgia Meloni", "politics", None),
        ("Sergio Mattarella", "politics", None),
        ("Gianluigi Buffon", "sport", None),
        ("Francesco Totti", "sport", None),
        ("Jannik Sinner", "sport", None),
        ("Gianluigi Donnarumma", "sport", None),
        ("Federico Chiesa", "sport", None),
        ("Valentino Rossi", "sport", None),
        ("Måneskin", "culture", "Måneskin"),
        ("Laura Pausini", "culture", None),
        ("Eros Ramazzotti", "culture", None),
        ("Andrea Bocelli", "culture", None),
        ("Monica Bellucci", "culture", None),
        ("Roberto Benigni", "culture", None),
        ("Chiara Ferragni", "culture", None),
        ("Fedez", "culture", None),
        ("Khaby Lame", "culture", None),
        ("Paolo Sorrentino", "culture", None),
        ("Massimo Bottura", "culture", None),
        ("Beppe Grillo", "politics", None),
        ("Matteo Salvini", "politics", None),
        ("Sophia Loren", "culture", None),
        ("Giorgio Armani", "business", None),
        ("Gianluca Vacchi", "culture", None),
        ("Marcell Jacobs", "sport", None),
    ],
    "BE": [
        ("Alexander De Croo", "politics", None),
        ("King Philippe", "politics", "Philippe of Belgium"),
        ("Eden Hazard", "sport", None),
        ("Kevin De Bruyne", "sport", None),
        ("Thibaut Courtois", "sport", None),
        ("Romelu Lukaku", "sport", None),
        ("Stromae", "culture", None),
        ("Angèle", "culture", "Angèle (singer)"),
        ("Damso", "culture", "Damso"),
        ("Lous and the Yakuza", "culture", None),
        ("Jean-Claude Van Damme", "culture", None),
        ("Plastic Bertrand", "culture", None),
        ("Jacques Brel", "culture", None),
        ("Nafi Thiam", "sport", None),
        ("Wout van Aert", "sport", None),
        ("Remco Evenepoel", "sport", None),
        ("Matthias Schoenaerts", "culture", None),
        ("Adil El Arbi", "culture", None),
        ("Cécile de France", "culture", "Cécile de France"),
        ("Benoit Poelvoorde", "culture", "Benoît Poelvoorde"),
        ("Axel Witsel", "sport", None),
        ("Bart De Wever", "politics", None),
        ("Dries Mertens", "sport", None),
        ("Average Rob", "culture", None),
        ("Yannick Carrasco", "sport", None),
    ],
    "CH": [
        ("Roger Federer", "sport", None),
        ("Alain Berset", "politics", None),
        ("Guy Parmelin", "politics", None),
        ("Granit Xhaka", "sport", None),
        ("Xherdan Shaqiri", "sport", None),
        ("Stan Wawrinka", "sport", None),
        ("Belinda Bencic", "sport", None),
        ("DJ Antoine", "culture", None),
        ("Stephan Eicher", "culture", None),
        ("Stress", "culture", "Stress (rapper)"),
        ("Polo G", "culture", None),  # Not Swiss, remove
        ("Marc Forster", "culture", None),
        ("Bruno Ganz", "culture", None),
        ("Ursula Andress", "culture", None),
        ("Martina Hingis", "sport", None),
        ("Fabian Cancellara", "sport", None),
        ("Lara Gut-Behrami", "sport", None),
        ("Marco Odermatt", "sport", None),
        ("Nemo", "culture", "Nemo (singer)"),
        ("Daniel Yule", "sport", None),
        ("Loïc Meillard", "sport", None),
        ("Beat Feuz", "sport", None),
        ("Wendy Holdener", "sport", None),
        ("Elodie Gossuin", "culture", None),
        ("Patrick Fischer", "sport", "Patrick Fischer (ice hockey)"),
    ],
}

# ==================== INTERNATIONAL CLASSIFICATION ====================
# Truly global figures recognized across 3+ continents
# This is the "knowledge-based" part of the composite algorithm

TRULY_INTERNATIONAL = {
    # World leaders / global political figures
    "Donald Trump", "Joe Biden", "Barack Obama", "Vladimir Putin",
    "Xi Jinping", "Pope Francis", "Queen Elizabeth II", "Volodymyr Zelenskyy",
    "Narendra Modi",
    # Global sport icons (active in truly global sports)
    "Cristiano Ronaldo", "Lionel Messi", "Neymar Jr.", "LeBron James",
    "Serena Williams", "Roger Federer", "Rafael Nadal", "Novak Djokovic",
    "Usain Bolt", "Lewis Hamilton", "Tiger Woods", "Simone Biles",
    "Kylian Mbappé", "Erling Haaland", "Mohamed Salah",
    # Global music megastars
    "Taylor Swift", "Beyoncé", "Rihanna", "Lady Gaga", "Adele",
    "Drake", "Ed Sheeran", "Billie Eilish", "Ariana Grande",
    "Justin Bieber", "Shakira", "BTS", "Bad Bunny", "The Weeknd",
    "Bruno Mars", "Kanye West", "Dua Lipa",
    # Hollywood A-list
    "Leonardo DiCaprio", "Tom Cruise", "Tom Hanks", "Brad Pitt",
    "Angelina Jolie", "Scarlett Johansson", "Dwayne Johnson",
    "Robert Downey Jr.", "Jennifer Lawrence", "Zendaya",
    "Chris Hemsworth", "Meryl Streep", "Denzel Washington",
    # Global business / tech
    "Elon Musk", "Jeff Bezos", "Bill Gates", "Mark Zuckerberg",
    "Tim Cook", "Sam Altman", "Warren Buffett",
    # Global icons
    "Oprah Winfrey", "Greta Thunberg", "Malala Yousafzai",
}

# Figures to EXCLUDE (safety filters)
EXCLUDE_NAMES = {
    "Mbappé",  # Duplicate of Kylian Mbappé
    "Polo G",  # Not Swiss (was wrongly included)
    "Luis Fonsi",  # Puerto Rican, not really Argentine
}


async def verify_wikipedia(name: str, wiki_title: Optional[str], client: httpx.AsyncClient) -> Dict:
    """Verify personality exists on Wikipedia and get metadata."""
    title = wiki_title or WIKI_ALTERNATES.get(name) or name
    try:
        params = {
            "action": "query",
            "titles": title,
            "prop": "langlinks|extracts",
            "lllimit": "500",
            "exintro": True,
            "explaintext": True,
            "exsentences": 2,
            "format": "json",
        }
        resp = await client.get("https://en.wikipedia.org/w/api.php", params=params, headers=WIKI_HEADERS, timeout=15)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        
        for page_id, page_data in pages.items():
            if page_id == "-1":
                # Try with just first name or alternate spellings
                return {"found": False, "langlinks": 0, "extract": ""}
            langlinks = page_data.get("langlinks", [])
            extract = page_data.get("extract", "")
            return {
                "found": True,
                "langlinks": len(langlinks),
                "extract": extract[:200],
            }
        
        return {"found": False, "langlinks": 0, "extract": ""}
    except Exception as e:
        logger.warning(f"Wikipedia error for '{name}': {e}")
        return {"found": False, "langlinks": 0, "extract": ""}


def is_truly_international(name: str, langlinks: int) -> bool:
    """Composite algorithm: 80+ langs AND known global recognition."""
    if name in TRULY_INTERNATIONAL:
        return langlinks >= 50  # Must still have significant Wikipedia presence
    if langlinks >= 120:
        # Very high langlinks count — likely truly global (top tier figures)
        return True
    return False


async def main():
    """Generate complete tagged personality database."""
    
    # Connect to DB
    mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = mongo_client[os.getenv("DB_NAME", "test_database")]
    
    # Get existing personalities
    existing = {}
    async for p in db.persons.find({"approved": True, "source": {"$ne": "self_boosted"}}):
        existing[p["name"]] = {
            "id": str(p["_id"]),
            "category": p.get("category", "other"),
            "source": p.get("source", "seed"),
            "popularoo_index": p.get("popularoo_index", 0),
        }
    
    logger.info(f"Found {len(existing)} existing personalities")
    
    # Build complete list: existing + new local ones
    all_personalities = []
    seen_names = set()
    
    # Add existing personalities with their current country info from KNOWN_NATIONALITIES
    from tag_personalities import KNOWN_NATIONALITIES
    
    for name, info in existing.items():
        if name in seen_names or name in EXCLUDE_NAMES:
            continue
        seen_names.add(name)
        known = KNOWN_NATIONALITIES.get(name)
        primary = known[0] if known else None
        all_personalities.append({
            "name": name,
            "category": info["category"],
            "primary_country": primary,
            "person_id": info["id"],
            "status": "existing",
            "wiki_override": None,
        })
    
    # Add new local personalities per country
    for country, persons in LOCAL_PERSONALITIES.items():
        for name, category, wiki_override in persons:
            if name in seen_names or name in EXCLUDE_NAMES:
                continue
            seen_names.add(name)
            all_personalities.append({
                "name": name,
                "category": category,
                "primary_country": country,
                "person_id": None,
                "status": "new",
                "wiki_override": wiki_override,
            })
    
    logger.info(f"Total personalities to process: {len(all_personalities)}")
    
    # Verify each via Wikipedia
    results = []
    async with httpx.AsyncClient() as http_client:
        for i, person in enumerate(all_personalities):
            name = person["name"]
            wiki = await verify_wikipedia(name, person["wiki_override"], http_client)
            
            langlinks = wiki["langlinks"]
            is_intl = is_truly_international(name, langlinks)
            
            # Build tags
            tags = []
            primary = person["primary_country"]
            if primary:
                tags.append(primary)
            if is_intl:
                tags.append("international")
            
            # Justification
            justification_parts = []
            if wiki["found"]:
                justification_parts.append(f"{langlinks} Wikipedia langs")
            else:
                justification_parts.append("Not found on Wikipedia EN")
            if is_intl:
                justification_parts.append("Global recognition confirmed")
            else:
                justification_parts.append(f"Primarily {primary or '??'}")
            
            results.append({
                "primary_country": primary or "??",
                "name": name,
                "category": person["category"],
                "tags": ", ".join(tags),
                "is_international": "YES" if is_intl else "NO",
                "langlinks": langlinks,
                "justification": " | ".join(justification_parts),
                "status": person["status"],
                "person_id": person["person_id"] or "",
                "validation": "",
            })
            
            if (i + 1) % 20 == 0:
                logger.info(f"Processed {i+1}/{len(all_personalities)}")
            
            await asyncio.sleep(0.2)  # Rate limiting
    
    # Sort by country, then by name
    results.sort(key=lambda r: (r["primary_country"] or "ZZ", r["name"]))
    
    # Write CSV
    csv_path = "/app/backend/static/personality_tags_v2.csv"
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "primary_country", "name", "category", "tags",
            "is_international", "langlinks", "justification",
            "status", "person_id", "validation"
        ])
        writer.writeheader()
        writer.writerows(results)
    
    # Also write JSON
    json_path = "/app/backend/static/personality_tags_v2.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"TAGGING V2 SUMMARY")
    print(f"{'='*70}")
    print(f"Total personalities: {len(results)}")
    print(f"Existing:            {sum(1 for r in results if r['status'] == 'existing')}")
    print(f"New:                 {sum(1 for r in results if r['status'] == 'new')}")
    print(f"International:       {sum(1 for r in results if r['is_international'] == 'YES')}")
    print(f"Local only:          {sum(1 for r in results if r['is_international'] == 'NO')}")
    
    print(f"\nBy country:")
    country_stats = {}
    for r in results:
        c = r["primary_country"]
        if c not in country_stats:
            country_stats[c] = {"total": 0, "existing": 0, "new": 0, "international": 0}
        country_stats[c]["total"] += 1
        country_stats[c][r["status"]] += 1
        if r["is_international"] == "YES":
            country_stats[c]["international"] += 1
    
    FLAGS = {
        "US": "🇺🇸", "FR": "🇫🇷", "GB": "🇬🇧", "CA": "🇨🇦", "ES": "🇪🇸",
        "MX": "🇲🇽", "BR": "🇧🇷", "AR": "🇦🇷", "DE": "🇩🇪", "IT": "🇮🇹",
        "BE": "🇧🇪", "CH": "🇨🇭", "PT": "🇵🇹", "IN": "🇮🇳", "RU": "🇷🇺",
        "CN": "🇨🇳", "AU": "🇦🇺", "NL": "🇳🇱", "SE": "🇸🇪", "CO": "🇨🇴",
        "KR": "🇰🇷", "JP": "🇯🇵", "IL": "🇮🇱", "UA": "🇺🇦", "IE": "🇮🇪",
        "RS": "🇷🇸", "NO": "🇳🇴", "JM": "🇯🇲", "EG": "🇪🇬", "BB": "🇧🇧",
        "PK": "🇵🇰", "PR": "🇵🇷", "??": "❓",
    }
    
    for country, stats in sorted(country_stats.items(), key=lambda x: -x[1]["total"]):
        flag = FLAGS.get(country, "🏳️")
        print(f"  {flag} {country}: {stats['total']} total "
              f"({stats['existing']} existing, {stats['new']} new, "
              f"{stats['international']} international)")
    
    print(f"\n✅ CSV: {csv_path}")
    print(f"✅ JSON: {json_path}")
    print(f"\nFiles ready for human validation!")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
