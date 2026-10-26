# Controllo dei canali

Riepilogo: CORRETTO 4, ROTTO 7, DOMINIO PARCHEGGIATO 3, BLOCCO ANTI BOT 1, IRRAGGIUNGIBILE 12, NON VERIFICATO 4, OK 19, SENZA INDIRIZZO 6, TEMPO SCADUTO 1

## CORRETTO (4)

### cinetecadibologna
Sito: http://cinestore.cinetecadibologna.it
- ROTTO: peliculas /video/alfabetico_completo | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/cinetecadibologna/pagina_peliculas_video_alfabetico_completo.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 10 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- ROTTO: menu /video/epoche | patron non trova titoli
-   campione della pagina salvato in correzioni/cinetecadibologna/pagina_menu_video_epoche.html
-   regex proposta: 10 titoli su 10 card
-   non applicata al file: la funzione ha piu varianti di regex
- OK: menu /video/registi | 20 risultati
- OK: menu /video/attori | 19 risultati
- file corretto scritto in correzioni/cinetecadibologna: 3 pagine su 4 ora trovano titoli

### guardaseriecam
Sito: https://guardaseriex.icu
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://guardaseriex.icu)
- ROTTO: peliculas /serietv-streaming | patron non trova titoli
-   campione della pagina salvato in correzioni/guardaseriecam/pagina_peliculas_serietv_streaming.html
-   regex proposta: 18 titoli su 18 card
- file corretto scritto in correzioni/guardaseriecam: 1 pagine su 1 ora trovano titoli
- riga per channels.json: "guardaseriecam": "https://guardaseriex.best",

### guardaserieicu
Sito: https://guardaseriex.cyou
- indirizzo scritto nel canale: https://guardaseriex.cyou
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://guardaseriex.cyou)
- ROTTO: peliculas /serietv-streaming/page/1/ | patron non trova titoli
-   campione della pagina salvato in correzioni/guardaserieicu/pagina_peliculas_serietv_streaming_page_1.html
-   regex proposta: 18 titoli su 18 card | gruppi persi: audio, category, duration, plot, rating, thumbnail
-   gruppi non piu presenti nelle card e non essenziali per S4Me: audio, category, duration, plot, rating, thumbnail
- file corretto scritto in correzioni/guardaserieicu: 1 pagine su 1 ora trovano titoli
- riga per channels.json: "guardaserieicu": "https://guardaseriex.best",

### tantifilm
Sito: https://tanti-film.fun
- il sito reindirizza a un altro indirizzo: https://tanti-film.garden (in channels.json c'e https://tanti-film.fun)
- ROTTO: peliculas /film | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/tantifilm/pagina_peliculas_film.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 33 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- ROTTO: peliculas /serie-tv/ | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/tantifilm/pagina_peliculas_serie_tv.html
-   patronBlock rimosso: senza blocco le regex dei titoli trovano 25 risultati sull'intera pagina (da controllare: potrebbero entrare anche card di slider o barre laterali)
- file corretto scritto in correzioni/tantifilm: 2 pagine su 2 ora trovano titoli
- riga per channels.json: "tantifilm": "https://tanti-film.garden",

## ROTTO (7)

### bt4g
Sito: https://bt4gprx.com
- ROTTO: peliculas / | patron non trova titoli
-   campione della pagina salvato in correzioni/bt4g/pagina_peliculas_home.html
-   nessuna regex sostitutiva trovata automaticamente in /

### cineblog001
Sito: https://cineblog001.loan
- il sito reindirizza a un altro indirizzo: https://cineblog001.men (in channels.json c'e https://cineblog001.loan)
- ROTTO: peliculas /film/ | patron non trova titoli
-   campione della pagina salvato in correzioni/cineblog001/pagina_peliculas_film.html
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- ROTTO: peliculas /serie-tv/ | patron non trova titoli
-   campione della pagina salvato in correzioni/cineblog001/pagina_peliculas_serie_tv.html
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- ROTTO: peliculas /sub-ita/ | patron non trova titoli
-   campione della pagina salvato in correzioni/cineblog001/pagina_peliculas_sub_ita.html
-   regex proposta: 70 titoli su 51 card
-   non applicata al file: regex dinamica
- riga per channels.json: "cineblog001": "https://cineblog001.men",

