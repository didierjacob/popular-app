# 📧 Configuration du Rapport Quotidien

## Vue d'ensemble

Le système de rapport quotidien est **prêt à être configuré**. Il vous suffit d'ajouter vos identifiants Gmail.

---

## 🔑 Étape 1 : Créer un App Password Gmail

### 1. Accéder à votre compte Google
1. Allez sur https://myaccount.google.com/
2. Connectez-vous avec votre compte Gmail

### 2. Activer la validation en deux étapes (2FA)
1. Dans le menu de gauche, cliquez sur **"Sécurité"**
2. Trouvez **"Validation en deux étapes"**
3. Si ce n'est pas activé, cliquez sur **"Activer"** et suivez les instructions
4. Configurez votre méthode (SMS, application Google Authenticator, etc.)

### 3. Créer un App Password
1. Une fois la 2FA activée, retournez dans **"Sécurité"**
2. Cliquez sur **"Validation en deux étapes"**
3. Descendez tout en bas jusqu'à **"Mots de passe des applications"**
4. Cliquez dessus
5. Sélectionnez **"Autre (nom personnalisé)"** dans le menu déroulant
6. Tapez : **"Popular App Reports"**
7. Cliquez sur **"Générer"**
8. **IMPORTANT** : Copiez le mot de passe affiché (16 caractères)
   - Format : `xxxx xxxx xxxx xxxx`
   - Vous ne pourrez plus le revoir !

---

## ⚙️ Étape 2 : Configurer le fichier .env

### Éditer `/app/backend/.env`

Remplacez les lignes vides par vos identifiants :

```bash
# Email Configuration (Gmail SMTP)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="votre.email@gmail.com"              # ← Votre email Gmail
SMTP_PASSWORD="xxxx xxxx xxxx xxxx"            # ← Votre App Password (16 caractères)
SMTP_FROM_EMAIL="votre.email@gmail.com"        # ← Même email
SMTP_FROM_NAME="Popular App"
```

### Exemple complet :

```bash
SMTP_HOST="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="reports.popular@gmail.com"
SMTP_PASSWORD="abcd efgh ijkl mnop"
SMTP_FROM_EMAIL="reports.popular@gmail.com"
SMTP_FROM_NAME="Popular App"
```

---

## 🚀 Étape 3 : Redémarrer le backend

Après avoir modifié le `.env`, redémarrez le backend :

```bash
sudo supervisorctl restart backend
```

---

## 📊 Étape 4 : Tester l'envoi manuel

### Test 1 : Voir les stats (sans envoyer d'email)

```bash
curl http://localhost:8001/api/reports/stats | python3 -m json.tool
```

**Résultat attendu :**
```json
{
  "date": "24/11/2024",
  "total_people": 42,
  "votes_24h": 156,
  "new_people_24h": 3,
  "active_users_24h": 12,
  "credits_sold_24h": 20,
  "revenue_24h": "90.00",
  "premium_votes_24h": 5,
  "top_people": [...]
}
```

### Test 2 : Envoyer le rapport par email

```bash
curl -X POST "http://localhost:8001/api/reports/daily?to_email=didier@coffeeandfilms.com"
```

**Résultat attendu :**
```json
{
  "success": true,
  "message": "Rapport quotidien envoyé à didier@coffeeandfilms.com",
  "stats": {...}
}
```

**Vérifiez votre boîte email** : `didier@coffeeandfilms.com`

---

## ⏰ Étape 5 : Automatiser l'envoi quotidien

### Option A : Cron Job (Linux)

Ajouter au crontab :

```bash
# Éditer le crontab
crontab -e

# Ajouter cette ligne (envoi à 09:00 tous les jours)
0 9 * * * curl -X POST "http://localhost:8001/api/reports/daily?to_email=didier@coffeeandfilms.com"
```

### Option B : Systemd Timer (Linux)

Créer `/etc/systemd/system/popular-daily-report.service` :

```ini
[Unit]
Description=Popular Daily Report

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -X POST "http://localhost:8001/api/reports/daily?to_email=didier@coffeeandfilms.com"
```

Créer `/etc/systemd/system/popular-daily-report.timer` :

```ini
[Unit]
Description=Popular Daily Report Timer

[Timer]
OnCalendar=daily
OnCalendar=09:00
Persistent=true

[Install]
WantedBy=timers.target
```

