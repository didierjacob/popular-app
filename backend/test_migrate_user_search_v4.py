"""
Local unit tests for candidate_detection.migrate_user_search_v4
(Vague 4, sous-tâche 9 — admin migration of legacy user_search profiles).

No network, no MongoDB: uses a tiny in-memory async fake of the `persons`
collection, including a `find()` cursor that understands the `$in` operator.
Run with:
    python3 test_migrate_user_search_v4.py

Covers the 7 expected cases:
  1. user_search, ext_score=20 (Cardin)   → new PI = 28.0, +40 simulated votes
  2. user_search, ext_score=87 (Cassel)   → new PI = 38.05
  3. user_search, ext_score=0 / None      → new PI = 25.0 (floor)
  4. already migrated (migrated_v4_at set) → skipped, untouched
  5. category=outsider                     → skipped (defensive guard)
  6. profile with real existing votes      → preserved + simulated added on top
  7. JSON response matches the schema
"""
import asyncio
from datetime import datetime, timezone

from candidate_detection import migrate_user_search_v4

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


# ──────────────────────────── In-memory fake DB ────────────────────────────
def _matches(doc, query):
    """Equality match, plus support for the {'$in': [...]} operator."""
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def _gen():
            for d in self._docs:
                yield d
        return _gen()


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self._id_seq = 1

    def find(self, query):
        return FakeCursor([d for d in self.docs if _matches(d, query)])

    async def find_one(self, query):
        for d in self.docs:
            if _matches(d, query):
                return d
        return None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class FakeDB:
    def __init__(self, persons=None):
        self.persons = FakeCollection(persons)


def make_person(_id, name, source="user_search", approved=True, ext_score=20.0,
                category="culture", popularoo_index=15.0, likes=0, dislikes=0,
                migrated_v4_at=None):
    doc = {
        "_id": _id,
        "name": name,
        "source": source,
        "approved": approved,
        "popularity_external_score": ext_score,
        "category": category,
        "score": popularoo_index,
        "popularoo_index": popularoo_index,
        "likes": likes,
        "dislikes": dislikes,
        "total_votes": likes + dislikes,
    }
    if migrated_v4_at is not None:
        doc["migrated_v4_at"] = migrated_v4_at
    return doc


# ──────────────────────────────── Harness ─────────────────────────────────
def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


