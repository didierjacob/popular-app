import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, LayoutAnimation, Platform, RefreshControl, StyleSheet, Text, TouchableOpacity, UIManager, View, FlatList, useWindowDimensions, ScrollView } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import * as Localization from "expo-localization";
import { fetchSWR } from "../services/cacheService";
import RankDeltaBadge from "../components/RankDeltaBadge";

// Enable LayoutAnimation on Android (no-op on iOS).
if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",  // dark red (down/negative)
  green: "#009B4D",   // green (up/positive)
  accent2: "#E04F5F",
  border: "#2E6148",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

// Helper to capitalize first letter
const capitalize = (str: string) => str ? str.charAt(0).toUpperCase() + str.slice(1) : str;

// Helper to format numbers without decimals
const formatNumber = (num: number) => Math.round(num).toLocaleString();

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

interface Person {
  id: string;
  name: string;
  category?: string;
  score: number;
  likes: number;
  dislikes: number;
  total_votes: number;
  rank_delta_24h?: number | null;
}

const CATEGORIES = [
  { key: "all", labelKey: "categories.all" },
  { key: "politics", labelKey: "categories.politics" },
  { key: "culture", labelKey: "categories.culture" },
  { key: "business", labelKey: "categories.business" },
  { key: "sport", labelKey: "categories.sport" },
  { key: "influencer", labelKey: "categories.influencer" },
];

export default function List() {
  const router = useRouter();
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ category?: string }>();
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState(params.category || "all");
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  // Update selected category if params change
  useEffect(() => {
    if (params.category) {
      setSelectedCategory(params.category);
    }
  }, [params.category]);

  // Sujet 2 — remember the previous order so we can run a LayoutAnimation
  // when a refresh actually swaps positions (not on first load).
  const prevOrderRef = useRef<string[]>([]);

  const load = useCallback(async () => {
    const regionCode = Localization.getLocales()?.[0]?.regionCode || '';
    const countryParam = regionCode ? `&country=${regionCode}` : '';
    const cacheKey = `people_list_300_${regionCode || 'ALL'}`;

    const applyData = (data: any) => {
      if (!Array.isArray(data)) return;
      const cleaned = (data as Person[]).filter((p) =>
        (p as any).category !== "outsider" && (p as any).source !== "self_boosted"
      );
      const prevIds = prevOrderRef.current;
      const newIds = cleaned.map((p) => p.id);
      const orderChanged = prevIds.length > 0
        && (prevIds.length !== newIds.length || newIds.some((id, i) => id !== prevIds[i]));
      if (orderChanged) {
        LayoutAnimation.configureNext(
          LayoutAnimation.create(600, LayoutAnimation.Types.easeInEaseOut, LayoutAnimation.Properties.opacity)
        );
      }
      prevOrderRef.current = newIds;
      setPeople(cleaned);
    };

    await fetchSWR<Person[]>(
      cacheKey,
      () => apiGet<Person[]>(`/people?limit=300${countryParam}`),
      {
        onCached: (data) => {
          applyData(data);
          setLoading(false);
        },
        onFresh: applyData,
        onError: (e) => console.error("Failed to load top 300:", e),
      },
      60 * 1000,
    );

    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
    // Sujet 2 — refresh every 60s so rank movements surface near real time.
    const interval = setInterval(() => load(), 60000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  const filteredPeople = useMemo(() => {
    if (selectedCategory === "all") return people;
    return people.filter(p => (p.category || "other").toLowerCase() === selectedCategory.toLowerCase());
  }, [people, selectedCategory]);

  const renderItem = ({ item, index }: { item: Person; index: number }) => {
    return (
      <TouchableOpacity
        style={styles.row}
        onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}
      >
        <View style={styles.rank}>
          <Text style={styles.rankText}>{index + 1}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.name} numberOfLines={1} ellipsizeMode="tail">{item.name}</Text>
          <Text style={styles.meta} numberOfLines={1} ellipsizeMode="tail">
            {t(`categories.${item.category}`) || capitalize(item.category || 'other')} • {formatNumber(item.total_votes)} {item.total_votes <= 1 ? 'vote' : 'votes'}
          </Text>
        </View>
        <View style={styles.arrowBox}>
          <RankDeltaBadge delta={item.rank_delta_24h} hideZero />
        </View>
      </TouchableOpacity>
    );
  };

  const renderFilters = () => (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.filterRow}
    >
      {CATEGORIES.map((cat) => {
        const isActive = selectedCategory === cat.key;
        return (
          <TouchableOpacity
            key={cat.key}
            style={[styles.filterBtn, isActive && styles.filterBtnActive]}
            onPress={() => setSelectedCategory(cat.key)}
          >
            <Text style={[styles.filterText, isActive && styles.filterTextActive]}>
              {t(cat.labelKey)}
            </Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color={PALETTE.accent2} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      <View style={{ flex: 1, maxWidth: isTablet ? 600 : undefined, width: '100%', alignSelf: 'center' }}>
        <View style={styles.header}>
          <Text style={styles.title}>{t("list.title")}</Text>
        </View>
        <FlatList
          data={filteredPeople}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          ListHeaderComponent={renderFilters}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />
          }
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: PALETTE.bg,
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  title: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: "700",
  },
  subtitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 4,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  rank: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: "center",
    justifyContent: "center",
  },
  rankText: {
    color: PALETTE.accent2,
    fontWeight: "700",
    fontSize: 14,
  },
  name: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: "600",
  },
  meta: {
    color: PALETTE.subtext,
    marginTop: 4,
    fontSize: 12,
  },
  arrowBox: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: "center",
    justifyContent: "center",
  },
  // Category filters
  filterRow: {
    flexDirection: "row",
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 8,
  },
  filterBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  filterBtnActive: {
    backgroundColor: PALETTE.accent2,
    borderColor: PALETTE.accent2,
  },
  filterText: {
    color: PALETTE.subtext,
    fontSize: 13,
    fontWeight: "600",
  },
  filterTextActive: {
    color: "#FFF",
  },
});
