"""
Étape 1 (chantier accents/slugs) — AUDIT READ-ONLY des doublons de Personnalités.

⚠️  CE SCRIPT N'ÉCRIT RIEN DANS LA BASE. Il ne fait que LIRE la collection `persons`,
    calcule une clé canonique accent-insensible `name_normalized = unidecode(name)`
    (minuscules, espaces normalisés) et remonte les groupes qui contiennent ≥2 fiches
    distinctes = doublons potentiels (ex : "Rosalía" vs "Rosalia", "Léa Seydoux" vs
    "Lea Seydoux"). Objectif : mesurer l'ampleur AVANT tout backfill/nettoyage.

    Aucune écriture Mongo. Écrit uniquement un fichier LOCAL `duplicates_audit.json`
    (résumé complet, pour concevoir ensuite le nettoyage D sur les vrais cas).

Usage (même base que le serveur) :
    cd backend
    MONGO_URL="<atlas-uri>" DB_NAME="popular_production" python3 audit_duplicates.py

Sortie :
    - tableau lisible dans le terminal (compte + exemples)
    - fichier local duplicates_audit.json
"""
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode


def normalize_key(name: str) -> str:
    """Clé canonique de dédup : MÊME logique que server.normalize_person_name,
    avec normalisation des espaces (comme clean_name à la création)."""
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


def _fmt(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt or "")


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🔎 [AUDIT READ-ONLY] base='{db_name}' — collection 'persons'")
    print("    Aucune écriture. Calcul des doublons par name_normalized (accent-insensible).\n")

    total = 0
    groups = defaultdict(list)  # key -> list of person summaries

    cursor = db.persons.find(
        {},
        {
            "name": 1, "slug": 1, "source": 1, "category": 1,
            "total_votes": 1, "likes": 1, "dislikes": 1,
            "created_at": 1, "wikidata_id": 1, "name_normalized": 1,
            "approved": 1, "visible_in_rankings": 1,
        },
    )
    async for doc in cursor:
        total += 1
        key = normalize_key(doc.get("name", ""))
        if not key:
            continue
        groups[key].append({
            "id": str(doc.get("_id")),
            "name": doc.get("name", ""),
            "slug": doc.get("slug", ""),
            "source": doc.get("source", ""),
            "category": doc.get("category", ""),
            "total_votes": int(doc.get("total_votes", 0) or 0),
            "likes": int(doc.get("likes", 0) or 0),
            "dislikes": int(doc.get("dislikes", 0) or 0),
            "created_at": _fmt(doc.get("created_at")),
            "wikidata_id": doc.get("wikidata_id", "") or "",
            "name_normalized_stored": doc.get("name_normalized", None),
            "approved": doc.get("approved", None),
            "visible_in_rankings": doc.get("visible_in_rankings", None),
        })

    # Groupes en doublon = au moins 2 fiches distinctes pour la même clé.
    dup_groups = {k: v for k, v in groups.items() if len(v) >= 2}

    # Tri : d'abord les groupes les plus gros, puis par total de votes du groupe.
    def group_votes(members):
        return sum(m["total_votes"] for m in members)

    ordered = sorted(
        dup_groups.items(),
        key=lambda kv: (len(kv[1]), group_votes(kv[1])),
        reverse=True,
    )

    extra_fiches = sum(len(v) - 1 for v in dup_groups.values())

    print("=" * 78)
    print(f"  Total fiches persons scannées        : {total}")
    print(f"  Clés (noms canoniques) distinctes    : {len(groups)}")
    print(f"  Groupes en DOUBLON (≥2 fiches)       : {len(dup_groups)}")
    print(f"  Fiches en trop (à fusionner/retirer) : {extra_fiches}")
    print("=" * 78)

    if not dup_groups:
        print("\n✅ Aucun doublon détecté par name_normalized.")
    else:
        # Combien impliquent des accents (au moins 2 orthographes 'name' différentes) ?
        accent_related = 0
        cross_source = 0
        for _, members in dup_groups.items():
            distinct_names = {m["name"] for m in members}
            distinct_sources = {m["source"] for m in members}
            if len(distinct_names) >= 2:
                accent_related += 1
            if len(distinct_sources) >= 2:
                cross_source += 1
        print(f"\n  Dont groupes avec orthographes différentes (accents/casse) : {accent_related}")
        print(f"  Dont groupes mêlant plusieurs 'source'                    : {cross_source}")

        show = min(len(ordered), 40)
        print(f"\n  ── Exemples ({show} premiers groupes) ──")
        for i, (key, members) in enumerate(ordered[:show], 1):
            print(f"\n  [{i}] name_normalized = '{key}'  ({len(members)} fiches)")
            # canonique provisoire = plus de votes, puis plus ancien, puis avec wikidata
            for m in sorted(members, key=lambda x: (-x["total_votes"], x["created_at"] or "")):
                nn = m["name_normalized_stored"]
                nn_flag = "∅" if nn is None else ("=" if nn == key else f"≠'{nn}'")
                print(
                    f"       - {m['id']}  \"{m['name']}\"  slug='{m['slug']}'  "
                    f"src={m['source']}  votes={m['total_votes']}  "
                    f"wd={m['wikidata_id'] or '-'}  created={m['created_at'] or '-'}  "
                    f"name_norm[{nn_flag}]"
                )

    # Écriture LOCALE (pas la base) du rapport complet.
    report = {
        "db_name": db_name,
        "total_persons": total,
        "distinct_keys": len(groups),
        "duplicate_groups": len(dup_groups),
        "extra_fiches": extra_fiches,
        "groups": [
            {"name_normalized": k, "members": v}
            for k, v in ordered
        ],
    }
    out_path = "duplicates_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 Rapport complet écrit dans ./{out_path} (fichier local, aucune écriture Mongo).")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
