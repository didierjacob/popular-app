import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, StyleSheet, Text, TouchableOpacity, View, FlatList } from "react-native";
import { useRouter } from "expo-router";

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

export default function List() {
  const router = useRouter();
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<Person[]>("/people?limit=20");
      setPeople(data);
    } catch (error) {
      console.error("Failed to load top 20:", error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(() => load(), 5000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  const renderItem = ({ item, index }: { item: Person; index: number }) => (
    <TouchableOpacity
      style={styles.row}
      onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}
    >
      <View style={styles.rank}>
        <Text style={styles.rankText}>#{index + 1}</Text>
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.name} numberOfLines={1} ellipsizeMode="tail">{item.name}</Text>
        <Text style={styles.meta} numberOfLines={1} ellipsizeMode="tail">
          {item.category} • Score {item.score} • {item.total_votes} votes
        </Text>
      </View>
      <View style={styles.scoreBox}>
        <Text style={styles.scoreText} numberOfLines={1}>{formatNumber(item.score)}</Text>
      </View>
    </TouchableOpacity>
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
      <View style={styles.header}>
        <Text style={styles.title}>Top 20 Popular</Text>
      </View>
      <FlashList
        data={people}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        estimatedItemSize={70}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />
        }
        contentContainerStyle={{ paddingBottom: 24 }}
      />
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
  scoreBox: {
    backgroundColor: PALETTE.card,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingHorizontal: 12,
    paddingVertical: 8,
    minWidth: 50,
    alignItems: "center",
  },
  scoreText: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: "700",
  },
});