### dreamsub
Sito: https://www.animeworld.ac
- ROTTO: peliculas /search?typeY=tv | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/dreamsub/pagina_peliculas_search_typeY_tv.html
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=movie | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/dreamsub/pagina_peliculas_search_typeY_movie.html
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=oav | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/dreamsub/pagina_peliculas_search_typeY_oav.html
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /search?typeY=spinoff | patronBlock non trova nessun blocco
-   campione della pagina salvato in correzioni/dreamsub/pagina_peliculas_search_typeY_spinoff.html
-   regex proposta: 237 titoli su 216 card | gruppi persi: episode, lang, year
-   non applicata al file: la funzione ha piu varianti di regex

### eurostreaming
Sito: https://eurostream.fun
- OK: peliculas /category/anime-cartoni-animati/ | 18 risultati
- ROTTO: peliculas /aggiornamento-episodi-nuovi/ | patron non trova titoli
-   campione della pagina salvato in correzioni/eurostreaming/pagina_peliculas_aggiornamento_episodi_nuovi.html
-   nessuna regex sostitutiva trovata automaticamente in /aggiornamento-episodi-nuovi/
- OK: peliculas /category/serie-tv-archive/ | 18 risultati

### eurostreaming_actor
Sito: https://eurostreaming.ooo
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- il sito reindirizza a un altro indirizzo: https://guardaseriex.best (in channels.json c'e https://eurostreaming.ooo)
- ROTTO: peliculas /animazione/ | patron non trova titoli
-   campione della pagina salvato in correzioni/eurostreaming_actor/pagina_peliculas_animazione.html
-   regex proposta: 1040 titoli su 343 card | gruppi persi: episode, lang, title2
-   non applicata al file: la funzione ha piu varianti di regex
- ROTTO: peliculas /aggiornamento-episodi/ | patron non trova titoli
-   campione della pagina salvato in correzioni/eurostreaming_actor/pagina_peliculas_aggiornamento_episodi.html
-   nessuna regex sostitutiva trovata automaticamente in /aggiornamento-episodi/
- riga per channels.json: "eurostreaming_actor": "https://guardaseriex.best",

### ilgeniodellostreaming_cam
Sito: https://il-geniodellostreaming.garden
- il sito reindirizza a un altro indirizzo: https://il-geniodellostreaming.ink (in channels.json c'e https://il-geniodellostreaming.garden)
- OK: peliculas /catalog/all | 15 risultati
- ROTTO: peliculas /serie-tv/ | patron non trova titoli
-   campione della pagina salvato in correzioni/ilgeniodellostreaming_cam/pagina_peliculas_serie_tv.html
-   regex proposta: 20 titoli su 20 card | gruppi persi: categories, plot, quality, rating
-   non applicata al file: la funzione ha piu varianti di regex
- riga per channels.json: "ilgeniodellostreaming_cam": "https://il-geniodellostreaming.ink",

### la7
Sito: https://www.la7.it
- indirizzo scritto nel canale: https://www.la7.it
- ROTTO: replay_menu / | patron non trova titoli
-   campione della pagina salvato in correzioni/la7/pagina_replay_menu_home.html
-   nessuna regex sostitutiva trovata automaticamente in /

## DOMINIO PARCHEGGIATO (3)

### animealtadefinizione
Sito: https://www.domainname.de
- la home di https://www.domainname.de sembra un dominio in vendita o vuoto | motivo: frase "Domainname.de" | link: 23 | dimensione: 25306 | titolo: Buy & sell domains safely | Domainname.de

### lordchannel
Sito: https://lordchannel.net
- la home di https://lordchannel.net sembra un dominio in vendita o vuoto | motivo: pagina quasi vuota | link: 0 | dimensione: 1938 | titolo: Manutenzione – LC3Remix

### serietvu
Sito: http://ww1.serietvu.live
- la home di http://ww1.serietvu.live sembra un dominio in vendita o vuoto | motivo: frase "abovedomains" | link: 1 | dimensione: 27468 | titolo: nessuno

