"""
Popularoo Email Sender — Bridges email_templates.py with email_service.py
Handles language detection, template rendering, and sending.
"""
import logging
from datetime import datetime
from typing import Optional
from email_templates import (
    EMAIL_BOOSTER_CONFIRMATION,
    EMAIL_DAILY_RUN_VICTORY,
    EMAIL_STRIKE_GOING_VIRAL,
    EMAIL_STRIKE_LEGEND_MODE,
    EMAIL_BOOSTER_EXPIRATION,
    EMAIL_WELCOME,
    SOCIAL_ACCOUNTS_FEATURE_ENABLED,
    get_template,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Duration Localization — translates English duration strings
# to the user's language for {{duration}} and {{timeRemaining}}
# ──────────────────────────────────────────────────────────
DURATION_TRANSLATIONS = {
    "en": {"hour": "hour", "hours": "hours", "day": "day", "days": "days", "week": "week", "weeks": "weeks", "minute": "minute", "minutes": "minutes"},
    "fr": {"hour": "heure", "hours": "heures", "day": "jour", "days": "jours", "week": "semaine", "weeks": "semaines", "minute": "minute", "minutes": "minutes"},
    "es": {"hour": "hora", "hours": "horas", "day": "día", "days": "días", "week": "semana", "weeks": "semanas", "minute": "minuto", "minutes": "minutos"},
    "pt": {"hour": "hora", "hours": "horas", "day": "dia", "days": "dias", "week": "semana", "weeks": "semanas", "minute": "minuto", "minutes": "minutos"},
    "de": {"hour": "Stunde", "hours": "Stunden", "day": "Tag", "days": "Tage", "week": "Woche", "weeks": "Wochen", "minute": "Minute", "minutes": "Minuten"},
    "it": {"hour": "ora", "hours": "ore", "day": "giorno", "days": "giorni", "week": "settimana", "weeks": "settimane", "minute": "minuto", "minutes": "minuti"},
}


def localize_duration(duration_str: str, lang: str) -> str:
    """Translate an English duration string like '3 hours' or '1 week' to the target language."""
    if lang == "en" or lang not in DURATION_TRANSLATIONS:
        return duration_str

    tr = DURATION_TRANSLATIONS[lang]
    result = duration_str
    # Replace longest keys first to avoid partial matches (e.g. "hours" before "hour")
    for en_key in sorted(tr.keys(), key=len, reverse=True):
        if en_key in result:
            result = result.replace(en_key, tr[en_key])
    return result


def _text_to_html(text: str) -> str:
    """Convert plain text email to styled HTML."""
    # Escape HTML chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold markers
    text = text.replace("**", "<b>", 1)
    while "**" in text:
        text = text.replace("**", "</b>", 1)
        if "**" in text:
            text = text.replace("**", "<b>", 1)
    # Bullet points
    lines = text.split("\n")
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("• "):
            html_lines.append(f'<div style="padding-left:16px;margin:4px 0;">• {stripped[2:]}</div>')
        elif stripped.startswith("[") and stripped.endswith("]"):
            # CTA button
            btn_text = stripped[1:-1]
            html_lines.append(
                f'<div style="text-align:center;margin:20px 0;">'
                f'<a href="https://popularoo.com" style="background:#E04F5F;color:white;'
                f'padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">'
                f'{btn_text}</a></div>'
            )
        elif stripped == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p style='margin:4px 0;'>{stripped}</p>")

    body_html = "\n".join(html_lines)

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 560px; margin: 0 auto; padding: 32px 24px;
                background: #0F2F22; color: #EAEAEA; border-radius: 12px;">
        <div style="text-align:center;margin-bottom:24px;">
            <span style="font-size:28px;font-weight:800;color:#2ECC71;">Popularoo</span>
        </div>
        <div style="line-height:1.6;font-size:15px;">
            {body_html}
        </div>
        <div style="margin-top:32px;padding-top:16px;border-top:1px solid #2E6148;
                    text-align:center;font-size:12px;color:#C9D8D2;">
            © {datetime.utcnow().year} Popularoo App
        </div>
    </div>
    """


async def _get_user_language(db, user_id: str) -> str:
    """Get user's preferred language from settings, default to 'en'."""
    try:
        settings = await db.user_settings.find_one({"device_id": user_id})
        if settings and settings.get("language"):
            return settings["language"]
    except Exception as e:
        logger.warning(f"Could not fetch user language: {e}")
    return "en"


async def send_booster_confirmation(db, email_service, email: str, user_id: str,
                                     name: str, tier_name: str, duration: str,
                                     is_golden: bool = False):
    """Email 1: Booster purchase confirmation (non-first purchases)."""
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_BOOSTER_CONFIRMATION, lang)

    # Localize the duration string (e.g. "24 hours" → "24 heures" in FR)
    localized_duration = localize_duration(duration, lang)

    golden_extra = tpl.get("goldenExtra", "") if is_golden else ""
    body = tpl["body"]
    body = body.replace("{{name}}", name)
    body = body.replace("{{tierName}}", tier_name)
    body = body.replace("{{duration}}", localized_duration)
    body = body.replace("{{goldenExtra}}", golden_extra)

    subject = tpl["subject"].replace("{{tierName}}", tier_name)
    html = _text_to_html(body)

    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 1] Booster confirmation sent to {email} ({lang})")


