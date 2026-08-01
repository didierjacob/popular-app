"""
Popularoo Transactional Email Templates — 6 Languages
All brand terms (Booster, Super Booster, Golden Booster, Strike, Legend Mode, 
Going Viral, Daily Run, Superlike, Popularoo Index, Victory Tiers, 
Standard Win, Underdog Win, Legendary Strike) remain in English.

Sending rules:
- Email 1 (Booster Confirmation): All purchases except first
- Email 2 (Daily Run Victory): Immediate on Run victory
- Email 3a (Going Viral): Immediate when 4 simultaneous Strikes
- Email 3b (Legend Mode): Immediate when 5+ simultaneous Strikes
- Email 4 (Booster Expiration): Super Booster 3h before, Golden Booster 24h before. No email for basic Booster.
- Email 5 (Welcome): First purchase only
"""

# ──────────────────────────────────────────────────────────
# EMAIL 1 — Booster Purchase Confirmation
# ──────────────────────────────────────────────────────────
EMAIL_BOOSTER_CONFIRMATION = {
    "en": {
        "subject": "Your {{tierName}} is live! 🚀",
        "body": (
            "Hey {{name}},\n\n"
            "Your {{tierName}} just went live! You're now visible in the Outsiders ranking.\n\n"
            "What's active:\n"
            "• {{tierName}} — {{duration}}\n"
            "• Your profile is live and collecting votes right now\n\n"
            "{{goldenExtra}}"
            "Go check your position and share your profile to rally votes.\n\n"
            "— The Popularoo Team"
        ),
        "goldenExtra": "You also have priority placement on the Home page and access to Daily Runs. Make it count!\n\n",
    },
    "fr": {
        "subject": "Ton {{tierName}} est actif ! 🚀",
        "body": (
            "Salut {{name}},\n\n"
            "Ton {{tierName}} vient d'être activé ! Tu es maintenant visible dans le classement Outsiders.\n\n"
            "Ce qui est actif :\n"
            "• {{tierName}} — {{duration}}\n"
            "• Ton profil est en ligne et collecte des votes en ce moment\n\n"
            "{{goldenExtra}}"
            "Va vérifier ta position et partage ton profil pour rallier des votes.\n\n"
            "— L'équipe Popularoo"
        ),
        "goldenExtra": "Tu as aussi un placement prioritaire en page d'accueil et un accès aux Daily Runs. Fais-en bon usage !\n\n",
    },
    "es": {
        "subject": "¡Tu {{tierName}} está activo! 🚀",
        "body": (
            "¡Hola {{name}}!\n\n"
            "¡Tu {{tierName}} acaba de activarse! Ya eres visible en el ranking Outsiders.\n\n"
            "Lo que está activo:\n"
            "• {{tierName}} — {{duration}}\n"
            "• Tu perfil está en línea y recibiendo votos ahora mismo\n\n"
            "{{goldenExtra}}"
            "Ve a ver tu posición y comparte tu perfil para conseguir votos.\n\n"
            "— El equipo Popularoo"
        ),
        "goldenExtra": "También tienes ubicación prioritaria en la portada y acceso a Daily Runs. ¡Aprovéchalo!\n\n",
    },
    "pt": {
        "subject": "Seu {{tierName}} está ativo! 🚀",
        "body": (
            "Oi {{name}},\n\n"
            "Seu {{tierName}} acabou de ser ativado! Você já está visível no ranking Outsiders.\n\n"
            "O que está ativo:\n"
            "• {{tierName}} — {{duration}}\n"
            "• Seu perfil está no ar e recebendo votos agora mesmo\n\n"
            "{{goldenExtra}}"
            "Confira sua posição e compartilhe seu perfil para conseguir votos.\n\n"
            "— Equipe Popularoo"
        ),
        "goldenExtra": "Você também tem posição prioritária na Home e acesso aos Daily Runs. Aproveite!\n\n",
    },
    "de": {
        "subject": "Dein {{tierName}} ist aktiv! 🚀",
        "body": (
            "Hey {{name}},\n\n"
            "Dein {{tierName}} ist jetzt aktiv! Du bist ab sofort im Outsiders-Ranking sichtbar.\n\n"
            "Was aktiv ist:\n"
            "• {{tierName}} — {{duration}}\n"
            "• Dein Profil ist live und sammelt gerade Stimmen\n\n"
            "{{goldenExtra}}"
            "Schau dir deine Position an und teile dein Profil, um Stimmen zu sammeln.\n\n"
            "— Das Popularoo Team"
        ),
        "goldenExtra": "Du hast außerdem eine Prioritätsplatzierung auf der Startseite und Zugang zu Daily Runs. Nutze es!\n\n",
    },
    "it": {
        "subject": "Il tuo {{tierName}} è attivo! 🚀",
        "body": (
            "Ciao {{name}},\n\n"
            "Il tuo {{tierName}} è appena stato attivato! Ora sei visibile nella classifica Outsiders.\n\n"
            "Cosa è attivo:\n"
            "• {{tierName}} — {{duration}}\n"
            "• Il tuo profilo è online e sta raccogliendo voti in questo momento\n\n"
            "{{goldenExtra}}"
            "Vai a controllare la tua posizione e condividi il tuo profilo per raccogliere voti.\n\n"
            "— Il team Popularoo"
        ),
        "goldenExtra": "Hai anche un posizionamento prioritario in homepage e accesso ai Daily Runs. Sfruttalo!\n\n",
    },
}

