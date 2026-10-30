# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per La7
# ------------------------------------------------------------

import sys
from core import support, httptools
from platformcode import logger
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
import html
import json
import ssl


# lettore dei dati incorporati nella pagina (aggiunto dal controllo dei canali)
import html as _html
import base64
import json
import re

TITOLO = ('titolo', 'title', 'name', 'nome', 'headline', 'label', 'canale')
LINK = ('pathname', 'url', 'href', 'link', 'permalink', 'path', 'streamingUrl')
IMMAGINE = ('imageUrl', 'image_url', 'thumbnailUrl', 'immagine_scena', 'immagine', 'image', 'img', 'thumbnail', 'thumb', 'poster', 'cover', 'immagine_programma',
            'immagine_cover', 'picture', 'scenaImage', 'coverImage', 'programmaImage')
TRAMA = ('excerpt', 'teaser', 'sinossi', 'plot', 'description', 'descrizione', 'abstract', 'occhiello', 'synopsis', 'summary', 'datePublished')
PROGRAMMA = ('propertyName', 'programma', 'program', 'show', 'serie', 'series')
ORARIO = ('ora', 'orario', 'time', 'start')
GRUPPO = ('data', 'date', 'day', 'giorno', 'stagione', 'season', 'nome', 'title', 'titolo', 'label')


# ---------------------------------------------------------------------------
# Parte copiata nel canale
# ---------------------------------------------------------------------------

def _testi(h):
    """Testi con dati JSON dentro la pagina: payload Next.js, __NEXT_DATA__, JSON-LD, script application/json."""
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[\d+,\s*("(?:[^"\\]|\\.)*")\s*\]\)', h):
        try:
            out.append(json.loads(m.group(1)))
        except Exception:
            pass
    for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', h, re.S):
        out.append(m.group(1))
    for m in re.finditer(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S):
        out.append(m.group(1))
    return out


def _oggetti(testo):
    """Tutti gli array e oggetti JSON che iniziano con [{ oppure {" dentro il testo (senza rileggere quelli annidati)."""
    dec = json.JSONDecoder()
    i, n, trovati = 0, len(testo), []
    rx = re.compile(r'\[\s*\{|\{\s*"')
    while i < n:
        m = rx.search(testo, i)
        if not m:
            break
        try:
            ob, fine = dec.raw_decode(testo, m.start())
            trovati.append(ob)
            i = fine
        except Exception:
            i = m.start() + 1
    return trovati


def _scegli(d, chiavi):
    for k in chiavi:
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get('url') or v.get('contentUrl') or v.get('src')
        if isinstance(v, list) and v:
            v = v[0].get('url') if isinstance(v[0], dict) else v[0]
        if isinstance(v, str) and v.strip():
            return k, v.strip()
    return None, ''


def _liste(ob, uscita, profondita=0):
    """Liste di almeno 3 dizionari, anche annidate."""
    if profondita > 12:
        return
    if isinstance(ob, list):
        dizionari = [x for x in ob if isinstance(x, dict)]
        navigazione = sum(1 for x in dizionari if str(x.get('@type', '')) in ('SiteNavigationElement', 'WPHeader', 'WPFooter'))
        if len(dizionari) >= 3 and navigazione < 0.5 * len(dizionari):
            uscita.append(dizionari)
        for x in ob:
            _liste(x, uscita, profondita + 1)
    elif isinstance(ob, dict):
        for v in ob.values():
            if isinstance(v, (list, dict)):
                _liste(v, uscita, profondita + 1)


def _spacchetta(d):
    """JSON-LD: ListItem con item dentro, o record con workFeatured."""
    if isinstance(d.get('item'), dict):
        return dict(d['item'])
    return d


def _etichetta(p, percorso):
    """Valore scalare di un campo del gruppo; il percorso puo essere annidato, per esempio '@attributes.data'."""
    v = p
    for k in percorso.split('.'):
        v = v.get(k) if isinstance(v, dict) else None
    return v if isinstance(v, (str, int)) else None


def _record(d, firma):
    d = _spacchetta(d)
    kt = firma['titolo']
    kl = firma['link']
    t = d.get(kt)
    u = d.get(kl)
    if isinstance(u, dict):
        u = u.get('url') or u.get('@id')
    if not isinstance(t, str) or not isinstance(u, str) or not t.strip() or not u.strip():
        return None
    r = {'titolo': _html.unescape(t).strip(), 'url': u.strip()}
    for nome in ('immagine', 'trama', 'orario'):
        k = firma.get(nome)
        r[nome] = _scegli(d, (k,))[1] if k else ''
    r['programma'] = _scegli(d, PROGRAMMA)[1]
    if re.match(r'\d{4}-\d{2}-\d{2}T', r['trama']):
        r['trama'] = r['trama'][:10]
    if r['trama']:
        r['trama'] = _html.unescape(re.sub(r'<[^>]+>', '', r['trama'])).replace('\xa0', ' ').strip()
    return r


