# 🔍 AUDIT WORDING V2 — Popularoo Frontend

**Date**: Février 2026  
**Objectif**: Identifier toutes les chaînes hardcodées, évaluer leur compatibilité V2, et proposer les réécritures nécessaires AVANT de lancer l'i18n.

**Légende**:
- ✅ Cohérent V2 — à traduire tel quel
- ⚠️ Obsolète — à réécrire avant traduction
- ➕ À créer — chaîne manquante pour la V2

---

## VOCABULAIRE V2 DE RÉFÉRENCE

| Terme V1 (obsolète) | Terme V2 (à utiliser) |
|---|---|
| Bull Run (hebdomadaire) | Daily Run (24h) |
| Score / raw score | Popularoo Index |
| Votes bruts comme métrique principale | Popularoo Index comme métrique |
| Bull Run access | Daily Run access |
| Objectifs hebdomadaires | Objectifs 24h glissantes |
| Top Bull Runners this week | (Supprimer ou remplacer par Daily Run) |
| Wins / Out-rallied | Victory Tiers (Standard Win, Underdog Win, Legendary Strike) |
| Strikes levels | Heating Up, On Fire, Trending, Going Viral, Legend Mode |

---

## ZONE 1 — Home Page (`index.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 1 | `"Popularoo"` | ✅ | — |
| 2 | `"Rate & rank personalities"` | ⚠️ | `"Discover the Popularoo Index"` ou `"See who's trending"` |
| 3 | `"Rate a personality"` | ⚠️ | `"Search a personality"` |
| 4 | `"Enter a name"` | ✅ | — |
| 5 | `"Rate"` (bouton) | ⚠️ | `"Search"` ou `"Go"` |
| 6 | `"Personality of the Day"` | ✅ | — |
| 7 | `"{category} • {n} votes"` | ✅ | — |
| 8 | `"{n} vote"` / `"{n} votes"` | ✅ | — |
| 9 | `"Outsider of the Day"` | ✅ | — |
| 10 | `"Categories"` | ✅ | — |
| 11 | `"Politics"` | ✅ | — |
| 12 | `"Culture"` | ✅ | — |
| 13 | `"Business"` | ✅ | — |
| 14 | `"Sport"` | ✅ | — |
| 15 | `"Top Personalities"` | ✅ | — |
| 16 | `"Loading..."` | ✅ | — |
| 17 | `"Error: {error}"` | ✅ | — |
| 18 | `"Retry"` | ✅ | — |
| 19 | `'"{name}" not found. Try another name.'` | ✅ | — |
| 20 | `"{n}m left"` / `"{n}h left"` / `"{n}d left"` | ✅ | — |

---

## ZONE 2 — Popular / Instant Polling (`popular.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 21 | `"Instant polling"` | ✅ | — |
| 22 | `"All"` | ✅ | — |
| 23 | Category labels (Politics/Culture/Business/Sport) | ✅ | — |

---

## ZONE 3 — Top 100 List (`list.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 24 | `"Top 100 Popularoo"` | ✅ | — |
| 25 | Filter labels (same as above) | ✅ | — |

---

