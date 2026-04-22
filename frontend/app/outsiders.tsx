import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
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
import { CreditsService, type OutsiderData } from "../services/creditsService";

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
};

const capitalize = (str: string) =>
  str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
const formatNumber = (num: number) => Math.round(num).toLocaleString();

function SocialLinksRow({ links }: { links: any }) {
  if (!links) return null;
  const hasAny = links.instagram || links.twitter || links.facebook;
  if (!hasAny) return null;

  const openLink = (platform: string, value: string) => {
    let url = "";
    if (platform === "instagram") {
      url = `https://instagram.com/${value.replace("@", "")}`;
    } else if (platform === "twitter") {
      url = `https://x.com/${value.replace("@", "")}`;
    } else if (platform === "facebook") {
      url = value.startsWith("http") ? value : `https://facebook.com/${value}`;
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
      {links.twitter && (
        <TouchableOpacity
          onPress={() => openLink("twitter", links.twitter)}
          style={styles.socialBtn}
        >
          <Ionicons name="logo-twitter" size={14} color="#1DA1F2" />
        </TouchableOpacity>
      )}
      {links.facebook && (
        <TouchableOpacity
          onPress={() => openLink("facebook", links.facebook)}
          style={styles.socialBtn}
        >
          <Ionicons name="logo-facebook" size={14} color="#1877F2" />
        </TouchableOpacity>
      )}
    </View>
  );
}

export default function Outsiders() {
  const router = useRouter();
  const [outsiders, setOutsiders] = useState<OutsiderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { width: screenWidth } = useWindowDimensions();
  const isTablet = screenWidth > 768;

  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await CreditsService.getOutsiders();
      // Merge golden + regular, sort by total_votes descending
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

  const renderHeader = () => (
    <TouchableOpacity
      style={styles.promoBanner}
      onPress={() => router.push("/premium")}
      activeOpacity={0.8}
    >
      <View style={styles.promoIcon}>
        <Ionicons name="rocket" size={20} color={PALETTE.gold} />
      </View>
      <View style={styles.promoText}>
        <Text style={styles.promoTitle}>Want to appear here?</Text>
        <Text style={styles.promoSub}>Get a Booster and join the ranking!</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={PALETTE.gold} />
    </TouchableOpacity>
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
    const arrowIcon = isUp ? "arrow-up" : isDown ? "arrow-down" : "remove";
    const arrowColor = isUp
      ? PALETTE.green
      : isDown
      ? PALETTE.accent
      : PALETTE.subtext;
    const isGolden = item.position === "top";

    return (
      <TouchableOpacity
        style={[styles.row, isGolden && styles.goldenRow]}
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
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={styles.name} numberOfLines={1} ellipsizeMode="tail">
              {item.name}
            </Text>
            {isGolden && (
              <Ionicons name="trophy" size={14} color={PALETTE.gold} />
            )}
          </View>
          <Text style={styles.meta} numberOfLines={1} ellipsizeMode="tail">
            {item.tier_name} •{" "}
            {formatNumber(item.total_votes)}{" "}
            {item.total_votes <= 1 ? "vote" : "votes"}
          </Text>
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
      <Text style={styles.emptyTitle}>No outsiders yet</Text>
      <Text style={styles.emptySub}>
        Be the first to get a Booster and appear here!
      </Text>
      <TouchableOpacity
        style={styles.emptyBtn}
        onPress={() => router.push("/premium")}
      >
        <Ionicons name="rocket" size={16} color="#FFF" />
        <Text style={styles.emptyBtnText}>Get a Booster</Text>
      </TouchableOpacity>
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
          <Text style={styles.title}>Outsiders</Text>
          <Text style={styles.subtitle}>Boosted by the community</Text>
        </View>
        <FlatList
          data={outsiders}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={renderEmpty}
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
});
