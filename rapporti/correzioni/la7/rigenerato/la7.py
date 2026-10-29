# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per La7
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

host = 'https://www.la7play.it'  # il dominio di channels.json ora reindirizza qui
headers = [['Referer', host + '/']]


# lettore dei dati incorporati nella pagina (generato da dati_incorporati.py)
import html as _html
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

ELENCHI_API = {'/programmi': ['f7034d55158fc906', '75b0227f0361abcf']}  # elenchi completi presi dalle richieste del sito: percorso -> codici delle richieste
CANALI_AZIONE = {'dirette': 'findvideos', 'guida-tv-rivedi': 'peliculas'}  # cosa apre ogni canale: findvideos (diretta) oppure peliculas (guida a giorni)


def _pagina(url):
    return httptools.downloadpage(url, headers=headers).data


def _e_serie(url):
    # un contenuto riproducibile ha un numero identificativo in fondo all'indirizzo; il resto sono programmi e serie
    return not re.search(r'-\d{4,}/?$', url.split('?')[0])


def _dettagli(item, itemlist):
    """Nelle liste di film: trama, anno, durata, generi e regista dalla pagina di ogni film (richieste in parallelo)."""
    if item.contentType != 'movie' or not itemlist:
        return itemlist
    from concurrent.futures import ThreadPoolExecutor

    def leggi(it):
        if it.action != 'findvideos':
            return {}
        try:
            h = _pagina(it.url)
        except Exception:
            return {}
        for blocco in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S):
            try:
                j = json.loads(blocco)
            except Exception:
                continue
            for n in (j.get('@graph', [j]) if isinstance(j, dict) else j):
                if isinstance(n, dict) and n.get('@type') in ('Movie', 'TVEpisode', 'VideoObject') and n.get('description'):
                    return n
        return {}

    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            nodi = list(ex.map(leggi, itemlist))
    except Exception as e:
        logger.error('dettagli non letti %s' % e)
        return itemlist
    for it, n in zip(itemlist, nodi):
        trama = _html.unescape(re.sub(r'<[^>]+>', ' ', n.get('description', ''))).replace('\xa0', ' ').strip()
        if trama:
            it.plot = trama
            it.infoLabels['plot'] = trama
        if re.match(r'\d{4}$', str(n.get('dateCreated', ''))):
            it.infoLabels['year'] = int(n['dateCreated'])
        d = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', n.get('duration', '') or '')
        if d and any(d.groups()):
            it.infoLabels['duration'] = int(d.group(1) or 0) * 3600 + int(d.group(2) or 0) * 60 + int(d.group(3) or 0)
        gen = n.get('genre', '')
        gen = [g for g in (gen if isinstance(gen, list) else [gen]) if g and g != 'Film']
        if gen:
            it.infoLabels['genre'] = ', '.join(gen)
        reg = n.get('director')
        reg = reg.get('name', '') if isinstance(reg, dict) else ''
        if reg:
            it.infoLabels['director'] = reg
    return itemlist


def _voci(item, elenco, pagina_corrente=0, html='', azione_pagina='peliculas'):
    itemlist = []
    for r in elenco:
        serie = _e_serie(r['url'])
        titolo = '%s - %s' % (r['orario'], r['titolo']) if r['orario'] else r['titolo']
        if r.get('programma') and not serie and r['programma'] != r['titolo']:
            titolo = '%s (%s)' % (titolo, r['programma'])
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
                                   action=azione_pagina, nextPage=True, thumbnail=support.thumb()))
    return itemlist


GIORNI_IT = ['lunedi', 'martedi', 'mercoledi', 'giovedi', 'venerdi', 'sabato', 'domenica']
MESI_IT = ['', 'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre',
           'ottobre', 'novembre', 'dicembre']


def _data_it(etichetta):
    """Se l'etichetta di un gruppo e una data: (data, 'Giovedi 22 ottobre'), altrimenti None."""
    from datetime import datetime
    m = re.fullmatch(r'(\d{2})[-/.](\d{2})[-/.](\d{4})', etichetta or '')
    if m:
        g, me, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:$|T|\s)', etichetta or '')
        if not m:
            return None
        a, me, g = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        d = datetime(a, me, g)
    except ValueError:
        return None
    nome = 'Oggi' if d.date() == datetime.now().date() else GIORNI_IT[d.weekday()].capitalize()
    return d, '%s %d %s' % (nome, g, MESI_IT[me])