# ──────────────────────────────────────────────────────────
# EMAIL 2 — Daily Run Victory (3 subject variants)
# ──────────────────────────────────────────────────────────
EMAIL_DAILY_RUN_VICTORY = {
    "en": {
        "subjects": {
            "standard": "You won your Daily Run! 🏆",
            "underdog": "Underdog victory! You crushed it! 💪",
            "legendary": "LEGENDARY! You just made Popularoo history! ⚡",
        },
        "body": (
            "Hey {{name}},\n\n"
            "{{victoryTier}}! You just beat {{targetName}} in a Daily Run.\n\n"
            "Your results:\n"
            "• Final Popularoo Index gap: {{gap}} points\n"
            "• Victory Tier: {{victoryTier}}\n"
            "• Votes received during the Run: {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Share your victory and keep the momentum going.\n\n"
            "— The Popularoo Team"
        ),
        "strikesLine": "• Strikes triggered: {{strikesCount}} (highest: {{highestStrike}})\n",
        "legendaryMsg": "This is the rarest kind of victory in Popularoo. Less than 1% of Runs end this way. Your community showed up in a massive way.\n\n",
        "underdogMsg": "Taking down a personality {{gap}} points above you is no small feat. Your supporters really came through.\n\n",
        "standardMsg": "\n",
    },
    "fr": {
        "subjects": {
            "standard": "Tu as gagné ton Daily Run ! 🏆",
            "underdog": "Victoire Underdog ! Tu as tout déchiré ! 💪",
            "legendary": "ÉPIQUE ! Tu viens d'écrire l'histoire de Popularoo ! ⚡",
        },
        "body": (
            "Salut {{name}},\n\n"
            "{{victoryTier}} ! Tu viens de battre {{targetName}} dans un Daily Run.\n\n"
            "Tes résultats :\n"
            "• Écart final de Popularoo Index : {{gap}} points\n"
            "• Victory Tier : {{victoryTier}}\n"
            "• Votes reçus pendant le Run : {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Partage ta victoire et maintiens la dynamique.\n\n"
            "— L'équipe Popularoo"
        ),
        "strikesLine": "• Strikes déclenchés : {{strikesCount}} (plus haut : {{highestStrike}})\n",
        "legendaryMsg": "C'est le type de victoire le plus rare sur Popularoo. Moins de 1% des Runs se terminent ainsi. Ta communauté s'est mobilisée de manière exceptionnelle.\n\n",
        "underdogMsg": "Battre une personnalité {{gap}} points au-dessus de toi n'est pas rien. Tes supporters ont vraiment assuré.\n\n",
        "standardMsg": "\n",
    },
    "es": {
        "subjects": {
            "standard": "¡Ganaste tu Daily Run! 🏆",
            "underdog": "¡Victoria Underdog! ¡Lo aplastaste! 💪",
            "legendary": "¡ÉPICO! ¡Acabas de hacer historia en Popularoo! ⚡",
        },
        "body": (
            "¡Hola {{name}}!\n\n"
            "¡{{victoryTier}}! Acabas de vencer a {{targetName}} en un Daily Run.\n\n"
            "Tus resultados:\n"
            "• Diferencia final de Popularoo Index: {{gap}} puntos\n"
            "• Victory Tier: {{victoryTier}}\n"
            "• Votos recibidos durante el Run: {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Comparte tu victoria y mantén el impulso.\n\n"
            "— El equipo Popularoo"
        ),
        "strikesLine": "• Strikes activados: {{strikesCount}} (máximo: {{highestStrike}})\n",
        "legendaryMsg": "Esta es la victoria más rara en Popularoo. Menos del 1% de los Runs terminan así. Tu comunidad se movilizó de forma masiva.\n\n",
        "underdogMsg": "Derribar a una personalidad {{gap}} puntos por encima de ti no es poca cosa. Tus seguidores realmente dieron la talla.\n\n",
        "standardMsg": "\n",
    },
    "pt": {
        "subjects": {
            "standard": "Você venceu seu Daily Run! 🏆",
            "underdog": "Vitória Underdog! Você arrasou! 💪",
            "legendary": "ÉPICO! Você acabou de fazer história no Popularoo! ⚡",
        },
        "body": (
            "Oi {{name}},\n\n"
            "{{victoryTier}}! Você acabou de vencer {{targetName}} em um Daily Run.\n\n"
            "Seus resultados:\n"
            "• Diferença final de Popularoo Index: {{gap}} pontos\n"
            "• Victory Tier: {{victoryTier}}\n"
            "• Votos recebidos durante o Run: {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Compartilhe sua vitória e mantenha o momentum.\n\n"
            "— Equipe Popularoo"
        ),
        "strikesLine": "• Strikes ativados: {{strikesCount}} (mais alto: {{highestStrike}})\n",
        "legendaryMsg": "Esta é a vitória mais rara no Popularoo. Menos de 1% dos Runs terminam assim. Sua comunidade se mobilizou de forma massiva.\n\n",
        "underdogMsg": "Derrubar uma personalidade {{gap}} pontos acima de você não é pouca coisa. Seus apoiadores realmente se superaram.\n\n",
        "standardMsg": "\n",
    },
    "de": {
        "subjects": {
            "standard": "Du hast deinen Daily Run gewonnen! 🏆",
            "underdog": "Underdog-Sieg! Du hast alles gegeben! 💪",
            "legendary": "EPISCH! Du hast Popularoo-Geschichte geschrieben! ⚡",
        },
        "body": (
            "Hey {{name}},\n\n"
            "{{victoryTier}}! Du hast gerade {{targetName}} in einem Daily Run besiegt.\n\n"
            "Deine Ergebnisse:\n"
            "• Finaler Popularoo Index Abstand: {{gap}} Punkte\n"
            "• Victory Tier: {{victoryTier}}\n"
            "• Stimmen während des Runs erhalten: {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Teile deinen Sieg und halte das Momentum aufrecht.\n\n"
            "— Das Popularoo Team"
        ),
        "strikesLine": "• Strikes ausgelöst: {{strikesCount}} (höchster: {{highestStrike}})\n",
        "legendaryMsg": "Das ist die seltenste Art von Sieg bei Popularoo. Weniger als 1% aller Runs enden so. Deine Community hat sich außergewöhnlich mobilisiert.\n\n",
        "underdogMsg": "Eine Persönlichkeit zu schlagen, die {{gap}} Punkte über dir liegt, ist keine Kleinigkeit. Deine Unterstützer haben wirklich geliefert.\n\n",
        "standardMsg": "\n",
    },
    "it": {
        "subjects": {
            "standard": "Hai vinto il tuo Daily Run! 🏆",
            "underdog": "Vittoria Underdog! Hai spaccato! 💪",
            "legendary": "EPICO! Hai appena fatto la storia di Popularoo! ⚡",
        },
        "body": (
            "Ciao {{name}},\n\n"
            "{{victoryTier}}! Hai appena battuto {{targetName}} in un Daily Run.\n\n"
            "I tuoi risultati:\n"
            "• Divario finale di Popularoo Index: {{gap}} punti\n"
            "• Victory Tier: {{victoryTier}}\n"
            "• Voti ricevuti durante il Run: {{votesReceived}}\n"
            "{{strikesLine}}\n"
            "{{tierMessage}}\n"
            "Condividi la tua vittoria e mantieni il momentum.\n\n"
            "— Il team Popularoo"
        ),
        "strikesLine": "• Strikes attivati: {{strikesCount}} (più alto: {{highestStrike}})\n",
        "legendaryMsg": "Questa è la vittoria più rara su Popularoo. Meno dell'1% dei Run finisce così. La tua community si è mobilitata in modo straordinario.\n\n",
        "underdogMsg": "Abbattere una personalità {{gap}} punti sopra di te non è uno scherzo. I tuoi sostenitori hanno davvero dato il massimo.\n\n",
        "standardMsg": "\n",
    },
}

