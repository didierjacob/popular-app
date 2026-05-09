/**
 * OutsiderCard — Composant réutilisable pour afficher une carte Outsider.
 * Utilisé sur la Home (Outsider du jour) et la page Outsiders (feed de cards).
 * Design unifié : même bordure, radius, padding, couleurs, taille de police.
 */
import React, { useRef, useEffect } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Easing,
  Linking,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#8FA89B",
  gold: "#FFD700",
  heart: "#FF4757",
  green: "#2ECC71",
  border: "#2E6148",
};

const formatNumber = (num: number) => Math.round(num).toLocaleString();

export interface OutsiderData {
  id: string;
  name: string;
  avatar_initials?: string;
  avatar_color?: string;
  tier?: string;
  tier_name?: string;
  likes?: number;
  total_votes?: number;
  hours_remaining?: number;
  social_links?: { instagram?: string; tiktok?: string; x?: string; twitter?: string; facebook?: string };
  position?: string;
}

interface OutsiderCardProps {
  outsider: OutsiderData;
  onLike: (id: string) => void;
  /** Whether to animate the heart with a pulsing effect */
  pulsingHeart?: boolean;
  /** Optional label shown above the card (e.g. "Outsider of the Day 1/13") */
  badgeLabel?: string;
  /** Optional counter text (e.g. "1/13") */
  badgeCounter?: string;
}

