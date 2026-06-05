# Popularoo — Document de passation pour Claude Code

**Date de rédaction :** 14 mai 2026
**Rédigé par :** Claude (conversation Anthropic) pour le compte de Didier Jacob
**Destinataire :** Claude Code (agent suivant)
**Statut projet :** ~75% du chemin technique, cible App Store début juin 2026

---

## 1. Contexte projet et acteurs

### Qui est l'utilisateur

**Didier Jacob**, fondateur de l'app Popularoo.
Société : SARL **EN HAUT DES MARCHES** (récemment migrée depuis un compte Apple Developer Individual).

**Profil technique :** Didier **ne code pas**. Il pilote le projet en tant que créateur produit. Il a besoin :
- D'explications **claires sans jargon technique**, avec des analogies concrètes
- De **suggestions inventives** sur les décisions produit
- De procédures **pas à pas** quand il doit exécuter quelque chose sur son Mac
- D'une **pédagogie active** : expliquer pourquoi avant le quoi

**Style de travail :** Didier réfléchit produit, valide stratégie, exécute techniquement seulement ce qui est strictement nécessaire (Terminal pour curl ou commandes EAS).

### Méthode de travail établie

Le projet a été développé via **Emergent** (agent IA de dev autonome) pendant environ 3 semaines. L'agent code dans sa preview locale, Didier clique "Save to GitHub" pour pousser, Render redéploie automatiquement le backend, puis Didier rebuild l'app via EAS pour TestFlight.

**Pendant ces 3 semaines, un Claude Anthropic conversationnel (moi) a accompagné Didier comme :**
- **Relecteur stratégique** : analyse au crible des retours d'Emergent avant validation
- **Rédacteur de briefs** : préparation des messages à copier-coller à Emergent (toujours avec scope serré, plan demandé avant code, garde-fous explicites)
- **Pédagogue** : traduction du jargon technique, analogies, recul produit
- **Coach de procédure** : guide Terminal commande par commande

Vous (Claude Code) reprenez ce rôle, mais avec un avantage décisif : **vous lisez et modifiez le code directement**, pas via un intermédiaire qui code aveugle dans une preview désynchronisée.

### Limites connues d'Emergent qui expliquent la bascule vers vous

1. **Code par hypothèse plutôt que diagnostic** : il faut le pousser plusieurs fois pour qu'il aille au bout d'un debug (a fallu 7 builds successifs pour résoudre Sentry)
2. **Teste souvent sur sa preview locale au lieu de la production réelle** : on a découvert plusieurs fois que sa "validation locale" ne reflétait pas l'état réel sur Render
3. **Manque de continuité** : à chaque session, redémarre parfois en perdant le contexte
4. **Scope creep** : tendance à ajouter des éléments non demandés ("Brevo SMTP" introduit sans justification, `recalculate-all-pi` glissé en backlog)

---

## 2. Architecture technique

### Stack complète

| Couche | Technologie | Localisation |
|---|---|---|
| Backend API | Python / FastAPI | `server.py` (6500+ lignes) — un seul fichier monolithique |
| Hébergement backend | Render | `popular-app.onrender.com` |
| Base de données | MongoDB Atlas | Connexion via variable d'env sur Render |
| Frontend mobile | React Native / Expo | dossier `frontend/` |
| Build mobile | EAS Build (Expo) | profile `preview` pour TestFlight |
| Distribution | TestFlight → App Store | iOS uniquement en V1 |
| Monitoring | Sentry | SDK JS actif, plugin de build retiré (DSN européen RGPD) |
| Email transactionnel | Brevo SMTP | introduit par Emergent, non encore exhaustivement testé |
| Repository | GitHub | `didierjacob/popular-app`, branche `main` |

### Workflow de déploiement

```
Code modifié dans Claude Code
    ↓
git add + git commit + git push origin main
    ↓
Render détecte le push → redéploie automatiquement le backend (2-3 min)
    ↓ (en parallèle pour le frontend)
npx eas build --platform ios --profile preview (25-35 min cloud)
    ↓
Lien EAS reçu → installation TestFlight sur iPhone Didier
    ↓
Test physique
```

