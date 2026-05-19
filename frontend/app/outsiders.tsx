import React, { useCallback, useEffect, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  LayoutAnimation,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  UIManager,
  View,
} from "react-native";

// Enable LayoutAnimation on Android (no-op on iOS).
if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import OutsiderCard, { type OutsiderData } from "../components/OutsiderCard";
import BackHeader from "../components/BackHeader";
import FlashOverlay from "../components/FlashOverlay";
import { fetchSWR } from "../services/cacheService";
import { useRankFlash } from "../hooks/useRankFlash";
import { cacheKeyOutsiders } from "./splash";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  cardBorder: "#2E6148",
  text: "#EAEAEA",
  subtext: "#8FA89B",
  accent: "#009B4D",
  accent2: "#2ECC71",
  gold: "#FFD700",
  heart: "#FF4757",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;
const DEVICE_KEY = "popularity_device_id";

// ---- Booster Promo Card (injected every 10 outsiders) ----
function BoosterPromoCard({ variant }: { variant: number }) {
  const router = useRouter();
  const { t } = useTranslation();

  const promos = [
    { icon: "rocket" as const, title: t("premium.title"), sub: t("premium.subtitle"), color: PALETTE.accent },
    { icon: "trophy" as const, title: "Golden Booster", sub: "Top ranking position", color: PALETTE.gold },
    { icon: "star" as const, title: "Super Booster", sub: "Accelerate your rise", color: "#9B59B6" },
  ];
  const promo = promos[variant % promos.length];

  return (
    <TouchableOpacity
      style={[styles.promoCard, { borderColor: promo.color }]}
      onPress={() => router.push("/premium")}
      activeOpacity={0.7}
    >
      <View style={[styles.promoIcon, { backgroundColor: promo.color + "22" }]}>
        <Ionicons name={promo.icon} size={28} color={promo.color} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={[styles.promoTitle, { color: promo.color }]}>{promo.title}</Text>
        <Text style={styles.promoSub}>{promo.sub}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={promo.color} />
    </TouchableOpacity>
  );
}

// ---- Main Outsiders Page ----
export default function OutsidersPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [outsiders, setOutsiders] = useState<OutsiderData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const getDeviceId = useCallback(async () => {
    let did = await AsyncStorage.getItem(DEVICE_KEY);
    if (!did) {
      did = `device_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      await AsyncStorage.setItem(DEVICE_KEY, did);
    }
    return did;
  }, []);

  // Sujet 2 — track previous order so a refresh that reshuffles ranks
  // can drive a smooth LayoutAnimation.
  const prevOrderRef = useRef<string[]>([]);

  const loadOutsiders = useCallback(async () => {
    const applyData = (data: any) => {
      const allOutsiders = [...(data?.golden || []), ...(data?.regular || [])];
      const prevIds = prevOrderRef.current;
      const newIds = allOutsiders.map((o) => o.id);
      const orderChanged = prevIds.length > 0
        && (prevIds.length !== newIds.length || newIds.some((id, i) => id !== prevIds[i]));
      if (orderChanged) {
        LayoutAnimation.configureNext(
          LayoutAnimation.create(350, LayoutAnimation.Types.easeOut, LayoutAnimation.Properties.opacity)
        );
      }
      prevOrderRef.current = newIds;
      setOutsiders(allOutsiders);
    };

    await fetchSWR<any>(
      cacheKeyOutsiders(),
      async () => {
        const res = await fetch(API("/outsiders"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      },
      {
        onCached: (data) => {
          applyData(data);
          setLoading(false);
        },
        onFresh: applyData,
        onError: (err) => console.error("Failed to load outsiders:", err),
      },
      60 * 1000,
    );

    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    loadOutsiders();
    // Sujet 2 — refresh every 60s so rank movements surface near real time.
    const interval = setInterval(() => loadOutsiders(), 60000);
    return () => clearInterval(interval);
  }, [loadOutsiders]);

  // Directional flash on rank shifts ≥3 between two refreshes (V1 "Stock
  // Market of Fame" lite, same hook used by Home and Classement).
  const flashMap = useRankFlash(outsiders, { minDelta: 3, flashDuration: 450 });

  const handleLikeOutsider = useCallback(async (personId: string) => {
    try {
      const did = await getDeviceId();
      const res = await fetch(API(`/people/${personId}/vote`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Device-ID": did,
        },
        body: JSON.stringify({ value: 1 }),
      });
      if (res.ok) {
        setOutsiders((prev) =>
          prev.map((o) =>
            o.id === personId ? { ...o, likes: (o.likes || 0) + 1 } : o
          )
        );
      }
    } catch (err) {
      console.error("Like outsider error:", err);
    }
  }, [getDeviceId]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadOutsiders();
  }, [loadOutsiders]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <BackHeader title={t("outsiders.title")} />
        <View style={styles.center}>
          <ActivityIndicator size="large" color={PALETTE.accent2} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <BackHeader title={t("outsiders.title")} />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 8, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.accent2} />}
      >
        {/* Page description */}
        <Text style={styles.pageDesc}>{t("outsiders.subtitle")}</Text>

        {outsiders.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="people-outline" size={64} color={PALETTE.cardBorder} />
            <Text style={styles.emptyText}>{t("outsiders.noOutsiders")}</Text>
            <TouchableOpacity style={styles.boostCta} onPress={() => router.push("/premium")} activeOpacity={0.7}>
              <Text style={styles.boostCtaText}>{t("outsiders.beFirst")}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          outsiders.map((outsider, idx) => (
            <React.Fragment key={outsider.id}>
              <View style={{ marginBottom: 12 }}>
                <OutsiderCard
                  outsider={outsider}
                  onLike={handleLikeOutsider}
                  pulsingHeart={false}
                />
                <FlashOverlay direction={flashMap.get(outsider.id)} borderRadius={12} />
              </View>
              {/* Inject promo card every 10 items */}
              {(idx + 1) % 10 === 0 && <BoosterPromoCard variant={Math.floor(idx / 10)} />}
            </React.Fragment>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  pageDesc: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: "center",
    marginBottom: 16,
    lineHeight: 20,
  },
  // Promo Card
  promoCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 2,
    padding: 16,
    marginBottom: 12,
    marginVertical: 4,
  },
  promoIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: "center",
    alignItems: "center",
  },
  promoTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  promoSub: {
    fontSize: 13,
    color: PALETTE.subtext,
    marginTop: 2,
  },
  // Empty
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 60,
  },
  emptyText: {
    fontSize: 16,
    color: PALETTE.subtext,
    marginTop: 12,
    marginBottom: 20,
  },
  boostCta: {
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 24,
  },
  boostCtaText: {
    color: "#FFF",
    fontWeight: "700",
    fontSize: 15,
  },
});