def _trova(h, firma):
    """Applica la firma (nomi dei campi) alla pagina e restituisce [(etichetta_gruppo, [record])]. Senza gruppo: etichetta ''."""
    migliore = []
    for testo in _testi(h):
        for ob in _oggetti(testo):
            liste = []
            _liste(ob, liste)
            for lista in liste:
                if firma.get('gruppo'):
                    gruppi = []
                    for p in lista:
                        figli = p.get(firma['figli'])
                        if isinstance(figli, list):
                            rec = [x for x in (_record(f, firma) for f in figli if isinstance(f, dict)) if x]
                            if rec:
                                gruppi.append((str(_etichetta(p, firma['gruppo'])), rec))
                    if sum(len(r) for _, r in gruppi) > sum(len(r) for _, r in migliore):
                        migliore = gruppi
                else:
                    rec = [x for x in (_record(d, firma) for d in lista) if x]
                    if firma.get('immagine') and sum(1 for x in rec if x['immagine']) < 0.5 * len(rec):
                        continue  # stessi nomi dei campi ma senza immagini: menu, piede della pagina, link
                    if len(rec) > sum(len(r) for _, r in migliore):
                        migliore = [('', rec)]
    return migliore


def _trova_tutte(h, firma):
    """Come _trova, ma tutte le liste che hanno quei campi, non solo la piu grande (carosello diviso in piu liste)."""
    out = []
    for testo in _testi(h):
        for ob in _oggetti(testo):
            liste = []
            _liste(ob, liste)
            for lista in liste:
                rec = [x for x in (_record(d, firma) for d in lista) if x]
                if len(rec) >= 3 and (not firma.get('immagine') or sum(1 for x in rec if x['immagine']) >= 0.5 * len(rec)):
                    out.append(rec)
    return out


def _unisci(base, u):
    if u.startswith('http'):
        return u
    if u.startswith('//'):
        return 'https:' + u
    return base.rstrip('/') + '/' + u.lstrip('/')


# ---------------------------------------------------------------------------
# Riconoscimento della lista in una pagina (copiato anche nel canale)
# ---------------------------------------------------------------------------

def _riconosci(dizionari, soglia=0.7):
    """Firma dei campi se la lista sembra un elenco di contenuti, altrimenti None."""
    dizionari = [_spacchetta(d) for d in dizionari]
    campioni = dizionari[:400]
    firma = None
    for kt in TITOLO:
        for kl in LINK:
            buoni = 0
            for d in campioni:
                t, u = d.get(kt), d.get(kl)
                if isinstance(u, dict):
                    u = u.get('url') or u.get('@id')
                if isinstance(t, str) and t.strip() and isinstance(u, str) and (u.startswith('/') or u.startswith('http')):
                    buoni += 1
            if buoni >= max(3, int(soglia * len(campioni))):
                if not firma or buoni > firma['buoni']:
                    firma = {'titolo': kt, 'link': kl, 'buoni': buoni}
    if not firma:
        return None
    for nome, chiavi in (('immagine', IMMAGINE), ('trama', TRAMA), ('orario', ORARIO)):
        conteggio = {}
        for d in campioni:
            k, v = _scegli(d, chiavi)
            if k:
                conteggio[k] = conteggio.get(k, 0) + 1
        if conteggio:
            k = max(conteggio, key=conteggio.get)
            if conteggio[k] >= 0.5 * firma['buoni']:
                firma[nome] = k
    return firma


