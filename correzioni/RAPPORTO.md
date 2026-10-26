# Controllo dei canali

Riepilogo: CORRETTO 1, ROTTO 13, DOMINIO PARCHEGGIATO 1, IRRAGGIUNGIBILE 12, NON VERIFICATO 2, OK 9, NON REGEX 13, SENZA INDIRIZZO 5, TEMPO SCADUTO 1

## CORRETTO (1)

### guardaseriecam
Sito: https://guardaseriex.icu
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://guardaseriex.icu)
- ROTTO: peliculas /serietv-streaming | patron non trova titoli
-   regex proposta: 18 titoli su 18 card
- file corretto scritto in correzioni/guardaseriecam: 1 pagine su 1 ora trovano titoli
- riga per channels.json: "guardaseriecam": "https://guardaseriex.best",

## ROTTO (13)

### animealtadefinizione
Sito: https://www.domainname.de
- ROTTO: peliculas /anime/ | patron non trova titoli
-   nessuna regex sostitutiva trovata automaticamente in /anime/

### bt4g
Sito: https://bt4gprx.com
- ROTTO: peliculas / | patron non trova titoli
-   nessuna regex sostitutiva trovata automaticamente in /

### cineblog001
Sito: https://cineblog001.loan
- il sito reindirizza a un altro indirizzo: https://cineblog001.men (in channels.json c'e https://cineblog001.loan)
- ROTTO: peliculas /film/ | patron non trova titoli
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- ROTTO: peliculas /serie-tv/ | patron non trova titoli
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- ROTTO: peliculas /sub-ita/ | patron non trova titoli
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- riga per channels.json: "cineblog001": "https://cineblog001.men",

### cinemalibero
Sito: https://cinemalibero.cafe
- ROTTO: peliculas /category/film/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /category/film/
- ROTTO: peliculas /category/serie-tv/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /category/serie-tv/
- ROTTO: peliculas /category/anime-giapponesi/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /category/anime-giapponesi/
- ROTTO: peliculas /aggiornamenti-serie-tv/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /aggiornamenti-serie-tv/

### cinetecadibologna
Sito: http://cinestore.cinetecadibologna.it
- ROTTO: peliculas /video/alfabetico_completo | patronBlock non trova nessun blocco
-   regex proposta: 10 titoli su 10 card
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: menu /video/epoche | patron non trova titoli
-   regex proposta: 10 titoli su 10 card
-   non applicata al file: la funzione ha piu varianti di regex
- OK: menu /video/registi | 20 risultati
- OK: menu /video/attori | 19 risultati

### dreamsub
Sito: https://www.animeworld.ac
- ROTTO: peliculas /search?typeY=tv | patronBlock non trova nessun blocco
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=movie | patronBlock non trova nessun blocco
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=oav | patronBlock non trova nessun blocco
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=spinoff | patronBlock non trova nessun blocco
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex

### eurostreaming
Sito: https://eurostream.fun
- OK: peliculas /category/anime-cartoni-animati/ | 18 risultati
- ROTTO: peliculas /aggiornamento-episodi-nuovi/ | patron non trova titoli
-   nessuna regex sostitutiva trovata automaticamente in /aggiornamento-episodi-nuovi/
- OK: peliculas /category/serie-tv-archive/ | 18 risultati

### eurostreaming_actor
Sito: https://eurostreaming.ooo
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://eurostreaming.ooo)
- ROTTO: peliculas /animazione/ | patron non trova titoli
-   regex proposta: 1040 titoli su 343 card | gruppi persi: episode, lang, title2
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /aggiornamento-episodi/ | patron non trova titoli
-   nessuna regex sostitutiva trovata automaticamente in /aggiornamento-episodi/
- riga per channels.json: "eurostreaming_actor": "https://guardaseriex.best",

### guardaserieicu
Sito: https://guardaseriex.cyou
- indirizzo scritto nel canale: https://guardaseriex.cyou
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://guardaseriex.cyou)
- ROTTO: peliculas /serietv-streaming/page/1/ | patron non trova titoli
-   regex proposta: 18 titoli su 18 card | gruppi persi: audio, category, duration, plot, rating, thumbnail
-   non applicata al file: perderebbe i gruppi audio, category, duration, plot, rating, thumbnail
- riga per channels.json: "guardaserieicu": "https://guardaseriex.best",