## ZONE 4 — Personality Page (`person.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 26 | `"Home"` | ✅ | — |
| 27 | `"{n} supporters"` | ✅ | — |
| 28 | `"{n} likes • {n} dislikes"` | ✅ | — |
| 29 | `"Popular"` / `"Unpopular"` | ✅ | — |
| 30 | `"{n} total votes"` | ✅ | — |
| 31 | `"Live ratings"` | ✅ | — |
| 32 | `"Your vote shapes the trend — be the first to vote!"` | ✅ | — |
| 33 | `"Vote history (24h)"` | ✅ | — |
| 34 | `"Vote history will appear as votes come in"` | ✅ | — |
| 35 | `"Current: {n} votes"` | ✅ | — |
| 36 | `"Vote for {name}"` | ✅ | — |
| 37 | `"Like"` / `"Dislike"` | ✅ | — |
| 38 | **`"Bull Run"`** (section title for outsiders) | ⚠️ | `"Daily Run"` |
| 39 | `"This is an Outsider competing in the ranking.\nYour vote helps them climb!"` | ✅ | — |
| 40 | `"Share"` | ✅ | — |
| 41 | `"Facebook"` / `"Twitter"` / `"Instagram"` / `"More"` | ✅ | — |
| 42 | `"Personality trends (live)"` | ✅ | — |
| 43 | `"Every vote counts — cast yours to start the chart!"` | ✅ | — |
| 44 | `"⏰ Already Voted"` (Alert title) | ✅ | — |
| 45 | `"You already voted for {name} today."` | ✅ | — |
| 46 | `"You can vote again in {n} hours/minutes."` | ✅ | — |
| 47 | `"Check out {name} on Popularoo! Current score: {n}..."` | ⚠️ | `"Check out {name} on Popularoo! Popularoo Index: {n}..."` |
| 48 | `"Share"` (Alert for Instagram fallback) | ✅ | — |

---

## ZONE 5 — My Votes (`myvotes.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 49 | **`"Chargement..."`** | ⚠️ | `"Loading..."` (c'est du français résiduel!) |
| 50 | `"My Votes"` | ✅ | — |
| 51 | `"Clear"` | ✅ | — |
| 52 | `"No votes yet"` | ✅ | — |
| 53 | `"Be the first to vote — your vote shapes the trend!"` | ✅ | — |
| 54 | `"Voting streak"` | ✅ | — |
| 55 | `"Vote every day to increase your streak"` | ✅ | — |
| 56 | `"Current days"` | ✅ | — |
| 57 | `"Record"` | ✅ | — |
| 58 | `"Total votes"` | ✅ | — |
| 59 | `"Badges"` | ✅ | — |
| 60 | `"📊 Statistics"` | ✅ | — |
| 61 | `"Distribution :"` | ✅ | — |
| 62 | `"Favorite category :"` | ✅ | — |
| 63 | `"Most voted :"` | ✅ | — |
| 64 | `"By category :"` | ✅ | — |
| 65 | `"History"` | ✅ | — |
| 66 | `"Just now"` / `"{n}min ago"` / `"{n}h ago"` / `"Yesterday"` / `"{n}d ago"` | ✅ | — |

---

## ZONE 6 — Outsiders (`outsiders.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 67 | `"Outsiders"` | ✅ | — |
| 68 | `"Boosted by the community"` | ✅ | — |
| 69 | `"{n} / {max} slots filled this week"` | ⚠️ | `"{n} / {max} active slots"` (plus de notion hebdomadaire en V2) |
| 70 | `"FULL"` / `"{n} open"` | ✅ | — |
| 71 | `"Want to appear here?"` | ✅ | — |
| 72 | `"Get a Booster and join the ranking!"` | ✅ | — |
| 73 | `"YOU"` | ✅ | — |
| 74 | `"Expired"` | ✅ | — |
| 75 | `"Renew"` | ✅ | — |
| 76 | `"No outsiders yet"` | ✅ | — |
| 77 | `"Be the first to get a Booster and appear here!"` | ✅ | — |
| 78 | `"Get a Booster"` | ✅ | — |
| 79 | `"Slot available"` | ✅ | — |
| 80 | `"Boost yourself to claim this spot"` | ✅ | — |
| 81 | **`"Top Bull Runners this week"`** | ⚠️ | **SUPPRIMER** ou remplacer par `"Daily Run Leaders"` |
| 82 | **`"Activate a Golden Booster to compete in Bull Run"`** | ⚠️ | `"Activate a Golden Booster to join the Daily Run"` |
| 83 | `"Learn more"` | ✅ | — |
| 84 | Time format: `"{n}m left"` / `"{n}h {n}m left"` etc. | ✅ | — |

