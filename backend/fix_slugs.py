"""
Étape 1 (chantier accents/slugs) — FIX DATA : 2 slugs abîmés (legacy) → propres.

Répare le slug interne de 2 fiches CANONIQUES conservées, dont le slug avait été
produit par l'ancien slugify bugué (accents supprimés au lieu de translittérés) :
    69fb5a2dd6b54065503009d6  Måneskin       'mneskin'      → 'maneskin'
    69fb5a25d6b54065503009b2  Thomas Müller  'thomas-mller' → 'thomas-muller'

Rappel : le slug n'est PAS l'identité publique (ObjectId) — aucun lien partagé
n'est cassé. C'est purement cosmétique/cohérence interne.

⚠️  GARDE-FOUS :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.
  • ABORT si le slug cible ('maneskin' / 'thomas-muller') n'est PAS LIBRE
    (déjà porté par une autre fiche) → on ne crée pas de collision.
  • ABORT si le nouveau slug ≠ slugify(name) (sanity : la cible doit être le slug
    correct du nom).
  • Vérifie name_normalized (doit déjà être cohérent après le backfill).
  • N'agit QUE sur les 2 _id listés.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python fix_slugs.py            # DRY-RUN (défaut)
    python fix_slugs.py --apply    # écrit, après lecture du dry-run
"""
import argparse
import asyncio
import os
import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode

FIXES = [
    {"id": "69fb5a2dd6b54065503009d6", "name": "Måneskin",      "old": "mneskin",      "new": "maneskin"},
    {"id": "69fb5a25d6b54065503009b2", "name": "Thomas Müller", "old": "thomas-mller", "new": "thomas-muller"},
]


def slugify(name: str) -> str:
    """Miroir exact de server.slugify."""
    s = unidecode(name).strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def normalize_person_name(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


async def main():
    parser = argparse.ArgumentParser(description="Fix 2 slugs abîmés (legacy).")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Écriture réelle.")
    args = parser.parse_args()
    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🔧 [FIX SLUGS] base='{db_name}' — mode: {mode}\n")

    planned = []
    aborted = False
    for fx in FIXES:
        oid = ObjectId(fx["id"])
        doc = await db.persons.find_one({"_id": oid})
        print("=" * 72)
        if not doc:
            print(f"⛔ {fx['id']} \"{fx['name']}\" : fiche INTROUVABLE → skip")
            aborted = True
            continue

        cur_slug = doc.get("slug", "")
        expected_new = slugify(fx["name"])
        nn = doc.get("name_normalized")
        nn_expected = normalize_person_name(fx["name"])

        print(f"  {fx['id']} \"{doc.get('name','')}\"")
        print(f"     slug actuel        : '{cur_slug}'")
        print(f"     slug cible         : '{fx['new']}'  (slugify(name)='{expected_new}')")
        print(f"     name_normalized    : {nn!r}  (attendu '{nn_expected}')")

        # Sanity 1 : la cible est bien le slug correct du nom.
        if fx["new"] != expected_new:
            print(f"     ⛔ ABORT : slug cible '{fx['new']}' ≠ slugify(name) '{expected_new}'")
            aborted = True
            continue
        # Sanity 2 : slug actuel = celui attendu (sinon la base a bougé).
        if cur_slug != fx["old"]:
            print(f"     ⚠️  slug actuel '{cur_slug}' ≠ attendu '{fx['old']}' "
                  f"(déjà corrigé ? drift ?)")
            if cur_slug == fx["new"]:
                print(f"     ✅ déjà à '{fx['new']}' → rien à faire")
                continue
            print(f"     ⛔ ABORT par prudence (slug de départ inattendu)")
            aborted = True
            continue
        # Sanity 3 : le slug cible est LIBRE (aucune autre fiche).
        clash = await db.persons.find_one({"slug": fx["new"], "_id": {"$ne": oid}})
        if clash:
            print(f"     ⛔ ABORT : slug cible '{fx['new']}' DÉJÀ PORTÉ par {clash['_id']} "
                  f"\"{clash.get('name','')}\" → collision")
            aborted = True
            continue

        print(f"     ✅ cible libre, prêt : '{cur_slug}' → '{fx['new']}'")
        planned.append((oid, fx["name"], cur_slug, fx["new"]))

    print("=" * 72)
    if aborted:
        print("\n⛔ ABORT global : au moins un cas problématique. Rien n'a été écrit.")
        client.close()
        return

    print(f"\n  {len(planned)} slug(s) à corriger.")
    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture. Pour appliquer : relancer avec --apply")
        client.close()
        return

    print("\n✍️  APPLY : mise à jour des slugs...")
    for oid, name, old, new in planned:
        res = await db.persons.update_one({"_id": oid}, {"$set": {"slug": new}})
        print(f"    ✅ \"{name}\" : '{old}' → '{new}'  (modified={res.modified_count})")
    print("\n✅ FIX SLUGS terminé.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
