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

import dati_incorporati as di
import esplora_dati as ed
import riproduzione as rip
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


def inertia_da_html(html):
    """Dati di una pagina Inertia.js (attributo data-page), oppure None."""
    from html import unescape
    m = re.search(r'<[a-z]+[^>]*\sdata-page="([^"]+)"', html or '')
    if not m:
        return None
    try:
        d = json.loads(unescape(m.group(1)))
    except Exception:
        return None
    return d if isinstance(d, dict) and 'props' in d else None


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
    def __init__(self, headless=True, chromium=None, dns=None, proxy=None, chrome=False):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {'headless': headless}
        if chrome:
            kw['channel'] = 'chrome'  # Google Chrome ha il Widevine: serve ai siti che non avviano il player senza DRM
        if chromium:
            kw['executable_path'] = chromium
        if dns:
            # Chromium: DoH integrato, con l'indirizzo IP del provider come modello
            kw['args'] = ['--enable-features=DnsOverHttps',
                          '--force-fieldtrial-params=DnsOverHttps.Fallback:Fallback/true/Templates/https%3A%2F%2F' + dns + '%2Fdns-query',
                          '--force-fieldtrials=DnsOverHttps/Fallback']
        if proxy:
            pu = urlsplit(proxy)
            kw['proxy'] = {'server': '%s://%s' % (pu.scheme or 'http', pu.netloc.split('@')[-1])}
            if pu.username:
                kw['proxy']['username'] = pu.username
                kw['proxy']['password'] = pu.password or ''
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
            if req.method == 'POST' and req.resource_type in ('xhr', 'fetch'):
                entry['hdr'] = {k: v for k, v in req.headers.items() if k.lower() not in (
                    'host', 'content-length', 'origin', 'referer', 'user-agent', 'cookie', 'accept-encoding',
                    'connection') and not k.lower().startswith(('sec-', ':'))}
            if req.headers.get('x-inertia'):
                entry['inertia'] = True
            if re.search(r'json|text|mpegurl|dash|xml|javascript', ct) and 'event-stream' not in ct and req.resource_type in (
                    'xhr', 'fetch', 'document', 'other'):
                entry['_resp'] = r  # il corpo si legge dopo, fuori dal gestore dell'evento
            self.net.append(entry)
        except Exception:
            pass

    def chiudi_banner(self):
        # banner dei cookie: se coprono la pagina bloccano click e menu
        for sel in ['#uc-btn-accept-banner', 'button[data-testid="uc-accept-all-button"]', '#onetrust-accept-btn-handler',
                    'button:has-text("Accetta tutto")', 'button:has-text("Accetta")', 'button:has-text("Accept all")',
                    'button:has-text("Consenti tutto")', 'button:has-text("Accetto")']:
            try:
                loc = self.page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    loc.first.click(timeout=2000)
                    self.page.wait_for_timeout(500)
                    return True
            except BaseException:
                continue
        return False

    def vai(self, url, attesa=4, timeout=60000):
        self.net = []
        self.page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        self.page.wait_for_timeout(1500)
        self.chiudi_banner()
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
        dp = inertia_da_html(html)
        if dp is None:
            # dopo l'avvio della pagina l'attributo puo sparire dal DOM: si legge dal documento scaricato
            for e in net:
                if e.get('tipo') == 'document' and 'html' in e.get('ct', '') and e.get('body'):
                    dp = inertia_da_html(e['body'])
                    if dp is not None:
                        break
        if dp is not None and not any(e.get('inertia') and e['url'] == self.page.url for e in net):
            # siti Inertia.js: la pagina porta con se i dati (attributo data-page), come se fossero la risposta di una API
            net.append({'url': self.page.url, 'method': 'GET', 'status': 200, 'tipo': 'document',
                        'ct': 'application/json', 'post': None, 'body': json.dumps(dp, ensure_ascii=False)[:3000000],
                        'inertia': True, 'versione': dp.get('version', '')})
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
                if sel.evaluate("e => !!e.closest('footer, header, nav')"):
                    continue
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

    def cerca_dinamica(self, testo='matrix', attesa=4):
        """Ricerca senza modulo: apre l'icona o il campo di ricerca (anche in un pannello), scrive il testo e invia."""
        self.net = []
        campi = ('input[type=search], input[placeholder*="erca" i], input[placeholder*="earch" i], '
                 'input[name*="search" i], input[name="q"], input[aria-label*="erca" i], input[aria-label*="earch" i]')

        def visibile():
            loc = self.page.locator(campi)
            for i in range(min(loc.count(), 8)):
                try:
                    if loc.nth(i).is_visible():
                        return loc.nth(i)
                except Exception:
                    continue
            return None
        diag = []
        box = visibile()
        if not box:
            for sel in ('button:has(img[alt*="erca" i])', 'button:has(img[alt*="earch" i])', 'button:has(img[src*="search" i])',
                        'button:has(svg[class*="search" i])', 'a:has(img[alt*="erca" i])', 'a:has(img[alt*="earch" i])',
                        'button:has-text("Cerca")', '[aria-label*="erca" i]', '[aria-label*="earch" i]', '[title*="erca" i]', '[title*="earch" i]',
                        'a[href*="cerca"]', 'a[href*="search"]', 'button[class*="search" i]', '[data-testid*="search" i]',
                        '[class*="search" i]'):
                try:
                    loc = self.page.locator(sel)
                    n = loc.count()
                    diag.append('%s: %d' % (sel, n))
                    for i in range(min(n, 4)):
                        vis = loc.nth(i).is_visible()
                        if vis:
                            loc.nth(i).click(timeout=3000, force=True)
                            self.page.wait_for_timeout(1800)
                            box = visibile()
                            diag.append('  cliccato %s #%d, url %s, campo %s' % (sel, i, self.page.url[:80], 'si' if box else 'no'))
                            if box:
                                break
                except Exception as ex:
                    diag.append('  errore %s: %s' % (sel, str(ex)[:80]))
                    continue
                if box:
                    break
        if not box:
            try:
                diag.append('input presenti: ' + ' | '.join(
                    self.page.eval_on_selector_all('input', 'els => els.map(e => (e.type||"") + "/" + (e.name||"") + "/" + (e.placeholder||"") + "/" + (e.offsetParent ? "v" : "n"))')[:12]))
            except Exception:
                pass
            return {'errore': 'campo di ricerca non trovato', 'url': self.page.url, 'html': '', 'net': [], 'diagnosi': diag}
        try:
            self.net = []
            box.click(timeout=3000)
            box.type(testo, delay=80, timeout=8000)
            box.press('Enter', timeout=3000)
        except Exception as e:
            return {'errore': str(e), 'url': self.page.url, 'html': '', 'net': []}
        self._assesta(attesa)
        st = self.stato()
        st['campo_dinamico'] = True
        return st

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
        # ogni classe e un elemento a parte: l'ordine e le classi in piu (is-current, active...) non devono contare
        scelte = sorted(cl, key=lambda x: -len(x))[:3]
        for t in sorted(scelte, key=cl.index):
            parte += r'(?=[^>]*class="(?:[^"]*\s)?' + re.escape(t) + r'(?:\s[^"]*)?")'
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
                              r'>\s*(?P<title>[^<]+?)(?:\s*\((?P<lang>ITA|SUB[\ \-]?ITA|Sub[\ \-]?Ita)\))?\s*<'))
            else:
                pezzi.append((p if p is not None else 3,
                              _tagre(tag) + r'[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)(?:\s*\((?P<lang>ITA|SUB[\ \-]?ITA|Sub[\ \-]?Ita)\))?\s*<'))
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
        paginata = re.search(r'(page|pagina|paged|[?&]p=|[?&]pg=|/\d+/?$)', a['href'], re.I)
        if (paginata and re.search(r'(next|success|avanti|prossim)', cl + ' ' + aria, re.I)) or \
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


def trova_ricerca_payload(net, testo='matrix'):
    """Richiesta GET il cui ultimo pezzo dell'indirizzo e un JSON in base64 che contiene il testo cercato."""
    import base64 as b64
    trovate = []
    for e in net:
        if e.get('method') != 'GET':
            continue
        parti = urlsplit(e['url'])
        seg = parti.path.rsplit('/', 1)[-1]
        if len(seg) < 8:
            continue
        try:
            grezzo = b64.urlsafe_b64decode(seg + '=' * (-len(seg) % 4)).decode('utf-8')
            pay = json.loads(grezzo)
        except Exception:
            continue
        if not isinstance(pay, dict) or testo not in grezzo.lower():
            continue
        def marca(v):
            if isinstance(v, dict):
                return {k: marca(x) for k, x in v.items()}
            return '__TESTO__' if isinstance(v, str) and v.lower() == testo else v
        payload = marca(pay)
        if '__TESTO__' not in json.dumps(payload):
            continue
        stile = None
        for sep in ((',', ':'), (', ', ': ')):
            for ordine in (True, False):
                rid = b64.urlsafe_b64encode(json.dumps(pay, separators=sep, sort_keys=ordine).encode()).decode().rstrip('=')
                if rid == seg:
                    stile = (sep, ordine)
                    break
            if stile:
                break
        stile = stile or ((',', ':'), True)
        trovate.append({'prefisso': parti.path[:len(parti.path) - len(seg)], 'payload': payload,
                        'separatori': stile[0], 'ordinate': stile[1], 'esempio': e['url'][:160]})
    if not trovate:
        return None

    def punti(t):
        # la ricerca vera e quella con la pagina e senza un limite basso (i suggerimenti mentre si scrive hanno un limite)
        chiavi = set(t['payload'])
        return ('page' in chiavi or 'pagina' in chiavi or 'offset' in chiavi, 'limit' not in chiavi, trovate.index(t))
    return max(trovate, key=punti)


def trova_episodi(soup):
    """Sulla pagina di dettaglio cerca un gruppo di link che sembrano episodi."""
    cand = {}
    for a in soup.find_all('a', href=True):
        t = a.get_text(' ', strip=True) + ' ' + (a.get('title') or '')
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


TIPO_VALORE_RE = re.compile(r'^(movie|film|tv|tvshow|tv_show|series|serie|show|anime|episode)s?$', re.I)


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
    if 'type' not in ris:
        for k in sorted(chiavi, key=lambda x: x.count('.')):
            if ultima(k).lower() in ('type', 'tipo', 'kind', 'content_type', 'contenttype', 'media_type') and \
                    isinstance(piatto[k], str) and TIPO_VALORE_RE.match(piatto[k]):
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


def html_pulito(html, limite=100000):
    """Pagina senza script, stili e svg, per capire com'e fatta senza scaricare megabyte."""
    h = re.sub(r'<(script|style|svg|noscript)\b.*?</\1>', '', html or '', flags=re.S | re.I)
    return re.sub(r'\s+', ' ', h)[:limite]


def dominio_base(url):
    """Parte principale del dominio (justwatch per apis.justwatch.com e www.justwatch.com)."""
    h = urlparse(url).netloc.lower().split(':')[0].split('.')
    return h[-2] if len(h) >= 2 else h[0]


SITO_BASE = ['']


def trova_elenco_api(net):
    """Tra le risposte JSON sceglie la lista di titoli piu grande (solo richieste del sito, non di terze parti)."""
    best = None
    for e in net:
        if not e.get('body') or 'json' not in e.get('ct', ''):
            continue
        if RUMORE.search(e['url']) or (SITO_BASE[0] and dominio_base(e['url']) != SITO_BASE[0]):
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
            if e.get('inertia') and not (ris.get('type') or ris.get('year') or ris.get('thumb')):
                continue  # nei dati di pagina Inertia servono segni di un vero titolo (tipo, anno o locandina)
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
            padre = None
            if not sk and ek and '.' in path:
                # la stagione puo stare nell'oggetto che contiene l'elenco (per esempio loadedSeason.number)
                pp = path.rsplit('.', 1)[0]
                oggetto = leggi(j, pp)
                if isinstance(oggetto, dict) and SEASON_RE.match(pp.split('.')[-1].replace('loaded', '').replace('current', '')):
                    padre = pp
            if (not sk and not padre) or not ek:
                continue
            ris, _ = scegli_chiavi(dicts[0])
            if sk:
                ris['season'] = sk
            ris['episode'] = ek
            if not best or len(dicts) > len(best['lista']):
                best = {'entry': e, 'path': path, 'lista': dicts, 'chiavi': ris, 'json': j, 'stagione_padre': padre}
    return best


SORT_PROVA = ['POPULAR', 'TRENDING', 'ALPHABETICAL', 'RANDOM', 'RELEASE_YEAR', 'TMDB_POPULARITY', 'IMDB_SCORE',
              'LAST_ADDED', 'NEWEST', 'RATING', 'TITLE', 'POPULARITY']
SORT_NOMI = {'POPULAR': 'Popolari', 'TRENDING': 'Di tendenza', 'ALPHABETICAL': 'Ordine alfabetico', 'RANDOM': 'Casuale',
             'RELEASE_YEAR': 'Anno di uscita', 'TMDB_POPULARITY': 'Popolarità TMDB', 'IMDB_SCORE': 'Punteggio IMDb',
             'LAST_ADDED': 'Ultimi aggiunti', 'NEWEST': 'Più recenti', 'RATING': 'Valutazione', 'TITLE': 'Titolo',
             'POPULARITY': 'Popolari'}
