"""
Chantier C — autonomous tests for run_potd_rotation_job.

Verifies:
  1. Pool filtering: only approved, non-suspended, non-outsider, non-self-boosted
     profiles are eligible.
  2. Selection happens within the top POTD_TOP_POOL_SIZE by popularoo_index.
  3. app_settings.potd_current is upserted with potd_person_id + selected_at.
  4. Empty-pool case logs a warning and writes nothing (no crash).
  5. Re-runs always pick *inside* the pool (probabilistic check over N draws).

No network, no MongoDB — in-memory async fake of persons + app_settings.

Run with:
    python3 test_potd_rotation.py
"""
import asyncio
import random
from datetime import datetime, timezone


# ── Tiny in-memory async fake matching what run_potd_rotation_job uses ───────

class _AsyncCursor:
    """Async iterator + `.sort().limit()` to mimic motor cursor behaviour."""

    def __init__(self, docs):
        self._docs = list(docs)
        self._sort_keys = None
        self._limit = None

    def sort(self, key_dir_pairs):
        # key_dir_pairs: list[(field, direction)] — direction 1 ASC, -1 DESC
        self._sort_keys = key_dir_pairs
        return self

    def limit(self, n):
        self._limit = n
        return self

    def __aiter__(self):
        docs = self._docs
        if self._sort_keys:
            for field, direction in reversed(self._sort_keys):
                docs = sorted(docs, key=lambda d: d.get(field, 0),
                              reverse=(direction == -1))
        if self._limit is not None:
            docs = docs[:self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class FakePersons:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query, projection=None):
        matched = [d for d in self.docs if _matches(d, query)]
        return _AsyncCursor(matched)


class FakeAppSettings:
    def __init__(self):
        self.docs = []

    async def update_one(self, query, update, upsert=False):
        target = None
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                target = d
                break
        if target is None:
            if not upsert:
                return type("R", (), {"matched_count": 0, "modified_count": 0})()
            target = dict(query)
            self.docs.append(target)
        for k, v in update.get("$set", {}).items():
            target[k] = v
        return type("R", (), {"matched_count": 1, "modified_count": 1})()

    async def find_one(self, query):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None


class FakeDB:
    def __init__(self, persons_docs):
        self.persons = FakePersons(persons_docs)
        self.app_settings = FakeAppSettings()


# ── Test helpers ─────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


def _make_person(oid, name, index, **overrides):
    base = {
        "_id": oid,
        "name": name,
        "popularoo_index": index,
        "total_votes": int(index * 10),
        "approved": True,
        "suspended": False,
        "category": "culture",
        "source": "seed",
    }
    base.update(overrides)
    return base


async def main():
    from scheduler import run_potd_rotation_job, POTD_TOP_POOL_SIZE

    results = []

    # ── Case 1: 200 eligible profiles → pool = top 100 by index, picked must be inside.
    random.seed(42)
    persons = [_make_person(f"oid-{i:03d}", f"Person {i:03d}", index=200 - i)
               for i in range(200)]
    db = FakeDB(persons)
    await run_potd_rotation_job(db)
    settings = await db.app_settings.find_one({"_id": "potd_current"})
    eligible_top_ids = {f"oid-{i:03d}" for i in range(POTD_TOP_POOL_SIZE)}
    ok = (
        settings is not None
        and settings.get("potd_person_id") in eligible_top_ids
        and isinstance(settings.get("selected_at"), datetime)
        and settings.get("selected_at").tzinfo == timezone.utc
    )
    results.append(_check(
        f"Case 1 — pick lands inside top {POTD_TOP_POOL_SIZE} by popularoo_index",
        ok,
        f"picked={settings.get('potd_person_id') if settings else None}",
    ))

    # ── Case 2: filtering — outsiders / suspended / unapproved / self_boosted skipped.
    persons = [
        _make_person("ok-1", "Eligible One", 90.0),
        _make_person("ok-2", "Eligible Two", 80.0),
        _make_person("out-1", "Outsider", 95.0, category="outsider"),
        _make_person("sus-1", "Suspended", 99.0, suspended=True),
        _make_person("napp-1", "NotApproved", 98.0, approved=False),
        _make_person("sb-1", "SelfBoost", 97.0, source="self_boosted"),
    ]
    db = FakeDB(persons)
    random.seed(0)
    # 20 runs to be confident the filter actually excludes the others.
    picked_ids = set()
    for _ in range(20):
        await run_potd_rotation_job(db)
        s = await db.app_settings.find_one({"_id": "potd_current"})
        picked_ids.add(s.get("potd_person_id"))
    eligible = {"ok-1", "ok-2"}
    ok = picked_ids.issubset(eligible) and picked_ids == eligible
    results.append(_check(
        "Case 2 — outsiders/suspended/unapproved/self_boosted excluded from pool",
        ok,
        f"picked over 20 runs={sorted(picked_ids)}",
    ))

    # ── Case 3: empty eligible pool → no write, no crash.
    persons = [_make_person("out-1", "OnlyOutsider", 50.0, category="outsider")]
    db = FakeDB(persons)
    await run_potd_rotation_job(db)
    settings = await db.app_settings.find_one({"_id": "potd_current"})
    ok = settings is None  # nothing was upserted
    results.append(_check(
        "Case 3 — empty eligible pool → no upsert, no crash",
        ok,
        f"app_settings.docs={db.app_settings.docs}",
    ))

    # ── Case 4: re-run upserts (single potd_current doc, never duplicates).
    persons = [_make_person(f"p-{i}", f"P{i}", index=100 - i) for i in range(5)]
    db = FakeDB(persons)
    await run_potd_rotation_job(db)
    await run_potd_rotation_job(db)
    await run_potd_rotation_job(db)
    docs_with_id = [d for d in db.app_settings.docs if d.get("_id") == "potd_current"]
    ok = len(docs_with_id) == 1
    results.append(_check(
        "Case 4 — re-runs upsert (single potd_current doc)",
        ok,
        f"docs_with_potd_current={len(docs_with_id)}",
    ))

    print()
    total = len(results)
    passed = sum(results)
    print(f"=== {passed}/{total} tests passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
