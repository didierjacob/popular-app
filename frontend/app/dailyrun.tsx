// =============================================================================
// DAILY RUN — DESACTIVE EN V1 (App Store release)
// =============================================================================
//
// Statut V1.0 :
//   - Ecran masque (placeholder redirect vers Home)
//   - Aucune entree de navigation visible (ni tab bar, ni bouton, ni icone)
//   - Backend INTACT et fonctionnel :
//       * backend/scheduler.py (jobs recurrents)
//       * Endpoints daily-run/* dans backend/server.py (19 endpoints, ne pas
//         toucher : utilises notamment par le scheduler et le panel admin
//         pour l'annulation auto lors de desactivation/deces d'un profil)
//
// Raison du retrait V1 :
//   Ecran integralement en mock data depuis trop longtemps. Le cablage des
//   endpoints serait un gros chantier qui retarderait le lancement App Store.
//   Decision produit : on retire pour V1, on recupere pour V2.
//
// Procedure de reactivation V2 :
//   1. Restaurer le contenu original depuis : frontend/disabled_v2/dailyrun.tsx
//      (copie verbatim de la version pre-retrait)
//      Commande : cp frontend/disabled_v2/dailyrun.tsx frontend/app/dailyrun.tsx
//   2. Dans frontend/app/_layout.tsx, remettre l'entree dailyrun visible :
//      retirer "href: null" et ajouter un title + tabBarIcon.
//   3. Cabler les endpoints backend daily-run/* (deja disponibles).
//   4. Retirer le repertoire frontend/disabled_v2/ une fois la reactivation OK.
//
// Note : la cle i18n "dailyRun" / "dailyRunsUsed" / "gdprDailyRuns" est en
// realite repurposed pour la feature Premium (traduit "Premium" partout).
// Le compteur account.tsx data_summary.daily_runs reste connecte au backend
// GDPR — c'est un affichage passif, pas une navigation, on ne touche pas.
//
// =============================================================================

import React, { useEffect } from "react";
import { useRouter } from "expo-router";

export default function DailyRunDisabledV1() {
  const router = useRouter();

  useEffect(() => {
    // Deep-link safety : si quelqu'un atteint /dailyrun, on renvoie vers Home.
    router.replace("/");
  }, [router]);

  return null;
}
