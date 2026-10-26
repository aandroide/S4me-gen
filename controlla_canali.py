#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
controlla_canali.py: controlla i canali S4Me scritti a mano (cartella canali_base) sui siti veri.

Per ogni canale con regex (@support.scrape):
  1. legge dal file i patron, patronBlock, patronNext e gli indirizzi del menu
  2. scarica le pagine del menu e applica le regex come fa support.scrape (stessa pulizia, stessi flag)
  3. se una regex non trova piu nulla, cerca i titoli con il riconoscimento delle card di s4me_gen.py,
     propone una regex nuova che mantiene i nomi dei gruppi e scrive il file corretto in correzioni/<canale>/

Non scrive mai nella repo dell'addon: i file corretti restano qui, da copiare a mano dopo la verifica.

Uso:
    python controlla_canali.py                  tutti i canali
    python controlla_canali.py serietvu eurostreaming
    python controlla_canali.py --senza-riparare
"""

import argparse
import ast
import concurrent.futures
import difflib
import json
import os
import re
import sys
import time
from urllib.parse import urlparse, urljoin

import requests
import urllib3
import warnings
urllib3.disable_warnings()
warnings.filterwarnings("ignore", category=SyntaxWarning)

import s4me_gen as g

QUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get('CANALI_BASE', os.path.join(QUI, 'canali_base'))
SNAP = os.environ.get('SNAPSHOT_API', os.path.join(QUI, 'snapshot_api'))
PROFILI = os.path.join(QUI, 'profili')
OUT = os.environ.get('CANALI_OUT', os.path.join(QUI, 'correzioni'))
UA = g.UA
NOMI_REGEX = ('patron', 'patronBlock', 'patronNext', 'patronMenu')
PARCHEGGIATO = re.compile(r'(domain (is )?for sale|domainname\.de/sale|sedo\.com|hugedomains|dominio in vendita|'
                          r'this domain (may be|is) for sale|parked (free|domain)|buy this domain|afternic)', re.I)
SALTA = {'__init__'}


# ---------------------------------------------------------------------------
# Lettura statica del canale
# ---------------------------------------------------------------------------

def valore_stringa(nodo):
    """Valore di un nodo ast che e una stringa o una somma di stringhe, altrimenti None."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        a, b = valore_stringa(nodo.left), valore_stringa(nodo.right)
        if a is not None and b is not None:
            return a + b
    return None


def posizioni(src):
    """Offset di inizio di ogni riga, per convertire (riga, colonna in byte) in posizione nel testo."""
    righe = src.splitlines(keepends=True)
    inizi, tot = [], 0
    for r in righe:
        inizi.append(tot)
        tot += len(r)
    return righe, inizi


def offset(righe, inizi, riga, col_byte):
    return inizi[riga - 1] + len(righe[riga - 1].encode('utf-8')[:col_byte].decode('utf-8', 'ignore'))


def usa_scrape(f):
    for d in f.decorator_list:
        n = d.attr if isinstance(d, ast.Attribute) else (d.id if isinstance(d, ast.Name) else '')
        if n == 'scrape':
            return True
    return False


def leggi_canale(src):
    """Funzioni con @support.scrape (con le loro regex) e voci di menu (indirizzo, funzione)."""
    tree = ast.parse(src)
    righe, inizi = posizioni(src)
    funzioni, menu = {}, []
    for f in tree.body:
        if not isinstance(f, ast.FunctionDef):
            continue
        if f.name == 'mainlist':
            for n in ast.walk(f):
                if isinstance(n, (ast.List, ast.Tuple)) and n.elts:
                    primo = valore_stringa(n.elts[0])
                    if primo is None:
                        continue
                    sec = valore_stringa(n.elts[1]) if len(n.elts) > 1 else None
                    for extra in n.elts[2:]:
                        ev = valore_stringa(extra)
                        if ev and ev.startswith('/') and not ev.startswith('//') and '{' not in ev and '%' not in ev:
                            menu.append((ev, 'json'))
                    if sec and re.fullmatch(r'[A-Za-z_]\w*', sec):
                        menu.append((primo, sec))
                    elif primo.startswith('/') and not primo.startswith('//'):
                        menu.append((primo, 'peliculas'))
            continue
        if not usa_scrape(f):
            continue
        d = {'patron': [], 'patronBlock': [], 'patronNext': [], 'patronMenu': [], 'flags': None}
        for n in ast.walk(f):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                nome = n.targets[0].id
                if nome in NOMI_REGEX:
                    v = valore_stringa(n.value)
                    ini = offset(righe, inizi, n.value.lineno, n.value.col_offset)
                    fin = offset(righe, inizi, n.value.end_lineno, n.value.end_col_offset)
                    d[nome].append({'valore': v, 'ini': ini, 'fin': fin, 'riga': n.lineno})
        funzioni[f.name] = d
    return funzioni, menu


def gruppi_di(patron):
    try:
        return set(re.compile(patron).groupindex)
    except re.error:
        return set()


