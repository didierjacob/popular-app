import React, { useCallback, useEffect, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Alert,
  ActivityIndicator,
  RefreshControl,
  Platform,
  Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';

const ADMIN_TOKEN_KEY = 'popularoo_admin_token_v1';

async function loadStoredToken(): Promise<string | null> {
  try {
    if (Platform.OS === 'web') {
      try { return window.localStorage.getItem(ADMIN_TOKEN_KEY); } catch { return null; }
    }
    return await SecureStore.getItemAsync(ADMIN_TOKEN_KEY);
  } catch { return null; }
}

async function saveStoredToken(token: string): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      try { window.localStorage.setItem(ADMIN_TOKEN_KEY, token); } catch {}
      return;
    }
    await SecureStore.setItemAsync(ADMIN_TOKEN_KEY, token);
  } catch {}
}

async function clearStoredToken(): Promise<void> {
  try {
    if (Platform.OS === 'web') {
      try { window.localStorage.removeItem(ADMIN_TOKEN_KEY); } catch {}
      return;
    }
    await SecureStore.deleteItemAsync(ADMIN_TOKEN_KEY);
  } catch {}
}

const PALETTE = {
  bg: '#0F2F22',
  card: '#1C3A2C',
  text: '#EAEAEA',
  subtext: '#C9D8D2',
  accent: '#8B0000',
  green: '#00D866',
  gold: '#FFD700',
  border: '#2E6148',
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const API = (path: string) => `${API_BASE}/api${path.startsWith('/') ? path : `/${path}`}`;

interface Stats {
  total_people: number;
  total_votes: number;
  active_users_24h: number;
  active_users_7d?: number;
  active_users_30d?: number;
  revenue_24h: string;
  revenue_total_lifetime?: string;
  new_people_24h: number;
}

// Vague 4 sous-tache 6 — Stats enrichie (GET /admin/dashboard-stats)
interface DashboardStats {
  total_celebrities: number;
  category_breakdown: Record<string, number>;
  alpha: number;
  queues: {
    pending_candidates: number;
    pending_deceased: number;
    pending_category_reviews: number;
  };
  last_jobs: {
    external_scores: string | null;
    candidate_detection: string | null;
    deceased_check_top50: string | null;
    deceased_check_all: string | null;
    category_review: string | null;
  };
  top5: Array<{ name: string; category: string | null; popularoo_index: number }>;
}

interface Person {
  id: string;
  name: string;
  score: number;
  likes: number;
  dislikes: number;
  total_votes: number;
  source?: string;
  category?: string;
  created_at?: string;
}

interface ActivityData {
  recent_people: any[];
  recent_purchases: any[];
  recent_uses: any[];
}

interface Settings {
  allow_user_additions: boolean;
  booster_price: number;
  super_booster_price: number;
  booster_votes: number;
  super_booster_votes: number;
  maintenance_mode: boolean;
}

// Vague 4 — Candidats (2 zones)
// Zone 1: candidate_queue (en attente de validation auto 24h, intervention admin avant echeance)
interface PendingQueueEntry {
  id: string;
  name: string;
  slug: string | null;
  requested_at: string | null;
  process_after: string | null;
  requested_by_device_id: string | null;
  pending_vote_value: number;
  last_error: string | null;
}

// Zone 2: persons.source=user_search publies recemment (moderation post-publication)
interface Candidate {
  id: string;
  name: string;
  category: string;
  category_confidence: string;
  score: number;
  popularoo_index: number;
  popularity_external_score: number;
  total_votes: number;
  visible_in_rankings: boolean;
  wiki_description: string;
  created_at: string | null;
}

const CANDIDATE_CATEGORIES = ['culture', 'sport', 'politics', 'business', 'influencer', 'other'] as const;
type CandidateCategory = typeof CANDIDATE_CATEGORIES[number];

type Tab =
  | 'stats'           // ex-dashboard, sera enrichi en sous-tache 6
  | 'activity'        // existant
  | 'candidates'      // placeholder, sous-tache 1
  | 'outsider_reports'// placeholder, sous-tache 2
  | 'manual_add'      // placeholder, sous-tache 3
  | 'deceased'        // placeholder, sous-tache 4
  | 'categories'      // placeholder, sous-tache 5
  | 'moderation'      // existant
  | 'settings';       // existant

const TAB_LABELS: Record<Tab, { label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  stats:            { label: 'Stats',      icon: 'stats-chart' },
  activity:         { label: 'Activite',   icon: 'pulse' },
  candidates:       { label: 'Candidats',  icon: 'people-circle' },
  outsider_reports: { label: 'Outsiders',  icon: 'flag' },
  manual_add:       { label: 'Ajout',      icon: 'add-circle' },
  deceased:         { label: 'Decedes',    icon: 'skull' },
  categories:       { label: 'Categories', icon: 'pricetags' },
  moderation:       { label: 'Moderation', icon: 'shield-checkmark' },
  settings:         { label: 'Settings',   icon: 'settings' },
};

const TAB_ORDER: Tab[] = [
  'stats', 'activity', 'candidates', 'outsider_reports',
  'manual_add', 'deceased', 'categories', 'moderation', 'settings',
];

export default function Admin() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [currentTab, setCurrentTab] = useState<Tab>('stats');
  // Tentative d'auto-auth via token stocke (verify-token au mount). Tant que c'est en cours, on affiche un loader plutot que le login.
  const [bootstrapping, setBootstrapping] = useState(true);
  
  // Stats
  const [stats, setStats] = useState<Stats | null>(null);
  const [topPeople, setTopPeople] = useState<Person[]>([]);
  // Vague 4 sous-tache 6 — Stats enrichie (dashboard-stats, parallele a stats legacy)
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  
  // Boost
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  
  // Search & Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterSource, setFilterSource] = useState<string>('');
  const [searchResults, setSearchResults] = useState<Person[]>([]);
  
  // Activity
  const [activityData, setActivityData] = useState<ActivityData | null>(null);
  
  // Settings
  const [settings, setSettings] = useState<Settings | null>(null);

  // Vague 4 — Candidats (zone 2: publies recents)
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [publishedCollapsed, setPublishedCollapsed] = useState(false);

  // Vague 4 — Candidats (zone 1: en attente queue 24h)
  const [pendingQueue, setPendingQueue] = useState<PendingQueueEntry[]>([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [pendingError, setPendingError] = useState<string | null>(null);

  const [adminToken, setAdminToken] = useState<string>('');

  // Helper: makes authenticated admin requests. On 403, forces re-login.
  const adminFetch = useCallback(async (url: string, options: RequestInit = {}): Promise<Response> => {
    const headers = {
      ...((options.headers as Record<string, string>) || {}),
      'X-Admin-Token': adminToken,
    };
    const response = await fetch(url, { ...options, headers });

    if (response.status === 403 && authenticated) {
      setAuthenticated(false);
      setAdminToken('');
      await clearStoredToken();
      Alert.alert(
        'Session expirée',
        'Votre session admin a expiré. Veuillez vous reconnecter.',
        [{ text: 'OK' }]
      );
    }
    return response;
  }, [adminToken, authenticated]);

  // Auto-auth au mount: si un token est stocke et toujours valide cote serveur, on saute le login.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await loadStoredToken();
      if (!stored) {
        if (!cancelled) setBootstrapping(false);
        return;
      }
      try {
        const res = await fetch(API('/admin/verify-token'), {
          headers: { 'X-Admin-Token': stored },
        });
        if (cancelled) return;
        if (res.ok) {
          setAdminToken(stored);
          setAuthenticated(true);
        } else {
          await clearStoredToken();
        }
      } catch {
        // Pas de reseau: on reste sur le login, le token survit en stockage.
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleLogout = useCallback(async () => {
    await clearStoredToken();
    setAdminToken('');
    setAuthenticated(false);
    setPassword('');
  }, []);

  const handleLogin = async () => {
    try {
      const response = await fetch(API('/admin/auth'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      
      if (response.ok) {
        const data = await response.json();
        setAdminToken(data.token);
        setAuthenticated(true);
        await saveStoredToken(data.token);
        loadData();
      } else {
        Alert.alert('Error', 'Mot de passe incorrect');
      }
    } catch (error) {
      Alert.alert('Error', 'Impossible de se connecter au serveur');
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const authHeaders: Record<string, string> = adminToken
        ? { 'X-Admin-Token': adminToken }
        : {};

      // Load stats (legacy business: revenus, users actifs, votes)
      // + dashboard-stats (operationnel: queues, last_jobs, top5, alpha, category_breakdown)
      // En parallele, degradent gracieusement si l'un echoue.
      const [statsResult, dashboardResult] = await Promise.allSettled([
        fetch(API('/admin/stats'), { headers: authHeaders }),
        fetch(API('/admin/dashboard-stats'), { headers: authHeaders }),
      ]);

      if (statsResult.status === 'fulfilled' && statsResult.value.ok) {
        try {
          setStats(await statsResult.value.json());
        } catch { setStats(null); }
      } else {
        setStats(null);
      }

      if (dashboardResult.status === 'fulfilled' && dashboardResult.value.ok) {
        try {
          setDashboardStats(await dashboardResult.value.json());
        } catch { setDashboardStats(null); }
      } else {
        setDashboardStats(null);
      }

      // Load top people
      const peopleRes = await fetch(API('/people?limit=50'));
      if (peopleRes.ok) {
        const peopleData = await peopleRes.json();
        setTopPeople(peopleData);
        setSearchResults(peopleData);
      }

      // Load activity
      const activityRes = await fetch(API('/admin/activity/recent'), { headers: authHeaders });
      if (activityRes.ok) {
        const actData = await activityRes.json();
        setActivityData(actData);
      }

      // Load settings
      const settingsRes = await fetch(API('/admin/settings'), { headers: authHeaders });
      if (settingsRes.ok) {
        const settData = await settingsRes.json();
        setSettings(settData);
      }
    } catch (error) {
      console.error('Failed to load admin data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleSearch = useCallback(async () => {
    try {
      let url = '/admin/search?limit=50';
      if (searchQuery) url += `&q=${encodeURIComponent(searchQuery)}`;
      if (filterCategory) url += `&category=${filterCategory}`;
      if (filterSource) url += `&source=${filterSource}`;

      const res = await fetch(API(url));
      if (res.ok) {
        const results = await res.json();
        setSearchResults(results);
      }
    } catch (error) {
      console.error('Search error:', error);
    }
  }, [searchQuery, filterCategory, filterSource]);

  useEffect(() => {
    if (authenticated) {
      handleSearch();
    }
  }, [searchQuery, filterCategory, filterSource, authenticated, handleSearch]);

  // Charge le contenu du panel apres auto-auth via SecureStore (handleLogin appelle deja loadData en direct).
  useEffect(() => {
    if (authenticated) {
      loadData();
    }
  }, [authenticated, loadData]);

  const handleBoostDialog = (type: 'likes' | 'dislikes') => {
    if (!selectedPerson) {
      Alert.alert('Error', 'Please select a personality first');
      return;
    }

    const typeLabel = type === 'likes' ? 'Likes' : 'Dislikes';
    const emoji = type === 'likes' ? '👍' : '👎';

    if (Platform.OS === 'ios') {
      Alert.prompt(
        `${emoji} Add ${typeLabel}`,
        `Personality : ${selectedPerson.name}\n\nHow many ${typeLabel.toLowerCase()} ? (1-5000)`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Add',
            onPress: async (value) => {
              const amount = parseInt(value || '0');
              if (isNaN(amount) || amount < 1 || amount > 5000) {
                Alert.alert('Error', 'Entrez un nombre entre 1 et 5000');
                return;
              }
              await executeBoost(selectedPerson.id, amount, type);
            },
          },
        ],
        'plain-text',
        '100',
        'number-pad'
      );
    } else {
      Alert.alert(
        `${emoji} Add ${typeLabel}`,
        `Personality : ${selectedPerson.name}\n\nNumber of ${typeLabel.toLowerCase()} (1-5000) :`,
        [
          { text: 'Cancel', style: 'cancel' },
          { text: '100', onPress: () => executeBoost(selectedPerson.id, 100, type) },
          { text: '500', onPress: () => executeBoost(selectedPerson.id, 500, type) },
          { text: '1000', onPress: () => executeBoost(selectedPerson.id, 1000, type) },
          {
            text: 'Custom',
            onPress: () => {
              Alert.prompt(
                'Custom amount',
                'Entrez le nombre (1-5000) :',
                [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Add',
                    onPress: async (value) => {
                      const amount = parseInt(value || '0');
                      if (isNaN(amount) || amount < 1 || amount > 5000) {
                        Alert.alert('Error', 'Entrez un nombre entre 1 et 5000');
                        return;
                      }
                      await executeBoost(selectedPerson.id, amount, type);
                    },
                  },
                ],
                'plain-text'
              );
            },
          },
        ]
      );
    }
  };

  const executeBoost = async (personId: string, amount: number, type: 'likes' | 'dislikes') => {
    try {
      const res = await fetch(API('/admin/boost-votes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_id: personId, amount, type }),
      });

      if (res.ok) {
        const result = await res.json();
        Alert.alert('✅ Success !', `${amount} ${type} added !`, [{ text: 'OK' }]);
        loadData();
        setSelectedPerson(null);
      } else {
        Alert.alert('Error', 'Boost failed');
      }
    } catch (error) {
      Alert.alert('Error', 'Network error');
    }
  };

  const handleDeletePerson = (person: Person) => {
    Alert.alert(
      '⚠️ Delete',
      `Are you sure you want to delete "${person.name}" ?\n\nThis action cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await fetch(API(`/admin/person/${person.id}`), { method: 'DELETE' });
              if (res.ok) {
                Alert.alert('✅ Deleted', `"${person.name}" has been deleted`);
                loadData();
              } else {
                Alert.alert('Error', 'Deletion failed');
              }
            } catch (error) {
              Alert.alert('Error', 'Network error');
            }
          },
        },
      ]
    );
  };

  const handleResetPerson = (person: Person) => {
    Alert.alert(
      '🔄 Reset',
      `Reset "${person.name}" to a neutral score of 50 ?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          onPress: async () => {
            try {
              const res = await fetch(API(`/admin/person/${person.id}/reset`), { method: 'POST' });
              if (res.ok) {
                Alert.alert('✅ Reset', `"${person.name}" has been reset`);
                loadData();
              } else {
                Alert.alert('Error', 'Reset failed');
              }
            } catch (error) {
              Alert.alert('Error', 'Network error');
            }
          },
        },
      ]
    );
  };

  const handleSaveSettings = async () => {
    if (!settings) return;

    try {
      const res = await fetch(API('/admin/settings'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (res.ok) {
        Alert.alert('✅ Saved', 'Settings updated successfully');
      } else {
        Alert.alert('Error', 'Save failed');
      }
    } catch (error) {
      Alert.alert('Error', 'Network error');
    }
  };

  // ---------- Vague 4 — Candidats ----------
  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    setCandidatesError(null);
    try {
      const res = await adminFetch(API('/admin/user-creations'));
      if (res.ok) {
        const data: Candidate[] = await res.json();
        setCandidates(data);
      } else if (res.status !== 403) {
        setCandidatesError('Impossible de charger les candidats');
      }
    } catch (e) {
      setCandidatesError('Erreur reseau');
    } finally {
      setCandidatesLoading(false);
    }
  }, [adminFetch]);

  const loadPendingQueue = useCallback(async () => {
    setPendingLoading(true);
    setPendingError(null);
    try {
      const res = await adminFetch(API('/admin/pending-candidate-queue'));
      if (res.ok) {
        const data: PendingQueueEntry[] = await res.json();
        setPendingQueue(data);
      } else if (res.status !== 403) {
        setPendingError('Impossible de charger la file en attente');
      }
    } catch (e) {
      setPendingError('Erreur reseau');
    } finally {
      setPendingLoading(false);
    }
  }, [adminFetch]);

  const loadCandidatesAll = useCallback(() => {
    loadPendingQueue();
    loadCandidates();
  }, [loadPendingQueue, loadCandidates]);

  // Auto-fetch quand on entre dans l'onglet candidates (et au refresh global)
  useEffect(() => {
    if (authenticated && currentTab === 'candidates') {
      loadCandidatesAll();
    }
  }, [authenticated, currentTab, loadCandidatesAll]);

  // ---------- Actions zone 1 (pending queue) ----------
  const pendingForceValidate = useCallback((entry: PendingQueueEntry) => {
    Alert.alert(
      'Valider maintenant',
      `Publier "${entry.name}" immediatement (avant l'echeance 24h) ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Valider maintenant',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/candidate-queue/${entry.id}/force-validate`), {
                method: 'POST',
              });
              if (res.ok) {
                const data = await res.json();
                if (data?.success) {
                  setPendingQueue((prev) => prev.filter((e) => e.id !== entry.id));
                  Alert.alert('Publie', `${entry.name} a ete publie (PI ${Math.round(data.initial_pi ?? 0)}).`);
                  // Refresh la zone 2 pour voir le nouvel arrivant
                  loadCandidates();
                } else {
                  const msg = data?.error_message || `Validation impossible: ${data?.error_code || 'unknown'}`;
                  Alert.alert('Echec', msg);
                  // Le backend a peut-etre change le statut (rejected/duplicate), refresh queue
                  loadPendingQueue();
                }
              } else {
                let msg = 'Echec de la validation';
                try {
                  const data = await res.json();
                  if (data?.detail) msg = String(data.detail);
                } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            }
          },
        },
      ]
    );
  }, [adminFetch, loadCandidates, loadPendingQueue]);

  const pendingReject = useCallback((entry: PendingQueueEntry) => {
    Alert.alert(
      'Refuser',
      `Refuser "${entry.name}" ? Cette action ajoute le slug a la blocklist permanente — la meme soumission ne pourra plus etre re-mise en file.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Refuser',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/candidate-queue/${entry.id}/reject`), {
                method: 'POST',
              });
              if (res.ok) {
                setPendingQueue((prev) => prev.filter((e) => e.id !== entry.id));
                Alert.alert('Refuse', `${entry.name} a ete refuse et ajoute a la blocklist.`);
              } else {
                let msg = 'Echec du refus';
                try {
                  const data = await res.json();
                  if (data?.detail) msg = String(data.detail);
                } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            }
          },
        },
      ]
    );
  }, [adminFetch]);

  const candidateValidate = useCallback((candidate: Candidate) => {
    Alert.alert(
      'Valider et publier',
      `Publier "${candidate.name}" et le rendre visible dans les classements ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Valider',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/user-creations/${candidate.id}/validate`), {
                method: 'POST',
              });
              if (res.ok) {
                setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));
                Alert.alert('Publie', `${candidate.name} a ete publie.`);
              } else {
                let msg = 'Echec de la validation';
                try {
                  const data = await res.json();
                  if (data?.detail) msg = String(data.detail);
                } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            }
          },
        },
      ]
    );
  }, [adminFetch]);

  const candidateUpdateCategory = useCallback((candidate: Candidate) => {
    const buttons = CANDIDATE_CATEGORIES.map((cat) => ({
      text: cat === candidate.category ? `${cat} (actuel)` : cat,
      onPress: async () => {
        if (cat === candidate.category) return;
        try {
          const res = await adminFetch(API(`/admin/user-creations/${candidate.id}/update-category`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: cat }),
          });
          if (res.ok) {
            setCandidates((prev) =>
              prev.map((c) => (c.id === candidate.id ? { ...c, category: cat } : c))
            );
            Alert.alert('Categorie mise a jour', `${candidate.name} -> ${cat}`);
          } else {
            let msg = 'Echec de la mise a jour';
            try {
              const data = await res.json();
              if (data?.detail) msg = String(data.detail);
            } catch {}
            Alert.alert('Erreur', msg);
          }
        } catch {
          Alert.alert('Erreur', 'Erreur reseau');
        }
      },
    }));
    Alert.alert(
      'Corriger la categorie',
      `${candidate.name}\n\nChoisissez la nouvelle categorie :`,
      [...buttons, { text: 'Annuler', style: 'cancel' as const }]
    );
  }, [adminFetch]);

  const candidateDeleteBlock = useCallback((candidate: Candidate) => {
    Alert.alert(
      'Refuser et bloquer',
      `Cette action ajoute "${candidate.name}" a la blocklist permanente. Vous ne pourrez plus le soumettre.\n\nConfirmer ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Refuser + bloquer',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/user-creations/${candidate.id}/delete-block`), {
                method: 'POST',
              });
              if (res.ok) {
                setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));
                Alert.alert('Refuse et bloque', `${candidate.name} a ete refuse et ajoute a la blocklist.`);
              } else {
                let msg = 'Echec du refus';
                try {
                  const data = await res.json();
                  if (data?.detail) msg = String(data.detail);
                } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            }
          },
        },
      ]
    );
  }, [adminFetch]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadData();
  }, [loadData]);

  const handleRefreshTrends = async () => {
    Alert.alert(
      '🔥 Refresh Google Trends',
      'This will fetch trending personalities from Google Trends. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Refresh',
          onPress: async () => {
            try {
              const res = await fetch(API('/admin/refresh-trends'), { method: 'POST' });
              if (res.ok) {
                const result = await res.json();
                Alert.alert(
                  '✅ Trends Refreshed !',
                  `${result.added} new personalities added\n${result.updated} updated as trending`,
                  [{ text: 'OK' }]
                );
                loadData();
              } else {
                Alert.alert('Error', 'Refresh failed');
              }
            } catch (error) {
              Alert.alert('Error', 'Network error');
            }
          },
        },
      ]
    );
  };

  if (bootstrapping) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loginContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
          <Text style={[styles.loginSubtitle, { marginTop: 16 }]}>Reprise de session...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!authenticated) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loginContainer}>
          <Ionicons name="lock-closed" size={64} color={PALETTE.gold} />
          <Text style={styles.loginTitle}>Admin Access</Text>
          <Text style={styles.loginSubtitle}>Secret gesture detected</Text>
          
          <TextInput
            style={styles.passwordInput}
            placeholder="Mot de passe admin"
            placeholderTextColor={PALETTE.subtext}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            returnKeyType="done"
            onSubmitEditing={handleLogin}
          />
          
          <TouchableOpacity style={styles.loginButton} onPress={handleLogin}>
            <Text style={styles.loginButtonText}>Se connecter</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>Retour</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBack} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Text style={{ color: PALETTE.text, fontSize: 24, fontWeight: '300' }}>{"<"}</Text>
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>🔧 Admin</Text>
        </View>
        <TouchableOpacity onPress={loadData} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }} style={{ marginRight: 16 }}>
          <Ionicons name="refresh" size={24} color={PALETTE.gold} />
        </TouchableOpacity>
        <TouchableOpacity onPress={handleLogout} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="log-out-outline" size={24} color={PALETTE.subtext} />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar} contentContainerStyle={{ paddingRight: 16 }}>
        {TAB_ORDER.map((t) => {
          const meta = TAB_LABELS[t];
          const active = currentTab === t;
          return (
            <TouchableOpacity
              key={t}
              style={[styles.tab, active && styles.tabActive]}
              onPress={() => setCurrentTab(t)}
            >
              <Ionicons name={meta.icon} size={20} color={active ? '#000' : PALETTE.text} />
              <Text style={[styles.tabText, active && styles.tabTextActive]}>{meta.label}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.gold} />
        }
      >
        {loading && !refreshing ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={PALETTE.gold} />
          </View>
        ) : (
          <>
            {currentTab === 'stats' && (
              <DashboardTab
                stats={stats}
                dashboardStats={dashboardStats}
                topPeople={topPeople}
                selectedPerson={selectedPerson}
                onSelectPerson={setSelectedPerson}
                onBoost={handleBoostDialog}
                onRefreshTrends={handleRefreshTrends}
              />
            )}

            {currentTab === 'activity' && activityData && (
              <ActivityTab activityData={activityData} />
            )}

            {currentTab === 'candidates' && (
              <CandidatesSection
                pendingQueue={pendingQueue}
                pendingLoading={pendingLoading}
                pendingError={pendingError}
                onPendingRefresh={loadPendingQueue}
                onForceValidate={pendingForceValidate}
                onPendingReject={pendingReject}
                candidates={candidates}
                candidatesLoading={candidatesLoading}
                candidatesError={candidatesError}
                publishedCollapsed={publishedCollapsed}
                onTogglePublishedCollapsed={() => setPublishedCollapsed((v) => !v)}
                onCandidatesRefresh={loadCandidates}
                onValidate={candidateValidate}
                onUpdateCategory={candidateUpdateCategory}
                onDeleteBlock={candidateDeleteBlock}
              />
            )}

            {currentTab === 'outsider_reports' && (
              <PlaceholderSection tab="outsider_reports" />
            )}

            {currentTab === 'manual_add' && (
              <PlaceholderSection tab="manual_add" />
            )}

            {currentTab === 'deceased' && (
              <PlaceholderSection tab="deceased" />
            )}

            {currentTab === 'categories' && (
              <PlaceholderSection tab="categories" />
            )}

            {currentTab === 'moderation' && (
              <ModerationTab
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                filterCategory={filterCategory}
                onCategoryChange={setFilterCategory}
                filterSource={filterSource}
                onSourceChange={setFilterSource}
                searchResults={searchResults}
                onDelete={handleDeletePerson}
                onReset={handleResetPerson}
              />
            )}

            {currentTab === 'settings' && settings && (
              <SettingsTab settings={settings} onSettingsChange={setSettings} onSave={handleSaveSettings} />
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

// Dashboard Tab Component — Vague 4 sous-tache 6 : enrichi avec /admin/dashboard-stats
function DashboardTab({ stats, dashboardStats, topPeople, selectedPerson, onSelectPerson, onBoost, onRefreshTrends }: any) {
  const ds: DashboardStats | null = dashboardStats;
  const noStats = !stats && !ds;
  return (
    <View>
      {noStats && (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.statLabel}>Statistiques indisponibles</Text>
          </View>
        </View>
      )}

      {/* ============ Section 1 — KPI business (legacy /admin/stats) ============ */}
      {stats && (
        <View style={styles.statsGrid}>
          <View style={[styles.statCard, { borderColor: PALETTE.gold }]}>
            <Ionicons name="people" size={32} color={PALETTE.gold} />
            <Text style={styles.statNumber}>{stats.total_people}</Text>
            <Text style={styles.statLabel}>Total profils</Text>
          </View>

          <View style={[styles.statCard, { borderColor: PALETTE.green }]}>
            <Ionicons name="bar-chart" size={32} color={PALETTE.green} />
            <Text style={styles.statNumber}>{stats.total_votes}</Text>
            <Text style={styles.statLabel}>Votes totaux</Text>
          </View>

          <View style={[styles.statCard, { borderColor: '#00D8FF' }]}>
            <Ionicons name="person" size={32} color="#00D8FF" />
            <Text style={styles.statNumber}>{stats.active_users_24h}</Text>
            <Text style={styles.statLabel}>Actifs 24h</Text>
          </View>

          <View style={[styles.statCard, { borderColor: '#FF4757' }]}>
            <Ionicons name="cash" size={32} color="#FF4757" />
            <Text style={styles.statNumber}>{stats.revenue_24h}€</Text>
            <Text style={styles.statLabel}>Revenus 24h</Text>
          </View>
        </View>
      )}

      {/* ============ Section 2 — Engagement & revenus (champs etendus /admin/stats) ============ */}
      {stats && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>📈 Engagement & revenus</Text>
          <View style={[styles.statsGrid, { padding: 0 }]}>
            <View style={[styles.statCard, { borderColor: '#00D8FF' }]}>
              <Ionicons name="people-outline" size={28} color="#00D8FF" />
              <Text style={styles.statNumber}>{stats.active_users_7d ?? '—'}</Text>
              <Text style={styles.statLabel}>Actifs 7 jours</Text>
            </View>

            <View style={[styles.statCard, { borderColor: '#00D8FF' }]}>
              <Ionicons name="calendar-outline" size={28} color="#00D8FF" />
              <Text style={styles.statNumber}>{stats.active_users_30d ?? '—'}</Text>
              <Text style={styles.statLabel}>Actifs 30 jours</Text>
            </View>

            <View style={[styles.statCard, { borderColor: PALETTE.gold }]}>
              <Ionicons name="add-circle-outline" size={28} color={PALETTE.gold} />
              <Text style={styles.statNumber}>{stats.new_people_24h}</Text>
              <Text style={styles.statLabel}>Nouveaux profils 24h</Text>
            </View>

            <View style={[styles.statCard, { borderColor: '#FF4757' }]}>
              <Ionicons name="wallet-outline" size={28} color="#FF4757" />
              <Text style={styles.statNumber}>{stats.revenue_total_lifetime ?? '—'}€</Text>
              <Text style={styles.statLabel}>Revenus a vie</Text>
            </View>
          </View>
        </View>
      )}

      {/* ============ Section 3 — Files d'attente admin (dashboard-stats.queues) ============ */}
      {ds && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>⏳ Files d'attente admin</Text>
          <View style={[styles.statsGrid, { padding: 0 }]}>
            <View style={[styles.statCard, { borderColor: PALETTE.gold }]}>
              <Ionicons name="people-circle-outline" size={28} color={PALETTE.gold} />
              <Text style={styles.statNumber}>{ds.queues.pending_candidates}</Text>
              <Text style={styles.statLabel}>Candidats en attente</Text>
            </View>

            <View style={[styles.statCard, { borderColor: PALETTE.accent }]}>
              <Ionicons name="skull-outline" size={28} color={PALETTE.accent} />
              <Text style={styles.statNumber}>{ds.queues.pending_deceased}</Text>
              <Text style={styles.statLabel}>Deces a verifier</Text>
            </View>

            <View style={[styles.statCard, { borderColor: PALETTE.gold }]}>
              <Ionicons name="pricetags-outline" size={28} color={PALETTE.gold} />
              <Text style={styles.statNumber}>{ds.queues.pending_category_reviews}</Text>
              <Text style={styles.statLabel}>Revues categorie</Text>
            </View>
          </View>
        </View>
      )}

      {/* ============ Section 4 — Top 5 popularite (dashboard-stats.top5) ============ */}
      {ds && ds.top5 && ds.top5.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🏆 Top 5 popularite</Text>
          <View style={styles.card}>
            {ds.top5.map((p, idx) => (
              <View key={`${idx}-${p.name}`} style={styles.dashTopRow}>
                <Text style={styles.dashTopRank}>{idx + 1}.</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.dashTopName}>{p.name}</Text>
                  <Text style={styles.dashTopMeta}>{categoryFR(p.category)}</Text>
                </View>
                <Text style={styles.dashTopScore}>{p.popularoo_index.toFixed(1)}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* ============ Section 5 — Repartition par categorie (dashboard-stats.category_breakdown) ============ */}
      {ds && ds.category_breakdown && Object.keys(ds.category_breakdown).length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🎯 Repartition par categorie</Text>
          <View style={styles.card}>
            <View style={styles.dashCategoryGrid}>
              {Object.entries(ds.category_breakdown).map(([cat, count]) => (
                <View key={cat} style={styles.dashCategoryChip}>
                  <Text style={styles.dashCategoryCount}>{count}</Text>
                  <Text style={styles.dashCategoryLabel}>{categoryFR(cat)}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* ============ Section 6 — Sante pipeline (dashboard-stats: total_celebrities + alpha + last_jobs) ============ */}
      {ds && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>🔧 Sante pipeline</Text>
          <View style={styles.card}>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Celebrites validees (hors outsiders)</Text>
              <Text style={styles.dashPipelineValue}>{ds.total_celebrities}</Text>
            </View>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Alpha (popularoo_index)</Text>
              <Text style={styles.dashPipelineValue}>{ds.alpha?.toFixed(3) ?? '—'}</Text>
            </View>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Scores externes</Text>
              <Text style={styles.dashPipelineValue}>{formatDateFR(ds.last_jobs.external_scores)}</Text>
            </View>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Detection candidats</Text>
              <Text style={styles.dashPipelineValue}>{formatDateFR(ds.last_jobs.candidate_detection)}</Text>
            </View>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Verif deces (top 50)</Text>
              <Text style={styles.dashPipelineValue}>{formatDateFR(ds.last_jobs.deceased_check_top50)}</Text>
            </View>
            <View style={styles.dashPipelineRow}>
              <Text style={styles.dashPipelineLabel}>Verif deces (complet)</Text>
              <Text style={styles.dashPipelineValue}>{formatDateFR(ds.last_jobs.deceased_check_all)}</Text>
            </View>
            <View style={[styles.dashPipelineRow, { borderBottomWidth: 0 }]}>
              <Text style={styles.dashPipelineLabel}>Revue categories</Text>
              <Text style={styles.dashPipelineValue}>{formatDateFR(ds.last_jobs.category_review)}</Text>
            </View>
          </View>
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🔥 Google Trends</Text>
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Refresh trending personalities</Text>
          <TouchableOpacity style={styles.refreshTrendsButton} onPress={onRefreshTrends}>
            <Ionicons name="trending-up" size={24} color="#000" />
            <Text style={styles.refreshTrendsButtonText}>Refresh Google Trends</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🚀 Booster</Text>
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Select a personality</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.personSelector}>
            {topPeople.slice(0, 10).map((person: Person) => (
              <TouchableOpacity
                key={person.id}
                style={[
                  styles.personChip,
                  selectedPerson?.id === person.id && styles.personChipSelected,
                ]}
                onPress={() => onSelectPerson(person)}
              >
                <Text style={styles.personChipText} numberOfLines={1}>
                  {person.name}
                </Text>
                <Text style={styles.personChipScore}>{person.score}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {selectedPerson && (
            <>
              <View style={styles.selectedPerson}>
                <Text style={styles.selectedPersonName}>✓ {selectedPerson.name}</Text>
                <Text style={styles.selectedPersonStats}>
                  {selectedPerson.likes} likes • {selectedPerson.dislikes} dislikes
                </Text>
              </View>

              <Text style={styles.cardLabel}>Actions de boost</Text>
              
              <View style={styles.boostActionsRow}>
                <TouchableOpacity style={styles.boostActionBtn} onPress={() => onBoost('likes')}>
                  <Ionicons name="thumbs-up" size={24} color={PALETTE.green} />
                  <Text style={styles.boostActionTitle}>Add Likes</Text>
                  <Text style={styles.boostActionSubtitle}>1-5000 votes</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.boostActionBtn} onPress={() => onBoost('dislikes')}>
                  <Ionicons name="thumbs-down" size={24} color={PALETTE.accent} />
                  <Text style={styles.boostActionTitle}>Add Dislikes</Text>
                  <Text style={styles.boostActionSubtitle}>1-5000 votes</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      </View>
    </View>
  );
}

// Moderation Tab Component
function ModerationTab({
  searchQuery,
  onSearchChange,
  filterCategory,
  onCategoryChange,
  filterSource,
  onSourceChange,
  searchResults,
  onDelete,
  onReset,
}: any) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>🔍 Advanced Search</Text>
      
      <View style={styles.card}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search by name..."
          placeholderTextColor={PALETTE.subtext}
          value={searchQuery}
          onChangeText={onSearchChange}
        />

        <View style={styles.filterRow}>
          <View style={{ flex: 1, marginRight: 8 }}>
            <Text style={styles.filterLabel}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {['', 'politics', 'culture', 'business', 'sport', 'other'].map((cat) => (
                <TouchableOpacity
                  key={cat}
                  style={[styles.filterChip, filterCategory === cat && styles.filterChipActive]}
                  onPress={() => onCategoryChange(cat)}
                >
                  <Text style={[styles.filterChipText, filterCategory === cat && { color: '#000' }]}>
                    {cat || 'Tous'}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          <View style={{ flex: 1, marginLeft: 8 }}>
            <Text style={styles.filterLabel}>Source</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {['', 'seed', 'user_added', 'self_boosted'].map((src) => (
                <TouchableOpacity
                  key={src}
                  style={[styles.filterChip, filterSource === src && styles.filterChipActive]}
                  onPress={() => onSourceChange(src)}
                >
                  <Text style={[styles.filterChipText, filterSource === src && { color: '#000' }]}>
                    {src === '' ? 'Tous' : src === 'seed' ? '⭐' : src === 'user_added' ? '➕' : '👤'}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>

        <Text style={styles.resultsCount}>{searchResults.length} result(s)</Text>

        {searchResults.map((person: Person) => (
          <View key={person.id} style={styles.moderationRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.moderationName}>{person.name}</Text>
              <Text style={styles.moderationStats}>
                Score {person.score} • {person.total_votes} votes • {person.source}
              </Text>
            </View>

            <TouchableOpacity style={styles.actionBtn} onPress={() => onReset(person)}>
              <Ionicons name="refresh" size={20} color={PALETTE.gold} />
            </TouchableOpacity>

            <TouchableOpacity style={styles.actionBtn} onPress={() => onDelete(person)}>
              <Ionicons name="trash" size={20} color={PALETTE.accent} />
            </TouchableOpacity>
          </View>
        ))}
      </View>
    </View>
  );
}

// Activity Tab Component
function ActivityTab({ activityData }: { activityData: ActivityData }) {
  return (
    <View>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>👤 Nouvelles Personalitys</Text>
        <View style={styles.card}>
          {activityData.recent_people.slice(0, 10).map((item: any, index: number) => (
            <View key={index} style={styles.activityRow}>
              <Text style={styles.activityIcon}>
                {item.source === 'seed' ? '⭐' : item.source === 'user_added' ? '➕' : '👤'}
              </Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.activityName}>{item.name}</Text>
                <Text style={styles.activityTime}>
                  {new Date(item.created_at).toLocaleString('fr-FR')}
                </Text>
              </View>
              <Text style={styles.activityScore}>{item.score}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>💰 Recent Purchases</Text>
        <View style={styles.card}>
          {activityData.recent_purchases.slice(0, 10).map((item: any, index: number) => (
            <View key={index} style={styles.activityRow}>
              <Ionicons name="cart" size={20} color={PALETTE.green} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.activityName}>{item.amount} credits</Text>
                <Text style={styles.activityTime}>
                  {new Date(item.timestamp).toLocaleString('fr-FR')}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>⚡ Recent Usage</Text>
        <View style={styles.card}>
          {activityData.recent_uses.slice(0, 10).map((item: any, index: number) => (
            <View key={index} style={styles.activityRow}>
              <Ionicons name="flash" size={20} color={PALETTE.gold} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.activityName}>{item.description}</Text>
                <Text style={styles.activityTime}>
                  {new Date(item.timestamp).toLocaleString('fr-FR')}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

// Settings Tab Component
function SettingsTab({ settings, onSettingsChange, onSave }: any) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>⚙️ Settings de l'App</Text>
      
      <View style={styles.card}>
        <View style={styles.settingRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.settingLabel}>Autoriser ajouts utilisateurs</Text>
            <Text style={styles.settingDesc}>Users can add personalities</Text>
          </View>
          <Switch
            value={settings.allow_user_additions}
            onValueChange={(v) => onSettingsChange({ ...settings, allow_user_additions: v })}
            trackColor={{ true: PALETTE.green, false: PALETTE.border }}
            thumbColor="#fff"
          />
        </View>

        <View style={styles.settingRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.settingLabel}>Mode maintenance</Text>
            <Text style={styles.settingDesc}>Disables access to the app</Text>
          </View>
          <Switch
            value={settings.maintenance_mode}
            onValueChange={(v) => onSettingsChange({ ...settings, maintenance_mode: v })}
            trackColor={{ true: PALETTE.accent, false: PALETTE.border }}
            thumbColor="#fff"
          />
        </View>

        <Text style={styles.cardLabel}>Prix des Boosters</Text>

        <View style={styles.settingInputRow}>
          <Text style={styles.settingInputLabel}>Booster (€)</Text>
          <TextInput
            style={styles.settingInput}
            value={String(settings.booster_price)}
            onChangeText={(v) => onSettingsChange({ ...settings, booster_price: parseFloat(v) || 0 })}
            keyboardType="decimal-pad"
          />
        </View>

        <View style={styles.settingInputRow}>
          <Text style={styles.settingInputLabel}>Super Booster (€)</Text>
          <TextInput
            style={styles.settingInput}
            value={String(settings.super_booster_price)}
            onChangeText={(v) => onSettingsChange({ ...settings, super_booster_price: parseFloat(v) || 0 })}
            keyboardType="decimal-pad"
          />
        </View>

        <Text style={styles.cardLabel}>Votes par Booster</Text>

        <View style={styles.settingInputRow}>
          <Text style={styles.settingInputLabel}>Booster (votes)</Text>
          <TextInput
            style={styles.settingInput}
            value={String(settings.booster_votes)}
            onChangeText={(v) => onSettingsChange({ ...settings, booster_votes: parseInt(v) || 0 })}
            keyboardType="number-pad"
          />
        </View>

        <View style={styles.settingInputRow}>
          <Text style={styles.settingInputLabel}>Super Booster (votes)</Text>
          <TextInput
            style={styles.settingInput}
            value={String(settings.super_booster_votes)}
            onChangeText={(v) => onSettingsChange({ ...settings, super_booster_votes: parseInt(v) || 0 })}
            keyboardType="number-pad"
          />
        </View>

        <TouchableOpacity style={styles.saveButton} onPress={onSave}>
          <Ionicons name="save" size={20} color="#000" />
          <Text style={styles.saveButtonText}>Enregistrer les Settings</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ---------- Composants partages (factorises pour Lot 4) ----------

type ReviewVariant = 'primary' | 'danger' | 'neutral';

export interface ReviewListAction {
  label: string;
  onPress: () => void;
  variant?: ReviewVariant;
  icon?: keyof typeof Ionicons.glyphMap;
  disabled?: boolean;
}

export interface ReviewListProps<T> {
  title?: string;
  data: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  actions?: (item: T, index: number) => ReviewListAction[];
  keyExtractor?: (item: T, index: number) => string;
  emptyText?: string;
  headerAction?: ReviewListAction;
}

export function ReviewList<T>({
  title,
  data,
  renderItem,
  actions,
  keyExtractor,
  emptyText = 'Aucun element',
  headerAction,
}: ReviewListProps<T>) {
  return (
    <View style={styles.section}>
      {(title || headerAction) && (
        <View style={styles.reviewListHeader}>
          {title ? <Text style={styles.sectionTitle}>{title}</Text> : <View />}
          {headerAction && (
            <TouchableOpacity
              style={[styles.reviewActionBtn, reviewVariantStyle(headerAction.variant)]}
              onPress={headerAction.onPress}
              disabled={headerAction.disabled}
            >
              {headerAction.icon && (
                <Ionicons name={headerAction.icon} size={16} color={reviewVariantTextColor(headerAction.variant)} />
              )}
              <Text style={[styles.reviewActionBtnText, { color: reviewVariantTextColor(headerAction.variant) }]}>
                {headerAction.label}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {data.length === 0 ? (
        <View style={styles.card}>
          <Text style={styles.reviewEmpty}>{emptyText}</Text>
        </View>
      ) : (
        data.map((item, index) => {
          const key = keyExtractor ? keyExtractor(item, index) : String(index);
          const itemActions = actions ? actions(item, index) : [];
          return (
            <View key={key} style={[styles.card, { marginBottom: 12 }]}>
              {renderItem(item, index)}
              {itemActions.length > 0 && (
                <View style={styles.reviewActionsRow}>
                  {itemActions.map((a, ai) => (
                    <TouchableOpacity
                      key={`${key}-${ai}`}
                      style={[styles.reviewActionBtn, reviewVariantStyle(a.variant), a.disabled && { opacity: 0.5 }]}
                      onPress={a.onPress}
                      disabled={a.disabled}
                    >
                      {a.icon && (
                        <Ionicons name={a.icon} size={16} color={reviewVariantTextColor(a.variant)} />
                      )}
                      <Text style={[styles.reviewActionBtnText, { color: reviewVariantTextColor(a.variant) }]}>
                        {a.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          );
        })
      )}
    </View>
  );
}

function reviewVariantStyle(v?: ReviewVariant) {
  switch (v) {
    case 'danger':  return { backgroundColor: PALETTE.accent, borderColor: PALETTE.accent };
    case 'neutral': return { backgroundColor: PALETTE.bg, borderColor: PALETTE.border };
    case 'primary':
    default:        return { backgroundColor: PALETTE.gold, borderColor: PALETTE.gold };
  }
}

function reviewVariantTextColor(v?: ReviewVariant) {
  if (v === 'danger') return '#FFF';
  if (v === 'neutral') return PALETTE.text;
  return '#000';
}

export interface AdminCardPerson {
  id?: string;
  name: string;
  score?: number;
  likes?: number;
  dislikes?: number;
  total_votes?: number;
  source?: string;
  category?: string;
  avatar_initials?: string;
  avatar_color?: string;
  created_at?: string;
}

export function AdminCard({
  person,
  rightSlot,
  subline,
}: {
  person: AdminCardPerson;
  rightSlot?: React.ReactNode;
  subline?: string;
}) {
  const initials = person.avatar_initials || (person.name || '?').slice(0, 2).toUpperCase();
  const color = person.avatar_color || PALETTE.border;
  return (
    <View style={styles.adminCardRow}>
      <View style={[styles.adminCardAvatar, { backgroundColor: color }]}>
        <Text style={styles.adminCardAvatarText}>{initials}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.adminCardName} numberOfLines={1}>{person.name}</Text>
        <Text style={styles.adminCardMeta} numberOfLines={1}>
          {typeof person.score === 'number' ? `PI ${Math.round(person.score)}` : null}
          {typeof person.total_votes === 'number' ? `${typeof person.score === 'number' ? ' • ' : ''}${person.total_votes} votes` : null}
          {person.source ? ` • ${person.source}` : null}
          {person.category ? ` • ${person.category}` : null}
        </Text>
        {subline ? <Text style={styles.adminCardSubline} numberOfLines={2}>{subline}</Text> : null}
      </View>
      {rightSlot}
    </View>
  );
}

// ---------- Vague 4 — Section Candidats ----------

function formatRelativeShort(iso: string | null): string {
  if (!iso) return '';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diffMs = Date.now() - ts;
  const absMs = Math.abs(diffMs);
  const future = diffMs < 0;
  const minutes = Math.round(absMs / 60000);
  if (minutes < 1) return future ? 'imminent' : "a l'instant";
  if (minutes < 60) return future ? `dans ${minutes} min` : `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return future ? `dans ${hours}h` : `il y a ${hours}h`;
  const days = Math.round(hours / 24);
  return future ? `dans ${days}j` : `il y a ${days}j`;
}

// Vague 4 sous-tache 6 — Format date FR : relatif si < 24h, absolu sinon ("14 mai a 21h30").
const FR_MONTHS = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'aout', 'septembre', 'octobre', 'novembre', 'decembre'];
function formatDateFR(iso: string | null): string {
  if (!iso) return 'Jamais execute';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return 'Date inconnue';
  const diffMs = Date.now() - ts;
  if (diffMs >= 0 && diffMs < 24 * 3600 * 1000) {
    return formatRelativeShort(iso);
  }
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getDate()} ${FR_MONTHS[d.getMonth()]} a ${hh}h${mm}`;
}

function categoryFR(cat: string | null | undefined): string {
  switch (cat) {
    case 'politics': return 'Politique';
    case 'culture': return 'Culture';
    case 'sport': return 'Sport';
    case 'business': return 'Business';
    case 'influencer': return 'Influenceur';
    case 'other': return 'Autre';
    default: return cat ? cat.charAt(0).toUpperCase() + cat.slice(1) : 'Autre';
  }
}

interface CandidatesSectionProps {
  // Zone 1 — file en attente (24h)
  pendingQueue: PendingQueueEntry[];
  pendingLoading: boolean;
  pendingError: string | null;
  onPendingRefresh: () => void;
  onForceValidate: (e: PendingQueueEntry) => void;
  onPendingReject: (e: PendingQueueEntry) => void;
  // Zone 2 — publies recents
  candidates: Candidate[];
  candidatesLoading: boolean;
  candidatesError: string | null;
  publishedCollapsed: boolean;
  onTogglePublishedCollapsed: () => void;
  onCandidatesRefresh: () => void;
  onValidate: (c: Candidate) => void;
  onUpdateCategory: (c: Candidate) => void;
  onDeleteBlock: (c: Candidate) => void;
}

function CandidatesSection({
  pendingQueue,
  pendingLoading,
  pendingError,
  onPendingRefresh,
  onForceValidate,
  onPendingReject,
  candidates,
  candidatesLoading,
  candidatesError,
  publishedCollapsed,
  onTogglePublishedCollapsed,
  onCandidatesRefresh,
  onValidate,
  onUpdateCategory,
  onDeleteBlock,
}: CandidatesSectionProps) {
  return (
    <View>
      {/* ============ Zone 1 — En attente de validation (24h) ============ */}
      <View style={[styles.candidatesPendingZone, styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>⏳ En attente de validation (24h)</Text>
            <Text style={styles.candidatesHeaderCount}>
              {pendingQueue.length} soumission{pendingQueue.length > 1 ? 's' : ''} en file
            </Text>
          </View>
          <TouchableOpacity
            onPress={onPendingRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>
        <Text style={styles.candidatesHelpText}>
          Ces celebrites seront publiees automatiquement a l'echeance. Vous pouvez intervenir avant si besoin.
        </Text>
      </View>

      {pendingLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : pendingError ? (
        <View style={[styles.candidatesPendingZone, styles.section]}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{pendingError}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onPendingRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View style={styles.candidatesPendingZone}>
          <ReviewList<PendingQueueEntry>
            data={pendingQueue}
            keyExtractor={(e) => e.id}
            emptyText="Aucune soumission en attente"
            renderItem={(e) => {
              const requestedRel = formatRelativeShort(e.requested_at);
              const processRel = formatRelativeShort(e.process_after);
              const isFutureDeadline = e.process_after
                ? Date.parse(e.process_after) > Date.now()
                : false;
              const deadlineLabel = isFutureDeadline
                ? processRel
                : processRel
                  ? `echeance: ${processRel}`
                  : '';
              const subline = e.last_error
                ? `Tentative precedente echouee: ${e.last_error}`
                : undefined;
              return (
                <AdminCard
                  person={{
                    id: e.id,
                    name: e.name,
                  }}
                  subline={subline}
                  rightSlot={
                    <View style={{ alignItems: 'flex-end' }}>
                      {!!requestedRel && (
                        <Text style={styles.candidatesDateText}>Demande {requestedRel}</Text>
                      )}
                      {!!deadlineLabel && (
                        <Text style={styles.candidatesDeadlineText}>{deadlineLabel}</Text>
                      )}
                      {e.pending_vote_value === 1 && (
                        <Text style={styles.candidatesImplicitLike}>👍 like implicite</Text>
                      )}
                    </View>
                  }
                />
              );
            }}
            actions={(e) => [
              {
                label: 'Valider maintenant',
                icon: 'flash',
                variant: 'primary',
                onPress: () => onForceValidate(e),
              },
              {
                label: 'Refuser',
                icon: 'ban',
                variant: 'danger',
                onPress: () => onPendingReject(e),
              },
            ]}
          />
        </View>
      )}

      {/* ============ Zone 2 — Publies recents (72h) ============ */}
      <View style={[styles.section, { paddingBottom: 0 }]}>
        <TouchableOpacity
          onPress={onTogglePublishedCollapsed}
          activeOpacity={0.7}
          style={styles.candidatesHeaderRow}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>
              {publishedCollapsed ? '▸' : '▾'} Publies recents (72h)
            </Text>
            <Text style={styles.candidatesHeaderCount}>
              {candidates.length} profil{candidates.length > 1 ? 's' : ''} cree{candidates.length > 1 ? 's' : ''}
            </Text>
          </View>
          <TouchableOpacity
            onPress={onCandidatesRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </TouchableOpacity>
      </View>

      {publishedCollapsed ? null : candidatesLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : candidatesError ? (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{candidatesError}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onCandidatesRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewList<Candidate>
          data={candidates}
          keyExtractor={(c) => c.id}
          emptyText="Aucun profil publie (72h)"
          renderItem={(c) => {
            const isPending = !c.visible_in_rankings;
            const wikiScore = Math.round(c.popularity_external_score);
            const subline = c.wiki_description
              ? c.wiki_description.length > 120
                ? `${c.wiki_description.slice(0, 117)}...`
                : c.wiki_description
              : undefined;
            return (
              <View style={!isPending ? undefined : { opacity: 0.85 }}>
                <AdminCard
                  person={{
                    id: c.id,
                    name: c.name,
                    category: c.category,
                  }}
                  subline={subline}
                  rightSlot={
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.candidatesWikiScore}>Wiki {wikiScore}</Text>
                      <Text style={styles.candidatesDateText}>{formatRelativeShort(c.created_at)}</Text>
                      {!isPending && (
                        <Text style={styles.candidatesPublishedTag}>Publie</Text>
                      )}
                    </View>
                  }
                />
              </View>
            );
          }}
          actions={(c) => [
            {
              label: 'Valider',
              icon: 'checkmark-circle',
              variant: 'primary',
              onPress: () => onValidate(c),
              disabled: c.visible_in_rankings,
            },
            {
              label: 'Categorie',
              icon: 'pricetag',
              variant: 'neutral',
              onPress: () => onUpdateCategory(c),
            },
            {
              label: 'Refuser + bloquer',
              icon: 'ban',
              variant: 'danger',
              onPress: () => onDeleteBlock(c),
            },
          ]}
        />
      )}
    </View>
  );
}

// Placeholder rendu pour les 5 sections restantes en construction (sous-taches 2-5 a venir).
function PlaceholderSection({ tab }: { tab: Tab }) {
  const meta = TAB_LABELS[tab];
  return (
    <View style={styles.section}>
      <View style={styles.placeholderCard}>
        <Ionicons name={meta.icon} size={48} color={PALETTE.gold} />
        <Text style={styles.placeholderTitle}>{meta.label}</Text>
        <Text style={styles.placeholderText}>Section en construction</Text>
        <Text style={styles.placeholderHint}>Le contenu arrive dans une sous-tache dediee.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PALETTE.bg },
  loginContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  loginTitle: { color: PALETTE.text, fontSize: 28, fontWeight: '700', marginTop: 24 },
  loginSubtitle: { color: PALETTE.subtext, fontSize: 14, marginTop: 8, marginBottom: 32 },
  passwordInput: {
    width: '100%',
    backgroundColor: PALETTE.card,
    borderWidth: 2,
    borderColor: PALETTE.border,
    borderRadius: 12,
    padding: 16,
    color: PALETTE.text,
    fontSize: 16,
    marginBottom: 16,
  },
  loginButton: {
    width: '100%',
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  loginButtonText: { color: '#000', fontSize: 16, fontWeight: '700' },
  backButton: { marginTop: 16 },
  backButtonText: { color: PALETTE.subtext, fontSize: 14 },
  header: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
  headerBack: { padding: 8 },
  headerTitle: { color: PALETTE.text, fontSize: 24, fontWeight: '700' },
  tabBar: { flexDirection: 'row', padding: 8, paddingHorizontal: 16 },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 20,
    marginRight: 8,
    backgroundColor: PALETTE.card,
    borderWidth: 2,
    borderColor: PALETTE.border,
  },
  tabActive: { backgroundColor: PALETTE.gold, borderColor: PALETTE.gold },
  tabText: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  tabTextActive: { color: '#000' },
  loadingContainer: { padding: 40, alignItems: 'center' },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', padding: 8, gap: 8 },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    borderWidth: 2,
  },
  statNumber: { color: PALETTE.text, fontSize: 28, fontWeight: '700', marginTop: 8 },
  statLabel: { color: PALETTE.subtext, fontSize: 12, marginTop: 4, textAlign: 'center' },
  // Vague 4 sous-tache 6 — Stats enrichie
  dashTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
    gap: 12,
  },
  dashTopRank: { color: PALETTE.gold, fontSize: 16, fontWeight: '700', width: 28 },
  dashTopName: { color: PALETTE.text, fontSize: 15, fontWeight: '600' },
  dashTopMeta: { color: PALETTE.subtext, fontSize: 12, marginTop: 2 },
  dashTopScore: { color: PALETTE.gold, fontSize: 16, fontWeight: '700' },
  dashCategoryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  dashCategoryChip: {
    backgroundColor: PALETTE.bg,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    minWidth: 88,
    alignItems: 'center',
  },
  dashCategoryCount: { color: PALETTE.gold, fontSize: 20, fontWeight: '700' },
  dashCategoryLabel: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },
  dashPipelineRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
    gap: 12,
  },
  dashPipelineLabel: { color: PALETTE.subtext, fontSize: 13, flex: 1 },
  dashPipelineValue: { color: PALETTE.text, fontSize: 13, fontWeight: '600', textAlign: 'right' },
  section: { padding: 16 },
  sectionTitle: { color: PALETTE.text, fontSize: 20, fontWeight: '700', marginBottom: 12 },
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  cardLabel: { color: PALETTE.subtext, fontSize: 14, fontWeight: '600', marginTop: 16, marginBottom: 8 },
  personSelector: { marginVertical: 8 },
  personChip: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    padding: 12,
    marginRight: 8,
    borderWidth: 2,
    borderColor: PALETTE.border,
    minWidth: 100,
  },
  personChipSelected: { borderColor: PALETTE.gold, backgroundColor: PALETTE.gold + '20' },
  personChipText: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  personChipScore: { color: PALETTE.subtext, fontSize: 12, marginTop: 4 },
  selectedPerson: {
    backgroundColor: PALETTE.gold + '20',
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
  },
  selectedPersonName: { color: PALETTE.text, fontSize: 16, fontWeight: '700' },
  selectedPersonStats: { color: PALETTE.subtext, fontSize: 14, marginTop: 4 },
  boostActionsRow: { flexDirection: 'row', gap: 12, marginTop: 8 },
  boostActionBtn: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: PALETTE.border,
    gap: 8,
  },
  boostActionTitle: { color: PALETTE.text, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  boostActionSubtitle: { color: PALETTE.subtext, fontSize: 12, textAlign: 'center' },
  searchInput: {
    backgroundColor: PALETTE.bg,
    borderWidth: 2,
    borderColor: PALETTE.border,
    borderRadius: 8,
    padding: 12,
    color: PALETTE.text,
    fontSize: 16,
  },
  filterRow: { flexDirection: 'row', marginTop: 16 },
  filterLabel: { color: PALETTE.subtext, fontSize: 12, marginBottom: 8 },
  filterChip: {
    backgroundColor: PALETTE.bg,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 16,
    marginRight: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  filterChipActive: { backgroundColor: PALETTE.gold, borderColor: PALETTE.gold },
  filterChipText: { color: PALETTE.text, fontSize: 12, fontWeight: '600' },
  resultsCount: { color: PALETTE.subtext, fontSize: 12, marginTop: 16, marginBottom: 8 },
  moderationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
    gap: 8,
  },
  moderationName: { color: PALETTE.text, fontSize: 16, fontWeight: '600' },
  moderationStats: { color: PALETTE.subtext, fontSize: 12, marginTop: 2 },
  actionBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  activityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
    gap: 12,
  },
  activityIcon: { fontSize: 20 },
  activityName: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  activityTime: { color: PALETTE.subtext, fontSize: 11, marginTop: 2 },
  activityScore: { color: PALETTE.gold, fontSize: 16, fontWeight: '700' },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  settingLabel: { color: PALETTE.text, fontSize: 16, fontWeight: '600' },
  settingDesc: { color: PALETTE.subtext, fontSize: 12, marginTop: 4 },
  settingInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 12,
  },
  settingInputLabel: { color: PALETTE.text, fontSize: 14, fontWeight: '600' },
  settingInput: {
    backgroundColor: PALETTE.bg,
    borderWidth: 2,
    borderColor: PALETTE.border,
    borderRadius: 8,
    padding: 10,
    color: PALETTE.text,
    fontSize: 14,
    width: 100,
    textAlign: 'center',
  },
  saveButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    padding: 16,
    marginTop: 24,
  },
  saveButtonText: { color: '#000', fontSize: 16, fontWeight: '700' },
  refreshTrendsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  refreshTrendsButtonText: { color: '#000', fontSize: 16, fontWeight: '700' },

  // ---------- Styles partages Lot 4 (ReviewList / AdminCard / Placeholder) ----------
  reviewListHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  reviewActionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  reviewActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
    borderWidth: 1,
  },
  reviewActionBtnText: {
    fontSize: 13,
    fontWeight: '700',
  },
  reviewEmpty: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 24,
  },
  adminCardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  adminCardAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  adminCardAvatarText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '700',
  },
  adminCardName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '700',
  },
  adminCardMeta: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  adminCardSubline: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 4,
    fontStyle: 'italic',
  },
  placeholderCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderStyle: 'dashed',
  },
  placeholderTitle: {
    color: PALETTE.text,
    fontSize: 22,
    fontWeight: '700',
    marginTop: 12,
  },
  placeholderText: {
    color: PALETTE.gold,
    fontSize: 14,
    fontWeight: '600',
    marginTop: 8,
  },
  placeholderHint: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 8,
    textAlign: 'center',
  },

  // ---------- Styles Vague 4 — Candidats ----------
  candidatesHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  candidatesHeaderCount: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: -4,
    marginBottom: 12,
  },
  candidatesFilterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.gold,
    backgroundColor: PALETTE.gold + '22',
  },
  candidatesFilterChipText: {
    color: PALETTE.gold,
    fontSize: 12,
    fontWeight: '700',
  },
  candidatesRefreshBtn: {
    padding: 6,
  },
  candidatesWikiScore: {
    color: PALETTE.gold,
    fontSize: 13,
    fontWeight: '700',
  },
  candidatesDateText: {
    color: PALETTE.subtext,
    fontSize: 11,
    marginTop: 2,
  },
  candidatesPublishedTag: {
    color: PALETTE.green,
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  candidatesErrorText: {
    color: PALETTE.accent,
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 12,
  },
  candidatesRetryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: PALETTE.gold,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    alignSelf: 'center',
  },
  candidatesRetryBtnText: {
    color: '#000',
    fontSize: 13,
    fontWeight: '700',
  },
  candidatesPendingZone: {
    backgroundColor: '#13354B', // bleu legerement teinte pour distinguer la zone "en attente"
  },
  candidatesHelpText: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 4,
    marginBottom: 12,
  },
  candidatesDeadlineText: {
    color: '#7AB8E0',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  candidatesImplicitLike: {
    color: PALETTE.green,
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
});
