"""
Automated Scheduler for Popularoo App
Handles daily tasks like Google Trends refresh and boost expiration reminders
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import asyncio
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


# ── Session 2: Daily External Scores Job ───────────────────────────────────

async def run_daily_external_scores_job(db):
    """
    Daily job (03:00 UTC): Fetch Wikipedia pageviews for all non-outsider celebrities
    and compute normalized external scores. Saves to each person document.

    Two-pass approach:
      Pass 1: Fetch wiki_score_brut for all persons → find global max
      Pass 2: Normalize and save popularity_external_score
    """
    import asyncio
    import time as _time
    from datetime import datetime, timezone
    from external_scores import fetch_wikipedia_pageviews, normalize_wiki_score, compute_external_score

    start_time = _time.time()
    now = datetime.now(timezone.utc)
    logger.info(f"🌐 [External Scores] Job started at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Fetch all non-outsider persons
    all_persons = await db.persons.find(
        {"source": {"$ne": "self_boosted"}, "category": {"$ne": "outsider"}}
    ).to_list(length=5000)

    total = len(all_persons)
    logger.info(f"🌐 [External Scores] Processing {total} celebrities")

    # ── Pass 1: Collect wiki_score_brut for all ──
    wiki_brut_map = {}  # person_id -> {name, wiki_brut, wiki_result}
    errors = []
    success_count = 0

    for idx, doc in enumerate(all_persons):
        name = doc.get("name", "")
        person_id = doc["_id"]

        try:
            wiki_result = await fetch_wikipedia_pageviews(name)
            wiki_brut = wiki_result["wiki_score_brut"]
            wiki_brut_map[person_id] = {
                "name": name,
                "wiki_brut": wiki_brut,
                "wiki_errors": wiki_result.get("errors", []),
            }
            success_count += 1
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
            logger.warning(f"🌐 [External Scores] FAIL: {name} — {e}")

        # Rate limiting: 200ms between persons (each person = 6 lang requests with internal delays)
        if idx < total - 1:
            await asyncio.sleep(0.2)

        # Progress log every 50 persons
        if (idx + 1) % 50 == 0:
            elapsed = round(_time.time() - start_time, 1)
            logger.info(f"🌐 [External Scores] Progress: {idx + 1}/{total} ({elapsed}s elapsed)")

    # ── Find global max ──
    all_bruts = [v["wiki_brut"] for v in wiki_brut_map.values() if v["wiki_brut"] > 0]
    max_wiki = max(all_bruts) if all_bruts else 1.0
    logger.info(f"🌐 [External Scores] Max wiki_brut = {max_wiki:,.1f}")

    # ── Compute category medians for fallback (Decision 5) ──
    category_scores = {}
    for person_id, data in wiki_brut_map.items():
        doc = next((d for d in all_persons if d["_id"] == person_id), None)
        if doc and data["wiki_brut"] > 0:
            cat = doc.get("category", "other")
            if cat not in category_scores:
                category_scores[cat] = []
            norm = normalize_wiki_score(data["wiki_brut"], max_wiki)
            category_scores[cat].append(norm)

    category_medians = {}
    for cat, scores in category_scores.items():
        sorted_scores = sorted(scores)
        mid = len(sorted_scores) // 2
        if len(sorted_scores) % 2 == 0 and len(sorted_scores) > 1:
            category_medians[cat] = round((sorted_scores[mid - 1] + sorted_scores[mid]) / 2, 1)
        elif sorted_scores:
            category_medians[cat] = sorted_scores[mid]
        else:
            category_medians[cat] = 50.0

    # ── Pass 2: Normalize and save ──
    update_count = 0
    for person_id, data in wiki_brut_map.items():
        doc = next((d for d in all_persons if d["_id"] == person_id), None)
        if not doc:
            continue

        wiki_brut = data["wiki_brut"]
        cat = doc.get("category", "other")

        if wiki_brut > 0:
            wiki_norm = normalize_wiki_score(wiki_brut, max_wiki)
            external_score = compute_external_score(wiki_norm, 0.0)
        else:
            # Fallback: use category median (Decision 5)
            external_score = category_medians.get(cat, 50.0)
            wiki_norm = external_score

        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {
                "popularity_external_score": external_score,
                "wiki_score_norm": wiki_norm,
                "wiki_score_brut": wiki_brut,
                "last_external_update": now,
            }}
        )
        update_count += 1

    # ── Summary ──
    elapsed_total = round(_time.time() - start_time, 1)
    end_time = datetime.now(timezone.utc)

    summary = {
        "job": "daily_external_scores",
        "start_time": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration_seconds": elapsed_total,
        "total_persons": total,
        "success_count": success_count,
        "error_count": len(errors),
        "updated_count": update_count,
        "max_wiki_brut": max_wiki,
        "errors": errors[:20],  # First 20 errors max
        "category_medians": category_medians,
    }

    logger.info(f"🌐 [External Scores] Job completed in {elapsed_total}s — "
                f"{success_count}/{total} success, {len(errors)} errors, "
                f"{update_count} updated")

    # Store last run summary in app_settings
    await db.app_settings.update_one(
        {"_id": "global"},
        {"$set": {"last_external_scores_run": summary}},
        upsert=True
    )

    return summary


async def run_daily_candidate_detection_job(db):
    """
    Session 3: Wrapper for the daily candidate detection job.
    Called by APScheduler at 05:00 UTC daily.
    """
    try:
        from candidate_detection import detect_candidates
        logger.info("🔍 [Scheduler] Starting daily candidate detection...")
        summary = await detect_candidates(db)
        logger.info(
            f"🔍 [Scheduler] Candidate detection complete: "
            f"{summary.get('eligible_candidates', 0)} eligible, "
            f"{summary.get('inserted_to_queue', 0)} inserted"
        )
    except Exception as e:
        logger.error(f"❌ [Scheduler] Candidate detection failed: {e}")


async def run_monthly_category_review_job(db):
    """
    Session 3 Lot 2: Monthly category re-inference for all personalities.
    Compares current categories with Wikipedia-inferred categories.
    Called by APScheduler on 1st of each month at 04:00 UTC.
    """
    try:
        import httpx as _httpx
        from candidate_detection import infer_category
        from datetime import datetime, timezone

        logger.info("📂 [Scheduler] Starting monthly category review...")
        now = datetime.now(timezone.utc)
        reviewed = 0
        divergences = 0

        persons = await db.persons.find({
            "approved": True,
            "source": {"$ne": "self_boosted"},
            "category": {"$ne": "outsider"},
        }).to_list(5000)

        async with _httpx.AsyncClient(timeout=10) as client:
            for person in persons:
                name = person.get("name", "")
                current_cat = person.get("category", "other")
                title = name.replace(" ", "_")
                description = ""
                try:
                    resp = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                        headers={"User-Agent": "Popularoo/1.0"},
                        follow_redirects=True,
                    )
                    if resp.status_code == 200:
                        description = resp.json().get("description", "")
                    await asyncio.sleep(0.1)
                except Exception:
                    pass

                if not description:
                    reviewed += 1
                    continue

                suggested_cat, confidence = infer_category(description)
                if suggested_cat != current_cat and suggested_cat != "other":
                    existing = await db.category_reviews.find_one({
                        "person_id": person["_id"],
                        "status": "pending",
                    })
                    if not existing:
                        await db.category_reviews.insert_one({
                            "person_id": person["_id"],
                            "name": name,
                            "current_category": current_cat,
                            "suggested_category": suggested_cat,
                            "confidence": confidence,
                            "wiki_description": description,
                            "created_at": now,
                            "status": "pending",
                        })
                        divergences += 1
                reviewed += 1

        await db.app_settings.update_one(
            {"_id": "global"},
            {"$set": {"last_category_review_run": {
                "timestamp": now.isoformat(),
                "reviewed": reviewed,
                "divergences": divergences,
            }}},
            upsert=True,
        )

        logger.info(f"📂 [Scheduler] Category review complete: {reviewed} reviewed, {divergences} divergences")
    except Exception as e:
        logger.error(f"❌ [Scheduler] Category review failed: {e}")


async def run_auto_promote_user_created(db):
    """
    Session 3: Auto-promote user-created profiles after 48h.
    Runs every 6 hours. Only promotes if not in blocklist and not deleted.
    """
    try:
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        cutoff_48h = now - timedelta(hours=48)

        # Find all user_search profiles older than 48h still invisible
        candidates = await db.persons.find({
            "source": "user_search",
            "visible_in_rankings": False,
            "created_at": {"$lt": cutoff_48h},
            "approved": True,
        }).to_list(500)

        if not candidates:
            return

        # Load blocklist
        settings = await db.app_settings.find_one({"_id": "global"}) or {}
        blocked_slugs = set(settings.get("seed_blocklist", []))

        promoted = 0
        blocked = 0

        for person in candidates:
            slug = person.get("slug", "")
            if slug in blocked_slugs:
                # Blocked — silently delete the profile
                await db.persons.delete_one({"_id": person["_id"]})
                blocked += 1
                logger.info(f"🚫 [AutoPromote] Deleted blocked profile: {person.get('name')}")
                continue

            # Promote
            await db.persons.update_one(
                {"_id": person["_id"]},
                {"$set": {"visible_in_rankings": True, "promoted_at": now}}
            )
            promoted += 1

        if promoted > 0 or blocked > 0:
            logger.info(f"🔄 [AutoPromote] {promoted} promoted, {blocked} blocked/deleted")
    except Exception as e:
        logger.error(f"❌ [AutoPromote] Failed: {e}")


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
    
    # ⚠️ DISABLED Session 2 — Audit revealed this job never worked on Render
    # (pytrends blocked by Google on cloud IPs) and has no admin validation,
    # no category inference, no anti-junk filters from Session 1.
    # Will be rewritten properly in Session 3 with admin approval workflow.
    # See: Session 2 Phase 1 audit — "Désactivation immédiate du job Trends existant"
    #
    # scheduler.add_job(
    #     refresh_google_trends,
    #     CronTrigger(hour=3, minute=0),
    #     args=[db, trends_service],
    #     id='daily_trends_refresh',
    #     name='Daily Google Trends Refresh',
    #     replace_existing=True
    # )

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

    # ── Session 2: Daily External Scores at 03:00 UTC ──
    # Fetches Wikipedia pageviews for all non-outsider celebrities,
    # normalizes scores (log scale), and saves popularity_external_score.
    # Replaces the disabled Google Trends auto-ingestion job on the 03:00 slot.
    scheduler.add_job(
        run_daily_external_scores_job,
        CronTrigger(hour=3, minute=0),
        args=[db],
        id='daily_external_scores_job',
        name='Daily External Scores (Wikipedia)',
        replace_existing=True
    )

    # ── Session 3: Daily Candidate Detection at 05:00 UTC ──
    # Scans WikiMedia Most Viewed across 6 languages, filters eligible humans,
    # writes to candidate_queue for admin review.
    scheduler.add_job(
        run_daily_candidate_detection_job,
        CronTrigger(hour=5, minute=0),
        args=[db],
        id='daily_candidate_detection_job',
        name='Daily Candidate Detection (Wikipedia)',
        replace_existing=True
    )

    # ── Session 3 Lot 2: Monthly Category Review on 1st of month at 04:00 UTC ──
    # Re-infers categories via Wikipedia for all personalities,
    # writes divergences to category_reviews for admin review.
    scheduler.add_job(
        run_monthly_category_review_job,
        CronTrigger(day=1, hour=4, minute=0),
        args=[db],
        id='monthly_category_review_job',
        name='Monthly Category Review (Wikipedia)',
        replace_existing=True
    )

    # ── Session 3: Auto-promote user-created profiles every 6 hours ──
    # Profiles created via /api/search with visible_in_rankings=false
    # are promoted to visible after 48h, unless blocked.
    scheduler.add_job(
        run_auto_promote_user_created,
        IntervalTrigger(hours=6),
        args=[db],
        id='auto_promote_user_created_job',
        name='Auto-Promote User Search Profiles (6h)',
        replace_existing=True
    )
    
    logger.info("Scheduler initialized with daily tasks")
    # Note: Daily Google Trends auto-ingestion DISABLED (Session 2 audit)
    logger.info("Boost expiration checker runs every 15 minutes")
    logger.info("Bull Run job runs every 5 minutes")
    logger.info("Popularoo Index recalculation runs every 15 minutes")
    logger.info("Daily Run victory check runs every 5 minutes")
    logger.info("Strike cleanup runs every 15 minutes")
    logger.info("Daily deceased check (top 50) scheduled at 6:00 AM UTC")
    logger.info("Weekly deceased check (all) scheduled Sundays 2:00 AM UTC")
    logger.info("Weekly tag evolution scheduled Sundays 4:00 AM UTC")
    logger.info("Daily external scores (Wikipedia) scheduled at 3:00 AM UTC")
    logger.info("Daily candidate detection (Wikipedia) scheduled at 5:00 AM UTC")
    logger.info("Monthly category review (Wikipedia) scheduled on 1st of month at 4:00 AM UTC")
    
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
