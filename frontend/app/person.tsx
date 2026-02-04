import React, { useCallback, useEffect, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, Animated, Linking, Platform, RefreshControl, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View, Easing, Share, Alert } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LineChart } from "react-native-gifted-charts";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from 'expo-haptics';
import ConfettiCannon from 'react-native-confetti-cannon';
import Svg, { Circle, Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { fetchWithCache } from "../services/cacheService";
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

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const formatNumber = (num: number) => Math.round(num).toLocaleString();

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

async function apiPost<T>(path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(API(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(headers || {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

const DEVICE_KEY = "popularity_device_id";
async function getDeviceId() {
  return await AsyncStorage.getItem(DEVICE_KEY) as string;
}

// Big Oscillating Gauge Component
function BigGaugeIcon({ score, size = 120 }: { score: number; size?: number }) {
  const oscillation = useRef(new Animated.Value(0)).current;
  
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(oscillation, { toValue: 1, duration: 1500, easing: Easing.inOut(Easing.sin), useNativeDriver: false }),
        Animated.timing(oscillation, { toValue: -1, duration: 1500, easing: Easing.inOut(Easing.sin), useNativeDriver: false }),
      ])
    ).start();
  }, []);

  // Score is 0-100, needle position based on score
  const normalizedScore = Math.min(100, Math.max(0, score));
  const baseAngle = -135 + (normalizedScore / 100) * 270;
  
  const animatedAngle = oscillation.interpolate({
    inputRange: [-1, 1],
    outputRange: [baseAngle - 3, baseAngle + 3],
  });

  const centerX = size / 2;
  const centerY = size / 2;
  const needleLength = size * 0.35;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <Defs>
          <LinearGradient id="bigGaugeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <Stop offset="0%" stopColor="#4A6858" />
            <Stop offset="50%" stopColor="#2E4A3A" />
            <Stop offset="100%" stopColor="#1C3A2C" />
          </LinearGradient>
          <LinearGradient id="bigBezelGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <Stop offset="0%" stopColor="#5A7868" />
            <Stop offset="100%" stopColor="#1C3428" />
          </LinearGradient>
        </Defs>
        
        <Circle cx={centerX} cy={centerY} r={size * 0.46} fill="url(#bigBezelGradient)" />
        <Circle cx={centerX} cy={centerY} r={size * 0.40} fill="#0F2F22" />
        <Circle cx={centerX} cy={centerY} r={size * 0.36} fill="url(#bigGaugeGradient)" />
        
        <Path
          d={`M ${centerX - size * 0.26} ${centerY + size * 0.1} A ${size * 0.28} ${size * 0.28} 0 1 1 ${centerX + size * 0.26} ${centerY + size * 0.1}`}
          stroke="#2E6148"
          strokeWidth={size * 0.04}
          fill="none"
          strokeLinecap="round"
        />
        
        <Circle cx={centerX} cy={centerY} r={size * 0.10} fill="#4A6858" />
        <Circle cx={centerX} cy={centerY} r={size * 0.06} fill="#3A5848" />
      </Svg>
      
      <Animated.View
        style={{
          position: 'absolute',
          width: needleLength,
          height: 4,
          backgroundColor: '#E04F5F',
          borderRadius: 2,
          left: centerX,
          top: centerY - 2,
          transformOrigin: 'left center',
          transform: [{
            rotate: animatedAngle.interpolate({
              inputRange: [-180, 180],
              outputRange: ['-180deg', '180deg'],
            })
          }],
        }}
      />
    </View>
  );
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
  const [person, setPerson] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  const [showConfetti, setShowConfetti] = useState(false);
  const confettiRef = useRef<any>(null);
  const likeScaleAnim = useRef(new Animated.Value(1)).current;
  const dislikeScaleAnim = useRef(new Animated.Value(1)).current;

  const { balance, useCredit, refreshBalance } = useCredits();
  const [isPremiumMode, setIsPremiumMode] = useState(false);
  const [premiumVoteCount, setPremiumVoteCount] = useState(1);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setInitialLoading(true);
    try {
      const [p, c24] = await Promise.all([
        fetchWithCache(`/people/${id}`, `person_${id}`, () => apiGet(`/people/${id}`), 2 * 60 * 1000),
        fetchWithCache(`/people/${id}/chart?window=24h`, `chart_24h_${id}`, () => apiGet(`/people/${id}/chart?window=24h`), 2 * 60 * 1000),
      ]);
      setPerson(p);
      const cRes = c24 as ChartRes;
      setName(cRes.name);
      setChart(cRes.points.map(pt => ({ t: pt.t, score: pt.score })));
    } catch (e) {
      console.error(e);
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
      if (isPremiumMode) {
        if (balance < premiumVoteCount) {
          Alert.alert('Insufficient credits', `You need ${premiumVoteCount} credits but only have ${balance}.`);
          return;
        }

        // Apply multiple premium votes
        for (let i = 0; i < premiumVoteCount; i++) {
          try {
            await useCredit(id, name, value);
          } catch (error) {
            console.error(`Premium vote ${i + 1} failed:`, error);
            break;
          }
        }
        
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
        setShowConfetti(true);
        setTimeout(() => setShowConfetti(false), 3000);
        await Promise.all([fetchData(true), refreshBalance()]);
        
        Alert.alert('✨ Premium Votes Applied!', `Applied ${premiumVoteCount} x100 ${value === 1 ? 'likes' : 'dislikes'}!`);
        setIsPremiumMode(false);
        setPremiumVoteCount(1);
        return;
      }

      const scaleAnim = value === 1 ? likeScaleAnim : dislikeScaleAnim;
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      
      Animated.sequence([
        Animated.timing(scaleAnim, { toValue: 1.3, duration: 100, useNativeDriver: true }),
        Animated.timing(scaleAnim, { toValue: 1, duration: 100, useNativeDriver: true }),
      ]).start();
      
      const did = await getDeviceId();
      await apiPost(`/people/${id}/vote`, { value }, { "X-Device-ID": did });
      
      try {
        const VOTES_KEY = "popular_my_votes";
        const storedVotes = await AsyncStorage.getItem(VOTES_KEY);
        const votes = storedVotes ? JSON.parse(storedVotes) : [];
        votes.push({
          personId: id,
          personName: name,
          category: person?.category || "other",
          vote: value,
          timestamp: new Date().toISOString(),
        });
        await AsyncStorage.setItem(VOTES_KEY, JSON.stringify(votes.slice(-100)));
      } catch (error) {}
      
      if (value === 1) {
        setShowConfetti(true);
        setTimeout(() => setShowConfetti(false), 3000);
      }
      
      await fetchData(true);
    } catch {}
  };

  // Share functions
  const shareMessage = `Check out ${name} on Popular! Current score: ${Math.round(person?.score || 0)} with ${formatNumber(person?.total_votes || 0)} votes! 📊`;

  const shareToFacebook = async () => {
    const url = `https://www.facebook.com/sharer/sharer.php?quote=${encodeURIComponent(shareMessage)}`;
    await Linking.openURL(url);
  };

  const shareToTwitter = async () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareMessage)}`;
    await Linking.openURL(url);
  };

  const shareToInstagram = async () => {
    // Instagram doesn't have a direct share URL, so we use the native share
    try {
      await Share.share({
        message: shareMessage,
      });
    } catch (error) {
      Alert.alert('Share', 'Copy this text and share on Instagram:\n\n' + shareMessage);
    }
  };

  const shareGeneric = async () => {
    try {
      await Share.share({
        message: shareMessage,
      });
    } catch (error) {
      console.error('Share failed:', error);
    }
  };

  // Chart data with rounded values
  const lineData = chart.map((p) => ({ value: Math.round(p.score) }));

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
            <Text style={styles.meta}>
              Score {Math.round(person?.score || 0)} • {formatNumber(person?.likes || 0)} likes • {formatNumber(person?.dislikes || 0)} dislikes
            </Text>
          </View>

          {/* Big Oscillating Gauge */}
          <View style={styles.gaugeSection}>
            <BigGaugeIcon score={person?.score || 50} size={140} />
            <Text style={styles.gaugeScore}>{Math.round(person?.score || 0)}</Text>
            <Text style={styles.gaugeVotes}>{formatNumber(person?.total_votes || 0)} total votes</Text>
          </View>

          {/* Live Ratings Chart */}
          <View style={styles.card}>
            <Text style={styles.section}>Live ratings</Text>
            {lineData.length > 0 ? (
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
                formatYLabel={(val) => Math.round(Number(val)).toString()}
              />
            ) : (
              <Text style={styles.noData}>No data yet - vote to see trends!</Text>
            )}
          </View>

          {/* Premium Vote Toggle with Count Selection */}
          {balance > 0 && (
            <View style={styles.card}>
              <TouchableOpacity style={styles.premiumToggle} onPress={() => setIsPremiumMode(!isPremiumMode)}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="rocket" size={20} color="#FFD700" />
                    <Text style={styles.premiumToggleTitle}>Use my booster</Text>
                  </View>
                  <Text style={styles.premiumToggleSubtitle}>
                    {isPremiumMode ? `Active • ${balance} credits left` : `${balance} credits available`}
                  </Text>
                </View>
                <View style={[styles.toggleSwitch, isPremiumMode && styles.toggleSwitchActive]}>
                  <View style={[styles.toggleThumb, isPremiumMode && styles.toggleThumbActive]} />
                </View>
              </TouchableOpacity>
              
              {isPremiumMode && (
                <View style={styles.voteCountSelector}>
                  <Text style={styles.voteCountLabel}>Number of boosts to use:</Text>
                  <View style={styles.voteCountRow}>
                    <TouchableOpacity 
                      style={styles.voteCountBtn} 
                      onPress={() => setPremiumVoteCount(Math.max(1, premiumVoteCount - 1))}
                    >
                      <Text style={styles.voteCountBtnText}>-</Text>
                    </TouchableOpacity>
                    <TextInput
                      style={styles.voteCountInput}
                      value={String(premiumVoteCount)}
                      onChangeText={(v) => {
                        const num = parseInt(v) || 1;
                        setPremiumVoteCount(Math.min(balance, Math.max(1, num)));
                      }}
                      keyboardType="number-pad"
                    />
                    <TouchableOpacity 
                      style={styles.voteCountBtn} 
                      onPress={() => setPremiumVoteCount(Math.min(balance, premiumVoteCount + 1))}
                    >
                      <Text style={styles.voteCountBtnText}>+</Text>
                    </TouchableOpacity>
                  </View>
                  <Text style={styles.voteCountInfo}>= {premiumVoteCount * 100} votes</Text>
                </View>
              )}
            </View>
          )}

          {/* Vote Buttons */}
          <View style={[styles.row, { justifyContent: 'space-between' }]}>
            <Animated.View style={{ transform: [{ scale: likeScaleAnim }], flex: 1, marginRight: 6 }}>
              <TouchableOpacity 
                style={[styles.cta, { backgroundColor: isPremiumMode ? '#FFD700' : PALETTE.accent }]} 
                onPress={() => like(1)}
              >
                <Ionicons name={isPremiumMode ? "diamond" : "thumbs-up"} size={18} color={isPremiumMode ? "#000" : "#fff"} />
                <Text style={[styles.ctaText, isPremiumMode && { color: '#000' }]}>
                  {isPremiumMode ? `Like x${premiumVoteCount * 100}` : 'Like'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
            <Animated.View style={{ transform: [{ scale: dislikeScaleAnim }], flex: 1, marginLeft: 6 }}>
              <TouchableOpacity 
                style={[styles.cta, { backgroundColor: isPremiumMode ? '#FFD700' : PALETTE.accent2 }]} 
                onPress={() => like(-1)}
              >
                <Ionicons name={isPremiumMode ? "diamond" : "thumbs-down"} size={18} color={isPremiumMode ? "#000" : "#fff"} />
                <Text style={[styles.ctaText, isPremiumMode && { color: '#000' }]}>
                  {isPremiumMode ? `Dislike x${premiumVoteCount * 100}` : 'Dislike'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          </View>

          {/* Personality Trends */}
          <Trends />

          {/* Share Section */}
          <View style={[styles.card, { marginBottom: 30 }]}>
            <Text style={styles.section}>Share</Text>
            <View style={styles.shareGrid}>
              <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#1877F2' }]} onPress={shareToFacebook}>
                <Ionicons name="logo-facebook" size={22} color="white" />
                <Text style={styles.shareText}>Facebook</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#1DA1F2' }]} onPress={shareToTwitter}>
                <Ionicons name="logo-twitter" size={22} color="white" />
                <Text style={styles.shareText}>Twitter</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#E4405F' }]} onPress={shareToInstagram}>
                <Ionicons name="logo-instagram" size={22} color="white" />
                <Text style={styles.shareText}>Instagram</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.shareButton, { backgroundColor: PALETTE.accent }]} onPress={shareGeneric}>
                <Ionicons name="share-outline" size={22} color="white" />
                <Text style={styles.shareText}>More</Text>
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      )}
      
      {showConfetti && (
        <ConfettiCannon count={200} origin={{x: -10, y: 0}} autoStart={true} ref={confettiRef} fadeOut={true} />
      )}
    </SafeAreaView>
  );
}

function Trends() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  const fetchTrends = useCallback(async () => {
    try {
      const res = await apiGet<any[]>("/trends?window=60m&limit=10");
      setItems(res);
    } catch (e) {
      console.error("Failed to fetch trends:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrends();
    const i = setInterval(fetchTrends, 5000);
    return () => clearInterval(i);
  }, [fetchTrends]);

  if (loading) {
    return (
      <View style={styles.card}>
        <Text style={styles.section}>Personality trends (live)</Text>
        <ActivityIndicator color={PALETTE.accent2} style={{ paddingVertical: 20 }} />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.card}>
        <Text style={styles.section}>Personality trends (live)</Text>
        <Text style={styles.noData}>No trends data yet - votes will appear here!</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.section}>Personality trends (live)</Text>
      {items.map((it) => {
        const delta = Math.round(it.delta);
        const isPositive = delta > 0;
        const isNegative = delta < 0;
        const deltaColor = isPositive ? '#00E676' : isNegative ? '#FF5252' : PALETTE.subtext;
        const arrow = isPositive ? '↗' : isNegative ? '↘' : '→';
        return (
          <View key={it.id} style={styles.trendRow}>
            <Text style={styles.trendName}>{it.name}</Text>
            <Text style={[styles.trendDelta, { color: deltaColor }]}>
              {arrow} {isPositive ? `+${delta}` : delta}
            </Text>
          </View>
        );
      })}
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
  gaugeSection: { alignItems: 'center', paddingVertical: 20 },
  gaugeScore: { color: PALETTE.text, fontSize: 32, fontWeight: '700', marginTop: 10 },
  gaugeVotes: { color: PALETTE.subtext, fontSize: 14, marginTop: 4 },
  card: { backgroundColor: PALETTE.card, marginHorizontal: 16, marginTop: 16, borderRadius: 12, padding: 12, borderColor: PALETTE.border, borderWidth: 1 },
  section: { color: PALETTE.subtext, marginBottom: 8, fontWeight: '600' },
  noData: { color: PALETTE.subtext, textAlign: 'center', paddingVertical: 20, fontStyle: 'italic' },
  row: { flexDirection: 'row', gap: 12, marginHorizontal: 16, marginTop: 16 },
  cta: { flex: 1, height: 52, borderRadius: 10, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 },
  ctaText: { color: 'white', fontWeight: '700', fontSize: 16 },
  trendRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  trendName: { color: PALETTE.text, flex: 1 },
  trendDelta: { fontWeight: '700' },
  shareGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  shareButton: { flex: 1, minWidth: '45%', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, paddingHorizontal: 12, borderRadius: 8 },
  shareText: { color: 'white', fontWeight: '600', fontSize: 13 },
  premiumToggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  premiumToggleTitle: { color: '#FFD700', fontSize: 16, fontWeight: '700' },
  premiumToggleSubtitle: { color: PALETTE.subtext, fontSize: 12, marginTop: 2 },
  toggleSwitch: { width: 50, height: 28, borderRadius: 14, backgroundColor: PALETTE.border, padding: 2, justifyContent: 'center' },
  toggleSwitchActive: { backgroundColor: '#FFD700' },
  toggleThumb: { width: 24, height: 24, borderRadius: 12, backgroundColor: '#fff' },
  toggleThumbActive: { alignSelf: 'flex-end' },
  voteCountSelector: { marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: PALETTE.border },
  voteCountLabel: { color: PALETTE.text, fontSize: 14, marginBottom: 10 },
  voteCountRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12 },
  voteCountBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#FFD700', alignItems: 'center', justifyContent: 'center' },
  voteCountBtnText: { color: '#000', fontSize: 24, fontWeight: '700' },
  voteCountInput: { width: 60, height: 44, backgroundColor: PALETTE.bg, borderRadius: 8, textAlign: 'center', color: PALETTE.text, fontSize: 18, fontWeight: '700' },
  voteCountInfo: { color: '#FFD700', textAlign: 'center', marginTop: 8, fontWeight: '600' },
});
