// Ultra-minimal App without expo-router
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView } from 'react-native';

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>🎉 Popular App</Text>
        <Text style={styles.subtitle}>Test réussi !</Text>
        <Text style={styles.info}>Si vous voyez ceci, l'app fonctionne.</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F2F22',
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#EAEAEA',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 24,
    color: '#00E676',
    marginBottom: 20,
  },
  info: {
    fontSize: 16,
    color: '#C9D8D2',
    textAlign: 'center',
  },
});
