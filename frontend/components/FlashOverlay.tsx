import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet } from 'react-native';
import type { FlashDirection } from '../hooks/useRankFlash';

const COLOR_UP = 'rgba(76, 175, 80, 0.25)';
const COLOR_DOWN = 'rgba(255, 82, 82, 0.25)';

interface Props {
  direction: FlashDirection | null | undefined;
  borderRadius?: number;
}

export default function FlashOverlay({ direction, borderRadius = 12 }: Props) {
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (direction !== 'up' && direction !== 'down') {
      opacity.setValue(0);
      return;
    }
    opacity.setValue(0);
    Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 1, useNativeDriver: true }),
      Animated.delay(250),
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start();
  }, [direction, opacity]);

  if (direction !== 'up' && direction !== 'down') return null;

  return (
    <Animated.View
      style={[
        StyleSheet.absoluteFillObject,
        {
          pointerEvents: 'none',
          backgroundColor: direction === 'up' ? COLOR_UP : COLOR_DOWN,
          borderRadius,
          opacity,
        },
      ]}
    />
  );
}
