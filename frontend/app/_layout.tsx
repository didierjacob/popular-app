import React from "react";
import { Stack } from "expo-router";

// TEMPORARY: Ultra-minimal layout to debug Expo Go crash
export default function RootLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
    </Stack>
  );
}
