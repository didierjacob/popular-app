"""
Résolution Wikidata PAR NOM, à la demande (commit 2/5 du chantier « Wikipédia
d'abord, modération en repli »). Alimente POST /api/people/from-wikipedia (commit 3).

POURQUOI PAS WDQS : l'import des 608 interroge query.wikidata.org (SPARQL), qui
répond en 504 sous charge — inacceptable dans un cycle de requête utilisateur.
Ce module n'utilise QUE l'API Action de Wikidata (www.wikidata.org/w/api.php),
un endpoint de lecture caché, en DEUX appels :
    1. wbsearchentities  → jusqu'à SEARCH_LIMIT QID candidats pour le nom saisi
    2. wbgetentities     → claims + sitelinks + labels des candidats, EN UN SEUL appel
WDQS n'est jamais sollicité ici.

wbsearchentities cherche par PRÉFIXE sur libellés et alias, sans tolérance à
l'ordre des mots. D'où deux replis, tous deux GRATUITS dans le cas nominal (ils ne
partent qu'après un échec) : langue (fr → en), puis permutation si la saisie fait
exactement 2 mots (« Adjani Isabelle » → « Isabelle Adjani »). Une seule tentative
chacun.

POURQUOI PAS search_wikipedia_person (server.py) : cette fonction devine tout à
partir du *snippet* de recherche en.wikipedia (décès détecté par la présence de
« was a », catégorie par mots-clés). Aucun P569/P570/P106/sitelinks. Elle ne peut
pas porter les garde-fous exigés et n'est pas utilisée ici.

GARDE-FOUS — identiques à l'import des 608, via wikidata_common (source unique) :
  1. humain          P31 contient Q5
  2. insultes        libellé Wikidata RÉSOLU (pas seulement la saisie utilisateur)
  3. décédés         AUCUN claim P570 (y compris novalue/somevalue : plus strict
                     que le `wdt:` de SPARQL, volontaire sur un chemin public)
  4. mineurs         P569 REQUISE et âge >= 18
  5. notoriété       nombre de sitelinks >= plancher (défaut DEFAULT_SITELINKS_FLOOR)
  6. catégorie       cat_of(P106) != "other"  (« other » exclu comme à l'import)
  7. latence         timeout par appel + enveloppe globale → jamais d'exception

⚠️  DIVERGENCE ASSUMÉE avec l'import des 608, garde-fou 4 : l'import inclut les
    personnes dont P569 est absente (import_wikidata.py, liste `age_unknown`).
    Ici une date de naissance INCONNUE est un REJET. Plus strict, décidé pour la
    sécurité mineurs : l'import des 608 est éditorial et relu, ce chemin-ci est
    public et déclenché par n'importe quel utilisateur.

CE MODULE NE TOUCHE NI LA BASE NI LE RÉSEAU SORTANT AUTRE QUE WIKIDATA. La dédup
(wikidata_id / name_normalized / slug), la blocklist anti-fantôme, le ban device,
le rate-limit et l'écriture dans `persons` sont l'affaire de l'endpoint (commit 3).

Tests hors ligne : python3 test_wikidata_resolve.py
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from unidecode import unidecode

from wikidata_common import (
    DEFAULT_SITELINKS_FLOOR,
    age_from_birth,
    cat_of,
    provisional_score,
)
from wordlist_profanity import contains_profanity

logger = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# Wikimedia throttle les User-Agent anonymes : le nôtre doit être explicite.
USER_AGENT = "Popularoo/1.0 (contact@popularoo.com)"

SEARCH_LIMIT = 5        # candidats demandés à wbsearchentities
DETAIL_LIMIT = 3        # candidats réellement détaillés (borne la charge utile :
                        # wbgetentities renvoie TOUS les claims, ~200 Ko par figure majeure)
HTTP_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
RESOLVE_BUDGET_S = 6.0  # enveloppe globale, au-delà → "unavailable"

Q_HUMAN = "Q5"
MIN_AGE = 18

# ── Statuts renvoyés (contrat avec l'endpoint, puis avec le front) ──
STATUS_RESOLVED = "resolved"        # → créer / naviguer vers la fiche
STATUS_NOT_FOUND = "not_found"      # → formulaire de repli
STATUS_REJECTED = "rejected"        # → formulaire de repli (raison en LOGS seulement)
STATUS_UNAVAILABLE = "unavailable"  # → formulaire de repli (Wikidata lent/en panne)

# ── Raisons de rejet : LOGS ET OBSERVABILITÉ UNIQUEMENT. ──
# Ne JAMAIS les afficher : « cette personne est mineure / décédée / pas assez
# connue » divulgue une information sur un tiers depuis une app publique. Le front
# affiche un message neutre unique (cf. plan, arbitrage ③).
REASON_NOT_HUMAN = "not_human"
REASON_PROFANITY = "profanity"
REASON_DECEASED = "deceased"
REASON_BIRTH_UNKNOWN = "birth_unknown"
REASON_MINOR = "minor"
REASON_NOT_NOTABLE = "not_notable"
REASON_CATEGORY_OTHER = "category_other"

# P27 (nationalité) → ISO-2, pour primary_country / country_tags (drapeaux).
# Base : les 23 pays du PANEL de fetch_wikidata (convention app UK→GB), étendue à
# quelques pays européens et francophones fréquents. Purement COSMÉTIQUE : un pays
# absent donne primary_country="" et ne bloque JAMAIS la création.
COUNTRY_QID_TO_ISO = {
    # Panel d'import des 608
    "Q142": "FR", "Q145": "GB", "Q183": "DE", "Q38": "IT", "Q29": "ES", "Q159": "RU",
    "Q30": "US", "Q155": "BR", "Q96": "MX", "Q16": "CA", "Q414": "AR",
    "Q668": "IN", "Q148": "CN", "Q17": "JP", "Q884": "KR", "Q252": "ID",
    "Q43": "TR", "Q794": "IR", "Q79": "EG",
    "Q1033": "NG", "Q258": "ZA", "Q1028": "MA", "Q408": "AU",
    # Extension (hors panel) : Europe proche + francophonie
    "Q31": "BE", "Q39": "CH", "Q45": "PT", "Q55": "NL", "Q34": "SE", "Q35": "DK",
    "Q20": "NO", "Q33": "FI", "Q36": "PL", "Q40": "AT", "Q27": "IE", "Q41": "GR",
    "Q262": "DZ", "Q948": "TN", "Q1041": "SN", "Q1008": "CI", "Q1009": "CM",
    "Q974": "CD", "Q790": "HT", "Q298": "CL", "Q739": "CO", "Q419": "PE",
}

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Normalisation de comparaison : accents retirés, espaces compactés, minuscules."""
    return unidecode(_WS_RE.sub(" ", (text or "").strip())).lower()


