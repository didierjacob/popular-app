import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  Linking,
  Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';
import { LinearGradient } from 'expo-linear-gradient';

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

// ── Thème « cockpit sombre » (tokens partagés) ──
const THEME = {
  plane: '#0d0d0d',            // fond écran
  surface: '#1a1a19',          // cartes
  surface2: '#211f1e',         // encarts / boutons
  ink: '#ffffff',
  ink2: '#c3c2b7',
  muted: '#898781',
  hairline: 'rgba(255,255,255,0.09)',
  hairlineStrong: 'rgba(255,255,255,0.14)',
  accent: '#9085e9',           // violet signature
  accentSoft: 'rgba(144,133,233,0.14)',
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
  info: '#3987e5',
  cat: {
    culture: '#d55181',
    politics: '#3987e5',
    sport: '#199e70',
    business: '#c98500',
    influencer: '#d95926',
  } as Record<string, string>,
  radius: { card: 12, pill: 9, btn: 8 },
} as const;

// PALETTE — REMAPPÉE sur THEME (Phase B3 : cohérence dark cockpit). Conservée telle
// quelle car de très nombreux styles y réfèrent ; changer les valeurs recolore
// l'ensemble des sections sans toucher au JSX. Correspondances :
//   bg→plane, card→surface, text→ink, subtext→ink2, border→hairline,
//   gold (primaire)→accent violet, green→good, accent (danger)→critical.
const PALETTE = {
  bg: THEME.plane,
  card: THEME.surface,
  text: THEME.ink,
  subtext: THEME.ink2,
  accent: THEME.critical,
  green: THEME.good,
  gold: THEME.accent,
  border: THEME.hairline,
};

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || 'https://popular-app.onrender.com';
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
  open_reports: number;
  queues: {
    pending_candidates: number;
    pending_deceased: number;
    pending_category_reviews: number;
    pending_personality_reports: number;
    pending_outsider_reports: number;
  };
  last_jobs: {
    external_scores: string | null;
    candidate_detection: string | null;
    deceased_check_top50: string | null;
    deceased_check_all: string | null;
    category_review: string | null;
  };
  top5: Array<{ name: string; category: string | null; popularoo_index: number; country?: string | null }>;
}

// Drapeau emoji dérivé d'un code pays ISO-2 (indicateurs régionaux). Générique pour
// tous les pays ; renvoie '' si code absent/invalide (affichage gracieux, pas de drapeau).
function flagEmoji(code?: string | null): string {
  if (!code) return '';
  const cc = code.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(cc)) return '';
  const A = 0x1F1E6; // 🇦
  return String.fromCodePoint(A + cc.charCodeAt(0) - 65, A + cc.charCodeAt(1) - 65);
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
  email?: string;
  boost_active?: boolean;
  tier?: string | null;
  tier_name?: string | null;
  hours_remaining?: number;
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
  // Bloc C (4) — IP de la soumission (info admin ; ban device-primary)
  requested_ip?: string | null;
  pending_vote_value: number;
  // Bloc B1 — liens sociaux fournis a la creation (handle par plateforme) : permettent
  // a l'admin de verifier la personne avant d'approuver. Cle = plateforme, valeur = handle nu.
  social_links?: Record<string, string>;
  social_links_format_ok?: Record<string, boolean>;
  last_error: string | null;
}

// Bloc B1 — Reconstruit une URL cliquable a partir du handle nu stocke cote backend
// (_extract_social_handle renvoie un handle sans @). Meme liste que CREATION_SOCIAL_PLATFORMS.
const SOCIAL_URL_BUILDERS: Record<string, (h: string) => string> = {
  instagram: (h) => `https://instagram.com/${h}`,
  tiktok: (h) => `https://tiktok.com/@${h}`,
  x: (h) => `https://x.com/${h}`,
  youtube: (h) => `https://youtube.com/@${h}`,
  facebook: (h) => `https://facebook.com/${h}`,
  twitch: (h) => `https://twitch.tv/${h}`,
  linkedin: (h) => `https://linkedin.com/in/${h}`,
};
const SOCIAL_LABELS: Record<string, string> = {
  instagram: 'Instagram',
  tiktok: 'TikTok',
  x: 'X',
  youtube: 'YouTube',
  facebook: 'Facebook',
  twitch: 'Twitch',
  linkedin: 'LinkedIn',
};

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

// Vague 4 sous-tache 5 — Ajout manuel (POST /admin/propose-celebrity)
interface ManualAddLastCreation {
  name: string;            // canonical name renvoye par Wikipedia
  category: CandidateCategory;
  popularoo_index: number;
  popularity_external_score: number;
  wikipedia_langs: string[];
}

// Mapping FR des codes d'erreur retournes par /admin/propose-celebrity avec success=false.
const MANUAL_ADD_ERROR_FR: Record<string, string> = {
  already_exists:         'Cette celebrite existe deja dans la base.',
  blocked:                'Ce nom est dans la blocklist (deces confirme precedemment) — impossible a ajouter.',
  wikipedia_not_found:    'Aucune page Wikipedia/Wikidata trouvee pour ce nom. Verifie l\'orthographe (Wikipedia anglais d\'abord).',
  deceased:               'Personne marquee decedee dans Wikidata — utilise l\'onglet Decedes pour gerer.',
  low_confidence:         'Visibilite Wikipedia insuffisante (score de confiance < 65). Attends que la personne ait plus de couverture.',
  wikipedia_check_failed: 'Echec de la verification Wikipedia. Reessaie dans quelques secondes.',
};

// Validation client-side du nom (miroir des verifs server.py /admin/propose-celebrity ligne 7727-7740)
// Retourne null si OK, ou un message FR si invalide.
function validateManualAddName(raw: string): string | null {
  const name = raw.trim();
  if (!name) return 'Le nom est obligatoire.';
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length < 2) return 'Le nom doit contenir au moins 2 mots (prenom + nom).';
  if (/\d/.test(name)) return 'Le nom ne doit pas contenir de chiffres.';
  for (const w of words) {
    // Acronymes all-caps non purement alphabetiques (ex: "X.AE", "U2S")
    if (w.length > 1 && w === w.toUpperCase() && !/^[A-Za-zÀ-ÿ]+$/.test(w)) {
      return `Acronyme suspect dans le nom : "${w}".`;
    }
  }
  return null;
}

// Vague 4 sous-tache 2 — Signalements Outsiders
// La reponse backend est groupee par outsider_person_id (1 ligne = 1 Outsider, signalements imbriques).
type OutsiderReportStatus = 'pending' | 'ignored' | 'warned' | 'deleted';

interface OutsiderReportItem {
  report_id: string;
  reason: string;
  comment: string;
  device_id: string;
  status: OutsiderReportStatus;
  created_at: string;
}

interface OutsiderReportGroup {
  outsider_person_id: string;
  outsider_name: string;
  report_count: number;
  reasons_summary: Record<string, number>;
  person_exists: boolean;
  person_source: string | null;
  person_email: string | null;
  reports: OutsiderReportItem[];
}

type OutsiderReportsFilter = 'pending' | 'all';

// Bloc B2 — Signalements de Personnalites UGC (source=user_search). Reponse backend
// groupee par person_id (1 ligne = 1 Personnalite, signalements imbriques). Lecture seule.
interface PersonalityReportItem {
  report_id: string;
  reason: string;
  comment: string;
  device_id: string;
  status: string;
  created_at: string;
}

interface PersonalityReportGroup {
  person_id: string;
  person_name: string;
  report_count: number;
  reasons_summary: Record<string, number>;
  person_exists: boolean;
  person_source: string | null;
  // Bloc C (2) — auto-masquage doux à seuil
  auto_hidden?: boolean;
  visible_in_rankings?: boolean | null;
  reports: PersonalityReportItem[];
}

// Vague 4 sous-tache 3 — Decedes (deceased_queue + 5 endpoints /admin/deceased*)
// Note divergence brief vs backend: confirm DESACTIVE le profil (is_deceased=true, approved=false,
// deactivated_reason=deceased) + annule Daily Runs actifs + ajoute slug a seed_blocklist. Pas de
// suppression DB. Reject marque la queue 'false_positive', le profil reste actif et publie.
interface DeceasedItem {
  id: string;
  person_id: string;
  name: string;
  category: string;
  death_date: string; // Wikidata time "+2024-11-28T00:00:00Z" OU "unknown" / "unknown_date" / ""
  wikidata_id: string | null;
  detected_at: string | null;
  status: string;
}

// Vague 4 sous-tache 4 — Categories (category_reviews + 4 endpoints /admin/category-review*)
// Source = Wikipedia REST description; confidence est une chaine ("high"/"medium"/"low").
// Limitation V1 connue: reject ne pose pas de flag definitif sur la personne — l'audit suivant
// peut recreer une review pour la meme divergence current vs suggested. A fixer en V2 (cf memoire).
interface CategoryReviewItem {
  id: string;
  person_id: string;
  name: string;
  current_category: string;
  suggested_category: string;
  confidence: string; // "high" | "medium" | "low"
  wiki_description: string;
  created_at: string | null;
  status: string;
}

type Tab =
  | 'stats'            // tableau de bord (stats + files + jobs)
  | 'activity'         // flux d'activité récente
  | 'candidates'       // créations utilisateurs à modérer (approuver/refuser)
  | 'outsider_reports' // signalements (Outsiders + Personnalités UGC)
  | 'manual_add'       // ajout manuel d'une célébrité (Wikidata)
  | 'deceased'         // file des décédés à confirmer
  | 'categories'       // revues de catégorie à appliquer
  | 'moderation'       // recherche + gestion des fiches existantes
  | 'settings';        // réglages

