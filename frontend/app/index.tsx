import React, { useEffect, useState, useRef } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  RefreshControl,
  Animated,
  Easing,
  FlatList,
  Linking,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { CreditsService, type OutsiderData } from "../services/creditsService";

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
}

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

// ---- Outsider Card ----

function OutsiderCard({ outsider, isGolden }: { outsider: OutsiderData; isGolden: boolean }) {
  const router = useRouter();

  return (
    <TouchableOpacity
      style={[
        styles.outsiderCard,
        isGolden ? styles.goldenCard : styles.regularCard,
        isGolden && { minWidth: 260 },
      ]}
      onPress={() => router.push({ pathname: "/person", params: { id: outsider.id, name: outsider.name } })}
      activeOpacity={0.7}
    >
      <View style={styles.outsiderBadge}>
        <Ionicons
          name={isGolden ? "trophy" : "rocket"}
          size={14}
          color={isGolden ? PALETTE.gold : PALETTE.accent2}
        />
        <Text style={[styles.outsiderBadgeText, isGolden && { color: PALETTE.gold }]}>
          {outsider.tier_name}
        </Text>
        <TimeRemainingBadge hours={outsider.hours_remaining} />
      </View>

      <Text style={[styles.outsiderName, isGolden && { color: PALETTE.gold }]}>
        {outsider.name}
      </Text>

      <Text style={styles.outsiderMeta}>
        {formatNumber(outsider.total_votes)} {outsider.total_votes <= 1 ? 'vote' : 'votes'}
      </Text>

      <SocialLinksRow links={outsider.social_links} />
    </TouchableOpacity>
  );
}

// ---- Main Component ----

