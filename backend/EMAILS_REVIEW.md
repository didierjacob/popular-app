# POPULAROO — Corpus Complet des Emails Transactionnels
## Version finale pour validation — 6 langues × 9 variantes

> **Règles de wording** : Les termes de marque (Booster, Super Booster, Golden Booster, Strike, Legend Mode, Going Viral, Daily Run, Superlike, Popularoo Index, Victory Tiers, Standard Win, Underdog Win, Legendary Strike, Outsider) restent TOUJOURS en anglais.
> "stock market of fame" reste aussi en anglais dans toutes les langues.

> **Variables dynamiques** :
> - `{{name}}` → Prénom de l'utilisateur
> - `{{tierName}}` → "Booster", "Super Booster" ou "Golden Booster" (EN invariant)
> - `{{duration}}` → Localisé automatiquement : "24 hours" / "24 heures" / "24 horas" / "24 Stunden" / "24 ore"
> - `{{timeRemaining}}` → Localisé automatiquement : "3 hours" / "3 heures" / "3 horas" / "3 Stunden" / "3 ore"
> - `{{targetName}}` → Nom de la personnalité (ex: "Elon Musk")
> - `{{gap}}`, `{{votesReceived}}`, `{{totalVotes}}`, `{{bestRank}}`, `{{dailyRunsCount}}`, `{{strikesCount}}` → Nombres
> - `{{victoryTier}}` → "Standard Win", "Underdog Win" ou "Legendary Strike" (EN invariant)
> - `{{highestStrike}}` → "Trending", "Going Viral", "Legend Mode" (EN invariant)

---

## EMAIL 1 — Booster Purchase Confirmation
*Déclencheur : Chaque achat de Booster sauf le premier (voir Email 5)*

### 🇬🇧 EN
**Subject:** Your {{tierName}} is live! 🚀

Hey {{name}},

Your {{tierName}} just went live! You're now visible in the Outsiders ranking.

What's active:
• {{tierName}} — {{duration}}
• Your profile is live and collecting votes right now

*[Si Golden Booster:]* You also have priority placement on the Home page and access to Daily Runs. Make it count!

Go check your position and share your profile to rally votes.

— The Popularoo Team

---

### 🇫🇷 FR
**Subject:** Ton {{tierName}} est actif ! 🚀

Salut {{name}},

Ton {{tierName}} vient d'être activé ! Tu es maintenant visible dans le classement Outsiders.

Ce qui est actif :
• {{tierName}} — {{duration}}
• Ton profil est en ligne et collecte des votes en ce moment

*[Si Golden Booster:]* Tu as aussi un placement prioritaire en page d'accueil et un accès aux Daily Runs. Fais-en bon usage !

Va vérifier ta position et partage ton profil pour rallier des votes.

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject:** ¡Tu {{tierName}} está activo! 🚀

¡Hola {{name}}!

¡Tu {{tierName}} acaba de activarse! Ya eres visible en el ranking Outsiders.

Lo que está activo:
• {{tierName}} — {{duration}}
• Tu perfil está en línea y recibiendo votos ahora mismo

*[Si Golden Booster:]* También tienes ubicación prioritaria en la portada y acceso a Daily Runs. ¡Aprovéchalo!

Ve a ver tu posición y comparte tu perfil para conseguir votos.

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject:** Seu {{tierName}} está ativo! 🚀

Oi {{name}},

Seu {{tierName}} acabou de ser ativado! Você já está visível no ranking Outsiders.

O que está ativo:
• {{tierName}} — {{duration}}
• Seu perfil está no ar e recebendo votos agora mesmo

*[Si Golden Booster:]* Você também tem posição prioritária na Home e acesso aos Daily Runs. Aproveite!

Confira sua posição e compartilhe seu perfil para conseguir votos.

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject:** Dein {{tierName}} ist aktiv! 🚀

Hey {{name}},

Dein {{tierName}} ist jetzt aktiv! Du bist ab sofort im Outsiders-Ranking sichtbar.

