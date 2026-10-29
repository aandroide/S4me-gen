# S4me-gen

Strumenti per tenere in ordine i canali di S4Me (Stream4me). Non scrive mai nella repo dell'addon: le correzioni pronte stanno in `riparazioni/` e si passano a mano.

## Come e organizzato

| Cartella | Cosa contiene |
|---|---|
| `strumenti/` | Tutti gli script (controllo canali, prova fino al video, generatore, scarica pagine, proxy) e le prove (`strumenti/test/`, con il Kodi finto in `strumenti/test/kodi_finto/`). |
| `canali_base/` | Copia dei canali S4Me ufficiali e `channels.json.txt` con gli indirizzi. Si aggiorna da sola ogni giorno. |
| `riparazioni/` | Canali corretti da me (la7, tantifilm, eurostreaming, streamingcommunity e altri), pronti da portare nell'addon. Le Action li usano al posto dell'originale. |
| `rapporti/` | Risultati delle Action: `correzioni/` (regex rotte e file corretti), `prove/` (esito fino al video), `snapshot_api/` (riferimenti delle API), `pagine/` (pagine scaricate). |
| `archivio/` | Canali generati dal tool e canale di riferimento JustWatch TV. Non servono al controllo giornaliero. |

## Le Action (Actions su GitHub)

- **Controlla canali** (ogni giorno alle 5:23, anche a mano): aggiorna indirizzi e canali da S4Me, prova le regex sui siti veri, scrive `rapporti/correzioni/` e poi prova ogni canale fino al video in `rapporti/prove/`.
- **Prova canale fino al video**: prova uno o piu canali (e una voce di menu) fino al flusso video.
- **Scarica pagine di un sito**: salva html, frame e richieste di rete in `rapporti/pagine/`.
- **Scarica file di un sito**: scarica file o pagine dal runner e li committa in `file_scaricati/` (da cancellare dopo l'uso).
- **Genera canale S4Me** e **Genera canale S4Me (sul mio PC Windows)**: analizzano un sito nuovo e scrivono il canale in `archivio/canali/<sito>/`.

## Sul mio PC (indirizzo italiano)

`PROVA_SUL_MIO_PC.bat` scarica il progetto, prova tutti i canali con `strumenti/prova_locale.py` e mette `prove_locali.zip` sul Desktop.

## Limiti

I runner di GitHub hanno un indirizzo americano: i siti che bloccano fuori Italia o usano Cloudflare duro possono dare falsi errori. Il controllo video con DRM e token va provato sul PC.

## Generatore di canali (`strumenti/s4me_gen.py`)

1. Actions, "Genera canale S4Me", Run workflow: scrivi il sito e avvia (`https://www.justwatch.com/it` per i siti che scelgono il paese dall'IP).
2. Dopo qualche minuto in `archivio/canali/<nome del sito>/` trovi il `.py`, il `.json`, il rapporto e la cattura.
3. Controlla sempre il rapporto: le righe TODO vanno completate a mano.

Se il sito e dietro Cloudflare parte FlareSolverr in Docker. In locale: `python3 strumenti/s4me_gen.py SITO --flaresolverr http://localhost:8191`. Se la run si blocca si ferma da sola dopo 20 minuti.
