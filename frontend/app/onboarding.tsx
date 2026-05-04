import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Animated,
  Dimensions,
  Easing,
  FlatList,
  Image,
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
import Svg, { Circle, Path, Defs, LinearGradient, Stop, Text as SvgText } from "react-native-svg";
import { Ionicons } from "@expo/vector-icons";

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
  orange: "#FFA500",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (p: string) => `${API_BASE}/api${p.startsWith("/") ? p : `/${p}`}`;
const ONBOARDING_KEY = "@popularoo_onboarding_done";

// Hardcoded fallback per country (ordered by notoriété)
const FALLBACK_TOP3: Record<string, { name: string; category: string; score: number }[]> = {
  US: [{ name: "Trump", category: "politics", score: 72 }, { name: "Beyoncé", category: "culture", score: 68 }, { name: "LeBron James", category: "sport", score: 65 }],
  FR: [{ name: "Mbappé", category: "sport", score: 71 }, { name: "Macron", category: "politics", score: 69 }, { name: "Aya Nakamura", category: "culture", score: 66 }],
  GB: [{ name: "King Charles III", category: "politics", score: 70 }, { name: "Adele", category: "culture", score: 67 }, { name: "Beckham", category: "sport", score: 65 }],
  BR: [{ name: "Neymar", category: "sport", score: 69 }, { name: "Lula", category: "politics", score: 66 }, { name: "Anitta", category: "culture", score: 63 }],
  DE: [{ name: "Toni Kroos", category: "sport", score: 68 }, { name: "Scholz", category: "politics", score: 65 }, { name: "Heidi Klum", category: "culture", score: 63 }],
  ES: [{ name: "Nadal", category: "sport", score: 71 }, { name: "Pedro Sánchez", category: "politics", score: 64 }, { name: "Rosalía", category: "culture", score: 62 }],
  IT: [{ name: "Sinner", category: "sport", score: 70 }, { name: "Meloni", category: "politics", score: 66 }, { name: "Måneskin", category: "culture", score: 63 }],
  PT: [{ name: "Cristiano Ronaldo", category: "sport", score: 74 }, { name: "Marcelo", category: "politics", score: 63 }, { name: "Mariza", category: "culture", score: 60 }],
  CA: [{ name: "Drake", category: "culture", score: 68 }, { name: "Trudeau", category: "politics", score: 65 }, { name: "Connor McDavid", category: "sport", score: 62 }],
  MX: [{ name: "Canelo Álvarez", category: "sport", score: 69 }, { name: "Sheinbaum", category: "politics", score: 64 }, { name: "Salma Hayek", category: "culture", score: 66 }],
  AR: [{ name: "Messi", category: "sport", score: 76 }, { name: "Milei", category: "politics", score: 65 }, { name: "María Becerra", category: "culture", score: 60 }],
  BE: [{ name: "De Bruyne", category: "sport", score: 69 }, { name: "De Croo", category: "politics", score: 62 }, { name: "Angèle", category: "culture", score: 64 }],
  CH: [{ name: "Federer", category: "sport", score: 73 }, { name: "Berset", category: "politics", score: 61 }, { name: "Nemo", category: "culture", score: 60 }],
  DEFAULT: [{ name: "Trump", category: "politics", score: 72 }, { name: "Beyoncé", category: "culture", score: 68 }, { name: "Mbappé", category: "sport", score: 70 }],
};

// ---- Reusable Gauge (same as Home page) ----