LINGUA_RE = re.compile(r'(lang|country|locale|region|culture)', re.I)


def variabili_di(post):
    """Ritorna (json completo, dizionario delle variabili) di una richiesta con corpo JSON."""
    try:
        j = json.loads(post)
    except Exception:
        return None, None
    v = j.get('variables') if isinstance(j, dict) and isinstance(j.get('variables'), dict) else (j if isinstance(j, dict) else None)
    return j, v


def percorsi_variabili(v, pre=(), prof=0):
    out = []
    for k, val in v.items():
        if isinstance(val, dict) and prof < 3:
            out += percorsi_variabili(val, pre + (k,), prof + 1)
        else:
            out.append((pre + (k,), val))
    return out


def imposta(v, percorso, valore):
    for k in percorso[:-1]:
        v = v[k]
    v[percorso[-1]] = valore


def differenze_variabili(post1, post2):
    _, a = variabili_di(post1 or '')
    _, b = variabili_di(post2 or '')
    if a is None or b is None:
        return {}
    da, db = dict(percorsi_variabili(a)), dict(percorsi_variabili(b))
    return {p: (da.get(p), db.get(p)) for p in set(da) | set(db) if da.get(p) != db.get(p)}


def solo_lingua(post1, post2):
    d = differenze_variabili(post1, post2)
    return bool(d) and all(LINGUA_RE.search('.'.join(p)) for p in d)


def leggi(d, path):
    for p in path.split('.'):
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and p.isdigit() and int(p) < len(d):
            d = d[int(p)]
        elif isinstance(d, list) and d and isinstance(d[0], dict) and not p.isdigit():
            d = d[0].get(p)  # percorso senza indice: si legge il primo elemento della lista
        else:
            return None
    return d


STATO_API = {'guasti': 0}


def posta_via_pagina(s, url, corpo):
    """Fa partire la richiesta dal browser vero: sostituisce il corpo della prima richiesta GraphQL della pagina,
    cosi partono le stesse intestazioni, cookie e controlli del sito (una richiesta ricostruita puo essere respinta)."""
    risultato = {}
    chiave = url.split('?')[0]

    def gestore(route, request):
        try:
            pd = request.post_data or ''
            if (not risultato.get('fatto') and request.method == 'POST' and chiave in request.url
                    and not re.search(r'"operationName"\s*:\s*"(Track|Register|Send)', pd)):
                risultato['fatto'] = True
                risultato['orig'] = pd
                route.continue_(post_data=corpo)
            else:
                route.continue_()
        except BaseException:
            try:
                route.continue_()
            except BaseException:
                pass

    s.page.route('**/*graphql*', gestore)
    try:
        s.net = []
        s.page.reload(wait_until='domcontentloaded', timeout=30000)
        s.page.wait_for_timeout(6000)
        st = s.stato()
    except BaseException:
        return None
    finally:
        try:
            s.page.unroute('**/*graphql*', gestore)
        except BaseException:
            pass
    for e in st['net']:
        if e.get('post') in (corpo, risultato.get('orig')) and (e.get('body') or '').lstrip()[:1] in ('{', '['):
            return e['body']
    return None


def posta_json(s, url, corpo, hdr=None):
    """POST JSON con le intestazioni della richiesta originale: dalla pagina, poi dal browser vero, poi dal contesto.
    Riprova se la risposta non e JSON (limite di richieste, risposta vuota) e dice cosa ha ricevuto."""
    h = dict(hdr or {})
    h.setdefault('content-type', 'application/json')
    errori = []
    for tentativo in range(2):
        stato, testo = None, None
        try:
            r = s.page.evaluate(
                "async ([u, b, h]) => { const r = await fetch(u, {method: 'POST', headers: h, body: b, credentials: 'include'}); "
                "return [r.status, await r.text()]; }", [url, corpo, h])
            stato, testo = r[0], r[1]
        except BaseException as ex:
            errori.append('fetch nella pagina (%s): %s' % (s.page.url[:60], str(ex)[:60]))
        if testo is None:
            try:
                h2 = dict(h)
                h2['referer'] = s.page.url
                h2['origin'] = '{0.scheme}://{0.netloc}'.format(urlparse(s.page.url))
                r = s.ctx.request.post(url, data=corpo, headers=h2, timeout=20000)
                stato, testo = r.status, r.text()
                errori.append('intestazioni della risposta: %s' % json.dumps(
                    {k: v[:80] for k, v in r.headers.items() if k.lower() not in ('set-cookie', 'cookie')}))
            except BaseException as ex:
                errori.append('richiesta del contesto: %s' % str(ex)[:60])
        if testo is not None and testo.lstrip()[:1] in ('{', '['):
            return testo
        if testo is not None:
            errori.append('risposta non JSON (stato %s, %d byte): %r' % (stato, len(testo), testo[:400]))
        if tentativo == 1:
            via = posta_via_pagina(s, url, corpo)
            if via:
                return via
            errori.append('anche la richiesta fatta partire dalla pagina non ha dato una risposta')
        else:
            # il sito limita le richieste al minuto: si aspetta che la finestra si svuoti
            s.page.wait_for_timeout(20000 if stato == 429 else 5000)
    STATO_API['guasti'] += 1
    raise RuntimeError(' | '.join(dict.fromkeys(errori)))


def operazione_di(post):
    try:
        return json.loads(post).get('operationName') or ''
    except Exception:
        return ''


def filtro_da_cache(s, pagine_free, api, rp):
    """La pagina dei contenuti gratuiti ha gia caricato l'elenco: la cache Apollo conserva il filtro usato
    (per esempio packages e monetizationTypes) nel nome della richiesta. Si legge senza fare altre richieste."""
    j0, v0 = variabili_di(api['entry'].get('post') or '')
    if v0 is None:
        return {}
    p_pack = p_mon = None
    for pth, val in percorsi_variabili(v0):
        if p_pack is None and re.search(r'package', pth[-1], re.I) and isinstance(val, list):
            p_pack = pth
        if p_mon is None and re.search(r'monetiz', pth[-1], re.I) and isinstance(val, list):
            p_mon = pth
    if not p_pack:
        return {}
    for u in pagine_free[:2]:
        try:
            s.vai(u, attesa=3, timeout=25000)
            chiavi = s.page.evaluate("() => { const c = window.__APOLLO_CLIENT__; if (!c) return []; "
                                     "const r = c.cache.extract().ROOT_QUERY || {}; return Object.keys(r); }")
        except BaseException as ex:
            rp('Filtro gratuito dalla cache: pagina non letta:', str(ex)[:100])
            continue
        for k in chiavi or []:
            m = re.search(r'"packages"\s*:\s*(\[[^\]]*\])', k)
            if m:
                try:
                    pk = json.loads(m.group(1))
                except Exception:
                    continue
                if not pk:
                    continue
                f = {p_pack: pk}
                mm = re.search(r'"monetizationTypes"\s*:\s*(\[[^\]]*\])', k)
                if p_mon and mm:
                    try:
                        f[p_mon] = json.loads(mm.group(1))
                    except Exception:
                        pass
                rp('Filtro gratuito letto dalla cache della pagina', u, ':', json.dumps({'.'.join(a): b for a, b in f.items()}))
                return f
    rp('Filtro gratuito: nella cache delle pagine non c\'e un filtro sui pacchetti')
    return {}


def trova_filtro_free(s, api, pagine_free, rp):
    """Ricava il filtro dei contenuti gratuiti interrogando l'elenco dei fornitori dell'API GraphQL."""
    e = api['entry']
    if 'graphql' not in e['url'] or not e.get('post'):
        return {}
    j0, v0 = variabili_di(e['post'])
    if v0 is None:
        return {}
    p_pack = p_mon = None
    paese = lingua = None
    for pth, val in percorsi_variabili(v0):
        if p_pack is None and re.search(r'package', pth[-1], re.I) and isinstance(val, list):
            p_pack = pth
        if p_mon is None and re.search(r'monetiz', pth[-1], re.I) and isinstance(val, list):
            p_mon = pth
        if pth[-1] == 'country' and isinstance(val, str):
            paese = val
    if not p_pack:
        rp('Filtro gratuito: la richiesta non ha una variabile dei pacchetti')
        return {}
    paese = paese if paese and re.fullmatch(r'[A-Z]{2}', paese) else 'IT'
    nomi = []
    for u in pagine_free:
        sl = urlparse(u).path.strip('/').split('/')
        nomi += [re.sub(r'[^a-z0-9]', '', x.lower()) for x in sl[-2:] if x]
    q = '{ packages(country: %s, platform: WEB) { shortName clearName technicalName } }' % paese
    try:
        corpo = posta_json(s, e['url'], json.dumps({'query': q}), e.get('hdr'))
        pacchetti = (json.loads(corpo).get('data') or {}).get('packages') or []
    except BaseException as ex:
        rp('Filtro gratuito: elenco pacchetti non letto:', str(ex)[:1500])
        return {}
    rp('Filtro gratuito: pacchetti letti dall API:', len(pacchetti))
    for pk in pacchetti:
        cn = re.sub(r'[^a-z0-9]', '', (pk.get('clearName') or '').lower())
        if cn and (cn in nomi or any(cn == n for n in nomi)) and FREE_RE.search(' '.join(pagine_free) + ' ' + (pk.get('clearName') or '')):
            f = {p_pack: [pk['shortName']]}
            if p_mon:
                f[p_mon] = ['FREE']
            rp('Filtro gratuito ricavato dall API:', pk.get('clearName'), '->', pk['shortName'])
            return f
    rp('Filtro gratuito: nessun pacchetto corrisponde a', nomi[:4])
    return {}


def sonda_api(s, ctx, api, rp, filtro_free, altre=()):
    """Prova a rigiocare la richiesta dell'elenco cambiando tipo, ordinamento e filtro gratuito."""
    e = api['entry']
    if e.get('method') != 'POST' or not e.get('post'):
        return []
    j0, v0 = variabili_di(e['post'])
    if v0 is None:
        return []
    chiave_tipo = api['chiavi'].get('type')
    tipi_visti = set()
    if chiave_tipo:
        for lst_ in [api['lista']] + [z['api']['lista'] for z in altre]:
            tipi_visti |= {str(appiattisci(x).get(chiave_tipo, '')).upper() for x in lst_}
        tipi_visti = sorted(tipi_visti - {''})

    errori = []

    def forma_tipo(t):
        return [t] if isinstance(dict(percorsi_variabili(v0)).get(p_tipo), list) else t

    guasti = []
    cache_r = {}
    base_mod = list(filtro_free.items())

    def rigioca(modifiche):
        if len(guasti) >= 2:  # l'API non risponde in JSON: inutile insistere con le altre prove
            return None, None
        j, v = variabili_di(e['post'])
        for pth, val in list(base_mod) + list(modifiche):  # il filtro gratuito vale per tutte le prove
            imposta(v, pth, val)
        chiave_c = json.dumps(j, sort_keys=True)
        if chiave_c in cache_r:
            risp, corpo = cache_r[chiave_c]
        else:
            try:
                corpo = posta_json(s, e['url'], json.dumps(j), e.get('hdr'))
                s.page.wait_for_timeout(3000)  # richieste distanziate per non superare il limite del sito
                risp = json.loads(corpo)
                cache_r[chiave_c] = (risp, corpo)
            except BaseException as ex:
                errori.append('richiesta fallita: %s' % str(ex)[:1500])
                guasti.append(1)
                return None, None
        lst = leggi(risp, api['path']) if isinstance(risp, dict) else None
        if isinstance(risp, dict) and risp.get('errors'):
            errori.append('errore API: %s' % json.dumps(risp['errors'], ensure_ascii=False)[:160])
            return None, None
        if not isinstance(lst, list) or not lst:
            errori.append('risposta senza elenco: %s' % corpo[:120])
            return None, None
        return json.dumps(j), [x for x in lst if isinstance(x, dict)]

    p_tipo = p_sort = None
    for pth, val in percorsi_variabili(v0):
        nome = pth[-1]
        if p_tipo is None and re.search(r'type', nome, re.I) and tipi_visti and (
                isinstance(val, list) or (isinstance(val, str) and val.isupper())):
            p_tipo = pth
        if p_sort is None and re.search(r'sort', nome, re.I) and isinstance(val, str) and val.isupper():
            p_sort = pth
    rp('Sonda API: variabile dei tipi =', '.'.join(p_tipo) if p_tipo else 'nessuna',
       '| variabile dell\'ordinamento =', '.'.join(p_sort) if p_sort else 'nessuna')
    base_mod = list(filtro_free.items())
    tipi_ok = []
    if p_tipo:
        for t in tipi_visti:
            post, lst = rigioca([(p_tipo, forma_tipo(t))])
            if lst:
                chiave = api['chiavi'].get('type')
                if all(str(appiattisci(x).get(chiave, '')).upper() == t for x in lst):
                    tipi_ok.append((t, 'tvshow' if re.search(r'show|serie|tv', t, re.I) else 'movie'))
    sort_ok = []
    sequenze = set()
    if p_sort:
        for so in SORT_PROVA:
            mod = [(p_sort, so)] + ([(p_tipo, forma_tipo(tipi_ok[0][0]))] if tipi_ok else [])
            post, lst = rigioca(mod)
            if lst:
                seq = tuple(str(appiattisci(x).get(api['chiavi'].get('title', ''), '')) for x in lst[:10])
                if seq not in sequenze:  # un alias con gli stessi risultati non serve
                    sequenze.add(seq)
                    sort_ok.append(so)
    rp('Sonda API: tipi riconosciuti =', [t for t, _ in tipi_ok], '| ordinamenti riconosciuti =', sort_ok)
    for er in sorted(set(errori))[:4]:
        rp('Sonda API, motivo dei rifiuti:', er)
    sezioni = []
    for t, tp in (tipi_ok or [(None, ctx['tipo'])]):
        for so in (sort_ok or [None]):
            mod = list(base_mod)
            if t and p_tipo:
                mod.append((p_tipo, forma_tipo(t)))
            if so and p_sort:
                mod.append((p_sort, so))
            if not mod and not so:
                continue
            post, lst = rigioca(mod)
            if not lst:
                continue
            ent = dict(e)
            ent['post'] = post
            ent['body'] = None
            nome = SORT_NOMI.get(so, (so or 'Titoli').replace('_', ' ').title()) if so else \
                ('Film' if tp == 'movie' else 'Serie TV')
            sezioni.append({'nome': nome, 'tipo': tp, 'entry': ent, 'gratis': bool(base_mod), 'lista': api['path'], 'pag': paginazione(e),
                            'api': {'entry': ent, 'path': api['path'], 'lista': lst, 'chiavi': api['chiavi']}})
    return sezioni


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


