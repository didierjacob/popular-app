# 💰 Guide de Monétisation - Application "Popularoo"

## Vue d'ensemble

L'application utilise un système de **crédits premium** qui permet aux utilisateurs d'acheter des votes avec un impact x100.

---

## 🎯 Fonctionnement

### Concept
- **1 crédit = 1 vote premium = 100 votes normaux**
- Prix : 5€ pour 1 crédit (pack Starter)
- Économies possibles sur les packs plus gros

### Grille Tarifaire

| Pack | Crédits | Prix | Équivalent votes | Prix/crédit | Économie |
|------|---------|------|------------------|-------------|----------|
| **Starter** | 1 | 5€ | 100 votes | 5€ | - |
| **Basic** | 5 | 20€ | 500 votes | 4€ | 5€ (20%) |
| **Pro** ⭐ | 10 | 35€ | 1,000 votes | 3.5€ | 15€ (30%) |
| **Elite** | 25 | 75€ | 2,500 votes | 3€ | 50€ (40%) |

---

## 📱 Guide Utilisateur

### 1. Accéder à la boutique
1. Ouvrir l'application "Popularoo"
2. Cliquer sur l'onglet **"Premium"** (icône diamant) en bas de l'écran
3. Voir votre solde actuel de crédits

### 2. Acheter des crédits
1. Dans l'onglet Premium, parcourir les 4 packs disponibles
2. Le pack **Pro** est recommandé (badge "POPULAIRE")
3. Cliquer sur le pack souhaité
4. Confirmer l'achat dans la popup
5. ✅ Crédits ajoutés instantanément à votre solde

**Note actuelle :** Le système est en mode simulation. Aucun paiement réel n'est effectué.

### 3. Utiliser un vote premium
1. Naviguer vers la page d'une personnalité
2. Si vous avez des crédits, une section **"Vote Premium x100"** apparaît
3. Activer le toggle (passe en doré)
4. Les boutons Like/Dislike deviennent dorés avec "x100"
5. Cliquer sur Like ou Dislike
6. Confirmer l'utilisation d'1 crédit
7. ✨ Vote appliqué avec impact x100 !
8. Confetti doré et message de confirmation

### 4. Consulter l'historique
1. Dans l'onglet Premium, faire défiler vers le bas
2. Section "Historique" affiche les 10 dernières transactions
3. Voir les achats et les utilisations de crédits

---

## 🔧 Configuration Technique

### Backend

**Endpoints disponibles :**
```bash
# Consulter le solde
GET /api/credits/balance/{user_id}

# Acheter des crédits
POST /api/credits/purchase
Body: {
  "user_id": "string",
  "pack": "starter|basic|pro|elite",
  "amount": number,
  "price": number
}

# Utiliser un crédit
POST /api/credits/use
Headers: { "user_id": "string" }
Body: {
  "person_id": "string",
  "person_name": "string",
  "vote": 1 ou -1,
  "multiplier": 100
}

# Historique
GET /api/credits/history/{user_id}?limit=20
```

**Collections MongoDB :**
- `user_credits` : Soldes des utilisateurs
- `credit_transactions` : Historique des transactions

### Frontend

**Services :**
- `/services/creditsService.ts` : Gestion des crédits
- Hook `useCredits()` pour l'état des crédits

**Pages :**
- `/app/premium.tsx` : Boutique et historique
- `/app/person.tsx` : Toggle et vote premium

---

## 🧪 Tests Manuels

### Test 1 : Achat de crédits
```bash
# Simuler un achat
curl -X POST http://localhost:8001/api/credits/purchase \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_001",
    "pack": "pro",
    "amount": 10,
    "price": 35.0
  }'

# Vérifier le solde
curl http://localhost:8001/api/credits/balance/test_user_001
```

**Résultat attendu :**
```json
{
  "success": true,
  "new_balance": 10,
  "message": "Successfully purchased 10 credit(s)!"
}
```

### Test 2 : Vote Premium
1. Ouvrir l'app et acheter des crédits
2. Aller sur une page personnalité
3. Activer le toggle premium
4. Voter (Like ou Dislike)
5. Vérifier que le score augmente/diminue de 100
6. Vérifier que le solde diminue de 1

### Test 3 : Historique
1. Effectuer plusieurs achats et votes
2. Ouvrir l'onglet Premium
3. Vérifier que toutes les transactions apparaissent
4. Vérifier les dates, montants et descriptions

---

## 💡 Cas d'usage

### Utilisateur Gratuit (Free)
- Vote normalement (+1/-1 par vote)
- Découvre les personnalités
- Consulte les classements
- Accède à toutes les fonctionnalités de base

### Utilisateur Premium
- Achète des crédits (pack Pro recommandé)
- Badge "Membre Premium" visible
- Peut utiliser des votes x100 pour :
  - Booster ses personnalités préférées
  - Influencer fortement le classement
  - Impacter rapidement les scores
- Accès aux statistiques avancées
- Export des votes (CSV/JSON)