---

## ZONE 7 — Premium / Boost (`premium.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 85 | `"Boost Yourself"` | ✅ | — |
| 86 | `"Get Noticed!"` | ✅ | — |
| 87 | `"Purchase a Booster and your name will appear in the Outsiders ranking for everyone to see. Golden Booster also gets priority placement and rotates on the Home page as Outsider of the Day."` | ✅ | — |
| 88 | `"Choose Your Booster"` | ✅ | — |
| 89 | `"Secure payment via {Apple/Google Play}"` | ✅ | — |
| 90 | `"Loading prices..."` | ✅ | — |
| 91 | `"BEST VALUE"` | ✅ | — |
| 92 | `"1 hour"` / `"24 hours"` / `"1 week"` | ✅ | — |
| 93 | **`"Home page rotation as Outsider of the Day + Bull Run access"`** | ⚠️ | `"Home page rotation as Outsider of the Day + Daily Run access"` |
| 94 | `"Priority placement in Outsiders + name in the ranking"` | ✅ | — |
| 95 | `"Selected"` | ✅ | — |
| 96 | `"Your Information"` | ✅ | — |
| 97 | `"Your Name *"` / `"Enter your full name"` | ✅ | — |
| 98 | `"Email (for confirmation)"` | ✅ | — |
| 99 | `"Social Media (optional)"` | ✅ | — |
| 100 | `"@username"` / `"Profile name or URL"` | ✅ | — |
| 101 | `"Confirm Purchase"` | ✅ | — |
| 102 | `"Buy via {Apple/Google} — {price}"` | ✅ | — |
| 103 | Payment disclaimers (iOS/Android/web) | ✅ | — |
| 104 | `"History"` | ✅ | — |
| 105 | `"No transactions yet"` | ✅ | — |
| 106 | `"Restore Purchases"` | ✅ | — |
| 107 | `"Terms of Use"` / `"Privacy Policy"` | ✅ | — |
| 108 | `"Select a Booster"` / `"Name required"` (alert titles) | ✅ | — |
| 109 | `"Connecting to Store"` / `"We are connecting to the App Store..."` | ✅ | — |
| 110 | `"🎉 Boost Activated!"` | ✅ | — |
| 111 | `"Purchases Restored"` / `"No Purchases Found"` | ✅ | — |

---

## ZONE 8 — Account (`account.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 112 | `"My Account"` | ✅ | — |
| 113 | `"Personal Information"` | ✅ | — |
| 114 | `"Full Name"` / `"Email"` / `"Address"` / `"City"` / `"Country"` | ✅ | — |
| 115 | `"Enter your name"` / `"Enter your email"` / `"Enter your address"` / `"City"` / `"Country"` (placeholders) | ✅ | — |
| 116 | `"Save Changes"` / `"Saving..."` | ✅ | — |
| 117 | `"Success"` / `"Account information saved!"` (alert) | ✅ | — |
| 118 | `"Error"` / `"Failed to save account information"` (alert) | ✅ | — |
| 119 | `"Billing & Payment"` | ✅ | — |
| 120 | `"Payment Methods"` / `"Via App Store / Google Play"` | ✅ | — |
| 121 | `"Billing History"` | ✅ | — |
| 122 | `"Invoices"` | ✅ | — |
| 123 | `"Support"` | ✅ | — |
| 124 | `"Help Center"` | ✅ | — |
| 125 | `"Contact Us"` | ✅ | — |
| 126 | **`"Popularoo v1.0.0"`** | ⚠️ | Devrait être dynamique ou `"Popularoo v2.0.0"` |
| 127 | `"© 2026 Popularoo App. All rights reserved."` | ✅ | — |
| 128 | `"No invoices yet"` / `"No transactions yet"` | ✅ | — |
| 129 | `"Your invoices/purchase history will appear here after your first boost."` | ✅ | — |
| 130 | `"Paid"` | ✅ | — |

