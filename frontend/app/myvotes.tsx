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
  const { badges, streakData, totalVotes, refreshEngagementData } = useUserEngagement();

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
        <Text style={styles.title}>Mes votes</Text>
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
        <FlashList
          data={votes}
          keyExtractor={(item, index) => `${item.personId}-${index}`}
          renderItem={renderItem}
          estimatedItemSize={80}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
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
});