### ilgeniodellostreaming_cam
Sito: https://il-geniodellostreaming.garden
- il sito reindirizza a un altro indirizzo: https://il-geniodellostreaming.ink (in channels.json c'e https://il-geniodellostreaming.garden)
- OK: peliculas /catalog/all | 15 risultati
- ROTTO: peliculas /serie-tv/ | patron non trova titoli
-   regex proposta: 20 titoli su 20 card | gruppi persi: categories, plot, quality, rating
-   non applicata al file: la funzione ha piu varianti di regex
- riga per channels.json: "ilgeniodellostreaming_cam": "https://il-geniodellostreaming.ink",

### la7
Sito: https://www.la7.it
- indirizzo scritto nel canale: https://www.la7.it
- ROTTO: replay_menu / | patron non trova titoli
-   nessuna regex sostitutiva trovata automaticamente in /

### serietvu
Sito: http://ww1.serietvu.live
- ROTTO: peliculas /category/serie-tv | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /category/serie-tv
- ROTTO: peliculas /ultimi-episodi/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /ultimi-episodi/

### tantifilm
Sito: https://tanti-film.fun
- il sito reindirizza a un altro indirizzo: https://tanti-film.garden (in channels.json c'e https://tanti-film.fun)
- ROTTO: peliculas /film | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /film
- ROTTO: peliculas /serie-tv/ | patronBlock non trova nessun blocco
-   nessuna regex sostitutiva trovata automaticamente in /serie-tv/
- riga per channels.json: "tantifilm": "https://tanti-film.garden",

## DOMINIO PARCHEGGIATO (1)

### lordchannel
Sito: https://lordchannel.net
- la home di https://lordchannel.net sembra un dominio in vendita o vuoto | motivo: pagina quasi vuota | link: 0 | dimensione: 1938 | titolo: Manutenzione – LC3Remix

## IRRAGGIUNGIBILE (12)

### altadefinizione
Sito: https://altadefinizione.nuovo.live
- findhost non ha dato un indirizzo partendo da https://altadefinizione.nuovo.live: Invalid URL '': No scheme supplied. Perhaps you meant https://?

### altadefinizionecommunity
Sito: https://altaregistrazione.net
- findhost non ha dato un indirizzo partendo da https://altaregistrazione.net: findhost non restituisce un indirizzo (pagina cambiata?)