Activer :

```bash
sudo systemctl enable popular-daily-report.timer
sudo systemctl start popular-daily-report.timer
```

### Option C : Scheduler Python (intégré)

Ajouter APScheduler au backend (à implémenter si besoin).

---

## 📧 Contenu du Rapport

Le rapport quotidien inclut :

### 📊 Vue d'ensemble
- **Total de personnalités** dans la base
- **Votes (24h)** : Nombre de votes des dernières 24h
- **Nouvelles personnalités** : Ajoutées dans les dernières 24h
- **Utilisateurs actifs** : Nombre d'utilisateurs ayant voté

### 💰 Monétisation
- **Crédits vendus** : Nombre de crédits achetés (24h)
- **Revenus (€)** : Revenus générés (simulation)
- **Votes Premium** : Nombre de votes x100 utilisés

### 🏆 Top 5 Personnalités
- Classement par nombre de votes (24h)
- Affiche : rang, nom, votes, score actuel

### 🎨 Design
- Email HTML responsive
- Design élégant avec couleurs de l'app
- Logo et header personnalisés
- Footer avec informations

---

## 🔧 Dépannage

### Erreur : "SMTP credentials not configured"

**Cause :** Les variables `SMTP_USER` ou `SMTP_PASSWORD` sont vides.

**Solution :** 
1. Vérifier que vous avez bien rempli le `.env`
2. Redémarrer le backend
3. Retester

### Erreur : "Authentication failed"

**Cause :** Mot de passe incorrect ou 2FA non activée.

**Solution :**
1. Vérifier que vous avez créé un **App Password** (pas votre mot de passe Gmail normal)
2. Vérifier que la 2FA est activée
3. Re-générer un nouvel App Password si nécessaire

### Erreur : "Connection timeout"

**Cause :** Firewall ou port bloqué.

**Solution :**
1. Vérifier que le port 587 est ouvert
2. Essayer avec le port 465 (SSL) : modifier `SMTP_PORT="465"` dans le `.env`

### L'email n'arrive pas

**Vérifier :**
1. ✅ Dossier Spam / Courrier indésirable
2. ✅ L'adresse email du destinataire
3. ✅ Les logs backend : `tail -f /var/log/supervisor/backend.err.log`

---

## 📝 Modification du destinataire

Pour changer l'adresse email de destination :

**Méthode 1 : Dans l'URL**
```bash
curl -X POST "http://localhost:8001/api/reports/daily?to_email=nouveau@email.com"
```

**Méthode 2 : Par défaut dans le code**

Éditer `/app/backend/server.py`, ligne avec `to_email` :
```python
async def send_daily_report(to_email: str = Query(default="nouveau@email.com")):
```

---

## 🔒 Sécurité

### ⚠️ IMPORTANT
- Ne **jamais** committer le fichier `.env` dans Git
- Garder votre App Password secret
- Utiliser un compte Gmail dédié (recommandé)

### Bonnes pratiques
- Créer un compte Gmail spécifique : `reports.popular@gmail.com`
- Activer la 2FA sur ce compte
- Ne pas partager les identifiants

---

## 📅 Horaire recommandé

**09:00 (UTC)** : Bon compromis international
- Paris : 10:00 (hiver) / 11:00 (été)
- New York : 04:00 (hiver) / 05:00 (été)

**Ajustez selon votre timezone !**

---

## ✅ Checklist finale

- [ ] App Password Gmail créé
- [ ] Fichier `.env` configuré
- [ ] Backend redémarré
- [ ] Test manuel réussi
- [ ] Email reçu dans didier@coffeeandfilms.com
- [ ] Cron job ou timer configuré
- [ ] Premier rapport quotidien automatique testé

---

## 🎉 Félicitations !

Votre rapport quotidien est maintenant **opérationnel** !

Vous recevrez chaque jour à 09:00 :
- 📊 Les statistiques complètes
- 💰 Les revenus du jour
- 🏆 Le Top 5 des personnalités

**Tout est prêt !** ✅

---

**Questions ou problèmes ?**
- Consulter les logs : `tail -f /var/log/supervisor/backend.err.log`
- Tester manuellement avec curl
- Vérifier le `.env`

**Version : 1.0**  
**Date : Novembre 2024**