### Exemple Concret
**Scénario : Soutenir une personnalité**
1. Jean aime beaucoup Ada Lovelace
2. Il achète le pack Pro (10 crédits = 35€)
3. Il active le vote premium sur sa page
4. Il clique "Like x100"
5. Le score d'Ada augmente de 100 points d'un coup ! 🚀
6. Ada grimpe dans le classement
7. Jean est satisfait, il a eu un impact réel

---

## 📊 Analytics Disponibles

### Pour les Utilisateurs
Dans l'onglet **"Mes votes"** :
- Nombre total de votes
- Série de votes (streaks)
- Badges débloqués
- Statistiques par catégorie
- Historique complet

### Pour les Administrateurs
Collections MongoDB à analyser :
- Volume d'achats par pack
- Taux de conversion free → premium
- Crédits utilisés vs non utilisés
- Personnalités les plus boostées
- Revenus par période

---

## 🚀 Passage en Production (Phase Future)

### Option : Intégration Stripe

**Prérequis :**
1. Créer un compte Stripe
2. Obtenir les clés API (test puis prod)
3. Configurer les webhooks

**Modifications nécessaires :**
```javascript
// Frontend: creditsService.ts
static async purchaseCredits(packId: string) {
  // Créer une PaymentIntent Stripe
  const paymentIntent = await createStripePaymentIntent(pack);
  
  // Rediriger vers la page de paiement
  const { error } = await stripe.redirectToCheckout({
    sessionId: paymentIntent.id
  });
  
  // Webhook valide le paiement
  // Backend ajoute les crédits après confirmation
}
```

**Temps d'implémentation : ~2-3 heures**

---

## 🔒 Sécurité

### Implémentations Actuelles
✅ Validation des packs côté serveur
✅ Vérification du solde avant utilisation
✅ Transactions atomiques (pas de perte de crédits)
✅ Logs de toutes les opérations
✅ user_id obligatoire

### Améliorations Futures
- [ ] Authentification JWT
- [ ] Rate limiting sur les endpoints
- [ ] Validation webhooks Stripe
- [ ] Chiffrement des données sensibles
- [ ] 2FA pour les gros achats

---

## 📈 Métriques de Succès

### KPIs à Suivre
- **Taux de conversion** : Free → Premium
- **Panier moyen** : Pack le plus acheté
- **Utilisation** : Crédits utilisés / achetés
- **Rétention** : Réachat après 30 jours
- **ARPU** : Revenu moyen par utilisateur

### Objectifs Recommandés
- 5% de conversion en premium (mois 1)
- 70% des crédits utilisés sous 7 jours
- Panier moyen : Pack Basic (20€)
- 30% de réachat à 30 jours

---

## 🎁 Idées de Promotions

### Promotions Possibles
1. **First Time** : -20% sur le premier achat
2. **Double Credits** : Week-end spécial 2x crédits
3. **Parrainage** : 5 crédits offerts par ami parrainé
4. **Streak Bonus** : Crédits offerts après X jours consécutifs
5. **Pack du Mois** : Nouveau pack limité chaque mois

---

## 💬 Support Utilisateur

### FAQ

**Q: Les paiements sont-ils sécurisés ?**
R: Actuellement en mode simulation. En production, Stripe assurera la sécurité PCI-DSS complète.

**Q: Puis-je être remboursé ?**
R: Les crédits ne sont pas remboursables une fois achetés (à définir en production).

**Q: Les crédits expirent-ils ?**
R: Non, les crédits n'ont pas de date d'expiration.

**Q: Puis-je transférer mes crédits ?**
R: Non, les crédits sont liés à votre compte.

**Q: Combien de temps les crédits restent-ils ?**
R: À vie ! Aucune expiration.

---

## ✅ Checklist de Lancement

### Avant Production
- [ ] Tests complets de tous les flux
- [ ] Intégration Stripe configurée
- [ ] Webhooks testés et validés
- [ ] Politique de remboursement définie
- [ ] CGV/CGU rédigées et validées
- [ ] Support client prêt
- [ ] Analytics configurés
- [ ] Tests de charge effectués

### Au Lancement
- [ ] Mode production activé
- [ ] Monitoring actif
- [ ] Support disponible 24/7
- [ ] Communication aux utilisateurs
- [ ] Promotion de lancement

---

## 🎉 État Actuel

**✅ Système 100% Fonctionnel en Mode Simulation**

- Backend : Opérationnel
- Frontend : Opérationnel
- Achats : Instantanés
- Votes Premium : Fonctionnels
- Historique : Complet
- UI/UX : Optimisée

**Prêt pour les tests utilisateurs !** 🚀

---

## 📞 Contact & Support

Pour toute question technique :
- Vérifier les logs backend : `/var/log/supervisor/backend.err.log`
- Vérifier les logs frontend : `/var/log/supervisor/expo.out.log`
- Tester les endpoints avec curl
- Consulter les collections MongoDB

---

**Version du document : 1.0**  
**Date : Novembre 2024**  
**Application : Popularoo - "Stock Market for People"**
