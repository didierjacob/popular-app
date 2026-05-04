import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState, useCallback } from 'react';

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";
const API = (path: string) => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

const USER_ID_KEY = 'popular_user_id';

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

// ---- Types ----

export interface BoosterTier {
  id: string;
  name: string;
  price: number;
  duration_hours: number;
  position: 'top' | 'bottom';
  description: string;
}

export interface SocialLinks {
  instagram?: string;
  tiktok?: string;
  x?: string;
}

export interface OutsiderData {
  id: string;
  boost_id: string;
  user_id: string;
  name: string;
  category: string;
  score: number;
  total_votes: number;
  likes: number;
  dislikes: number;
  tier: string;
  tier_name: string;
  position: string;
  end_time: string;
  hours_remaining: number;
  social_links: SocialLinks;
  avatar_initials?: string;
  avatar_color?: string;
  popularoo_index?: number;
  active_strikes?: number;
  strike_emoji?: string;
  strike_label?: string;
  is_seed?: boolean;
}

export interface OutsidersResponse {
  golden: OutsiderData[];
  regular: OutsiderData[];
  total_active: number;
}

export interface Transaction {
  _id: string;
  type: 'purchase' | 'use' | 'refund';
  amount?: number;
  description: string;
  timestamp: string;
  price?: number;
  pack?: string;
}

export const BOOSTER_TIERS: BoosterTier[] = [
  {
    id: 'booster',
    name: 'Booster',
    price: 0.99,
    duration_hours: 1,
    position: 'bottom',
    description: 'Get a spot in the Outsiders ranking for 1 hour. Get noticed by the community.',
  },
  {
    id: 'super_booster',
    name: 'Super Booster',
    price: 9.99,
    duration_hours: 24,
    position: 'bottom',
    description: 'Get a spot in the Outsiders ranking for 24 hours. More time = more votes = better climb.',
  },
  {
    id: 'golden_booster',
    name: 'Golden Booster',
    price: 49.99,
    duration_hours: 168,
    position: 'top',
    description: 'Priority placement in Outsiders + Home page rotation + exclusive Daily Run access.',
  },
];

// Keep old exports for backwards compatibility
export const BOOSTER_PACKS = BOOSTER_TIERS.map(t => ({
  id: t.id,
  name: t.name,
  votes: 0,
  price: t.price,
  popular: t.id === 'golden_booster',
}));

export const CREDIT_PACKS = BOOSTER_PACKS;

export interface BoosterBalance {
  active_boosts: number;
  boosters: number;
  super_boosters: number;
  is_premium: boolean;
}

// ---- Service ----

export class CreditsService {

  static async boostMyself(
    name: string,
    tier: string = 'booster',
    socialLinks?: SocialLinks,
    email?: string,
    receipt?: string,
    platform?: string,
  ): Promise<any> {
    try {
      const userId = await getUserId();
      const response = await fetch(API('/boost-myself'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          name: name.trim(),
          tier,
          social_links: socialLinks || {},
          email: email || '',
          receipt: receipt || '',
          platform: platform || '',
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to activate boost');
      }
      return await response.json();
    } catch (error: any) {
      console.error('Boost myself error:', error);
      throw error;
    }
  }

  static async extendBoost(boostId: string, tier: string): Promise<any> {
    try {
      const userId = await getUserId();
      const response = await fetch(API('/boost-myself/extend'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          boost_id: boostId,
          tier,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to extend boost');
      }
      return await response.json();
    } catch (error: any) {
      console.error('Extend boost error:', error);
      throw error;
    }
  }

  static async getOutsiders(): Promise<OutsidersResponse> {
    try {
      const response = await fetch(API('/outsiders'));
      if (!response.ok) throw new Error('Failed to get outsiders');
      return await response.json();
    } catch (error) {
      console.error('Get outsiders error:', error);
      return { golden: [], regular: [], total_active: 0 };
    }
  }

  static async getBalance(): Promise<BoosterBalance> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/balance/${userId}`));
      if (!response.ok) throw new Error('Failed to get balance');
      const data = await response.json();
      return {
        active_boosts: data.active_boosts || 0,
        boosters: data.boosters || 0,
        super_boosters: data.super_boosters || 0,
        is_premium: data.is_premium || false,
      };
    } catch (error) {
      console.error('Get balance error:', error);
      return { active_boosts: 0, boosters: 0, super_boosters: 0, is_premium: false };
    }
  }

  static async getHistory(limit: number = 20): Promise<Transaction[]> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/history/${userId}?limit=${limit}`));
      if (!response.ok) throw new Error('Failed to get history');
      const data = await response.json();
      return data.transactions || [];
    } catch (error) {
      console.error('Get history error:', error);
      return [];
    }
  }

  // Backwards compat stubs
  static async purchaseCredits(packId: string): Promise<any> {
    return { success: true, message: 'Use boost-myself instead' };
  }
  static async useBooster(personId: string, personName: string, vote: number, boosterType: string): Promise<any> {
    return { success: true };
  }
  static async useCreditForVote(personId: string, personName: string, vote: number): Promise<any> {
    return { success: true };
  }

  static async getActiveBoostDetails(): Promise<any> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/balance/${userId}`));
      if (!response.ok) throw new Error('Failed to get balance');
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Get active boost details error:', error);
      return { active_boosts: 0, boost_details: [] };
    }
  }

  /**
   * Check if the current user has an active boost.
   * Returns the first active boost detail if found, or null.
   */
  static async getExistingActiveBoost(): Promise<{
    tier: string;
    tier_name: string;
    name: string;
    end_time: string;
  } | null> {
    try {
      const userId = await getUserId();
      const response = await fetch(API(`/credits/balance/${userId}`));
      if (!response.ok) return null;
      const data = await response.json();
      if (data.active_boosts > 0 && data.boost_details && data.boost_details.length > 0) {
        const boost = data.boost_details[0];
        const tierInfo = BOOSTER_TIERS.find(t => t.id === boost.tier);
        return {
          tier: boost.tier,
          tier_name: tierInfo?.name || boost.tier,
          name: boost.name || '',
          end_time: boost.end_time,
        };
      }
      return null;
    } catch (error) {
      console.error('Check existing boost error:', error);
      return null;
    }
  }

  static async updateSocialLinks(boostId: string, links: SocialLinks): Promise<any> {
    try {
      const response = await fetch(API(`/outsiders/${boostId}/social-links`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(links),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update social links');
      }
      return await response.json();
    } catch (error: any) {
      console.error('Update social links error:', error);
      throw error;
    }
  }
}

// ---- React Hook ----

export function useCredits() {
  const [activeBoosts, setActiveBoosts] = useState(0);
  const [boosters, setBoosters] = useState(0);
  const [superBoosters, setSuperBoosters] = useState(0);
  const [isPremium, setIsPremium] = useState(false);
  const [loading, setLoading] = useState(true);

  const balance = activeBoosts;

  const loadBalance = useCallback(async () => {
    setLoading(true);
    try {
      const data = await CreditsService.getBalance();
      setActiveBoosts(data.active_boosts);
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
    return CreditsService.purchaseCredits(packId);
  };

  const useBooster = async (personId: string, personName: string, vote: number, boosterType: string = 'booster') => {
    return CreditsService.useBooster(personId, personName, vote, boosterType);
  };

  const useCredit = async (personId: string, personName: string, vote: number) => {
    return useBooster(personId, personName, vote, 'booster');
  };

  return {
    balance,
    activeBoosts,
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