def rileva(h):
    """Cerca nella pagina la migliore lista di contenuti. Restituisce {'firma':..., 'gruppi': [...], 'n': totale} o None."""
    migliore = None
    for testo in _testi(h):
        for ob in _oggetti(testo):
            liste = []
            _liste(ob, liste)
            for lista in liste:
                # elenco di gruppi (per esempio giorni) che contengono i contenuti
                figli = {}
                for p in lista:
                    for k, v in p.items():
                        if isinstance(v, list) and len([x for x in v if isinstance(x, dict)]) >= 1:
                            figli.setdefault(k, []).extend(x for x in v if isinstance(x, dict))
                for k, lf in figli.items():
                    if len(lf) < 3 or len(lista) < 2:
                        continue
                    firma = _riconosci(lf, 0.1)
                    if not firma:
                        continue
                    percorsi = list(GRUPPO)
                    for k2 in (lista[0] if lista else {}):
                        if isinstance(lista[0][k2], dict):
                            percorsi += ['%s.%s' % (k2, g2) for g2 in GRUPPO]
                    for g in percorsi:
                        if sum(1 for p in lista if _etichetta(p, g) not in (None, '')) >= 0.8 * len(lista):
                            firma2 = dict(firma, gruppo=g, figli=k)
                            gruppi = _trova(h, firma2)
                            n = sum(len(r) for _, r in gruppi)
                            if n >= 3 and len(gruppi) >= 2 and (not migliore or (bool(firma2.get('immagine')), n, len(firma2)) > (bool(migliore['firma'].get('immagine')), migliore['n'], len(migliore['firma']))):
                                migliore = {'firma': firma2, 'gruppi': gruppi, 'n': n}
                            break
                firma = _riconosci(lista)
                if firma:
                    gruppi = _trova(h, firma)
                    n = sum(len(r) for _, r in gruppi)
                    # a parita di elementi, una lista con gruppi vale di piu: gia gestita sopra
                    if n >= 3 and (not migliore or (not migliore['firma'].get('gruppo') and (bool(firma.get('immagine')), n, len(firma)) > (bool(migliore['firma'].get('immagine')), migliore['n'], len(migliore['firma'])))):
                        migliore = {'firma': firma, 'gruppi': gruppi, 'n': n}
    return migliore


def rileva_tutte(h, minimo=3):
    """Tutte le liste di contenuti della pagina (non solo la migliore): [{'firma':..., 'record': [...]}]."""
    out = []
    for testo in _testi(h):
        for ob in _oggetti(testo):
            liste = []
            _liste(ob, liste)
            for lista in liste:
                firma = _riconosci(lista)
                if not firma:
                    continue
                rec = [x for x in (_record(d, firma) for d in lista) if x]
                if len(rec) >= minimo and not any(o['firma'] == firma and [x['url'] for x in o['record']] == [x['url'] for x in rec] for o in out):
                    out.append({'firma': firma, 'record': rec})
    return out


def rileva_json(ob):
    """Come rileva, ma su una risposta JSON gia letta (per esempio la ricerca del sito)."""
    return rileva('<script type="application/json">' + json.dumps(ob) + '</script>')


def canali_fratelli(h, percorso):
    """Pagine sorelle di una pagina del tipo /sezione/nome (per esempio le dirette o le guide dei canali) nominate nella pagina:
    [(titolo, percorso)]. Il titolo e il nome del canale se la pagina lo indica, altrimenti l'ultimo pezzo dell'indirizzo."""
    parti = [x for x in percorso.split('/') if x]
    if len(parti) != 2:
        return []
    testo = h.replace('\\"', '"').replace('\\/', '/')
    trovati = []
    for m in re.finditer(r'["\'(=]/%s/([A-Za-z0-9_\-]+)["\')> ?#]' % re.escape(parti[0]), testo):
        p = '/%s/%s' % (parti[0], m.group(1))
        if p not in [x[1] for x in trovati]:
            nome = ''
            for n in re.finditer(r'"(?:canale|name|title|titolo)":"([^"]{2,40})"[^{}]{0,80}"[A-Za-z]+":"%s"' % re.escape(p), testo):
                nome = n.group(1)
            if not nome:
                nome = m.group(1).replace('-', ' ')
            if nome.isupper():
                nome = nome.title()
            trovati.append((nome, p))
    return trovati if len(trovati) >= 2 and percorso.rstrip('/') in [x[1] for x in trovati] else []

if sys.version_info[0] >= 3:
    from concurrent import futures
    from urllib.parse import urlencode
    import urllib.request as urllib_request
else:
    from concurrent_py2 import futures
    from urllib import urlencode
    import urllib2 as urllib_request  # urllib2 is used in Python 2

DRM = 'com.widevine.alpha'
key_widevine = "https://la7.prod.conax.cloud/widevine/license"
host = 'https://www.la7.it'
headers = {
    'host_token': 'pat.la7.it',
    'host_license': 'la7.prod.conax.cloud',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
    'accept': '*/*',
    'accept-language': 'en,en-US;q=0.9,it;q=0.8',
    'dnt': '1',
    'te': 'trailers',
    'origin': 'https://www.la7.it',
    'referer': 'https://www.la7.it/',
}

@support.menu
def mainlist(item):
    top =  [('Dirette {bold}', ['', 'live']),
            ('Replay {bold}', ['', 'replay_channels'])]

    menu = [('Programmi TV {bullet bold}', ['/tutti-i-programmi', 'peliculas', '', 'tvshow']),
            ('Teche La7 {bullet bold}', ['/la7teche', 'peliculas', '', 'tvshow']),
            ('Film La7Cinema {bullet bold}', ['/la7-cinema-tutti-i-film/rivedila7', 'episodios', '', 'peliculas'])]

    search = ''
    return locals()


