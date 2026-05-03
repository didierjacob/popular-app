import React, { useCallback, useEffect, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { ActivityIndicator, Animated, Linking, Platform, RefreshControl, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View, Easing, Share, Alert, useWindowDimensions } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LineChart } from "react-native-gifted-charts";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from 'expo-haptics';
import ConfettiCannon from 'react-native-confetti-cannon';
import Svg, { Circle, Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { fetchWithCache } from "../services/cacheService";
import { useTranslation } from "react-i18next";

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
interface VotesChartPoint { t: string; total_votes: number }
interface VotesChartRes { id: string; name: string; points: VotesChartPoint[] }

export default function Person() {
  const router = useRouter();
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ id: string; name?: string }>();
  const id = params.id as string;
  const [name, setName] = useState(params.name || "");
  const [initialLoading, setInitialLoading] = useState(true);
  const [chart, setChart] = useState<ChartPoint[]>([]);
  const [votesChart, setVotesChart] = useState<VotesChartPoint[]>([]);
  const [person, setPerson] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  const [showConfetti, setShowConfetti] = useState(false);
  const confettiRef = useRef<any>(null);
  const likeScaleAnim = useRef(new Animated.Value(1)).current;
  const dislikeScaleAnim = useRef(new Animated.Value(1)).current;
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setInitialLoading(true);
    try {
      const [p, c24, vc24] = await Promise.all([
        fetchWithCache(`/people/${id}`, `person_${id}`, () => apiGet(`/people/${id}`), 2 * 60 * 1000),
        fetchWithCache(`/people/${id}/chart?window=24h`, `chart_24h_${id}`, () => apiGet(`/people/${id}/chart?window=24h`), 2 * 60 * 1000),
        apiGet(`/people/${id}/votes-chart?window=24h`).catch(() => ({ points: [] })),
      ]);
      setPerson(p);
      const cRes = c24 as ChartRes;
      setName(cRes.name);
      setChart(cRes.points.map(pt => ({ t: pt.t, score: pt.score })));
      
      const vcRes = vc24 as VotesChartRes;
      setVotesChart(vcRes.points || []);
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
      const scaleAnim = value === 1 ? likeScaleAnim : dislikeScaleAnim;
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      
      Animated.sequence([
        Animated.timing(scaleAnim, { toValue: 1.3, duration: 100, useNativeDriver: true }),
        Animated.timing(scaleAnim, { toValue: 1, duration: 100, useNativeDriver: true }),
      ]).start();
      
      const did = await getDeviceId();
      const response = await fetch(API(`/people/${id}/vote`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-ID': did,
        },
        body: JSON.stringify({ value }),
      });
      
      const result = await response.json();
      
      // Check if already voted (24h limit)
      if (result.already_voted) {
        const nextVoteTime = result.next_vote_time ? new Date(result.next_vote_time) : null;
        let timeMessage = '';
        if (nextVoteTime) {
          const now = new Date();
          const hoursLeft = Math.ceil((nextVoteTime.getTime() - now.getTime()) / (1000 * 60 * 60));
          const minutesLeft = Math.ceil((nextVoteTime.getTime() - now.getTime()) / (1000 * 60)) % 60;
          if (hoursLeft > 1) {
            timeMessage = `You can vote again in ${hoursLeft} hours.`;
          } else if (hoursLeft === 1) {
            timeMessage = `You can vote again in about 1 hour.`;
          } else {
            timeMessage = `You can vote again in ${minutesLeft} minutes.`;
          }
        }
        Alert.alert(
          '⏰ Already Voted',
          `You already voted for ${name} today.\n\n${timeMessage}`,
          [{ text: 'OK' }]
        );
        return;
      }
      
      // Vote successful - update local state immediately
      if (person) {
        const updatedPerson = {
          ...person,
          total_votes: result.total_votes,
          likes: result.likes,
          dislikes: result.dislikes,
          score: result.score,
        };
        setPerson(updatedPerson);
      }
      
      // Save to local history
      try {
        const VOTES_KEY = "popular_my_votes";
        const storedVotes = await AsyncStorage.getItem(VOTES_KEY);
        const votes = storedVotes ? JSON.parse(storedVotes) : [];
        
        // Remove old vote for this person if exists
        const filteredVotes = votes.filter((v: any) => v.personId !== id);
        filteredVotes.push({
          personId: id,
          personName: name,
          category: person?.category || "other",
          vote: value,
          timestamp: new Date().toISOString(),
        });
        await AsyncStorage.setItem(VOTES_KEY, JSON.stringify(filteredVotes.slice(-100)));
      } catch (error) {}
      
      if (value === 1) {
        setShowConfetti(true);
        setTimeout(() => setShowConfetti(false), 3000);
      }
      
      // Fetch fresh data from server
      await fetchData(true);
    } catch (error) {
      console.error('Vote error:', error);
    }
  };

  // Share functions
  const shareMessage = `Check out ${name} on Popularoo! Popularoo Index: ${Math.round(person?.score || 0)} with ${formatNumber(person?.total_votes || 0)} votes! 📊`;

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
  
  // Votes chart data
  const votesLineData = votesChart.map((p) => ({ value: p.total_votes }));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {initialLoading ? (
        <View style={styles.center}> 
          <ActivityIndicator color={PALETTE.accent2} />
        </View>
      ) : (
        <ScrollView style={{ flex: 1 }} contentContainerStyle={isTablet ? { alignItems: 'center' } : {}} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}> 
          <View style={isTablet ? { maxWidth: 600, width: '100%' } : {}}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => router.push('/')} style={styles.homeBtn}>
              <Ionicons name="home-outline" size={20} color={PALETTE.text} />
              <Text style={styles.homeText}>{t("person.home")}</Text>
            </TouchableOpacity>
            <Text style={styles.title}>{name}</Text>
            <Text style={styles.meta}>
              {person?.source === "self_boosted" 
                ? `${formatNumber(person?.likes || 0)} supporters`
                : `${formatNumber(person?.likes || 0)} likes • ${formatNumber(person?.dislikes || 0)} dislikes`}
            </Text>
          </View>

          {/* Popularity Indicator */}
          <View style={styles.gaugeSection}>
            <View style={styles.popularityIndicator}>
              <Ionicons 
                name={(person?.score || 50) >= 50 ? "arrow-up-circle" : "arrow-down-circle"} 
                size={80} 
                color={(person?.score || 50) >= 50 ? "#009B4D" : "#8B0000"} 
              />
              <Text style={[
                styles.popularityText, 
                { color: (person?.score || 50) >= 50 ? "#009B4D" : "#8B0000" }
              ]}>
                {(person?.score || 50) >= 50 ? t("person.popular") : t("person.unpopular")}
              </Text>
            </View>
            <Text style={styles.gaugeVotes}>{t("person.totalVotes", { count: formatNumber(person?.total_votes || 0) })}</Text>
          </View>

          {/* Live Ratings Chart */}
          <View style={styles.card}>
            <Text style={styles.section}>{t("person.liveRatings")}</Text>
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
              <Text style={styles.noData}>{t("person.emptyChart")}</Text>
            )}
          </View>

          {/* Votes History Chart */}
          <View style={styles.card}>
            <Text style={styles.section}>{t("person.voteHistory")}</Text>
            {votesLineData.length > 1 ? (
              <LineChart
                areaChart
                data={votesLineData}
                curved
                color="#2ECC71"
                thickness={2}
                startFillColor="#2ECC71"
                startOpacity={0.25}
                endOpacity={0.05}
                hideDataPoints
                yAxisColor={PALETTE.border}
                xAxisColor={PALETTE.border}
                backgroundColor={PALETTE.card}
                rulesColor={PALETTE.border}
                noOfSections={4}
                initialSpacing={0}
                formatYLabel={(val) => formatNumber(Number(val))}
              />
            ) : (
              <View style={styles.votesChartPlaceholder}>
                <Ionicons name="bar-chart-outline" size={40} color={PALETTE.subtext} />
                <Text style={styles.noData}>{t("person.voteHistoryEmpty")}</Text>
                <Text style={styles.currentVotesText}>
                  {t("person.currentVotes", { count: formatNumber(person?.total_votes || 0) })}
                </Text>
              </View>
            )}
          </View>

          {/* Vote Buttons */}
          {person?.source === "self_boosted" ? (
            /* Boosted user: Support only (no dislike) */
            <View style={[styles.row, { justifyContent: 'center' }]}>
              <Animated.View style={{ transform: [{ scale: likeScaleAnim }], flex: 1 }}>
                <TouchableOpacity 
                  style={[styles.cta, { backgroundColor: PALETTE.gold }]} 
                  onPress={() => like(1)}
                >
                  <Ionicons name="heart" size={18} color="#0F2F22" />
                  <Text style={[styles.ctaText, { color: "#0F2F22" }]}>{t("person.voteFor", { name: name?.split(' ')[0] || '' })}</Text>
                </TouchableOpacity>
              </Animated.View>
            </View>
          ) : (
            /* Celebrity: Like + Dislike */
            <View style={[styles.row, { justifyContent: 'space-between' }]}>
              <Animated.View style={{ transform: [{ scale: likeScaleAnim }], flex: 1, marginRight: 6 }}>
                <TouchableOpacity 
                  style={[styles.cta, { backgroundColor: PALETTE.accent }]} 
                  onPress={() => like(1)}
                >
                  <Ionicons name="thumbs-up" size={18} color="#fff" />
                  <Text style={styles.ctaText}>{t("person.like")}</Text>
                </TouchableOpacity>
              </Animated.View>
              <Animated.View style={{ transform: [{ scale: dislikeScaleAnim }], flex: 1, marginLeft: 6 }}>
                <TouchableOpacity 
                  style={[styles.cta, { backgroundColor: PALETTE.accent2 }]} 
                  onPress={() => like(-1)}
                >
                  <Ionicons name="thumbs-down" size={18} color="#fff" />
                  <Text style={styles.ctaText}>{t("person.dislike")}</Text>
                </TouchableOpacity>
              </Animated.View>
            </View>
          )}

          {/* Social Follow Buttons — only for Outsiders with social links */}
          {person?.source === "self_boosted" && person?.social_links && (
            (person.social_links.instagram || person.social_links.tiktok || person.social_links.x) ? (
              <View style={styles.followSection}>
                <Text style={styles.followSectionTitle}>{t("socialConfig.followOn")}</Text>
                <View style={styles.followButtons}>
                  {person.social_links.instagram && (
                    <TouchableOpacity
                      style={styles.followBtnInstagram}
                      onPress={() => {
                        const u = person.social_links.instagram.replace('@', '');
                        Linking.openURL(`https://instagram.com/${u}`).catch(() => {});
                      }}
                      activeOpacity={0.7}
                    >
                      <Ionicons name="logo-instagram" size={20} color="#fff" />
                      <Text style={styles.followBtnText}>Instagram</Text>
                    </TouchableOpacity>
                  )}
                  {person.social_links.tiktok && (
                    <TouchableOpacity
                      style={styles.followBtnTiktok}
                      onPress={() => {
                        const u = person.social_links.tiktok.replace('@', '');
                        Linking.openURL(`https://tiktok.com/@${u}`).catch(() => {});
                      }}
                      activeOpacity={0.7}
                    >
                      <Ionicons name="logo-tiktok" size={20} color="#fff" />
                      <Text style={styles.followBtnText}>TikTok</Text>
                    </TouchableOpacity>
                  )}
                  {person.social_links.x && (
                    <TouchableOpacity
                      style={styles.followBtnX}
                      onPress={() => {
                        const u = person.social_links.x.replace('@', '');
                        Linking.openURL(`https://x.com/${u}`).catch(() => {});
                      }}
                      activeOpacity={0.7}
                    >
                      <Text style={{ color: '#fff', fontWeight: '800', fontSize: 16, marginRight: 6 }}>𝕏</Text>
                      <Text style={styles.followBtnText}>X</Text>
                    </TouchableOpacity>
                  )}
                </View>
              </View>
            ) : null
          )}

          {/* Personality Trends */}
          <Trends />

          {/* Share / Action Section */}
          {person?.source === "self_boosted" ? (
            /* Boosted user: No social share buttons — just Rally Cry context */
            <View style={[styles.card, { marginBottom: 30 }]}>
              <Text style={styles.section}>Daily Run</Text>
              <View style={{ alignItems: 'center', paddingVertical: 12 }}>
                <Ionicons name="rocket" size={28} color={PALETTE.gold} />
                <Text style={{ color: PALETTE.text, fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 20 }}>
                  This is an Outsider competing in the ranking.{'\n'}Your vote helps them climb!
                </Text>
              </View>
            </View>
          ) : (
            /* Celebrity: Classic share buttons */
            <View style={[styles.card, { marginBottom: 30 }]}>
              <Text style={styles.section}>{t("person.share")}</Text>
              <View style={styles.shareGrid}>
                <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#1877F2' }]} onPress={shareToFacebook}>
                  <Ionicons name="logo-facebook" size={22} color="white" />
                  <Text style={styles.shareText}>{t("person.facebook")}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#1DA1F2' }]} onPress={shareToTwitter}>
                  <Ionicons name="logo-twitter" size={22} color="white" />
                  <Text style={styles.shareText}>{t("person.twitter")}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.shareButton, { backgroundColor: '#E4405F' }]} onPress={shareToInstagram}>
                  <Ionicons name="logo-instagram" size={22} color="white" />
                  <Text style={styles.shareText}>{t("person.instagram")}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.shareButton, { backgroundColor: PALETTE.accent }]} onPress={shareGeneric}>
                  <Ionicons name="share-outline" size={22} color="white" />
                  <Text style={styles.shareText}>{t("person.more")}</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
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
        <Text style={styles.noData}>Every vote counts — cast yours to start the chart!</Text>
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
  popularityIndicator: { alignItems: 'center', marginBottom: 8 },
  popularityText: { fontSize: 28, fontWeight: '700', marginTop: 8 },
  gaugeVotes: { color: PALETTE.subtext, fontSize: 16, marginTop: 8 },
  card: { backgroundColor: PALETTE.card, marginHorizontal: 16, marginTop: 16, borderRadius: 12, padding: 12, borderColor: PALETTE.border, borderWidth: 1 },
  section: { color: PALETTE.subtext, marginBottom: 8, fontWeight: '600' },
  noData: { color: PALETTE.subtext, textAlign: 'center', paddingVertical: 20, fontStyle: 'italic' },
  votesChartPlaceholder: { alignItems: 'center', paddingVertical: 20 },
  currentVotesText: { color: '#2ECC71', fontWeight: '600', marginTop: 8, fontSize: 16 },
  row: { flexDirection: 'row', gap: 12, marginHorizontal: 16, marginTop: 16 },
  cta: { flex: 1, height: 52, borderRadius: 10, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 },
  ctaText: { color: 'white', fontWeight: '700', fontSize: 16 },
  trendRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth },
  trendName: { color: PALETTE.text, flex: 1 },
  trendDelta: { fontWeight: '700' },
  shareGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  shareButton: { flex: 1, minWidth: '45%', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, paddingHorizontal: 12, borderRadius: 8 },
  shareText: { color: 'white', fontWeight: '600', fontSize: 13 },
  // Follow buttons (Chantier 1I)
  followSection: {
    marginHorizontal: 16,
    marginTop: 16,
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  followSectionTitle: {
    color: PALETTE.subtext,
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 10,
    textAlign: 'center',
  },
  followButtons: {
    gap: 8,
  },
  followBtnInstagram: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#C13584',
  },
  followBtnTiktok: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#010101',
    borderWidth: 1,
    borderColor: '#25F4EE',
  },
  followBtnX: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#000000',
    borderWidth: 1,
    borderColor: '#333',
  },
  followBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