function GaugeIcon({ score, size = 32 }: { score: number; size?: number }) {
  const normalizedScore = Math.min(100, Math.max(0, score));
  const angle = -135 + (normalizedScore / 100) * 270;
  const angleRad = (angle * Math.PI) / 180;
  const cx = size / 2, cy = size / 2;
  const nl = size * 0.32;
  const nx = cx + nl * Math.cos(angleRad), ny = cy + nl * Math.sin(angleRad);
  return (
    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <Defs>
        <LinearGradient id="ogG" x1="0%" y1="0%" x2="100%" y2="100%">
          <Stop offset="0%" stopColor="#4A6858" /><Stop offset="100%" stopColor="#1C3A2C" />
        </LinearGradient>
        <LinearGradient id="ogB" x1="0%" y1="0%" x2="0%" y2="100%">
          <Stop offset="0%" stopColor="#5A7868" /><Stop offset="100%" stopColor="#1C3428" />
        </LinearGradient>
      </Defs>
      <Circle cx={cx} cy={cy} r={size * 0.46} fill="url(#ogB)" />
      <Circle cx={cx} cy={cy} r={size * 0.36} fill="url(#ogG)" />
      <Path d={`M ${cx - size * 0.26} ${cy + size * 0.1} A ${size * 0.28} ${size * 0.28} 0 1 1 ${cx + size * 0.26} ${cy + size * 0.1}`} stroke="#2E6148" strokeWidth={size * 0.04} fill="none" strokeLinecap="round" opacity={0.6} />
      <Path d={`M ${cx} ${cy} L ${nx} ${ny}`} stroke="#E04F5F" strokeWidth={size * 0.045} strokeLinecap="round" />
      <Circle cx={cx} cy={cy} r={size * 0.08} fill="#3A5848" />
    </Svg>
  );
}

// ---- Animated enriched chart ----

function EnrichedChart({ name, width = SCREEN_W - 72, height = 64 }: { name: string; width?: number; height?: number }) {
  const drawProgress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(drawProgress, {
      toValue: 1,
      duration: 1800,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, []);

  // Realistic data points (7 days) with upward trend
  const points = [0.52, 0.48, 0.55, 0.50, 0.58, 0.62, 0.56, 0.64, 0.60, 0.68, 0.72, 0.70, 0.76, 0.78];
  const chartW = width - 40; // leave room for Y axis labels
  const chartH = height - 4;
  const step = chartW / (points.length - 1);

  const pathParts = points.map((p, i) => {
    const x = 32 + i * step;
    const y = chartH - p * chartH;
    return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
  });
  const pathD = pathParts.join(" ");

  // Area fill path
  const areaD = pathD + ` L ${32 + (points.length - 1) * step} ${chartH} L 32 ${chartH} Z`;

  const lastX = 32 + (points.length - 1) * step;
  const lastY = chartH - points[points.length - 1] * chartH;

  // Calculate variation
  const variation = Math.round(((points[points.length - 1] - points[0]) / points[0]) * 100);

  // Initials for avatar
  const initials = name.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2);

  return (
    <Animated.View style={{ opacity: drawProgress, marginTop: 10 }}>
      <View style={{ backgroundColor: PALETTE.card, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: PALETTE.border }}>
        {/* Header: avatar + name + variation */}
        <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
          <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: PALETTE.gold + "20", borderWidth: 1, borderColor: PALETTE.gold, alignItems: "center", justifyContent: "center" }}>
            <Text style={{ color: PALETTE.gold, fontSize: 8, fontWeight: "700" }}>{initials}</Text>
          </View>
          <Text style={{ color: PALETTE.subtext, fontSize: 10, fontWeight: "600", marginLeft: 6, flex: 1 }}>{name} — 7 days</Text>
          <View style={{ backgroundColor: PALETTE.green + "20", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
            <Text style={{ color: PALETTE.green, fontSize: 10, fontWeight: "700" }}>+{variation}%</Text>
          </View>
        </View>

        {/* Chart */}
        <Svg width={width - 20} height={height} viewBox={`0 0 ${width} ${height}`}>
          {/* Y-axis labels */}
          <SvgText x={2} y={10} fill={PALETTE.subtext} fontSize={7} fontWeight="600">100</SvgText>
          <SvgText x={8} y={chartH / 2 + 3} fill={PALETTE.subtext} fontSize={7} fontWeight="600">50</SvgText>
          <SvgText x={14} y={chartH - 1} fill={PALETTE.subtext} fontSize={7} fontWeight="600">0</SvgText>

          {/* Grid lines */}
          <Path d={`M 32 ${chartH / 2} H ${width - 20}`} stroke={PALETTE.border} strokeWidth={0.5} strokeDasharray="3,3" />

          {/* Area fill */}
          <Path d={areaD} fill={PALETTE.green + "10"} />

          {/* Trend line */}
          <Path d={pathD} stroke={PALETTE.green} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />

          {/* Current point */}
          <Circle cx={lastX} cy={lastY} r={3.5} fill={PALETTE.green} />
          <Circle cx={lastX} cy={lastY} r={6} fill={PALETTE.green} fillOpacity={0.2} />
        </Svg>
      </View>
    </Animated.View>
  );
}

