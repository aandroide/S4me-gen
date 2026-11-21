# Convenzioni di codice (valide per tutto il repository)

Queste linee guida valgono per tutto il repository Stream4Me (`plugin.video.s4me`, fork italiano di Alfa, a sua volta erede di pelisalacarta; licenza GPL v3). Rispetta l'architettura e le convenzioni esistenti quando aggiungi o estendi funzionalità.

Il file è diviso in parti: regole generali (questa prima parte), poi canali, server video e codice condiviso (`core`). Prima di lavorare in una cartella leggi la parte generale e quella della cartella.

La wiki del progetto (https://github.com/Stream4me/addon/wiki) può essere in ritardo rispetto al codice: in caso di conflitto vale il codice. Le questioni ancora non chiarite sono elencate in fondo, in "Punti aperti".

## Uso in questa repo (S4me gen)

Queste regole sono quelle dell'addon S4Me. In questa repo valgono per ogni canale o server che il generatore scrive o ripara: il codice prodotto deve rispettarle, in particolare i decoratori `support.menu` e `support.scrape`, TMDB con titolo e anno originali, il controllo dei titoli TMDB sbagliati, la videoteca e la verifica fino al video.

+ La verifica automatica dei canali sta in `strumenti/controlla_framework.py`, con le regole in `strumenti/REGOLE_FRAMEWORK.md`. Se una regola di questo file non è controllata lì, va aggiunta.
+ I canali corretti stanno in `riparazioni/`, quelli generati in `archivio/canali/`. `canali_base/` si aggiorna da sola ogni giorno e non va modificata a mano.
+ Questa repo non scrive mai in stream4me/addon: le correzioni pronte si consegnano come file.

## Approvazione preventiva

***Non modificare nessun file di implementazione finché l'approccio non è stato approvato esplicitamente.*** Vale per ogni modifica, escluso per il fix di un singolo canale o server. Per i casi semplici la proposta può essere di poche righe, ma l'approvazione serve comunque.

+ Fino al via libera puoi solo leggere il codice ed eseguire controlli che non modificano file.
+ Anche questi richiedono approvazione prima di essere eseguiti: creare o eliminare file, spostare o rinominare moduli, modificare `channels.json`, `addon.xml` o i file `strings.po`, eseguire `tests/run.sh` (installa pacchetti con `pip` e cancella file in `tests/home`).
+ La proposta deve indicare: i file e le funzioni da cambiare, la responsabilità di ciascuno, i punti di estensione usati e un'implementazione esistente che mostri lo stesso schema. Se l'approccio tocca codice condiviso, spiega l'effetto sui consumatori.
+ Prima di proporre analizza il flusso dei dati: sito, regex, Item, TMDB, findvideos, server.
+ Solleva presto le questioni architetturali, con un'opzione raccomandata e le alternative significative.
+ Se durante il lavoro emerge che serve cambiare il livello proprietario, l'astrazione condivisa o lo schema concordato, fermati, spiega la revisione e ottieni una nuova approvazione prima di procedere.

## Regola d'oro

Ogni canale, resolver o funzione nuova si scrive nello stile del framework. Se esiste un decoratore, una funzione di `support` o un helper del framework per fare una cosa, usa quello. Prima di scrivere codice guarda sempre un canale o un server funzionante simile (un canale vicino non è per questo un buon riferimento: deve seguire queste convenzioni).

*Nota:* costruire menu o liste a mano è ammesso quando il contenuto è dinamico o non è nell'HTML. I dettagli sono nella parte Canali.

## Contesto del progetto

+ Stream4Me è un addon Kodi di terze parti che estrae da siti web le informazioni richieste (film, serie, episodi, link ai server video) con regole basate sulla struttura dei siti. I siti cambiano spesso: la manutenzione di canali e server è la parte più frequente del lavoro.
+ Id addon: `plugin.video.s4me`. `addon.xml` dichiara il debugger web pdb (`script.module.web-pdb`) e, come opzionali, i metadata scraper TMDb di Kodi. Extension point: plugin video (`default.py`), servizio (`service.py`, avvio a `login|startup`), menu contestuale (`contextmenu.py`).
+ Il repository non ospita né distribuisce contenuti: contiene solo codice che interroga siti di terzi. **Non aggiungere mai contenuti protetti, link diretti a file, chiavi o credenziali.**
+ Due rami: `master` è la beta, dove si sviluppano e si testano nuove funzionalità e fix; `stable` riceve ogni cambiamento già testato e verificato.

## Aggiornamenti e distribuzione

S4Me non usa il repository Kodi: ha un updater proprio (`platformcode/updater.py`), pensato per far arrivare subito agli utenti le piccole correzioni ai siti. **Fare push su un ramo equivale a pubblicare un aggiornamento.**

+ All'avvio di Kodi, e periodicamente (impostazione `addon_update_timer`, ore), l'updater chiede a GitHub l'ultimo commit, scarica le patch dei commit mancanti e le applica ai singoli file. Il commit corrente è tenuto in `last_commit.txt` (non versionato, è in `.gitignore`).
+ Senza `last_commit.txt` (installazione diretta, senza installer) l'addon calcola l'hash di sé stesso (`lib/githash.py`) per capire a che commit si trova; se non ci riesce scarica lo zip da GitHub.
+ L'updater è disattivato in dev mode.

***Non modificare `platformcode/updater.py`, `lib/githash.py` e la gestione di `last_commit.txt` senza accordo esplicito:*** un errore lì raggiunge tutti gli utenti al primo avvio di Kodi.

## Come funziona l'addon

+ Kodi chiama l'addon a ogni selezione di un elemento. Ogni elemento ha un URL `plugin://plugin.video.s4me/?<parametri>`: l'addon esegue l'azione richiesta, mostra gli elementi risultanti e termina. `default.py` è l'unico entry point.
+ Gli elementi sono oggetti `Item` (`core/item.py`), che rappresentano i `ListItem` di Kodi. Per passare i parametri l'`Item` viene convertito in JSON e poi in base64 e ricostruito alla selezione.
+ **Qualsiasi attributo aggiuntivo assegnato a un `Item` deve essere serializzabile in JSON** (stringhe, numeri, liste, dizionari). Non mettere oggetti Python arbitrari negli `Item`.
+ I parametri `channel` e `action` decidono cosa eseguire: `channel` è il modulo (in `channels/` o `specials/`), `action` è la funzione da chiamare. Lo smistamento è fatto da `platformcode/launcher.py`, che passa alla funzione anche l'`Item`.
+ Catena tipica: `mainlist` (menu), poi `peliculas`, `genres`, `episodios` (liste), poi `findvideos` (elenco dei server), poi azione `play` (risoluzione del link nel modulo del server).

## Mappa delle responsabilità

I percorsi sono relativi alla radice del repository. Usa la mappa per proporre dove deve stare una modifica; una funzionalità può richiedere interventi coordinati in più livelli, ciascuno con la propria responsabilità.

+ `default.py`: entry point. Nessuna logica di business.
+ `platformcode/launcher.py`: legge l'`Item` dall'URL e lancia la funzione indicata da `channel` e `action`.
+ `platformcode/`: tutto ciò che interagisce con Kodi: `config.py` (impostazioni, URL dei canali, stringhe localizzate, dev mode), `logger.py`, `platformtools.py` (dialoghi, liste, viste, riproduzione), `updater.py`, `autorenumber.py`, videoteca (`xbmc_videolibrary.py`). Non metterci logica di scraping.
+ `core/`: funzioni base di tutti gli scraper (vedi la parte Codice condiviso).
+ `channels/`: scraper dei canali (vedi la parte Canali).
+ `channels.json`: URL dei canali, in `direct` (indirizzo finale) e `findhost` (pagina che pubblica il dominio aggiornato).
+ `default_channel_settings.json`: impostazioni predefinite dei canali (ricerca globale, novità, controllo link, rinumerazione).
+ `servers/`: scraper dei server video (vedi la parte Server video). Sottocartelle `debriders/` e `decrypters/`.
+ `specials/`: sezioni né canale né server: ricerca (`search.py`, `globalsearch.py`), `news.py`, `videolibrary.py`, `downloads.py`, `favorites.py`, `community.py`, `setting.py`, `help.py`.
+ `channelselector.py`: menu iniziale e filtro dei canali per tipologia.
+ `service.py`: servizio in background: aggiornamento dell'addon (disattivato in dev mode), videoteca, pianificazioni.
+ `contextmenu.py`: voce di menu contestuale per elementi della libreria nativa di Kodi.
+ `lib/`: librerie esterne (in `PYTHONPATH`). Non modificarle salvo necessità. Qui c'è anche `cloudscraper` (fork venomous).
+ `resources/`: risorse Kodi: `language/` (`strings.po` it_IT e en_GB), `settings/`, `skins/`, `media/`, `settings.xml`.
+ `tools/`: script esterni all'addon, usati dai workflow (`updateDomains.py`).
+ `tests/`: suite generica di test degli scraper (`run.sh`, `test_generic.py`).
+ `.github/`: template di issue (`canale-non-funzionante`, `server-non-funzionante`, `test-canale`) e workflow.
+ `addon.xml`: metadati, dipendenze ed extension point. Modificalo solo con accordo esplicito.

Principi:

+ Distingui sempre: pagina web, dati estratti dal canale, `Item`, link del server, URL riproducibile. Sono responsabilità separate.
+ Rete, parsing e metadati stanno in `core/`; il codice che parla con Kodi sta in `platformcode/`. I canali non reimplementano ciò che `core/` e `support` offrono già.
+ Preferisci i punti di estensione già previsti. Non inserire logica di una funzionalità in codice condiviso solo perché è raggiungibile dal chiamante.

## Stile del codice

+ Il codice di base è scritto per Python 2 e Python 3 (flag `PY3`, `six`, `concurrent_py2`, `future`). **Nei moduli di `core/`, `platformcode/`, `specials/` non introdurre sintassi solo Python 3** (f-string, annotazioni di tipo, `nonlocal`, ecc.) e usa gli stessi accorgimenti dei file vicini. I pochi file che già usano f-string (`altadefinizione01`, `animesaturn`, `mediasetplay`, `doodstream`, `vidhide`) non sono un riferimento.
+ **Mai emoji o emoticon in qualunque file Kodi:** `settings.xml`, etichette, stringhe dell'interfaccia, log visibili all'utente.
+ Usa import espliciti e coerenti con il modulo in cui lavori; niente `from x import *` in codice nuovo; rimuovi gli import inutilizzati nelle righe che tocchi.
+ Una funzionalità distinta va in un modulo dal nome appropriato, nella cartella corretta (`channels/`, `servers/`, `specials/`, `core/`).
+ Quando sposti o rinomini un modulo aggiorna import, `channels.json`, il `.json` del modulo, `default_channel_settings.json` e le chiamate per nome stringa (`channel` e `action` negli `Item`). Cerca con grep il vecchio nome prima di dichiarare concluso il lavoro.
+ Riusa `support`, `scrapertools`, `httptools` e le utilità di `core/` invece di duplicarle; cerca prima se esiste già un helper. Preferisci piccole varianti (parametri, hook) alla copia di codice quasi identico tra canali.
+ Funzioni semplici e con un solo scopo; evita funzioni tuttofare e annidamenti profondi; preferisci strutture piatte e comprehension quando migliorano la leggibilità.
+ Stile EAFP: lascia emergere gli errori inattesi invece di mascherarli con guardie o `except` generici. Le eccezioni attese dalla rete (timeout, pagina cambiata) vanno gestite in modo esplicito e loggate. Nelle funzioni `search` e `newest` dei canali è invece prassi catturare l'eccezione, loggarla e restituire `[]`, per non interrompere la ricerca globale e le novità.
+ Non lasciare codice commentato, stampe di debug o chiamate alle funzioni di debug (`support.dbg()`, `regexDbg`, `debug=True`, `debugBlock=True`).

## Log, impostazioni e localizzazione

+ Usa `from platformcode import logger, config`: `logger.info` (sempre), `logger.debug` (solo con il debug attivo), `logger.error`; nei canali `support.info(...)` è lo stesso di `logger.info`. Non usare `print`. Non loggare dati personali: l'utente allega il log alle segnalazioni.
+ Impostazioni: `config.get_setting(name, channel="", server="", default=None)` e `config.set_setting(...)`. Non chiamare direttamente le API di Kodi per le impostazioni.
+ Le stringhe visibili all'utente vanno in `resources/language/resource.language.it_it/strings.po` e in `resource.language.en_gb/strings.po`, con lo stesso `msgctxt "#ID"` in entrambi, e si leggono con `config.get_localized_string(ID)`. Nei `.json` si richiamano con `"@ID"`. Prima di scegliere un ID verifica con grep che sia libero in entrambi i file. L'interfaccia è in italiano.
+ La voce di menu contestuale in `addon.xml` usa la stringa `90001`.

## Dev mode e debug

+ La dev mode si attiva se nella cartella dell'addon esiste `.git` (`config.dev_mode()`): abilita `support.dbg()` e `support.regexDbg()`, disattiva l'updater e mostra il menu contestuale `itemInfo` con l'`Item` in JSON. *Attenzione:* una copia senza `.git` (per esempio da zip) non attiva la dev mode e, se installata in Kodi, può essere sovrascritta dall'updater.
+ `support.dbg()` attiva web pdb e apre il browser. `support.regexDbg(item, patron, headers, data='')` apre Regex101 con regex e pagina già inserite; è lo strumento usato da `scrape` con `debug=True` (per `patron`) e `debugBlock=True` (per `patronBlock`). Preferiscilo a stampare la pagina nei log. Non lasciare queste chiamate nel codice consegnato.

## Licenza e crediti

+ Il progetto è GPL v3, come Alfa. Il codice riutilizzato da altri addon va citato: commento nel file con la fonte o, meglio, cherry pick che preservi lo storico.
+ Il codice riutilizzato deve avere una licenza compatibile con GPL v3; non copiare da progetti con licenza incompatibile o senza licenza.

## Verifica (regole generali)

Le verifiche specifiche per canali, server e codice condiviso stanno nelle rispettive parti.

+ Prima di dichiarare completato il lavoro rivedi il diff rispetto all'approccio approvato e alla mappa delle responsabilità: ogni modifica deve stare nel livello proprietario e usare i punti di estensione previsti.
+ Controlla import, `channels.json`, `.json` del canale o server, `default_channel_settings.json`, riferimenti per nome stringa, ID delle stringhe in entrambi i `.po`, coerenza tra `.json` e `.py` e compatibilità Python 2 e 3.
+ Controlla la sintassi dei moduli toccati (compilazione in memoria se la scrittura del bytecode non è disponibile) e whitespace e line ending.
+ Per le modifiche a codice condiviso verifica l'effetto su più canali e server che lo usano, anche non coinvolti nella richiesta.
+ Mantieni il comportamento esistente salvo che la richiesta preveda di cambiarlo.
+ **Nel report finale indica quali controlli hai eseguito e distingui i controlli isolati (regex, parsing, script) dalle prove effettive in Kodi.** Cosa non è stato provato su Kodi va dichiarato.
+ Non aggiungere test o file di prova al repository senza richiesta esplicita: la suite è generica e copre già ogni canale e server registrato.
+ Le prove di rete si fanno con IP italiano, in locale: non servono proxy a pagamento.

## Canali (channels/)

Regole per creare e modificare i canali. Valgono insieme alle regole generali della prima parte.

### Regola d'oro

Prima di scrivere un canale guarda sempre:

+ lo scheletro `0example.py.txt` e `0example.json.txt`;
+ i canali funzionanti simili a quello che devi creare o correggere;
+ la wiki dei decoratori `support.menu` e `support.scrape`.

Il caso normale è `mainlist` con `@support.menu` e liste ed episodi con `@support.scrape`.

Costruire menu o liste a mano (`itemlist.append(item.clone(...))` o `Item(...)`) è però ammesso, e diversi canali lo fanno, quando il contenuto è dinamico o non è nell'HTML: risposte API o JSON (accuradio costruisce la mainlist a mano dall'API), dirette e replay (la7, raiplay, mediasetplay, plutotv), stagioni e programmi (discoveryplus, vvvvid), elenchi con filtri. In quei casi usa comunque `support.typo`, `support.thumb` e `support.channel_config` come fanno gli altri canali, e prendi a modello un canale esistente dello stesso tipo.