# ---------------------------------------------------------------------------
# Rete
# ---------------------------------------------------------------------------

_cache = {}


def descrivi_errore(e):
    t = str(e)
    if 'NameResolution' in t or 'Name or service not known' in t or 'nodename nor servname' in t:
        return 'il nome del sito non esiste piu (DNS)'
    if 'Connection refused' in t:
        return 'connessione rifiutata dal server'
    if 'timed out' in t or 'Timeout' in type(e).__name__:
        return 'il sito non risponde (tempo scaduto)'
    if 'SSL' in t or 'certificate' in t:
        return 'errore del certificato HTTPS'
    if 'Connection reset' in t or 'RemoteDisconnected' in t or 'Connection aborted' in t:
        return 'connessione interrotta dal server (possibile blocco dei server di GitHub)'
    return t[:100]


def via_flaresolverr(url):
    """Pagina scaricata da FlareSolverr (un browser vero che supera la challenge di Cloudflare), una alla volta."""
    import fcntl
    ep = os.environ.get('FLARESOLVERR_URL', '').rstrip('/')
    if not ep:
        return None
    with open('/tmp/controlla_canali_flaresolverr.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                requests.post(ep + '/v1', json={'cmd': 'sessions.create', 'session': 'controllo'}, timeout=60)
            except Exception:
                pass
            r = requests.post(ep + '/v1', json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000, 'session': 'controllo'},
                              timeout=90).json()
        except Exception as e:
            return ('errore', '', url, 'FlareSolverr non raggiungibile: ' + str(e)[:60])
    if r.get('status') != 'ok':
        return ('cloudflare', '', url, 'FlareSolverr non ha superato la challenge: ' + str(r.get('message'))[:80])
    sol = r.get('solution', {})
    html = sol.get('response', '')
    if 'just a moment' in html[:5000].lower() or sol.get('status', 200) >= 400 and len(html) < 500:
        return ('cloudflare', '', sol.get('url', url), 'FlareSolverr: la challenge resta (HTTP %s)' % sol.get('status'))
    return ('ok', html[:1500000], sol.get('url', url), 'HTTP %s (FlareSolverr)' % sol.get('status'))


def scarica(url):
    """(stato, html, url finale, motivo). Stato: ok, cloudflare, errore."""
    if url in _cache:
        return _cache[url]
    ris = ('errore', '', url, 'non raggiungibile')
    for tentativo in range(2):
        try:
            r = requests.get(url, headers={'User-Agent': UA, 'Accept-Language': 'it-IT,it;q=0.9'}, timeout=(8, 15))
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e0:
            if 'SSL' not in str(e0) and 'certificate' not in str(e0):
                ris = ('errore', '', url, descrivi_errore(e0))
                time.sleep(2)
                continue
            try:
                r = requests.get(url, headers={'User-Agent': UA}, timeout=(8, 15), verify=False)
            except Exception as e:
                ris = ('errore', '', url, descrivi_errore(e))
                continue
        except Exception as e:
            ris = ('errore', '', url, descrivi_errore(e))
            time.sleep(2)
            continue
        t = r.text
        bassa = t[:20000].lower()
        if r.headers.get('cf-mitigated') == 'challenge' or 'just a moment' in bassa or \
                (r.status_code in (403, 503) and 'cloudflare' in (r.headers.get('server', '') + bassa).lower()):
            ris = ('cloudflare', '', r.url, 'protetto da Cloudflare, richiede il browser')
            fs = via_flaresolverr(url)
            if fs:
                ris = fs
            break
        if r.status_code >= 400 and len(t) < 500:
            ris = ('errore', '', r.url, 'HTTP %d' % r.status_code)
            break
        ris = ('ok', t[:1500000], r.url, 'HTTP %d' % r.status_code)
        break
    _cache[url] = ris
    return ris


# ---------------------------------------------------------------------------
# Prova delle regex come fa support.scrape
# ---------------------------------------------------------------------------

def uniforma(html):
    return g.normalizza(html)


def prova(patron, testo, flags=re.IGNORECASE):
    try:
        ms = [m.groupdict() for m in re.finditer(patron, testo, flags)]
    except re.error as e:
        return None, 'regex non valida: ' + str(e)
    return ms, ''


def prova_pagina(fn, html_norm):
    """Prova tutte le varianti di patronBlock e patron della funzione sulla pagina."""
    blocchi_testo = None
    risultati = {'blocchi': None, 'match': 0, 'varianti_ok': [], 'esempi': []}
    if fn['patronBlock']:
        blocchi_testo = []
        for b in fn['patronBlock']:
            if b['valore'] is None:
                continue
            ms, err = prova(b['valore'], html_norm)
            if ms:
                blocchi_testo += [m.get('block', '') for m in ms if m.get('block') is not None]
        risultati['blocchi'] = len(blocchi_testo)
    testi = blocchi_testo if blocchi_testo else ([html_norm] if not fn['patronBlock'] else [])
    for i, p in enumerate(fn['patron']):
        if p['valore'] is None:
            continue
        tot = 0
        for t in testi:
            ms, err = prova(p['valore'], t)
            if ms:
                tot += len(ms)
                if not risultati['esempi']:
                    risultati['esempi'] = ms[:2]
        if tot:
            risultati['varianti_ok'].append(i)
            risultati['match'] += tot
    return risultati


