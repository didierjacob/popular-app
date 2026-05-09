import React from "react";
import { View, Text, TouchableOpacity, StyleSheet, Platform } from "react-native";
import { useRouter } from "expo-router";

interface BackHeaderProps {
  title?: string;
  titleColor?: string;
  backgroundColor?: string;
}

export default function BackHeader({ title, titleColor = "#EAEAEA", backgroundColor = "transparent" }: BackHeaderProps) {
  const router = useRouter();

  return (
    <View style={[styles.container, { backgroundColor }]}>
      <TouchableOpacity
        onPress={() => router.back()}
        style={styles.backButton}
        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
      >
        <Text style={[styles.backArrow, { color: titleColor }]}>{"<"}</Text>
      </TouchableOpacity>
      {title ? (
        <Text style={[styles.title, { color: titleColor }]} numberOfLines={1}>
          {title}
        </Text>
      ) : null}
      {/* Spacer to balance the back button */}
      <View style={styles.spacer} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: Platform.OS === "ios" ? 8 : 12,
    paddingBottom: 8,
    minHeight: 44,
  },
  backButton: {
    width: 44,
    height: 44,
    justifyContent: "center",
    alignItems: "flex-start",
  },
  backArrow: {
    fontSize: 28,
    fontWeight: "300",
    lineHeight: 32,
  },
  title: {
    flex: 1,
    fontSize: 18,
    fontWeight: "700",
    textAlign: "center",
    marginHorizontal: 4,
  },
  spacer: {
    width: 44,
  },
});
