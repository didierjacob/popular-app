"""
Cœur honnête — Lot 3 : RETRAIT des Outsiders faux/test (démos + profils de test).

Contexte : Option B validée. Les Outsiders actuels sont tous faux/test (aucun vrai
payeur self_boosted — confirmé par audit_outsider_honesty.py). Le kill-switch de
re-seed (Lot 1) est déployé et vérifié en prod → aucun restart ne les recréera.
On peut donc les retirer.

Calqué sur cleanup_reseed_duplicates.py. MÊMES garde-fous, adaptés au cas Outsider :

  • --dry-run PAR DÉFAUT : n'écrit RIEN en base. --apply explicite requis.
  • SELF-BACKUP AVANT toute suppression (persons + toutes les collections possédées),
    en Extended JSON (bson.json_util) → restauration fidèle des _id/dates.
    Rollback : python remove_outsiders.py --rollback <backup.json>
  • IDEMPOTENT : relancé après --apply, les cibles n'existent plus → rien à faire.

  • CIBLE (prédicat "tout Outsider") :
        is_seed==True OR source=="self_boosted" OR category=="outsider" OR is_outsider==True

  • GARDE-FOU PAR PROFIL — SKIP (jamais forcé), listé pour revue manuelle, si :
      (a) VRAIS DOCS UTILISATEUR : au moins un document dans
          votes / vote_events / superlike_votes pour ce person_id.
          ⚠️  Ce sont les COLLECTIONS d'événements réels — PAS les compteurs
          likes/dislikes du doc person (ceux-là sont fabriqués au seeding et NE
          comptent pas comme "vrais").
      OU
      (b) BOOST RÉEL ACTIF : un active_boosts avec is_seed≠True ET non expiré
          (end_time > now, ou end_time absent = traité comme actif, prudence).

  • CASCADE (ordre) : votes → vote_events → superlike_votes → superlike_events →
    person_ticks → index_snapshots → active_boosts (du profil) → persons.

Usage (Render Shell, APRÈS Lot 1 déployé & vérifié) :
    cd /opt/render/project/src/backend
    python remove_outsiders.py                          # DRY-RUN (défaut) — liste + backup
    python remove_outsiders.py --apply                  # supprime (après lecture du dry-run)
    python remove_outsiders.py --rollback <backup.json> # restaure les profils supprimés
"""
import argparse
import asyncio
import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.json_util import dumps as bson_dumps, loads as bson_loads
from motor.motor_asyncio import AsyncIOMotorClient

# Prédicat "tout Outsider".
TARGET_QUERY = {"$or": [
    {"is_seed": True},
    {"source": "self_boosted"},
    {"category": "outsider"},
    {"is_outsider": True},
]}

# Cascade de suppression : docs possédés d'abord, persons en dernier.
OWNED = [
    ("votes", "person_id"),
    ("vote_events", "person_id"),
    ("superlike_votes", "person_id"),
    ("superlike_events", "person_id"),
    ("person_ticks", "person_id"),
    ("index_snapshots", "person_id"),
    ("active_boosts", "person_id"),
]

# Collections dont la SEULE présence (>0) = vrais docs utilisateur → SKIP profil.
REAL_USER = ["votes", "vote_events", "superlike_votes"]


def _variants(oid):
    """person_id peut être stocké en ObjectId ou en str → matcher les deux."""
    s = str(oid)
    out = [s]
    try:
        out.insert(0, ObjectId(s))
    except Exception:
        pass
    return out


def _to_naive_utc(dt):
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


async def _fetch_owned(db, pid):
    v = _variants(pid)
    return {coll: await db[coll].find({field: {"$in": v}}).to_list(None)
            for coll, field in OWNED}


def _real_user_count(owned):
    return sum(len(owned.get(c, [])) for c in REAL_USER)


def _real_boost(owned, now):
    """Retourne le premier boost RÉEL actif (is_seed≠True, non expiré), sinon None."""
    now = _to_naive_utc(now)
    for b in owned.get("active_boosts", []):
        if b.get("is_seed") is True:
            continue
        end = _to_naive_utc(b.get("end_time"))
        if end is None or end > now:   # end_time absent → prudence : considéré actif
            return b
    return None


async def do_rollback(db, path):
    if not os.path.exists(path):
        print(f"⛔ Fichier backup introuvable : {path}")
        return
    with open(path, encoding="utf-8") as f:
        data = bson_loads(f.read())
    removed = data.get("removed", [])
    print(f"↩️  ROLLBACK depuis {path} — {len(removed)} profils...")
    restored_persons = 0
    restored_owned = 0
    for entry in removed:
        p = entry["person"]
        await db.persons.replace_one({"_id": p["_id"]}, p, upsert=True)
        restored_persons += 1
        for coll, _ in OWNED:
            for d in entry.get(coll, []):
                await db[coll].replace_one({"_id": d["_id"]}, d, upsert=True)
                restored_owned += 1
    print(f"✅ Restauré : {restored_persons} persons + {restored_owned} docs possédés "
          f"(upsert par _id — idempotent).")


