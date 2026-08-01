/**
 * Libellé traduit d'une catégorie de personnalité.
 *
 * Les catégories transitent en clés techniques anglaises (`politics`, `culture`,
 * `business`, `sport`, `influencer`, `other`, `outsider` — cf. server.py:334) et
 * doivent TOUJOURS être affichées via `categories.*`, dont les 7 clés existent
 * déjà dans les 6 langues. Plusieurs écrans les rendaient brutes ou capitalisées,
 * donc en anglais quelle que soit la langue de l'app.
 *
 * POURQUOI UN HELPER plutôt que `t(\`categories.${cat}\`)` inline : le motif
 * répandu dans le code était
 *
 *     t(`categories.${cat}`) || capitalize(cat)
 *
 * dont le repli est MORT. `t()` ne renvoie jamais de chaîne vide : sur clé absente
 * il renvoie la CLÉ elle-même (« categories.xyz »), qui est truthy. Le `||` ne se
 * déclenche donc jamais, et une clé manquante s'afficherait telle quelle — un
 * chemin technique sous les yeux de l'utilisateur. Ici on compare explicitement au
 * chemin de la clé pour détecter l'absence et retomber sur un libellé lisible.
 */

const capitalize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

type TFunc = (key: string) => string;

export function categoryLabel(t: TFunc, category?: string | null): string {
  const key = (category || "other").trim() || "other";
  const path = `categories.${key}`;
  const label = t(path);
  // i18next renvoie le chemin lui-même quand la clé n'existe pas.
  return label === path ? capitalize(key) : label;
}
