import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv()

async def cleanup():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("DB_NAME", "test_database")]
    
    slugs = ["test-seed-person-diag", "test-outsider-diag"]
    r1 = await db.persons.delete_many({"slug": {"$in": slugs}})
    r2 = await db.active_boosts.delete_many({"user_id": "diag-user-001"})
    r3 = await db.superlike_votes.delete_many({"device_id": "diag-device-001"})
    r4 = await db.superlike_events.delete_many({"device_id": "diag-device-001"})
    r5 = await db.credit_transactions.delete_many({"user_id": "diag-user-001"})
    
    # Also clean from popularoo DB (first test mistake)
    db2 = client["popularoo"]
    await db2.persons.delete_many({"slug": {"$in": slugs}})
    await db2.active_boosts.delete_many({"user_id": "diag-user-001"})
    
    print(f"Cleaned: persons={r1.deleted_count}, boosts={r2.deleted_count}, sl_votes={r3.deleted_count}, sl_events={r4.deleted_count}, transactions={r5.deleted_count}")
    client.close()

asyncio.run(cleanup())
