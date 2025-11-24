import { CacheService } from './cacheService';

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(API(path));
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

/**
 * Service de préchargement intelligent des données fréquentes
 */
export class PrefetchService {
  private static isPrefetching = false;

  /**
   * Précharge les données les plus fréquemment consultées
   */
  static async prefetchFrequentData() {
    if (this.isPrefetching) return;
    
    this.isPrefetching = true;

    try {
      // Précharger en parallèle
      await Promise.all([
        this.prefetchPeopleList(),
        this.prefetchTrendingData(),
        this.prefetchControversialData(),
      ]);
      
      console.log('✅ Prefetch completed');
    } catch (error) {
      console.error('Prefetch error:', error);
    } finally {
      this.isPrefetching = false;
    }
  }

  /**
   * Précharge la liste principale des personnalités
   */
  private static async prefetchPeopleList() {
    try {
      const data = await apiGet('/people');
      await CacheService.set('people_all', data, 5 * 60 * 1000);
    } catch (error) {
      console.error('Failed to prefetch people list:', error);
    }
  }

  /**
   * Précharge les données trending
   */
  private static async prefetchTrendingData() {
    try {
      const data = await apiGet('/trending-now?limit=5');
      await CacheService.set('trending_data', data, 5 * 60 * 1000);
    } catch (error) {
      console.error('Failed to prefetch trending data:', error);
    }
  }

  /**
   * Précharge les données controversées
   */
  private static async prefetchControversialData() {
    try {
      const data = await apiGet('/controversial?limit=5');
      await CacheService.set('controversial_data', data, 5 * 60 * 1000);
    } catch (error) {
      console.error('Failed to prefetch controversial data:', error);
    }
  }

  /**
   * Précharge les graphiques d'une personnalité spécifique
   */
  static async prefetchPersonData(personId: string) {
    try {
      await Promise.all([
        apiGet(`/people/${personId}`).then(data => 
          CacheService.set(`person_${personId}`, data, 2 * 60 * 1000)
        ),
        apiGet(`/people/${personId}/chart?window=24h`).then(data => 
          CacheService.set(`chart_24h_${personId}`, data, 2 * 60 * 1000)
        ),
        apiGet(`/people/${personId}/chart?window=168h`).then(data => 
          CacheService.set(`chart_168h_${personId}`, data, 5 * 60 * 1000)
        ),
      ]);
    } catch (error) {
      console.error(`Failed to prefetch person ${personId}:`, error);
    }
  }

  /**
   * Précharge les personnalités les plus populaires
   */
  static async prefetchTopPeople(peopleIds: string[]) {
    // Limiter à 5 max pour ne pas surcharger
    const limitedIds = peopleIds.slice(0, 5);
    
    for (const id of limitedIds) {
      await this.prefetchPersonData(id);
    }
  }
}
