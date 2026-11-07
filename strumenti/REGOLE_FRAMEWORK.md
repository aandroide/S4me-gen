# Regole del framework S4Me per i canali e i server

Sono le regole che il tool controlla (`strumenti/controlla_framework.py`) e che il generatore applica a ogni canale che scrive. Nascono da errori trovati provando i canali su Kodi, non da teoria. Un ERRORE rompe qualcosa, un AVVISO si discosta dagli altri canali e va guardato.

## Come si controlla

    python3 strumenti/controlla_framework.py riparazioni/altadefinizione01.py riparazioni/server
    python3 strumenti/controlla_framework.py canali_base --solo-errori

Il generatore (`s4me_gen.py`) aggiunge nel rapporto del canale una sezione `FRAMEWORK`. L'Action "Controlla framework" lo esegue su `riparazioni/` a ogni modifica.

## Canali

| Codice | Regola | Perche |
|---|---|---|
| F01 | `mainlist` con `@support.menu` | icone, ordine e ricerca standard |
| F02 | `peliculas`, `genres`, `episodios` con `@support.scrape`. A mano solo se la pagina non si presta a una regex (JSON, dati incorporati), oppure episodi costruiti con `item.clone()` come StreamingCommunity e Filmpertutti | il decoratore gestisce TMDB, pagine successive, videoteca, thread |
| F03 | se il menu usa `'undefined'`, in `peliculas` fissare `item.contentType` (per esempio `movie`) | il tasto Successivo e un clone dell'item: con `undefined` Kodi lo disegna come cartella |
| F04 | con `'undefined'` serve `typeContentDict` e il gruppo `(?P<type>...)` nel patron | i titoli che TMDB non trova restano `undefined` e Kodi li mostra come cartelle, in elenco e in ricerca |
| F05 | info episodio TMDB solo dentro `if config.get_setting('episode_info') and not support.stackCheck(['add_tvshow', 'get_newest'])` | senza il controllo parte una chiamata TMDB per episodio anche quando l'utente non la vuole, e aggiungendo in videoteca |
| F06 | negli episodi scritti a mano, dopo `set_infoLabels_itemlist` riscrivere `it.title` come `1x01 - Titolo` | il core mette il titolo TMDB solo in `infoLabels`, l'etichetta resta `1x01` |
| F07 | episodi scritti a mano: `support.check_trakt(itemlist)` e `support.videolibrary(itemlist, item)` a fine elenco | Trakt e videoteca |
| F08 | nessuna richiesta a `api.themoviedb.org` e nessun `Tmdb.get_json` dal canale: usare `support.tmdb.set_infoLabels_itemlist` o `Tmdb(...).get_list_episodes()` | la cache, il limite di richieste e i nuovi tentativi sono nel core; chiamate dirette moltiplicano il traffico e causano errori TMDB |
| F09 | niente `requests`, `cloudscraper`, `urllib.request` nel canale: usare `httptools` | cookie, Cloudflare e timeout gia gestiti |
| F10 | niente thread ne `time.sleep` nel canale | Kodi aspetta i thread rimasti prima di far cliccare di nuovo il menu |
| F11 | non assegnare `folder` a mano | lasciarlo come nel canale originale |
| F12 | `findvideos` con `support.server`; `search` con `try/except` che ritorna `[]` | AutoPlay, controllo link, ricerca globale |
| F13 | il canale non chiama `probe` o `episodes_api` del server | una richiesta per stagione alla prima apertura puo sembrare traffico anomalo; gli episodi mancanti li scarta `test_video_exists` alla riproduzione |
| F14 | se il titolo e stato aggiunto da TMDB con un id di film per una serie (o il contrario), prendere l'id dalla pagina (`themoviedb.org/tv/<id>` per le serie) | la ricerca dell'elenco parte come film e puo trovare un film omonimo |

F14 non si controlla in automatico: si guarda leggendo il canale.

## Server (resolver)

| Codice | Regola | Perche |
|---|---|---|
| S01 | `cloudscraper.create_scraper(auto_refresh_on_403=False, max_concurrent_requests=16, min_request_interval=0)` | con le impostazioni predefinite un 403 mette in stallo la richiesta con se stessa e il thread resta appeso |
| S02 | thread con `daemon=True` | un thread normale tiene vivo lo script e Kodi blocca il menu |
| S03 | `test_video_exists` con tempo massimo (thread con `join`, o timeout sulle richieste) | se il sito non risponde il menu resta bloccato |
| S04 | `test_video_exists` ritorna `False` solo con 404 o 410 veri, anche sulla pagina del player. Mai dopo una verifica di rete extra (`get_embed_page`, `resolve`); in ogni dubbio `True` | la rete dell'utente puo bloccare quella pagina e il server che funziona viene scartato |

## Come si arriva a queste regole

Ogni regola ha un caso vero dietro: altadefinizione01 e i server vidxgo e vixsrc, provati su Kodi per Windows e Android. Quando se ne trova un'altra si aggiunge in `strumenti/framework.py`, si scrive qui il motivo e si aggiunge un caso in `strumenti/test/test_framework.py`.

F14 (errore): in episodios non impostare server sugli episodi. Con l'azione check il launcher scambia la lista per link e avvia la riproduzione del primo episodio invece di aprire il menu. Il server si imposta in findvideos.
