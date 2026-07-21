import { useEffect, useState } from "react";

// Chantier « cœur honnête » — masquage des compteurs de soutien/votes.
// Lit app_settings.show_vote_counts via GET /api/public-config.
// Défaut FALSE (masqué) : au lancement, et si le fetch échoue, on ne révèle
// jamais de compteurs. Les Outsiders ne passent PAS par ce hook (affichage
// inchangé — hors périmètre).

const API_BASE =
  process.env.EXPO_PUBLIC_BACKEND_URL || "https://popular-app.onrender.com";

let _cached: boolean | null = null;

export function useShowVoteCounts(): boolean {
  const [show, setShow] = useState<boolean>(_cached ?? false);

  useEffect(() => {
    let alive = true;
    if (_cached !== null) {
      setShow(_cached);
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/public-config`);
        const data = await res.json();
        const val = !!data?.show_vote_counts;
        _cached = val;
        if (alive) setShow(val);
      } catch {
        _cached = false;
        if (alive) setShow(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return show;
}
