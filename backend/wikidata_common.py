"""
Socle Wikidata PARTAGÉ — tables de décision et calculs communs à l'import des 608
(fetch_wikidata.py + import_wikidata.py) et, à venir, à l'ajout à la demande par nom
(endpoint POST /api/people/from-wikipedia).

RAISON D'ÊTRE : ces règles définissent qui entre dans la base et avec quel indice
de départ. Elles étaient prisonnières de deux scripts CLI, donc inaccessibles au
serveur. Les dupliquer aurait fait diverger l'ajout à la demande de l'import des
608 au premier ajustement — c'est exactement ce qu'on veut éviter, l'exigence
étant « MÊMES GARDE-FOUS ».

Extraction PURE : code déplacé sans la moindre modification de comportement.
  • PRIO, CAT, cat_of            ← fetch_wikidata.py
  • SITELINKS_REF, provisional_score, age_from_birth  ← import_wikidata.py
  • DEFAULT_SITELINKS_FLOOR      ← fetch_wikidata.FLOOR

100 % stdlib, aucun accès réseau ni base : importable depuis server.py sans effet
de bord (les deux scripts gardent leur main() sous `if __name__ == "__main__"`).

NOTE sur age_from_birth : la fonction dit seulement si l'âge est CONNU et lequel.
La POLITIQUE (que faire d'un âge inconnu) appartient à l'appelant, et elle diffère
volontairement : l'import des 608 inclut les âges inconnus, l'ajout à la demande
les REJETTE (chemin public, sécurité mineurs). Ne pas déplacer cette décision ici.
"""
import math
import re

# ── Plancher de notoriété (nombre de sitelinks Wikidata) ──
# Défaut historique de l'import des 608. L'ajout à la demande lira une clé de
# config (wikidata_ondemand_sitelinks_floor) qui retombe sur cette valeur.
DEFAULT_SITELINKS_FLOOR = 45

# ── Référence de l'échelle log de l'indice provisoire ──
SITELINKS_REF = 300      # réf pour l'échelle log (max Wikidata figures majeures)

# ── Ordre de priorité des catégories (perception populaire) ──
PRIO = ["politics", "sport", "influencer", "culture", "business", "other"]

# ── P106 (occupation) → catégorie Popularoo ──
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


def provisional_score(sitelinks: int) -> float:
    if sitelinks <= 0:
        return 0.0
    val = math.log10(sitelinks + 1) / math.log10(SITELINKS_REF) * 100.0
    return round(min(100.0, max(0.0, val)), 1)


def age_from_birth(birth_iso, now):
    """Renvoie (age|None, known:bool). Gère les dates ISO Wikidata et l'année seule."""
    if not birth_iso:
        return None, False
    m = re.match(r"^-?(\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?", birth_iso.lstrip("+"))
    if not m:
        return None, False
    if birth_iso.startswith("-"):
        return 999, True  # BCE → adulte évident
    y = int(m.group(1))
    mo = int(m.group(2) or 7)
    d = int(m.group(3) or 1)
    age = now.year - y - (1 if (now.month, now.day) < (mo, d) else 0)
    return age, True
