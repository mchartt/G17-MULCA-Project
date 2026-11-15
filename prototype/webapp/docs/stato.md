# Stato del progetto: Ctrl+Alt+Design (web app del Group Coordinator)

- **Modalità**: guidata
- **Dove si lavora**: computer di Matteo (cartella `WebstormProjects/group-coordinator/mulca/prototype/webapp`), con una copia di lavoro nello spazio cloud di Claude
- **Repository GitHub**: https://github.com/mchartt/G17-MULCA-Project (privato), branch `group17/coordinator`. GitLab del laboratorio non si tocca.
- **Partito da una ricetta?**: no

## Mappa delle fasi
- [x] 0. Setup strumenti (`setup-iniziale`), 15/11
- [x] 1. Idea chiarita (`intervista-idea`), 15/11, modalità breve
- [x] 2. Obiettivi: presi dalla specifica v3 (N1-N4, G1-G6), non rifatti
- [x] 3. Tipologia: web app con landing (istruzioni §6 e §12)
- [x] 4. Architettura: React + TS + Vite servita dall'adattatore `mulca_discord/web/` (istruzioni §6)
- [x] 5. Design: concept del film, token in `src/styles/tokens.css`, piano in `design.md`
- [x] 6. Asset: film di 436 fotogrammi (Higgsfield, gratis), `film/lavori.json`
- [x] 7. Costruzione: landing + console + adattatore web, 15/11
- [~] 8. Verifica: test automatici e controllo visivo fatti; axe-core e prova dal vivo con Azure da fare
- [~] 9. Messa online: anteprima statica su Vercel preparata (`scripts/deploy-vercel.sh`), non ancora pubblicata: serve il token in `.env.vercel` o il login dal terminale di Matteo
- [ ] 10. Ricetta salvata e manuale consegnato (`libreria-ricette`)

## Fase corrente
8 Verifica: manca solo la prova dal vivo (Azure + due browser) e il controllo axe-core.

## Prossima azione
Pubblicare l'anteprima su Vercel (README, sezione Online preview); poi prova dal vivo con Azure.

## Vincoli già decisi fuori da questo percorso (non si richiedono)
- Stack: React + TypeScript + Vite, servita dall'adattatore web nel processo MULCA (istruzioni di progetto, sezione 6).
- Stile cinematico solo sulle pagine di ingresso (benvenuto, crea o entra nello spazio, informativa sui dati); la console a tre colonne resta pulita sullo stile di humanlayer.dev (decisione del 15/11).
- Interfaccia in inglese; accessibilità WCAG 2.1 AA; `prefers-reduced-motion` (istruzioni, sezione 12).
- Scadenza della web app funzionante: 23/11/2026 (M2); demo 2/12/2026.
- Riferimenti di stile indicati da Matteo: fruitful.com, tradetash.com, contralabs.com/creative-intelligence-report-2026, getlayers.ai (prompt).
- Landing: immagini e video concatenati generati con Higgsfield (Seedance per le clip con fotogramma iniziale e finale), per simulare un'animazione 3D allo scroll (richiesta di Matteo del 15/11). Modelli di prompt: `docs/riferimenti/getlayers-*-prompt.md`, da riadattare.

## Domande aperte
- Mobbin: il connettore chiede un piano a pagamento; le schermate salvate non sono leggibili.
- Higgsfield: crediti 0; la prova gratuita copre Seedance 2.0 720p fino a 15 s e i modelli d'immagine a 1k/2k, solo fino al 16/11 09:49 UTC.

## Da ricontrollare più avanti (assunzioni approvate)
- nessuna

## Termini già spiegati
transazione, copertura dei test, branch, commit, push, remoto, bundle, interruttore (feature flag), ambiente virtuale, keyframe, concatenazione delle clip, token di accesso, WebSocket

## Registro sessioni
- 15/11/2026: creato il quaderno di cantiere, modalità guidata, nome Ctrl+Alt+Design.
- 15/11/2026 sera: interfaccia v2 morbida in stile Apple (SF Pro/Geist, Font Awesome, Lenis); controllo /api/health e CORS nell'adattatore; deploy Vercel preparato, non pubblicato (token non trovato).
- 15/11/2026: film (4 clip, 18 s dopo il raccordo e la rimozione dei fotogrammi doppi), adattatore web, landing e console; test: pytest 14 (copertura 98 %), Vitest 15, Playwright 1 e2e; screenshot in `docs/screens/`.
- 15/11/2026: fase 0 chiusa. Ambiente Python 3.11 ricreato, suite rieseguite (server 481 + 1 noto, MULCA 258), Playwright pronto, Higgsfield collegato in prova gratuita, Mobbin bloccato dal piano.

## Speso finora
0 € (Higgsfield: tutto dentro la prova gratuita)
