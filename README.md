# s4me_gen

Genera il canale S4Me (file .py e .json) analizzando un sito.

## Uso con GitHub Actions
1. Carica questi file in una tua repo (s4me_gen.py, requirements.txt, .github/workflows/genera.yml).
2. Impostazioni, Actions, General, Workflow permissions: Read and write permissions.
3. Actions, "Genera canale S4Me", Run workflow: scrivi il sito e avvia.
4. Dopo qualche minuto trovi la cartella `canali/<nome del sito>/` con il .py, il .json, il rapporto e la cattura.
   Gli stessi file sono anche nell'artifact della run.

Il nome della cartella e dato dal dominio senza www e senza estensione.

## Cloudflare
La action controlla prima se il sito mostra la challenge di Cloudflare. Solo in quel caso avvia FlareSolverr in Docker con LANG=en-US
(serve perche la challenge in italiano non viene riconosciuta), supera la challenge e passa cookie e user agent
al browser del tool. In locale: `python3 s4me_gen.py SITO --flaresolverr http://localhost:8191`.

## Limiti
Gli IP dei runner GitHub a volte vengono bloccati da Cloudflare: in quel caso rilancia la action.
Se continua a fallire usa il tool sul PC con --pausa.
Controlla sempre il rapporto: le righe TODO vanno completate a mano.

## Paese del sito
I runner GitHub sono negli Stati Uniti: i siti che scelgono il paese dall'IP (come JustWatch) aprono la versione americana.
Scrivi nel campo "sito" l'indirizzo con il paese, per esempio `https://www.justwatch.com/it`.

Se la run si blocca, il log stampa dopo 5 minuti lo stato del programma e la run si ferma da sola dopo 20 minuti.

## Riferimento
La cartella `riferimento/` contiene il canale JustWatch TV scritto a mano e verificato nell addon: è il modello di quello che il tool deve produrre per i siti con API (menu, cursore, TMDB con controllo, riproduzione Widevine).

## Cosa scopre da solo
Per i siti con API il tool visita le sezioni del menu, i percorsi dei titoli e i link a contenuti gratuiti, prova i menu a tendina (ordinamenti e filtri), apre un film e una serie di esempio, cerca la richiesta degli episodi (stagione ed episodio) e prova a far partire un film e un episodio. Il canale generato ha una voce di menu per ogni sezione e ordinamento trovati.
In `test/` ci sono un sito di prova (`server_c.py`) con sezioni, ordinamenti, serie, episodi e riproduzione, e lo script `run_c.py` che prova il canale generato.
