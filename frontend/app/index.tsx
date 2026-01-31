// ULTRA MINIMAL TEST - No external dependencies
import React from "react";
import { View, Text, StyleSheet } from "react-native";

export default function HomeScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Popular App</Text>
      <Text style={styles.subtitle}>Test Screen - Minimal</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0F2F22",
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 32,
    fontWeight: "bold",
    color: "#EAEAEA",
  },
  subtitle: {
    fontSize: 16,
    color: "#C9D8D2",
    marginTop: 10,
  },
});
