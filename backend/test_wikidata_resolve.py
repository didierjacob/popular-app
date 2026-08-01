"""
Tests unitaires locaux de wikidata_resolve (commit 2/5 « Wikipédia d'abord »).

Aucun réseau, aucun MongoDB : les réponses de l'API Action de Wikidata sont
rejouées depuis des fixtures construites à partir de VRAIES réponses (Q106383
Isabelle Adjani, Q11831704 l'album homonyme, relevées le 2026-08-01).

Run :
    python3 test_wikidata_resolve.py

Couvre les 6 garde-fous Wikidata + le contrat de statuts :
   1. Cas nominal (Isabelle Adjani)      → resolved, culture, FR, indice 79.3
   2. Homonyme non-humain (l'album)      → not_found (aucun humain trouvé)
   3. Décédé (P570 avec valeur)          → rejected/deceased
   4. P570 novalue (mort, date inconnue) → rejected/deceased  (plus strict que SPARQL)
   5. Mineur avéré                       → rejected/minor
   6. P569 absente                       → rejected/birth_unknown  (divergence assumée)
   7. Plancher de notoriété (44/45/45)   → rejected/not_notable, et OK pile au seuil
   8. Catégorie « other » / sans P106    → rejected/category_other
   9. Insulte dans le libellé résolu     → rejected/profanity
  10. Recherche vide / nom vide          → not_found
  11. Panne réseau, JSON illisible,
      HTTP 503, budget dépassé           → unavailable (jamais d'exception)
  12. Priorité des raisons               → un humain prime sur les homonymes
  13. 2e candidat retenu si le 1er échoue
  14. Plancher configurable              → le même sujet passe ou non selon `floor`

Validé en plus contre l'API RÉELLE le 2026-08-01 (hors CI, réseau requis) :
  Isabelle Adjani → resolved culture FR 91 sitelinks | Mbappé → sport | Macron →
  politics | Elvis Presley → rejected/deceased | nom absurde → not_found.
  Latence observée : 0,9 à 1,4 s pour les deux appels (budget 6 s).
"""
import asyncio
from datetime import datetime, timezone

import wikidata_resolve as WR
from wikidata_resolve import evaluate_entity, wikidata_resolve_by_name

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)

results = {"pass": 0, "fail": 0}


def check(label, got, expected):
    ok = got == expected
    results["pass" if ok else "fail"] += 1
    print(f"  {PASS if ok else FAIL}  {label}")
    if not ok:
        print(f"        attendu : {expected!r}")
        print(f"        obtenu  : {got!r}")


# ──────────────────────────── Fabriques de fixtures ────────────────────────────
def snak_qid(qid):
    return {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": qid}}}}


def snak_time(time_iso):
    return {"mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": time_iso}}}}


def entity(label="Isabelle Adjani", p31="Q5", birth="+1955-06-27T00:00:00Z",
           death=None, occupations=("Q10800557",), sitelinks=91, country="Q142",
           description="actrice française"):
    claims = {}
    if p31:
        claims["P31"] = [snak_qid(p31)]
    if birth:
        claims["P569"] = [snak_time(birth)]
    if death is not None:
        claims["P570"] = death
    if occupations:
        claims["P106"] = [snak_qid(q) for q in occupations]
    if country:
        claims["P27"] = [snak_qid(country)]
    return {
        "claims": claims,
        "sitelinks": {f"site{i}": {} for i in range(sitelinks)},
        "labels": {"fr": {"value": label}},
        "descriptions": {"fr": {"value": description}},
    }


ADJANI = entity()
ALBUM = entity(label="Isabelle Adjani", p31="Q482994", birth=None, occupations=(),
               sitelinks=1, country=None, description="album d'Isabelle Adjani")


# ──────────────────────────── Faux client httpx ────────────────────────────
class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeClient:
    """Rejoue wbsearchentities puis wbgetentities. `boom` simule une panne.

    `hits` accepte une liste (mêmes résultats quelle que soit la requête) ou un
    dict {chaîne recherchée: résultats}, pour tester les replis langue/permutation.
    `searches` conserve les chaînes réellement envoyées à wbsearchentities.
    """

    def __init__(self, hits, entities, boom=None):
        self.hits = hits
        self.entities = entities
        self.boom = boom
        self.calls = []
        self.searches = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(params.get("action"))
        if self.boom:
            raise self.boom
        if params["action"] == "wbsearchentities":
            term = params["search"]
            self.searches.append(term)
            hits = self.hits.get(term, []) if isinstance(self.hits, dict) else self.hits
            return FakeResponse({"search": hits})
        return FakeResponse({"entities": self.entities})


def resolve(hits, entities, boom=None, floor=45):
    client = FakeClient(hits, entities, boom)
    return asyncio.run(wikidata_resolve_by_name("Isabelle Adjani", floor=floor, now=NOW, client=client))


