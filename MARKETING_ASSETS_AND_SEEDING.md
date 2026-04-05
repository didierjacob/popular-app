# 📱 Populr App - Marketing Assets & Production Setup

## 📸 Screenshots Marketing (Prêts !)

### iOS (iPhone 6.7" - 1290x2796)
Les fichiers se trouvent dans `/app/screenshots/ios/` :
- `home.png` - Page d'accueil avec personnalité du jour et catégories
- `person_zendaya.png` - Page personnalité (Zendaya) avec graphiques
- `premium.png` - Page Boosters avec les offres
- `popular.png` - Page "Instant polling" avec filtres
- `list.png` - Top 100 Populr avec classement

### Android (1080x1920)
Les fichiers se trouvent dans `/app/screenshots/android/` :
- `home.png` - Page d'accueil
- `person_zendaya.png` - Page personnalité
- `premium.png` - Page Boosters
- `popular.png` - Page Instant polling
- `list.png` - Top 100 Populr

### 🎨 Icône de l'app (1024x1024)
- Fichier : `/app/frontend/assets/images/icon.png`
- Icône adaptative Android : `/app/frontend/assets/images/adaptive-icon.png`
- Favicon : `/app/frontend/assets/images/favicon.png`

---

## 🗄️ Commandes de Seeding Production

**IMPORTANT** : Ces commandes doivent être exécutées **une seule fois** sur votre backend de production hébergé sur Render.

URL de production : `https://popular-app.onrender.com`

### Étape 1 : Ajouter les personnalités manquantes (pour arriver à 100)
```bash
curl -X POST https://popular-app.onrender.com/api/admin/add-missing-seeds
```
> Ajoute les personnalités seed qui n'existent pas encore dans la base.

### Étape 2 : Corriger les catégories (Sport + Pope Francis)
```bash
curl -X POST https://popular-app.onrender.com/api/admin/fix-categories
```
> Déplace les sportifs dans "sport" et Pope Francis dans "politics".

### Étape 3 : Créer l'outsider de démonstration (Alex Martin)
```bash
curl -X POST https://popular-app.onrender.com/api/admin/create-demo-outsider
```
> Crée "Alex Martin" comme outsider avec 0 votes.

### Étape 4 : Initialiser les votes réalistes (8500-12000 par personnalité)
```bash
curl -X POST https://popular-app.onrender.com/api/admin/init-votes
```
> Donne à chaque personnalité un nombre aléatoire de votes pour que l'app paraisse active dès le lancement.

### Étape 5 : Initialiser les votes pour les personnalités à faible activité
```bash
curl -X POST https://popular-app.onrender.com/api/admin/initialize-votes
```
> Cible spécifiquement les personnalités avec moins de 100 votes (sauf les outsiders).

---

## ⚠️ Ordre recommandé d'exécution

1. **D'abord** : `add-missing-seeds` (ajouter les personnalités)
2. **Ensuite** : `fix-categories` (corriger les catégories)
3. **Ensuite** : `create-demo-outsider` (créer l'outsider)
4. **Enfin** : `init-votes` (initialiser les votes pour tous)

---

## 📝 Notes importantes
- Ces endpoints sont **idempotents** : vous pouvez les exécuter plusieurs fois sans risque de doublons
- Le backend Render se redéploie automatiquement à chaque `git push`
- Les données ne se mettent PAS à jour automatiquement lors d'un redéploiement
- Vérifiez que le backend Render est bien actif avant d'exécuter les commandes (le plan gratuit peut mettre le service en veille)