def live(item):
    la7live_item = item.clone(title=support.typo('La7', 'bold'), fulltitle='La7', url= host + '/dirette-tv', action='findvideos', forcethumb = True, no_return=True)
    la7dlive_item = item.clone(title=support.typo('La7Cinema', 'bold'), fulltitle='La7d', url= host + '/live-la7cinema', action='findvideos', forcethumb = True, no_return=True)
    json_data = json.loads(httptools.downloadpage("https://www.la7.it/sites/default/files/la7_app_home_smarttv.json").data)
    if "fascia_dirette" in json_data:
        if 'la7' in json_data["fascia_dirette"]:
            titolo = json_data["fascia_dirette"]["la7"].get("titolo","")
            la7live_item.plot = support.typo(titolo, 'bold') + " - " + json_data["fascia_dirette"]["la7"].get("descrizione","")
            la7live_item.fanart = json_data["fascia_dirette"]["la7"]["url_locandina"]

        if 'la7d' in json_data["fascia_dirette"]:
            titolo = json_data["fascia_dirette"]["la7d"].get("titolo","")
            la7dlive_item.plot = support.typo(titolo, 'bold') + " - " + json_data["fascia_dirette"]["la7d"].get("descrizione","")
            la7dlive_item.fanart = json_data["fascia_dirette"]["la7d"]["url_locandina"]
    itemlist = [la7live_item, la7dlive_item]
    return support.thumb(itemlist, live=True)


def replay_channels(item):
    itemlist = [item.clone(title=support.typo('La7', 'bold'), fulltitle='La7', url= host + '/rivedila7/0/la7', action='replay_menu', forcethumb = True),
                item.clone(title=support.typo('La7Cinema', 'bold'), fulltitle='La7d', url= host + '/rivedila7/0/la7cinema', action='replay_menu', forcethumb = True)]
    itemlist = support.thumb(itemlist, live=True)
    itemlist.append(item.clone(title=support.typo('TG La7', 'bold'), fulltitle='TG La7',
                               plot='Informazione a cura della redazione del TG LA7', url= host + '/tgla7', action='episodios',
                               thumbnail='https://raw.githubusercontent.com/Stream4me/media/refs/heads/master/resources/thumb/tg.png',
                               fanart='https://raw.githubusercontent.com/Stream4me/media/refs/heads/master/resources/thumb/tg.png'))
    return itemlist


def replay_menu(item):
    itemlist = []
    h = httptools.downloadpage(item.url).data
    for etichetta, elenco in _trova(h, {'titolo': 'titolo', 'link': 'pathname', 'buoni': 48, 'immagine': 'immagine_scena', 'trama': 'sinossi', 'orario': 'ora', 'gruppo': '@attributes.data', 'figli': 'programma'}):
        itemlist.append(item.clone(title=support.typo(etichetta, 'bold'), gruppo=etichetta, action='replay'))
    return itemlist

def replay(item):
    itemlist = []
    h = httptools.downloadpage(item.url).data
    for etichetta, elenco in _trova(h, {'titolo': 'titolo', 'link': 'pathname', 'buoni': 48, 'immagine': 'immagine_scena', 'trama': 'sinossi', 'orario': 'ora', 'gruppo': '@attributes.data', 'figli': 'programma'}):
        if etichetta != item.gruppo:
            continue
        for r in elenco:
            titolo = '%s - %s' % (r['orario'], r['titolo']) if r['orario'] else r['titolo']
            itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=r['titolo'], show=r['titolo'],
                                       url=_unisci(host, r['url']), thumbnail=_unisci(host, r['immagine']) if r['immagine'] else '',
                                       fanart=_unisci(host, r['immagine']) if r['immagine'] else '', plot=r['trama'],
                                       action='findvideos', forcethumb=True))
    return itemlist

def clean_title(t):
    t = html.unescape(t)
    t = t.replace("\xa0", " ")
    t = " ".join(t.split())
    return t


def search(item, text):
    if hasattr(item, "search") and item.search:
        text = item.search

    query = str(text).strip()
    if not query:
        return []

    raw_page = getattr(item, "page", 0)
    try:
        page = int(raw_page)
    except:
        page = 0

    encoded = quote_plus(query)
    url = f"{host}/ricerca?query={encoded}&page={page}"
    html_data = httptools.downloadpage(url).data

    if '<div class="view-content">' in html_data:
        html_results = html_data.split('<div class="view-content">')[-1]
        html_results = html_results.split('<div class="pager pagerBottom"', 1)[0]
    else:
        html_results = html_data

    patron = r'<a href="(?P<url>/[^"]+)"[^>]*>\s*<div class="holder-bg">.*?data-background-image="(?P<thumb>[^"]+)".*?<div class="title[^"]*">\s*(?P<title>[^<]+)\s*</div>'
    match = support.match(html_results, patron=patron)
    results = match.matches

    itemlist = []
    seen = set()

    for url, thumb, title in results:
        if url in seen:
            continue
        seen.add(url)

        title = clean_title(title)
        fullurl = host + url
        if thumb.startswith("//"):
            thumb = "https:" + thumb

        it = item.clone(
            title=support.typo(title, 'bold'),
            fulltitle=title,
            show=title,
            url=fullurl,
            thumbnail=thumb,
            fanart=thumb,
            action="findvideos"
        )
        itemlist.append(it)

    if f'query={encoded}&amp;page={page+1}' in html_data:
        next_item = item.clone(
            search=query,
            page=page+1,
            url=host
        )
        support.nextPage(itemlist, next_item, function_or_level='search_page')

    return itemlist


