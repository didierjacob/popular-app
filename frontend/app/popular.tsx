import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

const PALETTE = {
  bg: "#1F1F1F",
  card: "#2A2A2A",
  text: "#EAEAEA",
  subtext: "#B5B5B5",
  accent: "#8B0000",
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

export default function Popular() {
  const router = useRouter();
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const prevScoresRef = useRef<Record<string, number>>({});
  const [dirs, setDirs] = useState<Record<string, Direction>>({});

  const load = useCallback(async () => {
    try {
      const list = await apiGet<Person[]>("/people");
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

  const renderItem = ({ item }: { item: Person }) => {
    const dir = dirs[item.id] || "flat";
    const icon = dir === "up" ? "arrow-up" : dir === "down" ? "arrow-down" : undefined;
    const color = dir === "up" ? PALETTE.accent : dir === "down" ? PALETTE.subtext : PALETTE.subtext;

    return (
      <TouchableOpacity style={styles.row} onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.meta}>{item.category} • Score {item.score.toFixed(0)} • {item.total_votes} votes</Text>
        </View>
        <View style={styles.indicator}>
          {icon ? <Ionicons name={icon as any} size={16} color={color} /> : <View style={{ width: 16 }} />}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={PALETTE.accent2} /></View>
      ) : (
        <FlashList
          data={items}
          keyExtractor={(it) => it.id}
          renderItem={renderItem}
          estimatedItemSize={76}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      )}
    </SafeAreaView>
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
  indicator: { width: 24, alignItems: 'center' },
});
