"""
Apply user's manual corrections to personality_tags_v2.json before bulk import.
"""
import json
import os

json_path = "/app/backend/static/personality_tags_v2.json"
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Index by (country, name) for easy lookup
by_key = {}
for i, entry in enumerate(data):
    key = (entry["primary_country"], entry["name"])
    by_key[key] = i

corrections_applied = 0

# ==================== 1. EXCLUSIONS (mark validation = ❌) ====================
exclusions = [
    ("AR", "Diego Maradona"),
    ("BE", "Jacques Brel"),
    ("GB", "Ada Lovelace"),
    ("GB", "Queen Elizabeth II"),
    ("IT", "Giorgio Armani"),
]

for country, name in exclusions:
    key = (country, name)
    if key in by_key:
        data[by_key[key]]["validation"] = "❌"
        print(f"❌ Excluded: {name} ({country})")
        corrections_applied += 1
    else:
        print(f"⚠️ Not found for exclusion: {name} ({country})")

# ==================== 2. ADD INTERNATIONAL TAG ====================
add_international = [
    ("AR", "Anya Taylor-Joy"),
    ("BR", "Gisele Bündchen"),
    ("CA", "Jim Carrey"),
    ("CA", "Keanu Reeves"),
    ("CA", "Margaret Atwood"),
    ("CA", "Ryan Gosling"),
    ("ES", "Ana de Armas"),
    ("ES", "Penélope Cruz"),
    ("ES", "Rosalía"),
    ("FR", "Daft Punk"),
    ("FR", "Gérard Depardieu"),
    ("GB", "Daniel Craig"),
    ("GB", "David Beckham"),
    ("GB", "Harry Styles"),
    ("GB", "Idris Elba"),
    ("IT", "Giorgia Meloni"),
    ("IT", "Monica Bellucci"),
    ("IT", "Måneskin"),
    ("IT", "Sophia Loren"),
    ("MX", "Alejandro González Iñárritu"),
    ("MX", "Alfonso Cuarón"),
    ("MX", "Salma Hayek"),
    ("US", "Kim Kardashian"),
    ("US", "Michael Bloomberg"),
    ("US", "Michael Phelps"),
    ("US", "Michelle Obama"),
    ("US", "Mike Tyson"),
    ("US", "Sundar Pichai"),
]

for country, name in add_international:
    key = (country, name)
    if key in by_key:
        idx = by_key[key]
        entry = data[idx]
        entry["is_international"] = "YES"
        current_tags = [t.strip() for t in entry["tags"].split(",") if t.strip()]
        if "international" not in current_tags:
            current_tags.append("international")
        entry["tags"] = ", ".join(current_tags)
        entry["justification"] += " | Promoted to International by editor"
        print(f"🌍 International: {name} ({country})")
        corrections_applied += 1
    else:
        print(f"⚠️ Not found for international: {name} ({country})")

# ==================== 3. CATEGORY CORRECTIONS ====================
category_fixes = [
    ("BR", "Casimiro", "culture"),
    ("BR", "Roberto Carlos", "culture"),
    ("IT", "Beppe Grillo", "politics"),
    ("PK", "Malala Yousafzai", "culture"),
    ("SE", "Greta Thunberg", "culture"),
]

for country, name, new_cat in category_fixes:
    key = (country, name)
    if key in by_key:
        old_cat = data[by_key[key]]["category"]
        data[by_key[key]]["category"] = new_cat
        print(f"📂 Category: {name} ({country}): {old_cat} → {new_cat}")
        corrections_applied += 1
    else:
        print(f"⚠️ Not found for category fix: {name} ({country})")

# BTS: remove international tag
key = ("KR", "BTS")
if key in by_key:
    idx = by_key[key]
    data[idx]["is_international"] = "NO"
    current_tags = [t.strip() for t in data[idx]["tags"].split(",") if t.strip()]
    if "international" in current_tags:
        current_tags.remove("international")
    data[idx]["tags"] = ", ".join(current_tags)
    data[idx]["justification"] += " | International tag removed by editor"
    print(f"🏷️ BTS: international tag removed")
    corrections_applied += 1

# ==================== 4. GEOGRAPHIC CORRECTION ====================
key = ("CH", "Elodie Gossuin")
if key in by_key:
    idx = by_key[key]
    data[idx]["primary_country"] = "FR"
    current_tags = [t.strip() for t in data[idx]["tags"].split(",") if t.strip()]
    if "CH" in current_tags:
        current_tags.remove("CH")
    if "FR" not in current_tags:
        current_tags.insert(0, "FR")
    data[idx]["tags"] = ", ".join(current_tags)
    print(f"🗺️ Elodie Gossuin: CH → FR")
    corrections_applied += 1

# ==================== SAVE ====================
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\n{'='*50}")
print(f"✅ {corrections_applied} corrections applied to {json_path}")

intl = sum(1 for d in data if d["is_international"] == "YES" and d.get("validation") != "❌")
excl = sum(1 for d in data if d.get("validation") == "❌")
total = len(data) - excl
print(f"Total after exclusions: {total} ({excl} excluded)")
print(f"International: {intl}")
print(f"Local only: {total - intl}")
