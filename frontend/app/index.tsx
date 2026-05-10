import React, { useEffect, useState, useRef, useCallback } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
  RefreshControl,
  Animated,
  Easing,
  Linking,
  LayoutAnimation,
  Platform,
  UIManager,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { CreditsService, type OutsiderData } from "../services/creditsService";
import { useTranslation } from "react-i18next";
import * as Localization from "expo-localization";
import AsyncStorage from "@react-native-async-storage/async-storage";
import OutsiderCard from "../components/OutsiderCard";

// Enable LayoutAnimation on Android
if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  green: "#009B4D",
  border: "#2E6148",
  gold: "#FFD700",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const capitalize = (str: string) => str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
const formatNumber = (num: number) => Math.round(num).toLocaleString();

interface Person {
  id: string;
  name: string;
  category: string;
  score: number;
  total_votes: number;
  source?: string;
}

// ===== ANIMATION_CONFIG — Algo A: Weighted Random Increments =====
// All coefficients are grouped here for easy tuning after iPhone testing.
const ANIMATION_CONFIG = {
  TOP_LIST_SIZE: 30,                     // Number of items in the animated Top list
  MAX_DRIFT: 5,                          // Max ±positions drift from original rank
  TICK_MIN_MS: 1200,                     // Min interval between increments (ms)
  TICK_MAX_MS: 2800,                     // Max interval between increments (ms)
  INCREMENT_MIN: 1,                      // Min score bump per tick
  INCREMENT_MAX: 5,                      // Max score bump per tick
  PICKS_PER_TICK: 2,                     // How many personalities receive a bump per tick
  // Probability weight by rank bucket (higher = more likely to be selected)
  WEIGHT_TOP5: 0.40,                     // Ranks 1-5
  WEIGHT_MID: 0.35,                      // Ranks 6-15
  WEIGHT_TAIL: 0.25,                     // Ranks 16-30
};

interface Category {
  key: string;
  label: string;
  icon: string;
}

const CATEGORIES: Category[] = [
  { key: "politics", label: "Politics", icon: "people" },
  { key: "culture", label: "Culture", icon: "color-palette" },
  { key: "business", label: "Business", icon: "briefcase" },
  { key: "sport", label: "Sport", icon: "football" },
];

// ---- Gauge Components ----

function GaugeIcon({ score, size = 32 }: { score: number; size?: number }) {
  const normalizedScore = Math.min(100, Math.max(0, score));
  const angle = -135 + (normalizedScore / 100) * 270;
  const angleRad = (angle * Math.PI) / 180;
  const centerX = size / 2;
  const centerY = size / 2;
  const needleLength = size * 0.32;
  const needleX = centerX + needleLength * Math.cos(angleRad);
  const needleY = centerY + needleLength * Math.sin(angleRad);

  return (
    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <Defs>
        <LinearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <Stop offset="0%" stopColor="#4A6858" />
          <Stop offset="50%" stopColor="#2E4A3A" />
          <Stop offset="100%" stopColor="#1C3A2C" />
        </LinearGradient>
        <LinearGradient id="bezelGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <Stop offset="0%" stopColor="#5A7868" />
          <Stop offset="100%" stopColor="#1C3428" />
        </LinearGradient>
      </Defs>
      <Circle cx={centerX} cy={centerY} r={size * 0.46} fill="url(#bezelGradient)" />
      <Circle cx={centerX} cy={centerY} r={size * 0.36} fill="url(#gaugeGradient)" />
      <Path
        d={`M ${centerX - size * 0.26} ${centerY + size * 0.1} A ${size * 0.28} ${size * 0.28} 0 1 1 ${centerX + size * 0.26} ${centerY + size * 0.1}`}
        stroke="#2E6148"
        strokeWidth={size * 0.04}
        fill="none"
        strokeLinecap="round"
        opacity={0.6}
      />
      <Path d={`M ${centerX} ${centerY} L ${needleX} ${needleY}`} stroke="#E04F5F" strokeWidth={size * 0.045} strokeLinecap="round" />
      <Circle cx={centerX} cy={centerY} r={size * 0.08} fill="#3A5848" />
    </Svg>
  );
}

