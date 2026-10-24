#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s4me_gen.py: analizza un sito e prepara il canale per S4Me (file .py e .json).

Uso:
    python s4me_gen.py https://www.sito.it
    python s4me_gen.py https://www.sito.it --nome miosito --out canali
    python s4me_gen.py https://www.sito.it --mostra      (apre il browser visibile)

Requisiti:
    pip install playwright beautifulsoup4
    playwright install chromium

Cosa fa:
    1. apre il sito con un browser vero e registra tutte le chiamate di rete
    2. riconosce se i contenuti stanno nell'HTML (scraping con regex, decoratore support.scrape)
       oppure arrivano da un'API JSON o GraphQL
    3. apre il primo titolo, prova la ricerca e prova a far partire il video
    4. scrive <id>.py, <id>.json, la riga per channels.json e un rapporto con cio che va controllato
"""

import argparse
import pprint
import faulthandler
import signal
import json
import os
import re
import sys
import time
from urllib.parse import urlparse, urljoin, urlsplit, urlunsplit, parse_qsl, urlencode, quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

TITOLO_KEYS = ['title', 'name', 'titolo', 'nome', 'label', 'original_title', 'originalTitle']
ID_KEYS = ['slug', 'id', 'uuid', 'fullPath', 'full_path', 'permalink', 'url', 'href', 'link', 'path']
RUMORE = re.compile(r'(sentry|usercentrics|doubleclick|googletagmanager|google-analytics|tw\.cx|facebook|hotjar)', re.I)
LOGO_RE = re.compile(r'(logo|icon|avatar|flag|sprite|badge|favicon)', re.I)
IMG_RE = re.compile(r'(poster|image|img|thumb|cover|picture|locandina|foto|backdrop)', re.I)
ANNO_RE = re.compile(r'(year|anno|release|date)', re.I)
PLOT_RE = re.compile(r'(plot|desc|overview|synopsis|trama|summary|abstract)', re.I)
PAGE_KEYS = ['page', 'p', 'pg', 'paged', 'pagina', 'pageNumber']
OFFSET_KEYS = ['offset', 'start', 'skip', 'from']
SKIP_NAV = re.compile(r'(login|accedi|registr|contatt|privacy|dmca|cookie|termini|faq|chi siamo|about|'
                      r'richiest|segnala|telegram|facebook|twitter|instagram|whatsapp|youtube|home)', re.I)
NO_RISORSE = re.compile(r'\.(png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|css|m4s|ts|mp4|js|map)(\?|$)', re.I)
PLAY_SELETTORI = ['button[aria-label*="lay" i]', '.vjs-big-play-button', '.jw-icon-display',
                  '[class*="play-button" i]', '[class*="btn-play" i]', '[class*="play" i] button',
                  'a[href*="watch" i]', 'a[href*="guarda" i]', 'button:has-text("Guarda")', 'a:has-text("Guarda")',
                  'button:has-text("Watch")', 'a:has-text("Watch")', 'video', '[class*="play" i]']


def log(*a):
    print('[s4me_gen]', *a, flush=True)


# ---------------------------------------------------------------------------
# 1. Cattura con il browser
# ---------------------------------------------------------------------------

def normalizza(html):
    """Stessa pulizia che support.scrape fa alla pagina prima di applicare le regex."""
    html = re.sub(r"='([^']+)'", r'="\1"', html)
    return re.sub(r"\s+|&nbsp;", " ", html)


# ---------------------------------------------------------------------------
# DNS over HTTPS (Cloudflare), come fa il resolver di S4Me
# ---------------------------------------------------------------------------
DOH = {'cloudflare': '1.0.0.1', 'google': '8.8.8.8'}
_doh_cache = {}


def doh_risolvi(host, server):
    """Risolve host con DoH (JSON). Ritorna un IPv4 o None."""
    import requests
    if host in _doh_cache:
        return _doh_cache[host]
    if re.match(r'^[\d.]+$', host) or host == 'localhost':
        return host
    try:
        r = requests.get('https://%s/dns-query' % server, params={'name': host, 'type': 'A'},
                         headers={'accept': 'application/dns-json'}, timeout=8)
        for a in r.json().get('Answer', []):
            if a.get('type') == 1:
                _doh_cache[host] = a['data']
                return a['data']
    except Exception:
        pass
    return None


def attiva_dns(nome):
    """Fa passare per DoH le richieste Python (requests). Ritorna il server usato o None."""
    server = DOH.get((nome or '').lower())
    if not server:
        return None
    import urllib3.util.connection as uc
    orig = uc.create_connection

    def conn(address, *a, **k):
        host, port = address
        ip = doh_risolvi(host, server)
        return orig((ip or host, port), *a, **k)
    uc.create_connection = conn
    return server


# ---------------------------------------------------------------------------
# Cloudflare: FlareSolverr (come nelle Action gia usate per i mirror)
# ---------------------------------------------------------------------------
CF = {'cookies': [], 'ua': None}


def ha_challenge(url):
    """True se il sito risponde con la challenge di Cloudflare."""
    import requests
    try:
        r = requests.get(url, headers={'User-Agent': UA}, timeout=20)
    except Exception:
        return False
    t = r.text[:20000].lower()
    return (r.headers.get('cf-mitigated') == 'challenge' or
            (r.status_code in (403, 429, 503) and 'cloudflare' in (r.headers.get('server', '') + t).lower()) or
            'just a moment' in t or 'challenge-platform' in t and r.status_code != 200)


def flaresolverr(endpoint, url):
    """Se il sito mostra la challenge, la supera con FlareSolverr e salva cookie e user agent."""
    import requests
    if not ha_challenge(url):
        log('Nessuna challenge Cloudflare rilevata: FlareSolverr non serve')
        return False
    log('Challenge Cloudflare rilevata, uso FlareSolverr')
    try:
        r = requests.post(endpoint.rstrip('/') + '/v1',
                          json={'cmd': 'request.get', 'url': url, 'maxTimeout': 90000},
                          timeout=120).json()
    except Exception as e:
        log('FlareSolverr non raggiungibile:', e)
        return False
    if r.get('status') != 'ok':
        log('FlareSolverr:', r.get('message'))
        return False
    sol = r['solution']
    CF['ua'] = sol.get('userAgent')
    for c in sol.get('cookies', []):
        k = {'name': c['name'], 'value': c['value'], 'domain': c.get('domain', ''),
             'path': c.get('path', '/'), 'httpOnly': bool(c.get('httpOnly')), 'secure': bool(c.get('secure'))}
        if c.get('expires') and c['expires'] > 0:
            k['expires'] = c['expires']
        CF['cookies'].append(k)
    log('FlareSolverr: risposta ricevuta, cookie:', len(CF['cookies']))
    return True


class Scaduto(Exception):
    pass


def con_timeout(sec, fn, *a, **k):
    """Esegue fn e la interrompe dopo sec secondi (evita che una lettura di rete blocchi tutto)."""
    def _h(sig, frm):
        raise Scaduto()
    try:
        vecchio = signal.signal(signal.SIGALRM, _h)
    except Exception:
        return fn(*a, **k)
    signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, vecchio)


class Sessione:
    def __init__(self, headless=True, chromium=None, dns=None):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {'headless': headless}
        if chromium:
            kw['executable_path'] = chromium
        if dns:
            # Chromium: DoH integrato, con l'indirizzo IP del provider come modello
            kw['args'] = ['--enable-features=DnsOverHttps',
                          '--force-fieldtrial-params=DnsOverHttps.Fallback:Fallback/true/Templates/https%3A%2F%2F' + dns + '%2Fdns-query',
                          '--force-fieldtrials=DnsOverHttps/Fallback']
        self.browser = self._pw.chromium.launch(**kw)
        self.ctx = self.browser.new_context(user_agent=CF['ua'] or UA, locale='it-IT',
                                            viewport={'width': 1366, 'height': 900})
        if CF['cookies']:
            self.ctx.add_cookies(CF['cookies'])
        self.page = self.ctx.new_page()
        self.net = []
        self.page.on('response', self._on_response)

    def _on_response(self, r):
        try:
            req = r.request
            url = r.url
            if NO_RISORSE.search(url.split('#')[0]) and not re.search(r'\.(m3u8|mpd)', url):
                return
            ct = (r.headers.get('content-type') or '').lower()
            entry = {'url': url, 'method': req.method, 'status': r.status, 'tipo': req.resource_type,
                     'ct': ct, 'post': None, 'body': None}
            try:
                entry['post'] = req.post_data
            except Exception:
                entry['post'] = '(binario)'
            if re.search(r'json|text|mpegurl|dash|xml|javascript', ct) and 'event-stream' not in ct and req.resource_type in (
                    'xhr', 'fetch', 'document', 'other'):
                entry['_resp'] = r  # il corpo si legge dopo, fuori dal gestore dell'evento
            self.net.append(entry)
        except Exception:
            pass

    def vai(self, url, attesa=4):
        self.net = []
        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
        self._assesta(attesa)
        return self.stato()

    def _assesta(self, attesa):
        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        for _ in range(3):
            try:
                self.page.mouse.wheel(0, 2500)
            except Exception:
                pass
            self.page.wait_for_timeout(int(attesa * 1000 / 6.0))  # con sleep() gli eventi di rete non arrivano

    def stato(self):
        net = list(self.net)
        for e in net:
            r = e.pop('_resp', None)
            if r is not None and e.get('body') is None:
                try:
                    e['body'] = con_timeout(8, r.text)[:400000]
                except BaseException:
                    e['body'] = ''
        try:
            html = con_timeout(20, self.page.content)
        except BaseException:
            html = ''
        return {'url': self.page.url, 'html': html, 'net': net}

    def varianti(self, attesa=3):
        """Prova i menu a tendina della pagina (ordinamenti, filtri) e registra le richieste che ne escono."""
        out = []
        try:
            n_sel = self.page.locator('select').count()
        except Exception:
            n_sel = 0
        for i in range(min(n_sel, 3)):
            try:
                sel = self.page.locator('select').nth(i)
                opts = sel.locator('option').evaluate_all("els => els.map(o => [o.value, o.textContent.trim()])")
                corrente = sel.input_value()
                nome_corr = sel.evaluate("e => e.options[e.selectedIndex].textContent.trim()")
            except Exception:
                continue
            out.append({'label': nome_corr, 'base': True, 'net': None})
            for val, testo in opts[:8]:
                if val == corrente or not val:
                    continue
                self.net = []
                try:
                    sel.select_option(val, timeout=3000)
                except Exception:
                    continue
                self._assesta(attesa)
                out.append({'label': testo, 'base': False, 'net': self.stato()['net']})
            try:
                self.net = []
                sel.select_option(corrente, timeout=3000)
                self._assesta(1)
            except Exception:
                pass
            break
        if out:
            return out
        # menu personalizzati (non select): pulsante che apre una lista di opzioni
        try:
            for bott in self.page.locator('[aria-haspopup], [role=combobox]').all()[:3]:
                try:
                    bott.click(timeout=2000)
                    voci = self.page.locator('[role=option], [role=menuitem], [role=menuitemradio]')
                    testi = [t.strip() for t in voci.all_inner_texts() if t.strip()][:8]
                except Exception:
                    continue
                for t in testi:
                    self.net = []
                    try:
                        self.page.locator('[role=option], [role=menuitem], [role=menuitemradio]').get_by_text(
                            t, exact=True).first.click(timeout=2000)
                    except Exception:
                        continue
                    self._assesta(attesa)
                    out.append({'label': t, 'base': False, 'net': self.stato()['net']})
                    try:
                        bott.click(timeout=2000)
                    except Exception:
                        break
                if out:
                    break
        except Exception:
            pass
        return out

    def cerca(self, selettore_input, testo='matrix', attesa=4):
        self.net = []
        try:
            box = self.page.locator(selettore_input).first
            box.fill(testo, timeout=5000)
            box.press('Enter', timeout=5000)
        except Exception as e:
            return {'errore': str(e), 'url': self.page.url, 'html': '', 'net': []}
        self._assesta(attesa)
        return self.stato()

    def prova_play(self, attesa=10):
        self.net = []
        cliccato = ''
        for sel in PLAY_SELETTORI:
            try:
                loc = self.page.locator(sel)
                if loc.count():
                    loc.first.click(timeout=3000, force=True)
                    cliccato = sel
                    break
            except Exception:
                continue
        self.page.wait_for_timeout(int(attesa * 1000))
        st = self.stato()
        st['cliccato'] = cliccato
        return st

    def chiudi(self):
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 2. Analisi HTML
# ---------------------------------------------------------------------------

def soup_di(html):
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, 'lxml')
    except Exception:
        return BeautifulSoup(html, 'html.parser')


def firma(el):
    return (el.name, tuple(el.get('class', [])))


def _href(el):
    a = el if el.name == 'a' else el.find('a', href=True)
    if not a:
        return ''
    h = a.get('href', '')
    if not h or h.startswith('#') or h.lower().startswith('javascript'):
        return ''
    return h


def _thumb_attr(img):
    for at in ('data-src', 'data-original', 'data-lazy-src', 'data-lazy', 'src'):
        v = img.get(at, '')
        if v and not v.startswith('data:'):
            return at, v
    return '', ''


def trova_card(soup):
    """Cerca il gruppo di elementi ripetuti (locandina + link) che e la lista dei titoli."""
    gruppi = {}
    for el in soup.find_all(True):
        if el.name in ('html', 'body', 'head', 'script', 'style', 'ul', 'ol', 'section', 'main', 'form'):
            continue
        if any(p.name in ('nav', 'header', 'footer') for p in el.parents):
            continue
        img = el.find('img')
        if not img or not _href(el):
            continue
        if len(str(el)) > 5000:
            continue
        # loghi, icone dei provider e bandiere non sono titoli
        if LOGO_RE.search(' '.join([img.get('src', ''), img.get('data-src', ''), ' '.join(img.get('class', [])),
                                    img.get('alt', '')])) or '/provider' in _href(el):
            continue
        gruppi.setdefault(firma(el), []).append(el)
    migliore = None
    punti = 0
    for f, els in gruppi.items():
        hrefs = {_href(e) for e in els}
        if len(els) < 4 or len(hrefs) < 4:
            continue
        p = len(hrefs) + sum(1 for h in hrefs if h.strip('/').count('/') >= 1)
        if p > punti:
            punti = p
            migliore = els
    return migliore


def campi_card(el):
    """Individua dove stanno url, locandina, titolo, anno e trama dentro una card."""
    c = {}
    a = el if el.name == 'a' else el.find('a', href=True)
    c['url'] = ('attr', 'a', 'href')
    img = el.find('img')
    at, _ = _thumb_attr(img)
    if at:
        c['thumb'] = ('attr', 'img', at)
    # titolo: intestazione, poi title del link, poi alt, poi testo del link
    titolo = None
    h = el.find(re.compile(r'^h[1-6]$'))
    if h and h.get_text(strip=True):
        titolo = ('testo', h)
    if not titolo:
        for cand in el.find_all(True, class_=re.compile(r'(title|titolo|name|nome)', re.I)):
            if cand.get_text(strip=True) and not cand.find('img'):
                titolo = ('testo', cand)
                break
    if not titolo and a.get('title'):
        titolo = ('attr', 'a', 'title')
    if not titolo and img.get('alt'):
        titolo = ('attr', 'img', 'alt')
    if not titolo and a.get_text(strip=True):
        titolo = ('testo', a)
    if titolo:
        c['title'] = titolo
    # anno
    for cand in el.find_all(True):
        t = cand.get_text(strip=True)
        if cand is not titolo and re.fullmatch(r'\(?(19|20)\d{2}\)?', t or '') and not cand.find(True):
            c['year'] = ('testo', cand)
            break
    # trama
    for p in el.find_all('p'):
        if len(p.get_text(strip=True)) > 70:
            c['plot'] = ('testo', p)
            break
    return c


def _apertura(tag):
    """Il tag di apertura cosi come appare nell'html."""
    s = str(tag)
    return s[:s.index('>') + 1]


