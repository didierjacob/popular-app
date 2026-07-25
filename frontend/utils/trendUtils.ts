/**
 * Badge de tendance de la fiche personne — piloté par le VRAI signal backend.
 *
 * Chantier « cote qui bouge » : plus de hash cosmétique. La flèche/tendance dérive
 * de `vote_momentum` (sens du dernier vote encaissé, posé par le backend : "up" =
 * like, "down" = dislike) et de `delta` (variation d'indice au dernier vote, quand
 * disponible) qui distingue un mouvement fort (trending / freefall) d'un mouvement
 * simple (rising / falling).
 *
 * Renvoie null quand il n'y a pas de vrai vote (momentum absent) → pas de badge.
 */

export type TrendStatus = "rising" | "falling" | "trending" | "freefall";

interface TrendInput {
  momentum?: "up" | "down" | null;
  delta?: number; // variation d'indice (points) au dernier vote — optionnelle
}

// Seuil (points d'indice) au-delà duquel un mouvement est « fort ».
const STRONG_MOVE = 3;

export function getTrendStatus(input: TrendInput): TrendStatus | null {
  const { momentum, delta } = input;
  if (momentum !== "up" && momentum !== "down") return null; // pas de vrai vote

  const strong = typeof delta === "number" && Math.abs(delta) >= STRONG_MOVE;
  if (momentum === "up") return strong ? "trending" : "rising";
  return strong ? "freefall" : "falling";
}
