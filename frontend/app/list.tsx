import React, { useCallback, useEffect, useMemo, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, StyleSheet, Text, TouchableOpacity, View, FlatList, useWindowDimensions, ScrollView } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import * as Localization from "expo-localization";

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
  const [rotationKey, setRotationKey] = useState(0);

  // Update selected category if params change
  useEffect(() => {
    if (params.category) {
      setSelectedCategory(params.category);
    }
  }, [params.category]);

  const load = useCallback(async () => {
    try {
      const regionCode = Localization.getLocales()?.[0]?.regionCode || '';
      const countryParam = regionCode ? `&country=${regionCode}` : '';
      const data = await apiGet<Person[]>(`/people?limit=300${countryParam}`);
      setPeople(data);
    } catch (error) {
      console.error("Failed to load top 300:", error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Rotation every 6 minutes for "market movement" effect
    const interval = setInterval(() => load(), 360000);
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
    // Determine arrow direction with visual variety
    // Use a deterministic hash based on person name + current hour for daily consistency
    const nameHash = item.name.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    const hourFactor = new Date().getHours();
    const variation = (nameHash + hourFactor) % 10;
    
    // ~50% up, ~30% down, ~20% equal for credibility
    let arrowIcon: string;
    let arrowColor: string;
    if (variation < 5) { // 50% up
      arrowIcon = "arrow-up";
      arrowColor = PALETTE.green;
    } else if (variation < 8) { // 30% down
      arrowIcon = "arrow-down";
      arrowColor = PALETTE.accent;
    } else { // 20% equal
      arrowIcon = "swap-horizontal";
      arrowColor = PALETTE.subtext;
    }
    
    // Glow effect: items going up get subtle highlight
    const isGlowing = variation < 3;
    
    return (
      <TouchableOpacity
        style={[styles.row, isGlowing && styles.glowRow]}
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
          <Ionicons name={arrowIcon as any} size={22} color={arrowColor} />
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
  glowRow: {
    backgroundColor: "rgba(76, 175, 80, 0.06)",
    borderLeftWidth: 2,
    borderLeftColor: "#4CAF50",
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
