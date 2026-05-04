"""
Diagnostic test for bugs B1, B2, B4, B5
Tests the current state of the code WITHOUT modifying anything.
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
    # Create a test seed person
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
    
    # Create a test outsider for boost tests
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
        # ==================== TEST B1: Superlike on seed ====================
        print("\n" + "="*60)
        print("TEST B1: Superlike on seed outsider")
        print("="*60)
        
        try:
            resp = await client.post(
                f"{BASE_URL}/people/{seed_id}/vote",
                json={"value": 5},
                headers={"X-Device-ID": "diag-device-001"}
            )
            print(f"  Status: {resp.status_code}")
            body = resp.json()
            
            if resp.status_code == 200:
                print(f"  ✅ B1 PASS: Superlike accepted on seed")
                print(f"     superlikes={body.get('superlikes')}, total_votes={body.get('total_votes')}")
                results["passed"] += 1
            else:
                print(f"  ❌ B1 FAIL: {body}")
                results["failed"] += 1
                results["errors"].append(f"B1: {resp.status_code} - {body}")
        except Exception as e:
            print(f"  💥 B1 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B1: Exception - {e}")
        
        # ==================== TEST B2: boost_id in response ====================
        print("\n" + "="*60)
        print("TEST B2: boost_id present in /boost-myself response")
        print("="*60)
        
        try:
            boost_payload = {
                "user_id": "diag-user-001",
                "name": "Test Outsider Diag",
                "tier": "booster",
                "receipt": "test-receipt-valid-0123456789",
                "platform": "ios",
                "email": "diag@test.com",
            }
            resp = await client.post(f"{BASE_URL}/boost-myself", json=boost_payload)
            print(f"  Status: {resp.status_code}")
            body = resp.json()
            
            if resp.status_code == 200 and "boost_id" in body:
                print(f"  ✅ B2 PASS: boost_id='{body['boost_id']}' present in response")
                results["passed"] += 1
            elif resp.status_code == 200:
                print(f"  ❌ B2 FAIL: Response 200 but 'boost_id' missing. Keys: {list(body.keys())}")
                results["failed"] += 1
                results["errors"].append(f"B2: boost_id missing from response")
            else:
                print(f"  ❌ B2 FAIL: {resp.status_code} - {body}")
                results["failed"] += 1
                results["errors"].append(f"B2: {resp.status_code} - {body}")
        except Exception as e:
            print(f"  💥 B2 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B2: Exception - {e}")
        
        # ==================== TEST B5: Single active booster replacement ====================
        print("\n" + "="*60)
        print("TEST B5: Second boost replaces first (only 1 active)")
        print("="*60)
        
        try:
            # Check current active boosts
            now_check = datetime.now(timezone.utc)
            active_before = await db.active_boosts.count_documents({
                "person_id": outsider_result.inserted_id,
                "end_time": {"$gt": now_check}
            })
            print(f"  Active boosts before 2nd purchase: {active_before}")
            
            # Second purchase (should replace the first)
            boost_payload2 = {
                "user_id": "diag-user-001",
                "name": "Test Outsider Diag",
                "tier": "super_booster",
                "receipt": "test-receipt-valid-9876543210",
                "platform": "ios",
                "email": "diag@test.com",
            }
            resp = await client.post(f"{BASE_URL}/boost-myself", json=boost_payload2)
            print(f"  2nd boost status: {resp.status_code}")
            body = resp.json()
            
            if resp.status_code != 200:
                print(f"  ❌ B5 FAIL: 2nd purchase failed: {body}")
                results["failed"] += 1
                results["errors"].append(f"B5: 2nd purchase failed - {body}")
            else:
                print(f"  2nd boost response: success={body.get('success')}, boost_id={body.get('boost_id')}")
                
                # Count active boosts now
                now_after = datetime.now(timezone.utc)
                active_after = await db.active_boosts.count_documents({
                    "person_id": outsider_result.inserted_id,
                    "end_time": {"$gt": now_after}
                })
                total_docs = await db.active_boosts.count_documents({
                    "person_id": outsider_result.inserted_id
                })
                
                # Check replaced status
                replaced_count = await db.active_boosts.count_documents({
                    "person_id": outsider_result.inserted_id,
                    "status": "replaced"
                })
                
                print(f"  Active boosts after 2nd purchase: {active_after} (expected: 1)")
                print(f"  Total boost documents: {total_docs} (expected: 2)")
                print(f"  Replaced boosts: {replaced_count} (expected: 1)")
                
                if active_after == 1 and replaced_count == 1:
                    print(f"  ✅ B5 PASS: Exactly 1 active boost, 1 replaced")
                    results["passed"] += 1
                else:
                    print(f"  ❌ B5 FAIL: active={active_after}, replaced={replaced_count}")
                    results["failed"] += 1
                    results["errors"].append(f"B5: active={active_after}, replaced={replaced_count}")
        except Exception as e:
            print(f"  💥 B5 ERROR: {e}")
            results["failed"] += 1
            results["errors"].append(f"B5: Exception - {e}")
    
    # ==================== TEST B4: math.ceil in seed_outsiders.py ====================
    print("\n" + "="*60)
    print("TEST B4: math.ceil used in seed deactivation threshold")
    print("="*60)
    
    try:
        with open("seed_outsiders.py", "r") as f:
            content = f.read()
        
        if "math.ceil" in content:
            print(f"  ✅ B4 PASS: math.ceil found in seed_outsiders.py")
            results["passed"] += 1
        else:
            print(f"  ❌ B4 FAIL: math.ceil NOT found in seed_outsiders.py")
            results["failed"] += 1
            results["errors"].append("B4: math.ceil not found")
    except Exception as e:
        print(f"  💥 B4 ERROR: {e}")
        results["failed"] += 1
        results["errors"].append(f"B4: Exception - {e}")
    
    # ==================== CLEANUP ====================
    print("\n" + "="*60)
    print("CLEANUP")
    print("="*60)
    
    await db.persons.delete_many({"slug": {"$in": ["test-seed-person-diag", "test-outsider-diag"]}})
    await db.active_boosts.delete_many({"user_id": "diag-user-001"})
    await db.superlike_votes.delete_many({"device_id": "diag-device-001"})
    await db.superlike_events.delete_many({"device_id": "diag-device-001"})
    await db.credit_transactions.delete_many({"user_id": "diag-user-001"})
    print("  ✅ All test data cleaned up")
    
    # ==================== SUMMARY ====================
    print("\n" + "="*60)
    print(f"RÉSUMÉ: {results['passed']} PASS / {results['failed']} FAIL")
    print("="*60)
    if results["errors"]:
        print("Erreurs détaillées:")
        for e in results["errors"]:
            print(f"  - {e}")
    
    mongo_client.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
