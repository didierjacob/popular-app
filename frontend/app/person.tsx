import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LineChart } from "react-native-gifted-charts";
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

  // Calculate predictions based on vote volume, momentum, and volatility
  const predictions = useMemo(() => {
    if (!person || chart.length === 0) {
      return { dayLow: 100, dayHigh: 100, weekLow: 100, weekHigh: 100 };
    }

    const currentScore = person.score || 100;
    const totalVotes = person.total_votes || 0;
    const likes = person.likes || 0;
    const dislikes = person.dislikes || 0;

    // Calculate vote-based scaling factor (matches backend logic)
    let voteScale = 1;
    if (totalVotes >= 1000) voteScale = 50;
    else if (totalVotes >= 500) voteScale = 20;
    else if (totalVotes >= 100) voteScale = 10;
    else if (totalVotes >= 50) voteScale = 5;
    else if (totalVotes >= 10) voteScale = 2;

    // Calculate momentum from recent data (last 20% of points)
    const recentPoints = chart.slice(-Math.max(5, Math.floor(chart.length * 0.2)));
    const momentum = recentPoints.length > 1 
      ? (recentPoints[recentPoints.length - 1].score - recentPoints[0].score) / recentPoints.length
      : 0;

    // Calculate volatility (standard deviation of recent changes)
    const changes = recentPoints.slice(1).map((p, i) => p.score - recentPoints[i].score);
    const avgChange = changes.reduce((a, b) => a + b, 0) / (changes.length || 1);
    const variance = changes.reduce((sum, change) => sum + Math.pow(change - avgChange, 2), 0) / (changes.length || 1);
    const volatility = Math.sqrt(variance);

    // Estimate potential vote impact for predictions
    // Assume 10% of current vote volume might change in 24h, 30% in 7d
    const dayVoteEstimate = Math.max(5, Math.floor(totalVotes * 0.1));
    const weekVoteEstimate = Math.max(20, Math.floor(totalVotes * 0.3));

    // Calculate sentiment ratio
    const sentimentRatio = totalVotes > 0 ? likes / totalVotes : 0.5;

    // 24h predictions
    const dayImpact = dayVoteEstimate * voteScale;
    const dayLow = currentScore - dayImpact * (1 - sentimentRatio) - volatility * 2 + momentum * 5;
    const dayHigh = currentScore + dayImpact * sentimentRatio + volatility * 2 + momentum * 5;

    // 7d predictions (more volatile)
    const weekImpact = weekVoteEstimate * voteScale;
    const weekLow = currentScore - weekImpact * (1 - sentimentRatio) - volatility * 5 + momentum * 10;
    const weekHigh = currentScore + weekImpact * sentimentRatio + volatility * 5 + momentum * 10;

    return {
      dayLow: Math.max(0, dayLow),
      dayHigh: Math.max(currentScore, dayHigh),
      weekLow: Math.max(0, weekLow),
      weekHigh: Math.max(currentScore, weekHigh),
    };
  }, [chart, person]);

  const { dayLow, dayHigh, weekLow, weekHigh } = predictions;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {initialLoading ? (
        <View style={styles.center}> 
          <ActivityIndicator color={PALETTE.accent2} />
        </View>
      ) : (
        <ScrollView style={{ flex: 1 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}> 
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.push('/')} style={styles.homeBtn}>
              <Ionicons name="home-outline" size={20} color={PALETTE.text} />
              <Text style={styles.homeText}>Home</Text>
            </TouchableOpacity>
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
              showReferenceLine1
              referenceLine1Position={dayHigh}
              referenceLine1Config={{
                color: '#009B4D',
                thickness: 1,
                dashWidth: 4,
                dashGap: 4,
                labelText: `24h High: ${Math.round(dayHigh)}`,
                labelTextStyle: { color: '#009B4D', fontSize: 10 },
              }}
              showReferenceLine2
              referenceLine2Position={dayLow}
              referenceLine2Config={{
                color: '#8B0000',
                thickness: 1,
                dashWidth: 4,
                dashGap: 4,
                labelText: `24h Low: ${Math.round(dayLow)}`,
                labelTextStyle: { color: '#8B0000', fontSize: 10 },
              }}
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
  homeBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  homeText: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
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
