"""
Cœur honnête — RÉSIDU 1 : retire la part SEED des votes des fiches user_search,
en gardant les VRAIS votes. Dry-run par défaut.

Même math que l'endpoint /admin/migrate-user-search-honest-votes, avec en plus
un dry-run + self-backup + rollback (cohérent avec nos autres purges) :
    new_likes    = max(0, likes    - seed_votes_likes)
    new_dislikes = max(0, dislikes - seed_votes_dislikes)
    total_votes  = new_likes + new_dislikes + superlikes
    seed_votes_*  = 0
    last_real_vote_at = created_at (si absent, amorce l'horloge d'érosion)

Cible : source ∈ {user_search, user_search_confirmed} avec seed_votes_* > 0.
Idempotent (une fiche déjà à seed_votes=0 est ignorée). N'ajoute JAMAIS de votes.

⚠️  GARDE-FOUS :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.
  • SELF-BACKUP AVANT écriture (valeurs d'origine par _id) → rollback via
    --rollback <fichier>.
  • Outsiders et célébrités NON touchés.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python purge_user_search_seed_votes.py                          # DRY-RUN
    python purge_user_search_seed_votes.py --apply                  # purge (backup auto)
    python purge_user_search_seed_votes.py --rollback <backup.json> # restaure
"""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

SOURCES = ["user_search", "user_search_confirmed"]
BACKUP_FIELDS = ["likes", "dislikes", "total_votes",
                 "seed_votes_likes", "seed_votes_dislikes", "last_real_vote_at"]


async def do_rollback(db, path):
    if not os.path.exists(path):
        print(f"⛔ Backup introuvable : {path}")
        return
    backup = json.load(open(path, encoding="utf-8"))
    restored = 0
    for rec in backup["records"]:
        await db.persons.update_one({"_id": ObjectId(rec["id"])}, {"$set": rec["before"]})
        restored += 1
    print(f"✅ {restored} fiches restaurées depuis {path}.")


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
    print(f"🧹 [PURGE SEED user_search] base='{db_name}' — mode: {mode}\n")

    now = datetime.now(timezone.utc)
    targets = []
    async for p in db.persons.find({"source": {"$in": SOURCES}}):
        seed_l = int(p.get("seed_votes_likes", 0) or 0)
        seed_d = int(p.get("seed_votes_dislikes", 0) or 0)
        if seed_l == 0 and seed_d == 0:
            continue  # déjà propre
        likes = int(p.get("likes", 0) or 0)
        dislikes = int(p.get("dislikes", 0) or 0)
        superlikes = int(p.get("superlikes", 0) or 0)
        new_l = max(0, likes - seed_l)
        new_d = max(0, dislikes - seed_d)
        new_total = new_l + new_d + superlikes
        targets.append({"doc": p, "seed_l": seed_l, "seed_d": seed_d,
                        "likes": likes, "dislikes": dislikes,
                        "new_l": new_l, "new_d": new_d, "new_total": new_total})

    print("=" * 62)
    print(f"  Fiches user_search avec part seed à retirer : {len(targets)}")
    print("=" * 62)
    if not targets:
        print("\n✅ Rien à purger (toutes déjà à seed_votes=0).")
        return

    print("\n  before → after (max 25) :")
    for t in targets[:25]:
        d = t["doc"]
        print(f"     \"{d.get('name','')}\"  likes {t['likes']}→{t['new_l']}  "
              f"dislikes {t['dislikes']}→{t['new_d']}  (seed retiré {t['seed_l']}/{t['seed_d']})")

    # ── SELF-BACKUP ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"user_search_seed_backup_{stamp}.json"
    records = []
    for t in targets:
        d = t["doc"]
        before = {f: d.get(f) for f in BACKUP_FIELDS if f in d}
        records.append({"id": str(d["_id"]), "name": d.get("name", ""), "before": before})
    json.dump({"created_at": stamp, "db_name": db_name, "count": len(records), "records": records},
              open(backup_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"\n  💾 Backup : ./{backup_path}")

    if not apply:
        print("\n🔒 DRY-RUN : aucune écriture. Pour purger : --apply")
        print(f"   Rollback ensuite : python purge_user_search_seed_votes.py --rollback {backup_path}")
        return

    print("\n✍️  APPLY : purge en cours...")
    n = 0
    for t in targets:
        d = t["doc"]
        set_fields = {
            "likes": t["new_l"], "dislikes": t["new_d"], "total_votes": t["new_total"],
            "seed_votes_likes": 0, "seed_votes_dislikes": 0,
        }
        if not d.get("last_real_vote_at"):
            set_fields["last_real_vote_at"] = d.get("created_at") or now
        await db.persons.update_one({"_id": d["_id"]}, {"$set": set_fields})
        n += 1
    print(f"   {n} fiches → compteurs 100% réels (seed retiré).")
    print(f"\n✅ Terminé. Rollback : python purge_user_search_seed_votes.py --rollback {backup_path}")


if __name__ == "__main__":
    asyncio.run(main())
