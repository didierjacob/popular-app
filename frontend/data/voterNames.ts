/**
 * Voter names and countries by language for the Live Activity feed.
 * Used by generateDummyVote() in person.tsx to create credible virtual votes.
 *
 * Vague 1 — Sujets B+C: Differentiated virtual vote display.
 */

export type SupportedLang = "fr" | "en" | "es" | "de" | "it" | "pt";

// ── First name pools (~50 per language) ──

export const NAMES_BY_LANG: Record<SupportedLang | "international", string[]> = {
  fr: [
    "Marie", "Pierre", "Sophie", "Lucas", "Camille", "Antoine", "Léa", "Hugo",
    "Manon", "Théo", "Chloé", "Raphaël", "Inès", "Nathan", "Jade", "Louis",
    "Emma", "Gabriel", "Alice", "Arthur", "Juliette", "Adam", "Zoé", "Paul",
    "Lina", "Tom", "Clara", "Jules", "Léna", "Maxime", "Romane", "Mathis",
    "Eva", "Enzo", "Mila", "Adrien", "Margaux", "Axel", "Victoire", "Romain",
    "Célia", "Bastien", "Anaïs", "Clément", "Ambre", "Victor", "Louise",
    "Nolan", "Élodie", "Tristan",
  ],
  en: [
    "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason",
    "Isabella", "Logan", "Mia", "Jacob", "Charlotte", "William", "Amelia",
    "Lucas", "Harper", "Benjamin", "Evelyn", "James", "Abigail", "Alexander",
    "Emily", "Michael", "Elizabeth", "Daniel", "Sofia", "Henry", "Avery",
    "Joseph", "Ella", "Samuel", "Madison", "David", "Scarlett", "Owen",
    "Victoria", "Wyatt", "Aria", "John", "Grace", "Sebastian", "Chloe",
    "Carter", "Penelope", "Julian", "Layla", "Levi", "Riley", "Isaac",
  ],
  es: [
    "Carlos", "María", "José", "Sofía", "Diego", "Lucía", "Mateo", "Valentina",
    "Sebastián", "Camila", "Daniel", "Isabella", "Alejandro", "Mariana",
    "Andrés", "Gabriela", "Santiago", "Daniela", "Miguel", "Paula", "Javier",
    "Andrea", "Pablo", "Natalia", "Adrián", "Carolina", "Marcos", "Laura",
    "Tomás", "Beatriz", "Rafael", "Elena", "Manuel", "Patricia", "Antonio",
    "Cristina", "Francisco", "Marta", "Eduardo", "Ana", "Fernando", "Carmen",
    "Ricardo", "Pilar", "Luis", "Rosa", "Roberto", "Teresa", "Jorge", "Mónica",
  ],
  de: [
    "Lukas", "Lena", "Maximilian", "Hannah", "Felix", "Anna", "Paul", "Sophie",
    "Leon", "Emma", "Jonas", "Mia", "David", "Lea", "Tim", "Lina", "Niklas",
    "Marie", "Tom", "Laura", "Moritz", "Sarah", "Finn", "Lara", "Elias",
    "Julia", "Noah", "Clara", "Henry", "Charlotte", "Ben", "Maria", "Jakob",
    "Johanna", "Anton", "Emilia", "Karl", "Lisa", "Erik", "Katharina",
    "Friedrich", "Greta", "Wilhelm", "Helene", "Heinrich", "Theresa", "Otto",
    "Anneliese", "Werner", "Hilde",
  ],
  it: [
    "Marco", "Giulia", "Luca", "Sofia", "Matteo", "Aurora", "Lorenzo", "Alice",
    "Andrea", "Giorgia", "Francesco", "Emma", "Tommaso", "Beatrice",
    "Alessandro", "Anna", "Riccardo", "Sara", "Gabriele", "Greta", "Davide",
    "Vittoria", "Edoardo", "Chiara", "Leonardo", "Martina", "Filippo", "Elena",
    "Mattia", "Camilla", "Antonio", "Francesca", "Giovanni", "Caterina",
    "Federico", "Bianca", "Stefano", "Linda", "Giacomo", "Margherita",
    "Pietro", "Eleonora", "Cristiano", "Ludovica", "Niccolò", "Rebecca",
    "Samuele", "Ginevra", "Roberto", "Isabella",
  ],
  pt: [
    "Miguel", "Maria", "João", "Beatriz", "Tiago", "Matilde", "Diogo",
    "Leonor", "Rodrigo", "Carolina", "Gabriel", "Sofia", "Pedro", "Mariana",
    "Tomás", "Ana", "André", "Inês", "Guilherme", "Catarina", "Francisco",
    "Margarida", "Rafael", "Joana", "Bruno", "Rita", "Daniel", "Diana",
    "Henrique", "Madalena", "Bernardo", "Constança", "Vasco", "Helena",
    "Afonso", "Lara", "Eduardo", "Bárbara", "Filipe", "Vitória", "Manuel",
    "Patrícia", "Carlos", "Cristina", "José", "Mónica", "António", "Andreia",
    "Luís", "Susana",
  ],
  international: [
    "Aiden", "Mia", "Yuki", "Ahmed", "Priya", "Wei", "Jorge", "Lena",
    "Omar", "Sakura", "Khalid", "Anya", "Mateo", "Fatima", "Hiroshi",
    "Aisha", "Hugo", "Mei", "Kai", "Layla", "Diego", "Idris", "Tara",
    "Liu", "Zara", "Hassan", "Aria", "Yusuf", "Ines", "Chen",
  ],
};

