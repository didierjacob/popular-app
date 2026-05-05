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
  Linking,
} from 'react-native';
import * as Localization from 'expo-localization';
import { Ionicons } from '@expo/vector-icons';
import { CreditsService, BOOSTER_TIERS, type Transaction, type BoosterTier } from '../services/creditsService';
import { iapService, IAP_PRODUCT_IDS } from '../services/iapService';
import type { Product, ProductPurchase } from 'react-native-iap';
import { useTranslation } from "react-i18next";

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';

/**
 * Returns the public URL for legal pages on popularoo.com
 * Language detection: FR → French version, all others → English (fallback)
 * V1.5 TODO: Add DE/ES/IT/PT-BR native translations
 */
function getLegalUrl(page: 'terms' | 'privacy' | 'legal-notice'): string {
  const locale = Localization.getLocales()?.[0]?.languageCode || 'en';
  const isFrench = locale === 'fr';
  // FR users → French pages, all others (EN/DE/ES/IT/PT) → English pages
  const pageMap: Record<string, { fr: string; en: string }> = {
    'terms': { fr: 'terms-fr.html', en: 'terms-en.html' },
    'privacy': { fr: 'privacy-fr.html', en: 'privacy-en.html' },
    'legal-notice': { fr: 'mentions-legales.html', en: 'legal-notice.html' },
  };
  const entry = pageMap[page];
  const filename = isFrench ? entry.fr : entry.en;
  return `https://popularoo.com/${filename}`;
}

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

function getDurationLabel(hours: number, t: any): string {
  if (hours === 1) return t("premium.duration_1h");
  if (hours === 24) return t("premium.duration_24h");
  if (hours === 168) return t("premium.duration_1w");
  return `${hours}h`;
}

// Map tier ID to translation key for description
const TIER_DESC_KEYS: Record<string, string> = {
  booster: "premium.boosterDesc",
  super_booster: "premium.superBoosterDesc",
  golden_booster: "premium.goldenBoosterDesc",
};

// Platform-specific username validation (Chantier 1I)
const SOCIAL_PATTERNS: Record<string, RegExp> = {
  instagram: /^[a-zA-Z0-9._]{1,30}$/,
  tiktok: /^[a-zA-Z0-9._]{2,24}$/,
  x: /^[a-zA-Z0-9_]{4,15}$/,
};

function isValidUsername(platform: string, value: string): boolean {
  const cleaned = value.trim().replace(/^@/, '');
  if (!cleaned) return true; // empty = valid (optional)
  const pattern = SOCIAL_PATTERNS[platform];
  return pattern ? pattern.test(cleaned) : false;
}