# ---------------------------------------------------------------------------
# Riparazione
# ---------------------------------------------------------------------------

def proponi_patron(html, html_norm, vecchi):
    """Regex nuova dal riconoscimento delle card. Ritorna (patron, n, perse, nota) oppure None."""
    soup = g.soup_di(html)
    card = g.trova_card(soup)
    if not card:
        return None
    patron = g.costruisci_patron(card[len(card) // 2])
    if not patron:
        return None
    n, esempi, err = g.collauda(patron, html_norm)
    if err or n < max(3, int(0.6 * len(card))):
        return None
    nuovi = gruppi_di(patron)
    richiesti = set().union(*[gruppi_di(v['valore']) for v in vecchi if v['valore']]) if vecchi else set()
    perse = sorted(richiesti - nuovi - {'block'})
    return {'patron': patron, 'n': n, 'card': len(card), 'perse': perse, 'esempi': esempi}


def applica(src, sostituzioni):
    """Sostituzioni [(ini, fin, testo)] sul sorgente, dall'ultima alla prima."""
    for ini, fin, t in sorted(sostituzioni, reverse=True):
        src = src[:ini] + t + src[fin:]
    return src


# ---------------------------------------------------------------------------
# Controllo di un canale
# ---------------------------------------------------------------------------

CERCA = {}  # canali con findhost: nome -> indirizzo di partenza (sezione findhost di channels.json)


def host_di(nome, hosts):
    h = hosts.get(nome)
    if not h:
        return ''
    p = urlparse(h)
    return '{}://{}'.format(p.scheme or 'https', p.netloc)


class _Risp:
    def __init__(self, url, data, headers, code):
        self.url, self.data, self.headers, self.code = url, data, headers, code


class _Match:
    def __init__(self, data, match):
        self.data, self.match = data, match


class _Support:
    class scrapertools:
        @staticmethod
        def find_single_match(data, patron, index=0):
            m = re.search(patron, data, flags=re.DOTALL)
            if not m:
                return ''
            return m.group(1) if len(m.groups()) == 1 else (m.groups() if m.groups() else m.group())

    @staticmethod
    def match(url, **a):
        data = scarica(url)[1] if isinstance(url, str) and url.startswith('http') else str(url)
        data = uniforma(data)  # support.match fa html_uniform sulla pagina
        patron = a.get('patron')
        m = ''
        if patron:
            trovati = re.findall(patron, data, re.DOTALL)
            m = trovati[0] if trovati else ''
        return _Match(data, m)


class _Http:
    @staticmethod
    def downloadpage(url, **a):
        seg = a.get('follow_redirects', a.get('follow_redirect', True))
        r = requests.get(url, headers={'User-Agent': UA}, allow_redirects=bool(seg), timeout=(8, 15), verify=False)
        return _Risp(r.url, r.text, {k.lower(): v for k, v in r.headers.items()}, r.status_code)


def host_da_findhost(src, partenza):
    """Esegue la funzione findhost del canale (con rete vera) e ritorna l'indirizzo del sito, oppure ''."""
    tree = ast.parse(src)
    for f in tree.body:
        if isinstance(f, ast.FunctionDef) and f.name == 'findhost':
            codice = ast.get_source_segment(src, f)
            ns = {'re': re, 'support': _Support, 'httptools': _Http, 'scrapertools': _Support.scrapertools,
                  'config': None, 'logger': None}
            exec(codice, ns)
            try:
                r = ns['findhost'](partenza)
            except Exception as e:
                return '', descrivi_errore(e)
            if isinstance(r, (tuple, list)):
                r = r[0]
            r = (r or '').strip()
            return (r.rstrip('/'), '') if r.startswith('http') else ('', 'findhost non restituisce un indirizzo (pagina cambiata?)')
    return '', ''


def host_letterale(src):
    m = re.search(r'^host\s*=\s*[\'"](https?://[^\'"]+)[\'"]', src, re.M)
    return m.group(1).rstrip('/') if m else ''


# ---------------------------------------------------------------------------
# Canali che usano API o pagine con dati (senza regex)
# ---------------------------------------------------------------------------

RUMORE_URL = re.compile(r'(images?\.|img\.|/static/|\.(png|jpe?g|gif|webp|svg|m3u8|mpd|ts)(\?|$)|ip-api\.com|thaudray|'
                        r'googleapis\.com/youtube|gdata\.|theplatform\.com/data|license|/kenc|widevine)', re.I)


def impronta(obj, prefisso='', prof=0, out=None):
    """Insieme dei percorsi delle chiavi di una risposta JSON (le liste contano come un elemento)."""
    out = set() if out is None else out
    if len(out) > 600 or prof > 7:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = prefisso + '.' + str(k) if prefisso else str(k)
            out.add(p)
            impronta(v, p, prof + 1, out)
    elif isinstance(obj, list):
        for x in obj[:3]:
            impronta(x, prefisso + '[]', prof + 1, out)
    return out


def chiavi_usate(src):
    """Nomi di chiave che il canale legge: x['nome'] e x.get('nome')."""
    usate = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return usate
    for n in ast.walk(tree):
        if isinstance(n, ast.Subscript):
            sl = n.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                usate.add(sl.value)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get' and n.args:
            if isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                usate.add(n.args[0].value)
    return usate


def costanti(src):
    """Stringhe assegnate a livello di modulo (host, api_url...), anche concatenate tra loro."""
    env = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return env
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            v = valore_env(n.value, env)
            if v is not None:
                env[n.targets[0].id] = v
    return env


def valore_env(nodo, env):
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.Name):
        return env.get(nodo.id)
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        a, b = valore_env(nodo.left, env), valore_env(nodo.right, env)
        if a is not None and b is not None:
            return a + b
    return None


def url_da_espressioni(src, host):
    """Indirizzi completi costruiti con costanti del modulo (per esempio api_url + '/getLivestream?id=7')."""
    env = costanti(src)
    if host:
        env.setdefault('host', host)
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.BinOp):
            v = valore_env(n, env)
            if v and re.match(r'https?://', v):
                out.append(v)
    return out


