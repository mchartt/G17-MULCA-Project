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
