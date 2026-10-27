# Controllo dei canali

Riepilogo: ROTTO 3, OK 1, ERRORE 1

## ROTTO (3)

### ilgeniodellostreaming_cam
Sito: https://il-geniodellostreaming.ink
- OK: peliculas /catalog/all | 18 risultati
- ROTTO: peliculas /serie-tv/ | patron non trova titoli
-   campione della pagina salvato in correzioni/ilgeniodellostreaming_cam/pagina_peliculas_serie_tv.html
-   regex proposta: 20 titoli su 20 card | gruppi persi: categories, plot, quality, rating

### tantifilm
Sito: https://tanti-film.garden
- ROTTO: peliculas /film | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/tantifilm/pagina_peliculas_film.html
-   nessuna regex sostitutiva trovata automaticamente in /film
- ROTTO: peliculas /serie-tv/ | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/tantifilm/pagina_peliculas_serie_tv.html
-   nessuna regex sostitutiva trovata automaticamente in /serie-tv/

### guardaseriecam
Sito: https://guardaseriex.best
- ROTTO: peliculas /serietv-streaming | patron non trova titoli
-   campione della pagina salvato in correzioni/guardaseriecam/pagina_peliculas_serietv_streaming.html
-   regex proposta: 18 titoli su 18 card

## OK (1)

### animesaturn
Sito: https://www.animesaturn.net
- OK: peliculas /az-list | 30 risultati
- OK: peliculas /filter?languages=it | 30 risultati
- OK: peliculas /filter?languages=jp | 30 risultati
- OK: peliculas /filter?sort=best_rated | 30 risultati

## ERRORE (1)

### animemars
Sito: n.d.
- errore interno: [Errno 2] No such file or directory: '/home/runner/work/S4me-gen/S4me-gen/canali_base/animemars.py'

