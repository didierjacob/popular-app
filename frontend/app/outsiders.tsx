import React, { useCallback, useEffect, useState, useRef } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  Animated,
  Easing,
  FlatList,
  Linking,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
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

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;
const USER_ID_KEY = "popular_user_id";

const formatNumber = (num: number) => Math.round(num).toLocaleString();

// ---- Types ----

interface OutsiderItem {
  id: string;
  boost_id: string;
  user_id: string;
  name: string;
  category: string;
  score: number;
  total_votes: number;
  tier: string;
  tier_name: string;
  tier_priority: number;
  position: string;
  hours_remaining: number;
  social_links: { instagram?: string; tiktok?: string; x?: string };
  avatar_initials?: string;
  avatar_color?: string;
  popularoo_index: number;
  momentum_24h: number;
  is_seed?: boolean;
  country?: string;
}

interface PaginationInfo {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

type SortMode = "index" | "momentum" | "tier" | "votes";

const SORT_OPTIONS: { key: SortMode; icon: string }[] = [
  { key: "index", icon: "speedometer" },
  { key: "momentum", icon: "trending-up" },
  { key: "tier", icon: "trophy" },
  { key: "votes", icon: "heart" },
];

const PAGE_SIZE = 20;
const ROTATION_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

// ---- Sub-components ----

// Unified circle size for rank and avatar
const CIRCLE_SIZE = 36;

function InitialsAvatar({ initials, name, isGolden = false }: {
  initials?: string; name: string; isGolden?: boolean;
}) {
  const displayInitials = initials || name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
  return (
    <View style={{
      width: CIRCLE_SIZE, height: CIRCLE_SIZE, borderRadius: CIRCLE_SIZE / 2,
      backgroundColor: PALETTE.card,
      justifyContent: "center", alignItems: "center",
      borderWidth: 1.5,
      borderColor: isGolden ? PALETTE.gold : PALETTE.border,
    }}>
      <Text style={{ color: isGolden ? PALETTE.gold : PALETTE.text, fontSize: 13, fontWeight: "700", letterSpacing: 0.5 }}>{displayInitials}</Text>
    </View>
  );
}

function SocialLinksRow({ links }: { links: any }) {
  if (!links) return null;
  const hasAny = links.instagram || links.tiktok || links.x;
  if (!hasAny) return null;
  const openLink = (platform: string, value: string) => {
    const clean = value.replace("@", "");
    let url = "";
    if (platform === "instagram") url = `https://instagram.com/${clean}`;
    else if (platform === "tiktok") url = `https://tiktok.com/@${clean}`;
    else if (platform === "x") url = `https://x.com/${clean}`;
    if (url) Linking.openURL(url).catch(() => {});
  };
  return (
    <View style={styles.socialRow}>
      {links.instagram && (
        <TouchableOpacity onPress={() => openLink("instagram", links.instagram)} style={styles.socialBtn}>
          <Ionicons name="logo-instagram" size={13} color="#E1306C" />
        </TouchableOpacity>
      )}
      {links.tiktok && (
        <TouchableOpacity onPress={() => openLink("tiktok", links.tiktok)} style={styles.socialBtn}>
          <Ionicons name="logo-tiktok" size={13} color="#EAEAEA" />
        </TouchableOpacity>
      )}
      {links.x && (
        <TouchableOpacity onPress={() => openLink("x", links.x)} style={styles.socialBtn}>
          <Text style={{ color: '#EAEAEA', fontWeight: '800', fontSize: 10 }}>𝕏</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

function TimeRemainingBadge({ hours }: { hours: number }) {
  let label = "";
  let color = PALETTE.green;
  if (hours <= 0) { label = "Expired"; color = PALETTE.accent2; }
  else if (hours < 1) { label = `${Math.max(1, Math.round(hours * 60))}m`; color = PALETTE.accent2; }
  else if (hours < 24) { label = `${Math.round(hours)}h`; color = hours < 6 ? PALETTE.orange : PALETTE.green; }
  else { label = `${Math.round(hours / 24)}d`; }
  return (
    <View style={[styles.timeBadge, { backgroundColor: color + "15", borderColor: color + "40" }]}>
      <Ionicons name="time-outline" size={11} color={color} />
      <Text style={[styles.timeBadgeText, { color }]}>{label}</Text>
    </View>
  );
}

function MomentumBadge({ value }: { value: number }) {
  if (value === 0) return null;
  const isUp = value > 0;
  const color = isUp ? PALETTE.green : PALETTE.accent2;
  return (
    <View style={[styles.momentumBadge, { backgroundColor: color + "15" }]}>
      <Ionicons name={isUp ? "arrow-up" : "arrow-down"} size={10} color={color} />
      <Text style={[styles.momentumText, { color }]}>
        {isUp ? "+" : ""}{formatNumber(value)}
      </Text>
    </View>
  );
}

// ---- Main Component ----

export default function OutsidersScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  const [outsiders, setOutsiders] = useState<OutsiderItem[]>([]);
  const [pagination, setPagination] = useState<PaginationInfo>({ page: 1, limit: PAGE_SIZE, total: 0, total_pages: 0, has_next: false, has_prev: false });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sortBy, setSortBy] = useState<SortMode>("index");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchActive, setSearchActive] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [currentUserId, setCurrentUserId] = useState("");

  // Rotation timer with interaction-based pause
  const rotationTimer = useRef<NodeJS.Timeout | null>(null);
  const lastInteractionRef = useRef<number>(Date.now());
  const INACTIVITY_THRESHOLD = 60_000; // 60 seconds
  const fadeAnim = useRef(new Animated.Value(1)).current;

  // Track user interactions to pause rotation
  const recordInteraction = useCallback(() => {
    lastInteractionRef.current = Date.now();
  }, []);

  useEffect(() => {
    AsyncStorage.getItem(USER_ID_KEY).then((id) => { if (id) setCurrentUserId(id); });
  }, []);

  const fetchOutsiders = useCallback(async (page: number, sort: SortMode, search?: string, silent = false) => {
    try {
      if (!silent) setLoading(true);
      const params = new URLSearchParams({
        page: String(page),
        limit: String(PAGE_SIZE),
        sort_by: sort,
      });
      if (search && search.trim()) params.set("search", search.trim());

      const res = await fetch(API(`/outsiders/paginated?${params.toString()}`));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Fade in animation
      if (!silent) {
        fadeAnim.setValue(0);
        Animated.timing(fadeAnim, { toValue: 1, duration: 400, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
      }

      setOutsiders(data.outsiders || []);
      setPagination(data.pagination || { page: 1, limit: PAGE_SIZE, total: 0, total_pages: 0, has_next: false, has_prev: false });
    } catch (error) {
      console.error("Failed to load outsiders:", error);
    } finally {
      if (!silent) setLoading(false);
      setRefreshing(false);
    }
  }, [fadeAnim]);

  // Initial load & sort/page changes
  useEffect(() => {
    fetchOutsiders(currentPage, sortBy, searchActive ? searchQuery : undefined);
  }, [currentPage, sortBy]);

  // Auto-rotation every 10 minutes, paused if interaction < 60s ago
  useEffect(() => {
    rotationTimer.current = setInterval(() => {
      const timeSinceLastInteraction = Date.now() - lastInteractionRef.current;
      if (timeSinceLastInteraction < INACTIVITY_THRESHOLD) {
        // User active recently — skip this rotation cycle
        return;
      }
      setCurrentPage((prev) => {
        const nextPage = pagination.has_next ? prev + 1 : 1;
        return nextPage;
      });
    }, ROTATION_INTERVAL_MS);
    return () => { if (rotationTimer.current) clearInterval(rotationTimer.current); };
  }, [pagination.has_next]);

  const onRefresh = useCallback(() => {
    recordInteraction();
    setRefreshing(true);
    fetchOutsiders(currentPage, sortBy, searchActive ? searchQuery : undefined, true);
  }, [currentPage, sortBy, searchQuery, searchActive, fetchOutsiders, recordInteraction]);

  const handleSearch = () => {
    recordInteraction();
    if (!searchQuery.trim()) {
      setSearchActive(false);
      setCurrentPage(1);
      fetchOutsiders(1, sortBy);
      return;
    }
    setSearchActive(true);
    setCurrentPage(1);
    fetchOutsiders(1, sortBy, searchQuery);
  };

  const clearSearch = () => {
    recordInteraction();
    setSearchQuery("");
    setSearchActive(false);
    setCurrentPage(1);
    fetchOutsiders(1, sortBy);
  };

  const handleSortChange = (newSort: SortMode) => {
    recordInteraction();
    if (newSort === sortBy) return;
    setSortBy(newSort);
    setCurrentPage(1);
  };

  const goNextPage = () => {
    recordInteraction();
    if (pagination.has_next) {
      const next = currentPage + 1;
      setCurrentPage(next);
    }
  };

  const goPrevPage = () => {
    recordInteraction();
    if (pagination.has_prev) {
      const prev = currentPage - 1;
      setCurrentPage(prev);
    }
  };

  // ---- Render items ----

  const renderHeader = () => (
    <View>
      {/* Total counter */}
      <View style={styles.totalBar}>
        <View style={styles.totalLeft}>
          <Ionicons name="people" size={16} color={PALETTE.accent2} />
          <Text style={styles.totalText}>
            {formatNumber(pagination.total)} Outsiders {t("outsiders.activeLabel")}
          </Text>
        </View>
        <View style={styles.capacityBadge}>
          <Text style={styles.capacityText}>/ 1000</Text>
        </View>
      </View>

      {/* Search bar */}
      <View style={styles.searchContainer}>
        <View style={styles.searchInputRow}>
          <Ionicons name="search" size={18} color={PALETTE.subtext} style={{ marginRight: 8 }} />
          <TextInput
            style={styles.searchInput}
            placeholder={t("outsiders.searchPlaceholder")}
            placeholderTextColor={PALETTE.subtext + "80"}
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={clearSearch} style={styles.clearBtn}>
              <Ionicons name="close-circle" size={18} color={PALETTE.subtext} />
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={handleSearch} style={styles.searchGoBtn}>
            <Text style={styles.searchGoBtnText}>Go</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Sort pills */}
      <View style={styles.sortRow}>
        {SORT_OPTIONS.map((opt) => (
          <TouchableOpacity
            key={opt.key}
            style={[styles.sortPill, sortBy === opt.key && styles.sortPillActive]}
            onPress={() => handleSortChange(opt.key)}
          >
            <Ionicons
              name={opt.icon as any}
              size={14}
              color={sortBy === opt.key ? PALETTE.gold : PALETTE.subtext}
            />
            <Text style={[styles.sortPillText, sortBy === opt.key && styles.sortPillTextActive]}>
              {t(`outsiders.sort_${opt.key}`)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Promo banner */}
      <TouchableOpacity style={styles.promoBanner} onPress={() => router.push("/premium")} activeOpacity={0.8}>
        <View style={styles.promoIcon}>
          <Ionicons name="rocket" size={18} color={PALETTE.gold} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.promoTitle}>{t("outsiders.wantToAppear")}</Text>
          <Text style={styles.promoSub}>{t("outsiders.getBooster")}</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={PALETTE.gold} />
      </TouchableOpacity>
    </View>
  );

  const renderItem = ({ item, index }: { item: OutsiderItem; index: number }) => {
    const globalRank = (currentPage - 1) * PAGE_SIZE + index + 1;
    const isGolden = item.position === "top";
    const isOwn = item.user_id === currentUserId;

    return (
      <TouchableOpacity
        style={[styles.row, isGolden && styles.goldenRow, isOwn && styles.ownRow]}
        onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}
        activeOpacity={0.7}
      >
        {/* Rank */}
        <View style={[styles.rank, isGolden && styles.goldenRank]}>
          <Text style={[styles.rankText, isGolden && { color: PALETTE.gold }]}>{globalRank}</Text>
        </View>

        {/* Avatar */}
        <InitialsAvatar
          initials={item.avatar_initials}
          name={item.name}
          isGolden={isGolden}
        />

        {/* Info */}
        <View style={{ flex: 1, marginLeft: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
            <Text style={styles.name} numberOfLines={1} ellipsizeMode="tail">{item.name}</Text>
            {isGolden && <Ionicons name="trophy" size={12} color={PALETTE.gold} />}
            {isOwn && (
              <View style={styles.youBadge}>
                <Text style={styles.youBadgeText}>{t("outsiders.you")}</Text>
              </View>
            )}
          </View>

          {/* Contextual primary metric based on sort mode */}
          <View style={styles.metaRow}>
            {sortBy === "index" && item.popularoo_index > 0 && (
              <View style={styles.contextBadge}>
                <Ionicons name="speedometer" size={11} color={PALETTE.gold} />
                <Text style={[styles.contextBadgeText, { color: PALETTE.gold }]}>
                  PI {Math.round(item.popularoo_index)}
                </Text>
              </View>
            )}
            {sortBy === "momentum" && (
              <MomentumBadge value={item.momentum_24h} />
            )}
            {sortBy === "tier" && (
              <View style={styles.contextBadge}>
                <Ionicons name="trophy" size={11} color={item.tier_priority >= 3 ? PALETTE.gold : item.tier_priority >= 2 ? PALETTE.orange : PALETTE.subtext} />
                <Text style={[styles.contextBadgeText, { color: item.tier_priority >= 3 ? PALETTE.gold : item.tier_priority >= 2 ? PALETTE.orange : PALETTE.subtext }]}>
                  {item.tier_name}
                </Text>
              </View>
            )}
            {sortBy === "votes" && (
              <View style={styles.contextBadge}>
                <Ionicons name="heart" size={11} color={PALETTE.accent2} />
                <Text style={[styles.contextBadgeText, { color: PALETTE.accent2 }]}>
                  {formatNumber(item.total_votes)} votes
                </Text>
              </View>
            )}
            <Text style={styles.meta}>
              {sortBy === "tier" ? `${formatNumber(item.total_votes)} votes` : `${item.tier_name} • ${formatNumber(item.total_votes)}`}
            </Text>
          </View>

          <View style={styles.bottomRow}>
            <TimeRemainingBadge hours={item.hours_remaining} />
            <SocialLinksRow links={item.social_links} />
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  const renderFooter = () => {
    if (pagination.total_pages <= 1) return <View style={{ height: 80 }} />;
    return (
      <View style={styles.paginationContainer}>
        <TouchableOpacity
          style={[styles.pageBtn, !pagination.has_prev && styles.pageBtnDisabled]}
          onPress={goPrevPage}
          disabled={!pagination.has_prev}
        >
          <Ionicons name="chevron-back" size={18} color={pagination.has_prev ? PALETTE.text : PALETTE.subtext + "40"} />
        </TouchableOpacity>

        <View style={styles.pageInfo}>
          <Text style={styles.pageInfoText}>
            {pagination.page} / {pagination.total_pages}
          </Text>
          <Text style={styles.pageInfoSub}>
            {t("outsiders.rotationHint")}
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.pageBtn, !pagination.has_next && styles.pageBtnDisabled]}
          onPress={goNextPage}
          disabled={!pagination.has_next}
        >
          <Ionicons name="chevron-forward" size={18} color={pagination.has_next ? PALETTE.text : PALETTE.subtext + "40"} />
        </TouchableOpacity>
      </View>
    );
  };

  const renderEmpty = () => {
    if (loading) return null;
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="people-outline" size={48} color={PALETTE.subtext} />
        <Text style={styles.emptyTitle}>
          {searchActive ? t("outsiders.noResults") : t("outsiders.noOutsiders")}
        </Text>
        <Text style={styles.emptySub}>
          {searchActive ? t("outsiders.tryAnotherSearch") : t("outsiders.noOutsidersSubtitle")}
        </Text>
        {!searchActive && (
          <TouchableOpacity style={styles.emptyBtn} onPress={() => router.push("/premium")}>
            <Ionicons name="rocket" size={16} color="#FFF" />
            <Text style={styles.emptyBtnText}>{t("outsiders.getBoosterBtn")}</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  if (loading && outsiders.length === 0) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color={PALETTE.accent2} />
        <Text style={{ color: PALETTE.subtext, marginTop: 12 }}>{t("common.loading")}</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      <View style={{ flex: 1, maxWidth: isTablet ? 600 : undefined, width: "100%", alignSelf: "center" }}>
        {/* Fixed Header */}
        <View style={styles.header}>
          <Text style={styles.title}>{t("outsiders.title")}</Text>
        </View>

        {/* List */}
        <Animated.View style={{ flex: 1, opacity: fadeAnim }}>
          <FlatList
            data={outsiders}
            keyExtractor={(item) => item.boost_id}
            renderItem={renderItem}
            ListHeaderComponent={renderHeader}
            ListEmptyComponent={renderEmpty}
            ListFooterComponent={renderFooter}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />
            }
            contentContainerStyle={{ paddingBottom: 24 }}
            showsVerticalScrollIndicator={false}
          />
        </Animated.View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: PALETTE.bg },
  header: {
    paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: PALETTE.border,
  },
  title: { color: PALETTE.text, fontSize: 22, fontWeight: "700" },
  subtitle: { color: PALETTE.subtext, fontSize: 13, marginTop: 3 },

  // Total bar
  totalBar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginHorizontal: 16, marginTop: 12, paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: PALETTE.card, borderRadius: 10, borderWidth: 1, borderColor: PALETTE.border,
  },
  totalLeft: { flexDirection: "row", alignItems: "center", gap: 8 },
  totalText: { color: PALETTE.text, fontSize: 14, fontWeight: "600" },
  capacityBadge: { backgroundColor: PALETTE.border, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  capacityText: { color: PALETTE.subtext, fontSize: 11, fontWeight: "600" },

  // Search
  searchContainer: { marginHorizontal: 16, marginTop: 10 },
  searchInputRow: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: PALETTE.card, borderRadius: 10,
    paddingHorizontal: 12, paddingVertical: 8,
    borderWidth: 1, borderColor: PALETTE.border,
  },
  searchInput: { flex: 1, color: PALETTE.text, fontSize: 14, paddingVertical: 4 },
  clearBtn: { padding: 4, marginRight: 4 },
  searchGoBtn: {
    backgroundColor: PALETTE.accent2, paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 8, marginLeft: 6,
  },
  searchGoBtnText: { color: "#FFF", fontWeight: "700", fontSize: 13 },

  // Sort
  sortRow: {
    flexDirection: "row", paddingHorizontal: 16, marginTop: 10, gap: 6,
  },
  sortPill: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: 4, paddingVertical: 8, borderRadius: 8,
    backgroundColor: PALETTE.card, borderWidth: 1, borderColor: PALETTE.border,
  },
  sortPillActive: { borderColor: PALETTE.gold, backgroundColor: PALETTE.gold + "12" },
  sortPillText: { color: PALETTE.subtext, fontSize: 11, fontWeight: "600" },
  sortPillTextActive: { color: PALETTE.gold },

  // Promo
  promoBanner: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: PALETTE.card, marginHorizontal: 16, marginTop: 10, marginBottom: 8,
    padding: 12, borderRadius: 10, borderWidth: 1, borderColor: PALETTE.gold + "60",
  },
  promoIcon: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: PALETTE.gold + "20", alignItems: "center", justifyContent: "center", marginRight: 10,
  },
  promoTitle: { color: PALETTE.gold, fontSize: 13, fontWeight: "700" },
  promoSub: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },

  // List rows
  row: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomColor: PALETTE.border, borderBottomWidth: StyleSheet.hairlineWidth,
  },
  goldenRow: { backgroundColor: PALETTE.gold + "08" },
  ownRow: { backgroundColor: PALETTE.green + "10", borderLeftWidth: 3, borderLeftColor: PALETTE.green },
  rank: {
    width: CIRCLE_SIZE, height: CIRCLE_SIZE, borderRadius: CIRCLE_SIZE / 2,
    backgroundColor: PALETTE.card, borderWidth: 1.5, borderColor: PALETTE.border,
    alignItems: "center", justifyContent: "center",
  },
  goldenRank: { borderColor: PALETTE.gold },
  rankText: { color: PALETTE.text, fontWeight: "700", fontSize: 13, letterSpacing: 0.5 },
  name: { color: PALETTE.text, fontSize: 15, fontWeight: "600", flexShrink: 1 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3 },
  meta: { color: PALETTE.subtext, fontSize: 11 },
  bottomRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 5 },