# ──────────────────────────── 1. Cas nominal ────────────────────────────
print("\n1. Cas nominal — Isabelle Adjani")
res = resolve([{"id": "Q106383", "label": "Isabelle Adjani"}], {"Q106383": ADJANI})
check("statut resolved", res["status"], "resolved")
p = res.get("person", {})
check("wikidata_id", p.get("wikidata_id"), "Q106383")
check("nom", p.get("name"), "Isabelle Adjani")
check("catégorie (P106 Q10800557 → culture)", p.get("category"), "culture")
check("sitelinks", p.get("sitelinks"), 91)
check("indice provisoire (log sitelinks)", p.get("provisional_score"), 79.3)
check("âge", p.get("age"), 71)
check("pays (P27 Q142 → FR)", p.get("primary_country"), "FR")


# ──────────────── 2. Homonyme non-humain : l'album du même nom ────────────────
print("\n2. Homonyme non-humain (l'album « Isabelle Adjani », 2e résultat réel)")
res = resolve([{"id": "Q11831704", "label": "Isabelle Adjani"}], {"Q11831704": ALBUM})
check("statut not_found (aucun humain)", res["status"], "not_found")


# ──────────────────────────── 3-9. Garde-fous ────────────────────────────
print("\n3-9. Garde-fous (evaluate_entity, fonction pure)")


def reason_for(**kwargs):
    v = evaluate_entity("Q1", entity(**kwargs), 45, NOW)
    return v.get("reason") if not v["ok"] else "OK"


check("décédé (P570 avec valeur)", reason_for(death=[snak_time("+2020-01-01T00:00:00Z")]), "deceased")
check("décédé (P570 novalue → plus strict que SPARQL)",
      reason_for(death=[{"mainsnak": {"snaktype": "novalue"}}]), "deceased")
check("mineur avéré (né en 2015)", reason_for(birth="+2015-01-01T00:00:00Z"), "minor")
check("P569 absente → rejet (divergence assumée)", reason_for(birth=None), "birth_unknown")
check("sous le plancher (44 < 45)", reason_for(sitelinks=44), "not_notable")
check("au plancher exact (45)", reason_for(sitelinks=45), "OK")
check("catégorie other (Q1622272 académique)", reason_for(occupations=("Q1622272",)), "category_other")
check("sans P106 → other", reason_for(occupations=()), "category_other")
check("non-humain (P31 != Q5)", reason_for(p31="Q482994"), "not_human")
check("priorité catégorie (politics > culture)",
      evaluate_entity("Q1", entity(occupations=("Q10800557", "Q82955")), 45, NOW)["person"]["category"],
      "politics")
check("pays inconnu → vide, ne bloque pas",
      evaluate_entity("Q1", entity(country="Q999999"), 45, NOW)["person"]["primary_country"], "")

_slur = sorted(__import__("wordlist_profanity").PROFANITY_TERMS)[0]
check("insulte dans le libellé résolu", reason_for(label=f"Jean {_slur}"), "profanity")


# ──────────────────────────── 10-11. Contrat de statuts ────────────────────────────
print("\n10-11. Contrat de statuts")
check("recherche vide → not_found", resolve([], {})["status"], "not_found")
check("nom vide → not_found",
      asyncio.run(wikidata_resolve_by_name("   ", now=NOW, client=FakeClient([], {})))["status"], "not_found")
check("panne réseau → unavailable (pas d'exception)",
      resolve([{"id": "Q1", "label": "x"}], {}, boom=RuntimeError("connexion refusée"))["status"],
      "unavailable")
check("réponse sans résultat exploitable → not_found",
      asyncio.run(wikidata_resolve_by_name("x", now=NOW, client=FakeClient(None, {})))["status"],
      "not_found")


class BadJsonClient(FakeClient):
    """Corps de réponse illisible (JSON tronqué) : httpx lève sur .json()."""

    async def get(self, url, params=None, headers=None):
        class Bad:
            status_code = 200

            def json(self):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        return Bad()


class Http503Client(FakeClient):
    """Wikidata en panne / throttling."""

    async def get(self, url, params=None, headers=None):
        return FakeResponse({}, status_code=503)


check("JSON illisible → unavailable",
      asyncio.run(wikidata_resolve_by_name("x", now=NOW, client=BadJsonClient([], {})))["status"],
      "unavailable")
check("HTTP 503 Wikidata → unavailable",
      asyncio.run(wikidata_resolve_by_name("x", now=NOW, client=Http503Client([], {})))["status"],
      "unavailable")