def url_statici(src, host, menu):
    """Indirizzi del canale che si possono chiamare senza parametri: menu e indirizzi scritti per intero."""
    out = []
    for rel, azione in menu:
        if rel and rel.startswith('/') and '%' not in rel and '{' not in rel:
            out.append(urljoin(host + '/', rel))
    out += url_da_espressioni(src, host)
    for m in re.finditer(r"['\"](https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+)['\"]", src):
        u = m.group(1)
        if u.endswith('=') or '%' in u or '{' in u or RUMORE_URL.search(u):
            continue
        out.append(u)
    visti, ris = set(), []
    for u in out:
        if u not in visti and len(u) < 300:
            visti.add(u)
            ris.append(u)
    return ris[:10]


def leggi_risposta(testo):
    """(tipo, struttura) di una risposta: json, pagina Inertia oppure html."""
    t = (testo or '').lstrip()
    if t[:1] in '{[':
        try:
            return 'json', json.loads(t)
        except Exception:
            pass
    dp = g.inertia_da_html(testo)
    if dp is not None:
        props = {k: v for k, v in dp.get('props', {}).items() if k not in ('auth', 'flash', 'errors', 'ziggy', 'locale', 'locales')}
        return 'inertia', props
    return 'html', None


def snapshot_path(nome):
    return os.path.join(SNAP, nome + '.json')


def verifica_profilo(nome, host, ris):
    """Controlli scritti a mano (profili/<nome>.json) per i siti con pagine Inertia: percorsi e campi attesi."""
    pf = os.path.join(PROFILI, nome + '.json')
    if not os.path.exists(pf):
        return None
    prof = json.load(open(pf, encoding='utf-8'))
    problemi = 0

    def pagina(rel):
        st, html, fin, mot = scarica(urljoin(host + '/', rel))
        if st != 'ok':
            return None, mot
        dp = g.inertia_da_html(html)
        return dp, ('' if dp else 'pagina senza dati Inertia')

    for c in prof.get('controlli', []):
        dp, err = pagina(c['url'])
        lista = g.leggi(dp, c['percorso']) if dp else None
        if not isinstance(lista, list) or not lista:
            problemi += 1
            ris['dettagli'].append('PROBLEMA: %s | %s non trova %s %s' % (c['nome'], c['url'], c['percorso'], err))
            continue
        if isinstance(lista[0], list):
            lista = [x for sub in lista for x in sub]
        el = lista[0] if isinstance(lista[0], dict) else {}
        mancano = [k for k in c.get('campi', []) if k not in el]
        if mancano:
            problemi += 1
            ris['dettagli'].append('PROBLEMA: %s | campi mancanti: %s | presenti: %s' % (c['nome'], mancano, sorted(el)[:20]))
        else:
            ris['dettagli'].append('OK: %s | %d titoli in %s' % (c['nome'], len(lista), c['percorso']))
    sr = prof.get('serie')
    if sr:
        dp, err = pagina(sr['da'])
        tit = [x for x in (g.leggi(dp, 'props.titles') or []) if isinstance(x, dict) and x.get('slug') and x.get('id')] if dp else []
        if not tit:
            problemi += 1
            ris['dettagli'].append('PROBLEMA: nessuna serie trovata in %s per provare stagioni ed episodi' % sr['da'])
        else:
            u = '/it/titles/%s-%s' % (tit[0]['id'], tit[0]['slug'])
            dp, err = pagina(u)
            stg = g.leggi(dp, sr['percorso_stagioni']) if dp else None
            if not isinstance(stg, list) or not stg:
                problemi += 1
                ris['dettagli'].append('PROBLEMA: stagioni non trovate in %s (%s)' % (u, sr['percorso_stagioni']))
            else:
                u2 = u + sr['stagione_url'].format(S=stg[0].get('number', 1))
                dp2, err = pagina(u2)
                eps = g.leggi(dp2, sr['percorso_episodi']) if dp2 else None
                if not isinstance(eps, list) or not eps:
                    problemi += 1
                    ris['dettagli'].append('PROBLEMA: episodi non trovati in %s' % u2)
                else:
                    mc = [k for k in sr['campi_stagione'] if k not in stg[0]]
                    me = [k for k in sr['campi_episodio'] if k not in eps[0]]
                    if mc or me:
                        problemi += 1
                        ris['dettagli'].append('PROBLEMA: campi mancanti | stagione: %s | episodio: %s' % (mc, me))
                    else:
                        ris['dettagli'].append('OK: serie di esempio %s | %d stagioni, %d episodi nella prima' % (u, len(stg), len(eps)))
    return problemi