*Nota:* se il sito ha HTML statico e un menu fisso, basta il decoratore: non scrivere parser o menu a mano.

### File e registrazione

+ Un canale è `channels/<id>.py` più `channels/<id>.json`, più la voce in `channels.json`. Per partire copia `0example.py.txt` e `0example.json.txt` togliendo il suffisso `.txt`. **Dal `.json` va cancellato il blocco di promemoria iniziale fino a "Cancellare fino a qui": se resta, il canale non è visibile.** Rimuovi dal `.py` i commenti e il codice dello scheletro che non servono (lo scheletro contiene segnaposto che non sono Python valido).
+ Il `.json` contiene: `id` (uguale al nome del file), `name`, `active`, `language` (`ita`, `sub-ita`, `eng`), `thumbnail`, `banner`, `categories` (`movie`, `tvshow`, `anime`, `vos`, `documentary`), `settings` (anche vuoto: `[]`) e, se serve, `not_active` (per esempio `["include_in_newest"]` per canali senza novità), `renumber`, `tiny`. Le voci predefinite di impostazioni stanno in `default_channel_settings.json`: nel `.json` del canale lascia solo ciò che devi sovrascrivere.
+ L'icona del canale viene scaricata da raw.githubusercontent.com/Stream4me/media/master/resources/thumb/<nome>.png: se manca, nel log compare un 404.
+ L'URL del sito sta in `channels.json`, non nel codice: `direct` per l'indirizzo finale, `findhost` per i siti che cambiano dominio. Nel canale: `host = config.get_channel_url()`; con `findhost`, definisci `def findhost(url)` che restituisce il dominio corretto e usa `host = config.get_channel_url(findhost)`. Il decoratore `scrape` richiama `findhost` da solo se la pagina non restituisce risultati.
+ Il flag `active` del `.json` decide se il canale è disponibile: **un canale nuovo parte da `false` finché non è testato.**
+ I domini in `channels.json` (`direct`) sono aggiornati ogni giorno da un workflow automatico (`tools/updateDomains.py`). Non modificare a mano i domini senza motivo e aspettati conflitti su questo file. Il workflow elimina la voce di un canale il cui `.json` non esiste più.
+ Intestazione del `.py`: commenti con crediti, aggiornamenti e note per i beta tester (le voci Aggiungi alla Videoteca e Scarica non compaiono nella ricerca globale).

