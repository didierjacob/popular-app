"""
Étape 1 (chantier accents/slugs) — INSPECTION migration d'un doublon, READ-ONLY.

⚠️  CE SCRIPT N'ÉCRIT RIEN. Il éclaire le cas où une fiche à RETIRER porte de
    VRAIS documents utilisateur (votes / vote_events) — ex. Beyoncé — pour décider
    d'une migration sûre vers le canonique.

    Il :
      1. Charge la fiche à retirer (arg = son _id), déduit name_normalized,
         recalcule le groupe et identifie le CANONIQUE automatiquement
         (règle : total_votes desc → created_at asc → wikidata → _id min).
      2. DÉTAILLE chaque vrai doc de la fiche à retirer : votes (device_id, value,
         dates) + vote_events (device_id, delta, date).
      3. ANALYSE LA COLLISION : pour chaque device_id de la fiche à retirer,
         regarde si ce device a DÉJÀ voté sur le canonique (l'index unique
         (person_id, device_id) interdirait un re-pointage → collision).
      4. Chiffre les vrais docs du CANONIQUE (pour savoir s'il faut recompter).

    Aucune écriture Mongo. Écrit un fichier local migration_inspect.json.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python inspect_migration.py 69739dbfbea24e10586ba827
    # (si l'id est omis, valeur par défaut = la fiche Beyoncé à retirer)
"""
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode

DEFAULT_REMOVE_ID = "69739dbfbea24e10586ba827"  # fiche Beyoncé à retirer (breakdown)