// ---- Personality card (Home-matching with gold border) ----

function PersonCard({ rank, name, category, score, isYou = false }: {
  rank: number; name: string; category: string; score: number; isYou?: boolean;
}) {
  const { t } = useTranslation();
  const pulseAnim = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    if (isYou) {
      Animated.loop(Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1, duration: 1200, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 0.5, duration: 1200, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ])).start();
    }
  }, [isYou]);

  const catLabel = isYou ? "" : (t(`categories.${category}`) || category);
  const catIcon: Record<string, string> = { politics: "people", culture: "color-palette", sport: "football", business: "briefcase" };

  // Ajustement 3: Gauge differentiated by rank (95/82/68)
  const gaugeScore = rank === 1 ? 97 : rank === 2 ? 82 : 68;

  return (
    <Animated.View style={[
      styles.personCard,
      // Ajustement 1: Gold border for all personality cards
      !isYou && { borderColor: PALETTE.gold + "50" },
      isYou && styles.youCard,
      isYou && { opacity: pulseAnim },
    ]}>
      {/* Rank badge */}
      <View style={[styles.rankBadge, isYou && { borderColor: PALETTE.gold, backgroundColor: PALETTE.gold + "15" }]}>
        <Text style={[styles.rankText, isYou && { color: PALETTE.gold }]}>{rank}</Text>
      </View>

      {/* Info */}
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={[styles.personName, isYou && { color: PALETTE.gold, fontWeight: "800", letterSpacing: 2 }]} numberOfLines={1}>
          {isYou ? t("onboarding.you") : name}
        </Text>
        {!isYou && (
          <Text style={styles.personMeta}>
            {catLabel} • {Math.round(score * 200 + 10000).toLocaleString()} votes
          </Text>
        )}
      </View>

      {/* Gauge differentiated by rank, or ? for YOU */}
      {isYou ? (
        <View style={styles.youAvatarCircle}>
          <Text style={styles.youAvatarText}>?</Text>
        </View>
      ) : (
        <GaugeIcon score={gaugeScore} size={36} />
      )}
    </Animated.View>
  );
}

// ---- Page dots ----

function PageDots({ total, current }: { total: number; current: number }) {
  return (
    <View style={styles.dotsRow}>
      {Array.from({ length: total }).map((_, i) => (
        <View key={i} style={[styles.dot, i === current ? styles.dotActive : styles.dotInactive]} />
      ))}
    </View>
  );
}

// ---- Booster Tier Card with visual hierarchy ----

