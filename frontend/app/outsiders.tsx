import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  FlatList,
  useWindowDimensions,
  Linking,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { CreditsService, type OutsiderData } from "../services/creditsService";
import { useTranslation } from "react-i18next";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  green: "#009B4D",
  accent2: "#E04F5F",
  border: "#2E6148",
  gold: "#FFD700",
  orange: "#FFA500",
};

const USER_ID_KEY = "popular_user_id";

const capitalize = (str: string) =>
  str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
const formatNumber = (num: number) => Math.round(num).toLocaleString();

/** Avatar with initials on colored background (Spotify/Slack style) */
function InitialsAvatar({
  initials,
  color,
  name,
  size = 38,
  isGolden = false,
}: {
  initials?: string;
  color?: string;
  name: string;
  size?: number;
  isGolden?: boolean;
}) {
  // Fallback: generate initials from name if not provided by API
  const displayInitials =
    initials ||
    name
      .split(" ")
      .map((w) => w[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  const bgColor = color || "#1C3A2C";
  const borderColor = isGolden ? PALETTE.gold : "transparent";

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: bgColor,
        justifyContent: "center",
        alignItems: "center",
        borderWidth: isGolden ? 2 : 0,
        borderColor,
        marginRight: 10,
      }}
    >
      <Text
        style={{
          color: "#FFFFFF",
          fontSize: size * 0.38,
          fontWeight: "700",
          letterSpacing: 0.5,
        }}
      >
        {displayInitials}
      </Text>
    </View>
  );
}

function formatTimeRemaining(hours: number, t: any): string {
  if (hours <= 0) return t("common.expired");
  if (hours < 1) {
    const mins = Math.round(hours * 60);
    return t("common.timeLeft_m", { m: mins });
  }
  if (hours < 24) {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return m > 0 ? t("common.timeLeft_hm", { h, m }) : t("common.timeLeft_h", { h });
  }
  const days = Math.floor(hours / 24);
  const remainHours = Math.round(hours - days * 24);
  return remainHours > 0 ? t("common.timeLeft_dh", { d: days, h: remainHours }) : t("common.timeLeft_d", { d: days });
}

function getTimeBadgeColor(hours: number): string {
  if (hours <= 1) return PALETTE.accent2; // Red - expiring very soon
  if (hours <= 6) return PALETTE.orange;  // Orange - expiring soon
  return PALETTE.green;                    // Green - plenty of time
}

