# 📱 Guide Complet — Build TestFlight pour Popularoo

> **Temps estimé pour la première configuration : 1h30 à 2h**
> (dont ~30 min d'attente de compilation Apple)

---

## Section A — Prérequis sur Mac

### macOS minimum
- **macOS 13 Ventura** ou plus récent (recommandé : macOS 14 Sonoma+)
- Vérifiez : Menu Pomme → À propos de ce Mac

### 1. Installer Homebrew (gestionnaire de packages)
Ouvrez **Terminal** (Applications → Utilitaires → Terminal) et collez :
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Suivez les instructions à l'écran (mot de passe administrateur requis).

Vérification :
```bash
brew --version
```
Vous devez voir quelque chose comme `Homebrew 4.x.x`.

### 2. Installer Node.js (version recommandée : 22.x LTS)
```bash
brew install node@22
```
Si vous avez déjà Node installé, vérifiez la version :
```bash
node --version
```
Résultat attendu : `v22.x.x` (minimum v18, recommandé v22 pour compatibilité avec le projet).

### 3. Installer Git (si pas déjà présent)
Git est souvent préinstallé sur macOS. Vérifiez :
```bash
git --version
```
Si absent :
```bash
brew install git
```

### 4. Vérifications finales des prérequis
```bash
node --version   # → v22.x.x
npm --version    # → 10.x.x
git --version    # → git version 2.x.x
```

---

## Section B — Installation EAS CLI

### 1. Installer EAS CLI globalement
```bash
npm install -g eas-cli
```

> ⚠️ Si vous obtenez une erreur `EACCES` (permission denied), utilisez :
> ```bash
> sudo npm install -g eas-cli
> ```
> (Entrez votre mot de passe Mac)

### 2. Vérifier l'installation
```bash
eas --version
```
Résultat attendu : `eas-cli/x.x.x` (n'importe quelle version récente fonctionne).

---

## Section C — Récupération du code

### 1. Cloner le repo (première fois uniquement)
```bash
cd ~/Desktop
git clone https://github.com/VOTRE_USERNAME/popularoo.git
cd popularoo
```
> Remplacez `VOTRE_USERNAME` par votre nom d'utilisateur GitHub.

### 2. Si le repo est déjà cloné — Mise à jour
```bash
cd ~/Desktop/popularoo
git pull origin main
```

### 3. Se positionner dans le dossier frontend
```bash
cd frontend
```
> ⚠️ **IMPORTANT** : Toutes les commandes EAS doivent être lancées depuis le dossier `frontend/`, PAS depuis la racine du projet.

Vérification — vous devez voir `package.json` et `eas.json` :
```bash
ls package.json eas.json
```

---

## Section D — Installation des dépendances

### 1. Nettoyer l'ancien état (optionnel mais recommandé)
```bash
rm -rf node_modules
rm -f package-lock.json
```

### 2. Installer les dépendances
```bash
npm install
```

**Durée estimée** : 2 à 5 minutes selon votre connexion internet.

### 3. Erreurs typiques et solutions

| Erreur | Solution |
|--------|----------|
| `ERESOLVE unable to resolve dependency tree` | Ajoutez `--legacy-peer-deps` : `npm install --legacy-peer-deps` |
| `gyp ERR! build error` | Installez les Xcode Command Line Tools : `xcode-select --install` |
| `EACCES permission denied` | Ne PAS utiliser `sudo npm install`. Corrigez les permissions : `sudo chown -R $(whoami) ~/.npm` |
| `found: yarn.lock` warning | Ignorez ou supprimez `yarn.lock` : `rm yarn.lock` puis relancez `npm install` |

---

## Section E — Authentification

### 1. Se connecter à votre compte Expo
```bash
npx eas login
```
Entrez votre **email** et **mot de passe** Expo (celui créé sur expo.dev).

### 2. Vérifier la connexion
```bash
npx eas whoami
```
Résultat attendu : votre nom d'utilisateur Expo.

### 3. Vérifier la configuration EAS
Le fichier `eas.json` est déjà configuré. Vérifiez qu'il existe :
```bash
cat eas.json
```
Vous devez voir le profil `"preview"` avec `"distribution": "internal"`.

### 4. Lier le projet (si première fois)
Si EAS vous demande de configurer le projet :
```bash
npx eas build:configure
```
Choisissez les options par défaut.

---

## Section F — Lancement du build

### 1. Commande de build iOS (TestFlight)
```bash
npx eas build --platform ios --profile preview
```

### 2. Ce qui se passe pendant le build

1. **Questions interactives** (première fois uniquement) :
   - "Would you like to log in to your Apple account?" → **Yes**
   - Entrez votre **Apple ID** (email) et **mot de passe**
   - Code de vérification 2FA si activé
   - "Select a team" → Choisissez votre équipe Apple Developer
   - "Would you like to create a new provisioning profile?" → **Yes**

2. **Upload du code** : ~2 minutes
3. **Compilation sur les serveurs Apple/EAS** : **15-30 minutes**

### 3. Suivre l'avancement
- Le terminal affiche un lien vers le **Expo Build Dashboard**
- Ouvrez ce lien dans votre navigateur pour suivre en temps réel
- URL type : `https://expo.dev/accounts/VOTRE_COMPTE/projects/popularoo/builds/BUILD_ID`

### 4. Build terminé
Quand le build est fini, vous verrez dans le terminal :
```
✔ Build finished
🍎 Open this link on your iOS device to install the build:
https://expo.dev/artifacts/eas/XXXX.ipa
```

---

## Section G — Installation TestFlight

### Option 1 : Distribution interne (profil `preview`)
Avec le profil `preview` (`"distribution": "internal"`), le build est distribué via un lien direct :

1. Ouvrez le lien fourni par EAS **directement sur votre iPhone** (via Safari)
2. Acceptez l'installation du profil de configuration
3. L'app s'installe sur votre écran d'accueil

> Note : La première fois, vous devrez autoriser le développeur dans :
> Réglages → Général → VPN et gestion de l'appareil → Faire confiance

### Option 2 : TestFlight (profil `production`)
Si vous utilisez le profil `production` plus tard :
1. Le build est automatiquement envoyé à App Store Connect
2. Ouvrez **TestFlight** sur votre iPhone
3. L'app apparaît dans "Apps à tester" après ~15 minutes de processing Apple
4. Appuyez sur "Installer"

### Ajouter des testeurs internes (TestFlight)
1. Allez sur [App Store Connect](https://appstoreconnect.apple.com)
2. Mon App → TestFlight → Testeurs internes
3. Ajoutez les Apple ID des testeurs
4. Ils recevront une invitation par email

---

## Section H — Plan B si ça échoue

### Logs à me transmettre
Si le build échoue, copiez-collez :
1. Le message d'erreur complet du terminal
2. Ou envoyez-moi le lien du build sur le Dashboard Expo (il contient les logs détaillés)

### Erreurs fréquentes et solutions

| Erreur | Cause | Solution |
|--------|-------|----------|
| `No Apple Developer Team found` | Compte Apple Developer non configuré | Vérifiez sur [developer.apple.com](https://developer.apple.com) que votre abonnement est actif |
| `Missing provisioning profile` | Profil non créé | Répondez "Yes" quand EAS propose d'en créer un |
| `Bundle identifier mismatch` | Conflit d'identifiant | Vérifiez que `app.json` contient le bon `ios.bundleIdentifier` |
| `Credentials not found` | Première connexion Apple | Relancez le build, EAS redemandera vos credentials |
| `Build timeout` | Serveurs Apple surchargés | Attendez 10 min et relancez : même commande |
| `npm ERR! during install` | Dépendances corrompues | `rm -rf node_modules && npm install` puis relancez |
| `Xcode version mismatch` | Version Xcode trop ancienne sur les serveurs | Vérifiez `eas.json` et mettez à jour si nécessaire |

### Commande de relance (après correction)
```bash
npx eas build --platform ios --profile preview --clear-cache
```
L'option `--clear-cache` force une recompilation propre.

### Si rien ne marche
1. Vérifiez votre abonnement Apple Developer (99$/an, doit être actif)
2. Lancez `npx eas credentials` pour diagnostiquer vos certificats
3. En dernier recours : `npx eas build --platform ios --profile preview --non-interactive` et envoyez-moi les logs complets

---

## 📋 Résumé — Checklist rapide

```
□ Homebrew installé
□ Node.js v22 installé  
□ EAS CLI installé (npm install -g eas-cli)
□ Repo cloné et à jour (git pull)
□ Dans le dossier frontend/ 
□ npm install terminé sans erreur
□ eas login réussi (eas whoami affiche votre nom)
□ eas build --platform ios --profile preview lancé
□ Build terminé — lien d'installation reçu
□ App installée sur iPhone via le lien
□ Test ergonomique du Daily Run ✓
```

---

*Document généré le 5 mai 2026 — Popularoo V1.0*
