/**
 * Shared utility for computing deterministic trend status across the app.
 * Ensures coherence between list arrows and person page statuses.
 * 
 * V1.0: Uses deterministic hash (cosmetic "market effect").
 * V1.5 BACKLOG: Replace with real 24h delta from backend API.
 * V1.5 BACKLOG: Migrate Live Activity feed to backend-generated data
 *   (dedicated table of simulated votes, scriptable scenarios, inter-user coherence).
 */

export type TrendDirection = "up" | "down" | "equal";
export type TrendStatus = "rising" | "falling" | "trending" | "freefall";

interface TrendInput {
  name: string;
  score: number;
}

/**
 * Computes a stable hash from a person's name + current hour.
 * Changes once per hour for a "market movement" effect.
 */
function computeHash(input: TrendInput): number {
  const nameHash = input.name
    .split("")
    .reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const hourFactor = new Date().getHours();
  const scoreFactor = Math.floor((input.score || 50) / 10);
  return (nameHash + hourFactor + scoreFactor) % 20;
}

/**
 * Returns the simplified direction (up/down/equal) for list views.
 * Distribution: ~50% up, ~30% down, ~20% equal
 */
export function getTrendDirection(input: TrendInput): TrendDirection {
  const hash = computeHash(input);
  if (hash < 10) return "up";     // 50% (0-9)
  if (hash < 16) return "down";   // 30% (10-15)
  return "equal";                   // 20% (16-19)
}

/**
 * Returns the detailed 4-state status for the person page.
 * Must be coherent with getTrendDirection:
 *   - up    → rising OR trending
 *   - down  → falling OR freefall
 *   - equal → rising (neutral-positive bias)
 */
export function getTrendStatus(input: TrendInput): TrendStatus {
  const hash = computeHash(input);
  
  // 0-4: trending (strong up - 25%)
  if (hash < 5) return "trending";
  // 5-9: rising (mild up - 25%)
  if (hash < 10) return "rising";
  // 10-13: falling (mild down - 20%)
  if (hash < 14) return "falling";
  // 14-15: freefall (strong down - 10%)
  if (hash < 16) return "freefall";
  // 16-19: rising (equal/neutral - 20%)
  return "rising";
}

/**
 * Returns true if the item should have a "glow" effect in list views.
 * Corresponds to "trending" status (strong performers).
 */
export function hasGlowEffect(input: TrendInput): boolean {
  const hash = computeHash(input);
  return hash < 5; // Same items that get "trending" status
}
