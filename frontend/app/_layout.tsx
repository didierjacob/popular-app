import React, { useState, useEffect } from "react";
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import "../i18n"; // Initialize i18n on app start
import SplashScreen from "./splash";

// Sentry removed for V1.0 — will be reintegrated in V1.1 with proper EAS config

export default function RootLayout() {
  const [showSplash, setShowSplash] = useState(true);
  const { t } = useTranslation();

  if (showSplash) {
    return <SplashScreen onFinish={() => setShowSplash(false)} />;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#8B0000",
        tabBarStyle: {
          backgroundColor: "#2A2A2A",
          borderTopColor: "#3A3A3A",
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tabs.home"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="popular"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="list"
        options={{
          title: t("tabs.list"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="list-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="outsiders"
        options={{
          title: t("tabs.outsiders"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="people-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="myvotes"
        options={{
          title: t("tabs.myvotes"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="heart-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="premium"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="account"
        options={{
          title: t("tabs.account"),
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="person"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="category/[key]"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="splash"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="admin"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="dailyrun"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="bullrun"
        options={{
          href: null,
        }}
      />
    </Tabs>
  );
}
