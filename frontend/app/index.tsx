import React, { useEffect, useState } from "react";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useRouter } from "expo-router";

const PALETTE = {
  bg: "#0F2F22",
  card: "#1C3A2C",
  text: "#EAEAEA",
  subtext: "#C9D8D2",
  accent: "#009B4D",
  border: "#2E6148",
};

const API_BASE = "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

interface Person {
  id: string;
  name: string;
  category: string;
  score: number;
  total_votes: number;
}

export default function HomeScreen() {
  const router = useRouter();
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPeople();
  }, []);

  const loadPeople = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(API("/people?limit=10"));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setPeople(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Popular</Text>
        <Text style={styles.subtitle}>Rate them. Buy credits to become popular</Text>
      </View>

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={PALETTE.accent} />
          <Text style={styles.loadingText}>Loading...</Text>
        </View>
      )}

      {error && (
        <View style={styles.center}>
          <Text style={styles.errorText}>Error: {error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={loadPeople}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      {!loading && !error && (
        <ScrollView style={styles.list}>
          {people.map((person) => (
            <TouchableOpacity
              key={person.id}
              style={styles.personCard}
              onPress={() => router.push({ pathname: "/person", params: { id: person.id, name: person.name } })}
            >
              <Text style={styles.personName}>{person.name}</Text>
              <Text style={styles.personMeta}>
                {person.category} • Score: {person.score.toFixed(0)} • {person.total_votes} votes
              </Text>
            </TouchableOpacity>
          ))}
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
  center: {
    flex: 1,
    justifyContent: "center",
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
  list: {
    flex: 1,
    paddingHorizontal: 16,
  },
  personCard: {
    backgroundColor: PALETTE.card,
    padding: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  personName: {
    fontSize: 18,
    fontWeight: "600",
    color: PALETTE.text,
  },
  personMeta: {
    fontSize: 14,
    color: PALETTE.subtext,
    marginTop: 4,
  },
});
