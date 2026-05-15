import React, { useState, useEffect, useCallback } from "react";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Alert,
  Linking,
  Platform,
  ActivityIndicator,
  Modal,
  KeyboardAvoidingView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { CreditsService, BOOSTER_TIERS, type Transaction } from "../services/creditsService";
import { useTranslation } from "react-i18next";
import { useRouter } from "expo-router";
import { setLanguage, LANGUAGE_STORAGE_KEY } from "../i18n";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  border: "#2E6148",
  gold: "#FFD700",
  green: "#2ECC71",
  danger: "#E04F5F",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;
const SUPPORT_EMAIL = "popularoo@popularoo.com";
const COUNTRY_KEY = "popular_user_country";
const USER_ID_KEY = "popular_user_id";
const DEVICE_KEY = "popularity_device_id";

// Social validation patterns
const SOCIAL_PATTERNS: Record<string, RegExp> = {
  instagram: /^[a-zA-Z0-9._]{1,30}$/,
  tiktok: /^[a-zA-Z0-9._]{2,24}$/,
  x: /^[a-zA-Z0-9_]{4,15}$/,
};
function isValidSocialUsername(platform: string, value: string): boolean {
  const cleaned = value.trim().replace(/^@/, "");
  if (!cleaned) return true;
  const pattern = SOCIAL_PATTERNS[platform];
  return pattern ? pattern.test(cleaned) : false;
}

// ---- Countries ----
const COUNTRIES = [
  { code: "FR", name: "France", flag: "🇫🇷" },
  { code: "GB", name: "UK", flag: "🇬🇧" },
  { code: "US", name: "United States", flag: "🇺🇸" },
  { code: "CA", name: "Canada", flag: "🇨🇦" },
  { code: "ES", name: "España", flag: "🇪🇸" },
  { code: "MX", name: "México", flag: "🇲🇽" },
  { code: "BR", name: "Brasil", flag: "🇧🇷" },
  { code: "AR", name: "Argentina", flag: "🇦🇷" },
  { code: "DE", name: "Deutschland", flag: "🇩🇪" },
  { code: "IT", name: "Italia", flag: "🇮🇹" },
  { code: "PT", name: "Portugal", flag: "🇵🇹" },
  { code: "AU", name: "Australia", flag: "🇦🇺" },
];

// ---- Languages ----
const LANGUAGES = [
  { code: "en", name: "English", flag: "🇬🇧" },
  { code: "fr", name: "Français", flag: "🇫🇷" },
  { code: "es", name: "Español", flag: "🇪🇸" },
  { code: "pt", name: "Português", flag: "🇧🇷" },
  { code: "de", name: "Deutsch", flag: "🇩🇪" },
  { code: "it", name: "Italiano", flag: "🇮🇹" },
];

// ---- Sub-screens ----
type Screen = "main" | "billing" | "help" | "mydata";

// ---- GDPR Data Shape ----
interface MyOutsiderData {
  found: boolean;
  person_id: string;
  name: string;
  category: string;
  source: string;
  score: number;
  likes: number;
  dislikes: number;
  superlikes: number;
  total_votes: number;
  boost_active: boolean;
  boost_tier: string;
  hours_remaining: number;
  boost_end_time: string | null;
}

interface GDPRData {
  device_id: string;
  email_on_file: string | null;
  data_summary: {
    votes: number;
    superlikes: number;
    boosters_purchased: number;
    transactions: number;
    daily_runs: number;
    has_settings: boolean;
    country: string | null;
    language: string | null;
  };
  legal_notice: string;
}

