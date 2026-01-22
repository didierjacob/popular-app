"""
Automated Scheduler for Popular App
Handles daily tasks like Google Trends refresh
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def init_scheduler(db, trends_service):
    """
    Initialize the APScheduler with daily tasks
    
    Args:
        db: MongoDB database instance
        trends_service: GoogleTrendsService instance
    """
    global scheduler
    
    scheduler = AsyncIOScheduler()
    
    # Daily Google Trends refresh at 3:00 AM UTC
    scheduler.add_job(
        refresh_google_trends,
        CronTrigger(hour=3, minute=0),  # 3:00 AM UTC every day
        args=[db, trends_service],
        id='daily_trends_refresh',
        name='Daily Google Trends Refresh',
        replace_existing=True
    )
    
    logger.info("Scheduler initialized with daily tasks")
    logger.info("Next Google Trends refresh scheduled at 3:00 AM UTC")
    
    return scheduler


async def refresh_google_trends(db, trends_service):
    """
    Automated task: Refresh Google Trends
    Runs daily at 3:00 AM UTC
    """
    try:
        logger.info("🔥 Starting automated Google Trends refresh...")
        
        # Fetch trending personalities
        trending_names = trends_service.get_trending_personalities(limit=20)
        
        if not trending_names:
            logger.warning("No trending personalities found")
            return
        
        added_count = 0
        updated_count = 0
        now = datetime.utcnow()
        
        # Unmark all existing trending personalities
        await db.persons.update_many(
            {"is_trending": True},
            {"$set": {"is_trending": False}}
        )
        logger.info("Unmarked all previous trending personalities")
        
        for name in trending_names:
            # Slugify name
            slug = name.strip().lower()
            slug = ''.join(c for c in slug if c.isalnum() or c == ' ')
            slug = slug.replace(' ', '-')
            
            # Check if person exists
            existing = await db.persons.find_one({"slug": slug})
            
            if existing:
                # Mark as trending
                await db.persons.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "is_trending": True,
                            "trending_since": now,
                            "updated_at": now,
                        }
                    }
                )
                updated_count += 1
                logger.info(f"✅ Marked as trending: {name}")
            else:
                # Auto-add new trending personality
                person_doc = {
                    "name": name,
                    "slug": slug,
                    "category": "other",
                    "approved": True,
                    "created_at": now,
                    "updated_at": now,
                    "score": 50.0,
                    "likes": 0,
                    "dislikes": 0,
                    "total_votes": 0,
                    "source": "trending",
                    "is_trending": True,
                    "trending_since": now,
                }
                
                from bson import ObjectId
                result = await db.persons.insert_one(person_doc)
                
                # Add initial tick
                await db.person_ticks.insert_one({
                    "person_id": result.inserted_id,
                    "score": 50.0,
                    "created_at": now
                })
                
                added_count += 1
                logger.info(f"➕ Auto-added trending: {name}")
        
        # Update last refresh timestamp
        await db.app_settings.update_one(
            {"_id": "global"},
            {"$set": {"last_trends_refresh": now}},
            upsert=True
        )
        
        logger.info(f"🎉 Automated trends refresh complete: {added_count} added, {updated_count} updated")
        
    except Exception as e:
        logger.error(f"❌ Error in automated trends refresh: {e}")


def start_scheduler():
    """Start the scheduler"""
    global scheduler
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started successfully")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
