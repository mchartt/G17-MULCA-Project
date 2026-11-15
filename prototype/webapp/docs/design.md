# Design: Cadence · Group Coordinator (web app)

## Concept scelto
**Dalla nebbia alla luce del giorno** (scelto da Matteo il 15/11, tra tre concept: "Dalla nebbia
alla luce del giorno", "La scrivania si mette in ordine", "Fili che si sciolgono").

Passeggiata: in cima, un crepuscolo nebbioso blu-grigio con fumetti di chat in vetro smerigliato
e post-it di carta sospesi a caso. Scorrendo la camera avanza sempre verso una luce calda al
centro: i pezzi rallentano, si girano, si mettono in file lungo linee di luce, la nebbia si alza,
si posano su una bacheca chiara che si ordina in tre colonne come la console vera, con una scheda
di decisione evidenziata in salvia. Il film si scioglie nella sezione "il problema".
Il buio è il caos: sparisce mentre il piano prende forma (risolve il contrasto tra "spazio scuro"
e "calmo, chiaro").

Film: 6 keyframe, 5 clip da 5 s (25 s), 720p, Seedance 2.0 su Higgsfield, audio spento.
Storyboard versionato: `film/storyboard.json` (controllo della direzione: PASSA).

## Critica indipendente (sintesi)
Passaggio separato da direttore creativo scettico (nessun sub-agent, non richiesto): rischio di
testo finto sulle schede, quindi schede vuote con segnaposto grigi; idea accolta: l'ultimo
keyframe composto come la console a tre colonne, così il film atterra sul prodotto.
## Direzione artistica
- Palette provvisoria del film (contrasti UI da verificare nella fase di design): ardesia #3A4552,
  grigio freddo #6B7785, bianco caldo #F5F4EF, inchiostro #16181C, accento salvia #3E7C6B, punti dei
  membri terracotta, salvia, blu ardesia, ocra
- Tipografia (font titoli + font testo, fonte e licenza)
- Forme, spaziature, fotografia/illustrazione, movimento
## Design tokens
File: `sito/src/styles/tokens.css` (+ `design-tokens.json` per la ricetta)
## Wireframe e mockup (link Figma/Canva o file)
## Componenti previsti
## Approvazioni
| Cosa | Data | Note |
|---|---|---|

## Piano visivo dell'interfaccia (15/11, skill frontend-design)
- Mondo: bacheca di sughero, schede di carta, puntine, nastro, bollini colorati (dal film).
- Prima bozza scartata in revisione: bianco caldo + terracotta (è la combinazione più comune delle pagine generate).
- Palette: carta #ffffff, inchiostro #1c2430 (15.6:1), testo secondario #545e6c (6.4:1), righe blu #a9bcd6 e margine rosso #c8464b solo decorativi, salvia #2f6b5c per le azioni (6.3:1 con il bianco), bollini dei membri salvia, ardesia, ocra, corallo.
- Carattere: Atkinson Hyperlegible Next (pensato per la leggibilità), installato in locale: la demo funziona senza rete.
- Una sola cosa audace: il film allo scroll. Le frasi del film stanno su schede a righe (leggibili su fotogrammi scuri e chiari).
- Messaggi dell'agente: etichetta "Cadence" + tag "Coordinator", sfondo diverso e bordo: mai solo il colore.
- Screenshot: `docs/screens/`.
