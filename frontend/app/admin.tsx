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
  revenue_24h: string;
  new_people_24h: number;
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

type Tab = 'dashboard' | 'moderation' | 'activity' | 'settings';

export default function Admin() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [currentTab, setCurrentTab] = useState<Tab>('dashboard');
  
  // Stats
  const [stats, setStats] = useState<Stats | null>(null);
  const [topPeople, setTopPeople] = useState<Person[]>([]);
  
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

  const handleLogin = () => {
    if (password === 'fab31230') {
      setAuthenticated(true);
      loadData();
    } else {
      Alert.alert('Erreur', 'Mot de passe incorrect');
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Load stats
      const statsRes = await fetch(API('/admin/stats'));
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }

      // Load top people
      const peopleRes = await fetch(API('/people?limit=50'));
      if (peopleRes.ok) {
        const peopleData = await peopleRes.json();
        setTopPeople(peopleData);
        setSearchResults(peopleData);
      }

      // Load activity
      const activityRes = await fetch(API('/admin/activity/recent'));
      if (activityRes.ok) {
        const actData = await activityRes.json();
        setActivityData(actData);
      }

      // Load settings
      const settingsRes = await fetch(API('/admin/settings'));
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

  const handleBoostDialog = (type: 'likes' | 'dislikes') => {
    if (!selectedPerson) {
      Alert.alert('Erreur', 'Veuillez d\'abord sélectionner une personnalité');
      return;
    }

    const typeLabel = type === 'likes' ? 'Likes' : 'Dislikes';
    const emoji = type === 'likes' ? '👍' : '👎';

    if (Platform.OS === 'ios') {
      Alert.prompt(
        `${emoji} Ajouter ${typeLabel}`,
        `Personnalité : ${selectedPerson.name}\n\nCombien de ${typeLabel.toLowerCase()} ? (1-5000)`,
        [
          { text: 'Annuler', style: 'cancel' },
          {
            text: 'Ajouter',
            onPress: async (value) => {
              const amount = parseInt(value || '0');
              if (isNaN(amount) || amount < 1 || amount > 5000) {
                Alert.alert('Erreur', 'Entrez un nombre entre 1 et 5000');
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
        `${emoji} Ajouter ${typeLabel}`,
        `Personnalité : ${selectedPerson.name}\n\nNombre de ${typeLabel.toLowerCase()} (1-5000) :`,
        [
          { text: 'Annuler', style: 'cancel' },
          { text: '100', onPress: () => executeBoost(selectedPerson.id, 100, type) },
          { text: '500', onPress: () => executeBoost(selectedPerson.id, 500, type) },
          { text: '1000', onPress: () => executeBoost(selectedPerson.id, 1000, type) },
          {
            text: 'Personnalisé',
            onPress: () => {
              Alert.prompt(
                'Montant personnalisé',
                'Entrez le nombre (1-5000) :',
                [
                  { text: 'Annuler', style: 'cancel' },
                  {
                    text: 'Ajouter',
                    onPress: async (value) => {
                      const amount = parseInt(value || '0');
                      if (isNaN(amount) || amount < 1 || amount > 5000) {
                        Alert.alert('Erreur', 'Entrez un nombre entre 1 et 5000');
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
        Alert.alert('✅ Succès !', `${amount} ${type} ajoutés !`, [{ text: 'OK' }]);
        loadData();
        setSelectedPerson(null);
      } else {
        Alert.alert('Erreur', 'Échec du boost');
      }
    } catch (error) {
      Alert.alert('Erreur', 'Erreur réseau');
    }
  };

  const handleDeletePerson = (person: Person) => {
    Alert.alert(
      '⚠️ Supprimer',
      `Voulez-vous vraiment supprimer "${person.name}" ?\n\nCette action est irréversible.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await fetch(API(`/admin/person/${person.id}`), { method: 'DELETE' });
              if (res.ok) {
                Alert.alert('✅ Supprimé', `"${person.name}" a été supprimé`);
                loadData();
              } else {
                Alert.alert('Erreur', 'Échec de la suppression');
              }
            } catch (error) {
              Alert.alert('Erreur', 'Erreur réseau');
            }
          },
        },
      ]
    );
  };

  const handleResetPerson = (person: Person) => {
    Alert.alert(
      '🔄 Réinitialiser',
      `Réinitialiser "${person.name}" à un score neutre de 50 ?`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Réinitialiser',
          onPress: async () => {
            try {
              const res = await fetch(API(`/admin/person/${person.id}/reset`), { method: 'POST' });
              if (res.ok) {
                Alert.alert('✅ Réinitialisé', `"${person.name}" a été réinitialisé`);
                loadData();
              } else {
                Alert.alert('Erreur', 'Échec de la réinitialisation');
              }
            } catch (error) {
              Alert.alert('Erreur', 'Erreur réseau');
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
        Alert.alert('✅ Sauvegardé', 'Paramètres mis à jour avec succès');
      } else {
        Alert.alert('Erreur', 'Échec de la sauvegarde');
      }
    } catch (error) {
      Alert.alert('Erreur', 'Erreur réseau');
    }
  };

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadData();
  }, [loadData]);

  const handleRefreshTrends = async () => {
    Alert.alert(
      '🔥 Rafraîchir Google Trends',
      'Cela va récupérer les personnalités trending de Google Trends et les ajouter/mettre à jour dans l\'app. Continuer ?',
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Rafraîchir',
          onPress: async () => {
            try {
              const res = await fetch(API('/admin/refresh-trends'), { method: 'POST' });
              if (res.ok) {
                const result = await res.json();
                Alert.alert(
                  '✅ Trends Rafraîchis !',
                  `${result.added} nouvelles personnalités ajoutées\n${result.updated} mises à jour comme trending`,
                  [{ text: 'OK' }]
                );
                loadData();
              } else {
                Alert.alert('Erreur', 'Échec du rafraîchissement');
              }
            } catch (error) {
              Alert.alert('Erreur', 'Erreur réseau');
            }
          },
        },
      ]
    );
  };

  if (!authenticated) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loginContainer}>
          <Ionicons name="lock-closed" size={64} color={PALETTE.gold} />
          <Text style={styles.loginTitle}>Admin Access</Text>
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
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBack}>
          <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>🔧 Admin</Text>
        </View>
        <TouchableOpacity onPress={loadData}>
          <Ionicons name="refresh" size={24} color={PALETTE.gold} />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tab, currentTab === 'dashboard' && styles.tabActive]}
          onPress={() => setCurrentTab('dashboard')}
        >
          <Ionicons name="stats-chart" size={20} color={currentTab === 'dashboard' ? '#000' : PALETTE.text} />
          <Text style={[styles.tabText, currentTab === 'dashboard' && styles.tabTextActive]}>Dashboard</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tab, currentTab === 'moderation' && styles.tabActive]}
          onPress={() => setCurrentTab('moderation')}
        >
          <Ionicons name="shield-checkmark" size={20} color={currentTab === 'moderation' ? '#000' : PALETTE.text} />
          <Text style={[styles.tabText, currentTab === 'moderation' && styles.tabTextActive]}>Modération</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tab, currentTab === 'activity' && styles.tabActive]}
          onPress={() => setCurrentTab('activity')}
        >
          <Ionicons name="pulse" size={20} color={currentTab === 'activity' ? '#000' : PALETTE.text} />
          <Text style={[styles.tabText, currentTab === 'activity' && styles.tabTextActive]}>Activité</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tab, currentTab === 'settings' && styles.tabActive]}
          onPress={() => setCurrentTab('settings')}
        >
          <Ionicons name="settings" size={20} color={currentTab === 'settings' ? '#000' : PALETTE.text} />
          <Text style={[styles.tabText, currentTab === 'settings' && styles.tabTextActive]}>Paramètres</Text>
        </TouchableOpacity>
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
            {currentTab === 'dashboard' && (
              <DashboardTab
                stats={stats}
                topPeople={topPeople}
                selectedPerson={selectedPerson}
                onSelectPerson={setSelectedPerson}
                onBoost={handleBoostDialog}
                onRefreshTrends={handleRefreshTrends}
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
                onReset={handleResetPerson}
              />
            )}

            {currentTab === 'activity' && activityData && (
              <ActivityTab activityData={activityData} />
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

// Dashboard Tab Component
function DashboardTab({ stats, topPeople, selectedPerson, onSelectPerson, onBoost, onRefreshTrends }: any) {
  return (
    <View>
      {stats && (
        <View style={styles.statsGrid}>
          <View style={[styles.statCard, { borderColor: PALETTE.gold }]}>
            <Ionicons name="people" size={32} color={PALETTE.gold} />
            <Text style={styles.statNumber}>{stats.total_people}</Text>
            <Text style={styles.statLabel}>Personnalités</Text>
          </View>

          <View style={[styles.statCard, { borderColor: PALETTE.green }]}>
            <Ionicons name="bar-chart" size={32} color={PALETTE.green} />
            <Text style={styles.statNumber}>{stats.total_votes}</Text>
            <Text style={styles.statLabel}>Votes Totaux</Text>
          </View>

          <View style={[styles.statCard, { borderColor: '#00D8FF' }]}>
            <Ionicons name="person" size={32} color="#00D8FF" />
            <Text style={styles.statNumber}>{stats.active_users_24h}</Text>
            <Text style={styles.statLabel}>Users 24h</Text>
          </View>

          <View style={[styles.statCard, { borderColor: '#FF4757' }]}>
            <Ionicons name="cash" size={32} color="#FF4757" />
            <Text style={styles.statNumber}>{stats.revenue_24h}€</Text>
            <Text style={styles.statLabel}>Revenus 24h</Text>
          </View>
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🔥 Google Trends</Text>
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Rafraîchir les personnalités trending</Text>
          <TouchableOpacity style={styles.refreshTrendsButton} onPress={onRefreshTrends}>
            <Ionicons name="trending-up" size={24} color="#000" />
            <Text style={styles.refreshTrendsButtonText}>Rafraîchir Google Trends</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>🚀 Booster</Text>
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Sélectionner une personnalité</Text>
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
                  <Text style={styles.boostActionTitle}>Ajouter Likes</Text>
                  <Text style={styles.boostActionSubtitle}>1-5000 votes</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.boostActionBtn} onPress={() => onBoost('dislikes')}>
                  <Ionicons name="thumbs-down" size={24} color={PALETTE.accent} />
                  <Text style={styles.boostActionTitle}>Ajouter Dislikes</Text>
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
      <Text style={styles.sectionTitle}>🔍 Recherche Avancée</Text>
      
      <View style={styles.card}>
        <TextInput
          style={styles.searchInput}
          placeholder="Rechercher par nom..."
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
        <Text style={styles.sectionTitle}>👤 Nouvelles Personnalités</Text>
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
        <Text style={styles.sectionTitle}>💰 Achats Récents</Text>
        <View style={styles.card}>
          {activityData.recent_purchases.slice(0, 10).map((item: any, index: number) => (
            <View key={index} style={styles.activityRow}>
              <Ionicons name="cart" size={20} color={PALETTE.green} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.activityName}>{item.amount} crédits</Text>
                <Text style={styles.activityTime}>
                  {new Date(item.timestamp).toLocaleString('fr-FR')}
                </Text>
              </View>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>⚡ Utilisations Récentes</Text>
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
      <Text style={styles.sectionTitle}>⚙️ Paramètres de l'App</Text>
      
      <View style={styles.card}>
        <View style={styles.settingRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.settingLabel}>Autoriser ajouts utilisateurs</Text>
            <Text style={styles.settingDesc}>Les users peuvent ajouter des personnalités</Text>
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
          <Text style={styles.saveButtonText}>Enregistrer les Paramètres</Text>
        </TouchableOpacity>
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
  statLabel: { color: PALETTE.subtext, fontSize: 12, marginTop: 4 },
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
});
