// =============================================================================
// BULL RUN — DESACTIVE EN V1 (App Store release)
// =============================================================================
//
// Statut V1.0 :
//   - Ecran masque (placeholder redirect vers Home)
//   - Aucune entree de navigation visible (ni tab bar, ni bouton, ni icone)
//   - Backend INTACT et fonctionnel :
//       * backend/bull_run.py (logique metier)
//       * backend/scheduler.py (jobs recurrents)
//       * Endpoints bull-run/* dans backend/server.py
//
// Raison du retrait V1 :
//   Ecran integralement en mock data depuis trop longtemps. Le cablage des
//   endpoints serait un gros chantier qui retarderait le lancement App Store.
//   Decision produit : on retire pour V1, on recupere pour V2.
//
// Procedure de reactivation V2 :
//   1. Restaurer le contenu original depuis : frontend/disabled_v2/bullrun.tsx
//      (copie verbatim de la version pre-retrait)
//      Commande : cp frontend/disabled_v2/bullrun.tsx frontend/app/bullrun.tsx
//   2. Dans frontend/app/_layout.tsx, remettre l'entree bullrun visible :
//      retirer "href: null" et ajouter un title + tabBarIcon.
//   3. Cabler les endpoints backend bull-run/* (deja disponibles).
//   4. Retirer le repertoire frontend/disabled_v2/ une fois la reactivation OK.
//
// =============================================================================

import React, { useEffect } from "react";
import { useRouter } from "expo-router";

export default function BullRunDisabledV1() {
  const router = useRouter();

  useEffect(() => {
    // Deep-link safety : si quelqu'un atteint /bullrun, on renvoie vers Home.
    router.replace("/");
  }, [router]);

  return null;
}
