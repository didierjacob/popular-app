import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { getTrendDirection } from "../utils/trendUtils";

/**
 * Sujet 2 — Axe 1 mouvements up/down (Option B : rank_delta_24h).
 *
 * Backend snapshots the rank once a day (03:30 UTC) and refreshes
 * rank_delta_24h every 15 min. Positive = moved up, negative = moved down,
 * null/undefined = no snapshot yet (profile younger than 24h) → render nothing.
 *
 * fallbackToFake : si pas de vrai delta (0/null), affiche une flèche fake
 * (muette/grise) calculée par getTrendDirection(name,hour). Le vrai delta
 * écrase systématiquement la fake dès qu'il devient non nul.
 */
type Props = {
  /** Signed rank delta over the last 24h, or null/undefined if no snapshot. */
  delta?: number | null;
  /** Hide the dash badge for delta=0 (e.g. compact rows). Defaults to false. */
  hideZero?: boolean;
  /** Pass-through size for the chevron icon. */
  size?: number;
  /** Show a discreet fake arrow when delta is 0/null. Needs `name`. */
  fallbackToFake?: boolean;
  /** Required if fallbackToFake=true. */
  name?: string;
  /** Optional, only used by the fake direction hash. */
  score?: number;
};

const COLOR_UP = "#4CAF50";
const COLOR_DOWN = "#FF5252";
const COLOR_FLAT = "#8FA89B";
const COLOR_FAKE = "#8FA89B";

export default function RankDeltaBadge({
  delta,
  hideZero = false,
  size = 14,
  fallbackToFake = false,
  name,
  score,
}: Props) {
  const hasReal = delta !== null && delta !== undefined && Math.trunc(delta) !== 0;

  if (hasReal) {
    const n = Math.trunc(delta as number);
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

  if (fallbackToFake && name) {
    const dir = getTrendDirection({ name, score: score ?? 50 });
    if (dir === "equal") {
      if (hideZero) return null;
      return (
        <View style={[styles.badge, styles.flat]}>
          <Text style={[styles.text, { color: COLOR_FLAT }]}>—</Text>
        </View>
      );
    }
    const icon = dir === "up" ? "arrow-up" : "arrow-down";
    return (
      <View style={[styles.badge, styles.fake]}>
        <Ionicons name={icon} size={size} color={COLOR_FAKE} />
      </View>
    );
  }

  if (delta === null || delta === undefined) return null;
  if (hideZero) return null;
  return (
    <View style={[styles.badge, styles.flat]}>
      <Text style={[styles.text, { color: COLOR_FLAT }]}>—</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
    gap: 2,
  },
  up: { backgroundColor: "rgba(76, 175, 80, 0.14)" },
  down: { backgroundColor: "rgba(255, 82, 82, 0.14)" },
  flat: { backgroundColor: "transparent" },
  fake: { backgroundColor: "transparent", opacity: 0.55 },
  text: { fontSize: 12, fontWeight: "700" },
});
