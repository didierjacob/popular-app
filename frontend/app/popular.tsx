import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, Animated, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";

const PALETTE = {
  bg: "#0F2F22", // greener
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000", // dark red (up)
  green: "#009B4D", // dark green (down)
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
  category?: "politics" | "culture" | "business" | "other";
  score: number;
  total_votes: number;
}

type Direction = "up" | "down" | "flat";

type FilterCat = "all" | "politics" | "culture" | "business" | "sport";

async function apiPost<T>(path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(API(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} ${res.status}`);
  return res.json();
}

const DEVICE_KEY = "popularity_device_id";
async function getDeviceId() {
  let id = await AsyncStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

export default function Popular() {
  const router = useRouter();
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const prevScoresRef = useRef<Record<string, number>>({});
  const [dirs, setDirs] = useState<Record<string, Direction>>({});
  const [filter, setFilter] = useState<FilterCat>("all");

  // persist last selected category
  const loadSavedFilter = useCallback(async () => {
    try {
      const saved = await AsyncStorage.getItem("popularity_popular_filter");
      if (saved === "all" || saved === "politics" || saved === "culture" || saved === "business" || saved === "sport") {
        setFilter(saved as FilterCat);
      }
    } catch {}
  }, []);

  useEffect(() => { loadSavedFilter(); }, [loadSavedFilter]);
  useEffect(() => { AsyncStorage.setItem("popularity_popular_filter", filter).catch(() => {}); }, [filter]);

  const load = useCallback(async () => {
    try {
      const qry = filter === "all" ? "" : `?category=${filter}`;
      const list = await apiGet<Person[]>(`/people${qry}`);
      
      // Select random 15 personalities for instant polling
      const shuffled = [...list].sort(() => Math.random() - 0.5);
      const randomSelection = shuffled.slice(0, 15);
      
      // Compute direction animation for new scores
      const nextDirs: Record<string, Direction> = {};
      randomSelection.forEach((p) => {
        const prev = prevScoresRef.current[p.id];
        if (prev !== undefined) {
          if (p.score > prev) nextDirs[p.id] = "up";
          else if (p.score < prev) nextDirs[p.id] = "down";
          else nextDirs[p.id] = "flat";
        } else {
          nextDirs[p.id] = "flat";
        }
      });
      // update caches
      prevScoresRef.current = Object.fromEntries(randomSelection.map(p => [p.id, p.score]));
      setDirs(nextDirs);
      setItems(randomSelection);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
    const i = setInterval(load, 5000);
    return () => clearInterval(i);
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const displayed = useMemo(() => {
    return items; // filtering now handled in load function
  }, [items]);

  const renderItem = ({ item }: { item: Person }) => (
    <Row 
      item={item} 
      dir={dirs[item.id] || "flat"} 
      onOpen={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}
    />
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={PALETTE.accent2} /></View>
      ) : (
        <>
          <View style={styles.header}>
            <Text style={styles.headerTitle}>Instant polling</Text>
          </View>
          <FilterBar filter={filter} setFilter={setFilter} />
          <FlashList
            data={displayed}
            keyExtractor={(it) => it.id}
            renderItem={renderItem}
            estimatedItemSize={76}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
            contentContainerStyle={{ paddingBottom: 24 }}
          />
        </>
      )}
    </SafeAreaView>
  );
}

function FilterBar({ filter, setFilter }: { filter: FilterCat; setFilter: (v: FilterCat) => void }) {
  const tabs: { key: FilterCat; label: string }[] = [
    { key: "all", label: "All" },
    { key: "politics", label: "Politics" },
    { key: "culture", label: "Culture" },
    { key: "business", label: "Business" },
    { key: "sport", label: "Sport" },
  ];
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 8 }}>
      {tabs.map(t => {
        const active = filter === t.key;
        return (
          <TouchableOpacity key={t.key} onPress={() => setFilter(t.key)} style={[styles.chip, active ? { backgroundColor: PALETTE.accent } : {}]}>
            <Text style={[styles.chipText, active ? { color: "white" } : {}]}>{t.label}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

function Row({ item, dir, onOpen }: { item: Person; dir: Direction; onOpen: () => void }) {
  const scale = useRef(new Animated.Value(1)).current;
  const rot = useRef(new Animated.Value(0)).current; // 0..1

  useEffect(() => {
    if (dir === "flat") return;
    Animated.parallel([
      Animated.sequence([
        Animated.timing(scale, { toValue: 1.08, duration: 120, useNativeDriver: true }),
        Animated.timing(scale, { toValue: 1.0, duration: 120, useNativeDriver: true }),
      ]),
      Animated.sequence([
        Animated.timing(rot, { toValue: 1, duration: 120, useNativeDriver: true }),
        Animated.timing(rot, { toValue: 0, duration: 120, useNativeDriver: true }),
      ]),
    ]).start();
  }, [dir, scale, rot]);

  const iconColor = dir === "up" ? PALETTE.accent : dir === "down" ? PALETTE.green : PALETTE.subtext;
  const arrowChar = dir === "up" ? "▲" : dir === "down" ? "▼" : "–";
  const styleAnim = {
    transform: [
      { scale },
      { rotate: rot.interpolate({ inputRange: [0, 1], outputRange: ["0deg", dir === "up" ? "-6deg" : "6deg"] }) },
    ],
  } as any;

  return (
    <TouchableOpacity style={styles.row} onPress={onOpen}>
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.meta}>{capitalize(item.category || 'other')} • Score {formatNumber(item.score)} • {formatNumber(item.total_votes)} votes</Text>
      </View>
      <View style={styles.indicator}>
        <Animated.View accessible accessibilityLabel={`direction-${dir}`} style={styleAnim}>
          <Text style={{ color: iconColor, fontWeight: '800' }}>{arrowChar}</Text>
        </Animated.View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  headerTitle: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: '700',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  name: { color: PALETTE.text, fontSize: 16, fontWeight: '600' },
  meta: { color: PALETTE.subtext, marginTop: 4 },
  indicator: { width: 28, alignItems: 'center' },
  chip: {
    backgroundColor: PALETTE.card,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  chipText: { color: PALETTE.text, fontWeight: '600' },
});
