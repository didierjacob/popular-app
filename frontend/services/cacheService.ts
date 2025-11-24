import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_PREFIX = 'cache_';
const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes en millisecondes

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

/**
 * Service de cache intelligent pour optimiser les appels API
 */
export class CacheService {
  /**
   * Sauvegarde des données dans le cache avec un TTL
   */
  static async set<T>(key: string, data: T, ttl: number = DEFAULT_TTL): Promise<void> {
    try {
      const entry: CacheEntry<T> = {
        data,
        timestamp: Date.now(),
        ttl,
      };
      await AsyncStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(entry));
    } catch (error) {
      console.error(`Cache set error for key ${key}:`, error);
    }
  }

  /**
   * Récupère des données du cache si elles sont encore valides
   * @returns Les données ou null si le cache est expiré ou inexistant
   */
  static async get<T>(key: string): Promise<T | null> {
    try {
      const cached = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`);
      if (!cached) return null;

      const entry: CacheEntry<T> = JSON.parse(cached);
      const now = Date.now();
      
      // Vérifier si le cache est expiré
      if (now - entry.timestamp > entry.ttl) {
        // Cache expiré, le supprimer
        await this.remove(key);
        return null;
      }

      return entry.data;
    } catch (error) {
      console.error(`Cache get error for key ${key}:`, error);
      return null;
    }
  }

  /**
   * Supprime une entrée du cache
   */
  static async remove(key: string): Promise<void> {
    try {
      await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`);
    } catch (error) {
      console.error(`Cache remove error for key ${key}:`, error);
    }
  }

  /**
   * Vide tout le cache
   */
  static async clear(): Promise<void> {
    try {
      const keys = await AsyncStorage.getAllKeys();
      const cacheKeys = keys.filter(key => key.startsWith(CACHE_PREFIX));
      await AsyncStorage.multiRemove(cacheKeys);
    } catch (error) {
      console.error('Cache clear error:', error);
    }
  }

  /**
   * Vérifie si une clé existe dans le cache et est valide
   */
  static async has(key: string): Promise<boolean> {
    const data = await this.get(key);
    return data !== null;
  }
}

/**
 * Fonction helper pour fetch avec cache automatique
 */
export async function fetchWithCache<T>(
  url: string,
  cacheKey: string,
  fetchFn: () => Promise<T>,
  ttl: number = DEFAULT_TTL
): Promise<T> {
  // Essayer de récupérer depuis le cache
  const cached = await CacheService.get<T>(cacheKey);
  if (cached !== null) {
    return cached;
  }

  // Pas en cache, faire la requête
  const data = await fetchFn();
  
  // Sauvegarder dans le cache
  await CacheService.set(cacheKey, data, ttl);
  
  return data;
}