def _tagre(tag, attrs_extra=''):
    """Pezzo di regex che riconosce un tag per nome e classe."""
    cl = tag.get('class')
    parte = '<' + tag.name
    if cl:
        parte += r'[^>]*class="' + re.escape(' '.join(cl)) + '"'
    return parte + attrs_extra


def costruisci_patron(el):
    """Costruisce la regex 'patron' da una card di esempio."""
    campi = campi_card(el)
    s = str(el)
    pezzi = []  # (posizione, regex)

    def pos_di(stringa, da=0):
        i = s.find(stringa, da)
        return i if i >= 0 else None

    # url (se il titolo e un attributo dello stesso <a> si legge con una lookahead, senza un secondo <a>)
    a = el if el.name == 'a' else el.find('a', href=True)
    t = campi.get('title')
    titolo_su_a = bool(t and t[0] == 'attr' and t[1] == 'a')
    titolo_su_img = bool(t and t[0] == 'attr' and t[1] == 'img' and 'thumb' in campi)
    la_a = (r'(?=[^>]*?' + t[2] + r'="(?P<title>[^"]+)")') if titolo_su_a else ''
    if el.name == 'a':
        inizio = _tagre(el) + la_a + r'[^>]*?href="(?P<url>[^"]+)"'
        pezzi.append((0, inizio))
    else:
        pezzi.append((0, _tagre(el)))
        p = pos_di(_apertura(a))
        pezzi.append((p if p is not None else 1, r'<a ' + la_a + r'[^>]*?href="(?P<url>[^"]+)"'))
    # thumb (se il titolo e l'alt dello stesso <img>, i due campi si leggono insieme)
    if 'thumb' in campi:
        img = el.find('img')
        p = pos_di(_apertura(img))
        la_img = (r'(?=[^>]*?' + t[2] + r'="(?P<title>[^"]+)")') if titolo_su_img else ''
        pezzi.append((p if p is not None else 2,
                      r'<img ' + la_img + r'[^>]*?' + campi['thumb'][2] + r'="(?P<thumb>[^"]+)"'))
    # titolo
    if 'title' in campi and not titolo_su_a and not titolo_su_img:
        t = campi['title']
        if t[0] == 'attr':
            tag = el.find(t[1]) if t[1] != 'a' else a
            p = pos_di(_apertura(tag))
            pezzi.append((p if p is not None else 3,
                          '<' + t[1] + r' [^>]*?' + t[2] + r'="(?P<title>[^"]+)"'))
        else:
            tag = t[1]
            p = pos_di(_apertura(tag))
            if tag is a or tag is el:
                pezzi.append((p if p is not None else 3,
                              r'>\s*(?P<title>[^<]+?)\s*<'))
            else:
                pezzi.append((p if p is not None else 3,
                              _tagre(tag) + r'[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'))
    if 'year' in campi:
        tag = campi['year'][1]
        p = pos_di(_apertura(tag))
        pezzi.append((p if p is not None else 4,
                      _tagre(tag) + r'[^>]*>\s*\(?(?P<year>[0-9]{4})\)?'))
    if 'plot' in campi:
        tag = campi['plot'][1]
        p = pos_di(_apertura(tag))
        pezzi.append((p if p is not None else 5,
                      _tagre(tag) + r'[^>]*>\s*(?P<plot>[^<]+)'))
    pezzi.sort(key=lambda x: x[0])
    if el.name == 'a':
        # tutto deve stare dentro lo stesso link
        giunto = r'(?:(?!</a>).)*?'
    elif el.get('class'):
        # i campi non possono scavalcare l'inizio della card successiva
        giunto = r'(?:(?!' + pezzi[0][1] + r').)*?'
    else:
        giunto = '.*?'
    return giunto.join(p[1] for p in pezzi)


def collauda(patron, html_norm):
    """Applica la regex come fa support.scrape e restituisce (n, esempi)."""
    try:
        ms = [m.groupdict() for m in re.finditer(patron, html_norm, re.DOTALL)]
    except re.error as e:
        return 0, [], str(e)
    buoni = [m for m in ms if m.get('url') and m.get('title')]
    return len(buoni), buoni[:3], ''


