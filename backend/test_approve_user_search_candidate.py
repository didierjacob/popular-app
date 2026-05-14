"""
Local unit tests for candidate_detection.approve_user_search_candidate
(Vague 4, sous-tâche 6 — third branch of admin approve_candidate).

No network, no MongoDB: uses a tiny in-memory async fake of the collections
the helper touches (persons, candidate_queue, person_ticks, user_settings),
and injects a fake validate_fn so no Wikipedia/Wikidata call is made.
Run with:
    python3 test_approve_user_search_candidate.py

Covers the 6 expected cases:
  1. Valid user_search (Vincent Cassel, ext=87)  → created, PI ~38, 40 votes, contrib
  2. Valid user_search (Charlotte Cardin, ext=20) → created, PI = 28.0
  3. Invalid user_search (low_confidence)         → rejected, no person created
  4. Valid user_search, pending_vote_value = 0    → created, no implicit +1 like
  5. Slug already in persons                      → duplicate, no person created
  6. Randomisation: 3 runs of the same profile    → seed_votes_likes varies in 26..30
"""
import asyncio
from datetime import datetime, timezone, timedelta

from candidate_detection import approve_user_search_candidate, USER_SEARCH_LIKES_RANGE

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
    def __init__(self, persons=None, candidate_queue=None,
                 person_ticks=None, user_settings=None):
        self.persons = FakeCollection(persons)
        self.candidate_queue = FakeCollection(candidate_queue)
        self.person_ticks = FakeCollection(person_ticks)
        self.user_settings = FakeCollection(user_settings)


# ─────────────────────── Fake validate_single_name ────────────────────────
def make_validate_fn(profiles):
    """profiles: {name -> result dict}. Returns an async fn mimicking validate_single_name."""
    async def _fake(name):
        return profiles[name]
    return _fake


def valid_result(category="culture", ext=87.0, confidence=82):
    return {
        "valid": True,
        "popularity_external_score": ext,
        "wiki_score_norm": 71.0,
        "wiki_score_brut": 12345.0,
        "wiki_langs": ["fr", "en", "de"],
        "wikidata_id": "Q12345",
        "category": category,
        "confidence": confidence,
        "error_code": None,
    }


def invalid_result(error_code="low_confidence"):
    return {"valid": False, "error_code": error_code,
            "error_message": "nope", "confidence": 40}


