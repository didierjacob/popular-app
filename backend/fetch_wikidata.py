"""
Étape 2 (import Wikidata) — FETCH : sélection top-K/pays via SPARQL, READ-ONLY (Wikidata).

⚠️  N'ÉCRIT RIEN DANS MONGO. Interroge query.wikidata.org (endpoint public) et écrit
    un fichier LOCAL `wikidata_candidates.json` (consommé ensuite par import_wikidata.py).

Stratégie (validée par calibration 2026-07-23) :
  • Sélection PAR PAYS (P27) = diversité nationale native (le tri global sitelinks
    est infaisable sur WDQS → timeouts). Top-K par nation.
  • Panel de 23 nations, tous continents (extensible).
  • Vivants uniquement (FILTER NOT EXISTS P570).
  • Plancher de notoriété : sitelinks >= FLOOR (qualité > quota : moins que K là où
    la notoriété décroche).
  • Catégorie via occupation P106 (priorité politics>sport>influencer>culture>business).
    Les fiches "other" (académiques/juristes/etc.) sont EXCLUES.
  • Récupère aussi P569 (date de naissance) pour le filtre mineur (fait à l'import).

Réglages en tête de fichier (K, FLOOR, PANEL). Rate-limit + retry/backoff.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python fetch_wikidata.py            # écrit wikidata_candidates.json
"""
import json
import os
import time
import urllib.parse
import urllib.request

UA = "PopularooImport/1.0 (didier@coffeeandfilms.com)"
SPARQL = "https://query.wikidata.org/sparql"

TOPK = 20          # top-K par pays
FLOOR = 45         # plancher de notoriété (sitelinks)

# Panel de 23 nations (tous continents). QID de citoyenneté P27.
PANEL = {
    "FR": "Q142", "UK": "Q145", "DE": "Q183", "IT": "Q38", "ES": "Q29", "RU": "Q159",
    "US": "Q30", "BR": "Q155", "MX": "Q96", "CA": "Q16", "AR": "Q414",
    "IN": "Q668", "CN": "Q148", "JP": "Q17", "KR": "Q884", "ID": "Q252",
    "TR": "Q43", "IR": "Q794", "EG": "Q79",
    "NG": "Q1033", "ZA": "Q258", "MA": "Q1028", "AU": "Q408",
}

PRIO = ["politics", "sport", "influencer", "culture", "business", "other"]

# Mapping occupation P106 (QID) → catégorie app. Élargi au-delà du top-50 observé ;
# les occupations inconnues → non mappées (comptées "unmapped", n'apportent pas de
# catégorie). Une personne sans AUCUNE catégorie réelle → "other" → EXCLUE.
CAT = {
    # sport
    "Q937857": "sport", "Q628099": "sport", "Q10833314": "sport", "Q2066131": "sport",
    "Q3665646": "sport", "Q11338576": "sport", "Q10843402": "sport", "Q19204627": "sport",
    "Q11774891": "sport", "Q13381863": "sport", "Q12299841": "sport", "Q10841764": "sport",
    "Q2309784": "sport", "Q13141064": "sport", "Q11513337": "sport", "Q18515558": "sport",
    # politics
    "Q82955": "politics", "Q193391": "politics", "Q2285706": "politics", "Q83307": "politics",
    "Q30461": "politics", "Q48352": "politics", "Q372436": "politics", "Q116": "politics",
    "Q212238": "politics", "Q1084784": "politics", "Q4164871": "politics",
    # business
    "Q43845": "business", "Q131524": "business", "Q484876": "business", "Q806798": "business",
    "Q12362622": "business",
    # culture
    "Q33999": "culture", "Q10800557": "culture", "Q177220": "culture", "Q10798782": "culture",
    "Q36180": "culture", "Q3282637": "culture", "Q2526255": "culture", "Q4610556": "culture",
    "Q639669": "culture", "Q28389": "culture", "Q36834": "culture", "Q2405480": "culture",
    "Q753110": "culture", "Q2259451": "culture", "Q3455803": "culture", "Q578109": "culture",
    "Q1930187": "culture", "Q55960555": "culture", "Q488205": "culture", "Q183945": "culture",
    "Q5716684": "culture", "Q6625963": "culture", "Q947873": "culture", "Q482980": "culture",
    "Q855091": "culture", "Q18814623": "culture", "Q69423232": "culture", "Q1028181": "culture",
    "Q47541952": "culture", "Q49757": "culture", "Q245068": "culture", "Q11774202": "culture",
    "Q158852": "culture", "Q214917": "culture", "Q33231": "culture", "Q1281618": "culture",
    "Q483501": "culture", "Q2643890": "culture", "Q177467": "culture", "Q486748": "culture",
    "Q3357567": "culture", "Q266569": "culture", "Q15980158": "culture", "Q2914170": "culture",
    # influencer
    "Q17125263": "influencer", "Q2882257": "influencer", "Q108460070": "influencer",
    # other (académiques / droit / science → EXCLUS à l'import)
    "Q1622272": "other", "Q40348": "other", "Q188094": "other", "Q185351": "other",
    "Q81096": "other", "Q82594": "other", "Q169470": "other", "Q901": "other",
    "Q170790": "other", "Q593644": "other", "Q205375": "other",
}


