"""
Étape 1 (chantier accents/slugs) — BACKFILL de `name_normalized` sur `persons`.

But : doter CHAQUE fiche d'une clé canonique accent-insensible stockée
`name_normalized = unidecode(name)` (minuscules, espaces normalisés), pour que
toute la dédup (création, détection, IMPORT Wikidata à venir) repose dessus,
indépendamment des slugs historiques incohérents. On NE touche PAS aux slugs,
ni au `name` affiché (on garde "Rosalía" à l'écran).

⚠️  MODE PAR DÉFAUT = DRY-RUN (LECTURE SEULE). Il compte et échantillonne ce qui
    SERAIT modifié, sans rien écrire. L'écriture réelle exige le flag explicite
    --apply, et ne doit être lancée QU'APRÈS une sauvegarde MongoDB (snapshot Atlas).

Usage :
    cd backend
    # 1) Lecture seule (montre l'ampleur, n'écrit rien) :
    MONGO_URL="<atlas-uri>" DB_NAME="popular_production" python3 backfill_name_normalized.py --dry-run
    # 2) Écriture réelle (SEULEMENT après snapshot Atlas) :
    MONGO_URL="<atlas-uri>" DB_NAME="popular_production" python3 backfill_name_normalized.py --apply
"""
import argparse
import asyncio
import os
import re

from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode


def normalize_key(name: str) -> str:
    """MÊME logique que server.normalize_person_name + normalisation des espaces."""
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


async def main():
    parser = argparse.ArgumentParser(description="Backfill name_normalized sur persons.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Lecture seule (défaut). N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Écriture réelle (après snapshot Atlas uniquement).")
    args = parser.parse_args()

    # Sécurité : par défaut on est en dry-run. --apply doit être EXPLICITE.
    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🧩 [BACKFILL name_normalized] base='{db_name}' — mode: {mode}\n")

    total = 0
    missing = []   # pas de champ name_normalized
    stale = []     # champ présent mais != valeur canonique
    ok = 0
    empty_name = 0

    cursor = db.persons.find({}, {"name": 1, "name_normalized": 1})
    async for doc in cursor:
        total += 1
        desired = normalize_key(doc.get("name", ""))
        if not desired:
            empty_name += 1
            continue
        current = doc.get("name_normalized", None)
        if current is None:
            missing.append((str(doc["_id"]), doc.get("name", ""), desired))
        elif current != desired:
            stale.append((str(doc["_id"]), doc.get("name", ""), current, desired))
        else:
            ok += 1

    to_write = len(missing) + len(stale)

    print("=" * 78)
    print(f"  Total fiches persons              : {total}")
    print(f"  Déjà correct (name_normalized OK) : {ok}")
    print(f"  MANQUANT (champ absent)           : {len(missing)}")
    print(f"  INCOHÉRENT (champ ≠ canonique)    : {len(stale)}")
    print(f"  Nom vide (ignoré)                 : {empty_name}")
    print(f"  → fiches à écrire                 : {to_write}")
    print("=" * 78)

    if missing:
        print(f"\n  ── Exemples MANQUANT (max 15) ──")
        for _id, name, desired in missing[:15]:
            print(f"       - {_id}  \"{name}\"  →  name_normalized='{desired}'")
    if stale:
        print(f"\n  ── Exemples INCOHÉRENT (max 15) ──")
        for _id, name, current, desired in stale[:15]:
            print(f"       - {_id}  \"{name}\"  '{current}'  →  '{desired}'")

    # État de l'index (lecture seule).
    try:
        idx = await db.persons.index_information()
        has_idx = any(
            any(field == "name_normalized" for field, _ in spec.get("key", []))
            for spec in idx.values()
        )
        print(f"\n  Index sur name_normalized présent : {'oui' if has_idx else 'NON'}")
    except Exception as e:
        has_idx = False
        print(f"\n  (Impossible de lire les index : {e})")

    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture effectuée. Rien n'a été modifié.")
        print("   Pour écrire (APRÈS snapshot Atlas) : relancer avec --apply")
        client.close()
        return

    # ── APPLY : écriture réelle (uniquement si --apply explicite) ──
    print("\n✍️  APPLY : écriture en cours...")
    written = 0
    for _id, name, desired in missing:
        await db.persons.update_one({"_id": _to_oid(_id)}, {"$set": {"name_normalized": desired}})
        written += 1
    for _id, name, current, desired in stale:
        await db.persons.update_one({"_id": _to_oid(_id)}, {"$set": {"name_normalized": desired}})
        written += 1
    print(f"   {written} fiches mises à jour.")

    if not has_idx:
        print("   Création de l'index (non-unique) sur name_normalized...")
        await db.persons.create_index("name_normalized")
        print("   Index créé.")
    else:
        print("   Index déjà présent, rien à créer.")

    print("\n✅ Backfill APPLY terminé.")
    client.close()


def _to_oid(s):
    from bson import ObjectId
    return ObjectId(s)


if __name__ == "__main__":
    asyncio.run(main())