Was aktiv ist:
• {{tierName}} — {{duration}}
• Dein Profil ist live und sammelt gerade Stimmen

*[Si Golden Booster:]* Du hast außerdem eine Prioritätsplatzierung auf der Startseite und Zugang zu Daily Runs. Nutze es!

Schau dir deine Position an und teile dein Profil, um Stimmen zu sammeln.

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject:** Il tuo {{tierName}} è attivo! 🚀

Ciao {{name}},

Il tuo {{tierName}} è appena stato attivato! Ora sei visibile nella classifica Outsiders.

Cosa è attivo:
• {{tierName}} — {{duration}}
• Il tuo profilo è online e sta raccogliendo voti in questo momento

*[Si Golden Booster:]* Hai anche un posizionamento prioritario in homepage e accesso ai Daily Runs. Sfruttalo!

Vai a controllare la tua posizione e condividi il tuo profilo per raccogliere voti.

— Il team Popularoo

---
---

## EMAIL 2 — Daily Run Victory
*Déclencheur : Immédiat quand l'Outsider gagne un Daily Run*
*3 variantes de subject selon le Victory Tier*

### 🇬🇧 EN
**Subject (Standard Win):** You won your Daily Run! 🏆
**Subject (Underdog Win):** Underdog victory! You crushed it! 💪
**Subject (Legendary Strike):** LEGENDARY! You just made Popularoo history! ⚡

Hey {{name}},

{{victoryTier}}! You just beat {{targetName}} in a Daily Run.

Your results:
• Final Popularoo Index gap: {{gap}} points
• Victory Tier: {{victoryTier}}
• Votes received during the Run: {{votesReceived}}
*[Si Strikes:]* • Strikes triggered: {{strikesCount}} (highest: {{highestStrike}})

*[Si Legendary:]* This is the rarest kind of victory in Popularoo. Less than 1% of Runs end this way. Your community showed up in a massive way.
*[Si Underdog:]* Taking down a personality {{gap}} points above you is no small feat. Your supporters really came through.

Share your victory and keep the momentum going.

— The Popularoo Team

---

### 🇫🇷 FR
**Subject (Standard Win):** Tu as gagné ton Daily Run ! 🏆
**Subject (Underdog Win):** Victoire Underdog ! Tu as tout déchiré ! 💪
**Subject (Legendary Strike):** ÉPIQUE ! Tu viens d'écrire l'histoire de Popularoo ! ⚡

Salut {{name}},

{{victoryTier}} ! Tu viens de battre {{targetName}} dans un Daily Run.

Tes résultats :
• Écart final de Popularoo Index : {{gap}} points
• Victory Tier : {{victoryTier}}
• Votes reçus pendant le Run : {{votesReceived}}
*[Si Strikes:]* • Strikes déclenchés : {{strikesCount}} (plus haut : {{highestStrike}})

*[Si Legendary:]* C'est le type de victoire le plus rare sur Popularoo. Moins de 1% des Runs se terminent ainsi. Ta communauté s'est mobilisée de manière exceptionnelle.
*[Si Underdog:]* Battre une personnalité {{gap}} points au-dessus de toi n'est pas rien. Tes supporters ont vraiment assuré.

Partage ta victoire et maintiens la dynamique.

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject (Standard Win):** ¡Ganaste tu Daily Run! 🏆
**Subject (Underdog Win):** ¡Victoria Underdog! ¡Lo aplastaste! 💪
**Subject (Legendary Strike):** ¡ÉPICO! ¡Acabas de hacer historia en Popularoo! ⚡

¡Hola {{name}}!

¡{{victoryTier}}! Acabas de vencer a {{targetName}} en un Daily Run.

Tus resultados:
• Diferencia final de Popularoo Index: {{gap}} puntos
• Victory Tier: {{victoryTier}}
• Votos recibidos durante el Run: {{votesReceived}}
*[Si Strikes:]* • Strikes activados: {{strikesCount}} (máximo: {{highestStrike}})

