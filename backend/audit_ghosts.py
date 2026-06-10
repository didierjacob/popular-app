"""
Lot 1 — Audit READ-ONLY des fantômes potentiels (anti-fantôme, étape post-implémentation).

⚠️  CE SCRIPT N'ÉCRIT RIEN, NE SUPPRIME RIEN. Il ne fait que LIRE la base et lister
    les fiches qui peuvent être re-créées automatiquement (source auto_detected /
    trending / user_search). Didier valide la liste à l'œil ; la re-suppression se fait
    ENSUITE via l'admin (DELETE /admin/person/{id}), qui les inscrit dans la blocklist.

Usage (avec la même base que le serveur) :
    cd backend
    MONGO_URL="<atlas-uri>" DB_NAME="popular_production" python audit_ghosts.py

Sortie :
    - tableau lisible dans le terminal
    - fichier JSON ghosts_audit.json (liste complète, pour construire la kill-list validée)
"""
import asyncio
import json
import os
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

# Sources qui peuvent réapparaître automatiquement (≠ outsider/self-boost, ≠ seed manuel).
AUTO_SOURCES = ["auto_detected", "trending", "user_search"]


def _fmt(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt or "")


async def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Blocklist actuelle (pour signaler ce qui est déjà couvert vs pas encore).
    settings = await db.app_settings.find_one({"_id": "global"}) or {}
    bl_names = set(settings.get("seed_blocklist_names", []))
    bl_slugs = set(settings.get("seed_blocklist", []))
    bl_wd = set(settings.get("seed_blocklist_wikidata", []))

    cursor = db.persons.find(
        {"source": {"$in": AUTO_SOURCES}},
        {
            "name": 1, "slug": 1, "source": 1, "wikidata_id": 1,
            "created_at": 1, "total_votes": 1, "likes": 1, "dislikes": 1,
            "popularoo_index": 1, "score": 1,
        },
    ).sort("created_at", -1)

    rows = []
    async for p in cursor:
        rows.append(p)

    print(f"\n=== AUDIT FANTÔMES (READ-ONLY) — base '{db_name}' ===")
    print(f"Sources auditées : {', '.join(AUTO_SOURCES)}")
    print(f"Total fiches re-créables automatiquement : {len(rows)}\n")
    print(f"{'#':>3}  {'source':<13} {'created':<16} {'votes':>7}  {'wikidata':<11} name")
    print("-" * 90)

    export = []
    for i, p in enumerate(rows, 1):
        name = p.get("name", "")
        slug = p.get("slug", "")
        wd = p.get("wikidata_id") or ""
        src = p.get("source", "")
        votes = p.get("total_votes", 0)
        already = (
            (slug in bl_slugs)
            or (wd and wd in bl_wd)
        )
        flag = " [DÉJÀ BLOCKLISTÉ]" if already else ""
        print(f"{i:>3}  {src:<13} {_fmt(p.get('created_at')):<16} {votes:>7}  {wd:<11} {name}{flag}")
        export.append({
            "_id": str(p["_id"]),
            "name": name,
            "slug": slug,
            "source": src,
            "wikidata_id": wd,
            "created_at": _fmt(p.get("created_at")),
            "total_votes": votes,
            "already_blocklisted": bool(already),
        })

    out_path = os.path.join(os.path.dirname(__file__), "ghosts_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print("-" * 90)
    print(f"\n📄 Liste complète exportée : {out_path}")
    print("➡️  Validez la liste, puis re-supprimez les fantômes via l'admin "
          "(DELETE /admin/person/{id}) — ils entreront alors dans la blocklist.\n")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
