import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def check():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    cas1_slugs = [
        "donald-trump", "jeff-bezos", "zendaya", "kylian-mbappe", "billie-eilish",
        "elon-musk", "timothee-chalamet", "taylor-swift", "barack-obama", "beyonce",
        "kim-kardashian", "vladimir-putin", "justin-bieber", "leonardo-dicaprio",
        "benjamin-netanyahu", "sam-altman", "mark-zuckerberg", "xi-jinping",
        "king-charles-iii", "pope-leon-xiv",
    ]

    present = []
    absent = []
    for slug in cas1_slugs:
        doc = await db.persons.find_one({"slug": slug})
        if doc:
            ext = doc.get("popularity_external_score", "N/A")
            wl = doc.get("wiki_langs", [])
            present.append(f"  OK  {slug}  name={doc['name']}  ext={ext}  wiki_langs={wl}")
        else:
            # Try broader regex search
            keyword = slug.replace("-", " ")
            doc2 = await db.persons.find_one({"name": {"$regex": keyword, "$options": "i"}})
            if doc2:
                absent.append(f"  ABSENT  {slug}  (proche: slug={doc2.get('slug','')} name={doc2['name']})")
            else:
                absent.append(f"  ABSENT  {slug}  (aucun match)")

    print("=== PRESENTS EN BASE ===")
    for p in present:
        print(p)
    print(f"\nTotal presents: {len(present)}/20\n")

    print("=== ABSENTS ===")
    for a in absent:
        print(a)
    print(f"\nTotal absents: {len(absent)}/20")

    # Also check outsider structure
    outsider = await db.persons.find_one({"source": "self_boosted"})
    if outsider:
        print("\n=== STRUCTURE OUTSIDER ===")
        for k in sorted(outsider.keys()):
            if k != "_id":
                print(f"  {k}: {type(outsider[k]).__name__} = {repr(outsider[k])[:80]}")

    # Check an existing profile wiki_langs example
    trump = await db.persons.find_one({"slug": "donald-trump"})
    if trump:
        print(f"\n=== EXEMPLE: Donald Trump ===")
        print(f"  wiki_langs: {trump.get('wiki_langs', [])}")
        print(f"  wiki_score_brut: {trump.get('wiki_score_brut', 'N/A')}")
        print(f"  primary_country: {trump.get('primary_country', 'N/A')}")
        print(f"  dominant_language: {trump.get('dominant_language', 'N/A')}")

    client.close()

asyncio.run(check())