## BLOCCO ANTI BOT (1)

### cinemalibero
Sito: https://cinemalibero.cafe
- peliculas /category/film/: il sito risponde con una pagina di sfida o di redirect via script (titolo "redirecting...", 1 link, 5634 byte): non e un cambio di struttura
- peliculas /category/serie-tv/: il sito risponde con una pagina di sfida o di redirect via script (titolo "redirecting...", 1 link, 5642 byte): non e un cambio di struttura
- peliculas /category/anime-giapponesi/: il sito risponde con una pagina di sfida o di redirect via script (titolo "redirecting...", 1 link, 5662 byte): non e un cambio di struttura
- peliculas /aggiornamenti-serie-tv/: il sito risponde con una pagina di sfida o di redirect via script (titolo "redirecting...", 1 link, 5655 byte): non e un cambio di struttura

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

## NON VERIFICATO (4)

### animeunity
Sito: https://www.animeunity.to
- home https://www.animeunity.to: FlareSolverr non ha superato la challenge: Error: Error solving the challenge. Cloudflare has blocked this request. Probabl
- non controllabile senza parametri: https://www.animeunity.to/archivio (FlareSolverr non ha superato la challenge: Error: Error solving the challenge. Cloudflare has blocked this request. Probabl)
- non controllabile senza parametri: https://www.animeunity.to/archivio/get-animes (FlareSolverr non ha superato la challenge: Error: Error solving the challenge. Cloudflare has blocked this request. Probabl)
- nessun indirizzo controllabile senza parametri o accessi: canale a API con login o dati dinamici

### aniplay
Sito: https://aniplay.co
- home https://aniplay.co: il sito non risponde (tempo scaduto)
- non controllabile senza parametri: https://aniplay.co/api/anime/advanced-search (il sito non risponde (tempo scaduto))
- non controllabile senza parametri: https://aniplay.co/api/anime/find-by-char (il sito non risponde (tempo scaduto))
- nessun indirizzo controllabile senza parametri o accessi: canale a API con login o dati dinamici

### paramount
Sito: https://www.mtv.com

### streamingita
Sito: https://streamingita.homes

## OK (19)

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

### discoveryplus
Sito: https://www.discoveryplus.com
- OK: https://eu1-prod-direct.discoveryplus.com | html

### hd4me
Sito: https://hd4me.net
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- OK: peliculas /index | 3449 risultati

### justwatch
Sito: https://www.justwatch.com
- OK: https://www.justwatch.com/ | html
- non controllabile senza parametri: https://apis.justwatch.com/graphql (HTTP 400)

### mediasetplay
Sito: https://mediasetinfinity.mediaset.it
- OK: https://mediasetinfinity.mediaset.it/cinema | html
- OK: https://mediasetinfinity.mediaset.it/fiction | html
- OK: https://mediasetinfinity.mediaset.it/programmitv | html
- OK: https://mediasetinfinity.mediaset.it/talent | html
- OK: https://mediasetinfinity.mediaset.it/kids | html
- OK: https://mediasetinfinity.mediaset.it/documentari | html
- non controllabile senza parametri: https://api-ott-prod-fe.mediaset.net/PROD/play/reco/anonymous/v2.0? (HTTP 401)
- OK: https://mediasetinfinity.mediaset.it | html
- non controllabile senza parametri: https://api-ott-prod-fe.mediaset.net/PROD/play/idm/anonymous/login/v2.0 (HTTP 403)
- non controllabile senza parametri: https://api-ott-prod-fe.mediaset.net/PROD/play/reco/anonymous/v2.0 (HTTP 401)

### plutotv
Sito: https://pluto.tv
- OK: https://pluto.tv/it/live-tv/ | html
- non controllabile senza parametri: https://api.pluto.tv (HTTP 404)
- non controllabile senza parametri: https://boot.pluto.tv/v4/start (HTTP 400)
- non controllabile senza parametri: https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv (HTTP 404)
- non controllabile senza parametri: https://cfd-v4-service-stitcher-dash-use1-1.prd.pluto.tv (HTTP 404)
- OK: https://pluto.tv | html
- OK: https://pluto.tv/ | html

