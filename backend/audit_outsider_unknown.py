"""
READ-ONLY audit — Vague 4 prep.

Goal: list every profile that is category "outsider" while having NO real `source`
(seeded outsiders from seed_outsiders.py carry no `source` field at all, which
popularoo_index.py reads as "unknown"). These are the "fantômes" to review
profile-by-profile before deciding suppression vs recategorisation.

This script ONLY reads. It performs no insert / update / delete.

Run:
    cd backend
    MONGO_URL="<prod connection string>" DB_NAME="popular_production" python audit_outsider_unknown.py
(or put MONGO_URL / DB_NAME in backend/.env — load_dotenv() picks them up)
"""

import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def _src(doc):
    """How popularoo_index.py sees the source: missing/None -> 'unknown'."""
    return doc.get("source") or "unknown"


async def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "popular_production")
    if not mongo_url:
        print("❌ MONGO_URL not set. Pass it as env var or put it in backend/.env")
        return

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # ---- All category == "outsider" profiles ----
    outsiders = await db.persons.find({"category": "outsider"}).to_list(length=None)
    print(f"\n=== {len(outsiders)} profiles with category == 'outsider' ===\n")

    # Breakdown by effective source
    from collections import Counter
    by_src = Counter(_src(d) for d in outsiders)
    for src, n in by_src.most_common():
        print(f"  source={src!r:<20} -> {n}")

    # ---- The "fantômes": category outsider + source unknown/missing ----
    ghosts = [d for d in outsiders if _src(d) == "unknown"]
    print(f"\n=== {len(ghosts)} fantômes (category 'outsider' + source unknown/missing) ===\n")

    hdr = f"{'name':<26} {'source':<10} {'tv':>5} {'L':>5} {'D':>5} {'SL':>4} {'pi':>6} {'score':>7} {'appr':>5} {'vis':>5} {'is_seed':>8}"
    print(hdr)
    print("-" * len(hdr))
    for d in sorted(ghosts, key=lambda x: -(x.get("score") or 0)):
        likes = d.get("likes", 0)
        dislikes = d.get("dislikes", 0)
        tv = d.get("total_votes", 0)
        pi = d.get("popularoo_index")
        score = d.get("score")
        appr = d.get("approved")
        vis = d.get("visible_in_rankings", "—")
        is_seed = d.get("is_seed", False)
        # incohérence flag: tv != likes+dislikes(+superlikes) or score >> pi
        sl = d.get("superlikes", 0)
        flags = []
        if tv != likes + dislikes + sl:
            flags.append(f"tv!=L+D+SL ({tv}!={likes}+{dislikes}+{sl})")
        if pi is not None and score is not None and score - pi > 5:
            flags.append(f"score>{pi}")
        flag_str = ("  ⚠ " + "; ".join(flags)) if flags else ""
        print(f"{(d.get('name') or '?')[:25]:<26} {_src(d):<10} {tv:>5} {likes:>5} "
              f"{dislikes:>5} {sl:>4} {str(pi):>6} {str(score):>7} {str(appr):>5} "
              f"{str(vis):>5} {str(is_seed):>8}{flag_str}")

    print(f"\nTotal fantômes: {len(ghosts)}")
    print("Aucune modification effectuée — audit lecture seule.\n")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