async def main():
    results = []

    # ── Case 1: user_search, ext_score=20 → new PI = 28.0, +40 simulated votes ──
    db = FakeDB([make_person("p1", "Charlotte Cardin", ext_score=20.0,
                             popularoo_index=15.0, likes=0, dislikes=0)])
    out = await migrate_user_search_v4(db)
    p = db.persons.docs[0]
    # 25 + 20*0.15 = 28.0
    ok = (
        out["migrated"] == 1
        and abs(p["popularoo_index"] - 28.0) < 0.001
        and abs(p["score"] - 28.0) < 0.001
        and abs(p["initial_pi"] - 28.0) < 0.001
        and 26 <= p["seed_votes_likes"] <= 30
        and 10 <= p["seed_votes_dislikes"] <= 14
        and p["likes"] == p["seed_votes_likes"]          # 0 existing + simulated
        and p["dislikes"] == p["seed_votes_dislikes"]
        and p["total_votes"] == p["likes"] + p["dislikes"]
        and 36 <= p["total_votes"] <= 44
        and p["created_via"] == "deferred_v4_migrated"
        and p["migrated_v4_at"] is not None
        and p["last_updated"] is not None
    )
    results.append(_check("Case 1 — user_search ext=20 → PI 28.0, +40 simulated votes",
                          ok, f"new_pi={p['popularoo_index']} votes={p['total_votes']}"))

    # ── Case 2: user_search, ext_score=87 → new PI = 38.05 ──
    db = FakeDB([make_person("p2", "Vincent Cassel", ext_score=87.0,
                             popularoo_index=12.0)])
    out = await migrate_user_search_v4(db)
    p = db.persons.docs[0]
    # 25 + 87*0.15 = 38.05
    ok = (
        out["migrated"] == 1
        and abs(p["popularoo_index"] - 38.05) < 0.001
        and abs(p["initial_pi"] - 38.05) < 0.001
    )
    results.append(_check("Case 2 — user_search ext=87 → PI 38.05",
                          ok, f"new_pi={p['popularoo_index']}"))

    # ── Case 3: ext_score=0 / None → new PI = 25.0 (floor) ──
    db = FakeDB([
        make_person("p3a", "Zero Ext", ext_score=0),
        make_person("p3b", "None Ext", ext_score=None),
    ])
    out = await migrate_user_search_v4(db)
    pa, pb = db.persons.docs
    ok = (
        out["migrated"] == 2
        and abs(pa["popularoo_index"] - 25.0) < 0.001
        and abs(pa["initial_pi"] - 25.0) < 0.001
        and abs(pb["popularoo_index"] - 25.0) < 0.001
        and abs(pb["initial_pi"] - 25.0) < 0.001
    )
    results.append(_check("Case 3 — ext=0 / None → PI 25.0 (floor)",
                          ok, f"zero_pi={pa['popularoo_index']} none_pi={pb['popularoo_index']}"))

    # ── Case 4: already migrated (migrated_v4_at set) → skipped, untouched ──
    already = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db = FakeDB([make_person("p4", "Deja Migre", ext_score=87.0,
                             popularoo_index=33.0, migrated_v4_at=already)])
    out = await migrate_user_search_v4(db)
    p = db.persons.docs[0]
    ok = (
        out["migrated"] == 0
        and out["skipped_already_migrated"] == 1
        and out["total_eligible"] == 1
        and p["popularoo_index"] == 33.0          # untouched
        and p["migrated_v4_at"] == already        # untouched
        and "initial_pi" not in p                 # not re-migrated
    )
    results.append(_check("Case 4 — already migrated → skipped, untouched",
                          ok, f"migrated={out['migrated']} skipped={out['skipped_already_migrated']}"))

    # ── Case 5: category=outsider → skipped (defensive guard) ──
    db = FakeDB([make_person("p5", "Un Outsider", ext_score=50.0,
                             category="outsider", popularoo_index=15.0)])
    out = await migrate_user_search_v4(db)
    p = db.persons.docs[0]
    ok = (
        out["migrated"] == 0
        and out["skipped_outsider"] == 1
        and out["total_eligible"] == 1
        and p["popularoo_index"] == 15.0          # untouched
        and "initial_pi" not in p
    )
    results.append(_check("Case 5 — category=outsider → skipped (defensive guard)",
                          ok, f"migrated={out['migrated']} skipped_outsider={out['skipped_outsider']}"))

    # ── Case 6: profile with real existing votes → preserved + simulated added ──
    db = FakeDB([make_person("p6", "Avec Vrais Votes", ext_score=20.0,
                             popularoo_index=15.0, likes=5, dislikes=3)])
    out = await migrate_user_search_v4(db)
    p = db.persons.docs[0]
    ok = (
        out["migrated"] == 1
        and p["likes"] == 5 + p["seed_votes_likes"]      # 5 real + simulated
        and p["dislikes"] == 3 + p["seed_votes_dislikes"]
        and p["total_votes"] == p["likes"] + p["dislikes"]
        and 26 <= p["seed_votes_likes"] <= 30
        and 10 <= p["seed_votes_dislikes"] <= 14
    )
    results.append(_check("Case 6 — real existing votes preserved + simulated added on top",
                          ok, f"likes={p['likes']} (5 real + {p['seed_votes_likes']} sim) "
                              f"dislikes={p['dislikes']} (3 real + {p['seed_votes_dislikes']} sim)"))

    # ── Case 7: JSON response matches the schema ──
    db = FakeDB([
        make_person("p7a", "Florence Pugh", source="user_search", ext_score=60.0),
        make_person("p7b", "John Travolta", source="user_search_confirmed", ext_score=80.0),
        make_person("p7c", "Deja Fait", ext_score=40.0, migrated_v4_at=already),
        make_person("p7d", "Outsider Garde", ext_score=30.0, category="outsider"),
        make_person("p7e", "Pas Approuve", approved=False, ext_score=50.0),  # excluded by query
        make_person("p7f", "Une Seed", source="seed", ext_score=90.0),       # excluded by query
    ])
    out = await migrate_user_search_v4(db)
    expected_keys = {
        "total_eligible", "migrated", "skipped_already_migrated",
        "skipped_outsider", "errors", "migrated_sample", "errors_detail",
    }
    sample_ok = all(
        set(s.keys()) == {"name", "old_pi", "new_pi", "ext_score"}
        for s in out["migrated_sample"]
    )
    ok = (
        set(out.keys()) == expected_keys
        and out["total_eligible"] == 4       # 2 user_search + confirmed + migrated + outsider
        and out["migrated"] == 2             # Pugh + Travolta
        and out["skipped_already_migrated"] == 1
        and out["skipped_outsider"] == 1
        and out["errors"] == 0
        and isinstance(out["migrated_sample"], list)
        and len(out["migrated_sample"]) == 2
        and len(out["migrated_sample"]) <= 10
        and sample_ok
        and out["errors_detail"] == []
        # the source-excluded profiles were never counted
        and out["total_eligible"] + 2 == 6
    )
    results.append(_check("Case 7 — JSON response matches the schema",
                          ok, f"keys ok={set(out.keys()) == expected_keys} "
                              f"eligible={out['total_eligible']} migrated={out['migrated']} "
                              f"skipped_migrated={out['skipped_already_migrated']} "
                              f"skipped_outsider={out['skipped_outsider']} "
                              f"sample_len={len(out['migrated_sample'])}"))

    print()
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"{PASS} — {passed}/{total} cases passed")
    else:
        print(f"{FAIL} — {passed}/{total} cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
