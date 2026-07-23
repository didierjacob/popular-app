"""
Cœur honnête — AUDIT READ-ONLY des faux compteurs de votes restants.

⚠️  N'ÉCRIT RIEN. Compte, par `source`, les fiches persons portant encore des
    compteurs de votes non nuls (likes/dislikes/total_votes/superlikes/seed_votes_*),
    et sépare :
      • CÉLÉBRITÉS (NON-outsider ET NON-user_search) → cible de purge_fake_votes.py
      • user_search / user_search_confirmed → traités par
        /admin/migrate-user-search-honest-votes (hors périmètre de la purge)
      • Outsiders (self_boosted / category=outsider / is_outsider) → NON touchés

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python audit_fake_votes.py
"""
import asyncio
import os
from collections import Counter, defaultdict

from motor.motor_asyncio import AsyncIOMotorClient

USER_SEARCH_SOURCES = {"user_search", "user_search_confirmed"}
COUNTER_FIELDS = ["likes", "dislikes", "total_votes", "superlikes",
                  "seed_votes_likes", "seed_votes_dislikes"]


def is_outsider(d):
    return (d.get("source") == "self_boosted"
            or d.get("category") == "outsider"
            or d.get("is_outsider") is True)


def has_counters(d):
    return any(int(d.get(f, 0) or 0) > 0 for f in COUNTER_FIELDS)


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]

    print(f"🔎 [AUDIT FAUX VOTES — READ-ONLY] base='{db_name}'\n")

    total = 0
    celeb_target = []          # célébrités avec compteurs > 0 (cible purge)
    by_source_target = Counter()
    user_search_with = 0
    outsider_with = 0
    sum_total_votes = 0

    proj = {"name": 1, "source": 1, "category": 1, "is_outsider": 1,
            **{f: 1 for f in COUNTER_FIELDS}}
    async for d in db.persons.find({}, proj):
        total += 1
        if not has_counters(d):
            continue
        if is_outsider(d):
            outsider_with += 1
        elif d.get("source") in USER_SEARCH_SOURCES:
            user_search_with += 1
        else:
            celeb_target.append(d)
            by_source_target[d.get("source", "?")] += 1
            sum_total_votes += int(d.get("total_votes", 0) or 0)

    print("=" * 64)
    print(f"  Total persons scannés                        : {total}")
    print(f"  CÉLÉBRITÉS avec faux compteurs (CIBLE PURGE) : {len(celeb_target)}")
    print(f"  user_search avec compteurs (hors purge)      : {user_search_with}")
    print(f"  Outsiders avec compteurs (NON touchés)       : {outsider_with}")
    print(f"  Somme total_votes sur la cible               : {sum_total_votes}")
    print("=" * 64)

    if by_source_target:
        print("\n  Cible par source :")
        for s, n in by_source_target.most_common():
            print(f"     {s:<18}: {n}")

    if celeb_target:
        print("\n  Échantillon cible (15) :")
        for d in celeb_target[:15]:
            print(f"     {d['_id']}  \"{d.get('name','')}\"  src={d.get('source','?')}  "
                  f"likes={d.get('likes',0)} dislikes={d.get('dislikes',0)} "
                  f"total={d.get('total_votes',0)} seed={d.get('seed_votes_likes',0)}/{d.get('seed_votes_dislikes',0)}")
    else:
        print("\n✅ Aucune célébrité ne porte de faux compteur — rien à purger.")

    print("\n(fin — aucune écriture)")


if __name__ == "__main__":
    asyncio.run(main())
