import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Animated, Easing } from "react-native";

const PALETTE = {
  bg: "#0F2F22",
  gold: "#FFD700",
};

interface SplashScreenProps {
  onFinish: () => void;
}

export default function SplashScreen({ onFinish = () => {} }: SplashScreenProps) {
  const scale = useRef(new Animated.Value(0.25)).current;
  const letterOpacity = useRef(new Animated.Value(0)).current;
  const screenOpacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    // Phase 1: Gold P appears and expands organically from center (0-1.4s)
    Animated.parallel([
      Animated.timing(letterOpacity, {
        toValue: 1,
        duration: 350,
        useNativeDriver: true,
      }),
      Animated.spring(scale, {
        toValue: 1,
        friction: 6,
        tension: 40,
        useNativeDriver: true,
      }),
    ]).start();

    // Phase 2: After 1.7s, fade out and call onFinish
    const timer = setTimeout(() => {
      Animated.timing(screenOpacity, {
        toValue: 0,
        duration: 300,
        easing: Easing.out(Easing.ease),
        useNativeDriver: true,
      }).start(() => {
        onFinish();
      });
    }, 1700);

    return () => clearTimeout(timer);
  }, []);

  return (
    <Animated.View style={[styles.container, { opacity: screenOpacity }]}>
      <Animated.Text
        style={[
          styles.letter,
          {
            opacity: letterOpacity,
            transform: [{ scale }],
          },
        ]}
      >
        P
      </Animated.Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    alignItems: "center",
    justifyContent: "center",
  },
  letter: {
    fontSize: 140,
    fontWeight: "900",
    color: PALETTE.gold,
    textShadowColor: "rgba(255, 215, 0, 0.4)",
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 30,
  },
});
