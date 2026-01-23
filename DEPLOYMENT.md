# 🚀 Guide de Déploiement - Popular App

## Prérequis Complétés
- [x] MongoDB Atlas configuré
- [x] Brevo SMTP configuré
- [x] Fichiers de déploiement créés

---

## Étape 1 : Déployer le Backend sur Render

### Option A : Déploiement automatique (recommandé)

1. Allez sur **https://render.com** et connectez-vous (GitHub recommandé)

2. Cliquez sur **"New" → "Web Service"**

3. Connectez votre repo GitHub ou utilisez **"Public Git repository"**

4. Configuration :
   - **Name** : `popular-api`
   - **Region** : Frankfurt (EU)
   - **Branch** : `main`
   - **Root Directory** : `backend`
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `uvicorn server:app --host 0.0.0.0 --port $PORT`

5. Cliquez **"Advanced"** et ajoutez les **Environment Variables** :

```
MONGO_URL = mongodb+srv://popular_admin:qJqQVK0hqGPlsaKw@cluster0.gvhxqbc.mongodb.net/popular_production?retryWrites=true&w=majority
DB_NAME = popular_production
SMTP_HOST = smtp-relay.brevo.com
SMTP_PORT = 587
SMTP_USER = a0b2e7001@smtp-brevo.com
SMTP_PASSWORD = ZfyDKRU8FJLrNpgM
SMTP_FROM_EMAIL = noreply@popular-app.com
SMTP_FROM_NAME = Popular App
REPORT_EMAIL = didier@coffeeandfilms.com
```

6. Cliquez **"Create Web Service"**

7. Attendez le déploiement (~5 minutes)

8. Votre API sera disponible sur : `https://popular-api.onrender.com`

---

## Étape 2 : Configurer l'App Mobile

Une fois le backend déployé, mettez à jour le frontend :

### Fichier : `/app/frontend/.env`
```
EXPO_PUBLIC_API_URL=https://popular-api.onrender.com
```

---

## Étape 3 : Tester le Déploiement

1. **Test API** :
```bash
curl https://popular-api.onrender.com/api/
```

2. **Test Stats** :
```bash
curl https://popular-api.onrender.com/api/admin/stats
```

3. **Test Email** (optionnel) :
```bash
curl -X POST "https://popular-api.onrender.com/api/send-daily-report?to_email=didier@coffeeandfilms.com"
```

---

## Étape 4 : Build de l'App Mobile

### Pour Android (APK) :
```bash
cd frontend
eas build --platform android --profile preview
```

### Pour iOS (IPA) :
```bash
cd frontend  
eas build --platform ios --profile preview
```

---

## Variables d'Environnement (Référence)

| Variable | Valeur | Description |
|----------|--------|-------------|
| MONGO_URL | mongodb+srv://... | Connection MongoDB Atlas |
| DB_NAME | popular_production | Nom de la base |
| SMTP_HOST | smtp-relay.brevo.com | Serveur Brevo |
| SMTP_PORT | 587 | Port SMTP |
| SMTP_USER | a0b2e7001@smtp-brevo.com | Login Brevo |
| SMTP_PASSWORD | *** | Clé API Brevo |
| SMTP_FROM_EMAIL | noreply@popular-app.com | Email expéditeur |
| REPORT_EMAIL | didier@coffeeandfilms.com | Destinataire rapports |

---

## Troubleshooting

### Le backend ne démarre pas
- Vérifiez les logs dans Render Dashboard
- Assurez-vous que MONGO_URL est correct

### Les emails ne s'envoient pas
- Vérifiez les credentials Brevo dans les variables d'environnement
- Testez avec l'endpoint `/api/send-daily-report`

### L'app mobile ne se connecte pas
- Vérifiez que EXPO_PUBLIC_API_URL pointe vers le bon URL Render
- Le backend doit être "Live" (vert) dans Render

---

## Coûts Estimés

| Service | Plan | Coût |
|---------|------|------|
| Render | Free | 0€ |
| MongoDB Atlas | M0 Free | 0€ |
| Brevo | Free (300 emails/jour) | 0€ |
| **Total** | | **0€/mois** |

⚠️ Note : Le plan gratuit Render met le service en veille après 15 min d'inactivité. Premier appel peut prendre ~30s.
