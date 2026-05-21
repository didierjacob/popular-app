import { Platform } from 'react-native';
import {
  initConnection,
  endConnection,
  getProducts,
  getAvailablePurchases,
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

  // Fetches IAP products with retry + backoff. On iOS/iPad, StoreKit can return
  // 0 products on the first call right after initConnection (the connection isn't
  // fully ready yet) — a single shot would leave the UI stuck. We retry, re-initing
  // the connection between attempts, before giving up. (Chantier 3 — Apple 2.1 iPad fix)
  async getStoreProducts(retries: number = 3, baseDelayMs: number = 1500): Promise<Product[]> {
    if (!this.connected) {
      await this.init();
    }
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        const products = await getProducts({ skus: IAP_SKUS });
        if (products.length > 0) {
          console.log(`[IAP] Products loaded: ${products.length} (attempt ${attempt}/${retries})`);
          return products;
        }
        console.warn(`[IAP] StoreKit returned 0 products (attempt ${attempt}/${retries}) for SKUs:`, IAP_SKUS);
      } catch (error) {
        console.error(`[IAP] Network/exception while fetching products (attempt ${attempt}/${retries}):`, error);
      }
      if (attempt < retries) {
        // Connection may not have been ready — re-init, then back off (1.5s, 3s, …)
        try { await this.init(); } catch { /* keep retrying */ }
        await new Promise((resolve) => setTimeout(resolve, baseDelayMs * attempt));
      }
    }
    console.error(
      '[IAP] StoreKit returned 0 products after', retries, 'attempts for SKUs:', IAP_SKUS,
      '— likely causes: IAP not attached to current build in App Store Connect, sandbox tester not signed in, IAP status not "Ready to Submit", or bundle ID mismatch.'
    );
    return [];
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

  async restorePurchases(): Promise<ProductPurchase[]> {
    if (!this.connected) {
      await this.init();
    }
    try {
      const purchases = await getAvailablePurchases();
      console.log('[IAP] Restored purchases:', purchases.length);
      // Finish any pending consumable transactions
      for (const purchase of purchases) {
        try {
          await finishTransaction({ purchase, isConsumable: true });
        } catch (e) {
          console.warn('[IAP] Could not finish restored purchase:', e);
        }
      }
      return purchases;
    } catch (error) {
      console.error('[IAP] Failed to restore purchases:', error);
      throw error;
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