def genera_menu(voci, tipo_default, azioni=None):
    film, serie, anime, top = [], [], [], []
    for nome, full in voci:
        t = tipo_da_testo(nome)
        if t == 'movie' and not re.search(r'(film|movie|cinema)', nome, re.I):
            t = tipo_default
        path = urlparse(full).path + (('?' + urlparse(full).query) if urlparse(full).query else '')
        riga = "('%s', ['%s', '%s', '', '%s'])" % (nome.replace("'", ''), path, (azioni or {}).get(full, 'peliculas'), 'tvshow' if t == 'anime' else t)
        top.append(riga)
    righe = ['    top = [' + ',\n           '.join(top) + ']'] if top else []
    return '\n'.join(righe)


def genera_html(nome, ctx):
    cod = HEADER.replace('__NOME__', nome)
    menu = genera_menu(ctx['menu'], ctx['tipo'], ctx.get('azioni_menu'))
    cod += '''
@support.menu
def mainlist(item):
''' + (menu + '\n' if menu else '') + '''    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = '__AZIONE__'
''' + ("    anime = True\n" if ctx.get('anime') else '') + '''    patron = __PATRON__
''' + ("    patronNext = " + raw(ctx['next']) + "\n" if ctx['next'] else "    # patronNext: pagina successiva non trovata\n")
    tipi = ctx.get('tipi') or {}
    if tipi:
        cod = cod.replace('__AZIONE__', 'findvideos')
        righe = "    typeContentDict = %s\n" % json.dumps({k: v for k, v in tipi.items() if k in ('movie', 'tvshow', 'anime')})
        if tipi.get('tvshow'):
            righe += "    typeActionDict = %s\n" % json.dumps({'episodios': tipi['tvshow']})
        cod = cod.replace("    #debug = True  # apre regex101", righe + "    #debug = True  # apre regex101", 1)
    else:
        cod = cod.replace('__AZIONE__', 'episodios' if ctx['episodi'] and ctx['tipo'] in ('tvshow', 'anime') else 'findvideos')
    cod = cod.replace('__PATRON__', raw(ctx['patron']))
    cod += '''    #debug = True  # apre regex101 con pagina e regex
'''
    if (ctx.get('regola_serie') or ctx.get('regola_serie2')) and ctx['episodi']:
        cod += '''
    def itemHook(item):
        # la scheda puo puntare a un episodio: la lista episodi sta nella pagina del titolo
'''
        for k in ('regola_serie', 'regola_serie2'):
            if ctx.get(k):
                cod += "        item.url = re.sub(%s, %s, item.url)\n" % (raw(ctx[k][0]), raw(ctx[k][1]))
        cod += "        return item\n"
    cod += '''    return locals()

'''
    if ctx['episodi']:
        cod += '''
@support.scrape
def episodios(item):
    support.info(item)
    action = 'findvideos'
''' + ("    anime = True\n" if ctx.get('anime') else '') + '''__STAGIONE__    patron = __PATRONEP__
__PATRONB__    if '(?P<episode>' in patron and '(?P<season>' not in patron and not item.season:
        # nessuna stagione nel sito: una sola, cosi S4Me mostra 1x01 e cerca i titoli degli episodi su TMDB
        item.season = '1'
    #debug = True

    def itemHook(it):
        # senza season sull'episodio S4Me salta la ricerca dei titoli su TMDB
        if item.season:
            it.season = item.season
        return it

    def itemlistHook(itemlist):
        # S4Me scrive il titolo dell'episodio solo nelle info, non nell'etichetta: lo aggiungo accanto a 1x01
        if config.get_setting('episode_info') and itemlist and itemlist[0].season:
            try:
                tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
            except Exception:
                pass
            for it in itemlist:
                nome = it.infoLabels.get('title') if it.infoLabels else ''
                if nome and nome != it.fulltitle and nome not in it.title:
                    it.title += support.typo(nome, '-- bold')
        return itemlist
    return locals()

'''.replace('__STAGIONE__', (
            "    # titolo e anno servono a TMDB: se la lista non ha l'anno lo cerco nella pagina della serie\n"
            "    if not item.infoLabels.get('year'):\n"
            "        anno = support.match(item.url, patron=r'(?:years=|[Aa]nno|[Uu]scita|[Yy]ear|[Rr]elease)[^<]{0,60}?((?:19|20)\\d{2})').match\n"
            "        if anno:\n            item.infoLabels['year'] = anno\n"
            "    if item.infoLabels.get('year') and not item.infoLabels.get('tmdb_id'):\n"
            "        # titolo e anno a TMDB per riconoscere la serie, come fanno gli altri canali\n"
            "        item.infoLabels['tvshowtitle'] = item.contentSerieName or item.fulltitle\n"
            "        try:\n            tmdb.set_infoLabels_item(item, seekTmdb=True)\n        except Exception:\n            pass\n"
            if '(?P<episode>' in ctx['patron_ep'] + (ctx.get('patron_ep_b') or '') and '(?P<season>' not in ctx['patron_ep'] else '')).replace('__PATRONEP__', raw(ctx['patron_ep'])).replace('__PATRONB__', (
            "    if not re.search(r'/[^/]*\\d+/?$', item.url):\n        patron = " + raw(ctx['patron_ep_b']) + "\n") if ctx.get('patron_ep_b') else '')
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
    if ctx.get('player'):
        pl = ctx['player']
        hop = ''
        if ctx.get('hop'):
            hop = "    url = url.replace('/%s/', '/%s/', 1)\n" % (ctx['hop'][0], ctx['hop'][1])
        play = ''
        if pl.get('playlist'):
            play = ("    base_e, _, q = embed.partition('?')\n"
                    "    testi.append(httptools.downloadpage(base_e + '%s' + ('?' + q if q else ''), headers=ref).data)\n" % pl['playlist'])
            if pl.get('cifrato'):
                play += ("    try:\n"
                         "        r = base64.b64decode(json.loads(str(testi[-1])).get('d'))\n"
                         "        for chiave in re.findall(r'(?:^|[?&])[^=&]+=([^&]+)', q):\n"
                         "            t = ''.join(chr(c ^ ord(chiave[n % len(chiave)])) for n, c in enumerate(r))\n"
                         "            if t.startswith('http'):\n"
                         "                testi.insert(0, t)\n"
                         "                break\n"
                         "    except Exception:\n"
                         "        pass\n")
        cod += '''

def findvideos(item):
    support.info(item)
    itemlist = []
    # la pagina dell'episodio contiene l'iframe del player; il video si legge dalle risposte del player
    url = item.url
__HOP__    data = httptools.downloadpage(url, headers=headers).data
    embed = support.match(data, patron=__IFRAME__).match
    if not embed:
        return support.server(item, data=data, headers=headers)
    embed = embed.replace('&amp;', '&')
    if embed.startswith('//'):
        embed = 'https:' + embed
    origine = re.match(r'https?://[^/]+', embed).group(0)
    ref = [['Referer', host + '/']]
    testi = []
__PLAY__    testi.append(httptools.downloadpage(embed, headers=ref).data)
    visti = []
    for t in testi:
        t = str(t).replace('\\\\/', '/')
        for u in re.findall(r'https?://[^"\\'\\s<>\\\\]+?\\.(?:mp4|m3u8)[^"\\'\\s<>\\\\]*', t):
            u = u.replace('&amp;', '&')
            if u not in visti:
                visti.append(u)
        if visti:
            break
    for u in visti:
        itemlist.append(item.clone(action='play', title=support.config.get_localized_string(30137), server='directo',
                                   url=u + '|Referer=' + origine + '/'))
    if not itemlist:
        return support.server(item, data=embed, headers=ref)
    return support.server(item, itemlist=itemlist)
'''.replace('__HOP__', hop).replace('__IFRAME__', raw(pl['iframe_re'])).replace('__PLAY__', play)
        return cod
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
        elif isinstance(d, list) and d and isinstance(d[0], dict) and not p.isdigit():
            d = d[0].get(p)  # percorso senza indice: si legge il primo elemento della lista
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


_INERTIA = {}


def intestazioni_inertia():
    # siti Inertia.js: la versione dei file cambia a ogni aggiornamento del sito, si legge dalla home
    if 'v' not in _INERTIA:
        versione = ''
        try:
            pagina = httptools.downloadpage(host + '/', headers={'Referer': host + '/'}).data
            m = re.search(r'data-page="([^"]+)"', pagina)
            if m:
                from html import unescape
                versione = json.loads(unescape(m.group(1))).get('version', '')
        except Exception:
            logger.error('Versione Inertia non letta')
        _INERTIA['v'] = versione
    return {'X-Inertia': 'true', 'X-Inertia-Version': _INERTIA['v'], 'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/html, application/xhtml+xml'}


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
        intest = {'Referer': host + '/'}
        if RICERCA_INERTIA:
            intest.update(intestazioni_inertia())
        return httptools.downloadpage(RICERCA % item.search_text.replace(' ', '+'), headers=intest).json
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
    if sez.get('inertia'):
        opt['headers'].update(intestazioni_inertia())
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
    lista = prendi(risposta, RICERCA_LISTA if (item.search_text and RICERCA_LISTA) else sez['lista'], [])
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
            if DETT_CAMPI:
                dett = DETTAGLIO.format(**{n: str(prendi(el, k) or '') for n, k in DETT_CAMPI.items()})
            else:
                dett = DETTAGLIO.format(idv)
            url = host + dett if dett.startswith('/') else dett
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
    ch = EPISODI['chiavi']
    if EPISODI.get('inertia'):
        # la pagina del titolo elenca le stagioni, ogni stagione ha la sua pagina con gli episodi
        intest = {'Referer': host + '/'}
        intest.update(intestazioni_inertia())
        pagina_titolo = item.url if item.url.startswith('http') else host + item.url
        r0 = httptools.downloadpage(pagina_titolo, headers=intest).json
        numeri = []
        for st in prendi(r0, EPISODI['stagioni'], []):
            try:
                numeri.append(int(float(prendi(st, EPISODI['num_stagione']))))
            except (ValueError, TypeError):
                continue
        elenco = []
        for n in numeri or [1]:
            r1 = httptools.downloadpage(pagina_titolo + EPISODI['stagione_url'].format(S=n), headers=intest).json
            for ep in (prendi(r1, EPISODI['lista'], []) or cerca_lista(r1, ch.get('title', 'title'))):
                elenco.append((n, ep))
    else:
        url = EPISODI['url'].replace('{ID}', item.idv)
        if not url.startswith('http'):
            url = host + url
        opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
        if EPISODI['body']:
            opt['post'] = EPISODI['body'].replace('{ID}', item.idv)
        risposta = httptools.downloadpage(url, **opt).json
        lista = prendi(risposta, EPISODI['lista'], []) or cerca_lista(risposta, ch.get('title', 'title'))
        elenco = [(None, ep) for ep in lista]
    titolo_serie = item.sito_title or item.contentSerieName or item.fulltitle
    anno = item.sito_year or item.infoLabels.get('year', '')
    for stagione_nota, ep in elenco:
        try:
            stagione = stagione_nota if stagione_nota is not None else int(float(prendi(ep, ch['season'])))
            numero = int(float(prendi(ep, ch['episode'])))
        except (ValueError, TypeError, KeyError):
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
                             url=item.url if EPISODI.get('inertia') else ''))
    if itemlist and config.get_setting('episode_info'):
        try:
            tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        except:
            logger.error('TMDB non disponibile')
    support.videolibrary(itemlist, item)
    return itemlist

