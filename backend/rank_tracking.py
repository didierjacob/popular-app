"""
Sujet 2 — Axe 1 mouvements up/down (Option B : rank_delta_24h).

Two operations:
  - snapshot_ranks(db): once per day (cron 03:30 UTC), writes the current rank
    of each approved person into `rank_24h_ago` + timestamp `rank_snapshot_at`.
  - update_rank_deltas(db): called after each Popularoo Index recalc
    (every 15 min via run_index_recalc_job), recomputes the current rank
    and writes `rank_delta_24h = rank_24h_ago - current_rank`
    (positive = moved up, negative = moved down).

Two separate rankings:
  - Celebrities: approved=True, suspended != True, NOT outsider, NOT self_boosted
    ordered by total_votes DESC, popularoo_index DESC (matches /api/people sort)
  - Outsiders: approved=True, suspended != True, (source=self_boosted OR category=outsider)
    ordered by popularoo_index DESC

Profiles created less than 24h ago have no `rank_24h_ago` yet → rank_delta_24h stays None.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _celebrity_filter() -> Dict[str, Any]:
    return {
        "approved": True,
        "suspended": {"$ne": True},
        "category": {"$ne": "outsider"},
        "source": {"$ne": "self_boosted"},
    }


def _outsider_filter() -> Dict[str, Any]:
    return {
        "approved": True,
        "suspended": {"$ne": True},
        "$or": [
            {"source": "self_boosted"},
            {"category": "outsider"},
            {"is_outsider": True},
        ],
    }


async def _ranked_ids(db, filter_q: Dict[str, Any], sort: List[Tuple[str, int]]) -> List[Any]:
    """Return ordered list of _id matching filter_q, sorted by `sort`."""
    cursor = db.persons.find(filter_q, {"_id": 1}).sort(sort)
    return [doc["_id"] async for doc in cursor]


async def snapshot_ranks(db) -> Dict[str, int]:
    """
    Cron 03:30 UTC. Snapshot current rank into `rank_24h_ago` and
    timestamp `rank_snapshot_at` for every approved profile.
    Two independent rankings (celebrities, outsiders).
    """
    now = _now_utc()

    celebrity_ids = await _ranked_ids(
        db, _celebrity_filter(),
        [("total_votes", -1), ("popularoo_index", -1)],
    )
    outsider_ids = await _ranked_ids(
        db, _outsider_filter(),
        [("popularoo_index", -1), ("total_votes", -1)],
    )

    written = 0
    for rank, pid in enumerate(celebrity_ids, start=1):
        await db.persons.update_one(
            {"_id": pid},
            {"$set": {"rank_24h_ago": rank, "rank_snapshot_at": now}},
        )
        written += 1
    for rank, pid in enumerate(outsider_ids, start=1):
        await db.persons.update_one(
            {"_id": pid},
            {"$set": {"rank_24h_ago": rank, "rank_snapshot_at": now}},
        )
        written += 1

    logger.info(
        f"📸 [Rank Snapshot] Wrote rank_24h_ago for {written} profiles "
        f"({len(celebrity_ids)} celebrities, {len(outsider_ids)} outsiders)"
    )
    return {
        "celebrities": len(celebrity_ids),
        "outsiders": len(outsider_ids),
        "total": written,
    }


async def update_rank_deltas(db) -> Dict[str, int]:
    """
    Called after each Popularoo Index recalc (15 min interval).
    Recomputes current rank and writes rank_delta_24h for profiles that
    have a rank_24h_ago snapshot. Profiles without snapshot get None
    (so the frontend can hide the badge).
    """
    celebrity_ids = await _ranked_ids(
        db, _celebrity_filter(),
        [("total_votes", -1), ("popularoo_index", -1)],
    )
    outsider_ids = await _ranked_ids(
        db, _outsider_filter(),
        [("popularoo_index", -1), ("total_votes", -1)],
    )

    updated = 0
    cleared = 0

    async def _apply(ids: List[Any]):
        nonlocal updated, cleared
        for current_rank, pid in enumerate(ids, start=1):
            doc = await db.persons.find_one(
                {"_id": pid}, {"rank_24h_ago": 1}
            )
            if not doc:
                continue
            rank_prev = doc.get("rank_24h_ago")
            if isinstance(rank_prev, int) and rank_prev > 0:
                delta = rank_prev - current_rank  # +N = moved up N positions
                await db.persons.update_one(
                    {"_id": pid},
                    {"$set": {"rank_delta_24h": int(delta)}},
                )
                updated += 1
            else:
                # No snapshot yet (profile too young). Make sure stale delta
                # from a previous identity doesn't linger.
                await db.persons.update_one(
                    {"_id": pid},
                    {"$unset": {"rank_delta_24h": ""}},
                )
                cleared += 1

    await _apply(celebrity_ids)
    await _apply(outsider_ids)

    logger.info(
        f"📊 [Rank Delta] Updated {updated} deltas, cleared {cleared} (no snapshot yet)"
    )
    return {"updated": updated, "cleared": cleared}