def trova_next(soup):
    for a in soup.find_all('a', href=True):
        rel = a.get('rel') or []
        testo = a.get_text(' ', strip=True)
        cl = ' '.join(a.get('class', []))
        if 'next' in rel:
            return r'<a [^>]*?rel="next"[^>]*?href="([^"]+)"|<a [^>]*?href="([^"]+)"[^>]*?rel="next"', a['href']
    for a in soup.find_all('a', href=True):
        testo = a.get_text(' ', strip=True)
        cl = ' '.join(a.get('class', []))
        aria = a.get('aria-label', '') + ' ' + a.get('title', '')
        if re.search(r'(next|success|avanti|prossim)', cl + ' ' + aria, re.I) or \
                re.fullmatch(r'(»|›|>|>>|Avanti|Successiv[ao]|Next|Pagina successiva)', testo or '', re.I):
            if a['href'] in ('#', '') or a['href'].startswith('javascript'):
                continue
            if a.get('class'):
                return (r'<a [^>]*?class="' + re.escape(' '.join(a['class'])) +
                        r'"[^>]*?href="([^"]+)"'), a['href']
            return (r'<a [^>]*?href="([^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*' +
                    re.escape(testo)), a['href']
    return '', ''


def trova_menu(soup, base):
    voci = []
    visti = set()
    cont = soup.find_all(['nav', 'header'])
    for blocco in cont:
        for a in blocco.find_all('a', href=True):
            t = a.get_text(' ', strip=True)
            h = a['href']
            if not t or len(t) > 30 or h.startswith('#') or h.startswith('javascript'):
                continue
            if re.fullmatch(r'[\d\W]+', t) or re.search(r'[?&](page|p|pg|paged)=', h) or \
                    re.fullmatch(r'(next|prev|successiv\w*|precedent\w*)', t, re.I):
                continue
            if SKIP_NAV.search(t) or SKIP_NAV.search(h):
                continue
            full = urljoin(base, h)
            if urlparse(full).netloc != urlparse(base).netloc:
                continue
            if full in visti or full.rstrip('/') == base.rstrip('/'):
                continue
            visti.add(full)
            voci.append((t, full))
    return voci[:14]


def tipo_da_testo(t):
    t = t.lower()
    if re.search(r'anime', t):
        return 'anime'
    if re.search(r'(serie|tv|telefilm|fiction|episod)', t):
        return 'tvshow'
    return 'movie'


def trova_ricerca(soup, base):
    for f in soup.find_all('form'):
        inp = f.find('input', attrs={'type': re.compile('^(search|text)$', re.I)}) or \
            f.find('input', attrs={'name': re.compile('(s|q|query|search|story|keyword)', re.I)})
        if not inp or not inp.get('name'):
            continue
        sel = 'input[name="%s"]' % inp['name']
        return {'selettore': sel, 'nome': inp['name'],
                'azione': urljoin(base, f.get('action') or base),
                'metodo': (f.get('method') or 'get').lower()}
    inp = soup.find('input', attrs={'type': 'search'}) or soup.find(
        'input', attrs={'placeholder': re.compile('(cerca|search)', re.I)})
    if inp:
        sel = ('input[name="%s"]' % inp['name']) if inp.get('name') else 'input[type=search]'
        return {'selettore': sel, 'nome': inp.get('name', ''), 'azione': '', 'metodo': ''}
    return None


def trova_episodi(soup):
    """Sulla pagina di dettaglio cerca un gruppo di link che sembrano episodi."""
    cand = {}
    for a in soup.find_all('a', href=True):
        t = a.get_text(' ', strip=True)
        if re.search(r'(\d+\s*[x×]\s*\d+|episod|\bS\d+\s*E\d+|\bep\.?\s*\d+)', t, re.I):
            cand.setdefault(firma(a), []).append(a)
    best = max(cand.values(), key=len) if cand else None
    return best if best and len(best) >= 3 else None


# ---------------------------------------------------------------------------
# 3. Analisi API
# ---------------------------------------------------------------------------

def appiattisci(d, prefisso='', prof=0, out=None):
    out = {} if out is None else out
    if prof > 3 or not isinstance(d, dict):
        return out
    for k, v in d.items():
        p = prefisso + k
        if isinstance(v, dict):
            appiattisci(v, p + '.', prof + 1, out)
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out[p] = v
    return out


def liste_json(obj, path='', prof=0, out=None, minimo=4):
    out = [] if out is None else out
    if prof > 6:
        return out
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if len(dicts) >= minimo:
            out.append((path, obj))
        for i, x in enumerate(obj[:1]):
            liste_json(x, path, prof + 1, out, minimo)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            liste_json(v, (path + '.' if path else '') + k, prof + 1, out, minimo)
    return out


def scegli_chiavi(item):
    """Per un elemento dell'elenco decide quale campo e titolo, id, locandina, anno, trama."""
    piatto = appiattisci(item)
    chiavi = list(piatto.keys())

    def ultima(k):
        return k.split('.')[-1]

    ris = {}
    for tk in TITOLO_KEYS:
        for k in sorted(chiavi, key=lambda x: x.count('.')):
            if ultima(k).lower() == tk.lower() and isinstance(piatto[k], str) and len(piatto[k]) > 1:
                ris['title'] = k
                break
        if 'title' in ris:
            break
    for k in chiavi:
        if ultima(k) == '__typename' and isinstance(piatto[k], str):
            ris['type'] = k
            break
    for ik in ID_KEYS:
        for k in sorted(chiavi, key=lambda x: x.count('.')):
            if ultima(k) == ik:
                ris.setdefault('ids', []).append(k)
    for k in sorted(chiavi, key=lambda x: x.count('.')):
        v = piatto[k]
        if isinstance(v, str) and 'thumb' not in ris and IMG_RE.search(ultima(k)):
            ris['thumb'] = k
        if 'year' not in ris and ANNO_RE.search(ultima(k)) and re.search(r'(19|20)\d{2}', str(v)):
            ris['year'] = k
        if 'plot' not in ris and PLOT_RE.search(ultima(k)) and isinstance(v, str) and len(v) > 30:
            ris['plot'] = k
    return ris, piatto


def trova_elenco_api(net):
    """Tra le risposte JSON sceglie la lista di titoli piu grande."""
    best = None
    for e in net:
        if not e.get('body') or 'json' not in e.get('ct', ''):
            continue
        try:
            j = json.loads(e['body'])
        except Exception:
            continue
        for path, lst in liste_json(j):
            dicts = [x for x in lst if isinstance(x, dict)]
            ris, _ = scegli_chiavi(dicts[0])
            if 'title' not in ris or not ris.get('ids'):
                continue
            titolati = sum(1 for x in dicts if scegli_chiavi(x)[0].get('title'))
            if titolati < 0.6 * len(dicts):
                continue
            punteggio = len(dicts) + (3 if 'thumb' in ris else 0)
            if not best or punteggio > best['punteggio']:
                best = {'entry': e, 'path': path, 'lista': dicts, 'chiavi': ris,
                        'punteggio': punteggio, 'json': j}
    return best


TIPI_URL = {'movie': ['film', 'films', 'movie', 'movies', 'filmes', 'cinema'],
            'tvshow': ['serie-tv', 'serie', 'series', 'tv', 'show', 'shows', 'serietv', 'telefilm', 'tv-show'],
            'anime': ['anime']}


def tipi_da_url(hrefs):
    """Se i link delle card contengono sia /film/ sia /serie-tv/ ecc., ritorna i tipi trovati."""
    trovati = {}
    for h in hrefs:
        for seg in urlparse(h).path.lower().split('/'):
            for tipo, nomi in TIPI_URL.items():
                if seg in nomi:
                    trovati.setdefault(tipo, set()).add(seg)
    return {k: sorted(v) for k, v in trovati.items()} if len(trovati) >= 2 else {}


FREE_RE = re.compile(r'(free|gratis|gratuit|senza abbonamento)', re.I)
SEASON_RE = re.compile(r'^(season|stagione)(number|num|n|no)?$', re.I)
EPISODE_RE = re.compile(r'^(episode|episodio|ep)(number|num|n|no)?$|^number$', re.I)


def firma_richiesta(e):
    """Identifica una richiesta ignorando i parametri di pagina."""
    post = e.get('post') or ''
    try:
        j = json.loads(post)
        v = j.get('variables') if isinstance(j, dict) and 'variables' in j else j
        if isinstance(v, dict):
            for k in PAGE_KEYS + OFFSET_KEYS + ['after', 'cursor', 'endCursor']:
                v.pop(k, None)
        post = json.dumps(j, sort_keys=True)
    except Exception:
        pass
    sp = urlsplit(e['url'])
    q = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if k not in PAGE_KEYS + OFFSET_KEYS]
    return (sp.path, tuple(sorted(q)), post)


def trova_episodi_api(net):
    """Cerca una risposta JSON che contiene l'elenco degli episodi (campi stagione e episodio)."""
    best = None
    for e in net:
        if not e.get('body') or 'json' not in e.get('ct', ''):
            continue
        try:
            j = json.loads(e['body'])
        except Exception:
            continue
        for path, lst in liste_json(j, minimo=2):
            dicts = [x for x in lst if isinstance(x, dict)]
            piatto = appiattisci(dicts[0])
            sk = ek = None
            for k in sorted(piatto, key=lambda x: x.count('.')):
                ult = k.split('.')[-1]
                if sk is None and SEASON_RE.match(ult) and isinstance(piatto[k], (int, float, str)):
                    sk = k
                if ek is None and EPISODE_RE.match(ult) and isinstance(piatto[k], (int, float, str)):
                    ek = k
            if not sk or not ek:
                continue
            ris, _ = scegli_chiavi(dicts[0])
            ris['season'] = sk
            ris['episode'] = ek
            if not best or len(dicts) > len(best['lista']):
                best = {'entry': e, 'path': path, 'lista': dicts, 'chiavi': ris, 'json': j}
    return best