# ──────────────────────────────────────────────────────────
# EMAIL 3a — Strike: Going Viral
# ──────────────────────────────────────────────────────────
EMAIL_STRIKE_GOING_VIRAL = {
    "en": {
        "subject": "Going Viral! Your momentum is incredible! 🌊",
        "body": (
            "Hey {{name}},\n\n"
            "You just reached Going Viral — one of the highest Strike levels in Popularoo.\n\n"
            "Strike chain:\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "Your community is sending a powerful wave of Superlikes. This kind of momentum is rare and puts you in a strong position.\n\n"
            "If you're in a Daily Run, this could be the edge you need to land an Underdog or even a Legendary victory.\n\n"
            "Keep pushing — Legend Mode is within reach!\n\n"
            "— The Popularoo Team"
        ),
    },
    "fr": {
        "subject": "Going Viral ! Ta dynamique est incroyable ! 🌊",
        "body": (
            "Salut {{name}},\n\n"
            "Tu viens d'atteindre Going Viral — l'un des plus hauts niveaux de Strike sur Popularoo.\n\n"
            "Chaîne de Strikes :\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "Ta communauté envoie une vague puissante de Superlikes. Ce type de dynamique est rare et te place en position de force.\n\n"
            "Si tu es dans un Daily Run, c'est peut-être l'avantage qu'il te faut pour décrocher une victoire Underdog voire Legendary.\n\n"
            "Continue à pousser — Legend Mode est à portée de main !\n\n"
            "— L'équipe Popularoo"
        ),
    },
    "es": {
        "subject": "¡Going Viral! ¡Tu impulso es increíble! 🌊",
        "body": (
            "¡Hola {{name}}!\n\n"
            "Acabas de alcanzar Going Viral — uno de los niveles de Strike más altos en Popularoo.\n\n"
            "Cadena de Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "Tu comunidad está enviando una oleada potente de Superlikes. Este tipo de impulso es raro y te coloca en una posición fuerte.\n\n"
            "Si estás en un Daily Run, esta podría ser la ventaja que necesitas para lograr una victoria Underdog o incluso Legendary.\n\n"
            "¡Sigue empujando — Legend Mode está al alcance!\n\n"
            "— El equipo Popularoo"
        ),
    },
    "pt": {
        "subject": "Going Viral! Seu momentum é incrível! 🌊",
        "body": (
            "Oi {{name}},\n\n"
            "Você acabou de alcançar Going Viral — um dos níveis de Strike mais altos no Popularoo.\n\n"
            "Cadeia de Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "Sua comunidade está enviando uma onda poderosa de Superlikes. Esse tipo de momentum é raro e te coloca em uma posição forte.\n\n"
            "Se você está em um Daily Run, essa pode ser a vantagem que você precisa para garantir uma vitória Underdog ou até Legendary.\n\n"
            "Continue empurrando — Legend Mode está ao alcance!\n\n"
            "— Equipe Popularoo"
        ),
    },
    "de": {
        "subject": "Going Viral! Dein Momentum ist unglaublich! 🌊",
        "body": (
            "Hey {{name}},\n\n"
            "Du hast gerade Going Viral erreicht — eine der höchsten Strike-Stufen bei Popularoo.\n\n"
            "Strike-Kette:\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "Deine Community sendet eine kraftvolle Welle von Superlikes. Diese Art von Momentum ist selten und bringt dich in eine starke Position.\n\n"
            "Wenn du in einem Daily Run bist, könnte dies der Vorteil sein, den du brauchst, um einen Underdog- oder sogar Legendary-Sieg zu landen.\n\n"
            "Weiter so — Legend Mode ist in Reichweite!\n\n"
            "— Das Popularoo Team"
        ),
    },
    "it": {
        "subject": "Going Viral! Il tuo momentum è incredibile! 🌊",
        "body": (
            "Ciao {{name}},\n\n"
            "Hai appena raggiunto Going Viral — uno dei livelli di Strike più alti su Popularoo.\n\n"
            "Catena di Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral 🌊\n\n"
            "La tua community sta inviando un'ondata potente di Superlikes. Questo tipo di momentum è raro e ti mette in una posizione forte.\n\n"
            "Se sei in un Daily Run, questa potrebbe essere la spinta che ti serve per ottenere una vittoria Underdog o persino Legendary.\n\n"
            "Continua a spingere — Legend Mode è a portata di mano!\n\n"
            "— Il team Popularoo"
        ),
    },
}