def _da_api(codici):
    """Elenco completo dalle richieste del sito (la pagina ne mostra solo una parte)."""
    for codice in codici:
        try:
            r = rileva_json(json.loads(_pagina(host + '/api/gql/' + codice)))
        except Exception:
            continue
        if r:
            return [x for _, rr in r['gruppi'] for x in rr]
    return []


def canali(item):
    itemlist = []
    percorso = re.sub(r'^https?://[^/]+', '', item.url.split('?')[0]).rstrip('/')
    azione = CANALI_AZIONE.get(percorso.strip('/').split('/')[0], 'findvideos')
    for titolo, p in canali_fratelli(_pagina(item.url), percorso):
        itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=titolo, url=_unisci(host, p),
                                   action=azione, forcethumb=True, no_return=True))
    return support.thumb(itemlist, live=True)


def peliculas(item):
    support.info(item)
    percorso = re.sub(r'^https?://[^/]+', '', item.url.split('?')[0]).rstrip('/')
    if percorso in ELENCHI_API:
        elenco = _da_api(ELENCHI_API[percorso])
        if elenco:
            return _dettagli(item, _voci(item, elenco))
    h = _pagina(item.url)
    r = rileva(h)
    if not r:
        logger.error('nessuna lista di titoli nei dati della pagina %s' % item.url)
        return []
    if r['firma'].get('gruppo'):
        date = [_data_it(etichetta) for etichetta, elenco in r['gruppi']]
        if all(date):
            ordine = sorted(zip(date, r['gruppi']), key=lambda x: x[0][0], reverse=True)
            return [item.clone(title=support.typo(d[1], 'bold'), gruppo=etichetta, action='giorno', thumbnail=support.thumb())
                    for d, (etichetta, elenco) in ordine]
        return [item.clone(title=support.typo(etichetta, 'bold'), gruppo=etichetta, action='giorno')
                for etichetta, elenco in r['gruppi']]
    elenco = [x for _, rr in r['gruppi'] for x in rr]
    return _dettagli(item, _voci(item, elenco, int(item.page or 1) if getattr(item, 'page', '') else 1, h))


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
    # prima le pagine dedicate agli episodi, poi le altre sezioni, per ultima la pagina stessa (che mescola episodi e video)
    candidati = []
    for rx in (r'puntat|episod', r'stagion', r'video'):
        for u in re.findall(r'href="(%s/[^"/#?]+)"' % re.escape(percorso), h):
            if re.search(rx, u) and _unisci(host, u) not in candidati:
                candidati.append(_unisci(host, u))
    if item.url not in candidati:
        candidati.append(item.url)
    migliore, pagina_ok = [], item.url
    for u in candidati:
        hh = h if u == item.url else _pagina(u)
        r = rileva(hh)
        if not r:
            continue
        elenco = [x for _, rr in r['gruppi'] for x in rr if percorso in x['url'] and x['url'].rstrip('/') != percorso]
        if elenco:
            migliore, pagina_ok, h = elenco, u, hh
            break
    if not migliore:
        return []
    item.url = pagina_ok
    itemlist = _voci(item, migliore, int(item.page or 1) if getattr(item, 'page', '') else 1, h, 'episodios')
    for it in itemlist:
        if it.action == 'episodios' and not getattr(it, 'nextPage', False):
            it.action = 'findvideos'
            it.contentType = 'episode'
    return itemlist


def _codifica(variabili):
    return base64.urlsafe_b64encode(json.dumps(variabili, separators=(',', ':'), sort_keys=True).encode()).decode().rstrip('=')


def _sostituisci(v, testo):
    if isinstance(v, dict):
        return {k: _sostituisci(x, testo) for k, x in v.items()}
    if v == '__TESTO__':
        return testo
    return v