def cat_of(occ_qids):
    cats = {CAT[o] for o in occ_qids if o in CAT}
    for c in PRIO:
        if c in cats:
            return c
    return "other"


def run(query, timeout=110, retries=4):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            last = e
            time.sleep(4 * (i + 1))
    raise last


def fetch_country(qid):
    q = f"""SELECT ?p ?pLabel (MAX(?sl) AS ?sitelinks) (SAMPLE(?birth) AS ?birthDate)
       (GROUP_CONCAT(DISTINCT ?occ; separator="|") AS ?occs) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P27 wd:{qid} ; wikibase:sitelinks ?sl .
  FILTER NOT EXISTS {{ ?p wdt:P570 ?d }}
  OPTIONAL {{ ?p wdt:P569 ?birth }}
  OPTIONAL {{ ?p wdt:P106 ?occ }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}} GROUP BY ?p ?pLabel ORDER BY DESC(?sitelinks) LIMIT {TOPK}"""
    rows = run(q)
    out = []
    for x in rows:
        qid_p = x["p"]["value"].rsplit("/", 1)[-1]
        label = x.get("pLabel", {}).get("value", "")
        # Si le label est resté le QID (pas de libellé FR/EN), on ignore la fiche.
        if not label or label == qid_p:
            continue
        occs = [o.rsplit("/", 1)[-1] for o in x["occs"]["value"].split("|") if o] if x.get("occs", {}).get("value") else []
        out.append({
            "wikidata_id": qid_p,
            "name": label,
            "sitelinks": int(x["sitelinks"]["value"]),
            "birth": x.get("birthDate", {}).get("value"),  # ISO string or None
            "occs": occs,
        })
    return out


def main():
    seen = {}      # wikidata_id -> record (dédup inter-pays : 1re nationalité gagne)
    per_country_kept = {}
    excluded_other = 0
    excluded_floor = 0

    for cc, qid in PANEL.items():
        try:
            rows = fetch_country(qid)
        except Exception as e:
            print(f"  {cc} ({qid}) ERREUR: {e}")
            continue
        kept = 0
        for r in rows:
            if r["sitelinks"] < FLOOR:
                excluded_floor += 1
                continue
            category = cat_of(r["occs"])
            if category == "other":
                excluded_other += 1
                continue
            if r["wikidata_id"] in seen:
                continue
            r["category"] = category
            r["country"] = cc
            del r["occs"]
            seen[r["wikidata_id"]] = r
            kept += 1
        per_country_kept[cc] = kept
        print(f"  {cc}: retenus={kept}")
        time.sleep(1.5)

    records = list(seen.values())
    out_path = "wikidata_candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"topk": TOPK, "floor": FLOOR, "panel": list(PANEL.keys()),
                   "records": records}, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"  Candidats uniques retenus : {len(records)}")
    print(f"  Exclus (< plancher {FLOOR}) : {excluded_floor}")
    print(f"  Exclus (catégorie 'other') : {excluded_other}")
    print(f"  Par pays : " + "  ".join(f"{cc}={n}" for cc, n in per_country_kept.items()))
    print(f"\n📄 Écrit dans ./{out_path} (fichier local, aucune écriture Mongo).")


if __name__ == "__main__":
    main()