async def main():
    parser = argparse.ArgumentParser(description="Retrait des Outsiders faux/test (Lot 3).")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="Défaut. N'écrit rien en base.")
    g.add_argument("--apply", action="store_true", help="Suppression réelle (après backup).")
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
    now = datetime.utcnow()
    print(f"🧹 [RETRAIT OUTSIDERS] base='{db_name}' — mode: {mode}\n")

    targets = await db.persons.find(TARGET_QUERY).to_list(None)
    print(f"Profils correspondant au prédicat Outsider : {len(targets)}\n")

    eligible = []   # (doc, owned) — à supprimer
    skipped = []    # (doc, owned, raison) — conservés pour revue

    for doc in targets:
        owned = await _fetch_owned(db, doc["_id"])
        ru = _real_user_count(owned)
        rb = _real_boost(owned, now)
        reasons = []
        if ru > 0:
            reasons.append(f"vrais docs utilisateur={ru} "
                           f"(votes={len(owned['votes'])}/vote_events={len(owned['vote_events'])}"
                           f"/superlike_votes={len(owned['superlike_votes'])})")
        if rb is not None:
            reasons.append(f"boost RÉEL actif (tier={rb.get('tier','?')}, end={rb.get('end_time')})")
        if reasons:
            skipped.append((doc, owned, "; ".join(reasons)))
        else:
            eligible.append((doc, owned))

    # ── Tableau des cibles éligibles ──
    hdr = (f"{'name':<26} {'source':<14} {'seed':>5} {'L':>5} {'D':>5} "
           f"{'v/ve/sv':>10} {'se':>4} {'ticks':>5} {'snap':>5} {'boost':>6}")
    print("── ÉLIGIBLES À LA SUPPRESSION ──")
    print(hdr)
    print("-" * len(hdr))
    for doc, owned in sorted(eligible, key=lambda t: -(t[0].get("popularoo_index") or 0)):
        vsv = f"{len(owned['votes'])}/{len(owned['vote_events'])}/{len(owned['superlike_votes'])}"
        print(f"{(doc.get('name') or '?')[:25]:<26} {(doc.get('source') or 'unknown')[:13]:<14} "
              f"{str(bool(doc.get('is_seed'))):>5} {int(doc.get('likes',0) or 0):>5} "
              f"{int(doc.get('dislikes',0) or 0):>5} {vsv:>10} "
              f"{len(owned['superlike_events']):>4} {len(owned['person_ticks']):>5} "
              f"{len(owned['index_snapshots']):>5} {len(owned['active_boosts']):>6}")

    # ── Tableau des profils SKIP (revue manuelle) ──
    if skipped:
        print("\n── ⚠️  SKIP (VRAIS docs / boost réel — NON supprimés, revue manuelle) ──")
        for doc, _o, reason in skipped:
            print(f"   • {(doc.get('name') or '?')[:30]:<31} src={doc.get('source','?'):<13} "
                  f"is_seed={bool(doc.get('is_seed'))}  → {reason}")

    print("\n" + "=" * 70)
    print(f"  Prédicat Outsider trouvés : {len(targets)}")
    print(f"  → ÉLIGIBLES à supprimer   : {len(eligible)}")
    print(f"  → SKIP (revue manuelle)   : {len(skipped)}")
    print("=" * 70)
    print("  ⚠️  Vérifie que le nombre d'éligibles correspond bien aux profils faux/test")
    print("      attendus (ex. 51) AVANT de lancer --apply.")

    if not eligible:
        print("\n✅ Aucun profil éligible — rien à supprimer (idempotent).")
        return

    # ── SELF-BACKUP (Extended JSON) — écrit aussi en dry-run ──
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = f"outsiders_removal_backup_{stamp}.json"
    backup = {"created_at": stamp, "db_name": db_name, "mode": mode,
              "predicate": "is_seed|self_boosted|category=outsider|is_outsider",
              "count": len(eligible), "removed": []}
    for doc, owned in eligible:
        backup["removed"].append({"person": doc, **{c: owned[c] for c, _ in OWNED}})
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(bson_dumps(backup, indent=2))
    tot = {c: sum(len(o[c]) for _d, o in eligible) for c, _ in OWNED}
    print(f"\n  💾 Backup écrit : ./{backup_path}  ({len(eligible)} persons)")
    print("     " + "  ".join(f"{c}={tot[c]}" for c, _ in OWNED))

    if not apply:
        print("\n🔒 DRY-RUN : aucune suppression. Rien n'a été modifié en base.")
        print(f"   Pour supprimer : python remove_outsiders.py --apply")
        print(f"   Rollback (après --apply) : python remove_outsiders.py --rollback {backup_path}")
        return

    # ── APPLY : cascade-delete des éligibles uniquement ──
    print("\n✍️  APPLY : suppression en cours...\n")
    for doc, _owned in eligible:
        pid = doc["_id"]
        v = _variants(pid)
        deleted = {}
        for coll, field in OWNED:
            res = await db[coll].delete_many({field: {"$in": v}})
            deleted[coll] = res.deleted_count
        res_p = await db.persons.delete_one({"_id": pid})
        print(f"    🗑️  {(doc.get('name') or '?')[:28]:<29} persons={res_p.deleted_count}, "
              + ", ".join(f"{c}={deleted[c]}" for c, _ in OWNED))

    print(f"\n✅ APPLY terminé : {len(eligible)} Outsiders faux/test supprimés "
          f"({len(skipped)} skip conservés).")
    print(f"   Restauration possible : python remove_outsiders.py --rollback {backup_path}")


if __name__ == "__main__":
    asyncio.run(main())