function SocialLinksRow({ links }: { links: any }) {
  if (!links) return null;
  const hasAny = links.instagram || links.tiktok || links.x;
  if (!hasAny) return null;

  const openLink = (platform: string, value: string) => {
    let url = "";
    const clean = value.replace("@", "");
    if (platform === "instagram") {
      url = `https://instagram.com/${clean}`;
    } else if (platform === "tiktok") {
      url = `https://tiktok.com/@${clean}`;
    } else if (platform === "x") {
      url = `https://x.com/${clean}`;
    }
    if (url) Linking.openURL(url).catch(() => {});
  };

  return (
    <View style={styles.socialRow}>
      {links.instagram && (
        <TouchableOpacity
          onPress={() => openLink("instagram", links.instagram)}
          style={styles.socialBtn}
        >
          <Ionicons name="logo-instagram" size={14} color="#E1306C" />
        </TouchableOpacity>
      )}
      {links.tiktok && (
        <TouchableOpacity
          onPress={() => openLink("tiktok", links.tiktok)}
          style={styles.socialBtn}
        >
          <Ionicons name="logo-tiktok" size={14} color="#EAEAEA" />
        </TouchableOpacity>
      )}
      {links.x && (
        <TouchableOpacity
          onPress={() => openLink("x", links.x)}
          style={styles.socialBtn}
        >
          <Text style={{ color: '#EAEAEA', fontWeight: '800', fontSize: 11 }}>𝕏</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

export default function Outsiders() {
  const router = useRouter();
  const { t } = useTranslation();
  const [outsiders, setOutsiders] = useState<OutsiderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<string>("");
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  useEffect(() => {
    AsyncStorage.getItem(USER_ID_KEY).then((id) => {
      if (id) setCurrentUserId(id);
    });
  }, []);

  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await CreditsService.getOutsiders();
      const all = [...(data.golden || []), ...(data.regular || [])];
      all.sort((a, b) => b.total_votes - a.total_votes);
      setOutsiders(all);
    } catch (error) {
      console.error("Failed to load outsiders:", error);
    } finally {
      if (!silent) setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(() => load(true), 10000);
    return () => clearInterval(interval);
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load(true);
  }, [load]);

  const handleRenew = (item: OutsiderData) => {
    router.push("/premium");
  };

  const MAX_SLOTS = 10;
  const filledSlots = outsiders.length;
  const emptySlots = Math.max(0, MAX_SLOTS - filledSlots);

  const renderHeader = () => (
    <View>
      {/* Slot counter */}
      <View style={styles.slotCounter}>
        <View style={styles.slotCounterLeft}>
          <Ionicons name="people" size={18} color={PALETTE.accent2} />
          <Text style={styles.slotCounterText}>
            {t("outsiders.activeSlots", { filled: filledSlots, max: MAX_SLOTS })}
          </Text>
        </View>
        <View style={[styles.slotCounterBadge, filledSlots >= MAX_SLOTS && { backgroundColor: PALETTE.accent + '20' }]}>
          <Text style={[styles.slotCounterBadgeText, filledSlots >= MAX_SLOTS && { color: PALETTE.accent }]}>
            {filledSlots >= MAX_SLOTS ? t("outsiders.full") : t("outsiders.open", { count: emptySlots })}
          </Text>
        </View>
      </View>
      {/* Promo banner */}
      <TouchableOpacity
        style={styles.promoBanner}
        onPress={() => router.push("/premium")}
        activeOpacity={0.8}
      >
        <View style={styles.promoIcon}>
          <Ionicons name="rocket" size={20} color={PALETTE.gold} />
        </View>
        <View style={styles.promoText}>
          <Text style={styles.promoTitle}>{t("outsiders.wantToAppear")}</Text>
          <Text style={styles.promoSub}>
            {t("outsiders.getBooster")}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={PALETTE.gold} />
      </TouchableOpacity>
    </View>
  );

  const renderItem = ({
    item,
    index,
  }: {
    item: OutsiderData;
    index: number;
  }) => {
    const score = item.score;
    const isUp = score > 50;
    const isDown = score < 50;
    const arrowIcon = isUp ? "arrow-up" : isDown ? "arrow-down" : "swap-horizontal";
    const arrowColor = isUp
      ? PALETTE.green
      : isDown
      ? PALETTE.accent
      : PALETTE.subtext;
    const isGolden = item.position === "top";
    const isOwn = item.user_id === currentUserId;
    const timeBadgeColor = getTimeBadgeColor(item.hours_remaining);

    return (
      <TouchableOpacity
        style={[styles.row, isGolden && styles.goldenRow, isOwn && styles.ownRow]}
        onPress={() =>
          router.push({
            pathname: "/person",
            params: { id: item.id, name: item.name },
          })
        }
      >
        <View style={[styles.rank, isGolden && styles.goldenRank]}>
          <Text style={[styles.rankText, isGolden && { color: PALETTE.gold }]}>
            {index + 1}
          </Text>
        </View>
        <InitialsAvatar
          initials={item.avatar_initials}
          color={item.avatar_color}
          name={item.name}
          size={38}
          isGolden={isGolden}
        />
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={styles.name} numberOfLines={1} ellipsizeMode="tail">
              {item.name}
            </Text>
            {isGolden && (
              <Ionicons name="trophy" size={14} color={PALETTE.gold} />
            )}
            {isOwn && (
              <View style={styles.youBadge}>
                <Text style={styles.youBadgeText}>{t("outsiders.you")}</Text>
              </View>
            )}
          </View>
          <Text style={styles.meta} numberOfLines={1} ellipsizeMode="tail">
            {item.tier_name} •{" "}
            {formatNumber(item.total_votes)}{" "}
            {item.total_votes <= 1 ? t("common.vote") : t("common.votes")}
          </Text>
          {/* Time remaining badge */}
          <View style={styles.timeRow}>
            <View style={[styles.timeBadge, { backgroundColor: timeBadgeColor + "20", borderColor: timeBadgeColor + "40" }]}>
              <Ionicons name="time-outline" size={12} color={timeBadgeColor} />
              <Text style={[styles.timeBadgeText, { color: timeBadgeColor }]}>
                {formatTimeRemaining(item.hours_remaining, t)}
              </Text>
            </View>
            {isOwn && item.hours_remaining <= 24 && (
              <TouchableOpacity
                style={styles.renewBtn}
                onPress={(e) => {
                  e.stopPropagation?.();
                  handleRenew(item);
                }}
              >
                <Ionicons name="refresh" size={13} color="#FFF" />
                <Text style={styles.renewBtnText}>{t("outsiders.renew")}</Text>
              </TouchableOpacity>
            )}
          </View>
          <SocialLinksRow links={item.social_links} />
        </View>
        <View style={styles.arrowBox}>
          <Ionicons name={arrowIcon as any} size={22} color={arrowColor} />
        </View>
      </TouchableOpacity>
    );
  };

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Ionicons name="people-outline" size={48} color={PALETTE.subtext} />
      <Text style={styles.emptyTitle}>{t("outsiders.noOutsiders")}</Text>
      <Text style={styles.emptySub}>
        {t("outsiders.noOutsidersSubtitle")}
      </Text>
      <TouchableOpacity
        style={styles.emptyBtn}
        onPress={() => router.push("/premium")}
      >
        <Ionicons name="rocket" size={16} color="#FFF" />
        <Text style={styles.emptyBtnText}>{t("outsiders.getBoosterBtn")}</Text>
      </TouchableOpacity>
    </View>
  );

  const renderFooter = () => (
    <View>
      {/* Empty slots */}
      {emptySlots > 0 && (
        <View style={styles.emptySlotsSection}>
          {Array.from({ length: Math.min(emptySlots, 5) }).map((_, i) => (
            <TouchableOpacity
              key={`empty-slot-${i}`}
              style={styles.emptySlotRow}
              onPress={() => router.push("/premium")}
              activeOpacity={0.7}
            >
              <View style={styles.emptySlotCircle}>
                <Ionicons name="add" size={20} color={PALETTE.subtext} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.emptySlotTitle}>{t("outsiders.slotAvailable")}</Text>
                <Text style={styles.emptySlotSub}>{t("outsiders.slotBoost")}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={PALETTE.subtext} />
            </TouchableOpacity>
          ))}
        </View>
      )}
      {/* Top Bull Runners section */}
      <View style={styles.bullRunnerSection}>
        <View style={styles.bullRunnerHeader}>
          <Ionicons name="rocket" size={18} color={PALETTE.gold} />
          <Text style={styles.bullRunnerTitle}>{t("outsiders.dailyRunLeaders")}</Text>
        </View>
        <View style={styles.bullRunnerPlaceholder}>
          <Ionicons name="trophy-outline" size={32} color={PALETTE.gold + '60'} />
          <Text style={styles.bullRunnerPlaceholderText}>
            {t("outsiders.goldenBoosterCta")}
          </Text>
          <TouchableOpacity
            style={styles.bullRunnerCta}
            onPress={() => router.push("/premium")}
          >
            <Text style={styles.bullRunnerCtaText}>{t("outsiders.learnMore")}</Text>
            <Ionicons name="arrow-forward" size={14} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>
      </View>
    </View>
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
      <View
        style={{
          flex: 1,
          maxWidth: isTablet ? 600 : undefined,
          width: "100%",
          alignSelf: "center",
        }}
      >
        <View style={styles.header}>
          <Text style={styles.title}>{t("outsiders.title")}</Text>
          <Text style={styles.subtitle}>{t("outsiders.subtitle")}</Text>
        </View>
        <FlatList
          data={outsiders}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={renderEmpty}
          ListFooterComponent={outsiders.length > 0 ? renderFooter : undefined}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={PALETTE.accent2}
            />
          }
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      </View>
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
  // Promo Banner
  promoBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 8,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.gold,
  },
  promoIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.gold + "20",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  promoText: { flex: 1 },
  promoTitle: {
    color: PALETTE.gold,
    fontSize: 15,
    fontWeight: "700",
  },
  promoSub: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  // List rows
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  goldenRow: {
    backgroundColor: PALETTE.gold + "08",
  },
  ownRow: {
    backgroundColor: PALETTE.green + "10",
    borderLeftWidth: 3,
    borderLeftColor: PALETTE.green,
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
  goldenRank: {
    borderColor: PALETTE.gold,
    backgroundColor: PALETTE.gold + "15",
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
  // YOU badge
  youBadge: {
    backgroundColor: PALETTE.green,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  youBadgeText: {
    color: "#FFF",
    fontSize: 9,
    fontWeight: "800",
  },
  // Time remaining
  timeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 6,
  },
  timeBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    borderWidth: 1,
  },
  timeBadgeText: {
    fontSize: 11,
    fontWeight: "700",
  },
  // Renew button
  renewBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: PALETTE.accent2,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  renewBtnText: {
    color: "#FFF",
    fontSize: 11,
    fontWeight: "700",
  },
  arrowBox: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: "center",
    justifyContent: "center",
  },
  // Social links
  socialRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 6,
  },
  socialBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: PALETTE.bg,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  // Empty state
  emptyContainer: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 60,
    paddingHorizontal: 40,
  },
  emptyTitle: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: "700",
    marginTop: 16,
  },
  emptySub: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: "center",
    marginTop: 8,
  },
  emptyBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: PALETTE.accent2,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 25,
    marginTop: 20,
  },
  emptyBtnText: {
    color: "#FFF",
    fontWeight: "700",
    fontSize: 15,
  },
  // Slot counter
  slotCounter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginHorizontal: 16,
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  slotCounterLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  slotCounterText: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: "600",
  },
  slotCounterBadge: {
    backgroundColor: PALETTE.green + "20",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  slotCounterBadgeText: {
    color: PALETTE.green,
    fontSize: 12,
    fontWeight: "700",
  },
  // Empty slots
  emptySlotsSection: {
    marginTop: 8,
  },
  emptySlotRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  emptySlotCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1.5,
    borderColor: PALETTE.border,
    borderStyle: "dashed" as any,
    alignItems: "center",
    justifyContent: "center",
  },
  emptySlotTitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: "600",
  },
  emptySlotSub: {
    color: PALETTE.subtext + "80",
    fontSize: 12,
    marginTop: 2,
  },
  // Bull Runner section
  bullRunnerSection: {
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 16,
    backgroundColor: PALETTE.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.gold + "40",
    overflow: "hidden",
  },
  bullRunnerHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.gold + "20",
    backgroundColor: PALETTE.gold + "08",
  },
  bullRunnerTitle: {
    color: PALETTE.gold,
    fontSize: 15,
    fontWeight: "700",
  },
  bullRunnerPlaceholder: {
    alignItems: "center",
    paddingVertical: 24,
    paddingHorizontal: 20,
  },
  bullRunnerPlaceholderText: {
    color: PALETTE.subtext,
    fontSize: 13,
    textAlign: "center",
    marginTop: 10,
    lineHeight: 18,
  },
  bullRunnerCta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 14,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.gold + "40",
  },
  bullRunnerCtaText: {
    color: PALETTE.gold,
    fontSize: 13,
    fontWeight: "600",
  },
});
