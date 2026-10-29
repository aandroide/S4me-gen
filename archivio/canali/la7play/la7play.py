# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per La7play
# Generato da s4me_gen.py: controllare le regex e provare ogni voce del menu
# ------------------------------------------------------------

import json
import re
import base64
import difflib
from urllib.parse import urlencode

from core import support, httptools, tmdb
from core.item import Item, InfoLabels
from platformcode import config, logger, platformtools

host = support.config.get_channel_url().rstrip('/')
headers = [['Referer', host + '/']]


# lettore dei dati incorporati nella pagina (generato da dati_incorporati.py)
import html as _html
import json
import re

TITOLO = ('titolo', 'title', 'name', 'nome', 'headline', 'label')
LINK = ('pathname', 'url', 'href', 'link', 'permalink', 'path')
IMMAGINE = ('imageUrl', 'image_url', 'thumbnailUrl', 'immagine_scena', 'immagine', 'image', 'img', 'thumbnail', 'thumb', 'poster', 'cover', 'immagine_programma',
            'immagine_cover', 'picture')
TRAMA = ('excerpt', 'teaser', 'sinossi', 'plot', 'description', 'descrizione', 'abstract', 'occhiello', 'synopsis', 'summary')
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


def rileva_json(ob):
    """Come rileva, ma su una risposta JSON gia letta (per esempio la ricerca del sito)."""
    return rileva('<script type="application/json">' + json.dumps(ob) + '</script>')


def _pagina(url):
    return httptools.downloadpage(url, headers=headers).data


def _e_serie(url):
    # un contenuto riproducibile ha un numero identificativo in fondo all'indirizzo; il resto sono programmi e serie
    return not re.search(r'-\d{4,}/?$', url.split('?')[0])


def _voci(item, elenco, pagina_corrente=0, html=''):
    itemlist = []
    for r in elenco:
        serie = _e_serie(r['url'])
        titolo = '%s - %s' % (r['orario'], r['titolo']) if r['orario'] else r['titolo']
        itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=r['titolo'], show=r['titolo'],
                                   contentTitle='' if serie else r['titolo'],
                                   contentSerieName=r['titolo'] if serie else '',
                                   contentType='tvshow' if serie else 'movie',
                                   url=_unisci(host, r['url']),
                                   thumbnail=_unisci(host, r['immagine']) if r['immagine'] else '',
                                   fanart=_unisci(host, r['immagine']) if r['immagine'] else '',
                                   plot=r['trama'], action='episodios' if serie else 'findvideos', forcethumb=True))
    if pagina_corrente and len(itemlist) >= 10 and re.search(r'[?&]page=%d\b' % (pagina_corrente + 1), html):
        base = item.url.split('?')[0]
        itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'),
                                   url='%s?page=%d' % (base, pagina_corrente + 1), page=pagina_corrente + 1,
                                   action=item.action, thumbnail=support.thumb()))
    return itemlist


def peliculas(item):
    support.info(item)
    h = _pagina(item.url)
    r = rileva(h)
    if not r:
        logger.error('nessuna lista di titoli nei dati della pagina %s' % item.url)
        return []
    if r['firma'].get('gruppo'):
        return [item.clone(title=support.typo(etichetta, 'bold'), gruppo=etichetta, action='giorno')
                for etichetta, elenco in r['gruppi']]
    elenco = [x for _, rr in r['gruppi'] for x in rr]
    return _voci(item, elenco, int(item.page or 1) if getattr(item, 'page', '') else 1, h)


def giorno(item):
    r = rileva(_pagina(item.url))
    itemlist = []
    for etichetta, elenco in (r['gruppi'] if r else []):
        if etichetta == item.gruppo:
            itemlist = _voci(item, elenco)
    return itemlist


def episodios(item):
    support.info(item)
    h = _pagina(item.url)
    percorso = re.sub(r'^https?://[^/]+', '', item.url.split('?')[0]).rstrip('/')
    candidati = [item.url]
    for u in re.findall(r'href="(%s/[^"/#?]+)"' % re.escape(percorso), h):
        if re.search(r'puntat|episod|stagion|video', u) and _unisci(host, u) not in candidati:
            candidati.append(_unisci(host, u))
    migliore, pagina_ok = [], item.url
    for u in candidati:
        hh = h if u == item.url else _pagina(u)
        r = rileva(hh)
        if not r:
            continue
        elenco = [x for _, rr in r['gruppi'] for x in rr if percorso in x['url'] and x['url'].rstrip('/') != percorso]
        if len(elenco) > len(migliore):
            migliore, pagina_ok, h = elenco, u, hh
    if not migliore:
        return []
    item.url = pagina_ok
    itemlist = _voci(item, migliore, int(item.page or 1) if getattr(item, 'page', '') else 1, h)
    for it in itemlist:
        if it.action == 'episodios':
            it.action = 'findvideos'
            it.contentType = 'episode'
    return itemlist



@support.menu
def mainlist(item):
    top = [('Dirette', ['/dirette/la7', 'peliculas', '', 'tvshow']),
           ('Guida Tv e Rivedi', ['/guida-tv-rivedi/la7', 'peliculas', '', 'tvshow']),
           ('Programmi', ['/programmi', 'peliculas', '', 'tvshow']),
           ('Film', ['/film', 'peliculas', '', 'movie']),
           ('Documentari', ['/documentari', 'peliculas', '', 'tvshow']),
           ('Podcast', ['/podcast', 'peliculas', '', 'tvshow'])]
    search = ''
    return locals()




def search(item, text):
    support.info(text)
    item.url = host + '/ricerca?query=%s' % text.replace(' ', '+')
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []


def findvideos(item):
    support.info(item)
    return support.server(item, headers=headers)
