import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import * as Localization from "expo-localization";
import AsyncStorage from "@react-native-async-storage/async-storage";

import en from "./locales/en.json";
import fr from "./locales/fr.json";
import es from "./locales/es.json";
import pt from "./locales/pt.json";
import de from "./locales/de.json";
import it from "./locales/it.json";

const SUPPORTED_LANGUAGES = ["en", "fr", "es", "pt", "de", "it"];
const LANGUAGE_STORAGE_KEY = "@popularoo_language";

// Detect best matching language from device locale
function detectLanguage(): string {
  try {
    const locales = Localization.getLocales();
    if (locales && locales.length > 0) {
      const deviceLang = locales[0].languageCode || "en";
      // Map pt-BR to pt
      const normalized = deviceLang.toLowerCase().split("-")[0];
      if (SUPPORTED_LANGUAGES.includes(normalized)) {
        return normalized;
      }
    }
  } catch {}
  return "en";
}

// Initialize with saved or detected language
async function initLanguage() {
  try {
    const saved = await AsyncStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved && SUPPORTED_LANGUAGES.includes(saved)) {
      await i18n.changeLanguage(saved);
    }
  } catch {}
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fr: { translation: fr },
    es: { translation: es },
    pt: { translation: pt },
    de: { translation: de },
    it: { translation: it },
  },
  lng: detectLanguage(),
  fallbackLng: "en",
  interpolation: {
    escapeValue: false,
  },
  react: {
    useSuspense: false,
  },
});

// Load saved preference
initLanguage();

// Helper to change and persist language
export async function setLanguage(lang: string) {
  if (SUPPORTED_LANGUAGES.includes(lang)) {
    await i18n.changeLanguage(lang);
    await AsyncStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  }
}

export { SUPPORTED_LANGUAGES, LANGUAGE_STORAGE_KEY };
export default i18n;