export default function AccountScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [screen, setScreen] = useState<Screen>("main");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingTx, setLoadingTx] = useState(false);

  // Language & Country (integrated from settings.tsx)
  const [selectedCountry, setSelectedCountry] = useState<string>("");
  const [selectedLanguage, setSelectedLanguage] = useState<string>(i18n.language || "en");
  const [saving, setSaving] = useState(false);

  // Social links state
  const [activeBoostId, setActiveBoostId] = useState<string | null>(null);
  const [socialModalVisible, setSocialModalVisible] = useState(false);
  const [editInsta, setEditInsta] = useState("");
  const [editTiktok, setEditTiktok] = useState("");
  const [editX, setEditX] = useState("");
  const [savingSocial, setSavingSocial] = useState(false);
  const [currentSocial, setCurrentSocial] = useState<{ instagram?: string; tiktok?: string; x?: string }>({});

  // GDPR data
  const [gdprData, setGdprData] = useState<GDPRData | null>(null);
  const [gdprLoading, setGdprLoading] = useState(false);
  const [gdprDeleting, setGdprDeleting] = useState(false);

  // My Outsider (Cas A — withdraw)
  const [myOutsider, setMyOutsider] = useState<MyOutsiderData | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);

  useEffect(() => {
    loadSavedPreferences();
    loadTransactions();
    loadActiveBoostSocial();
    loadMyOutsider();
  }, []);

  const loadSavedPreferences = async () => {
    try {
      const savedCountry = await AsyncStorage.getItem(COUNTRY_KEY);
      const savedLang = await AsyncStorage.getItem(LANGUAGE_STORAGE_KEY);
      if (savedCountry) setSelectedCountry(savedCountry);
      if (savedLang) setSelectedLanguage(savedLang);
    } catch (e) {
      console.error("Failed to load preferences:", e);
    }
  };

  const getUserId = useCallback(async () => {
    let userId = await AsyncStorage.getItem(USER_ID_KEY);
    if (!userId) {
      userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      await AsyncStorage.setItem(USER_ID_KEY, userId);
    }
    return userId;
  }, []);

  const getDeviceId = useCallback(async () => {
    let did = await AsyncStorage.getItem(DEVICE_KEY);
    if (!did) {
      did = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      await AsyncStorage.setItem(DEVICE_KEY, did);
    }
    return did;
  }, []);

  const handleCountrySelect = useCallback(async (code: string) => {
    setSelectedCountry(code);
    setSaving(true);
    try {
      await AsyncStorage.setItem(COUNTRY_KEY, code);
      const userId = await getUserId();
      await fetch(API("/user-settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: userId, country: code }),
      });
    } catch (e) {
      console.error("Failed to save country:", e);
    } finally {
      setSaving(false);
    }
  }, [getUserId]);

  const handleLanguageSelect = useCallback(async (code: string) => {
    setSelectedLanguage(code);
    setSaving(true);
    try {
      await setLanguage(code);
      const userId = await getUserId();
      await fetch(API("/user-settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: userId, language: code }),
      });
    } catch (e) {
      console.error("Failed to save language:", e);
    } finally {
      setSaving(false);
    }
  }, [getUserId]);

  const loadTransactions = useCallback(async () => {
    setLoadingTx(true);
    try {
      const history = await CreditsService.getHistory(50);
      setTransactions(history);
    } catch (e) {
      console.error("Failed to load transactions:", e);
    } finally {
      setLoadingTx(false);
    }
  }, []);

  const loadActiveBoostSocial = async () => {
    try {
      const data = await CreditsService.getActiveBoostDetails();
      if (data.boost_details && data.boost_details.length > 0) {
        const boost = data.boost_details[0];
        setActiveBoostId(boost.id);
        const social = boost.social_links || {};
        setCurrentSocial(social);
        setEditInsta(social.instagram || "");
        setEditTiktok(social.tiktok || "");
        setEditX(social.x || "");
      }
    } catch (e) {
      console.error("Failed to load active boost social:", e);
    }
  };

  const loadMyOutsider = useCallback(async () => {
    try {
      const data = await CreditsService.getMyOutsiderProfile();
      if (data && data.boost_active) {
        setMyOutsider(data as MyOutsiderData);
      } else {
        setMyOutsider(null);
      }
    } catch (e) {
      console.error("Failed to load my outsider:", e);
    }
  }, []);

  const handleWithdrawOutsider = useCallback(() => {
    Alert.alert(
      t("account.withdrawModalTitle"),
      t("account.withdrawModalBody"),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("account.withdrawConfirm"),
          style: "destructive",
          onPress: async () => {
            setWithdrawing(true);
            try {
              await CreditsService.deleteMyOutsiderProfile();
              setMyOutsider(null);
              setActiveBoostId(null);
              setCurrentSocial({});
              Alert.alert(t("common.success"), t("account.withdrawSuccess"));
            } catch (e: any) {
              Alert.alert(t("common.errorTitle"), e?.message || t("account.withdrawError"));
            } finally {
              setWithdrawing(false);
            }
          },
        },
      ]
    );
  }, [t]);

  const handleSaveSocial = async () => {
    if (!activeBoostId) return;
    setSavingSocial(true);
    try {
      const payload: any = {};
      if (editInsta.trim()) payload.instagram = editInsta.trim().replace(/^@/, "");
      if (editTiktok.trim()) payload.tiktok = editTiktok.trim().replace(/^@/, "");
      if (editX.trim()) payload.x = editX.trim().replace(/^@/, "");
      await CreditsService.updateSocialLinks(activeBoostId, payload);
      setCurrentSocial(payload);
      setSocialModalVisible(false);
      Alert.alert(t("socialConfig.editSocial"), "✓");
    } catch (e: any) {
      Alert.alert("Error", e.message || "Failed to update social links");
    } finally {
      setSavingSocial(false);
    }
  };

  // ---- GDPR: Fetch user data summary ----
  const loadGDPRData = useCallback(async () => {
    setGdprLoading(true);
    try {
      const did = await getDeviceId();
      const res = await fetch(API("/gdpr/my-data"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-ID": did },
      });
      if (res.ok) {
        const data = await res.json();
        setGdprData(data);
      }
    } catch (e) {
      console.error("Failed to load GDPR data:", e);
    } finally {
      setGdprLoading(false);
    }
  }, [getDeviceId]);

  // ---- GDPR: Delete user data ----
  const handleGDPRDelete = useCallback(async () => {
    Alert.alert(
      t("account.gdprDeleteConfirmTitle"),
      t("account.gdprDeleteConfirmMsg"),
      [
        { text: t("common.cancel"), style: "cancel" },
        {
          text: t("account.gdprDeleteConfirm"),
          style: "destructive",
          onPress: async () => {
            setGdprDeleting(true);
            try {
              const did = await getDeviceId();
              const res = await fetch(API("/gdpr/delete-my-data"), {
                method: "DELETE",
                headers: { "Content-Type": "application/json", "X-Device-ID": did },
                body: JSON.stringify({ confirm: true }),
              });
              if (res.ok) {
                const result = await res.json();
                Alert.alert(t("common.success"), t("account.gdprDeleteSuccess"));
                // Clear local storage
                await AsyncStorage.multiRemove([
                  DEVICE_KEY, USER_ID_KEY, COUNTRY_KEY, LANGUAGE_STORAGE_KEY,
                  "popular_my_votes", "popular_account_info",
                ]);
                // Reload data
                setGdprData(null);
                setScreen("main");
              } else {
                Alert.alert(t("common.errorTitle"), t("account.gdprDeleteError"));
              }
            } catch (e) {
              Alert.alert(t("common.errorTitle"), t("account.gdprDeleteError"));
            } finally {
              setGdprDeleting(false);
            }
          },
        },
      ]
    );
  }, [getDeviceId, t]);

  const contactSupport = () => {
    const subject = encodeURIComponent("Popularoo App — Support");
    const body = encodeURIComponent("Bonjour,\n\nJ'ai besoin d'aide avec :\n\n");
    Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`);
  };

  const formatDate = (timestamp: string) => {
    const d = new Date(timestamp);
    return d.toLocaleDateString("en-GB", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  };

  // ==================== BILLING SUB-SCREEN ====================
  if (screen === "billing") {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.subHeader}>
          <TouchableOpacity onPress={() => setScreen("main")} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <Text style={styles.subTitle}>{t("account.billingHistory")}</Text>
          <View style={{ width: 32 }} />
        </View>
        {loadingTx ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={PALETTE.accent2} />
          </View>
        ) : transactions.length === 0 ? (
          <View style={styles.center}>
            <Ionicons name="receipt-outline" size={64} color={PALETTE.border} />
            <Text style={styles.emptyText}>{t("account.noTransactions")}</Text>
          </View>
        ) : (
          <ScrollView style={{ flex: 1 }}>
            {transactions.map((tx, idx) => {
              const tierLabel = tx.pack === "golden_booster" ? "Golden Booster"
                : tx.pack === "super_booster" ? "Super Booster"
                : tx.pack === "booster" ? "Booster" : tx.pack || "—";
              return (
                <View key={tx._id || idx} style={styles.txCard}>
                  <View style={styles.txRow}>
                    <View style={[styles.txIcon, { backgroundColor: PALETTE.green + "20" }]}>
                      <Ionicons name="rocket" size={22} color={PALETTE.green} />
                    </View>
                    <View style={styles.txInfo}>
                      <Text style={styles.txTitle}>{tierLabel}</Text>
                      <Text style={styles.txDesc} numberOfLines={2}>{tx.description}</Text>
                      <Text style={styles.txDate}>{formatDate(tx.timestamp)}</Text>
                    </View>
                    {tx.price !== undefined && tx.price !== null && (
                      <Text style={styles.txPrice}>€{Number(tx.price).toFixed(2)}</Text>
                    )}
                  </View>
                </View>
              );
            })}
            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </SafeAreaView>
    );
  }

  // ==================== HELP CENTER SUB-SCREEN ====================
  if (screen === "help") {
    const FAQ = [
      { q: t("helpCenter.faq_whatIsPopularoo_q"), a: t("helpCenter.faq_whatIsPopularoo_a") },
      { q: t("helpCenter.faq_popularooIndex_q"), a: t("helpCenter.faq_popularooIndex_a") },
      { q: t("helpCenter.faq_superlike_q"), a: t("helpCenter.faq_superlike_a") },
      { q: t("helpCenter.faq_boosters_q"), a: t("helpCenter.faq_boosters_a") },
      { q: t("helpCenter.faq_vote_q"), a: t("helpCenter.faq_vote_a") },
      { q: t("helpCenter.faq_potd_q"), a: t("helpCenter.faq_potd_a") },
      { q: t("helpCenter.faq_addPerson_q"), a: t("helpCenter.faq_addPerson_a") },
      { q: t("helpCenter.faq_contact_q"), a: t("helpCenter.faq_contact_a", { email: SUPPORT_EMAIL }) },
      { q: t("helpCenter.faq_privacy_q"), a: t("helpCenter.faq_privacy_a") },
    ];
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.subHeader}>
          <TouchableOpacity onPress={() => setScreen("main")} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <Text style={styles.subTitle}>{t("helpCenter.title")}</Text>
          <View style={{ width: 32 }} />
        </View>
        <ScrollView style={{ flex: 1 }}>
          <View style={{ paddingHorizontal: 16, paddingTop: 8 }}>
            {FAQ.map((item, i) => (
              <FAQItem key={i} question={item.q} answer={item.a} />
            ))}
            <View style={styles.helpFooter}>
              <Text style={styles.helpFooterText}>{t("helpCenter.cantFind")}</Text>
              <TouchableOpacity style={styles.contactBtn} onPress={contactSupport}>
                <Ionicons name="mail-outline" size={18} color={PALETTE.text} />
                <Text style={styles.contactBtnText}>{t("helpCenter.contactSupport")}</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={{ height: 40 }} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ==================== MES DONNÉES (GDPR) SUB-SCREEN ====================
  if (screen === "mydata") {
    if (!gdprData && !gdprLoading) {
      loadGDPRData();
    }
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.subHeader}>
          <TouchableOpacity onPress={() => setScreen("main")} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <Text style={styles.subTitle}>{t("account.gdprTitle")}</Text>
          <View style={{ width: 32 }} />
        </View>

        {gdprLoading ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={PALETTE.accent2} />
            <Text style={[styles.emptyText, { marginTop: 12 }]}>{t("account.gdprLoading")}</Text>
          </View>
        ) : gdprData ? (
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}>
            {/* Data summary */}
            <View style={[styles.section, { marginTop: 16 }]}>
              <Text style={styles.sectionTitle}>{t("account.gdprSummary")}</Text>
              <View style={styles.card}>
                <DataRow label={t("account.gdprEmail")} value={gdprData.email_on_file || t("account.gdprNone")} />
                <DataRow label={t("account.gdprVotes")} value={String(gdprData.data_summary.votes)} />
                <DataRow label={t("account.gdprSuperlikes")} value={String(gdprData.data_summary.superlikes)} />
                <DataRow label={t("account.gdprBoosters")} value={String(gdprData.data_summary.boosters_purchased)} />
                <DataRow label={t("account.gdprTransactions")} value={String(gdprData.data_summary.transactions)} />
                <DataRow label={t("account.gdprDailyRuns")} value={String(gdprData.data_summary.daily_runs)} />
                <DataRow label={t("account.gdprCountry")} value={gdprData.data_summary.country || t("account.gdprNone")} />
                <DataRow label={t("account.gdprLanguage")} value={gdprData.data_summary.language || t("account.gdprNone")} />
              </View>
            </View>

            {/* Legal notice */}
            <View style={styles.section}>
              <View style={[styles.card, { backgroundColor: "#1C3A2C", borderColor: PALETTE.gold + "40" }]}>
                <Ionicons name="information-circle" size={20} color={PALETTE.gold} style={{ marginBottom: 6 }} />
                <Text style={{ color: PALETTE.subtext, fontSize: 12, lineHeight: 18 }}>
                  {t("account.gdprLegalNotice")}
                </Text>
              </View>
            </View>

            {/* Danger zone — Delete */}
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: PALETTE.danger }]}>
                {t("account.gdprDeleteTitle")}
              </Text>
              <View style={[styles.card, { borderColor: PALETTE.danger + "40" }]}>
                <Text style={{ color: PALETTE.subtext, fontSize: 13, lineHeight: 20, marginBottom: 8 }}>
                  {t("account.gdprDeleteDesc")}
                </Text>
                <Text style={{ color: PALETTE.accent2, fontSize: 12, lineHeight: 18, marginBottom: 16 }}>
                  {t("account.gdprDeleteWarning")}
                </Text>
                <TouchableOpacity
                  style={styles.dangerBtn}
                  onPress={handleGDPRDelete}
                  disabled={gdprDeleting}
                >
                  {gdprDeleting ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="trash" size={18} color="#FFF" />
                      <Text style={styles.dangerBtnText}>{t("account.gdprDeleteButton")}</Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </ScrollView>
        ) : (
          <View style={styles.center}>
            <Text style={styles.emptyText}>{t("account.gdprDeleteError")}</Text>
          </View>
        )}
      </SafeAreaView>
    );
  }

  // ==================== MAIN ACCOUNT SCREEN ====================
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: insets.bottom + 40 }}>
        {/* Header */}
        <View style={styles.header}>
          <Ionicons name="person-circle-outline" size={80} color={PALETTE.accent2} />
          <Text style={styles.title}>{t("account.title")}</Text>
          {saving && <ActivityIndicator size="small" color={PALETTE.green} style={{ marginTop: 6 }} />}
        </View>

        {/* ===== LANGUAGE SECTION (from old settings.tsx) ===== */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            <Ionicons name="language" size={16} color={PALETTE.subtext} /> {t("settings.languageSection")}
          </Text>
          <View style={styles.optionsGrid}>
            {LANGUAGES.map((lang) => {
              const isSelected = selectedLanguage === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[styles.optionCard, isSelected && styles.optionCardSelected]}
                  onPress={() => handleLanguageSelect(lang.code)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.optionFlag}>{lang.flag}</Text>
                  <Text style={[styles.optionName, isSelected && styles.optionNameSelected]} numberOfLines={1}>
                    {lang.name}
                  </Text>
                  {isSelected && <Ionicons name="checkmark-circle" size={20} color={PALETTE.green} />}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ===== COUNTRY SECTION (from old settings.tsx) ===== */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            <Ionicons name="globe" size={16} color={PALETTE.subtext} /> {t("settings.countrySection")}
          </Text>
          <Text style={styles.sectionDesc}>{t("settings.countryDesc")}</Text>
          <View style={styles.optionsGrid}>
            {COUNTRIES.map((country) => {
              const isSelected = selectedCountry === country.code;
              return (
                <TouchableOpacity
                  key={country.code}
                  style={[styles.optionCard, isSelected && styles.optionCardSelected]}
                  onPress={() => handleCountrySelect(country.code)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.optionFlag}>{country.flag}</Text>
                  <Text style={[styles.optionName, isSelected && styles.optionNameSelected]} numberOfLines={1}>
                    {country.name}
                  </Text>
                  {isSelected && <Ionicons name="checkmark-circle" size={20} color={PALETTE.green} />}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ===== MY BOOSTERS ===== */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("account.myBoosters")}</Text>
          <View style={styles.card}>
            <View style={styles.menuItem}>
              <Ionicons name="flash" size={24} color={PALETTE.gold} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>{t("account.activeBoosters")}</Text>
                <Text style={styles.menuItemSubtext}>{t("account.noActiveBooster")}</Text>
              </View>
              <TouchableOpacity style={styles.activateBtn} onPress={() => router.push("/premium")}>
                <Text style={styles.activateBtnText}>{t("account.activateBooster")}</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.divider} />
            <TouchableOpacity style={styles.menuItem} onPress={() => { loadTransactions(); setScreen("billing"); }}>
              <Ionicons name="receipt-outline" size={24} color={PALETTE.text} />
              <Text style={[styles.menuItemText, { flex: 1 }]}>{t("account.billingHistory")}</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
            <View style={styles.divider} />
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => {
                if (Platform.OS === "ios") {
                  Linking.openURL("https://apps.apple.com/account/subscriptions");
                } else {
                  Linking.openURL("https://play.google.com/store/account/subscriptions");
                }
              }}
            >
              <Ionicons name={Platform.OS === "ios" ? "logo-apple" : "logo-google-playstore"} size={24} color={PALETTE.text} />
              <Text style={[styles.menuItemText, { flex: 1 }]}>
                {Platform.OS === "ios" ? t("account.viewAppStoreHistory") : t("account.viewGooglePlayHistory")}
              </Text>
              <Ionicons name="open-outline" size={18} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* ===== MY OUTSIDER (Cas A — withdraw) ===== */}
        {myOutsider && myOutsider.boost_active && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>
              <Ionicons name="star" size={16} color={PALETTE.gold} /> {t("account.myOutsider")}
            </Text>
            <View style={styles.card}>
              <View style={moStyles.headerRow}>
                <Text style={moStyles.name} numberOfLines={1}>{myOutsider.name}</Text>
                <View style={moStyles.tierBadge}>
                  <Text style={moStyles.tierText}>
                    {BOOSTER_TIERS.find((b) => b.id === myOutsider.boost_tier)?.name || myOutsider.boost_tier}
                  </Text>
                </View>
              </View>
              <Text style={moStyles.timeLeft}>
                ⏱ {t("account.myOutsiderHoursLeft", { hours: myOutsider.hours_remaining.toFixed(1) })}
              </Text>
              <View style={moStyles.statsRow}>
                <View style={moStyles.statBox}>
                  <Text style={moStyles.statValue}>{myOutsider.likes ?? 0}</Text>
                  <Text style={moStyles.statLabel}>{t("account.myOutsiderLikes")}</Text>
                </View>
                <View style={moStyles.statBox}>
                  <Text style={moStyles.statValue}>{myOutsider.dislikes ?? 0}</Text>
                  <Text style={moStyles.statLabel}>{t("account.myOutsiderDislikes")}</Text>
                </View>
                <View style={moStyles.statBox}>
                  <Text style={moStyles.statValue}>{myOutsider.score ?? 0}</Text>
                  <Text style={moStyles.statLabel}>{t("account.myOutsiderScore")}</Text>
                </View>
              </View>
              <TouchableOpacity
                style={[styles.dangerBtn, { marginTop: 16 }]}
                onPress={handleWithdrawOutsider}
                disabled={withdrawing}
              >
                {withdrawing ? (
                  <ActivityIndicator color="#FFF" />
                ) : (
                  <>
                    <Ionicons name="exit-outline" size={18} color="#FFF" />
                    <Text style={styles.dangerBtnText}>{t("account.withdrawButton")}</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ===== SOCIAL ACCOUNTS ===== */}
        {activeBoostId && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{t("socialConfig.editSocial")}</Text>
            <View style={styles.card}>
              {(currentSocial.instagram || currentSocial.tiktok || currentSocial.x) ? (
                <View style={{ paddingTop: 4 }}>
                  {currentSocial.instagram && (
                    <View style={scStyles.socialRow}>
                      <View style={[scStyles.socialBadge, { backgroundColor: "#C13584" }]}>
                        <Ionicons name="logo-instagram" size={16} color="#fff" />
                      </View>
                      <Text style={scStyles.socialHandle}>@{currentSocial.instagram}</Text>
                      <Ionicons name="checkmark-circle" size={18} color="#4CAF50" />
                    </View>
                  )}
                  {currentSocial.tiktok && (
                    <View style={scStyles.socialRow}>
                      <View style={[scStyles.socialBadge, { backgroundColor: "#010101", borderWidth: 1, borderColor: "#25F4EE" }]}>
                        <Ionicons name="logo-tiktok" size={16} color="#fff" />
                      </View>
                      <Text style={scStyles.socialHandle}>@{currentSocial.tiktok}</Text>
                      <Ionicons name="checkmark-circle" size={18} color="#4CAF50" />
                    </View>
                  )}
                  {currentSocial.x && (
                    <View style={scStyles.socialRow}>
                      <View style={[scStyles.socialBadge, { backgroundColor: "#000", borderWidth: 1, borderColor: "#333" }]}>
                        <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>𝕏</Text>
                      </View>
                      <Text style={scStyles.socialHandle}>@{currentSocial.x}</Text>
                      <Ionicons name="checkmark-circle" size={18} color="#4CAF50" />
                    </View>
                  )}
                </View>
              ) : (
                <Text style={{ color: PALETTE.subtext, fontSize: 13, fontStyle: "italic" }}>
                  {t("socialConfig.optional")}
                </Text>
              )}
              <TouchableOpacity
                style={scStyles.editBtn}
                onPress={() => {
                  setEditInsta(currentSocial.instagram || "");
                  setEditTiktok(currentSocial.tiktok || "");
                  setEditX(currentSocial.x || "");
                  setSocialModalVisible(true);
                }}
              >
                <Ionicons name="create-outline" size={20} color={PALETTE.gold} />
                <Text style={scStyles.editBtnText}>{t("socialConfig.editSocial")}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ===== SUPPORT ===== */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("account.support")}</Text>
          <View style={styles.card}>
            <TouchableOpacity style={styles.menuItem} onPress={() => setScreen("help")}>
              <Ionicons name="help-circle-outline" size={24} color={PALETTE.text} />
              <Text style={styles.menuItemText}>{t("account.helpCenter")}</Text>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
            <View style={styles.divider} />
            <TouchableOpacity style={styles.menuItem} onPress={contactSupport}>
              <Ionicons name="mail-outline" size={24} color={PALETTE.text} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>{t("account.contactUs")}</Text>
                <Text style={styles.menuItemSubtext}>{SUPPORT_EMAIL}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* ===== MES DONNÉES (GDPR) ===== */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("account.myData")}</Text>
          <View style={styles.card}>
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => { setGdprData(null); setScreen("mydata"); }}
            >
              <Ionicons name="shield-checkmark-outline" size={24} color={PALETTE.text} />
              <View style={{ flex: 1 }}>
                <Text style={styles.menuItemText}>{t("account.gdprTitle")}</Text>
                <Text style={styles.menuItemSubtext}>{t("account.myDataDesc")}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
            </TouchableOpacity>
            <View style={styles.divider} />
            <TouchableOpacity
              style={styles.menuItem}
              onPress={() => {
                const url = `https://www.popularoo.com/terms-${selectedLanguage || "en"}.html`;
                Linking.openURL(url).catch(() => {
                  Linking.openURL("https://www.popularoo.com/terms-en.html").catch(() => {});
                });
              }}
            >
              <Ionicons name="document-text-outline" size={24} color={PALETTE.text} />
              <Text style={[styles.menuItemText, { flex: 1 }]}>CGU / Terms of Service</Text>
              <Ionicons name="open-outline" size={18} color={PALETTE.subtext} />
            </TouchableOpacity>
          </View>
        </View>

        {/* ===== APP INFO ===== */}
        <View style={[styles.section, { marginBottom: 20 }]}>
          <View style={styles.appInfo}>
            <Text style={styles.appVersion}>{t("account.appVersion")}</Text>
            <Text style={styles.appCopyright}>{t("account.copyright")}</Text>
          </View>
        </View>
      </ScrollView>

      {/* ===== Social Edit Modal ===== */}
      <Modal
        visible={socialModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setSocialModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={{ flex: 1 }}
        >
          <View style={scStyles.modalOverlay}>
            <View style={scStyles.modalContent}>
              <View style={scStyles.modalHeader}>
                <Text style={scStyles.modalTitle}>{t("socialConfig.editSocial")}</Text>
                <TouchableOpacity onPress={() => setSocialModalVisible(false)}>
                  <Ionicons name="close" size={24} color={PALETTE.text} />
                </TouchableOpacity>
              </View>
              <Text style={scStyles.modalHint}>{t("socialConfig.optional")}</Text>

              {/* Instagram */}
              <View style={scStyles.inputRow}>
                <View style={[scStyles.iconBadge, { backgroundColor: "#C13584" }]}>
                  <Ionicons name="logo-instagram" size={20} color="#fff" />
                </View>
                <TextInput
                  style={[scStyles.input, editInsta.trim() && !isValidSocialUsername("instagram", editInsta) && scStyles.inputError]}
                  placeholder={t("socialConfig.placeholderInsta")}
                  placeholderTextColor={PALETTE.subtext}
                  value={editInsta}
                  onChangeText={(text) => setEditInsta(text.replace(/^@/, ""))}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              {/* TikTok */}
              <View style={scStyles.inputRow}>
                <View style={[scStyles.iconBadge, { backgroundColor: "#010101", borderWidth: 1, borderColor: "#25F4EE" }]}>
                  <Ionicons name="logo-tiktok" size={20} color="#fff" />
                </View>
                <TextInput
                  style={[scStyles.input, editTiktok.trim() && !isValidSocialUsername("tiktok", editTiktok) && scStyles.inputError]}
                  placeholder={t("socialConfig.placeholderTiktok")}
                  placeholderTextColor={PALETTE.subtext}
                  value={editTiktok}
                  onChangeText={(text) => setEditTiktok(text.replace(/^@/, ""))}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              {/* X */}
              <View style={scStyles.inputRow}>
                <View style={[scStyles.iconBadge, { backgroundColor: "#000", borderWidth: 1, borderColor: "#333" }]}>
                  <Text style={{ color: "#fff", fontWeight: "800", fontSize: 16 }}>𝕏</Text>
                </View>
                <TextInput
                  style={[scStyles.input, editX.trim() && !isValidSocialUsername("x", editX) && scStyles.inputError]}
                  placeholder={t("socialConfig.placeholderX")}
                  placeholderTextColor={PALETTE.subtext}
                  value={editX}
                  onChangeText={(text) => setEditX(text.replace(/^@/, ""))}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <TouchableOpacity
                style={[scStyles.saveBtn, savingSocial && { opacity: 0.6 }]}
                onPress={handleSaveSocial}
                disabled={savingSocial}
              >
                {savingSocial ? (
                  <ActivityIndicator color="#000" />
                ) : (
                  <Text style={scStyles.saveBtnText}>{t("common.save")}</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

// ---- Helper Components ----
function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: PALETTE.border }}>
      <Text style={{ color: PALETTE.subtext, fontSize: 14 }}>{label}</Text>
      <Text style={{ color: PALETTE.text, fontSize: 14, fontWeight: "600" }}>{value}</Text>
    </View>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <TouchableOpacity style={styles.faqCard} onPress={() => setOpen(!open)} activeOpacity={0.7}>
      <View style={styles.faqHeader}>
        <Text style={styles.faqQuestion}>{question}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={PALETTE.subtext} />
      </View>
      {open && <Text style={styles.faqAnswer}>{answer}</Text>}
    </TouchableOpacity>
  );
}