# ──────────────────────────────────────────────────────────
# EMAIL 3b — Strike: Legend Mode
# ──────────────────────────────────────────────────────────
EMAIL_STRIKE_LEGEND_MODE = {
    "en": {
        "subject": "Legend Mode activated! You're on fire! 🔥",
        "body": (
            "Hey {{name}},\n\n"
            "Something incredible just happened — you hit Legend Mode, the highest Strike level in Popularoo.\n\n"
            "Strike chain:\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "Your community triggered an extraordinary wave of Superlikes. This kind of momentum is extremely rare and signals that something big is happening around your profile.\n\n"
            "If you're in a Daily Run, this could be the push that lands you a Legendary victory.\n\n"
            "Keep the energy going!\n\n"
            "— The Popularoo Team"
        ),
    },
    "fr": {
        "subject": "Legend Mode activé ! Tu es en feu ! 🔥",
        "body": (
            "Salut {{name}},\n\n"
            "Quelque chose d'incroyable vient de se passer — tu as atteint Legend Mode, le plus haut niveau de Strike sur Popularoo.\n\n"
            "Chaîne de Strikes :\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "Ta communauté a déclenché une vague extraordinaire de Superlikes. Ce type de dynamique est extrêmement rare et signale que quelque chose de grand se passe autour de ton profil.\n\n"
            "Si tu es dans un Daily Run, c'est peut-être la poussée qui te mènera à une victoire Legendary.\n\n"
            "Maintiens l'énergie !\n\n"
            "— L'équipe Popularoo"
        ),
    },
    "es": {
        "subject": "¡Legend Mode activado! ¡Estás en llamas! 🔥",
        "body": (
            "¡Hola {{name}}!\n\n"
            "Algo increíble acaba de pasar — acabas de alcanzar Legend Mode, el nivel de Strike más alto en Popularoo.\n\n"
            "Cadena de Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "Tu comunidad desató una oleada extraordinaria de Superlikes. Este tipo de impulso es extremadamente raro y señala que algo grande está pasando alrededor de tu perfil.\n\n"
            "Si estás en un Daily Run, este podría ser el empujón que te lleve a una victoria Legendary.\n\n"
            "¡Mantén la energía!\n\n"
            "— El equipo Popularoo"
        ),
    },
    "pt": {
        "subject": "Legend Mode ativado! Você está pegando fogo! 🔥",
        "body": (
            "Oi {{name}},\n\n"
            "Algo incrível acabou de acontecer — você atingiu Legend Mode, o nível de Strike mais alto no Popularoo.\n\n"
            "Cadeia de Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "Sua comunidade disparou uma onda extraordinária de Superlikes. Esse tipo de momentum é extremamente raro e sinaliza que algo grande está acontecendo ao redor do seu perfil.\n\n"
            "Se você está em um Daily Run, esse pode ser o impulso que te leva a uma vitória Legendary.\n\n"
            "Mantenha a energia!\n\n"
            "— Equipe Popularoo"
        ),
    },
    "de": {
        "subject": "Legend Mode aktiviert! Du brennst! 🔥",
        "body": (
            "Hey {{name}},\n\n"
            "Etwas Unglaubliches ist gerade passiert — du hast Legend Mode erreicht, die höchste Strike-Stufe bei Popularoo.\n\n"
            "Strike-Kette:\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "Deine Community hat eine außergewöhnliche Welle von Superlikes ausgelöst. Diese Art von Momentum ist extrem selten und zeigt, dass etwas Großes rund um dein Profil passiert.\n\n"
            "Wenn du in einem Daily Run bist, könnte dies der Schub sein, der dich zu einem Legendary-Sieg führt.\n\n"
            "Halte die Energie aufrecht!\n\n"
            "— Das Popularoo Team"
        ),
    },
    "it": {
        "subject": "Legend Mode attivato! Sei in fiamme! 🔥",
        "body": (
            "Ciao {{name}},\n\n"
            "Qualcosa di incredibile è appena successo — hai raggiunto Legend Mode, il livello di Strike più alto su Popularoo.\n\n"
            "Catena di Strikes:\n"
            "Heating Up → On Fire → Trending → Going Viral → Legend Mode ⚡\n\n"
            "La tua community ha scatenato un'ondata straordinaria di Superlikes. Questo tipo di momentum è estremamente raro e segnala che qualcosa di grande sta accadendo intorno al tuo profilo.\n\n"
            "Se sei in un Daily Run, questa potrebbe essere la spinta che ti porta a una vittoria Legendary.\n\n"
            "Mantieni l'energia!\n\n"
            "— Il team Popularoo"
        ),
    },
}