def _claim_qids(claims: Dict[str, Any], prop: str) -> List[str]:
    """QID des snaks de type `value` pour une propriété (P31, P106, P27…)."""
    out = []
    for claim in claims.get(prop) or []:
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        qid = ((snak.get("datavalue") or {}).get("value") or {}).get("id")
        if qid:
            out.append(qid)
    return out


def _claim_times(claims: Dict[str, Any], prop: str) -> List[str]:
    """Dates ISO Wikidata (`+1955-06-27T00:00:00Z`) pour une propriété temporelle."""
    out = []
    for claim in claims.get(prop) or []:
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        time_val = ((snak.get("datavalue") or {}).get("value") or {}).get("time")
        if time_val:
            out.append(time_val)
    return out


def _has_any_claim(claims: Dict[str, Any], prop: str) -> bool:
    """True dès qu'un claim existe, même `novalue`/`somevalue`.

    Utilisé pour P570 : « mort à une date inconnue » reste une mort. Plus strict
    que le `wdt:` de SPARQL (qui ne retient que les valeurs réelles) — assumé.
    """
    return bool(claims.get(prop))


def _best_label(entity: Dict[str, Any], fallback: str = "") -> str:
    labels = entity.get("labels") or {}
    for lang in ("fr", "en"):
        val = (labels.get(lang) or {}).get("value")
        if val:
            return val
    return fallback


def _best_description(entity: Dict[str, Any]) -> str:
    descs = entity.get("descriptions") or {}
    for lang in ("fr", "en"):
        val = (descs.get(lang) or {}).get("value")
        if val:
            return val
    return ""


def _primary_country(claims: Dict[str, Any]) -> str:
    for qid in _claim_qids(claims, "P27"):
        iso = COUNTRY_QID_TO_ISO.get(qid)
        if iso:
            return iso
    return ""


