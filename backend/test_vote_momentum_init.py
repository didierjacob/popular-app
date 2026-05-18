"""
Chantier B — autonomous tests for the vote_momentum initialization.

Verifies that approve_user_search_candidate (Vague 4 — sous-tâche 6) writes
vote_momentum: "up" on the persons document it creates, in line with the
implicit +1 like (Q3) and the new direction-arrow contract.

No network, no MongoDB — reuses the in-memory FakeDB harness from
test_approve_user_search_candidate.py.

Run with:
    python3 test_vote_momentum_init.py
"""
import asyncio
from datetime import datetime, timezone, timedelta

from candidate_detection import approve_user_search_candidate

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


# ── In-memory fake DB (same shape as test_approve_user_search_candidate.py) ──
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

    async def update_one(self, query, update, upsert=False):
        target = None
        for d in self.docs:
            if _matches(d, query):
                target = d
                break
        if target is None:
            if not upsert:
                return type("R", (), {"matched_count": 0, "modified_count": 0})()
            target = dict(query)
            for k, v in update.get("$setOnInsert", {}).items():
                target[k] = v
            self.docs.append(target)
        for k, v in update.get("$set", {}).items():
            target[k] = v
        for k, v in update.get("$addToSet", {}).items():
            target.setdefault(k, [])
            if v not in target[k]:
                target[k].append(v)
        return type("R", (), {"matched_count": 1, "modified_count": 1})()


class FakeDB:
    def __init__(self):
        self.persons = FakeCollection()
        self.candidate_queue = FakeCollection()
        self.person_ticks = FakeCollection()
        self.user_settings = FakeCollection()


def valid_result(ext=80.0):
    return {
        "valid": True,
        "popularity_external_score": ext,
        "wiki_score_norm": 70.0,
        "wiki_score_brut": 9000.0,
        "wiki_langs": ["fr", "en"],
        "wikidata_id": "Q9999",
        "category": "culture",
        "confidence": 80,
        "error_code": None,
    }


def make_candidate(name, slug, device="device-vm", pending_vote=1):
    return {
        "_id": f"cand-{name}",
        "name": name,
        "name_normalized": name.lower(),
        "slug": slug,
        "source": "user_search",
        "requested_by_device_id": device,
        "requested_at": datetime.now(timezone.utc) - timedelta(hours=24),
        "process_after": datetime.now(timezone.utc),
        "pending_vote_value": pending_vote,
        "status": "pending",
    }


def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


async def main():
    results = []

    # ── Case 1: approved V4 profile → vote_momentum = "up" written at creation ──
    db = FakeDB()
    cand = make_candidate("Vincent Cassel", "vincent-cassel")
    db.candidate_queue.docs.append(cand)
    async def vfn(_): return valid_result(ext=80.0)
    out = await approve_user_search_candidate(db, cand, validate_fn=vfn)
    person = db.persons.docs[-1] if db.persons.docs else None
    ok = (
        out["status"] == "approved"
        and person is not None
        and person.get("vote_momentum") == "up"
        and person.get("created_via") == "deferred_v4"
        and person.get("source") == "user_search"
    )
    results.append(_check(
        "Case 1 — V4 approved candidate → person.vote_momentum == 'up'",
        ok,
        f"vote_momentum={person.get('vote_momentum') if person else None}",
    ))

    # ── Case 2: V4 with pending_vote_value=0 → still vote_momentum 'up' (user
    #   submitted the name, which itself counts as a positive intent) ──
    db = FakeDB()
    cand = make_candidate("Charlotte Cardin", "charlotte-cardin", pending_vote=0)
    db.candidate_queue.docs.append(cand)
    out = await approve_user_search_candidate(db, cand, validate_fn=vfn)
    person = db.persons.docs[-1] if db.persons.docs else None
    ok = (
        out["status"] == "approved"
        and person is not None
        and person.get("vote_momentum") == "up"
    )
    results.append(_check(
        "Case 2 — V4 candidate without implicit +1 → vote_momentum still 'up'",
        ok,
        f"vote_momentum={person.get('vote_momentum') if person else None}",
    ))

    # ── Case 3: rejection path → no person created → no vote_momentum written ──
    db = FakeDB()
    cand = make_candidate("Banned Name", "banned-name")
    db.candidate_queue.docs.append(cand)
    async def vfn_reject(_):
        return {"valid": False, "error_code": "low_confidence",
                "error_message": "nope", "confidence": 30}
    out = await approve_user_search_candidate(db, cand, validate_fn=vfn_reject)
    ok = (out["status"] == "rejected" and len(db.persons.docs) == 0)
    results.append(_check(
        "Case 3 — rejected candidate → no person, no vote_momentum written",
        ok,
        f"persons_count={len(db.persons.docs)}",
    ))

    # ── Case 4: duplicate path → no new person → no overwrite of existing one ──
    db = FakeDB()
    db.persons.docs.append({
        "_id": "existing-oid",
        "name": "Vincent Cassel",
        "slug": "vincent-cassel",
        # Pre-existing profile already has vote_momentum 'down' from a real
        # dislike — duplicate path must not touch it.
        "vote_momentum": "down",
    })
    cand = make_candidate("Vincent Cassel", "vincent-cassel")
    db.candidate_queue.docs.append(cand)
    out = await approve_user_search_candidate(db, cand, validate_fn=vfn)
    existing = db.persons.docs[0]
    ok = (
        out["status"] == "duplicate"
        and len(db.persons.docs) == 1
        and existing.get("vote_momentum") == "down"
    )
    results.append(_check(
        "Case 4 — duplicate → existing vote_momentum preserved, no new person",
        ok,
        f"persons_count={len(db.persons.docs)} preserved={existing.get('vote_momentum')}",
    ))

    print()
    total = len(results)
    passed = sum(results)
    print(f"=== {passed}/{total} tests passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
