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
}

export default function Admin() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  
  // Stats
  const [stats, setStats] = useState<Stats | null>(null);
  const [topPeople, setTopPeople] = useState<Person[]>([]);
  
  // Boost form
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const [boostAmount, setBoostAmount] = useState('100');
  const [boostType, setBoostType] = useState<'likes' | 'dislikes'>('likes');

  const handleLogin = () => {
    // Simple password check
    if (password === 'admin2025') {
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
      }
    } catch (error) {
      console.error('Failed to load admin data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleBoostDialog = (type: 'likes' | 'dislikes') => {
    if (!selectedPerson) {
      Alert.alert('Erreur', 'Veuillez d\'abord sélectionner une personnalité');
      return;
    }

    const typeLabel = type === 'likes' ? 'Likes' : 'Dislikes';
    const emoji = type === 'likes' ? '👍' : '👎';

    if (Platform.OS === 'ios') {
      // iOS supports Alert.prompt
      Alert.prompt(
        `${emoji} Ajouter ${typeLabel}`,
        `Personnalité : ${selectedPerson.name}\n\nCombien de ${typeLabel.toLowerCase()} voulez-vous ajouter ? (1-5000)`,
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
      // Android fallback with default prompt
      Alert.alert(
        `${emoji} Ajouter ${typeLabel}`,
        `Personnalité : ${selectedPerson.name}\n\nEntrez le nombre de ${typeLabel.toLowerCase()} (1-5000) :`,
        [
          { text: 'Annuler', style: 'cancel' },
          {
            text: '100',
            onPress: () => executeBoost(selectedPerson.id, 100, type),
          },
          {
            text: '500',
            onPress: () => executeBoost(selectedPerson.id, 500, type),
          },
          {
            text: '1000',
            onPress: () => executeBoost(selectedPerson.id, 1000, type),
          },
          {
            text: 'Personnalisé',
            onPress: () => {
              // Recursive call for custom amount
              Alert.prompt(
                'Montant personnalisé',
                'Entrez le nombre de votes (1-5000) :',
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
    const typeLabel = type === 'likes' ? 'likes' : 'dislikes';
    
    try {
      const res = await fetch(API('/admin/boost-votes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          person_id: personId,
          amount: amount,
          type: type,
        }),
      });

      if (res.ok) {
        const result = await res.json();
        Alert.alert(
          '✅ Succès !',
          `${amount} ${typeLabel} ajoutés à "${result.person_name}"\n\n` +
          `Nouveau score : ${result.new_score.toFixed(1)}\n` +
          `Total votes : ${result.new_total_votes}`,
          [{ text: 'OK' }]
        );
        loadData();
        setSelectedPerson(null);
      } else {
        const error = await res.json();
        Alert.alert('Erreur', error.detail || 'Échec du boost');
      }
    } catch (error) {
      console.error('Boost error:', error);
      Alert.alert('Erreur', 'Erreur réseau');
    }
  };

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadData();
  }, [loadData]);

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

          <TouchableOpacity 
            style={styles.backButton} 
            onPress={() => router.back()}
          >
            <Text style={styles.backButtonText}>Retour</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={PALETTE.gold} />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerBack}>
            <Ionicons name="arrow-back" size={24} color={PALETTE.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerTitle}>🔧 Admin Dashboard</Text>
            <Text style={styles.headerSubtitle}>Gestion et statistiques</Text>
          </View>
          <TouchableOpacity onPress={loadData}>
            <Ionicons name="refresh" size={24} color={PALETTE.gold} />
          </TouchableOpacity>
        </View>

        {loading && !refreshing ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={PALETTE.gold} />
          </View>
        ) : (
          <>
            {/* Stats Cards */}
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

            {/* Boost Section */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>🚀 Booster Manuellement</Text>
              <View style={styles.card}>
                <Text style={styles.cardLabel}>Personnalité</Text>
                <ScrollView 
                  horizontal 
                  showsHorizontalScrollIndicator={false}
                  style={styles.personSelector}
                >
                  {topPeople.slice(0, 10).map((person) => (
                    <TouchableOpacity
                      key={person.id}
                      style={[
                        styles.personChip,
                        selectedPerson?.id === person.id && styles.personChipSelected,
                      ]}
                      onPress={() => setSelectedPerson(person)}
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
                      <TouchableOpacity 
                        style={styles.boostActionBtn}
                        onPress={() => handleBoostDialog('likes')}
                      >
                        <Ionicons name="thumbs-up" size={24} color={PALETTE.green} />
                        <Text style={styles.boostActionTitle}>Ajouter Likes</Text>
                        <Text style={styles.boostActionSubtitle}>1-5000 votes</Text>
                      </TouchableOpacity>

                      <TouchableOpacity 
                        style={styles.boostActionBtn}
                        onPress={() => handleBoostDialog('dislikes')}
                      >
                        <Ionicons name="thumbs-down" size={24} color={PALETTE.accent} />
                        <Text style={styles.boostActionTitle}>Ajouter Dislikes</Text>
                        <Text style={styles.boostActionSubtitle}>1-5000 votes</Text>
                      </TouchableOpacity>
                    </View>
                  </>
                )}
              </View>
            </View>

            {/* Top Personalities List */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>📊 Top Personnalités</Text>
              <View style={styles.card}>
                {topPeople.slice(0, 15).map((person, index) => (
                  <TouchableOpacity
                    key={person.id}
                    style={styles.personRow}
                    onPress={() => setSelectedPerson(person)}
                  >
                    <View style={styles.personRank}>
                      <Text style={styles.personRankText}>#{index + 1}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.personRowName}>{person.name}</Text>
                      <Text style={styles.personRowStats}>
                        {person.total_votes} votes • Score {person.score}
                      </Text>
                    </View>
                    <View style={styles.sourceBadge}>
                      <Text style={styles.sourceBadgeText}>
                        {person.source === 'self_boosted' ? '👤' : person.source === 'user_added' ? '➕' : '⭐'}
                      </Text>
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  loginContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  loginTitle: {
    color: PALETTE.text,
    fontSize: 28,
    fontWeight: '700',
    marginTop: 24,
  },
  loginSubtitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 8,
    marginBottom: 32,
  },
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
  loginButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
  backButton: {
    marginTop: 16,
  },
  backButtonText: {
    color: PALETTE.subtext,
    fontSize: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    gap: 12,
  },
  headerBack: {
    padding: 8,
  },
  headerTitle: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 2,
  },
  loadingContainer: {
    padding: 40,
    alignItems: 'center',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 8,
    gap: 8,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    borderWidth: 2,
  },
  statNumber: {
    color: PALETTE.text,
    fontSize: 28,
    fontWeight: '700',
    marginTop: 8,
  },
  statLabel: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 4,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    color: PALETTE.text,
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 12,
  },
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  cardLabel: {
    color: PALETTE.subtext,
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
    marginTop: 16,
  },
  personSelector: {
    marginVertical: 8,
  },
  personChip: {
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    padding: 12,
    marginRight: 8,
    borderWidth: 2,
    borderColor: PALETTE.border,
    minWidth: 100,
  },
  personChipSelected: {
    borderColor: PALETTE.gold,
    backgroundColor: PALETTE.gold + '20',
  },
  personChipText: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
  },
  personChipScore: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 4,
  },
  selectedPerson: {
    backgroundColor: PALETTE.gold + '20',
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
  },
  selectedPersonName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '700',
  },
  selectedPersonStats: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginTop: 4,
  },
  boostTypeRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  boostTypeBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: PALETTE.bg,
    borderRadius: 8,
    padding: 12,
    borderWidth: 2,
    borderColor: PALETTE.border,
  },
  boostTypeBtnActive: {
    backgroundColor: PALETTE.gold,
    borderColor: PALETTE.gold,
  },
  boostTypeText: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: '600',
  },
  boostTypeTextActive: {
    color: '#000',
  },
  input: {
    backgroundColor: PALETTE.bg,
    borderWidth: 2,
    borderColor: PALETTE.border,
    borderRadius: 8,
    padding: 12,
    color: PALETTE.text,
    fontSize: 16,
  },
  boostButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: PALETTE.gold,
    borderRadius: 12,
    padding: 16,
    marginTop: 16,
  },
  boostButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
  personRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  personRank: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: PALETTE.gold + '30',
    alignItems: 'center',
    justifyContent: 'center',
  },
  personRankText: {
    color: PALETTE.gold,
    fontSize: 12,
    fontWeight: '700',
  },
  personRowName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: '600',
  },
  personRowStats: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  sourceBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: PALETTE.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sourceBadgeText: {
    fontSize: 14,
  },
});