*[Si Legendary:]* Esta es la victoria más rara en Popularoo. Menos del 1% de los Runs terminan así. Tu comunidad se movilizó de forma masiva.
*[Si Underdog:]* Derribar a una personalidad {{gap}} puntos por encima de ti no es poca cosa. Tus seguidores realmente dieron la talla.

Comparte tu victoria y mantén el impulso.

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject (Standard Win):** Você venceu seu Daily Run! 🏆
**Subject (Underdog Win):** Vitória Underdog! Você arrasou! 💪
**Subject (Legendary Strike):** ÉPICO! Você acabou de fazer história no Popularoo! ⚡

Oi {{name}},

{{victoryTier}}! Você acabou de vencer {{targetName}} em um Daily Run.

Seus resultados:
• Diferença final de Popularoo Index: {{gap}} pontos
• Victory Tier: {{victoryTier}}
• Votos recebidos durante o Run: {{votesReceived}}
*[Si Strikes:]* • Strikes ativados: {{strikesCount}} (mais alto: {{highestStrike}})

*[Si Legendary:]* Esta é a vitória mais rara no Popularoo. Menos de 1% dos Runs terminam assim. Sua comunidade se mobilizou de forma massiva.
*[Si Underdog:]* Derrubar uma personalidade {{gap}} pontos acima de você não é pouca coisa. Seus apoiadores realmente se superaram.

Compartilhe sua vitória e mantenha o momentum.

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject (Standard Win):** Du hast deinen Daily Run gewonnen! 🏆
**Subject (Underdog Win):** Underdog-Sieg! Du hast alles gegeben! 💪
**Subject (Legendary Strike):** EPISCH! Du hast Popularoo-Geschichte geschrieben! ⚡

Hey {{name}},

{{victoryTier}}! Du hast gerade {{targetName}} in einem Daily Run besiegt.

Deine Ergebnisse:
• Finaler Popularoo Index Abstand: {{gap}} Punkte
• Victory Tier: {{victoryTier}}
• Stimmen während des Runs erhalten: {{votesReceived}}
*[Si Strikes:]* • Strikes ausgelöst: {{strikesCount}} (höchster: {{highestStrike}})

*[Si Legendary:]* Das ist die seltenste Art von Sieg bei Popularoo. Weniger als 1% aller Runs enden so. Deine Community hat sich außergewöhnlich mobilisiert.
*[Si Underdog:]* Eine Persönlichkeit zu schlagen, die {{gap}} Punkte über dir liegt, ist keine Kleinigkeit. Deine Unterstützer haben wirklich geliefert.

Teile deinen Sieg und halte das Momentum aufrecht.

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject (Standard Win):** Hai vinto il tuo Daily Run! 🏆
**Subject (Underdog Win):** Vittoria Underdog! Hai spaccato! 💪
**Subject (Legendary Strike):** EPICO! Hai appena fatto la storia di Popularoo! ⚡

Ciao {{name}},

{{victoryTier}}! Hai appena battuto {{targetName}} in un Daily Run.

I tuoi risultati:
• Divario finale di Popularoo Index: {{gap}} punti
• Victory Tier: {{victoryTier}}
• Voti ricevuti durante il Run: {{votesReceived}}
*[Si Strikes:]* • Strikes attivati: {{strikesCount}} (più alto: {{highestStrike}})

*[Si Legendary:]* Questa è la vittoria più rara su Popularoo. Meno dell'1% dei Run finisce così. La tua community si è mobilitata in modo straordinario.
*[Si Underdog:]* Abbattere una personalità {{gap}} punti sopra di te non è uno scherzo. I tuoi sostenitori hanno davvero dato il massimo.

Condividi la tua vittoria e mantieni il momentum.

— Il team Popularoo

---
---

## EMAIL 3a — Strike: Going Viral
*Déclencheur : Immédiat quand l'Outsider atteint 4 Strikes simultanés*