### Funzioni di un canale

+ Ordine: `mainlist` (con `@support.menu`), `peliculas`, `episodios`, `genres` (con `@support.scrape`, `genres` solo se il sito ha menu per genere, anno o lettera), poi `search(item, text)`, `newest(categoria)`, `findvideos(item)` che restituisce `support.server(item, headers=headers)`.
+ `search(item, text)`: costruisce l'URL di ricerca e chiama la funzione di scraping; imposta `item.url` e `item.contentType` (obbligatorio per la ricerca globale se il canale non è solo film). Cattura l'eccezione, la logga e restituisce `[]`, per non bloccare la ricerca globale.
+ `newest(categoria)`: solo se il sito ha una pagina di novità; la categoria è `peliculas`; toglie l'ultimo item se la sua action è `peliculas` (pagina successiva).
+ `check(item)`: solo se il sito non distingue film e serie nei risultati.
+ Il modulo deve definire `host` (letto da `support.menu`) e, se serve, `headers` (letto da `support.scrape` quando non passi `headers` tra le variabili).
+ Un canale nuovo deve essere completo e funzionante: menu, liste, ricerca, episodi, aggiunta in videoteca. L'autoplay non è più collegato nei canali: è commentato in `core/support.py`.

### support.menu

+ Si applica a `mainlist`. Legge dalle variabili locali: `film`, `tvshow`, `anime` (menu di primo livello con sottomenu), `top` (solo voci di primo livello, senza url iniziale), `search`, `host` (sovrascrive l'host del menu) e qualsiasi altra variabile, che diventa un menu extra in fondo (per esempio `menu = [...]`, `generi = [...]`).
+ Struttura: lista in cui il primo valore è l'URL relativo (il dominio è `host`; si omette se vuoto) e gli altri sono tuple `(titolo, [url, action, args, contentType, folder])`. Le voci dopo `url` sono facoltative. Gli item ereditano `contentType` dal sottomenu.
+ Nei titoli puoi usare il markup di `typo` (`{submenu}`, `{bold}`, `{italic bold}`, `{bullet bold}`). La thumbnail si sceglie dalle parole del titolo (tabella in `support.thumb`: popolari, alfabetico, novita, top, generi, anno, lettera, film, serie): parole fuori tabella danno un'icona generica.
+ `search=''` crea un'unica voce di ricerca; se manca, viene creata una voce "Cerca ..." per ogni menu di primo livello.
+ **Termina sempre con `return locals()`.**

### support.scrape

+ Si applica alle funzioni di scraping. **Termina sempre con `return locals()`.** Il decoratore normalizza la pagina (`html_uniform`: a capo in spazio, apici singoli in doppi, niente spazi tra i tag): scrivi le regex sul testo normalizzato, non sul sorgente grezzo.
+ Variabili lette: `patron` (regex con soli named group tra `url`, `title`, `title2`, `season`, `episode`, `thumb`, `quality`, `year`, `plot`, `duration`, `genere`, `rating`, `type`, `lang`, `other`, `size`, `seed`), `patronBlock` (gruppi `block`, `season`, `lang`, `quality`), `patronNext` (un solo gruppo), `patronMenu` (come `patron`, senza TMDB, per sottomenu dinamici), `action` (se omessa: `episodios` per le serie nelle liste, altrimenti `findvideos`), `blacklist`, `data`, `headers` (lista di liste, per esempio `[['Referer', host]]`), `flags`, `flagsBlock`, `debug`, `debugBlock`, `anime` (rinumerazione per la videoteca), `addVideolibrary`, `search`, `typeActionDict`, `typeContentDict`, `pagination` (se presente e vuota: 20 risultati per pagina), `sceneTitle` (usa `guessit`), `deflang`, `disabletmdb`, `group`, `downloadEnabled`, `nextPageUrl`, `actLike`.
+ Hook opzionali, da definire come funzioni nel canale e passare tra le variabili: `itemHook(item)`, `itemlistHook(itemlist)`, `fullItemlistHook(itemlist)` (include anche Successivo e Aggiungi in videoteca).
+ `scrape` crea gli `Item` con `channel`, `action`, `contentType`, `title`, `fulltitle`, `show`, `quality`, `url`, `infoLabels` (anno e plot), `thumbnail`, `args`, `contentSerieName` (se non film), `contentTitle` (se film), poi chiama `tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)`, tranne per `mainlist`, `episodios` senza `episode_info` e `patronMenu`.
+ Usa `blacklist` per escludere gli articoli di servizio del sito; non filtrarli a mano.
+ Helper correlati: `support.match(url, patron=...)`, `support.nextPage(...)`, `support.pagination(...)`, `support.typo(...)` per la formattazione dei titoli (invece di scrivere a mano `[COLOR]` o `[B]`), `support.thumb(...)`.
+ **Non estendere i decoratori con casi specifici di un solo sito.**

### Fonti video: support.server

+ Firma attuale: `support.server(item, data='', itemlist=[], headers='', CheckLinks=True, Download=True, patronTag=None, Videolibrary=True, Sorted=True, referer=True)`. `data` e `itemlist` possono essere usati insieme; se mancano entrambi la pagina viene scaricata. Riconosce i server con `servertools.find_video_items`, usando i pattern dei `.json` dei server, e tenta l'unshorten dei link corti.
+ Un link che nessun server riconosce viene scartato; in modalità test solleva un'eccezione (`Server missing: <url>`): per supportare un nuovo host aggiungi un pattern nel `.json` del server (vedi la parte Server video).
+ Non disabilitare `CheckLinks`, `Download`, `Videolibrary` senza motivo. Per gli streaming protetti, i cui link non si possono salvare né scaricare, `Download=False` e `Videolibrary=False` sono giustificati.
+ Per i siti che usano hdpass: `support.hdpass_get_servers(item)`.
+ Item riproducibile direttamente (canale JSON senza regex): `server='directo'`, `manifest='mpd'` o `'hls'`, `drm='com.widevine.alpha'`, `license='url|header|R{SSM}|'`, `no_return=True`. `platformtools.play_video` gestisce il DRM solo nel ramo mpd (nel ramo hls serve la patch per `license_type` e `license_key`).

### TMDB nei canali

+ `tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)` fa la ricerca in parallelo ed è attiva solo se l'opzione TMDB è attiva; per gli episodi il framework la chiama solo se `config.get_setting('episode_info')`.
+ **Passa a TMDB titolo e anno originali del sito, non quelli già riscritti.**
+ Il tipo di ricerca dipende da `contentType`: `movie` cerca film, `undefined` fa ricerca multi, il resto cerca serie. Per i film conta `infoLabels` title, per le serie `tvshowtitle`, l'anno viene da `infoLabels` year. Per gli episodi servono `tvshowtitle`, `season`, `episode`.
+ Ricerca: prima per `tmdb_id`, `imdb_id`, `tvdb_id`; altrimenti per titolo con anno e, se non trova, ripete senza anno e prende il risultato più simile, anche sbagliato (per esempio Tarzan 1935 diventa Batman 1977). **Nei canali con titoli vecchi o rari controlla il risultato** (difflib, soglia 0.9, contenimento ammesso). Se non somiglia, azzera `infoLabels`, `thumbnail` e `fanart` (`item.fanart = ''`) e tieni i dati del sito.
+ TMDB scrive in `infoLabels`: plot, title, originaltitle, year, genre, rating, thumbnail, fanart, tmdb_id, imdb_id; `tvshowtitle` resta quello passato dal canale; imposta anche `item.thumbnail` e `item.fanart`.
+ La lingua dei metadati segue l'impostazione videoteca (`info_language`), non la lingua di Kodi; se TMDB non ha la trama nella lingua usa quella inglese.
+ Nei canali JSON senza regex costruisci gli Item nuovi come fa `support.scrape` (`channel`, `action`, `contentType`, `title`, `fulltitle`, `show`, `contentTitle` per i film o `contentSerieName` per le serie, `infoLabels` con `year`, `thumbnail`). Per le voci di titolo non usare `item.clone()` partendo dall'Item del menu, perché eredita attributi sbagliati; per le voci di menu, cartelle, dirette e stagioni `item.clone()` va bene ed è usato in molti canali.

### Viste e menu

+ Le liste di titoli usano sempre `action='peliculas'`, con `args` per distinguere la sezione (per esempio trending/movie/day) e `contentType` movie o tvshow. Un'azione personalizzata fa mostrare video generici e copertine doppie, perché `platformtools.getCurrentView` sceglie la vista dall'azione del menu padre.
+ Le cartelle (piattaforme, generi) possono avere azione propria, perché sono elenchi di voci di menu.
+ **Non toccare `folder`:** lascialo come in origine (per esempio non mettere `folder=False` negli episodi di AnimeUnity).
+ La paginazione nei canali JSON usa `item.clone` con `action='peliculas'`, un cursore in un attributo e l'etichetta `config.get_localized_string(30992)`.

### Videoteca

+ Le serie si aggiungono alla videoteca con `support.videolibrary(itemlist, item)`, da chiamare nella funzione che elenca gli episodi (o la lista della serie). Con `@support.scrape` si può usare la variabile `addVideolibrary` per controllare la voce Aggiungi alla Videoteca.
+ Le voci Aggiungi alla Videoteca e Scarica non compaiono nella ricerca globale: è normale e va annotato nell'intestazione del canale per i beta tester.
+ In `support.server` i parametri `Videolibrary` e `Download` abilitano le rispettive voci sui link.
+ Per la videoteca servono Item completi e stabili: `channel`, `action`, `contentType`, e `contentSerieName` per le serie o `contentTitle` per i film, con titolo e anno originali del sito. Per gli episodi servono anche `season` ed `episode`, titolo nel formato 1x01.
+ Le informazioni degli episodi da TMDB vengono richieste dal framework solo se è attiva l'impostazione `episode_info`.
+ Non cambiare `folder` degli Item di serie ed episodi: la videoteca ne dipende.
+ Se il canale usa autorenumber (`anime=True` e sezione `renumber` nel json), verifica la numerazione di stagioni ed episodi prima di aggiungere alla videoteca, per evitare duplicati o episodi fuori posto.
+ Verifica sempre il giro completo: aggiunta in videoteca, aggiornamento della serie e riproduzione di un episodio dalla videoteca.

### Cloudflare e rete

+ Per le richieste usa `core/httptools.py`. Per i siti con protezione usa `lib/cloudscraper` (fork venomous).
+ Per i bypass difficili esistono FlareSolverr e S4Me Assistant (app Android con server HTTP e WebView, con la challenge aperta sul telefono). Non reinventare un altro metodo: riusa quello già integrato.
+ Se i cookie scadono si rifà il bypass. Nelle ricerche multi thread vale il lock globale.

### Verifica di un canale

+ Leggi sempre il menu (il `@support.menu`, oppure la mainlist a mano nei canali che la costruiscono dall'API) e **prova ogni voce e ogni sezione, non solo i film.**
+ Verifica i casi significativi: menu e sottomenu, liste, paginazione, ricerca, serie con più stagioni, episodio singolo, aggiunta in videoteca, link morto o video rimosso, sito non raggiungibile, risposta inattesa.
+ **Verifica che da ogni sito si arrivi fino al video, non solo ai titoli.**
+ Le regex di `scrape` operano sulla pagina normalizzata: testale con `regexDbg`, poi rimuovi le chiamate di debug.
+ Con TMDB attivo controlla che non ci siano corrispondenze sbagliate.
+ I canali abilitati nel json dell'addon sono considerati funzionanti su Kodi anche se una prova isolata non li passa.
+ Test automatici: vedi la parte Server video per la descrizione di `tests/run.sh`. Chiedi approvazione prima di eseguirlo.

### Da non fare

+ Parser o menu scritti a mano quando basta un decoratore (HTML statico con menu fisso).
+ `item.clone()` dall'Item del menu per costruire le voci di titolo nei canali JSON.
+ Azioni personalizzate per le liste di titoli.
+ Modifica di `folder`.
+ Codice specifico di un sito nei decoratori di `support`.

## Server video (servers/)

Regole per creare e modificare i resolver dei server video. Valgono insieme alle regole generali della prima parte.

### Struttura

+ Un server è `servers/<id>.py` più `servers/<id>.json`. Sottocartelle: `debriders/` e `decrypters/`.
+ Il riconoscimento dei link avviene dai pattern del `.json`: `core/servertools.py` li usa tramite `servertools.find_video_items`, chiamato da `support.server` nei canali.

### File .json

+ Campi: `id`, `name`, `active`, `free`, `find_videos` e `settings` (di norma la voce `black_list`).
+ `find_videos` contiene `patterns` (lista di `{"pattern": regex, "url": modello con \\1}`) e `ignore_urls`.
+ **Un link che nessun server riconosce viene scartato** e, in modalità test, solleva l'eccezione `Server missing: <url>`. Per supportare un nuovo host aggiungi un pattern nel `.json` del server.

### File .py

+ `test_video_exists(page_url)` restituisce `(True, "")` oppure `(False, messaggio)`, con il messaggio da `config.get_localized_string(70449) % "NomeServer"`. **È obbligatoria:** il test generico fallisce se manca.
+ `get_video_url(page_url, premium=False, user="", password="", video_password="")` restituisce una lista di `[etichetta, url]`.
+ `get_filename(page_url)` è facoltativa.
+ I link restituiti da `get_video_url` possono portare header in coda: `url|Header=valore&Header2=valore`.
+ Usa `httptools.downloadpage`, `scrapertools`, `lib.jsunpack` e `support.get_jwplayer_mediaurl` come i server vicini, e il logger di `platformcode`.
+ Gestisci esplicitamente il caso "video rimosso o non disponibile".
+ ***Non memorizzare token, cookie o credenziali nel codice.***

### Riproduzione diretta e DRM

+ Un Item può essere riproducibile direttamente (canale JSON senza regex): `server='directo'`, `manifest='mpd'` o `'hls'`, `drm='com.widevine.alpha'`, `license='url|header|R{SSM}|'`, `no_return=True`.
+ *Nota:* `platformtools.play_video` gestisce il DRM solo nel ramo mpd. Nel ramo hls serve la patch per `license_type` e `license_key`.

### Verifica di un server

+ Controlla `test_video_exists` sia con un video valido sia con un video rimosso.
+ **Controlla che `get_video_url` restituisca un link riproducibile** e non solo una pagina.
+ Controlla i pattern del `.json` su più link reali dello stesso host.
+ Verifica la compatibilità Python 2 e 3 e che non ci siano emoji nelle stringhe.

### Test automatici

+ `tests/test_generic.py` esegue per ogni canale `mainlist`, `newest` e le voci di menu (con controllo di anno, pagina successiva e numero di risultati), e per ogni server trovato `test_video_exists` e `get_video_url`.
+ I link diretti devono rispondere con codice inferiore a 400 e `Content-Type` video, `mpegurl`, `octet-stream` o `dash+xml`.
+ Si lancia con `tests/run.sh [id_canale]` (Python 3, emulatore Kodi `sakee`, accesso alla rete; imposta `PYTHONPATH`, `KODI_HOME`, `KODI_INTERACTIVE=0` e, per un solo canale, `S4ME_TST_CH`) e scrive i report in `reports/`.
+ Alcuni canali e server sono esclusi da `chBlackList` e `srvBlacklist` nel file di test.
+ **Chiedi approvazione prima di eseguirlo:** installa pacchetti con `pip` e cancella file in `tests/home`.

## Codice condiviso (core/)

Regole per le modifiche alle funzioni base usate da tutti i canali e server. Valgono insieme alle regole generali della prima parte.

***Una modifica qui raggiunge tutti i canali e tutti i server.*** Fermati e chiedi approvazione prima di toccare questa cartella.

### Quando modificare core

+ Metti il comportamento specifico di un sito nel canale (o server) interessato. Modifica `core/`, `platformcode/`, `specials/` o i decoratori di `support` solo se il comportamento appartiene a tutti i consumatori.
+ Prima di proporre una modifica condivisa ispeziona chiamanti ed effetti su tutti i canali e server che la usano (quasi tutti i canali usano `support.menu` e `support.scrape`) e spiega perché appartiene all'astrazione condivisa.
+ **Non aggiungere rami specifici di un sito nel codice condiviso** per evitare di sistemare il canale.
+ Mantieni il contratto delle funzioni condivise: firma, tipo di ritorno, valori predefiniti e nomi delle variabili locali che i decoratori leggono con `return locals()`.
+ Preferisci piccole varianti (parametri, hook) alla copia di codice quasi identico.

### Compatibilità

+ Il codice è scritto per Python 2 e Python 3 (flag `PY3`, `six`, `concurrent_py2`, `future`). **Non introdurre sintassi solo Python 3** (f-string, annotazioni di tipo, `nonlocal`, ecc.) e usa gli stessi accorgimenti dei file vicini.
+ Mai emoji o emoticon in stringhe, etichette o log visibili all'utente.

### Moduli

+ `item.py`: la classe `Item`. Gli attributi extra devono essere serializzabili in JSON, perché l'Item viene convertito in JSON e poi in base64 nell'URL del plugin. Nel costruttore gli `infoLabels` passati vengono applicati per primi, poi le proprietà speciali (`contentTitle`, `contentSerieName`, `show`, `contentType`, `contentSeason`, `contentEpisodeNumber`, `plot`, `quality`, ecc.). Il `mediatype` viene dedotto: con `tvshowtitle` e `tvshow`, `season` o `episode` è serie; con solo `title` è film.
+ `support.py`: decoratori `menu` e `scrape`, `server`, `match`, `nextPage`, `pagination`, `typo`, `thumb`, `hdpass_get_servers`, `videolibrary`, `channel_config`, `dbg`, `regexDbg`, helper `dooplay_*`. Le regole d'uso dei decoratori stanno nella parte Canali.
+ `httptools.py`: tutte le richieste di rete. Usa `lib/cloudscraper` (fork venomous) per i siti protetti.
+ `tmdb.py` e `tvdb.py`: metadati. La ricerca TMDB parte da `tmdb_id`, `imdb_id`, `tvdb_id`; altrimenti per titolo con anno e, se non trova, senza anno, prendendo il risultato più simile anche se sbagliato. La lingua segue `info_language` della videoteca.
+ `servertools.py`: riconoscimento dei server dai pattern dei `.json` (vedi la parte Server video).
+ `scrapertools.py`, `channeltools.py`, `jsontools.py`, `videolibrarytools.py`, `downloader.py`, `autoplay.py`, `filtertools.py`.

### Contratto dei decoratori

+ `support.menu` e `support.scrape` leggono le variabili locali della funzione decorata tramite `return locals()`. **Non rinominare né rimuovere queste variabili.**
+ Il decoratore `scrape` normalizza la pagina (`html_uniform`) prima di applicare le regex dei canali: cambiare questa normalizzazione rompe le regex di tutti i canali.
+ `support.server` ha la firma `support.server(item, data='', itemlist=[], headers='', CheckLinks=True, Download=True, patronTag=None, Videolibrary=True, Sorted=True, referer=True)`: non cambiarla senza controllare tutti i chiamanti.
+ L'autoplay non è più collegato nei canali: è commentato in `support.py`.

### Verifica

+ Cerca con grep tutti i chiamanti della funzione che modifichi, in `channels/`, `servers/`, `specials/` e `platformcode/`.
+ Prova la modifica su più canali o server che la usano, anche non coinvolti nella richiesta.
+ Controlla la compatibilità Python 2 e 3.
+ ***Nel report finale dichiara quali canali e server hai controllato e quali no.***

# Regole finali per tutto il repository

### Consegna (regole generali)

+ **Il repository `stream4me/addon` non è di chi lavora qui: non fare mai push su S4Me.** Le modifiche all'addon si consegnano come file.
+ I file si consegnano diretti e singoli, in chat. Niente zip, salvo richiesta esplicita.
+ Il lavoro su strumenti collegati (per esempio il generatore di canali) avviene solo sulla repo per cui c'è autorizzazione.

### Da non fare

+ Emoji nel codice Kodi.
+ Modifiche a classi o funzioni condivise di `core` senza controllare tutti i canali che le usano.
+ Codice specifico di un sito nei decoratori o nel codice condiviso.
+ Dichiarare funzionante ciò che non è stato provato fino al video.

### Punti aperti

Da confermare; finché non sono chiariti, segui il comportamento del codice circostante.

+ Promozione da `master` a `stable`: la wiki dice che su `stable` va ogni cambiamento testato e verificato, ma non spiega chi decide né come avviene. Non spostare modifiche su `stable` senza richiesta esplicita.
+ Versioni supportate: `CONTRIBUTING.md` indica Kodi 17.x e 18.x (Python 2); i test girano su Python 3.9 e `addon.xml` non dichiara `xbmc.python`. La regola di compatibilità Python 2 e 3 sopra è quella prudente.
+ Autoplay: `CONTRIBUTING.md` richiede che i canali nuovi supportino l'autoplay, ma nel codice è disattivato.
