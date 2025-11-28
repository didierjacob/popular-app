import React, { useState, useEffect } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Alert, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useCredits, CREDIT_PACKS, CreditsService, type Transaction } from '../services/creditsService';

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  green: "#2ECC71",
  gold: "#FFD700",
  border: "#2E6148",
};

export default function Premium() {
  const { balance, isPremium, loading, purchaseCredits, refreshBalance } = useCredits();
  const [purchasing, setPurchasing] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const history = await CreditsService.getHistory(10);
      setTransactions(history);
    } catch (error) {
      console.error('Failed to load history:', error);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handlePurchase = async (packId: string) => {
    const pack = CREDIT_PACKS.find(p => p.id === packId);
    if (!pack) return;

    Alert.alert(
      'Confirmer l\'achat',
      `Acheter ${pack.credits} crédit${pack.credits > 1 ? 's' : ''} pour ${pack.price}€ ?\n\n(Simulation - Aucun paiement réel)`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Acheter',
          onPress: async () => {
            setPurchasing(true);
            try {
              const result = await purchaseCredits(packId);
              Alert.alert('Succès !', result.message);
              await loadHistory();
            } catch (error: any) {
              Alert.alert('Erreur', error.message || 'Échec de l\'achat');
            } finally {
              setPurchasing(false);
            }
          },
        },
      ]
    );
  };

  const handleBoostMyself = () => {
    if (Platform.OS === 'ios') {
      // iOS supports Alert.prompt
      Alert.prompt(
        'Boost Myself',
        'Entrez votre nom complet pour vous ajouter comme personnalité avec 100 votes (coûte 1 crédit) :',
        [
          { text: 'Annuler', style: 'cancel' },
          {
            text: 'Créer & Boost',
            onPress: async (name) => {
              if (name && name.trim()) {
                await processBoostMyself(name.trim());
              } else {
                Alert.alert('Erreur', 'Veuillez entrer un nom valide');
              }
            },
          },
        ],
        'plain-text'
      );
    } else {
      // Android doesn't support Alert.prompt, show a simple alert
      Alert.alert(
        'Boost Myself',
        'Cette fonctionnalité nécessite une saisie de texte.\n\nVous serez ajouté comme personnalité avec 100 votes pour 1 crédit.\n\nVeuillez saisir votre nom :',
        [
          { text: 'Annuler', style: 'cancel' },
          {
            text: 'Continuer',
            onPress: () => {
              // On Android, we'll use a default prompt
              // In a production app, you'd use a modal with TextInput
              Alert.prompt(
                'Votre Nom',
                'Entrez votre nom complet :',
                [
                  { text: 'Annuler', style: 'cancel' },
                  {
                    text: 'Créer',
                    onPress: async (name) => {
                      if (name && name.trim()) {
                        await processBoostMyself(name.trim());
                      }
                    },
                  },
                ]
              );
            },
          },
        ]
      );
    }
  };

  const processBoostMyself = async (name: string) => {
    setPurchasing(true);
    try {
      const result = await CreditsService.boostMyself(name);
      Alert.alert(
        '🎉 Succès !',
        `${result.message}\n\nVous avez maintenant ${result.new_balance} crédit${result.new_balance > 1 ? 's' : ''} restant${result.new_balance > 1 ? 's' : ''}.`,
        [{ text: 'OK' }]
      );
      await refreshBalance();
      await loadHistory();
    } catch (error: any) {
      const message = error.message || 'Échec de la création';
      Alert.alert('Erreur', message);
    } finally {
      setPurchasing(false);
    }
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView>
        {/* Header */}
        <View style={styles.header}>
          <Ionicons name="rocket" size={32} color={PALETTE.gold} />
          <Text style={styles.title}>Boosters</Text>
        </View>

        {/* Balance Card */}
        <View style={[styles.card, styles.balanceCard]}>
          <View style={styles.balanceHeader}>
            <Text style={styles.balanceLabel}>Your Votes</Text>
            <TouchableOpacity onPress={refreshBalance}>
              <Ionicons name="refresh" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
          <Text style={styles.balanceAmount}>{balance}</Text>
          <Text style={styles.balanceSubtext}>
            Available to boost personalities
          </Text>
          {isPremium && (
            <View style={styles.premiumBadge}>
              <Ionicons name="star" size={16} color={PALETTE.gold} />
              <Text style={styles.premiumBadgeText}>Premium Member</Text>
            </View>
          )}
        </View>

        {/* Hero Message */}
        <View style={styles.heroCard}>
          <Ionicons name="trophy" size={48} color={PALETTE.gold} />
          <Text style={styles.heroTitle}>Get to the Top!</Text>
          <Text style={styles.heroText}>
            Try to get into the top of the world's most popular personalities by buying boosters and super boosters
          </Text>
          
          {balance > 0 && (
            <TouchableOpacity 
              style={styles.boostMyselfButton}
              onPress={handleBoostMyself}
              disabled={purchasing}
            >
              <Ionicons name="person-add" size={20} color="#000" />
              <Text style={styles.boostMyselfText}>Boost Myself (1 crédit)</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Packs Section */}
        <Text style={styles.sectionTitle}>Buy Boosters</Text>
        
        {CREDIT_PACKS.map((pack) => (
          <TouchableOpacity
            key={pack.id}
            style={[
              styles.packCard,
              pack.popular && styles.packCardPopular,
            ]}
            onPress={() => handlePurchase(pack.id)}
            disabled={purchasing}
          >
            {pack.popular && (
              <View style={styles.popularBadge}>
                <Text style={styles.popularText}>POPULAIRE</Text>
              </View>
            )}
            
            <View style={styles.packHeader}>
              <View>
                <Text style={styles.packName}>{pack.name}</Text>
                <Text style={styles.packCredits}>
                  {pack.credits} votes
                </Text>
              </View>
              <View style={styles.packPriceContainer}>
                <Text style={styles.packPrice}>${pack.price}</Text>
              </View>
            </View>

            <View style={styles.packFooter}>
              <Text style={styles.packDetail}>
                Boost any personality instantly
              </Text>
              <Ionicons name="arrow-forward-circle" size={24} color={PALETTE.gold} />
            </View>
          </TouchableOpacity>
        ))}

        {/* History Section */}
        <Text style={styles.sectionTitle}>Historique</Text>
        
        {loadingHistory ? (
          <View style={styles.card}>
            <ActivityIndicator size="small" color={PALETTE.gold} />
          </View>
        ) : transactions.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.emptyText}>Aucune transaction</Text>
          </View>
        ) : (
          <View style={styles.card}>
            {transactions.map((t) => (
              <View key={t._id} style={styles.transactionRow}>
                <View style={styles.transactionIcon}>
                  <Ionicons
                    name={t.type === 'purchase' ? 'add-circle' : 'remove-circle'}
                    size={24}
                    color={t.type === 'purchase' ? PALETTE.green : PALETTE.accent}
                  />
                </View>
                <View style={styles.transactionInfo}>
                  <Text style={styles.transactionDesc}>{t.description}</Text>
                  <Text style={styles.transactionDate}>{formatDate(t.timestamp)}</Text>
                </View>
                <Text
                  style={[
                    styles.transactionAmount,
                    t.type === 'purchase' && styles.transactionAmountPositive,
                  ]}
                >
                  {t.type === 'purchase' ? '+' : ''}{t.amount}
                </Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
  },
  title: {
    color: PALETTE.text,
    fontSize: 28,
    fontWeight: '700',
  },
  card: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  balanceCard: {
    alignItems: 'center',
    borderColor: PALETTE.gold,
    borderWidth: 2,
  },
  balanceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  balanceLabel: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: '600',
  },
  balanceAmount: {
    color: PALETTE.gold,
    fontSize: 48,
    fontWeight: '700',
  },
  balanceSubtext: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 4,
  },
  heroCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 24,
    borderWidth: 2,
    borderColor: PALETTE.gold,
    alignItems: 'center',
  },
  heroTitle: {
    color: PALETTE.gold,
    fontSize: 24,
    fontWeight: '700',
    marginTop: 16,
    marginBottom: 8,
  },
  heroText: {
    color: PALETTE.text,
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 24,
  },
  premiumBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: PALETTE.gold + '20',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginTop: 12,
  },
  premiumBadgeText: {
    color: PALETTE.gold,
    fontSize: 12,
    fontWeight: '700',
  },
  cardTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 12,
  },
  infoText: {
    color: PALETTE.subtext,
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
  },
  sectionTitle: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 8,
  },
  packCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: PALETTE.border,
    position: 'relative',
  },
  packCardPopular: {
    borderColor: PALETTE.gold,
  },
  popularBadge: {
    position: 'absolute',
    top: -10,
    right: 16,
    backgroundColor: PALETTE.gold,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  popularText: {
    color: PALETTE.bg,
    fontSize: 10,
    fontWeight: '700',
  },
  packHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  packName: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
  },
  packCredits: {
    color: PALETTE.gold,
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  packPriceContainer: {
    alignItems: 'flex-end',
  },
  packPrice: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: '700',
  },
  packSavings: {
    color: PALETTE.green,
    fontSize: 12,
    fontWeight: '600',
    marginTop: 2,
  },
  packFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
  },
  packDetail: {
    color: PALETTE.subtext,
    fontSize: 14,
  },
  emptyText: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: 'center',
  },
  transactionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  transactionIcon: {
    marginRight: 12,
  },
  transactionInfo: {
    flex: 1,
  },
  transactionDesc: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
  },
  transactionDate: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  transactionAmount: {
    color: PALETTE.accent,
    fontSize: 16,
    fontWeight: '700',
  },
  transactionAmountPositive: {
    color: PALETTE.green,
  },
  boostMyselfButton: {
    backgroundColor: PALETTE.gold,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    paddingHorizontal: 24,
    borderRadius: 12,
    marginTop: 16,
    shadowColor: PALETTE.gold,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 5,
  },
  boostMyselfText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
});
