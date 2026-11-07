# -*- coding: utf-8 -*-
"""Controllo statico: un canale o un server S4Me segue il framework?

Le regole vengono dagli errori trovati davvero provando i canali su Kodi.
Ogni problema e una tupla (livello, codice, riga, messaggio):
  ERRORE   rompe qualcosa (blocchi del menu, titoli persi, chiamate di troppo)
  AVVISO   non rompe ma si discosta dagli altri canali, da controllare
Uso: controlla_file(percorso) oppure controlla_codice(testo, tipo).
"""
import ast
import re
import warnings

warnings.filterwarnings('ignore', category=SyntaxWarning)

ERRORE, AVVISO = 'ERRORE', 'AVVISO'

DECORATORI_SCRAPE = ('peliculas', 'episodios', 'genres', 'search_scrape')
RETE_DIRETTA = ('requests', 'urllib.request', 'urllib2', 'cloudscraper', 'http.client')


def _nome_chiamata(nodo):
    """Nome completo di una chiamata, per esempio support.tmdb.set_infoLabels_itemlist."""
    f = nodo.func if isinstance(nodo, ast.Call) else nodo
    parti = []
    while isinstance(f, ast.Attribute):
        parti.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parti.append(f.id)
    return '.'.join(reversed(parti))


def _decoratori(fn):
    out = []
    for d in fn.decorator_list:
        out.append(_nome_chiamata(d) if isinstance(d, (ast.Call, ast.Attribute)) else getattr(d, 'id', ''))
    return out


def _funzioni(albero):
    return {n.name: n for n in albero.body if isinstance(n, ast.FunctionDef)}


def _contiene(nodo, testo):
    return any(testo in (ast.get_source_segment(SORGENTE[0], n) or '') for n in ast.walk(nodo)
               if isinstance(n, (ast.If, ast.IfExp, ast.BoolOp)))


SORGENTE = ['']