async def _slow_resolve():
    class SlowClient(FakeClient):
        async def get(self, url, params=None, headers=None):
            await asyncio.sleep(0.05)
            return await super().get(url, params, headers)

    WR.RESOLVE_BUDGET_S = 0.01   # budget volontairement minuscule
    try:
        return await wikidata_resolve_by_name(
            "x", now=NOW, client=SlowClient([{"id": "Q1", "label": "x"}], {"Q1": ADJANI}))
    finally:
        WR.RESOLVE_BUDGET_S = 6.0


check("dépassement du budget → unavailable", asyncio.run(_slow_resolve())["status"], "unavailable")


# ──────────────────────────── 12. Priorité des raisons ────────────────────────────
print("\n12. Un candidat humain prime sur les homonymes non-humains")
res = resolve(
    [{"id": "Q11831704", "label": "Isabelle Adjani"}, {"id": "Q106383", "label": "Isabelle Adjani"}],
    {"Q11831704": ALBUM, "Q106383": entity(sitelinks=10)},
)
check("raison = not_notable (l'humain), pas not_human (l'album)", res.get("reason"), "not_notable")
check("statut rejected", res["status"], "rejected")

print("\n13. Le 2e candidat est retenu si le 1er échoue")
res = resolve(
    [{"id": "Q11831704", "label": "Isabelle Adjani"}, {"id": "Q106383", "label": "Isabelle Adjani"}],
    {"Q11831704": ALBUM, "Q106383": ADJANI},
)
check("statut resolved sur le 2e", res["status"], "resolved")
check("bon QID retenu", res["person"]["wikidata_id"], "Q106383")


# ──────────────────────────── 14. Plancher configurable ────────────────────────────
print("\n14. Plancher configurable (clé de config du commit 3)")
hits, ents = [{"id": "Q106383", "label": "Isabelle Adjani"}], {"Q106383": entity(sitelinks=30)}
check("30 sitelinks, plancher 45 → rejeté", resolve(hits, ents, floor=45)["status"], "rejected")
check("30 sitelinks, plancher 25 → accepté", resolve(hits, ents, floor=25)["status"], "resolved")


# ──────────── 15. Repli « ordre des mots inversé » (strictement 2 mots) ────────────
print("\n15. Repli permutation — « Adjani Isabelle » → « Isabelle Adjani »")


def resolve_named(saisie, hits_par_requete, entities=None):
    client = FakeClient(hits_par_requete, entities or {"Q106383": ADJANI})
    res = asyncio.run(wikidata_resolve_by_name(saisie, floor=45, now=NOW, client=client))
    return res, client


# Seule « Isabelle Adjani » ramène quelque chose : c'est le cas réel constaté en
# prod, où « adjani isabelle » renvoie 0 résultat chez Wikidata lui-même.
TABLE = {"Isabelle Adjani": [{"id": "Q106383", "label": "Isabelle Adjani"}]}

res, cli = resolve_named("Adjani Isabelle", TABLE)
check("2 mots inversés → resolved", res["status"], "resolved")
check("bonne personne retenue", res["person"]["wikidata_id"], "Q106383")
check("3 recherches : fr, en, puis permutation",
      cli.searches, ["Adjani Isabelle", "Adjani Isabelle", "Isabelle Adjani"])

res, cli = resolve_named("Isabelle Adjani", TABLE)
check("succès du 1er coup → resolved", res["status"], "resolved")
check("AUCUN appel supplémentaire (repli gratuit)", cli.searches, ["Isabelle Adjani"])

res, cli = resolve_named("Jean Michel Dupont", {})
check("3 mots → pas de permutation", cli.searches, ["Jean Michel Dupont"] * 2)
check("3 mots → not_found", res["status"], "not_found")

res, cli = resolve_named("Madonna", {})
check("1 mot (mononyme) → pas de permutation", cli.searches, ["Madonna"] * 2)

res, cli = resolve_named("Ali Ali", {})
check("2 mots identiques → pas de permutation", cli.searches, ["Ali Ali"] * 2)

# La permutation ne doit pas fausser le classement « libellé identique d'abord » :
# il compare désormais à la requête EFFECTIVE, pas à la saisie d'origine.
res, cli = resolve_named(
    "Adjani Isabelle",
    {"Isabelle Adjani": [{"id": "Q11831704", "label": "Autre chose"},
                         {"id": "Q106383", "label": "Isabelle Adjani"}]},
    {"Q11831704": ALBUM, "Q106383": ADJANI},
)
check("classement sur la requête effective (exact match d'abord)",
      res["person"]["wikidata_id"], "Q106383")


# ──────────────────────────── Bilan ────────────────────────────
total = results["pass"] + results["fail"]
print(f"\n{'=' * 60}")
print(f"  {results['pass']}/{total} tests OK" + (f"  — {results['fail']} ÉCHEC(S)" if results["fail"] else ""))
print(f"{'=' * 60}")
raise SystemExit(1 if results["fail"] else 0)
