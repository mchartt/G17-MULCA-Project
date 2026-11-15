# Strumenti del progetto: Ctrl+Alt+Design (web app del Group Coordinator)

Aggiornato: 15/11/2026, fase 0 (setup).

| Bisogno | Strumento scelto | Connettore o chiave | Stato | Costo |
|---|---|---|---|---|
| Codice della web app (React + TypeScript + Vite) | Node 22.23, npm 10.9 sulla shell del PC | nessuno | pronto | 0 |
| Adattatore web nel processo MULCA (FastAPI + WebSocket) | Python 3.11.17 in un ambiente virtuale della sessione (`uv venv -p 3.11`) | nessuno | pronto: server 481 passati + 1 errore noto di voce, MULCA 258 passati (15/11) | 0 |
| Test end to end | Playwright con Chromium headless, scaricato sulla shell del PC | nessuno | pronto (download riuscito il 15/11) | 0 |
| Versioni del codice | git, remoto `github` (mchartt/G17-MULCA-Project, privato); GitLab non si tocca | nessuno; `gh` non installato | push solo su richiesta | 0 |
| Riferimenti di stile | fruitful.com, tradetash.com, contralabs.com/creative-intelligence-report-2026, humanlayer.dev (console) | lettura web | pronto | 0 |
| Modelli di prompt per la landing | prompt getlayers.ai "Baseline" e "Lumora" (copie in `docs/riferimenti/`) | file | pronto | 0 |
| Schermate salvate su Mobbin | Mobbin | connettore collegato | BLOCCATO: il connettore chiede un piano Mobbin a pagamento | piano Mobbin |
| Immagini (keyframe della landing) | Higgsfield, modelli gratuiti nella prova (gpt_image_2_6 a 1k/2k qualità low/medium, nano_banana, seedream_v5_pro) | connettore Higgsfield | pronto, crediti 0, prova gratuita fino al 16/11 09:49 UTC | 0 dentro la prova |
| Video concatenati della landing (finta animazione 3D allo scroll) | Higgsfield Seedance 2.0 (fotogramma iniziale e finale, 720p, max 15 s) | connettore Higgsfield | pronto, stessa finestra gratuita | 0 dentro la prova, poi crediti a pagamento |
| Montaggio clip e fotogrammi | ffmpeg | da controllare sulla shell del PC | da controllare in fase 7 | 0 |
| Mockup | Prototipo cliccabile e mockup esistenti (artefatti del progetto) + anteprime HTML | nessuno | pronto | 0 |
| Hosting | nessuno: la web app è servita in locale dall'adattatore MULCA (istruzioni di progetto, niente hosting a pagamento) | nessuno | deciso | 0 |

## Chiavi necessarie (solo i nomi, mai i valori)
| Nome variabile | Servizio | Presente nel .env |
|---|---|---|
| nessuna per la web app | Higgsfield si usa tramite connettore, senza chiave | n/d |
| (chiavi Azure e token Discord: vedi `muca-server/docs/coordinator/AZURE_SETUP.md`) | Azure OpenAI, Discord | in attesa di Matteo |
