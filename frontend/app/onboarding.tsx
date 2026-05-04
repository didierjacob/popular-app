import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Dimensions,
  Easing,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  NativeScrollEvent,
  NativeSyntheticEvent,
} from "react-native";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { getLocales } from "expo-localization";

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  gold: "#FFD700",
  accent2: "#E04F5F",
  border: "#2E6148",
  green: "#009B4D",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;
const ONBOARDING_KEY = "@popularoo_onboarding_done";
const CIRCLE = 36;

// Category icon mapping
const CAT_ICON: Record<string, string> = {
  politics: "🏛️",
  culture: "🎵",
  sport: "⚽",
  business: "💼",
  other: "⭐",
};

// Hardcoded fallback per country (ordered by notoriété)
const FALLBACK_TOP3: Record<string, { name: string; category: string }[]> = {
  US: [
    { name: "Trump", category: "politics" },
    { name: "Beyoncé", category: "culture" },
    { name: "LeBron James", category: "sport" },
  ],
  FR: [
    { name: "Mbappé", category: "sport" },
    { name: "Macron", category: "politics" },
    { name: "Aya Nakamura", category: "culture" },
  ],
  GB: [
    { name: "King Charles III", category: "politics" },
    { name: "Adele", category: "culture" },
    { name: "Beckham", category: "sport" },
  ],
  BR: [
    { name: "Neymar", category: "sport" },
    { name: "Lula", category: "politics" },
    { name: "Anitta", category: "culture" },
  ],
  DE: [
    { name: "Toni Kroos", category: "sport" },
    { name: "Scholz", category: "politics" },
    { name: "Heidi Klum", category: "culture" },
  ],
  ES: [
    { name: "Nadal", category: "sport" },
    { name: "Pedro Sánchez", category: "politics" },
    { name: "Rosalía", category: "culture" },
  ],
  IT: [
    { name: "Sinner", category: "sport" },
    { name: "Meloni", category: "politics" },
    { name: "Måneskin", category: "culture" },
  ],
  PT: [
    { name: "Cristiano Ronaldo", category: "sport" },
    { name: "Marcelo", category: "politics" },
    { name: "Mariza", category: "culture" },
  ],
  CA: [
    { name: "Drake", category: "culture" },
    { name: "Trudeau", category: "politics" },
    { name: "Connor McDavid", category: "sport" },
  ],
  MX: [
    { name: "Canelo Álvarez", category: "sport" },
    { name: "Sheinbaum", category: "politics" },
    { name: "Salma Hayek", category: "culture" },
  ],
  AR: [
    { name: "Messi", category: "sport" },
    { name: "Milei", category: "politics" },
    { name: "María Becerra", category: "culture" },
  ],
  BE: [
    { name: "De Bruyne", category: "sport" },
    { name: "De Croo", category: "politics" },
    { name: "Angèle", category: "culture" },
  ],
  CH: [
    { name: "Federer", category: "sport" },
    { name: "Berset", category: "politics" },
    { name: "Nemo", category: "culture" },
  ],
  DEFAULT: [
    { name: "Trump", category: "politics" },
    { name: "Beyoncé", category: "culture" },
    { name: "Mbappé", category: "sport" },
  ],
};

// --- Sub-components ---

function RankingCard({
  rank,
  name,
  category,
  isYou = false,
}: {
  rank: number;
  name: string;
  category: string;
  isYou?: boolean;
}) {
  // Pulse animation for YOU card
  const pulseAnim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    if (isYou) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 1200,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 0.4,
            duration: 1200,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ])
      ).start();
    }
  }, [isYou, pulseAnim]);

  const initials = isYou
    ? "?"
    : name
        .split(" ")
        .map((w) => w[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);

  return (
    <Animated.View
      style={[
        styles.rankCard,
        isYou && styles.youCard,
        isYou && { borderColor: PALETTE.gold, opacity: pulseAnim },
      ]}
    >
      {/* Rank circle */}
      <View
        style={[styles.rankCircle, isYou && { borderColor: PALETTE.gold }]}
      >
        <Text
          style={[
            styles.rankNum,
            isYou && { color: PALETTE.gold },
          ]}
        >
          {rank}
        </Text>
      </View>

      {/* Avatar circle */}
      <View
        style={[
          styles.avatarCircle,
          isYou && { backgroundColor: PALETTE.gold + "30", borderColor: PALETTE.gold },
        ]}
      >
        <Text
          style={[
            styles.avatarText,
            isYou && { color: PALETTE.gold },
          ]}
        >
          {initials}
        </Text>
      </View>

      {/* Name + category */}
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text
          style={[styles.rankName, isYou && { color: PALETTE.gold, fontWeight: "800" }]}
          numberOfLines={1}
        >
          {name}
        </Text>
        {!isYou && (
          <Text style={styles.rankCat}>
            {CAT_ICON[category] || "⭐"} {category.charAt(0).toUpperCase() + category.slice(1)}
          </Text>
        )}
      </View>
    </Animated.View>
  );
}

