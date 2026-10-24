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
Nella action c'e l'opzione "cloudflare" (attiva di default): avvia FlareSolverr in Docker con LANG=en-US
(serve perche la challenge in italiano non viene riconosciuta), supera la challenge e passa cookie e user agent
al browser del tool. In locale: `python3 s4me_gen.py SITO --flaresolverr http://localhost:8191`.

## Limiti
Gli IP dei runner GitHub a volte vengono bloccati da Cloudflare: in quel caso rilancia la action.
Se continua a fallire usa il tool sul PC con --pausa.
Controlla sempre il rapporto: le righe TODO vanno completate a mano.