def make_candidate(name, slug, device="device-xyz", pending_vote=1, _id="cand-1"):
    return {
        "_id": _id,
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


# ──────────────────────────────── Harness ─────────────────────────────────
def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


async def main():
    results = []

    # ── Case 1: valid user_search (Vincent Cassel, ext=87) ──
    db = FakeDB()
    cand = make_candidate("Vincent Cassel", "vincent-cassel", device="device-vc")
    db.candidate_queue.docs.append(cand)
    validate_fn = make_validate_fn({"Vincent Cassel": valid_result(category="culture", ext=87.0, confidence=82)})
    out = await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
    person = db.persons.docs[-1] if db.persons.docs else None
    tick = db.person_ticks.docs[-1] if db.person_ticks.docs else None
    settings = db.user_settings.docs[-1] if db.user_settings.docs else None
    # 25 + 87*0.15 = 38.05
    ok = (
        out["status"] == "approved"
        and abs(out["initial_pi"] - 38.05) < 0.001
        and person is not None
        and person["source"] == "user_search"
        and person["created_via"] == "deferred_v4"
        and person["visible_in_rankings"] is True
        and person["approved"] is True
        and person["suspended"] is False
        and person["category"] == "culture"
        and abs(person["score"] - 38.05) < 0.001
        and abs(person["popularoo_index"] - 38.05) < 0.001
        and abs(person["initial_pi"] - 38.05) < 0.001
        and person["popularity_external_score"] == 87.0
        and person["wikidata_id"] == "Q12345"
        and 27 <= person["likes"] <= 31          # 26..30 + implicit +1
        and 10 <= person["dislikes"] <= 14
        and person["likes"] == person["seed_votes_likes"] + 1   # implicit like applied
        and person["dislikes"] == person["seed_votes_dislikes"]
        and person["total_votes"] == person["likes"] + person["dislikes"]
        and 37 <= person["total_votes"] <= 45
        and person["superlikes"] == 0
        and person["active_strikes"] == 0
        and person["created_by_device_id"] == "device-vc"
        # initial tick
        and tick is not None and abs(tick["score"] - 38.05) < 0.001
        and tick["person_id"] == person["_id"]
        # contributor tracking
        and settings is not None
        and settings["device_id"] == "device-vc"
        and str(person["_id"]) in settings["contributed_person_ids"]
        # candidate_queue updated
        and cand["status"] == "approved"
        and cand["person_id"] == str(person["_id"])
        and abs(cand["initial_pi"] - 38.05) < 0.001
        and cand["validation_confidence"] == 82
    )
    results.append(_check("Case 1 — valid (Vincent Cassel, ext=87) → PI 38.05, ~40 votes, contrib",
                          ok, f"PI={out.get('initial_pi')} likes={person['likes'] if person else None} "
                              f"dislikes={person['dislikes'] if person else None} "
                              f"total={person['total_votes'] if person else None}"))

    # ── Case 2: valid user_search (Charlotte Cardin, ext=20) → PI = 28.0 ──
    db = FakeDB()
    cand = make_candidate("Charlotte Cardin", "charlotte-cardin", device="device-cc")
    db.candidate_queue.docs.append(cand)
    validate_fn = make_validate_fn({"Charlotte Cardin": valid_result(category="culture", ext=20.0, confidence=70)})
    out = await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
    person = db.persons.docs[-1] if db.persons.docs else None
    # 25 + 20*0.15 = 28.0
    ok = (
        out["status"] == "approved"
        and abs(out["initial_pi"] - 28.0) < 0.001
        and person is not None
        and abs(person["initial_pi"] - 28.0) < 0.001
        and abs(person["popularoo_index"] - 28.0) < 0.001
    )
    results.append(_check("Case 2 — valid (Charlotte Cardin, ext=20) → PI 28.0",
                          ok, f"PI={out.get('initial_pi')}"))

    # ── Case 3: invalid user_search (low_confidence) → rejected, no person ──
    db = FakeDB()
    cand = make_candidate("Inconnu Test", "inconnu-test")
    db.candidate_queue.docs.append(cand)
    validate_fn = make_validate_fn({"Inconnu Test": invalid_result("low_confidence")})
    out = await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
    ok = (
        out["status"] == "rejected"
        and out["error_code"] == "low_confidence"
        and len(db.persons.docs) == 0
        and len(db.person_ticks.docs) == 0
        and cand["status"] == "rejected"
        and cand["validation_error"] == "low_confidence"
    )
    results.append(_check("Case 3 — invalid (low_confidence) → rejected, no person created",
                          ok, f"status={out.get('status')} persons={len(db.persons.docs)}"))

    # ── Case 4: valid user_search, pending_vote_value = 0 → no implicit +1 ──
    db = FakeDB()
    cand = make_candidate("Sans Like", "sans-like", pending_vote=0)
    db.candidate_queue.docs.append(cand)
    validate_fn = make_validate_fn({"Sans Like": valid_result(ext=50.0)})
    out = await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
    person = db.persons.docs[-1] if db.persons.docs else None
    ok = (
        out["status"] == "approved"
        and person is not None
        and person["likes"] == person["seed_votes_likes"]        # no +1
        and person["dislikes"] == person["seed_votes_dislikes"]
        and 26 <= person["likes"] <= 30
        and person["total_votes"] == person["likes"] + person["dislikes"]
    )
    results.append(_check("Case 4 — pending_vote_value=0 → created without implicit +1 like",
                          ok, f"likes={person['likes'] if person else None} "
                              f"seed_likes={person['seed_votes_likes'] if person else None}"))

    # ── Case 5: slug already in persons → duplicate, no person created ──
    db = FakeDB(persons=[{"_id": "existing-1", "slug": "vincent-cassel", "name": "Vincent Cassel"}])
    cand = make_candidate("Vincent Cassel", "vincent-cassel")
    db.candidate_queue.docs.append(cand)
    validate_fn = make_validate_fn({"Vincent Cassel": valid_result(ext=87.0)})
    out = await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
    ok = (
        out["status"] == "duplicate"
        and out["person_id"] == "existing-1"
        and len(db.persons.docs) == 1            # nothing created
        and len(db.person_ticks.docs) == 0
        and cand["status"] == "duplicate"
        and cand["person_id"] == "existing-1"
    )
    results.append(_check("Case 5 — slug already in persons → duplicate, no person created",
                          ok, f"status={out.get('status')} persons={len(db.persons.docs)}"))

    # ── Case 6: randomisation — 3 runs of same profile, seed_votes_likes varies ──
    seed_likes_seen = []
    for i in range(3):
        db = FakeDB()
        cand = make_candidate("Repeat Profil", "repeat-profil", _id=f"cand-r{i}")
        db.candidate_queue.docs.append(cand)
        validate_fn = make_validate_fn({"Repeat Profil": valid_result(ext=60.0)})
        await approve_user_search_candidate(db, cand, validate_fn=validate_fn)
        seed_likes_seen.append(db.persons.docs[-1]["seed_votes_likes"])
    lo, hi = USER_SEARCH_LIKES_RANGE
    ok = all(lo <= v <= hi for v in seed_likes_seen)
    # not a hard requirement that all 3 differ, but values must stay in range;
    # flag if they're suspiciously all identical
    detail = f"seed_votes_likes over 3 runs = {seed_likes_seen} (expected each in {lo}..{hi})"
    if len(set(seed_likes_seen)) == 1:
        detail += "  [note: all identical — re-run to confirm randomisation]"
    results.append(_check("Case 6 — randomisation: 3 runs → seed_votes_likes in 26..30", ok, detail))

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
