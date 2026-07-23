"""
Étape 2 (import Wikidata) — ROLLBACK par tag. Dry-run par défaut.

Annule l'import : supprime les fiches persons `source="wikidata_import"` ET leurs
person_ticks associés. L'import étant purement additif et étiqueté, ce rollback est
le filet complet (pas de snapshot requis).

⚠️  --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis pour supprimer.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python rollback_wikidata_import.py            # DRY-RUN : compte ce qui serait supprimé
    python rollback_wikidata_import.py --apply    # supprime persons + ticks associés
"""
import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

TAG = {"source": "wikidata_import"}


async def main():
    parser = argparse.ArgumentParser(description="Rollback de l'import Wikidata (par tag).")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Suppression réelle.")
    args = parser.parse_args()
    apply = bool(args.apply)
    mode = "APPLY (suppression réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]

    print(f"↩️  [ROLLBACK WIKIDATA] base='{db_name}' — mode: {mode}\n")

    total_before = await db.persons.count_documents({})
    n_import = await db.persons.count_documents(TAG)

    # _id des fiches importées (pour cibler leurs ticks).
    ids = [d["_id"] async for d in db.persons.find(TAG, {"_id": 1})]
    n_ticks = await db.person_ticks.count_documents({"person_id": {"$in": ids}}) if ids else 0

    print("=" * 60)
    print(f"  Total persons (avant)          : {total_before}")
    print(f"  Fiches source='wikidata_import': {n_import}")
    print(f"  person_ticks associés          : {n_ticks}")
    print("=" * 60)

    if n_import == 0:
        print("\n✅ Rien à annuler (aucune fiche wikidata_import).")
        return

    if not apply:
        print(f"\n🔒 DRY-RUN : aucune suppression. Supprimerait {n_import} fiches + {n_ticks} ticks.")
        print("   Pour annuler réellement : relancer avec --apply")
        return

    # ── APPLY : ticks d'abord, puis persons ──
    print("\n✍️  APPLY : suppression en cours...")
    res_ticks = await db.person_ticks.delete_many({"person_id": {"$in": ids}})
    res_persons = await db.persons.delete_many(TAG)
    total_after = await db.persons.count_documents({})

    print(f"    person_ticks supprimés : {res_ticks.deleted_count}")
    print(f"    persons supprimés      : {res_persons.deleted_count}")
    print(f"    Total persons (après)  : {total_after}")
    print("\n✅ Rollback terminé.")


if __name__ == "__main__":
    asyncio.run(main())