function BoosterTierCard({ icon, name, duration, desc, color, tier }: {
  icon: string; name: string; duration: string; desc: string; color: string; tier: "basic" | "super" | "golden";
}) {
  const isGolden = tier === "golden";
  const isSuper = tier === "super";

  return (
    <View style={[
      styles.tierCard,
      { borderColor: color + (isGolden ? "70" : "40") },
      isGolden && { backgroundColor: PALETTE.gold + "0C", borderWidth: 1.5 },
      isSuper && { backgroundColor: PALETTE.orange + "08" },
    ]}>
      <View style={[
        styles.tierIcon,
        { backgroundColor: color + (isGolden ? "25" : "15") },
        isGolden && { borderWidth: 1, borderColor: PALETTE.gold + "50" },
      ]}>
        <Ionicons name={icon as any} size={isGolden ? 24 : 22} color={color} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={[styles.tierName, { color }, isGolden && { fontSize: 16 }]}>{name}</Text>
          {isGolden && (
            <View style={{ backgroundColor: PALETTE.gold + "20", paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
              <Text style={{ color: PALETTE.gold, fontSize: 8, fontWeight: "800" }}>MOST POPULAR</Text>
            </View>
          )}
        </View>
        <Text style={[styles.tierDuration, isGolden && { fontWeight: "700" }]}>{duration}</Text>
        <Text style={styles.tierDesc}>{desc}</Text>
      </View>
    </View>
  );
}

// ==== MAIN COMPONENT ====

export default function OnboardingScreen({ onComplete }: { onComplete?: () => void }) {
  const router = useRouter();
  const { t } = useTranslation();
  const flatListRef = useRef<FlatList>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [top3, setTop3] = useState<{ name: string; category: string; score: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadTop3 = async () => {
      let region = "DEFAULT";
      try { region = getLocales()?.[0]?.regionCode || "DEFAULT"; } catch {}

      try {
        const res = await fetch(API(`/onboarding/top3?country=${region}`));
        if (res.ok) {
          const data = await res.json();
          if (data.top3?.length === 3) {
            const mapped = data.top3.map((p: any) => ({
              name: p.name,
              category: p.category,
              score: p.popularoo_index || 65,
            }));
            setTop3(mapped);
            setLoading(false);
            return;
          }
        }
      } catch {}

      setTop3(FALLBACK_TOP3[region] || FALLBACK_TOP3["DEFAULT"]);
      setLoading(false);
    };
    loadTop3();
  }, []);

  const completeOnboarding = useCallback(async () => {
    await AsyncStorage.setItem(ONBOARDING_KEY, "true");
    if (onComplete) onComplete();
    else router.replace("/");
  }, [router, onComplete]);

  const goNext = useCallback(() => {
    if (currentIndex < 3) {
      const next = currentIndex + 1;
      flatListRef.current?.scrollToIndex({ index: next, animated: true });
      setCurrentIndex(next);
    }
  }, [currentIndex]);

  const onScroll = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const idx = Math.round(e.nativeEvent.contentOffset.x / SCREEN_W);
    setCurrentIndex(idx);
  }, []);

  // ---- Screen 1: Welcome with official icon ----
  const renderScreen1 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <View style={styles.iconShadow}>
          <Image
            source={require("../assets/images/icon.png")}
            style={styles.appIcon}
          />
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

  // ---- Screen 2: Vote with rich cards + mini chart ----
  const renderScreen2 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <Text style={styles.screenTitle}>{t("onboarding.vote_title")}</Text>
        <Text style={styles.screenSubtitle}>{t("onboarding.vote_subtitle")}</Text>
        <View style={styles.rankingContainer}>
          {top3.map((p, i) => (
            <PersonCard key={i} rank={i + 1} name={p.name} category={p.category} score={p.score} />
          ))}
        </View>
        <MiniChart />
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={1} />
        <TouchableOpacity style={styles.continueBtn} onPress={goNext} activeOpacity={0.8}>
          <Text style={styles.continueBtnText}>{t("onboarding.continue")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  // ---- Screen 3: Promo with YOU card ----
  const renderScreen3 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <Text style={styles.screenTitle}>{t("onboarding.promo_title")}</Text>
        <Text style={styles.screenSubtitle}>{t("onboarding.promo_subtitle")}</Text>
        <View style={styles.rankingContainer}>
          {top3.map((p, i) => (
            <PersonCard key={i} rank={i + 1} name={p.name} category={p.category} score={p.score} />
          ))}
          <PersonCard rank={4} name="" category="" score={0} isYou />
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

  // ---- Screen 4: Booster tiers (informative, no prices) ----
  const renderScreen4 = () => (
    <View style={[styles.screen, { width: SCREEN_W }]}>
      <View style={styles.screenContent}>
        <Text style={styles.screenTitle}>{t("onboarding.action_title")}</Text>
        <Text style={styles.screenSubtitle}>{t("onboarding.action_subtitle")}</Text>
        <View style={styles.tiersContainer}>
          <BoosterTierCard
            icon="flash"
            name="Booster"
            duration={t("onboarding.booster_1h")}
            desc={t("onboarding.booster_1h_desc")}
            color={PALETTE.green}
            tier="basic"
          />
          <BoosterTierCard
            icon="star"
            name="Super Booster"
            duration={t("onboarding.booster_24h")}
            desc={t("onboarding.booster_24h_desc")}
            color={PALETTE.orange}
            tier="super"
          />
          <BoosterTierCard
            icon="trophy"
            name="Golden Booster"
            duration={t("onboarding.booster_7d")}
            desc={t("onboarding.booster_7d_desc")}
            color={PALETTE.gold}
            tier="golden"
          />
        </View>
      </View>
      <View style={styles.bottomArea}>
        <PageDots total={4} current={3} />
        <TouchableOpacity style={[styles.continueBtn, styles.startBtn]} onPress={completeOnboarding} activeOpacity={0.8}>
          <Text style={styles.startBtnText}>{t("onboarding.start_exploring")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const screens = [renderScreen1, renderScreen2, renderScreen3, renderScreen4];

  if (loading) return <View style={[styles.screen, { backgroundColor: PALETTE.bg }]} />;

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
        getItemLayout={(_, index) => ({ length: SCREEN_W, offset: SCREEN_W * index, index })}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, height: SCREEN_H, backgroundColor: PALETTE.bg, justifyContent: "space-between" },
  screenContent: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 24 },

  // Screen 1 — Icon
  iconShadow: { marginBottom: 28, alignItems: "center" },
  appIcon: { width: 100, height: 100, borderRadius: 22 },
  welcomeTitle: { fontSize: 26, fontWeight: "800", color: PALETTE.text, textAlign: "center", marginBottom: 10 },
  welcomeSubtitle: { fontSize: 15, color: PALETTE.gold, fontStyle: "italic", textAlign: "center", letterSpacing: 0.5 },

  // Screen titles
  screenTitle: { fontSize: 20, fontWeight: "700", color: PALETTE.text, textAlign: "center", marginBottom: 6, lineHeight: 28 },
  screenSubtitle: { fontSize: 13, color: PALETTE.subtext, textAlign: "center", marginBottom: 20, lineHeight: 19 },

  // Ranking container
  rankingContainer: { width: "100%", gap: 6 },

  // Person card (Home-matching style)
  personCard: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: PALETTE.card, paddingHorizontal: 14, paddingVertical: 11,
    borderRadius: 10, borderWidth: 1, borderColor: PALETTE.border,
  },
  youCard: { backgroundColor: PALETTE.gold + "08", borderStyle: "dashed", borderWidth: 1.5, borderColor: PALETTE.gold },
  rankBadge: {
    width: 30, height: 30, borderRadius: 15,
    backgroundColor: PALETTE.accent2, alignItems: "center", justifyContent: "center",
  },
  rankText: { color: "#FFF", fontWeight: "700", fontSize: 13 },
  personName: { color: PALETTE.text, fontSize: 15, fontWeight: "600" },
  personMeta: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },
  youAvatarCircle: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: PALETTE.gold + "25", borderWidth: 1.5, borderColor: PALETTE.gold,
    alignItems: "center", justifyContent: "center",
  },
  youAvatarText: { color: PALETTE.gold, fontSize: 18, fontWeight: "800" },

  // Booster tiers
  tiersContainer: { width: "100%", gap: 10, marginTop: 8 },
  tierCard: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: PALETTE.card, paddingHorizontal: 14, paddingVertical: 14,
    borderRadius: 12, borderWidth: 1,
  },
  tierIcon: {
    width: 44, height: 44, borderRadius: 22,
    alignItems: "center", justifyContent: "center",
  },
  tierName: { fontSize: 15, fontWeight: "700" },
  tierDuration: { color: PALETTE.text, fontSize: 12, fontWeight: "600", marginTop: 2 },
  tierDesc: { color: PALETTE.subtext, fontSize: 11, marginTop: 1 },

  // Bottom area
  bottomArea: { paddingBottom: 56, paddingHorizontal: 32, alignItems: "center", gap: 18 },
  dotsRow: { flexDirection: "row", justifyContent: "center", gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  dotActive: { backgroundColor: PALETTE.gold, width: 24 },
  dotInactive: { backgroundColor: PALETTE.border },
  continueBtn: {
    backgroundColor: PALETTE.card, paddingHorizontal: 48, paddingVertical: 14,
    borderRadius: 28, borderWidth: 1, borderColor: PALETTE.border,
    width: "100%", alignItems: "center",
  },
  continueBtnText: { color: PALETTE.text, fontSize: 16, fontWeight: "700" },
  startBtn: { backgroundColor: PALETTE.gold, borderColor: PALETTE.gold },
  startBtnText: { color: PALETTE.bg, fontSize: 17, fontWeight: "800", letterSpacing: 0.5 },
});