def trasforma_id(testo, candidati):
    """Trova dove compare l'id del titolo in una richiesta: diretto oppure dentro un valore base64."""
    import base64
    for idv in candidati:
        if idv and idv in testo:
            return {'tipo': 'dir', 'id': idv}
    for tok in set(re.findall(r'[A-Za-z0-9+/]{12,}={0,2}', testo)):
        try:
            dec = base64.b64decode(tok + '=' * (-len(tok) % 4)).decode('utf-8')
        except Exception:
            continue
        for idv in candidati:
            if idv and idv in dec:
                return {'tipo': 'b64', 'id': idv, 'token': tok, 'formato': dec.replace(idv, '{ID}')}
    return None


def nome_da_url(u):
    seg = [x for x in urlparse(u).path.split('/') if x]
    return (seg[-1] if seg else 'Titoli').replace('-', ' ').replace('_', ' ').title()


def titoli_api(api):
    k = api['chiavi'].get('title')
    return {str(appiattisci(x).get(k, '')).strip().lower() for x in api['lista']} - {''}


def titoli_html(patron, html_norm):
    out = set()
    try:
        for m in re.finditer(patron, html_norm, re.I):
            t = (m.groupdict().get('title') or '').strip().lower()
            if t:
                out.add(t)
    except re.error:
        pass
    return out


def paginazione(entry):
    """Trova il parametro di pagina nell'url o nel corpo della richiesta."""
    sp = urlsplit(entry['url'])
    query = dict(parse_qsl(sp.query, keep_blank_values=True))
    for k in PAGE_KEYS:
        if k in query:
            return {'dove': 'query', 'chiave': k, 'tipo': 'pagina', 'valore': query[k]}
    for k in OFFSET_KEYS:
        if k in query:
            return {'dove': 'query', 'chiave': k, 'tipo': 'offset', 'valore': query[k]}
    if entry.get('post'):
        try:
            body = json.loads(entry['post'])
        except Exception:
            return None
        variabili = body.get('variables', body) if isinstance(body, dict) else {}
        for k in PAGE_KEYS:
            if k in variabili:
                return {'dove': 'corpo', 'chiave': k, 'tipo': 'pagina', 'valore': variabili[k]}
        for k in OFFSET_KEYS:
            if k in variabili:
                return {'dove': 'corpo', 'chiave': k, 'tipo': 'offset', 'valore': variabili[k]}
        for k in ('after', 'cursor', 'endCursor'):
            if k in variabili:
                return {'dove': 'corpo', 'chiave': k, 'tipo': 'cursore', 'valore': variabili[k]}
    return None


def trova_manifest(net):
    """Cerca manifest m3u8/mpd e richieste di licenza DRM nella rete."""
    man = []
    lic = []
    for e in net:
        u = e['url']
        if re.search(r'\.(m3u8|mpd)(\?|$)', u) or 'mpegurl' in e.get('ct', '') or 'dash+xml' in e.get('ct', ''):
            man.append(e)
        if re.search(r'(licen[sc]e|widevine|drm|playready)', u, re.I) and e['method'] in ('POST', 'GET') \
                and not re.search(r'\.(m3u8|mpd)', u):
            lic.append(e)
    return man, lic


def percorso_valore(obj, valore, path=''):
    """Cerca in un JSON la stringa 'valore' e restituisce il percorso (a.b.0.c)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            r = percorso_valore(v, valore, (path + '.' if path else '') + k)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            r = percorso_valore(v, valore, (path + '.' if path else '') + str(i))
            if r is not None:
                return r
    elif isinstance(obj, str) and valore in obj:
        return path
    return None


def sorgente_manifest(net, manifest_url):
    """Quale risposta JSON contiene l'url del manifest? Restituisce la richiesta che lo produce."""
    for e in net:
        if not e.get('body') or 'json' not in e.get('ct', ''):
            continue
        if manifest_url.split('?')[0] not in e['body'] and manifest_url not in e['body']:
            continue
        try:
            j = json.loads(e['body'])
        except Exception:
            continue
        p = percorso_valore(j, manifest_url.split('?')[0])
        if p:
            return {'entry': e, 'path': p, 'json': j}
    return None


# ---------------------------------------------------------------------------
# 4. Generazione dei file
# ---------------------------------------------------------------------------

def id_da_url(url):
    host = urlparse(url).netloc.lower()
    host = re.sub(r'^(www|m)\.', '', host)
    parti = host.split('.')
    base = parti[0] if len(parti) > 1 else host
    return re.sub(r'[^a-z0-9]', '', base) or 'canale'


def py_str(s):
    return repr(s)


def raw(s):
    """Stringa raw tra apici tripli, per le regex."""
    if "'''" in s:
        return repr(s)
    return "r'''" + s + "'''"


HEADER = '''# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per __NOME__
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

'''


def genera_menu(voci, tipo_default):
    film, serie, anime, top = [], [], [], []
    for nome, full in voci:
        t = tipo_da_testo(nome)
        path = urlparse(full).path + (('?' + urlparse(full).query) if urlparse(full).query else '')
        riga = "('%s', ['%s', 'peliculas', '', '%s'])" % (nome.replace("'", ''), path, t)
        top.append(riga)
    righe = ['    top = [' + ',\n           '.join(top) + ']'] if top else []
    return '\n'.join(righe)


def genera_html(nome, ctx):
    cod = HEADER.replace('__NOME__', nome)
    menu = genera_menu(ctx['menu'], ctx['tipo'])
    cod += '''
@support.menu
def mainlist(item):
''' + (menu + '\n' if menu else '') + '''    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = '__AZIONE__'
    patron = __PATRON__
''' + ("    patronNext = " + raw(ctx['next']) + "\n" if ctx['next'] else "    # patronNext: pagina successiva non trovata\n")
    tipi = ctx.get('tipi') or {}
    if tipi:
        cod = cod.replace('__AZIONE__', 'findvideos')
        righe = "    typeContentDict = %s\n" % json.dumps({k: v for k, v in tipi.items() if k in ('movie', 'tvshow', 'anime')})
        if tipi.get('tvshow'):
            righe += "    typeActionDict = %s\n" % json.dumps({'episodios': tipi['tvshow']})
        cod = cod.replace("    #debug = True  # apre regex101", righe + "    #debug = True  # apre regex101", 1)
    else:
        cod = cod.replace('__AZIONE__', 'episodios' if ctx['episodi'] and ctx['tipo'] == 'tvshow' else 'findvideos')
    cod = cod.replace('__PATRON__', raw(ctx['patron']))
    cod += '''    #debug = True  # apre regex101 con pagina e regex
    return locals()

'''
    if ctx['episodi']:
        cod += '''
@support.scrape
def episodios(item):
    support.info(item)
    action = 'findvideos'
    patron = __PATRONEP__
    #debug = True
    return locals()

'''.replace('__PATRONEP__', raw(ctx['patron_ep']))
    # ricerca
    r = ctx['ricerca']
    if r and r.get('url_modello'):
        cod += '''
def search(item, text):
    support.info(text)
    item.url = host + '__URLR__' % text.replace(' ', '+')
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []

'''.replace('__URLR__', r['url_modello'].replace('%', '%%').replace('%%s', '%s'))
    else:
        cod += '''
def search(item, text):
    # TODO: ricerca non rilevata automaticamente, impostare l'url della ricerca del sito
    support.info(text)
    item.url = host + '/?s=' + text.replace(' ', '+')
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []

'''
    cod += '''
def findvideos(item):
    support.info(item)
    return support.server(item, headers=headers)
'''
    return cod


def espr_url(url, base):
    """Espressione Python per un url: relativo all'host del canale se il sito e lo stesso."""
    sp = urlsplit(url)
    if sp.netloc == urlparse(base).netloc:
        rel = urlunsplit(('', '', sp.path, '', ''))
        return 'host + ' + py_str(rel)
    return py_str(urlunsplit((sp.scheme, sp.netloc, sp.path, '', '')))