### 🇬🇧 EN
**Subject:** Going Viral! Your momentum is incredible! 🌊

Hey {{name}},

You just reached Going Viral — one of the highest Strike levels in Popularoo.

Strike chain:
Heating Up → On Fire → Trending → Going Viral 🌊

Your community is sending a powerful wave of Superlikes. This kind of momentum is rare and puts you in a strong position.

If you're in a Daily Run, this could be the edge you need to land an Underdog or even a Legendary victory.

Keep pushing — Legend Mode is within reach!

— The Popularoo Team

---

### 🇫🇷 FR
**Subject:** Going Viral ! Ta dynamique est incroyable ! 🌊

Salut {{name}},

Tu viens d'atteindre Going Viral — l'un des plus hauts niveaux de Strike sur Popularoo.

Chaîne de Strikes :
Heating Up → On Fire → Trending → Going Viral 🌊

Ta communauté envoie une vague puissante de Superlikes. Ce type de dynamique est rare et te place en position de force.

Si tu es dans un Daily Run, c'est peut-être l'avantage qu'il te faut pour décrocher une victoire Underdog voire Legendary.

Continue à pousser — Legend Mode est à portée de main !

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject:** ¡Going Viral! ¡Tu impulso es increíble! 🌊

¡Hola {{name}}!

Acabas de alcanzar Going Viral — uno de los niveles de Strike más altos en Popularoo.

Cadena de Strikes:
Heating Up → On Fire → Trending → Going Viral 🌊

Tu comunidad está enviando una oleada potente de Superlikes. Este tipo de impulso es raro y te coloca en una posición fuerte.

Si estás en un Daily Run, esta podría ser la ventaja que necesitas para lograr una victoria Underdog o incluso Legendary.

¡Sigue empujando — Legend Mode está al alcance!

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject:** Going Viral! Seu momentum é incrível! 🌊

Oi {{name}},

Você acabou de alcançar Going Viral — um dos níveis de Strike mais altos no Popularoo.

Cadeia de Strikes:
Heating Up → On Fire → Trending → Going Viral 🌊

Sua comunidade está enviando uma onda poderosa de Superlikes. Esse tipo de momentum é raro e te coloca em uma posição forte.

Se você está em um Daily Run, essa pode ser a vantagem que você precisa para garantir uma vitória Underdog ou até Legendary.

Continue empurrando — Legend Mode está ao alcance!

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject:** Going Viral! Dein Momentum ist unglaublich! 🌊

Hey {{name}},

Du hast gerade Going Viral erreicht — eine der höchsten Strike-Stufen bei Popularoo.

Strike-Kette:
Heating Up → On Fire → Trending → Going Viral 🌊

Deine Community sendet eine kraftvolle Welle von Superlikes. Diese Art von Momentum ist selten und bringt dich in eine starke Position.

Wenn du in einem Daily Run bist, könnte dies der Vorteil sein, den du brauchst, um einen Underdog- oder sogar Legendary-Sieg zu landen.

Weiter so — Legend Mode ist in Reichweite!

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject:** Going Viral! Il tuo momentum è incredibile! 🌊

Ciao {{name}},

Hai appena raggiunto Going Viral — uno dei livelli di Strike più alti su Popularoo.

Catena di Strikes:
Heating Up → On Fire → Trending → Going Viral 🌊

La tua community sta inviando un'ondata potente di Superlikes. Questo tipo di momentum è raro e ti mette in una posizione forte.

Se sei in un Daily Run, questa potrebbe essere la spinta che ti serve per ottenere una vittoria Underdog o persino Legendary.

Continua a spingere — Legend Mode è a portata di mano!

— Il team Popularoo

---
---

## EMAIL 3b — Strike: Legend Mode
*Déclencheur : Immédiat quand l'Outsider atteint 5+ Strikes simultanés*

### 🇬🇧 EN
**Subject:** Legend Mode activated! You're on fire! 🔥

Hey {{name}},