### raiplay
Sito: https://www.raiplay.it
- OK: https://www.raiplay.it/palinsesto/onAir.json | json, struttura invariata
- OK: https://www.raiplay.it/dirette | html
- OK: https://www.raiplay.it/guidatv.json | json, struttura invariata
- OK: https://www.raiplay.it/guidatv | html
- OK: https://www.raiplay.it/tipologia/film/index.json | json, struttura invariata
- OK: https://www.raiplay.it/film | html
- OK: https://www.raiplay.it/tipologia/serieitaliane/index.json | json, struttura invariata
- OK: https://www.raiplay.it/serieitaliane | html
- OK: https://www.raiplay.it/tipologia/serieinternazionali/index.json | json, struttura invariata
- OK: https://www.raiplay.it/serieinternazionali | html

### streamingcommunity
Sito: https://streamingcommunityz.build
- OK: Pagina film (sliders) | 30 titoli in props.sliders.0.titles
- OK: Pagina serie TV (sliders) | 30 titoli in props.sliders.0.titles
- OK: Archivio | 60 titoli in props.titles
- OK: Archivio film | 60 titoli in props.titles
- OK: Archivio serie TV | 60 titoli in props.titles
- OK: Archivio per nome | 60 titoli in props.titles
- OK: Ricerca | 60 titoli in props.titles
- OK: Generi | 20 titoli in props.genres
- OK: serie di esempio /it/titles/66423-minimum-wage | 1 stagioni, 14 episodi nella prima

### thepiratebay
Sito: https://apibay.org
- OK: https://apibay.org/q.php?q=matrix | html

### toonitalia
Sito: https://toonitalia.xyz
- sito protetto da Cloudflare: pagine scaricate con FlareSolverr
- OK: peliculas /category/anime | 400 risultati
- OK: peliculas /anime-ita | 2768 risultati
- attenzione: peliculas /anime-ita, patronNext non trova la pagina successiva (puo essere l'ultima pagina)
- OK: peliculas /contatti | 822 risultati
- attenzione: peliculas /contatti, patronNext non trova la pagina successiva (puo essere l'ultima pagina)

### tunein
Sito: http://api.radiotime.com
- indirizzo scritto nel canale: http://api.radiotime.com
- OK: http://api.radiotime.com | html
- OK: https://opml.radiotime.com/Tune.ashx?render=json&id=s24939 | json, struttura invariata

### videosky
Sito: https://video.sky.it
- indirizzo scritto nel canale: https://video.sky.it
- OK: https://video.sky.it/api/v1/getLivestream?id=7 | json, struttura invariata
- OK: https://video.sky.it/api/v1/getLivestream?id=2 | json, struttura invariata
- OK: https://video.sky.it/api/v1/getLivestream?id=1 | json, struttura invariata
- OK: https://video.sky.it | html
- non controllabile senza parametri: https://video.sky.it/api/v1 (HTTP 404)

### vvvvid
Sito: https://www.vvvvid.it
- indirizzo scritto nel canale: https://www.vvvvid.it
- OK: https://www.vvvvid.it/vvvvid/ondemand/anime/ | html
- OK: https://www.vvvvid.it/vvvvid/ondemand/film/ | html
- OK: https://www.vvvvid.it/vvvvid/ondemand/series/ | html
- OK: https://www.vvvvid.it/vvvvid/ondemand/show/ | html
- OK: https://www.vvvvid.it/vvvvid/ondemand/kids/ | html
- OK: https://www.vvvvid.it/user/login | html
- OK: https://www.vvvvid.it/vvvvid/ondemand/ | html
- OK: https://www.vvvvid.it | html
- non controllabile senza parametri: https://or01.top-ix.org/videomg/_definst_/mp4: (HTTP 404)

## SENZA INDIRIZZO (6)

### animeuniverse
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

### guardaserieclick
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

### ilgeniodellostreaming
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

### italiaserie
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

### streamtime
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

### youtube_channel
Sito: n.d.
- canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file

## TEMPO SCADUTO (1)

### cineblog01
Sito: https://cb01official.uno
- il controllo di questo canale ha superato 600 secondi (sito lento o pagina enorme)

