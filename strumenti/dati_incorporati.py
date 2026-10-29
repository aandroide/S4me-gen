# -*- coding: utf-8 -*-
"""
dati_incorporati.py: legge le liste di titoli che le pagine moderne (Next.js, JSON-LD) incorporano nel codice.

Quando le regex sull'html non servono piu perche il sito ha cambiato struttura, i titoli, i link, le immagini e le
trame stanno quasi sempre dentro un blocco di dati della pagina (self.__next_f.push, __NEXT_DATA__, JSON-LD).
Questo modulo trova la lista piu grande e omogenea, riconosce i campi (titolo, link, immagine, trama, orario) e,
se i record sono raggruppati (per esempio puntate dentro un giorno), anche il gruppo.

Le funzioni che iniziano con "_" e sono elencate in PARTI_CANALE vengono copiate nel canale corretto, cosi il
canale non dipende da questo file. Il resto serve solo al controllo.
"""
import html as _html
import inspect
import json
import re

TITOLO = ('titolo', 'title', 'name', 'nome', 'headline', 'label')
LINK = ('pathname', 'url', 'href', 'link', 'permalink', 'path')
IMMAGINE = ('immagine_scena', 'immagine', 'image', 'img', 'thumbnail', 'thumb', 'poster', 'cover', 'immagine_programma',
            'immagine_cover', 'picture')
TRAMA = ('sinossi', 'plot', 'description', 'descrizione', 'abstract', 'occhiello', 'synopsis', 'summary')
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
        if len(dizionari) >= 3:
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
                    if len(rec) > sum(len(r) for _, r in migliore):
                        migliore = [('', rec)]
    return migliore


def _unisci(base, u):
    if u.startswith('http'):
        return u
    if u.startswith('//'):
        return 'https:' + u
    return base.rstrip('/') + '/' + u.lstrip('/')


PARTI_CANALE = (_testi, _oggetti, _scegli, _liste, _spacchetta, _etichetta, _record, _trova, _unisci)


def codice_helper():
    """Sorgente da copiare nel canale corretto (usa solo json, re e html)."""
    righe = ['import html as _html', 'import json', 'import re', '', '']
    righe += [inspect.getsource(f).rstrip() + '\n\n' for f in PARTI_CANALE]
    return '\n'.join(righe)


# ---------------------------------------------------------------------------
# Parte del controllo: riconosce la firma da una pagina
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
                            if n >= 3 and len(gruppi) >= 2 and (not migliore or (n, len(firma2)) > (migliore['n'], len(migliore['firma']))):
                                migliore = {'firma': firma2, 'gruppi': gruppi, 'n': n}
                            break
                firma = _riconosci(lista)
                if firma:
                    gruppi = _trova(h, firma)
                    n = sum(len(r) for _, r in gruppi)
                    # a parita di elementi, una lista con gruppi vale di piu: gia gestita sopra
                    if n >= 3 and (not migliore or (not migliore['firma'].get('gruppo') and (n, len(firma)) > (migliore['n'], len(migliore['firma'])))):
                        migliore = {'firma': firma, 'gruppi': gruppi, 'n': n}
    return migliore


# ---------------------------------------------------------------------------
# Generazione delle funzioni del canale
# ---------------------------------------------------------------------------

def _titolo_py(firma, nome_var):
    if firma.get('orario'):
        return "'%%s - %%s' %% (%s['orario'], %s['titolo']) if %s['orario'] else %s['titolo']" % ((nome_var,) * 4)
    return "%s['titolo']" % nome_var


def funzione_lista(nome, azione, firma):
    """Funzione senza gruppi: elenco piano di contenuti."""
    return '''def %(nome)s(item):
    itemlist = []
    h = httptools.downloadpage(item.url).data
    for etichetta, elenco in _trova(h, %(firma)r):
        for r in elenco:
            titolo = %(titolo)s
            itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=r['titolo'], show=r['titolo'],
                                       url=_unisci(host, r['url']), thumbnail=_unisci(host, r['immagine']) if r['immagine'] else '',
                                       fanart=_unisci(host, r['immagine']) if r['immagine'] else '', plot=r['trama'],
                                       action=%(azione)r, forcethumb=True))
    return itemlist
''' % {'nome': nome, 'azione': azione, 'firma': firma, 'titolo': _titolo_py(firma, 'r')}


def funzioni_gruppi(nome_menu, azione_menu, nome_figli, azione_figli, firma):
    """Coppia di funzioni: il menu dei gruppi (per esempio i giorni) e l'elenco dei contenuti del gruppo scelto."""
    menu = '''def %(nome)s(item):
    itemlist = []
    h = httptools.downloadpage(item.url).data
    for etichetta, elenco in _trova(h, %(firma)r):
        itemlist.append(item.clone(title=support.typo(etichetta, 'bold'), gruppo=etichetta, action=%(azione)r))
    return itemlist
''' % {'nome': nome_menu, 'azione': azione_menu, 'firma': firma}
    figli = '''def %(nome)s(item):
    itemlist = []
    h = httptools.downloadpage(item.url).data
    for etichetta, elenco in _trova(h, %(firma)r):
        if etichetta != item.gruppo:
            continue
        for r in elenco:
            titolo = %(titolo)s
            itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=r['titolo'], show=r['titolo'],
                                       url=_unisci(host, r['url']), thumbnail=_unisci(host, r['immagine']) if r['immagine'] else '',
                                       fanart=_unisci(host, r['immagine']) if r['immagine'] else '', plot=r['trama'],
                                       action=%(azione)r, forcethumb=True))
    return itemlist
''' % {'nome': nome_figli, 'azione': azione_figli, 'firma': firma, 'titolo': _titolo_py(firma, 'r')}
    return menu, figli
