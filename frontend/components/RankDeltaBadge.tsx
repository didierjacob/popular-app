import React from "react";
import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

/**
 * Direction badge — reflects the very last vote received on a profile.
 * Backend stores it as `vote_momentum`: "up" (like / superlike / self-boost /
 * V4 implicit like) or "down" (dislike). null = no real vote yet → no badge.
 */
type VoteMomentum = "up" | "down" | null | undefined;

type Props = {
  momentum?: VoteMomentum;
  size?: number;
};

const COLOR_UP = "#4CAF50";
const COLOR_DOWN = "#FF5252";

export default function RankDeltaBadge({ momentum, size = 14 }: Props) {
  if (momentum !== "up" && momentum !== "down") return null;

  const isUp = momentum === "up";
  const color = isUp ? COLOR_UP : COLOR_DOWN;
  const icon = isUp ? "chevron-up" : "chevron-down";

  return (
    <View style={[styles.badge, isUp ? styles.up : styles.down]}>
      <Ionicons name={icon} size={size} color={color} />
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 28,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
  },
  up: { backgroundColor: "rgba(76, 175, 80, 0.14)" },
  down: { backgroundColor: "rgba(255, 82, 82, 0.14)" },
});
