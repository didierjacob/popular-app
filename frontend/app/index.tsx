import React, { useEffect, useState, useRef } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  RefreshControl,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Svg, { Circle, Path, Defs, LinearGradient, Stop, Ellipse } from "react-native-svg";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000",
  accent2: "#E04F5F",
  green: "#009B4D",
  border: "#2E6148",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

// Helper to capitalize first letter
const capitalize = (str: string) => str ? str.charAt(0).toUpperCase() + str.slice(1) : str;

// Helper to format numbers without decimals
const formatNumber = (num: number) => Math.round(num).toLocaleString();

interface Person {
  id: string;
  name: string;
  category: string;
  score: number;
  total_votes: number;
}

interface Category {
  key: string;
  label: string;
  icon: string;
}

const CATEGORIES: Category[] = [
  { key: "politics", label: "Politics", icon: "people" },
  { key: "culture", label: "Culture", icon: "color-palette" },
  { key: "business", label: "Business", icon: "briefcase" },
  { key: "sport", label: "Sport", icon: "football" },
];

// 3D Gauge Icon Component
function GaugeIcon({ score, size = 32 }: { score: number; size?: number }) {
  // Normalize score to 0-100 range for the gauge
  const normalizedScore = Math.min(100, Math.max(0, score));
  // Convert score to angle (-135 to 135 degrees, so 270 degree sweep)
  const angle = -135 + (normalizedScore / 100) * 270;
  const angleRad = (angle * Math.PI) / 180;
  
  const centerX = size / 2;
  const centerY = size / 2;
  const needleLength = size * 0.32;
  
  const needleX = centerX + needleLength * Math.cos(angleRad);
  const needleY = centerY + needleLength * Math.sin(angleRad);

  return (
    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <Defs>
        <LinearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <Stop offset="0%" stopColor="#4A6858" />
          <Stop offset="50%" stopColor="#2E4A3A" />
          <Stop offset="100%" stopColor="#1C3A2C" />
        </LinearGradient>
        <LinearGradient id="bezelGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <Stop offset="0%" stopColor="#5A7868" />
          <Stop offset="30%" stopColor="#3E5A4A" />
          <Stop offset="70%" stopColor="#2A4636" />
          <Stop offset="100%" stopColor="#1C3428" />
        </LinearGradient>
        <LinearGradient id="innerShadow" x1="0%" y1="0%" x2="0%" y2="100%">
          <Stop offset="0%" stopColor="#0F2F22" />
          <Stop offset="100%" stopColor="#1C3A2C" />
        </LinearGradient>
        <LinearGradient id="needleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <Stop offset="0%" stopColor="#FF6B6B" />
          <Stop offset="50%" stopColor="#EE5A5A" />
          <Stop offset="100%" stopColor="#CC4444" />
        </LinearGradient>
      </Defs>
      
      {/* Outer bezel - 3D ring effect */}
      <Circle
        cx={centerX}
        cy={centerY}
        r={size * 0.46}
        fill="url(#bezelGradient)"
      />
      
      {/* Inner shadow ring */}
      <Circle
        cx={centerX}
        cy={centerY}
        r={size * 0.40}
        fill="url(#innerShadow)"
      />
      
      {/* Main gauge face */}
      <Circle
        cx={centerX}
        cy={centerY}
        r={size * 0.36}
        fill="url(#gaugeGradient)"
      />
      
      {/* Scale arc background */}
      <Path
        d={`M ${centerX - size * 0.26} ${centerY + size * 0.1} 
            A ${size * 0.28} ${size * 0.28} 0 1 1 ${centerX + size * 0.26} ${centerY + size * 0.1}`}
        stroke="#1A3328"
        strokeWidth={size * 0.06}
        fill="none"
        strokeLinecap="round"
      />
      
      {/* Colored scale arc */}
      <Path
        d={`M ${centerX - size * 0.26} ${centerY + size * 0.1} 
            A ${size * 0.28} ${size * 0.28} 0 1 1 ${centerX + size * 0.26} ${centerY + size * 0.1}`}
        stroke="#2E6148"
        strokeWidth={size * 0.04}
        fill="none"
        strokeLinecap="round"
        opacity={0.6}
      />
      
      {/* Needle shadow */}
      <Path
        d={`M ${centerX + 1} ${centerY + 1} L ${needleX + 1} ${needleY + 1}`}
        stroke="rgba(0,0,0,0.4)"
        strokeWidth={size * 0.05}
        strokeLinecap="round"
      />
      
      {/* Main needle */}
      <Path
        d={`M ${centerX} ${centerY} L ${needleX} ${needleY}`}
        stroke="url(#needleGradient)"
        strokeWidth={size * 0.045}
        strokeLinecap="round"
      />
      
      {/* Center hub - outer ring */}
      <Circle
        cx={centerX}
        cy={centerY}
        r={size * 0.09}
        fill="#4A6858"
      />
      
      {/* Center hub - inner */}
      <Circle
        cx={centerX}
        cy={centerY}
        r={size * 0.06}
        fill="#3A5848"
      />
      
      {/* Center hub - highlight */}
      <Ellipse
        cx={centerX - size * 0.015}
        cy={centerY - size * 0.02}
        rx={size * 0.025}
        ry={size * 0.02}
        fill="rgba(255,255,255,0.2)"
      />
    </Svg>
  );
}

