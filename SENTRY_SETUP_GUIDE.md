# Sentry V1.0 — Guide d'intégration Popularoo

## Ce qui est déjà fait (côté code)

1. `@sentry/react-native` v8.10.0 installé
2. Plugin Sentry ajouté dans `app.json`
3. Initialisation conditionnelle dans `_layout.tsx` (si DSN présent → active, sinon → no-op)
4. Configuration production :
   - `tracesSampleRate: 0.2` (20% des transactions tracées)
   - `enableAutoSessionTracking: true`
   - `attachScreenshot: true` (capture l'écran lors d'un crash)

## Ce que tu dois faire (5 minutes)

### Étape 1 : Créer un projet Sentry

1. Va sur https://sentry.io et crée un compte gratuit (plan Developer = gratuit)
2. Crée une organisation : `popularoo`
3. Crée un projet :
   - Platform : **React Native**
   - Nom : `popularoo-mobile`
4. Copie le **DSN** (Client Keys → DSN)
   - Format : `https://xxxxx@oXXXXX.ingest.sentry.io/XXXXXXX`

### Étape 2 : Ajouter le DSN dans ton `.env` local

Dans le fichier `/frontend/.env` de ton projet local, ajoute :

```
EXPO_PUBLIC_SENTRY_DSN=https://ton-dsn-ici@oXXXXX.ingest.sentry.io/XXXXXXX
```

### Étape 3 : Rebuild

```bash
cd ~/Desktop/popular/frontend
npm install
npx eas build --platform ios --profile production
```

### Étape 4 : Vérification

Une fois l'app installée via TestFlight, tu verras dans le dashboard Sentry :
- Les sessions utilisateurs
- Les crashes avec stack traces
- Les screenshots au moment du crash

## Notes importantes

- **Sans DSN** : Sentry est désactivé silencieusement (pas d'erreur, pas d'impact perf)
- **Privacy Policy** : déjà couverte par la mention "services tiers de monitoring d'erreurs"
- **Coût** : Le plan Developer Sentry est gratuit (5000 événements/mois, largement suffisant pour V1.0)
- **Source Maps** : Pour les builds EAS production, les source maps sont automatiquement uploadées via le plugin `@sentry/react-native/expo`

## Configuration du plugin (app.json)

```json
[
  "@sentry/react-native/expo",
  {
    "organization": "popularoo",
    "project": "popularoo-mobile"
  }
]
```

> Note : L'upload des source maps nécessite un auth token Sentry.
> Lors du `eas build`, tu seras invité à le configurer via `SENTRY_AUTH_TOKEN`.
> Crée-le sur : https://sentry.io/settings/auth-tokens/
