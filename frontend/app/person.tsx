import React, { useCallback, useEffect, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  Animated,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  Easing,
  Share,
  Alert,
  useWindowDimensions,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import ConfettiCannon from "react-native-confetti-cannon";
import { fetchWithCache } from "../services/cacheService";
import { useTranslation } from "react-i18next";
import { getTrendStatus, type TrendStatus } from "../utils/trendUtils";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  green: "#009B4D",
  border: "#2E6148",
  gold: "#FFD700",
};

const API_BASE =
  process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) =>
  `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const formatNumber = (num: number) => Math.round(num).toLocaleString();

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

const DEVICE_KEY = "popularity_device_id";
async function getDeviceId() {
  return (await AsyncStorage.getItem(DEVICE_KEY)) as string;
}

// --- Dummy Live Feed Data ---

const FIRST_NAMES = [
  "Emma", "Liam", "Sofia", "Lucas", "Mia", "Noah", "Olivia", "Hugo",
  "Amelia", "Arthur", "Lea", "Louis", "Chloe", "Gabriel", "Valentina",
  "Matteo", "Yuki", "Hiroshi", "Fatima", "Ahmed", "Priya", "Raj",
  "Chen", "Mei", "Carlos", "Isabella", "Mohamed", "Aisha", "James",
  "Charlotte", "William", "Hannah", "Luca", "Giulia", "Felix", "Zara",
  "Oscar", "Ella", "Leo", "Nora", "Ethan", "Ava", "Theo", "Luna",
  "Maxime", "Camille", "Antoine", "Jade", "Raphael", "Manon",
];

const COUNTRIES = [
  "France", "USA", "UK", "Brazil", "Japan", "Germany", "Spain",
  "Italy", "Canada", "Australia", "Mexico", "India", "South Korea",
  "Netherlands", "Sweden", "Portugal", "Argentina", "Colombia",
  "Belgium", "Switzerland",
];

interface LiveVoteEntry {
  id: number;
  firstName: string;
  action: "liked" | "disliked";
  country: string;
  timestamp: number;
}

function generateDummyVote(idCounter: number): LiveVoteEntry {
  const firstName = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
  const action = Math.random() > 0.3 ? "liked" : "disliked";
  const country = COUNTRIES[Math.floor(Math.random() * COUNTRIES.length)];
  return {
    id: idCounter,
    firstName,
    action,
    country,
    timestamp: Date.now() - Math.floor(Math.random() * 5000),
  };
}

// --- Trend Status Logic (imported from utils/trendUtils) ---

function TrendStatusBadge({ status }: { status: TrendStatus }) {
  const { t } = useTranslation();
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (status === "trending" || status === "freefall") {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.05,
            duration: 1200,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 1200,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ])
      ).start();
    }
  }, [status]);

  let label: string;
  let textColor: string;
  let bgColor: string;
  let borderColor: string;
  let arrows = "";
  let hasGlow = false;

  switch (status) {
    case "rising":
      label = t("person.status_rising");
      textColor = "#2ECC71";
      bgColor = "rgba(46, 204, 113, 0.10)";
      borderColor = "rgba(46, 204, 113, 0.25)";
      break;
    case "falling":
      label = t("person.status_falling");
      textColor = "#E74C3C";
      bgColor = "rgba(231, 76, 60, 0.10)";
      borderColor = "rgba(231, 76, 60, 0.25)";
      break;
    case "trending":
      label = t("person.status_trending");
      textColor = "#2ECC71";
      bgColor = "rgba(46, 204, 113, 0.15)";
      borderColor = "rgba(46, 204, 113, 0.40)";
      arrows = " \u25B2\u25B2";
      hasGlow = true;
      break;
    case "freefall":
      label = t("person.status_freefall");
      textColor = "#E74C3C";
      bgColor = "rgba(231, 76, 60, 0.15)";
      borderColor = "rgba(231, 76, 60, 0.40)";
      arrows = " \u25BC\u25BC";
      hasGlow = true;
      break;
  }

  return (
    <Animated.View
      style={[
        styles.trendBadge,
        {
          backgroundColor: bgColor,
          borderColor: borderColor,
          transform: [{ scale: hasGlow ? pulseAnim : 1 }],
        },
        hasGlow && {
          ...Platform.select({
            ios: {
              shadowColor: textColor,
              shadowOffset: { width: 0, height: 0 },
              shadowOpacity: 0.5,
              shadowRadius: 12,
            },
            android: { elevation: 8 },
            default: {},
          }),
        },
      ]}
    >
      <Text style={[styles.trendBadgeText, { color: textColor }]}>
        {label}
        {arrows}
      </Text>
    </Animated.View>
  );
}

// --- Live Vote Feed Item ---

function LiveVoteItem({
  entry,
  personName,
}: {
  entry: LiveVoteEntry;
  personName: string;
}) {
  const { t } = useTranslation();
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(-20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 400,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  const elapsed = Math.floor((Date.now() - entry.timestamp) / 1000);
  let timeStr: string;
  if (elapsed < 3) {
    timeStr = t("person.timeAgo_now");
  } else if (elapsed < 60) {
    timeStr = t("person.timeAgo_sec", { count: elapsed });
  } else {
    timeStr = t("person.timeAgo_min", { count: Math.floor(elapsed / 60) });
  }

  const actionText =
    entry.action === "liked" ? t("person.liked") : t("person.disliked");
  const actionColor = entry.action === "liked" ? "#2ECC71" : "#E74C3C";
  const actionIcon = entry.action === "liked" ? "heart" : "heart-dislike";

  return (
    <Animated.View
      style={[
        styles.liveVoteRow,
        { opacity: fadeAnim, transform: [{ translateY: slideAnim }] },
      ]}
    >
      <View style={[styles.liveVoteDot, { backgroundColor: actionColor }]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.liveVoteText}>
          <Text style={{ fontWeight: "700", color: PALETTE.text }}>
            {entry.firstName}
          </Text>{" "}
          <Text style={{ color: actionColor }}>{actionText}</Text>{" "}
          <Text style={{ color: PALETTE.subtext }}>
            {t("person.inCountry")} {entry.country}
          </Text>
        </Text>
      </View>
      <Text style={styles.liveVoteTime}>{timeStr}</Text>
    </Animated.View>
  );
}

// --- Main Component ---

export default function Person() {
  const router = useRouter();
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ id: string; name?: string }>();
  const id = params.id as string;
  const [name, setName] = useState(params.name || "");
  const [initialLoading, setInitialLoading] = useState(true);
  const [person, setPerson] = useState<any>(null);

  const [showConfetti, setShowConfetti] = useState(false);
  const confettiRef = useRef<any>(null);
  const likeScaleAnim = useRef(new Animated.Value(1)).current;
  const dislikeScaleAnim = useRef(new Animated.Value(1)).current;
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  // Live feed state
  const [liveVotes, setLiveVotes] = useState<LiveVoteEntry[]>([]);
  const voteIdCounter = useRef(0);
  const liveIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Index pulsing animation
  const indexPulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(indexPulse, {
          toValue: 1.02,
          duration: 2000,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(indexPulse, {
          toValue: 1,
          duration: 2000,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, []);

  const fetchData = useCallback(
    async (silent = false) => {
      if (!silent) setInitialLoading(true);
      try {
        const p = await fetchWithCache(
          `/people/${id}`,
          `person_${id}`,
          () => apiGet(`/people/${id}`),
          2 * 60 * 1000
        );
        setPerson(p);
        if ((p as any)?.name) setName((p as any).name);
      } catch (e) {
        console.error(e);
      } finally {
        if (!silent) setInitialLoading(false);
      }
    },
    [id]
  );

  useEffect(() => {
    fetchData(false);
    const i = setInterval(() => fetchData(true), 10000);
    return () => clearInterval(i);
  }, [fetchData]);

  // Live feed: generate dummy votes every 2-4 seconds
  useEffect(() => {
    // Seed initial votes
    const initial: LiveVoteEntry[] = [];
    for (let i = 0; i < 8; i++) {
      voteIdCounter.current++;
      const entry = generateDummyVote(voteIdCounter.current);
      entry.timestamp = Date.now() - (8 - i) * 3000;
      initial.push(entry);
    }
    setLiveVotes(initial);

    const addVote = () => {
      voteIdCounter.current++;
      const newEntry = generateDummyVote(voteIdCounter.current);
      newEntry.timestamp = Date.now();
      setLiveVotes((prev) => [newEntry, ...prev].slice(0, 30));

      // BLOC 1.7: Sync visual vote counter with live feed
      setPerson((prev: any) => {
        if (!prev) return prev;
        if (newEntry.action === "liked") {
          return {
            ...prev,
            likes: (prev.likes || 0) + 1,
            total_votes: (prev.total_votes || 0) + 1,
          };
        } else {
          return {
            ...prev,
            dislikes: (prev.dislikes || 0) + 1,
            total_votes: (prev.total_votes || 0) + 1,
          };
        }
      });
    };

    liveIntervalRef.current = setInterval(addVote, 2500 + Math.random() * 2000);
    return () => {
      if (liveIntervalRef.current) clearInterval(liveIntervalRef.current);
    };
  }, []);

  // Force re-render every second to update relative times
  const [, setTick] = useState(0);
  useEffect(() => {
    const ticker = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(ticker);
  }, []);

  const like = async (value: 1 | -1) => {
    try {
      const scaleAnim = value === 1 ? likeScaleAnim : dislikeScaleAnim;
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

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

      const did = await getDeviceId();
      const response = await fetch(API(`/people/${id}/vote`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Device-ID": did,
        },
        body: JSON.stringify({ value }),
      });

      const result = await response.json();

      if (result.already_voted) {
        const nextVoteTime = result.next_vote_time
          ? new Date(result.next_vote_time)
          : null;
        let timeMessage = "";
        if (nextVoteTime) {
          const now = new Date();
          const hoursLeft = Math.ceil(
            (nextVoteTime.getTime() - now.getTime()) / (1000 * 60 * 60)
          );
          const minutesLeft =
            Math.ceil(
              (nextVoteTime.getTime() - now.getTime()) / (1000 * 60)
            ) % 60;
          if (hoursLeft > 1) {
            timeMessage = `${hoursLeft}h`;
          } else if (hoursLeft === 1) {
            timeMessage = "~1h";
          } else {
            timeMessage = `${minutesLeft}min`;
          }
        }
        Alert.alert(
          t("person.alreadyVotedTitle"),
          `${t("person.alreadyVotedMessage", { name })}\n\n${t("person.alreadyVotedSub", { time: timeMessage })}`,
          [{ text: "OK" }]
        );
        return;
      }

      // Vote successful - update local state
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
        const filteredVotes = votes.filter((v: any) => v.personId !== id);
        filteredVotes.push({
          personId: id,
          personName: name,
          category: person?.category || "other",
          vote: value,
          timestamp: new Date().toISOString(),
        });
        await AsyncStorage.setItem(
          VOTES_KEY,
          JSON.stringify(filteredVotes.slice(-100))
        );
      } catch (error) {}

      if (value === 1) {
        setShowConfetti(true);
        setTimeout(() => setShowConfetti(false), 3000);
      }

      await fetchData(true);
    } catch (error) {
      console.error("Vote error:", error);
    }
  };

  // Share
  const shareMessage = t("person.shareMessage", {
    name,
    score: Math.round(person?.score || 0),
    votes: formatNumber(person?.total_votes || 0),
  });

  const shareToFacebook = async () => {
    const url = `https://www.facebook.com/sharer/sharer.php?quote=${encodeURIComponent(shareMessage)}`;
    await Linking.openURL(url);
  };

  const shareToTwitter = async () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareMessage)}`;
    await Linking.openURL(url);
  };

  const shareToInstagram = async () => {
    try {
      await Share.share({ message: shareMessage });
    } catch (error) {
      Alert.alert(t("person.instagramShareTitle"), shareMessage);
    }
  };

  const shareGeneric = async () => {
    try {
      await Share.share({ message: shareMessage });
    } catch (error) {
      console.error("Share failed:", error);
    }
  };

  const trendStatus = getTrendStatus({ name: person?.name || name, score: person?.score || 50 });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      {initialLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={PALETTE.accent2} />
        </View>
      ) : (
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={isTablet ? { alignItems: "center" } : {}}
        >
          <View style={isTablet ? { maxWidth: 600, width: "100%" } : {}}>
            {/* Header */}
            <View style={styles.header}>
              <TouchableOpacity
                onPress={() => router.back()}
                style={styles.homeBtn}
                hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
              >
                <Text style={styles.backArrow}>{"<"}</Text>
                <Text style={styles.homeText}>{t("person.home")}</Text>
              </TouchableOpacity>
              <Text style={styles.title}>{name}</Text>
              <Text style={styles.meta}>
                {person?.source === "self_boosted"
                  ? `${formatNumber(person?.likes || 0)} supporters`
                  : `${formatNumber(person?.likes || 0)} likes \u2022 ${formatNumber(person?.dislikes || 0)} dislikes`}
              </Text>
            </View>

            {/* Large Popularoo Index */}
            <View style={styles.indexSection}>
              <Text style={styles.indexLabel}>
                {t("person.popularooIndex")}
              </Text>
              <Animated.View style={{ transform: [{ scale: indexPulse }] }}>
                <Text
                  style={[
                    styles.indexValue,
                    {
                      color:
                        trendStatus === "falling" || trendStatus === "freefall"
                          ? "#E74C3C"
                          : "#2ECC71",
                    },
                  ]}
                >
                  {Math.round(person?.score || 0)}
                </Text>
              </Animated.View>
              <Text style={styles.indexVotes}>
                {t("person.totalVotes", {
                  count: formatNumber(person?.total_votes || 0),
                })}
              </Text>
              <TrendStatusBadge status={trendStatus} />
            </View>

            {/* Vote Buttons - Immediately accessible */}
            {person?.source === "self_boosted" ? (
              <View style={[styles.voteRow, { justifyContent: "center" }]}>
                <Animated.View
                  style={{
                    transform: [{ scale: likeScaleAnim }],
                    flex: 1,
                  }}
                >
                  <TouchableOpacity
                    style={[styles.voteBtn, styles.voteBtnLike]}
                    onPress={() => like(1)}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="heart" size={20} color="#0F2F22" />
                    <Text style={[styles.voteBtnText, { color: "#0F2F22" }]}>
                      {t("person.voteFor", {
                        name: name?.split(" ")[0] || "",
                      })}
                    </Text>
                  </TouchableOpacity>
                </Animated.View>
              </View>
            ) : (
              <View style={styles.voteRow}>
                <Animated.View
                  style={{
                    transform: [{ scale: likeScaleAnim }],
                    flex: 1,
                    marginRight: 6,
                  }}
                >
                  <TouchableOpacity
                    style={[styles.voteBtn, styles.voteBtnLike]}
                    onPress={() => like(1)}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="thumbs-up" size={20} color="#fff" />
                    <Text style={styles.voteBtnText}>{t("person.like")}</Text>
                  </TouchableOpacity>
                </Animated.View>
                <Animated.View
                  style={{
                    transform: [{ scale: dislikeScaleAnim }],
                    flex: 1,
                    marginLeft: 6,
                  }}
                >
                  <TouchableOpacity
                    style={[styles.voteBtn, styles.voteBtnDislike]}
                    onPress={() => like(-1)}
                    activeOpacity={0.7}
                  >
                    <Ionicons name="thumbs-down" size={20} color="#fff" />
                    <Text style={styles.voteBtnText}>
                      {t("person.dislike")}
                    </Text>
                  </TouchableOpacity>
                </Animated.View>
              </View>
            )}

            {/* Social Follow Buttons for Outsiders */}
            {person?.source === "self_boosted" &&
              person?.social_links &&
              (person.social_links.instagram ||
                person.social_links.tiktok ||
                person.social_links.x) && (
                <View style={styles.followSection}>
                  <View style={styles.followButtons}>
                    {person.social_links.instagram && (
                      <TouchableOpacity
                        style={styles.followBtnInstagram}
                        onPress={() => {
                          const u = person.social_links.instagram.replace(
                            "@",
                            ""
                          );
                          Linking.openURL(
                            `https://instagram.com/${u}`
                          ).catch(() => {});
                        }}
                        activeOpacity={0.7}
                      >
                        <Ionicons
                          name="logo-instagram"
                          size={20}
                          color="#fff"
                        />
                        <Text style={styles.followBtnText}>Instagram</Text>
                      </TouchableOpacity>
                    )}
                    {person.social_links.tiktok && (
                      <TouchableOpacity
                        style={styles.followBtnTiktok}
                        onPress={() => {
                          const u = person.social_links.tiktok.replace(
                            "@",
                            ""
                          );
                          Linking.openURL(
                            `https://tiktok.com/@${u}`
                          ).catch(() => {});
                        }}
                        activeOpacity={0.7}
                      >
                        <Ionicons
                          name="logo-tiktok"
                          size={20}
                          color="#fff"
                        />
                        <Text style={styles.followBtnText}>TikTok</Text>
                      </TouchableOpacity>
                    )}
                    {person.social_links.x && (
                      <TouchableOpacity
                        style={styles.followBtnX}
                        onPress={() => {
                          const u = person.social_links.x.replace("@", "");
                          Linking.openURL(`https://x.com/${u}`).catch(
                            () => {}
                          );
                        }}
                        activeOpacity={0.7}
                      >
                        <Text
                          style={{
                            color: "#fff",
                            fontWeight: "800",
                            fontSize: 18,
                          }}
                        >
                          {"\uD835\uDD4F"}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              )}

            {/* Live Activity Feed */}
            <View style={styles.liveCard}>
              <View style={styles.liveHeader}>
                <View style={styles.liveDotPulse} />
                <Text style={styles.liveTitle}>
                  {t("person.liveActivity")}
                </Text>
              </View>
              {liveVotes.length === 0 ? (
                <Text style={styles.liveEmpty}>
                  {t("person.liveActivityEmpty")}
                </Text>
              ) : (
                <View style={styles.liveFeed}>
                  {liveVotes.slice(0, 15).map((entry) => (
                    <LiveVoteItem
                      key={entry.id}
                      entry={entry}
                      personName={name}
                    />
                  ))}
                </View>
              )}
            </View>

            {/* Share Section */}
            {person?.source === "self_boosted" ? (
              <View style={[styles.card, { marginBottom: 30 }]}>
                <Text style={styles.sectionTitle}>
                  {t("person.dailyRun")}
                </Text>
                <View
                  style={{
                    alignItems: "center",
                    paddingVertical: 12,
                  }}
                >
                  <Ionicons name="rocket" size={28} color={PALETTE.gold} />
                  <Text style={styles.outsiderBannerText}>
                    {t("person.outsiderBanner")}
                  </Text>
                </View>
              </View>
            ) : (
              <View style={[styles.card, { marginBottom: 30 }]}>
                <Text style={styles.sectionTitle}>{t("person.share")}</Text>
                <View style={styles.shareGrid}>
                  <TouchableOpacity
                    style={[styles.shareButton, { backgroundColor: "#1877F2" }]}
                    onPress={shareToFacebook}
                  >
                    <Ionicons name="logo-facebook" size={22} color="white" />
                    <Text style={styles.shareText}>
                      {t("person.facebook")}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.shareButton, { backgroundColor: "#1DA1F2" }]}
                    onPress={shareToTwitter}
                  >
                    <Ionicons name="logo-twitter" size={22} color="white" />
                    <Text style={styles.shareText}>
                      {t("person.twitter")}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.shareButton, { backgroundColor: "#E4405F" }]}
                    onPress={shareToInstagram}
                  >
                    <Ionicons name="logo-instagram" size={22} color="white" />
                    <Text style={styles.shareText}>
                      {t("person.instagram")}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[
                      styles.shareButton,
                      { backgroundColor: PALETTE.accent },
                    ]}
                    onPress={shareGeneric}
                  >
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
        <ConfettiCannon
          count={200}
          origin={{ x: -10, y: 0 }}
          autoStart={true}
          ref={confettiRef}
          fadeOut={true}
        />
      )}
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
    paddingTop: 12,
    paddingBottom: 8,
  },
  homeBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginBottom: 8,
  },
  homeText: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: "600",
  },
  backArrow: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: "300",
    lineHeight: 28,
    marginRight: 2,
  },
  title: {
    color: PALETTE.text,
    fontSize: 26,
    fontWeight: "700",
    letterSpacing: -0.5,
  },
  meta: {
    color: PALETTE.subtext,
    marginTop: 4,
    fontSize: 14,
  },

  // Index Section
  indexSection: {
    alignItems: "center",
    paddingVertical: 24,
    paddingHorizontal: 16,
  },
  indexLabel: {
    color: PALETTE.subtext,
    fontSize: 13,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 1.5,
    marginBottom: 8,
  },
  indexValue: {
    fontSize: 72,
    fontWeight: "800",
    letterSpacing: -2,
  },
  indexVotes: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 6,
  },

  // Trend Badge
  trendBadge: {
    marginTop: 12,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
  },
  trendBadgeText: {
    fontSize: 14,
    fontWeight: "700",
    letterSpacing: 0.5,
  },

  // Vote Buttons
  voteRow: {
    flexDirection: "row",
    marginHorizontal: 16,
    marginTop: 8,
    marginBottom: 16,
    gap: 12,
  },
  voteBtn: {
    flex: 1,
    height: 54,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
  },
  voteBtnLike: {
    backgroundColor: PALETTE.green,
  },
  voteBtnDislike: {
    backgroundColor: PALETTE.accent,
  },
  voteBtnText: {
    color: "white",
    fontWeight: "700",
    fontSize: 16,
  },

  // Live Activity Feed
  liveCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 12,
    padding: 14,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  liveHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  liveDotPulse: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#2ECC71",
  },
  liveTitle: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: "700",
  },
  liveEmpty: {
    color: PALETTE.subtext,
    textAlign: "center",
    paddingVertical: 20,
    fontStyle: "italic",
  },
  liveFeed: {
    gap: 2,
  },
  liveVoteRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PALETTE.border,
  },
  liveVoteDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  liveVoteText: {
    color: PALETTE.subtext,
    fontSize: 13,
    lineHeight: 18,
  },
  liveVoteTime: {
    color: PALETTE.subtext,
    fontSize: 11,
    opacity: 0.7,
  },

  // Cards
  card: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 12,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  sectionTitle: {
    color: PALETTE.subtext,
    marginBottom: 8,
    fontWeight: "600",
  },
  outsiderBannerText: {
    color: PALETTE.text,
    fontSize: 14,
    textAlign: "center",
    marginTop: 8,
    lineHeight: 20,
  },

  // Share
  shareGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 8,
  },
  shareButton: {
    flex: 1,
    minWidth: "45%",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  shareText: {
    color: "white",
    fontWeight: "600",
    fontSize: 13,
  },

  // Follow buttons (Outsiders)
  followSection: {
    marginHorizontal: 16,
    marginTop: 12,
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  followButtons: {
    gap: 8,
  },
  followBtnInstagram: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: "#C13584",
  },
  followBtnTiktok: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: "#010101",
    borderWidth: 1,
    borderColor: "#25F4EE",
  },
  followBtnX: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: "#000000",
    borderWidth: 1,
    borderColor: "#333",
  },
  followBtnText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
});
