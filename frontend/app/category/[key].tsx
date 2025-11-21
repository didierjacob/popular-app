import React, { useCallback, useEffect, useMemo, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useLocalSearchParams, useRouter } from "expo-router";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  border: "#2E6148",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

interface Person { id: string; name: string; category?: string; score: number; total_votes: number }

export default function CategoryList() {
  const router = useRouter();
  const params = useLocalSearchParams<{ key: string }>();
  const catKey = (params.key as string) || "all";
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const title = useMemo(() => {
    if (catKey === "politics") return "Politics";
    if (catKey === "culture") return "Culture";
    if (catKey === "business") return "Business";
    return "All";
  }, [catKey]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = catKey && catKey !== "all" ? `?category=${encodeURIComponent(catKey)}` : "";
      const data = await apiGet<Person[]>(`/people${qs}`);
      setItems([...data].sort((a, b) => b.score - a.score));
    } finally { setLoading(false); }
  }, [catKey]);

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, [load]);

  const onRefresh = useCallback(async () => { setRefreshing(true); await load(); setRefreshing(false); }, [load]);

  const renderItem = ({ item }: { item: Person }) => (
    <TouchableOpacity style={styles.row} onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}>
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.meta}>{item.category} • Score {item.score.toFixed(0)} • {item.total_votes} votes</Text>
      </View>
      <Text style={styles.chev}>{">"}</Text>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={PALETTE.accent2} /></View>
      ) : (
        <>
          <View style={styles.header}><Text style={styles.title}>{title}</Text></View>
          <FlashList
            data={items}
            keyExtractor={(it) => it.id}
            renderItem={renderItem}
            estimatedItemSize={72}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
          />
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  title: { color: PALETTE.text, fontSize: 20, fontWeight: '700' },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  name: { color: PALETTE.text, fontSize: 16, fontWeight: '600' },
  meta: { color: PALETTE.subtext, marginTop: 4 },
  chev: { color: PALETTE.subtext, fontWeight: '800' }
});
