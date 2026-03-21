import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState, useCallback } from 'react';

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
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

export interface BoosterPack {
  id: string;
  name: string;
  votes: number;  // How many votes this booster applies
  price: number;
  popular?: boolean;
}

export const BOOSTER_PACKS: BoosterPack[] = [
  {
    id: 'booster',
    name: 'Booster',
    votes: 100,
    price: 0.99,
  },
  {
    id: 'super_booster',
    name: 'Super Booster',
    votes: 1000,
    price: 4.99,
    popular: true,
  },
];

// Keep old export for backwards compatibility
export const CREDIT_PACKS = BOOSTER_PACKS.map(p => ({
  id: p.id,
  name: p.name,
  credits: p.votes,
  price: p.price,
  popular: p.popular,
}));

export interface BoosterBalance {
  boosters: number;      // Number of Boosters available (100 votes each)
  super_boosters: number; // Number of Super Boosters available (1000 votes each)
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
 * Service for managing boosters
 */
export class CreditsService {
  /**
   * Purchase a booster pack (simulation)
   */
  static async purchaseCredits(packId: string): Promise<{ success: boolean; new_balance: number; boosters: number; super_boosters: number; message: string }> {
    try {
      const userId = await getUserId();
      const pack = BOOSTER_PACKS.find(p => p.id === packId);
      
      if (!pack) {
        throw new Error('Invalid pack');
      }

      const response = await fetch(API('/credits/purchase'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          pack: packId,
          amount: 1, // Always 1 booster per purchase
          price: pack.price,
        }),
      });

      if (!response.ok) {
        throw new Error('Purchase failed');
      }

      return await response.json();
    } catch (error) {
      console.error('Purchase error:', error);
      throw error;
    }
  }

  /**
   * Get booster balance
   */
  static async getBalance(): Promise<BoosterBalance> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/balance/${userId}`));
      
      if (!response.ok) {
        throw new Error('Failed to get balance');
      }

      const data = await response.json();
      return {
        boosters: data.boosters || 0,
        super_boosters: data.super_boosters || 0,
        is_premium: data.is_premium || false,
      };
    } catch (error) {
      console.error('Get balance error:', error);
      return { boosters: 0, super_boosters: 0, is_premium: false };
    }
  }

  /**
   * Use a booster on a personality (applies all votes at once)
   */
  static async useBooster(personId: string, personName: string, vote: number, boosterType: 'booster' | 'super_booster'): Promise<any> {
    try {
      const userId = await getUserId();
      const votes = boosterType === 'super_booster' ? 1000 : 100;
      
      const response = await fetch(API('/credits/use-booster'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          person_id: personId,
          person_name: personName,
          vote: vote,
          booster_type: boosterType,
          votes: votes,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to use booster');
      }

      return await response.json();
    } catch (error) {
      console.error('Use booster error:', error);
      throw error;
    }
  }

  // Keep old method for backwards compatibility
  static async useCreditForVote(personId: string, personName: string, vote: number): Promise<any> {
    return this.useBooster(personId, personName, vote, 'booster');
  }

  /**
   * Get transaction history
   */
  static async getHistory(limit: number = 20): Promise<Transaction[]> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/history/${userId}?limit=${limit}`));
      
      if (!response.ok) {
        throw new Error('Failed to get history');
      }

      const data = await response.json();
      return data.transactions || [];
    } catch (error) {
      console.error('Get history error:', error);
      return [];
    }
  }

  /**
   * Boost yourself - Create a new personality (costs 1 Booster)
   */
  static async boostMyself(name: string, category: string = 'other'): Promise<{ success: boolean; person_id: string; person_name: string; boosters: number; super_boosters: number; message: string }> {
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
        throw new Error(error.detail || 'Failed to create personality');
      }

      return await response.json();
    } catch (error: any) {
      console.error('Boost myself error:', error);
      throw error;
    }
  }
}

/**
 * React hook for managing boosters
 */
export function useCredits() {
  const [boosters, setBoosters] = useState(0);
  const [superBoosters, setSuperBoosters] = useState(0);
  const [isPremium, setIsPremium] = useState(false);
  const [loading, setLoading] = useState(true);

  // For backwards compatibility
  const balance = boosters + superBoosters;

  const loadBalance = useCallback(async () => {
    setLoading(true);
    try {
      const data = await CreditsService.getBalance();
      setBoosters(data.boosters);
      setSuperBoosters(data.super_boosters);
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
      await loadBalance();
      return result;
    } catch (error) {
      throw error;
    }
  };

  const useBooster = async (personId: string, personName: string, vote: number, boosterType: 'booster' | 'super_booster' = 'booster') => {
    try {
      const result = await CreditsService.useBooster(personId, personName, vote, boosterType);
      await loadBalance();
      return result;
    } catch (error) {
      throw error;
    }
  };

  // Keep old method for backwards compatibility
  const useCredit = async (personId: string, personName: string, vote: number) => {
    return useBooster(personId, personName, vote, 'booster');
  };

  return {
    balance,
    boosters,
    superBoosters,
    isPremium,
    loading,
    purchaseCredits,
    useCredit,
    useBooster,
    refreshBalance: loadBalance,
  };
}