# indirizzi di prova noti per canali a API senza indirizzo in channels.json
EXTRA_API = {
    'thepiratebay': ['https://apibay.org/q.php?q=matrix'],
    'tunein': ['https://opml.radiotime.com/Tune.ashx?render=json&id=s24939'],
}


def controlla_api(nome, src, host, menu, ris):
    """Canale senza regex: raggiungibilita, struttura dei dati e confronto con la rilevazione precedente."""
    if not host and nome in EXTRA_API:
        host = 'https://' + urlparse(EXTRA_API[nome][0]).netloc
        ris['host'] = host
    if not host:
        ris.update(stato='SENZA INDIRIZZO', dettagli=['canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file'])
        return ris
    st, html, finale, motivo = scarica(host + '/')
    if st != 'ok':
        # molte API rispondono solo agli indirizzi giusti: la home non basta per dire che e morto, se non e un errore di rete
        if st == 'errore' and ('DNS' in motivo or 'rifiutata' in motivo):
            ris.update(stato='IRRAGGIUNGIBILE', dettagli=['%s (%s)' % (motivo, host)])
            return ris
        ris['dettagli'].append('home %s: %s' % (host, motivo))
    problemi = 0
    p = verifica_profilo(nome, host, ris)
    if p is not None:
        problemi += p
    usate = chiavi_usate(src)
    try:
        vecchio = json.load(open(snapshot_path(nome), encoding='utf-8'))
    except Exception:
        vecchio = None
    nuovo = {}
    controllati = 0
    for u in list(url_statici(src, host, menu)) + EXTRA_API.get(nome, []):
        if p is not None and u.startswith(host):
            continue  # gia coperto dai controlli del profilo
        st, testo, fin, mot = scarica(u)
        if st != 'ok':
            nuovo[u] = {'stato': st, 'motivo': mot}
            prima = (vecchio or {}).get(u)
            if prima and prima.get('stato') == 'ok':
                problemi += 1
                ris['dettagli'].append('PROBLEMA: %s rispondeva e ora no (%s)' % (u[:90], mot))
            else:
                ris['dettagli'].append('non controllabile senza parametri: %s (%s)' % (u[:90], mot))
            continue
        tipo, dati = leggi_risposta(testo)
        controllati += 1
        voce = {'stato': 'ok', 'tipo': tipo}
        if dati is not None:
            voce['chiavi'] = sorted(impronta(dati))
        else:
            voce['dimensione'] = len(testo)
        nuovo[u] = voce
        prima = (vecchio or {}).get(u)
        if prima and prima.get('chiavi') and voce.get('chiavi') is not None:
            spariti = sorted(set(prima['chiavi']) - set(voce['chiavi']))
            lette = [k for k in spariti if k.split('.')[-1].replace('[]', '') in usate]
            if lette:
                problemi += 1
                ris['dettagli'].append('PROBLEMA: %s | chiavi sparite che il canale legge: %s' % (u[:90], ', '.join(lette[:8])))
            elif spariti:
                ris['dettagli'].append('attenzione: %s | chiavi sparite (non lette dal canale): %s' % (u[:90], ', '.join(spariti[:6])))
            else:
                ris['dettagli'].append('OK: %s | %s, struttura invariata' % (u[:90], tipo))
        elif prima and prima.get('tipo') != tipo:
            problemi += 1
            ris['dettagli'].append('PROBLEMA: %s | il tipo di risposta e cambiato da %s a %s' % (u[:90], prima.get('tipo'), tipo))
        else:
            ris['dettagli'].append('OK: %s | %s%s' % (u[:90], tipo, ' (prima rilevazione, riferimento salvato)' if not vecchio else ''))
    if nuovo and controllati:
        os.makedirs(SNAP, exist_ok=True)
        unito = dict(vecchio or {})
        unito.update(nuovo)
        json.dump(unito, open(snapshot_path(nome), 'w', encoding='utf-8'), indent=0, ensure_ascii=False, sort_keys=True)
    if not controllati and p is None:
        ris['stato'] = 'NON VERIFICATO'
        ris['dettagli'].append('nessun indirizzo controllabile senza parametri o accessi: canale a API con login o dati dinamici')
    else:
        ris['stato'] = 'ROTTO' if problemi else 'OK'
    return ris