  // Badges
  youBadge: { backgroundColor: PALETTE.green, borderRadius: 5, paddingHorizontal: 5, paddingVertical: 1 },
  youBadgeText: { color: "#FFF", fontSize: 8, fontWeight: "800" },
  timeBadge: {
    flexDirection: "row", alignItems: "center", gap: 3,
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8, borderWidth: 1,
  },
  timeBadgeText: { fontSize: 10, fontWeight: "700" },
  momentumBadge: {
    flexDirection: "row", alignItems: "center", gap: 2,
    paddingHorizontal: 5, paddingVertical: 2, borderRadius: 6,
  },
  momentumText: { fontSize: 10, fontWeight: "700" },
  indexBadge: {
    backgroundColor: PALETTE.border, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 6,
  },
  indexText: { color: PALETTE.subtext, fontSize: 9, fontWeight: "700" },
  contextBadge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: PALETTE.bg, paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: 8, borderWidth: 1, borderColor: PALETTE.border,
  },
  contextBadgeText: { fontSize: 11, fontWeight: "700" },

  // Social
  socialRow: { flexDirection: "row", gap: 5 },
  socialBtn: {
    width: 24, height: 24, borderRadius: 12,
    backgroundColor: PALETTE.bg, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: PALETTE.border,
  },

  // Pagination
  paginationContainer: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    paddingVertical: 16, paddingHorizontal: 16, gap: 16,
    marginBottom: 60,
  },
  pageBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: PALETTE.card, borderWidth: 1, borderColor: PALETTE.border,
    alignItems: "center", justifyContent: "center",
  },
  pageBtnDisabled: { opacity: 0.4 },
  pageInfo: { alignItems: "center" },
  pageInfoText: { color: PALETTE.text, fontSize: 14, fontWeight: "600" },
  pageInfoSub: { color: PALETTE.subtext, fontSize: 10, marginTop: 2 },

  // Empty
  emptyContainer: { alignItems: "center", justifyContent: "center", paddingVertical: 60, paddingHorizontal: 40 },
  emptyTitle: { color: PALETTE.text, fontSize: 18, fontWeight: "700", marginTop: 16 },
  emptySub: { color: PALETTE.subtext, fontSize: 13, textAlign: "center", marginTop: 8 },
  emptyBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: PALETTE.accent2, paddingHorizontal: 22, paddingVertical: 11,
    borderRadius: 22, marginTop: 18,
  },
  emptyBtnText: { color: "#FFF", fontWeight: "700", fontSize: 14 },
});