---

## ZONE 9 — Help Center / FAQ (`account.tsx` → screen "help")

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 131 | `"Help Center"` | ✅ | — |
| 132 | `"Can't find what you're looking for?"` | ✅ | — |
| 133 | `"Contact Support"` | ✅ | — |
| 134 | **Q: `"What is Popularoo?"`** | ⚠️ | Réponse mentionne "rate and rank" — devrait mentionner le Popularoo Index, les Daily Runs, les Strikes |
| 135 | A: `"Popularoo is an app where you can rate and rank public personalities..."` | ⚠️ | `"Popularoo is the first real-time popularity index. Vote, discover trending personalities, compete in Daily Runs, and trigger Strikes to climb the rankings."` |
| 136 | **Q: `"How do Boosters work?"`** | ⚠️ | Réponse mentionne `"Bull Run access"` |
| 137 | A: `"...Golden Booster (€49.99) — 7 days with priority placement, Home page rotation as Outsider of the Day, and Bull Run access"` | ⚠️ | Remplacer `"Bull Run access"` par `"Daily Run access"` |
| 138 | Q: `"How do I vote?"` | ✅ | — |
| 139 | Q: `"What is Personality of the Day?"` | ✅ | — |
| 140 | A: `"It's the personality with the highest popularity score at the moment."` | ⚠️ | `"It's the personality with the highest Popularoo Index at the moment."` |
| 141 | Q: `"Can I add a new personality?"` | ✅ | — |
| 142 | Q: `"How do I contact support?"` | ✅ | — |
| 143 | Q: `"Is my data private?"` | ✅ | — |
| 144 | ➕ **FAQ manquante**: `"What is the Popularoo Index?"` | ➕ | Expliquer le concept central de la V2 |
| 145 | ➕ **FAQ manquante**: `"What are Daily Runs?"` | ➕ | Expliquer les défis 24h ciblés |
| 146 | ➕ **FAQ manquante**: `"What are Strikes?"` | ➕ | Expliquer les amplificateurs (Heating Up → Legend Mode) |
| 147 | ➕ **FAQ manquante**: `"What are Victory Tiers?"` | ➕ | Expliquer Standard Win, Underdog Win, Legendary Strike |
| 148 | ➕ **FAQ manquante**: `"What is a Superlike?"` | ➕ | Expliquer la mécanique du superlike |

---

## ZONE 10 — Bull Run Page (`bullrun.tsx`) — ⚠️ ÉCRAN ENTIER OBSOLÈTE

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 149 | **Tout l'écran** | ⚠️ | Cet écran utilise des **MOCK DATA** et du vocabulaire V1 ("Bull Run", "wins", "out-rallied", etc.). Il devra être **entièrement réécrit** pour la Phase C (Daily Run UI). **Ne pas traduire cet écran.** |
| 150 | `"Bull Run"` (header) | ⚠️ | `"Daily Run"` (Phase C) |
| 151 | `"LIVE"` | ✅ | — |
| 152 | `"The Ladder"` | ⚠️ | À revoir en Phase C |
| 153 | `"Launch Rally Cry"` | ⚠️ | À revoir en Phase C |
| 154 | Rally Cry modal (toutes les chaînes) | ⚠️ | À revoir en Phase C |

---

## ZONE 11 — Splash Screen (`splash.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 155 | Aucune chaîne de texte (juste le "P" animé) | ✅ | — |

---

## ZONE 12 — Category Page (`category/[key].tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 156 | Category labels (Politics/Culture/Business/Sport) | ✅ | — |
| 157 | **`"Score {n}"`** (dans la ligne meta) | ⚠️ | Supprimer ou remplacer par Popularoo Index icon |

---

