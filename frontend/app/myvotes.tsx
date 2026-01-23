import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import { StyleSheet, Text, TouchableOpacity, View, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { FlashList } from "@shopify/flash-list";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import { useUserEngagement } from "../hooks/useUserEngagement";

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

const VOTES_KEY = "popular_my_votes";

interface VoteHistory {
  personId: string;
  personName: string;
  category: string;
  vote: 1 | -1; // 1 = Like, -1 = Dislike
  timestamp: string;
}

export default function MyVotes() {
  const router = useRouter();
  const [votes, setVotes] = useState<VoteHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const { badges, streakData, totalVotes, voteStats, refreshEngagementData } = useUserEngagement();

  const loadVotes = useCallback(async () => {
    try {
      const stored = await AsyncStorage.getItem(VOTES_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Sort by timestamp descending (most recent first)
        parsed.sort((a: VoteHistory, b: VoteHistory) => 
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );
        setVotes(parsed);
      }
      // Refresh engagement data
      await refreshEngagementData();
    } catch (error) {
      console.error("Failed to load votes:", error);
    } finally {
      setLoading(false);
    }
  }, [refreshEngagementData]);

  useEffect(() => {
    loadVotes();
    // Reload when screen gets focus
    const unsubscribe = router.addListener?.('focus', loadVotes);
    return () => unsubscribe?.();
  }, [loadVotes, router]);

  const clearHistory = useCallback(async () => {
    try {
      await AsyncStorage.removeItem(VOTES_KEY);
      setVotes([]);
    } catch (error) {
      console.error("Failed to clear votes:", error);
    }
  }, []);

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return "À l'instant";
    if (minutes < 60) return `Il y a ${minutes}min`;
    if (hours < 24) return `Il y a ${hours}h`;
    if (days === 1) return "Hier";
    return `Il y a ${days}j`;
  };

  const renderItem = ({ item }: { item: VoteHistory }) => (
    <TouchableOpacity
      style={styles.voteCard}
      onPress={() => router.push({ pathname: "/person", params: { id: item.personId, name: item.personName } })}
    >
      <View style={{ flex: 1 }}>
        <Text style={styles.personName} numberOfLines={1}>{item.personName}</Text>
        <Text style={styles.category} numberOfLines={1}>{item.category}</Text>
        <Text style={styles.timestamp}>{formatDate(item.timestamp)}</Text>
      </View>
      <View style={[styles.voteBadge, item.vote === 1 ? styles.likeBadge : styles.dislikeBadge]}>
        <Ionicons 
          name={item.vote === 1 ? "thumbs-up" : "thumbs-down"} 
          size={20} 
          color="white" 
        />
      </View>
    </TouchableOpacity>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.center}>
          <Text style={styles.emptyText}>Chargement...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>My Votes</Text>
        {votes.length > 0 && (
          <TouchableOpacity onPress={clearHistory} style={styles.clearButton}>
            <Ionicons name="trash-outline" size={20} color={PALETTE.accent} />
            <Text style={styles.clearText}>Effacer</Text>
          </TouchableOpacity>
        )}
      </View>

      {votes.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Ionicons name="heart-outline" size={64} color={PALETTE.subtext} />
          <Text style={styles.emptyText}>Aucun vote encore</Text>
          <Text style={styles.emptySubtext}>Votez pour des personnalités pour les voir ici</Text>
        </View>
      ) : (
        <ScrollView style={{ flex: 1 }}>
          {/* Streak Card */}
          <View style={styles.streakCard}>
            <View style={styles.streakHeader}>
              <Ionicons name="flame" size={32} color="#FF6B35" />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.streakTitle}>Série de votes</Text>
                <Text style={styles.streakSubtitle}>Votez chaque jour pour augmenter votre série</Text>
              </View>
            </View>
            <View style={styles.streakStats}>
              <View style={styles.streakStatItem}>
                <Text style={styles.streakStatValue}>{streakData.currentStreak}</Text>
                <Text style={styles.streakStatLabel}>Jours en cours</Text>
              </View>
              <View style={styles.streakDivider} />
              <View style={styles.streakStatItem}>
                <Text style={styles.streakStatValue}>{streakData.longestStreak}</Text>
                <Text style={styles.streakStatLabel}>Record</Text>
              </View>
              <View style={styles.streakDivider} />
              <View style={styles.streakStatItem}>
                <Text style={styles.streakStatValue}>{totalVotes}</Text>
                <Text style={styles.streakStatLabel}>Total votes</Text>
              </View>
            </View>
          </View>

          {/* Badges Card */}
          <View style={styles.badgesCard}>
            <Text style={styles.badgesTitle}>Badges</Text>
            <View style={styles.badgesGrid}>
              {badges.map((badge) => (
                <View 
                  key={badge.id} 
                  style={[
                    styles.badgeItem,
                    !badge.unlocked && styles.badgeItemLocked
                  ]}
                >
                  <Ionicons 
                    name={badge.icon as any} 
                    size={32} 
                    color={badge.unlocked ? PALETTE.green : PALETTE.subtext} 
                  />
                  <Text style={[
                    styles.badgeName,
                    !badge.unlocked && styles.badgeTextLocked
                  ]}>
                    {badge.name}
                  </Text>
                  <Text style={[
                    styles.badgeDesc,
                    !badge.unlocked && styles.badgeTextLocked
                  ]}>
                    {badge.description}
                  </Text>
                  {badge.unlocked && (
                    <View style={styles.unlockedBadge}>
                      <Ionicons name="checkmark-circle" size={16} color={PALETTE.green} />
                    </View>
                  )}
                </View>
              ))}
            </View>
          </View>

          {/* Statistics Card */}
          {voteStats.categoriesBreakdown.length > 0 && (
            <View style={styles.statsCard}>
              <Text style={styles.statsTitle}>📊 Statistiques</Text>
              
              {/* Likes vs Dislikes */}
              <View style={styles.statRow}>
                <Text style={styles.statLabel}>Répartition :</Text>
                <View style={{ flexDirection: 'row', gap: 12 }}>
                  <Text style={styles.statValue}>👍 {voteStats.totalLikes}</Text>
                  <Text style={styles.statValue}>👎 {voteStats.totalDislikes}</Text>
                </View>
              </View>

              {/* Favorite Category */}
              <View style={styles.statRow}>
                <Text style={styles.statLabel}>Catégorie préférée :</Text>
                <Text style={[styles.statValue, { fontWeight: '700' }]}>{voteStats.favoriteCategory}</Text>
              </View>

              {/* Most Voted Person */}
              {voteStats.mostVotedPerson.name && (
                <View style={styles.statRow}>
                  <Text style={styles.statLabel}>Plus voté :</Text>
                  <Text style={[styles.statValue, { fontWeight: '700', flex: 1, textAlign: 'right' }]} numberOfLines={1}>
                    {voteStats.mostVotedPerson.name} ({voteStats.mostVotedPerson.count})
                  </Text>
                </View>
              )}

              {/* Categories Breakdown */}
              <Text style={[styles.statLabel, { marginTop: 12, marginBottom: 8 }]}>Par catégorie :</Text>
              {voteStats.categoriesBreakdown.map((cat) => (
                <View key={cat.category} style={styles.categoryBar}>
                  <Text style={styles.categoryName}>{cat.category}</Text>
                  <View style={styles.categoryBarContainer}>
                    <View style={[styles.categoryBarFill, { width: `${cat.percentage}%` }]} />
                  </View>
                  <Text style={styles.categoryPercent}>{cat.percentage}%</Text>
                </View>
              ))}
            </View>
          )}

          {/* Votes History */}
          <View style={styles.historyHeader}>
            <Text style={styles.historyTitle}>Historique</Text>
          </View>
          
          <View style={{ height: votes.length * 80 + 24 }}>
            <FlashList
              data={votes}
              keyExtractor={(item, index) => `${item.personId}-${index}`}
              renderItem={renderItem}
              estimatedItemSize={80}
            />
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  title: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: "700",
  },
  clearButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  clearText: {
    color: PALETTE.accent,
    fontSize: 14,
    fontWeight: "600",
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 40,
  },
  emptyText: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: "600",
    marginTop: 16,
  },
  emptySubtext: {
    color: PALETTE.subtext,
    fontSize: 14,
    textAlign: "center",
    marginTop: 8,
  },
  streakCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  streakHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  streakTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: "700",
  },
  streakSubtitle: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 2,
  },
  streakStats: {
    flexDirection: "row",
    justifyContent: "space-around",
    marginTop: 16,
  },
  streakStatItem: {
    flex: 1,
    alignItems: "center",
  },
  streakStatValue: {
    color: PALETTE.text,
    fontSize: 24,
    fontWeight: "700",
  },
  streakStatLabel: {
    color: PALETTE.subtext,
    fontSize: 12,
    marginTop: 4,
    textAlign: "center",
  },
  streakDivider: {
    width: 1,
    backgroundColor: PALETTE.border,
    marginHorizontal: 8,
  },
  badgesCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  badgesTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 16,
  },
  badgesGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  badgeItem: {
    width: "47%",
    backgroundColor: PALETTE.bg,
    padding: 12,
    borderRadius: 8,
    alignItems: "center",
    borderWidth: 2,
    borderColor: PALETTE.green,
    position: "relative",
  },
  badgeItemLocked: {
    opacity: 0.5,
    borderColor: PALETTE.border,
  },
  badgeName: {
    color: PALETTE.text,
    fontSize: 14,
    fontWeight: "700",
    marginTop: 8,
  },
  badgeDesc: {
    color: PALETTE.subtext,
    fontSize: 11,
    marginTop: 4,
    textAlign: "center",
  },
  badgeTextLocked: {
    color: PALETTE.subtext,
  },
  unlockedBadge: {
    position: "absolute",
    top: 8,
    right: 8,
  },
  historyHeader: {
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 12,
  },
  historyTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: "700",
  },
  voteCard: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomColor: PALETTE.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  personName: {
    color: PALETTE.text,
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 4,
  },
  category: {
    color: PALETTE.subtext,
    fontSize: 14,
    marginBottom: 4,
  },
  timestamp: {
    color: PALETTE.subtext,
    fontSize: 12,
  },
  voteBadge: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  likeBadge: {
    backgroundColor: PALETTE.green,
  },
  dislikeBadge: {
    backgroundColor: PALETTE.accent,
  },
  // Phase 3 - Statistics
  statsCard: {
    backgroundColor: PALETTE.card,
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  statsTitle: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 16,
  },
  statRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  statLabel: {
    color: PALETTE.subtext,
    fontSize: 14,
  },
  statValue: {
    color: PALETTE.text,
    fontSize: 14,
  },
  categoryBar: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 8,
    gap: 8,
  },
  categoryName: {
    color: PALETTE.text,
    fontSize: 12,
    width: 70,
  },
  categoryBarContainer: {
    flex: 1,
    height: 12,
    backgroundColor: PALETTE.bg,
    borderRadius: 6,
    overflow: "hidden",
  },
  categoryBarFill: {
    height: "100%",
    backgroundColor: PALETTE.green,
    borderRadius: 6,
  },
  categoryPercent: {
    color: PALETTE.subtext,
    fontSize: 12,
    width: 35,
    textAlign: "right",
  },
});