Something incredible just happened — you hit Legend Mode, the highest Strike level in Popularoo.

Strike chain:
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

Your community triggered an extraordinary wave of Superlikes. This kind of momentum is extremely rare and signals that something big is happening around your profile.

If you're in a Daily Run, this could be the push that lands you a Legendary victory.

Keep the energy going!

— The Popularoo Team

---

### 🇫🇷 FR
**Subject:** Legend Mode activé ! Tu es en feu ! 🔥

Salut {{name}},

Quelque chose d'incroyable vient de se passer — tu as atteint Legend Mode, le plus haut niveau de Strike sur Popularoo.

Chaîne de Strikes :
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

Ta communauté a déclenché une vague extraordinaire de Superlikes. Ce type de dynamique est extrêmement rare et signale que quelque chose de grand se passe autour de ton profil.

Si tu es dans un Daily Run, c'est peut-être la poussée qui te mènera à une victoire Legendary.

Maintiens l'énergie !

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject:** ¡Legend Mode activado! ¡Estás en llamas! 🔥

¡Hola {{name}}!

Algo increíble acaba de pasar — acabas de alcanzar Legend Mode, el nivel de Strike más alto en Popularoo.

Cadena de Strikes:
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

Tu comunidad desató una oleada extraordinaria de Superlikes. Este tipo de impulso es extremadamente raro y señala que algo grande está pasando alrededor de tu perfil.

Si estás en un Daily Run, este podría ser el empujón que te lleve a una victoria Legendary.

¡Mantén la energía!

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject:** Legend Mode ativado! Você está pegando fogo! 🔥

Oi {{name}},

Algo incrível acabou de acontecer — você atingiu Legend Mode, o nível de Strike mais alto no Popularoo.

Cadeia de Strikes:
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

Sua comunidade disparou uma onda extraordinária de Superlikes. Esse tipo de momentum é extremamente raro e sinaliza que algo grande está acontecendo ao redor do seu perfil.

Se você está em um Daily Run, esse pode ser o impulso que te leva a uma vitória Legendary.

Mantenha a energia!

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject:** Legend Mode aktiviert! Du brennst! 🔥

Hey {{name}},

Etwas Unglaubliches ist gerade passiert — du hast Legend Mode erreicht, die höchste Strike-Stufe bei Popularoo.

Strike-Kette:
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

Deine Community hat eine außergewöhnliche Welle von Superlikes ausgelöst. Diese Art von Momentum ist extrem selten und zeigt, dass etwas Großes rund um dein Profil passiert.

Wenn du in einem Daily Run bist, könnte dies der Schub sein, der dich zu einem Legendary-Sieg führt.

Halte die Energie aufrecht!

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject:** Legend Mode attivato! Sei in fiamme! 🔥

Ciao {{name}},

Qualcosa di incredibile è appena successo — hai raggiunto Legend Mode, il livello di Strike più alto su Popularoo.

Catena di Strikes:
Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡

La tua community ha scatenato un'ondata straordinaria di Superlikes. Questo tipo di momentum è estremamente raro e segnala che qualcosa di grande sta accadendo intorno al tuo profilo.

Se sei in un Daily Run, questa potrebbe essere la spinta che ti porta a una vittoria Legendary.

Mantieni l'energia!

— Il team Popularoo

---
---

## EMAIL 4 — Booster Expiration
*Déclencheur : Super Booster → 3h avant expiration | Golden Booster → 24h avant | Booster basique → pas d'email*

### 🇬🇧 EN
**Subject:** Your {{tierName}} expires soon ⏰

Hey {{name}},

Heads up — your {{tierName}} expires in {{timeRemaining}}.

Your stats during this boost:
• Total votes received: {{totalVotes}}
• Highest ranking position: #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs completed: {{dailyRunsCount}}

Want to keep the momentum? Grab another Booster before your spot disappears.

[Renew my Booster →]

— The Popularoo Team

---

