"""
Popularoo Index — Proprietary scoring algorithm (0-100)
Confidential: coefficients and formula are never exposed publicly.

Components:
  - score_volume (20%): logarithmic scale of weighted votes
  - ratio_approbation (40%): approval ratio favoring positive engagement
  - momentum_24h (25%): delta of base_index over last 24h
  - regularity (15%): consistency of voting over 7 days
  + strikes_bonus: +5 per active strike (outsiders only)

Circularity resolution:
  base_index = volume*w_v + ratio*w_r + regularity*w_reg + strikes_bonus
  momentum = (base_index_now - base_index_24h_ago) * 5
  final_index = min(100, base_index + momentum * w_m)
"""

import math
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger("popularoo_index")

# ---- In-memory config cache ----
_config_cache: Optional[Dict[str, Any]] = None
_config_last_loaded: Optional[datetime] = None
CONFIG_CACHE_TTL_SECONDS = 300  # 5 minutes

# ---- Alpha : VERROUILLÉ à 1.0 (cœur honnête) — plus de cache DB, cf. get_alpha ci-dessous ----

# ---- Erosion cache (chantier « cœur honnête ») ----
_erosion_cache: Optional[Tuple[float, float]] = None
_erosion_last_loaded: Optional[datetime] = None
EROSION_CACHE_TTL_SECONDS = 60  # réglable sans redeploy via app_settings

# Défauts d'érosion par inactivité (nouveaux entrants, branche 2)
EROSION_GRACE_DAYS_DEFAULT = 14.0     # jours sans vrai vote avant érosion
EROSION_PER_WEEK_DEFAULT = 0.5        # points de PI perdus par semaine d'inactivité


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to naive UTC so it can be subtracted from _utcnow().
    Documents may store tz-aware datetimes (candidate_detection uses
    datetime.now(timezone.utc)) while _utcnow() is naive — mixing them raises.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ==================== CONFIG ====================

DEFAULT_CONFIG = {
    "_id": "popularoo_index",
    "coefficients": {
        "volume": 0.20,
        "ratio": 0.40,
        "momentum": 0.25,
        "regularity": 0.15,
    },
    "strike_value": 5,  # points per active strike
    "low_vote_cap": 30,  # max index if total_engagement < low_vote_threshold
    "low_vote_threshold": 10,  # total engagement below which cap applies
    "momentum_multiplier": 5,  # momentum = delta * this
    "regularity_scale": 10,  # regularity normalized to 0-this
    "volume_scale": 35,  # score_volume = log10(total_engagement+1) * this
    "ratio_scale": 25,  # ratio_approbation = log10(ratio_raw+1) * this
    "adaptive_ceiling": 0,  # 0 = disabled. When > 0, normalizes volume relative to this ceiling
    # ── Moteur « cote » célébrités (effet Bourse) — cf. compute_celebrity_index ──
    # GATE dormant par défaut : tant que False, l'indice célébrité reste = externe seul
    # (comportement α=1.0 inchangé). Passer à True en config pour activer le mouvement.
    "celebrity_vote_movement_enabled": False,
    "shrinkage_k": 40,          # shrinkage bayésien : c = n / (n + K). Petit K => bouge tôt.
    "move_cap": 15,             # décalage persistant max ± autour de l'ancre externe
    "momentum_gain": 5,         # gain du burst : Δmom = gain * (m_now - m_24h)
    "momentum_cap": 5,          # circuit breaker : |Δmom| borné à ± ce point/jour
    "external_fallback_anchor": 50,  # ancre si popularity_external_score absent
}


async def load_config(db) -> Dict[str, Any]:
    """Load algorithm config from MongoDB with in-memory caching."""
    global _config_cache, _config_last_loaded

    now = _utcnow()
    if _config_cache and _config_last_loaded:
        if (now - _config_last_loaded).total_seconds() < CONFIG_CACHE_TTL_SECONDS:
            return _config_cache

    try:
        doc = await db.algorithm_config.find_one({"_id": "popularoo_index"})
        if doc:
            _config_cache = doc
        else:
            # First run: seed default config
            await db.algorithm_config.insert_one(DEFAULT_CONFIG.copy())
            _config_cache = DEFAULT_CONFIG.copy()
            logger.info("📊 Seeded default algorithm_config")
    except Exception as e:
        logger.warning(f"Failed to load config from DB: {e}, using defaults")
        _config_cache = DEFAULT_CONFIG.copy()

    _config_last_loaded = now
    return _config_cache


