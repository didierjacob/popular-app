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

/**
 * Stale-While-Revalidate: appelle `onCached` immédiatement si une valeur
 * est en cache (même expirée), puis lance un fetch frais en arrière-plan
 * et appelle `onFresh` lorsque la réponse fraîche est disponible.
 * Le cache est toujours rafraîchi en cas de succès.
 *
 * Si le fetch échoue, le callback `onError` est appelé. Si aucun cache
 * n'existait, l'appelant doit gérer l'état de chargement initial.
 */
export async function fetchSWR<T>(
  cacheKey: string,
  fetchFn: () => Promise<T>,
  callbacks: {
    onCached?: (data: T) => void;
    onFresh?: (data: T) => void;
    onError?: (err: any) => void;
  } = {},
  ttl: number = DEFAULT_TTL,
): Promise<{ hadCache: boolean }> {
  let hadCache = false;

  // 1) Lire le cache (même expiré) pour affichage instantané
  try {
    const raw = await AsyncStorage.getItem(`${CACHE_PREFIX}${cacheKey}`);
    if (raw) {
      const entry: CacheEntry<T> = JSON.parse(raw);
      hadCache = true;
      callbacks.onCached?.(entry.data);
    }
  } catch {
    // Ignore — on tombera sur le fetch frais
  }

  // 2) Fetch frais en arrière-plan
  try {
    const fresh = await fetchFn();
    await CacheService.set(cacheKey, fresh, ttl);
    callbacks.onFresh?.(fresh);
  } catch (err) {
    callbacks.onError?.(err);
  }

  return { hadCache };
}
