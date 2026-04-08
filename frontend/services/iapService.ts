import { Platform } from 'react-native';
import {
  initConnection,
  endConnection,
  getProducts,
  requestPurchase,
  finishTransaction,
  purchaseUpdatedListener,
  purchaseErrorListener,
  type ProductPurchase,
  type PurchaseError,
  type Product,
} from 'react-native-iap';

// Product IDs - must match App Store Connect & Google Play Console
export const IAP_PRODUCT_IDS = {
  booster: 'popularoo_booster',            // €0.99 - 1 hour
  super_booster: 'popularoo_super_booster', // €9.99 - 24 hours
  golden_booster: 'popularoo_golden_booster', // €49.99 - 1 week
};

export const IAP_SKUS = Object.values(IAP_PRODUCT_IDS);

class IAPService {
  private connected = false;
  private purchaseUpdateSubscription: any = null;
  private purchaseErrorSubscription: any = null;

  async init(): Promise<boolean> {
    try {
      const result = await initConnection();
      this.connected = true;
      console.log('[IAP] Connection initialized:', result);
      return true;
    } catch (error) {
      console.error('[IAP] Failed to init connection:', error);
      this.connected = false;
      return false;
    }
  }

  async getStoreProducts(): Promise<Product[]> {
    if (!this.connected) {
      await this.init();
    }
    try {
      const products = await getProducts({ skus: IAP_SKUS });
      console.log('[IAP] Products loaded:', products.length);
      return products;
    } catch (error) {
      console.error('[IAP] Failed to get products:', error);
      return [];
    }
  }

  async purchase(sku: string): Promise<void> {
    if (!this.connected) {
      await this.init();
    }
    try {
      if (Platform.OS === 'android') {
        await requestPurchase({ skus: [sku] });
      } else {
        await requestPurchase({ sku });
      }
    } catch (error: any) {
      // User cancelled is not an error
      if (error?.code === 'E_USER_CANCELLED') {
        console.log('[IAP] User cancelled purchase');
        return;
      }
      console.error('[IAP] Purchase error:', error);
      throw error;
    }
  }

  async finishPurchase(purchase: ProductPurchase, isConsumable: boolean = true): Promise<void> {
    try {
      await finishTransaction({ purchase, isConsumable });
      console.log('[IAP] Transaction finished:', purchase.productId);
    } catch (error) {
      console.error('[IAP] Failed to finish transaction:', error);
    }
  }

  setupListeners(
    onPurchaseSuccess: (purchase: ProductPurchase) => void,
    onPurchaseError: (error: PurchaseError) => void,
  ) {
    this.purchaseUpdateSubscription = purchaseUpdatedListener(onPurchaseSuccess);
    this.purchaseErrorSubscription = purchaseErrorListener(onPurchaseError);
  }

  removeListeners() {
    if (this.purchaseUpdateSubscription) {
      this.purchaseUpdateSubscription.remove();
      this.purchaseUpdateSubscription = null;
    }
    if (this.purchaseErrorSubscription) {
      this.purchaseErrorSubscription.remove();
      this.purchaseErrorSubscription = null;
    }
  }

  async disconnect(): Promise<void> {
    this.removeListeners();
    try {
      await endConnection();
      this.connected = false;
      console.log('[IAP] Connection ended');
    } catch (error) {
      console.error('[IAP] Failed to end connection:', error);
    }
  }

  // Map our tier IDs to store product IDs
  getProductIdForTier(tierId: string): string {
    return IAP_PRODUCT_IDS[tierId as keyof typeof IAP_PRODUCT_IDS] || tierId;
  }

  // Map store product IDs back to our tier IDs
  getTierIdForProduct(productId: string): string | null {
    const entry = Object.entries(IAP_PRODUCT_IDS).find(([_, sku]) => sku === productId);
    return entry ? entry[0] : null;
  }
}

export const iapService = new IAPService();