export default function HomeScreen() {
  const router = useRouter();
  const [people, setPeople] = useState<Person[]>([]);
  const [personOfTheDay, setPersonOfTheDay] = useState<Person | null>(null);
  const [goldenOutsiders, setGoldenOutsiders] = useState<OutsiderData[]>([]);
  const [regularOutsiders, setRegularOutsiders] = useState<OutsiderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchName, setSearchName] = useState("");
  const titleTapCount = useRef(0);
  const titleTapTimer = useRef<NodeJS.Timeout | null>(null);

  const loadData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);

      const [peopleRes, outsidersData] = await Promise.all([
        fetch(API("/people?limit=10")),
        CreditsService.getOutsiders(),
      ]);

      if (!peopleRes.ok) throw new Error(`HTTP ${peopleRes.status}`);
      const data = await peopleRes.json();

      const sortedByVotes = [...data].sort((a: Person, b: Person) => b.total_votes - a.total_votes);
      setPeople(sortedByVotes);

      if (data.length > 0) {
        const sorted = [...data].sort((a: Person, b: Person) => b.score - a.score);
        setPersonOfTheDay(sorted[0]);
      }

      setGoldenOutsiders(outsidersData.golden || []);
      setRegularOutsiders(outsidersData.regular || []);

    } catch (e: any) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(true), 10000);
    return () => clearInterval(interval);
  }, []);

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
    try {
      const response = await fetch(API(`/search?query=${encodeURIComponent(searchName.trim())}`));
      if (response.ok) {
        const results = await response.json();
        if (results.length > 0) {
          router.push({ pathname: "/person", params: { id: results[0].id, name: results[0].name } });
          setSearchName("");
          return;
        }
      }
    } catch {}
    alert(`"${searchName}" not found. Try another name.`);
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={{ flex: 1 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={handleTitleTap} activeOpacity={0.8}>
            <Text style={styles.title}>Popular</Text>
          </TouchableOpacity>
          <Text style={styles.subtitle}>Rate & rank personalities</Text>
        </View>

        {/* Search Box */}
        <View style={styles.searchCard}>
          <Text style={styles.searchLabel}>Rate a personality</Text>
          <View style={styles.searchRow}>
            <TextInput
              style={styles.searchInput}
              placeholder="Enter a name"
              placeholderTextColor={PALETTE.subtext}
              value={searchName}
              onChangeText={setSearchName}
              onSubmitEditing={handleSearch}
            />
            <TouchableOpacity style={styles.searchButton} onPress={handleSearch}>
              <Text style={styles.searchButtonText}>Rate</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Personality of the Day */}
        {personOfTheDay && (
          <TouchableOpacity
            style={styles.potdCard}
            onPress={() => router.push({ pathname: "/person", params: { id: personOfTheDay.id, name: personOfTheDay.name } })}
          >
            <View style={styles.potdBadge}>
              <Ionicons name="star" size={16} color={PALETTE.gold} />
              <Text style={styles.potdBadgeText}>Personality of the Day</Text>
            </View>
            <View style={styles.potdContent}>
              <View style={styles.potdInfo}>
                <Text style={styles.potdName}>{personOfTheDay.name}</Text>
                <Text style={styles.potdMeta}>
                  {capitalize(personOfTheDay.category)} • {formatNumber(personOfTheDay.total_votes)} votes
                </Text>
                <Text style={styles.potdVotes}>
                  {formatNumber(personOfTheDay.total_votes)} {personOfTheDay.total_votes <= 1 ? 'vote' : 'votes'}
                </Text>
              </View>
              <BigOscillatingGauge score={personOfTheDay.score} size={90} />
            </View>
          </TouchableOpacity>
        )}

        {/* ===== GOLDEN OUTSIDERS (under Personality of the Day) ===== */}
        {goldenOutsiders.length > 0 && (
          <View style={styles.goldenSection}>
            <View style={styles.goldenSectionHeader}>
              <Ionicons name="trophy" size={18} color={PALETTE.gold} />
              <Text style={styles.goldenSectionTitle}>Featured Outsiders</Text>
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.goldenScrollContent}
            >
              {goldenOutsiders.map((outsider) => (
                <OutsiderCard key={outsider.id} outsider={outsider} isGolden={true} />
              ))}
            </ScrollView>
          </View>
        )}

        {/* Categories */}
        <View style={styles.categoriesContainer}>
          <Text style={styles.sectionTitle}>Categories</Text>
          <View style={styles.categoriesRow}>
            {CATEGORIES.map((cat) => (
              <TouchableOpacity
                key={cat.key}
                style={styles.categoryCardSmall}
                onPress={() => router.push({ pathname: "/category/[key]", params: { key: cat.key } })}
              >
                <Ionicons name={cat.icon as any} size={20} color={PALETTE.accent2} />
                <Text style={styles.categoryLabelSmall}>{cat.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Top Personalities */}
        <View style={styles.topSection}>
          <Text style={styles.sectionTitle}>Top Personalities</Text>

          {loading && (
            <View style={styles.center}>
              <ActivityIndicator size="large" color={PALETTE.accent2} />
              <Text style={styles.loadingText}>Loading...</Text>
            </View>
          )}

          {error && (
            <View style={styles.center}>
              <Text style={styles.errorText}>Error: {error}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={() => loadData()}>
                <Text style={styles.retryText}>Retry</Text>
              </TouchableOpacity>
            </View>
          )}

          {!loading && !error && people.map((person, index) => (
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
                  {capitalize(person.category)} • {formatNumber(person.total_votes)} {person.total_votes <= 1 ? 'vote' : 'votes'}
                </Text>
              </View>
              <View style={styles.gaugeContainer}>
                <GaugeIcon score={person.score} size={36} />
              </View>
            </TouchableOpacity>
          ))}
        </View>

        {/* ===== REGULAR OUTSIDERS (below Top Personalities) ===== */}
        {regularOutsiders.length > 0 && (
          <View style={styles.regularSection}>
            <View style={styles.regularSectionHeader}>
              <Ionicons name="rocket" size={18} color={PALETTE.accent2} />
              <Text style={styles.regularSectionTitle}>Outsiders</Text>
            </View>
            {regularOutsiders.map((outsider) => (
              <OutsiderCard key={outsider.id} outsider={outsider} isGolden={false} />
            ))}
          </View>
        )}

        {/* Bottom spacing */}
        <View style={{ height: 24 }} />
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
  potdVotes: { color: PALETTE.accent2, fontSize: 14, fontWeight: "600", marginTop: 4 },

  // ===== Golden Outsiders Section =====
  goldenSection: { marginTop: 16 },
  goldenSectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    marginBottom: 10,
  },
  goldenSectionTitle: { color: PALETTE.gold, fontSize: 16, fontWeight: "700" },
  goldenScrollContent: { paddingHorizontal: 16, gap: 12 },

  // ===== Regular Outsiders Section =====
  regularSection: { marginTop: 24, paddingHorizontal: 16 },
  regularSectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  regularSectionTitle: { color: PALETTE.accent2, fontSize: 16, fontWeight: "700" },

  // ===== Outsider Card =====
  outsiderCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  goldenCard: {
    borderWidth: 2,
    borderColor: PALETTE.gold,
  },
  regularCard: {
    borderWidth: 1,
    borderColor: PALETTE.accent2,
  },
  outsiderBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 8,
  },
  outsiderBadgeText: {
    color: PALETTE.accent2,
    fontSize: 12,
    fontWeight: "700",
    flex: 1,
  },
  outsiderName: {
    color: PALETTE.accent2,
    fontSize: 18,
    fontWeight: "700",
  },
  outsiderMeta: {
    color: PALETTE.subtext,
    fontSize: 13,
    marginTop: 4,
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
});
