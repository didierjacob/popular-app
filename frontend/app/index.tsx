import React, { useEffect, useState, useRef, useCallback } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  AppState,
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
import RankDeltaBadge from "../components/RankDeltaBadge";
import { fetchSWR } from "../services/cacheService";
import { cacheKeyPeopleHome, cacheKeyOutsiders } from "./splash";

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
  vote_momentum?: "up" | "down" | null;
  popularoo_index?: number;
}

// Sujet 2 — Top list size kept for the Home feed (was 30 under the old Algo A).
const TOP_LIST_SIZE = 30;

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
  // Vague 4: feedback banner shown after a celebrity request is submitted
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const searchMsgTimer = useRef<NodeJS.Timeout | null>(null);
  const titleTapCount = useRef(0);
  const titleTapTimer = useRef<NodeJS.Timeout | null>(null);

  const fadeAnim = useRef(new Animated.Value(1)).current;
  // Pulsing heart animation for Outsider of the Day
  const heartPulse = useRef(new Animated.Value(1)).current;
  // Removed: listFadeAnim was used by the old periodic shuffle, replaced by Algo A

  const applyPeople = (data: any) => {
    if (!Array.isArray(data)) return;
    const sortedByVotes = [...data]
      .filter((p: Person) => p.source !== "self_boosted" && p.category !== "outsider")
      .sort((a: Person, b: Person) => b.total_votes - a.total_votes);
    setPeople(sortedByVotes);
  };

  // Chantier C — Personality of the Day is now backend-rotated hourly.
  const loadPersonOfTheDay = useCallback(async () => {
    try {
      const res = await fetch(API("/personality-of-the-day"));
      if (!res.ok) return;
      const data = (await res.json()) as Person;
      if (data && data.id) setPersonOfTheDay(data);
    } catch {
      // Silent — Home keeps the previous POTD if the fetch fails.
    }
  }, []);

  const applyOutsiders = (data: any) => {
    setGoldenOutsiders(data?.golden || []);
  };

  // SWR : lit d'abord le cache (prefetché par splash.tsx ou refresh précédent),
  // affiche instantanément, puis revalide en arrière-plan. Si aucun cache et le
  // fetch échoue, on remonte l'erreur classique.
  const loadData = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);

    const regionCode = Localization.getLocales()?.[0]?.regionCode || '';
    const countryParam = regionCode ? `&country=${regionCode}` : '';

    let hadPeopleCache = false;

    const peoplePromise = fetchSWR<any[]>(
      cacheKeyPeopleHome(regionCode),
      async () => {
        const res = await fetch(API(`/people?limit=50${countryParam}`));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      },
      {
        onCached: (data) => {
          hadPeopleCache = true;
          applyPeople(data);
          if (!silent) setLoading(false);
        },
        onFresh: applyPeople,
        onError: (err: any) => {
          if (!silent && !hadPeopleCache) setError(err?.message || 'Network error');
        },
      },
      60 * 1000,
    );

    const outsidersPromise = fetchSWR<any>(
      cacheKeyOutsiders(),
      () => CreditsService.getOutsiders() as Promise<any>,
      {
        onCached: applyOutsiders,
        onFresh: applyOutsiders,
      },
      60 * 1000,
    );

    await Promise.all([peoplePromise, outsidersPromise]);
    if (!silent) setLoading(false);
  };

  useEffect(() => {
    loadData();
    loadPersonOfTheDay();
    const interval = setInterval(() => loadData(true), 30000);
    return () => clearInterval(interval);
  }, [loadPersonOfTheDay]);

  // Chantier C — re-fetch the POTD when the app comes back to foreground,
  // so users returning after an hour see the freshly rotated profile.
  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (next === "active") loadPersonOfTheDay();
    });
    return () => sub.remove();
  }, [loadPersonOfTheDay]);

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

  // Sujet 2 — Real rank movement: mirror `people` into `displayedPeople`
  // and run a 600ms LayoutAnimation whenever the order actually changes
  // between two refreshes (replaces the old Algo A simulated drift).
  useEffect(() => {
    const top = people.slice(0, TOP_LIST_SIZE);
    setDisplayedPeople(prev => {
      const orderChanged = prev.length !== top.length
        || top.some((p, i) => p.id !== prev[i]?.id);
      if (orderChanged && prev.length > 0) {
        LayoutAnimation.configureNext(
          LayoutAnimation.create(600, LayoutAnimation.Types.easeInEaseOut, LayoutAnimation.Properties.opacity)
        );
      }
      return top;
    });
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

  // Vague 4: clear the search field + banner 3s after a request is submitted
  const scheduleSearchClear = () => {
    if (searchMsgTimer.current) clearTimeout(searchMsgTimer.current);
    searchMsgTimer.current = setTimeout(() => {
      setSearchName("");
      setSearchSuggestions([]);
      setSearchMessage(null);
    }, 3000);
  };

  const handleSearch = async (overrideText?: string) => {
    // iOS predictive-text commits the final character together with the Go event,
    // so reading `searchName` from state can miss the last char on the first tap.
    // Prefer the synchronous nativeEvent.text when available; fall back to state.
    const rawText = (overrideText ?? searchName).trim();
    if (!rawText) return;
    const query = rawText.toLowerCase();
    setSearchMessage(null);

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
      const response = await fetch(API(`/search?query=${encodeURIComponent(rawText)}`));
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

    // Vague 4: no match anywhere → submit a celebrity request, show a banner
    try {
      let did = await AsyncStorage.getItem("popularity_device_id");
      if (!did) {
        did = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        await AsyncStorage.setItem("popularity_device_id", did);
      }
      const response = await fetch(API("/submit-celebrity-request"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rawText, device_id: did }),
      });

      if (!response.ok) {
        setSearchMessage(t("search.queue_error"));
        scheduleSearchClear();
        return;
      }

      const data = await response.json();

      if (data.status === "already_exists" && data.person_id) {
        // Typo that still matched an existing profile → redirect to it
        setSearchMessage(t("search.already_exists"));
        router.push({ pathname: "/person", params: { id: data.person_id } });
        setSearchName("");
        setSearchSuggestions([]);
        setSearchMessage(null);
        return;
      } else if (data.status === "already_pending") {
        setSearchMessage(t("search.already_pending"));
      } else {
        // "queued" — also covers "rejected" (masked by the backend)
        setSearchMessage(t("search.queued_message"));
      }
      scheduleSearchClear();
    } catch {
      setSearchMessage(t("search.queue_error"));
      scheduleSearchClear();
    }
  };

  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;
  const contentStyle = isTablet ? { maxWidth: 600, alignSelf: 'center' as const, width: '100%' as const } : {};

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={isTablet ? { alignItems: 'center' } : {}}
        keyboardShouldPersistTaps="handled"
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
              onSubmitEditing={(e) => handleSearch(e.nativeEvent?.text)}
            />
            <TouchableOpacity style={styles.searchButton} onPress={() => handleSearch()}>
              <Text style={styles.searchButtonText}>{t("home.searchButton")}</Text>
            </TouchableOpacity>
          </View>
          {/* Vague 4: celebrity-request feedback banner */}
          {searchMessage && (
            <View style={styles.searchBanner}>
              <Text style={styles.searchBannerText}>{searchMessage}</Text>
            </View>
          )}
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
              <BigOscillatingGauge score={personOfTheDay.popularoo_index || personOfTheDay.score} size={90} />
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
              {displayedPeople.map((person, index) => (
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
                    <RankDeltaBadge momentum={person.vote_momentum} />
                  </View>
                </TouchableOpacity>
              ))}
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
  // Vague 4: celebrity-request feedback banner
  searchBanner: {
    marginTop: 12,
    backgroundColor: PALETTE.accent,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: PALETTE.accent2,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  searchBannerText: {
    color: PALETTE.text,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "600",
    textAlign: "center",
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