def controlla_canale(testo):
    problemi = []
    try:
        albero = ast.parse(testo)
    except SyntaxError as e:
        return [(ERRORE, 'SINTASSI', e.lineno or 0, 'il file non si compila: %s' % e.msg)]
    SORGENTE[0] = testo
    funz = _funzioni(albero)

    def add(liv, cod, riga, msg):
        problemi.append((liv, cod, riga, msg))

    # F01 mainlist e le liste con i decoratori del framework
    ml = funz.get('mainlist')
    if ml is not None and 'support.menu' not in _decoratori(ml):
        add(AVVISO, 'F01', ml.lineno, 'mainlist senza @support.menu: il menu non avra icone e ordine standard')
    for nome in ('peliculas', 'episodios', 'genres'):
        fn = funz.get(nome)
        if fn is None:
            continue
        if 'support.scrape' not in _decoratori(fn):
            gira_rete = any(_nome_chiamata(n).startswith(('httptools.', 'support.match')) for n in ast.walk(fn)
                            if isinstance(n, ast.Call))
            usa_clone = nome == 'episodios' and '.clone(' in testo and bool(
                re.search(r"contentType\s*=\s*['\"]episode['\"]", testo))
            if gira_rete and not usa_clone:
                add(AVVISO, 'F02', fn.lineno,
                    '%s legge la pagina a mano invece di @support.scrape: va bene solo se la pagina non si presta '
                    'a una regex (JSON, dati incorporati); dillo nel commento' % nome)

    # F03 voci di menu 'undefined' e pagina successiva (cartella al posto del quadratino)
    pel = funz.get('peliculas')
    usa_undefined = bool(re.search(r"\[[^\]]*'peliculas'[^\]]*'undefined'\s*\]", testo))
    if usa_undefined and pel is not None:
        corpo = ast.get_source_segment(testo, pel) or ''
        if not re.search(r"contentType\s*==|contentType in|contentType\s*=", corpo):
            add(AVVISO, 'F03', pel.lineno,
                "il menu usa 'undefined' e peliculas non fissa item.contentType: il tasto Successivo e un clone "
                "dell'item e Kodi lo mostra come cartella. In peliculas: if item.contentType in ('undefined', ''): "
                "item.contentType = 'movie'")
    if usa_undefined and 'typeContentDict' not in testo and '(?P<type>' not in testo:
        add(AVVISO, 'F04', 1,
            "voci 'undefined' senza typeContentDict: i titoli che TMDB non trova restano 'undefined' e Kodi li "
            "mostra come cartelle. Aggiungi typeContentDict e il gruppo (?P<type>...) nel patron")

    # F05 info episodio TMDB: solo con episode_info e fuori da add_tvshow e get_newest
    for fn in funz.values():
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and _nome_chiamata(n).endswith('set_infoLabels_itemlist') and fn.name == 'episodios':
                blocco_if = None
                for padre in ast.walk(fn):
                    if isinstance(padre, ast.If) and any(c is n for c in ast.walk(padre)):
                        blocco_if = padre
                cond = (ast.get_source_segment(testo, blocco_if.test) or '') if blocco_if else ''
                if "episode_info" not in cond:
                    add(ERRORE, 'F05', n.lineno,
                        "set_infoLabels_itemlist negli episodi senza if config.get_setting('episode_info'): "
                        "chiama TMDB per ogni episodio anche se l'utente non lo vuole")
                elif 'stackCheck' not in cond:
                    add(AVVISO, 'F05', n.lineno,
                        "manca not support.stackCheck(['add_tvshow', 'get_newest']) accanto a episode_info: "
                        "aggiungendo in videoteca o cercando le novita parte una chiamata TMDB per episodio")

    # F06 il titolo TMDB dell'episodio va nell'etichetta
    ep = funz.get('episodios')
    if ep is not None and 'support.scrape' not in _decoratori(ep):
        corpo = ast.get_source_segment(testo, ep) or ''
        if 'set_infoLabels_itemlist' in corpo and not re.search(r"infoLabels(\.get\(|\[)['\"]title['\"]", corpo):
            add(AVVISO, 'F06', ep.lineno,
                "il core mette il titolo TMDB solo in infoLabels: negli episodi scritti a mano riscrivi it.title "
                "come '1x01 - Titolo' dopo set_infoLabels_itemlist")
    if ep is not None:
        corpo = ast.get_source_segment(testo, ep) or ''
        if 'check_trakt' not in corpo and 'support.scrape' not in _decoratori(ep):
            add(AVVISO, 'F07', ep.lineno, 'episodios scritta a mano senza support.check_trakt(itemlist)')
        if 'support.videolibrary' not in corpo and 'support.scrape' not in _decoratori(ep):
            add(AVVISO, 'F07', ep.lineno, 'episodios scritta a mano senza support.videolibrary(itemlist, item)')

    # F08 niente chiamate dirette a TMDB e niente rete fuori da httptools
    for i, riga in enumerate(testo.splitlines(), 1):
        if re.search(r'api\.themoviedb\.org', riga):
            add(ERRORE, 'F08', i, "richiesta diretta all'API di TMDB nel canale: usa support.tmdb o core.tmdb "
                                   "(cache, limite di richieste e nuovi tentativi gia gestiti)")
    for n in ast.walk(albero):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            nomi = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or '']
            for nome in nomi:
                if nome.split('.')[0] in ('requests', 'cloudscraper', 'urllib2') or nome == 'urllib.request':
                    add(AVVISO, 'F09', n.lineno, "importa %s: le pagine si scaricano con httptools, che gestisce "
                                                  "cookie, Cloudflare e timeout" % nome)
        if isinstance(n, ast.Call) and _nome_chiamata(n).endswith('Tmdb') and _nome_chiamata(n) not in ('tmdb.Tmdb', 'Tmdb'):
            pass
        if isinstance(n, ast.Call) and _nome_chiamata(n).split('.')[-1] == 'get_json':
            add(AVVISO, 'F08', n.lineno, 'Tmdb.get_json chiamata dal canale: meglio get_list_episodes o '
                                         'set_infoLabels_itemlist, che usano la stessa cache')

    # F10 thread e attese nel canale: Kodi aspetta i thread rimasti prima di far cliccare il menu
    for n in ast.walk(albero):
        if isinstance(n, ast.Call):
            nome = _nome_chiamata(n)
            if nome in ('threading.Thread', 'Thread', 'concurrent.futures.ThreadPoolExecutor', 'ThreadPoolExecutor'):
                add(AVVISO, 'F10', n.lineno, 'thread creato dal canale: se resta vivo dopo lo stop, Kodi blocca il '
                                              'menu. Usa le funzioni del core (support.scrape, tmdb) che gestiscono i thread')
            if nome in ('time.sleep', 'sleep'):
                add(AVVISO, 'F10', n.lineno, 'sleep nel canale: rallenta l apertura delle liste')

    # F11 non toccare folder
    for n in ast.walk(albero):
        if isinstance(n, ast.keyword) and n.arg == 'folder':
            add(AVVISO, 'F11', getattr(n, 'lineno', 0) or 0, 'folder passato a mano: lascialo come nel canale originale')
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and n.attr == 'folder':
            add(AVVISO, 'F11', n.lineno, 'item.folder assegnato a mano: lascialo come nel canale originale')

    # F12 findvideos e ricerca
    fv = funz.get('findvideos')
    if fv is not None:
        corpo = ast.get_source_segment(testo, fv) or ''
        if 'support.server' not in corpo and "server='directo'" not in corpo.replace('"', "'"):
            add(AVVISO, 'F12', fv.lineno, 'findvideos senza support.server: AutoPlay, controllo link e '
                                           'download non funzionano')
    se = funz.get('search')
    if se is not None and not any(isinstance(n, ast.Try) for n in ast.walk(se)):
        add(AVVISO, 'F12', se.lineno, 'search senza try/except che ritorna []: un errore blocca la ricerca globale')

    # F13 test di esistenza e altri controlli lunghi nei canali
    chiama_prova = any(isinstance(n, ast.Call) and (_nome_chiamata(n).split('.')[-1] == 'probe' or
                       _nome_chiamata(n).split('.')[-1] == 'episodes_api') for n in ast.walk(albero)) or \
        bool(re.search(r"getattr\([^)]*['\"](probe|episodes_api)['\"]", testo))
    if chiama_prova:
        add(AVVISO, 'F13', 1, 'il canale chiama funzioni di prova del server (probe, episodes_api): una richiesta '
                              'per stagione alla prima apertura puo sembrare traffico anomalo. Lascia che sia '
                              'test_video_exists a scartare i link mancanti, alla riproduzione')
    return problemi


