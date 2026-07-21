"""
Local unit tests for scheduler.run_process_user_submissions_job
(Vague 4, sous-tâche 7 — job qui dépile les soumissions user_search à échéance).

No network, no MongoDB: tiny in-memory async fake of the collections the job
and approve_user_search_candidate touch (candidate_queue, persons, person_ticks,
user_settings). validate_single_name is monkeypatched so no Wikipedia/Wikidata
call is made.

Run with:
    python3 test_process_user_submissions_job.py

Covers the 4 expected cases:
  1. candidate_queue entry, process_after in the past   → status "approved" + persons profile created
  2. candidate_queue entry, process_after in the future → stays "pending", ignored by the job
  3. source != "user_search" (auto_detection)           → ignored by the job
  4. approve_user_search_candidate raises for one entry → last_error written, job continues, no crash
"""
import asyncio
from datetime import datetime, timezone, timedelta

import candidate_detection
from scheduler import run_process_user_submissions_job

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


# ──────────────────────────── In-memory fake DB ────────────────────────────
def _match_value(actual, condition):
    """Equality match, plus the Mongo operators the job query uses."""
    if isinstance(condition, dict):
        for op, operand in condition.items():
            if op == "$lte":
                if actual is None or not (actual <= operand):
                    return False
            elif op == "$lt":
                if actual is None or not (actual < operand):
                    return False
            elif op == "$gt":
                if actual is None or not (actual > operand):
                    return False
            elif op == "$ne":
                if actual == operand:
                    return False
            else:
                raise NotImplementedError(f"FakeCollection: unsupported operator {op}")
        return True
    return actual == condition