def evaluate_entity(
    qid: str,
    entity: Dict[str, Any],
    floor: int,
    now: datetime,
    search_label: str = "",
) -> Dict[str, Any]:
    """Applique les garde-fous 1-6 à UNE entité Wikidata.

    Renvoie {"ok": True, "person": {...}} ou {"ok": False, "reason": "..."}.
    Fonction PURE (aucun réseau, aucune base) : c'est elle que testent les tests
    hors ligne.
    """
    claims = entity.get("claims") or {}

    # 1) Humain — écarte les homonymes non-humains (l'album « Isabelle Adjani »
    #    est le 2e résultat de recherche pour ce nom).
    if Q_HUMAN not in _claim_qids(claims, "P31"):
        return {"ok": False, "reason": REASON_NOT_HUMAN}

    label = _best_label(entity, fallback=search_label)

    # 2) Insultes sur le libellé RÉSOLU (et pas seulement sur la saisie).
    if contains_profanity(label):
        return {"ok": False, "reason": REASON_PROFANITY}

    # 3) Décédés (P570) — l'app exclut les défunts par design.
    if _has_any_claim(claims, "P570"):
        return {"ok": False, "reason": REASON_DECEASED}

    # 4) Mineurs (P569) — date de naissance REQUISE ici (cf. divergence assumée).
    births = _claim_times(claims, "P569")
    age, known = age_from_birth(births[0] if births else None, now)
    if not known:
        return {"ok": False, "reason": REASON_BIRTH_UNKNOWN}
    if age < MIN_AGE:
        return {"ok": False, "reason": REASON_MINOR}

    # 5) Plancher de notoriété — même métrique que `wikibase:sitelinks` en SPARQL.
    sitelinks = len(entity.get("sitelinks") or {})
    if sitelinks < floor:
        return {"ok": False, "reason": REASON_NOT_NOTABLE}

    # 6) Catégorie via P106 — « other » (académiques, droit, science) exclu, comme
    #    à l'import des 608.
    occupations = _claim_qids(claims, "P106")
    category = cat_of(occupations)
    if category == "other":
        return {"ok": False, "reason": REASON_CATEGORY_OTHER}

    return {
        "ok": True,
        "person": {
            "wikidata_id": qid,
            "name": label,
            "category": category,
            "sitelinks": sitelinks,
            "provisional_score": provisional_score(sitelinks),
            "birth": births[0],
            "age": age,
            "description": _best_description(entity),
            "primary_country": _primary_country(claims),
            "occupations": occupations,
        },
    }


