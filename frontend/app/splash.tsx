import React, { useRef, useEffect } from "react";
import { View, StyleSheet, Animated, Easing, useWindowDimensions } from "react-native";

interface SplashScreenProps {
  onFinish?: () => void;
}

/**
 * Splash Screen — V1.0 Cinematic Animation
 *
 * T=0          : Screen 100% BLACK, nothing visible
 * T=0 → 0.5s  : Background fades from black to dark green (#0F2F22)
 *                Icon appears at center, growing from scale 0 → 0.3
 * T=0.5s → 2s : Icon continues growing from scale 0.3 → 5 (golden P fills screen)
 * T=2s         : Fade out to transparent, then navigate to Home
 */
export default function SplashScreen({ onFinish = () => {} }: SplashScreenProps) {
  const { width, height } = useWindowDimensions();

  // Background: interpolates from black (#000) to dark green (#0F2F22)
  const bgProgress = useRef(new Animated.Value(0)).current;
  // Icon opacity: fades in from 0 to 1
  const iconOpacity = useRef(new Animated.Value(0)).current;
  // Icon scale: grows from 0 to 5
  const iconScale = useRef(new Animated.Value(0)).current;
  // Final fade-out of everything
  const fadeOut = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    // ── Phase 1 (T=0 → T=0.5s): Black → Green + Icon appears (scale 0 → 0.3) ──
    Animated.parallel([
      Animated.timing(bgProgress, {
        toValue: 1,
        duration: 500,
        easing: Easing.ease,
        useNativeDriver: false, // backgroundColor can't use native driver
      }),
      Animated.timing(iconOpacity, {
        toValue: 1,
        duration: 500,
        easing: Easing.ease,
        useNativeDriver: true,
      }),
      Animated.timing(iconScale, {
        toValue: 0.3,
        duration: 500,
        easing: Easing.out(Easing.ease),
        useNativeDriver: true,
      }),
    ]).start(() => {
      // ── Phase 2 (T=0.5s → T=2s): Icon grows from 0.3 → 5 ──
      Animated.timing(iconScale, {
        toValue: 5,
        duration: 1500,
        easing: Easing.bezier(0.25, 0.1, 0.25, 1),
        useNativeDriver: true,
      }).start(() => {
        // ── Phase 3 (T=2s → T=2.4s): Fade out everything ──
        Animated.timing(fadeOut, {
          toValue: 0,
          duration: 400,
          useNativeDriver: true,
        }).start(() => {
          onFinish();
        });
      });
    });
  }, []);

  // Interpolate background color from black to dark green
  const backgroundColor = bgProgress.interpolate({
    inputRange: [0, 1],
    outputRange: ["#000000", "#0F2F22"],
  });

  return (
    <Animated.View style={[styles.container, { backgroundColor, opacity: fadeOut }]}>
      <Animated.Image
        source={require("../assets/branding/icon-v8-1024.png")}
        style={[
          styles.icon,
          {
            opacity: iconOpacity,
            transform: [{ scale: iconScale }],
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
    alignItems: "center",
    justifyContent: "center",
  },
  icon: {
    width: 200,
    height: 200,
    borderRadius: 40,
  },
});
