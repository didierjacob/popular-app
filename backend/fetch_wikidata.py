"""
Étape 2 (import Wikidata) — FETCH robuste : sélection top-K/pays via SPARQL, READ-ONLY.

⚠️  N'ÉCRIT RIEN DANS MONGO. Interroge query.wikidata.org (endpoint public) et écrit
    un fichier LOCAL `wikidata_candidates.json` (consommé ensuite par import_wikidata.py).

Stratégie robuste (2 requêtes LÉGÈRES par pays, pour éviter les 504 de WDQS) :
  • Requête A (cheap, index sitelinks) : top-K QID par pays.
      ?p wdt:P31 wd:Q5 ; wdt:P27 wd:<pays> ; wikibase:sitelinks ?sl .
      FILTER NOT EXISTS { ?p wdt:P570 ?d } ORDER BY DESC(?sl) LIMIT K
      → uniquement QID + sitelinks (aucun OPTIONAL, aucun GROUP BY).
  • Requête B (détails) : pour les QID collectés, par lots via VALUES ?p {...} :
      labels FR/EN + P106 (occupations) + P569 (naissance).

  Vivants uniquement (P570 exclu en A). Plancher sitelinks >= FLOOR. Catégorie via
  P106 (priorité politics>sport>influencer>culture>business) ; "other" EXCLU.
  User-Agent explicite, timeout par requête, RETRY backoff sur 504/timeout, pause
  entre pays.

Réglages : TOPK, FLOOR, PANEL, BATCH_B en tête de fichier.

Usage (Render Shell) :
    cd /opt/render/project/src/backend
    python fetch_wikidata.py            # écrit wikidata_candidates.json
"""
import json
import time
import urllib.parse
import urllib.request

UA = "PopularooImport/1.0 (didier@coffeeandfilms.com)"
SPARQL = "https://query.wikidata.org/sparql"

TOPK = 20          # top-K par pays (requête A)
FLOOR = 45         # plancher de notoriété (sitelinks)
BATCH_B = 50       # taille des lots VALUES (requête B)

PANEL = {
    "FR": "Q142", "UK": "Q145", "DE": "Q183", "IT": "Q38", "ES": "Q29", "RU": "Q159",
    "US": "Q30", "BR": "Q155", "MX": "Q96", "CA": "Q16", "AR": "Q414",
    "IN": "Q668", "CN": "Q148", "JP": "Q17", "KR": "Q884", "ID": "Q252",
    "TR": "Q43", "IR": "Q794", "EG": "Q79",
    "NG": "Q1033", "ZA": "Q258", "MA": "Q1028", "AU": "Q408",
}

PRIO = ["politics", "sport", "influencer", "culture", "business", "other"]

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


def run(query, timeout=90, retries=4):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:
            last = e
            wait = 4 * (i + 1)
            print(f"      retry {i+1}/{retries} après {wait}s ({e})")
            time.sleep(wait)
    raise last


# ── Requête A : top-K QID + sitelinks pour un pays (cheap) ──
def fetch_country_qids(qid):
    q = f"""SELECT ?p ?sl WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P27 wd:{qid} ; wikibase:sitelinks ?sl .
  FILTER NOT EXISTS {{ ?p wdt:P570 ?d }}
}} ORDER BY DESC(?sl) LIMIT {TOPK}"""
    rows = run(q)
    return [(x["p"]["value"].rsplit("/", 1)[-1], int(x["sl"]["value"])) for x in rows]


# ── Requête B : détails (label + occs + naissance) pour un lot de QID via VALUES ──
def fetch_details(qids):
    values = " ".join(f"wd:{q}" for q in qids)
    q = f"""SELECT ?p ?pLabel (GROUP_CONCAT(DISTINCT ?occ; separator="|") AS ?occs)
       (SAMPLE(?birth) AS ?birthDate) WHERE {{
  VALUES ?p {{ {values} }}
  OPTIONAL {{ ?p wdt:P106 ?occ }}
  OPTIONAL {{ ?p wdt:P569 ?birth }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "fr,en". }}
}} GROUP BY ?p ?pLabel"""
    rows = run(q)
    out = {}
    for x in rows:
        qid_p = x["p"]["value"].rsplit("/", 1)[-1]
        label = x.get("pLabel", {}).get("value", "")
        occs = [o.rsplit("/", 1)[-1] for o in x["occs"]["value"].split("|") if o] if x.get("occs", {}).get("value") else []
        out[qid_p] = {"name": label, "occs": occs, "birth": x.get("birthDate", {}).get("value")}
    return out


def main():
    # ── Étape 1 : QID par pays (dédup inter-pays : 1re nationalité gagne) ──
    assigned = {}   # qid -> {"sitelinks", "country"}
    per_country_raw = {}
    for cc, qid in PANEL.items():
        try:
            pairs = fetch_country_qids(qid)
        except Exception as e:
            print(f"  {cc} ({qid}) A ÉCHEC: {e}")
            per_country_raw[cc] = 0
            continue
        n = 0
        for q, sl in pairs:
            if sl < FLOOR:
                continue
            if q in assigned:
                continue
            assigned[q] = {"sitelinks": sl, "country": cc}
            n += 1
        per_country_raw[cc] = n
        print(f"  {cc}: {n} QID (>= plancher {FLOOR})")
        time.sleep(1.5)

    qids = list(assigned.keys())
    print(f"\n  {len(qids)} QID uniques à détailler (requête B, lots de {BATCH_B})...")

    # ── Étape 2 : détails par lots ──
    details = {}
    for i in range(0, len(qids), BATCH_B):
        chunk = qids[i:i + BATCH_B]
        try:
            details.update(fetch_details(chunk))
        except Exception as e:
            print(f"    lot B {i//BATCH_B + 1} ÉCHEC: {e}")
        print(f"    lot B {i//BATCH_B + 1}/{(len(qids)+BATCH_B-1)//BATCH_B} ok ({len(details)} détaillés)")
        time.sleep(1.5)

    # ── Assemblage + filtre catégorie ──
    records = []
    excluded_other = 0
    no_label = 0
    for q, meta in assigned.items():
        det = details.get(q)
        if not det or not det["name"] or det["name"] == q:
            no_label += 1
            continue
        category = cat_of(det["occs"])
        if category == "other":
            excluded_other += 1
            continue
        records.append({
            "wikidata_id": q,
            "name": det["name"],
            "sitelinks": meta["sitelinks"],
            "birth": det["birth"],
            "category": category,
            "country": meta["country"],
        })

    out_path = "wikidata_candidates.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"topk": TOPK, "floor": FLOOR, "panel": list(PANEL.keys()),
                   "records": records}, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"  Candidats retenus          : {len(records)}")
    print(f"  Exclus (catégorie 'other') : {excluded_other}")
    print(f"  Ignorés (sans libellé)     : {no_label}")
    print(f"  Par pays (QID >= plancher) : " + "  ".join(f"{cc}={n}" for cc, n in per_country_raw.items()))
    print(f"\n📄 Écrit dans ./{out_path} (fichier local, aucune écriture Mongo).")


if __name__ == "__main__":
    main()
