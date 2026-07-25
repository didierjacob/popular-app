"""
Cœur honnête — AUDIT LECTURE SEULE des Outsiders (indice honnête).

⚠️  N'ÉCRIT RIEN. Aucun insert / update / delete. Réversibilité garantie : rien à annuler.

Lève les deux inconnues avant qu'on tranche l'indice Outsider honnête :

  (i)  Combien de VRAIS payeurs (source="self_boosted") vs SEEDS démo (is_seed=True) ?
       Ventilation par source / category / is_seed / is_outsider, et par tier de boost
       (active_boosts non-seed & non expirés = vrais achats).

  (ii) Que portent-ils AUJOURD'HUI ? popularoo_index affiché, likes/dislikes,
       seed_votes_*, total_votes — et surtout :
         • votes réels  = likes - seed_votes_likes  (0 = 100% fabriqué)
         • PI_formule   = min(3 + max(likes-dislikes,0)/10, 25)   [Branche 1 live]
         • écart PI_stocké vs PI_formule → révèle les seeds encore à 42-63
           (indice codé en dur au seeding) alors que la formule cape à 25.

Run (Render Shell) :
    cd /opt/render/project/src/backend
    python audit_outsider_honesty.py
(ou MONGO_URL / DB_NAME dans backend/.env — load_dotenv() les récupère)
"""

import os
import asyncio
from collections import Counter
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def is_outsider(d):
    return (d.get("source") == "self_boosted"
            or d.get("category") == "outsider"
            or d.get("is_outsider") is True)


def pi_formula(d):
    """Reproduit EXACTEMENT la Branche 1 de popularoo_index.py (live)."""
    likes = int(d.get("likes", 0) or 0)
    dislikes = int(d.get("dislikes", 0) or 0)
    net = max(likes - dislikes, 0)
    return round(min(3.0 + (net / 10.0) * 1.0, 25.0), 1)


async def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "popular_production")
    if not mongo_url:
        print("❌ MONGO_URL non défini. Passe-le en variable d'env ou dans backend/.env")
        return

    db = AsyncIOMotorClient(mongo_url)[db_name]
    now = datetime.utcnow()

    outsiders = await db.persons.find({
        "$or": [
            {"source": "self_boosted"},
            {"category": "outsider"},
            {"is_outsider": True},
        ]
    }).to_list(length=None)

    print(f"\n{'='*70}")
    print(f"  AUDIT OUTSIDERS (lecture seule) — base '{db_name}'")
    print(f"  {len(outsiders)} profils outsiders au total")
    print(f"{'='*70}\n")

    # ── (i) Ventilations ──
    print("── Ventilation par source ──")
    for s, n in Counter((d.get("source") or "unknown") for d in outsiders).most_common():
        print(f"     {s:<20}: {n}")

    print("\n── Ventilation is_seed ──")
    seeds = [d for d in outsiders if d.get("is_seed") is True]
    reals = [d for d in outsiders if d.get("is_seed") is not True]
    print(f"     is_seed=True (démo) : {len(seeds)}")
    print(f"     is_seed≠True (réel) : {len(reals)}")

    print("\n── VRAIS self_boosted (source=self_boosted, non-seed) ──")
    true_payers = [d for d in outsiders
                   if d.get("source") == "self_boosted" and d.get("is_seed") is not True]
    print(f"     → {len(true_payers)} vrais payeurs self_boosted")

    # ── active_boosts : vrais achats (non-seed, non expirés) ──
    real_boosts = await db.active_boosts.count_documents({
        "is_seed": {"$ne": True},
        "end_time": {"$gt": now},
    })
    seed_boosts = await db.active_boosts.count_documents({"is_seed": True})
    print(f"\n── active_boosts ──")
    print(f"     boosts réels (non-seed, actifs) : {real_boosts}")
    print(f"     boosts seed                     : {seed_boosts}")
    tiers = Counter()
    async for b in db.active_boosts.find({"is_seed": {"$ne": True}, "end_time": {"$gt": now}}):
        tiers[b.get("tier", "?")] += 1
    if tiers:
        print("     tiers payés réels :")
        for t, n in tiers.most_common():
            print(f"        {t:<16}: {n}")

    # ── (ii) État actuel : PI, votes réels, écart formule ──
    print(f"\n{'='*70}")
    print("  ÉTAT ACTUEL — PI stocké vs formule, part de faux votes")
    print(f"{'='*70}\n")

    hdr = (f"{'name':<24} {'src':<13} {'seed':>4} {'L':>5} {'D':>5} "
           f"{'sL':>5} {'sD':>5} {'réels':>6} {'PI_st':>6} {'PI_f':>5} {'Δ':>5}")
    print(hdr)
    print("-" * len(hdr))

    fabricated = 0   # votes réels == 0
    stale_pi = 0     # PI stocké > PI formule + 1  (seed encore à 42-63)
    for d in sorted(outsiders, key=lambda x: -(x.get("popularoo_index") or 0)):
        likes = int(d.get("likes", 0) or 0)
        dislikes = int(d.get("dislikes", 0) or 0)
        sL = int(d.get("seed_votes_likes", 0) or 0)
        sD = int(d.get("seed_votes_dislikes", 0) or 0)
        real = (likes - sL) - (dislikes - sD)
        pi_st = d.get("popularoo_index")
        pi_f = pi_formula(d)
        delta = round((pi_st or 0) - pi_f, 1)
        if (likes - sL) <= 0:
            fabricated += 1
        if pi_st is not None and (pi_st - pi_f) > 1:
            stale_pi += 1
        print(f"{(d.get('name') or '?')[:23]:<24} {(d.get('source') or 'unknown')[:12]:<13} "
              f"{str(bool(d.get('is_seed'))):>4} {likes:>5} {dislikes:>5} {sL:>5} {sD:>5} "
              f"{real:>6} {str(pi_st):>6} {pi_f:>5} {delta:>5}")

    print(f"\n{'='*70}")
    print("  SYNTHÈSE")
    print(f"{'='*70}")
    print(f"  Total outsiders                         : {len(outsiders)}")
    print(f"  · dont seeds démo (is_seed)             : {len(seeds)}")
    print(f"  · dont vrais self_boosted (payeurs)     : {len(true_payers)}")
    print(f"  Profils à 0 vrai like (likes-seed ≤ 0)  : {fabricated}  ← 100% fabriqué")
    print(f"  Profils PI_stocké > PI_formule +1       : {stale_pi}  ← indice seed figé (42-63) jamais recalculé")
    print(f"  Vrais boosts payés actifs (active_boosts): {real_boosts}")
    print("\n  Aucune écriture effectuée — audit lecture seule.\n")


if __name__ == "__main__":
    asyncio.run(main())