def controlla(nome, hosts, ripara=True):
    ris = {'canale': nome, 'stato': '', 'dettagli': [], 'correzione': False, 'host': host_di(nome, hosts)}
    percorso = os.path.join(BASE, nome + '.py')
    src = open(percorso, encoding='utf-8').read()
    try:
        funzioni, menu = leggi_canale(src)
    except SyntaxError as e:
        ris.update(stato='NON ANALIZZABILE', dettagli=['il file non e leggibile da Python 3: %s' % e])
        return ris
    host = ris['host']
    if nome in CERCA and 'def findhost' in src:
        partenza = CERCA[nome]
        host, errore = host_da_findhost(src, partenza)
        if not host:
            ris.update(stato='IRRAGGIUNGIBILE', dettagli=['findhost non ha dato un indirizzo partendo da %s: %s' % (partenza, errore)])
            return ris
        ris['host'] = host
        ris['dettagli'].append('indirizzo ricavato dalla funzione findhost del canale: %s (partenza %s)' % (host, partenza))
    if not host:
        letterale = host_letterale(src)
        if letterale:
            host = ris['host'] = letterale
            ris['dettagli'].append('indirizzo scritto nel canale: %s' % letterale)
    if not host:
        ris.update(stato='SENZA INDIRIZZO', dettagli=['canale non attivo: non e in channels.json e non ha un indirizzo fisso nel file'])
        return ris
    if not funzioni:
        return controlla_api(nome, src, host, menu, ris)

    # pagine da provare: indirizzi del menu per le funzioni con regex
    prove = []
    visti = set()
    for url, azione in menu:
        if azione in funzioni and funzioni[azione]['patron'] and url and (azione, url) not in visti:
            visti.add((azione, url))
            prove.append((azione, url))
    if not prove:
        # nessun indirizzo fisso nel menu: si prova la home con la prima funzione che ha regex
        for azione, fn in funzioni.items():
            if fn['patron']:
                prove.append((azione, '/'))
                break
    prove = prove[:4]
    cartella_pagine = os.path.join(OUT, nome)

    # la home dice se il sito e raggiungibile, parcheggiato o spostato
    st, html, finale, motivo = scarica(host + '/')
    if st != 'ok':
        ris.update(stato='IRRAGGIUNGIBILE' if st == 'errore' else 'CLOUDFLARE', dettagli=['%s (%s)' % (motivo, host)])
        return ris
    mp = PARCHEGGIATO.search(html[:60000])
    n_link = len(g.soup_di(html).find_all('a', href=True))
    if mp or (n_link < 3 and len(html) < 4000):
        tit = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        ris.update(stato='DOMINIO PARCHEGGIATO', dettagli=[
            'la home di %s sembra un dominio in vendita o vuoto | motivo: %s | link: %d | dimensione: %d | titolo: %s' % (
                host, ('frase "%s"' % mp.group(0)) if mp else 'pagina quasi vuota', n_link, len(html),
                (tit.group(1).strip()[:80] if tit else 'nessuno'))])
        return ris
    if 'FlareSolverr' in motivo:
        ris['dettagli'].append('sito protetto da Cloudflare: pagine scaricate con FlareSolverr')
    if 'FlareSolverr' in motivo:
        prove = prove[:3]
    nuovo = '{}://{}'.format(urlparse(finale).scheme, urlparse(finale).netloc)
    if urlparse(finale).netloc.replace('www.', '') != urlparse(host).netloc.replace('www.', ''):
        ris['dettagli'].append('il sito reindirizza a un altro indirizzo: %s (in channels.json c\'e %s)' % (nuovo, host))
        ris['nuovo_host'] = nuovo

    sostituzioni = []
    problemi = 0
    ok = 0
    for azione, rel in prove:
        fn = funzioni[azione]
        url = urljoin(host + '/', rel)
        st, html, finale, motivo = scarica(url)
        if st != 'ok':
            ris['dettagli'].append('%s %s: pagina non scaricata (%s)' % (azione, rel, motivo))
            continue
        norm = uniforma(html)
        r = prova_pagina(fn, norm)
        if r['match']:
            ok += 1
            ris['dettagli'].append('OK: %s %s | %d risultati' % (azione, rel, r['match']))
            nxt = fn['patronNext']
            if nxt and nxt[0]['valore']:
                m = re.search(nxt[0]['valore'], norm, re.I)
                if not m:
                    ris['dettagli'].append('attenzione: %s %s, patronNext non trova la pagina successiva (puo essere l\'ultima pagina)' % (azione, rel))
            continue
        problemi += 1
        # regex rotta: si cerca una sostituta
        if r['blocchi'] == 0 and fn['patronBlock']:
            causa = 'patronBlock non trova nessun blocco'
        elif fn['patronBlock']:
            causa = 'patronBlock trova %d blocchi ma patron non trova titoli' % r['blocchi']
        else:
            causa = 'patron non trova titoli'
        ris['dettagli'].append('ROTTO: %s %s | %s' % (azione, rel, causa))
        try:
            prop = g.con_timeout(45, proponi_patron, html[:500000], norm, fn['patron'])
        except BaseException as ex:
            prop = None
            ris['dettagli'].append('  ricerca della regex sostitutiva interrotta dopo 45 secondi (pagina troppo grande)')
        # campione della pagina, per capire a mano cosa e cambiato
        try:
            os.makedirs(cartella_pagine, exist_ok=True)
            nf = 'pagina_%s_%s.html' % (azione, re.sub(r'\W+', '_', rel).strip('_')[:40] or 'home')
            open(os.path.join(cartella_pagine, nf), 'w', encoding='utf-8').write(html[:250000])
            ris['dettagli'].append('  campione della pagina salvato in correzioni/%s/%s' % (nome, nf))
        except Exception:
            pass
        if not prop:
            ris['dettagli'].append('  nessuna regex sostitutiva trovata automaticamente in %s' % rel)
            continue
        ris['dettagli'].append('  regex proposta: %d titoli su %d card%s' % (
            prop['n'], prop['card'], (' | gruppi persi: ' + ', '.join(prop['perse'])) if prop['perse'] else ''))
        ris.setdefault('proposte', []).append({'funzione': azione, 'pagina': rel, 'patron': prop['patron'],
                                               'esempi': prop['esempi'], 'perse': prop['perse']})
        if ripara and len(fn['patron']) == 1 and fn['patron'][0]['valore'] is not None and not prop['perse']:
            sostituzioni.append((fn['patron'][0]['ini'], fn['patron'][0]['fin'], g.raw(prop['patron'])))
            if fn['patronBlock']:
                # il blocco non serve piu se la nuova regex lavora sull'intera pagina
                for b in fn['patronBlock']:
                    if b['valore'] is not None and r['blocchi'] == 0:
                        sostituzioni.append((b['ini'], b['fin'], "''"))
            nx = fn['patronNext']
            if len(nx) == 1 and nx[0]['valore'] and not re.search(nx[0]['valore'], norm, re.I):
                try:
                    nuovo_next = g.trova_next(g.soup_di(html))[0]
                except Exception:
                    nuovo_next = ''
                if nuovo_next and nuovo_next.count('|<a ') == 1 and 'rel="next"' in nuovo_next:
                    nuovo_next = r'<a (?=[^>]*rel="next")[^>]*?href="([^"]+)"'  # un solo gruppo, come si aspetta nextPage
                if nuovo_next and re.compile(nuovo_next).groups == 1 and re.search(nuovo_next, norm, re.I):
                    sostituzioni.append((nx[0]['ini'], nx[0]['fin'], g.raw(nuovo_next)))
                    ris['dettagli'].append('  patronNext sostituito (il vecchio non trovava la pagina successiva)')
        elif ripara:
            ris['dettagli'].append('  non applicata al file: %s' % (
                'la funzione ha piu varianti di regex' if len(fn['patron']) != 1 else
                'perderebbe i gruppi ' + ', '.join(prop['perse']) if prop['perse'] else 'regex dinamica'))

    if problemi == 0 and ok:
        ris['stato'] = 'OK'
    elif ok == 0 and problemi == 0:
        ris['stato'] = 'NON VERIFICATO'
    elif sostituzioni:
        nuovo_src = applica(src, sostituzioni)
        try:
            ast.parse(nuovo_src)
        except SyntaxError as e:
            ris['stato'] = 'ROTTO'
            ris['dettagli'].append('correzione scartata: il file risultante non e valido (%s)' % e)
            return ris
        cartella = os.path.join(OUT, nome)
        os.makedirs(cartella, exist_ok=True)
        open(os.path.join(cartella, nome + '.py'), 'w', encoding='utf-8').write(nuovo_src)
        diff = ''.join(difflib.unified_diff(src.splitlines(True), nuovo_src.splitlines(True),
                                            'canali_base/%s.py' % nome, 'correzioni/%s/%s.py' % (nome, nome)))
        open(os.path.join(cartella, nome + '.diff'), 'w', encoding='utf-8').write(diff)
        # verifica del file corretto sulle stesse pagine
        f2, _ = leggi_canale(nuovo_src)
        buone = 0
        for azione, rel in prove:
            st, html, finale, motivo = scarica(urljoin(host + '/', rel))
            if st == 'ok' and prova_pagina(f2[azione], uniforma(html))['match']:
                buone += 1
        ris['dettagli'].append('file corretto scritto in correzioni/%s: %d pagine su %d ora trovano titoli' % (nome, buone, len(prove)))
        ris['stato'] = 'CORRETTO' if buone >= ok + 1 else 'ROTTO'
        ris['correzione'] = ris['stato'] == 'CORRETTO'
    else:
        ris['stato'] = 'ROTTO'
    return ris