async def _search_entities(client: httpx.AsyncClient, name: str, language: str) -> List[Dict[str, Any]]:
    resp = await client.get(
        WIKIDATA_API,
        params={
            "action": "wbsearchentities",
            "search": name,
            "language": language,
            "uselang": language,
            "type": "item",
            "limit": SEARCH_LIMIT,
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code != 200:
        raise httpx.HTTPError(f"wbsearchentities {resp.status_code}")
    return resp.json().get("search") or []


async def _get_entities(client: httpx.AsyncClient, qids: List[str]) -> Dict[str, Any]:
    resp = await client.get(
        WIKIDATA_API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "claims|sitelinks|labels|descriptions",
            "languages": "fr|en",
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code != 200:
        raise httpx.HTTPError(f"wbgetentities {resp.status_code}")
    return resp.json().get("entities") or {}


def _order_candidates(hits: List[Dict[str, Any]], name: str) -> List[Dict[str, Any]]:
    """Libellé identique à la saisie d'abord, puis l'ordre de pertinence de l'API."""
    target = _norm(name)
    exact = [h for h in hits if _norm(h.get("label", "")) == target]
    rest = [h for h in hits if h not in exact]
    return exact + rest


def _swapped_words(name: str) -> Optional[str]:
    """« Adjani Isabelle » → « Isabelle Adjani ». None si ça n'a pas de sens.

    wbsearchentities cherche par PRÉFIXE sur les libellés et alias : ce n'est pas
    une recherche floue, et l'ordre inversé ne renvoie RIEN (vérifié le 2026-08-01,
    « adjani isabelle » → 0 résultat). Or « Nom Prénom » est une saisie courante.

    Strictement 2 mots : au-delà, le nombre de permutations n'est plus justifiable
    et le risque de résoudre vers une autre personne augmente.
    """
    parts = name.split()
    if len(parts) != 2:
        return None
    swapped = f"{parts[1]} {parts[0]}"
    # Deux mots identiques (« Ali Ali ») : la permutation ne changerait rien.
    return swapped if swapped != name else None


async def _resolve(name: str, floor: int, now: datetime, client: httpx.AsyncClient) -> Dict[str, Any]:
    # La requête qui a effectivement produit les résultats — sert au classement
    # « libellé identique d'abord » plus bas, qui doit comparer à la BONNE chaîne.
    effective_query = name

    hits = await _search_entities(client, name, "fr")
    if not hits:
        # Nom probablement anglophone : une seconde chance, puis on abandonne.
        hits = await _search_entities(client, name, "en")
    if not hits:
        # Dernier recours, gratuit dans le cas nominal : on n'arrive ici qu'après
        # deux recherches infructueuses. Une seule tentative, jamais davantage.
        swapped = _swapped_words(name)
        if swapped:
            hits = await _search_entities(client, swapped, "fr")
            if hits:
                effective_query = swapped
    if not hits:
        return {"status": STATUS_NOT_FOUND}

    ordered = _order_candidates(hits, effective_query)[:DETAIL_LIMIT]
    qids = [h["id"] for h in ordered if h.get("id")]
    if not qids:
        return {"status": STATUS_NOT_FOUND}

    entities = await _get_entities(client, qids)

    # On garde la raison la PLUS INFORMATIVE : celle d'un candidat humain prime
    # sur le bruit des homonymes non-humains (albums, films, listes…).
    best_reason: Optional[str] = None
    for hit in ordered:
        qid = hit.get("id")
        entity = entities.get(qid)
        if not entity:
            continue
        verdict = evaluate_entity(qid, entity, floor, now, search_label=hit.get("label", ""))
        if verdict["ok"]:
            return {"status": STATUS_RESOLVED, "person": verdict["person"]}
        reason = verdict["reason"]
        if best_reason is None or best_reason == REASON_NOT_HUMAN:
            best_reason = reason

    if best_reason is None or best_reason == REASON_NOT_HUMAN:
        # Aucun humain parmi les résultats → « Wikidata ne connaît pas cette
        # personne », ce qui est plus juste qu'un rejet.
        return {"status": STATUS_NOT_FOUND}
    return {"status": STATUS_REJECTED, "reason": best_reason}


async def wikidata_resolve_by_name(
    name: str,
    floor: int = DEFAULT_SITELINKS_FLOOR,
    now: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Résout un nom en une fiche Wikidata éligible, ou explique pourquoi non.

    Renvoie l'un de :
        {"status": "resolved",    "person": {...}}
        {"status": "not_found"}
        {"status": "rejected",    "reason": "<logs uniquement>"}
        {"status": "unavailable"}

    NE LÈVE JAMAIS : toute panne réseau, tout timeout, tout JSON inattendu devient
    "unavailable". L'appelant retombe alors sur le formulaire modéré — l'utilisateur
    n'est jamais bloqué par une indisponibilité de Wikidata.

    `client` est injectable pour les tests hors ligne.
    """
    clean = _WS_RE.sub(" ", (name or "").strip())
    if not clean:
        return {"status": STATUS_NOT_FOUND}
    now = now or datetime.now(timezone.utc)

    async def _run() -> Dict[str, Any]:
        if client is not None:
            return await _resolve(clean, floor, now, client)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as owned:
            return await _resolve(clean, floor, now, owned)

    try:
        result = await asyncio.wait_for(_run(), timeout=RESOLVE_BUDGET_S)
    except asyncio.TimeoutError:
        logger.warning(f"[wikidata_resolve] budget {RESOLVE_BUDGET_S}s dépassé pour '{clean}'")
        return {"status": STATUS_UNAVAILABLE}
    except Exception as e:
        logger.warning(f"[wikidata_resolve] échec pour '{clean}': {type(e).__name__}: {e}")
        return {"status": STATUS_UNAVAILABLE}

    if result["status"] == STATUS_REJECTED:
        # Seule trace de la raison exacte : elle ne remonte jamais à l'utilisateur.
        logger.info(f"[wikidata_resolve] '{clean}' rejeté ({result['reason']})")
    return result
