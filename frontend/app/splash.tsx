import React, { useRef, useEffect } from "react";
import { View, StyleSheet, Animated, Easing, useWindowDimensions } from "react-native";

interface SplashScreenProps {
  onFinish?: () => void;
}

/**
 * Splash Screen — V1.0 Cinematic Animation (3 acts)
 *
 * ACT 1 — T=0 → T=0.5s   : Screen 100% BLACK. Nothing visible. Pause (lever de rideau).
 * ACT 2 — T=0.5s → T=1.2s : Background fades from black to dark green (#0F2F22). Icon NOT visible yet.
 * ACT 3 — T=1.2s → T=2.8s : Icon appears at center (scale 0) and grows to scale 5 (golden P fills screen).
 * FADE  — T=2.8s → T=3.0s : Everything fades out, navigate to Home.
 *
 * Total: 3.0 seconds.
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
    // ── ACT 1 (T=0 → T=0.5s): Pure black. Nothing happens. ──
    const act1Timer = setTimeout(() => {
      // ── ACT 2 (T=0.5s → T=1.2s): Black fades to green. Icon still hidden. ──
      Animated.timing(bgProgress, {
        toValue: 1,
        duration: 700, // 0.7s fade
        easing: Easing.ease,
        useNativeDriver: false, // backgroundColor can't use native driver
      }).start(() => {
        // ── ACT 3 (T=1.2s → T=2.8s): Icon appears and grows ──
        Animated.parallel([
          Animated.timing(iconOpacity, {
            toValue: 1,
            duration: 400, // Quick fade-in of icon
            easing: Easing.ease,
            useNativeDriver: true,
          }),
          Animated.timing(iconScale, {
            toValue: 5,
            duration: 1600, // 1.6s growth
            easing: Easing.bezier(0.25, 0.1, 0.25, 1),
            useNativeDriver: true,
          }),
        ]).start(() => {
          // ── FADE (T=2.8s → T=3.0s): Fade out everything ──
          Animated.timing(fadeOut, {
            toValue: 0,
            duration: 200,
            useNativeDriver: true,
          }).start(() => {
            onFinish();
          });
        });
      });
    }, 500); // 500ms black pause

    return () => clearTimeout(act1Timer);
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
