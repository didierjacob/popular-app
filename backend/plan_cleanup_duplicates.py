"""
Étape 1 (chantier accents/slugs) — PLAN DE NETTOYAGE des doublons, READ-ONLY.

⚠️  CE SCRIPT N'ÉCRIT RIEN. Il ne SUPPRIME rien, ne modifie rien. Il :
    1. Recalcule les groupes de doublons par name_normalized (comme audit_duplicates).
    2. Choisit le CANONIQUE (fiche à GARDER) par la règle :
         total_votes desc → created_at asc → possède wikidata_id → _id min.
    3. Marque les autres fiches du groupe comme À RETIRER.
    4. Pour CHAQUE fiche (gardée et retirée), CHIFFRE les données réelles et les
       références croisées (person_ticks + 14 collections, ObjectId ET string),
       pour prouver qu'aucune donnée utilisateur ne serait perdue au retrait.

    Sortie : tableau terminal + fichier LOCAL `cleanup_plan.json` (manifeste
    keep/remove que l'éventuel script d'exécution consommera plus tard).
    Aucune écriture Mongo.

Usage (Render Shell, MONGO_URL/DB_NAME déjà dans l'env) :
    cd /opt/render/project/src/backend
    python plan_cleanup_duplicates.py
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


# (collection, champ) référençant un _id de personne. On teste ObjectId ET str.
REF_MAP = [
    ("person_ticks", "person_id"),
    ("votes", "person_id"),
    ("vote_events", "person_id"),
    ("superlike_votes", "person_id"),
    ("daily_runs", "person_id"),
    ("bull_runs", "person_id"),
    ("active_boosts", "person_id"),
    ("strikes", "person_id"),
    ("category_reviews", "person_id"),
    ("deceased_queue", "person_id"),
    ("index_snapshots", "person_id"),
    ("user_settings", "contributed_person_ids"),   # array de str
    ("personality_reports", "person_id"),          # str
    ("outsider_reports", "outsider_person_id"),    # str
]


async def count_refs(db, pid_str: str) -> dict:
    """Compte, en lecture seule, les références vers cet _id dans chaque collection."""
    try:
        oid = ObjectId(pid_str)
        variants = [oid, pid_str]
    except Exception:
        variants = [pid_str]

    out = {}
    for coll, field in REF_MAP:
        try:
            n = await db[coll].count_documents({field: {"$in": variants}})
        except Exception as e:
            n = f"err:{e}"
        if n:
            out[f"{coll}.{field}"] = n

    # Cas particulier : app_settings.potd_current (doc unique).
    try:
        potd = await db.app_settings.find_one({"_id": "potd_current"})
        if potd and str(potd.get("potd_person_id", "")) == pid_str:
            out["app_settings.potd_current"] = 1
    except Exception:
        pass
    return out


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🧭 [PLAN NETTOYAGE — READ-ONLY] base='{db_name}'")
    print("    Aucune écriture. Décision keep/remove + chiffrage des données à risque.\n")

    groups = defaultdict(list)
    cursor = db.persons.find({}, {
        "name": 1, "slug": 1, "source": 1, "category": 1,
        "total_votes": 1, "likes": 1, "dislikes": 1, "superlikes": 1,
        "created_at": 1, "wikidata_id": 1, "name_normalized": 1,
    })
    async for doc in cursor:
        key = normalize_key(doc.get("name", ""))
        if key:
            groups[key].append(doc)

    dup_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"  Groupes en doublon détectés : {len(dup_groups)}\n")

    manifest = []
    total_remove = 0
    total_data_at_risk = 0

    for gi, (key, members) in enumerate(sorted(dup_groups.items()), 1):
        # Règle du canonique.
        def sort_key(d):
            return (
                -int(d.get("total_votes", 0) or 0),
                _fmt(d.get("created_at")) or "9999",
                0 if d.get("wikidata_id") else 1,
                str(d.get("_id")),
            )
        ordered = sorted(members, key=sort_key)
        keep = ordered[0]
        remove = ordered[1:]

        print("=" * 78)
        print(f"[{gi}] name_normalized = '{key}'  ({len(members)} fiches)")

        for d in ordered:
            pid = str(d["_id"])
            refs = await count_refs(db, pid)
            role = "GARDER  ✅" if d is keep else "RETIRER ❌"
            real_data = (
                int(d.get("total_votes", 0) or 0)
                + int(d.get("likes", 0) or 0)
                + int(d.get("dislikes", 0) or 0)
                + int(d.get("superlikes", 0) or 0)
            )
            refs_str = ", ".join(f"{k}={v}" for k, v in refs.items()) if refs else "aucune"
            print(
                f"   {role}  {pid}  \"{d.get('name','')}\"  slug='{d.get('slug','')}'  "
                f"src={d.get('source','')}  votes={d.get('total_votes',0)}  "
                f"likes={d.get('likes',0)}/{d.get('dislikes',0)}  "
                f"super={d.get('superlikes',0)}  wd={d.get('wikidata_id') or '-'}  "
                f"created={_fmt(d.get('created_at')) or '-'}"
            )
            print(f"            références croisées : {refs_str}")

            if d is not keep:
                total_remove += 1
                # ticks comptent comme historique interne, pas donnée utilisateur ;
                # mais on chiffre TOUTE référence non-tick comme "à migrer".
                non_tick_refs = sum(
                    v for k, v in refs.items()
                    if isinstance(v, int) and not k.startswith("person_ticks")
                )
                at_risk = real_data + non_tick_refs
                total_data_at_risk += at_risk

        # Raison du choix (lisible).
        reason = "plus de total_votes"
        kv = int(keep.get("total_votes", 0) or 0)
        if all(int(m.get("total_votes", 0) or 0) == kv for m in members):
            reason = "votes égaux → plus ancienne / wikidata / _id min"
        manifest.append({
            "name_normalized": key,
            "keep": {"id": str(keep["_id"]), "name": keep.get("name", ""),
                     "slug": keep.get("slug", ""), "total_votes": keep.get("total_votes", 0),
                     "reason": reason},
            "remove": [{"id": str(d["_id"]), "name": d.get("name", ""),
                        "slug": d.get("slug", ""), "total_votes": d.get("total_votes", 0)}
                       for d in remove],
        })

    print("=" * 78)
    print(f"\n  RÉSUMÉ")
    print(f"    Fiches à RETIRER                         : {total_remove}")
    print(f"    Données utilisateur réelles à perdre     : {total_data_at_risk}")
    print(f"    (0 = aucune donnée réelle sur les fiches retirées → suppression sûre)")

    with open("cleanup_plan.json", "w", encoding="utf-8") as f:
        json.dump({"db_name": db_name, "groups": manifest,
                   "total_remove": total_remove,
                   "total_data_at_risk": total_data_at_risk},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 Manifeste écrit dans ./cleanup_plan.json (fichier local, aucune écriture Mongo).")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