def _raccogli(ob, firma, uscita):
    # tutti i gruppi di risultati (programmi, video, film), tranne gli articoli di giornale
    if isinstance(ob, dict):
        if any(isinstance(ob.get(k), str) and re.search(r'articl', ob.get(k), re.I) for k in ('contentType', 'type', 'tipo')):
            return
        for v in ob.values():
            _raccogli(v, firma, uscita)
    elif isinstance(ob, list):
        rec = [x for x in (_record(d, firma) for d in ob if isinstance(d, dict)) if x]
        if rec:
            uscita.extend(rec)
        else:
            for x in ob:
                _raccogli(x, firma, uscita)


def _pagine_totali(ob):
    if isinstance(ob, dict):
        for k, v in ob.items():
            if re.fullmatch(r'total_?pages', k, re.I) and isinstance(v, int):
                return v
            r = _pagine_totali(v)
            if r:
                return r
    elif isinstance(ob, list):
        for x in ob:
            r = _pagine_totali(x)
            if r:
                return r
    return 0


def search(item, text):
    support.info(text)
    q = str(getattr(item, 'search', '') or text).strip()
    pagina = int(getattr(item, 'page', 0) or 1)
    try:
        variabili = _sostituisci({'q': '__TESTO__'}, q)
        if pagina > 1:
            variabili['page'] = pagina
        r = json.loads(_pagina(host + '/api/gql/4da1e384f8a63808/' + _codifica(variabili)))
        trovati = rileva_json(r)
        if not trovati:
            return []
        elenco, visti = [], set()
        _raccogli(r, trovati['firma'], elenco)
        elenco = [x for x in elenco if not (x['url'] in visti or visti.add(x['url']))]
        itemlist = _voci(item, elenco)
        if pagina < _pagine_totali(r):
            itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'), search=q,
                                       page=pagina + 1, action='search_page', nextPage=True, thumbnail=support.thumb()))
        return itemlist
    except Exception:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []


def search_page(item):
    return search(item, item.search)


# riproduzione imparata dal sito (riproduzione.py)
from urllib.parse import urlsplit as _urlsplit

ESPR = re.compile(r'"([A-Za-z_][\w\-]*)":("(?:[^"\\]|\\.)*"|true|false|-?\d+(?:\.\d+)?)')


def pulisci(h):
    return h.replace('\\"', '"').replace('\\u0026', '&').replace('\\/', '/').replace('\\\\', '\\')


def valori_pagina(h):
    """Prima occorrenza di ogni chiave dei dati incorporati: {chiave: valore come stringa}."""
    out = {}
    for m in ESPR.finditer(pulisci(h)):
        k, v = m.group(1), m.group(2)
        if k in out:
            continue
        if v.startswith('"'):
            v = v[1:-1]
        out[k] = v
    return out


def _ultimo(v):
    return v.split('?')[0].rstrip('/').split('/')[-1]


TRASFORMAZIONI = [
    ('id', lambda v: v),
    ('ultimo', _ultimo),
    ('senza_slash', lambda v: v.strip('/')),
    ('senza_mp4', lambda v: v.replace('.mp4', '')),
    ('prima', lambda v: v.split('|')[0]),
    ('seconda', lambda v: v.split('|')[1] if '|' in v else ''),
    ('origine', lambda v: '%s://%s' % (_urlsplit(v).scheme, _urlsplit(v).netloc) if v.startswith('http') else ''),
]
TR = dict(TRASFORMAZIONI)


def applica(modello, valori):
    out = ''
    for p in modello:
        if p[0] == 'lett':
            out += p[1]
        else:
            v = valori.get(p[1])
            if v is None or v == '':
                return None
            out += TR[p[2]](v)
    return out


def licenza_url(v, sistema='com.widevine.alpha'):
    """Indirizzo del server di licenza dentro il valore della pagina (elenco 'sistema|indirizzo;sistema|indirizzo')."""
    for parte in (v or '').split(';'):
        if parte.lower().startswith(sistema) and '|' in parte:
            return parte.split('|', 1)[1]
    return v if (v or '').startswith('http') else ''


def condizione_ok(c, url, valori):
    if not c:
        return True
    if c[0] == 'percorso':
        return c[1] in url
    if c[0] == 'chiave':
        return valori.get(c[1]) == c[2]
    return True


