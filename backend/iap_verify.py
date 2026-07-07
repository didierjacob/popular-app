"""
Server-side In-App Purchase verification.

Currently Android-only (Google Play). Apple / App Store server validation is
deliberately out of scope here and deferred to a future lot — see boost_myself
in server.py where iOS receipts keep passing through unverified.

The single public entrypoint is verify_google_purchase(product_id, purchase_token),
which asks Google whether a given purchase token is a real, completed purchase of
a given product. It NEVER raises on an operational failure (missing key, network
error, timeout, unknown token): it always returns a dict, and the caller decides
whether to enforce (refuse) or merely observe (log) based on its own env flag.
"""

import os
import logging
import threading

logger = logging.getLogger(__name__)

# ── Constants ──
# Android application id, as published on Google Play. Fixed server-side; never
# taken from the client.
ANDROID_PACKAGE = "com.didierjacob.popularapp"

# tier → Google Play productId. Derived SERVER-SIDE from the trusted tier only,
# never from a client-supplied "product" field. This is what prevents a client
# from paying for a cheap tier while claiming an expensive one (or vice-versa):
# the token we verify is always checked against the product our own tier logic
# expects.
TIER_TO_PRODUCT_ID = {
    "booster": "popularoo_booster",
    "super_booster": "popularoo_super_booster",
    "golden_booster": "popularoo_golden_booster",
}

# Path to the Google service-account JSON key. Overridable via env so the same
# code runs in prod (Render Secret File) and in tests. Default matches the
# Render Secret File mount.
GOOGLE_SA_PATH_ENV = "GOOGLE_SA_PATH"
DEFAULT_SA_PATH = "/etc/secrets/google-service-account.json"

ANDROIDPUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# Short timeout: a slow Google response must not hang a paid checkout. On timeout
# the call returns valid=False with reason="api_error"; enforce/observe is the
# caller's decision.
HTTP_TIMEOUT_SECONDS = 8

# Google purchaseState: 0 = purchased, 1 = canceled, 2 = pending.
_PURCHASE_STATE_PURCHASED = 0

# Cached androidpublisher client (building it does disk I/O + auth; reuse it).
_client = None
_client_lock = threading.Lock()


def _sentry_capture(exc):
    """Report to Sentry if the SDK is configured; silent no-op otherwise."""
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def product_id_for_tier(tier):
    """Return the Google Play productId for a validated tier, or None if unknown."""
    return TIER_TO_PRODUCT_ID.get(tier)


def _get_client():
    """Build (once) and return a cached androidpublisher v3 client with a short
    request timeout. Raises FileNotFoundError if the SA key is missing, or a
    generic Exception if the client cannot be constructed."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client

        import httplib2
        from google.oauth2 import service_account
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build

        sa_path = os.getenv(GOOGLE_SA_PATH_ENV, DEFAULT_SA_PATH)
        if not os.path.exists(sa_path):
            raise FileNotFoundError(
                f"Google service account key not found at {sa_path}"
            )

        creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=[ANDROIDPUBLISHER_SCOPE]
        )
        # Timeout-aware HTTP so a slow Google response cannot hang checkout.
        authed_http = AuthorizedHttp(
            creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS)
        )
        _client = build(
            "androidpublisher",
            "v3",
            http=authed_http,
            cache_discovery=False,
        )
        return _client


def verify_google_purchase(product_id, purchase_token):
    """
    Verify a Google Play in-app purchase.

    Calls androidpublisher purchases.products.get(packageName, productId, token)
    and returns a dict:
        {"valid": bool, "reason": str, "raw": dict|None}

    valid is True ONLY when Google confirms purchaseState == 0 (purchased).
    Any operational problem — missing key, network/timeout, unknown token,
    canceled/pending purchase — returns valid=False with a machine-readable
    reason and never raises. The caller enforces (403) or observes (log) as it
    sees fit.
    """
    if not product_id:
        return {"valid": False, "reason": "no_product_id", "raw": None}
    if not purchase_token:
        return {"valid": False, "reason": "no_purchase_token", "raw": None}

    try:
        client = _get_client()
    except FileNotFoundError as e:
        # Fail-safe: key absent. Log + Sentry; caller decides enforce vs observe.
        logger.error(f"IAP verify: service account key missing: {e}")
        _sentry_capture(e)
        return {"valid": False, "reason": "sa_key_missing", "raw": None}
    except Exception as e:
        logger.error(f"IAP verify: failed to build Google client: {e}")
        _sentry_capture(e)
        return {"valid": False, "reason": "client_init_failed", "raw": None}

    try:
        resp = (
            client.purchases()
            .products()
            .get(
                packageName=ANDROID_PACKAGE,
                productId=product_id,
                token=purchase_token,
            )
            .execute(num_retries=0)
        )
    except Exception as e:
        # Network error, timeout, 4xx/5xx from Google (incl. unknown token).
        logger.error(
            f"IAP verify: Google API call failed (product={product_id}): {e}"
        )
        _sentry_capture(e)
        return {"valid": False, "reason": "api_error", "raw": None}

    purchase_state = resp.get("purchaseState")
    if purchase_state == _PURCHASE_STATE_PURCHASED:
        return {"valid": True, "reason": "purchased", "raw": resp}
    return {"valid": False, "reason": f"purchase_state_{purchase_state}", "raw": resp}