// ---- Styles ----
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  header: { alignItems: "center", paddingVertical: 24 },
  title: { fontSize: 24, fontWeight: "700", color: PALETTE.text, marginTop: 12 },
  subHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: PALETTE.border,
  },
  backBtn: { width: 32, padding: 4 },
  subTitle: { fontSize: 18, fontWeight: "700", color: PALETTE.text },
  section: { marginTop: 16, paddingHorizontal: 16 },
  sectionTitle: { fontSize: 16, fontWeight: "600", color: PALETTE.subtext, marginBottom: 10 },
  sectionDesc: { fontSize: 12, color: PALETTE.subtext, marginBottom: 12, lineHeight: 16 },
  card: {
    backgroundColor: PALETTE.card, borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: PALETTE.border,
  },
  divider: { height: 1, backgroundColor: PALETTE.border, marginVertical: 4 },
  menuItem: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 12 },
  menuItemText: { flex: 1, fontSize: 16, color: PALETTE.text },
  menuItemSubtext: { fontSize: 12, color: PALETTE.subtext, marginTop: 2 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 80 },
  emptyText: { color: PALETTE.text, fontSize: 18, fontWeight: "600", marginTop: 16 },

  // Options grid (Language/Country)
  optionsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  optionCard: {
    flexDirection: "row", alignItems: "center", backgroundColor: PALETTE.card,
    borderRadius: 12, paddingVertical: 12, paddingHorizontal: 14,
    borderWidth: 1.5, borderColor: PALETTE.border, minWidth: "47%", flex: 1, maxWidth: "49%",
  },
  optionCardSelected: { borderColor: PALETTE.green, backgroundColor: PALETTE.green + "15" },
  optionFlag: { fontSize: 22, marginRight: 10 },
  optionName: { fontSize: 14, fontWeight: "600", color: PALETTE.text, flex: 1 },
  optionNameSelected: { color: PALETTE.green },

  // Boosters
  activateBtn: { backgroundColor: PALETTE.accent2, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  activateBtnText: { color: "#FFF", fontSize: 12, fontWeight: "700" },

  // Transactions
  txCard: {
    backgroundColor: PALETTE.card, marginHorizontal: 16, marginTop: 10,
    borderRadius: 12, padding: 14, borderWidth: 1, borderColor: PALETTE.border,
  },
  txRow: { flexDirection: "row", alignItems: "center" },
  txIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", marginRight: 12 },
  txInfo: { flex: 1 },
  txTitle: { color: PALETTE.text, fontSize: 16, fontWeight: "700" },
  txDesc: { color: PALETTE.subtext, fontSize: 13, marginTop: 2 },
  txDate: { color: PALETTE.subtext, fontSize: 12, marginTop: 4 },
  txPrice: { color: PALETTE.green, fontSize: 18, fontWeight: "700" },

  // FAQ
  faqCard: {
    backgroundColor: PALETTE.card, borderRadius: 12, padding: 16,
    marginBottom: 10, borderWidth: 1, borderColor: PALETTE.border,
  },
  faqHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  faqQuestion: { color: PALETTE.text, fontSize: 15, fontWeight: "600", flex: 1, marginRight: 8 },
  faqAnswer: { color: PALETTE.subtext, fontSize: 14, lineHeight: 22, marginTop: 12 },

  // App info
  appInfo: { alignItems: "center", paddingVertical: 20 },
  appVersion: { fontSize: 14, color: PALETTE.subtext },
  appCopyright: { fontSize: 12, color: PALETTE.subtext, marginTop: 4 },

  // Help footer
  helpFooter: { alignItems: "center", marginTop: 20, paddingVertical: 20 },
  helpFooterText: { color: PALETTE.subtext, fontSize: 14, marginBottom: 12 },
  contactBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: PALETTE.accent, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 8,
  },
  contactBtnText: { color: PALETTE.text, fontSize: 16, fontWeight: "600" },

  // GDPR Danger button
  dangerBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: PALETTE.danger, borderRadius: 12, paddingVertical: 14,
  },
  dangerBtnText: { color: "#FFF", fontSize: 16, fontWeight: "700" },
});