"""


def genera_dati(nome, ctx):
    """Canale per i siti che mettono i titoli nei dati della pagina: stesso scheletro del canale html, ma le liste
    (programmi, episodi, giorni) si leggono dai dati incorporati con il lettore copiato nel file."""
    import ast as _ast
    ctx = dict(ctx, patron=ctx.get('patron') or r'(?P<url>x)(?P<title>x)', modo='html')
    cod = genera_html(nome, ctx)
    tree = _ast.parse(cod)
    righe = cod.splitlines(keepends=True)
    inizi, tot = [], 0
    for r_ in righe:
        inizi.append(tot)
        tot += len(r_)
    def inizio(f):
        return inizi[min([d.lineno for d in f.decorator_list] + [f.lineno]) - 1]
    def fine(f):
        return inizi[f.end_lineno - 1] + len(righe[f.end_lineno - 1])
    sost = []
    for f in tree.body:
        if isinstance(f, _ast.FunctionDef) and (f.name in ('peliculas', 'episodios') or (f.name == 'search' and ctx.get('search_gql'))
                                                or (f.name == 'findvideos' and ctx.get('ricette_video'))):
            sost.append((inizio(f), fine(f), ''))
    for ini, fin, t in sorted(sost, reverse=True):
        cod = cod[:ini] + t + cod[fin:]
    # lettore dei dati e funzioni nuove subito dopo la riga dei header
    punto = cod.index("headers = [['Referer', host + '/']]\n") + len("headers = [['Referer', host + '/']]\n")
    costanti = ('ELENCHI_API = %s  # elenchi completi presi dalle richieste del sito: percorso -> codici delle richieste\n'
                'CANALI_AZIONE = %s  # cosa apre ogni canale: findvideos (diretta) oppure peliculas (guida a giorni)\n'
                'ELENCHI_EXTRA = %s  # altre pagine che mostrano titoli mancanti nell\'elenco completo: percorso -> [(pagina, campi)]\n'
                'ORDINA_ELENCHI = %s  # elenchi che il sito mostra in ordine alfabetico\n') % (
        pprint.pformat(ctx.get('elenchi_api') or {}, width=110), pprint.pformat(ctx.get('canali_azione') or {}, width=110),
        pprint.pformat(ctx.get('elenchi_extra') or {}, width=110), pprint.pformat(ctx.get('ordina_elenchi') or {}, width=110))
    video = ''
    if ctx.get('ricette_video'):
        video = '\n# riproduzione imparata dal sito (riproduzione.py)\n' + rip.codice_helper() + '\n' + rip.codice_canale(ctx['ricette_video']) + '\n'
    cod = cod[:punto] + '\n\n# lettore dei dati incorporati nella pagina (generato da dati_incorporati.py)\n' + di.codice_helper() + '\n' + costanti + '\n' + di.FUNZIONI_CANALE + '\n' + (di.funzione_ricerca(ctx['search_gql']) + '\n' if ctx.get('search_gql') else '') + video + cod[punto:]
    return cod


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
                       'lista': z['lista'], 'pag': z.get('pag'), 'inertia': bool(ez.get('inertia'))})
    cod += "SEZIONI = %s\n" % pprint.pformat(elenco, width=110, sort_dicts=False)
    cod += "CAMPI = %s\n" % json.dumps({k: v for k, v in chiavi.items() if k != 'ids'}, ensure_ascii=False)
    cod += "IDS = %s  # campi che identificano il titolo, in ordine di preferenza\n" % json.dumps(chiavi.get('ids', []))
    cod += "DETTAGLIO = %s  # pagina del titolo, {} al posto dell'id (oppure {nome} dei campi di DETT_CAMPI)\n" % py_str(dett)
    cod += "DETT_CAMPI = %s  # nome usato nel modello -> campo del titolo\n" % json.dumps(ctx.get('dettaglio_campi') or {})
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
    cod += "RICERCA_INERTIA = %s\n" % bool(ctx.get('search_inertia'))
    cod += "RICERCA_LISTA = %s\n" % py_str(ctx.get('search_lista', ''))
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



def gql_valore(v, nome=''):
    """Scrive un valore della cache Apollo come letterale GraphQL (paese, lingua e piattaforma diventano variabili)."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        n = nome.lower()
        if n in ('country', 'releasedincountry') :
            return '$country'
        if n == 'language':
            return '$language'
        if n == 'platform':
            return '$platform'
        if re.fullmatch(r'[A-Z][A-Z0-9_]*', v) and n not in ('packages', 'providers'):
            return v  # valore di un enum
        return json.dumps(v)
    if isinstance(v, list):
        return '[' + ', '.join(gql_valore(x, nome) for x in v) + ']'
    if isinstance(v, dict):
        return '{' + ', '.join('%s: %s' % (k, gql_valore(x, k)) for k, x in v.items()) + '}'
    return 'null'


def campo_con_argomenti(chiave, extra=None):
    """'offers({"country":"IT"})' -> 'offers(country: $country)'"""
    m = re.match(r'^([A-Za-z_]\w*)(?:\((.*)\))?$', chiave, re.S)
    if not m:
        return None, {}
    nome, a = m.group(1), m.group(2)
    args = {}
    if a:
        try:
            args = json.loads(a)
        except Exception:
            return None, {}
    if extra:
        args = extra(args)
    if not args:
        return nome, {}
    return '%s(%s)' % (nome, ', '.join('%s: %s' % (k, gql_valore(v, k)) for k, v in args.items())), args


def episodi_da_cache(s, cache, entry_api, id_serie, filtro_free, rp):
    """Costruisce la richiesta degli episodi a partire dalla cache Apollo della pagina e la prova."""
    show = cache.get('Show:' + id_serie) or cache.get(id_serie)
    if not isinstance(show, dict):
        rp('Episodi dalla cache: voce della serie non trovata (%s)' % id_serie)
        return None
    chiavi_show = show.get('_chiavi', [])
    ek = next((k for k in chiavi_show if k.startswith('episodes')), None)
    if not ek:
        rp('Episodi dalla cache: la serie non ha un campo degli episodi. Campi:', [k[:40] for k in chiavi_show][:25])
        return None
    ep_id = next((n for n in cache if n.startswith('Episode:')), None)
    ep = cache.get(ep_id) if ep_id else None
    if not isinstance(ep, dict):
        return None
    sel = ['id']
    ck = next((k for k in ep.get('_chiavi', []) if k.startswith('content(')), None)
    campi_contenuto = [c for c in ep.get('_contenuto', []) if c in (
        'title', 'shortDescription', 'episodeNumber', 'seasonNumber', 'runtime', 'posterUrl', 'originalReleaseDate')]
    if not ck or not campi_contenuto:
        rp('Episodi dalla cache: contenuto dell\'episodio non letto')
        return None
    sel_c, _ = campo_con_argomenti(ck)
    sel.append('%s { %s }' % (sel_c, ' '.join(campi_contenuto)))
    ok_off = [k for k in ep.get('_chiavi', []) if k.startswith('offers(') and re.search(r'FREE|ADS', k)]
    if ok_off:
        def aggiungi_pacchetto(args):
            f = dict(args.get('filter') or {})
            for pth, val in filtro_free.items():
                if re.search(r'package', pth[-1], re.I):
                    f['packages'] = val
                if re.search(r'monetiz', pth[-1], re.I):
                    f['monetizationTypes'] = val
            args = dict(args)
            args['filter'] = f
            return args
        sel_o, _ = campo_con_argomenti(ok_off[0], aggiungi_pacchetto)
        if sel_o:
            sel.append('%s { id }' % sel_o)
    def tutti_gli_episodi(args):
        # la pagina chiede solo gli ultimi episodi (per esempio limit 3, ordine decrescente): il canale li vuole tutti, in ordine
        args = dict(args)
        for k in list(args):
            if k.lower() == 'limit':
                args[k] = 1000
            if k.lower() in ('sortdirection', 'sortorder', 'order') and isinstance(args[k], str):
                args[k] = 'ASC'
        return args
    cep, argep = campo_con_argomenti(ek, tutti_gli_episodi)
    usate = set()
    corpo_q = '%s { %s }' % (cep, ' '.join(sel))
    for v in ('country', 'language', 'platform'):
        if '$' + v in corpo_q:
            usate.add(v)
    tipi = {'country': 'Country!', 'language': 'Language!', 'platform': 'Platform! = WEB'}
    dich = ', '.join('$%s: %s' % (v, tipi[v]) for v in ('country', 'language', 'platform') if v in usate)
    query = 'query Episodi(%s) { node(id: "{ID}") { ... on Show { %s } } }' % (dich, corpo_q)
    j0, v0 = variabili_di(entry_api.get('post') or '')
    vv = {}
    for v in usate:
        for pth, val in percorsi_variabili(v0 or {}):
            if pth[-1] == v:
                vv[v] = val
                break
    if 'country' in usate and 'country' not in vv:
        vv['country'] = 'IT'
    if 'language' in usate and 'language' not in vv:
        vv['language'] = 'it'
    if 'platform' in usate and 'platform' not in vv:
        vv['platform'] = 'WEB'
    corpo = {'operationName': 'Episodi', 'variables': vv, 'query': query}
    prova_ = dict(corpo)
    prova_['query'] = query.replace('{ID}', id_serie)
    try:
        testo = posta_json(s, entry_api['url'], json.dumps(prova_), entry_api.get('hdr'))
        risp = json.loads(testo)
    except BaseException as ex:
        rp('Episodi dalla cache: richiesta non riuscita:', str(ex)[:1500])
        return None
    if risp.get('errors'):
        rp('Episodi dalla cache: errore API:', json.dumps(risp['errors'], ensure_ascii=False)[:300], '| richiesta:', query[:300])
        return None
    lst = (((risp.get('data') or {}).get('node') or {}).get('episodes'))
    if not isinstance(lst, list) or not lst:
        rp('Episodi dalla cache: la risposta non ha episodi:', testo[:200])
        return None
    rp('Episodi dalla cache: %d episodi ricevuti con la richiesta ricostruita' % len(lst))
    ids = ['id'] + (['offers.0.id'] if ok_off else [])
    chiavi = {'title': 'content.title', 'season': 'content.seasonNumber', 'episode': 'content.episodeNumber', 'ids': ids}
    if 'shortDescription' in campi_contenuto:
        chiavi['plot'] = 'content.shortDescription'
    return {'url': entry_api['url'], 'body': json.dumps(corpo, ensure_ascii=False), 'lista': 'data.node.episodes',
            'chiavi': chiavi, 'lista_prova': lst}


def manifest_da_richiesta(net, rp):
    """Se il sito rifiuta la riproduzione (blocco per paese) ma la richiesta del player e stata catturata,
    ricava dal testo della query dove si trovano manifest e licenza nella risposta (non verificato su una risposta vera)."""
    for e in net:
        po = e.get('post') or ''
        if 'graphql' not in e['url'] or 'manifest' not in po:
            continue
        try:
            j = json.loads(po)
        except Exception:
            continue
        q = j.get('query') or ''
        m_man = re.search(r'\b(manifestUrlDash|manifestUrl\w*|dashUrl|mpdUrl)\b', q)
        if not m_man:
            continue
        man = m_man.group(1)
        radice = re.search(r'\)\s*\{\s*(\w+)\s*[\(\{]', q) or re.search(r'\{\s*(\w+)\s*\(', q)
        cont = re.search(r'(\w+)\s*\{[^{}]*\b%s\b' % man, q)
        if not radice or not cont:
            continue
        percorso = 'data.%s.%s.0.%s' % (radice.group(1), cont.group(1), man)
        lic = None
        m_la = re.search(r'\b(laURL|licenseUrl|licenseURL|licenceUrl)\b', q)
        if m_la:
            cl = re.search(r'(\w+)\s*\{[^{}]*\b%s\b' % m_la.group(1), q)
            if cl:
                lic = 'data.%s.%s.0.%s.0.%s' % (radice.group(1), cont.group(1), cl.group(1), m_la.group(1))
        ent = dict(e)
        ent['post'] = re.sub(r'("deviceOs"\s*:\s*")[^"]*(")', r'\1android\2', po)
        rp('Manifest ricostruito dalla richiesta del player (sito bloccato per paese): percorso', percorso,
           '| licenza', lic or 'non indicata')
        return {'url': 'manifestUrlDash.mpd', 'licenza': '', 'licenza_percorso': lic,
                'sorgente': {'entry': ent, 'path': percorso, 'json': {}}, 'ricostruito': True}
    return None


def riproduci(s, args, rp, cattura, chiave):
    """Prova a far partire il video nella pagina aperta e ritorna le informazioni sul manifest."""
    rp('Provo a far partire il video...')
    pl = s.prova_play(attesa=args.attesa + 4)
    cattura[chiave] = {'url': pl['url'], 'cliccato': pl.get('cliccato'), 'net': pl['net']}
    man, lic = trova_manifest(pl['net'])
    geo_bloccato = False
    for e_ in pl['net']:
        m_ = re.search(r'"errorCode"\s*:\s*"([A-Z_]*(?:GEO|REGION|COUNTRY|RESTRICT)[A-Z_]*)"', e_.get('body') or '')
        if m_:
            geo_bloccato = True
            rp('ATTENZIONE: il sito rifiuta la riproduzione per il paese di questo computer (%s). '
               'Serve un indirizzo del paese giusto: usa il proxy (PROXY_URL / --proxy) o esegui il tool sul tuo computer.' % m_.group(1))
            break
    if not man:
        da_richiesta = manifest_da_richiesta(pl['net'], rp) if geo_bloccato else None
        if da_richiesta:
            return da_richiesta
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


