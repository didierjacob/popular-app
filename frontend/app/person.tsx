import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, Animated, Platform, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LineChart } from "react-native-gifted-charts";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from 'expo-haptics';
import ConfettiCannon from 'react-native-confetti-cannon';
import { fetchWithCache } from "../services/cacheService";
import { useNetworkStatus } from "../services/networkService";
import { useCredits } from "../services/creditsService";

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
  
  // Phase 1 - Vote animations
  const [showConfetti, setShowConfetti] = useState(false);
  const confettiRef = useRef<any>(null);
  const likeScaleAnim = useRef(new Animated.Value(1)).current;
  const dislikeScaleAnim = useRef(new Animated.Value(1)).current;

  // Phase 4 - Premium votes
  const { balance, useCredit, refreshBalance } = useCredits();
  const [isPremiumMode, setIsPremiumMode] = useState(false);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setInitialLoading(true);
    try {
      // Phase 4 - Cache des graphiques avec TTL de 2 minutes
      const [p, c24, c168] = await Promise.all([
        fetchWithCache(
          `/people/${id}`,
          `person_${id}`,
          () => apiGet(`/people/${id}`),
          2 * 60 * 1000 // 2 minutes
        ),
        fetchWithCache(
          `/people/${id}/chart?window=24h`,
          `chart_24h_${id}`,
          () => apiGet(`/people/${id}/chart?window=24h`),
          2 * 60 * 1000 // 2 minutes
        ),
        fetchWithCache(
          `/people/${id}/chart?window=168h`,
          `chart_168h_${id}`,
          () => apiGet(`/people/${id}/chart?window=168h`),
          5 * 60 * 1000 // 5 minutes (moins critique)
        ),
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
    try {
      // Phase 4 - Premium vote check
      if (isPremiumMode) {
        if (balance < 1) {
          alert('Crédits insuffisants!\n\nAchetez des crédits dans l\'onglet Premium pour utiliser les votes x100.');
          return;
        }

        // Confirm premium vote
        if (!confirm(`Utiliser 1 crédit pour un vote x100 ?\n\nCe vote aura 100x plus d\'impact!`)) {
          return;
        }

        try {
          // Use premium vote via API
          const result = await useCredit(id, name, value);
          
          // Premium animations (gold confetti)
          await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
          setShowConfetti(true);
          setTimeout(() => setShowConfetti(false), 3000);
          
          // Refresh data and balance
          await Promise.all([fetchData(true), refreshBalance()]);
          
          alert(`✨ Vote Premium appliqué !\n\n+${result.votes_applied} votes • Nouveau score: ${result.new_score}\nCrédits restants: ${result.new_balance}`);
          
          // Disable premium mode after use
          setIsPremiumMode(false);
          return;
        } catch (error: any) {
          alert('Erreur: ' + (error.message || 'Échec du vote premium'));
          return;
        }
      }

      // Normal vote (existing logic)
      // Phase 1 - Trigger animations
      const scaleAnim = value === 1 ? likeScaleAnim : dislikeScaleAnim;
      
      // Haptic feedback
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      
      // Button bounce animation
      Animated.sequence([
        Animated.timing(scaleAnim, {
          toValue: 1.3,
          duration: 100,
          useNativeDriver: true,
        }),
        Animated.timing(scaleAnim, {
          toValue: 1,
          duration: 100,
          useNativeDriver: true,
        }),
      ]).start();
      
      // Vote API call
      const did = await getDeviceId();
      await apiPost(`/people/${id}/vote`, { value }, { "X-Device-ID": did });
      
      // Phase 2 - Save vote to history
      try {
        const VOTES_KEY = "popular_my_votes";
        const storedVotes = await AsyncStorage.getItem(VOTES_KEY);
        const votes = storedVotes ? JSON.parse(storedVotes) : [];
        
        // Add new vote
        votes.push({
          personId: id,
          personName: name,
          category: person?.category || "other",
          vote: value,
          timestamp: new Date().toISOString(),
        });
        
        // Keep only last 100 votes
        const recentVotes = votes.slice(-100);
        await AsyncStorage.setItem(VOTES_KEY, JSON.stringify(recentVotes));
      } catch (error) {
        console.error("Failed to save vote history:", error);
      }
      
      // Show confetti for positive votes
      if (value === 1) {
        setShowConfetti(true);
        setTimeout(() => setShowConfetti(false), 3000);
      }
      
      await fetchData(true);
    } catch {}
  };

  // Build datasets
  const lineData = chart.map((p) => ({ value: p.score }));

  const shareToFacebook = async () => {
    if (Platform.OS === 'web') {
      alert('Le partage social n\'est disponible que sur mobile');
      return;
    }
    
    try {
      const Share = require('react-native-share').default;
      const message = `Découvrez la popularité de ${name} sur Popular ! Score actuel : ${person?.score?.toFixed(0)} 📊`;
      
      await Share.shareSingle({
        social: Share.Social.FACEBOOK,
        message: message,
      });
    } catch (error) {
      console.error('Share to Facebook failed:', error);
    }
  };

  const shareToTwitter = async () => {
    if (Platform.OS === 'web') {
      alert('Le partage social n\'est disponible que sur mobile');
      return;
    }
    
    try {
      const Share = require('react-native-share').default;
      const message = `Découvrez la popularité de ${name} sur Popular ! Score actuel : ${person?.score?.toFixed(0)} 📊`;
      
      await Share.shareSingle({
        social: Share.Social.TWITTER,
        message: message,
      });
    } catch (error) {
      console.error('Share to Twitter failed:', error);
    }
  };

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
                color: '#00D866',
                thickness: 2,
                dashWidth: 8,
                dashGap: 6,
                labelText: `24h High: ${Math.round(dayHigh)}`,
                labelTextStyle: { 
                  color: '#00D866', 
                  fontSize: 11, 
                  fontWeight: '600',
                  backgroundColor: 'rgba(0, 216, 102, 0.15)',
                  paddingHorizontal: 6,
                  paddingVertical: 2,
                  borderRadius: 4,
                },
              }}
              showReferenceLine2
              referenceLine2Position={dayLow}
              referenceLine2Config={{
                color: '#FF4757',
                thickness: 2,
                dashWidth: 8,
                dashGap: 6,
                labelText: `24h Low: ${Math.round(dayLow)}`,
                labelTextStyle: { 
                  color: '#FF4757', 
                  fontSize: 11, 
                  fontWeight: '600',
                  backgroundColor: 'rgba(255, 71, 87, 0.15)',
                  paddingHorizontal: 6,
                  paddingVertical: 2,
                  borderRadius: 4,
                },
              }}
            />
          </View>

          <View style={styles.card}>
            <Text style={styles.section}>Predictions</Text>
            <View style={styles.predRow}>
              <Text style={styles.predLabel}>24h</Text>
              <Text style={styles.predValue} numberOfLines={1} ellipsizeMode="tail">Low {Math.round(dayLow)} • High {Math.round(dayHigh)}</Text>
            </View>
            <View style={styles.predRow}>
              <Text style={styles.predLabel}>7d</Text>
              <Text style={styles.predValue} numberOfLines={1} ellipsizeMode="tail">Low {Math.round(weekLow)} • High {Math.round(weekHigh)}</Text>
            </View>
          </View>

          {Platform.OS !== 'web' && (
            <View style={styles.card}>
              <Text style={styles.section}>Partager</Text>
              <View style={[styles.row, { marginHorizontal: 0, marginTop: 8, gap: 8 }]}>
                <TouchableOpacity style={styles.shareButton} onPress={shareToFacebook}>
                  <Ionicons name="logo-facebook" size={20} color="white" />
                  <Text style={styles.shareText}>Facebook</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.shareButton} onPress={shareToTwitter}>
                  <Ionicons name="logo-twitter" size={20} color="white" />
                  <Text style={styles.shareText}>X (Twitter)</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Phase 4 - Premium Vote Toggle */}
          {balance > 0 && (
            <View style={styles.card}>
              <TouchableOpacity 
                style={styles.premiumToggle}
                onPress={() => setIsPremiumMode(!isPremiumMode)}
              >
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="rocket" size={20} color="#FFD700" />
                    <Text style={styles.premiumToggleTitle}>Use my booster</Text>
                  </View>
                  <Text style={styles.premiumToggleSubtitle}>
                    {isPremiumMode ? `✓ Active • ${balance} votes left` : `${balance} votes available`}
                  </Text>
                </View>
                <View style={[styles.toggleSwitch, isPremiumMode && styles.toggleSwitchActive]}>
                  <View style={[styles.toggleThumb, isPremiumMode && styles.toggleThumbActive]} />
                </View>
              </TouchableOpacity>
            </View>
          )}

          <View style={[styles.row, { justifyContent: 'space-between' }]}>
            <Animated.View style={{ transform: [{ scale: likeScaleAnim }], flex: 1, marginRight: 6 }}>
              <TouchableOpacity 
                style={[
                  styles.cta, 
                  { backgroundColor: isPremiumMode ? '#FFD700' : PALETTE.accent }
                ]} 
                onPress={() => like(1)}
              >
                {isPremiumMode && <Ionicons name="diamond" size={14} color="#000" style={{ marginRight: 4 }} />}
                <Text style={[styles.ctaText, isPremiumMode && { color: '#000' }]}>
                  Like {isPremiumMode && 'x100'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
            <Animated.View style={{ transform: [{ scale: dislikeScaleAnim }], flex: 1, marginLeft: 6 }}>
              <TouchableOpacity 
                style={[
                  styles.cta, 
                  { backgroundColor: isPremiumMode ? '#FFD700' : PALETTE.accent2 }
                ]} 
                onPress={() => like(-1)}
              >
                {isPremiumMode && <Ionicons name="diamond" size={14} color="#000" style={{ marginRight: 4 }} />}
                <Text style={[styles.ctaText, isPremiumMode && { color: '#000' }]}>
                  Dislike {isPremiumMode && 'x100'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          </View>

          <Trends />
        </ScrollView>
      )}
      
      {showConfetti && (
        <ConfettiCannon
          count={200}
          origin={{x: -10, y: 0}}
          autoStart={true}
          ref={confettiRef}
          fadeOut={true}
        />
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
  cta: { flex: 1, height: 24, borderRadius: 8, alignItems: 'center', justifyContent: 'center', flexDirection: 'row' },
  ctaText: { color: 'white', fontWeight: '700', fontSize: 12 },
  trendRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  trendName: { color: PALETTE.text },
  trendDelta: { color: PALETTE.accent2, fontWeight: '700' },
  predRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  predLabel: { color: PALETTE.subtext, fontWeight: '700', width: 40, flexShrink: 0 },
  predValue: { color: PALETTE.text, flex: 1, textAlign: 'right', flexShrink: 1 },
  shareButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: PALETTE.accent, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 8 },
  shareText: { color: 'white', fontWeight: '600', fontSize: 14 },
  // Phase 4 - Premium toggle
  premiumToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  premiumToggleTitle: {
    color: '#FFD700',
    fontSize: 16,
    fontWeight: '700',
  },
  premiumToggleSubtitle: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  toggleSwitch: {
    width: 50,
    height: 28,
    borderRadius: 14,
    backgroundColor: PALETTE.border,
    padding: 2,
    justifyContent: 'center',
  },
  toggleSwitchActive: {
    backgroundColor: '#FFD700',
  },
  toggleThumb: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#fff',
  },
  toggleThumbActive: {
    alignSelf: 'flex-end',
  },
});