function BigOscillatingGauge({ score, size = 100 }: { score: number; size?: number }) {
  const oscillation = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(oscillation, { toValue: 1, duration: 1500, easing: Easing.inOut(Easing.sin), useNativeDriver: false }),
        Animated.timing(oscillation, { toValue: -1, duration: 1500, easing: Easing.inOut(Easing.sin), useNativeDriver: false }),
      ])
    ).start();
  }, []);

  const normalizedScore = Math.min(100, Math.max(0, score));
  const baseAngle = -135 + (normalizedScore / 100) * 270;
  const animatedAngle = oscillation.interpolate({
    inputRange: [-1, 1],
    outputRange: [baseAngle - 5, baseAngle + 5],
  });
  const centerX = size / 2;
  const centerY = size / 2;
  const needleLength = size * 0.35;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <Defs>
          <LinearGradient id="bigGaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#4A6858" />
            <Stop offset="100%" stopColor="#1C3A2C" />
          </LinearGradient>
          <LinearGradient id="bigBezelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <Stop offset="0%" stopColor="#5A7868" />
            <Stop offset="100%" stopColor="#1C3428" />
          </LinearGradient>
        </Defs>
        <Circle cx={centerX} cy={centerY} r={size * 0.46} fill="url(#bigBezelGrad)" />
        <Circle cx={centerX} cy={centerY} r={size * 0.40} fill="#0F2F22" />
        <Circle cx={centerX} cy={centerY} r={size * 0.36} fill="url(#bigGaugeGrad)" />
        <Path
          d={`M ${centerX - size * 0.26} ${centerY + size * 0.1} A ${size * 0.28} ${size * 0.28} 0 1 1 ${centerX + size * 0.26} ${centerY + size * 0.1}`}
          stroke="#2E6148"
          strokeWidth={size * 0.04}
          fill="none"
          strokeLinecap="round"
        />
        <Circle cx={centerX} cy={centerY} r={size * 0.10} fill="#4A6858" />
        <Circle cx={centerX} cy={centerY} r={size * 0.06} fill="#3A5848" />
      </Svg>
      <Animated.View
        style={{
          position: 'absolute',
          width: needleLength,
          height: 4,
          backgroundColor: '#E04F5F',
          borderRadius: 2,
          left: centerX,
          top: centerY - 2,
          transformOrigin: 'left center',
          transform: [{
            rotate: animatedAngle.interpolate({
              inputRange: [-180, 180],
              outputRange: ['-180deg', '180deg'],
            })
          }],
        }}
      />
    </View>
  );
}

// ---- Social Links Row ----

function SocialLinksRow({ links }: { links: any }) {
  if (!links) return null;
  const hasAny = links.instagram || links.twitter || links.facebook;
  if (!hasAny) return null;

  const openLink = (platform: string, value: string) => {
    let url = '';
    if (platform === 'instagram') {
      const handle = value.replace('@', '');
      url = `https://instagram.com/${handle}`;
    } else if (platform === 'twitter') {
      const handle = value.replace('@', '');
      url = `https://x.com/${handle}`;
    } else if (platform === 'facebook') {
      url = value.startsWith('http') ? value : `https://facebook.com/${value}`;
    }
    if (url) Linking.openURL(url).catch(() => {});
  };

  return (
    <View style={styles.socialLinksRow}>
      {links.instagram && (
        <TouchableOpacity onPress={() => openLink('instagram', links.instagram)} style={styles.socialLinkBtn}>
          <Ionicons name="logo-instagram" size={16} color="#E1306C" />
        </TouchableOpacity>
      )}
      {links.twitter && (
        <TouchableOpacity onPress={() => openLink('twitter', links.twitter)} style={styles.socialLinkBtn}>
          <Ionicons name="logo-twitter" size={16} color="#1DA1F2" />
        </TouchableOpacity>
      )}
      {links.facebook && (
        <TouchableOpacity onPress={() => openLink('facebook', links.facebook)} style={styles.socialLinkBtn}>
          <Ionicons name="logo-facebook" size={16} color="#1877F2" />
        </TouchableOpacity>
      )}
    </View>
  );
}

// ---- Time Remaining Badge ----

function TimeRemainingBadge({ hours }: { hours: number }) {
  let label = '';
  let color = PALETTE.green;

  if (hours < 1) {
    const mins = Math.max(1, Math.round(hours * 60));
    label = `${mins}m left`;
    color = PALETTE.accent2;
  } else if (hours < 24) {
    label = `${Math.round(hours)}h left`;
    color = hours < 6 ? '#FFA500' : PALETTE.green;
  } else {
    const days = Math.round(hours / 24);
    label = `${days}d left`;
  }

  return (
    <View style={[styles.timeBadge, { backgroundColor: color + '20', borderColor: color }]}>
      <Ionicons name="time" size={12} color={color} />
      <Text style={[styles.timeBadgeText, { color }]}>{label}</Text>
    </View>
  );
}

