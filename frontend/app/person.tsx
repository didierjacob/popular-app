import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LineChart } from "react-native-gifted-charts";

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
async function apiPost<T>(path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(API(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

const DEVICE_KEY = "popularity_device_id";
async function getDeviceId() {
  const id = await AsyncStorage.getItem(DEVICE_KEY);
  return id as string;
}

interface ChartPoint { t: string; score: number }
interface ChartRes { id: string; name: string; points: ChartPoint[] }

export default function Person() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string; name?: string }>();
  const id = params.id as string;
  const [name, setName] = useState(params.name || "");
  const [initialLoading, setInitialLoading] = useState(true);
  const [chart, setChart] = useState<ChartPoint[]>([]);
  const [chartWeek, setChartWeek] = useState<ChartPoint[]>([]);
  const [person, setPerson] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setInitialLoading(true);
    try {
      const [p, c24, c168] = await Promise.all([
        apiGet(`/people/${id}`),
        apiGet(`/people/${id}/chart?window=24h`),
        apiGet(`/people/${id}/chart?window=168h`),
      ]);
      setPerson(p);
      const cRes = c24 as ChartRes;
      const wRes = c168 as ChartRes;
      setName(cRes.name);
      setChart(cRes.points.map(pt => ({ t: pt.t, score: pt.score })));
      setChartWeek(wRes.points.map(pt => ({ t: pt.t, score: pt.score })));
    } finally {
      if (!silent) setInitialLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData(false);
    const i = setInterval(() => fetchData(true), 5000);
    return () => clearInterval(i);
  }, [fetchData]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchData(true);
    setRefreshing(false);
  }, [fetchData]);

  const like = async (value: 1 | -1) => {
    const device = await getDeviceId();
    try {
      await apiPost(`/people/${id}/vote`, { value }, { "X-Device-ID": device || "web" });
      await fetchData(true);
    } catch {}
  };

  // Build datasets
  const lineData = chart.map((p) => ({ value: p.score }));

  // Simple predicted low/high from recent windows (UI hint, not ML)
  const dayLow = useMemo(() => Math.min(...(chart.map(p => p.score).concat(person?.score ?? []))), [chart, person]);
  const dayHigh = useMemo(() => Math.max(...(chart.map(p => p.score).concat(person?.score ?? []))), [chart, person]);
  const weekLow = useMemo(() => Math.min(...(chartWeek.map(p => p.score).concat(person?.score ?? []))), [chartWeek, person]);
  const weekHigh = useMemo(() => Math.max(...(chartWeek.map(p => p.score).concat(person?.score ?? []))), [chartWeek, person]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {initialLoading ? (
        <View style={styles.center}> 
          <ActivityIndicator color={PALETTE.accent2} />
        </View>
      ) : (
        <ScrollView style={{ flex: 1 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}> 
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.back()}><Text style={styles.back}>{"< Back"}</Text></TouchableOpacity>
            <Text style={styles.title}>{name}</Text>
            <Text style={styles.meta}>Score {person?.score?.toFixed(0)} • Likes {person?.likes} • Dislikes {person?.dislikes}</Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.section}>Live ratings</Text>
            <LineChart
              areaChart
              data={lineData}
              curved
              color={PALETTE.accent2}
              thickness={2}
              startFillColor={PALETTE.accent2}
              startOpacity={0.25}
              endOpacity={0.05}
              hideDataPoints
              yAxisColor={PALETTE.border}
              xAxisColor={PALETTE.border}
              backgroundColor={PALETTE.card}
              rulesColor={PALETTE.border}
              noOfSections={4}
              initialSpacing={0}
            />
          </View>

          <View style={styles.card}>
            <Text style={styles.section}>Predictions</Text>
            <View style={styles.predRow}>
              <Text style={styles.predLabel}>24h</Text>
              <Text style={styles.predValue}>Low {Math.round(dayLow)} • High {Math.round(dayHigh)}</Text>
            </View>
            <View style={styles.predRow}>
              <Text style={styles.predLabel}>7d</Text>
              <Text style={styles.predValue}>Low {Math.round(weekLow)} • High {Math.round(weekHigh)}</Text>
            </View>
          </View>

          <View style={[styles.row, { justifyContent: 'space-between' }]}>
            <TouchableOpacity style={[styles.cta, { backgroundColor: PALETTE.accent }]} onPress={() => like(1)}>
              <Text style={styles.ctaText}>Like</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.cta, { backgroundColor: PALETTE.accent2 }]} onPress={() => like(-1)}>
              <Text style={styles.ctaText}>Dislike</Text>
            </TouchableOpacity>
          </View>

          <Trends />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Trends() {
  const [items, setItems] = useState<any[]>([]);
  const fetchTrends = useCallback(async () => {
    try {
      const res = await apiGet<any[]>("/trends?window=60m&limit=20");
      setItems(res);
    } catch {}
  }, []);

  useEffect(() => {
    fetchTrends();
    const i = setInterval(fetchTrends, 5000);
    return () => clearInterval(i);
  }, [fetchTrends]);

  return (
    <View style={styles.card}>
      <Text style={styles.section}>Personality trends (live)</Text>
      {items.map((it) => (
        <View key={it.id} style={styles.trendRow}>
          <Text style={styles.trendName}>{it.name}</Text>
          <Text style={styles.trendDelta}>Δ {it.delta > 0 ? `+${it.delta}` : it.delta}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: PALETTE.bg },
  header: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8 },
  back: { color: PALETTE.subtext, marginBottom: 8 },
  title: { color: PALETTE.text, fontSize: 24, fontWeight: '700' },
  meta: { color: PALETTE.subtext, marginTop: 4 },
  card: { backgroundColor: PALETTE.card, marginHorizontal: 16, marginTop: 16, borderRadius: 12, padding: 12, borderColor: PALETTE.border, borderWidth: 1 },
  section: { color: PALETTE.subtext, marginBottom: 8 },
  row: { flexDirection: 'row', gap: 12, marginHorizontal: 16, marginTop: 16 },
  cta: { flex: 1, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  ctaText: { color: 'white', fontWeight: '700', fontSize: 16 },
  trendRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  trendName: { color: PALETTE.text },
  trendDelta: { color: PALETTE.accent2, fontWeight: '700' },
  predRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  predLabel: { color: PALETTE.subtext, fontWeight: '700' },
  predValue: { color: PALETTE.text },
});
