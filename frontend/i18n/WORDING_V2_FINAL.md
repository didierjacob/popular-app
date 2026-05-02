# 📋 WORDING EN V2 FIGÉ — Pour Validation

**Date**: Février 2026  
**Objectif**: Présenter toutes les chaînes EN source corrigées et les nouvelles FAQ V2 pour validation avant lancement des traductions.

---

## ✅ CORRECTIONS APPLIQUÉES (22 chaînes)

### 1. Home Page (`index.tsx`)
| Avant | Après |
|---|---|
| `Rate & rank personalities` | **`Vote on the world's most famous people`** |
| `Rate a personality` | **`Cast your vote`** |
| `Rate` (bouton) | **`Go`** |

### 2. Personality Page (`person.tsx`)
| Avant | Après |
|---|---|
| `Bull Run` (section title) | **`Daily Run`** |
| `Current score: {n}` (share) | **`Popularoo Index: {n}`** |

### 3. Outsiders (`outsiders.tsx`)
| Avant | Après |
|---|---|
| `{n} / {max} slots filled this week` | **`{n} / {max} active slots`** |
| `Top Bull Runners this week` | **`Daily Run Leaders`** |
| `Activate a Golden Booster to compete in Bull Run` | **`Activate a Golden Booster to join the Daily Run`** |

### 4. Premium (`premium.tsx`)
| Avant | Après |
|---|---|
| `• Bull Run access included` | **`• Daily Run access included`** |
| `Home page rotation + Bull Run access` | **`Home page rotation + Daily Run access`** |

### 5. Credits Service (`creditsService.ts`)
| Avant | Après |
|---|---|
| `exclusive Bull Run access` | **`exclusive Daily Run access`** |

### 6. My Votes (`myvotes.tsx`)
| Avant | Après |
|---|---|
| `Chargement...` (français résiduel) | **`Loading...`** |

### 7. Category Page (`category/[key].tsx`)
| Avant | Après |
|---|---|
| `{category} • Score {n} • {votes} votes` | **`{category} • {votes} votes`** (Score supprimé) |

### 8. Account (`account.tsx`)
| Avant | Après |
|---|---|
| `Popularoo v1.0.0` | **`Popularoo v2.0.0`** |

---

## ➕ 5 NOUVELLES FAQ V2

### FAQ 1 — What is the Popularoo Index?
**Q: "What is the Popularoo Index?"**

A: "The Popularoo Index is a live score assigned to every personality in the app. It reflects their current popularity based on community votes, engagement momentum, and recent trends. Think of it as a real-time pulse on public opinion.

The exact formula is kept under wraps — but the more votes and engagement a personality receives, the higher their Index climbs."

---

### FAQ 2 — What are Daily Runs?
**Q: "What are Daily Runs?"**

A: "A Daily Run is a 24-hour challenge where you pick a personality and rally the community to vote for them. It's like launching a campaign — you choose your target, and the clock starts ticking.

For example: you launch a Daily Run for Beyoncé. Over the next 24 hours, every vote she receives counts toward the Run. If enough momentum builds, you could trigger a Strike and earn a Victory.

Daily Runs are the heart of the game. See 'What are Strikes?' to learn what happens when a Run catches fire."

---

### FAQ 3 — What are Strikes?
**Q: "What are Strikes?"**

A: "Strikes are momentum amplifiers triggered by Superlikes during a Daily Run. When a personality receives a burst of Superlikes, the app detects the surge and activates a Strike chain:

• Heating Up — The personality is gaining traction
• On Fire — Momentum is building fast
• Trending — The community is taking notice
• Going Viral — Massive engagement detected
• Legend Mode — The highest level, reserved for exceptional surges

Each Strike level boosts the personality's Popularoo Index further. Strikes are rare and exciting — they mean something big is happening."

---

### FAQ 4 — What are Victory Tiers?
**Q: "What are Victory Tiers?"**

A: "When a Daily Run ends, the outcome is evaluated and assigned a Victory Tier based on how well the personality performed:

• Standard Win — Solid performance, the personality gained meaningful votes
• Underdog Win — An unexpected surge! The personality outperformed expectations
• Legendary Strike — The rarest outcome. The Run triggered multiple Strikes and the community went all-in

Victory Tiers reward strategic play and community engagement."

---

### FAQ 5 — What is a Superlike?
**Q: "What is a Superlike?"**

A: "A Superlike is a premium vote that carries more weight than a regular vote. It signals strong support for a personality and is the key to triggering Strikes during Daily Runs.

Use Superlikes strategically — they can be the difference between a quiet Run and a Legendary Strike."

---

## 📝 FAQ EXISTANTES MISES À JOUR

### "What is Popularoo?" (réécrit)
**Avant**: "Popularoo is an app where you can rate and rank public personalities. Discover trending figures, vote for your favorites, and see who's the most popular!"

**Après**: "Popularoo is the first real-time popularity index for public figures. Vote on your favorite personalities, discover who's trending, and watch rankings shift in real time. Every vote counts — and your voice shapes the Popularoo Index."

### "How do Boosters work?" (corrigé)
**Avant**: "...Bull Run access"
**Après**: "...Daily Run access"

### "What is Personality of the Day?" (corrigé)
**Avant**: "...highest popularity score..."
**Après**: "It's the personality with the highest Popularoo Index at the moment. It updates automatically based on votes and engagement."

---

## 🚫 EXCLUSIONS

- **`bullrun.tsx`** — Écran entier exclu de l'i18n (sera réécrit en Phase C)
- **Backend** — Aucune modification (backend déjà stable à 100%)

---

## ✅ VALIDATION DEMANDÉE

Merci de relire les points suivants :
1. Les 3 nouvelles formulations Home page (baseline, search label, button)
2. Les 5 nouvelles FAQ V2 (ton, contenu, longueur)
3. La FAQ "What is Popularoo?" réécrite

**Une fois validé, je lance immédiatement l'extraction i18n et la traduction dans les 6 langues.**
