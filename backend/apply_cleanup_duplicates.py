"""
Étape 1 (chantier accents/slugs) — APPLY du nettoyage des doublons.

Supprime les 5 fiches persons en DOUBLON (issues de l'ancien bug de slug accentué),
en gardant le CANONIQUE de chaque groupe. Cascade-delete des documents possédés,
avec migration ciblée des VRAIS votes non-collision (aucun dans les 5 cas vérifiés).

──────────────────────────────────────────────────────────────────────────────
GARDE-FOUS (multiples, car pas de snapshot Atlas gratuit) :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis pour supprimer.
  • ANTI-DRIFT : abort si le nombre de groupes en doublon ≠ EXPECTED_GROUPS (5)
    ou le nombre de fiches à retirer ≠ EXPECTED_REMOVES (5).
  • SELF-BACKUP : AVANT toute suppression, exporte dans un JSON local (sur Render)
    TOUS les docs qui seront supprimés (persons + person_ticks + index_snapshots +
    votes + vote_events + superlike_votes). Imprime le chemin + un résumé. C'est le
    point de restauration en session.
  • Imprime aussi à l'écran les 5 documents `persons` (petits) en JSON, pour copie
    durable locale.
  • CATÉGORIE D : abort si une fiche à retirer a une référence dans daily_runs /
    bull_runs / active_boosts / strikes / category_reviews / deceased_queue /
    user_settings.contributed_person_ids / personality_reports / outsider_reports /
    potd_current (jamais rencontré au breakdown, mais revérifié ici).
  • NE fait PAS : ajout à seed_blocklist (clé name_normalized partagée avec le
    canonique → le bloquerait), ni blocage de device, ni modification du canonique.
  • Idempotent : relancé, ne retrouve plus de doublon.

RESTAURATION (si besoin, depuis le fichier de backup) : ré-insérer chaque section
dans sa collection (db.<coll>.insert_many(...)). Les _id d'origine sont conservés.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python apply_cleanup_duplicates.py            # DRY-RUN (défaut), n'écrit rien
    python apply_cleanup_duplicates.py --apply    # écrit, APRÈS lecture du dry-run
"""
import argparse
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode

EXPECTED_GROUPS = 5    # anti-drift : nb de groupes en doublon attendus
EXPECTED_REMOVES = 5   # anti-drift : nb de fiches à retirer attendues