# ──────────────────────────────────────────────────────────
# EMAIL 4 — Booster Expiration
# Timing: Super Booster → 3h before | Golden Booster → 24h before | Basic → no email
# ──────────────────────────────────────────────────────────
EMAIL_BOOSTER_EXPIRATION = {
    "en": {
        "subject": "Your {{tierName}} expires soon ⏰",
        "body": (
            "Hey {{name}},\n\n"
            "Heads up — your {{tierName}} expires in {{timeRemaining}}.\n\n"
            "Your stats during this boost:\n"
            "• Total votes received: {{totalVotes}}\n"
            "• Highest ranking position: #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\nWant to keep the momentum? Grab another Booster before your spot disappears.\n\n"
            "[Renew my Booster →]\n\n"
            "— The Popularoo Team"
        ),
        "dailyRunsLine": "• Daily Runs completed: {{dailyRunsCount}}\n",
    },
    "fr": {
        "subject": "Ton {{tierName}} expire bientôt ⏰",
        "body": (
            "Salut {{name}},\n\n"
            "Attention — ton {{tierName}} expire dans {{timeRemaining}}.\n\n"
            "Tes stats pendant ce boost :\n"
            "• Votes reçus au total : {{totalVotes}}\n"
            "• Meilleure position au classement : #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\nTu veux garder la dynamique ? Prends un nouveau Booster avant que ta place disparaisse.\n\n"
            "[Renouveler mon Booster →]\n\n"
            "— L'équipe Popularoo"
        ),
        "dailyRunsLine": "• Daily Runs complétés : {{dailyRunsCount}}\n",
    },
    "es": {
        "subject": "Tu {{tierName}} expira pronto ⏰",
        "body": (
            "¡Hola {{name}}!\n\n"
            "Atención — tu {{tierName}} expira en {{timeRemaining}}.\n\n"
            "Tus stats durante este boost:\n"
            "• Votos recibidos en total: {{totalVotes}}\n"
            "• Mejor posición en el ranking: #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\n¿Quieres mantener el impulso? Consigue otro Booster antes de que tu lugar desaparezca.\n\n"
            "[Renovar mi Booster →]\n\n"
            "— El equipo Popularoo"
        ),
        "dailyRunsLine": "• Daily Runs completados: {{dailyRunsCount}}\n",
    },
    "pt": {
        "subject": "Seu {{tierName}} expira em breve ⏰",
        "body": (
            "Oi {{name}},\n\n"
            "Atenção — seu {{tierName}} expira em {{timeRemaining}}.\n\n"
            "Suas stats durante este boost:\n"
            "• Votos recebidos no total: {{totalVotes}}\n"
            "• Melhor posição no ranking: #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\nQuer manter o momentum? Pegue outro Booster antes que sua vaga desapareça.\n\n"
            "[Renovar meu Booster →]\n\n"
            "— Equipe Popularoo"
        ),
        "dailyRunsLine": "• Daily Runs completados: {{dailyRunsCount}}\n",
    },
    "de": {
        "subject": "Dein {{tierName}} läuft bald ab ⏰",
        "body": (
            "Hey {{name}},\n\n"
            "Achtung — dein {{tierName}} läuft in {{timeRemaining}} ab.\n\n"
            "Deine Stats während dieses Boosts:\n"
            "• Stimmen insgesamt erhalten: {{totalVotes}}\n"
            "• Beste Ranking-Position: #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\nWillst du das Momentum halten? Hol dir einen neuen Booster, bevor dein Platz verschwindet.\n\n"
            "[Meinen Booster erneuern →]\n\n"
            "— Das Popularoo Team"
        ),
        "dailyRunsLine": "• Daily Runs abgeschlossen: {{dailyRunsCount}}\n",
    },
    "it": {
        "subject": "Il tuo {{tierName}} scade presto ⏰",
        "body": (
            "Ciao {{name}},\n\n"
            "Attenzione — il tuo {{tierName}} scade tra {{timeRemaining}}.\n\n"
            "Le tue stats durante questo boost:\n"
            "• Voti ricevuti in totale: {{totalVotes}}\n"
            "• Miglior posizione in classifica: #{{bestRank}}\n"
            "{{dailyRunsLine}}"
            "\nVuoi mantenere il momentum? Prendi un altro Booster prima che il tuo posto scompaia.\n\n"
            "[Rinnova il mio Booster →]\n\n"
            "— Il team Popularoo"
        ),
        "dailyRunsLine": "• Daily Runs completati: {{dailyRunsCount}}\n",
    },
}