export default function HomeScreen() {
  const router = useRouter();
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleTapCount = useRef(0);
  const titleTapTimer = useRef<NodeJS.Timeout | null>(null);

  const loadPeople = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const response = await fetch(API("/people?limit=10"));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setPeople(data);
    } catch (e: any) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadPeople();
    const interval = setInterval(() => loadPeople(true), 5000);
    return () => clearInterval(interval);
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadPeople(true);
    setRefreshing(false);
  };

  const handleTitleTap = () => {
    titleTapCount.current += 1;
    
    if (titleTapTimer.current) {
      clearTimeout(titleTapTimer.current);
    }
    
    if (titleTapCount.current >= 7) {
      titleTapCount.current = 0;
      router.push("/admin");
      return;
    }
    
    titleTapTimer.current = setTimeout(() => {
      titleTapCount.current = 0;
    }, 2000);
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={{ flex: 1 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={PALETTE.accent2}
          />
        }
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={handleTitleTap} activeOpacity={0.8}>
            <Text style={styles.title}>Popular</Text>
          </TouchableOpacity>
          <Text style={styles.subtitle}>Rate them. Buy credits to become popular</Text>
        </View>

        {/* Categories */}
        <View style={styles.categoriesContainer}>
          <Text style={styles.sectionTitle}>Categories</Text>
          <View style={styles.categoriesGrid}>
            {CATEGORIES.map((cat) => (
              <TouchableOpacity
                key={cat.key}
                style={styles.categoryCard}
                onPress={() => router.push({ pathname: "/category/[key]", params: { key: cat.key } })}
              >
                <Ionicons name={cat.icon as any} size={28} color={PALETTE.accent2} />
                <Text style={styles.categoryLabel}>{cat.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Top Personalities */}
        <View style={styles.topSection}>
          <Text style={styles.sectionTitle}>Top Personalities</Text>
          
          {loading && (
            <View style={styles.center}>
              <ActivityIndicator size="large" color={PALETTE.accent2} />
              <Text style={styles.loadingText}>Loading...</Text>
            </View>
          )}

          {error && (
            <View style={styles.center}>
              <Text style={styles.errorText}>Error: {error}</Text>
              <TouchableOpacity style={styles.retryBtn} onPress={() => loadPeople()}>
                <Text style={styles.retryText}>Retry</Text>
              </TouchableOpacity>
            </View>
          )}

          {!loading && !error && people.map((person, index) => (
            <TouchableOpacity
              key={person.id}
              style={styles.personCard}
              onPress={() => router.push({ pathname: "/person", params: { id: person.id, name: person.name } })}
            >
              <View style={styles.rankBadge}>
                <Text style={styles.rankText}>#{index + 1}</Text>
              </View>
              <View style={styles.personInfo}>
                <Text style={styles.personName}>{person.name}</Text>
                <Text style={styles.personMeta}>
                  {capitalize(person.category)} • {formatNumber(person.total_votes)} {person.total_votes <= 1 ? 'vote' : 'votes'}
                </Text>
              </View>
              <View style={styles.gaugeContainer}>
                <GaugeIcon score={person.score} size={36} />
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  header: {
    padding: 20,
    alignItems: "center",
  },
  title: {
    fontSize: 32,
    fontWeight: "bold",
    color: PALETTE.text,
  },
  subtitle: {
    fontSize: 14,
    color: PALETTE.subtext,
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: PALETTE.text,
    marginBottom: 12,
    paddingHorizontal: 16,
  },
  categoriesContainer: {
    marginTop: 8,
  },
  categoriesGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: 12,
    gap: 8,
  },
  categoryCard: {
    width: "47%",
    backgroundColor: PALETTE.card,
    padding: 16,
    borderRadius: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  categoryLabel: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: "600",
    marginTop: 8,
  },
  topSection: {
    marginTop: 24,
    paddingBottom: 24,
  },
  center: {
    padding: 40,
    alignItems: "center",
  },
  loadingText: {
    color: PALETTE.subtext,
    marginTop: 10,
  },
  errorText: {
    color: "#E04F5F",
    fontSize: 16,
  },
  retryBtn: {
    marginTop: 20,
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: {
    color: PALETTE.text,
    fontWeight: "600",
  },
  personCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginBottom: 10,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  rankBadge: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: PALETTE.accent,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  rankText: {
    color: PALETTE.text,
    fontWeight: "700",
    fontSize: 14,
  },
  personInfo: {
    flex: 1,
  },
  personName: {
    fontSize: 16,
    fontWeight: "600",
    color: PALETTE.text,
  },
  personMeta: {
    fontSize: 13,
    color: PALETTE.subtext,
    marginTop: 2,
  },
  gaugeContainer: {
    marginLeft: 8,
  },
});
