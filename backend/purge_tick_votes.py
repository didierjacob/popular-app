"""
Cœur honnête — RÉSIDU 2 : retire le total_votes fake des person_ticks des CÉLÉBRITÉS.
Dry-run par défaut.

Les ticks des célébrités (créés au seeding) portent encore un `total_votes` fake, lu
uniquement par /people/{id}/votes-chart (masqué par show_vote_counts=False). Ce script
fait `$unset total_votes` sur ces ticks → le votes-chart retombe sur person.total_votes
(=0 après la purge des compteurs). Le champ `score` du tick (courbe de score) est PRÉSERVÉ.

Cible : ticks dont le person_id est une CÉLÉBRITÉ
    NON-outsider (source≠self_boosted, category≠outsider, is_outsider≠True)
    ET NON-user_search (source ∉ {user_search, user_search_confirmed})
et qui possèdent un champ total_votes.

⚠️  GARDE-FOUS :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.
  • SELF-BACKUP AVANT écriture (tick _id + total_votes d'origine) → rollback.
  • Ne touche NI aux ticks Outsiders/user_search, NI au champ score.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python purge_tick_votes.py                          # DRY-RUN
    python purge_tick_votes.py --apply                  # $unset total_votes (backup auto)
    python purge_tick_votes.py --rollback <backup.json> # restaure total_votes
"""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

USER_SEARCH_SOURCES = {"user_search", "user_search_confirmed"}


def is_celebrity(d):
    if (d.get("source") == "self_boosted" or d.get("category") == "outsider"
            or d.get("is_outsider") is True):
        return False
    if d.get("source") in USER_SEARCH_SOURCES:
        return False
    return True


async def do_rollback(db, path):
    if not os.path.exists(path):
        print(f"⛔ Backup introuvable : {path}")
        return
    backup = json.load(open(path, encoding="utf-8"))
    restored = 0
    for rec in backup["records"]:
        await db.person_ticks.update_one(
            {"_id": ObjectId(rec["tick_id"])},
            {"$set": {"total_votes": rec["total_votes"]}},
        )
        restored += 1
    print(f"✅ {restored} ticks restaurés depuis {path}.")


async def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--rollback", metavar="FICHIER")
    args = parser.parse_args()

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]

    if args.rollback:
        await do_rollback(db, args.rollback)
        return

    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"
    print(f"🧹 [PURGE TICKS célébrités] base='{db_name}' — mode: {mode}\n")

    # 1) _id des célébrités
    celeb_ids = set()
    async for d in db.persons.find({}, {"source": 1, "category": 1, "is_outsider": 1}):
        if is_celebrity(d):
            celeb_ids.add(d["_id"])
    print(f"  Célébrités (persons) : {len(celeb_ids)}")

    # 2) ticks de ces célébrités qui portent total_votes
    affected = []
    async for tk in db.person_ticks.find(
        {"person_id": {"$in": list(celeb_ids)}, "total_votes": {"$exists": True}},
        {"person_id": 1, "total_votes": 1},
    ):
        affected.append(tk)

    print("=" * 60)
    print(f"  Ticks célébrités avec total_votes : {len(affected)}")
    print("=" * 60)
    if not affected:
        print("\n✅ Aucun tick à nettoyer.")
        return

    nonzero = sum(1 for t in affected if int(t.get("total_votes", 0) or 0) > 0)
    print(f"  dont total_votes > 0 : {nonzero}")
    print("  échantillon (10) :", [int(t.get("total_votes", 0) or 0) for t in affected[:10]])

    # ── SELF-BACKUP ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"tick_votes_backup_{stamp}.json"
    records = [{"tick_id": str(t["_id"]), "total_votes": t.get("total_votes")} for t in affected]
    json.dump({"created_at": stamp, "db_name": db_name, "count": len(records), "records": records},
              open(backup_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\n  💾 Backup : ./{backup_path} ({len(records)} ticks)")

    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture. Pour nettoyer : --apply")
        print(f"   Rollback ensuite : python purge_tick_votes.py --rollback {backup_path}")
        return

    print("\n✍️  APPLY : $unset total_votes en cours...")
    ids = [t["_id"] for t in affected]
    res = await db.person_ticks.update_many(
        {"_id": {"$in": ids}}, {"$unset": {"total_votes": ""}}
    )
    print(f"   {res.modified_count} ticks nettoyés (total_votes retiré ; score préservé).")
    print(f"\n✅ Terminé. Rollback : python purge_tick_votes.py --rollback {backup_path}")


if __name__ == "__main__":
    asyncio.run(main())