TEMPLATE_API = """
def prendi(d, path, default=''):
    for p in path.split('.'):
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and p.isdigit() and int(p) < len(d):
            d = d[int(p)]
        else:
            return default
        if d is None:
            return default
    return d


def cerca_chiave(d, chiave):
    # cerca una chiave (per esempio endCursor) in qualsiasi punto della risposta
    if isinstance(d, dict):
        if d.get(chiave) not in (None, ''):
            return d[chiave]
        for v in d.values():
            r = cerca_chiave(v, chiave)
            if r not in (None, ''):
                return r
    elif isinstance(d, list):
        for v in d:
            r = cerca_chiave(v, chiave)
            if r not in (None, ''):
                return r
    return None


def cerca_lista(d, chiave_titolo):
    # prima lista di oggetti che contengono il campo del titolo
    if isinstance(d, list):
        if d and isinstance(d[0], dict) and prendi(d[0], chiave_titolo):
            return d
        for v in d:
            r = cerca_lista(v, chiave_titolo)
            if r:
                return r
    elif isinstance(d, dict):
        for v in d.values():
            r = cerca_lista(v, chiave_titolo)
            if r:
                return r
    return []


def sezione(item):
    return SEZIONI[int(item.args)] if str(item.args).isdigit() and int(item.args) < len(SEZIONI) else SEZIONI[0]


def chiama(item):
    sez = sezione(item)
    PAGINAZIONE = sez['pag']
    params = dict(sez['params'])
    body = json.loads(json.dumps(sez['body'])) if sez['body'] is not None else None
    url = sez['url'] if sez['url'].startswith('http') else host + sez['url']
    pagina = int(item.pagina) if item.pagina else 1
    if item.search_text and RICERCA_BODY is not None:
        body = json.loads(RICERCA_BODY.replace('__TESTO__', json.dumps(item.search_text)[1:-1]))
        url = RICERCA_URL or url
    elif item.search_text and RICERCA:
        return httptools.downloadpage(RICERCA % item.search_text.replace(' ', '+'),
                                      headers={'Referer': host + '/'}).json
    if PAGINAZIONE:
        ch = PAGINAZIONE['chiave']
        if PAGINAZIONE['dove'] == 'query':
            bersaglio = params
        else:
            bersaglio = body.get('variables') if 'variables' in body else body
        if PAGINAZIONE['tipo'] == 'cursore':
            if item.after:
                bersaglio[ch] = item.after
        elif PAGINAZIONE['tipo'] == 'pagina':
            bersaglio[ch] = pagina
        else:
            bersaglio[ch] = (pagina - 1) * int(PAGINAZIONE.get('passo', 20))
    url = url + ('?' + urlencode(params) if params else '')
    opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
    if body is not None:
        opt['post'] = json.dumps(body)
    return httptools.downloadpage(url, **opt).json


def url_in_chiaro(d):
    # primo url di manifest (m3u8 o mpd) presente in qualsiasi punto della risposta
    if isinstance(d, str):
        return d if re.match(r'https?://', d) and re.search(r'\\.(m3u8|mpd)(\\?|$)', d) else ''
    if isinstance(d, dict):
        valori = d.values()
    elif isinstance(d, list):
        valori = d
    else:
        return ''
    for v in valori:
        r = url_in_chiaro(v)
        if r:
            return r
    return ''


def simile(a, b):
    na = re.sub(r'[^a-z0-9]', '', (a or '').lower())
    nb = re.sub(r'[^a-z0-9]', '', (b or '').lower())
    if not na or not nb:
        return 0
    if na in nb or nb in na:
        return 1
    return difflib.SequenceMatcher(None, na, nb).ratio()


def verificaTmdb(itemlist):
    # se TMDB ha scelto un altro titolo (risultato sbagliato) si torna ai dati del sito
    for it in itemlist:
        info = it.infoLabels
        if not info.get('tmdb_id') or not it.sito_title:
            continue
        trovati = [info.get('originaltitle'), info.get('title')]
        if max([simile(it.sito_title, t) for t in trovati]) >= 0.9:
            continue
        logger.debug('TMDB scartato per', it.sito_title, trovati)
        pulite = {'year': it.sito_year} if it.sito_year else {}
        if it.contentType == 'movie':
            pulite['title'] = it.sito_title
        else:
            pulite['tvshowtitle'] = it.sito_title
        if it.sito_plot:
            pulite['plot'] = it.sito_plot
        it.__dict__['infoLabels'] = InfoLabels(pulite)
        it.thumbnail = it.sito_thumb
        it.fanart = ''


def peliculas(item):
    logger.debug()
    itemlist = []
    sez = sezione(item)
    PAGINAZIONE = sez['pag']
    risposta = chiama(item)
    lista = prendi(risposta, sez['lista'], [])
    if not lista:
        lista = cerca_lista(risposta, CAMPI.get('title', 'title'))
    for el in lista:
        titolo = prendi(el, CAMPI.get('title', 'title'))
        if not titolo:
            continue
        idv = ''
        for k in IDS:
            idv = prendi(el, k)
            if idv:
                break
        anno = prendi(el, CAMPI['year']) if 'year' in CAMPI else ''
        m = re.search(r'(19|20)\\d{2}', str(anno))
        anno = m.group(0) if m else ''
        url = ''
        if DETTAGLIO:
            url = host + DETTAGLIO.format(idv) if DETTAGLIO.startswith('/') else DETTAGLIO.format(idv)
        thumb = prendi(el, CAMPI['thumb']) if 'thumb' in CAMPI else ''
        thumb = str(thumb).replace('{profile}', 's332').replace('{format}', 'jpg')
        if thumb.startswith('/'):
            thumb = host + thumb
        plot = prendi(el, CAMPI['plot']) if 'plot' in CAMPI else ''
        tipo = sez['tipo']
        if 'type' in CAMPI:
            tipo = 'tvshow' if re.search(r'show|serie|tv|series', str(prendi(el, CAMPI['type'])), re.I) else 'movie'
        comuni = dict(channel=item.channel, title=titolo, fulltitle=titolo, show=titolo,
                      thumbnail=thumb, url=url, idv=str(idv),
                      sito_title=titolo, sito_year=anno, sito_plot=str(plot or ''), sito_thumb=thumb)
        if tipo == 'tvshow':
            itemlist.append(Item(action='episodios', contentType='tvshow', contentSerieName=titolo,
                                 infoLabels={'tvshowtitle': titolo, 'year': anno} if anno else {'tvshowtitle': titolo},
                                 **comuni))
        else:
            itemlist.append(Item(action='findvideos', contentType='movie', contentTitle=titolo,
                                 infoLabels={'year': anno} if anno else {}, **comuni))
    try:
        tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        verificaTmdb(itemlist)
    except:
        logger.error('TMDB non disponibile')

    if itemlist and PAGINAZIONE and not item.search_text:
        if PAGINAZIONE['tipo'] == 'cursore':
            fine = cerca_chiave(risposta, 'endCursor')
            ancora = cerca_chiave(risposta, 'hasNextPage')
            if fine and ancora is not False:
                itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'),
                                           action='peliculas', after=fine, thumbnail=support.thumb()))
        else:
            itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'),
                                       action='peliculas', pagina=(int(item.pagina) if item.pagina else 1) + 1,
                                       thumbnail=support.thumb()))
    return itemlist


def episodios(item):
    logger.debug()
    itemlist = []
    if not EPISODI:
        platformtools.dialog_ok('__NOME__', 'Episodi non rilevati sul sito')
        return []
    url = EPISODI['url'].replace('{ID}', item.idv)
    if not url.startswith('http'):
        url = host + url
    opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
    if EPISODI['body']:
        opt['post'] = EPISODI['body'].replace('{ID}', item.idv)
    risposta = httptools.downloadpage(url, **opt).json
    ch = EPISODI['chiavi']
    lista = prendi(risposta, EPISODI['lista'], []) or cerca_lista(risposta, ch.get('title', 'title'))
    titolo_serie = item.sito_title or item.contentSerieName or item.fulltitle
    anno = item.sito_year or item.infoLabels.get('year', '')
    for ep in lista:
        try:
            stagione = int(float(prendi(ep, ch['season'])))
            numero = int(float(prendi(ep, ch['episode'])))
        except (ValueError, TypeError):
            continue
        nome = prendi(ep, ch['title']) if 'title' in ch else ''
        idv = ''
        for k in ch.get('ids', []):
            idv = prendi(ep, k)
            if idv:
                break
        itemlist.append(Item(channel=item.channel,
                             action='findvideos',
                             contentType='episode',
                             title=support.typo('{}x{:02d}'.format(stagione, numero) + (' - ' + nome if nome else ''), 'bold'),
                             fulltitle=titolo_serie,
                             show=titolo_serie,
                             contentSerieName=titolo_serie,
                             contentSeason=stagione,
                             contentEpisodeNumber=numero,
                             infoLabels={'season': stagione, 'episode': numero,
                                         'tvshowtitle': titolo_serie, 'year': anno},
                             thumbnail=item.thumbnail,
                             idv=str(idv),
                             url=''))
    if itemlist and config.get_setting('episode_info'):
        try:
            tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        except:
            logger.error('TMDB non disponibile')
    support.videolibrary(itemlist, item)
    return itemlist

"""


def genera_api(nome, ctx):
    api = ctx['api']
    e = api['entry']
    base = ctx['base']
    sp = urlsplit(e['url'])
    query = dict(parse_qsl(sp.query, keep_blank_values=True))
    pag = ctx['pag']
    chiavi = api['chiavi']
    post = None
    if e.get('post'):
        try:
            post = json.loads(e['post'])
        except Exception:
            post = None
    dett = ctx.get('dettaglio', '')

    cod = HEADER.replace('__NOME__', nome)
    sezioni = ctx.get('sezioni') or [{'nome': 'Titoli', 'tipo': ctx['tipo'], 'entry': e, 'lista': api['path'], 'pag': pag}]
    elenco = []
    for z in sezioni:
        ez = z['entry']
        spz = urlsplit(ez['url'])
        try:
            bz = json.loads(ez['post']) if ez.get('post') else None
        except Exception:
            bz = None
        rel = urlunsplit(('', '', spz.path, '', '')) if spz.netloc == urlparse(base).netloc else \
            urlunsplit((spz.scheme, spz.netloc, spz.path, '', ''))
        elenco.append({'nome': z['nome'], 'tipo': z['tipo'], 'url': rel,
                       'params': dict(parse_qsl(spz.query, keep_blank_values=True)), 'body': bz,
                       'lista': z['lista'], 'pag': z.get('pag')})
    cod += "SEZIONI = %s\n" % pprint.pformat(elenco, width=110, sort_dicts=False)
    cod += "CAMPI = %s\n" % json.dumps({k: v for k, v in chiavi.items() if k != 'ids'}, ensure_ascii=False)
    cod += "IDS = %s  # campi che identificano il titolo, in ordine di preferenza\n" % json.dumps(chiavi.get('ids', []))
    cod += "DETTAGLIO = %s  # pagina del titolo, {} al posto dell'id\n" % py_str(dett)
    epi = ctx.get('episodi_api')
    if epi:
        cod += "EPISODI = %s\n" % pprint.pformat(epi, width=110, sort_dicts=False)
    else:
        cod += "EPISODI = None  # episodi non rilevati sul sito\n"
    # menu: una voce per sezione, raggruppate per tipo come negli altri canali S4Me
    gruppi = {}
    for i, z in enumerate(elenco):
        gruppi.setdefault(z['tipo'], []).append("('%s', ['', 'peliculas', '%d', '%s'])" % (z['nome'].replace("'", ''), i, z['tipo']))
    righe = []
    for tp, voci in gruppi.items():
        chiave = tp if tp in ('movie', 'tvshow', 'anime') else 'movie'
        chiave = {'movie': 'film'}.get(chiave, chiave)
        righe.append("    %s = ['',\n           %s]" % (chiave, ',\n           '.join(voci)))
    cod += "\n\n@support.menu\ndef mainlist(item):\n" + '\n'.join(righe) + "\n    search = ''\n    return locals()\n\n\n"
    s = ctx['search_api']
    sb = ctx.get('search_body')
    cod += "RICERCA = %s\n" % (espr_url_ricerca(s, base) if s else 'None')
    cod += "RICERCA_BODY = %s\n" % (py_str(sb['post']) if sb else 'None')
    cod += "RICERCA_URL = %s\n" % (espr_url(sb['url'], base) if sb and sb['url'] != e['url'] else "''")
    corpo = TEMPLATE_API.replace('__TIPO__', ctx['tipo']).replace('__NOME__', nome)
    cod += '\n' + corpo

    if s or sb:
        cod += """

def search(item, text):
    logger.debug(text)
    item.search_text = text
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []

"""
    else:
        cod += """

def search(item, text):
    # TODO: ricerca non rilevata automaticamente
    return []

"""
    cod += genera_findvideos_api(ctx, nome)
    return cod


