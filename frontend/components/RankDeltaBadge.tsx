import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

/**
 * Sujet 2 — Axe 1 mouvements up/down (Option B : rank_delta_24h).
 *
 * Backend snapshots the rank once a day (03:30 UTC) and refreshes
 * rank_delta_24h every 15 min. Positive = moved up, negative = moved down,
 * null/undefined/0 = neutral "—" badge (always rendered for visual coherence).
 */
type Props = {
  /** Signed rank delta over the last 24h, or null/undefined if no snapshot. */
  delta?: number | null;
  /** Pass-through size for the chevron icon. */
  size?: number;
};

const COLOR_UP = "#4CAF50";
const COLOR_DOWN = "#FF5252";
const COLOR_FLAT = "#6B7C7A";

export default function RankDeltaBadge({ delta, size = 14 }: Props) {
  const n = delta === null || delta === undefined ? 0 : Math.trunc(delta);

  if (n === 0) {
    return (
      <View style={[styles.badge, styles.flat]}>
        <Text style={[styles.text, { color: COLOR_FLAT }]}>—</Text>
      </View>
    );
  }

  const isUp = n > 0;
  const color = isUp ? COLOR_UP : COLOR_DOWN;
  const icon = isUp ? "arrow-up" : "arrow-down";
  return (
    <View style={[styles.badge, isUp ? styles.up : styles.down]}>
      <Ionicons name={icon} size={size} color={color} />
      <Text style={[styles.text, { color }]}>{Math.abs(n)}</Text>
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
    gap: 2,
  },
  up: { backgroundColor: "rgba(76, 175, 80, 0.14)" },
  down: { backgroundColor: "rgba(255, 82, 82, 0.14)" },
  flat: { backgroundColor: "rgba(155, 175, 170, 0.15)" },
  text: { fontSize: 12, fontWeight: "700" },
});