# ──────────────────────────────────────────────────────────
# EMAIL 5 — Welcome (first purchase only)
# ──────────────────────────────────────────────────────────
EMAIL_WELCOME = {
    "en": {
        "subject": "Welcome to Popularoo — your stock market of fame ✨",
        "body": (
            "Hey {{name}},\n\n"
            "Welcome to Popularoo — the world's stock market of fame.\n\n"
            "Your first Booster just went live, and you've officially stepped into the ring with the world's most famous people. "
            "From now on, every vote you receive shapes your Popularoo Index.\n\n"
            "Quick tips to maximize your time as an Outsider:\n"
            "• Share your profile with your community to rally votes\n"
            "• Watch the leaderboard — your position can change at any moment\n"
            "• Watch the Strikes — a wave of Superlikes can change everything\n\n"
            "The clock is ticking. Make it count.\n\n"
            "— The Popularoo Team"
        ),
    },
    "fr": {
        "subject": "Bienvenue sur Popularoo — your stock market of fame ✨",
        "body": (
            "Salut {{name}},\n\n"
            "Bienvenue sur Popularoo — the world's stock market of fame.\n\n"
            "Ton premier Booster vient d'être activé, et tu viens officiellement d'entrer dans l'arène avec les personnalités les plus célèbres du monde. "
            "Désormais, chaque vote que tu reçois façonne ton Popularoo Index.\n\n"
            "Quelques conseils pour maximiser ton temps en tant qu'Outsider :\n"
            "• Partage ton profil avec ta communauté pour rallier des votes\n"
            "• Surveille le classement — ta position peut changer à tout moment\n"
            "• Surveille les Strikes — une vague de Superlikes peut tout changer\n\n"
            "Le compte à rebours est lancé. Fais-en bon usage.\n\n"
            "— L'équipe Popularoo"
        ),
    },
    "es": {
        "subject": "Bienvenido a Popularoo — your stock market of fame ✨",
        "body": (
            "¡Hola {{name}}!\n\n"
            "Bienvenido a Popularoo — the world's stock market of fame.\n\n"
            "Tu primer Booster acaba de activarse, y acabas de entrar oficialmente en la arena con las personas más famosas del mundo. "
            "A partir de ahora, cada voto que recibas moldea tu Popularoo Index.\n\n"
            "Consejos rápidos para maximizar tu tiempo como Outsider:\n"
            "• Comparte tu perfil con tu comunidad para conseguir votos\n"
            "• Vigila el ranking — tu posición puede cambiar en cualquier momento\n"
            "• Vigila los Strikes — una oleada de Superlikes puede cambiarlo todo\n\n"
            "El reloj corre. Aprovéchalo.\n\n"
            "— El equipo Popularoo"
        ),
    },
    "pt": {
        "subject": "Bem-vindo ao Popularoo — your stock market of fame ✨",
        "body": (
            "Oi {{name}},\n\n"
            "Bem-vindo ao Popularoo — the world's stock market of fame.\n\n"
            "Seu primeiro Booster acabou de ser ativado, e você oficialmente entrou na arena com as pessoas mais famosas do mundo. "
            "A partir de agora, cada voto que você recebe molda seu Popularoo Index.\n\n"
            "Dicas rápidas para maximizar seu tempo como Outsider:\n"
            "• Compartilhe seu perfil com sua comunidade para conseguir votos\n"
            "• Fique de olho no ranking — sua posição pode mudar a qualquer momento\n"
            "• Fique de olho nos Strikes — uma onda de Superlikes pode mudar tudo\n\n"
            "O relógio está correndo. Faça valer a pena.\n\n"
            "— Equipe Popularoo"
        ),
    },
    "de": {
        "subject": "Willkommen bei Popularoo — your stock market of fame ✨",
        "body": (
            "Hey {{name}},\n\n"
            "Willkommen bei Popularoo — the world's stock market of fame.\n\n"
            "Dein erster Booster wurde gerade aktiviert, und du bist offiziell in die Arena mit den berühmtesten Menschen der Welt eingetreten. "
            "Ab jetzt formt jede Stimme, die du erhältst, deinen Popularoo Index.\n\n"
            "Schnelle Tipps, um deine Zeit als Outsider zu maximieren:\n"
            "• Teile dein Profil mit deiner Community, um Stimmen zu sammeln\n"
            "• Beobachte die Rangliste — deine Position kann sich jederzeit ändern\n"
            "• Beobachte die Strikes — eine Welle von Superlikes kann alles verändern\n\n"
            "Die Uhr tickt. Nutze die Zeit.\n\n"
            "— Das Popularoo Team"
        ),
    },
    "it": {
        "subject": "Benvenuto su Popularoo — your stock market of fame ✨",
        "body": (
            "Ciao {{name}},\n\n"
            "Benvenuto su Popularoo — the world's stock market of fame.\n\n"
            "Il tuo primo Booster è appena stato attivato, e sei ufficialmente entrato nell'arena con le persone più famose del mondo. "
            "Da ora in poi, ogni voto che ricevi plasma il tuo Popularoo Index.\n\n"
            "Consigli rapidi per massimizzare il tuo tempo come Outsider:\n"
            "• Condividi il tuo profilo con la tua community per raccogliere voti\n"
            "• Tieni d'occhio la classifica — la tua posizione può cambiare in qualsiasi momento\n"
            "• Tieni d'occhio gli Strikes — un'ondata di Superlikes può cambiare tutto\n\n"
            "Il tempo scorre. Fai che conti.\n\n"
            "— Il team Popularoo"
        ),
    },
}


