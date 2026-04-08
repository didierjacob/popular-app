import React, { useState, useEffect } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Keyboard,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CreditsService, BOOSTER_TIERS, type Transaction, type BoosterTier } from '../services/creditsService';
import { iapService, IAP_PRODUCT_IDS } from '../services/iapService';
import type { Product, ProductPurchase } from 'react-native-iap';

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  green: "#2ECC71",
  gold: "#FFD700",
  border: "#2E6148",
  accent2: "#E04F5F",
};

const TIER_COLORS: Record<string, string> = {
  booster: "#2ECC71",
  super_booster: "#3498DB",
  golden_booster: "#FFD700",
};

const TIER_ICONS: Record<string, string> = {
  booster: "flash",
  super_booster: "rocket",
  golden_booster: "trophy",
};

function getDurationLabel(hours: number): string {
  if (hours === 1) return "1 hour";
  if (hours === 24) return "24 hours";
  if (hours === 168) return "1 week";
  return `${hours}h`;
}

export default function Premium() {
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [instagram, setInstagram] = useState('');
  const [twitter, setTwitter] = useState('');
  const [facebook, setFacebook] = useState('');
  const [purchasing, setPurchasing] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [storeProducts, setStoreProducts] = useState<Product[]>([]);
  const [iapReady, setIapReady] = useState(false);

  useEffect(() => {
    loadHistory();
    initIAP();

    return () => {
      iapService.removeListeners();
    };
  }, []);

  const initIAP = async () => {
    try {
      const connected = await iapService.init();
      if (connected) {
        const products = await iapService.getStoreProducts();
        setStoreProducts(products);
        setIapReady(true);
        console.log('[Premium] IAP ready, products:', products.length);
      }
    } catch (error) {
      console.error('[Premium] IAP init failed:', error);
    }

    // Setup purchase listeners
    iapService.setupListeners(
      async (purchase: ProductPurchase) => {
        console.log('[Premium] Purchase success:', purchase.productId);
        try {
          // Get the tier from the product ID
          const tierId = iapService.getTierIdForProduct(purchase.productId);
          if (!tierId) {
            console.error('[Premium] Unknown product:', purchase.productId);
            return;
          }

          // Get receipt for validation
          const receipt = Platform.OS === 'ios'
            ? purchase.transactionReceipt
            : purchase.purchaseToken;

          // Send to backend to validate and activate boost
          const socialLinks: any = {};
          if (instagram.trim()) socialLinks.instagram = instagram.trim();
          if (twitter.trim()) socialLinks.twitter = twitter.trim();
          if (facebook.trim()) socialLinks.facebook = facebook.trim();

          const result = await CreditsService.boostMyself(
            name.trim(),
            tierId,
            Object.keys(socialLinks).length > 0 ? socialLinks : undefined,
            email.trim() || undefined,
            receipt || undefined,
            Platform.OS,
          );

          // Finish the transaction (consumable)
          await iapService.finishPurchase(purchase, true);

          Alert.alert(
            '🎉 Boost Activated!',
            `${result.message}\n\nExpires: ${new Date(result.end_time).toLocaleString()}`,
          );

          // Reset form
          setName('');
          setEmail('');
          setInstagram('');
          setTwitter('');
          setFacebook('');
          setSelectedTier(null);
          await loadHistory();
        } catch (error: any) {
          console.error('[Premium] Post-purchase error:', error);
          Alert.alert('Error', error.message || 'Failed to activate boost');
        } finally {
          setPurchasing(false);
        }
      },
      (error: any) => {
        console.error('[Premium] Purchase error:', error);
        if (error.code !== 'E_USER_CANCELLED') {
          Alert.alert('Purchase Failed', error.message || 'An error occurred during purchase');
        }
        setPurchasing(false);
      },
    );
  };

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

  const handlePurchase = async () => {
    if (!selectedTier) {
      Alert.alert('Select a Booster', 'Please choose a booster tier first.');
      return;
    }
    if (!name.trim()) {
      Alert.alert('Name required', 'Please enter your name to appear on the Home page.');
      return;
    }

    const tier = BOOSTER_TIERS.find(t => t.id === selectedTier);
    if (!tier) return;

    const durationLabel = getDurationLabel(tier.duration_hours);
    const productId = iapService.getProductIdForTier(selectedTier);

    // Find the store product to show the real price
    const storeProduct = storeProducts.find(p => p.productId === productId);
    const displayPrice = storeProduct?.localizedPrice || `€${tier.price.toFixed(2)}`;

    Alert.alert(
      'Confirm Boost',
      `Activate ${tier.name} for ${displayPrice}?\n\n` +
      `• "${name.trim()}" will appear on the Home page\n` +
      `• Duration: ${durationLabel}\n` +
      `• Position: ${tier.position === 'top' ? 'Top (under Personality of the Day)' : 'Home page'}`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: `Buy ${displayPrice}`,
          onPress: async () => {
            Keyboard.dismiss();
            setPurchasing(true);
            try {
              await iapService.purchase(productId);
              // The purchase listener in initIAP will handle the rest
            } catch (error: any) {
              console.error('[Premium] Purchase initiation error:', error);
              Alert.alert('Error', error.message || 'Purchase failed');
              setPurchasing(false);
            }
          },
        },
      ]
    );
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView keyboardShouldPersistTaps="handled">
          {/* Header */}
          <View style={styles.header}>
            <Ionicons name="rocket" size={32} color={PALETTE.gold} />
            <Text style={styles.title}>Boost Yourself</Text>
          </View>

          {/* Hero */}
          <View style={styles.heroCard}>
            <Ionicons name="megaphone" size={48} color={PALETTE.gold} />
            <Text style={styles.heroTitle}>Get Noticed!</Text>
            <Text style={styles.heroText}>
              Purchase a Booster and your name will appear on the Home page for everyone to see.
            </Text>
          </View>

          {/* Tier Selection */}
          <Text style={styles.sectionTitle}>Choose Your Booster</Text>

          {BOOSTER_TIERS.map((tier) => {
            const isSelected = selectedTier === tier.id;
            const color = TIER_COLORS[tier.id] || PALETTE.gold;
            const iconName = TIER_ICONS[tier.id] || "flash";

            return (
              <TouchableOpacity
                key={tier.id}
                style={[
                  styles.tierCard,
                  isSelected && { borderColor: color, borderWidth: 2 },
                ]}
                onPress={() => setSelectedTier(tier.id)}
                activeOpacity={0.7}
              >
                {tier.id === 'golden_booster' && (
                  <View style={[styles.bestBadge, { backgroundColor: color }]}>
                    <Text style={styles.bestBadgeText}>BEST VALUE</Text>
                  </View>
                )}

                <View style={styles.tierHeader}>
                  <View style={styles.tierLeft}>
                    <View style={[styles.tierIconCircle, { backgroundColor: color + '20' }]}>
                      <Ionicons name={iconName as any} size={24} color={color} />
                    </View>
                    <View style={styles.tierInfo}>
                      <Text style={styles.tierName}>{tier.name}</Text>
                      <Text style={[styles.tierDuration, { color }]}>
                        {getDurationLabel(tier.duration_hours)}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.tierPriceBox}>
                    <Text style={styles.tierPrice}>€{tier.price.toFixed(2)}</Text>
                  </View>
                </View>

                <Text style={styles.tierDesc}>{tier.description}</Text>

                {tier.position === 'top' && (
                  <View style={styles.tierHighlight}>
                    <Ionicons name="star" size={14} color={PALETTE.gold} />
                    <Text style={styles.tierHighlightText}>
                      Appears at the top of the Home page + name in the ranking
                    </Text>
                  </View>
                )}

                {isSelected && (
                  <View style={[styles.selectedIndicator, { backgroundColor: color }]}>
                    <Ionicons name="checkmark" size={16} color="#000" />
                    <Text style={styles.selectedText}>Selected</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}

          {/* Form - Only show when a tier is selected */}
          {selectedTier && (
            <View style={styles.formSection}>
              <Text style={styles.sectionTitle}>Your Information</Text>

              <View style={styles.formCard}>
                <Text style={styles.inputLabel}>Your Name *</Text>
                <TextInput
                  style={styles.input}
                  placeholder="Enter your full name"
                  placeholderTextColor={PALETTE.subtext}
                  value={name}
                  onChangeText={setName}
                  autoCapitalize="words"
                />

                <Text style={styles.inputLabel}>Email (for confirmation)</Text>
                <TextInput
                  style={styles.input}
                  placeholder="your@email.com"
                  placeholderTextColor={PALETTE.subtext}
                  value={email}
                  onChangeText={setEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                />

                <Text style={[styles.inputLabel, { marginTop: 12 }]}>
                  Social Media (optional)
                </Text>

                <View style={styles.socialRow}>
                  <View style={[styles.socialIcon, { backgroundColor: '#E1306C20' }]}>
                    <Ionicons name="logo-instagram" size={18} color="#E1306C" />
                  </View>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    placeholder="@username"
                    placeholderTextColor={PALETTE.subtext}
                    value={instagram}
                    onChangeText={setInstagram}
                    autoCapitalize="none"
                  />
                </View>

                <View style={styles.socialRow}>
                  <View style={[styles.socialIcon, { backgroundColor: '#1DA1F220' }]}>
                    <Ionicons name="logo-twitter" size={18} color="#1DA1F2" />
                  </View>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    placeholder="@username"
                    placeholderTextColor={PALETTE.subtext}
                    value={twitter}
                    onChangeText={setTwitter}
                    autoCapitalize="none"
                  />
                </View>

                <View style={styles.socialRow}>
                  <View style={[styles.socialIcon, { backgroundColor: '#1877F220' }]}>
                    <Ionicons name="logo-facebook" size={18} color="#1877F2" />
                  </View>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    placeholder="Profile name or URL"
                    placeholderTextColor={PALETTE.subtext}
                    value={facebook}
                    onChangeText={setFacebook}
                    autoCapitalize="none"
                  />
                </View>
              </View>

              {/* Purchase Button */}
              <TouchableOpacity
                style={[
                  styles.purchaseButton,
                  { backgroundColor: TIER_COLORS[selectedTier] || PALETTE.gold },
                  purchasing && { opacity: 0.6 },
                ]}
                onPress={handlePurchase}
                disabled={purchasing}
              >
                {purchasing ? (
                  <ActivityIndicator color="#000" />
                ) : (
                  <>
                    <Ionicons name="flash" size={20} color="#000" />
                    <Text style={styles.purchaseButtonText}>
                      Activate Boost - €{BOOSTER_TIERS.find(t => t.id === selectedTier)?.price.toFixed(2)}
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* History Section */}
          <Text style={styles.sectionTitle}>History</Text>

          {loadingHistory ? (
            <View style={styles.card}>
              <ActivityIndicator size="small" color={PALETTE.gold} />
            </View>
          ) : transactions.length === 0 ? (
            <View style={styles.card}>
              <Text style={styles.emptyText}>No transactions yet</Text>
            </View>
          ) : (
            <View style={styles.card}>
              {transactions.map((t) => (
                <View key={t._id} style={styles.transactionRow}>
                  <View style={styles.transactionIcon}>
                    <Ionicons
                      name={t.type === 'purchase' ? 'rocket' : 'time'}
                      size={24}
                      color={t.type === 'purchase' ? PALETTE.green : PALETTE.subtext}
                    />
                  </View>
                  <View style={styles.transactionInfo}>
                    <Text style={styles.transactionDesc}>{t.description}</Text>
                    <Text style={styles.transactionDate}>{formatDate(t.timestamp)}</Text>
                  </View>
                  {t.price !== undefined && (
                    <Text style={[styles.transactionAmount, { color: PALETTE.green }]}>
                      €{t.price?.toFixed(2)}
                    </Text>
                  )}
                </View>
              ))}
            </View>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
  },
  title: { color: PALETTE.text, fontSize: 28, fontWeight: '700' },

  heroCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
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
    marginTop: 12,
    marginBottom: 8,
  },
  heroText: {
    color: PALETTE.text,
    fontSize: 15,
    textAlign: 'center',
    lineHeight: 22,
  },

  sectionTitle: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 12,
  },

  // Tier cards
  tierCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    position: 'relative',
  },
  bestBadge: {
    position: 'absolute',
    top: -10,
    right: 16,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  bestBadgeText: { color: '#000', fontSize: 10, fontWeight: '700' },
  tierHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  tierLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  tierIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tierInfo: {},
  tierName: { color: PALETTE.text, fontSize: 18, fontWeight: '700' },
  tierDuration: { fontSize: 14, fontWeight: '600', marginTop: 2 },
  tierPriceBox: { alignItems: 'flex-end' },
  tierPrice: { color: PALETTE.text, fontSize: 24, fontWeight: '700' },
  tierDesc: { color: PALETTE.subtext, fontSize: 14, marginTop: 4, marginBottom: 4 },
  tierHighlight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
    backgroundColor: PALETTE.gold + '15',
    padding: 8,
    borderRadius: 8,
  },
  tierHighlightText: { color: PALETTE.gold, fontSize: 12, fontWeight: '600', flex: 1 },
  selectedIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 12,
    paddingVertical: 8,
    borderRadius: 8,
  },
  selectedText: { color: '#000', fontWeight: '700', fontSize: 14 },

  // Form
  formSection: {},
  formCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  inputLabel: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 6,
  },
  input: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: PALETTE.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    marginBottom: 12,
  },
  socialRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 10,
  },
  socialIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },

  purchaseButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginTop: 16,
    paddingVertical: 16,
    borderRadius: 12,
  },
  purchaseButtonText: {
    color: '#000',
    fontSize: 18,
    fontWeight: '700',
  },

  // History
  card: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  emptyText: { color: PALETTE.subtext, fontSize: 14, textAlign: 'center' },
  transactionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  transactionIcon: { marginRight: 12 },
  transactionInfo: { flex: 1 },
  transactionDesc: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  transactionDate: { color: PALETTE.subtext, fontSize: 12, marginTop: 2 },
  transactionAmount: { fontSize: 16, fontWeight: '700' },
});
