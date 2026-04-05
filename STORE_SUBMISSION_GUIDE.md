# 🚀 Guide de Soumission aux App Stores

## Pré-requis
- ✅ Compte Apple Developer (99€/an)
- ✅ Compte Google Play Developer (25€ une fois)
- ✅ EAS CLI installé (`npm install -g eas-cli`)
- ✅ Connexion EAS (`npx eas login`)

---

## ÉTAPE 1 : Récupérer le code à jour

```bash
cd ~/popular/frontend
git pull origin main
npm install
```

> Si erreur `yarn.lock` / `package-lock.json`, supprimez les deux et refaites `npm install`.

---

## ÉTAPE 2 : Seeder la base de production

⚠️ **À exécuter UNE SEULE FOIS** — les endpoints sont idempotents.

```bash
# 1. Ajouter les 100 personnalités
curl -X POST https://popular-app.onrender.com/api/admin/add-missing-seeds

# 2. Corriger les catégories
curl -X POST https://popular-app.onrender.com/api/admin/fix-categories

# 3. Créer l'outsider de démo
curl -X POST https://popular-app.onrender.com/api/admin/create-demo-outsider

# 4. Initialiser les votes (8500-12000 par personnalité)
curl -X POST https://popular-app.onrender.com/api/admin/init-votes
```

---

## ÉTAPE 3 : Vérifier la config `.env`

Dans `~/popular/frontend/`, créez ou modifiez le fichier `.env` :

```
EXPO_PUBLIC_BACKEND_URL=https://popular-app.onrender.com
```

> C'est l'URL de votre backend sur Render.

---

## ÉTAPE 4 : Build de production

### iOS (App Store)
```bash
cd ~/popular/frontend
npx eas build --platform ios --profile production
```

- EAS va vous demander de vous connecter à votre compte Apple Developer
- Le build prend ~15-20 minutes
- Résultat : un fichier `.ipa` hébergé sur EAS

### Android (Google Play)
```bash
cd ~/popular/frontend
npx eas build --platform android --profile production
```

- Résultat : un fichier `.aab` (Android App Bundle)

### OU les deux en même temps :
```bash
npx eas build --platform all --profile production
```

---

## ÉTAPE 5 : Préparer les fiches stores

### Informations de l'app
| Champ | Valeur |
|-------|--------|
| **Nom** | Populr |
| **Sous-titre** | Rate & rank personalities |
| **Catégorie** | Entertainment / Social |
| **Prix** | Gratuit (avec achats in-app) |
| **Contact email** | contactpopulr@proton.me |
| **URL politique de confidentialité** | *(à créer sur votre site)* |

### Description courte (80 caractères)
```
Vote for your favorite personalities and see who's the most popular!
```

### Description longue
```
Populr is the ultimate personality ranking app! Rate and rank public figures from politics, culture, sports, and business.

🗳️ VOTE — Like or dislike personalities every 24 hours
📊 TRACK — Follow real-time popularity scores and trends
🔍 DISCOVER — Search thousands of public figures or add new ones
🏆 TOP 100 — See who's the most popular in every category
🚀 BOOST — Get featured on the Home page with Boosters

Features:
• Real-time polling with instant score updates
• Vote history with personal statistics and badges
• Personality of the Day spotlight
• Category filters: Politics, Culture, Business, Sport
• Wikipedia integration for discovering new personalities
• Booster system to promote yourself as an Outsider
• Beautiful dark-themed design

Download now and make your voice heard!
```

### Screenshots requis
Les screenshots sont prêts dans `/app/screenshots/` :
- **iOS** (1290x2796) : `ios/home.png`, `ios/person_zendaya.png`, `ios/premium.png`, `ios/popular.png`, `ios/list.png`
- **Android** (1080x1920) : même chose dans `android/`

### Icône
- Fichier : `assets/images/icon.png` (1024x1024)
- Déjà configuré dans `app.json`

---

## ÉTAPE 6 : Soumettre aux stores

### iOS — App Store Connect
```bash
npx eas submit --platform ios --profile production
```

- EAS va uploader le `.ipa` sur App Store Connect
- Connectez-vous à [App Store Connect](https://appstoreconnect.apple.com)
- Remplissez : description, screenshots, catégorie, prix
- Soumettez pour review (délai : 24-48h en général)

### Android — Google Play Console
```bash
npx eas submit --platform android --profile production
```

- EAS va uploader le `.aab` sur Google Play Console
- Connectez-vous à [Google Play Console](https://play.google.com/console)
- Créez une fiche de l'app avec description et screenshots
- Soumettez pour review (délai : quelques heures à 7 jours)

---

## ⚠️ Points importants pour la review

1. **Achats in-app** : Le système de boosters est en simulation pour l'instant. Apple/Google peuvent demander une intégration avec leur système de paiement (StoreKit / Google Billing). C'est une mise à jour post-lancement.

2. **Politique de confidentialité** : Obligatoire. Créez une page simple expliquant :
   - L'app utilise un ID anonyme (pas de compte requis)
   - Les données personnelles sont optionnelles
   - Contact : contactpopulr@proton.me

3. **Encryption** : Déjà configuré dans `app.json` (`ITSAppUsesNonExemptEncryption: false`)

---

## 🆘 En cas d'erreur

### "yarn: command not found"
→ Utilisez `npm` à la place de `yarn`

### "Could not find module" 
→ `npm install` puis réessayez

### "Build failed"
→ Supprimez `node_modules`, `yarn.lock`, `package-lock.json` puis :
```bash
npm install
npx eas build --platform ios --profile production --clear-cache
```

### "Apple credentials"
→ EAS vous guidera pour configurer les certificats Apple automatiquement