def modello_dettaglio(soups, elementi, chiavi, base):
    """Dai link delle locandine ricava il modello dell'indirizzo del titolo, per esempio /it/titles/{id}-{slug}."""
    ids = chiavi.get('ids', [])
    if not ids:
        return None
    host = urlparse(base).netloc
    percorsi = []
    for sp in soups:
        for a in sp.find_all('a', href=True):
            u = urlsplit(urljoin(base, a['href']))
            if u.netloc == host and u.path.strip('/'):
                percorsi.append(u.path)
    percorsi = list(dict.fromkeys(percorsi))
    conta = {}
    for i, el in enumerate(elementi[:60]):
        piatto = appiattisci(el)
        valori = {k: str(piatto[k]) for k in ids if k in piatto and str(piatto[k]) and not str(piatto[k]).startswith(('/', 'http'))}
        if not valori:
            continue
        for pth in percorsi:
            tpl, usati = pth, {}
            for k, v in sorted(valori.items(), key=lambda kv: -len(kv[1])):
                nome = re.sub(r'\W', '_', k)
                nuovo = re.sub(r'(?<![A-Za-z0-9])' + re.escape(v) + r'(?![A-Za-z0-9])', '{' + nome + '}', tpl, count=1)
                if nuovo != tpl:
                    tpl = nuovo
                    usati[nome] = k
            if usati:
                conta.setdefault((tpl, tuple(sorted(usati.items()))), set()).add(i)
    if not conta:
        return None
    (tpl, usati), quanti = max(conta.items(), key=lambda kv: (len(kv[1]), len(kv[0][1])))
    if len(quanti) < min(2, len(elementi)):
        return None
    return {'modello': tpl, 'campi': dict(usati), 'conferme': len(quanti)}


INERTIA_PERCORSI_STAGIONE = ['/season-{S}', '/stagione-{S}', '/seasons/{S}', '/stagioni/{S}', '?season={S}', '?stagione={S}']


