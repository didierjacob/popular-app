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


async def run_index_recalc_job(db):
    """Wrapper to call the Popularoo Index recalculation job"""
    try:
        from popularoo_index import recalculate_all_indices
        await recalculate_all_indices(db)
    except Exception as e:
        logger.error(f"❌ Index recalculation job error: {e}")


async def run_daily_run_check_job(db):
    """Wrapper to call the Daily Run victory/expiration check job"""
    try:
        from daily_run_v2 import check_victories
        await check_victories(db, email_service=_email_service)
    except Exception as e:
        logger.error(f"❌ Daily Run check job error: {e}")


async def run_strike_cleanup_job(db):
    """Wrapper to call the strike cleanup job"""
    try:
        from strikes import cleanup_expired_strikes
        await cleanup_expired_strikes(db)
    except Exception as e:
        logger.error(f"❌ Strike cleanup job error: {e}")


async def run_deceased_check_job(db):
    """Daily wrapper: check top 50 via Wikidata P570 (structured death_date)"""
    try:
        from person_maintenance import check_deceased_top50
        await check_deceased_top50(db)
    except Exception as e:
        logger.error(f"❌ Deceased check (top50) job error: {e}")


async def run_deceased_check_all_job(db):
    """Weekly wrapper: check ALL remaining persons via Wikidata P570"""
    try:
        from person_maintenance import check_deceased_all
        await check_deceased_all(db)
    except Exception as e:
        logger.error(f"❌ Deceased check (all) job error: {e}")


async def run_tag_evolution_job(db):
    """Weekly wrapper: evolve country tags based on vote distribution"""
    try:
        from person_maintenance import evolve_country_tags
        await evolve_country_tags(db, min_votes=50)
    except Exception as e:
        logger.error(f"❌ Tag evolution job error: {e}")


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

    # Popularoo Index recalculation every 15 minutes
    # (full recalc with momentum, regularity, snapshots)
    scheduler.add_job(
        run_index_recalc_job,
        IntervalTrigger(minutes=15),
        args=[db],
        id='index_recalc_job',
        name='Popularoo Index Recalculation',
        replace_existing=True
    )

    # Daily Run victory/expiration check every 5 minutes
    scheduler.add_job(
        run_daily_run_check_job,
        IntervalTrigger(minutes=5),
        args=[db],
        id='daily_run_check_job',
        name='Daily Run Victory Check',
        replace_existing=True
    )

    # Strike cleanup every 15 minutes
    scheduler.add_job(
        run_strike_cleanup_job,
        IntervalTrigger(minutes=15),
        args=[db],
        id='strike_cleanup_job',
        name='Strike Cleanup',
        replace_existing=True
    )

    # Weekly deceased persons check — ALL remaining (Sunday 2:00 AM UTC)
    scheduler.add_job(
        run_deceased_check_all_job,
        CronTrigger(day_of_week='sun', hour=2, minute=0),
        args=[db],
        id='deceased_check_all_job',
        name='Weekly Deceased Check (All)',
        replace_existing=True
    )

    # Daily deceased check — Top 50 by Index (every day at 6:00 AM UTC)
    scheduler.add_job(
        run_deceased_check_job,
        CronTrigger(hour=6, minute=0),
        args=[db],
        id='deceased_check_top50_job',
        name='Daily Deceased Check (Top 50)',
        replace_existing=True
    )

    # Weekly country tag evolution (Sunday 4:00 AM UTC)
    scheduler.add_job(
        run_tag_evolution_job,
        CronTrigger(day_of_week='sun', hour=4, minute=0),
        args=[db],
        id='tag_evolution_job',
        name='Weekly Tag Evolution',
        replace_existing=True
    )
    
    logger.info("Scheduler initialized with daily tasks")
    logger.info("Next Google Trends refresh scheduled at 3:00 AM UTC")
    logger.info("Boost expiration checker runs every 15 minutes")
    logger.info("Bull Run job runs every 5 minutes")
    logger.info("Popularoo Index recalculation runs every 15 minutes")
    logger.info("Daily Run victory check runs every 5 minutes")
    logger.info("Strike cleanup runs every 15 minutes")
    logger.info("Daily deceased check (top 50) scheduled at 6:00 AM UTC")
    logger.info("Weekly deceased check (all) scheduled Sundays 2:00 AM UTC")
    logger.info("Weekly tag evolution scheduled Sundays 4:00 AM UTC")
    
    return scheduler


async def check_expiring_boosts(db):
    """Check for boosts expiring soon and send translated reminder emails"""
    try:
        from email_sender import send_booster_expiration
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
            user_id = boost.get("user_id", "")
            end_time = boost.get("end_time", now)
            remaining_hours = max(1, int((end_time - now).total_seconds() / 3600))

            if _email_service:
                try:
                    # Gather stats for the email
                    total_votes = await db.votes.count_documents({"person_id": boost.get("person_id")}) if boost.get("person_id") else 0
                    daily_runs_count = await db.daily_runs.count_documents({"outsider_id": boost.get("person_id"), "status": "completed"}) if boost.get("person_id") else 0

                    await send_booster_expiration(
                        db, _email_service, email, user_id, person_name,
                        "Golden Booster", f"{remaining_hours} hours",
                        total_votes=total_votes, best_rank=0, daily_runs_count=daily_runs_count
                    )
                    logger.info(f"📧 24h reminder (translated) sent to {email} for '{person_name}'")
                except Exception as email_err:
                    logger.warning(f"Failed to send 24h reminder: {email_err}")

            await db.active_boosts.update_one(
                {"_id": boost["_id"]},
                {"$set": {"reminder_24h_sent": True}}
            )

        # --- Reminder 2: 3h before expiry (Super Boosters) ---
        three_ahead = now + timedelta(hours=3)
        three_window_start = now + timedelta(hours=2)
        super_expiring = await db.active_boosts.find({
            "end_time": {"$lte": three_ahead, "$gt": three_window_start},
            "reminder_sent": {"$ne": True},
            "email": {"$ne": ""},
            "tier": "super_booster",
        }).to_list(100)

        for boost in super_expiring:
            email = boost.get("email", "")
            if not email:
                continue

            person_name = boost.get("person_name", "Unknown")
            user_id = boost.get("user_id", "")
            end_time = boost.get("end_time", now)
            remaining_hours = max(1, int((end_time - now).total_seconds() / 3600))

            if _email_service:
                try:
                    total_votes = await db.votes.count_documents({"person_id": boost.get("person_id")}) if boost.get("person_id") else 0
                    daily_runs_count = await db.daily_runs.count_documents({"outsider_id": boost.get("person_id"), "status": "completed"}) if boost.get("person_id") else 0

                    await send_booster_expiration(
                        db, _email_service, email, user_id, person_name,
                        "Super Booster", f"{remaining_hours} hours",
                        total_votes=total_votes, best_rank=0, daily_runs_count=daily_runs_count
                    )
                    logger.info(f"📧 3h reminder (translated) sent to {email} for '{person_name}'")
                except Exception as email_err:
                    logger.warning(f"Failed to send 3h reminder: {email_err}")

            # Mark as reminded
            await db.active_boosts.update_one(
                {"_id": boost["_id"]},
                {"$set": {"reminder_sent": True}}
            )

        total_sent = len(golden_expiring) + len(super_expiring)
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