// ── Country pools by language ──
// Sujet 3 (i18n pays): on stocke des codes ISO 3166-1 alpha-2.
// Le rendu côté UI traduit via i18n (countries.XX) dans la langue
// de l'app du user, avec fallback sur le code si absent.

export const COUNTRIES_BY_LANG: Record<SupportedLang | "international", string[]> = {
  fr: ["FR", "BE", "CH", "CA", "MA", "SN", "TN", "DZ"],
  en: ["US", "GB", "CA", "AU", "NZ", "IE", "ZA"],
  es: ["ES", "MX", "AR", "CO", "CL", "PE", "VE"],
  de: ["DE", "AT", "CH"],
  it: ["IT", "CH", "SM"],
  pt: ["PT", "BR", "AO", "MZ"],
  international: [
    "US", "GB", "FR", "JP", "DE", "ES", "IT", "CA", "AU", "BR",
    "MX", "IN", "KR", "NL", "SE", "PT", "AR", "CO", "BE", "CH",
  ],
};

// ── Helper: pick a random name respecting geo coefficient ──

/**
 * Returns a random first name adapted to the geo coefficient and dominant language.
 *
 * @param dominantLang - The dominant language for this personality (e.g. "fr", "en")
 * @param geoLocal - Local coefficient (0.0 to 1.0). 1.0 = 100% local names.
 * @param recentNames - Array of recently used names (to avoid repetition)
 * @returns A first name string
 */
export function pickVoterName(
  dominantLang: SupportedLang,
  geoLocal: number,
  recentNames: string[] = [],
): string {
  const useLocal = Math.random() < geoLocal;
  const pool = useLocal
    ? NAMES_BY_LANG[dominantLang] || NAMES_BY_LANG.international
    : NAMES_BY_LANG.international;

  // Filter out recent names for variety
  const filtered = pool.filter((n) => !recentNames.includes(n));
  const finalPool = filtered.length > 0 ? filtered : pool;

  return finalPool[Math.floor(Math.random() * finalPool.length)];
}

/**
 * Returns a random country ISO 3166-1 alpha-2 code (e.g. "FR", "BE", "JP")
 * adapted to the geo coefficient and dominant language.
 * Le code est ensuite traduit côté UI via i18n (countries.XX).
 */
export function pickVoterCountry(
  dominantLang: SupportedLang,
  geoLocal: number,
): string {
  const useLocal = Math.random() < geoLocal;
  const pool = useLocal
    ? COUNTRIES_BY_LANG[dominantLang] || COUNTRIES_BY_LANG.international
    : COUNTRIES_BY_LANG.international;

  return pool[Math.floor(Math.random() * pool.length)];
}
