"""
Local unit tests for candidate_detection.process_celebrity_request
(Vague 4, sous-tâche 5 — endpoint POST /api/submit-celebrity-request).

No network, no MongoDB needed: uses a tiny in-memory async fake of the three
collections the helper touches (persons, candidate_queue, app_settings).
Run with:
    python3 test_submit_celebrity_request.py

Covers the 5 expected cases:
  1. New unknown name            → queued + entry in candidate_queue (+24h)
  2. Name already in persons     → already_exists
  3. Name already pending        → already_pending
  4. Name in seed_blocklist      → rejected
  5. Empty name / empty device   → ValueError (endpoint maps to HTTP 400)
"""
import asyncio
from datetime import datetime, timezone, timedelta

from candidate_detection import process_celebrity_request, slugify_name

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


# ──────────────────────────── In-memory fake DB ────────────────────────────
def _matches(doc, query):
    return all(doc.get(k) == v for k, v in query.items())


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self._id_seq = 1

    async def find_one(self, query):
        for d in self.docs:
            if _matches(d, query):
                return d
        return None

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", f"fake-oid-{self._id_seq}")
        self._id_seq += 1
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc["_id"]})()


class FakeDB:
    def __init__(self, persons=None, candidate_queue=None, app_settings=None):
        self.persons = FakeCollection(persons)
        self.candidate_queue = FakeCollection(candidate_queue)
        self.app_settings = FakeCollection(app_settings)


# ──────────────────────────────── Harness ─────────────────────────────────
def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


async def main():
    results = []

    # ── Case 1: new unknown name → queued + entry created in candidate_queue ──
    db = FakeDB()
    before = datetime.now(timezone.utc)
    res = await process_celebrity_request(db, "  timothée  chalamet ", "device-abc-123")
    after = datetime.now(timezone.utc)
    entry = db.candidate_queue.docs[-1] if db.candidate_queue.docs else None
    ok = (
        res["status"] == "queued"
        and entry is not None
        and entry["status"] == "pending"
        and entry["source"] == "user_search"
        and entry["name"] == "Timothée Chalamet"          # trim + collapse + Title Case
        and entry["slug"] == "timothe-chalamet"           # accent stripped (mirrors server.slugify)
        and entry["requested_by_device_id"] == "device-abc-123"
        and entry["pending_vote_value"] == 1              # implicit like (Q3)
        and entry["name_normalized"] == "timothee chalamet"
        # process_after ≈ requested_at + 24h
        and timedelta(hours=24) - timedelta(seconds=5)
            <= (entry["process_after"] - entry["requested_at"])
            <= timedelta(hours=24) + timedelta(seconds=5)
        and before + timedelta(hours=24) - timedelta(seconds=5)
            <= entry["process_after"]
            <= after + timedelta(hours=24) + timedelta(seconds=5)
    )
    results.append(_check(
        "Case 1 — new unknown name → queued + pending entry @ +24h",
        ok,
        f"status={res['status']} name={entry and entry['name']!r} "
        f"slug={entry and entry['slug']!r} pending_vote_value={entry and entry.get('pending_vote_value')} "
        f"delay={entry and (entry['process_after'] - entry['requested_at'])}",
    ))

    # ── Case 2: name already in persons → already_exists ──
    db = FakeDB(persons=[{"_id": "person-trump-1", "slug": slugify_name("Donald Trump")}])
    res = await process_celebrity_request(db, "donald trump", "device-xyz")
    ok = (
        res["status"] == "already_exists"
        and res["person_id"] == "person-trump-1"
        and len(db.candidate_queue.docs) == 0              # no new queue entry
    )
    results.append(_check(
        "Case 2 — existing person (Donald Trump) → already_exists",
        ok,
        f"status={res['status']} person_id={res.get('person_id')!r} "
        f"queue_size={len(db.candidate_queue.docs)}",
    ))

    # ── Case 3: name already pending in queue → already_pending ──
    original_after = datetime.now(timezone.utc) + timedelta(hours=18)
    db = FakeDB(candidate_queue=[{
        "_id": "cq-1",
        "name": "Greta Thunberg",
        "slug": slugify_name("Greta Thunberg"),
        "source": "user_search",
        "status": "pending",
        "process_after": original_after,
    }])
    res = await process_celebrity_request(db, "Greta Thunberg", "device-2")
    ok = (
        res["status"] == "already_pending"
        and res["process_after"] == original_after.isoformat()   # original kept
        and len(db.candidate_queue.docs) == 1                    # no duplication
    )
    results.append(_check(
        "Case 3 — already pending in queue → already_pending (no dup)",
        ok,
        f"status={res['status']} process_after={res.get('process_after')!r} "
        f"queue_size={len(db.candidate_queue.docs)}",
    ))

    # ── Case 4: name in seed_blocklist → rejected ──
    blocked_slug = slugify_name("Blocked Person")
    db = FakeDB(app_settings=[{"_id": "global", "seed_blocklist": [blocked_slug]}])
    res = await process_celebrity_request(db, "blocked person", "device-3")
    ok = (
        res["status"] == "rejected"
        and "process_after" not in res                     # helper returns bare rejection
        and len(db.candidate_queue.docs) == 0              # nothing enqueued
    )
    results.append(_check(
        "Case 4 — blocklisted slug → rejected (nothing enqueued)",
        ok,
        f"status={res['status']} queue_size={len(db.candidate_queue.docs)} "
        f"(endpoint masks this as 'queued' to the user)",
    ))

    # ── Case 5: empty name / empty device_id → ValueError (→ HTTP 400) ──
    db = FakeDB()
    ok_name = False
    try:
        await process_celebrity_request(db, "   ", "device-4")
    except ValueError as e:
        ok_name = "name" in str(e)
    ok_device = False
    try:
        await process_celebrity_request(db, "Some Name", "")
    except ValueError as e:
        ok_device = "device_id" in str(e)
    ok = ok_name and ok_device and len(db.candidate_queue.docs) == 0
    results.append(_check(
        "Case 5 — empty name / empty device_id → ValueError (clean 400)",
        ok,
        f"empty_name_raised={ok_name} empty_device_raised={ok_device}",
    ))

    print("=" * 60)
    print(f"TOTAL: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
