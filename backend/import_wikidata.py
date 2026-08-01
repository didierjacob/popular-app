"""
Étape 2 (import Wikidata) — IMPORT dans persons. Dry-run par défaut.

Lit `wikidata_candidates.json` (produit par fetch_wikidata.py) et insère des fiches
persons NEUVES (import purement additif, tag source="wikidata_import").

⚠️  --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.

Traitements :
  • MINEURS EXCLUS : si P569 (naissance) présent et âge < 18 → exclu (listé).
    Âge inconnu (P569 absent) → INCLUS, mais listé pour info.
  • DÉDUP : skip si wikidata_id déjà en base, OU find_existing_person
    (name_normalized indexé) OU slug déjà présent. Idempotent.
  • ZÉRO vote fake : likes=dislikes=total_votes=superlikes=0, approved=true, visible.
  • Indice PROVISOIRE depuis sitelinks (échelle log 0-100, comparable à
    popularity_external_score) → affiné par le job quotidien pageviews sous 24h.
  • Champs wiki laissés vides (wiki_langs=[], wiki_score_brut=0) : le job les remplit.

ROLLBACK : suppression par tag → db.persons.delete_many({"source":"wikidata_import"})
(+ leurs person_ticks). Import additif et étiqueté → pas de snapshot requis.

Usage (Render Shell, APRÈS fetch_wikidata.py) :
    cd /opt/render/project/src/backend
    python import_wikidata.py            # DRY-RUN (défaut)
    python import_wikidata.py --apply    # écrit, après lecture du dry-run
"""
import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode

# Calculs PARTAGÉS avec l'ajout à la demande (cf. wikidata_common.py) : indice de
# départ et lecture de P569 identiques des deux côtés, par construction.
from wikidata_common import SITELINKS_REF, age_from_birth, provisional_score  # noqa: F401

CANDIDATES_FILE = "wikidata_candidates.json"
BATCH = 50               # lots d'insertion (--apply)
CATEGORY_SOFT_CAP = 0.35 # info dry-run : aucune catégorie ne devrait dépasser 35%

# Panel code → primary_country ISO-2 (identité sauf UK→GB, convention app).
CC_MAP = {"UK": "GB"}