# ---------------------------------------------------------------------------

def carica_hosts():
    d = json.load(open(os.path.join(BASE, 'channels.json.txt'), encoding='utf-8'))
    CERCA.update({k: v for k, v in d.get('findhost', {}).items() if isinstance(v, str) and v.startswith('http')})
    out = {}
    for sez in ('direct', 'findhost'):
        for k, v in (d.get(sez) or {}).items():
            if isinstance(v, str) and v.startswith('http'):
                out.setdefault(k, v)
    return out


def riepilogo(risultati):
    ordine = ['CORRETTO', 'ROTTO', 'DOMINIO PARCHEGGIATO', 'IRRAGGIUNGIBILE', 'CLOUDFLARE', 'NON VERIFICATO', 'OK',
              'NON REGEX', 'SENZA INDIRIZZO', 'NON ANALIZZABILE', 'TEMPO SCADUTO', 'ERRORE']
    r = ['# Controllo dei canali', '']
    conta = {}
    for x in risultati:
        conta[x['stato']] = conta.get(x['stato'], 0) + 1
    r.append('Riepilogo: ' + ', '.join('%s %d' % (k, conta[k]) for k in ordine if k in conta))
    r.append('')
    for st in ordine:
        gruppo = [x for x in risultati if x['stato'] == st]
        if not gruppo:
            continue
        r.append('## %s (%d)' % (st, len(gruppo)))
        r.append('')
        for x in gruppo:
            r.append('### %s' % x['canale'])
            r.append('Sito: %s' % (x['host'] or 'n.d.'))
            for dtt in x['dettagli']:
                r.append('- ' + dtt)
            if x.get('nuovo_host'):
                r.append('- riga per channels.json: "%s": "%s",' % (x['canale'], x['nuovo_host']))
            r.append('')
    return '\n'.join(r) + '\n'