def episodi_inertia(s, ep, det, base, rp):
    """Serie su sito Inertia.js: elenco delle stagioni nella pagina del titolo, una pagina per ogni stagione."""
    j = ep['json']
    stagioni = None
    for path, lst in liste_json(j, minimo=1):
        if re.match(r'^(seasons?|stagion[ei])$', path.split('.')[-1], re.I):
            dicts = [x for x in lst if isinstance(x, dict)]
            for k in appiattisci(dicts[0]):
                if re.match(r'^(number|numero|season_number|n)$', k.split('.')[-1], re.I):
                    stagioni = {'percorso': path, 'chiave': k, 'numeri': [int(float(appiattisci(x)[k])) for x in dicts if k in appiattisci(x)]}
                    break
        if stagioni:
            break
    if not stagioni:
        rp('Episodi Inertia: elenco delle stagioni non trovato nella pagina del titolo.')
        return None
    ver = ep['entry'].get('versione', '')
    intest = {'X-Inertia': 'true', 'X-Inertia-Version': ver, 'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'text/html, application/xhtml+xml', 'Referer': base + '/'}
    pagina = det['url'].split('#')[0].split('?')[0]
    prova_n = stagioni['numeri'][-1] if stagioni['numeri'] else 1
    for pat in INERTIA_PERCORSI_STAGIONE:
        u = pagina + pat.format(S=prova_n)
        try:
            r = s.ctx.request.get(u, headers=intest, timeout=20000)
            corpo = r.text()
        except BaseException as ex:
            rp('Episodi Inertia: richiesta non riuscita', u, str(ex)[:80])
            continue
        e2 = {'url': u, 'method': 'GET', 'ct': 'application/json', 'body': corpo}
        ris = trova_episodi_api([e2])
        rp('Episodi Inertia: provo', u, '| stato', r.status, '| episodi:', len(ris['lista']) if ris else 0)
        if ris:
            ch = dict(ris['chiavi'])
            ch.pop('season', None)
            return {'inertia': True, 'stagioni': stagioni['percorso'], 'num_stagione': stagioni['chiave'],
                    'stagione_url': pat, 'lista': ris['path'], 'chiavi': ch, '_lista': ris['lista']}
    rp('Episodi Inertia: nessun indirizzo di stagione ha risposto con gli episodi.')
    return None


def esplora_api(s, ctx, base, args, rp, cattura, soup, pagina_elenco, api, primo=''):
    """Per i siti con API: scopre sezioni e ordinamenti, poi apre un film e una serie per trovare episodi e riproduzione."""
    import posixpath
    t0 = time.time()
    sezioni, viste = [], set()
    tempo = min(args.attesa, 4)

    def tipo_elemento(el, chiavi, fallback):
        k = chiavi.get('type')
        if k:
            v = str(appiattisci(el).get(k, ''))
            return 'tvshow' if re.search(r'show|serie|tv|series', v, re.I) else 'movie'
        return fallback

    filtro_free = {}
    base_post = api['entry'].get('post') or ''

    def aggiungi(nome, a, fallback):
        f = firma_richiesta(a['entry'])
        if f in viste:
            return None
        if base_post and sezioni and solo_lingua(base_post, a['entry'].get('post') or ''):
            rp('Scartata (cambia solo la lingua o il paese):', nome)
            return None
        op_base, op_new = operazione_di(base_post), operazione_di(a['entry'].get('post') or '')
        if op_base and op_new and op_base != op_new:
            rp('Scartata (operazione diversa dall\'elenco, probabile area sponsorizzata):', nome, '|', op_new)
            return None
        viste.add(f)
        pag = paginazione(a['entry'])
        if pag and pag['tipo'] == 'offset':
            pag['passo'] = len(a['lista'])
        z = {'nome': nome, 'tipo': tipo_elemento(a['lista'][0], a['chiavi'], fallback), 'entry': a['entry'],
             'lista': a['path'], 'pag': pag, 'api': a}
        sezioni.append(z)
        diff = differenze_variabili(base_post, a['entry'].get('post') or '')
        rp('Sezione:', nome, '| tipo:', z['tipo'], '| titoli:', len(a['lista']), '| richiesta:',
           a['entry']['url'][:70], '| cambia:', json.dumps({'.'.join(k): v[1] for k, v in list(diff.items())[:5]},
                                                          ensure_ascii=False)[:200] if diff else 'niente')
        # una sezione gratuita insegna quale filtro (provider o tipo di offerta) usare per tutte le altre
        if FREE_RE.search(nome + ' ' + a['entry']['url']) or any(
                re.search(r'(package|monetiz)', '.'.join(k), re.I) and v[1] for k, v in diff.items()):
            for k, v in diff.items():
                if re.search(r'(package|monetiz)', '.'.join(k), re.I) and v[1]:
                    filtro_free[k] = v[1]
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
    for a_ in soup.find_all('a', href=True):
        t = a_.get_text(' ', strip=True)
        if FREE_RE.search(t + ' ' + a_['href']) and len(t) < 40:
            cand.append((t or nome_da_url(a_['href']), urljoin(base, a_['href'])))
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
    def sonda_e_unisci():
        for z in sonda_api(s, ctx, api, rp, filtro_free, list(sezioni)):
            f = firma_richiesta(z['entry'])
            if f not in viste:
                viste.add(f)
                sezioni.append(z)

    # prima le richieste che servono davvero (filtro gratuito, tipi, ordinamenti): il sito limita le richieste
    # per indirizzo, quindi si fanno subito, prima di aprire altre pagine
    pagine_free = [u for t_, u in cand if FREE_RE.search(t_ + ' ' + u)]
    if not filtro_free and pagine_free:
        filtro_free.update(filtro_da_cache(s, pagine_free, api, rp))
        try:
            s.vai(pagina_elenco, attesa=2, timeout=25000)
        except Exception:
            pass
    if not filtro_free:
        filtro_free.update(trova_filtro_free(s, api, pagine_free, rp))
    sonda_presto = bool(filtro_free)
    if sonda_presto:
        sonda_e_unisci()

    visti = {pagina_elenco.rstrip('/')}
    sez_debug = []
    pagine_html = []
    n = 0
    for t, u in cand:
        u = u.split('#')[0]
        if u.rstrip('/') in visti or urlparse(u).netloc != urlparse(base).netloc:
            continue
        visti.add(u.rstrip('/'))
        if n >= 6:
            break
        n += 1
        if time.time() - t0 > 240:
            rp('Esplorazione delle sezioni interrotta dopo 4 minuti')
            break
        try:
            e = s.vai(u, attesa=tempo, timeout=25000)
        except Exception as ex:
            rp('Pagina non raggiungibile:', u)
            continue
        if len(pagine_html) < 8:
            pagine_html.append(e['html'])
        a2 = trova_elenco_api(e['net'])
        if a2:
            con_varianti(t, a2, fallback0)
        else:
            ops = []
            for x in e['net']:
                if x.get('post') and 'graphql' in x['url'] and not RUMORE.search(x['url']):
                    try:
                        o = json.loads(x['post']).get('operationName')
                    except Exception:
                        o = None
                    if o and o not in ops and not o.startswith('Track'):
                        ops.append(o)
            rp('Pagina senza elenco API:', u, '| operazioni GraphQL viste:', ops[:8] if ops else 'nessuna',
               '| titoli nel DOM:', len(trova_card(soup_di(e['html'])) or []))
            sez_debug.append({'url': u, 'nome': t, 'net': [{k: (str(v)[:1500] if k == 'post' else v) for k, v in x.items()
                                                           if k in ('url', 'method', 'post', 'status')} for x in e['net']
                                                          if not RUMORE.search(x['url'])],
                              'html': html_pulito(e['html']) if len(sez_debug) < 3 else ''})
    if filtro_free:
        rp('Filtro gratuito ricavato dalle sezioni:', json.dumps({'.'.join(k): v for k, v in filtro_free.items()}, ensure_ascii=False))
    if not sonda_presto:
        # la sonda usa tutte le sezioni scoperte e l'eventuale filtro gratuito ricavato dalle pagine
        try:
            s.vai(pagina_elenco, attesa=2, timeout=25000)
        except Exception:
            pass
        sonda_e_unisci()
    # il sito puo limitare le richieste per qualche minuto: si aspetta e si ripete, senza le sezioni non c'e canale
    for giro in range(2):
        if not (STATO_API['guasti'] > 0 and not any(z.get('gratis') for z in sezioni) and len(sezioni) <= 1):
            break
        rp('Il sito ha limitato le richieste: aspetto 5 minuti e riprovo (tentativo %d di 2)' % (giro + 1))
        s.page.wait_for_timeout(300000)
        STATO_API['guasti'] = 0
        try:
            s.vai(pagina_elenco, attesa=2, timeout=25000)
        except Exception:
            pass
        if not filtro_free:
            filtro_free.update(trova_filtro_free(s, api, pagine_free, rp))
        sonda_e_unisci()
    visti_titoli, unici = set(), []
    for z in sezioni:
        k = z['api']['chiavi'].get('title', '')
        seq = (z['tipo'], tuple(str(appiattisci(x).get(k, '')) for x in z['api']['lista'][:10]))
        if seq in visti_titoli:
            continue
        visti_titoli.add(seq)
        unici.append(z)
    sezioni[:] = unici
    if filtro_free and any(z.get('gratis') for z in sezioni):
        # il canale mostra solo i contenuti gratuiti: le liste senza filtro (a pagamento) si tolgono
        tolte = [z['nome'] for z in sezioni if not z.get('gratis')]
        if tolte:
            rp('Tolte le sezioni senza filtro gratuito:', tolte)
        sezioni[:] = [z for z in sezioni if z.get('gratis')]
    ctx['sezioni'] = sezioni
    cattura['sezioni_senza_elenco'] = {'net': [], 'pagine': sez_debug}
    rp('Sezioni trovate:', len(sezioni))

    # un film e una serie di esempio
    campioni = {}
    for z in sezioni:
        gratis = bool(z.get('gratis') or FREE_RE.search(z['nome'] + ' ' + z['entry']['url'] + ' ' + (z['entry'].get('post') or '')))
        for el in z['api']['lista'][:20]:
            tp = tipo_elemento(el, z['api']['chiavi'], z['tipo'])
            campioni.setdefault(tp, []).append((not gratis, len(campioni.get(tp, [])), el, z['api']['chiavi']))
    # prima i titoli delle sezioni gratuite, al massimo tre tentativi per tipo
    for tp in campioni:
        campioni[tp] = [(el, ch) for _, _, el, ch in sorted(campioni[tp], key=lambda x: (x[0], x[1]))[:3]]
    ctx['id_episodi'] = []

    # indirizzo della pagina del titolo: se i dati non lo contengono si ricava dai link delle locandine
    if not any(str(v).startswith(('/', 'http')) for el in api['lista'][:5] for v in
               [appiattisci(el).get(k, '') for k in api['chiavi'].get('ids', [])]):
        try:
            pagine = [soup] + [soup_di(h) for h in pagine_html]
            try:
                pagine.append(soup_di(s.stato()['html']))
            except BaseException:
                pass
            elementi = list(api['lista']) + [x for z in sezioni for x in z['api']['lista'][:15]]
            md = modello_dettaglio(pagine, elementi, api['chiavi'], base)
        except BaseException as ex:
            md = None
            rp('Modello dell\'indirizzo del titolo non ricavato:', str(ex)[:100])
        if md:
            ctx['dettaglio'] = md['modello']
            ctx['dettaglio_campi'] = md['campi']
            rp('Indirizzo della pagina del titolo ricavato dai link:', md['modello'], '| campi:', json.dumps(md['campi']),
               '| titoli che lo confermano:', md['conferme'])
        else:
            rp('Indirizzo della pagina del titolo: non ricavabile dai link delle locandine.')

    def apri(el, chiavi):
        piatto = appiattisci(el)
        url, idv = '', ''
        for k in chiavi.get('ids', []):
            v = str(piatto.get(k, ''))
            if (v.startswith('http') or v.startswith('/')) and not url:
                url = urljoin(base, v)
            elif v and not v.startswith('/') and not idv:
                idv = v
        if not url and ctx.get('dettaglio_campi'):
            try:
                url = urljoin(base, ctx['dettaglio'].format(**{n: str(piatto.get(k, '')) for n, k in ctx['dettaglio_campi'].items()}))
            except (KeyError, IndexError):
                pass
        return url, idv, piatto

    for el, chiavi in campioni.get('movie', []):
        url, idv, piatto = apri(el, chiavi)
        if not url and primo:
            url = primo  # nessun percorso nei dati: si usa il link della prima card
        if not url:
            continue
        rp('Apro un film di esempio:', url)
        det = s.vai(url, attesa=args.attesa)
        cattura['dettaglio'] = {'url': det['url'], 'net': det['net']}
        ctx['primo_id'] = idv
        if idv and idv in det['url'] and not ctx.get('dettaglio_campi'):
            ctx['dettaglio'] = det['url'].replace(idv, '{}')
            if ctx['dettaglio'].startswith(base):
                ctx['dettaglio'] = ctx['dettaglio'][len(base):]
        info = riproduci(s, args, rp, cattura, 'play')
        if info:
            ctx['manifest'] = info
            break
    for el, chiavi in campioni.get('tvshow', []):
        url, idv, piatto = apri(el, chiavi)
        if not url:
            continue
        rp('Apro una serie di esempio:', url)
        det = s.vai(url, attesa=args.attesa)
        cattura['serie'] = {'url': det['url'], 'net': det['net']}
        ep = trova_episodi_api(det['net'])
        dpi = next((e for e in det['net'] if e.get('inertia') and e.get('body')), None)
        if dpi and not ep:
            try:
                pj = json.loads(dpi['body'])
                rp('Pagina Inertia della serie: componente', pj.get('component'), '| dati:', json.dumps(
                    {k: (list(v.keys())[:20] if isinstance(v, dict) else (type(v).__name__ + str(len(v) if hasattr(v, '__len__') else '')))
                     for k, v in pj.get('props', {}).items()}, ensure_ascii=False)[:900])
                cattura['serie_inertia'] = {k: v for k, v in pj.get('props', {}).items() if len(json.dumps(v)) < 30000}
            except Exception:
                pass
        if ep and ep['entry'].get('inertia'):
            ei = episodi_inertia(s, ep, det, base, rp)
            if not ei:
                continue
            lp = ei.pop('_lista')
            ctx['episodi_api'] = ei
            ctx['id_episodi'] = [str(appiattisci(lp[0]).get(k, '')) for k in ei['chiavi'].get('ids', []) if appiattisci(lp[0]).get(k)]
            rp('Episodi (Inertia): stagioni in', ei['stagioni'], '| pagina di stagione', ei['stagione_url'],
               '| elenco', ei['lista'], '| titolo', ei['chiavi'].get('title'), '| episodio', ei['chiavi'].get('episode'))
            break
        if not ep:
            try:
                cache = s.page.evaluate(
                    "() => { const c = window.__APOLLO_CLIENT__; if (!c) return null; const x = c.cache.extract(); "
                    "const o = {}; for (const k of Object.keys(x)) { "
                    "if (/^(Show|Episode):/.test(k)) { const v = x[k]; const e = {_chiavi: Object.keys(v)}; "
                    "const ck = Object.keys(v).find(n => n.startsWith('content(')); "
                    "if (ck && v[ck] && typeof v[ck] === 'object') e._contenuto = Object.keys(v[ck]).filter(n => v[ck][n] === null || typeof v[ck][n] !== 'object').map(n => n); "
                    "o[k] = e; } "
                    "else if (/^(Season|Offer|OfferEpisode):/.test(k) || k === 'ROOT_QUERY') { const s = JSON.stringify(x[k]); o[k] = s.length > 3000 ? s.slice(0, 3000) : s; } } return o; }")
            except BaseException as ex:
                cache = None
                rp('Cache Apollo non letta:', str(ex)[:100])
            if cache:
                nep = sum(1 for k in cache if k.startswith('Episode:'))
                rp('Cache Apollo della serie: %d voci, di cui %d episodi' % (len(cache), nep))
                cattura['serie_cache'] = cache
                if nep and idv and not ctx.get('episodi_api'):
                    ec = episodi_da_cache(s, cache, api['entry'], idv, filtro_free, rp)
                    if ec:
                        lp = ec.pop('lista_prova')
                        ctx['episodi_api'] = ec
                        ctx['id_episodi'] = [str(appiattisci(lp[0]).get(k, '')) for k in ec['chiavi']['ids']
                                             if appiattisci(lp[0]).get(k)]
                        break
            elif cache is None:
                rp('Nessun client Apollo nella pagina della serie.')
            rp('Episodi: nessuna risposta JSON con stagioni ed episodi trovata nella pagina di questa serie.')
            continue
        e = ep['entry']
        valori = [idv] + [str(v) for v in piatto.values() if isinstance(v, (str, int)) and len(str(v)) >= 3]
        tr = trasforma_id((e['url'] or '') + ' ' + (e.get('post') or ''), valori)
        if not tr:
            rp('ATTENZIONE: episodi trovati ma non so in quale punto della richiesta compare l\'id della serie.')
            continue
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
        break

# ---------------------------------------------------------------------------
# Catena scheda, dettaglio, episodio, player (siti HTML)
# ---------------------------------------------------------------------------

PUBBLICITA = re.compile(r'(a-ads|doubleclick|googlesyndication|adsystem|adnxs|popads|propeller|clickadu|exoclick|'
                        r'google|facebook|twitter|disqus|recaptcha|cloudflare)', re.I)
EP_TOKEN = re.compile(r'(?:^|[-_/])(?:ep(?:isod\w*)?[-_]?\d+|\d+x\d+|s\d+e\d+)$', re.I)


def segmenti(url):
    return [x for x in urlparse(url).path.split('/') if x]


def e_episodio(url):
    sg = segmenti(url)
    return bool(sg and EP_TOKEN.search(sg[-1]))


def iframe_player(soup):
    """Iframe che sembrano il player (quelli pubblicitari sono esclusi), i piu probabili per primi."""
    out = []
    for i in soup.find_all('iframe'):
        src = i.get('src') or i.get('data-src') or ''
        if not src or src.startswith(('about:', 'javascript')) or PUBBLICITA.search(src):
            continue
        punti = 0
        testo = ' '.join([src, i.get('id') or '', ' '.join(i.get('class') or [])])
        if re.search(r'(embed|player|video|watch|stream)', testo, re.I):
            punti += 2
        if i.get('allowfullscreen') is not None:
            punti += 1
        out.append((punti, i))
    out.sort(key=lambda x: -x[0])
    return [i for _, i in out]


def prossimi_link(soup, url_pagina, base, visti):
    """Link della pagina che portano a un'altra pagina dello stesso titolo (dettaglio, episodio...)."""
    slug = [x for x in segmenti(url_pagina) if len(x) >= 6]
    cand = []
    for a in soup.find_all('a', href=True):
        h = urljoin(url_pagina, a['href']).split('#')[0]
        pu = urlparse(h)
        if pu.netloc.replace('www.', '') != urlparse(base).netloc.replace('www.', ''):
            continue
        if h in visti or h.rstrip('/') == url_pagina.rstrip('/'):
            continue
        sg = segmenti(h)
        if not any(x in sg for x in slug):
            continue
        punti = 2 if e_episodio(h) == e_episodio(url_pagina) else 0
        if e_episodio(h) and e_episodio(url_pagina) and sg[-1] == segmenti(url_pagina)[-1]:
            punti += 2
        cand.append((punti, h))
    out = []
    for _, h in sorted(cand, key=lambda x: -x[0]):
        if h not in out:
            out.append(h)
    return out


def regola_sostituzione(src, dst):
    """Se dst e src differiscono per un solo segmento del percorso, ritorna (da, a)."""
    s1, d1 = segmenti(src), segmenti(dst)
    if len(s1) != len(d1):
        return None
    diff = [(x, y) for x, y in zip(s1, d1) if x != y]
    return diff[0] if len(diff) == 1 else None


def regola_serie(card_url, serie_url):
    """Regex che porta l'url di una scheda (a volte un episodio) alla pagina con la lista episodi."""
    s1, d1 = segmenti(card_url), segmenti(serie_url)
    comuni = [x for x in d1 if x in s1 and len(x) >= 6]
    if not comuni or s1 == d1:
        return None
    i_s, i_d = s1.index(comuni[0]), d1.index(comuni[0])
    pre_s, pre_d = s1[:i_s], d1[:i_d]
    if len(pre_s) != 1 or len(pre_d) != 1:
        return None
    coda = s1[i_s + 1:]
    if len(coda) > 1:
        return None
    pre = '|'.join(re.escape(x) for x in dict.fromkeys([pre_s[0], pre_d[0]]))
    cod = ''
    if coda:
        cod = '(?:/' + re.sub(r'\d+', lambda m: r'\d+', re.escape(coda[0])) + ')?'
    return (r'/(?:%s)/([^/]+)%s/?$' % (pre, cod), r'/%s/\1' % pre_d[0])


def patron_episodio(eps):
    ep0 = eps[len(eps) // 2]
    pt = (_tagre(ep0) + r'[^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<') \
        if ep0.name == 'a' else r'<a [^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'
    pt = pt.replace('<a<', '<a')
    if re.fullmatch(r'\d{1,4}', ep0.get_text(' ', strip=True)):
        pt = pt.replace(r'(?P<title>[^<]+?)', r'(?P<episode>\d+)', 1)
    return pt


def decodifica_playlist(body, embed):
    """Playlist del tipo {"d": base64, ...}: l'indirizzo e cifrato con XOR ciclico usando un parametro (token) dell'iframe."""
    import base64
    try:
        d = json.loads(body).get('d')
        if not d:
            return ''
        raw_ = base64.b64decode(d)
    except BaseException:
        return ''
    for chiave in re.findall(r'(?:^|[?&])[^=&]+=([^&]+)', embed):
        t = ''.join(chr(c ^ ord(chiave[n % len(chiave)])) for n, c in enumerate(raw_))
        if t.startswith('http'):
            return t
    return ''


def esplora_catena(s, det, primo, base, args, rp, cattura, ctx):
    """Segue i link da una scheda fino alla lista episodi e al player, e capisce come ricavare il video."""
    visti = []
    coda_pagine = [primo]
    ep_url = None
    serie_url = None
    eps_serie = None
    page = det
    while coda_pagine and len(visti) < 5:
        u = coda_pagine.pop(0)
        if u in visti:
            continue
        if page is None or page['url'].rstrip('/') != u.rstrip('/'):
            try:
                page = s.vai(u, attesa=args.attesa)
            except BaseException as ex:
                rp('Catena: pagina non aperta', u, str(ex)[:80])
                page = None
                continue
        visti.append(u)
        if page['url'] not in visti:
            visti.append(page['url'])
        sp = soup_di(page['html'])
        eps = trova_episodi(sp)
        ifr = iframe_player(sp)
        rp('Catena:', page['url'][:110], '| episodi:', len(eps) if eps else 0, '| iframe del player:', len(ifr))
        if eps and not eps_serie:
            eps_serie, serie_url = eps, page['url']
        if ifr and not ep_url:
            ep_url = page['url']
        if eps_serie and ep_url:
            break
        for h in prossimi_link(sp, page['url'], base, visti)[:3]:
            if h not in coda_pagine:
                coda_pagine.append(h)
        page = None
    if eps_serie:
        ctx['episodi'] = eps_serie
        ctx['patron_ep'] = patron_episodio(eps_serie)
        ctx['tipo'] = 'tvshow' if not args.tipo else args.tipo
        rp('Lista episodi su', serie_url, '|', len(eps_serie), 'episodi')
        if urlparse(primo).path != urlparse(serie_url).path:
            sost = regola_sostituzione(primo, serie_url)
            if sost:
                r = (r'/%s/' % re.escape(sost[0]), '/%s/' % sost[1])
            else:
                r = regola_serie(primo, serie_url)
            if r:
                ctx['regola_serie'] = r
                rp('Le schede portano a', urlparse(primo).path, 'ma la lista episodi sta su', urlparse(serie_url).path,
                   '| regola:', r[0], '->', r[1])
    if not ep_url:
        rp('Catena: nessuna pagina con il player trovata.')
        return
    # se la lista episodi sta su una pagina di episodio, la pagina del titolo (senza l'ultimo segmento) puo avere un'altra struttura
    if eps_serie and e_episodio(serie_url):
        madre = serie_url.rsplit('/', 1)[0]
        try:
            pm = s.vai(madre, attesa=args.attesa)
            epm = trova_episodi(soup_di(pm['html']))
            if epm:
                # la pagina del titolo ha la lista episodi: le schede vanno portate li (si toglie l'ultimo segmento)
                coda_ep = serie_url.rsplit('/', 1)[1].split('?')[0]
                ctx['patron_ep'] = patron_episodio(epm)
                ctx.pop('patron_ep_b', None)
                ctx['episodi'] = epm
                ctx['regola_serie2'] = (r'/%s/?$' % re.sub(r'\d+', lambda m: r'\d+', re.escape(coda_ep)), '')
                rp('La pagina del titolo', madre, 'ha la lista episodi (%d): tolgo "%s" dall\'indirizzo delle schede' % (len(epm), coda_ep))
        except BaseException as ex:
            rp('Pagina del titolo non aperta:', madre, str(ex)[:80])
    # la scheda (spesso un episodio) puo non essere la pagina del player o quella con la lista episodi
    pp, pe = urlparse(primo).path, urlparse(ep_url).path
    if pp != pe:
        regola_hop = regola_sostituzione(primo, ep_url)
        if regola_hop:
            ctx['hop'] = regola_hop
            rp('La scheda apre %s ma il player sta su %s (segmento "%s" diventa "%s")' % (pp, pe, regola_hop[0], regola_hop[1]))
        else:
            rp('ATTENZIONE: la scheda (%s) e la pagina del player (%s) hanno percorsi diversi e non riesco a derivare la regola.' % (pp, pe))
    # pagina del player, con la rete dell'iframe
    pl = s.vai(ep_url, attesa=args.attesa + 4)
    cattura['player'] = {'url': pl['url'], 'net': [{k: (str(v)[:6000] if k == 'body' else v) for k, v in x.items() if k != '_resp'}
                                                    for x in pl['net'] if not PUBBLICITA.search(x['url'])]}
    psoup = soup_di(pl['html'])
    ifr = iframe_player(psoup)
    if not ifr:
        return
    el = ifr[0]
    if el.get('id'):
        iframe_re = r'<iframe(?=[^>]*id="%s")[^>]*?(?:data-)?src="([^"]+)"' % re.escape(el['id'])
    elif el.get('class'):
        iframe_re = r'<iframe(?=[^>]*class="%s")[^>]*?(?:data-)?src="([^"]+)"' % re.escape(' '.join(el['class']))
    else:
        iframe_re = r'<iframe[^>]*?src="((?:https?:)?//[^"]+)"'
    embed = urljoin(pl['url'], el.get('src') or el.get('data-src'))
    player = {'iframe_re': iframe_re, 'embed': embed, 'playlist': ''}
    rp('Player: iframe', embed[:120])
    eu = urlparse(embed)
    video = ''
    for e in pl['net']:
        pu = urlparse(e['url'])
        if e['url'] == embed or PUBBLICITA.search(e['url']) or e.get('status') != 200 or not e.get('body'):
            continue
        if e.get('tipo') in ('fetch', 'xhr') and pu.netloc.replace(':80', '').replace(':443', '') == eu.netloc.replace(':80', '').replace(':443', '') and pu.path.startswith(eu.path.rstrip('/') + '/') \
                and pu.path != eu.path:
            m = re.search(r'https?:(?:\\?/){2}[^"\'\s<>\\]+?\.(?:mp4|m3u8)[^"\'\s<>]*', e['body'])
            if m:
                player['playlist'] = pu.path[len(eu.path.rstrip('/')):]
                video = m.group(0).replace('\\/', '/')
                rp('Elenco dei file video:', e['url'][:120], '| suffisso rispetto all\'iframe:', player['playlist'])
                break
            dec = decodifica_playlist(e['body'], embed)
            if dec:
                player['playlist'] = pu.path[len(eu.path.rstrip('/')):]
                player['cifrato'] = True
                video = dec
                rp('Elenco dei file video CIFRATO (base64 e XOR con un parametro dell\'iframe):', e['url'][:120],
                   '| suffisso rispetto all\'iframe:', player['playlist'])
                break
    if not video:
        for e in pl['net']:
            if e.get('body') and e['url'] != pl['url'] and not PUBBLICITA.search(e['url']):
                m = re.search(r'https?:(?:\\?/){2}[^"\'\s<>\\]+?\.(?:mp4|m3u8)[^"\'\s<>]*', e['body'])
                if m:
                    video = m.group(0).replace('\\/', '/')
                    rp('File video trovato in', e['url'][:120])
                    break
    if video:
        rp('Video:', video[:140])
    else:
        rp('ATTENZIONE: nessun file video trovato nelle risposte dell\'iframe (il canale prova comunque a cercarlo a runtime).')
    player['video'] = video
    ctx['player'] = player



def analizza(url, args):
    rapporto = []

    def rp(*a):
        riga = ' '.join(str(x) for x in a)
        rapporto.append(riga)
        log(riga)

    base = '{0.scheme}://{0.netloc}'.format(urlparse(url))
    SITO_BASE[0] = dominio_base(url)
    id_ = args.nome or id_da_url(url)
    nome = args.titolo or id_.capitalize()
    ctx = {'base': base, 'menu': [], 'tipo': 'movie', 'next': '', 'patron': '', 'episodi': None, 'patron_ep': '',
           'ricerca': None, 'api': None, 'search_api': '', 'pag': None, 'manifest': None}

    s = Sessione(headless=not (args.mostra or args.pausa), chromium=args.chromium, dns=DOH.get(args.dns),
                 proxy=args.proxy or os.environ.get('PROXY_URL') or None)
    cattura = {}
    try:
        px = args.proxy or os.environ.get('PROXY_URL')
        if px:
            try:
                s.page.goto('https://ipinfo.io/json', timeout=20000)
                inf = json.loads(s.page.inner_text('body'))
                rp('Proxy in uso: %s | IP visto dal sito: %s, paese %s, %s' % (
                    urlsplit(px).netloc.split('@')[-1], inf.get('ip'), inf.get('country'), inf.get('org', '')))
            except BaseException as ex:
                rp('Proxy in uso: %s | controllo dell\'IP non riuscito (%s)' % (urlsplit(px).netloc.split('@')[-1], str(ex)[:80]))
        else:
            rp('Nessun proxy: il sito vede l\'IP del computer che esegue il tool.')
        rp('Apro', url)
        try:
            elenco = s.vai(url, attesa=args.attesa)
        except BaseException as ex:
            if not (args.proxy or os.environ.get('PROXY_URL')):
                raise
            rp('Il proxy non ha aperto la pagina (%s): riprovo senza proxy.' % str(ex)[:100])
            s.chiudi()
            s = Sessione(headless=not (args.mostra or args.pausa), chromium=args.chromium, dns=DOH.get(args.dns))
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
            stessi = bool(th) and comuni >= 0.5 * len(th)
            pag_api = paginazione(api['entry'])
            if stessi and pag_api and len(api['lista']) >= 10:
                modo = 'api'
                rp('L\'HTML e la API mostrano gli stessi titoli, ma la API ha la paginazione (%s) e i tipi di contenuto: '
                   'scelgo la API, che permette anche sezioni, serie ed episodi.' % pag_api['tipo'])
            elif stessi:
                modo = 'html'
            else:
                modo = 'api'
                rp('I titoli letti dall\'HTML non coincidono con quelli della API: scelgo la API.')
        elif card and collaudo[0] >= 3:
            modo = 'html'
        elif api:
            modo = 'api'
        elif (_dati := di.rileva(scarica_grezzo(pagina_elenco))):
            modo = 'dati'
            ctx['dati'] = _dati['firma']
            rp('La regex non trova i titoli nell\'html grezzo, ma la pagina contiene i dati dei titoli (Next.js o JSON-LD): '
               'campi %s. Il canale li leggera da li.' % json.dumps({k: v for k, v in ctx['dati'].items() if k != 'buoni'}))
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

        if modo == 'dati':
            try:
                ed.esplora(s, ctx, base, args, rp, cattura, scarica_grezzo, pagina_elenco)
            except BaseException as ex:
                import traceback
                rp('Esplorazione dei dati non completata: %s' % str(ex)[:150])
                rp(traceback.format_exc()[-600:])

        # Ricerca
        ric = trova_ricerca(soup, base)
        if not ric and not ctx.get('search_gql'):
            try:
                s.vai(pagina_elenco, attesa=2)
                rd = s.cerca_dinamica('matrix', attesa=args.attesa)
            except BaseException as ex:
                rd = {'errore': str(ex)[:100], 'net': []}
            cattura['ricerca_dinamica'] = {'url': rd.get('url'), 'errore': rd.get('errore'),
                                           'net': [{k: v for k, v in x.items() if k not in ('_resp', 'body')} for x in rd.get('net', [])][:60]}
            if rd.get('errore'):
                rp('Ricerca senza modulo: %s' % rd['errore'])
                for riga_d in rd.get('diagnosi', []):
                    rp('   ' + riga_d)
            else:
                pl = trova_ricerca_payload(rd.get('net', []))
                pagina_ricerca = False
                if 'matrix' in (rd.get('url') or '').lower():
                    # il sito ha aperto una pagina dei risultati: se i titoli stanno nei dati della pagina e cambiano con il testo,
                    # la ricerca e quella pagina (i suggerimenti mentre si scrive hanno un limite basso e altri tipi di contenuto)
                    try:
                        def titoli_pagina(u):
                            rr = di.rileva(scarica_grezzo(u))
                            return {x['titolo'] for _, gg in rr['gruppi'] for x in gg} if rr else set()
                        t1 = titoli_pagina(rd['url'])
                        t2 = titoli_pagina(rd['url'].replace('matrix', 'amore'))
                        rp('Pagina dei risultati: %d titoli con "matrix", %d con "amore"' % (len(t1), len(t2)))
                        if (t1 or t2) and t1 != t2:
                            pagina_ricerca = True
                            pl = None
                            u_r = rd['url']
                            ctx['ricerca'] = {'selettore': '', 'nome': '', 'azione': '', 'metodo': '',
                                              'url_modello': (u_r.replace('matrix', '%s')[len(base):] if u_r.startswith(base) else u_r.replace('matrix', '%s'))}
                            rp('Ricerca su pagina con i titoli nei dati:', u_r)
                        else:
                            r2 = s.vai(rd['url'], attesa=args.attesa)
                            pl2 = trova_ricerca_payload(r2.get('net', []))
                            pl = pl2 or pl
                    except BaseException as ex:
                        rp('Pagina dei risultati non analizzata: %s' % str(ex)[:80])
                if pagina_ricerca:
                    pass
                elif pl:
                    ctx['search_gql'] = pl
                    rp('Ricerca via richiesta con parametri in base64:', pl['esempio'], '| parametri:', json.dumps(pl['payload']))
                else:
                    for e in rd.get('net', []):
                        if 'matrix' in e['url'].lower() and e['method'] == 'GET' and not RUMORE.search(e['url']):
                            ctx['search_api'] = e['url']
                            rp('Ricerca via API:', e['url'][:120])
                            break
                    else:
                        if 'matrix' in (rd.get('url') or '').lower():
                            ctx['ricerca'] = {'selettore': '', 'nome': '', 'azione': '', 'metodo': '',
                                              'url_modello': (rd['url'].replace('matrix', '%s')[len(base):] if rd['url'].startswith(base) else rd['url'].replace('matrix', '%s'))}
                            rp('Url di ricerca (campo aperto dalla pagina):', rd['url'])
                        else:
                            rp('Ricerca senza modulo: il testo e stato inviato ma non ho trovato una richiesta riconoscibile (url finale %s)' % rd.get('url'))
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
            if modo == 'api' and not ctx.get('search_api') and not ctx.get('search_body'):
                # ricerca che apre una pagina Inertia con i risultati nei dati della pagina, oppure una API GET
                a_s = trova_elenco_api(r.get('net', []))
                if a_s and 'matrix' in a_s['entry']['url'].lower() and not a_s['entry'].get('inertia'):
                    ctx['search_api'] = a_s['entry']['url']
                    ctx['search_lista'] = a_s['path']
                    rp('Ricerca via API:', a_s['entry']['url'][:120])
                elif a_s and a_s['entry'].get('inertia') and 'matrix' in r.get('url', '').lower():
                    ctx['search_api'] = r['url']
                    ctx['search_inertia'] = True
                    ctx['search_lista'] = a_s['path']
                    rp('Ricerca su pagina Inertia:', r['url'][:120], '| lista:', a_s['path'])

        if modo == 'api' and not ctx.get('search_api') and not ctx.get('search_body'):
            # nessun campo di ricerca utilizzabile: si prova la pagina di ricerca piu comune
            m_l = re.match(r'^/[a-z]{2}(?=/|$)', urlparse(pagina_elenco).path)
            for cand_r in ([m_l.group(0) + '/search?q=matrix'] if m_l else []) + ['/search?q=matrix']:
                try:
                    r2 = s.vai(base + cand_r, attesa=args.attesa)
                except BaseException:
                    continue
                a_s = trova_elenco_api(r2['net'])
                rp('Ricerca provata:', base + cand_r, '| url finale:', r2['url'][:100], '| elenco:',
                   a_s['path'] if a_s else 'nessuno', '| chiamate JSON:',
                   [x['url'][:80] for x in r2['net'] if 'json' in x.get('ct', '') and not RUMORE.search(x['url'])][:6])
                cattura.setdefault('ricerca_prove', []).append(
                    {'url': r2['url'], 'net': [{k: (str(v)[:3000] if k == 'body' else v) for k, v in x.items() if k != '_resp'}
                                               for x in r2['net'] if 'json' in x.get('ct', '') and not RUMORE.search(x['url'])]})
                if a_s and any('matrix' in str(appiattisci(x).get(a_s['chiavi'].get('title', ''), '')).lower() for x in a_s['lista']):
                    ctx['search_api'] = (a_s['entry']['url'] if not a_s['entry'].get('inertia') and 'matrix' in a_s['entry']['url'].lower()
                                         else base + cand_r)
                    ctx['search_inertia'] = bool(a_s['entry'].get('inertia'))
                    ctx['search_lista'] = a_s['path']
                    rp('Ricerca trovata provando', cand_r, '| lista:', a_s['path'], '| Inertia:', ctx['search_inertia'])
                    break
            else:
                rp('Ricerca: nessun campo e nessuna pagina di ricerca riconosciuta.')

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
                if re.fullmatch(r'\d{1,4}', ep0.get_text(' ', strip=True)):
                    ctx['patron_ep'] = ctx['patron_ep'].replace(r'(?P<title>[^<]+?)', r'(?P<episode>\d+)', 1)
                rp('Episodi rilevati:', len(eps), '(titolo esempio:', ep0.get_text(' ', strip=True)[:40] + ')')
                ctx['tipo'] = 'tvshow' if not args.tipo else args.tipo
            ifr = [i.get('src') for i in dsoup.find_all('iframe') if i.get('src')]
            rp('Iframe nella pagina:', ifr[:3] if ifr else 'nessuno')
            if modo == 'html':
                try:
                    esplora_catena(s, det, primo, base, args, rp, cattura, ctx)
                except BaseException as ex:
                    rp('Catena scheda-episodio-player non completata:', str(ex)[:120])
            if modo == 'html':
                ctx['anime'] = args.tipo == 'anime' or bool(re.search(r'anime', base, re.I))
                if ctx['anime']:
                    rp('Sito di anime: il canale usera anime = True (rinumerazione dal menu contestuale)')
                # tengo solo le voci di menu che aprono davvero un elenco di titoli (stessa regex delle schede)
                if ctx.get('patron') and len(ctx['menu']) > 1:
                    buone = []
                    for nome_m, url_m in ctx['menu']:
                        try:
                            pg = s.vai(url_m, attesa=max(2, args.attesa // 2))
                            n_m = collauda(ctx['patron'], normalizza(pg['html']))[0]
                        except BaseException:
                            n_m = 0
                        rp('Voce di menu', nome_m, url_m[:80], '| titoli trovati:', n_m)
                        if n_m >= 3:
                            buone.append((nome_m, url_m))
                    if buone:
                        ctx['menu'] = buone
            # url della pagina titolo con segnaposto
            if modo == 'api' and ctx.get('primo_id') and ctx['primo_id'] in det['url']:
                ctx['dettaglio'] = det['url'].replace(ctx['primo_id'], '{}')
                if ctx['dettaglio'].startswith(base):
                    ctx['dettaglio'] = ctx['dettaglio'][len(base):]
                    ctx['dettaglio'] = '{}' if False else ctx['dettaglio']

            # Riproduzione
            if ctx.get('player'):
                return id_, nome, ctx, cattura, rapporto, base
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


PROFILI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'profili')


def trova_profilo(url, args):
    """Canale gia verificato a mano per questo sito: cartella profili, un .py e un .json con le chiavi di riconoscimento."""
    if getattr(args, 'senza_profilo', False) or not os.path.isdir(PROFILI_DIR):
        return None
    testo = (urlparse(url).netloc + ' ' + (args.nome or '')).lower()
    for f in sorted(os.listdir(PROFILI_DIR)):
        if not f.endswith('.json'):
            continue
        try:
            d = json.load(open(os.path.join(PROFILI_DIR, f), encoding='utf-8'))
        except Exception:
            continue
        if any(k in testo for k in d.get('chiavi', [])) and os.path.exists(os.path.join(PROFILI_DIR, f[:-5] + '.py')):
            d['_nome'] = f[:-5]
            return d
    return None


def usa_profilo(prof, url, args):
    """Scrive il canale verificato com'e e controlla sul sito vero che i dati che usa ci siano ancora."""
    rapporto = []

    def rp(*a):
        riga = ' '.join(str(x) for x in a)
        rapporto.append(riga)
        log(riga)

    base = '{0.scheme}://{0.netloc}'.format(urlparse(url))
    id_ = args.nome or id_da_url(url)
    nome = args.titolo or id_.capitalize()
    rp('Profilo verificato in uso:', prof['_nome'], '| il canale e identico a quello scritto a mano')
    rp('Controllo che il sito abbia ancora la struttura che il canale si aspetta')
    s = Sessione(headless=not (args.mostra or args.pausa), chromium=args.chromium, dns=DOH.get(args.dns),
                 proxy=args.proxy or os.environ.get('PROXY_URL') or None)
    cattura, problemi = {}, []

    def pagina(rel):
        st = s.vai(base + rel, attesa=min(args.attesa, 3))
        dp = inertia_da_html(st['html'])
        if dp is None:
            for e in st['net']:
                if e.get('tipo') == 'document' and e.get('body'):
                    dp = inertia_da_html(e['body'])
                    if dp is not None:
                        break
        return dp

    try:
        for c in prof.get('controlli', []):
            try:
                dp = pagina(c['url'])
            except BaseException as ex:
                problemi.append(c['nome'])
                rp('PROBLEMA:', c['nome'], '| pagina non aperta:', c['url'], str(ex)[:80])
                continue
            lista = leggi(dp, c['percorso']) if dp else None
            if not isinstance(lista, list) or not lista:
                problemi.append(c['nome'])
                rp('PROBLEMA:', c['nome'], '| in', c['url'], 'non trovo', c['percorso'], '(pagina Inertia:', 'si' if dp else 'no', ')')
                continue
            if lista and isinstance(lista[0], list):
                lista = [x for sub in lista for x in sub]
            el = lista[0] if isinstance(lista[0], dict) else {}
            mancano = [k for k in c.get('campi', []) if k not in el]
            if mancano:
                problemi.append(c['nome'])
                rp('PROBLEMA:', c['nome'], '| campi mancanti nei titoli:', mancano, '| campi presenti:', sorted(el.keys())[:25])
            else:
                rp('OK:', c['nome'], '|', len(lista), 'titoli in', c['percorso'])
            cattura[c['nome']] = {'url': c['url'], 'percorso': c['percorso'], 'primo': el}
        sr = prof.get('serie')
        if sr:
            dp = pagina(sr['da'])
            tit = [x for x in (leggi(dp, 'props.titles') or []) if isinstance(x, dict) and x.get('slug') and x.get('id')] if dp else []
            if tit:
                u = '/it/titles/%s-%s' % (tit[0]['id'], tit[0]['slug'])
                dp = pagina(u)
                stg = leggi(dp, sr['percorso_stagioni']) if dp else None
                if not isinstance(stg, list) or not stg:
                    problemi.append('Stagioni')
                    rp('PROBLEMA: stagioni non trovate in', u, sr['percorso_stagioni'])
                else:
                    mc = [k for k in sr['campi_stagione'] if k not in stg[0]]
                    dp2 = pagina(u + sr['stagione_url'].format(S=stg[0].get('number', 1)))
                    eps = leggi(dp2, sr['percorso_episodi']) if dp2 else None
                    if not isinstance(eps, list) or not eps:
                        problemi.append('Episodi')
                        rp('PROBLEMA: episodi non trovati in', u + sr['stagione_url'].format(S=stg[0].get('number', 1)))
                    else:
                        me = [k for k in sr['campi_episodio'] if k not in eps[0]]
                        if mc or me:
                            problemi.append('Campi di stagioni o episodi')
                            rp('PROBLEMA: campi mancanti | stagione:', mc, '| episodio:', me)
                        else:
                            rp('OK: serie di esempio', u, '|', len(stg), 'stagioni,', len(eps), 'episodi nella prima')
            else:
                problemi.append('Serie di esempio')
                rp('PROBLEMA: nessuna serie trovata nell\'archivio per provare stagioni ed episodi')
    finally:
        s.chiudi()
    if problemi:
        rp('ATTENZIONE: il sito e cambiato o non risponde come previsto in:', ', '.join(problemi),
           '| il canale scritto e comunque quello verificato: controllare prima di usarlo')
    else:
        rp('Tutti i controlli superati: la struttura del sito e quella che il canale si aspetta')
    os.makedirs(args.out, exist_ok=True)
    py = open(os.path.join(PROFILI_DIR, prof['_nome'] + '.py'), encoding='utf-8').read()
    open(os.path.join(args.out, id_ + '.py'), 'w', encoding='utf-8').write(py)
    open(os.path.join(args.out, id_ + '.json'), 'w', encoding='utf-8').write(
        genera_json(id_, nome, 'movie', tipi={k: [] for k in prof.get('categorie', ['movie', 'tvshow'])}))
    open(os.path.join(args.out, 'riga_channels_json.txt'), 'w', encoding='utf-8').write('        "%s": "%s",\n' % (id_, base))
    rapporto += ['', 'File scritti in %s: %s.py, %s.json, riga_channels_json.txt' % (args.out, id_, id_),
                 'Da fare a mano: copiare i file in channels/, aggiungere la riga in channels.json (sezione direct), '
                 'caricare l\'icona %s.png nella repo media.' % id_,
                 'Il canale usa il resolver streamingcommunityws e le funzioni callAds e check_trakt dell\'addon: il tool non puo verificarli.']
    open(os.path.join(args.out, id_ + '_rapporto.txt'), 'w', encoding='utf-8').write('\n'.join(rapporto) + '\n')
    open(os.path.join(args.out, id_ + '_cattura.json'), 'w', encoding='utf-8').write(json.dumps(cattura, indent=1, ensure_ascii=False))
    log('Fatto. File in', os.path.abspath(args.out))


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
    ap.add_argument('--proxy', help='proxy del paese giusto (http://utente:password@host:porta), anche dalla variabile PROXY_URL')
    ap.add_argument('--chromium', help='percorso di un chromium gia installato')
    ap.add_argument('--senza-profilo', action='store_true', help='ignora i profili verificati e genera il canale dal sito')
    args = ap.parse_args()
    if args.controlla_cf:
        print('true' if ha_challenge(args.url if '://' in args.url else 'https://' + args.url) else 'false')
        return
    faulthandler.dump_traceback_later(2400, exit=False)  # solo se resta fermo oltre 40 minuti, il log mostra dove
    srv = attiva_dns(args.dns)
    if srv:
        log('DNS over HTTPS attivo:', args.dns, srv)

    url = args.url if '://' in args.url else 'https://' + args.url
    if args.flaresolverr:
        flaresolverr(args.flaresolverr, url)
    profilo = trova_profilo(url, args)
    if profilo:
        usa_profilo(profilo, url, args)
        return
    id_, nome, ctx, cattura, rapporto, base = analizza(url, args)

    os.makedirs(args.out, exist_ok=True)
    if ctx['modo'] == 'api':
        py = genera_api(nome, ctx)
    elif ctx['modo'] == 'dati':
        py = genera_dati(nome, ctx)
    else:
        if not ctx['patron']:
            ctx['patron'] = r'<a [^>]*?href="(?P<url>[^"]+)"[^>]*>.*?<img [^>]*?src="(?P<thumb>[^"]+)".*?(?P<title>[^<]+)<'
            rapporto.append('TODO: regex patron non generata, scritta una regex di esempio da adattare.')
        py = genera_html(nome, ctx)
    mancano = []
    if not ctx.get('manifest') and not ctx.get('ricette_video') and not (ctx.get('player') and ctx['player'].get('video')):
        mancano.append('riproduzione (nessun manifest rilevato: findvideos generico con support.server)')
    if not ctx.get('ricerca') and not ctx.get('search_api') and not ctx.get('search_gql'):
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