def slugify(name: str) -> str:
    s = unidecode(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def normalize_person_name(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


async def find_existing(db, name, slug):
    nn = normalize_person_name(name)
    if nn:
        doc = await db.persons.find_one({"name_normalized": nn}, {"_id": 1})
        if doc:
            return "name_normalized"
    if slug and await db.persons.find_one({"slug": slug}, {"_id": 1}):
        return "slug"
    return None


async def main():
    parser = argparse.ArgumentParser(description="Import Wikidata dans persons.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Écriture réelle.")
    args = parser.parse_args()
    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]
    now = datetime.now(timezone.utc)

    if not os.path.exists(CANDIDATES_FILE):
        print(f"⛔ {CANDIDATES_FILE} introuvable — lance d'abord fetch_wikidata.py")
        return
    blob = json.load(open(CANDIDATES_FILE, encoding="utf-8"))
    records = blob["records"]
    print(f"🌍 [IMPORT WIKIDATA] base='{db_name}' — mode: {mode}")
    print(f"   {len(records)} candidats (topk={blob.get('topk')} floor={blob.get('floor')})\n")

    # alpha VERROUILLÉ à 1.0 (garde-fou « cœur honnête », cf. popularoo_index.get_alpha) :
    # indice provisoire = 1.0 × score externe. La valeur stockée en base est ignorée.
    alpha = 1.0

    to_insert = []
    minors = []          # âge < 18 avéré → exclus
    age_unknown = []     # P569 absent → inclus mais listés
    skipped = Counter()  # raisons de skip (déjà présent)
    seen_nn = set()      # dédup interne au lot

    for r in records:
        name = r["name"]
        wdid = r["wikidata_id"]
        slug = slugify(name)
        nn = normalize_person_name(name)

        # ── Filtre mineur ──
        age, known = age_from_birth(r.get("birth"), now)
        if known and age < 18:
            minors.append((name, age, r["country"]))
            continue
        if not known:
            age_unknown.append((name, r["country"]))

        # ── Dédup base : wikidata_id d'abord ──
        if await db.persons.find_one({"wikidata_id": wdid}, {"_id": 1}):
            skipped["wikidata_id"] += 1
            continue
        reason = await find_existing(db, name, slug)
        if reason:
            skipped[reason] += 1
            continue
        # dédup interne au lot (2 pays, même personne échappée à seen)
        if nn in seen_nn:
            skipped["intra_batch"] += 1
            continue
        seen_nn.add(nn)

        prov = provisional_score(r["sitelinks"])
        pi = round(alpha * prov, 2)
        pc = CC_MAP.get(r["country"], r["country"])
        to_insert.append({
            "name": name,
            "name_normalized": nn,
            "slug": slug,
            "category": r["category"],
            "source": "wikidata_import",
            "wikidata_id": wdid,
            "wiki_langs": [],
            "wiki_score_brut": 0,
            "wiki_score_norm": prov,
            "popularity_external_score": prov,
            "popularoo_index": pi,
            "score": pi,
            "initial_pi": pi,
            "primary_country": pc,
            "country_tags": [pc, "international"],
            "likes": 0, "dislikes": 0, "total_votes": 0, "superlikes": 0,
            "approved": True,
            "visible_in_rankings": True,
            "created_at": now,
            "updated_at": now,
            "_sitelinks": r["sitelinks"],  # debug (retiré avant insert)
        })

    # ── Rapport ──
    print("=" * 66)
    print(f"  NET À IMPORTER            : {len(to_insert)}")
    print(f"  Déjà présents (skippés)   : {sum(skipped.values())}  "
          f"({', '.join(f'{k}={v}' for k, v in skipped.items()) or '—'})")
    print(f"  Mineurs exclus (<18)      : {len(minors)}")
    print(f"  Âge inconnu (P569 absent) : {len(age_unknown)}  (inclus)")
    print("=" * 66)

    cat = Counter(d["category"] for d in to_insert)
    pays = Counter(d["primary_country"] for d in to_insert)
    tot = max(1, len(to_insert))
    print("\n  Répartition CATÉGORIE :")
    for c, n in cat.most_common():
        flag = "  ⚠️ > cap" if n / tot > CATEGORY_SOFT_CAP else ""
        print(f"     {c:<10}: {n:>3}  ({100*n/tot:4.1f}%){flag}")
    print("\n  Répartition PAYS :")
    print("     " + "  ".join(f"{c}={n}" for c, n in sorted(pays.items(), key=lambda kv: -kv[1])))

    if minors:
        print(f"\n  Mineurs exclus : " + "; ".join(f"{n} ({a} ans, {c})" for n, a, c in minors[:20]))
    if age_unknown:
        print(f"\n  Âge inconnu (échantillon) : " + "; ".join(f"{n} ({c})" for n, c in age_unknown[:20]))

    print("\n  Échantillon (20) :")
    for d in sorted(to_insert, key=lambda x: -x["_sitelinks"])[:20]:
        print(f"     [{d['category']:<9} {d['primary_country']}] {d['name']}  "
              f"sitelinks={d['_sitelinks']}  index_prov={d['popularoo_index']}")

    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture. Pour importer : relancer avec --apply")
        return

    # ── APPLY : insertion par lots ──
    print(f"\n✍️  APPLY : insertion de {len(to_insert)} fiches par lots de {BATCH}...")
    inserted = 0
    for i in range(0, len(to_insert), BATCH):
        chunk = to_insert[i:i + BATCH]
        docs = [{k: v for k, v in d.items() if k != "_sitelinks"} for d in chunk]
        res = await db.persons.insert_many(docs)
        # ticks initiaux
        await db.person_ticks.insert_many([
            {"person_id": oid, "score": docs[j]["score"],
             "total_votes": 0, "created_at": now}
            for j, oid in enumerate(res.inserted_ids)
        ])
        inserted += len(res.inserted_ids)
        print(f"    lot {i//BATCH + 1} : +{len(res.inserted_ids)} (total {inserted})")

    print(f"\n✅ Import terminé : {inserted} fiches source='wikidata_import'.")
    print("   Rollback : db.persons.delete_many({'source':'wikidata_import'}) + person_ticks associés.")
    print("   Le job quotidien (03:00 UTC) affinera les scores sous 24h.")


if __name__ == "__main__":
    asyncio.run(main())