# ── VERROU α = 1.0 (garde-fou « cœur honnête ») ──
# L'indice Popularoo est DÉFINITIVEMENT = popularité externe seule :
#   popularoo_index = 1.0 × external + 0.0 × votes.
# get_alpha() retourne 1.0 EN DUR (point d'étranglement unique lu par tout le
# recalcul d'indice), quelle que soit la valeur stockée en base. Le levier
# /admin/set-alpha est verrouillé (no-op) côté server.py.
ALPHA_LOCKED = 1.0


async def get_alpha(db) -> float:
    """
    VERROUILLÉ à 1.0 (cœur honnête). L'ancien réglage app_settings.alpha est ignoré.
    popularoo_index = α × external + (1-α) × votes, avec α = 1.0 → 100% external.
    Signature async conservée (les appelants font `await get_alpha(db)`).
    """
    return ALPHA_LOCKED


async def get_erosion_config(db) -> Tuple[float, float]:
    """
    Chantier « cœur honnête » : réglages d'érosion par inactivité des nouveaux
    entrants (branche 2), externalisés dans app_settings.global pour ajustement
    sans redeploy.
      - erosion_grace_days : jours sans vrai vote avant que l'érosion démarre.
      - erosion_per_week   : points de PI perdus par semaine d'inactivité.
    Retourne (grace_days, erosion_per_week). Cache 60 s.
    """
    global _erosion_cache, _erosion_last_loaded

    now = _utcnow()
    if _erosion_cache is not None and _erosion_last_loaded:
        if (now - _erosion_last_loaded).total_seconds() < EROSION_CACHE_TTL_SECONDS:
            return _erosion_cache

    grace = EROSION_GRACE_DAYS_DEFAULT
    per_week = EROSION_PER_WEEK_DEFAULT
    try:
        settings = await db.app_settings.find_one({"_id": "global"})
        if settings:
            grace = float(settings.get("erosion_grace_days", EROSION_GRACE_DAYS_DEFAULT))
            per_week = float(settings.get("erosion_per_week", EROSION_PER_WEEK_DEFAULT))
    except Exception as e:
        logger.warning(f"Failed to load erosion config: {e}, using defaults")

    _erosion_cache = (grace, per_week)
    _erosion_last_loaded = now
    return _erosion_cache


def compute_blended_index(
    alpha: float,
    external_score: Optional[float],
    score_votes_users: float,
) -> float:
    """
    Session 2: Compute the blended Popularoo Index.
    popularoo_index = α × external + (1-α) × votes

    Fallback (Préoccupation A): if external_score is None, use votes only.
    """
    if external_score is None:
        # No external score yet — ignore alpha, use votes only
        return round(max(0.0, min(100.0, score_votes_users)), 1)

    blended = (alpha * external_score) + ((1.0 - alpha) * score_votes_users)
    return round(max(0.0, min(100.0, blended)), 1)


def compute_score_votes_users(person: Dict) -> float:
    """
    Session 2: Compute the user vote component.
    score_votes_users = (likes - dislikes) / max(likes + dislikes, 1) × 100
    Range: -100 to +100.
    """
    likes = int(person.get("likes", 0))
    dislikes = int(person.get("dislikes", 0))
    total = likes + dislikes
    if total <= 0:
        return 0.0
    return ((likes - dislikes) / total) * 100


