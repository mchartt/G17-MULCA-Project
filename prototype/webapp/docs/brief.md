# Brief: web app del Group Coordinator (progetto Ctrl+Alt+Design)

> Ogni riga viene da una risposta di Matteo (15/11/2026), dalla specifica v3 o dalle istruzioni
> di progetto. Modalità breve: la specifica copre già bisogni, obiettivi e scenari.

## In una frase
Una landing cinematografica e una console a tre colonne per un agente che aiuta gruppi di 3-5
studenti pari a coordinarsi: propone azioni brevi come schede, e nulla cambia finché un membro
non clicca.

## L'attività o il progetto
Prototipo del corso Advanced User Interfaces 2026-27 (proposta 4.6, Gruppo 17). Nome del prodotto
sulla landing: **Cadence**, mostrato come "Cadence · Group Coordinator" (scelta di Matteo). Esistono
altri prodotti con questo nome (un'app Slack per aggiornamenti di team, Cadence Calendar, Cadence
Design Systems): accettabile per un prototipo del corso non commerciale.

## Il pubblico
Membri di gruppi di pari senza capo (personas Sofia, Ahmed, Luca della specifica §3.2), da
portatile. Alla Demo Madness del 2/12: tutor, docente e altri gruppi, su proiettore.

## Il problema che il sito risolve per il visitatore
Coordinarsi costa: decisioni che non si chiudono, attività senza responsabile, ritardi scoperti
tardi (specifica §2.1).

## Cosa deve fare il visitatore (l'azione principale)
Creare lo spazio del gruppo oppure entrarci con un codice di invito (UC1, FR1, FR2), dopo
l'informativa sui dati.

## Contenuti
Hero cinematografico, poi tre sezioni, poi l'ingresso (scelta di Matteo):
1. il problema in una riga;
2. come funziona in 4 passi: carta del progetto, piano, schede di proposta, check-in;
3. la regola: nulla cambia finché un membro non clicca;
4. crea o entra.
Tutti i testi vengono dalla specifica; niente testimonianze, numeri o recensioni inventate.

## Stile e sensazione
Calmo, chiaro, affidabile (scelta di Matteo): colori chiari, molto spazio, tono rassicurante.
Movimento: cinematografico solo sulla landing; la console resta pulita, sullo stile di
humanlayer.dev.

## Il viaggio della telecamera (film della landing)
"Dal caos al piano" (scelta di Matteo): fumetti di chat e post-it che fluttuano in uno spazio
scuro si allineano piano piano e diventano una bacheca 3D pulita (linea temporale, attività con
responsabile, una scheda di decisione). Clip Seedance 2.0 su Higgsfield concatenate (fotogramma
finale di una clip = fotogramma iniziale della successiva), proiettate allo scroll.

## Riferimenti
fruitful.com (tono calmo, percorso in passi numerati), tradetash.com (titoli corti e decisi,
"Scroll to explore"), contralabs.com/creative-intelligence-report-2026 (sezioni con un dato o un
video ciascuna), humanlayer.dev (console). Modelli di prompt: `riferimenti/getlayers-*-prompt.md`.
Schermate Mobbin non leggibili (piano a pagamento).

## Vincoli
Budget 0 €; immagini e video gratuiti solo nella prova Higgsfield fino al 16/11 09:49 UTC.
Web app funzionante entro il 23/11, demo il 2/12. Interfaccia in inglese, WCAG 2.1 AA,
`prefers-reduced-motion` (versione statica senza film). Servita in locale dall'adattatore MULCA,
nessun hosting. Nessuno aggiorna i contenuti dopo la consegna.

## Fuori dallo scopo
Canali, privacy dettagliata e FAQ sulla landing (scartati come "pagina completa"); hosting
pubblico; testimonianze.

## Registro della chiarezza
| Voce | Stato | Valore | Fonte |
|---|---|---|---|
| Cos'è | chiaro | landing + console del Group Coordinator | specifica §2.2 |
| Nome | chiaro | Cadence · Group Coordinator | Matteo 15/11 |
| Pubblico | chiaro | studenti in gruppi di pari; pubblico della demo | specifica §3 |
| Azione principale | chiaro | crea o entra nello spazio | UC1 |
| Contenuti | chiaro | hero + 3 sezioni + ingresso | Matteo 15/11 |
| Sensazione | chiaro | calmo, chiaro, affidabile | Matteo 15/11 |
| Viaggio del film | chiaro | dal caos al piano | Matteo 15/11 |
| Movimento | chiaro | cinematografico solo sulla landing | decisione 15/11 |
| Budget e tempi | chiaro | 0 €, 23/11, prova Higgsfield fino al 16/11 | istruzioni, Higgsfield |