def search_page(item):
    return search(item, item.search)


def peliculas(item):
    html_content = httptools.downloadpage(item.url).data

    if 'la7teche' in item.url:
        patron = r'<a href="(?P<url>[^"]+)" title="(?P<title>[^"]+)" class="teche-i-img".*?url\(\'(?P<thumb>[^\']+)'
    else:
        tids = {'/fa-che-io-sia-lultima': '115013', '/100minuti': '115737', '/atelechiavi': '84090', '/ai-il-futuro': '114921', '/amarsi-un-po': '115239', '/amgstories': '112885',
             '/amoristonati': '79999', '/artbox': '104964', '/atlantide': '27381', '/atlantidefiles': '87126', '/barbero-risponde': '118666', '/bellitalia-in-viaggio': '102099',
             '/bellidentrobellifuori': '82353', '/bersaglio-mobile': '45819', '/bull': '115680', '/buongiornomondo': '119675', '/c-era-una-volta': '111648', '/cera-una-volta-il-novecento': '111932',
             '/cambio-cuoco': '75628', '/camera-con-vista': '81722', '/cercasiautodisperatamente': '82794', '/coffee-break': '27592', '/cristina-parodi-live': '27533',
             '/crozza': '25457', '/cuochi-e-fiamme': '33163', '/defining-class-since-1886': '114836', '/diciannovequaranta': '59402', '/dimartedi': '59403', '/dizionario-del-tempo-presente': '101035',
             '/donne-vittime-e-carnefici': '33198', '/donne-storie-che-ispirano': '96013', '/downton-abbey': '106972', '/drink-me-out': '86027', '/eccezionale-veramente': '69716',
             '/eccezionale-veramente-2017': '74976', '/eccezionale-veramente-ma-veramente': '72974', '/omnibus-edicola': '114491', '/effetti-personali': '33311', '/quirinale': '106765',
             '/elezioni': '32577', '/elezioni-amministrative-2021': '104639', '/elezioni-europee-2024': '117571', '/elezioni-politiche-2022': '109941', '/regionali2015': '65426',
             '/elezioni-regionali-2020': '94442', '/elezioni-usa': '95091', '/eqelements': '114288', '/euro-dieci': '117427', '/europost': '119993', '/eventi-live': '116094',
             '/speciali-ezio-mauro': '119401', '/facciaafaccia': '73973', '/famiglie-ditalia': '118714', '/film-e-fiction': '53050', '/food-maniac': '34470', '/webserie': '58781',
             '/fuori-di-gusto': '34408', '/fuorionda': '69092', '/futbol': '72814', '/gazzetta-sports-awards': '74693', '/gigawatt': '118659', '/guerrieri': '52614', '/gustibus': '64469',
             '/hawthorne': '85101', '/honestlygood': '82312', '/i-men%C3%B9-di-benedetta': '36443', '/i-responsabili': '109082', '/il-bello-delle-curve': '76901', '/il-boss-dei-comici': '67694',
             '/il-commissario-cordier': '53311', '/il-gusto-di-sapere': '91393', '/il-mondo-che-verr%C3%A0': '37129', '/il-palio-di-siena': '109478', '/ilpolliceverdesonoio': '68548',
              '/il-processo-di-biscardi': '112450', '/in-altre-parole': '114460', '/ricette-di-cucina': '58727', '/la-cucina-di-sonia': '97070', '/in-cucina-con-vissani': '42222', '/in-onda': '58737',
             '/in-treatment': '57985', '/in-tv': '42300', '/in-viaggio-con-barbero': '114442', '/inarrestabili': '58625', '/inchieste-da-fermo': '113584', '/indovina-cosa-sceglie-la-sposa': '75632',
             '/innovation': '36568', '/inseparabili': '101261', '/intanto': '101263', '/italia-fashion-show': '55904', '/josephineangegardien': '77994', '/kataklo': '90255', '/laria-che-tira': '38052',
             '/lariadestate': '66668', '/lerba-del-vicino': '56552', '/lingrediente-perfetto': '86510', '/lofficina-delle-erbe': '74825', '/lora-della-salute': '75316','/lunionefalaforza': '86454',
             '/la-caduta': '115146', '/le-copertine-di-crozza': '66697', '/la-corsa-al-voto': '109702', '/lafelicitanoneunatruffa': '82920', '/la-gabbia': '52618', '/la-gaia-scienza': '38026',
             '/la-mala-educaxxxion': '56214', '/la-mala-educaxxxion-la7d': '38317', '/la-torre-di-babele': '114981', '/la-torre-di-babele-doc': '118783', '/la7cult': '111885', '/la7-cult': '26075',
             '/la7magazine': '63005', '/la7ricorda': '83508', '/la7racconta': '72941', '/la7speciali': '102882', '/la7venti': '103095', '/le-invasioni-barbariche': '38071',
             '/le-parole-della-salute': '91908', '/libri-in-onda': '111130', '/like': '84156', '/linea-gialla': '38501', '/lingo': '109910', '/little-murders': '81521', '/magazine7': '64468',
             '/mamma-mia-che-settimana': '43996', '/marxisti-tendenza-groucho': '48797', '/meravigliosamente': '78387', '/meteo-della-sera': '93826', '/meteola7': '60540',
             '/mica-pizza-e-fichi': '86104', '/miss-italia': '52620', '/miss-marple': '109479', '/missione-natura': '42849', '/mode-e-modi': '58403', '/mondo-senza-fine': '54093',
             '/motorstorie': '111088', '/nene-e-margherita': '49131', '/niente-ferma-le-donne': '75540', '/non-ditelo-alla-sposa': '54990', '/nonelarena': '78932',
             '/oliver-stone-nuclear-now': '115049', '/omnibus': '43855', '/oroscopo': '53863', '/otto-e-mezzo': '45098', '/our-godfather': '85928', '/padre-brown': '109373', '/piazzapulita': '42851',
             '/pinkisgood': '78693', '/trash-it': '76993', '/propagandalive': '78368', '/quattrodonneeunfunerale': '54398', '/raffaella-carra': '103352', '/recital-di-corrado-guzzanti': '53862',
             '/rigenerazione': '115362', '/figworldcup': '84181', '/roshn-saudi-league': '114296', '/royal-wedding': '81166', '/sconosciuti': '116192', '/se-stasera-sono-qui': '45749',
             '/selfiefood': '79476', '/sempre-meglio-che-restare-a-casa': '112451', '/senti-chi-mangia': '92485', '/sfera': '71860', '/si-parla-di': '83927', '/skroll': '78278',
             '/specialguest': '66670', '/speciali': '55153', '/speciali-mentana': '45796', '/startupeconomy': '91462', '/storie-dellaltro-social': '112291', '/storie-di-grandi-chef': '42921',
             '/storie-di-palazzi': '110336', '/syusy-e-patrizio-news': '118758', '/tacco12enonsolo': '72605', '/taga-doc': '87967', '/tagada': '67838', '/taste-il-gusto-delleccellenza': '116662',
             '/tgla7': '52619', '/the-dr-oz-show': '87313', '/the-show-must-go-off': '42865', '/ti-ci-porto-io': '46132', '/trumpstory': '119618', '/un-dolce-da-maestro': '84410',
             '/una-giornata-particolare': '109868', '/uno-maggio-taranto-liberi-e-pensanti': '91830', '/uozzap': '81522', '/urban-scouters': '109003', '/vado-a-vivere-in-montagna': '85810',
             '/varcondicio': '79932', '/victor-victoria': '42868', '/voicetown': '100017', '/voto-piu-voto-meno': '119921', '/welovecinema': '60262', '/zeta': '46396'}
        program_details = {}
        def fetch_program_data(path, tid):
            url = f"https://www.la7.it/appla7/service_propertysmarttv?s=hbbtv&field_property_tid={tid}"
            try:
                data = json.loads(httptools.downloadpage(url).data)
                if data and isinstance(data, list):  # Ensure data is a non-empty list
                    item = data[0]
                    return path, {
                        "titolo": html.unescape(item.get("titolo", "")),
                        "testo": html.unescape(item.get("testo", "")),
                        "img": item.get("img", "").split('src="')[1].split('"')[0] if 'src="' in item.get("img", "") else "",
                        "img_verticale": item.get("img_verticale", "").split('src="')[1].split('"')[0] if 'src="' in item.get("img_verticale", "") else "",
                    }
                else:
                    return path, None
            except Exception as e:
                return path, None  # Return None if request or parsing fails

        # Use ThreadPoolExecutor for parallel requests
        with futures.ThreadPoolExecutor() as executor:
            future_to_path = {executor.submit(fetch_program_data, path, tid): path for path, tid in tids.items()}
            
            for future in futures.as_completed(future_to_path):
                path, data = future.result()
                if data:
                    program_details[path] = data
        patron = r'<a href="(?P<url>[^"]+)"[^>]*>\s*<div class="[^"]+" data-background-image="(?P<thumb>[^"]+)"'

    match = support.match(html_content, patron=patron)
    matches = match.matches
    # url_splits = item.url.split('?')

    itemlist = []
    for n, key in enumerate(matches):
        if 'la7teche' in item.url:
            programma_url, titolo, thumb = key
            plot = ""
            fanart = ""
        else:
            programma_url, thumb = key
            if programma_url in program_details:
                pinfo = program_details[programma_url]
                titolo = pinfo['titolo'] if pinfo['titolo'] else " ".join(programma_url.replace("/", "").split('-')).title()
                plot = pinfo['testo']
                thumb = pinfo['img'] if pinfo['img'] else thumb
                fanart = pinfo['img_verticale']
            else:
                titolo = " ".join(programma_url.replace("/", "").split('-')).title()
                plot = ""
                fanart = ""

        if not thumb.startswith("https://"):
            thumb = f'{host}/{thumb}'
        programma_url = f'{host}{programma_url}'
        titolo = html.unescape(titolo)

        it = item.clone(title=support.typo(titolo, 'bold'),
                        data='',
                        fulltitle=titolo,
                        show=titolo,
                        plot = plot,
                        thumbnail=thumb,
                        fanart = fanart,
                        url=programma_url,
                        video_url=programma_url,
                        order=n)
        it.action = 'episodios'
        it.contentSerieName = it.fulltitle

        itemlist.append(it)

    return itemlist