## ZONE 13 — Tab Bar Labels (`_layout.tsx`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 158 | `"Home"` | ✅ | — |
| 159 | `"List"` | ✅ | — |
| 160 | `"Outsiders"` | ✅ | — |
| 161 | `"My Votes"` | ✅ | — |
| 162 | `"Boost"` | ✅ | — |
| 163 | `"Account"` | ✅ | — |

---

## ZONE 14 — User Engagement / Badges (`useUserEngagement.ts`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 164 | `"Beginner"` / `"Vote 10 times"` | ✅ | — |
| 165 | `"Active"` / `"Vote 50 times"` | ✅ | — |
| 166 | `"Expert"` / `"Vote 100 times"` | ✅ | — |
| 167 | `"Legend"` / `"Vote 250 times"` | ✅ | — |
| 168 | `"Master"` / `"Vote 500 times"` | ✅ | — |

---

## ZONE 15 — Booster Tier Descriptions (`creditsService.ts`)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 169 | `"Get a spot in the Outsiders ranking for 1 hour. Get noticed by the community."` | ✅ | — |
| 170 | `"Get a spot in the Outsiders ranking for 24 hours. More time = more votes = better climb."` | ✅ | — |
| 171 | **`"Priority placement in Outsiders + Home page rotation + exclusive Bull Run access."`** | ⚠️ | `"Priority placement in Outsiders + Home page rotation + exclusive Daily Run access."` |

---

## ZONE 16 — Notifications / Emails (Backend-triggered)

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 172 | ➕ Pas de notifications in-app localisées | ➕ | À créer dans Chantier 1G |

---

## ZONE 17 — Messages d'erreur génériques

| # | Chaîne actuelle (EN) | Statut | Suggestion V2 |
|---|---|---|---|
| 173 | `"Payment Methods"` (alert body about App Store) | ✅ | — |
| 174 | `"Purchase Error"` / `"Could not initiate purchase."` | ✅ | — |
| 175 | `"Restore Failed"` / `"Could not restore purchases."` | ✅ | — |

---

## 📊 RÉSUMÉ DE L'AUDIT

| Statut | Nombre | Pourcentage |
|---|---|---|
| ✅ Cohérent V2 | ~148 | ~85% |
| ⚠️ Obsolète / à réécrire | ~22 | ~12.5% |
| ➕ À créer | ~5 | ~2.5% |

### ⚠️ Chaînes prioritaires à réécrire (BLOQUANT pour traduction)

1. **"Bull Run" → "Daily Run"** — 6 occurrences dans 4 fichiers (`person.tsx`, `outsiders.tsx`, `premium.tsx`, `creditsService.ts`)
2. **"Score" → "Popularoo Index"** — 2 occurrences (`category/[key].tsx`, share message dans `person.tsx`)
3. **"Rate & rank personalities" → "Discover the Popularoo Index"** — 1 occurrence (`index.tsx`)
4. **"Rate a personality" / "Rate" button** — 2 occurrences (`index.tsx`)
5. **"Chargement..." → "Loading..."** — 1 occurrence de français résiduel (`myvotes.tsx`)
6. **"v1.0.0" → version dynamique** — 1 occurrence (`account.tsx`)
7. **"this week" → "active slots"** — 1 occurrence (`outsiders.tsx`)
8. **FAQ Help Center** — 5 réponses à mettre à jour + 5 nouvelles FAQ à créer
9. **bullrun.tsx** — Écran entier à exclure de l'i18n (sera réécrit en Phase C)

### RECOMMANDATION

**Niveau d'effort estimé** : ~1 session pour les réécritures ⚠️ + FAQ ➕, car la grande majorité (85%) du wording est déjà V2-compatible.

**Séquence recommandée** :
1. Corriger les 22 chaînes ⚠️ obsolètes dans le code source
2. Ajouter les 5 FAQ ➕ manquantes
3. Vous soumettre le wording EN figé pour validation
4. Une fois validé → extraire toutes les chaînes dans les JSON i18n
5. Traduire dans les 5 autres langues (FR, ES, PT, DE, IT)