def espr_url_ricerca(url, base):
    """Url di ricerca con %s al posto del testo, relativo all'host se possibile."""
    sp = urlsplit(url)
    resto = urlunsplit(('', '', sp.path, sp.query, '')).replace('%', '%%').replace('matrix', '%s')
    if sp.netloc == urlparse(base).netloc:
        return 'host + ' + py_str(resto)
    return py_str(urlunsplit((sp.scheme, sp.netloc, '', '', '')) + resto)


def genera_findvideos_api(ctx, nome='canale'):
    man = ctx.get('manifest')
    base = ctx['base']
    if man and man.get('sorgente'):
        src = man['sorgente']
        e = src['entry']
        corpo = e.get('post') or ''
        # l'id del titolo (o dell'episodio) compare nella richiesta in chiaro oppure dentro un valore base64
        cands = [x for x in ([ctx.get('primo_id', '')] + ctx.get('id_episodi', [])) if x]
        tr = trasforma_id(e['url'] + ' ' + corpo, cands)
        idv = tr['id'] if tr else ''
        b64 = tr if tr and tr['tipo'] == 'b64' else None
        url_t = e['url'].replace(idv, '{ID}') if idv and idv in e['url'] else e['url']
        if b64:
            corpo_t = corpo.replace(b64['token'], '{B64}')
        else:
            corpo_t = corpo.replace(idv, '{ID}') if idv and idv in corpo else corpo
        tipo = 'mpd' if re.search(r'\.mpd|dash', man['url'], re.I) else 'hls'
        if man.get('licenza_percorso'):
            lic_espr = "prendi(r, %s)" % py_str(man['licenza_percorso'])
        elif man.get('licenza'):
            lic = man['licenza'].replace(idv, '{ID}') if idv and idv in man['licenza'] else man['licenza']
            lic_espr = "%s.replace('{ID}', idv)" % py_str(lic)
        else:
            lic_espr = "''  # nessuna licenza DRM rilevata: stream in chiaro"
        url_espr = espr_url(url_t.split('?')[0], base) + (
            (" + '?' + " + py_str(urlsplit(url_t).query)) if urlsplit(url_t).query else '')
        return """
def findvideos(item):
    support.info(item)
    idv = item.idv
    url = (__URL__).replace('{ID}', idv)
    corpo = __CORPO__.replace('{ID}', idv)__B64__
    opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
    if corpo:
        opt['post'] = corpo
    r = httptools.downloadpage(url, **opt).json
    manifest = prendi(r, __PERCORSO__)
    licenza = __LICENZA__ if manifest else ''
    if not manifest or (__DRM__ and not licenza):
        # alcuni contenuti non hanno DRM: lo stream e un manifest in chiaro in un altro campo della risposta
        chiaro = url_in_chiaro(r)
        if chiaro:
            logger.info('Stream senza DRM: {}'.format(chiaro))
            it = item.clone(server='directo', url=chiaro, manifest='mpd' if '.mpd' in chiaro else 'hls',
                            drm='', license='', referer=host + '/', no_return=True)
            return support.server(item, itemlist=[it], Download=False, Videolibrary=False)
        logger.error('Stream non trovato', r)
        platformtools.dialog_ok('__NOME__', 'Stream non disponibile' if not manifest else 'Licenza non trovata')
        return []
    if not licenza:
        it = item.clone(server='directo', url=manifest, manifest='__TIPO__', drm='', license='',
                        referer=host + '/', no_return=True)
        return support.server(item, itemlist=[it], Download=False, Videolibrary=False)
    it = item.clone(server='directo', url=manifest, manifest='__TIPO__',
                    drm='com.widevine.alpha',
                    license=licenza + '|' + urlencode({'Content-Type': 'application/octet-stream',
                                                       'User-Agent': httptools.get_user_agent(),
                                                       'Origin': host, 'Referer': host + '/'}) + '|R{SSM}|',
                    referer=host + '/', no_return=True)
    return support.server(item, itemlist=[it], Download=False, Videolibrary=False)
""".replace('__URL__', url_espr).replace('__CORPO__', py_str(corpo_t)) \
            .replace('__B64__', ("\n    corpo = corpo.replace('{B64}', base64.b64encode(%s.replace('{ID}', idv).encode('utf-8')).decode('utf-8'))" % py_str(b64['formato'])) if b64 else '') \
            .replace('__PERCORSO__', py_str(src['path'])).replace('__TIPO__', tipo) \
            .replace('__LICENZA__', lic_espr).replace('__NOME__', nome) \
            .replace('__DRM__', 'True' if (man.get('licenza') or man.get('licenza_percorso')) else 'False')
    return """
def findvideos(item):
    support.info(item)
    # TODO: sorgente del video non rilevata automaticamente: se la pagina del titolo ha iframe
    # o link ai server, support.server li trova da solo
    return support.server(item, headers=headers)
"""


def genera_json(id_, nome, tipo, ricerca_globale=True, tipi=None):
    cat = {'movie': ['movie'], 'tvshow': ['tvshow'], 'anime': ['anime']}.get(tipo, ['movie'])
    if tipi:
        cat = [k for k in ('movie', 'tvshow', 'anime') if k in tipi]
    d = {
        'id': id_,
        'name': nome,
        'language': ['ita'],
        'active': True,
        'thumbnail': id_ + '.png',
        'banner': id_ + '.png',
        'categories': cat,
        'not_active': ['include_in_newest'],
        'settings': [
            {'id': 'include_in_global_search', 'type': 'bool', 'label': 'Includi in Ricerca Globale',
             'default': ricerca_globale, 'enabled': True, 'visible': True}
        ]
    }
    return json.dumps(d, indent=4, ensure_ascii=False) + '\n'


# ---------------------------------------------------------------------------
# 5. Programma principale
# ---------------------------------------------------------------------------

def scarica_grezzo(url):
    import requests
    try:
        return requests.get(url, headers={'User-Agent': CF['ua'] or UA}, cookies={c['name']: c['value'] for c in CF['cookies']}, timeout=20).text
    except Exception as e:
        return ''



def riproduci(s, args, rp, cattura, chiave):
    """Prova a far partire il video nella pagina aperta e ritorna le informazioni sul manifest."""
    rp('Provo a far partire il video...')
    pl = s.prova_play(attesa=args.attesa + 4)
    cattura[chiave] = {'url': pl['url'], 'cliccato': pl.get('cliccato'), 'net': pl['net']}
    man, lic = trova_manifest(pl['net'])
    if not man:
        rp('Nessun manifest rilevato (iframe e link ai server vanno gestiti da support.server).')
        return None
    m = man[0]
    rp('Manifest:', m['url'][:140])
    info = {'url': m['url'], 'licenza': '', 'sorgente': sorgente_manifest(pl['net'], m['url'])}
    if lic:
        info['licenza'] = lic[0]['url']
        rp('Licenza DRM:', lic[0]['method'], lic[0]['url'][:140])
        if info['sorgente']:
            info['licenza_percorso'] = percorso_valore(info['sorgente']['json'], lic[0]['url'].split('?')[0])
            if info['licenza_percorso']:
                rp('La licenza arriva dalla stessa risposta:', info['licenza_percorso'])
    if info['sorgente']:
        rp('Il manifest arriva da:', info['sorgente']['entry']['url'][:120], '| percorso:', info['sorgente']['path'])
    return info


