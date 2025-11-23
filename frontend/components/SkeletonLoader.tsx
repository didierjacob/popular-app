import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';

const PALETTE = {
  card: "#1C3A2C",
  border: "#2E6148",
};

interface SkeletonProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: any;
}

export function SkeletonBox({ width = '100%', height = 20, borderRadius = 8, style }: SkeletonProps) {
  const shimmerAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(shimmerAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(shimmerAnim, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, [shimmerAnim]);

  const opacity = shimmerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <Animated.View
      style={[
        styles.skeleton,
        {
          width,
          height,
          borderRadius,
          opacity,
        },
        style,
      ]}
    />
  );
}

export function SkeletonPersonCard() {
  return (
    <View style={styles.personCard}>
      <View style={{ flex: 1 }}>
        <SkeletonBox width="60%" height={18} style={{ marginBottom: 8 }} />
        <SkeletonBox width="80%" height={14} />
      </View>
      <View style={styles.actions}>
        <SkeletonBox width={50} height={10} style={{ marginBottom: 4 }} />
        <SkeletonBox width={50} height={10} style={{ marginBottom: 4 }} />
        <SkeletonBox width={50} height={10} />
      </View>
    </View>
  );
}

export function SkeletonFeaturedCard() {
  return (
    <View style={styles.featuredCard}>
      <SkeletonBox width="50%" height={16} style={{ marginBottom: 8 }} />
      <SkeletonBox width="70%" height={12} style={{ marginBottom: 12 }} />
      <SkeletonBox width="100%" height={80} />
    </View>
  );
}

const styles = StyleSheet.create({
  skeleton: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  personCard: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  actions: {
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: 4,
  },
  featuredCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
});