// ---- Social Badges Row ----
function SocialBadges({ links, noSocialMessage }: { links?: OutsiderData["social_links"]; noSocialMessage: string }) {
  const hasInstagram = links?.instagram;
  const hasTiktok = links?.tiktok;
  const hasX = links?.x || links?.twitter;
  const hasAny = hasInstagram || hasTiktok || hasX;

  const openLink = (platform: string, value: string) => {
    const handle = value.replace(/^@/, "");
    let url = "";
    if (platform === "instagram") url = `https://instagram.com/${handle}`;
    else if (platform === "tiktok") url = `https://tiktok.com/@${handle}`;
    else if (platform === "x") url = `https://x.com/${handle}`;
    if (url) Linking.openURL(url).catch(() => {});
  };

  const showNoSocialAlert = () => {
    Alert.alert("Social", noSocialMessage);
  };

  if (!hasAny) {
    // Default: show Instagram icon greyed out with "no account" dialog on tap
    return (
      <View style={badgeStyles.row}>
        <TouchableOpacity style={[badgeStyles.badge, { backgroundColor: "#888" }]} onPress={showNoSocialAlert} activeOpacity={0.7}>
          <Ionicons name="logo-instagram" size={16} color="#fff" />
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={badgeStyles.row}>
      {hasInstagram && (
        <TouchableOpacity
          style={[badgeStyles.badge, { backgroundColor: "#E1306C" }]}
          onPress={() => openLink("instagram", links!.instagram!)}
          activeOpacity={0.7}
        >
          <Ionicons name="logo-instagram" size={16} color="#fff" />
        </TouchableOpacity>
      )}
      {hasTiktok && (
        <TouchableOpacity
          style={[badgeStyles.badge, { backgroundColor: "#111", borderWidth: 1, borderColor: "#25F4EE" }]}
          onPress={() => openLink("tiktok", links!.tiktok!)}
          activeOpacity={0.7}
        >
          <Ionicons name="logo-tiktok" size={16} color="#fff" />
        </TouchableOpacity>
      )}
      {hasX && (
        <TouchableOpacity
          style={[badgeStyles.badge, { backgroundColor: "#000", borderWidth: 1, borderColor: "#333" }]}
          onPress={() => openLink("x", (links!.x || links!.twitter)!)}
          activeOpacity={0.7}
        >
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 11 }}>𝕏</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const badgeStyles = StyleSheet.create({
  row: { flexDirection: "row", gap: 8 },
  badge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: "center",
    alignItems: "center",
  },
});

// ---- Time Badge ----
function TimeBadge({ hours }: { hours: number }) {
  if (hours <= 0) return null;
  const d = Math.floor(hours / 24);
  const h = Math.floor(hours % 24);
  const label = d > 0 ? `${d}d ${h}h` : `${h}h`;
  const color = hours < 6 ? "#FFA500" : PALETTE.green;
  return (
    <View style={[styles.timeBadge, { borderColor: color + "33" }]}>
      <Ionicons name="time-outline" size={10} color={color} />
      <Text style={[styles.timeText, { color }]}>{label}</Text>
    </View>
  );
}

// ---- Main OutsiderCard Component ----
export default function OutsiderCard({ outsider, onLike, pulsingHeart = false, badgeLabel, badgeCounter }: OutsiderCardProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const heartScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!pulsingHeart) return;
    Animated.loop(
      Animated.sequence([
        Animated.timing(heartScale, { toValue: 1.25, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(heartScale, { toValue: 1, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ])
    ).start();
  }, [pulsingHeart]);

  const initials =
    outsider.avatar_initials ||
    outsider.name
      .split(" ")
      .map((w: string) => w[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);

  const isGolden = outsider.tier === "golden_booster";

  return (
    <View style={styles.card}>
      {/* Badge label (e.g. "Outsider of the Day") */}
      {badgeLabel && (
        <View style={styles.badgeRow}>
          <Ionicons name="star" size={14} color={PALETTE.gold} />
          <Text style={styles.badgeLabel}>{badgeLabel}</Text>
          {badgeCounter && <Text style={styles.badgeCounter}>{badgeCounter}</Text>}
        </View>
      )}

      {/* Header: Avatar + Name + Tier */}
      <TouchableOpacity
        style={styles.header}
        onPress={() => router.push({ pathname: "/person", params: { id: outsider.id, name: outsider.name } })}
        activeOpacity={0.7}
      >
        <View
          style={[
            styles.avatar,
            { backgroundColor: outsider.avatar_color || PALETTE.card },
            isGolden && { borderColor: PALETTE.gold, borderWidth: 2 },
          ]}
        >
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={styles.name} numberOfLines={1}>
            {outsider.name}
          </Text>
          <View style={{ flexDirection: "row", alignItems: "center", marginTop: 3, flexWrap: "wrap" }}>
            <View style={[styles.tierBadge, isGolden && { backgroundColor: PALETTE.gold + "22", borderColor: PALETTE.gold + "44" }]}>
              <Ionicons name={isGolden ? "trophy" : "rocket"} size={11} color={isGolden ? PALETTE.gold : PALETTE.green} />
              <Text style={[styles.tierText, isGolden && { color: PALETTE.gold }]}>{outsider.tier_name || "Booster"}</Text>
            </View>
          </View>
        </View>
      </TouchableOpacity>

      {/* Votes count */}
      <View style={styles.meta}>
        <Text style={styles.votes}>{formatNumber(outsider.total_votes || outsider.likes || 0)} votes</Text>
      </View>

      {/* Actions: Heart + Social */}
      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.heartButton}
          onPress={() => onLike(outsider.id)}
          activeOpacity={0.7}
        >
          <Animated.View style={{ transform: [{ scale: heartScale }] }}>
            <Ionicons name="heart" size={18} color={PALETTE.heart} />
          </Animated.View>
          <Text style={styles.heartText}>{formatNumber(outsider.likes || 0)}</Text>
        </TouchableOpacity>
        <SocialBadges links={outsider.social_links} noSocialMessage={t("person.noSocialAccount")} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: PALETTE.gold,
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 10,
  },
  badgeLabel: {
    color: PALETTE.gold,
    fontSize: 14,
    fontWeight: "700",
    flex: 1,
  },
  badgeCounter: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontWeight: "600",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1.5,
    borderColor: PALETTE.gold,
  },
  avatarText: {
    color: "#FFF",
    fontWeight: "700",
    fontSize: 13,
  },
  name: {
    color: PALETTE.gold,
    fontSize: 20,
    fontWeight: "700",
  },
  tierBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(46,204,113,0.12)",
    borderRadius: 10,
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: "rgba(46,204,113,0.25)",
    marginRight: 6,
  },
  tierText: {
    color: PALETTE.green,
    fontSize: 11,
    fontWeight: "600",
    marginLeft: 3,
  },
  timeBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(0,155,77,0.12)",
    borderRadius: 10,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderWidth: 1,
  },
  timeText: {
    fontSize: 10,
    fontWeight: "600",
    marginLeft: 3,
  },
  meta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 6,
  },
  votes: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: "600",
  },
  actions: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: PALETTE.gold + "33",
  },
  heartButton: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(255, 71, 87, 0.12)",
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
  },
  heartText: {
    color: PALETTE.heart,
    fontWeight: "700",
    fontSize: 14,
    marginLeft: 5,
  },
});
