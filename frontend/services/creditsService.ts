import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState, useCallback } from 'react';

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const USER_ID_KEY = 'popular_user_id';

/**
 * Generate or retrieve a unique user ID
 */
async function getUserId(): Promise<string> {
  try {
    let userId = await AsyncStorage.getItem(USER_ID_KEY);
    if (!userId) {
      userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      await AsyncStorage.setItem(USER_ID_KEY, userId);
    }
    return userId;
  } catch (error) {
    console.error('Failed to get user ID:', error);
    return `user_temp_${Date.now()}`;
  }
}

export interface CreditPack {
  id: string;
  name: string;
  credits: number;
  price: number;
  savings?: number;
  popular?: boolean;
}

export const CREDIT_PACKS: CreditPack[] = [
  {
    id: 'booster',
    name: 'Booster',
    credits: 100,
    price: 0.99,
  },
  {
    id: 'super_booster',
    name: 'Super Booster',
    credits: 1000,
    price: 4.99,
    popular: true,
  },
];

export interface CreditBalance {
  balance: number;
  is_premium: boolean;
}

export interface Transaction {
  _id: string;
  type: 'purchase' | 'use' | 'refund';
  amount: number;
  description: string;
  timestamp: string;
  price?: number;
  pack?: string;
}

/**
 * Service de gestion des crédits premium
 */
export class CreditsService {
  /**
   * Acheter des crédits (simulation)
   */
  static async purchaseCredits(packId: string): Promise<{ success: boolean; new_balance: number; message: string }> {
    try {
      const userId = await getUserId();
      const pack = CREDIT_PACKS.find(p => p.id === packId);
      
      if (!pack) {
        throw new Error('Pack invalide');
      }

      const response = await fetch(API('/credits/purchase'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          pack: packId,
          amount: pack.credits,
          price: pack.price,
        }),
      });

      if (!response.ok) {
        throw new Error('Échec de l\'achat');
      }

      return await response.json();
    } catch (error) {
      console.error('Purchase error:', error);
      throw error;
    }
  }

  /**
   * Obtenir le solde de crédits
   */
  static async getBalance(): Promise<CreditBalance> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/balance/${userId}`));
      
      if (!response.ok) {
        throw new Error('Échec de récupération du solde');
      }

      return await response.json();
    } catch (error) {
      console.error('Get balance error:', error);
      return { balance: 0, is_premium: false };
    }
  }

  /**
   * Utiliser un crédit pour un vote premium
   */
  static async useCreditForVote(personId: string, personName: string, vote: number): Promise<any> {
    try {
      const userId = await getUserId();
      
      const response = await fetch(API('/credits/use'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'user_id': userId,
        },
        body: JSON.stringify({
          person_id: personId,
          person_name: personName,
          vote: vote,
          multiplier: 100,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Échec du vote premium');
      }

      return await response.json();
    } catch (error) {
      console.error('Use credit error:', error);
      throw error;
    }
  }

  /**
   * Obtenir l'historique des transactions
   */
  static async getHistory(limit: number = 20): Promise<Transaction[]> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/history/${userId}?limit=${limit}`));
      
      if (!response.ok) {
        throw new Error('Échec de récupération de l\'historique');
      }

      const data = await response.json();
      return data.transactions || [];
    } catch (error) {
      console.error('Get history error:', error);
      return [];
    }
  }

  /**
   * Boost yourself - Create a new personality and apply 100 votes for 1 credit
   */
  static async boostMyself(name: string, category: string = 'other'): Promise<{ success: boolean; person_id: string; person_name: string; new_balance: number; message: string }> {
    try {
      const userId = await getUserId();
      
      const response = await fetch(API('/boost-myself'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          name: name.trim(),
          category: category,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Échec de la création');
      }

      return await response.json();
    } catch (error: any) {
      console.error('Boost myself error:', error);
      throw error;
    }
  }
}

/**
 * Hook React pour gérer les crédits
 */
export function useCredits() {
  const [balance, setBalance] = useState(0);
  const [isPremium, setIsPremium] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadBalance = useCallback(async () => {
    setLoading(true);
    try {
      const data = await CreditsService.getBalance();
      setBalance(data.balance);
      setIsPremium(data.is_premium);
    } catch (error) {
      console.error('Failed to load balance:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBalance();
  }, [loadBalance]);

  const purchaseCredits = async (packId: string) => {
    try {
      const result = await CreditsService.purchaseCredits(packId);
      await loadBalance(); // Recharger le solde
      return result;
    } catch (error) {
      throw error;
    }
  };

  const useCredit = async (personId: string, personName: string, vote: number) => {
    try {
      const result = await CreditsService.useCreditForVote(personId, personName, vote);
      await loadBalance(); // Recharger le solde
      return result;
    } catch (error) {
      throw error;
    }
  };

  return {
    balance,
    isPremium,
    loading,
    purchaseCredits,
    useCredit,
    refreshBalance: loadBalance,
  };
}
