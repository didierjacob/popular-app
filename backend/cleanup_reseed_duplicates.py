"""
Étape 2 (chantier accents/slugs) — CLEANUP CIBLÉ des 2 doublons re-seedés le 2026-07-22.

Contexte : le seed loader (avant le fix e5b82bc) a re-créé 2 fiches au démarrage
(dédup par slug, ratant les originaux à slug abîmé). On SUPPRIME ces 2 NOUVELLES
fiches et on GARDE les originaux (05-06, avec historique + name_normalized).

⚠️  CIBLAGE EXPLICITE par _id (PAS la règle auto "plus de votes" : les nouvelles
    fiches ont des votes fake plus élevés, l'auto garderait les MAUVAISES).

Fiches à RETIRER (les nouvelles) :
    6a60c11e5d45acbedd75f688  Måneskin       (re-seed 13:09)
    6a60c11b5d45acbedd75f686  Thomas Müller  (re-seed 13:09)

──────────────────────────────────────────────────────────────────────────────
GARDE-FOUS (identiques à apply_cleanup_duplicates) :
  • --dry-run PAR DÉFAUT : n'écrit rien. --apply explicite requis.
  • Pour CHAQUE fiche à retirer, vérifie : existe, source="seed", créée ~13:09
    (fenêtre 12:30–13:30 UTC du 2026-07-22), et qu'un ORIGINAL du même
    name_normalized existe (≠ cet _id, plus ancien) → sinon ABORT.
  • ABORT si vrais docs utilisateur (votes + vote_events + superlike_votes) > 0.
  • SELF-BACKUP AVANT toute suppression (persons + ticks + snapshots + votes +
    vote_events + superlike_votes) → fichier local + résumé.
  • Imprime les 2 documents persons à l'écran.
  • Cascade-delete : votes → vote_events → superlike_votes → person_ticks →
    index_snapshots → persons. NE touche PAS aux originaux. Pas de seed_blocklist.
  • Idempotent : relancé, les _id n'existent plus → rien à faire.

Usage (Render Shell, APRÈS déploiement du fix seed loader e5b82bc) :
    cd /opt/render/project/src/backend
    python cleanup_reseed_duplicates.py            # DRY-RUN (défaut)
    python cleanup_reseed_duplicates.py --apply    # écrit, après lecture du dry-run
"""
import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unidecode import unidecode

# Les 2 NOUVELLES fiches à supprimer (ciblage explicite).
REMOVE_IDS = [
    {"id": "6a60c11e5d45acbedd75f688", "expect_name": "Måneskin"},
    {"id": "6a60c11b5d45acbedd75f686", "expect_name": "Thomas Müller"},
]
EXPECTED_REMOVES = 2

# Fenêtre de création attendue (re-seed du 2026-07-22 ~13:09 UTC).
WINDOW_START = datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 7, 22, 13, 30, tzinfo=timezone.utc)

# Collections cascade (docs possédés par la fiche retirée).
OWNED = [
    ("votes", "person_id"),
    ("vote_events", "person_id"),
    ("superlike_votes", "person_id"),
    ("person_ticks", "person_id"),
    ("index_snapshots", "person_id"),
]
# Vrais docs utilisateur (seuil de sécurité = 0).
REAL_USER = ["votes", "vote_events", "superlike_votes"]


