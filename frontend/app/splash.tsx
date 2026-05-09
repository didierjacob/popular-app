import React, { useRef, useEffect } from "react";
import { View, StyleSheet, Animated, Easing, Image, useWindowDimensions } from "react-native";

interface SplashScreenProps {
  onFinish?: () => void;
}

/**
 * Splash Screen — Animation spec (Brief 1.1):
 * T=0        : Dark green background (#0F2F22), nothing visible
 * T=0→2s     : App icon V8 (golden P on green background) fades in at center and grows
 * T=2s       : The icon fills the screen — only the golden P is visible
 * T=2s→2.5s  : Fade to white/transparent, then navigate to Home
 */
export default function SplashScreen({ onFinish = () => {} }: SplashScreenProps) {
  const { width, height } = useWindowDimensions();
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.3)).current;
  const fadeOut = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    // Phase 1: Fade in + grow icon (0 → 2s)
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
      Animated.timing(scale, {
        toValue: 5, // Grow until it fills the screen
        duration: 2200,
        easing: Easing.bezier(0.25, 0.1, 0.25, 1),
        useNativeDriver: true,
      }),
    ]).start(() => {
      // Phase 2: Fade out everything (2s → 2.5s)
      Animated.timing(fadeOut, {
        toValue: 0,
        duration: 400,
        useNativeDriver: true,
      }).start(() => {
        onFinish();
      });
    });
  }, []);

  return (
    <Animated.View style={[styles.container, { opacity: fadeOut }]}>
      <Animated.Image
        source={require("../assets/branding/icon-v8-1024.png")}
        style={[
          styles.icon,
          {
            opacity,
            transform: [{ scale }],
          },
        ]}
        resizeMode="contain"
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0F2F22",
    alignItems: "center",
    justifyContent: "center",
  },
  icon: {
    width: 200,
    height: 200,
    borderRadius: 40,
  },
});
