/**
 * Shared utility for the person page's 4-state trend status badge.
 *
 * V1.0: deterministic hash (cosmetic "market effect").
 * V1.5 BACKLOG: replace with real backend signal.
 */

export type TrendStatus = "rising" | "falling" | "trending" | "freefall";

interface TrendInput {
  name: string;
  score: number;
}

function computeHash(input: TrendInput): number {
  const nameHash = input.name
    .split("")
    .reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const hourFactor = new Date().getHours();
  const scoreFactor = Math.floor((input.score || 50) / 10);
  return (nameHash + hourFactor + scoreFactor) % 20;
}

/**
 * Returns the detailed 4-state status for the person page.
 * Distribution: trending 25% / rising 25% / falling 20% / freefall 10% / rising (neutral) 20%
 */
export function getTrendStatus(input: TrendInput): TrendStatus {
  const hash = computeHash(input);

  if (hash < 5) return "trending";
  if (hash < 10) return "rising";
  if (hash < 14) return "falling";
  if (hash < 16) return "freefall";
  return "rising";
}