def esplora_api(s, ctx, base, args, rp, cattura, soup, pagina_elenco, api, primo=''):
    """Per i siti con API: scopre sezioni e ordinamenti, poi apre un film e una serie per trovare episodi e riproduzione."""
    import posixpath
    sezioni, viste = [], set()
    tempo = min(args.attesa, 4)

    def tipo_elemento(el, chiavi, fallback):
        k = chiavi.get('type')
        if k:
            v = str(appiattisci(el).get(k, ''))
            return 'tvshow' if re.search(r'show|serie|tv|series', v, re.I) else 'movie'
        return fallback

    def aggiungi(nome, a, fallback):
        f = firma_richiesta(a['entry'])
        if f in viste:
            return None
        viste.add(f)
        pag = paginazione(a['entry'])
        if pag and pag['tipo'] == 'offset':
            pag['passo'] = len(a['lista'])
        z = {'nome': nome, 'tipo': tipo_elemento(a['lista'][0], a['chiavi'], fallback), 'entry': a['entry'],
             'lista': a['path'], 'pag': pag, 'api': a}
        sezioni.append(z)
        rp('Sezione:', nome, '| tipo:', z['tipo'], '| titoli:', len(a['lista']))
        return z

    def con_varianti(nome, a, fallback):
        var = s.varianti(attesa=tempo)
        base_label = next((v['label'] for v in var if v['base']), '')
        z = aggiungi(nome + (' ' + base_label if base_label and any(not v['base'] for v in var) else ''), a, fallback)
        for v in var:
            if v['base'] or not v['net']:
                continue
            a2 = trova_elenco_api(v['net'])
            if a2:
                aggiungi(nome + ' ' + v['label'], a2, fallback)
        return z

    # sezione di partenza e suoi ordinamenti
    fallback0 = ctx['tipo']
    nome0 = next((t for t, u in ctx['menu'] if u.rstrip('/') == pagina_elenco.rstrip('/')), '') or \
        (nome_da_url(pagina_elenco) if urlparse(pagina_elenco).path.strip('/') else 'Titoli')
    s.vai(pagina_elenco, attesa=tempo)
    con_varianti(nome0, api, fallback0)

    # altre sezioni: menu, percorsi dei titoli, link a contenuti gratuiti
    cand = []
    for t, u in ctx['menu']:
        cand.append((t, u))
    for el in api['lista'][:5]:
        piatto = appiattisci(el)
        for k in api['chiavi'].get('ids', []):
            v = str(piatto.get(k, ''))
            if v.startswith('/'):
                par = posixpath.dirname(v)
                if par and par != '/':
                    cand.append((nome_da_url(par), urljoin(base, par)))
    for a_ in soup.find_all('a', href=True):
        t = a_.get_text(' ', strip=True)
        if FREE_RE.search(t + ' ' + a_['href']) and len(t) < 40:
            cand.append((t or nome_da_url(a_['href']), urljoin(base, a_['href'])))
    visti = {pagina_elenco.rstrip('/')}
    n = 0
    for t, u in cand:
        u = u.split('#')[0]
        if u.rstrip('/') in visti or urlparse(u).netloc != urlparse(base).netloc:
            continue
        visti.add(u.rstrip('/'))
        if n >= 10:
            break
        n += 1
        e = s.vai(u, attesa=tempo)
        a2 = trova_elenco_api(e['net'])
        if a2:
            con_varianti(t, a2, fallback0)
    ctx['sezioni'] = sezioni
    rp('Sezioni trovate:', len(sezioni))

    # un film e una serie di esempio
    campioni = {}
    for z in sezioni:
        for el in z['api']['lista'][:20]:
            tp = tipo_elemento(el, z['api']['chiavi'], z['tipo'])
            campioni.setdefault(tp, (el, z['api']['chiavi']))
    ctx['id_episodi'] = []

    def apri(el, chiavi):
        piatto = appiattisci(el)
        url, idv = '', ''
        for k in chiavi.get('ids', []):
            v = str(piatto.get(k, ''))
            if (v.startswith('http') or v.startswith('/')) and not url:
                url = urljoin(base, v)
            elif v and not v.startswith('/') and not idv:
                idv = v
        return url, idv, piatto

    if 'movie' in campioni:
        el, chiavi = campioni['movie']
        url, idv, piatto = apri(el, chiavi)
        if not url and primo:
            url = primo  # nessun percorso nei dati: si usa il link della prima card
        if url:
            rp('Apro un film di esempio:', url)
            det = s.vai(url, attesa=args.attesa)
            cattura['dettaglio'] = {'url': det['url'], 'net': det['net']}
            ctx['primo_id'] = idv
            if idv and idv in det['url']:
                ctx['dettaglio'] = det['url'].replace(idv, '{}')
                if ctx['dettaglio'].startswith(base):
                    ctx['dettaglio'] = ctx['dettaglio'][len(base):]
            info = riproduci(s, args, rp, cattura, 'play')
            if info:
                ctx['manifest'] = info
    if 'tvshow' in campioni:
        el, chiavi = campioni['tvshow']
        url, idv, piatto = apri(el, chiavi)
        if url:
            rp('Apro una serie di esempio:', url)
            det = s.vai(url, attesa=args.attesa)
            cattura['serie'] = {'url': det['url'], 'net': det['net']}
            ep = trova_episodi_api(det['net'])
            if not ep:
                rp('Episodi: nessuna risposta JSON con stagioni ed episodi trovata nella pagina della serie.')
            else:
                e = ep['entry']
                valori = [idv] + [str(v) for v in piatto.values() if isinstance(v, (str, int)) and len(str(v)) >= 3]
                tr = trasforma_id((e['url'] or '') + ' ' + (e.get('post') or ''), valori)
                if not tr:
                    rp('ATTENZIONE: episodi trovati ma non so in quale punto della richiesta compare l\'id della serie.')
                else:
                    sp = urlsplit(e['url'])
                    rel = urlunsplit(('', '', sp.path, sp.query, '')) if sp.netloc == urlparse(base).netloc else e['url']
                    ch = dict(ep['chiavi'])
                    ctx['episodi_api'] = {'url': rel.replace(tr['id'], '{ID}'),
                                          'body': (e.get('post') or '').replace(tr['id'], '{ID}') if e.get('post') else '',
                                          'lista': ep['path'], 'chiavi': ch}
                    rp('Episodi: %d nella risposta, richiesta %s, stagione=%s episodio=%s titolo=%s' % (
                        len(ep['lista']), e['method'], ch.get('season'), ch.get('episode'), ch.get('title')))
                    pe = appiattisci(ep['lista'][0])
                    ctx['id_episodi'] = [str(pe[k]) for k in ch.get('ids', []) if k in pe]
            info = riproduci(s, args, rp, cattura, 'play_serie')
            if info and not ctx.get('manifest'):
                ctx['manifest'] = info
            elif info:
                rp('Riproduzione di un episodio rilevata (stessa sorgente del film).')