**Note importante :** les modifications backend sont effectives **dès le redéploiement Render** (2-3 min) sans rebuild EAS. Seules les modifications frontend nécessitent un rebuild EAS.

### Structure du projet

```
~/Desktop/popularoo/
├── server.py                  # Backend FastAPI monolithique
├── candidate_detection.py     # Module helper pour détection candidats Wikipedia
├── external_scores.py         # Module helper pour scoring Wikipedia
├── frontend/
│   ├── app/                   # Écrans Expo Router
│   │   ├── (tabs)/
│   │   │   ├── index.tsx      # Home (50 personnalités + Outsider du jour)
│   │   │   ├── list.tsx       # Classement complet
│   │   │   ├── outsiders.tsx  # Page Outsiders
│   │   │   └── account.tsx    # Compte (948 lignes — gros fichier)
│   │   ├── person.tsx         # Page Personnalité (PI affiché L650, L524, L571)
│   │   ├── booster.tsx        # Formulaire achat Booster
│   │   ├── dailyrun.tsx       # MASQUÉ en V1 (UI cachée, backend conservé)
│   │   └── _layout.tsx        # Layout racine (init Sentry SDK)
│   ├── locales/               # Traductions FR EN DE ES IT PT-BR
│   ├── eas.json               # Config EAS Build
│   ├── app.json               # Config Expo
│   ├── package.json
│   └── package-lock.json      # ⚠ git checkout obligatoire avant pull (régulièrement modifié localement)
└── (autres fichiers admin / docs)
```

### Endpoints API critiques (server.py)

**Endpoints publics :**
- `GET /api/people?query=&limit=300` → liste personnalités, **filtre `visible_in_rankings: {"$ne": False}`** (ligne 949)
- `GET /api/search?query=` → recherche fuzzy, **PAS de filtre `visible_in_rankings`** (ligne 1676, commentaire ajouté en Vague 2.5)
- `POST /api/create-from-search` → création synchrone d'une nouvelle célébrité via search
- `POST /api/vote` → enregistrement d'un vote (like/dislike pour célébrité, like/superlike pour Outsider)

**Endpoints admin (protégés par header `X-Admin-Password`) :**
- `POST /api/admin/recalculate-all-pi` → recalcule tous les PI (à utiliser après changement de formule globale)
- `POST /api/admin/recalculate-all-indices` → recalcule tous les indices blended (α × ext + (1-α) × votes)
- `POST /api/admin/get-alpha` → lit la valeur actuelle de α (actuellement 1.0 = 100% Wikipedia)
- `POST /api/admin/update-person-category-batch` → mise à jour catégorie en batch
- `POST /api/admin/delete-persons-batch` → suppression en batch
- `POST /api/admin/fix-visible-user-search` → migration profils user_search vers `visible_in_rankings: true` (créé en Vague 2.5)
- Plusieurs autres endpoints d'audit, batch rename, etc.

### Modèle de données MongoDB

**Collection `persons` (258 documents en production) :**

```javascript
{
  "_id": ObjectId,
  "id": "string ID hex",
  "name": "Nom Prénom",
  "category": "culture" | "sport" | "politics" | "business" | "influencer" | "other" | "outsider",
  "approved": true | false,           // doit être true pour apparaître publiquement
  "suspended": false,                  // anti-spam
  "visible_in_rankings": true | false, // contrôle apparition dans /api/people
  "is_deceased": false,                // filtre décédés
  "source": "seed" | "user_search" | "user_search_confirmed" | "self_boosted" | "unknown",
  "score": 0-100,                      // PI final affiché (popularoo_index)
  "popularoo_index": 0-100,            // identique à score (résultat de la formule blended)
  "popularity_external_score": 0-100,  // score Wikipedia normalisé (ext_score)
  "wiki_score_norm": 0-100,            // normalisé pour la formule
  "wiki_score_brut": float,            // brut (somme pageviews etc.)
  "last_external_update": "ISO date",
  "likes": int,
  "dislikes": int,
  "superlikes": int,                   // uniquement pour Outsiders
  "total_votes": int,
  "active_strikes": int,               // V2, en réserve
  "strike_emoji": null,
  "strike_label": null,
  "is_trending": false,
  "country_tags": ["FR", "US", ...],
  "is_international": bool,
  "primary_country": "FR" | ...,
  "social_links": { instagram, x, tiktok } | null,
  "avatar_initials": "DD",
  "avatar_color": "#hex",
  "last_updated": "ISO date"
}
```