def normalize_key(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


def _fmt(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt or "")


def _variants(pid_str):
    try:
        return [ObjectId(pid_str), pid_str]
    except Exception:
        return [pid_str]


async def real_docs(db, pid_str):
    """Liste détaillée des vrais docs utilisateur d'une fiche."""
    v = _variants(pid_str)
    votes = await db.votes.find({"person_id": {"$in": v}}).to_list(None)
    events = await db.vote_events.find({"person_id": {"$in": v}}).to_list(None)
    slikes = await db.superlike_votes.find({"person_id": {"$in": v}}).to_list(None)
    return votes, events, slikes


async def main():
    remove_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REMOVE_ID

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🔍 [INSPECTION MIGRATION — READ-ONLY] base='{db_name}'  remove_id={remove_id}\n")

    remove_doc = await db.persons.find_one({"_id": ObjectId(remove_id)})
    if not remove_doc:
        print("❌ Fiche à retirer introuvable.")
        client.close()
        return

    key = normalize_key(remove_doc.get("name", ""))
    print(f"  name_normalized = '{key}'")

    # Recompose le groupe + canonique (même règle déterministe).
    members = []
    cursor = db.persons.find({}, {
        "name": 1, "slug": 1, "source": 1, "total_votes": 1,
        "likes": 1, "dislikes": 1, "superlikes": 1, "created_at": 1, "wikidata_id": 1,
    })
    async for d in cursor:
        if normalize_key(d.get("name", "")) == key:
            members.append(d)

    def sort_key(d):
        return (
            -int(d.get("total_votes", 0) or 0),
            _fmt(d.get("created_at")) or "9999",
            0 if d.get("wikidata_id") else 1,
            str(d.get("_id")),
        )
    ordered = sorted(members, key=sort_key)
    keep = ordered[0]
    keep_id = str(keep["_id"])

    print(f"  ✅ CANONIQUE (garder) : {keep_id}  \"{keep.get('name','')}\"  "
          f"slug='{keep.get('slug','')}'  votes(compteur)={keep.get('total_votes',0)}")
    print(f"  ❌ À RETIRER          : {remove_id}  \"{remove_doc.get('name','')}\"  "
          f"slug='{remove_doc.get('slug','')}'  votes(compteur)={remove_doc.get('total_votes',0)}")

    if keep_id == remove_id:
        print("\n⚠️  L'id fourni EST le canonique du groupe — rien à migrer depuis lui.")
        client.close()
        return

    # ── 1. Détail des vrais docs de la fiche à retirer ──
    r_votes, r_events, r_slikes = await real_docs(db, remove_id)
    print(f"\n  ── VRAIS DOCS de la fiche à retirer ──")
    print(f"     votes={len(r_votes)}  vote_events={len(r_events)}  superlike_votes={len(r_slikes)}")
    for vdoc in r_votes:
        print(f"     [vote]  device={vdoc.get('device_id','?')}  value={vdoc.get('value')}  "
              f"created={_fmt(vdoc.get('created_at'))}  updated={_fmt(vdoc.get('updated_at'))}")
    for edoc in r_events:
        print(f"     [event] device={edoc.get('device_id','?')}  delta={edoc.get('delta')}  "
              f"created={_fmt(edoc.get('created_at'))}")
    for sdoc in r_slikes:
        print(f"     [super] device={sdoc.get('device_id','?')}  created={_fmt(sdoc.get('created_at'))}")

    # ── 2. Vrais docs du canonique + devices déjà présents ──
    k_votes, k_events, k_slikes = await real_docs(db, keep_id)
    keep_vote_devices = {vd.get("device_id") for vd in k_votes}
    print(f"\n  ── VRAIS DOCS du canonique ──")
    print(f"     votes={len(k_votes)}  vote_events={len(k_events)}  superlike_votes={len(k_slikes)}")
    print(f"     compteurs (seed) : total_votes={keep.get('total_votes',0)} "
          f"likes={keep.get('likes',0)} dislikes={keep.get('dislikes',0)} superlikes={keep.get('superlikes',0)}")
    if keep_vote_devices:
        print(f"     devices ayant déjà voté sur le canonique : {sorted(d for d in keep_vote_devices if d)}")

    # ── 3. Analyse de collision (index unique person_id+device_id sur votes) ──
    print(f"\n  ── COLLISION (votes : index unique person_id+device_id) ──")
    migratable = []
    colliding = []
    for vdoc in r_votes:
        dev = vdoc.get("device_id")
        if dev in keep_vote_devices:
            colliding.append(vdoc)
            print(f"     ⚠️  device={dev} a DÉJÀ voté sur le canonique → COLLISION "
                  f"(ne pas re-pointer ce vote ; garder celui du canonique)")
        else:
            migratable.append(vdoc)
            print(f"     ✅ device={dev} absent du canonique → re-pointage possible")
    if not r_votes:
        print("     (aucun vote à migrer)")

    # ── Résumé ──
    print("\n" + "=" * 78)
    print("  RÉSUMÉ MIGRATION Beyoncé (proposition, AUCUNE écriture)")
    print(f"    votes re-pointables (device absent du canonique) : {len(migratable)}")
    print(f"    votes en collision (device déjà présent)          : {len(colliding)}")
    print(f"    vote_events à re-pointer (journal, sans unicité)   : {len(r_events)}")
    print(f"    superlike_votes                                    : {len(r_slikes)}")
    net_likes = sum(1 for v in migratable if int(v.get('value', 0)) == 1)
    net_dislikes = sum(1 for v in migratable if int(v.get('value', 0)) == -1)
    print(f"    → si on incrémente les compteurs du canonique par les votes migrés : "
          f"+{net_likes} like / +{net_dislikes} dislike")

    report = {
        "db_name": db_name,
        "name_normalized": key,
        "keep_id": keep_id,
        "remove_id": remove_id,
        "remove_real": {"votes": len(r_votes), "vote_events": len(r_events), "superlikes": len(r_slikes)},
        "keep_real": {"votes": len(k_votes), "vote_events": len(k_events), "superlikes": len(k_slikes)},
        "keep_vote_devices": sorted(d for d in keep_vote_devices if d),
        "migratable_votes": [{"device_id": v.get("device_id"), "value": v.get("value"),
                              "created_at": _fmt(v.get("created_at"))} for v in migratable],
        "colliding_votes": [{"device_id": v.get("device_id"), "value": v.get("value"),
                             "created_at": _fmt(v.get("created_at"))} for v in colliding],
        "vote_events": [{"device_id": e.get("device_id"), "delta": e.get("delta"),
                         "created_at": _fmt(e.get("created_at"))} for e in r_events],
    }
    with open("migration_inspect.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\n📄 Détail écrit dans ./migration_inspect.json (local, aucune écriture Mongo).")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
