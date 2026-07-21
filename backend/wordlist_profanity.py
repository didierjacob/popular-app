"""
Wordlist de modération (FR + EN) — insultes / haine / termes sexuels.
Utilisée par le filtre auto de création de Personnalités (candidate_detection).

⚠️ DISTINCTE de BLACKLISTED_DESCRIPTION_WORDS (candidate_detection) qui vise les
faits divers dans les DESCRIPTIONS. Ici on filtre le NOM saisi par l'utilisateur.

Matching : tokens à frontière de mot (anti-Scunthorpe — "con" ne matche pas
"Concha"), + sous-chaîne pour les expressions multi-mots. Le texte est normalisé
(accents retirés, minuscules) avant comparaison, comme name_normalized.

Principe : ce n'est qu'un PREMIER tri, en amont d'une modération admin qui attrape
le reste avant toute publication. En cas de doute sur un terme (collision possible
avec un vrai nom propre), on le RETIRE — mieux vaut trop permissif que bloquer un
vrai contributeur. Termes retirés pour cette raison : dick, coon, paki, fag, negre,
nazi, cretin(e), mongol, pd, kike, chink.

TODO (durcissement, Lot C) : élargir la section slurs depuis un lexique maintenu,
gérer le leetspeak (0→o, 3→e, @→a) et les répétitions (connnnard).
"""
import re
from unidecode import unidecode

# Insultes courantes — un seul mot (comparaison token = token, jamais un vrai nom)
PROFANITY_TERMS = {
    # FR
    "connard", "connasse", "salope", "salopard", "encule", "enculee", "pute",
    "putain", "batard", "batarde", "abruti", "abrutie", "debile",
    "tapette", "gouine", "bougnoule", "youpin", "pedale", "trisomique",
    "attarde", "attardee",
    # EN
    "fuck", "fucker", "motherfucker", "asshole", "bitch", "bastard", "slut",
    "whore", "cunt", "faggot", "nigger", "nigga", "retard", "retarded",
    "spastic", "tranny", "wetback", "rapist", "pedophile", "pedo",
}

# Expressions multi-mots — comparaison en sous-chaîne
PROFANITY_PHRASES = {
    "fils de pute", "son of a bitch", "sale race", "go kill yourself",
    "kill yourself", "child porn", "porno enfant",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def contains_profanity(text: str) -> bool:
    """True si `text` contient une insulte/terme haineux. Best-effort, non exhaustif.
    Normalise le texte (unidecode + lower) puis :
      - match token exact pour PROFANITY_TERMS (évite le problème Scunthorpe) ;
      - match sous-chaîne pour PROFANITY_PHRASES (expressions multi-mots).
    """
    if not text:
        return False
    norm = unidecode(text).lower()
    tokens = set(_TOKEN_RE.findall(norm))
    if tokens & PROFANITY_TERMS:
        return True
    return any(phrase in norm for phrase in PROFANITY_PHRASES)
