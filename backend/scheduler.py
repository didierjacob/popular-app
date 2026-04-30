"""
Automated Scheduler for Popularoo App
Handles daily tasks like Google Trends refresh and boost expiration reminders
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None
_email_service = None


async def run_bull_run_job(db):
    """Wrapper to call the Bull Run background job"""
    try:
        from bull_run import bull_run_background_job
        await bull_run_background_job(db)
    except Exception as e:
        logger.error(f"❌ Bull Run job wrapper error: {e}")


def init_scheduler(db, trends_service, email_svc=None):
    """
    Initialize the APScheduler with daily tasks
    
    Args:
        db: MongoDB database instance
        trends_service: GoogleTrendsService instance
        email_svc: EmailService instance (optional)
    """
    global scheduler, _email_service
    _email_service = email_svc
    
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

    # Check for expiring boosts every 15 minutes
    scheduler.add_job(
        check_expiring_boosts,
        IntervalTrigger(minutes=15),
        args=[db],
        id='check_expiring_boosts',
        name='Check Expiring Boosts',
        replace_existing=True
    )

    # Bull Run background job every 5 minutes
    # (win confirmation, Legend recalculation, new win detection)
    scheduler.add_job(
        run_bull_run_job,
        IntervalTrigger(minutes=5),
        args=[db],
        id='bull_run_background_job',
        name='Bull Run Win Check & Legend Recalculation',
        replace_existing=True
    )
    
    logger.info("Scheduler initialized with daily tasks")
    logger.info("Next Google Trends refresh scheduled at 3:00 AM UTC")
    logger.info("Boost expiration checker runs every 15 minutes")
    logger.info("Bull Run job runs every 5 minutes")
    
    return scheduler


async def check_expiring_boosts(db):
    """Check for boosts expiring soon and send reminder emails"""
    try:
        now = datetime.utcnow()

        # --- Reminder 1: 24h before expiry (Golden Boosters only) ---
        day_ahead = now + timedelta(hours=24)
        day_window_start = now + timedelta(hours=23)  # 23-24h window to avoid duplicates
        golden_expiring = await db.active_boosts.find({
            "end_time": {"$lte": day_ahead, "$gt": day_window_start},
            "reminder_24h_sent": {"$ne": True},
            "email": {"$ne": ""},
            "tier": "golden_booster",
        }).to_list(100)

        for boost in golden_expiring:
            email = boost.get("email", "")
            if not email:
                continue

            person_name = boost.get("person_name", "Unknown")
            end_time = boost.get("end_time", now)
            remaining_hours = max(0, int((end_time - now).total_seconds() / 3600))

            if _email_service:
                try:
                    html = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #0F2F22; color: #EAEAEA;">
                        <h1 style="color: #FFD700; text-align: center;">⏳ 24 Hours Left!</h1>
                        <div style="background: #1C3A2C; border-radius: 12px; padding: 24px; margin: 20px 0; border: 2px solid #FFD700;">
                            <h2 style="color: #EAEAEA; margin-top: 0;">Hello {person_name}!</h2>
                            <p style="color: #C9D8D2;">Your <strong style="color: #FFD700;">Golden Booster</strong> expires in approximately <strong style="color: #FFD700;">{remaining_hours} hours</strong>.</p>
                            <p style="color: #C9D8D2;">Don't lose your priority placement in Outsiders and Home page rotation!</p>
                            <div style="text-align: center; margin-top: 20px;">
                                <a href="https://popularoo.com" style="display: inline-block; background: #FFD700; color: #0F2F22; padding: 12px 30px; border-radius: 25px; text-decoration: none; font-weight: bold;">Renew Now</a>
                            </div>
                        </div>
                        <p style="color: #C9D8D2; text-align: center; font-size: 12px;">Popularoo App - Rate & rank personalities</p>
                    </div>
                    """
                    await _email_service.send_email(email, f"⏳ Your Golden Booster for '{person_name}' expires in 24h!", html)
                    logger.info(f"📧 24h reminder sent to {email} for '{person_name}'")
                except Exception as email_err:
                    logger.warning(f"Failed to send 24h reminder: {email_err}")

            await db.active_boosts.update_one(
                {"_id": boost["_id"]},
                {"$set": {"reminder_24h_sent": True}}
            )

        # --- Reminder 2: 1h before expiry (All tiers) ---
        soon = now + timedelta(hours=1)
        expiring = await db.active_boosts.find({
            "end_time": {"$lte": soon, "$gt": now},
            "reminder_sent": {"$ne": True},
            "email": {"$ne": ""},
        }).to_list(100)

        if not expiring and not golden_expiring:
            return

        for boost in expiring:
            email = boost.get("email", "")
            if not email:
                continue

            person_name = boost.get("person_name", "Unknown")
            end_time = boost.get("end_time", now)
            remaining_mins = max(0, int((end_time - now).total_seconds() / 60))

            # Send reminder email
            if _email_service:
                try:
                    html = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #0F2F22; color: #EAEAEA;">
                        <h1 style="color: #FFA500; text-align: center;">⏰ Your Boost is Expiring!</h1>
                        <div style="background: #1C3A2C; border-radius: 12px; padding: 24px; margin: 20px 0; border: 2px solid #FFA500;">
                            <h2 style="color: #EAEAEA; margin-top: 0;">Hello {person_name}!</h2>
                            <p style="color: #C9D8D2;">Your visibility boost expires in approximately <strong style="color: #FFA500;">{remaining_mins} minutes</strong>.</p>
                            <p style="color: #C9D8D2;">Want to stay visible? Open Popularoo and renew your booster!</p>
                            <div style="text-align: center; margin-top: 20px;">
                                <a href="https://popularoo.com" style="display: inline-block; background: #E04F5F; color: white; padding: 12px 30px; border-radius: 25px; text-decoration: none; font-weight: bold;">Renew Now</a>
                            </div>
                        </div>
                        <p style="color: #C9D8D2; text-align: center; font-size: 12px;">Popularoo App - Rate & rank personalities</p>
                    </div>
                    """
                    await _email_service.send_email(email, f"⏰ Your boost for '{person_name}' expires soon!", html)
                    logger.info(f"📧 Expiration reminder sent to {email} for '{person_name}'")
                except Exception as email_err:
                    logger.warning(f"Failed to send expiration reminder: {email_err}")

            # Mark as reminded
            await db.active_boosts.update_one(
                {"_id": boost["_id"]},
                {"$set": {"reminder_sent": True}}
            )

        total_sent = len(golden_expiring) + len(expiring)
        if total_sent > 0:
            logger.info(f"⏰ Checked expiring boosts: {total_sent} reminders sent")

    except Exception as e:
        logger.error(f"❌ Error checking expiring boosts: {e}")


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