// My Outsider styles (Cas A)
const moStyles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  name: { flex: 1, color: PALETTE.text, fontSize: 18, fontWeight: "700", marginRight: 10 },
  tierBadge: { backgroundColor: PALETTE.gold + "22", borderColor: PALETTE.gold, borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  tierText: { color: PALETTE.gold, fontSize: 12, fontWeight: "700" },
  timeLeft: { color: PALETTE.subtext, fontSize: 13, marginBottom: 14 },
  statsRow: { flexDirection: "row", gap: 10 },
  statBox: { flex: 1, backgroundColor: PALETTE.bg, borderRadius: 10, paddingVertical: 12, alignItems: "center", borderWidth: 1, borderColor: PALETTE.border },
  statValue: { color: PALETTE.text, fontSize: 18, fontWeight: "700" },
  statLabel: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },
});

// Social config styles
const scStyles = StyleSheet.create({
  socialRow: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 10 },
  socialBadge: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  socialHandle: { flex: 1, color: PALETTE.text, fontSize: 15, fontWeight: "500" },
  editBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 14, borderTopWidth: 1, borderTopColor: PALETTE.border, marginTop: 8,
  },
  editBtnText: { color: PALETTE.gold, fontSize: 15, fontWeight: "600" },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  modalContent: {
    backgroundColor: PALETTE.card, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: Platform.OS === "ios" ? 40 : 20,
  },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  modalTitle: { color: PALETTE.gold, fontSize: 18, fontWeight: "700" },
  modalHint: { color: PALETTE.subtext, fontSize: 12, fontStyle: "italic", marginBottom: 16 },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 12 },
  iconBadge: { width: 40, height: 40, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  input: {
    flex: 1, backgroundColor: PALETTE.bg, borderRadius: 8, paddingHorizontal: 14,
    paddingVertical: 11, color: PALETTE.text, fontSize: 15, borderWidth: 1, borderColor: PALETTE.border,
  },
  inputError: { borderColor: "#F44336" },
  saveBtn: { backgroundColor: PALETTE.gold, borderRadius: 12, paddingVertical: 16, alignItems: "center", marginTop: 8 },
  saveBtnText: { color: "#000", fontSize: 17, fontWeight: "700" },
});