# ──────────────────────────────────────────────────────────
# HELPER: Get email template with language fallback
# ──────────────────────────────────────────────────────────
SOCIAL_ACCOUNTS_FEATURE_ENABLED = False  # Reserved for Chantier 1I — not used in V1 emails

def get_template(template_dict: dict, lang: str = "en") -> dict:
    """Get email template for given language, fallback to English."""
    return template_dict.get(lang, template_dict["en"])


def render_email(template: dict, variables: dict) -> tuple:
    """Render email subject and body with given variables. Returns (subject, body)."""
    subject = template["subject"]
    body = template["body"]

    for key, val in variables.items():
        subject = subject.replace("{{" + key + "}}", str(val))
        body = body.replace("{{" + key + "}}", str(val))

    return subject, body


# ──────────────────────────────────────────────────────────
# EMAIL 6 — Diplôme Popularoo (confirmation d'achat de Boost)
#
# Remplace, sur le parcours d'achat, l'ancien texte brut « Welcome to Popularoo —
# the world's stock market of fame » (EMAIL_WELCOME) et ses défauts : mention d'un
# « premier Booster » qui ne valait qu'au tout premier achat, et « les personnalités
# les plus célèbres du monde » qui sur-promettait.
#
# CONTRAINTES E-MAIL respectées : styles 100 % EN LIGNE (aucun bloc <style>, que
# beaucoup de clients suppriment), mise en page par tableaux, pile de polices
# web-safe avec repli Arial/Helvetica. border-radius est ignoré par Outlook — le
# certificat s'y affichera à angles droits, sans casse.
#
# Les noms de paliers (Booster / Super Booster / Golden Booster) restent en anglais
# dans les 6 langues : ce sont des noms de marque.
# ──────────────────────────────────────────────────────────

DIPLOMA_TIER_BADGES = {
    "booster": "⚡ Booster",              # ⚡
    "super_booster": "\U0001F680 Super Booster",   # 🚀
    "golden_booster": "\U0001F451 Golden Booster",  # 👑
}

# Mois par langue, pour formater la date sans dépendance externe (pas de babel).
DIPLOMA_MONTHS = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro"],
}


def format_diploma_date(dt, lang: str = "en") -> str:
    """Date d'achat formatée selon les usages de chaque langue.

    fr « 1ᵉʳ août 2026 » (ordinal au 1er seulement) · en « August 1, 2026 »
    de « 1. August 2026 » · es « 1 de agosto de 2026 »
    it « 1º agosto 2026 » (ordinal au 1er seulement) · pt « 1 de agosto de 2026 »
    """
    months = DIPLOMA_MONTHS.get(lang, DIPLOMA_MONTHS["en"])
    d, m, y = dt.day, months[dt.month - 1], dt.year
    if lang == "fr":
        return f"{'1ᵉʳ' if d == 1 else d} {m} {y}"
    if lang == "it":
        return f"{'1º' if d == 1 else d} {m} {y}"
    if lang == "de":
        return f"{d}. {m} {y}"
    if lang == "es":
        return f"{d} de {m} de {y}"
    if lang == "pt":
        return f"{d} de {m} de {y}"
    return f"{m} {d}, {y}"