export default function Premium() {
  const { t } = useTranslation();
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [instagram, setInstagram] = useState('');
  const [tiktok, setTiktok] = useState('');
  const [xAccount, setXAccount] = useState('');
  const [purchasing, setPurchasing] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [storeProducts, setStoreProducts] = useState<Product[]>([]);
  const [iapReady, setIapReady] = useState(false);
  const [iapLoading, setIapLoading] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [showPurchaseStep, setShowPurchaseStep] = useState(false);

  useEffect(() => {
    loadHistory();
    initIAP();

    return () => {
      iapService.removeListeners();
    };
  }, []);

  const initIAP = async () => {
    setIapLoading(true);
    try {
      const connected = await iapService.init();
      if (connected) {
        const products = await iapService.getStoreProducts();
        setStoreProducts(products);
        if (products.length > 0) {
          setIapReady(true);
          console.log('[Premium] IAP ready, products:', products.length);
        } else {
          console.warn('[Premium] No IAP products found in store');
          setIapReady(false);
        }
      } else {
        setIapReady(false);
      }
    } catch (error) {
      console.error('[Premium] IAP init failed:', error);
      setIapReady(false);
    } finally {
      setIapLoading(false);
    }

    // Setup purchase listeners
    iapService.setupListeners(
      async (purchase: ProductPurchase) => {
        console.log('[Premium] Purchase success:', purchase.productId);
        try {
          const tierId = iapService.getTierIdForProduct(purchase.productId);
          if (!tierId) {
            console.error('[Premium] Unknown product:', purchase.productId);
            return;
          }

          // Get receipt for server-side validation
          const receipt = Platform.OS === 'ios'
            ? purchase.transactionReceipt
            : purchase.purchaseToken;

          if (!receipt) {
            Alert.alert(t('common.errorTitle'), t('premium.noReceiptError'));
            setPurchasing(false);
            return;
          }

          const socialLinks: any = {};
          if (instagram.trim()) socialLinks.instagram = instagram.trim().replace(/^@/, '');
          if (tiktok.trim()) socialLinks.tiktok = tiktok.trim().replace(/^@/, '');
          if (xAccount.trim()) socialLinks.x = xAccount.trim().replace(/^@/, '');

          const result = await CreditsService.boostMyself(
            name.trim(),
            tierId,
            Object.keys(socialLinks).length > 0 ? socialLinks : undefined,
            email.trim() || undefined,
            receipt,
            Platform.OS,
          );

          // Finish the transaction (consumable) — required by Apple
          await iapService.finishPurchase(purchase, true);

          Alert.alert(
            t('premium.boostActivated'),
            t('premium.boostActivatedMsg', { message: result.message, date: new Date(result.end_time).toLocaleString() }),
          );

          setName('');
          setEmail('');
          setInstagram('');
          setTiktok('');
          setXAccount('');
          setSelectedTier(null);
          await loadHistory();
        } catch (error: any) {
          console.error('[Premium] Post-purchase error:', error);
          Alert.alert(t('common.errorTitle'), error.message || t('premium.activateError'));
        } finally {
          setPurchasing(false);
        }
      },
      (error: any) => {
        console.error('[Premium] Purchase error:', error);
        if (error.code !== 'E_USER_CANCELLED') {
          Alert.alert(t('premium.purchaseFailed'), error.message || t('premium.purchaseErrorMsg'));
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
      Alert.alert(t('premium.selectBooster'), t('premium.selectBoosterMsg'));
      return;
    }
    if (!name.trim()) {
      Alert.alert(t('premium.nameRequired'), t('premium.nameRequiredMsg'));
      return;
    }
    if (!iapReady) {
      Alert.alert(
        t('premium.connectingStore'),
        t('premium.connectingStoreMsg'),
        [
          { text: t('premium.ok') },
          { text: t('premium.retry'), onPress: () => {
            // Try to reinitialize IAP
            iapService.getProducts().then((products: any) => {
              if (products && products.length > 0) {
                setStoreProducts(products);
                setIapReady(true);
              }
            }).catch(() => {});
          }},
        ]
      );
      return;
    }

    const tier = BOOSTER_TIERS.find(t => t.id === selectedTier);
    if (!tier) return;

    const durationLabel = getDurationLabel(tier.duration_hours, t);
    const productId = iapService.getProductIdForTier(selectedTier);

    // Use the real store price
    const storeProduct = storeProducts.find(p => p.productId === productId);
    const displayPrice = storeProduct?.localizedPrice || `€${tier.price.toFixed(2)}`;

    // B5: Check if user already has an active booster → show replacement warning
    const existingBoost = await CreditsService.getExistingActiveBoost();

    if (existingBoost) {
      // Format the end time of the active boost for display
      const endDate = new Date(existingBoost.end_time);
      const endDateStr = endDate.toLocaleString(undefined, {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });

      Alert.alert(
        t('premium.replaceTitle'),
        t('premium.replaceBody', {
          currentTier: existingBoost.tier_name,
          endDate: endDateStr,
        }) + `\n\n` +
        t('premium.replaceNewBooster', { tierName: tier.name, duration: durationLabel }) + `\n\n` +
        t('premium.withdrawalConsent'),
        [
          { text: t('premium.cancel'), style: 'cancel' },
          {
            text: t('premium.replaceContinue'),
            style: 'destructive',
            onPress: () => proceedWithPurchase(productId, displayPrice, tier),
          },
        ]
      );
    } else {
      // No existing boost — show standard confirmation
      Alert.alert(
        t('premium.confirmPurchase'),
        t('premium.confirmBody', { tierName: tier.name, price: displayPrice }) + `\n\n` +
        `• ${t('premium.confirmAppear', { name: name.trim() })}\n` +
        `• ${t('premium.confirmDuration', { duration: durationLabel })}\n` +
        (tier.id === 'golden_booster'
          ? `• ${t('premium.confirmGoldenExtra')}\n\n`
          : `\n`) +
        t('premium.confirmPaymentVia', { store: Platform.OS === 'ios' ? 'Apple' : 'Google' }) + `\n\n` +
        t('premium.withdrawalConsent'),
        [
          { text: t('premium.cancel'), style: 'cancel' },
          {
            text: t('premium.buyPrice', { price: displayPrice }),
            onPress: () => proceedWithPurchase(productId, displayPrice, tier),
          },
        ]
      );
    }
  };

  const proceedWithPurchase = async (productId: string, displayPrice: string, tier: BoosterTier) => {
    Keyboard.dismiss();
    setPurchasing(true);
    try {
      await iapService.purchase(productId);
      // The purchase listener in initIAP will handle the rest
    } catch (error: any) {
      console.error('[Premium] Purchase initiation error:', error);
      if (error?.code !== 'E_USER_CANCELLED') {
        Alert.alert(t('premium.purchaseError'), error.message || t('premium.purchaseErrorMsg'));
      }
      setPurchasing(false);
    }
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

  const handleRestorePurchases = async () => {
    setRestoring(true);
    try {
      const restored = await iapService.restorePurchases();
      if (restored.length > 0) {
        Alert.alert(
          t('premium.purchasesRestored'),
          t('premium.purchasesRestoredMsg', { count: restored.length }),
        );
        await loadHistory();
      } else {
        Alert.alert(
          t('premium.noPurchasesFound'),
          t('premium.noPurchasesFoundMsg'),
        );
      }
    } catch (error: any) {
      console.error('[Premium] Restore error:', error);
      Alert.alert(t('premium.restoreFailed'), error.message || t('premium.restoreFailedMsg'));
    } finally {
      setRestoring(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scrollContent}>
          <View style={styles.contentWrapper}>
          {/* Header */}
          <View style={styles.header}>
            <Ionicons name="rocket" size={32} color={PALETTE.gold} />
            <Text style={styles.title}>{t("premium.title")}</Text>
          </View>

          {/* Hero */}
          <View style={styles.heroCard}>
            <Ionicons name="megaphone" size={48} color={PALETTE.gold} />
            <Text style={styles.heroTitle}>{t("premium.subtitle")}</Text>
            <Text style={styles.heroText}>
              {t("premium.description")}
            </Text>
          </View>

          {/* Tier Selection */}
          <Text style={styles.sectionTitle}>{t("premium.chooseBooster")}</Text>

          {/* Payment notice */}
          <View style={styles.paymentNotice}>
            <Ionicons name="shield-checkmark" size={16} color={PALETTE.green} />
            <Text style={styles.paymentNoticeText}>
              {t("premium.securePayment")}
            </Text>
          </View>

          {iapLoading && (
            <View style={styles.iapLoadingContainer}>
              <ActivityIndicator size="small" color={PALETTE.gold} />
              <Text style={styles.iapLoadingText}>{t("premium.loadingPrices")}</Text>
            </View>
          )}

          {BOOSTER_TIERS.map((tier) => {
            const isSelected = selectedTier === tier.id;
            const color = TIER_COLORS[tier.id] || PALETTE.gold;
            const iconName = TIER_ICONS[tier.id] || "flash";
            const productId = iapService.getProductIdForTier(tier.id);
            const storeProduct = storeProducts.find((p: any) => p.productId === productId);
            // Always show a price - use store price if available, otherwise fallback
            const displayPrice = storeProduct?.localizedPrice || `€${tier.price.toFixed(2)}`;

            return (
              <TouchableOpacity
                key={tier.id}
                style={[
                  styles.tierCard,
                  isSelected && { borderColor: color, borderWidth: 2 },
                ]}
                onPress={() => {
                  setSelectedTier(tier.id);
                  setShowPurchaseStep(false);
                }}
                activeOpacity={0.7}
              >
                {tier.id === 'golden_booster' && (
                  <View style={[styles.bestBadge, { backgroundColor: color }]}>
                    <Text style={styles.bestBadgeText}>{t("premium.bestValue")}</Text>
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
                        {getDurationLabel(tier.duration_hours, t)}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.tierPriceBox}>
                    <Text style={styles.tierPrice}>{displayPrice}</Text>
                  </View>
                </View>

                <Text style={styles.tierDesc}>{t(TIER_DESC_KEYS[tier.id] || "premium.boosterDesc")}</Text>

                {tier.position === 'top' && (
                  <View style={styles.tierHighlight}>
                    <Ionicons name="star" size={14} color={PALETTE.gold} />
                    <Text style={styles.tierHighlightText}>
                      {t("premium.priorityFeature")}
                    </Text>
                  </View>
                )}

                {tier.id === 'golden_booster' && (
                  <View style={[styles.tierHighlight, { borderColor: PALETTE.gold + '40', backgroundColor: PALETTE.gold + '10' }]}>
                    <Ionicons name="trophy" size={14} color={PALETTE.gold} />
                    <Text style={[styles.tierHighlightText, { color: PALETTE.gold }]}>
                      {t("premium.goldenFeature")}
                    </Text>
                  </View>
                )}

                {isSelected && (
                  <View style={[styles.selectedIndicator, { backgroundColor: color }]}>
                    <Ionicons name="checkmark" size={16} color="#000" />
                    <Text style={styles.selectedText}>{t("premium.selected")}</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}

          {/* Form - Only show when a tier is selected */}
          {selectedTier && (
            <View style={styles.formSection}>
              <Text style={styles.sectionTitle}>{t("premium.yourInfo")}</Text>

              <View style={styles.formCard}>
                <Text style={styles.inputLabel}>{t("premium.yourName")}</Text>
                <TextInput
                  style={styles.input}
                  placeholder={t("premium.enterName")}
                  placeholderTextColor={PALETTE.subtext}
                  value={name}
                  onChangeText={setName}
                  autoCapitalize="words"
                />

                <Text style={styles.inputLabel}>{t("premium.email")}</Text>
                <TextInput
                  style={styles.input}
                  placeholder="your@email.com"
                  placeholderTextColor={PALETTE.subtext}
                  value={email}
                  onChangeText={setEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                />
              </View>

              {/* Social Accounts Configuration — Chantier 1I */}
              <View style={styles.socialSection}>
                <View style={styles.socialHeader}>
                  <Ionicons name="people-circle" size={28} color={PALETTE.gold} />
                  <Text style={styles.socialTitle}>{t("socialConfig.title")}</Text>
                </View>
                <Text style={styles.socialSubtitle}>{t("socialConfig.subtitle")}</Text>
                <Text style={styles.socialOptional}>{t("socialConfig.optional")}</Text>

                {/* Instagram field */}
                <View style={styles.socialInputRow}>
                  <View style={[styles.socialIconBadge, styles.instagramBadge]}>
                    <Ionicons name="logo-instagram" size={20} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <TextInput
                      style={[styles.socialInput, instagram.trim() && !isValidUsername('instagram', instagram) && styles.socialInputError]}
                      placeholder={t("socialConfig.placeholderInsta")}
                      placeholderTextColor={PALETTE.subtext}
                      value={instagram}
                      onChangeText={(text) => setInstagram(text.replace(/^@/, ''))}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  {instagram.trim() ? (
                    <View style={styles.validationBadge}>
                      {isValidUsername('instagram', instagram) ? (
                        <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />
                      ) : (
                        <Ionicons name="close-circle" size={22} color="#F44336" />
                      )}
                    </View>
                  ) : (
                    <View style={styles.validationBadge}>
                      <Ionicons name="ellipse-outline" size={20} color={PALETTE.subtext} />
                    </View>
                  )}
                </View>

                {/* TikTok field */}
                <View style={styles.socialInputRow}>
                  <View style={[styles.socialIconBadge, styles.tiktokBadge]}>
                    <Ionicons name="logo-tiktok" size={20} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <TextInput
                      style={[styles.socialInput, tiktok.trim() && !isValidUsername('tiktok', tiktok) && styles.socialInputError]}
                      placeholder={t("socialConfig.placeholderTiktok")}
                      placeholderTextColor={PALETTE.subtext}
                      value={tiktok}
                      onChangeText={(text) => setTiktok(text.replace(/^@/, ''))}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  {tiktok.trim() ? (
                    <View style={styles.validationBadge}>
                      {isValidUsername('tiktok', tiktok) ? (
                        <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />
                      ) : (
                        <Ionicons name="close-circle" size={22} color="#F44336" />
                      )}
                    </View>
                  ) : (
                    <View style={styles.validationBadge}>
                      <Ionicons name="ellipse-outline" size={20} color={PALETTE.subtext} />
                    </View>
                  )}
                </View>

                {/* X (Twitter) field */}
                <View style={styles.socialInputRow}>
                  <View style={[styles.socialIconBadge, styles.xBadge]}>
                    <Text style={{ color: '#fff', fontWeight: '800', fontSize: 16 }}>𝕏</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <TextInput
                      style={[styles.socialInput, xAccount.trim() && !isValidUsername('x', xAccount) && styles.socialInputError]}
                      placeholder={t("socialConfig.placeholderX")}
                      placeholderTextColor={PALETTE.subtext}
                      value={xAccount}
                      onChangeText={(text) => setXAccount(text.replace(/^@/, ''))}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  {xAccount.trim() ? (
                    <View style={styles.validationBadge}>
                      {isValidUsername('x', xAccount) ? (
                        <Ionicons name="checkmark-circle" size={22} color="#4CAF50" />
                      ) : (
                        <Ionicons name="close-circle" size={22} color="#F44336" />
                      )}
                    </View>
                  ) : (
                    <View style={styles.validationBadge}>
                      <Ionicons name="ellipse-outline" size={20} color={PALETTE.subtext} />
                    </View>
                  )}
                </View>

                <Text style={styles.socialEncouragement}>{t("socialConfig.encouragement")}</Text>
              </View>

              {/* Continue button — always active, acts as skip if no social accounts */}
              {!showPurchaseStep && (
                <TouchableOpacity
                  style={styles.continueButton}
                  onPress={() => {
                    if (!name.trim()) {
                      Alert.alert(t('premium.nameRequired'), t('premium.nameRequiredMsg'));
                      return;
                    }
                    Keyboard.dismiss();
                    setShowPurchaseStep(true);
                  }}
                  activeOpacity={0.7}
                >
                  <Text style={styles.continueButtonText}>{t("socialConfig.continue")}</Text>
                  <Ionicons name="arrow-forward" size={20} color="#000" />
                </TouchableOpacity>
              )}

              {/* Purchase Section — only shown after Continue */}
              {showPurchaseStep && (
                <View style={styles.purchaseSection}>
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
                        <Ionicons name={Platform.OS === 'ios' ? 'logo-apple' : 'logo-google-playstore'} size={20} color="#000" />
                        <Text style={styles.purchaseButtonText}>
                          {t("premium.buyVia", {
                            store: Platform.OS === 'ios' ? 'Apple' : 'Google',
                            price: (() => {
                              const productId = iapService.getProductIdForTier(selectedTier);
                              const storeProduct = storeProducts.find((p: any) => p.productId === productId);
                              return storeProduct?.localizedPrice || `€${BOOSTER_TIERS.find(bt => bt.id === selectedTier)?.price.toFixed(2)}`;
                            })()
                          })}
                        </Text>
                      </>
                    )}
                  </TouchableOpacity>

                  {/* Edit social links link */}
                  <TouchableOpacity
                    style={styles.editSocialLink}
                    onPress={() => setShowPurchaseStep(false)}
                  >
                    <Ionicons name="create-outline" size={16} color={PALETTE.subtext} />
                    <Text style={styles.editSocialLinkText}>{t("socialConfig.editSocial")}</Text>
                  </TouchableOpacity>

                  <Text style={styles.purchaseDisclaimer}>
                    {Platform.OS === 'ios'
                      ? 'Payment will be charged to your Apple ID account at the price displayed above when you confirm the purchase. This is a one-time, non-recurring purchase processed securely by Apple.'
                      : Platform.OS === 'android'
                      ? 'Payment will be charged to your Google account at the price displayed above when you confirm the purchase. This is a one-time, non-recurring purchase processed securely by Google Play.'
                      : 'Payment processed securely through the App Store or Google Play. One-time purchase, non-recurring.'}
                  </Text>
                </View>
              )}
            </View>
          )}

          {/* History Section */}
          <Text style={styles.sectionTitle}>{t("premium.historyTitle")}</Text>

          {loadingHistory ? (
            <View style={styles.card}>
              <ActivityIndicator size="small" color={PALETTE.gold} />
            </View>
          ) : transactions.length === 0 ? (
            <View style={styles.card}>
              <Text style={styles.emptyText}>{t("premium.noTransactions")}</Text>
            </View>
          ) : (
            <View style={styles.card}>
              {transactions.map((tx) => (
                <View key={tx._id} style={styles.transactionRow}>
                  <View style={styles.transactionIcon}>
                    <Ionicons
                      name={tx.type === 'purchase' ? 'rocket' : 'time'}
                      size={24}
                      color={tx.type === 'purchase' ? PALETTE.green : PALETTE.subtext}
                    />
                  </View>
                  <View style={styles.transactionInfo}>
                    <Text style={styles.transactionDesc}>{tx.description}</Text>
                    <Text style={styles.transactionDate}>{formatDate(tx.timestamp)}</Text>
                  </View>
                  {tx.price !== undefined && (
                    <Text style={[styles.transactionAmount, { color: PALETTE.green }]}>
                      €{tx.price?.toFixed(2)}
                    </Text>
                  )}
                </View>
              ))}
            </View>
          )}

          <View style={{ height: 40 }} />

          {/* Restore Purchases Button */}
          <TouchableOpacity
            style={styles.restoreButton}
            onPress={handleRestorePurchases}
            disabled={restoring}
          >
            {restoring ? (
              <ActivityIndicator size="small" color={PALETTE.accent2} />
            ) : (
              <>
                <Ionicons name="refresh-outline" size={18} color={PALETTE.accent2} />
                <Text style={styles.restoreButtonText}>{t("premium.restorePurchases")}</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Legal Links - Required by Apple */}
          <View style={styles.legalSection}>
            <TouchableOpacity onPress={() => Linking.openURL(getLegalUrl('terms'))}>
              <Text style={styles.legalLink}>{t("premium.termsOfUse")}</Text>
            </TouchableOpacity>
            <Text style={styles.legalSeparator}>|</Text>
            <TouchableOpacity onPress={() => Linking.openURL(getLegalUrl('privacy'))}>
              <Text style={styles.legalLink}>{t("premium.privacyPolicy")}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ height: 40 }} />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  scrollContent: {
    alignItems: 'center',
  },
  contentWrapper: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
  },
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

  // IAP Status
  iapLoadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginHorizontal: 16,
    marginTop: 16,
    paddingVertical: 16,
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  iapLoadingText: {
    color: PALETTE.subtext,
    fontSize: 14,
  },
  iapUnavailableContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginHorizontal: 16,
    marginTop: 16,
    paddingVertical: 16,
    paddingHorizontal: 16,
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.accent2,
  },
  iapUnavailableText: {
    color: PALETTE.accent2,
    fontSize: 14,
    flex: 1,
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
  restoreButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    marginHorizontal: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 12,
  },
  restoreButtonText: {
    color: PALETTE.accent2,
    fontSize: 15,
    fontWeight: '600',
  },
  legalSection: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginTop: 20,
    paddingHorizontal: 16,
  },
  legalLink: {
    color: PALETTE.subtext,
    fontSize: 13,
    textDecorationLine: 'underline',
  },
  legalSeparator: {
    color: PALETTE.subtext,
    fontSize: 13,
  },
  paymentNotice: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: PALETTE.green + '15',
    borderRadius: 8,
  },
  paymentNoticeText: {
    color: PALETTE.green,
    fontSize: 13,
    fontWeight: '500',
  },
  purchaseDisclaimer: {
    color: PALETTE.subtext,
    fontSize: 12,
    textAlign: 'center',
    marginTop: 10,
    paddingHorizontal: 16,
    lineHeight: 16,
  },
  // Social section styles (Chantier 1I)
  socialSection: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.gold + '40',
  },
  socialHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 4,
  },
  socialTitle: {
    color: PALETTE.gold,
    fontSize: 18,
    fontWeight: '700',
  },
  socialSubtitle: {
    color: PALETTE.text,
    fontSize: 14,
    marginBottom: 4,
    lineHeight: 20,
  },
  socialOptional: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontStyle: 'italic',
    marginBottom: 16,
  },
  socialInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  socialIconBadge: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  instagramBadge: {
    backgroundColor: '#C13584',
  },
  tiktokBadge: {
    backgroundColor: '#010101',
    borderWidth: 1,
    borderColor: '#25F4EE',
  },
  xBadge: {
    backgroundColor: '#000000',
    borderWidth: 1,
    borderColor: '#333',
  },
  socialInput: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 11,
    color: PALETTE.text,
    fontSize: 15,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  socialInputError: {
    borderColor: '#F44336',
  },
  validationBadge: {
    width: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  socialEncouragement: {
    color: PALETTE.subtext,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 18,
    fontStyle: 'italic',
  },
  continueButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginTop: 16,
    paddingVertical: 16,
    borderRadius: 12,
    backgroundColor: PALETTE.gold,
  },
  continueButtonText: {
    color: '#000',
    fontSize: 18,
    fontWeight: '700',
  },
  purchaseSection: {
    marginTop: 16,
  },
  editSocialLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 12,
    paddingVertical: 8,
  },
  editSocialLinkText: {
    color: PALETTE.subtext,
    fontSize: 13,
    textDecorationLine: 'underline',
  },
});