// Libellés d'onglets — clairs et cohérents (FR). La clé technique (ex. 'candidates')
// est inchangée ; seul le label affiché évolue.
const TAB_LABELS: Record<Tab, { label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  stats:            { label: 'Stats',        icon: 'stats-chart' },
  activity:         { label: 'Activite',     icon: 'pulse' },
  candidates:       { label: 'Creations',    icon: 'people-circle' },
  outsider_reports: { label: 'Signalements', icon: 'flag' },
  manual_add:       { label: 'Ajout manuel', icon: 'add-circle' },
  deceased:         { label: 'Decedes',      icon: 'skull' },
  categories:       { label: 'Categories',   icon: 'pricetags' },
  moderation:       { label: 'Recherche',    icon: 'shield-checkmark' },
  settings:         { label: 'Reglages',     icon: 'settings' },
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
  // Vague 4 sous-tache 6 — Stats enrichie (dashboard-stats, parallele a stats legacy)
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  // Search & Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterSource, setFilterSource] = useState<string>('');
  const [searchResults, setSearchResults] = useState<Person[]>([]);
  // Rename Outsider (admin manual correction — e.g. user paid without a name)
  const [renameTarget, setRenameTarget] = useState<Person | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameSaving, setRenameSaving] = useState(false);

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

  // Vague 4 sous-tache 2 — Signalements Outsiders
  const [outsiderReports, setOutsiderReports] = useState<OutsiderReportGroup[]>([]);
  const [outsiderReportsLoading, setOutsiderReportsLoading] = useState(false);
  const [outsiderReportsError, setOutsiderReportsError] = useState<string | null>(null);
  const [outsiderReportsFilter, setOutsiderReportsFilter] = useState<OutsiderReportsFilter>('pending');

  // Bloc B2 — Signalements de Personnalites UGC (lecture seule)
  const [personalityReports, setPersonalityReports] = useState<PersonalityReportGroup[]>([]);
  const [personalityReportsLoading, setPersonalityReportsLoading] = useState(false);
  const [personalityReportsError, setPersonalityReportsError] = useState<string | null>(null);
  const [personalityReportsFilter, setPersonalityReportsFilter] = useState<OutsiderReportsFilter>('pending');

  // Vague 4 sous-tache 3 — Decedes
  const [deceasedItems, setDeceasedItems] = useState<DeceasedItem[]>([]);
  const [deceasedLoading, setDeceasedLoading] = useState(false);
  const [deceasedError, setDeceasedError] = useState<string | null>(null);
  // Loading dedie pour le bouton "Lancer la detection" (job lourd cote serveur, rate-limit 2/60min).
  const [deceasedRunChecking, setDeceasedRunChecking] = useState(false);
  // Loading dedie pour le bouton "Confirmer tout" (boucle backend sur N profils).
  const [deceasedBulkConfirming, setDeceasedBulkConfirming] = useState(false);

  // Vague 4 sous-tache 4 — Categories
  const [categoryReviews, setCategoryReviews] = useState<CategoryReviewItem[]>([]);
  const [categoryReviewsLoading, setCategoryReviewsLoading] = useState(false);
  const [categoryReviewsError, setCategoryReviewsError] = useState<string | null>(null);
  // Loading dedie pour le bouton "Lancer l'audit" (job lourd, rate-limit 2/60min).
  const [categoryRunning, setCategoryRunning] = useState(false);

  // Vague 4 sous-tache 5 — Ajout manuel
  const [manualAddName, setManualAddName] = useState('');
  const [manualAddCategory, setManualAddCategory] = useState<CandidateCategory>('culture');
  const [manualAddLoading, setManualAddLoading] = useState(false);
  const [manualAddError, setManualAddError] = useState<string | null>(null);
  const [manualAddLast, setManualAddLast] = useState<ManualAddLastCreation | null>(null);

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
        Alert.alert('Erreur', 'Mot de passe incorrect');
      }
    } catch (error) {
      Alert.alert('Erreur', 'Impossible de se connecter au serveur');
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Load stats (legacy business: revenus, users actifs, votes)
      // + dashboard-stats (operationnel: queues, last_jobs, top5, alpha, category_breakdown)
      // En parallele, degradent gracieusement si l'un echoue.
      const [statsResult, dashboardResult] = await Promise.allSettled([
        adminFetch(API('/admin/stats')),
        adminFetch(API('/admin/dashboard-stats')),
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

      // Load people (public endpoint, pas besoin d'auth) — seed initial de la
      // recherche de l'onglet Modération (limit=300).
      const peopleRes = await fetch(API('/people?limit=300'));
      if (peopleRes.ok) {
        const peopleData = await peopleRes.json();
        setSearchResults(peopleData);
      }

      // Load activity
      const activityRes = await adminFetch(API('/admin/activity/recent'));
      if (activityRes.ok) {
        const actData = await activityRes.json();
        setActivityData(actData);
      }

      // Load settings
      const settingsRes = await adminFetch(API('/admin/settings'));
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
  }, [adminFetch]);

  const handleSearch = useCallback(async () => {
    try {
      let url = '/admin/search?limit=50';
      if (searchQuery) url += `&q=${encodeURIComponent(searchQuery)}`;
      if (filterCategory) url += `&category=${filterCategory}`;
      if (filterSource) url += `&source=${filterSource}`;

      const res = await adminFetch(API(url));
      if (res.ok) {
        const results = await res.json();
        setSearchResults(results);
      }
    } catch (error) {
      console.error('Search error:', error);
    }
  }, [adminFetch, searchQuery, filterCategory, filterSource]);

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

  // Cœur honnête : le « Booster » (ajout manuel de likes/dislikes) a été retiré —
  // action trompeuse et sans effet sur l'indice (α=1.0). L'endpoint /admin/boost-votes
  // est verrouillé (no-op) côté backend.

  const handleDeletePerson = (person: Person) => {
    Alert.alert(
      '⚠️ Supprimer',
      `Supprimer "${person.name}" ?\n\nCette action est irréversible.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/person/${person.id}`), { method: 'DELETE' });
              if (res.ok) {
                Alert.alert('✅ Supprimé', `"${person.name}" a été supprimé`);
                loadData();
              } else {
                Alert.alert('Erreur', 'Suppression échouée');
              }
            } catch (error) {
              Alert.alert('Erreur', 'Erreur réseau');
            }
          },
        },
      ]
    );
  };

  // Cœur honnête : le « Reset (score 50) » a été retiré — sémantique morte avec α=1.0
  // (l'indice = popularité externe, pas le score-vote). Endpoint reset verrouillé (no-op).

  const handleRenameOutsider = (person: Person) => {
    setRenameTarget(person);
    setRenameValue(person.name === 'Outsider' ? '' : person.name);
  };

  const submitRenameOutsider = async () => {
    if (!renameTarget) return;
    const newName = renameValue.trim();
    if (newName.length < 2) {
      Alert.alert('Nom invalide', 'Le nom doit comporter au moins 2 caractères.');
      return;
    }
    setRenameSaving(true);
    try {
      const res = await adminFetch(API(`/admin/outsider/${renameTarget.id}/rename`), {
        method: 'POST',
        body: JSON.stringify({ new_name: newName }),
      });
      if (res.ok) {
        const data = await res.json();
        // Reflect the new name immediately in the search results
        setSearchResults((prev) =>
          prev.map((p) => (p.id === renameTarget.id ? { ...p, name: data.new_name } : p))
        );
        setRenameTarget(null);
        setRenameValue('');
        Alert.alert('✅ Renommé', `"${data.old_name || 'Outsider'}" → "${data.new_name}"`);
      } else {
        const err = await res.json().catch(() => ({}));
        Alert.alert('Erreur', err.detail || 'Renommage échoué');
      }
    } catch (error) {
      Alert.alert('Erreur', 'Erreur réseau');
    } finally {
      setRenameSaving(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;

    try {
      const res = await adminFetch(API('/admin/settings'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (res.ok) {
        Alert.alert('✅ Enregistré', 'Réglages mis à jour');
      } else {
        Alert.alert('Erreur', 'Enregistrement échoué');
      }
    } catch (error) {
      Alert.alert('Erreur', 'Erreur réseau');
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

  // ---------- Vague 4 sous-tache 2 — Signalements Outsiders ----------
  const loadOutsiderReports = useCallback(async (filter: OutsiderReportsFilter = outsiderReportsFilter) => {
    setOutsiderReportsLoading(true);
    setOutsiderReportsError(null);
    try {
      const res = await adminFetch(API(`/admin/outsider-reports?status=${filter === 'all' ? 'all' : 'pending'}`));
      if (res.ok) {
        const data = await res.json();
        setOutsiderReports(Array.isArray(data?.reports) ? data.reports : []);
      } else if (res.status !== 403) {
        setOutsiderReportsError('Impossible de charger les signalements');
      }
    } catch {
      setOutsiderReportsError('Erreur reseau');
    } finally {
      setOutsiderReportsLoading(false);
    }
  }, [adminFetch, outsiderReportsFilter]);

  useEffect(() => {
    if (authenticated && currentTab === 'outsider_reports') {
      loadOutsiderReports(outsiderReportsFilter);
    }
  }, [authenticated, currentTab, outsiderReportsFilter, loadOutsiderReports]);

  // ---------- Bloc B2 — Signalements de Personnalites UGC (lecture seule) ----------
  const loadPersonalityReports = useCallback(async (filter: OutsiderReportsFilter = personalityReportsFilter) => {
    setPersonalityReportsLoading(true);
    setPersonalityReportsError(null);
    try {
      const res = await adminFetch(API(`/admin/personality-reports?status=${filter === 'all' ? 'all' : 'pending'}`));
      if (res.ok) {
        const data = await res.json();
        setPersonalityReports(Array.isArray(data?.reports) ? data.reports : []);
      } else if (res.status !== 403) {
        setPersonalityReportsError('Impossible de charger les signalements');
      }
    } catch {
      setPersonalityReportsError('Erreur reseau');
    } finally {
      setPersonalityReportsLoading(false);
    }
  }, [adminFetch, personalityReportsFilter]);

  useEffect(() => {
    if (authenticated && currentTab === 'outsider_reports') {
      loadPersonalityReports(personalityReportsFilter);
    }
  }, [authenticated, currentTab, personalityReportsFilter, loadPersonalityReports]);

  // Bloc C (2) — ré-afficher une Personnalité auto-masquée (après revue admin).
  const personalityRestore = useCallback((g: PersonalityReportGroup) => {
    Alert.alert(
      'Re-afficher',
      `Re-afficher "${g.person_name || '(sans nom)'}" dans les classements ? Ses signalements seront marques "revus".`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Re-afficher',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/personality-reports/${g.person_id}/restore`), {
                method: 'POST',
              });
              if (res.ok) {
                Alert.alert('Re-affichee', `${g.person_name || 'La fiche'} est de nouveau visible.`);
                loadPersonalityReports(personalityReportsFilter);
              } else {
                let msg = 'Echec du re-affichage';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            }
          },
        },
      ]
    );
  }, [adminFetch, personalityReportsFilter, loadPersonalityReports]);

  // Backend resout en bulk tous les pending pour l'outsider, donc on passe report_id de reports[0].
  const firstReportId = (g: OutsiderReportGroup): string | null =>
    g.reports && g.reports.length > 0 ? g.reports[0].report_id : null;

  const outsiderIgnore = useCallback((g: OutsiderReportGroup) => {
    const rid = firstReportId(g);
    if (!rid) return;
    Alert.alert(
      'Classer sans suite',
      `Aucune violation detectee pour ${g.outsider_name} ?\n\nLes ${g.report_count} signalement${g.report_count > 1 ? 's' : ''} en attente seront marques comme ignores.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Ignorer',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/outsider-reports/${rid}/ignore`), {
                method: 'POST',
              });
              if (res.ok) {
                setOutsiderReports((prev) => prev.filter((x) => x.outsider_person_id !== g.outsider_person_id));
                Alert.alert('Classe sans suite', `Signalements de ${g.outsider_name} classes sans suite.`);
              } else {
                let msg = 'Echec';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const outsiderWarn = useCallback((g: OutsiderReportGroup) => {
    const rid = firstReportId(g);
    if (!rid) return;
    const emailLabel = g.person_email ? ` (${g.person_email})` : '';
    Alert.alert(
      'Avertir l\'Outsider',
      `Envoyer un email d'avertissement a ${g.outsider_name}${emailLabel} ?\n\nL'email bilingue FR+EN rappelle les conditions d'utilisation.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Envoyer',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/outsider-reports/${rid}/warn`), {
                method: 'POST',
              });
              if (res.ok) {
                // Maj optimiste: marque tous les reports pending du groupe comme warned (la carte reste mais change de statut)
                setOutsiderReports((prev) =>
                  prev.map((x) =>
                    x.outsider_person_id === g.outsider_person_id
                      ? {
                          ...x,
                          reports: x.reports.map((r) =>
                            r.status === 'pending' ? { ...r, status: 'warned' as OutsiderReportStatus } : r
                          ),
                        }
                      : x
                  )
                );
                Alert.alert('Avertissement envoye', `Email envoye a ${g.outsider_name}.`);
              } else if (res.status === 422) {
                Alert.alert(
                  'Email indisponible',
                  `Aucun email connu pour ${g.outsider_name} — impossible d'envoyer l'avertissement.`
                );
              } else {
                let msg = 'Echec de l\'avertissement';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const outsiderDelete = useCallback((g: OutsiderReportGroup) => {
    const rid = firstReportId(g);
    if (!rid) return;
    Alert.alert(
      '⚠️ Retirer l\'Outsider',
      `Action irreversible. Retirer ${g.outsider_name} entraine :\n\n` +
        `• Suppression definitive du profil Outsider\n` +
        `• Expiration immediate de ses Boosters (sans remboursement)\n` +
        `• Blocage de l'utilisateur (slug + device) — il ne pourra plus creer d'Outsider\n` +
        `• Envoi d'un email de notification\n\n` +
        `Confirmer le retrait ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Retirer',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/outsider-reports/${rid}/delete`), {
                method: 'POST',
              });
              if (res.ok) {
                setOutsiderReports((prev) => prev.filter((x) => x.outsider_person_id !== g.outsider_person_id));
                Alert.alert('Outsider retire', `🚫 ${g.outsider_name} retire de la liste des Outsiders.`);
              } else {
                let msg = 'Echec du retrait';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  // ---------- Vague 4 sous-tache 3 — Decedes ----------
  // Section sensible (mort de personnes reelles): tone neutre, pas de rouge, pas d'emojis.
  // Confirm = desactivation profil + cancel Daily Runs + slug -> seed_blocklist (irreversible).
  // Reject = false_positive (profil reste vivant).
  const loadDeceased = useCallback(async () => {
    setDeceasedLoading(true);
    setDeceasedError(null);
    try {
      const res = await adminFetch(API('/admin/deceased-queue?status=pending'));
      if (res.ok) {
        const data: DeceasedItem[] = await res.json();
        setDeceasedItems(Array.isArray(data) ? data : []);
      } else if (res.status !== 403) {
        setDeceasedError('Impossible de charger la file des deces');
      }
    } catch {
      setDeceasedError('Erreur reseau');
    } finally {
      setDeceasedLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (authenticated && currentTab === 'deceased') {
      loadDeceased();
    }
  }, [authenticated, currentTab, loadDeceased]);

  const deceasedConfirm = useCallback((item: DeceasedItem) => {
    Alert.alert(
      'Confirmer le deces',
      `Confirmer le deces de ${item.name} ?\n\nCette action :\n` +
        `• Desactive le profil (retire des classements)\n` +
        `• Annule les Daily Runs actifs lies a cette personne\n` +
        `• Ajoute le nom a la blocklist permanente (anti-reinsertion)\n\n` +
        `Action irreversible.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Confirmer le deces',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/deceased/${item.id}/confirm`), {
                method: 'POST',
              });
              if (res.ok) {
                setDeceasedItems((prev) => prev.filter((x) => x.id !== item.id));
                Alert.alert('Deces confirme', `${item.name} a ete retire des classements.`);
              } else {
                let msg = 'Echec de la confirmation';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const deceasedReject = useCallback((item: DeceasedItem) => {
    Alert.alert(
      'Faux positif',
      `Marquer la detection de ${item.name} comme faux positif ?\n\nLe profil reste actif et publie.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Faux positif',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/deceased/${item.id}/reject`), {
                method: 'POST',
              });
              if (res.ok) {
                setDeceasedItems((prev) => prev.filter((x) => x.id !== item.id));
                Alert.alert('Marque faux positif', `Detection de ${item.name} ignoree.`);
              } else {
                let msg = 'Echec';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const deceasedConfirmAll = useCallback(() => {
    const count = deceasedItems.length;
    if (count === 0) return;
    Alert.alert(
      'Confirmer tous les deces',
      `Confirmer le deces de ${count} profil${count > 1 ? 's' : ''} detecte${count > 1 ? 's' : ''} ?\n\n` +
        `Chaque profil sera desactive et ses Daily Runs actifs annules. Tous les noms seront ajoutes a la blocklist permanente.\n\n` +
        `Action irreversible.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: `Confirmer (${count})`,
          onPress: async () => {
            setDeceasedBulkConfirming(true);
            try {
              const res = await adminFetch(API('/admin/deceased/confirm-all'), {
                method: 'POST',
              });
              if (res.ok) {
                const data = await res.json();
                const confirmed = Number(data?.confirmed ?? 0);
                setDeceasedItems([]);
                Alert.alert('Deces confirmes', `${confirmed} profil${confirmed > 1 ? 's' : ''} retire${confirmed > 1 ? 's' : ''} des classements.`);
              } else {
                let msg = 'Echec';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            } finally {
              setDeceasedBulkConfirming(false);
            }
          },
        },
      ]
    );
  }, [adminFetch, deceasedItems.length]);

  const deceasedRunCheck = useCallback(() => {
    Alert.alert(
      'Lancer la detection',
      `Le serveur va interroger Wikidata pour toutes les personnalites (sweep complete). ` +
        `L'operation peut prendre plusieurs minutes. La file sera rafraichie automatiquement au retour.\n\n` +
        `Lancer ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Lancer',
          onPress: async () => {
            setDeceasedRunChecking(true);
            try {
              const res = await adminFetch(API('/admin/run-deceased-check'), {
                method: 'POST',
              });
              if (res.status === 429) {
                Alert.alert(
                  'Detection deja lancee recemment',
                  'Limite atteinte (2 lancements par heure). Reessaie dans environ une heure.'
                );
                return;
              }
              if (res.ok) {
                const data = await res.json();
                const checked = Number(data?.checked ?? 0);
                const detected = Number(data?.detected ?? 0);
                Alert.alert(
                  'Detection terminee',
                  `${checked} profil${checked > 1 ? 's' : ''} verifie${checked > 1 ? 's' : ''}, ${detected} deces detecte${detected > 1 ? 's' : ''}.`
                );
                // Refetch queue pour voir les nouveaux items
                loadDeceased();
              } else {
                let msg = 'Echec du lancement';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            } finally {
              setDeceasedRunChecking(false);
            }
          },
        },
      ]
    );
  }, [adminFetch, loadDeceased]);

  // ---------- Vague 4 sous-tache 4 — Categories ----------
  // Workflow: l'audit compare current_category vs Wikipedia REST description pour chaque profil
  // non-outsider et non-self_boosted; les divergences atterrissent dans category_reviews (pending).
  // Apply = update persons.category (pas de recalcul PI). Reject = mark rejected (cf limitation V1
  // documentee: la review peut etre recreee au prochain audit, pas de flag personne).
  const loadCategoryReviews = useCallback(async () => {
    setCategoryReviewsLoading(true);
    setCategoryReviewsError(null);
    try {
      const res = await adminFetch(API('/admin/category-reviews?status=pending'));
      if (res.ok) {
        const data: CategoryReviewItem[] = await res.json();
        setCategoryReviews(Array.isArray(data) ? data : []);
      } else if (res.status !== 403) {
        setCategoryReviewsError('Impossible de charger les revisions de categorie');
      }
    } catch {
      setCategoryReviewsError('Erreur reseau');
    } finally {
      setCategoryReviewsLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (authenticated && currentTab === 'categories') {
      loadCategoryReviews();
    }
  }, [authenticated, currentTab, loadCategoryReviews]);

  const categoryApply = useCallback((item: CategoryReviewItem) => {
    const fromLabel = categoryFR(item.current_category);
    const toLabel = categoryFR(item.suggested_category);
    Alert.alert(
      'Appliquer la correction',
      `Modifier la categorie de ${item.name} :\n${fromLabel} → ${toLabel} ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Appliquer',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/category-reviews/${item.id}/apply`), {
                method: 'POST',
              });
              if (res.ok) {
                setCategoryReviews((prev) => prev.filter((x) => x.id !== item.id));
                Alert.alert('Categorie modifiee', `${item.name} : ${fromLabel} → ${toLabel}.`);
              } else {
                let msg = 'Echec de la modification';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const categoryReject = useCallback((item: CategoryReviewItem) => {
    const currentLabel = categoryFR(item.current_category);
    Alert.alert(
      "Garder l'actuelle",
      `Conserver la categorie ${currentLabel} pour ${item.name} ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Conserver',
          onPress: async () => {
            try {
              const res = await adminFetch(API(`/admin/category-reviews/${item.id}/reject`), {
                method: 'POST',
              });
              if (res.ok) {
                setCategoryReviews((prev) => prev.filter((x) => x.id !== item.id));
                Alert.alert('Categorie conservee', `${currentLabel} maintenue pour ${item.name}.`);
              } else {
                let msg = 'Echec';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
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

  const categoryRunReview = useCallback(() => {
    Alert.alert(
      "Lancer l'audit",
      `Le serveur va comparer chaque profil non-outsider avec sa description Wikipedia ` +
        `et flagger les divergences de categorie. L'operation peut prendre plusieurs minutes. ` +
        `La file sera rafraichie automatiquement au retour.\n\nLancer ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Lancer',
          onPress: async () => {
            setCategoryRunning(true);
            try {
              const res = await adminFetch(API('/admin/run-category-review'), {
                method: 'POST',
              });
              if (res.status === 429) {
                Alert.alert(
                  'Audit deja lance recemment',
                  'Limite atteinte (2 lancements par heure). Reessaie dans environ une heure.'
                );
                return;
              }
              if (res.ok) {
                const data = await res.json();
                const reviewed = Number(data?.reviewed ?? 0);
                const divergences = Number(data?.divergences ?? 0);
                Alert.alert(
                  'Audit termine',
                  `${reviewed} profil${reviewed > 1 ? 's' : ''} analyse${reviewed > 1 ? 's' : ''}, ${divergences} divergence${divergences > 1 ? 's' : ''} detectee${divergences > 1 ? 's' : ''}.`
                );
                loadCategoryReviews();
              } else {
                let msg = 'Echec du lancement';
                try { const d = await res.json(); if (d?.detail) msg = String(d.detail); } catch {}
                Alert.alert('Erreur', msg);
              }
            } catch {
              Alert.alert('Erreur', 'Erreur reseau');
            } finally {
              setCategoryRunning(false);
            }
          },
        },
      ]
    );
  }, [adminFetch, loadCategoryReviews]);

  // ---------- Vague 4 sous-tache 5 — Soumission ajout manuel ----------
  // Cree immediatement une celebrite via /admin/propose-celebrity (visible=true, source=admin_manual).
  // Pipeline backend: validation Wikidata (humain vivant) + confidence ≥ 65 + external score + PI.
  const manualAddSubmit = useCallback(() => {
    const trimmed = manualAddName.trim();
    // Validation client en miroir du backend, evite un aller-retour 400.
    const localErr = validateManualAddName(trimmed);
    if (localErr) {
      setManualAddError(localErr);
      return;
    }
    setManualAddError(null);

    Alert.alert(
      'Creer cette celebrite ?',
      `"${trimmed}" sera publie(e) IMMEDIATEMENT en categorie "${manualAddCategory}".\n\nPipeline auto: verification Wikidata (humain vivant, non decede), score externe Wikipedia, calcul du Popularoo Index.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Creer',
          onPress: async () => {
            setManualAddLoading(true);
            setManualAddError(null);
            try {
              const res = await adminFetch(API('/admin/propose-celebrity'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: trimmed, category: manualAddCategory }),
              });

              if (res.status === 403) {
                // adminFetch a deja gere la deconnexion + alerte. On sort proprement.
                return;
              }

              // 4xx (validation backend) -> {detail: string}
              if (!res.ok) {
                let detail = 'Echec de la creation.';
                try {
                  const data = await res.json();
                  if (data?.detail) detail = String(data.detail);
                } catch {}
                setManualAddError(detail);
                return;
              }

              const data = await res.json();
              if (data?.success === false) {
                const code: string = data?.error || 'unknown';
                const fr = MANUAL_ADD_ERROR_FR[code] || data?.message || `Echec (${code}).`;
                setManualAddError(fr);
                return;
              }

              // Succes: capture le canonical name + index + score + langs renvoyes par le backend.
              const canonical: string = data?.name || trimmed;
              const last: ManualAddLastCreation = {
                name: canonical,
                category: (data?.category as CandidateCategory) || manualAddCategory,
                popularoo_index: Number(data?.popularoo_index ?? 0),
                popularity_external_score: Number(data?.popularity_external_score ?? 0),
                wikipedia_langs: Array.isArray(data?.wikipedia_langs) ? data.wikipedia_langs : [],
              };
              setManualAddLast(last);
              setManualAddName(''); // reset uniquement le nom; on garde la categorie (probable usage en serie)

              // Toast confirmation
              Alert.alert(
                '✅ Cree',
                `${canonical} cree(e) — PI ${last.popularoo_index.toFixed(1)}.`,
              );

              // Refresh des contextes impactes: dashboard-stats (total_celebrities, category_breakdown,
              // top5) + zone Candidats (publies recents). Aucun impact attendu sur la pending queue.
              loadData();
              loadCandidates();
            } catch (e) {
              setManualAddError('Erreur reseau. Verifie ta connexion et reessaie.');
            } finally {
              setManualAddLoading(false);
            }
          },
        },
      ]
    );
  }, [adminFetch, manualAddName, manualAddCategory, loadData, loadCandidates]);

  // Le recap de la derniere creation est ephemere: 3s puis disparait (brief Didier).
  useEffect(() => {
    if (!manualAddLast) return;
    const t = setTimeout(() => setManualAddLast(null), 3000);
    return () => clearTimeout(t);
  }, [manualAddLast]);

  // ---------- Actions zone 1 (pending queue) ----------
  const pendingForceValidate = useCallback((entry: PendingQueueEntry) => {
    Alert.alert(
      'Approuver et publier',
      `Publier "${entry.name}" et le rendre visible dans les classements ?\n\n` +
        `⚠️ Verifiez la majorite : n'approuvez pas une personne mineure ` +
        `(controle de la date de naissance a faire manuellement via les liens sociaux).`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Approuver',
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
          <Text style={styles.loginTitle}>Accès admin</Text>
          <Text style={styles.loginSubtitle}>Geste secret détecté</Text>
          
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
      {/* Header — barre du haut « cockpit » (B1) */}
      <View style={styles.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.topbarBack} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Ionicons name="chevron-back" size={22} color={THEME.ink2} />
        </TouchableOpacity>
        <LinearGradient
          colors={['#9d93f0', '#6f63d6']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.topbarLogo}
        >
          <Text style={styles.topbarLogoText}>P</Text>
        </LinearGradient>
        <Text style={styles.topbarTitle} numberOfLines={1}>Popularoo · Administration</Text>
        <View style={{ flex: 1 }} />
        <View style={styles.statusPill}>
          <View style={[styles.statusDot, { backgroundColor: THEME.good }]} />
          <Text style={styles.statusPillText}>α verrouillé {(dashboardStats?.alpha ?? 1).toFixed(2)}</Text>
        </View>
        <View style={styles.statusPill}>
          <View style={[styles.statusDot, { backgroundColor: THEME.info }]} />
          <Text style={styles.statusPillText}>Live</Text>
        </View>
        <TouchableOpacity onPress={loadData} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }} style={styles.topbarIcon}>
          <Ionicons name="refresh" size={20} color={THEME.ink2} />
        </TouchableOpacity>
        <TouchableOpacity onPress={handleLogout} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }} style={styles.topbarIcon}>
          <Ionicons name="log-out-outline" size={20} color={THEME.muted} />
        </TouchableOpacity>
      </View>

      {/* Tabs — pills ; badges de compte (files) ; fade droite = scroll horizontal */}
      <View style={styles.tabBarWrapper}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar} contentContainerStyle={{ paddingRight: 32 }}>
          {TAB_ORDER.map((t) => {
            const meta = TAB_LABELS[t];
            const active = currentTab === t;
            // Badges de compte (données déjà chargées ; aucun fetch ajouté).
            let badge = 0;
            let badgeColor: string = THEME.warning;
            if (t === 'candidates') badge = dashboardStats?.queues?.pending_candidates ?? 0;
            else if (t === 'deceased') badge = dashboardStats?.queues?.pending_deceased ?? 0;
            else if (t === 'outsider_reports') { badge = outsiderReports.length + personalityReports.length; badgeColor = THEME.serious; }
            return (
              <TouchableOpacity
                key={t}
                style={[styles.tab, active && styles.tabActive]}
                onPress={() => setCurrentTab(t)}
              >
                <Ionicons name={meta.icon} size={16} color={active ? THEME.ink : THEME.ink2} />
                <Text style={[styles.tabText, active && styles.tabTextActive]}>{meta.label}</Text>
                {badge > 0 && (
                  <View style={[styles.tabBadge, { backgroundColor: badgeColor }]}>
                    <Text style={styles.tabBadgeText}>{badge}</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </ScrollView>
        <LinearGradient
          colors={['rgba(13,13,13,0)', THEME.plane]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          pointerEvents="none"
          style={styles.tabBarFade}
        />
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
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
                activityData={activityData}
                onOpenTab={setCurrentTab}
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
              <>
                <OutsiderReportsSection
                  reports={outsiderReports}
                  loading={outsiderReportsLoading}
                  error={outsiderReportsError}
                  filter={outsiderReportsFilter}
                  onFilterChange={setOutsiderReportsFilter}
                  onRefresh={() => loadOutsiderReports(outsiderReportsFilter)}
                  onIgnore={outsiderIgnore}
                  onWarn={outsiderWarn}
                  onDelete={outsiderDelete}
                />
                {/* Bloc B2/C — Signalements de Personnalites UGC (+ auto-masquage / re-affichage) */}
                <PersonalityReportsSection
                  reports={personalityReports}
                  loading={personalityReportsLoading}
                  error={personalityReportsError}
                  filter={personalityReportsFilter}
                  onFilterChange={setPersonalityReportsFilter}
                  onRefresh={() => loadPersonalityReports(personalityReportsFilter)}
                  onRestore={personalityRestore}
                />
              </>
            )}

            {currentTab === 'manual_add' && (
              <ManualAddSection
                name={manualAddName}
                onNameChange={setManualAddName}
                category={manualAddCategory}
                onCategoryChange={setManualAddCategory}
                loading={manualAddLoading}
                error={manualAddError}
                lastCreation={manualAddLast}
                onSubmit={manualAddSubmit}
              />
            )}

            {currentTab === 'deceased' && (
              <DeceasedSection
                items={deceasedItems}
                loading={deceasedLoading}
                error={deceasedError}
                runChecking={deceasedRunChecking}
                bulkConfirming={deceasedBulkConfirming}
                onRefresh={loadDeceased}
                onConfirm={deceasedConfirm}
                onReject={deceasedReject}
                onConfirmAll={deceasedConfirmAll}
                onRunCheck={deceasedRunCheck}
              />
            )}

            {currentTab === 'categories' && (
              <CategoriesSection
                items={categoryReviews}
                loading={categoryReviewsLoading}
                error={categoryReviewsError}
                running={categoryRunning}
                onRefresh={loadCategoryReviews}
                onApply={categoryApply}
                onReject={categoryReject}
                onRunReview={categoryRunReview}
              />
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
                onRename={handleRenameOutsider}
              />
            )}

            {currentTab === 'settings' && settings && (
              <SettingsTab settings={settings} onSettingsChange={setSettings} onSave={handleSaveSettings} />
            )}
          </>
        )}
      </ScrollView>

      {/* Rename Outsider modal (admin manual name correction) */}
      <Modal
        visible={renameTarget !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setRenameTarget(null)}
      >
        <View style={styles.renameOverlay}>
          <View style={styles.renameCard}>
            <Text style={styles.renameTitle}>✏️ Renommer l'Outsider</Text>
            {renameTarget?.email ? (
              <Text style={styles.renameSub}>{renameTarget.email}</Text>
            ) : null}
            <TextInput
              style={styles.renameInput}
              placeholder="Nom d'affichage au classement"
              placeholderTextColor={PALETTE.subtext}
              value={renameValue}
              onChangeText={setRenameValue}
              autoCapitalize="words"
              autoFocus
            />
            <View style={styles.renameActions}>
              <TouchableOpacity
                style={[styles.renameBtn, styles.renameBtnCancel]}
                onPress={() => setRenameTarget(null)}
                disabled={renameSaving}
              >
                <Text style={styles.renameBtnCancelText}>Annuler</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.renameBtn, styles.renameBtnConfirm]}
                onPress={submitRenameOutsider}
                disabled={renameSaving}
              >
                {renameSaving ? (
                  <ActivityIndicator color="#000" size="small" />
                ) : (
                  <Text style={styles.renameBtnConfirmText}>Renommer</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// Dashboard Tab Component — Vague 4 sous-tache 6 : enrichi avec /admin/dashboard-stats
function DashboardTab({ stats, dashboardStats, activityData, onOpenTab }: any) {
  const ds: DashboardStats | null = dashboardStats;
  const noStats = !stats && !ds;
  const catColor = (c?: string | null) => (c && THEME.cat[c]) ? THEME.cat[c] : THEME.muted;
  const catTotal = ds ? Object.values(ds.category_breakdown || {}).reduce((a: number, b) => a + (b as number), 0) : 0;

  const Tile = ({ label, value, sub, subColor = THEME.ink2, accent = false }:
    { label: string; value: any; sub?: string; subColor?: string; accent?: boolean }) => (
    <View style={styles.kpiTile}>
      {accent && <View style={styles.kpiAccentBar} />}
      <Text style={styles.kpiLabel}>{label}</Text>
      <Text style={styles.kpiValue}>{value}</Text>
      {sub ? <Text style={[styles.kpiSub, { color: subColor }]}>{sub}</Text> : null}
    </View>
  );

  const ModRow = ({ icon, title, sub, count, tab, first }:
    { icon: any; title: string; sub: string; count: number; tab: Tab; first?: boolean }) => (
    <View style={[styles.rowLine, first && { borderTopWidth: 0 }]}>
      <View style={styles.modIcon}><Ionicons name={icon} size={16} color={THEME.ink2} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.modTitle}>{title}</Text>
        <Text style={styles.modSub}>{sub}</Text>
      </View>
      {count > 0 && (
        <View style={styles.modBadge}><Text style={styles.modBadgeText}>{count}</Text></View>
      )}
      <TouchableOpacity
        style={count > 0 ? styles.btnPrimary : styles.btnPlain}
        onPress={() => onOpenTab?.(tab)}
      >
        <Text style={count > 0 ? styles.btnPrimaryText : styles.btnPlainText}>Ouvrir →</Text>
      </TouchableOpacity>
    </View>
  );

  if (noStats) {
    return (
      <View style={styles.panel}>
        <Text style={styles.kpiLabel}>Statistiques indisponibles</Text>
      </View>
    );
  }

  return (
    <View>
      {/* ── Tuiles KPI ── */}
      {stats && ds && (
        <View style={styles.kpiGrid}>
          <Tile label="Total profils" value={stats.total_people} sub="profils en base" accent />
          <Tile label="Votes totaux" value={stats.total_votes} sub="cumulés" />
          <Tile label="Actifs 24h" value={stats.active_users_24h} sub={`${stats.active_users_7d ?? '—'} sur 7 jours`} />
          <Tile label="À modérer" value={ds.queues.pending_candidates} sub="créations en attente" subColor={THEME.warning} />
          <Tile label="Signalements" value={ds.open_reports} sub="ouverts à traiter" subColor={THEME.serious} />
          <Tile label="Décès à vérifier" value={ds.queues.pending_deceased} sub="file décédés" subColor={THEME.serious} />
          <Tile label="Revenus 24h" value={`${stats.revenue_24h}€`} sub="estimé (non vérifié IAP)" />
        </View>
      )}

      {/* ── File de modération (navigation) ── */}
      {ds && (
        <View style={styles.panel}>
          <View style={styles.panelHead}>
            <Text style={styles.panelTitle}>File de modération</Text>
            <Text style={styles.panelCount}>
              {ds.queues.pending_candidates + ds.queues.pending_deceased + ds.queues.pending_category_reviews} en attente
            </Text>
          </View>
          <ModRow first icon="people-circle-outline" title="Créations utilisateurs"
            sub="à approuver ou refuser" count={ds.queues.pending_candidates} tab="candidates" />
          <ModRow icon="skull-outline" title="Décès à vérifier"
            sub="confirmer / rejeter" count={ds.queues.pending_deceased} tab="deceased" />
          <ModRow icon="pricetags-outline" title="Revues de catégorie"
            sub="appliquer / rejeter" count={ds.queues.pending_category_reviews} tab="categories" />
        </View>
      )}

      {/* ── Top 5 popularité ── */}
      {ds && ds.top5 && ds.top5.length > 0 && (
        <View style={styles.panel}>
          <View style={styles.panelHead}>
            <Text style={styles.panelTitle}>Top 5 popularité</Text>
            <Text style={styles.panelCount}>indice Popularoo</Text>
          </View>
          {ds.top5.map((p, idx) => (
            <View key={`${idx}-${p.name}`} style={[styles.top5Row, idx === 0 && { borderTopWidth: 0 }]}>
              <Text style={styles.top5Rank}>{idx + 1}</Text>
              {flagEmoji(p.country) ? <Text style={styles.top5Flag}>{flagEmoji(p.country)}</Text> : null}
              <Text style={styles.top5Name} numberOfLines={1}>{p.name}</Text>
              {p.category && (
                <View style={[styles.catChip, { backgroundColor: catColor(p.category) }]}>
                  <Text style={styles.catChipText}>{categoryFR(p.category)}</Text>
                </View>
              )}
              <Text style={styles.top5Index}>{p.popularoo_index.toFixed(1)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* ── Répartition par catégorie (barres) ── */}
      {ds && ds.category_breakdown && Object.keys(ds.category_breakdown).length > 0 && (
        <View style={styles.panel}>
          <View style={styles.panelHead}>
            <Text style={styles.panelTitle}>Répartition par catégorie</Text>
            <Text style={styles.panelCount}>{catTotal} profils</Text>
          </View>
          {Object.entries(ds.category_breakdown)
            .sort((a, b) => (b[1] as number) - (a[1] as number))
            .map(([cat, count]) => {
              const pct = catTotal > 0 ? Math.round((count as number) / catTotal * 100) : 0;
              return (
                <View key={cat} style={styles.catBarRow}>
                  <View style={styles.catBarHead}>
                    <Text style={styles.catBarLabel}>{categoryFR(cat)}</Text>
                    <Text style={styles.catBarPct}>{count} · {pct}%</Text>
                  </View>
                  <View style={styles.catBarTrack}>
                    <View style={[styles.catBarFill, { width: `${pct}%`, backgroundColor: catColor(cat) }]} />
                  </View>
                </View>
              );
            })}
        </View>
      )}

      {/* ── Flux d'activité (données déjà chargées) ── */}
      {activityData?.recent_people?.length > 0 && (
        <View style={styles.panel}>
          <View style={styles.panelHead}>
            <Text style={styles.panelTitle}>Activité récente</Text>
            <Text style={styles.panelCount}>nouveaux profils</Text>
          </View>
          {activityData.recent_people.slice(0, 6).map((it: any, i: number) => (
            <View key={i} style={[styles.actRow, i === 0 && { borderTopWidth: 0 }]}>
              <View style={[styles.actDot, { backgroundColor: THEME.good }]} />
              <Text style={styles.actText} numberOfLines={1}>{it.name || it.person_name || 'Profil'}</Text>
              <Text style={styles.actTime}>{it.created_at ? formatRelativeShort(it.created_at) : ''}</Text>
            </View>
          ))}
        </View>
      )}

      {/* ── Santé pipeline ── */}
      {ds && (
        <View style={styles.panel}>
          <View style={styles.panelHead}>
            <Text style={styles.panelTitle}>Santé pipeline</Text>
            <Text style={styles.panelCount}>{ds.total_celebrities} célébrités</Text>
          </View>
          {([
            ['Alpha (indice)', ds.alpha?.toFixed(2) ?? '—'],
            ['Scores externes', formatDateFR(ds.last_jobs.external_scores)],
            ['Détection candidats', formatDateFR(ds.last_jobs.candidate_detection)],
            ['Vérif décès (top 50)', formatDateFR(ds.last_jobs.deceased_check_top50)],
            ['Vérif décès (complet)', formatDateFR(ds.last_jobs.deceased_check_all)],
            ['Revue catégories', formatDateFR(ds.last_jobs.category_review)],
          ] as [string, string][]).map(([label, value], i) => (
            <View key={label} style={[styles.pipeRow, i === 0 && { borderTopWidth: 0 }]}>
              <Text style={styles.pipeLabel}>{label}</Text>
              <Text style={styles.pipeValue}>{value}</Text>
            </View>
          ))}
        </View>
      )}

      {/* ── Pied — disclaimer ── */}
      <Text style={styles.footerNote}>
        💡 Revenus = estimation (nb de boosts × prix tarifaire), NON vérifiés côté IAP
        (Google Play en observation). Indice = popularité externe (α verrouillé à 1.00).
      </Text>
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
  onRename,
}: any) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>🔍 Recherche avancée</Text>
      
      <View style={styles.card}>
        <TextInput
          style={styles.searchInput}
          placeholder="Rechercher par nom ou e-mail..."
          placeholderTextColor={PALETTE.subtext}
          value={searchQuery}
          onChangeText={onSearchChange}
        />

        <View style={styles.filterRow}>
          <View style={{ flex: 1, marginRight: 8 }}>
            <Text style={styles.filterLabel}>Catégorie</Text>
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

        <Text style={styles.resultsCount}>{searchResults.length} résultat(s)</Text>

        {searchResults.map((person: Person) => (
          <View key={person.id} style={styles.moderationRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.moderationName}>{person.name}</Text>
              <Text style={styles.moderationStats}>
                Score {person.score} • {person.total_votes} votes • {person.source}
              </Text>
              {person.email ? (
                <Text style={styles.moderationStats}>✉️ {person.email}</Text>
              ) : null}
              {person.boost_active ? (
                <Text style={styles.moderationStats}>
                  🚀 {person.tier_name || person.tier} • {person.hours_remaining}h restantes
                </Text>
              ) : (person.source === 'self_boosted' ? (
                <Text style={styles.moderationStats}>⏸ boost inactif</Text>
              ) : null)}
            </View>

            <TouchableOpacity style={styles.actionBtn} onPress={() => onRename(person)}>
              <Ionicons name="create-outline" size={20} color={PALETTE.green} />
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
        <Text style={styles.sectionTitle}>👤 Nouvelles personnalités</Text>
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
        <Text style={styles.sectionTitle}>💰 Achats récents</Text>
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
        <Text style={styles.sectionTitle}>⚡ Utilisations récentes</Text>
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
      <Text style={styles.sectionTitle}>⚙️ Réglages de l'app</Text>
      
      <View style={styles.card}>
        <View style={styles.settingRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.settingLabel}>Autoriser ajouts utilisateurs</Text>
            <Text style={styles.settingDesc}>Les utilisateurs peuvent ajouter des personnalités</Text>
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
            <Text style={styles.settingDesc}>Désactive l'accès à l'app</Text>
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
      {/* ============ Zone 1 — Propositions a moderer (approbation admin requise) ============ */}
      <View style={[styles.candidatesPendingZone, styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>⏳ Propositions a moderer</Text>
            <Text style={styles.candidatesHeaderCount}>
              {pendingQueue.length} proposition{pendingQueue.length > 1 ? 's' : ''} en attente
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
          Rien n'est publie sans votre approbation. Verifiez chaque proposition (liens sociaux, majorite)
          puis Approuvez pour publier, ou Refusez.
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
              const subline = e.last_error
                ? `Tentative precedente echouee: ${e.last_error}`
                : undefined;
              // Bloc B1 — liens sociaux cliquables (verification avant approbation).
              const socialEntries = Object.entries(e.social_links || {}).filter(
                ([platform, handle]) => SOCIAL_URL_BUILDERS[platform] && !!handle
              );
              return (
                <View>
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
                        {!!e.requested_ip && (
                          <Text style={styles.candidatesDateText}>IP {e.requested_ip}</Text>
                        )}
                        {e.pending_vote_value === 1 && (
                          <Text style={styles.candidatesImplicitLike}>👍 like implicite</Text>
                        )}
                      </View>
                    }
                  />
                  {socialEntries.length > 0 ? (
                    <View style={styles.candidatesSocialRow}>
                      {socialEntries.map(([platform, handle]) => {
                        const url = SOCIAL_URL_BUILDERS[platform](handle);
                        const formatOk = e.social_links_format_ok?.[platform] !== false;
                        return (
                          <TouchableOpacity
                            key={platform}
                            style={styles.candidatesSocialChip}
                            onPress={() => Linking.openURL(url).catch(() => {})}
                            activeOpacity={0.7}
                          >
                            <Ionicons name="link-outline" size={13} color={PALETTE.gold} />
                            <Text style={styles.candidatesSocialChipText} numberOfLines={1}>
                              {SOCIAL_LABELS[platform] || platform} · @{handle}
                            </Text>
                            {!formatOk && (
                              <Text style={styles.candidatesSocialWarn}>⚠︎</Text>
                            )}
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  ) : (
                    <Text style={styles.candidatesSocialEmpty}>Aucun lien social fourni</Text>
                  )}
                </View>
              );
            }}
            actions={(e) => [
              {
                label: 'Approuver',
                icon: 'checkmark-circle',
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

// ---------- Vague 4 sous-tache 2 — Section Outsiders signales ----------

const REASON_FR: Record<string, string> = {
  spam: 'spam',
  inappropriate: 'inapproprie',
  fake: 'faux profil',
  offensive: 'offensant',
  // Bloc B2 — motifs specifiques aux Personnalites UGC
  impersonation: 'usurpation',
  minor: 'mineur',
  other: 'autre',
};

function formatReasonsSummary(summary: Record<string, number>): string {
  const entries = Object.entries(summary || {});
  if (entries.length === 0) return '';
  return entries
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${REASON_FR[k] || k} (${v})`)
    .join(' • ');
}

function statusBadgeStyle(status: OutsiderReportStatus) {
  switch (status) {
    case 'warned':  return { color: '#FFB44C' };
    case 'ignored': return { color: PALETTE.subtext };
    case 'deleted': return { color: PALETTE.accent };
    case 'pending':
    default:        return { color: PALETTE.gold };
  }
}

function statusLabel(status: OutsiderReportStatus): string {
  switch (status) {
    case 'warned':  return 'Averti';
    case 'ignored': return 'Classe sans suite';
    case 'deleted': return 'Retire';
    case 'pending':
    default:        return 'En attente';
  }
}

interface OutsiderReportsSectionProps {
  reports: OutsiderReportGroup[];
  loading: boolean;
  error: string | null;
  filter: OutsiderReportsFilter;
  onFilterChange: (f: OutsiderReportsFilter) => void;
  onRefresh: () => void;
  onIgnore: (g: OutsiderReportGroup) => void;
  onWarn: (g: OutsiderReportGroup) => void;
  onDelete: (g: OutsiderReportGroup) => void;
}

function OutsiderReportsSection({
  reports,
  loading,
  error,
  filter,
  onFilterChange,
  onRefresh,
  onIgnore,
  onWarn,
  onDelete,
}: OutsiderReportsSectionProps) {
  const pendingCount = reports.length; // backend filtre deja, donc length = nb d'Outsiders dans le filtre courant
  return (
    <View>
      {/* Header */}
      <View style={[styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>🚩 Outsiders signales</Text>
            <Text style={styles.candidatesHeaderCount}>
              {pendingCount} Outsider{pendingCount > 1 ? 's' : ''} {filter === 'pending' ? 'en attente' : 'au total'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={onRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>

        {/* Toggle filter */}
        <View style={styles.outsiderFilterRow}>
          {(['pending', 'all'] as OutsiderReportsFilter[]).map((f) => {
            const active = filter === f;
            return (
              <TouchableOpacity
                key={f}
                onPress={() => onFilterChange(f)}
                style={[styles.outsiderFilterChip, active && styles.outsiderFilterChipActive]}
              >
                <Text style={[styles.outsiderFilterChipText, active && styles.outsiderFilterChipTextActive]}>
                  {f === 'pending' ? 'En attente' : 'Tous'}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : error ? (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{error}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewList<OutsiderReportGroup>
          data={reports}
          keyExtractor={(g) => g.outsider_person_id}
          emptyText={filter === 'pending' ? 'Aucun signalement en attente' : 'Aucun signalement'}
          renderItem={(g) => {
            const latest = g.reports && g.reports.length > 0 ? g.reports[0] : null;
            const currentStatus: OutsiderReportStatus = latest?.status || 'pending';
            const reasonsLine = formatReasonsSummary(g.reasons_summary);
            const lastComment = latest?.comment && latest.comment.trim().length > 0
              ? latest.comment.length > 140
                ? `« ${latest.comment.slice(0, 137)}... »`
                : `« ${latest.comment} »`
              : null;
            const subline = [reasonsLine, lastComment].filter(Boolean).join(' — ') || undefined;
            return (
              <View style={!g.person_exists ? { opacity: 0.7 } : undefined}>
                <AdminCard
                  person={{
                    id: g.outsider_person_id,
                    name: g.outsider_name || '(sans nom)',
                  }}
                  subline={subline}
                  rightSlot={
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.outsiderReportCount}>
                        {g.report_count} signalement{g.report_count > 1 ? 's' : ''}
                      </Text>
                      {latest?.created_at && (
                        <Text style={styles.candidatesDateText}>{formatRelativeShort(latest.created_at)}</Text>
                      )}
                      <Text style={[styles.outsiderStatusBadge, statusBadgeStyle(currentStatus)]}>
                        {statusLabel(currentStatus)}
                      </Text>
                    </View>
                  }
                />
                {/* Bandeau info: email owner + profil supprime */}
                <View style={styles.outsiderInfoRow}>
                  {g.person_email ? (
                    <Text style={styles.outsiderInfoText} numberOfLines={1}>
                      ✉ {g.person_email}
                    </Text>
                  ) : (
                    <Text style={[styles.outsiderInfoText, { color: '#FFB44C' }]}>
                      ✉ Aucun email connu
                    </Text>
                  )}
                  {!g.person_exists && (
                    <Text style={styles.outsiderDeletedTag}>Outsider supprime</Text>
                  )}
                </View>
              </View>
            );
          }}
          actions={(g) => {
            const latest = g.reports && g.reports.length > 0 ? g.reports[0] : null;
            // Actions uniquement si le groupe est encore actionnable (status pending)
            if (!latest || latest.status !== 'pending') return [];
            // Si le profil n'existe plus, seul ignore est utile
            if (!g.person_exists) {
              return [
                {
                  label: 'Classer sans suite',
                  icon: 'checkmark-outline',
                  variant: 'neutral',
                  onPress: () => onIgnore(g),
                },
              ];
            }
            return [
              {
                label: 'Ignorer',
                icon: 'checkmark-outline',
                variant: 'neutral',
                onPress: () => onIgnore(g),
              },
              {
                label: 'Avertir (email)',
                icon: 'mail-outline',
                variant: 'primary',
                onPress: () => onWarn(g),
                disabled: !g.person_email,
              },
              {
                label: 'Retirer Outsider',
                icon: 'ban',
                variant: 'danger',
                onPress: () => onDelete(g),
              },
            ];
          }}
        />
      )}
    </View>
  );
}

// ---------- Bloc B2 — Section Personnalites signalees (lecture seule) ----------
// Miroir allege de OutsiderReportsSection : liste groupee par Personnalite UGC, motifs,
// dernier commentaire. Pas d'actions ici (approbation/refus = onglet Candidats ;
// auto-masquage a seuil = Bloc C). Objectif : rendre chaque signalement consultable.

interface PersonalityReportsSectionProps {
  reports: PersonalityReportGroup[];
  loading: boolean;
  error: string | null;
  filter: OutsiderReportsFilter;
  onFilterChange: (f: OutsiderReportsFilter) => void;
  onRefresh: () => void;
  onRestore: (g: PersonalityReportGroup) => void;
}

function PersonalityReportsSection({
  reports,
  loading,
  error,
  filter,
  onFilterChange,
  onRefresh,
  onRestore,
}: PersonalityReportsSectionProps) {
  const count = reports.length;
  return (
    <View style={{ marginTop: 8 }}>
      {/* Header */}
      <View style={[styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>🚩 Personnalites signalees</Text>
            <Text style={styles.candidatesHeaderCount}>
              {count} personnalite{count > 1 ? 's' : ''} {filter === 'pending' ? 'en attente' : 'au total'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={onRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>

        {/* Toggle filter */}
        <View style={styles.outsiderFilterRow}>
          {(['pending', 'all'] as OutsiderReportsFilter[]).map((f) => {
            const active = filter === f;
            return (
              <TouchableOpacity
                key={f}
                onPress={() => onFilterChange(f)}
                style={[styles.outsiderFilterChip, active && styles.outsiderFilterChipActive]}
              >
                <Text style={[styles.outsiderFilterChipText, active && styles.outsiderFilterChipTextActive]}>
                  {f === 'pending' ? 'En attente' : 'Tous'}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : error ? (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{error}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewList<PersonalityReportGroup>
          data={reports}
          keyExtractor={(g) => g.person_id}
          emptyText={filter === 'pending' ? 'Aucun signalement en attente' : 'Aucun signalement'}
          renderItem={(g) => {
            const latest = g.reports && g.reports.length > 0 ? g.reports[0] : null;
            const reasonsLine = formatReasonsSummary(g.reasons_summary);
            const lastComment = latest?.comment && latest.comment.trim().length > 0
              ? latest.comment.length > 140
                ? `« ${latest.comment.slice(0, 137)}... »`
                : `« ${latest.comment} »`
              : null;
            const subline = [reasonsLine, lastComment].filter(Boolean).join(' — ') || undefined;
            return (
              <View style={!g.person_exists ? { opacity: 0.7 } : undefined}>
                <AdminCard
                  person={{
                    id: g.person_id,
                    name: g.person_name || '(sans nom)',
                  }}
                  subline={subline}
                  rightSlot={
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.outsiderReportCount}>
                        {g.report_count} signalement{g.report_count > 1 ? 's' : ''}
                      </Text>
                      {latest?.created_at && (
                        <Text style={styles.candidatesDateText}>{formatRelativeShort(latest.created_at)}</Text>
                      )}
                      {g.auto_hidden && (
                        <Text style={styles.personalityAutoHiddenTag}>🫥 Auto-masquee</Text>
                      )}
                      {!g.person_exists && (
                        <Text style={styles.outsiderDeletedTag}>Profil supprime</Text>
                      )}
                    </View>
                  }
                />
              </View>
            );
          }}
          actions={(g) => (g.auto_hidden ? [
            {
              label: 'Re-afficher',
              icon: 'eye-outline',
              variant: 'primary',
              onPress: () => onRestore(g),
            },
          ] : [])}
        />
      )}
    </View>
  );
}

// ---------- Vague 4 sous-tache 5 — Section Ajout manuel ----------
// UI focalisee sur /admin/propose-celebrity (creation immediate, validation Wikidata pipeline).
// Skip volontaire des endpoints /propose-celebrity-to-queue (legacy, doublon visuel avec onglet
// Candidats) et /add-celebrities-batch (seeding marketing avec votes random, pas un outil admin).

interface ManualAddSectionProps {
  name: string;
  onNameChange: (v: string) => void;
  category: CandidateCategory;
  onCategoryChange: (c: CandidateCategory) => void;
  loading: boolean;
  error: string | null;
  lastCreation: ManualAddLastCreation | null;
  onSubmit: () => void;
}

function ManualAddSection({
  name,
  onNameChange,
  category,
  onCategoryChange,
  loading,
  error,
  lastCreation,
  onSubmit,
}: ManualAddSectionProps) {
  const trimmed = name.trim();
  const localErr = trimmed ? validateManualAddName(trimmed) : null;
  // Le bouton est disabled si: chargement en cours, ou input vide, ou validation locale en echec.
  const disabled = loading || !trimmed || !!localErr;

  return (
    <View>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>➕ Ajout manuel</Text>
        <Text style={styles.manualAddIntro}>
          Cree une celebrite IMMEDIATEMENT. Le backend verifie Wikipedia/Wikidata (humain
          vivant, score de visibilite minimal) puis publie en categorie choisie avec son
          Popularoo Index initial.
        </Text>

        <View style={styles.card}>
          <Text style={styles.manualAddLabel}>Nom complet</Text>
          <TextInput
            style={styles.manualAddInput}
            value={name}
            onChangeText={onNameChange}
            placeholder="Ex: Pope Leo XIV"
            placeholderTextColor={PALETTE.subtext}
            autoCapitalize="words"
            autoCorrect={false}
            editable={!loading}
          />
          <Text style={styles.manualAddHelper}>
            Prenom + nom (2 mots minimum). Pas de chiffres. Orthographe Wikipedia anglais
            recommandee pour optimiser la detection.
          </Text>

          <Text style={[styles.manualAddLabel, { marginTop: 16 }]}>Categorie</Text>
          <View style={styles.manualAddCategoryRow}>
            {CANDIDATE_CATEGORIES.map((c) => {
              const active = c === category;
              return (
                <TouchableOpacity
                  key={c}
                  onPress={() => onCategoryChange(c)}
                  disabled={loading}
                  style={[
                    styles.manualAddCategoryChip,
                    active && styles.manualAddCategoryChipActive,
                    loading && { opacity: 0.5 },
                  ]}
                >
                  <Text
                    style={[
                      styles.manualAddCategoryChipText,
                      active && styles.manualAddCategoryChipTextActive,
                    ]}
                  >
                    {c}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <TouchableOpacity
            onPress={onSubmit}
            disabled={disabled}
            style={[
              styles.manualAddSubmitBtn,
              disabled && styles.manualAddSubmitBtnDisabled,
            ]}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color="#000" />
            ) : (
              <>
                <Ionicons name="flash" size={18} color="#000" />
                <Text style={styles.manualAddSubmitBtnText}>Creer maintenant</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Erreur (validation locale OU backend) */}
          {!!(error || localErr) && (
            <View style={styles.manualAddErrorBox}>
              <Ionicons name="alert-circle" size={16} color={PALETTE.accent} />
              <Text style={styles.manualAddErrorText}>{error || localErr}</Text>
            </View>
          )}
        </View>

        {/* Recap ephemere (3s) — feedback immediat sur ce que le backend a determine */}
        {lastCreation && (
          <View style={styles.manualAddLastCard}>
            <View style={styles.manualAddLastHeader}>
              <Ionicons name="checkmark-circle" size={18} color={PALETTE.green} />
              <Text style={styles.manualAddLastTitle}>Derniere creation</Text>
            </View>
            <Text style={styles.manualAddLastName}>{lastCreation.name}</Text>
            <Text style={styles.manualAddLastMeta}>
              Categorie: {lastCreation.category} • PI{' '}
              <Text style={styles.manualAddLastPi}>
                {lastCreation.popularoo_index.toFixed(1)}
              </Text>{' '}
              • Score externe {lastCreation.popularity_external_score.toFixed(1)}
            </Text>
            {lastCreation.wikipedia_langs.length > 0 && (
              <Text style={styles.manualAddLastMeta}>
                Wikipedia: {lastCreation.wikipedia_langs.join(', ')}
              </Text>
            )}
          </View>
        )}

        {/* Bloc info permanent en bas: oriente vers les autres flux d'ajout */}
        <View style={styles.manualAddInfoCard}>
          <Ionicons name="information-circle-outline" size={18} color={PALETTE.subtext} />
          <View style={{ flex: 1 }}>
            <Text style={styles.manualAddInfoText}>
              <Text style={{ fontWeight: '700' }}>Soumettre puis valider plus tard ?</Text>{' '}
              Les demandes utilisateur passent par la file 24h, gerable depuis l'onglet
              Candidats.
            </Text>
            <Text style={[styles.manualAddInfoText, { marginTop: 6 }]}>
              <Text style={{ fontWeight: '700' }}>Ajout en masse ?</Text> Reserve aux scripts
              de seeding (commande backend), pas exposee en UI admin.
            </Text>
          </View>
        </View>
      </View>
    </View>
  );
}

// ---------- Vague 4 sous-tache 3 — Section Decedes ----------
// Tone neutre, professionnel: pas de rouge, pas d'emojis dans les Alerts (mort de personnes
// reelles). Variants 'neutral' pour les actions; la modale de confirmation porte la gravite.

// Wikidata renvoie le death_date au format ISO precede d'un '+' (ex: "+2024-11-28T00:00:00Z").
// Cas particuliers: "unknown", "unknown_date" ou chaine vide -> "Date inconnue".
function formatDeathDateFR(raw: string | null | undefined): string {
  if (!raw) return 'Date inconnue';
  if (raw === 'unknown' || raw === 'unknown_date') return 'Date inconnue';
  const cleaned = raw.startsWith('+') ? raw.slice(1) : raw;
  const ts = Date.parse(cleaned);
  if (Number.isNaN(ts)) return 'Date inconnue';
  const d = new Date(ts);
  return `${d.getDate()} ${FR_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

interface DeceasedSectionProps {
  items: DeceasedItem[];
  loading: boolean;
  error: string | null;
  runChecking: boolean;
  bulkConfirming: boolean;
  onRefresh: () => void;
  onConfirm: (item: DeceasedItem) => void;
  onReject: (item: DeceasedItem) => void;
  onConfirmAll: () => void;
  onRunCheck: () => void;
}

function DeceasedSection({
  items,
  loading,
  error,
  runChecking,
  bulkConfirming,
  onRefresh,
  onConfirm,
  onReject,
  onConfirmAll,
  onRunCheck,
}: DeceasedSectionProps) {
  const count = items.length;
  const bulkDisabled = count === 0 || bulkConfirming || runChecking;
  const runDisabled = runChecking || bulkConfirming;

  return (
    <View>
      {/* Header */}
      <View style={[styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>Profils decedes a verifier</Text>
            <Text style={styles.candidatesHeaderCount}>
              {count} deces a verifier
            </Text>
          </View>
          <TouchableOpacity
            onPress={onRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>

        {/* Actions header: detection manuelle + bulk confirm */}
        <View style={styles.deceasedHeaderActions}>
          <TouchableOpacity
            onPress={onRunCheck}
            disabled={runDisabled}
            style={[styles.deceasedHeaderBtn, runDisabled && { opacity: 0.5 }]}
            activeOpacity={0.8}
          >
            {runChecking ? (
              <ActivityIndicator color={PALETTE.text} size="small" />
            ) : (
              <Ionicons name="search-outline" size={16} color={PALETTE.text} />
            )}
            <Text style={styles.deceasedHeaderBtnText}>
              {runChecking ? 'Detection en cours...' : 'Lancer la detection'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={onConfirmAll}
            disabled={bulkDisabled}
            style={[
              styles.deceasedHeaderBtn,
              styles.deceasedHeaderBtnAccent,
              bulkDisabled && { opacity: 0.5 },
            ]}
            activeOpacity={0.8}
          >
            {bulkConfirming ? (
              <ActivityIndicator color={PALETTE.text} size="small" />
            ) : (
              <Ionicons name="checkmark-done-outline" size={16} color={PALETTE.text} />
            )}
            <Text style={styles.deceasedHeaderBtnText}>
              {bulkConfirming ? 'Confirmation...' : `Confirmer tout${count > 0 ? ` (${count})` : ''}`}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : error ? (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{error}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewList<DeceasedItem>
          data={items}
          keyExtractor={(it) => it.id}
          emptyText="Aucun deces a verifier"
          renderItem={(it) => {
            const deathLabel = formatDeathDateFR(it.death_date);
            const detectedRel = formatDateFR(it.detected_at);
            const catFr = categoryFR(it.category);
            const wikiHref = it.wikidata_id
              ? `https://www.wikidata.org/wiki/${it.wikidata_id}`
              : null;
            return (
              <View>
                <AdminCard
                  person={{
                    id: it.id,
                    name: it.name,
                    category: it.category,
                  }}
                  rightSlot={
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.deceasedDeathDate}>{deathLabel}</Text>
                      {!!detectedRel && (
                        <Text style={styles.candidatesDateText}>Detecte {detectedRel}</Text>
                      )}
                      <Text style={styles.deceasedCategoryTag}>{catFr}</Text>
                    </View>
                  }
                />
                <View style={styles.deceasedSourceRow}>
                  {wikiHref ? (
                    <TouchableOpacity
                      onPress={() => Linking.openURL(wikiHref).catch(() => {})}
                      hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                    >
                      <Text style={styles.deceasedSourceLink}>
                        Source : Wikidata {it.wikidata_id} (P570) ↗
                      </Text>
                    </TouchableOpacity>
                  ) : (
                    <Text style={styles.deceasedSourceText}>Source : Wikidata P570</Text>
                  )}
                </View>
              </View>
            );
          }}
          actions={(it) => [
            {
              label: 'Confirmer le deces',
              icon: 'checkmark-circle-outline',
              variant: 'neutral',
              onPress: () => onConfirm(it),
            },
            {
              label: 'Faux positif',
              icon: 'close-circle-outline',
              variant: 'neutral',
              onPress: () => onReject(it),
            },
          ]}
        />
      )}
    </View>
  );
}

// ---------- Vague 4 sous-tache 4 — Categories ----------
// Confiance: backend renvoie "high"/"medium"/"low" -> label FR + code-couleur valide par Didier
// (vert/orange/gris neutre). Pas de pourcentage (cf reconnaissance).
function confidenceFR(c: string | null | undefined): string {
  switch ((c || '').toLowerCase()) {
    case 'high': return 'Confiance elevee';
    case 'medium': return 'Confiance moyenne';
    case 'low': return 'Confiance faible';
    default: return 'Confiance inconnue';
  }
}

function confidenceRank(c: string | null | undefined): number {
  switch ((c || '').toLowerCase()) {
    case 'high': return 3;
    case 'medium': return 2;
    case 'low': return 1;
    default: return 0;
  }
}

function confidenceBadgeStyle(c: string | null | undefined) {
  switch ((c || '').toLowerCase()) {
    case 'high': return { bg: '#1F4D2E', fg: '#7FD99B', border: '#2F6D43' };
    case 'medium': return { bg: '#4A3416', fg: '#E8B26A', border: '#6A4E26' };
    case 'low': return { bg: '#2A2A30', fg: '#A0A0A8', border: '#3A3A42' };
    default: return { bg: '#2A2A30', fg: '#A0A0A8', border: '#3A3A42' };
  }
}

interface CategoriesSectionProps {
  items: CategoryReviewItem[];
  loading: boolean;
  error: string | null;
  running: boolean;
  onRefresh: () => void;
  onApply: (item: CategoryReviewItem) => void;
  onReject: (item: CategoryReviewItem) => void;
  onRunReview: () => void;
}

function CategoriesSection({
  items,
  loading,
  error,
  running,
  onRefresh,
  onApply,
  onReject,
  onRunReview,
}: CategoriesSectionProps) {
  // Tri client confiance DESC puis created_at DESC (le backend trie deja created_at desc).
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      const rankDiff = confidenceRank(b.confidence) - confidenceRank(a.confidence);
      if (rankDiff !== 0) return rankDiff;
      const ta = a.created_at ? Date.parse(a.created_at) : 0;
      const tb = b.created_at ? Date.parse(b.created_at) : 0;
      return tb - ta;
    });
  }, [items]);
  const count = sorted.length;
  const runDisabled = running;

  return (
    <View>
      <View style={[styles.section, { paddingBottom: 0 }]}>
        <View style={styles.candidatesHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sectionTitle}>Categories a reviser</Text>
            <Text style={styles.candidatesHeaderCount}>
              {count} revision{count > 1 ? 's' : ''} en attente
            </Text>
          </View>
          <TouchableOpacity
            onPress={onRefresh}
            style={styles.candidatesRefreshBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="refresh-outline" size={20} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>

        <View style={styles.deceasedHeaderActions}>
          <TouchableOpacity
            onPress={onRunReview}
            disabled={runDisabled}
            style={[styles.deceasedHeaderBtn, runDisabled && { opacity: 0.5 }]}
            activeOpacity={0.8}
          >
            {running ? (
              <ActivityIndicator color={PALETTE.text} size="small" />
            ) : (
              <Ionicons name="search-outline" size={16} color={PALETTE.text} />
            )}
            <Text style={styles.deceasedHeaderBtnText}>
              {running ? 'Audit en cours...' : "Lancer l'audit"}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={PALETTE.gold} />
        </View>
      ) : error ? (
        <View style={styles.section}>
          <View style={styles.card}>
            <Text style={styles.candidatesErrorText}>{error}</Text>
            <TouchableOpacity style={styles.candidatesRetryBtn} onPress={onRefresh}>
              <Ionicons name="refresh" size={16} color="#000" />
              <Text style={styles.candidatesRetryBtnText}>Reessayer</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <ReviewList<CategoryReviewItem>
          data={sorted}
          keyExtractor={(it) => it.id}
          emptyText="Aucune revision de categorie en attente"
          renderItem={(it) => {
            const currentFr = categoryFR(it.current_category);
            const suggestedFr = categoryFR(it.suggested_category);
            const detectedRel = formatDateFR(it.created_at);
            const badge = confidenceBadgeStyle(it.confidence);
            const wikiTitle = encodeURIComponent((it.name || '').replace(/ /g, '_'));
            const wikiHref = wikiTitle ? `https://en.wikipedia.org/wiki/${wikiTitle}` : null;
            return (
              <View>
                <AdminCard
                  person={{
                    id: it.id,
                    name: it.name,
                    category: it.current_category,
                  }}
                  rightSlot={
                    <View
                      style={[
                        styles.categoryConfidenceBadge,
                        { backgroundColor: badge.bg, borderColor: badge.border },
                      ]}
                    >
                      <Text style={[styles.categoryConfidenceBadgeText, { color: badge.fg }]}>
                        {confidenceFR(it.confidence)}
                      </Text>
                    </View>
                  }
                />

                <View style={styles.categoryTransitionRow}>
                  <View style={[styles.categoryBadge, styles.categoryBadgeCurrent]}>
                    <Text style={styles.categoryBadgeCurrentText}>{currentFr}</Text>
                  </View>
                  <Ionicons name="arrow-forward" size={14} color={PALETTE.gold} />
                  <View style={[styles.categoryBadge, styles.categoryBadgeSuggested]}>
                    <Text style={styles.categoryBadgeSuggestedText}>{suggestedFr}</Text>
                  </View>
                </View>

                {!!it.wiki_description && (
                  <Text style={styles.categoryWikiDescription} numberOfLines={2}>
                    « {it.wiki_description} »
                  </Text>
                )}

                <View style={styles.deceasedSourceRow}>
                  <View style={styles.categorySourceRowInner}>
                    {!!detectedRel && (
                      <Text style={styles.candidatesDateText}>Detecte {detectedRel}</Text>
                    )}
                    {wikiHref ? (
                      <TouchableOpacity
                        onPress={() => Linking.openURL(wikiHref).catch(() => {})}
                        hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                      >
                        <Text style={styles.deceasedSourceLink}>Voir sur Wikipedia ↗</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              </View>
            );
          }}
          actions={(it) => [
            {
              label: 'Appliquer la correction',
              icon: 'checkmark-circle-outline',
              variant: 'primary',
              onPress: () => onApply(it),
            },
            {
              label: "Garder l'actuelle",
              icon: 'close-circle-outline',
              variant: 'neutral',
              onPress: () => onReject(it),
            },
          ]}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: THEME.plane },
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
  // ── Top bar (Phase B1) ──
  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: THEME.hairline,
  },
  topbarBack: { padding: 4 },
  topbarLogo: {
    width: 30,
    height: 30,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  topbarLogoText: { color: '#fff', fontSize: 17, fontWeight: '800' },
  topbarTitle: { color: THEME.ink, fontSize: 15, fontWeight: '600', flexShrink: 1, marginLeft: 2 },
  topbarIcon: { padding: 6 },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: THEME.surface2,
    borderRadius: THEME.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: THEME.hairline,
  },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  statusPillText: { color: THEME.ink2, fontSize: 11.5, fontWeight: '600' },
  // ── Barre d'onglets (pills, Phase B1) ──
  tabBarWrapper: { position: 'relative' },
  tabBar: { flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 16 },
  tabBarFade: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    width: 40,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingVertical: 8,
    paddingHorizontal: 13,
    borderRadius: THEME.radius.pill,
    marginRight: 8,
    backgroundColor: THEME.surface,
    borderWidth: 1,
    borderColor: THEME.hairline,
  },
  tabActive: { backgroundColor: THEME.accentSoft, borderColor: THEME.accent },
  tabText: { color: THEME.ink2, fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: THEME.ink },
  tabBadge: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 2,
  },
  tabBadgeText: { color: '#1a1a19', fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] },
  loadingContainer: { padding: 40, alignItems: 'center' },

  // ══════════ Phase B2 — Dashboard cockpit (THEME) ══════════
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, paddingHorizontal: 12, paddingTop: 12 },
  kpiTile: {
    flexBasis: '47%',
    flexGrow: 1,
    backgroundColor: THEME.surface,
    borderRadius: THEME.radius.card,
    borderWidth: 1,
    borderColor: THEME.hairline,
    paddingVertical: 14,
    paddingHorizontal: 15,
    overflow: 'hidden',
  },
  kpiAccentBar: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, backgroundColor: THEME.accent },
  kpiLabel: { color: THEME.muted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  kpiValue: { color: THEME.ink, fontSize: 30, fontWeight: '700', marginTop: 6, fontVariant: ['tabular-nums'] },
  kpiSub: { fontSize: 11.5, marginTop: 3 },

  panel: {
    backgroundColor: THEME.surface,
    borderRadius: THEME.radius.card,
    borderWidth: 1,
    borderColor: THEME.hairline,
    marginHorizontal: 12,
    marginTop: 12,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  panelHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 },
  panelTitle: { color: THEME.ink, fontSize: 13.5, fontWeight: '700' },
  panelCount: { color: THEME.muted, fontSize: 12 },

  rowLine: { flexDirection: 'row', alignItems: 'center', gap: 11, paddingVertical: 10, borderTopWidth: 1, borderTopColor: THEME.hairline },
  modIcon: { width: 30, height: 30, borderRadius: 8, backgroundColor: THEME.surface2, alignItems: 'center', justifyContent: 'center' },
  modTitle: { color: THEME.ink, fontSize: 13.5, fontWeight: '600' },
  modSub: { color: THEME.muted, fontSize: 11.5, marginTop: 1 },
  modBadge: { minWidth: 22, height: 20, borderRadius: 10, paddingHorizontal: 6, backgroundColor: THEME.surface2, borderWidth: 1, borderColor: THEME.hairline, alignItems: 'center', justifyContent: 'center' },
  modBadgeText: { color: THEME.ink2, fontSize: 12, fontWeight: '700', fontVariant: ['tabular-nums'] },
  btnPrimary: { backgroundColor: THEME.accent, borderRadius: THEME.radius.btn, paddingHorizontal: 12, paddingVertical: 7 },
  btnPrimaryText: { color: '#fff', fontSize: 12.5, fontWeight: '600' },
  btnPlain: { backgroundColor: THEME.surface2, borderRadius: THEME.radius.btn, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: THEME.hairline },
  btnPlainText: { color: THEME.ink2, fontSize: 12.5, fontWeight: '600' },

  top5Row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9, borderTopWidth: 1, borderTopColor: THEME.hairline },
  top5Rank: { color: THEME.muted, fontSize: 13, width: 16, fontVariant: ['tabular-nums'] },
  top5Flag: { fontSize: 15 },
  top5Name: { color: THEME.ink, fontSize: 13.5, flex: 1 },
  catChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  catChipText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  top5Index: { color: THEME.ink, fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'], marginLeft: 4 },

  catBarRow: { marginTop: 11 },
  catBarHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 },
  catBarLabel: { color: THEME.ink2, fontSize: 12 },
  catBarPct: { color: THEME.muted, fontSize: 12, fontVariant: ['tabular-nums'] },
  catBarTrack: { height: 7, borderRadius: 4, backgroundColor: THEME.surface2, overflow: 'hidden' },
  catBarFill: { height: 7, borderRadius: 4 },

  actRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderTopWidth: 1, borderTopColor: THEME.hairline },
  actDot: { width: 8, height: 8, borderRadius: 4 },
  actText: { color: THEME.ink, fontSize: 13, flex: 1 },
  actTime: { color: THEME.muted, fontSize: 11, marginLeft: 8 },

  pipeRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderTopWidth: 1, borderTopColor: THEME.hairline },
  pipeLabel: { color: THEME.ink2, fontSize: 12.5 },
  pipeValue: { color: THEME.ink, fontSize: 12.5, fontWeight: '600', fontVariant: ['tabular-nums'] },

  footerNote: { color: THEME.muted, fontSize: 11, fontStyle: 'italic', lineHeight: 15, padding: 14, marginTop: 4 },

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
  // Rename Outsider modal
  renameOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  renameCard: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 20,
  },
  renameTitle: { color: PALETTE.text, fontSize: 18, fontWeight: '700', marginBottom: 6 },
  renameSub: { color: PALETTE.subtext, fontSize: 13, marginBottom: 12 },
  renameInput: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: PALETTE.text,
    fontSize: 16,
    marginTop: 4,
  },
  renameActions: { flexDirection: 'row', gap: 12, marginTop: 16 },
  renameBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  renameBtnCancel: { backgroundColor: PALETTE.bg, borderWidth: 1, borderColor: PALETTE.border },
  renameBtnCancelText: { color: PALETTE.text, fontSize: 15, fontWeight: '600' },
  renameBtnConfirm: { backgroundColor: PALETTE.green },
  renameBtnConfirmText: { color: '#000', fontSize: 15, fontWeight: '700' },
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
  candidatesImplicitLike: {
    color: PALETTE.green,
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  // Bloc B1 — liens sociaux cliquables sous la carte de proposition
  candidatesSocialRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 6,
    marginLeft: 4,
  },
  candidatesSocialChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    maxWidth: '100%',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    backgroundColor: PALETTE.bg,
  },
  candidatesSocialChipText: {
    color: PALETTE.gold,
    fontSize: 12,
    fontWeight: '600',
    flexShrink: 1,
  },
  candidatesSocialWarn: {
    color: '#E0A800',
    fontSize: 12,
    fontWeight: '700',
  },
  candidatesSocialEmpty: {
    color: PALETTE.subtext,
    fontSize: 11,
    fontStyle: 'italic',
    marginTop: 6,
    marginLeft: 4,
  },

  // ---------- Styles Vague 4 sous-tache 2 — Outsiders signales ----------
  outsiderFilterRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
    marginTop: 4,
  },
  outsiderFilterChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    backgroundColor: PALETTE.card,
  },
  outsiderFilterChipActive: {
    borderColor: PALETTE.gold,
    backgroundColor: PALETTE.gold + '22',
  },
  outsiderFilterChipText: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontWeight: '700',
  },
  outsiderFilterChipTextActive: {
    color: PALETTE.gold,
  },
  outsiderReportCount: {
    color: PALETTE.gold,
    fontSize: 13,
    fontWeight: '700',
  },
  outsiderStatusBadge: {
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  outsiderInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
  },
  outsiderInfoText: {
    color: PALETTE.subtext,
    fontSize: 12,
    flex: 1,
  },
  outsiderDeletedTag: {
    color: PALETTE.accent,
    fontSize: 11,
    fontWeight: '700',
  },
  // Bloc C (2) — badge auto-masquage
  personalityAutoHiddenTag: {
    color: '#E0A800',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },

  // ---------- Styles Vague 4 sous-tache 3 — Decedes ----------
  // Tone sobre: gris-bleu pour les boutons header, pas de rouge accent.
  deceasedHeaderActions: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
    marginTop: 4,
  },
  deceasedHeaderBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: PALETTE.bg,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  // Variante "accent neutre" pour le bouton bulk: bordure plus marquee, fond legerement different,
  // sans rouge. Distingue visuellement l'action de masse sans dramatiser.
  deceasedHeaderBtnAccent: {
    backgroundColor: '#1A4A6A',
    borderColor: '#2A6A8A',
  },
  deceasedHeaderBtnText: {
    color: PALETTE.text,
    fontSize: 13,
    fontWeight: '600',
  },
  deceasedDeathDate: {
    color: PALETTE.text,
    fontSize: 13,
    fontWeight: '700',
  },
  deceasedCategoryTag: {
    color: PALETTE.subtext,
    fontSize: 11,
    marginTop: 2,
    fontStyle: 'italic',
  },
  deceasedSourceRow: {
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
  },
  deceasedSourceLink: {
    color: '#7AB8E0',
    fontSize: 11,
    fontWeight: '600',
  },
  deceasedSourceText: {
    color: PALETTE.subtext,
    fontSize: 11,
  },

  // ---------- Styles Vague 4 sous-tache 4 — Categories ----------
  categoryConfidenceBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
    borderWidth: 1,
  },
  categoryConfidenceBadgeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  categoryTransitionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 12,
    flexWrap: 'wrap',
  },
  categoryBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
  },
  categoryBadgeCurrent: {
    backgroundColor: PALETTE.bg,
    borderColor: PALETTE.border,
  },
  categoryBadgeCurrentText: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontWeight: '600',
  },
  categoryBadgeSuggested: {
    backgroundColor: PALETTE.gold + '22',
    borderColor: PALETTE.gold,
  },
  categoryBadgeSuggestedText: {
    color: PALETTE.gold,
    fontSize: 12,
    fontWeight: '700',
  },
  categoryWikiDescription: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 10,
    fontStyle: 'italic',
    lineHeight: 17,
  },
  categorySourceRowInner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },

  // ---------- Styles Vague 4 sous-tache 5 — Ajout manuel ----------
  manualAddIntro: {
    color: PALETTE.subtext,
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 16,
  },
  manualAddLabel: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
  },
  manualAddInput: {
    backgroundColor: PALETTE.bg,
    borderWidth: 2,
    borderColor: PALETTE.border,
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 14,
    color: PALETTE.text,
    fontSize: 16,
  },
  manualAddHelper: {
    color: PALETTE.subtext,
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 6,
    lineHeight: 16,
  },
  manualAddCategoryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  manualAddCategoryChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    backgroundColor: PALETTE.bg,
  },
  manualAddCategoryChipActive: {
    borderColor: PALETTE.gold,
    backgroundColor: PALETTE.gold + '22',
  },
  manualAddCategoryChipText: {
    color: PALETTE.subtext,
    fontSize: 13,
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  manualAddCategoryChipTextActive: {
    color: PALETTE.gold,
  },
  manualAddSubmitBtn: {
    marginTop: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    paddingVertical: 14,
  },
  manualAddSubmitBtnDisabled: {
    opacity: 0.4,
  },
  manualAddSubmitBtnText: {
    color: '#000',
    fontSize: 15,
    fontWeight: '700',
  },
  manualAddErrorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginTop: 12,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: PALETTE.accent + '22',
    borderLeftWidth: 3,
    borderLeftColor: PALETTE.accent,
    borderRadius: 6,
  },
  manualAddErrorText: {
    color: PALETTE.text,
    fontSize: 13,
    flex: 1,
    lineHeight: 18,
  },
  manualAddLastCard: {
    marginTop: 16,
    padding: 14,
    borderRadius: 10,
    backgroundColor: PALETTE.green + '15',
    borderLeftWidth: 3,
    borderLeftColor: PALETTE.green,
  },
  manualAddLastHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 6,
  },
  manualAddLastTitle: {
    color: PALETTE.green,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  manualAddLastName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  manualAddLastMeta: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
    lineHeight: 16,
  },
  manualAddLastPi: {
    color: PALETTE.gold,
    fontWeight: '700',
  },
  manualAddInfoCard: {
    marginTop: 20,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    padding: 14,
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderStyle: 'dashed',
  },
  manualAddInfoText: {
    color: PALETTE.subtext,
    fontSize: 12,
    lineHeight: 17,
  },
});
