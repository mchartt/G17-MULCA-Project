# Registro delle decisioni

Ogni decisione importante, anche quelle delegate ("decidi tu"). Le più recenti in alto.

| Data | Fase | Decisione | Alternative scartate | Motivo | Chi ha deciso |
|---|---|---|---|---|---|
| 15/11/2026 | 0 | Immagini e video della landing con Higgsfield, clip Seedance concatenate per un effetto 3D allo scroll | animazione solo in codice (GSAP), nessun video | richiesta esplicita di Matteo; eccezione al budget di complessità (istruzioni §8) confermata da lui | Matteo |
| 15/11/2026 | 0 | La web app non va su un hosting: la serve l'adattatore web nel processo MULCA | Vercel, Netlify | istruzioni di progetto §0 e §6 (niente hosting a pagamento, un solo processo client) | istruzioni |
| 15/11/2026 | 1 | Nome del prodotto: Cadence, mostrato come "Cadence · Group Coordinator" | Tandem, Quorum, Keel, Group Coordinator | scelta di Matteo; omonimi esistenti accettabili per un prototipo non commerciale | Matteo |
| 15/11/2026 | 1 | Landing: hero film + 3 sezioni + crea o entra; sensazione calma, chiara, affidabile | solo hero; pagina completa | scelta di Matteo | Matteo |
| 15/11/2026 | 5 | Concept del film: Dalla nebbia alla luce del giorno, 5 clip da 5 s a 720p | La scrivania si mette in ordine; Fili che si sciolgono | scelta di Matteo; 720p perché è il limite della prova gratuita | Matteo |
| 15/11/2026 | 6 | Film: v1 stilizzata 3D scartata, v2 fotografica | v1 | richiesta di Matteo (meno 'AI slop') | Matteo |
| 15/11/2026 | 6 | Film di 4 clip: l'ultima clip (primissimo piano) tagliata | 5 clip | oltre i 2 s il sughero diventa un artefatto e spariscono i bollini | Claude, da confermare |
| 15/11/2026 | 6 | Raccordo geometrico alle giunture (`film/raccorda.py`) e rimozione dei fotogrammi ripetuti | rigenerare le clip | Higgsfield allunga del 2 % in verticale l'immagine di partenza; misurato e corretto senza dissolvenze | Claude |
| 15/11/2026 | 7 | Gruppi web come conversazioni proprie (`web:<codice>`); unione con Discord rinviata | stessa conversazione subito | A5/A6 non ancora verificate dal vivo | Claude, da confermare |
| 15/11/2026 | 7 | Esempio di scheda sulla landing: solo il tipo 'carta del progetto' | scheda di responsabile e data | è l'unico tipo che esiste oggi: niente promesse non mantenute | Claude |
| 15/11/2026 | 5 | Interfaccia v2 morbida e premium in stile Apple: SF Pro di sistema + Geist, Font Awesome, Lenis, titoli del film allo scroll, titolo che si accende parola per parola | v1 (Atkinson, schede a righe); Inter | richiesta di Matteo; Inter scartato perché è il font 'da AI' per eccellenza | Matteo |
| 15/11/2026 | 9 | Anteprima statica su Vercel (piano Hobby gratuito): solo sito e film, l'adattatore resta sul portatile della demo | nessuna pubblicazione; ospitare anche il backend | richiesta esplicita di Matteo; Vercel non tiene processi con WebSocket sempre accesi | Matteo |
| 16/11/2026 | 9 | Schermate di anteprima con dati di esempio sotto `/preview` (Connections, Plan around calendars, Catch up, Reflection), sempre etichettate "Preview · sample data"; sezione "Next" nella landing | cambiare i testi della landing come se il multicanale esistesse già; mockup solo su Figma | Thomas (mail e incontro 11/11) chiede la visione multicanale e i mockup di pianificazione e riflessione; la regola "niente promesse non mantenute" resta: ciò che non esiste è dichiarato anteprima | Gabriele, da confermare con Matteo |
| 16/11/2026 | 7 | Account veri (registrazione, login, profilo) e canali collegati: un canale Discord o Slack si collega a uno spazio web con `/coordinator link CODICE`; piano, decisioni e schede condivisi, chat separate ma visibili (mirror) e 'Catch up' reale | unione completa in una sola conversazione (tocca `runtime.py` del laboratorio e richiede di collegare gli account); account solo temporanei | richiesta di Gabriele: memoria condivisa e versione funzionante del cross-channel; sostituisce 'unione con Discord rinviata' del 15/11 | Gabriele, da confermare con Matteo |