**Autres collections :** `app_settings` (configuration globale dont `cas1_celebrities` éditoriale), `votes_log`, `outsiders_signals`, `deceased_queue`, `audit_log`, `blocklist`.

---

## 3. Logique métier

### Concept central : Popularoo Index (PI)

Le PI est un score de 0 à 100 affiché sur chaque profil. Il représente la popularité globale d'une personnalité ou d'un Outsider.

**Formule blended avec coefficient α :**

```
popularoo_index = α × popularity_external_score + (1 - α) × votes_score
```

- `popularity_external_score` : calculé depuis Wikipedia (multi-langues + pageviews + Wikidata)
- `votes_score` : calculé depuis les votes utilisateurs réels
- `α` (alpha) : actuellement **1.0** (100% Wikipedia au lancement, car peu d'utilisateurs → votes non significatifs)

Au fil des mois, α descendra progressivement vers 0.5 puis 0.3 quand l'app aura suffisamment d'utilisateurs pour que les votes deviennent significatifs.

### Les 2 types d'entités

**Personnalités (célébrités confirmées)**
- Sources : `seed` (peuplement initial), `user_search_confirmed` (créées via recherche utilisateur + endpoint synchrone), `user_search` (créées via recherche utilisateur + background task)
- Catégories : `culture`, `sport`, `politics`, `business`, `influencer`, `other`
- Votes acceptés : **Like** ou **Dislike** (symétrique)
- PI : calculé selon la formule blended, peut monter jusqu'à 100
- Aspect : page Personnalité avec PI central, compteur likes/dislikes, activité en direct

**Outsiders (utilisateurs payants)**
- Source : `self_boosted` (paiement Booster IAP) ou seed historique avec `category: "outsider"`
- Votes acceptés : **Like** ou **Superlike** (jamais Dislike — le Dislike Outsider a été supprimé définitivement)
- PI : **plafonné à 25 maximum** (correction du 14 mai 2026 — à confirmer dans le code, ligne à identifier)
- Aspect : carte Outsider dans la page Outsiders + cadre "Outsider du jour" sur la Home

### Les 3 Boosters IAP

| Produit | Prix | Durée |
|---|---|---|
| Booster | 0,99 € | 1 heure |
| Super Booster | 9,99 € | 24 heures |
| Golden Booster | 49,99 € | 1 semaine |

**Mécanique :** un utilisateur achète un Booster, remplit un formulaire (nom + compte social Instagram/X/TikTok optionnel), devient un Outsider visible pendant la durée du Booster.

### Vagues de développement (livrées)

**Vague 1 (livrée) — 3 tiers de crédibilité pour les votes virtuels seed**

Quand on peuple la base avec des seeds (au lancement), chaque profil reçoit une dotation initiale de votes virtuels pour qu'il ne soit pas à zéro. Cette dotation varie selon le tier de notoriété :
- **Cas 1** : célébrités absolues (Trump, Cristiano Ronaldo) → votes massifs simulés
- **Cas 2** : célébrités confirmées → votes modérés
- **Cas 3** : célébrités locales/secondaires → votes faibles

La liste éditoriale Cas 1 est stockée dans `app_settings.cas1_celebrities` et modifiable via panel admin.

**Vague 2 (livrée) — Recherche → création visible + macaron contributeur**

L'utilisateur tape un nom dans le search. Si le nom n'existe pas en base, deux mécanismes :
1. **Background task asynchrone** (`/api/search`) : déclenche en arrière-plan le pipeline Wikipedia/Wikidata, crée le profil avec `source: "user_search"`
2. **Endpoint synchrone** (`/api/create-from-search`) : créé via clic explicite sur "Créer cette fiche" depuis le modal, `source: "user_search_confirmed"`

Le profil créé reçoit un macaron "contributeur" indiquant qui l'a ajouté.

**Vague 2.5 (en cours de clôture — 14 mai soir) — Corrections finales**

- **Correction A** : bug d'affichage du PI (utilisait `score` au lieu de `popularoo_index || score`). Corrigée dans `person.tsx` L650, L524, L571 + `index.tsx` L717.
- **Correction B** : scoring de confiance Wikipedia pour filtrer les nouveaux entrants. Seuil **65**, formule :
  - FR wiki : +30
  - EN wiki : +25
  - Wikidata humain (Q5) : +20
  - Vivant : +10
  - Pageviews FR >1000 : +15 (>200 : +8)
  - Pageviews EN >500 : +10 (>100 : +5)
  - 3+ langues : +20
  - **≥65** → création / **30-64** → refus bienveillant / **<30** → refus
  - Pipeline série : `is_human` → `is_deceased` → `confidence_score`
- **Fix asymétrie /api/search vs /api/people** : la background task créait avec `visible_in_rankings: False`, rendant les profils invisibles dans `/api/people`. Modifié à `True` ligne 1875 (après validation du scoring ≥65). Endpoint admin `fix-visible-user-search` créé pour migrer les profils existants (4 migrés : Florence Pugh, John Travolta, Juliette Binoche, Charlotte Cardin).
- **Plafond PI Outsider à 25** : fix en cours d'implémentation par Emergent au moment de la rédaction de ce document. À vérifier que c'est bien poussé en production avant de commencer la suite.

---

## 4. Décisions produit verrouillées

### Charte graphique
- **Background** : `#0F2F22` (vert sombre profond)
- **Accent** : doré (le P de l'icône)
- **Pas d'emojis** dans la charte, typographie pure
- **Animations** : glow pulsant Trending fort, chute libre Trending baisse
- **Splash screen** : icône au centre, grossit jusqu'à ce que le P doré déborde, 2 secondes total, fondu vers Home

### Langues supportées
6 langues : **FR EN DE ES IT PT-BR**. Toute nouvelle chaîne doit être traduite dans les 6.

### Conformité juridique
- CGU V2.1, Privacy V2.0, Mentions légales : **en ligne en FR + EN**
- Statut hébergeur LCEN/DSA revendiqué
- Âge minimum **16 ans**
- Clause liens externes (article XX) pour les comptes sociaux d'Outsiders
- Sentry DSN européen (RGPD-friendly)

### Catégories de personnalités
6 catégories : `culture`, `sport`, `politics`, `business`, `influencer`, `other`. La catégorisation auto via Wikipedia mappe vers ces 6 buckets.

### Daily Run et Strikes
- **Daily Run** : UI **masquée en V1**, backend conservé intact pour réactivation V2
- **Strikes** (Flash, Diversité, Série) : backend conservé, UI désactivée en V1

### Comportement de vote
- **1 vote par utilisateur par célébrité par 24h** (limite par Device ID local)
- Message d'attente : "Vous pourrez revoter dans 24h" (à corriger pour ajouter les accents FR si pas déjà fait)
- Live activity feed sur les pages Personnalité (rapide) et Outsider (ralenti à 1-2 min en V1 pour cohérence avec faible volume)

---

## 5. Roadmap restante jusqu'à App Store

### Vague 3 — Mouvements de classement + Performance (4-7h)

**Mouvements de classement plus visibles**
- Sur `list.tsx`, animation flash vert (montée) / flash rouge (descente) quand une personnalité change de position
- Mini ALGO A pour mouvements progressifs Top 100 (basé sur les seeds, simulé tant qu'il y a peu d'utilisateurs)
- Calibrer le rythme (ni hyperactif ni mort)

**Performance lancement**
- Cache `stale-while-revalidate` sur `/api/people` côté frontend
- Prefetch pendant le splash screen 2s
- **Plan payant Render à 7$/mois** : à activer pour gagner en CPU/RAM (le plan free met l'app en sommeil après 15 min d'inactivité, causant 30-60s de cold start)
- Mesurer le temps de lancement avant/après

### Vague 4 — Validation différée 24h (8-12h)

**Vision produit de Didier (verrouillée le 14 mai 2026) :**

Au lieu du flow actuel "search → modal → clic Créer → fiche immédiate", on bascule sur un flow asynchrone élégant :

1. L'utilisateur tape un nouveau nom dans le search
2. Si le nom n'existe pas : message immédiat **"Votre vote sera pris en compte sous 24h"**
3. **En arrière-plan, vérification approfondie multi-sources** :
   - Wikipedia FR/EN/DE/ES/IT/PT-BR fuzzy (pas matching exact)
   - Wikidata SearchEntities (plus tolérant aux variantes de nom)
   - Wikipedia disambiguation pages
   - Recherche sur réseaux sociaux pour valider compte vivant (optionnel V2)
4. **Si validation OK** :
   - Création silencieuse avec **40 votes simulés** distribution **70% likes / 30% dislikes**
   - **PI initial entre 25 et 40, calculé selon le score Wikipedia** (Cassel à ~38, Cardin à ~28, hiérarchie naturelle)
   - Notification push iOS à l'utilisateur : "✅ Votre nouvelle célébrité est en ligne"
   - Le vote initial de l'utilisateur est appliqué
5. **Si validation KO** :
   - Message bienveillant : "Cette personnalité n'a pas pu être ajoutée"
   - Notification push optionnelle
   - Profil non créé

**Avantages de cette refonte :**
- Pas de friction modal "Créer cette fiche"
- Pas de bug de race condition (déjà rencontré en Vague 2.5)
- Hiérarchie PI claire : Outsiders ≤ 25 / Nouveaux entrants 25-40 / Célébrités confirmées sans plafond
- Modération admin possible pendant les 24h
- Architecture solide pour la suite (auto-ingestion future, etc.)

**Composants techniques attendus :**
- File de validation `pending_creations` (collection MongoDB)
- Job APScheduler qui dépile la file toutes les 30 min
- Endpoint admin pour validation manuelle pré-publication
- Notifications push iOS (Expo Push Notifications API)
- Recherche fuzzy + sources multiples dans `external_scores.py`
- Distribution votes simulés avec randomisation contrôlée

### Lot 4 — Frontend panel admin enrichi (4-6h)

**Accès :** 7 taps sur le nom de l'app dans la page Compte (easter egg admin)

**6 sections du panel admin :**
1. **Candidats** : profils en file de validation Vague 4
2. **Décédés** : queue de décédés détectés (Wikidata P570), à supprimer en lot
3. **Catégories** : audit et correction de catégorisation en batch
4. **Stats** : utilisateurs, votes, créations 7j / 30j
5. **Ajout manuel** : formulaire de création directe pour cas particuliers (ex : Pope Leo XIV, Kim Kardashian)
6. **Modération Outsiders signalés** : profils signalés par utilisateurs, action retrait + bannissement

Le backend de ces sections existe déjà (Sessions 1-3 d'Emergent). Lot 4 = frontend de visualisation/action.

### Lot 5 — Frontend Outsiders utilisateur (5-7h)

**Cas A — Retrait Outsider depuis Compte**
- Section dans `account.tsx` (948 lignes, gros fichier à manipuler avec soin)
- Si l'utilisateur a payé un Booster, il voit son profil Outsider et peut le retirer avant expiration
- Confirmation modal + suppression côté backend
- Remboursement non automatique (politique : pas de remboursement, le service a été rendu)

**Cas B — Signalement centralisé**
- Section dans `account.tsx > Nous contacter`
- Permet à un utilisateur de signaler un Outsider (contenu inapproprié, usurpation, etc.)
- Crée une entrée dans `outsiders_signals`, visible dans Lot 4 panel admin section 6

### Lot 6 — Frontend modération admin + jobs scheduler + test final (2-3h)

- Activation des **3 nouveaux jobs scheduler** dans server.py (à identifier dans le code, probablement `auto_promote_user_created`, `pending_creations_processor`, `deceased_detector`)
- Frontend de la section 6 du panel admin (modération Outsiders signalés)
- Test backend global avant Session 4

### Session 4 — Polish général + Préparation App Store (11-17h)

**Polish général :**
- Revue de code globale (audit qualité)
- Suppression dead code (Daily Run UI désactivée, anciens helpers)
- Optimisations performance (queries MongoDB indexées, lazy loading écrans)
- Animations et transitions fluides
- Tests edge cases (réseau intermittent, mode hors ligne, etc.)
- **Refactoring `server.py`** (6500+ lignes en un fichier) — à découper si possible, sinon à reporter post-lancement

**Préparation App Store :**
- Screenshots Apple Store (6.7", 6.5", 5.5") + Play Store (Android plus tard)
- Textes promotionnels (titre 30 car, sous-titre 30 car, description 4000 car) en 6 langues
- Vérifications légales finales (CGU, Privacy, mentions, lien support)
- **⚠ Sujet ouvert : rejet App Store sur IAP grisés iPad** — un workspace Emergent parallèle a évoqué ce sujet sans contexte clair. À investiguer : tester l'app sur simulateur iPad, vérifier que les 3 IAP s'affichent correctement, lire la documentation Apple sur les IAP cross-device.
- Soumission App Store via App Store Connect
- Délai Apple : 2-7 jours de review

**Cible de lancement : 1ère ou 2e semaine de juin 2026.**

---

## 6. Procédures opérationnelles

### Save to GitHub (côté Didier dans Emergent)

C'est Didier qui clique le bouton "Save to GitHub" dans l'interface Emergent. Cela déclenche un push vers le repo `didierjacob/popular-app` branche `main`.

**Avec Claude Code, le workflow change :** vous (Claude Code) modifiez directement le code local de Didier. Vous lui demanderez de faire `git add . && git commit -m "..." && git push` à votre place quand un palier est atteint.

### Render redéploiement automatique

Après chaque push GitHub, Render détecte automatiquement et redéploie le backend (2-3 min). Pas d'action manuelle requise.

**Vérification que c'est live :**
```bash
curl "https://popular-app.onrender.com/api/search?query=Donald%20Trump" | python3 -m json.tool
```
Si retour avec `"score": 100.0`, la production tourne.

### Rebuild EAS (frontend mobile)

Séquence Terminal sur le Mac de Didier :

```bash
cd ~/Desktop/popularoo
git checkout frontend/package-lock.json frontend/yarn.lock  # nettoie modifs locales
git pull origin main
cd frontend
rm -rf node_modules
npm install                                                  # 2-3 min
npx eas build --platform ios --profile preview --clear-cache # 25-35 min cloud
```

**Quand rebuild EAS est nécessaire :** uniquement quand le code frontend (dossier `frontend/`) a été modifié. Les modifications backend (server.py uniquement) ne nécessitent pas de rebuild EAS.

### Commandes curl admin

Toutes protégées par header `X-Admin-Password: MONMOTDEPASSE` (Didier connaît son vrai mot de passe).

**Vérifications de production utiles :**
```bash
# Recherche d'une personne
curl "https://popular-app.onrender.com/api/search?query=Nom%20Prenom" | python3 -m json.tool

# Récupération par ID
curl "https://popular-app.onrender.com/api/people/IDHEX" | python3 -m json.tool

# Liste classement complet
curl "https://popular-app.onrender.com/api/people?limit=300" | python3 -m json.tool
```

**Commandes admin importantes :**
```bash
# Recalcul global des PI (après changement de formule)
curl -X POST "https://popular-app.onrender.com/api/admin/recalculate-all-pi" \
  -H "X-Admin-Password: MONMOTDEPASSE"

# Migration visibilité user_search (déjà exécutée en Vague 2.5)
curl -X POST "https://popular-app.onrender.com/api/admin/fix-visible-user-search" \
  -H "X-Admin-Password: MONMOTDEPASSE"
```

⚠ **Toujours rappeler à Didier de remplacer `MONMOTDEPASSE`** par son vrai mot de passe avant exécution.

### Apple Developer

- **Team ID confirmé pour la SARL :** à clarifier — il y a une confusion historique entre `RM6N9F576RR` (donné par Emergent) et `WWSNPS7M6R` (utilisé par EAS). À vérifier dans `developer.apple.com/account` avant la première soumission.
- **3 IAP créés dans App Store Connect** avec Review Notes propres
- **Contrat Paid Apps signé**, banque SARL validée
- **Provisioning profile actif** au nom "En haut des marches"
- **⚠ Ne plus jamais toucher à `npx eas credentials`** — un incident antérieur a supprimé un certificat de distribution qui fonctionnait. Si EAS demande quelque chose sur les credentials, dire "Yes" sur les options de réutilisation, jamais "Delete".

---

## 7. Points de vigilance et sujets ouverts

### Sujets techniques

1. **Mystère IAP iPad grisés** : un workspace Emergent parallèle a mentionné un rejet App Store sur les IAP grisés sur iPad. À investiguer en Session 4 : tester sur simulateur iPad, vérifier l'affichage des Boosters, lire la doc Apple sur les IAP cross-device.

2. **298 votes artificiels à la création** : `random.randint(100, 500)` sur les anciens profils seed. C'est de l'astroturfing systémique. **Décision** : documenter dans CGV ou nettoyer en V1.5. Pas urgent.

3. **`server.py` à 6500+ lignes** : refactoring proposé par Emergent. À faire **post-lancement App Store** (Session 4 bis).

4. **Catégorisation `other` mal calibrée** : Didier Deschamps est tombé en `other` alors qu'il devrait être `sport`. Améliorer le mapping en V2 avec mots-clés : `coach`, `manager`, `senator`, `judge`, `entraineur`, `selectionneur`.

5. **`recalculate-all-pi` en réserve** : endpoint existe, à utiliser uniquement si une formule globale est modifiée. Ne pas l'exécuter sans raison explicite (impact sur 258 profils).

### Sujets produit en réflexion

6. **Réintégration du Daily Run** prévue en V2 (backend conservé)
7. **Strikes** (Flash, Diversité, Série) prévus en V2
8. **α descendant progressivement** : passer de 1.0 à 0.5 puis 0.3 quand les utilisateurs seront en nombre suffisant. Logique de transition à designer.

### Sujets juridiques en attente

9. **Email transactionnel via Brevo SMTP** : introduit par Emergent, non encore exhaustivement testé. À valider avant lancement App Store.
10. **RGPD "Mes données"** : section dans Compte permettant à l'utilisateur de voir/exporter/supprimer ses données. À implémenter en Lot 5.

---

## 8. Style de communication attendu avec Didier

### Ce qui fonctionne bien

- **Analogies concrètes** : "Sentry, c'est un détecteur de fumée qui prévient quand l'app brûle"
- **Pédagogie progressive** : pourquoi → quoi → comment
- **Notes "Pour vous, Didier"** en fin de message pour donner du recul stratégique
- **"Ce que vous faites maintenant"** en étapes numérotées pour les actions concrètes
- **Délimiteurs visuels** quand vous préparez un texte qu'il doit copier-coller ailleurs

### Ce qui est à éviter

- Le jargon technique non expliqué
- Les blocs de code sans contexte
- Les décisions techniques prises sans explication du trade-off
- Le scope creep (ajouter des choses non demandées)

### Cadence de validation

Didier valide chaque palier produit important. **Ne jamais coder une décision stratégique sans son OK explicite.** Pour les choix techniques mineurs (renommage de variable, structure d'un helper), vous pouvez décider seul.

---

## 9. État précis au moment de la passation

**Date : 14 mai 2026, soir.**

**Dernière action en cours :** Emergent vient de coder le fix plafond PI Outsider à 25. Didier doit confirmer que c'est poussé sur GitHub + Render redéployé, et que le PI Mila Krause (qui était à 69 pour 17 supporters) est descendu à 25 max.

**Premier objectif Claude Code (demain matin 15 mai) :**

1. Confirmer avec Didier que le fix plafond Outsider est OK en production
2. Attaquer **Vague 4 (validation différée 24h)** — c'est le chantier le plus impactant et le plus aligné avec la vision produit de Didier
3. Vague 3 (mouvements classement + perf) peut être faite en parallèle ou après Vague 4 selon votre préférence

**Préparation conseillée au démarrage :**

- Lire `server.py` complet (6500 lignes — prendre 30 min)
- Lire `external_scores.py` et `candidate_detection.py`
- Lire les écrans frontend principaux : `index.tsx`, `list.tsx`, `outsiders.tsx`, `account.tsx`, `person.tsx`
- Examiner les modèles MongoDB via une requête sur `/api/people?limit=5`

**Bonne chance, et prenez bien soin de Didier — il est à 75% du chemin, fatigué mais déterminé. Ce qui compte, c'est de finir proprement, pas de tout réécrire.**

---

*Fin du document de passation*