def compute_celebrity_index(
    person: Dict,
    config: Dict,
    m_24h_ago: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Moteur « cote » célébrités (effet Bourse) — ancre externe + mouvement de votes
    borné + momentum 24 h + shrinkage bayésien. Honnête : ne consomme que les VRAIS
    votes (seed_votes_* soustraits par sécurité, même si les faux ont été purgés).

    Formule :
        E   = popularity_external_score (ancre, [0..100]) ; None -> external_fallback_anchor
        L,D = vrais likes / dislikes ; n = L + D
        r   = (L - D) / n           ∈ [-1, +1]   (0 si n == 0)
        c   = n / (n + K)           shrinkage : peu de votes -> c≈0 -> quasi immobile
        S   = move_cap * c * r      décalage PERSISTANT borné (± move_cap)
        m   = c * r                 « pression » instantanée (à snapshoter pour le Δ24h)
        Δmom= clamp(momentum_gain * (m - m_24h_ago), ±momentum_cap)   (0 si pas de 24h)
        cote= clamp(E + S + Δmom, 0, 100)

    Renvoie (cote, m_now). m_now doit être stocké dans le snapshot pour alimenter le
    momentum du prochain recalcul. Aucun vote (n == 0) -> c=0 -> S=0, Δmom=0 -> cote = E
    (d'où : gate ON mais 0 vote => indices strictement égaux à l'externe).

    Isolation : ne lit ni n'écrit α, ne touche ni la Branche 1 (Outsiders) ni la
    Branche 2 (user_search). Bornée par move_cap / momentum_cap (circuit breakers).
    """
    E = person.get("popularity_external_score")
    if E is None:
        E = float(config.get("external_fallback_anchor", 50))
    E = float(E)

    likes = max(0, int(person.get("likes", 0) or 0) - int(person.get("seed_votes_likes", 0) or 0))
    dislikes = max(0, int(person.get("dislikes", 0) or 0) - int(person.get("seed_votes_dislikes", 0) or 0))
    n = likes + dislikes
    r = (likes - dislikes) / n if n > 0 else 0.0

    K = float(config.get("shrinkage_k", 40))
    move_cap = float(config.get("move_cap", 15))
    mom_gain = float(config.get("momentum_gain", config.get("momentum_multiplier", 5)))
    mom_cap = float(config.get("momentum_cap", 5))

    c = n / (n + K) if (n + K) > 0 else 0.0
    m_now = c * r
    S = move_cap * m_now

    if m_24h_ago is not None:
        d_mom = mom_gain * (m_now - m_24h_ago)
        d_mom = max(-mom_cap, min(mom_cap, d_mom))
    else:
        d_mom = 0.0

    cote = max(0.0, min(100.0, E + S + d_mom))
    return round(cote, 1), m_now


def compute_user_search_index(
    person: Dict,
    now: Optional[datetime] = None,
    grace_days: float = EROSION_GRACE_DAYS_DEFAULT,
    erosion_per_week: float = EROSION_PER_WEEK_DEFAULT,
) -> float:
    """
    Vague 4 — Branche 2 : évolution post-création des profils user_search.

    Le PI part de `initial_pi` (champ figé à la création, sous-tâche 6) et
    est "nudgé" par les VRAIS votes — c.-à-d. les votes encaissés au-delà des
    votes simulés au seeding (seed_votes_likes / seed_votes_dislikes ; désormais
    0 depuis le chantier « cœur honnête », mais toujours soustraits pour les
    profils legacy).

        real_likes    = max(0, likes    - seed_votes_likes)
        real_dislikes = max(0, dislikes - seed_votes_dislikes)
        real_net      = real_likes - real_dislikes
        nudge         = (real_net / 100.0) * 5.0   # 100 votes nets réels → +5 PI
        pi            = clamp(initial_pi + nudge - erosion, 25.0, 50.0)

    Érosion par inactivité (chantier « cœur honnête ») :
        Après `grace_days` sans VRAI vote positif, le PI s'érode de
        `erosion_per_week` points par semaine, vers le plancher dur 25 :

            jours_inactif = (now - last_real_vote_at) en jours
            erosion       = max(0, jours_inactif - grace_days) * (erosion_per_week / 7)

        Aucun vote négatif n'est requis : la seule inactivité fait redescendre.
        L'érosion n'est appliquée QUE si `now` est fourni (les appels historiques
        `compute_user_search_index(person)` restent sans érosion — rétro-compat
        des tests). `last_real_vote_at` absent → fallback `created_at` ; les deux
        absents → pas d'érosion (nudge seul).

    Garde-fous :
      - initial_pi absent (profils legacy pré-migration sous-tâche 9) → fallback 25.0
      - seed_votes_* absents (profils anciens / auto_detection) → 0, donc tous
        les votes comptent comme réels (comportement par défaut acceptable)
      - aucun vote réel → pi = initial_pi (nudge nul), puis érosion éventuelle

    Plafond DUR 50 / plancher DUR 25 : un profil Vague 4 ne peut JAMAIS
    dépasser 50 ni descendre sous 25, peu importe les votes ou l'érosion. Le
    franchissement de 50 nécessite une intervention admin manuelle (Lot 4).

    Isolation : cette branche ne lit ni α ni external_score et ne touche jamais
    la branche 3 des célébrités. L'érosion vit exclusivement ici.
    """
    initial_pi = person.get("initial_pi")
    if initial_pi is None:
        initial_pi = 25.0
    initial_pi = float(initial_pi)

    real_likes = max(0, person.get("likes", 0) - person.get("seed_votes_likes", 0))
    real_dislikes = max(0, person.get("dislikes", 0) - person.get("seed_votes_dislikes", 0))
    real_net = real_likes - real_dislikes

    nudge = (real_net / 100.0) * 5.0
    pi = initial_pi + nudge

    # ── Érosion par inactivité (branche 2 uniquement) ──
    if now is not None:
        last_vote = _to_naive_utc(person.get("last_real_vote_at") or person.get("created_at"))
        ref_now = _to_naive_utc(now)
        if last_vote is not None and ref_now is not None:
            days_inactive = (ref_now - last_vote).total_seconds() / 86400.0
            erosion = max(0.0, days_inactive - grace_days) * (erosion_per_week / 7.0)
            pi = pi - erosion

    # Plafond / plancher durs Vague 4
    pi = min(50.0, max(25.0, pi))
    return round(pi, 1)


def invalidate_config_cache():
    """Force reload config on next call."""
    global _config_cache, _config_last_loaded
    _config_cache = None
    _config_last_loaded = None


# ==================== COMPONENT CALCULATIONS ====================

def calc_score_volume(person: Dict, config: Dict) -> float:
    """
    score_volume = log10(total_engagement + 1) * volume_scale
    total_engagement = likes + (5 * superlikes) + dislikes
    Uses TOTAL engagement (notoriety) — not net positive.
    Being massively known (even controversially) = high volume.
    """
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    scale = config.get("volume_scale", 35)

    total_engagement = likes + (5 * superlikes) + dislikes
    total_engagement = max(0, total_engagement)
    return math.log10(total_engagement + 1) * scale


def calc_ratio_approbation(person: Dict, config: Dict) -> float:
    """
    ratio_approbation = log10((weighted_likes² / (weighted_likes + dislikes + 1)) + 1) * ratio_scale
    Log normalization prevents explosion with large vote counts while preserving relative ranking.
    weighted_likes = likes + (5 * superlikes)
    """
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    scale = config.get("ratio_scale", 10)

    weighted_likes = likes + (5 * superlikes)
    if weighted_likes <= 0:
        return 0.0

    ratio_raw = (weighted_likes ** 2) / (weighted_likes + dislikes + 1)
    # Log normalization: keeps the ranking but prevents explosion
    return math.log10(ratio_raw + 1) * scale


def calc_regularity(daily_vote_counts: list, config: Dict) -> float:
    """
    regularity = consistency of votes over 7 days × regularity_scale
    Uses inverse coefficient of variation (1 - CV) clamped to [0, 1].
    Perfect consistency (same votes each day) → 1.0
    No votes or wildly inconsistent → 0.0
    """
    scale = config.get("regularity_scale", 10)

    if not daily_vote_counts or len(daily_vote_counts) == 0:
        return 0.0

    counts = [float(c) for c in daily_vote_counts]
    mean = sum(counts) / len(counts)

    if mean == 0:
        return 0.0

    # Standard deviation
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    std_dev = math.sqrt(variance)

    # Coefficient of variation (CV = std/mean)
    cv = std_dev / mean if mean > 0 else 0

    # Inverse: high consistency = low CV = high regularity
    regularity = max(0.0, min(1.0, 1.0 - cv))
    return regularity * scale


def calc_strikes_bonus(person: Dict, config: Dict) -> float:
    """
    strikes_bonus = active_strikes × strike_value
    Only for outsiders (source = "self_boosted").
    """
    if person.get("source") != "self_boosted":
        return 0.0

    active_strikes = person.get("active_strikes", 0)
    strike_value = config.get("strike_value", 5)
    return active_strikes * strike_value


# ==================== INDEX CALCULATION ====================

def compute_base_index(person: Dict, config: Dict, daily_votes: Optional[list] = None) -> float:
    """
    Compute base_index (without momentum) for a person.
    base_index = volume * w_v + ratio * w_r + regularity * w_reg + strikes_bonus
    """
    coeffs = config.get("coefficients", DEFAULT_CONFIG["coefficients"])
    w_v = coeffs.get("volume", 0.20)
    w_r = coeffs.get("ratio", 0.40)
    w_reg = coeffs.get("regularity", 0.15)

    volume = calc_score_volume(person, config)
    ratio = calc_ratio_approbation(person, config)
    regularity = calc_regularity(daily_votes or [], config)
    strikes = calc_strikes_bonus(person, config)

    base = (volume * w_v) + (ratio * w_r) + (regularity * w_reg) + strikes
    return base


def compute_popularoo_index(
    person: Dict,
    config: Dict,
    daily_votes: Optional[list] = None,
    base_index_24h_ago: Optional[float] = None,
) -> Tuple[float, Dict[str, float]]:
    """
    Compute the full Popularoo Index for a person.

    Returns:
        (index, components_dict)
        index: float 0-100
        components_dict: breakdown of each component (for debugging/admin)
    """
    coeffs = config.get("coefficients", DEFAULT_CONFIG["coefficients"])
    w_v = coeffs.get("volume", 0.20)
    w_r = coeffs.get("ratio", 0.40)
    w_m = coeffs.get("momentum", 0.25)
    w_reg = coeffs.get("regularity", 0.15)

    volume = calc_score_volume(person, config)
    ratio = calc_ratio_approbation(person, config)
    regularity = calc_regularity(daily_votes or [], config)
    strikes = calc_strikes_bonus(person, config)

    base = (volume * w_v) + (ratio * w_r) + (regularity * w_reg) + strikes

    # Momentum: delta of base_index over 24h
    momentum_mult = config.get("momentum_multiplier", 5)
    if base_index_24h_ago is not None:
        momentum_raw = (base - base_index_24h_ago) * momentum_mult
    else:
        momentum_raw = 0.0

    final = base + (momentum_raw * w_m)

    # Low-vote cap — use total engagement, not net
    likes = person.get("likes", 0)
    superlikes = person.get("superlikes", 0)
    dislikes = person.get("dislikes", 0)
    total_engagement = likes + (5 * superlikes) + dislikes
    low_cap = config.get("low_vote_cap", 30)
    low_threshold = config.get("low_vote_threshold", 10)

    if total_engagement < low_threshold:
        final = min(final, low_cap)

    # Clamp to [0, 100]
    final = max(0.0, min(100.0, final))

    components = {
        "score_volume": round(volume, 2),
        "ratio_approbation": round(ratio, 2),
        "momentum_24h": round(momentum_raw, 2),
        "regularity": round(regularity, 2),
        "strikes_bonus": round(strikes, 2),
        "base_index": round(base, 2),
        "final_index": round(final, 2),
        "total_engagement": total_engagement,
    }

    return round(final, 1), components


# ==================== STRIKE LEVELS ====================

STRIKE_LEVELS = {
    0: ("", ""),
    1: ("🔥", "Heating Up"),
    2: ("⚡", "On Fire"),
    3: ("🌟", "Trending"),
    4: ("💥", "Going Viral"),
}
# 5+ → Legend Mode
LEGEND_MODE = ("👑", "Legend Mode")


def get_strike_level(strike_count: int) -> Tuple[str, str]:
    """
    Returns (emoji, label) for the given strike count.
    """
    if strike_count <= 0:
        return STRIKE_LEVELS[0]
    if strike_count >= 5:
        return LEGEND_MODE
    return STRIKE_LEVELS.get(strike_count, LEGEND_MODE)


# ==================== BACKGROUND JOBS ====================

async def get_daily_vote_counts(db, person_id, days: int = 7) -> list:
    """
    Aggregate vote counts per day for the last N days.
    Returns a list of N integers (one per day).
    """
    from bson import ObjectId
    now = _utcnow()
    start = now - timedelta(days=days)

    pipeline = [
        {"$match": {
            "person_id": ObjectId(str(person_id)) if not isinstance(person_id, ObjectId) else person_id,
            "created_at": {"$gte": start, "$lte": now}
        }},
        {"$group": {
            "_id": {
                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
            },
            "count": {"$sum": 1}
        }}
    ]

    cursor = db.vote_events.aggregate(pipeline)
    results = {}
    async for doc in cursor:
        results[doc["_id"]] = doc["count"]

    # Build array for all N days (0 for missing days)
    daily = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append(results.get(day, 0))

    return daily


async def get_base_index_24h_ago(db, person_id) -> Optional[float]:
    """Get the base_index snapshot from ~24h ago."""
    from bson import ObjectId
    pid = ObjectId(str(person_id)) if not isinstance(person_id, ObjectId) else person_id
    target_time = _utcnow() - timedelta(hours=24)

    # Find snapshot closest to 24h ago
    snapshot = await db.index_snapshots.find_one(
        {
            "person_id": pid,
            "timestamp": {"$lte": target_time}
        },
        sort=[("timestamp", -1)]
    )
    if snapshot:
        return snapshot.get("base_index", None)
    return None


async def get_vote_pressure_24h_ago(db, person_id) -> Optional[float]:
    """Pression de vote (m = c·r) snapshotée il y a ~24 h — alimente le momentum
    du moteur cote célébrités (compute_celebrity_index)."""
    from bson import ObjectId
    pid = ObjectId(str(person_id)) if not isinstance(person_id, ObjectId) else person_id
    target_time = _utcnow() - timedelta(hours=24)

    snapshot = await db.index_snapshots.find_one(
        {"person_id": pid, "timestamp": {"$lte": target_time}},
        sort=[("timestamp", -1)]
    )
    if snapshot:
        return snapshot.get("vote_pressure", None)
    return None


async def recalculate_index_for_person(db, person: Dict, config: Dict, alpha: Optional[float] = None) -> float:
    """
    Full recalculation of Popularoo Index for a single person.
    3-branch formula based on source.
      - self_boosted / outsider: PI = 3 + (net_votes / 10) * 1.0, cap 25
      - user_search / user_search_confirmed (Vague 4): initial_pi nudgé par
        les vrais votes, clamp dur [25, 50] — voir compute_user_search_index()
      - seed / unknown: α-blended formula (unchanged)
    Updates both 'score' and 'popularoo_index' with the same value.
    """
    from bson import ObjectId

    person_id = person["_id"]
    source = person.get("source", "unknown")
    now = _utcnow()

    # ── Branch 1: Outsiders (self_boosted OR category=outsider OR is_outsider) ──
    _is_outsider = source == "self_boosted" or person.get("category") == "outsider" or person.get("is_outsider") is True
    if _is_outsider:
        # Cœur honnête : on soustrait les votes simulés au seeding (seed_votes_*),
        # exactement comme la Branche 2 user_search (cf. compute_user_search_index).
        # Un vrai Outsider n'a pas de seed_votes_* → real == brut → impact NUL.
        likes = max(0, person.get("likes", 0) - person.get("seed_votes_likes", 0))
        dislikes = max(0, person.get("dislikes", 0) - person.get("seed_votes_dislikes", 0))
        net_votes = max(likes - dislikes, 0)
        index_val = min(3.0 + (net_votes / 10.0) * 1.0, 25.0)  # Cap Outsider PI at 25
        index_val = round(index_val, 1)

        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
                "last_index_calc": now,
            }}
        )
        await db.index_snapshots.insert_one({
            "person_id": person_id,
            "base_index": index_val,
            "popularoo_index": index_val,
            "timestamp": now,
        })
        return index_val

    # ── Branch 2: Profils user_search (évolution post-création Vague 4) ──
    # initial_pi figé à la création (25-40), nudgé par les VRAIS votes.
    # Plafond dur 50 / plancher dur 25. Les Outsiders (category=outsider) sont
    # déjà interceptés par la Branche 1 ci-dessus — garde défensive ici malgré tout.
    if source in ("user_search", "user_search_confirmed") and person.get("category") != "outsider":
        grace_days, erosion_per_week = await get_erosion_config(db)
        index_val = compute_user_search_index(
            person, now=now, grace_days=grace_days, erosion_per_week=erosion_per_week
        )

        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
                "last_index_calc": now,
            }}
        )
        await db.index_snapshots.insert_one({
            "person_id": person_id,
            "base_index": index_val,
            "popularoo_index": index_val,
            "timestamp": now,
        })
        return index_val

    # ── Branch 3: Célébrités / seeds existants ──
    # GATE moteur cote (effet Bourse). Dormant par défaut → comportement inchangé
    # (externe seul, α=1.0). Passé à True en config → ancre externe + mouvement votes.
    if bool(config.get("celebrity_vote_movement_enabled", False)):
        m_24h_ago = await get_vote_pressure_24h_ago(db, person_id)
        index_val, m_now = compute_celebrity_index(person, config, m_24h_ago)

        await db.persons.update_one(
            {"_id": person_id},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
                "last_index_calc": now,
            }}
        )
        await db.index_snapshots.insert_one({
            "person_id": person_id,
            "base_index": index_val,
            "popularoo_index": index_val,
            "vote_pressure": m_now,   # base du Δ24h pour le momentum
            "timestamp": now,
        })
        return index_val

    # Gate OFF → α-blended (externe seul à α=1.0), strictement inchangé.
    if alpha is None:
        alpha = await get_alpha(db)

    external_score = person.get("popularity_external_score")
    score_votes = compute_score_votes_users(person)
    index_val = compute_blended_index(alpha, external_score, score_votes)

    await db.persons.update_one(
        {"_id": person_id},
        {"$set": {
            "popularoo_index": index_val,
            "score": index_val,
            "last_index_calc": now,
        }}
    )

    await db.index_snapshots.insert_one({
        "person_id": person_id,
        "base_index": index_val,
        "popularoo_index": index_val,
        "timestamp": now,
    })

    return index_val


async def quick_recalc_index(db, person: Dict, config: Dict) -> float:
    """
    Quick recalculation after a vote.
    3-branch formula based on source (cf. recalculate_index_for_person).
    """
    source = person.get("source", "unknown")

    # ── Branch 1: Outsiders (self_boosted OR category=outsider OR is_outsider) ──
    _is_outsider = source == "self_boosted" or person.get("category") == "outsider" or person.get("is_outsider") is True
    if _is_outsider:
        # Cœur honnête : on soustrait les votes simulés au seeding (seed_votes_*),
        # exactement comme la Branche 2 user_search (cf. compute_user_search_index).
        # Un vrai Outsider n'a pas de seed_votes_* → real == brut → impact NUL.
        likes = max(0, person.get("likes", 0) - person.get("seed_votes_likes", 0))
        dislikes = max(0, person.get("dislikes", 0) - person.get("seed_votes_dislikes", 0))
        net_votes = max(likes - dislikes, 0)
        index_val = min(3.0 + (net_votes / 10.0) * 1.0, 25.0)  # Cap Outsider PI at 25
        index_val = round(index_val, 1)

        await db.persons.update_one(
            {"_id": person["_id"]},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
            }}
        )
        return index_val

    # ── Branch 2: Profils user_search (évolution post-création Vague 4) ──
    # Garde défensive category != outsider (déjà couvert par la Branche 1).
    if source in ("user_search", "user_search_confirmed") and person.get("category") != "outsider":
        grace_days, erosion_per_week = await get_erosion_config(db)
        index_val = compute_user_search_index(
            person, now=_utcnow(), grace_days=grace_days, erosion_per_week=erosion_per_week
        )

        await db.persons.update_one(
            {"_id": person["_id"]},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
            }}
        )
        return index_val

    # ── Branch 3: Célébrités / seeds existants ──
    # GATE moteur cote. Au vote, on applique l'ancre + décalage persistant S (le vote
    # bouge la cote TOUT DE SUITE) ; le momentum (Δ24h) est appliqué par le job 15 min
    # qui détient l'historique des snapshots → quick_recalc reste léger (pas de lecture DB).
    if bool(config.get("celebrity_vote_movement_enabled", False)):
        index_val, _m_now = compute_celebrity_index(person, config, m_24h_ago=None)
        await db.persons.update_one(
            {"_id": person["_id"]},
            {"$set": {
                "popularoo_index": index_val,
                "score": index_val,
            }}
        )
        return index_val

    # Gate OFF → α-blended (externe seul à α=1.0), strictement inchangé.
    alpha = await get_alpha(db)
    external_score = person.get("popularity_external_score")
    score_votes = compute_score_votes_users(person)
    index_val = compute_blended_index(alpha, external_score, score_votes)

    await db.persons.update_one(
        {"_id": person["_id"]},
        {"$set": {
            "popularoo_index": index_val,
            "score": index_val,
        }}
    )

    return index_val


async def recalculate_all_indices(db):
    """
    Background job: recalculate Popularoo Index for all active persons.
    Run every 15 minutes.
    Session 2: Loads alpha once, uses α-blended formula for non-outsiders.
    """
    config = await load_config(db)
    alpha = await get_alpha(db)
    now = _utcnow()

    # Find all persons with votes or active boosts
    cursor = db.persons.find({
        "$or": [
            {"total_votes": {"$gt": 0}},
            {"superlikes": {"$gt": 0}},
            {"source": "self_boosted"},
            {"popularity_external_score": {"$exists": True}},
        ]
    })

    count = 0
    async for person in cursor:
        try:
            await recalculate_index_for_person(db, person, config, alpha)
            count += 1
        except Exception as e:
            logger.warning(f"Failed to recalculate index for {person.get('name')}: {e}")

    # Clean old snapshots (keep only last 48h)
    cutoff = now - timedelta(hours=48)
    result = await db.index_snapshots.delete_many({"timestamp": {"$lt": cutoff}})
    if result.deleted_count > 0:
        logger.debug(f"🗑️ Cleaned {result.deleted_count} old index snapshots")

    logger.info(f"📊 Recalculated Popularoo Index for {count} persons (α={alpha})")
    return count


async def ensure_indexes(db):
    """Create MongoDB indexes for efficient queries."""
    try:
        # Index snapshots: fast lookup by person + timestamp
        await db.index_snapshots.create_index(
            [("person_id", 1), ("timestamp", -1)]
        )
        # Superlike events: for strike detection
        await db.superlike_events.create_index(
            [("person_id", 1), ("created_at", -1)]
        )
        await db.superlike_events.create_index(
            [("person_id", 1), ("device_id", 1), ("created_at", -1)]
        )
        # Superlike votes: for cooldown tracking
        await db.superlike_votes.create_index(
            [("person_id", 1), ("device_id", 1)]
        )
        # Strikes
        await db.strikes.create_index(
            [("person_id", 1), ("expires_at", 1)]
        )
        # Vote events (for regularity)
        await db.vote_events.create_index(
            [("person_id", 1), ("created_at", -1)]
        )
        logger.info("📊 Popularoo Index database indexes ensured")
    except Exception as e:
        logger.warning(f"Failed to create indexes: {e}")


# ==================== MIGRATION ====================

async def migrate_initial_index(db):
    """
    One-time migration: calculate initial Popularoo Index for all persons.
    Adds superlikes=0 and computes initial index based on existing votes.
    """
    config = await load_config(db)

    # Add superlikes field if missing
    await db.persons.update_many(
        {"superlikes": {"$exists": False}},
        {"$set": {"superlikes": 0}}
    )

    # Add active_strikes field if missing
    await db.persons.update_many(
        {"active_strikes": {"$exists": False}},
        {"$set": {"active_strikes": 0}}
    )

    # Calculate index for all persons
    cursor = db.persons.find({})
    count = 0
    async for person in cursor:
        try:
            daily_votes = await get_daily_vote_counts(db, person["_id"])
            index_val, components = compute_popularoo_index(
                person, config, daily_votes, None  # No 24h snapshot yet
            )
            base = components["base_index"]

            await db.persons.update_one(
                {"_id": person["_id"]},
                {"$set": {
                    "popularoo_index": index_val,
                    "base_index": base,
                    "index_components": components,
                    "last_index_calc": _utcnow(),
                    "superlikes": person.get("superlikes", 0),
                    "active_strikes": person.get("active_strikes", 0),
                }}
            )

            # Initial snapshot
            await db.index_snapshots.insert_one({
                "person_id": person["_id"],
                "base_index": base,
                "popularoo_index": index_val,
                "timestamp": _utcnow(),
            })

            count += 1
        except Exception as e:
            logger.warning(f"Migration failed for {person.get('name')}: {e}")

    logger.info(f"✅ Popularoo Index migration complete: {count} persons indexed")
    return count