def _matches(doc, query):
    return all(_match_value(doc.get(k), v) for k, v in query.items())


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        self._docs = sorted(self._docs, key=lambda d: d.get(key), reverse=(direction == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return list(self._docs if length is None else self._docs[:length])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self._id_seq = 1

    def find(self, query):
        # Return references to the live docs so update_one is reflected.
        return FakeCursor([d for d in self.docs if _matches(d, query)])

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
    def __init__(self, candidate_queue=None, persons=None,
                 person_ticks=None, user_settings=None, app_settings=None):
        self.candidate_queue = FakeCollection(candidate_queue)
        self.persons = FakeCollection(persons)
        self.person_ticks = FakeCollection(person_ticks)
        self.user_settings = FakeCollection(user_settings)
        # approve_user_search_candidate Step 2b (anti-ghost) lit app_settings.
        # Vide par défaut → aucune blocklist ne s'applique dans ces tests.
        self.app_settings = FakeCollection(app_settings)


# ─────────────────────── Fake validate_single_name ────────────────────────
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


def make_validate_fn(profiles):
    async def _fake(name):
        return profiles.get(name, {"valid": False, "error_code": "low_confidence"})
    return _fake


def make_candidate(name, slug, source="user_search", status="pending",
                   process_after_offset_hours=-1, requested_at_offset_hours=-24,
                   device="device-xyz", pending_vote=1, _id=None,
                   moderation_status="approved"):
    # Bloc 2 : le job ne dépile QUE les docs moderation_status="approved". Les
    # cas qui DOIVENT être publiés en reçoivent un par défaut ; Case 5 passe
    # explicitement "unreviewed" pour prouver la coupure d'auto-publication.
    now = datetime.now(timezone.utc)
    return {
        "_id": _id or f"cand-{slug}",
        "name": name,
        "name_normalized": name.lower(),
        "slug": slug,
        "source": source,
        "status": status,
        "moderation_status": moderation_status,
        "requested_by_device_id": device,
        "requested_at": now + timedelta(hours=requested_at_offset_hours),
        "process_after": now + timedelta(hours=process_after_offset_hours),
        "pending_vote_value": pending_vote,
    }


# ──────────────────────────────── Harness ─────────────────────────────────
def _check(label, ok, detail=""):
    print(f"[{PASS if ok else FAIL}] {label}")
    if detail:
        print(f"    {detail}")
    return ok


async def main():
    results = []
    _real_validate = candidate_detection.validate_single_name
    _real_approve = candidate_detection.approve_user_search_candidate

    # ── Case 1: process_after in the past → approved + persons profile created ──
    candidate_detection.validate_single_name = make_validate_fn(
        {"Vincent Cassel": valid_result(category="culture", ext=87.0, confidence=82)}
    )
    db = FakeDB()
    cand = make_candidate("Vincent Cassel", "vincent-cassel", process_after_offset_hours=-1)
    db.candidate_queue.docs.append(cand)
    summary = await run_process_user_submissions_job(db)
    person = db.persons.docs[-1] if db.persons.docs else None
    tick = db.person_ticks.docs[-1] if db.person_ticks.docs else None
    ok = (
        summary is not None
        and summary["processed"] == 1 and summary["approved"] == 1
        and summary["rejected"] == 0 and summary["duplicates"] == 0 and summary["errors"] == 0
        and cand["status"] == "approved"
        and person is not None
        and person["slug"] == "vincent-cassel"
        and person["source"] == "user_search"
        and person["approved"] is True
        and abs(person["popularoo_index"] - 38.05) < 0.001   # 25 + 87*0.15
        and cand["person_id"] == str(person["_id"])
        and tick is not None and tick["person_id"] == person["_id"]
        and "last_error" not in cand
    )
    results.append(_check(
        "Case 1 — process_after in the past → status 'approved' + persons profile created",
        ok, f"summary={summary} person_status={cand.get('status')} persons={len(db.persons.docs)}"))

    # ── Case 2: process_after in the future → stays pending, ignored ──
    candidate_detection.validate_single_name = make_validate_fn(
        {"Future Profil": valid_result(ext=50.0)}
    )
    db = FakeDB()
    cand = make_candidate("Future Profil", "future-profil", process_after_offset_hours=+12)
    db.candidate_queue.docs.append(cand)
    summary = await run_process_user_submissions_job(db)
    ok = (
        summary is None                       # job returns early: "no due submissions"
        and cand["status"] == "pending"
        and len(db.persons.docs) == 0
        and "last_error" not in cand
    )
    results.append(_check(
        "Case 2 — process_after in the future → stays 'pending', ignored by the job",
        ok, f"summary={summary} status={cand.get('status')} persons={len(db.persons.docs)}"))

    # ── Case 3: source != user_search → ignored by the job ──
    candidate_detection.validate_single_name = make_validate_fn(
        {"Auto Detected": valid_result(ext=60.0)}
    )
    db = FakeDB()
    cand = make_candidate("Auto Detected", "auto-detected", source="auto_detection",
                          process_after_offset_hours=-1)
    db.candidate_queue.docs.append(cand)
    summary = await run_process_user_submissions_job(db)
    ok = (
        summary is None                       # not picked up → "no due submissions"
        and cand["status"] == "pending"
        and len(db.persons.docs) == 0
    )
    results.append(_check(
        "Case 3 — source 'auto_detection' → ignored by the job",
        ok, f"summary={summary} status={cand.get('status')} persons={len(db.persons.docs)}"))

    # ── Case 4: approve raises for one entry → last_error written, job continues ──
    async def _flaky_approve(db_, candidate):
        if candidate["name"] == "Boom Profil":
            raise RuntimeError("simulated Wikipedia timeout")
        return {"status": "approved", "name": candidate["name"], "person_id": "ok-1"}

    candidate_detection.approve_user_search_candidate = _flaky_approve
    db = FakeDB()
    # FIFO order: Boom is the oldest (requested first), Good is newer
    boom = make_candidate("Boom Profil", "boom-profil",
                          requested_at_offset_hours=-30, process_after_offset_hours=-2,
                          _id="cand-boom")
    good = make_candidate("Good Profil", "good-profil",
                          requested_at_offset_hours=-20, process_after_offset_hours=-1,
                          _id="cand-good")
    db.candidate_queue.docs.extend([good, boom])   # inserted out of order on purpose
    summary = await run_process_user_submissions_job(db)
    ok = (
        summary is not None
        and summary["processed"] == 2
        and summary["errors"] == 1
        and summary["approved"] == 1
        and boom.get("last_error") == "simulated Wikipedia timeout"
        and "last_error_at" in boom
        and boom["status"] == "pending"          # untouched → retried next run
        and "last_error" not in good             # the healthy one was still processed
    )
    results.append(_check(
        "Case 4 — approve raises for one entry → last_error written, job continues, no crash",
        ok, f"summary={summary} boom.last_error={boom.get('last_error')!r} "
            f"good.last_error={good.get('last_error')!r}"))

    # ── Case 5 (Bloc 2 — COUPURE) : moderation_status="unreviewed" → JAMAIS publié ──
    # Doc éligible sur tous les autres critères (user_search, pending, échéance
    # passée), mais NON approuvé par un admin. Le job ne doit PAS le dépiler :
    # aucun person créé, statut inchangé. C'est la preuve de la coupure d'auto-pub.
    _approve_called = {"hit": False}

    async def _spy_approve(db_, candidate):
        _approve_called["hit"] = True
        return {"status": "approved", "name": candidate["name"], "person_id": "should-not-happen"}

    candidate_detection.approve_user_search_candidate = _spy_approve
    candidate_detection.validate_single_name = make_validate_fn(
        {"Unreviewed Profil": valid_result(ext=70.0)}
    )
    db = FakeDB()
    cand = make_candidate("Unreviewed Profil", "unreviewed-profil",
                          process_after_offset_hours=-2, moderation_status="unreviewed")
    db.candidate_queue.docs.append(cand)
    summary = await run_process_user_submissions_job(db)
    ok = (
        summary is None                       # rien d'éligible → "no due submissions"
        and _approve_called["hit"] is False   # approve JAMAIS appelé
        and cand["status"] == "pending"       # doc intact, attend le clic admin
        and cand["moderation_status"] == "unreviewed"
        and len(db.persons.docs) == 0         # AUCUNE personne publiée
    )
    results.append(_check(
        "Case 5 — moderation_status 'unreviewed' → NON publié par le job (coupure auto-pub)",
        ok, f"summary={summary} approve_called={_approve_called['hit']} "
            f"status={cand.get('status')} persons={len(db.persons.docs)}"))

    candidate_detection.validate_single_name = _real_validate
    candidate_detection.approve_user_search_candidate = _real_approve

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
