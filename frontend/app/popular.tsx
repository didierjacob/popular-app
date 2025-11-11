import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withTiming } from "react-native-reanimated";

const PALETTE = {
  bg: "#1F1F1F",
  card: "#2A2A2A",
  text: "#EAEAEA",
  subtext: "#B5B5B5",
  accent: "#8B0000", // dark red (up)
  green: "#009B4D", // dark green (down)
  accent2: "#E04F5F",
  border: "#3A3A3A",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

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

type FilterCat = "all" | "politics" | "culture" | "business";

export default function Popular() {
  const router = useRouter();
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const prevScoresRef = useRef<Record<string, number>>({});
  const [dirs, setDirs] = useState<Record<string, Direction>>({});
  const [filter, setFilter] = useState<FilterCat>("all");

  const load = useCallback(async () => {
    try {
      const fetched = await apiGet<Person[]>("/people");
      const list = [...fetched].sort((a, b) => b.score - a.score); // highest score first
      // compute directions vs previous
      const prev = prevScoresRef.current;
      const nextDirs: Record<string, Direction> = {};
      list.forEach(p => {
        const prevVal = prev[p.id];
        if (typeof prevVal === "number") {
          if (p.score > prevVal) nextDirs[p.id] = "up";
          else if (p.score < prevVal) nextDirs[p.id] = "down";
          else nextDirs[p.id] = "flat";
        } else {
          nextDirs[p.id] = "flat";
        }
      });
      // update caches
      prevScoresRef.current = Object.fromEntries(list.map(p => [p.id, p.score]));
      setDirs(nextDirs);
      setItems(list);
    } finally {
      setLoading(false);
    }
  }, []);

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
    const base = filter === "all" ? items : items.filter(it => it.category === filter);
    return base; // already sorted by score desc
  }, [items, filter]);

  const renderItem = ({ item }: { item: Person }) => (
    <Row item={item} dir={dirs[item.id] || "flat"} onOpen={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })} />
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={PALETTE.accent2} /></View>
      ) : (
        <>
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
  const scale = useSharedValue(1);
  const rotate = useSharedValue(0); // deg

  useEffect(() => {
    if (dir === "flat") return;
    // small pulse and tilt towards direction
    scale.value = 0.95;
    rotate.value = 0;
    const target = dir === "up" ? -8 : 8; // degrees
    scale.value = withSequence(
      withTiming(1.15, { duration: 150 }),
      withTiming(1.0, { duration: 150 })
    );
    rotate.value = withSequence(
      withTiming(target, { duration: 150 }),
      withTiming(0, { duration: 150 })
    );
  }, [dir]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: scale.value },
      { rotate: `${rotate.value}deg` },
    ],
  }));

  const iconName = dir === "up" ? "arrow-up" : dir === "down" ? "arrow-down" : undefined;
  const iconColor = dir === "up" ? PALETTE.accent : dir === "down" ? PALETTE.green : PALETTE.subtext;

  return (
    <TouchableOpacity style={styles.row} onPress={onOpen}>
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.meta}>{item.category} • Score {item.score.toFixed(0)} • {item.total_votes} votes</Text>
      </View>
      <View style={styles.indicator}>
        {iconName ? (
          <Animated.View style={animatedStyle}>
            <Ionicons name={iconName as any} size={16} color={iconColor} />
          </Animated.View>
        ) : (
          <Text style={{ color: PALETTE.subtext, fontWeight: '700' }}>–</Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
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