function PageDots({ total, current }: { total: number; current: number }) {
  return (
    <View style={styles.dotsRow}>
      {Array.from({ length: total }).map((_, i) => (
        <View
          key={i}
          style={[
            styles.dot,
            i === current ? styles.dotActive : styles.dotInactive,
          ]}
        />
      ))}
    </View>
  );
}

// --- Main Onboarding Screen ---

export default function OnboardingScreen({ onComplete }: { onComplete?: () => void }) {
  const router = useRouter();
  const { t } = useTranslation();
  const flatListRef = useRef<FlatList>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [top3, setTop3] = useState<{ name: string; category: string }[]>([]);
  const [loading, setLoading] = useState(true);

  // Detect country
  useEffect(() => {
    const loadTop3 = async () => {
      let region = "DEFAULT";
      try {
        const locales = getLocales();
        region = locales?.[0]?.regionCode || "DEFAULT";
      } catch (e) {}

      try {
        // Try API first
        const res = await fetch(API(`/onboarding/top3?country=${region}`));
        if (res.ok) {
          const data = await res.json();
          if (data.top3 && data.top3.length === 3) {
            setTop3(data.top3);
            setLoading(false);
            return;
          }
        }
      } catch (e) {
        // API failed, use fallback
      }

      // Fallback: hardcoded by country
      const fallback = FALLBACK_TOP3[region] || FALLBACK_TOP3["DEFAULT"];
      setTop3(fallback);
      setLoading(false);
    };

    loadTop3();
  }, []);

  const completeOnboarding = useCallback(async () => {
    await AsyncStorage.setItem(ONBOARDING_KEY, "true");
    if (onComplete) {
      onComplete();
    } else {
      router.replace("/");
    }
  }, [router, onComplete]);

  const goNext = useCallback(() => {
    if (currentIndex < 3) {
      flatListRef.current?.scrollToIndex({ index: currentIndex + 1, animated: true });
    }
  }, [currentIndex]);

  const onScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const idx = Math.round(event.nativeEvent.contentOffset.x / SCREEN_W);
      setCurrentIndex(idx);
    },
    []
  );

  // --- Screen renderers ---

  const renderScreen1 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <View style={styles.logoContainer}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoP}>P</Text>
          </View>
        </View>
        <Text style={styles.welcomeTitle}>{t("onboarding.welcome_title")}</Text>
        <Text style={styles.welcomeSubtitle}>{t("onboarding.welcome_subtitle")}</Text>
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={0} />
        <TouchableOpacity style={styles.continueBtn} onPress={goNext} activeOpacity={0.8}>
          <Text style={styles.continueBtnText}>{t("onboarding.continue")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderScreen2 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <Text style={styles.screenTitle}>{t("onboarding.vote_title")}</Text>
        <Text style={styles.screenSubtitle}>{t("onboarding.vote_subtitle")}</Text>
        <View style={styles.rankingContainer}>
          {top3.map((p, i) => (
            <RankingCard key={i} rank={i + 1} name={p.name} category={p.category} />
          ))}
        </View>
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={1} />
        <TouchableOpacity style={styles.continueBtn} onPress={goNext} activeOpacity={0.8}>
          <Text style={styles.continueBtnText}>{t("onboarding.continue")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderScreen3 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <Text style={styles.screenTitle}>{t("onboarding.promo_title")}</Text>
        <Text style={styles.screenSubtitle}>{t("onboarding.promo_subtitle")}</Text>
        <View style={styles.rankingContainer}>
          {top3.map((p, i) => (
            <RankingCard key={i} rank={i + 1} name={p.name} category={p.category} />
          ))}
          <RankingCard rank={4} name={t("onboarding.you")} category="" isYou />
        </View>
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={2} />
        <TouchableOpacity style={styles.continueBtn} onPress={goNext} activeOpacity={0.8}>
          <Text style={styles.continueBtnText}>{t("onboarding.continue")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderScreen4 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <View style={styles.actionIconContainer}>
          <Text style={styles.actionIcon}>🚀</Text>
        </View>
        <Text style={styles.actionTitle}>{t("onboarding.action_title")}</Text>
        <Text style={styles.actionSubtitle}>{t("onboarding.action_subtitle")}</Text>
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={3} />
        <TouchableOpacity
          style={[styles.continueBtn, styles.startBtn]}
          onPress={completeOnboarding}
          activeOpacity={0.8}
        >
          <Text style={styles.startBtnText}>{t("onboarding.start_voting")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const screens = [renderScreen1, renderScreen2, renderScreen3, renderScreen4];

  if (loading) {
    return <View style={styles.screen}><View style={styles.screenContent} /></View>;
  }

  return (
    <View style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      <FlatList
        ref={flatListRef}
        data={screens}
        horizontal
        pagingEnabled
        bounces={false}
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyExtractor={(_, i) => String(i)}
        renderItem={({ item: renderFn }) => renderFn()}
        getItemLayout={(_, index) => ({
          length: SCREEN_W,
          offset: SCREEN_W * index,
          index,
        })}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    height: SCREEN_H,
    backgroundColor: PALETTE.bg,
    justifyContent: "space-between",
  },
  screenContent: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 32,
  },

  // Logo (Screen 1)
  logoContainer: { marginBottom: 32, alignItems: "center" },
  logoCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: PALETTE.gold,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: PALETTE.gold,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 20,
    elevation: 15,
  },
  logoP: { fontSize: 40, fontWeight: "900", color: PALETTE.bg },

  welcomeTitle: {
    fontSize: 28,
    fontWeight: "800",
    color: PALETTE.text,
    textAlign: "center",
    marginBottom: 12,
  },
  welcomeSubtitle: {
    fontSize: 16,
    color: PALETTE.gold,
    fontStyle: "italic",
    textAlign: "center",
    letterSpacing: 0.5,
  },

  // Generic screen text
  screenTitle: {
    fontSize: 22,
    fontWeight: "700",
    color: PALETTE.text,
    textAlign: "center",
    marginBottom: 8,
    lineHeight: 30,
  },
  screenSubtitle: {
    fontSize: 14,
    color: PALETTE.subtext,
    textAlign: "center",
    marginBottom: 28,
    lineHeight: 20,
  },

  // Ranking cards
  rankingContainer: {
    width: "100%",
    marginTop: 8,
    gap: 8,
  },
  rankCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  youCard: {
    backgroundColor: PALETTE.gold + "08",
    borderStyle: "dashed",
    borderWidth: 1.5,
  },
  rankCircle: {
    width: CIRCLE,
    height: CIRCLE,
    borderRadius: CIRCLE / 2,
    backgroundColor: PALETTE.card,
    borderWidth: 1.5,
    borderColor: PALETTE.border,
    alignItems: "center",
    justifyContent: "center",
  },
  rankNum: {
    color: PALETTE.text,
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  avatarCircle: {
    width: CIRCLE,
    height: CIRCLE,
    borderRadius: CIRCLE / 2,
    backgroundColor: PALETTE.card,
    borderWidth: 1.5,
    borderColor: PALETTE.border,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
  },
  avatarText: {
    color: PALETTE.text,
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  rankName: {
    color: PALETTE.text,
    fontSize: 15,
    fontWeight: "600",
  },
  rankCat: {
    color: PALETTE.subtext,
    fontSize: 11,
    marginTop: 2,
  },

  // Screen 4 (Action)
  actionIconContainer: { marginBottom: 24 },
  actionIcon: { fontSize: 56 },
  actionTitle: {
    fontSize: 28,
    fontWeight: "800",
    color: PALETTE.text,
    textAlign: "center",
    marginBottom: 8,
  },
  actionSubtitle: {
    fontSize: 20,
    fontWeight: "700",
    color: PALETTE.gold,
    textAlign: "center",
    fontStyle: "italic",
    letterSpacing: 0.5,
  },

  // Bottom area
  bottomArea: {
    paddingBottom: 60,
    paddingHorizontal: 32,
    alignItems: "center",
    gap: 20,
  },
  dotsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  dotActive: { backgroundColor: PALETTE.gold, width: 24 },
  dotInactive: { backgroundColor: PALETTE.border },
  continueBtn: {
    backgroundColor: PALETTE.card,
    paddingHorizontal: 48,
    paddingVertical: 14,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: PALETTE.border,
    width: "100%",
    alignItems: "center",
  },
  continueBtnText: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: "700",
  },
  startBtn: {
    backgroundColor: PALETTE.gold,
    borderColor: PALETTE.gold,
  },
  startBtnText: {
    color: PALETTE.bg,
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
});