### 🇫🇷 FR
**Subject:** Ton {{tierName}} expire bientôt ⏰

Salut {{name}},

Attention — ton {{tierName}} expire dans {{timeRemaining}}.

Tes stats pendant ce boost :
• Votes reçus au total : {{totalVotes}}
• Meilleure position au classement : #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs complétés : {{dailyRunsCount}}

Tu veux garder la dynamique ? Prends un nouveau Booster avant que ta place disparaisse.

[Renouveler mon Booster →]

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject:** Tu {{tierName}} expira pronto ⏰

¡Hola {{name}}!

Atención — tu {{tierName}} expira en {{timeRemaining}}.

Tus stats durante este boost:
• Votos recibidos en total: {{totalVotes}}
• Mejor posición en el ranking: #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs completados: {{dailyRunsCount}}

¿Quieres mantener el impulso? Consigue otro Booster antes de que tu lugar desaparezca.

[Renovar mi Booster →]

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject:** Seu {{tierName}} expira em breve ⏰

Oi {{name}},

Atenção — seu {{tierName}} expira em {{timeRemaining}}.

Suas stats durante este boost:
• Votos recebidos no total: {{totalVotes}}
• Melhor posição no ranking: #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs completados: {{dailyRunsCount}}

Quer manter o momentum? Pegue outro Booster antes que sua vaga desapareça.

[Renovar meu Booster →]

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject:** Dein {{tierName}} läuft bald ab ⏰

Hey {{name}},

Achtung — dein {{tierName}} läuft in {{timeRemaining}} ab.

Deine Stats während dieses Boosts:
• Stimmen insgesamt erhalten: {{totalVotes}}
• Beste Ranking-Position: #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs abgeschlossen: {{dailyRunsCount}}

Willst du das Momentum halten? Hol dir einen neuen Booster, bevor dein Platz verschwindet.

[Meinen Booster erneuern →]

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject:** Il tuo {{tierName}} scade presto ⏰

Ciao {{name}},

Attenzione — il tuo {{tierName}} scade tra {{timeRemaining}}.

Le tue stats durante questo boost:
• Voti ricevuti in totale: {{totalVotes}}
• Miglior posizione in classifica: #{{bestRank}}
*[Si Daily Runs:]* • Daily Runs completati: {{dailyRunsCount}}

Vuoi mantenere il momentum? Prendi un altro Booster prima che il tuo posto scompaia.

[Rinnova il mio Booster →]

— Il team Popularoo

---
---

## EMAIL 5 — Welcome (First Purchase Only)
*Déclencheur : Premier achat de Booster uniquement*

### 🇬🇧 EN
**Subject:** Welcome to Popularoo — your stock market of fame ✨

Hey {{name}},

Welcome to Popularoo — the world's stock market of fame.

Your first Booster just went live, and you've officially stepped into the ring with the world's most famous people. From now on, every vote you receive shapes your Popularoo Index.

Quick tips to maximize your time as an Outsider:
• Share your profile with your community to rally votes
• Watch the leaderboard — your position can change at any moment
• Watch the Strikes — a wave of Superlikes can change everything

The clock is ticking. Make it count.

— The Popularoo Team

---

### 🇫🇷 FR
**Subject:** Bienvenue sur Popularoo — your stock market of fame ✨

Salut {{name}},

Bienvenue sur Popularoo — the world's stock market of fame.

Ton premier Booster vient d'être activé, et tu viens officiellement d'entrer dans l'arène avec les personnalités les plus célèbres du monde. Désormais, chaque vote que tu reçois façonne ton Popularoo Index.

Quelques conseils pour maximiser ton temps en tant qu'Outsider :
• Partage ton profil avec ta communauté pour rallier des votes
• Surveille le classement — ta position peut changer à tout moment
• Surveille les Strikes — une vague de Superlikes peut tout changer

Le compte à rebours est lancé. Fais-en bon usage.

— L'équipe Popularoo

---

### 🇪🇸 ES
**Subject:** Bienvenido a Popularoo — your stock market of fame ✨