async def send_welcome(db, email_service, email: str, user_id: str, name: str):
    """Email 5: Welcome email (first purchase only)."""
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_WELCOME, lang)

    social_tip = tpl.get("socialTipEnabled", "") if SOCIAL_ACCOUNTS_FEATURE_ENABLED else tpl.get("socialTipDefault", "")
    body = tpl["body"]
    body = body.replace("{{name}}", name)
    body = body.replace("{{socialTip}}", social_tip)

    subject = tpl["subject"]
    html = _text_to_html(body)

    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 5] Welcome sent to {email} ({lang})")


async def send_daily_run_victory(db, email_service, email: str, user_id: str,
                                  name: str, target_name: str, gap: int,
                                  victory_tier: str, votes_received: int,
                                  strikes_count: int = 0, highest_strike: str = ""):
    """Email 2: Daily Run victory (3 subject variants)."""
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_DAILY_RUN_VICTORY, lang)

    # Determine subject tier key
    if "Legendary" in victory_tier:
        tier_key = "legendary"
    elif "Underdog" in victory_tier:
        tier_key = "underdog"
    else:
        tier_key = "standard"

    subject = tpl["subjects"][tier_key]

    # Build strikes line (only if > 0)
    strikes_line = ""
    if strikes_count > 0:
        strikes_line = tpl["strikesLine"]
        strikes_line = strikes_line.replace("{{strikesCount}}", str(strikes_count))
        strikes_line = strikes_line.replace("{{highestStrike}}", highest_strike)

    # Build tier-specific message
    if tier_key == "legendary":
        tier_message = tpl["legendaryMsg"].replace("{{gap}}", str(gap))
    elif tier_key == "underdog":
        tier_message = tpl["underdogMsg"].replace("{{gap}}", str(gap))
    else:
        tier_message = tpl["standardMsg"]

    body = tpl["body"]
    body = body.replace("{{name}}", name)
    body = body.replace("{{targetName}}", target_name)
    body = body.replace("{{gap}}", str(gap))
    body = body.replace("{{victoryTier}}", victory_tier)
    body = body.replace("{{votesReceived}}", str(votes_received))
    body = body.replace("{{strikesLine}}", strikes_line)
    body = body.replace("{{tierMessage}}", tier_message)

    html = _text_to_html(body)
    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 2] Daily Run {tier_key} victory sent to {email} ({lang})")


async def send_strike_going_viral(db, email_service, email: str, user_id: str, name: str):
    """Email 3a: Strike Going Viral (4 simultaneous strikes)."""
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_STRIKE_GOING_VIRAL, lang)

    body = tpl["body"].replace("{{name}}", name)
    subject = tpl["subject"]
    html = _text_to_html(body)

    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 3a] Going Viral sent to {email} ({lang})")


async def send_strike_legend_mode(db, email_service, email: str, user_id: str, name: str):
    """Email 3b: Strike Legend Mode (5+ simultaneous strikes)."""
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_STRIKE_LEGEND_MODE, lang)

    body = tpl["body"].replace("{{name}}", name)
    subject = tpl["subject"]
    html = _text_to_html(body)

    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 3b] Legend Mode sent to {email} ({lang})")


async def send_booster_expiration(db, email_service, email: str, user_id: str,
                                   name: str, tier_name: str, time_remaining: str,
                                   total_votes: int = 0, best_rank: int = 0,
                                   daily_runs_count: int = 0):
    """Email 4: Booster expiration warning.
    Timing: Super Booster → 3h before | Golden Booster → 24h before | Basic → no email
    """
    lang = await _get_user_language(db, user_id)
    tpl = get_template(EMAIL_BOOSTER_EXPIRATION, lang)

    # Localize the time remaining string (e.g. "3 hours" → "3 heures" in FR)
    localized_time = localize_duration(time_remaining, lang)

    daily_runs_line = ""
    if daily_runs_count > 0:
        daily_runs_line = tpl.get("dailyRunsLine", "")
        daily_runs_line = daily_runs_line.replace("{{dailyRunsCount}}", str(daily_runs_count))

    body = tpl["body"]
    body = body.replace("{{name}}", name)
    body = body.replace("{{tierName}}", tier_name)
    body = body.replace("{{timeRemaining}}", localized_time)
    body = body.replace("{{totalVotes}}", str(total_votes))
    body = body.replace("{{bestRank}}", str(best_rank))
    body = body.replace("{{dailyRunsLine}}", daily_runs_line)

    subject = tpl["subject"].replace("{{tierName}}", tier_name)
    html = _text_to_html(body)

    await email_service.send_email(email, subject, html)
    logger.info(f"[Email 4] Booster expiration sent to {email} ({lang})")