def lavora(nome, hosts, ripara, coda):
    try:
        coda.put(controlla(nome, hosts, ripara))
    except BaseException as e:
        coda.put({'canale': nome, 'stato': 'ERRORE', 'dettagli': ['errore interno: %s' % str(e)[:200]], 'host': host_di(nome, hosts),
                  'correzione': False})


def esegui(nomi, hosts, ripara, processi, tempo):
    """Un processo per canale: se un sito o un'analisi si blocca, il canale e segnato e si va avanti."""
    import multiprocessing as mp
    ctx = mp.get_context('fork')
    attesa, attivi, risultati = list(nomi), {}, {}
    while attesa or attivi:
        while attesa and len(attivi) < processi:
            n = attesa.pop(0)
            q = ctx.Queue()
            pr = ctx.Process(target=lavora, args=(n, hosts, ripara, q), daemon=True)
            pr.start()
            attivi[n] = (pr, q, time.time())
        time.sleep(0.5)
        for n in list(attivi):
            pr, q, t0 = attivi[n]
            try:
                r = q.get_nowait()
                risultati[n] = r
            except Exception:
                if time.time() - t0 > tempo:
                    risultati[n] = {'canale': n, 'stato': 'TEMPO SCADUTO', 'host': host_di(n, hosts), 'correzione': False,
                                    'dettagli': ['il controllo di questo canale ha superato %d secondi (sito lento o pagina enorme)' % tempo]}
                elif not pr.is_alive():
                    try:
                        risultati[n] = q.get(timeout=2)
                    except Exception:
                        risultati[n] = {'canale': n, 'stato': 'ERRORE', 'host': host_di(n, hosts), 'correzione': False,
                                        'dettagli': ['il processo si e fermato senza risultato']}
                else:
                    continue
            if pr.is_alive():
                pr.kill()
            del attivi[n]
            print('%s: %s' % (n, risultati[n]['stato']), flush=True)
    return [risultati[n] for n in nomi]


def main():
    ap = argparse.ArgumentParser(description='Controlla i canali S4Me sui siti veri e prepara le correzioni')
    ap.add_argument('canali', nargs='*', help='nomi dei canali (vuoto: tutti)')
    ap.add_argument('--senza-riparare', action='store_true')
    ap.add_argument('--processi', type=int, default=6)
    ap.add_argument('--tempo', type=int, default=150, help='secondi massimi per canale')
    a = ap.parse_args()
    hosts = carica_hosts()
    nomi = a.canali or sorted(f[:-3] for f in os.listdir(BASE) if f.endswith('.py') and f[:-3] not in SALTA
                              and not f.startswith('0example'))
    os.makedirs(OUT, exist_ok=True)
    risultati = esegui(nomi, hosts, not a.senza_riparare, a.processi, a.tempo)
    testo = riepilogo(risultati)
    open(os.path.join(OUT, 'RAPPORTO.md'), 'w', encoding='utf-8').write(testo)
    json.dump(risultati, open(os.path.join(OUT, 'stato.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(testo)
    # codice di uscita 0 sempre: l'esito sta nel rapporto


if __name__ == '__main__':
    main()
