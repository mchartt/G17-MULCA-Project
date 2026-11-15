# Stato del progetto: Ctrl+Alt+Design (web app del Group Coordinator)

- **Modalità**: guidata
- **Dove si lavora**: computer di Matteo (cartella `WebstormProjects/group-coordinator/mulca/prototype/webapp`), con una copia di lavoro nello spazio cloud di Claude
- **Repository GitHub**: https://github.com/mchartt/G17-MULCA-Project (privato), branch `group17/coordinator`. GitLab del laboratorio non si tocca.
- **Partito da una ricetta?**: no

## Mappa delle fasi
- [x] 0. Setup strumenti (`setup-iniziale`), 15/11
- [ ] 1. Idea chiarita (`intervista-idea`)
- [ ] 2. Obiettivi (`obiettivi-sito`)
- [ ] 3. Tipologia (`tipologia-sito`)
- [ ] 4. Architettura e tecnologia (`architettura-sito`)
- [ ] 5. Design (`design-sito`)
- [ ] 6. Asset (`crea-asset`)
- [ ] 7. Costruzione (`costruisci-sito` o `sito-film`)
- [ ] 8. Verifica (`verifica-sito`)
- [ ] 9. Messa online (`deploy-sito`)
- [ ] 10. Ricetta salvata e manuale consegnato (`libreria-ricette`)

## Fase corrente
1 Idea: si apre l'intervista (`intervista-idea`), compressa perché bisogni, obiettivi e scenari esistono già nella specifica v3.

## Prossima azione
Matteo sceglie come usare la finestra gratuita di Higgsfield (fino al 16/11 09:49 UTC, 10:49 in Italia) e come sostituire Mobbin; poi intervista sulla landing.

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
transazione, copertura dei test, branch, commit, push, remoto, bundle, interruttore (feature flag), ambiente virtuale, keyframe, concatenazione delle clip

## Registro sessioni
- 15/11/2026: creato il quaderno di cantiere, modalità guidata, nome Ctrl+Alt+Design.
- 15/11/2026: fase 0 chiusa. Ambiente Python 3.11 ricreato, suite rieseguite (server 481 + 1 noto, MULCA 258), Playwright pronto, Higgsfield collegato in prova gratuita, Mobbin bloccato dal piano.

## Speso finora
0 €