# `tips` contient volontairement du HTML (<b>) : le gras porte sur des segments
# différents selon la langue, impossible à déduire côté rendu.
EMAIL_DIPLOMA = {
    "fr": {
        "subject": "\U0001F3C6 Ton diplôme d'Outsider Popularoo",
        "label": "Outsider officiel",
        "declaration": "est officiellement un Outsider de Popularoo.",
        "datePrefix": "Depuis le {{date}}",
        "punch": "Ta cote est lancée. À toi de la faire grimper.",
        "tips": "<b>Partage</b> ton profil pour rallier des votes &middot; "
                "<b>Surveille le classement</b> : ta position peut bouger à tout moment.",
        "signature": "— L'équipe Popularoo",
    },
    "en": {
        "subject": "\U0001F3C6 Your Popularoo Outsider certificate",
        "label": "Official Outsider",
        "declaration": "is officially a Popularoo Outsider.",
        "datePrefix": "Since {{date}}",
        "punch": "Your score is live. Now make it climb.",
        "tips": "<b>Share</b> your profile to rally votes &middot; "
                "<b>Watch the leaderboard</b>: your position can change any moment.",
        "signature": "— The Popularoo Team",
    },
    "de": {
        "subject": "\U0001F3C6 Dein Popularoo-Outsider-Diplom",
        "label": "Offizieller Outsider",
        "declaration": "ist offiziell ein Popularoo-Outsider.",
        "datePrefix": "Seit dem {{date}}",
        "punch": "Dein Kurs läuft. Jetzt bring ihn nach oben.",
        "tips": "<b>Teile</b> dein Profil, um Stimmen zu sammeln &middot; "
                "<b>Behalte das Ranking im Auge</b>: deine Position kann sich jederzeit ändern.",
        "signature": "— Das Popularoo-Team",
    },
    "es": {
        "subject": "\U0001F3C6 Tu diploma de Outsider Popularoo",
        "label": "Outsider oficial",
        "declaration": "es oficialmente un Outsider de Popularoo.",
        "datePrefix": "Desde el {{date}}",
        "punch": "Tu cotización está en marcha. Ahora hazla subir.",
        "tips": "<b>Comparte</b> tu perfil para reunir votos &middot; "
                "<b>Vigila la clasificación</b>: tu posición puede cambiar en cualquier momento.",
        "signature": "— El equipo Popularoo",
    },
    "it": {
        "subject": "\U0001F3C6 Il tuo diploma di Outsider Popularoo",
        "label": "Outsider ufficiale",
        "declaration": "è ufficialmente un Outsider di Popularoo.",
        "datePrefix": "Dal {{date}}",
        "punch": "La tua quotazione è lanciata. Ora falla salire.",
        "tips": "<b>Condividi</b> il tuo profilo per raccogliere voti &middot; "
                "<b>Tieni d'occhio la classifica</b>: la tua posizione può cambiare da un momento all'altro.",
        "signature": "— Il team Popularoo",
    },
    "pt": {
        "subject": "\U0001F3C6 Seu diploma de Outsider Popularoo",
        "label": "Outsider oficial",
        "declaration": "é oficialmente um Outsider do Popularoo.",
        "datePrefix": "Desde {{date}}",
        "punch": "Sua cotação está no ar. Agora faça-a subir.",
        "tips": "<b>Compartilhe</b> seu perfil para juntar votos &middot; "
                "<b>Fique de olho no ranking</b>: sua posição pode mudar a qualquer momento.",
        "signature": "— A equipe Popularoo",
    },
}

_DIPLOMA_FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
                 "Helvetica,Arial,sans-serif")


def render_diploma_html(lang: str, name: str, tier_id: str, purchased_at) -> tuple:
    """Construit (sujet, html) du diplôme. Styles entièrement en ligne.

    `name` est échappé : il vient d'une saisie utilisateur et ne doit jamais
    pouvoir injecter de balise dans l'e-mail.
    """
    import html as _html

    tpl = get_template(EMAIL_DIPLOMA, lang)
    safe_name = _html.escape(name or "Outsider")
    badge = DIPLOMA_TIER_BADGES.get(tier_id, DIPLOMA_TIER_BADGES["booster"])
    date_line = tpl["datePrefix"].replace("{{date}}", format_diploma_date(purchased_at, lang))
    year = purchased_at.year
    f = _DIPLOMA_FONT

    body = f"""<body style="margin:0;padding:0;background:#0B2A1E;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0B2A1E;">
<tr><td align="center" style="padding:32px 16px;">

  <!-- Certificat -->
  <table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;width:100%;background:#0F2F22;border:2px solid #FFD700;border-radius:20px;">
    <tr><td align="center" style="padding:40px 36px 32px;font-family:{f};">
      <div style="font-size:64px;line-height:1;margin-bottom:10px;">&#127942;</div>
      <div style="font-size:34px;font-weight:800;color:#FFD700;letter-spacing:0.5px;margin:0 0 6px;">Popularoo</div>
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:16px auto 20px;"><tr>
        <td style="width:60px;height:3px;background:#FFD700;border-radius:2px;line-height:3px;font-size:0;">&nbsp;</td>
      </tr></table>
      <div style="font-size:12px;font-weight:700;letter-spacing:3px;color:#2ECC71;text-transform:uppercase;margin-bottom:18px;">{tpl['label']}</div>
      <div style="font-size:30px;font-weight:800;color:#FFFFFF;margin:0 0 10px;">{safe_name}</div>
      <div style="font-size:16px;color:#C9D8D2;line-height:1.6;margin:0 auto 24px;max-width:380px;">{tpl['declaration']}</div>
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;"><tr>
        <td style="background:#1A3A2A;border:1px solid #FFD700;border-radius:999px;padding:9px 20px;color:#FFD700;font-weight:700;font-size:15px;font-family:{f};white-space:nowrap;">{badge}</td>
      </tr></table>
      <div style="color:#8FB3A2;font-size:13px;margin-top:12px;letter-spacing:0.5px;">{date_line}</div>
    </td></tr>
  </table>

  <!-- Accroche + astuces -->
  <table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;width:100%;">
    <tr><td align="center" style="padding:26px 16px 0;font-family:{f};">
      <div style="color:#EAEAEA;font-size:16px;font-weight:600;margin:0 0 18px;">{tpl['punch']}</div>
      <div style="color:#A8C3B7;font-size:14px;line-height:1.7;margin:0 auto;max-width:420px;">{tpl['tips']}</div>
    </td></tr>
  </table>

  <!-- Signature + mentions -->
  <table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;width:100%;">
    <tr><td align="center" style="padding:20px 16px 0;border-top:1px solid #1F4A36;font-family:{f};">
      <div style="color:#C9D8D2;font-size:14px;font-weight:600;margin:4px 0;">{tpl['signature']}</div>
      <div style="color:#6B8B7B;font-size:12px;margin:4px 0;">&copy; {year} Popularoo</div>
    </td></tr>
  </table>

</td></tr>
</table>
</body>"""
    return tpl["subject"], body