def episodios(item):
    if item.url.endswith('/tgla7'):
        html_content = httptools.downloadpage('https://tg.la7.it/ultime-edizioni-del-tgla7').data
    else:
        html_content = httptools.downloadpage(item.url).data

    if '/la7-cinema-tutti-i-film/rivedila7/' in item.url:
        return [ item.clone(action='findvideos', url=item.url, video_url=item.url) ]

    itemlist = []
    matches = []

    if 'la7teche' in item.url:
        patron = r'[^>]+>\s*<a href="(?P<url>[^"]+)">.*?image="(?P<thumb>[^"]+)(?:[^>]+>){4,5}\s*(?P<title>[\d\w][^<]+)(?:(?:[^>]+>){7}\s*(?P<title2>[\d\w][^<]+))?'
        html_content = html_content.split('id="block-system-main"')[1]
        match = support.match(html_content, patron=patron)
        matches.extend(match.matches)

    elif 'tgla7' in item.url:
        patron = r'<a href="(?P<url>[^"]+)"[^>]+data-bg="(?P<thumb>[^"]+)".*?</a>.*?<h4 class="news-title">\s*<a [^>]*>(?P<title>[^<]+)</a>.*?<div class="news-descrizione">\s*(?P<plot>[^<]+)\s*<'
        match = support.match(html_content, patron=patron)
        matches.extend(match.matches)

    else:
        if len(item.url.split('www.la7.it')[-1].strip('/').split("/")) == 1:
            match = support.match(html_content, patron=r'page-taxonomy-term-(\d+)')
            tid = match.matches[0] if match.matches else ""
            if tid:
                data = json.loads(httptools.downloadpage(
                    f"https://www.la7.it/appla7/service_propertysmarttv?s=hbbtv&field_property_tid={tid}"
                ).data)
                plot = html.unescape(data[0].get("testo", "")) if data else ""
            else:
                plot = ""

            match = support.match(html_content, patron=r'background-image:url\((\'|")([^\'"]+)(\'|")\);')
            fanart = match.matches[0][1] if match.matches else ""

            match = support.match(html_content,
                                  patron=r'<li class="voce_menu">\s*<a href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>\s*</li>')
            result_dict = {text: href for href, text in match.matches}

            for k, v in result_dict.items():
                if len(v.strip('/').split("/")) > 1:
                    if not v.startswith('/') and not v.startswith('https://www.la7.it'):
                        continue
                    v = f'{host}{v}'
                    new_item = item.clone(
                        title=support.typo(k, 'bold'),
                        data='',
                        fulltitle=k,
                        show=k,
                        url=v,
                        plot=plot,
                        fanart=fanart
                    )
                    itemlist.append(new_item)

            patron = r'<div class="item.*?"> <a href="(?P<url>[^"]+)"><div class="holder-bg">.*?data-background-image="(?P<image>(?:https?:)?//[^"]+)".*?<div class="(?:title|occhiello)[^"]*">\s*(?P<title>[^<]+)\s*</div>'
            match = support.match(html_content.split('<div class="subcontent">')[-1], patron=patron)
            matches.extend(match.matches)

        else:
            html_content = html_content.split('<div class="main-content-node">')[-1].split('<div class="right">')[0]
            html_content = html_content.split('<div class="view-content clearfix">')
            patron = r'<div class="[^"]*"[^>]*>.*?<a href="(?P<url>[^"]+)">.*?data-background-image="(?P<image>(?:https?:)?//[^"]+)"[^>]*>.*?<div class="title[^"]*">\s*(?P<title>[^<]+)\s*</div>'

            if '<li class="pager-previous">' not in html_content[0]:
                if len(html_content) > 1:
                    match = support.match(html_content[0], patron=patron)
                    matches.extend(match.matches)

            html_content = html_content[-1]
            match = support.match(html_content, patron=patron)
            matches.extend(match.matches)

    visited = set()

    def itInfo(n, key, item):
        if 'la7teche' in item.url:
            programma_url, thumb, titolo, plot = key
        elif 'tgla7' in item.url:
            programma_url, thumb, titolo, plot = key
        else:
            programma_url, thumb, titolo = key
            plot = ""

        if programma_url in visited:
            return None

        visited.add(programma_url)
        programma_url = f'{"https://tg.la7.it" if "tgla7" in item.url else host}{programma_url}'
        thumb = 'https://' + thumb[2:] if thumb.startswith("//") else thumb
        titolo = html.unescape(titolo)

        it = item.clone(
            title=support.typo(titolo, 'bold'),
            data='',
            fulltitle=titolo,
            show=titolo,
            thumbnail=thumb,
            url=programma_url,
            video_url=programma_url,
            plot=plot if plot else item.plot,
            order=n
        )
        it.action = 'findvideos'
        return it

    original_length = len(itemlist)

    with futures.ThreadPoolExecutor() as executor:
        itlist = [executor.submit(itInfo, n, it, item) for n, it in enumerate(matches)]
        for res in futures.as_completed(itlist):
            if res.result():
                itemlist.append(res.result())

    itemlist[original_length:] = sorted(itemlist[original_length:], key=lambda it: it.order)

    match = support.match(html_content, patron=r'<li class="pager-next"><a href="(.*?)">›</a></li>')
    if match.matches:
        next_page_link = match.matches[0]
        itemlist.append(
            item.clone(
                title=support.typo(support.config.get_localized_string(30992), 'color std bold'),
                url=f'{host}{next_page_link}',
                order=len(itemlist),
                video_url='',
                thumbnail=''
            )
        )

    return itemlist


