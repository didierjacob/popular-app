import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Platform,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import { setLanguage, SUPPORTED_LANGUAGES, LANGUAGE_STORAGE_KEY } from "../i18n";

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
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;
const COUNTRY_KEY = "popular_user_country";
const USER_ID_KEY = "popular_user_id";

// Countries supported by the backend
const COUNTRIES = [
  { code: "FR", name: "France", flag: "\u{1F1EB}\u{1F1F7}" },
  { code: "GB", name: "UK", flag: "\u{1F1EC}\u{1F1E7}" },
  { code: "US", name: "United States", flag: "\u{1F1FA}\u{1F1F8}" },
  { code: "CA", name: "Canada", flag: "\u{1F1E8}\u{1F1E6}" },
  { code: "ES", name: "España", flag: "\u{1F1EA}\u{1F1F8}" },
  { code: "MX", name: "México", flag: "\u{1F1F2}\u{1F1FD}" },
  { code: "BR", name: "Brasil", flag: "\u{1F1E7}\u{1F1F7}" },
  { code: "AR", name: "Argentina", flag: "\u{1F1E6}\u{1F1F7}" },
  { code: "DE", name: "Deutschland", flag: "\u{1F1E9}\u{1F1EA}" },
  { code: "IT", name: "Italia", flag: "\u{1F1EE}\u{1F1F9}" },
  { code: "PT", name: "Portugal", flag: "\u{1F1F5}\u{1F1F9}" },
  { code: "AU", name: "Australia", flag: "\u{1F1E6}\u{1F1FA}" },
];

// Languages supported by the app
const LANGUAGES = [
  { code: "en", name: "English", flag: "\u{1F1EC}\u{1F1E7}" },
  { code: "fr", name: "Français", flag: "\u{1F1EB}\u{1F1F7}" },
  { code: "es", name: "Español", flag: "\u{1F1EA}\u{1F1F8}" },
  { code: "pt", name: "Português", flag: "\u{1F1E7}\u{1F1F7}" },
  { code: "de", name: "Deutsch", flag: "\u{1F1E9}\u{1F1EA}" },
  { code: "it", name: "Italiano", flag: "\u{1F1EE}\u{1F1F9}" },
];

export default function SettingsScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [selectedCountry, setSelectedCountry] = useState<string>("");
  const [selectedLanguage, setSelectedLanguage] = useState<string>(i18n.language || "en");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Load saved settings
  useEffect(() => {
    (async () => {
      try {
        const savedCountry = await AsyncStorage.getItem(COUNTRY_KEY);
        const savedLang = await AsyncStorage.getItem(LANGUAGE_STORAGE_KEY);

        if (savedCountry) setSelectedCountry(savedCountry);
        if (savedLang) setSelectedLanguage(savedLang);
      } catch (e) {
        console.error("Failed to load settings:", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const getUserId = useCallback(async () => {
    let userId = await AsyncStorage.getItem(USER_ID_KEY);
    if (!userId) {
      userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      await AsyncStorage.setItem(USER_ID_KEY, userId);
    }
    return userId;
  }, []);

  const handleCountrySelect = useCallback(
    async (code: string) => {
      setSelectedCountry(code);
      setSaving(true);
      try {
        await AsyncStorage.setItem(COUNTRY_KEY, code);
        const userId = await getUserId();
        await fetch(API("/user-settings"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            device_id: userId,
            country: code,
          }),
        });
      } catch (e) {
        console.error("Failed to save country:", e);
      } finally {
        setSaving(false);
      }
    },
    [getUserId]
  );

  const handleLanguageSelect = useCallback(
    async (code: string) => {
      setSelectedLanguage(code);
      setSaving(true);
      try {
        // Change language immediately via i18next
        await setLanguage(code);
        // Also save to backend
        const userId = await getUserId();
        await fetch(API("/user-settings"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            device_id: userId,
            language: code,
          }),
        });
      } catch (e) {
        console.error("Failed to save language:", e);
      } finally {
        setSaving(false);
      }
    },
    [getUserId]
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color={PALETTE.accent2} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{t("settings.title")}</Text>
        {saving && <ActivityIndicator size="small" color={PALETTE.green} style={{ marginLeft: 8 }} />}
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}
        showsVerticalScrollIndicator={false}
      >
        {/* ---- LANGUAGE SECTION ---- */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("settings.languageSection")}</Text>
          <Text style={styles.sectionDesc}>{t("settings.languageDesc")}</Text>
          <View style={styles.optionsGrid}>
            {LANGUAGES.map((lang) => {
              const isSelected = selectedLanguage === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[
                    styles.optionCard,
                    isSelected && styles.optionCardSelected,
                  ]}
                  onPress={() => handleLanguageSelect(lang.code)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.optionFlag}>{lang.flag}</Text>
                  <Text
                    style={[
                      styles.optionName,
                      isSelected && styles.optionNameSelected,
                    ]}
                    numberOfLines={1}
                  >
                    {lang.name}
                  </Text>
                  {isSelected && (
                    <Ionicons
                      name="checkmark-circle"
                      size={20}
                      color={PALETTE.green}
                      style={styles.checkIcon}
                    />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* ---- COUNTRY SECTION ---- */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t("settings.countrySection")}</Text>
          <Text style={styles.sectionDesc}>{t("settings.countryDesc")}</Text>
          <View style={styles.optionsGrid}>
            {COUNTRIES.map((country) => {
              const isSelected = selectedCountry === country.code;
              return (
                <TouchableOpacity
                  key={country.code}
                  style={[
                    styles.optionCard,
                    isSelected && styles.optionCardSelected,
                  ]}
                  onPress={() => handleCountrySelect(country.code)}
                  activeOpacity={0.7}
                >
                  <Text style={styles.optionFlag}>{country.flag}</Text>
                  <Text
                    style={[
                      styles.optionName,
                      isSelected && styles.optionNameSelected,
                    ]}
                    numberOfLines={1}
                  >
                    {country.name}
                  </Text>
                  {isSelected && (
                    <Ionicons
                      name="checkmark-circle"
                      size={20}
                      color={PALETTE.green}
                      style={styles.checkIcon}
                    />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  backBtn: {
    padding: 4,
    marginRight: 12,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: "700",
    color: PALETTE.text,
    flex: 1,
  },
  scrollView: {
    flex: 1,
    paddingHorizontal: 16,
  },
  section: {
    marginTop: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: PALETTE.text,
    marginBottom: 4,
  },
  sectionDesc: {
    fontSize: 13,
    color: PALETTE.subtext,
    marginBottom: 16,
    lineHeight: 18,
  },
  optionsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  optionCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderWidth: 1.5,
    borderColor: PALETTE.border,
    minWidth: "47%",
    flex: 1,
    maxWidth: "49%",
  },
  optionCardSelected: {
    borderColor: PALETTE.green,
    backgroundColor: PALETTE.green + "15",
  },
  optionFlag: {
    fontSize: 22,
    marginRight: 10,
  },
  optionName: {
    fontSize: 14,
    fontWeight: "600",
    color: PALETTE.text,
    flex: 1,
  },
  optionNameSelected: {
    color: PALETTE.green,
  },
  checkIcon: {
    marginLeft: 4,
  },
});
