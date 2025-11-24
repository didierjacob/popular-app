import NetInfo from '@react-native-community/netinfo';
import { useEffect, useState } from 'react';

/**
 * Service de gestion de la connectivité réseau
 */
export class NetworkService {
  /**
   * Vérifie si l'appareil est connecté à internet
   */
  static async isConnected(): Promise<boolean> {
    try {
      const state = await NetInfo.fetch();
      return state.isConnected === true && state.isInternetReachable !== false;
    } catch (error) {
      console.error('Network check error:', error);
      return true; // En cas d'erreur, on assume qu'on est connecté
    }
  }

  /**
   * Écoute les changements de connexion
   */
  static subscribe(callback: (isConnected: boolean) => void) {
    return NetInfo.addEventListener(state => {
      const isConnected = state.isConnected === true && state.isInternetReachable !== false;
      callback(isConnected);
    });
  }
}

/**
 * Hook React pour gérer l'état de la connectivité
 */
export function useNetworkStatus() {
  const [isConnected, setIsConnected] = useState(true);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    // Vérification initiale
    NetworkService.isConnected().then(connected => {
      setIsConnected(connected);
      setIsChecking(false);
    });

    // S'abonner aux changements
    const unsubscribe = NetworkService.subscribe(connected => {
      setIsConnected(connected);
      setIsChecking(false);
    });

    return () => unsubscribe();
  }, []);

  return { isConnected, isChecking };
}
