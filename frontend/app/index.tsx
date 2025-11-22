import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { FlashList } from "@shopify/flash-list";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter } from "expo-router";
import { LineChart } from "react-native-gifted-charts";

const PALETTE = {
  // Greener theme
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#8B0000", // dark red
  accent2: "#E04F5F", // secondary accent
  border: "#2E6148",
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || ""; // ingress will route /api -> backend
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

// Simple API helper
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

async function apiPost<T>(path: string, body?: any, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(API(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`POST ${path} ${res.status} ${txt}`);
  }
  return res.json();
}

// Device ID (for anonymous voting)
const DEVICE_KEY = "popularity_device_id";
async function getDeviceId() {
  let id = await AsyncStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    await AsyncStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

type FilterCat = "all" | "politics" | "culture" | "business" | "sport";

// Types
interface Person {
  id: string;
  name: string;
  category?: "politics" | "culture" | "business" | "sport" | "other";
  approved: boolean;
  score: number;
  likes: number;
  dislikes: number;
  total_votes: number;
}

export default function Index() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [lastSearches, setLastSearches] = useState<string[]>([]);
  const [byCat, setByCat] = useState<{ politics: string[]; culture: string[]; business: string[] }>({ politics: [], culture: [], business: [] });
  const [filter, setFilter] = useState<FilterCat>("all");
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [pendingPersonName, setPendingPersonName] = useState("");

  // Featured mini chart
  const [featured, setFeatured] = useState<Person | null>(null);
  const [featuredPoints, setFeaturedPoints] = useState<{ value: number }[]>([]);
  const rotateTimer = useRef<any>(null);

  const loadSavedFilter = useCallback(async () => {
    try {
      const saved = await AsyncStorage.getItem("popularity_home_filter");
      if (saved === "all" || saved === "politics" || saved === "culture" || saved === "business") {
        setFilter(saved);
      }
    } catch {}
  }, []);

  useEffect(() => { loadSavedFilter(); }, [loadSavedFilter]);
  useEffect(() => { AsyncStorage.setItem("popularity_home_filter", filter).catch(() => {}); }, [filter]);

  const fetchPeople = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const data = await apiGet<Person[]>(`/people${q ? `?query=${encodeURIComponent(q)}` : ""}`);
      setPeople(data);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSuggestions = useCallback(async () => {
    try {
      const data = await apiGet<{ terms: string[] }>("/search-suggestions?window=24h&limit=10");
      setSuggestions(data.terms);
    } catch {}
  }, []);

  const fetchLast = useCallback(async () => {
    try {
      const data = await apiGet<{ terms: string[] }>("/last-searches?limit=5");
      setLastSearches(data.terms);
    } catch {}
  }, []);

  const fetchByCategory = useCallback(async () => {
    try {
      const data = await apiGet<{ politics: string[]; culture: string[]; business: string[] }>("/search-suggestions/by-category?window=24h&perCatLimit=12");
      setByCat({ politics: data.politics || [], culture: data.culture || [], business: data.business || [] });
    } catch {}
  }, []);

  useEffect(() => {
    fetchPeople();
    fetchSuggestions();
    fetchLast();
    fetchByCategory();
  }, [fetchPeople, fetchSuggestions, fetchLast, fetchByCategory]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchPeople(query || undefined), fetchSuggestions(), fetchLast(), fetchByCategory()]);
    setRefreshing(false);
  }, [fetchPeople, fetchSuggestions, fetchLast, fetchByCategory, query]);

  const dismissKeyboard = () => Keyboard.dismiss();

  const onSearch = useCallback(async () => {
    dismissKeyboard();
    try {
      await apiPost("/searches", { query });
      fetchLast();
    } catch {}
    fetchPeople(query);
  }, [query, fetchPeople, fetchLast]);

  const onAddPerson = useCallback(async (category?: string) => {
    const name = category ? pendingPersonName : query.trim();
    if (!name) return;
    
    // If no category provided, show modal to select one
    if (!category) {
      setPendingPersonName(name);
      setShowCategoryModal(true);
      return;
    }
    
    try {
      const person = await apiPost<Person>("/people", { name, category });
      setQuery("");
      setPendingPersonName("");
      setShowCategoryModal(false);
      await fetchPeople();
      router.push({ pathname: "/person", params: { id: person.id, name: person.name } });
    } catch (e) {}
  }, [query, pendingPersonName, fetchPeople, router]);

  const filteredPeople = useMemo(() => {
    if (filter === "all") return people;
    return people.filter(p => p.category === filter);
  }, [people, filter]);

  // Open by name utility
  const openPersonByName = useCallback(async (name: string) => {
    try { await apiPost('/searches', { query: name }); } catch {}
    try {
      const results = await apiGet<Person[]>(`/people?query=${encodeURIComponent(name)}`);
      if (results && results.length > 0) {
        router.push({ pathname: '/person', params: { id: results[0].id, name: results[0].name } });
        return;
      }
    } catch {}
    setQuery(name);
    fetchPeople(name);
  }, [fetchPeople, router]);

  // Featured rotation logic
  const pickRandomFeatured = useCallback(async () => {
    if (!people || people.length === 0) return;
    const idx = Math.floor(Math.random() * people.length);
    const p = people[idx];
    setFeatured(p);
    try {
      const chart = await apiGet<{ id: string; name: string; points: { t: string; score: number }[] }>(`/people/${p.id}/chart?window=24h`);
      const pts = chart.points.map(pt => ({ value: pt.score }))
        .slice(-30); // keep small slice
      setFeaturedPoints(pts);
    } catch {}
  }, [people]);

  useEffect(() => {
    if (!people || people.length === 0) return;
    // initial pick
    pickRandomFeatured();
    // rotate every 10s
    if (rotateTimer.current) clearInterval(rotateTimer.current);
    rotateTimer.current = setInterval(pickRandomFeatured, 10000);
    return () => { if (rotateTimer.current) clearInterval(rotateTimer.current); };
  }, [people, pickRandomFeatured]);

  const renderPerson = ({ item }: { item: Person }) => (
    <View style={styles.personRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.personName} numberOfLines={1} ellipsizeMode="tail">{item.name}</Text>
        <Text style={styles.personMeta} numberOfLines={1} ellipsizeMode="tail">{item.category} • Score {item.score.toFixed(0)} • {item.total_votes} votes</Text>
        {/* Arrow mini controls */}
        <View style={styles.arrowRow}>
          <TouchableOpacity style={[styles.arrowBtn, { backgroundColor: PALETTE.accent }]} onPress={() => handleVote(item.id, 1)}>
            <Text style={styles.arrowText}>▲</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.arrowBtn, { backgroundColor: PALETTE.accent2 }]} onPress={() => handleVote(item.id, -1)}>
            <Text style={styles.arrowText}>▼</Text>
          </TouchableOpacity>
        </View>
      </View>
      <View style={styles.actions}>
        <TouchableOpacity style={[styles.rateBtn, styles.like]} onPress={() => handleVote(item.id, 1)}>
          <Text style={styles.rateText}>Like</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.rateBtn, styles.dislike]} onPress={() => handleVote(item.id, -1)}>
          <Text style={styles.rateText}>Dislike</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.openBtn} onPress={() => router.push({ pathname: "/person", params: { id: item.id, name: item.name } })}>
          <Text style={styles.openText}>Open</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const handleVote = useCallback(async (id: string, value: 1 | -1) => {
    const device = await getDeviceId();
    try {
      await apiPost(`/people/${id}/vote`, { value }, { "X-Device-ID": device });
      await fetchPeople(query || undefined);
    } catch {}
  }, [fetchPeople, query]);

  const renderChips = (items: string[]) => (
    <ScrollView horizontal contentContainerStyle={styles.chips} showsHorizontalScrollIndicator={false}>
      {items.map((s) => (
        <TouchableOpacity key={s} style={styles.chip} onPress={() => openPersonByName(s)}>
          <Text style={styles.chipText}>{s}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderRectangle = (items: string[], emptyText: string, max = 4) => (
    <View style={styles.lastCard}>
      {(items.slice(0, max)).length === 0 ? (
        <Text style={styles.lastText}>{emptyText}</Text>
      ) : (
        items.slice(0, max).map((s) => (
          <TouchableOpacity key={s} onPress={() => openPersonByName(s)} style={styles.lastRow}>
            <Text style={styles.lastText}>{s}</Text>
          </TouchableOpacity>
        ))
      )}
    </View>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: PALETTE.bg }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <Pressable onPress={dismissKeyboard} style={{ flex: 1 }}>
          <View style={styles.header}>
            <Text style={styles.title}>Popular</Text>
            <Text style={styles.subtitle}>Rate them. Watch their ratings move up and down live</Text>
          </View>

          <View style={styles.searchCard}>
            <TextInput
              placeholder="Enter a name..."
              placeholderTextColor={PALETTE.subtext}
              style={styles.input}
              value={query}
              onChangeText={setQuery}
              returnKeyType="search"
              onSubmitEditing={() => onAddPerson()}
            />
            <TouchableOpacity onPress={onAddPerson} style={[styles.primaryBtn, { backgroundColor: PALETTE.accent, marginTop: 12 }] }>
              <Text style={styles.primaryText}>Rate</Text>
            </TouchableOpacity>
          </View>

          {/* Category Filter Bar (smaller chips) */}
          <FilterBarSmall onNavigate={(key) => {
            router.push({ pathname: '/category/[key]', params: { key } });
          }} />

          {/* Featured mini chart */}
          {featured && (
            <TouchableOpacity style={styles.featureCard} onPress={() => router.push({ pathname: '/person', params: { id: featured.id, name: featured.name } })}>
              <Text style={styles.featureTitle} numberOfLines={1} ellipsizeMode="tail">{featured.name}</Text>
              <View style={{ height: 8 }} />
              <Text style={styles.featureMeta} numberOfLines={1} ellipsizeMode="tail">{featured.category} • Score {Math.round(featured.score)}</Text>
              <View style={{ height: 8 }} />
              <LineChart
                areaChart
                data={featuredPoints}
                curved
                color={PALETTE.accent2}
                thickness={2}
                startFillColor={PALETTE.accent2}
                startOpacity={0.25}
                endOpacity={0.05}
                hideDataPoints
                yAxisThickness={0}
                xAxisThickness={0}
                backgroundColor={PALETTE.card}
                rulesColor={PALETTE.border}
                noOfSections={3}
                height={80}
                initialSpacing={0}
              />
            </TouchableOpacity>
          )}

          {loading ? (
            <ActivityIndicator color={PALETTE.accent2} style={{ marginTop: 24 }} />
          ) : (
            <View style={{ paddingBottom: 24 }}>
              <Text style={styles.sectionTitle}>Trending searches</Text>
              {renderRectangle(suggestions, 'No trending searches', 8)}
            </View>
          )}
        </Pressable>
      </KeyboardAvoidingView>

      {/* Category Selection Modal */}
      <Modal
        visible={showCategoryModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowCategoryModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Sélectionnez une catégorie</Text>
            <Text style={styles.modalSubtitle}>{pendingPersonName}</Text>
            
            <TouchableOpacity style={[styles.categoryBtn, { backgroundColor: '#2E6148' }]} onPress={() => onAddPerson('politics')}>
              <Text style={styles.categoryBtnText}>Politics</Text>
            </TouchableOpacity>
            
            <TouchableOpacity style={[styles.categoryBtn, { backgroundColor: '#2E6148' }]} onPress={() => onAddPerson('culture')}>
              <Text style={styles.categoryBtnText}>Culture</Text>
            </TouchableOpacity>
            
            <TouchableOpacity style={[styles.categoryBtn, { backgroundColor: '#2E6148' }]} onPress={() => onAddPerson('business')}>
              <Text style={styles.categoryBtnText}>Business</Text>
            </TouchableOpacity>
            
            <TouchableOpacity style={[styles.categoryBtn, { backgroundColor: '#2E6148' }]} onPress={() => onAddPerson('sport')}>
              <Text style={styles.categoryBtnText}>Sport</Text>
            </TouchableOpacity>
            
            <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowCategoryModal(false); setPendingPersonName(''); }}>
              <Text style={styles.cancelBtnText}>Annuler</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function FilterBarSmall({ onNavigate }: { onNavigate: (key: FilterCat) => void }) {
  const tabs: { key: FilterCat; label: string }[] = [
    { key: "all", label: "All" },
    { key: "politics", label: "Politics" },
    { key: "culture", label: "Culture" },
    { key: "business", label: "Business" },
    { key: "sport", label: "Sport" },
  ];
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 4, gap: 8 }}>
      {tabs.map(t => (
        <TouchableOpacity key={t.key} onPress={() => onNavigate(t.key)} style={styles.smallChip}>
          <Text style={styles.smallChipText}>{t.label}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 8,
  },
  title: {
    fontSize: 28,
    fontWeight: "800",
    color: PALETTE.text,
  },
  subtitle: {
    fontSize: 14,
    color: PALETTE.subtext,
    marginTop: 4,
  },
  searchCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 12,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  input: {
    backgroundColor: PALETTE.bg,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: Platform.select({ ios: 12, android: 10 }),
    color: PALETTE.text,
    fontSize: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  searchActions: {
    flexDirection: "row",
    gap: 12,
    marginTop: 12,
  },
  primaryBtn: {
    flex: 1,
    height: 44,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryText: {
    color: "white",
    fontWeight: "700",
    fontSize: 16,
  },
  secondaryText: {
    color: PALETTE.text,
    fontWeight: "700",
    fontSize: 16,
  },
  sectionTitle: {
    color: PALETTE.subtext,
    marginHorizontal: 16,
    marginTop: 16,
    marginBottom: 8,
  },
  featureCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 12,
    padding: 12,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  featureTitle: { color: PALETTE.text, fontWeight: '700', fontSize: 16 },
  featureMeta: { color: PALETTE.subtext },
  chips: {
    paddingHorizontal: 12,
  },
  chip: {
    backgroundColor: PALETTE.card,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
    marginHorizontal: 4,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  chipText: { color: PALETTE.text, fontWeight: '600' },
  lastCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    borderRadius: 12,
    borderColor: PALETTE.border,
    borderWidth: 1,
    overflow: 'hidden',
  },
  lastRow: {
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  lastText: { color: PALETTE.text },
  personRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 10,
  },
  personName: { color: PALETTE.text, fontSize: 16, fontWeight: "600" },
  personMeta: { color: PALETTE.subtext, marginTop: 2 },
  arrowRow: { flexDirection: 'row', gap: 6, marginTop: 6 },
  arrowBtn: { height: 24, paddingHorizontal: 8, borderRadius: 6, alignItems: 'center', justifyContent: 'center' },
  arrowText: { color: 'white', fontWeight: '800', fontSize: 12 },
  actions: { flexDirection: "column", alignItems: "flex-end", gap: 4 },
  rateBtn: {
    height: 10,
    width: 50,
    paddingHorizontal: 4,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
  },
  like: { backgroundColor: PALETTE.accent },
  dislike: { backgroundColor: PALETTE.accent2 },
  rateText: { color: "white", fontWeight: "700", fontSize: 9 },
  openBtn: {
    height: 10,
    width: 50,
    paddingHorizontal: 4,
    borderRadius: 8,
    borderColor: PALETTE.border,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: PALETTE.card,
  },
  openText: { color: PALETTE.text, fontWeight: "700", fontSize: 9 },
  smallChip: {
    backgroundColor: PALETTE.card,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 14,
    borderColor: PALETTE.border,
    borderWidth: 1,
    marginHorizontal: 4,
  },
  smallChipText: { color: PALETTE.text, fontSize: 12, fontWeight: '600' },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    padding: 24,
    width: '80%',
    maxWidth: 400,
    borderColor: PALETTE.border,
    borderWidth: 1,
  },
  modalTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  modalSubtitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginBottom: 20,
    textAlign: 'center',
  },
  categoryBtn: {
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
    alignItems: 'center',
  },
  categoryBtnText: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '600',
  },
  cancelBtn: {
    padding: 12,
    marginTop: 8,
    alignItems: 'center',
  },
  cancelBtnText: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: '600',
  },
});
