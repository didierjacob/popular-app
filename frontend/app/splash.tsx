import React, { useEffect } from "react";
import { View, Text, StyleSheet } from "react-native";

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
  useEffect(() => {
    // Simple timeout without animations
    const timer = setTimeout(() => {
      onFinish();
    }, 2000);

    return () => clearTimeout(timer);
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.letterContainer}>
        <Text style={styles.letter}>P</Text>
      </View>
      
      <View style={styles.bottomTextContainer}>
        <Text style={styles.bottomText}>No registration required.</Text>
        <Text style={styles.bottomText}>Your vote is anonymous.</Text>
      </View>
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