### animeforce
Sito: https://www.animeforce.it
- il sito non risponde (tempo scaduto) (https://www.animeforce.it)

### cb01anime
Sito: https://cb01new.one
- il nome del sito non esiste piu (DNS) (https://cb01new.one)

### dinostreaming
Sito: https://dinostreaming.it
- il nome del sito non esiste piu (DNS) (https://dinostreaming.it)

### filmpertutti
Sito: https://filmpertuttiiii.nuovo.live
- findhost non ha dato un indirizzo partendo da https://filmpertuttiiii.nuovo.live: findhost non restituisce un indirizzo (pagina cambiata?)

### filmstreaming
Sito: https://film-streaming-ita.cam
- il nome del sito non esiste piu (DNS) (https://film-streaming-ita.cam)

### ilcorsaronero
Sito: https://ilcorsaronero.link
- il sito non risponde (tempo scaduto) (https://ilcorsaronero.link)

### italiafilm
Sito: https://italia-film.lifestyle
- il nome del sito non esiste piu (DNS) (https://italia-film.lifestyle)

### metalvideo
Sito: https://metalvideo.com
- errore del certificato HTTPS (https://metalvideo.com)

### mondoserietv
Sito: http://ww25.mondoserietv.club
- il nome del sito non esiste piu (DNS) (http://ww25.mondoserietv.club)

### piratestreaming
Sito: https://piratestreaming.design
- il nome del sito non esiste piu (DNS) (https://piratestreaming.design)

## NON VERIFICATO (2)

### paramount
Sito: https://www.mtv.com

### streamingita
Sito: https://streamingita.homes

## OK (9)

### 1337x
Sito: https://1337x.to
- indirizzo scritto nel canale: https://1337x.to
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- OK: peliculas /movie-lib-sort/all/it/popularity/desc/all/1/ | 14 risultati
- OK: peliculas /movie-library/1/ | 25 risultati

### accuradio
Sito: https://www.accuradio.com
- indirizzo scritto nel canale: https://www.accuradio.com
- OK: peliculas / | 48 risultati

### altadefinizione01
Sito: https://altadefinizione-01.autos
- OK: peliculas /lastnews/ | 78 risultati
- OK: peliculas /cinema/ | 94 risultati
- OK: peliculas /sub-ita/ | 94 risultati
- OK: peliculas /serie-tv/ | 94 risultati

### altadefinizioneclick
Sito: https://altadefinizionex.forum
- il sito reindirizza a un altro indirizzo: https://altadefinizionex.vip (in channels.json c'e https://altadefinizionex.forum)
- OK: peliculas /film/ | 30 risultati
- OK: peliculas /serie-tv/ | 30 risultati
- riga per channels.json: "altadefinizioneclick": "https://altadefinizionex.vip",

### animesaturn
Sito: https://www.animesaturn.net
- OK: peliculas /az-list | 30 risultati
- OK: peliculas /filter?languages=it | 30 risultati
- OK: peliculas /filter?languages=jp | 30 risultati
- OK: peliculas /filter?sort=best_rated | 30 risultati

### animeworld
Sito: https://www.animeworld.ac
- OK: peliculas /filter?sort= | 40 risultati
- OK: peliculas /ongoing | 40 risultati
- OK: peliculas /updated | 78 risultati
- OK: peliculas /newest | 40 risultati

### casacinema
Sito: https://casa-cinema.boats
- OK: peliculas /film | 16 risultati
- OK: peliculas /serie-tv | 16 risultati
- OK: peliculas /miniserie-tv | 16 risultati

### hd4me
Sito: https://hd4me.net
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- OK: peliculas /index | 4585 risultati

### toonitalia
Sito: https://toonitalia.xyz
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- OK: peliculas /category/anime | 400 risultati
- OK: peliculas /anime-ita | 2768 risultati
- attenzione: peliculas /anime-ita, patronNext non trova la pagina successiva (puo essere l'ultima pagina)
- OK: peliculas /contatti | 822 risultati
- attenzione: peliculas /contatti, patronNext non trova la pagina successiva (puo essere l'ultima pagina)
- OK: peliculas /film-animazione | 1626 risultati
- attenzione: peliculas /film-animazione, patronNext non trova la pagina successiva (puo essere l'ultima pagina)

## NON REGEX (13)

### animeunity
Sito: https://www.animeunity.to
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### aniplay
Sito: https://aniplay.co
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### discoveryplus
Sito: https://www.discoveryplus.com
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### justwatch
Sito: https://www.justwatch.com
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### mediasetplay
Sito: https://mediasetinfinity.mediaset.it
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### plutotv
Sito: https://pluto.tv
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### raiplay
Sito: https://www.raiplay.it
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### streamingcommunity
Sito: https://streamingcommunityz.build
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### thepiratebay
Sito: n.d.
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### tunein
Sito: n.d.
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### videosky
Sito: n.d.
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### vvvvid
Sito: n.d.
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

### youtube_channel
Sito: n.d.
- nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato

## SENZA INDIRIZZO (5)

### animeuniverse
Sito: n.d.
- il canale non e in channels.json e non ha un indirizzo fisso nel file

### guardaserieclick
Sito: n.d.
- il canale non e in channels.json e non ha un indirizzo fisso nel file

### ilgeniodellostreaming
Sito: n.d.
- il canale non e in channels.json e non ha un indirizzo fisso nel file

### italiaserie
Sito: n.d.
- il canale non e in channels.json e non ha un indirizzo fisso nel file

### streamtime
Sito: n.d.
- il canale non e in channels.json e non ha un indirizzo fisso nel file

## TEMPO SCADUTO (1)

### cineblog01
Sito: https://cb01official.uno
- il controllo di questo canale ha superato 600 secondi (sito lento o pagina enorme)

