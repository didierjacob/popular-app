import React, { useEffect } from "react";
import { View, Text, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSequence,
  Easing,
} from "react-native-reanimated";

const PALETTE = {
  bg: "#0F2F22",
  bgLight: "#1C3A2C",
  text: "#EAEAEA",
  accent: "#009B4D",
};

interface SplashScreenProps {
  onFinish: () => void;
}

export default function SplashScreen({ onFinish }: SplashScreenProps) {
  const opacity = useSharedValue(0);
  const rotation = useSharedValue(0);
  const scale = useSharedValue(0.8);

  useEffect(() => {
    // Fade in + scale + rotate
    opacity.value = withTiming(1, { duration: 500, easing: Easing.out(Easing.cubic) });
    scale.value = withTiming(1, { duration: 600, easing: Easing.out(Easing.back(1.2)) });
    
    // Subtle rotation animation
    rotation.value = withSequence(
      withTiming(-5, { duration: 400, easing: Easing.inOut(Easing.ease) }),
      withTiming(5, { duration: 600, easing: Easing.inOut(Easing.ease) }),
      withTiming(0, { duration: 400, easing: Easing.inOut(Easing.ease) })
    );

    // Fade out and finish
    const timer = setTimeout(() => {
      opacity.value = withTiming(0, { duration: 300 }, () => {
        onFinish();
      });
    }, 1700);

    return () => clearTimeout(timer);
  }, []);

  const animatedStyle = useAnimatedStyle(() => {
    return {
      opacity: opacity.value,
      transform: [
        { rotate: `${rotation.value}deg` },
        { scale: scale.value }
      ],
    };
  });

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.letterContainer, animatedStyle]}>
        <Text style={styles.letter}>P</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    alignItems: "center",
    justifyContent: "center",
  },
  letterContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  letter: {
    fontSize: 140,
    fontWeight: "300",
    color: PALETTE.text,
    letterSpacing: -2,
    textShadowColor: PALETTE.accent,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 20,
  },
});
