# Controllo dei canali

Riepilogo: CORRETTO 3

## CORRETTO (3)

### tantifilm
Sito: https://tanti-film.garden
- ROTTO: peliculas /film | patronBlock non trova nessun blocco
-   campione della pagina salvato in rapporti/correzioni/tantifilm/pagina_peliculas_film.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 33 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- ROTTO: peliculas /serie-tv/ | patronBlock non trova nessun blocco
-   campione della pagina salvato in rapporti/correzioni/tantifilm/pagina_peliculas_serie_tv.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 25 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- file corretto scritto in rapporti/correzioni/tantifilm: 2 pagine su 2 ora trovano titoli

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
- riga per channels.json: "la7": "https://www.la7play.it",

### cinetecadibologna
Sito: http://cinestore.cinetecadibologna.it
- ROTTO: peliculas /video/alfabetico_completo | patronBlock non trova nessun blocco
-   campione della pagina salvato in rapporti/correzioni/cinetecadibologna/pagina_peliculas_video_alfabetico_completo.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 10 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- ROTTO: menu /video/epoche | patron non trova titoli
-   campione della pagina salvato in rapporti/correzioni/cinetecadibologna/pagina_menu_video_epoche.html
-   regex proposta: 10 titoli su 10 card
-   non applicata al file: la funzione ha piu varianti di regex
- OK: menu /video/registi | 20 risultati
- OK: menu /video/attori | 19 risultati
- file corretto scritto in rapporti/correzioni/cinetecadibologna: 3 pagine su 4 ora trovano titoli