def controlla_server(testo):
    problemi = []
    try:
        albero = ast.parse(testo)
    except SyntaxError as e:
        return [(ERRORE, 'SINTASSI', e.lineno or 0, 'il file non si compila: %s' % e.msg)]
    SORGENTE[0] = testo

    def add(liv, cod, riga, msg):
        problemi.append((liv, cod, riga, msg))

    scraper = [n for n in ast.walk(albero) if isinstance(n, ast.Call) and _nome_chiamata(n).endswith('create_scraper')]
    if scraper and not any('auto_refresh_on_403' in {k.arg for k in n.keywords} for n in scraper):
        add(ERRORE, 'S01', scraper[0].lineno,
            'cloudscraper.create_scraper senza auto_refresh_on_403=False: con il limite di 1 richiesta '
            'alla volta si blocca da solo su un 403 e il thread resta appeso (menu bloccato)')
    for fn_ in [x for x in ast.walk(albero) if isinstance(x, ast.FunctionDef)]:
        sorgente = ast.get_source_segment(testo, fn_) or ''
        for n in ast.walk(fn_):
            if isinstance(n, ast.Call) and _nome_chiamata(n) in ('threading.Thread', 'Thread', '_th.Thread'):
                if not any(k.arg == 'daemon' for k in n.keywords) and 'daemon' not in sorgente:
                    add(AVVISO, 'S02', n.lineno,
                        'thread senza daemon=True: un thread normale tiene vivo lo script di Kodi')

    fn = next((x for x in albero.body if isinstance(x, ast.FunctionDef) and x.name == 'test_video_exists'), None)
    if fn is not None:
        corpo = ast.get_source_segment(testo, fn) or ''
        impl = next((x for x in albero.body if isinstance(x, ast.FunctionDef) and x.name == '_test_video_exists_impl'), None)
        corpo_impl = (ast.get_source_segment(testo, impl) or '') if impl else corpo
        if 'join(' not in corpo and 'timeout' not in corpo_impl:
            add(ERRORE, 'S03', fn.lineno, 'test_video_exists senza tempo massimo: se il sito non risponde il '
                                           'menu resta bloccato')
        # S04: False solo con un 404 o 410 vero. Ogni verifica extra che fallisce per rete e un falso errore
        for m in re.finditer(r'return\s+False\b', corpo_impl):
            riga = corpo_impl[:m.start()].count('\n') + (impl.lineno if impl else fn.lineno)
            prima = corpo_impl[:m.start()]
            ultimo_if = prima.rfind('if ')
            contesto = prima[ultimo_if:] if ultimo_if >= 0 else prima
            if 'get_embed_page' in contesto or 'resolve' in contesto:
                add(ERRORE, 'S04', riga,
                    'test_video_exists dice che il video non esiste dopo una verifica di rete (get_embed_page, resolve): '
                    'se la rete dell utente blocca quella pagina scarta un server che funziona. '
                    'Ritorna False solo con 404 o 410 sia sulla richiesta leggera sia sulla pagina del player')
        if not re.search(r'return\s+True', corpo_impl):
            add(AVVISO, 'S04', fn.lineno, 'test_video_exists senza ripiego True: in ogni dubbio il video va provato')
    return problemi


def controlla_codice(testo, tipo='canale'):
    return controlla_server(testo) if tipo == 'server' else controlla_canale(testo)


def controlla_file(percorso, tipo=None):
    testo = open(percorso, encoding='utf-8').read()
    if tipo is None:
        tipo = 'server' if re.search(r'^def get_video_url\(', testo, re.M) else 'canale'
    return controlla_codice(testo, tipo)


def formatta(problemi, nome=''):
    righe = []
    for liv, cod, riga, msg in sorted(problemi, key=lambda p: (p[0] != ERRORE, p[2])):
        righe.append('%s %s%s riga %s: %s' % (liv, cod, (' ' + nome) if nome else '', riga, msg))
    return righe