# Collections dont on supprime les docs possédés par la fiche retirée (cascade).
OWNED = [
    ("votes", "person_id"),
    ("vote_events", "person_id"),
    ("superlike_votes", "person_id"),
    ("person_ticks", "person_id"),
    ("index_snapshots", "person_id"),
]
# Catégorie D : présence = abort (revue manuelle avant suppression).
CATEGORY_D = [
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


def normalize_key(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


def _variants(pid_str):
    try:
        return [ObjectId(pid_str), pid_str]
    except Exception:
        return [pid_str]


def _sort_key(d):
    return (
        -int(d.get("total_votes", 0) or 0),
        (d.get("created_at").isoformat() if isinstance(d.get("created_at"), datetime) else "9999"),
        0 if d.get("wikidata_id") else 1,
        str(d.get("_id")),
    )


async def _fetch_owned(db, pid_str):
    v = _variants(pid_str)
    out = {}
    for coll, field in OWNED:
        out[coll] = await db[coll].find({field: {"$in": v}}).to_list(None)
    return out


async def _category_d_refs(db, pid_str):
    v = _variants(pid_str)
    hits = {}
    for coll, field in CATEGORY_D:
        n = await db[coll].count_documents({field: {"$in": v}})
        if n:
            hits[f"{coll}.{field}"] = n
    # potd_current (doc unique dans app_settings)
    potd = await db.app_settings.find_one({"_id": "potd_current"})
    if potd and str(potd.get("potd_person_id", "")) == pid_str:
        hits["app_settings.potd_current"] = 1
    return hits


async def main():
    parser = argparse.ArgumentParser(description="Apply cascade-delete des doublons.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Écriture réelle (après lecture du dry-run).")
    args = parser.parse_args()
    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"🧹 [APPLY CLEANUP] base='{db_name}' — mode: {mode}\n")

    # ── Recompose les groupes + canonique ──
    groups = defaultdict(list)
    cursor = db.persons.find({}, {
        "name": 1, "slug": 1, "source": 1, "total_votes": 1,
        "likes": 1, "dislikes": 1, "superlikes": 1, "created_at": 1, "wikidata_id": 1,
    })
    async for d in cursor:
        key = normalize_key(d.get("name", ""))
        if key:
            groups[key].append(d)
    dup_groups = {k: v for k, v in groups.items() if len(v) >= 2}

    plan = []  # (key, keep_doc, [remove_docs])
    for key, members in sorted(dup_groups.items()):
        ordered = sorted(members, key=_sort_key)
        plan.append((key, ordered[0], ordered[1:]))
    total_removes = sum(len(rm) for _, _, rm in plan)

    # ── GARDE-FOU anti-drift ──
    print(f"  Groupes en doublon : {len(dup_groups)} (attendu {EXPECTED_GROUPS})")
    print(f"  Fiches à retirer   : {total_removes} (attendu {EXPECTED_REMOVES})")
    if len(dup_groups) != EXPECTED_GROUPS or total_removes != EXPECTED_REMOVES:
        print("\n⛔ ABORT anti-drift : l'état de la base diffère de ce qui a été vérifié.")
        print("   Rien n'a été touché. Relancer l'audit avant toute suppression.")
        client.close()
        return

    # ── Collecte : docs à supprimer + vérifs de sécurité ──
    print("\n  ── Fiches ciblées ──")
    removes_detail = []
    aborted = False
    for key, keep, removes in plan:
        keep_id = str(keep["_id"])
        keep_votes = await db.votes.find({"person_id": {"$in": _variants(keep_id)}}).to_list(None)
        keep_devices = {vd.get("device_id") for vd in keep_votes}
        for rd in removes:
            rid = str(rd["_id"])
            owned = await _fetch_owned(db, rid)
            catd = await _category_d_refs(db, rid)

            # Migration ciblée (générique) : votes dont le device est ABSENT du canonique.
            migratable = [v for v in owned["votes"] if v.get("device_id") not in keep_devices]
            colliding = [v for v in owned["votes"] if v.get("device_id") in keep_devices]

            print(f"    • '{key}': RETIRER {rid} \"{rd.get('name','')}\" → GARDER {keep_id}")
            print(f"        votes={len(owned['votes'])} (migrables={len(migratable)}, collision={len(colliding)})"
                  f"  vote_events={len(owned['vote_events'])}  superlikes={len(owned['superlike_votes'])}"
                  f"  ticks={len(owned['person_ticks'])}  snapshots={len(owned['index_snapshots'])}")
            if catd:
                print(f"        ⛔ CATÉGORIE D non vide : {catd} → ABORT (revue manuelle requise)")
                aborted = True
            if migratable:
                print(f"        ⚠️  {len(migratable)} vote(s) MIGRABLES détecté(s) (device absent du canonique) —")
                print(f"            cas NON attendu (on avait vérifié 0). Ils seront re-pointés vers le canonique.")

            removes_detail.append({
                "key": key, "keep_id": keep_id, "remove_id": rid,
                "owned": owned, "migratable": migratable, "colliding": colliding,
            })

    if aborted:
        print("\n⛔ ABORT : au moins une fiche porte une référence catégorie D. Rien n'a été touché.")
        client.close()
        return

    # ── Impression des 5 persons docs (copie durable locale) ──
    print("\n  ── 5 documents persons à retirer (copie-les) ──")
    for rdet in removes_detail:
        pdoc = await db.persons.find_one({"_id": ObjectId(rdet["remove_id"])})
        print(json.dumps(pdoc, ensure_ascii=False, default=str))

    # ── SELF-BACKUP : export complet AVANT toute suppression ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"cleanup_backup_{stamp}.json"
    backup = {
        "created_at": stamp, "db_name": db_name, "mode": mode,
        "expected_groups": EXPECTED_GROUPS, "expected_removes": EXPECTED_REMOVES,
        "removes": [],
    }
    for rdet in removes_detail:
        pdoc = await db.persons.find_one({"_id": ObjectId(rdet["remove_id"])})
        backup["removes"].append({
            "key": rdet["key"], "keep_id": rdet["keep_id"], "remove_id": rdet["remove_id"],
            "persons": pdoc,
            **{coll: rdet["owned"][coll] for coll, _ in OWNED},
        })
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2, default=str)

    def _count(section):
        return sum(len(r[section]) for r in [rd["owned"] for rd in removes_detail])
    print(f"\n  💾 Backup écrit : ./{backup_path}")
    print(f"     persons=5  votes={_count('votes')}  vote_events={_count('vote_events')}  "
          f"superlike_votes={_count('superlike_votes')}  person_ticks={_count('person_ticks')}  "
          f"index_snapshots={_count('index_snapshots')}")

    if not apply:
        print("\n🔒 DRY-RUN : aucune suppression effectuée. Rien n'a été modifié.")
        print("   Le backup ci-dessus est un aperçu. Pour supprimer : relancer avec --apply")
        client.close()
        return

    # ── APPLY : suppressions (après backup) ──
    print("\n✍️  APPLY : suppression en cours...\n")
    for rdet in removes_detail:
        rid = rdet["remove_id"]
        keep_id = rdet["keep_id"]
        v = _variants(rid)

        # 1) Migration ciblée des votes non-collision (0 attendu) + leurs vote_events.
        for vote in rdet["migratable"]:
            dev = vote.get("device_id")
            await db.votes.update_one({"_id": vote["_id"]}, {"$set": {"person_id": ObjectId(keep_id)}})
            await db.vote_events.update_many(
                {"person_id": {"$in": v}, "device_id": dev},
                {"$set": {"person_id": ObjectId(keep_id)}},
            )
            print(f"    ↪️  migré vote+events device={dev} : {rid} → {keep_id}")

        # 2) Cascade-delete de tout ce qui reste possédé par la fiche retirée.
        deleted = {}
        for coll, field in OWNED:
            res = await db[coll].delete_many({field: {"$in": v}})
            deleted[coll] = res.deleted_count
        res_p = await db.persons.delete_one({"_id": ObjectId(rid)})
        print(f"    🗑️  {rid} supprimé "
              f"(persons={res_p.deleted_count}, " +
              ", ".join(f"{c}={deleted[c]}" for c, _ in OWNED) + ")")

    print("\n✅ APPLY terminé. Doublons supprimés, canoniques intacts.")
    print(f"   Restauration possible depuis ./{backup_path} si besoin.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