def analizza(url, args):
    rapporto = []

    def rp(*a):
        riga = ' '.join(str(x) for x in a)
        rapporto.append(riga)
        log(riga)

    base = '{0.scheme}://{0.netloc}'.format(urlparse(url))
    id_ = args.nome or id_da_url(url)
    nome = args.titolo or id_.capitalize()
    ctx = {'base': base, 'menu': [], 'tipo': 'movie', 'next': '', 'patron': '', 'episodi': None, 'patron_ep': '',
           'ricerca': None, 'api': None, 'search_api': '', 'pag': None, 'manifest': None}

    s = Sessione(headless=not (args.mostra or args.pausa), chromium=args.chromium, dns=DOH.get(args.dns))
    cattura = {}
    try:
        rp('Apro', url)
        elenco = s.vai(url, attesa=args.attesa)
        if args.pausa:
            input('Supera a mano eventuali controlli o banner nel browser, poi premi Invio qui... ')
            s.net = []
            s.page.reload(wait_until='domcontentloaded')
            s._assesta(args.attesa)
            elenco = s.stato()
        cattura['elenco'] = elenco
        soup = soup_di(elenco['html'])
        ctx['menu'] = trova_menu(soup, base)
        rp('Voci di menu trovate:', len(ctx['menu']))
        if not ctx['menu']:
            rp('Nessuna voce di menu: aggiungo la pagina di partenza come voce unica.')
            ctx['menu'] = [('Titoli', url)]

        # Se la home non ha l'elenco, prova la prima voce di menu
        card = trova_card(soup)
        api = trova_elenco_api(elenco['net'])
        if not card and not api and ctx['menu']:
            rp('Nessun elenco nella home, provo la prima voce di menu:', ctx['menu'][0][1])
            elenco = s.vai(ctx['menu'][0][1], attesa=args.attesa)
            cattura['elenco2'] = elenco
            soup = soup_di(elenco['html'])
            card = trova_card(soup)
            api = trova_elenco_api(elenco['net'])
        pagina_elenco = elenco['url']

        # Tipo di sito: HTML se il contenuto sta nell'html grezzo, altrimenti API
        patron = ''
        collaudo = (0, [], '')
        grezzo = normalizza(scarica_grezzo(pagina_elenco))
        if card:
            patron = costruisci_patron(card[len(card) // 2])
            collaudo_grezzo = collauda(patron, grezzo) if grezzo else (0, [], '')
            collaudo_dom = collauda(patron, normalizza(elenco['html']))
            rp('Card trovate nel DOM:', len(card), '| regex sul DOM:', collaudo_dom[0],
               '| regex sull\'html grezzo:', collaudo_grezzo[0])
            collaudo = collaudo_grezzo
        modo = None
        if card and collaudo[0] >= 3 and api:
            # tutte e due le strade funzionano: vale quella i cui titoli coincidono con la API
            th = titoli_html(patron, grezzo)
            ta = titoli_api(api)
            comuni = len(th & ta)
            rp('Titoli HTML:', len(th), '| titoli API:', len(ta), '| in comune:', comuni)
            modo = 'html' if th and comuni >= 0.5 * len(th) else 'api'
            if modo == 'api':
                rp('I titoli letti dall\'HTML non coincidono con quelli della API: scelgo la API.')
        elif card and collaudo[0] >= 3:
            modo = 'html'
        elif api:
            modo = 'api'
        elif card:
            modo = 'html'
            rp('ATTENZIONE: la regex non trova i titoli nell\'html grezzo: il sito genera la lista con JavaScript '
               'e non e stata trovata nessuna API JSON. S4Me non vede la pagina come il browser.')
        else:
            rp('Non ho trovato nessun elenco di titoli ne nell\'html ne nelle chiamate di rete.')
        ctx['modo'] = modo
        rp('Modalita scelta:', modo)

        if modo == 'html':
            ctx['patron'] = patron
            if card and collaudo_dom[0] < 0.7 * len(card):
                rp('ATTENZIONE: la regex trova %d titoli su %d card: controllare il patron.' % (collaudo_dom[0], len(card)))
            tipi = tipi_da_url([_href(c) for c in card]) if card else {}
            if tipi and '(?P<url>[^"]+)' in patron:
                alt = '|'.join(re.escape(x) for v in tipi.values() for x in v)
                ctx['patron'] = patron.replace('(?P<url>[^"]+)', '(?P<url>[^"]*?/(?P<type>' + alt + ')/[^"]*)', 1)
                ctx['tipi'] = tipi
                rp('Il sito mescola tipi diversi, riconosciuti dall\'url:', json.dumps(tipi))
            ctx['next'], prossima = trova_next(soup)
            rp('Pagina successiva:', prossima or 'non trovata')
            if collaudo[1]:
                rp('Esempi di risultati della regex:', json.dumps(collaudo[1], ensure_ascii=False)[:600])
            primo = ''
            for c0 in card:
                h0 = urljoin(base, _href(c0))
                if h0.rstrip('/') != base.rstrip('/') and urlparse(h0).path.strip('/'):
                    primo = h0
                    break
        elif modo == 'api':
            ctx['api'] = api
            ctx['pag'] = paginazione(api['entry'])
            if ctx['pag'] and ctx['pag']['tipo'] == 'offset':
                ctx['pag']['passo'] = len(api['lista'])
            rp('API elenco:', api['entry']['method'], api['entry']['url'][:120], '| lista:', api['path'],
               '| elementi:', len(api['lista']))
            rp('Campi:', json.dumps(api['chiavi'], ensure_ascii=False))
            rp('Paginazione:', json.dumps(ctx['pag']) if ctx['pag'] else 'non trovata (TODO)')
            if ctx['pag'] and ctx['pag']['tipo'] == 'cursore':
                rp('Paginazione a cursore: gestita dal canale generato (endCursor e hasNextPage).')
            el0 = api['lista'][0]
            ris, piatto = scegli_chiavi(el0)
            primo = ''
            for k in ris.get('ids', []):
                v = str(piatto.get(k, ''))
                if v.startswith('http') or v.startswith('/'):
                    primo = urljoin(base, v)
                    break
            if not primo and card:
                primo = urljoin(base, _href(card[0]))
            ctx['primo_id'] = str(piatto.get(ris['ids'][0], '')) if ris.get('ids') else ''
        else:
            primo = ''

        if ctx['menu'] and not args.tipo:
            ctx['tipo'] = tipo_da_testo(urlparse(pagina_elenco).path + ' ' + (ctx['menu'][0][0] if ctx['menu'] else ''))
        if args.tipo:
            ctx['tipo'] = args.tipo

        # Ricerca
        ric = trova_ricerca(soup, base)
        if ric:
            rp('Campo di ricerca:', ric['selettore'])
            s.vai(pagina_elenco, attesa=2)
            r = s.cerca(ric['selettore'], 'matrix', attesa=args.attesa)
            cattura['ricerca'] = {'url': r.get('url'), 'net': r.get('net', [])}
            if 'matrix' in r.get('url', '').lower():
                ricerca_url = r['url'].replace('matrix', '%s')
                ric['url_modello'] = ricerca_url[len(base):] if ricerca_url.startswith(base) else ricerca_url
                rp('Url di ricerca:', ric['url_modello'])
            else:
                for e in r.get('net', []):
                    if 'matrix' in e['url'].lower() and e['method'] == 'GET':
                        ctx['search_api'] = e['url']
                        rp('Ricerca via API:', e['url'][:120])
                        break
                    if e['method'] == 'POST' and 'matrix' in (e.get('post') or '').lower() \
                            and not RUMORE.search(e['url']) and 'Track' not in (e.get('post') or ''):
                        ctx['search_body'] = {'url': e['url'],
                                              'post': re.sub('matrix', '__TESTO__', e['post'], flags=re.I)}
                        rp('Ricerca via API (POST):', e['url'][:120])
                        break
            ctx['ricerca'] = ric

        if modo == 'api':
            esplora_api(s, ctx, base, args, rp, cattura, soup, pagina_elenco, api, primo)
            primo = ''  # il dettaglio e gia stato esplorato

        # Pagina di dettaglio
        if primo:
            rp('Apro il primo titolo:', primo)
            det = s.vai(primo, attesa=args.attesa)
            cattura['dettaglio'] = {'url': det['url'], 'net': det['net']}
            dsoup = soup_di(det['html'])
            eps = trova_episodi(dsoup)
            if eps:
                ctx['episodi'] = eps
                ep0 = eps[len(eps) // 2]
                campi = {'url': ('attr', 'a', 'href')}
                ctx['patron_ep'] = (_tagre(ep0) + r'[^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*'
                                    r'(?P<title>[^<]+?)\s*<') if ep0.name == 'a' else \
                    r'<a [^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'
                ctx['patron_ep'] = ctx['patron_ep'].replace('<a<', '<a')
                rp('Episodi rilevati:', len(eps), '(titolo esempio:', ep0.get_text(' ', strip=True)[:40] + ')')
                ctx['tipo'] = 'tvshow' if not args.tipo else args.tipo
            ifr = [i.get('src') for i in dsoup.find_all('iframe') if i.get('src')]
            rp('Iframe nella pagina:', ifr[:3] if ifr else 'nessuno')
            # url della pagina titolo con segnaposto
            if modo == 'api' and ctx.get('primo_id') and ctx['primo_id'] in det['url']:
                ctx['dettaglio'] = det['url'].replace(ctx['primo_id'], '{}')
                if ctx['dettaglio'].startswith(base):
                    ctx['dettaglio'] = ctx['dettaglio'][len(base):]
                    ctx['dettaglio'] = '{}' if False else ctx['dettaglio']

            # Riproduzione
            rp('Provo a far partire il video...')
            pl = s.prova_play(attesa=args.attesa + 4)
            cattura['play'] = {'url': pl['url'], 'cliccato': pl.get('cliccato'), 'net': pl['net']}
            man, lic = trova_manifest(pl['net'])
            if man:
                m = man[0]
                rp('Manifest:', m['url'][:140])
                info = {'url': m['url'], 'licenza': '', 'sorgente': sorgente_manifest(pl['net'], m['url'])}
                if lic:
                    info['licenza'] = lic[0]['url']
                    rp('Licenza DRM:', lic[0]['method'], lic[0]['url'][:140])
                    if info['sorgente']:
                        info['licenza_percorso'] = percorso_valore(info['sorgente']['json'], lic[0]['url'].split('?')[0])
                        if info['licenza_percorso']:
                            rp('La licenza arriva dalla stessa risposta:', info['licenza_percorso'])
                if info['sorgente']:
                    rp('Il manifest arriva da:', info['sorgente']['entry']['url'][:120],
                       '| percorso:', info['sorgente']['path'])
                ctx['manifest'] = info
            else:
                rp('Nessun manifest rilevato (iframe e link ai server vanno gestiti da support.server).')
    finally:
        s.chiudi()

    return id_, nome, ctx, cattura, rapporto, base


def main():
    ap = argparse.ArgumentParser(description='Genera un canale S4Me da un sito')
    ap.add_argument('url')
    ap.add_argument('--nome', help='id del canale (nome dei file)')
    ap.add_argument('--titolo', help='nome mostrato in S4Me')
    ap.add_argument('--tipo', choices=['movie', 'tvshow', 'anime'], help='forza il tipo di contenuti')
    ap.add_argument('--out', default='canali_generati')
    ap.add_argument('--attesa', type=int, default=5, help='secondi di attesa dopo ogni pagina')
    ap.add_argument('--mostra', action='store_true', help='browser visibile')
    ap.add_argument('--pausa', action='store_true',
                    help='browser visibile e pausa dopo la prima pagina: utile per superare Cloudflare o i banner a mano')
    ap.add_argument('--dns', default='cloudflare', choices=['cloudflare', 'google', 'nessuno'],
                    help='DNS over HTTPS per le richieste (predefinito cloudflare, come S4Me)')
    ap.add_argument('--flaresolverr', default=os.environ.get('FLARESOLVERR_URL', ''),
                    help='indirizzo di FlareSolverr (per esempio http://localhost:8191) per superare Cloudflare')
    ap.add_argument('--controlla-cf', action='store_true',
                    help='stampa true se il sito mostra la challenge di Cloudflare, false altrimenti, ed esce')
    ap.add_argument('--chromium', help='percorso di un chromium gia installato')
    args = ap.parse_args()
    if args.controlla_cf:
        print('true' if ha_challenge(args.url if '://' in args.url else 'https://' + args.url) else 'false')
        return
    faulthandler.dump_traceback_later(300, repeat=True)  # se si blocca, il log mostra dove
    srv = attiva_dns(args.dns)
    if srv:
        log('DNS over HTTPS attivo:', args.dns, srv)

    url = args.url if '://' in args.url else 'https://' + args.url
    if args.flaresolverr:
        flaresolverr(args.flaresolverr, url)
    id_, nome, ctx, cattura, rapporto, base = analizza(url, args)

    os.makedirs(args.out, exist_ok=True)
    if ctx['modo'] == 'api':
        py = genera_api(nome, ctx)
    else:
        if not ctx['patron']:
            ctx['patron'] = r'<a [^>]*?href="(?P<url>[^"]+)"[^>]*>.*?<img [^>]*?src="(?P<thumb>[^"]+)".*?(?P<title>[^<]+)<'
            rapporto.append('TODO: regex patron non generata, scritta una regex di esempio da adattare.')
        py = genera_html(nome, ctx)
    mancano = []
    if not ctx.get('manifest'):
        mancano.append('riproduzione (nessun manifest rilevato: findvideos generico con support.server)')
    if not ctx.get('ricerca') and not ctx.get('search_api'):
        mancano.append('ricerca')
    if ctx.get('modo') == 'api' and any(z['tipo'] == 'tvshow' for z in ctx.get('sezioni', [])) and not ctx.get('episodi_api'):
        mancano.append('episodi delle serie (nessuna richiesta di episodi rilevata)')
    if mancano:
        rapporto.append('INCOMPLETO, da completare a mano: ' + '; '.join(mancano))
    open(os.path.join(args.out, id_ + '.py'), 'w', encoding='utf-8').write(py)
    open(os.path.join(args.out, id_ + '.json'), 'w', encoding='utf-8').write(genera_json(id_, nome, ctx['tipo'], tipi=ctx.get('tipi')))
    open(os.path.join(args.out, 'riga_channels_json.txt'), 'w', encoding='utf-8').write(
        '        "%s": "%s",\n' % (id_, base))
    rapporto += ['', 'File scritti in %s: %s.py, %s.json, riga_channels_json.txt' % (args.out, id_, id_),
                 'Da fare a mano: copiare i file in channels/, aggiungere la riga in channels.json (sezione direct), '
                 'caricare l\'icona %s.png nella repo media.' % id_]
    open(os.path.join(args.out, id_ + '_rapporto.txt'), 'w', encoding='utf-8').write('\n'.join(rapporto) + '\n')
    # la cattura serve per capire cosa e successo, senza i corpi troppo grandi
    for st in cattura.values():
        for e in st.get('net', []):
            if RUMORE.search(e['url']) or 'TrackSraEvent' in (e.get('post') or '') or 'GetFinalClickoutUrl' in (e.get('post') or ''):
                e['body'] = ''
            elif e.get('body') and len(e['body']) > 150000:
                e['body'] = e['body'][:150000] + '...(tagliato)'
    open(os.path.join(args.out, id_ + '_cattura.json'), 'w', encoding='utf-8').write(
        json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'html'} for k, v in cattura.items()},
                   indent=1, ensure_ascii=False))
    log('Fatto. File in', os.path.abspath(args.out))


if __name__ == '__main__':
    main()