def indirizzo_token(tk, valori):
    base = applica(tk['base'], valori)
    if not base:
        return None
    q = []
    for k, v in tk['param']:
        x = valori.get(v[1]) if v[0] == 'chiave' else v[1]
        if x is None:
            return None
        q.append('%s=%s' % (k, x))
    return base + ('?' + '&'.join(q) if q else '')


RICETTE_VIDEO = [{'token': {'base': [('chiave', 'drmTokenEndpoint', 'id')],
            'param': [('id', ('chiave', 'drmContentId')), ('contentType', ('lett', 'LIVE'))],
            'campo': 'preAuthToken'},
  'licenza': 'drmLicenseServer',
  'manifest': [('chiave', 'mainLiveUrl', 'prima')],
  'campioni': 1,
  'riprodotti': 1,
  'esempio': 'https://www.la7play.it/dirette/la7',
  'condizione': ('chiave', 'isLiveBroadcast', 'true'),
  'intestazione': 'PreAuthorization'},
 {'token': {'base': [('chiave', 'drmTokenEndpoint', 'id')],
            'param': [('id', ('chiave', 'drmContentId')), ('contentType', ('lett', 'VOD'))],
            'campo': 'preAuthToken'},
  'licenza': 'drmLicenseServer',
  'manifest': [('chiave', 'hostnameCdnDrm', 'id'),
               ('chiave', 'cf_remote_url', 'id'),
               ('lett', '/DASH'),
               ('chiave', 'cf_remote_url', 'id'),
               ('lett', '.mpd')],
  'campioni': 1,
  'riprodotti': 1,
  'esempio': 'https://www.la7play.it/programmi',
  'condizione': ('chiave', 'drm', 'true'),
  'intestazione': 'PreAuthorization'},
 {'token': None,
  'licenza': None,
  'manifest': [('chiave', 'hostnameCdn', 'id'),
               ('lett', '/local/hls/,'),
               ('chiave', 'cf_remote_url', 'senza_mp4'),
               ('lett', ',.mp4.urlset/master.m3u8')],
  'campioni': 5,
  'riprodotti': 5,
  'esempio': 'https://www.la7play.it/documentari',
  'condizione': ('chiave', 'drm', 'false')}]
DRM_SISTEMA = 'com.widevine.alpha'


def _token_video(tk, valori):
    url = indirizzo_token(tk, valori)
    if not url:
        return ''
    try:
        j = json.loads(httptools.downloadpage(url, headers=headers).data)
    except Exception as e:
        logger.error('token non ottenuto %s' % e)
        return ''
    return j.get(tk['campo']) or j.get('preAuthToken') or j.get('token') or j.get('auth') or ''


def findvideos(item):
    support.info(item)
    valori = valori_pagina(_pagina(item.url))
    for ric in RICETTE_VIDEO:
        if not condizione_ok(ric.get('condizione'), item.url, valori):
            continue
        url = applica(ric['manifest'], valori)
        if not url:
            continue
        it = item.clone(title='Direct', server='directo', url=url, action='play')
        if ric.get('token'):
            token = _token_video(ric['token'], valori)
            licenza = licenza_url(valori.get(ric['licenza']), DRM_SISTEMA)
            if token and licenza:
                it.drm = DRM_SISTEMA
                it.license = '%s|%s=%s&Origin=%s&Referer=%s/|R{SSM}|' % (licenza, ric['intestazione'], token, host, host + '/')
        return support.server(it, itemlist=[it], Download=False, Videolibrary=False)
    return support.server(item, headers=headers)



@support.menu
def mainlist(item):
    top = [('Dirette', ['/dirette/la7', 'canali', '', 'movie']),
           ('Guida Tv e Rivedi', ['/guida-tv-rivedi/la7', 'canali', '', 'tvshow']),
           ('Programmi', ['/programmi', 'peliculas', '', 'movie']),
           ('Film', ['/film', 'peliculas', '', 'movie']),
           ('Documentari', ['/documentari', 'peliculas', '', 'movie']),
           ('Tg La7', ['/tgla7', 'episodios', '', 'movie']),
           ('Coffee Tech', ['/coffee-tech', 'episodios', '', 'movie'])]
    search = ''
    return locals()






