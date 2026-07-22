"""
Étape 1 (chantier accents/slugs) — BREAKDOWN des doublons, READ-ONLY.

⚠️  CE SCRIPT N'ÉCRIT RIEN. Il éclaire le chiffre "données à perdre" en séparant
    proprement, par fiche à RETIRER, TROIS natures de données très différentes :

      A. COMPTEURS DE SEED (faux) : total_votes / likes / dislikes / superlikes
         gravés sur le document persons (seeding simulé). NON comptés comme perte —
         c'est justement ce qu'on veut voir disparaître avec le doublon.

      B. HISTORIQUE INTERNE (docs possédés) : person_ticks + index_snapshots.
         Cascade-delete AVEC la fiche. Pas des données utilisateur.

      C. VRAIS DOCS UTILISATEUR : votes + vote_events + superlike_votes (lignes
         réelles). SEUL critère de sécurité : doit être 0 sur chaque fiche à retirer.
         Si > 0 → ALERTE, arrêt, revue manuelle.

      D. AUTRES MÉCANIQUES (listées si présentes) : daily_runs, bull_runs,
         active_boosts, strikes, category_reviews, deceased_queue,
         contributed_person_ids, personality_reports, outsider_reports, potd.

    Décision keep/remove : MÊME règle que plan_cleanup_duplicates
    (total_votes desc → created_at asc → wikidata → _id min).

Usage (Render Shell, MONGO_URL/DB_NAME déjà dans l'env) :
    cd /opt/render/project/src/backend
    python breakdown_cleanup.py
"""
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode


def normalize_key(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


def _fmt(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt or "")


# Catégorie C — vrais documents utilisateur (seuil de sécurité = 0).
REAL_USER_DOCS = [
    ("votes", "person_id"),
    ("vote_events", "person_id"),
    ("superlike_votes", "person_id"),
]
# Catégorie B — historique interne possédé (cascade-delete).
INTERNAL_HISTORY = [
    ("person_ticks", "person_id"),
    ("index_snapshots", "person_id"),
]
# Catégorie D — autres mécaniques (listées si présentes).
OTHER_MECHANICS = [
    ("daily_runs", "person_id"),
    ("bull_runs", "person_id"),
    ("active_boosts", "person_id"),
    ("strikes", "person_id"),
    ("category_reviews", "person_id"),
    ("deceased_queue", "person_id"),
    ("user_settings", "contributed_person_ids"),
    ("personality_reports", "person_id"),
    ("outsider_reports", "outsider_person_id"),
]


async def _count(db, coll, field, pid_str):
    try:
        variants = [ObjectId(pid_str), pid_str]
    except Exception:
        variants = [pid_str]
    try:
        return await db[coll].count_documents({field: {"$in": variants}})
    except Exception as e:
        return f"err:{e}"


async def category_counts(db, pairs, pid_str):
    out = {}
    for coll, field in pairs:
        n = await _count(db, coll, field, pid_str)
        if n:
            out[f"{coll}.{field}"] = n
    return out


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🔬 [BREAKDOWN — READ-ONLY] base='{db_name}'")
    print("    Aucune écriture. Sépare seed(faux) / historique interne / vrais docs utilisateur.\n")

    groups = defaultdict(list)
    cursor = db.persons.find({}, {
        "name": 1, "slug": 1, "source": 1,
        "total_votes": 1, "likes": 1, "dislikes": 1, "superlikes": 1,
        "created_at": 1, "wikidata_id": 1,
    })
    async for doc in cursor:
        key = normalize_key(doc.get("name", ""))
        if key:
            groups[key].append(doc)

    dup_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"  Groupes en doublon : {len(dup_groups)}\n")

    grand_seed = 0
    grand_internal = 0
    grand_real = 0
    grand_other = 0
    alerts = []
    manifest = []

    for gi, (key, members) in enumerate(sorted(dup_groups.items()), 1):
        def sort_key(d):
            return (
                -int(d.get("total_votes", 0) or 0),
                _fmt(d.get("created_at")) or "9999",
                0 if d.get("wikidata_id") else 1,
                str(d.get("_id")),
            )
        ordered = sorted(members, key=sort_key)
        keep, remove = ordered[0], ordered[1:]

        print("=" * 78)
        print(f"[{gi}] name_normalized = '{key}'  ({len(members)} fiches)")
        print(f"    ✅ GARDER : {keep['_id']}  \"{keep.get('name','')}\"  slug='{keep.get('slug','')}'  "
              f"votes={keep.get('total_votes',0)}")

        remove_entries = []
        for d in remove:
            pid = str(d["_id"])
            seed_counters = (
                int(d.get("total_votes", 0) or 0)
                + int(d.get("likes", 0) or 0)
                + int(d.get("dislikes", 0) or 0)
                + int(d.get("superlikes", 0) or 0)
            )
            internal = await category_counts(db, INTERNAL_HISTORY, pid)
            real = await category_counts(db, REAL_USER_DOCS, pid)
            other = await category_counts(db, OTHER_MECHANICS, pid)

            internal_total = sum(v for v in internal.values() if isinstance(v, int))
            real_total = sum(v for v in real.values() if isinstance(v, int))
            other_total = sum(v for v in other.values() if isinstance(v, int))

            grand_seed += seed_counters
            grand_internal += internal_total
            grand_real += real_total
            grand_other += other_total

            safe = (real_total == 0)
            flag = "OK (0 vrai doc)" if safe else "⚠️  ALERTE : vrais docs > 0"
            if not safe:
                alerts.append((key, pid, real))

            print(f"    ❌ RETIRER : {pid}  \"{d.get('name','')}\"  slug='{d.get('slug','')}'  "
                  f"src={d.get('source','')}")
            print(f"         A. compteurs seed (faux, non comptés) : total_votes={d.get('total_votes',0)} "
                  f"likes={d.get('likes',0)} dislikes={d.get('dislikes',0)} superlikes={d.get('superlikes',0)}")
            print(f"         B. historique interne (cascade)       : {internal or 'aucun'}  (={internal_total})")
            print(f"         C. VRAIS DOCS UTILISATEUR             : {real or 'aucun'}  (={real_total})  → {flag}")
            print(f"         D. autres mécaniques                  : {other or 'aucune'}  (={other_total})")

            remove_entries.append({
                "id": pid, "name": d.get("name", ""), "slug": d.get("slug", ""),
                "seed_counters": seed_counters,
                "internal_history": internal, "internal_total": internal_total,
                "real_user_docs": real, "real_total": real_total,
                "other_mechanics": other, "other_total": other_total,
                "safe_to_delete": safe,
            })

        manifest.append({
            "name_normalized": key,
            "keep": {"id": str(keep["_id"]), "name": keep.get("name", ""), "slug": keep.get("slug", "")},
            "remove": remove_entries,
        })

    print("=" * 78)
    print("\n  RÉSUMÉ GLOBAL (fiches à RETIRER)")
    print(f"    A. compteurs de seed (faux, ignorés)     : {grand_seed}")
    print(f"    B. historique interne (cascade-delete)   : {grand_internal}")
    print(f"    D. autres mécaniques (à examiner si >0)  : {grand_other}")
    print(f"    ── C. VRAIS DOCS UTILISATEUR À PERDRE     : {grand_real}")
    if grand_real == 0:
        print("    ✅ SÛR : aucune donnée utilisateur réelle sur les fiches à retirer.")
    else:
        print("    ⛔ STOP : des vrais documents utilisateur existent — revue manuelle requise :")
        for key, pid, real in alerts:
            print(f"        - groupe '{key}' fiche {pid} : {real}")

    with open("breakdown_cleanup.json", "w", encoding="utf-8") as f:
        json.dump({
            "db_name": db_name,
            "totals": {"seed_counters": grand_seed, "internal_history": grand_internal,
                       "other_mechanics": grand_other, "real_user_docs": grand_real},
            "groups": manifest,
        }, f, ensure_ascii=False, indent=2, default=str)
    print("\n📄 Détail écrit dans ./breakdown_cleanup.json (fichier local, aucune écriture Mongo).")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