def normalize_key(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", (name or "").strip())
    return unidecode(collapsed).lower().strip()


def _variants(pid_str):
    try:
        return [ObjectId(pid_str), pid_str]
    except Exception:
        return [pid_str]


async def _fetch_owned(db, pid_str):
    v = _variants(pid_str)
    return {coll: await db[coll].find({field: {"$in": v}}).to_list(None) for coll, field in OWNED}


async def main():
    parser = argparse.ArgumentParser(description="Cleanup ciblé des 2 doublons re-seedés.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien.")
    g.add_argument("--apply", action="store_true", help="Écriture réelle.")
    args = parser.parse_args()
    apply = bool(args.apply)
    mode = "APPLY (écriture réelle)" if apply else "DRY-RUN (lecture seule)"

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "popular_production")
    db = AsyncIOMotorClient(mongo_url)[db_name]

    print(f"🧹 [CLEANUP RE-SEED CIBLÉ] base='{db_name}' — mode: {mode}\n")

    details = []
    aborted = False
    for tgt in REMOVE_IDS:
        rid = tgt["id"]
        print("=" * 74)
        try:
            oid = ObjectId(rid)
        except Exception:
            print(f"⛔ {rid} : _id invalide → ABORT")
            aborted = True
            continue

        doc = await db.persons.find_one({"_id": oid})
        if not doc:
            print(f"⛔ {rid} \"{tgt['expect_name']}\" : INTROUVABLE → ABORT")
            aborted = True
            continue

        created = oid.generation_time
        key = normalize_key(doc.get("name", ""))
        source = doc.get("source", "")
        print(f"  {rid}  \"{doc.get('name','')}\"  src={source}  "
              f"slug='{doc.get('slug','')}'  nn={doc.get('name_normalized')!r}  "
              f"votes={doc.get('total_votes',0)}  créée={created.isoformat()}")

        # ── Sanity 1 : source seed ──
        if source != "seed":
            print(f"     ⛔ source '{source}' ≠ 'seed' → ABORT (ne pas supprimer une fiche non-seed)")
            aborted = True
        # ── Sanity 2 : créée dans la fenêtre de re-seed ──
        if not (WINDOW_START <= created <= WINDOW_END):
            print(f"     ⛔ created {created.isoformat()} hors fenêtre re-seed "
                  f"[{WINDOW_START.isoformat()}..{WINDOW_END.isoformat()}] → ABORT")
            aborted = True
        # ── Sanity 3 : un ORIGINAL du même name_normalized existe (plus ancien, ≠ cet _id) ──
        siblings = await db.persons.find(
            {"_id": {"$ne": oid}},
            {"name": 1, "slug": 1, "source": 1, "created_at": 1, "name_normalized": 1},
        ).to_list(None)
        original = None
        for s in siblings:
            if normalize_key(s.get("name", "")) == key:
                if original is None or s["_id"].generation_time < original["_id"].generation_time:
                    original = s
        if not original:
            print(f"     ⛔ AUCUN original '{key}' trouvé (≠ cet _id) → ABORT (on ne supprime pas le dernier)")
            aborted = True
        elif original["_id"].generation_time >= created:
            print(f"     ⛔ le candidat 'original' {original['_id']} n'est pas plus ancien → ABORT")
            aborted = True
        else:
            print(f"     ✅ original conservé : {original['_id']} \"{original.get('name','')}\" "
                  f"slug='{original.get('slug','')}' créée={original['_id'].generation_time.isoformat()}")

        # ── Sanity 4 : vrais docs utilisateur = 0 ──
        owned = await _fetch_owned(db, rid)
        real_total = sum(len(owned[c]) for c in REAL_USER)
        counts = {c: len(owned[c]) for c, _ in OWNED}
        print(f"     docs possédés : " + ", ".join(f"{c}={counts[c]}" for c, _ in OWNED))
        if real_total > 0:
            print(f"     ⛔ VRAIS DOCS UTILISATEUR = {real_total} (>0) → ABORT (revue manuelle)")
            aborted = True
        else:
            print(f"     ✅ vrais docs utilisateur = 0 (suppression sûre)")

        details.append({"id": rid, "doc": doc, "owned": owned,
                        "original_id": str(original["_id"]) if original else None})

    print("=" * 74)
    if len(details) != EXPECTED_REMOVES or aborted:
        print(f"\n⛔ ABORT : {len(details)}/{EXPECTED_REMOVES} fiches valides, aborted={aborted}. "
              f"RIEN n'a été touché.")
        return

    # ── Impression des 2 persons (copie durable) ──
    print("\n── 2 documents persons à retirer (copie-les) ──")
    for d in details:
        print(json.dumps(d["doc"], ensure_ascii=False, default=str))

    # ── SELF-BACKUP avant toute suppression ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"reseed_cleanup_backup_{stamp}.json"
    backup = {"created_at": stamp, "db_name": db_name, "mode": mode, "removes": []}
    for d in details:
        backup["removes"].append({
            "id": d["id"], "original_id": d["original_id"],
            "persons": d["doc"],
            **{c: d["owned"][c] for c, _ in OWNED},
        })
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2, default=str)
    tot = {c: sum(len(d["owned"][c]) for d in details) for c, _ in OWNED}
    print(f"\n  💾 Backup écrit : ./{backup_path}")
    print(f"     persons={len(details)}  " + "  ".join(f"{c}={tot[c]}" for c, _ in OWNED))

    if not apply:
        print("\n🔒 DRY-RUN : aucune suppression. Rien n'a été modifié.")
        print("   Pour supprimer : relancer avec --apply")
        return

    # ── APPLY : cascade-delete ──
    print("\n✍️  APPLY : suppression en cours...\n")
    for d in details:
        rid = d["id"]
        v = _variants(rid)
        deleted = {}
        for coll, field in OWNED:
            res = await db[coll].delete_many({field: {"$in": v}})
            deleted[coll] = res.deleted_count
        res_p = await db.persons.delete_one({"_id": ObjectId(rid)})
        print(f"    🗑️  {rid} supprimé (persons={res_p.deleted_count}, "
              + ", ".join(f"{c}={deleted[c]}" for c, _ in OWNED) + ")")

    print("\n✅ APPLY terminé. Les 2 doublons re-seedés supprimés, originaux intacts.")
    print(f"   Restauration possible depuis ./{backup_path} si besoin.")


if __name__ == "__main__":
    asyncio.run(main())
