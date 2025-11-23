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
  subtext: "#C9D8D2",
};

interface SplashScreenProps {
  onFinish: () => void;
}

export default function SplashScreen({ onFinish }: SplashScreenProps) {
  const letterOpacity = useSharedValue(0);
  const rotation = useSharedValue(0);
  const scale = useSharedValue(0.8);
  const textOpacity = useSharedValue(0);

  useEffect(() => {
    // Fade in letter + scale
    letterOpacity.value = withTiming(1, { duration: 400, easing: Easing.out(Easing.cubic) });
    scale.value = withTiming(1, { duration: 500, easing: Easing.out(Easing.back(1.2)) });
    
    // Full 360 degree rotation
    rotation.value = withTiming(360, { duration: 1600, easing: Easing.inOut(Easing.ease) });

    // Bottom text fade in after 200ms, stays longer, then fade out before end
    setTimeout(() => {
      textOpacity.value = withTiming(1, { duration: 500, easing: Easing.out(Easing.cubic) });
    }, 300);

    setTimeout(() => {
      textOpacity.value = withTiming(0, { duration: 500, easing: Easing.in(Easing.cubic) });
    }, 2200);

    // Fade out letter and finish
    const timer = setTimeout(() => {
      letterOpacity.value = withTiming(0, { duration: 500, easing: Easing.in(Easing.cubic) }, () => {
        onFinish();
      });
    }, 2700);

    return () => clearTimeout(timer);
  }, []);

  const animatedLetterStyle = useAnimatedStyle(() => {
    return {
      opacity: letterOpacity.value,
      transform: [
        { rotate: `${rotation.value}deg` },
        { scale: scale.value }
      ],
    };
  });

  const animatedTextStyle = useAnimatedStyle(() => {
    return {
      opacity: textOpacity.value,
    };
  });

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.letterContainer, animatedLetterStyle]}>
        <Text style={styles.letter}>P</Text>
      </Animated.View>
      
      <Animated.View style={[styles.bottomTextContainer, animatedTextStyle]}>
        <Text style={styles.bottomText}>No registration required.</Text>
        <Text style={styles.bottomText}>Your vote is anonymous.</Text>
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
  bottomTextContainer: {
    position: "absolute",
    bottom: 60,
    alignItems: "center",
    paddingHorizontal: 40,
  },
  bottomText: {
    fontSize: 14,
    fontWeight: "400",
    color: PALETTE.subtext,
    textAlign: "center",
    lineHeight: 20,
  },
});