¡Hola {{name}}!

Bienvenido a Popularoo — the world's stock market of fame.

Tu primer Booster acaba de activarse, y acabas de entrar oficialmente en la arena con las personas más famosas del mundo. A partir de ahora, cada voto que recibas moldea tu Popularoo Index.

Consejos rápidos para maximizar tu tiempo como Outsider:
• Comparte tu perfil con tu comunidad para conseguir votos
• Vigila el ranking — tu posición puede cambiar en cualquier momento
• Vigila los Strikes — una oleada de Superlikes puede cambiarlo todo

El reloj corre. Aprovéchalo.

— El equipo Popularoo

---

### 🇵🇹 PT
**Subject:** Bem-vindo ao Popularoo — your stock market of fame ✨

Oi {{name}},

Bem-vindo ao Popularoo — the world's stock market of fame.

Seu primeiro Booster acabou de ser ativado, e você oficialmente entrou na arena com as pessoas mais famosas do mundo. A partir de agora, cada voto que você recebe molda seu Popularoo Index.

Dicas rápidas para maximizar seu tempo como Outsider:
• Compartilhe seu perfil com sua comunidade para conseguir votos
• Fique de olho no ranking — sua posição pode mudar a qualquer momento
• Fique de olho nos Strikes — uma onda de Superlikes pode mudar tudo

O relógio está correndo. Faça valer a pena.

— Equipe Popularoo

---

### 🇩🇪 DE
**Subject:** Willkommen bei Popularoo — your stock market of fame ✨

Hey {{name}},

Willkommen bei Popularoo — the world's stock market of fame.

Dein erster Booster wurde gerade aktiviert, und du bist offiziell in die Arena mit den berühmtesten Menschen der Welt eingetreten. Ab jetzt formt jede Stimme, die du erhältst, deinen Popularoo Index.

Schnelle Tipps, um deine Zeit als Outsider zu maximieren:
• Teile dein Profil mit deiner Community, um Stimmen zu sammeln
• Beobachte die Rangliste — deine Position kann sich jederzeit ändern
• Beobachte die Strikes — eine Welle von Superlikes kann alles verändern

Die Uhr tickt. Nutze die Zeit.

— Das Popularoo Team

---

### 🇮🇹 IT
**Subject:** Benvenuto su Popularoo — your stock market of fame ✨

Ciao {{name}},

Benvenuto su Popularoo — the world's stock market of fame.

Il tuo primo Booster è appena stato attivato, e sei ufficialmente entrato nell'arena con le persone più famose del mondo. Da ora in poi, ogni voto che ricevi plasma il tuo Popularoo Index.

Consigli rapidi per massimizzare il tuo tempo come Outsider:
• Condividi il tuo profilo con la tua community per raccogliere voti
• Tieni d'occhio la classifica — la tua posizione può cambiare in qualsiasi momento
• Tieni d'occhio gli Strikes — un'ondata di Superlikes può cambiare tutto

Il tempo scorre. Fai che conti.

— Il team Popularoo

---
---

## ANNEXE — Localisation des Variables Temporelles

| Variable EN | FR | ES | PT | DE | IT |
|---|---|---|---|---|---|
| 1 hour | 1 heure | 1 hora | 1 hora | 1 Stunde | 1 ora |
| 3 hours | 3 heures | 3 horas | 3 horas | 3 Stunden | 3 ore |
| 24 hours | 24 heures | 24 horas | 24 horas | 24 Stunden | 24 ore |
| 1 day | 1 jour | 1 día | 1 dia | 1 Tag | 1 giorno |
| 7 days | 7 jours | 7 días | 7 dias | 7 Tage | 7 giorni |
| 1 week | 1 semaine | 1 semana | 1 semana | 1 Woche | 1 settimana |

> Les termes de marque (Booster, Super Booster, Golden Booster, Strike, Daily Run, Superlike, Outsider, etc.) ne sont **jamais** traduits.
