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
import { SkeletonPersonCard, SkeletonFeaturedCard } from "../components/SkeletonLoader";
import { fetchWithCache, CacheService } from "../services/cacheService";
import { useNetworkStatus } from "../services/networkService";
import { PrefetchService } from "../services/prefetchService";

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
  source?: "seed" | "user_added" | "self_boosted";
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
  
  // Phase 1 - New features
  const [trendingNow, setTrendingNow] = useState<Person[]>([]);
  const [personOfDay, setPersonOfDay] = useState<Person | null>(null);
  const [showVoteAnimation, setShowVoteAnimation] = useState(false);
  
  // Phase 3 - Controversial personalities
  const [controversial, setControversial] = useState<Person[]>([]);

  // Phase 4 - Network status
  const { isConnected, isChecking } = useNetworkStatus();

  // Phase 4 - Real-time suggestions
  const [searchSuggestions, setSearchSuggestions] = useState<Person[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Admin secret gesture
  const [tapCount, setTapCount] = useState(0);
  const tapTimerRef = useRef<any>(null);

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
      const endpoint = `/people${q ? `?query=${encodeURIComponent(q)}` : ""}`;
      const cacheKey = `people_${q || 'all'}`;
      
      // Utiliser le cache avec TTL de 5 minutes
      const data = await fetchWithCache(
        endpoint,
        cacheKey,
        () => apiGet<Person[]>(endpoint),
        5 * 60 * 1000 // 5 minutes
      );
      
      setPeople(data);
    } catch (error) {
      console.error('Failed to fetch people:', error);
      // En cas d'erreur, essayer de charger depuis le cache même expiré
      const cacheKey = `people_${q || 'all'}`;
      const cached = await CacheService.get<Person[]>(cacheKey);
      if (cached) {
        setPeople(cached);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Phase 1 - Load Trending Now
  const fetchTrendingNow = useCallback(async () => {
    try {
      const res = await apiGet<Person[]>("/trending-now?limit=5");
      setTrendingNow(res);
    } catch {}
  }, []);

  // Phase 3 - Load Controversial
  const fetchControversial = useCallback(async () => {
    try {
      const res = await apiGet<Person[]>("/controversial?limit=5");
      setControversial(res);
    } catch {}
  }, []);

  // Phase 1 - Person of the Day (based on date)
  const selectPersonOfDay = useCallback((people: Person[]) => {
    if (people.length === 0) return;
    const today = new Date().toDateString();
    const seed = today.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const index = seed % people.length;
    setPersonOfDay(people[index]);
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
    loadSavedFilter();
    fetchTrendingNow(); // Phase 1
    fetchControversial(); // Phase 3
  }, [fetchPeople, fetchSuggestions, fetchLast, fetchByCategory, loadSavedFilter, fetchTrendingNow, fetchControversial]);

  // Phase 4 - Debounced search with real-time suggestions
  useEffect(() => {
    if (!query || query.length < 2) {
      setSearchSuggestions([]);
      setShowSuggestions(false);
      if (!query) {
        fetchPeople();
      }
      return;
    }

    // Debounce: attendre 300ms après la dernière frappe
    const timeoutId = setTimeout(async () => {
      try {
        // Fetch suggestions
        const results = await apiGet<Person[]>(`/people?query=${encodeURIComponent(query)}&limit=5`);
        setSearchSuggestions(results);
        setShowSuggestions(results.length > 0);
      } catch (error) {
        console.error('Failed to fetch suggestions:', error);
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [query]);

  // Phase 1 - Select person of day when people load
  useEffect(() => {
    if (people.length > 0) {
      selectPersonOfDay(people);
    }
  }, [people, selectPersonOfDay]);

  // Phase 4 - Prefetch top people data in background
  useEffect(() => {
    if (people.length > 0 && isConnected) {
      // Attendre 2 secondes après le chargement initial, puis précharger
      const timer = setTimeout(() => {
        const topPeopleIds = people
          .sort((a, b) => b.score - a.score)
          .slice(0, 5)
          .map(p => p.id);
        PrefetchService.prefetchTopPeople(topPeopleIds);
      }, 2000);

      return () => clearTimeout(timer);
    }
  }, [people, isConnected]);

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

  // Select suggestion
  const selectSuggestion = useCallback((person: Person) => {
    setQuery('');
    setShowSuggestions(false);
    setSearchSuggestions([]);
    dismissKeyboard();
    router.push({ pathname: '/person', params: { id: person.id, name: person.name } });
  }, [router]);

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

  // Get name color based on source
  const getNameColor = (source?: string) => {
    if (source === 'self_boosted') return '#A8C9B8'; // Lighter green-tinted for self-boosted users
    if (source === 'user_added') return '#C9D8D2'; // Slight variation for user-added
    return PALETTE.text; // White for seed personalities
  };

  const renderPerson = ({ item }: { item: Person }) => (
    <View style={styles.personRow}>
      <View style={{ flex: 1 }}>
        <Text style={[styles.personName, { color: getNameColor(item.source) }]} numberOfLines={1} ellipsizeMode="tail">{item.name}</Text>
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
      {/* Phase 4 - Offline indicator */}
      {!isConnected && !isChecking && (
        <View style={styles.offlineBanner}>
          <Text style={styles.offlineText}>📵 Mode hors-ligne • Données en cache</Text>
        </View>
      )}
      
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <Pressable onPress={dismissKeyboard} style={{ flex: 1 }}>
          <View style={styles.header}>
            <TouchableOpacity 
              activeOpacity={0.9}
              onPress={handleTitleTap}
            >
              <Text style={styles.title}>Popular</Text>
            </TouchableOpacity>
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

          {/* Phase 4 - Real-time suggestions */}
          {showSuggestions && searchSuggestions.length > 0 && (
            <View style={styles.suggestionsCard}>
              <Text style={styles.suggestionsTitle}>Suggestions :</Text>
              {searchSuggestions.map((person) => (
                <TouchableOpacity
                  key={person.id}
                  style={styles.suggestionItem}
                  onPress={() => selectSuggestion(person)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.suggestionName}>{person.name}</Text>
                    <Text style={styles.suggestionMeta}>
                      {person.category} • Score {person.score?.toFixed(0)}
                    </Text>
                  </View>
                  <Ionicons name="arrow-forward" size={20} color={PALETTE.subtext} />
                </TouchableOpacity>
              ))}
            </View>
          )}

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
            <View style={{ paddingVertical: 16 }}>
              <SkeletonFeaturedCard />
              <SkeletonPersonCard />
              <SkeletonPersonCard />
              <SkeletonPersonCard />
            </View>
          ) : (
            <View style={{ paddingBottom: 24 }}>
              {/* Phase 1 - Person of the Day */}
              {personOfDay && (
                <TouchableOpacity 
                  style={styles.personOfDayCard}
                  onPress={() => router.push({ pathname: '/person', params: { id: personOfDay.id, name: personOfDay.name } })}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                    <Text style={styles.badge}>⭐ Du jour</Text>
                  </View>
                  <Text style={styles.personOfDayName} numberOfLines={1}>{personOfDay.name}</Text>
                  <Text style={styles.personOfDayMeta} numberOfLines={1}>
                    Score {personOfDay.score} • {personOfDay.total_votes} votes
                  </Text>
                </TouchableOpacity>
              )}

              {/* Phase 1 - Trending Now */}
              {trendingNow.length > 0 && (
                <>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginTop: 16, marginBottom: 8 }}>
                    <Text style={styles.sectionTitle} style={{ margin: 0 }}>🔥 Trending Now</Text>
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 12 }}>
                    {trendingNow.map(p => (
                      <TouchableOpacity
                        key={p.id}
                        style={styles.trendingCard}
                        onPress={() => router.push({ pathname: '/person', params: { id: p.id, name: p.name } })}
                      >
                        <Text style={[styles.trendingName, { color: getNameColor(p.source) }]} numberOfLines={1}>{p.name}</Text>
                        <Text style={styles.trendingScore}>↗ {p.score}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                </>
              )}

              {/* Phase 3 - Controversial */}
              {controversial.length > 0 && (
                <>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginTop: 16, marginBottom: 8 }}>
                    <Text style={styles.sectionTitle} style={{ margin: 0 }}>⚡ Controversées</Text>
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 12 }}>
                    {controversial.map(p => (
                      <TouchableOpacity
                        key={p.id}
                        style={styles.controversialCard}
                        onPress={() => router.push({ pathname: '/person', params: { id: p.id, name: p.name } })}
                      >
                        <View style={styles.controversialBadge}>
                          <Text style={styles.controversialBadgeText}>⚡</Text>
                        </View>
                        <Text style={[styles.controversialName, { color: getNameColor(p.source) }]} numberOfLines={1}>{p.name}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 }}>
                          <Text style={styles.controversialVotes}>👍 {p.likes}</Text>
                          <Text style={styles.controversialVotes}>👎 {p.dislikes}</Text>
                        </View>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                </>
              )}

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
  // Phase 1 - Person of the Day
  personOfDayCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 16,
    marginBottom: 16,
    borderWidth: 2,
    borderColor: '#FFD700',
  },
  badge: {
    color: '#FFD700',
    fontSize: 14,
    fontWeight: '700',
  },
  personOfDayName: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 4,
  },
  personOfDayMeta: {
    color: PALETTE.subtext,
    fontSize: 14,
  },
  // Phase 1 - Trending Now
  trendingCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    padding: 12,
    width: 120,
    borderWidth: 1,
    borderColor: '#FF6B6B',
  },
  trendingName: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  trendingScore: {
    color: '#FF6B6B',
    fontSize: 16,
    fontWeight: '700',
  },
  // Phase 3 - Controversial
  controversialCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    padding: 12,
    width: 130,
    borderWidth: 2,
    borderColor: '#FFA500',
    position: 'relative',
  },
  controversialBadge: {
    position: 'absolute',
    top: -8,
    right: -8,
    backgroundColor: '#FFA500',
    borderRadius: 12,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  controversialBadgeText: {
    fontSize: 14,
  },
  controversialName: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  controversialVotes: {
    color: PALETTE.subtext,
    fontSize: 12,
  },
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
  // Phase 4 - Offline indicator
  offlineBanner: {
    backgroundColor: '#FF9800',
    paddingVertical: 8,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  offlineText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  // Phase 4 - Suggestions
  suggestionsCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  suggestionsTitle: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 8,
  },
  suggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  suggestionName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '600',
  },
  suggestionMeta: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
});
