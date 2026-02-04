import React, { useCallback, useEffect, useMemo, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  border: "#2E6148",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const capitalize = (str: string) => str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
const formatNumber = (num: number) => Math.round(num).toLocaleString();

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

interface Person { id: string; name: string; category?: string; score: number; total_votes: number }

const CATEGORY_LABELS: Record<string, string> = {
  politics: "Politics",
  culture: "Culture",
  business: "Business",
  sport: "Sport",
};

export default function CategoryList() {
  const router = useRouter();
  const params = useLocalSearchParams<{ key: string }>();
  const catKey = (params.key as string) || "all";
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const title = useMemo(() => CATEGORY_LABELS[catKey] || capitalize(catKey), [catKey]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const qs = catKey && catKey !== "all" ? `?category=${encodeURIComponent(catKey)}` : "";
      const data = await apiGet<Person[]>(`/people${qs}`);
      setItems([...data].sort((a, b) => b.score - a.score));
    } catch (e) {
      console.error(e);
    } finally { 
      if (!silent) setLoading(false); 
    }
  }, [catKey]);

  useEffect(() => { 
    load(false); 
    const i = setInterval(() => load(true), 5000); 
    return () => clearInterval(i); 
  }, [load]);

  const onRefresh = useCallback(async () => { 
    setRefreshing(true); 
    await load(true); 
    setRefreshing(false); 
  }, [load]);

  const renderItem = ({ item }: { item: Person }) => (
    <TouchableOpacity style={styles.row} onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}>
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.meta}>
          {capitalize(item.category || 'other')} • Score {Math.round(item.score)} • {formatNumber(item.total_votes)} {item.total_votes <= 1 ? 'vote' : 'votes'}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={PALETTE.subtext} />
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      <View style={styles.headerRow}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
        </TouchableOpacity>
        <Text style={styles.title}>{title}</Text>
      </View>
      
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={PALETTE.accent2} /></View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(it) => it.id}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
  headerRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  backBtn: { marginRight: 12 },
  title: { color: PALETTE.text, fontSize: 20, fontWeight: '700' },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  name: { color: PALETTE.text, fontSize: 16, fontWeight: '600' },
  meta: { color: PALETTE.subtext, marginTop: 4, fontSize: 13 },
});
