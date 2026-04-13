// Web fallback for iapService - react-native-iap is native only
import { Platform } from 'react-native';

export const IAP_PRODUCT_IDS = {
  booster: 'popularoo_booster',
  super_booster: 'popularoo_super_booster',
  golden_booster: 'popularoo_golden_booster',
};

export const IAP_SKUS = Object.values(IAP_PRODUCT_IDS);

class IAPService {
  async init(): Promise<boolean> {
    console.warn('[IAP] Not available on web');
    return false;
  }

  async getStoreProducts(): Promise<any[]> {
    return [];
  }

  async purchase(sku: string): Promise<void> {
    throw new Error('In-App Purchases are not available on web');
  }

  async finishPurchase(purchase: any, isConsumable: boolean = true): Promise<void> {}

  setupListeners(onSuccess: any, onError: any) {}

  removeListeners() {}

  async disconnect(): Promise<void> {}

  async restorePurchases(): Promise<any[]> {
    return [];
  }

  getProductIdForTier(tierId: string): string {
    return IAP_PRODUCT_IDS[tierId as keyof typeof IAP_PRODUCT_IDS] || tierId;
  }

  getTierIdForProduct(productId: string): string | null {
    const entry = Object.entries(IAP_PRODUCT_IDS).find(([_, sku]) => sku === productId);
    return entry ? entry[0] : null;
  }
}

export const iapService = new IAPService();
