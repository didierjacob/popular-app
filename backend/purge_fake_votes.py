"""
Cœur honnête — PURGE des faux compteurs de votes sur les CÉLÉBRITÉS. Dry-run défaut.

Met à 0 les compteurs de votes (likes/dislikes/total_votes/superlikes/score) et retire
seed_votes_likes/seed_votes_dislikes, UNIQUEMENT pour les célébrités :
    NON-outsider (source≠self_boosted, category≠outsider, is_outsider≠True)
    ET NON-user_search (source ∉ {user_search, user_search_confirmed}).

Justification : α=1.0 → les votes n'entrent PAS dans l'indice ; ces compteurs sont du
faux seeding résiduel qui biaise encore les tie-breaks et réapparaîtrait si
show_vote_counts passait à True. Purge sûre (pas de vrais utilisateurs sur ces fiches).

⚠️  GARDE-FOUS :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.
  • SELF-BACKUP AVANT toute écriture : export local des valeurs d'origine (par _id
    et par champ) → point de restauration. Rollback via --rollback <fichier>.
  • Outsiders et user_search NON touchés (ces derniers via
    /admin/migrate-user-search-honest-votes).
  • Ne touche PAS aux person_ticks (historique de chart ; masqué par show_vote_counts).

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python purge_fake_votes.py                          # DRY-RUN
    python purge_fake_votes.py --apply                  # purge (après backup auto)
    python purge_fake_votes.py --rollback <backup.json> # restaure les valeurs d'origine
"""
import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

USER_SEARCH_SOURCES = {"user_search", "user_search_confirmed"}
COUNTER_FIELDS = ["likes", "dislikes", "total_votes", "superlikes",
                  "seed_votes_likes", "seed_votes_dislikes", "score"]


def is_outsider(d):
    return (d.get("source") == "self_boosted"
            or d.get("category") == "outsider"
            or d.get("is_outsider") is True)


def is_target(d):
    if is_outsider(d):
        return False
    if d.get("source") in USER_SEARCH_SOURCES:
        return False
    return any(int(d.get(f, 0) or 0) > 0 for f in
               ["likes", "dislikes", "total_votes", "superlikes",
                "seed_votes_likes", "seed_votes_dislikes"])


async def do_rollback(db, path):
    if not os.path.exists(path):
        print(f"⛔ Fichier backup introuvable : {path}")
        return
    backup = json.load(open(path, encoding="utf-8"))
    print(f"↩️  ROLLBACK depuis {path} — {len(backup['records'])} fiches...")
    restored = 0
    for rec in backup["records"]:
        await db.persons.update_one({"_id": ObjectId(rec["id"])}, {"$set": rec["before"]})
        restored += 1
    print(f"✅ {restored} fiches restaurées à leurs valeurs d'origine.")


async def main():
    parser = argparse.ArgumentParser(description="Purge des faux compteurs (célébrités).")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Purge réelle.")
    g.add_argument("--rollback", metavar="FICHIER", help="Restaure depuis un backup JSON.")
    args = parser.parse_args()

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]

    if args.rollback:
        await do_rollback(db, args.rollback)
        return

    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"
    print(f"🧹 [PURGE FAUX VOTES] base='{db_name}' — mode: {mode}\n")

    proj = {"name": 1, "source": 1, "category": 1, "is_outsider": 1,
            **{f: 1 for f in COUNTER_FIELDS}}
    targets = []
    async for d in db.persons.find({}, proj):
        if is_target(d):
            targets.append(d)

    by_source = Counter(d.get("source", "?") for d in targets)
    print("=" * 62)
    print(f"  Célébrités à purger : {len(targets)}")
    for s, n in by_source.most_common():
        print(f"     {s:<18}: {n}")
    print("=" * 62)

    if not targets:
        print("\n✅ Rien à purger.")
        return

    print("\n  Échantillon (15) :")
    for d in targets[:15]:
        print(f"     {d['_id']}  \"{d.get('name','')}\"  src={d.get('source','?')}  "
              f"likes={d.get('likes',0)} dislikes={d.get('dislikes',0)} total={d.get('total_votes',0)}")

    # ── SELF-BACKUP (valeurs d'origine) ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"fake_votes_backup_{stamp}.json"
    records = []
    for d in targets:
        before = {f: d.get(f) for f in COUNTER_FIELDS if f in d}
        records.append({"id": str(d["_id"]), "name": d.get("name", ""),
                        "source": d.get("source", ""), "before": before})
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump({"created_at": stamp, "db_name": db_name, "count": len(records),
                   "records": records}, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  💾 Backup écrit : ./{backup_path} ({len(records)} fiches, valeurs d'origine)")

    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture. Pour purger : relancer avec --apply")
        print(f"   Rollback (après --apply) : python purge_fake_votes.py --rollback {backup_path}")
        return

    # ── APPLY : mise à 0 des compteurs + retrait des seed_votes_* ──
    print("\n✍️  APPLY : purge en cours...")
    update = {"$set": {"likes": 0, "dislikes": 0, "total_votes": 0,
                       "superlikes": 0, "score": 0.0},
              "$unset": {"seed_votes_likes": "", "seed_votes_dislikes": ""}}
    purged = 0
    for d in targets:
        await db.persons.update_one({"_id": d["_id"]}, update)
        purged += 1
    print(f"   {purged} fiches purgées (compteurs = 0, seed_votes_* retirés).")
    print(f"\n✅ Purge terminée. Rollback possible : python purge_fake_votes.py --rollback {backup_path}")


if __name__ == "__main__":
    asyncio.run(main())
