import React, { useState, useEffect, useRef } from 'react';
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
  Modal,
} from 'react-native';
import * as Localization from 'expo-localization';
import { Ionicons } from '@expo/vector-icons';
import { CreditsService, BOOSTER_TIERS, type Transaction, type BoosterTier } from '../services/creditsService';
import { iapService, IAP_PRODUCT_IDS } from '../services/iapService';
import { isUserCancelledError } from 'react-native-iap';
import type { Product, Purchase } from 'react-native-iap';
import { useTranslation } from "react-i18next";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CacheService } from '../services/cacheService';
import { cacheKeyOutsiders } from './splash';
import { USER_VOTE_CACHE_KEY } from './person';

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || 'https://popular-app.onrender.com';

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
  const router = useRouter();
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  // Deep-link palier : /premium?tier=booster|super_booster|golden_booster.
  // Sans paramètre (les 6 points d'entrée historiques), selectedTier reste null
  // et l'écran se comporte exactement comme avant.
  const { tier: tierParam } = useLocalSearchParams<{ tier?: string }>();
  const scrollRef = useRef<ScrollView | null>(null);
  // Position verticale de chaque carte de palier, relevée à la volée (onLayout),
  // pour pouvoir faire défiler jusqu'au palier pré-sélectionné.
  const tierOffsets = useRef<Record<string, number>>({});
  const didAutoScroll = useRef(false);
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
  const [showPurchaseStep, setShowPurchaseStep] = useState(false);
  // Post-purchase name prompt (only when the user paid without a name)
  const [namePromptVisible, setNamePromptVisible] = useState(false);
  const [purchasedPersonId, setPurchasedPersonId] = useState<string | null>(null);
  const [postPurchaseName, setPostPurchaseName] = useState('');
  const [savingName, setSavingName] = useState(false);

  // Miroir des champs du formulaire, toujours à jour, lisible par le listener
  // d'achat (enregistré une seule fois au montage → sinon closure figée = valeurs vides).
  const latestForm = useRef({ name: '', email: '', instagram: '', tiktok: '', xAccount: '' });
  useEffect(() => {
    latestForm.current = { name, email, instagram, tiktok, xAccount };
  });   // pas de deps → resynchronisé après chaque commit, avant tout callback async

  useEffect(() => {
    loadHistory();
    initIAP();

    return () => {
      iapService.removeListeners();
    };
  }, []);

  // Flush des snapshots client d'un Outsider (re)boosté :
  //  - cacheKeyOutsiders() : la liste (TTL 60s) montre la carte à jour (nom + social)
  //  - person_${id}        : la fiche (TTL 2min) montre le social tout de suite
  //  - user_vote_${id}     : repart sur une activité récente VIERGE (Sujet 1) — on
  //    supprime UNIQUEMENT le vote rattaché à CET Outsider (cet id), jamais ceux
  //    posés sur d'autres profils. Affichage seulement : le vote réel est déjà chez
  //    le backend, le cache user_vote ne sert qu'à ré-afficher "Vous avez liké".
  const invalidateOutsiderCaches = async (personId?: string | null) => {
    await CacheService.remove(cacheKeyOutsiders());
    if (personId) {
      await CacheService.remove(`person_${personId}`);
      await CacheService.remove(USER_VOTE_CACHE_KEY(personId));
    }
  };

  // Deliver a single paid-but-undelivered purchase found in the store queue at startup.
  // No in-memory name/social is available on a replay (fresh mount), so we deliver under
  // the backend's provisional "Outsider" name; backend idempotency (R2) preserves the
  // original name if the boost already exists. Finishes the transaction ONLY on a confirmed
  // backend delivery — on any failure we leave it queued for the next launch.
  const deliverPendingBoost = async (purchase: Purchase) => {
    try {
      const tierId = iapService.getTierIdForProduct(purchase.productId);
      if (!tierId) {
        console.warn('[Premium] Catch-up: unknown product, skipping:', purchase.productId);
        return;
      }
      const receipt = purchase.purchaseToken;
      if (!receipt) {
        // No proof of purchase → cannot validate server-side. Leave it queued (unfinished).
        console.warn('[Premium] Catch-up: missing receipt, leaving transaction queued');
        return;
      }
      const result = await CreditsService.boostMyself('', tierId, undefined, undefined, receipt, Platform.OS);
      await invalidateOutsiderCaches(result?.person_id);
      await iapService.finishPurchase(purchase, true);
      console.log('[Premium] Catch-up delivered pending boost:', purchase.productId);
      await loadHistory();
    } catch (e) {
      // Still failing (offline, transient 5xx, or a residual permanent error such as
      // celebrity-name/ban — accepted out of scope). Leave the transaction in the store
      // queue; it will be retried on the next launch.
      console.warn('[Premium] Catch-up delivery deferred:', e);
    }
  };

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
      async (purchase: Purchase) => {
        console.log('[Premium] Purchase success:', purchase.productId);
        try {
          const form = latestForm.current;   // valeurs COURANTES, pas celles du montage
          const tierId = iapService.getTierIdForProduct(purchase.productId);
          if (!tierId) {
            console.error('[Premium] Unknown product:', purchase.productId);
            return;
          }

          // Get receipt for server-side validation.
          // react-native-iap v14 unifies the proof of purchase under purchaseToken
          // (iOS: StoreKit 2 JWS, Android: Play purchase token). transactionReceipt no
          // longer exists. The backend only requires a non-empty token (len >= 10), so
          // the JWS passes unchanged — see /boost-myself.
          const receipt = purchase.purchaseToken;

          if (!receipt) {
            Alert.alert(t('common.errorTitle'), t('premium.noReceiptError'));
            setPurchasing(false);
            return;
          }

          // R1: only send well-formed handles. A malformed handle is dropped here so it can
          // never make /boost-myself fail and strand a paid purchase; the user can add or
          // correct the link afterwards via the account edit screen. (The backend also
          // tolerates bad handles, but we avoid even sending them.)
          const socialLinks: any = {};
          if (form.instagram.trim() && isValidUsername('instagram', form.instagram)) socialLinks.instagram = form.instagram.trim().replace(/^@/, '');
          if (form.tiktok.trim() && isValidUsername('tiktok', form.tiktok)) socialLinks.tiktok = form.tiktok.trim().replace(/^@/, '');
          if (form.xAccount.trim() && isValidUsername('x', form.xAccount)) socialLinks.x = form.xAccount.trim().replace(/^@/, '');

          const result = await CreditsService.boostMyself(
            form.name.trim(),
            tierId,
            Object.keys(socialLinks).length > 0 ? socialLinks : undefined,
            form.email.trim() || undefined,
            receipt,
            Platform.OS,
          );

          // Sujet 2 + Sujet 1 : flush des caches DÈS le boost, pour LES DEUX
          // branches ci-dessous (nom rempli ET nom provisoire). Le social apparaît
          // immédiatement et le feed d'activité repart vierge.
          await invalidateOutsiderCaches(result?.person_id);

          // Finish the transaction (consumable) — required by Apple
          await iapService.finishPurchase(purchase, true);

          // When the user paid WITHOUT a name (backend returned name_provisional=true),
          // open the success name prompt so they can name themselves and see it in the
          // ranking right away. When the name was already filled → unchanged Alert (no
          // friction for the majority).
          const nameProvisional = !!result?.name_provisional;
          if (nameProvisional) {
            setPurchasedPersonId(result.person_id || null);
            setPostPurchaseName('');
            setNamePromptVisible(true);
          } else {
            Alert.alert(
              t('premium.boostActivated'),
              t('premium.boostActivatedMsg', { message: result.message, date: new Date(result.end_time).toLocaleString() }) + '\n\n' + t('premium.nameDelayNotice'),
            );
          }

          setName('');
          setEmail('');
          setInstagram('');
          setTiktok('');
          setXAccount('');
          setSelectedTier(null);
          await loadHistory();
        } catch (error: any) {
          console.error('[Premium] Post-purchase error:', error);
          // The Apple/Google payment already succeeded when we reach this listener, so a
          // failure here means "paid but delivery deferred", NOT "money lost". We did NOT
          // reach finishPurchase, so the transaction stays in the store queue and the
          // startup catch-up (getPendingPurchases → deliverPendingBoost) retries delivery
          // automatically. Show a reassuring message instead of an error.
          Alert.alert(t('premium.deliveryPendingTitle'), t('premium.deliveryPendingMsg'));
        } finally {
          setPurchasing(false);
        }
      },
      (error: any) => {
        console.error('[Premium] Purchase error:', error);
        if (!isUserCancelledError(error)) {
          Alert.alert(t('premium.purchaseFailed'), error.message || t('premium.purchaseErrorMsg'));
        }
        setPurchasing(false);
      },
    );

    // Catch-up (G1+G2): deliver any paid-but-undelivered transactions left in the store
    // queue (app killed mid-flight, lost response, or a prior deferred delivery). Backend
    // idempotency (R2) guarantees this never creates a duplicate boost. getPendingPurchases()
    // is read-only — it never finishes a transaction; deliverPendingBoost finishes only on a
    // confirmed delivery, otherwise the transaction stays queued for the next launch.
    try {
      const pending = await iapService.getPendingPurchases();
      for (const p of pending) {
        await deliverPendingBoost(p);
      }
    } catch (e) {
      console.warn('[Premium] Pending purchases catch-up failed:', e);
    }
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

  // Applique le palier reçu en paramètre, UNE seule fois et seulement s'il fait
  // partie des 3 ids connus : un lien forgé (?tier=nimportequoi) est ignoré,
  // jamais propagé à l'achat.
  useEffect(() => {
    if (!tierParam || didAutoScroll.current) return;
    if (!BOOSTER_TIERS.some((tr) => tr.id === tierParam)) return;
    didAutoScroll.current = true;
    setSelectedTier(tierParam);
    // Le défilement attend que les cartes aient été mesurées (onLayout).
    const timer = setTimeout(() => {
      const y = tierOffsets.current[tierParam];
      if (y != null) scrollRef.current?.scrollTo({ y: Math.max(0, y - 80), animated: true });
    }, 350);
    return () => clearTimeout(timer);
  }, [tierParam]);

  const handlePurchase = async () => {
    if (!selectedTier) {
      Alert.alert(t('premium.selectBooster'), t('premium.selectBoosterMsg'));
      return;
    }
    // Name is intentionally NOT required here (Apple 5.1.1(v) / 2.1(b)): the purchase
    // must always be able to start. A blank name is accepted and the backend assigns a
    // provisional "Outsider" display name (correctable later).
    // B (Chantier 3): instead of a dead-end "Connecting to Store" popup, lazily
    // ensure products are loaded (getStoreProducts now retries with backoff). On
    // success we continue the flow; on failure we show a clear, non-looping error.
    let effectiveProducts = storeProducts;
    if (!iapReady || effectiveProducts.length === 0) {
      setIapLoading(true);
      try {
        effectiveProducts = await iapService.getStoreProducts();
      } catch {
        effectiveProducts = [];
      }
      setIapLoading(false);
      if (effectiveProducts.length > 0) {
        setStoreProducts(effectiveProducts);
        setIapReady(true);
      } else {
        Alert.alert(
          t('premium.storeUnavailableTitle'),
          t('premium.storeUnavailableMsg'),
        );
        return;
      }
    }

    const tier = BOOSTER_TIERS.find(t => t.id === selectedTier);
    if (!tier) return;

    const durationLabel = getDurationLabel(tier.duration_hours, t);
    const productId = iapService.getProductIdForTier(selectedTier);

    // Use the real store price (from the freshly-ensured product list).
    // v14 Product exposes `id` (the SKU) and `displayPrice` (formatted); `productId`
    // and `localizedPrice` no longer exist on Product. Fallback = hardcoded tier price.
    const storeProduct = effectiveProducts.find(p => p.id === productId);
    const displayPrice = storeProduct?.displayPrice || `€${tier.price.toFixed(2)}`;

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
        `• ${name.trim().length >= 2
          ? t('premium.confirmAppear', { name: name.trim() })
          : t('premium.confirmAppearNoName')}\n` +
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
      if (!isUserCancelledError(error)) {
        Alert.alert(t('premium.purchaseError'), error.message || t('premium.purchaseErrorMsg'));
      }
      setPurchasing(false);
    }
  };

  // Post-purchase: save the chosen Outsider name, then send the user to the ranking
  // to see themselves immediately (cache invalidated so it's fresh, not 60s stale).
  const submitPostPurchaseName = async () => {
    const newName = postPurchaseName.trim();
    if (newName.length < 2) {
      Alert.alert(t('premium.nameRequired'), t('premium.nameRequiredMsg'));
      return;
    }
    if (!purchasedPersonId) {
      setNamePromptVisible(false);
      return;
    }
    setSavingName(true);
    try {
      const res = await CreditsService.setMyOutsiderName(purchasedPersonId, newName);
      // Re-flush APRÈS le renommage : le nom choisi (+ social) remplacent le
      // snapshot provisoire immédiatement. Même helper que le listener.
      await invalidateOutsiderCaches(purchasedPersonId);
      setNamePromptVisible(false);
      Alert.alert(t('premium.boostActivated'), t('premium.nameSavedMsg', { name: res.new_name }) + '\n\n' + t('premium.nameDelayNotice'));
      router.replace('/outsiders');
    } catch (error: any) {
      console.error('[Premium] Set name error:', error);
      Alert.alert(t('common.errorTitle'), error.message || t('premium.activateError'));
    } finally {
      setSavingName(false);
    }
  };

  // User chose to keep the provisional "Outsider" name for now (no easy self-rename
  // exists yet — admin corrects on request). Confirm the purchase succeeded.
  const keepOutsiderName = () => {
    setNamePromptVisible(false);
    Alert.alert(t('premium.boostActivated'), t('premium.setNameSubtitle') + '\n\n' + t('premium.nameDelayNotice'));
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
        <ScrollView
          ref={scrollRef}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.scrollContent}
        >
          <View style={styles.contentWrapper}>
          {/* Back button */}
          <TouchableOpacity
            onPress={() => router.back()}
            style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 }}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <Text style={{ color: PALETTE.text, fontSize: 24, fontWeight: '300', marginRight: 6 }}>{"<"}</Text>
            <Text style={{ color: PALETTE.text, fontSize: 14, fontWeight: '600' }}>{t("person.home")}</Text>
          </TouchableOpacity>
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
              {t("premium.securePayment", { store: Platform.OS === 'ios' ? 'Apple' : 'Google Play' })}
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
            const storeProduct = storeProducts.find((p: any) => p.id === productId);
            // Always show a price - use store price if available, otherwise fallback
            // v14: Product uses `id` (SKU) and `displayPrice` (formatted price).
            const displayPrice = storeProduct?.displayPrice || `€${tier.price.toFixed(2)}`;

            return (
              <TouchableOpacity
                key={tier.id}
                onLayout={(e) => {
                  tierOffsets.current[tier.id] = e.nativeEvent.layout.y;
                }}
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
                    // Name is optional — never block here (Apple 5.1.1(v)). A blank name
                    // is handled by the backend with a provisional "Outsider" name.
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
                              const storeProduct = storeProducts.find((p: any) => p.id === productId);
                              return storeProduct?.displayPrice || `€${BOOSTER_TIERS.find(bt => bt.id === selectedTier)?.price.toFixed(2)}`;
                            })()
                          })}
                        </Text>
                      </>
                    )}
                  </TouchableOpacity>

                  {/* Chantier 2 — Apple "no charge yet" reassurance (iOS only; Android shows it natively via Google Play UX) */}
                  {Platform.OS === 'ios' && (
                    <Text style={styles.noChargeYet}>{t("premium.noChargeYet")}</Text>
                  )}

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

      {/* Post-purchase name prompt — only shown when the user paid without a name */}
      <Modal
        visible={namePromptVisible}
        transparent
        animationType="fade"
        onRequestClose={keepOutsiderName}
      >
        <View style={styles.nameModalOverlay}>
          <View style={styles.nameModalCard}>
            <Ionicons name="sparkles" size={32} color={PALETTE.gold} style={{ alignSelf: 'center' }} />
            <Text style={styles.nameModalTitle}>{t('premium.setNameTitle')}</Text>
            <Text style={styles.nameModalSubtitle}>{t('premium.setNameSubtitle')}</Text>
            <TextInput
              style={styles.nameModalInput}
              placeholder={t('premium.yourName')}
              placeholderTextColor={PALETTE.subtext}
              value={postPurchaseName}
              onChangeText={setPostPurchaseName}
              autoCapitalize="words"
              autoFocus
            />
            <TouchableOpacity
              style={[styles.nameModalConfirm, savingName && { opacity: 0.6 }]}
              onPress={submitPostPurchaseName}
              disabled={savingName}
            >
              {savingName ? (
                <ActivityIndicator color="#000" />
              ) : (
                <Text style={styles.nameModalConfirmText}>{t('premium.validateName')}</Text>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.nameModalKeep}
              onPress={keepOutsiderName}
              disabled={savingName}
            >
              <Text style={styles.nameModalKeepText}>{t('premium.keepOutsider')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
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
  noChargeYet: {
    color: '#9FB5AB',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 8,
    paddingHorizontal: 16,
    lineHeight: 16,
  },
  // Post-purchase name prompt modal
  nameModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  nameModalCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    borderWidth: 2,
    borderColor: PALETTE.gold,
    padding: 24,
  },
  nameModalTitle: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
    textAlign: 'center',
    marginTop: 12,
  },
  nameModalSubtitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 16,
    lineHeight: 20,
  },
  nameModalInput: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: PALETTE.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  nameModalConfirm: {
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
  },
  nameModalConfirmText: {
    color: '#000',
    fontSize: 18,
    fontWeight: '700',
  },
  nameModalKeep: {
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  nameModalKeepText: {
    color: PALETTE.subtext,
    fontSize: 14,
    textDecorationLine: 'underline',
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
