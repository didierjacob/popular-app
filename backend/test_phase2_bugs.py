"""
Phase 2 Integration Tests - Bug Verification Suite (B1, B2, B4, B5)
====================================================================
Use this script to verify that the 4 critical bug fixes are functional.
Run: python3 test_phase2_bugs.py

IMPORTANT:
- Uses DB_NAME from .env (default: test_database)
- Route: POST /api/people/{id}/vote (NOT /api/vote/{id})
- Cleans up all test data after execution
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_URL = "http://localhost:8001/api"
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "test_database")

async def run_tests():
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    now = datetime.now(timezone.utc)
    
    results = {"passed": 0, "failed": 0, "errors": []}
    
    # ==================== SETUP ====================
    test_seed = {
        "name": "Test Seed Person",
        "slug": "test-seed-person-diag",
        "category": "other",
        "approved": True,
        "source": "seed",
        "score": 50.0,
        "likes": 100,
        "dislikes": 10,
        "superlikes": 5,
        "total_votes": 115,
        "created_at": now,
        "updated_at": now,
    }
    seed_result = await db.persons.insert_one(test_seed)
    seed_id = str(seed_result.inserted_id)
    print(f"[SETUP] Seed person created: {seed_id}")
    
    test_outsider = {
        "name": "Test Outsider Diag",
        "slug": "test-outsider-diag",
        "category": "other",
        "approved": True,
        "source": "self_boosted",
        "score": 50.0,
        "likes": 0,
        "dislikes": 0,
        "total_votes": 0,
        "created_at": now,
        "updated_at": now,
    }
    outsider_result = await db.persons.insert_one(test_outsider)
    outsider_id = str(outsider_result.inserted_id)
    print(f"[SETUP] Outsider created: {outsider_id}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # ==================== TEST B1 ====================
        print("\n" + "="*60)
        print("TEST B1: Superlike on seed outsider")
        print("="*60)
        try:
            resp = await client.post(
                f"{BASE_URL}/people/{seed_id}/vote",
                json={"value": 5},
                headers={"X-Device-ID": "diag-device-001"}
            )
            body = resp.json()
            if resp.status_code == 200:
                print(f"  ✅ B1 PASS: superlikes={body.get('superlikes')}")
                results["passed"] += 1
            else:
                print(f"  ❌ B1 FAIL: {resp.status_code} - {body}")
                results["failed"] += 1
                results["errors"].append(f"B1: {resp.status_code} - {body}")
        except Exception as e:
            print(f"  💥 B1 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B1: {e}")
        
        # ==================== TEST B2 ====================
        print("\n" + "="*60)
        print("TEST B2: boost_id in /boost-myself response")
        print("="*60)
        try:
            resp = await client.post(f"{BASE_URL}/boost-myself", json={
                "user_id": "diag-user-001",
                "name": "Test Outsider Diag",
                "tier": "booster",
                "receipt": "test-receipt-valid-0123456789",
                "platform": "ios",
                "email": "diag@test.com",
            })
            body = resp.json()
            if resp.status_code == 200 and "boost_id" in body:
                print(f"  ✅ B2 PASS: boost_id='{body['boost_id']}'")
                results["passed"] += 1
            else:
                print(f"  ❌ B2 FAIL: {resp.status_code}, keys={list(body.keys())}")
                results["failed"] += 1
                results["errors"].append(f"B2: boost_id missing")
        except Exception as e:
            print(f"  💥 B2 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B2: {e}")
        
        # ==================== TEST B5 ====================
        print("\n" + "="*60)
        print("TEST B5: Second boost replaces first")
        print("="*60)
        try:
            resp = await client.post(f"{BASE_URL}/boost-myself", json={
                "user_id": "diag-user-001",
                "name": "Test Outsider Diag",
                "tier": "super_booster",
                "receipt": "test-receipt-valid-9876543210",
                "platform": "ios",
                "email": "diag@test.com",
            })
            body = resp.json()
            if resp.status_code == 200:
                now_after = datetime.now(timezone.utc)
                active_after = await db.active_boosts.count_documents({
                    "person_id": outsider_result.inserted_id,
                    "end_time": {"$gt": now_after}
                })
                replaced_count = await db.active_boosts.count_documents({
                    "person_id": outsider_result.inserted_id,
                    "status": "replaced"
                })
                if active_after == 1 and replaced_count == 1:
                    print(f"  ✅ B5 PASS: 1 active, 1 replaced")
                    results["passed"] += 1
                else:
                    print(f"  ❌ B5 FAIL: active={active_after}, replaced={replaced_count}")
                    results["failed"] += 1
                    results["errors"].append(f"B5: active={active_after}, replaced={replaced_count}")
            else:
                print(f"  ❌ B5 FAIL: {resp.status_code} - {body}")
                results["failed"] += 1
                results["errors"].append(f"B5: {resp.status_code}")
        except Exception as e:
            print(f"  💥 B5 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B5: {e}")
    
    # ==================== TEST B4 ====================
    print("\n" + "="*60)
    print("TEST B4: math.ceil in seed_outsiders.py")
    print("="*60)
    try:
        with open("seed_outsiders.py", "r") as f:
            if "math.ceil" in f.read():
                print(f"  ✅ B4 PASS")
                results["passed"] += 1
            else:
                print(f"  ❌ B4 FAIL: math.ceil not found")
                results["failed"] += 1
    except Exception as e:
        print(f"  💥 B4 ERROR: {e}")
        results["failed"] += 1
    
    # ==================== CLEANUP ====================
    slugs = ["test-seed-person-diag", "test-outsider-diag"]
    await db.persons.delete_many({"slug": {"$in": slugs}})
    await db.active_boosts.delete_many({"user_id": "diag-user-001"})
    await db.superlike_votes.delete_many({"device_id": "diag-device-001"})
    await db.superlike_events.delete_many({"device_id": "diag-device-001"})
    await db.credit_transactions.delete_many({"user_id": "diag-user-001"})
    
    print("\n" + "="*60)
    print(f"RÉSULTAT: {results['passed']}/4 PASS | {results['failed']}/4 FAIL")
    print("="*60)
    if results["errors"]:
        for e in results["errors"]:
            print(f"  ⚠️  {e}")
    
    mongo_client.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
