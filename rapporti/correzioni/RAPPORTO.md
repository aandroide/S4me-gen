# Controllo dei canali

Riepilogo: CORRETTO IN PARTE 1

## CORRETTO IN PARTE (1)

### la7
Sito: https://www.la7.it
- indirizzo scritto nel canale: https://www.la7.it
- il sito reindirizza a un altro indirizzo: https://www.la7play.it (in channels.json c'e https://www.la7.it)
- ROTTO: replay_menu /rivedila7/0/la7 | patron non trova titoli
-   campione della pagina salvato in rapporti/correzioni/la7/pagina_replay_menu_rivedila7_0_la7.html
-   nessuna regex sostitutiva trovata automaticamente in /rivedila7/0/la7
- ROTTO: replay_menu /rivedila7/0/la7cinema | patron non trova titoli
-   campione della pagina salvato in rapporti/correzioni/la7/pagina_replay_menu_rivedila7_0_la7cinema.html
-   regex proposta: 5 titoli su 5 card | gruppi persi: day, month, num
-   gruppi non piu presenti nelle card e non essenziali per S4Me: day, month, num
- file corretto scritto in rapporti/correzioni/la7: 1 pagine su 2 ora trovano titoli
- attenzione: non tutte le pagine sono state riparate, il canale resta da rivedere a mano
- riga per channels.json: "la7": "https://www.la7play.it",