// ---- Main Component ----

export default function HomeScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const [people, setPeople] = useState<Person[]>([]);
  const [displayedPeople, setDisplayedPeople] = useState<Person[]>([]);
  const [personOfTheDay, setPersonOfTheDay] = useState<Person | null>(null);
  const [goldenOutsiders, setGoldenOutsiders] = useState<OutsiderData[]>([]);
  const [currentOutsiderIndex, setCurrentOutsiderIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchName, setSearchName] = useState("");
  const [searchSuggestions, setSearchSuggestions] = useState<Person[]>([]);
  const titleTapCount = useRef(0);
  const titleTapTimer = useRef<NodeJS.Timeout | null>(null);

  const fadeAnim = useRef(new Animated.Value(1)).current;
  // Pulsing heart animation for Outsider of the Day
  const heartPulse = useRef(new Animated.Value(1)).current;
  // Removed: listFadeAnim was used by the old periodic shuffle, replaced by Algo A

  const loadData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);

      // Detect user country from device locale
      const regionCode = Localization.getLocales()?.[0]?.regionCode || '';
      const countryParam = regionCode ? `&country=${regionCode}` : '';

      const [peopleRes, outsidersData] = await Promise.all([
        fetch(API(`/people?limit=50${countryParam}`)),
        CreditsService.getOutsiders(),
      ]);

      if (!peopleRes.ok) throw new Error(`HTTP ${peopleRes.status}`);
      const data = await peopleRes.json();

      const sortedByVotes = [...data]
        .filter((p: Person) => p.source !== "self_boosted" && p.category !== "outsider") // P0 BUG FIX: Never show outsiders (self_boosted or seeds) in Top list
        .sort((a: Person, b: Person) => b.total_votes - a.total_votes);
      setPeople(sortedByVotes);

      if (data.length > 0) {
        const sorted = [...data].sort((a: Person, b: Person) => b.score - a.score);
        setPersonOfTheDay(sorted[0]);
      }

      setGoldenOutsiders(outsidersData.golden || []);

    } catch (e: any) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(true), 30000);
    return () => clearInterval(interval);
  }, []);

  // BLOC 2.4: Like an outsider directly from the Home card
  // FIX: Send { value: 1 } with X-Device-ID header (matching backend VoteIn schema)
  const handleLikeOutsider = useCallback(async (personId: string) => {
    try {
      let did = await AsyncStorage.getItem('popularity_device_id');
      if (!did) {
        did = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        await AsyncStorage.setItem('popularity_device_id', did);
      }
      const res = await fetch(API(`/people/${personId}/vote`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-ID': did,
        },
        body: JSON.stringify({ value: 1 }),
      });
      if (res.ok) {
        // Optimistic update on the golden outsiders state
        setGoldenOutsiders(prev =>
          prev.map(o => o.id === personId ? { ...o, likes: (o.likes || 0) + 1 } : o)
        );
      }
    } catch (err) {
      console.error('Like outsider error:', err);
    }
  }, []);

  // ===== ALGO A: Organic Ranking Movement =====
  // Each person gets an internal "simulated score" that evolves by small random increments.
  // When a score crosses another, the list re-sorts with a smooth LayoutAnimation.
  const simulatedScores = useRef<Map<string, number>>(new Map());
  const originalRanks = useRef<Map<string, number>>(new Map());
  const animTickRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (people.length <= 1) return;

    // Initialize: take first 30 non-outsider people, assign simulated scores
    const top = people.slice(0, ANIMATION_CONFIG.TOP_LIST_SIZE);
    const scoreMap = new Map<string, number>();
    const rankMap = new Map<string, number>();
    top.forEach((p, i) => {
      scoreMap.set(p.id, p.total_votes);
      rankMap.set(p.id, i);
    });
    simulatedScores.current = scoreMap;
    originalRanks.current = rankMap;
    setDisplayedPeople(top);

    // Weighted random selection helper
    const pickRandomPerson = (list: Person[]): number => {
      const r = Math.random();
      const { WEIGHT_TOP5, WEIGHT_MID } = ANIMATION_CONFIG;
      let bucket: [number, number];
      if (r < WEIGHT_TOP5) {
        bucket = [0, Math.min(5, list.length)];
      } else if (r < WEIGHT_TOP5 + WEIGHT_MID) {
        bucket = [Math.min(5, list.length), Math.min(15, list.length)];
      } else {
        bucket = [Math.min(15, list.length), list.length];
      }
      if (bucket[0] >= bucket[1]) bucket = [0, list.length];
      return bucket[0] + Math.floor(Math.random() * (bucket[1] - bucket[0]));
    };

    // Schedule next organic tick
    const scheduleTick = () => {
      const delay = ANIMATION_CONFIG.TICK_MIN_MS +
        Math.random() * (ANIMATION_CONFIG.TICK_MAX_MS - ANIMATION_CONFIG.TICK_MIN_MS);
      animTickRef.current = setTimeout(() => {
        setDisplayedPeople(prev => {
          const scores = simulatedScores.current;
          const origRanks = originalRanks.current;
          const copy = [...prev];

          // Pick N people and add a random increment to their simulated score
          let bumpedNames: string[] = [];
          for (let p = 0; p < ANIMATION_CONFIG.PICKS_PER_TICK; p++) {
            const idx = pickRandomPerson(copy);
            if (idx < copy.length) {
              const person = copy[idx];
              const current = scores.get(person.id) || person.total_votes;
              const increment = ANIMATION_CONFIG.INCREMENT_MIN +
                Math.floor(Math.random() * (ANIMATION_CONFIG.INCREMENT_MAX - ANIMATION_CONFIG.INCREMENT_MIN + 1));
              scores.set(person.id, current + increment);
              bumpedNames.push(`${person.name}(+${increment})`);
            }
          }

          // Re-sort by simulated score
          copy.sort((a, b) => (scores.get(b.id) || 0) - (scores.get(a.id) || 0));

          // Enforce ±MAX_DRIFT from original rank
          const clamped = [...copy];
          for (let i = 0; i < clamped.length; i++) {
            const origRank = origRanks.get(clamped[i].id);
            if (origRank !== undefined) {
              const drift = i - origRank;
              if (Math.abs(drift) > ANIMATION_CONFIG.MAX_DRIFT) {
                // Reset simulated score slightly to pull back toward original rank
                const baseVotes = clamped[i].total_votes;
                scores.set(clamped[i].id, baseVotes + Math.floor(Math.random() * 10));
              }
            }
          }

          // Final sort after clamping
          copy.sort((a, b) => (scores.get(b.id) || 0) - (scores.get(a.id) || 0));

          // Check if order actually changed
          const changed = copy.some((p, i) => p.id !== prev[i]?.id);
          if (changed) {
            console.log(`[Algo A] SWAP detected — bumped: ${bumpedNames.join(', ')}`);
            LayoutAnimation.configureNext(
              LayoutAnimation.create(350, LayoutAnimation.Types.easeInEaseOut, LayoutAnimation.Properties.opacity)
            );
          } else {
            console.log(`[Algo A] tick — no swap (bumped: ${bumpedNames.join(', ')})`);
          }

          return copy;
        });

        scheduleTick(); // Chain next tick
      }, delay);
    };

    scheduleTick();

    return () => {
      if (animTickRef.current) clearTimeout(animTickRef.current);
    };
  }, [people]);

  // Pulsing heart animation — infinite loop
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(heartPulse, { toValue: 1.25, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(heartPulse, { toValue: 1, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ])
    ).start();
  }, []);

  // Rotate outsider of the day every 10 seconds
  useEffect(() => {
    if (goldenOutsiders.length <= 1) return;
    const rotateInterval = setInterval(() => {
      // Fade out
      Animated.timing(fadeAnim, {
        toValue: 0,
        duration: 300,
        useNativeDriver: true,
      }).start(() => {
        setCurrentOutsiderIndex(prev => (prev + 1) % goldenOutsiders.length);
        // Fade in
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }).start();
      });
    }, 10000);
    return () => clearInterval(rotateInterval);
  }, [goldenOutsiders.length]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData(true);
    setRefreshing(false);
  };

  const handleTitleTap = () => {
    titleTapCount.current += 1;
    if (titleTapTimer.current) clearTimeout(titleTapTimer.current);
    if (titleTapCount.current >= 7) {
      titleTapCount.current = 0;
      router.push("/admin");
      return;
    }
    titleTapTimer.current = setTimeout(() => { titleTapCount.current = 0; }, 2000);
  };

  const handleSearch = async () => {
    if (!searchName.trim()) return;
    const query = searchName.trim().toLowerCase();
    
    // FAST PATH: Check locally loaded people first for instant navigation
    const localMatch = people.find(p => 
      p.name.toLowerCase() === query || 
      p.name.toLowerCase().includes(query)
    );
    if (localMatch) {
      router.push({ pathname: "/person", params: { id: localMatch.id, name: localMatch.name } });
      setSearchName("");
      setSearchSuggestions([]);
      return;
    }

    // SLOW PATH: Query backend search (Wikipedia fallback etc.)
    try {
      const response = await fetch(API(`/search?query=${encodeURIComponent(searchName.trim())}`));
      if (response.ok) {
        const results = await response.json();
        if (results.length > 0) {
          // Prioritize exact name match over partial
          const exactMatch = results.find((r: any) => r.name.toLowerCase() === query);
          const best = exactMatch || results[0];
          router.push({ pathname: "/person", params: { id: best.id, name: best.name } });
          setSearchName("");
          setSearchSuggestions([]);
          return;
        }
      }
    } catch {}
    alert(`"${searchName}" not found. Try another name.`);
  };

  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;
  const contentStyle = isTablet ? { maxWidth: 600, alignSelf: 'center' as const, width: '100%' as const } : {};

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={isTablet ? { alignItems: 'center' } : {}}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
      >
        <View style={contentStyle}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={handleTitleTap} activeOpacity={0.8}>
            <Text style={styles.title}>Popularoo</Text>
          </TouchableOpacity>
          <Text style={styles.subtitle}>{t("home.baseline")}</Text>
        </View>

        {/* Search Box */}
        <View style={styles.searchCard}>
          <View style={styles.searchRow}>
            <TextInput
              style={styles.searchInput}
              placeholder={t("home.searchPlaceholder")}
              placeholderTextColor={PALETTE.subtext}
              value={searchName}
              onChangeText={(text) => {
                setSearchName(text);
                // Auto-complete suggestions
                if (text.length >= 2) {
                  const filtered = people.filter(p => 
                    p.name.toLowerCase().includes(text.toLowerCase())
                  ).slice(0, 5);
                  setSearchSuggestions(filtered);
                } else {
                  setSearchSuggestions([]);
                }
              }}
              onSubmitEditing={handleSearch}
            />
            <TouchableOpacity style={styles.searchButton} onPress={handleSearch}>
              <Text style={styles.searchButtonText}>{t("home.searchButton")}</Text>
            </TouchableOpacity>
          </View>
          {/* Auto-complete suggestions */}
          {searchSuggestions.length > 0 && searchName.length >= 2 && (
            <View style={styles.suggestionsContainer}>
              {searchSuggestions.map((suggestion) => (
                <TouchableOpacity
                  key={suggestion.id}
                  style={styles.suggestionItem}
                  onPress={() => {
                    router.push({ pathname: "/person", params: { id: suggestion.id, name: suggestion.name } });
                    setSearchName("");
                    setSearchSuggestions([]);
                  }}
                >
                  <Ionicons name="person-outline" size={14} color={PALETTE.subtext} />
                  <Text style={styles.suggestionText}>{suggestion.name}</Text>
                  <Text style={styles.suggestionMeta}>{capitalize(suggestion.category || 'other')}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>

        {/* Personality of the Day */}
        {personOfTheDay && (
          <TouchableOpacity
            style={styles.potdCard}
            onPress={() => router.push({ pathname: "/person", params: { id: personOfTheDay.id, name: personOfTheDay.name } })}
          >
            <View style={styles.potdBadge}>
              <Ionicons name="star" size={16} color={PALETTE.gold} />
              <Text style={styles.potdBadgeText}>{t("home.personalityOfTheDay")}</Text>
            </View>
            <View style={styles.potdContent}>
              <View style={styles.potdInfo}>
                <Text style={styles.potdName}>{personOfTheDay.name}</Text>
                <Text style={styles.potdMeta}>
                  {t(`categories.${personOfTheDay.category}`) || capitalize(personOfTheDay.category)} • {formatNumber(personOfTheDay.total_votes)} votes
                </Text>
                <Text style={styles.potdIndex}>
                  Popularoo Index: {personOfTheDay.popularoo_index || Math.round(personOfTheDay.score)}
                </Text>
              </View>
              <BigOscillatingGauge score={personOfTheDay.score} size={90} />
            </View>
          </TouchableOpacity>
        )}

        {/* ===== OUTSIDER OF THE DAY (Golden Boosters only, rotates every 10s) ===== */}
        {goldenOutsiders.length > 0 && !goldenOutsiders[currentOutsiderIndex]?.name?.toLowerCase().includes('test') && (
          <Animated.View style={[styles.outsiderOfTheDaySection, { opacity: fadeAnim }]}>
            <View style={{ marginHorizontal: 16 }}>
              <OutsiderCard
                outsider={goldenOutsiders[currentOutsiderIndex]}
                onLike={handleLikeOutsider}
                pulsingHeart={true}
                badgeLabel={t("home.outsiderOfTheDay")}
                badgeCounter={goldenOutsiders.length > 1 ? `${currentOutsiderIndex + 1}/${goldenOutsiders.length}` : undefined}
              />
            </View>
          </Animated.View>
        )}

        {/* Categories */}
        <View style={styles.categoriesContainer}>
          <Text style={styles.sectionTitle}>{t("home.categoriesTitle")}</Text>
          <View style={styles.categoriesRow}>
            {CATEGORIES.map((cat) => (
              <TouchableOpacity
                key={cat.key}
                style={styles.categoryCardSmall}
                onPress={() => router.push({ pathname: "/list", params: { category: cat.key } })}
              >
                <Ionicons name={cat.icon as any} size={20} color={PALETTE.accent2} />
                <Text style={styles.categoryLabelSmall}>{t(`categories.${cat.key}`)}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Top Personalities */}
        <View style={styles.topSection}>
          <Text style={styles.sectionTitle}>{t("home.topPersonalities")}</Text>

          {loading && (
            <View style={styles.center}>
              <ActivityIndicator size="large" color={PALETTE.accent2} />
              <Text style={styles.loadingText}>{t("common.loading")}</Text>
            </View>
          )}

          {error && (
            <View style={styles.center}>
              <Text style={styles.errorText}>{t("common.error", { message: error })}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={() => loadData()}>
                <Text style={styles.retryText}>{t("common.retry")}</Text>
              </TouchableOpacity>
            </View>
          )}

          {!loading && !error && (
            <View>
              {displayedPeople.map((person, index) => {
                // Determine trend arrow with visual variety (deterministic)
                const nameHash = person.name.split('').reduce((acc: number, c: string) => acc + c.charCodeAt(0), 0);
                const hourFactor = new Date().getHours();
                const variation = (nameHash + hourFactor) % 10;
                const isUp = variation < 5;
                const isDown = variation >= 5 && variation < 8;
                const arrowIcon = isUp ? "arrow-up" : isDown ? "arrow-down" : "swap-horizontal";
                const arrowColor = isUp ? "#4CAF50" : isDown ? "#FF5252" : PALETTE.subtext;
                return (
                  <TouchableOpacity
                    key={person.id}
                    style={styles.personCard}
                    onPress={() => router.push({ pathname: "/person", params: { id: person.id, name: person.name } })}
                  >
                    <View style={styles.rankBadge}>
                      <Text style={styles.rankText}>{index + 1}</Text>
                    </View>
                    <View style={styles.personInfo}>
                      <Text style={styles.personName}>{person.name}</Text>
                      <Text style={styles.personMeta}>
                        {t(`categories.${person.category}`) || capitalize(person.category)} • {formatNumber(person.total_votes)} {person.total_votes <= 1 ? t("common.vote") : t("common.votes")}
                      </Text>
                    </View>
                    <View style={[styles.gaugeContainer, { flexDirection: 'row', alignItems: 'center' }]}>
                      <Ionicons name={arrowIcon as any} size={20} color={arrowColor} />
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}
        </View>

        {/* Bottom spacing */}
        <View style={{ height: 80 }} />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  header: { padding: 20, alignItems: "center" },
  title: { fontSize: 32, fontWeight: "bold", color: PALETTE.text },
  subtitle: { fontSize: 14, color: PALETTE.subtext, marginTop: 4 },

  // Search Box
  searchCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  searchLabel: { color: PALETTE.text, fontSize: 16, fontWeight: "600", marginBottom: 10 },
  searchRow: { flexDirection: "row", gap: 10 },
  suggestionsContainer: {
    marginTop: 8,
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
    overflow: 'hidden',
  },
  suggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PALETTE.border,
    gap: 8,
  },
  suggestionText: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '500',
    flex: 1,
  },
  suggestionMeta: {
    color: PALETTE.subtext,
    fontSize: 11,
  },
  searchInput: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: PALETTE.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  searchButton: {
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 24,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  searchButtonText: { color: PALETTE.text, fontWeight: "700", fontSize: 16 },

  // Personality of the Day
  potdCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: PALETTE.gold,
  },
  potdBadge: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 12 },
  potdBadgeText: { color: PALETTE.gold, fontSize: 14, fontWeight: "700" },
  potdContent: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  potdInfo: { flex: 1 },
  potdName: { color: PALETTE.text, fontSize: 22, fontWeight: "700" },
  potdMeta: { color: PALETTE.subtext, fontSize: 14, marginTop: 4 },
  potdIndex: { color: PALETTE.gold, fontSize: 14, fontWeight: "600", marginTop: 4 },

  // ===== Outsider of the Day =====
  outsiderOfTheDaySection: { marginTop: 16 },
  outsiderOfTheDayCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: PALETTE.gold,
  },
  outsiderOfTheDayBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 10,
  },
  outsiderOfTheDayBadgeText: {
    color: PALETTE.gold,
    fontSize: 14,
    fontWeight: "700",
    flex: 1,
  },
  outsiderOfTheDayCounter: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontWeight: "600",
  },
  outsiderOfTheDayName: {
    color: PALETTE.gold,
    fontSize: 20,
    fontWeight: "700",
    marginBottom: 6,
  },
  outsiderOfTheDayMeta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  outsiderOfTheDayVotes: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: "600",
  },

  // Social Links
  socialLinksRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 8,
  },
  socialLinkBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: PALETTE.bg,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: PALETTE.border,
  },

  // Time badge
  timeBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    borderWidth: 1,
  },
  timeBadgeText: {
    fontSize: 11,
    fontWeight: "600",
  },

  // Categories & rest
  sectionTitle: { fontSize: 18, fontWeight: "700", color: PALETTE.text, marginBottom: 12, paddingHorizontal: 16 },
  categoriesContainer: { marginTop: 16 },
  categoriesRow: { flexDirection: "row", paddingHorizontal: 16, gap: 8 },
  categoryCardSmall: {
    flex: 1,
    backgroundColor: PALETTE.card,
    padding: 10,
    borderRadius: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  categoryLabelSmall: { color: PALETTE.text, fontSize: 11, fontWeight: "600", marginTop: 4 },
  topSection: { marginTop: 20, paddingBottom: 8 },
  center: { padding: 40, alignItems: "center" },
  loadingText: { color: PALETTE.subtext, marginTop: 10 },
  errorText: { color: "#E04F5F", fontSize: 16 },
  retryBtn: { marginTop: 20, backgroundColor: PALETTE.accent, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  retryText: { color: PALETTE.text, fontWeight: "600" },
  personCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginBottom: 10,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  rankBadge: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: PALETTE.accent,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  rankText: { color: PALETTE.text, fontWeight: "700", fontSize: 14 },
  personInfo: { flex: 1 },
  personName: { fontSize: 16, fontWeight: "600", color: PALETTE.text },
  personMeta: { fontSize: 13, color: PALETTE.subtext, marginTop: 2 },
  gaugeContainer: { marginLeft: 8 },

  // "Your Spot is Waiting" section
  spotSection: {
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 8,
    padding: 24,
    borderRadius: 16,
    backgroundColor: "#FFD70008",
    borderWidth: 1.5,
    borderColor: "#FFD70050",
    borderStyle: "dashed",
    alignItems: "center",
  },
  spotCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 14,
  },
  spotAvatarCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#FFD70020",
    borderWidth: 1.5,
    borderColor: "#FFD700",
    alignItems: "center",
    justifyContent: "center",
  },
  spotAvatarText: {
    color: "#FFD700",
    fontSize: 20,
    fontWeight: "800",
  },
  spotYou: {
    color: "#FFD700",
    fontSize: 22,
    fontWeight: "800",
    letterSpacing: 2,
  },
  spotTitle: {
    color: "#EAEAEA",
    fontSize: 17,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 6,
  },
  spotSub: {
    color: "#C9D8D2",
    fontSize: 12,
    textAlign: "center",
    lineHeight: 18,
  },
});