def findvideos(item):
    support.info()
    if item.livefilter:
        for it in live(item):
            if it.fulltitle == item.livefilter:
                item = it
                break
    data = support.match(item).data

    url = support.match(data, patron=r'''["]?dash["]?\s*:\s*["']([^"']+)["']''').match

    if url:
        preurl = support.match(data, patron=r'preTokenUrl = "(.+?)"').match
        tokenHeader = {
            'host': headers['host_token'],
            'user-agent': headers['user-agent'],
            'accept': headers['accept'],
            'accept-language': headers['accept-language'],
            'dnt': headers['dnt'],
            'te': headers['te'],
            'origin': headers['origin'],
            'referer': headers['referer'],
        }
        req = urllib_request.Request(preurl, headers=tokenHeader)
        with urllib_request.urlopen(req, context=ssl._create_unverified_context()) as response:
            data = json.load(response)  # Parse JSON response
        preAuthToken = data['preAuthToken']

        licenseHeader = {
            'host': headers['host_license'],
            'user-agent': headers['user-agent'],
            'accept': headers['accept'],
            'accept-language': headers['accept-language'],
            'preAuthorization': preAuthToken,
            'origin': headers['origin'],
            'referer': headers['referer'],
        }
        preLic= '&'.join(['%s=%s' % (name, value) for (name, value) in licenseHeader.items()])
        tsatmp=str(int(support.time()))
        license_url= key_widevine + '?d=%s'%tsatmp
        lic_url='%s|%s|R{SSM}|'%(license_url, preLic)
        item.drm = DRM
        item.license = lic_url
    else:
        match = support.match(data, patron=r'''["]?m3u8["]?\s*:\s*["']([^"']+)["']''').match
        if match:
            url = match.replace("http://la7-vh.akamaihd.net/i/", "https://awsvodpkg.iltrovatore.it/local/hls/").replace("csmil/master.m3u8", "urlset/master.m3u8");
    
    if url=="":
        url = support.match(data, patron=r'''["]?mp4["]?\s*:\s*["']([^"']+)["']''').match

    item = item.clone(title='Direct', server='directo', url=url, action='play')
    return support.server(item, itemlist=[item], Download=False, Videolibrary=False)
