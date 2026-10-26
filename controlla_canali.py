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


def via_flaresolverr(url):
    """Pagina scaricata da FlareSolverr (un browser vero che supera la challenge di Cloudflare), una alla volta."""
    import fcntl
    ep = os.environ.get('FLARESOLVERR_URL', '').rstrip('/')
    if not ep:
        return None
    with open('/tmp/controlla_canali_flaresolverr.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            r = requests.post(ep + '/v1', json={'cmd': 'request.get', 'url': url, 'maxTimeout': 60000}, timeout=90).json()
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
        except requests.exceptions.SSLError:
            try:
                r = requests.get(url, headers={'User-Agent': UA}, timeout=(8, 15), verify=False)
            except Exception as e:
                ris = ('errore', '', url, 'SSL: ' + str(e)[:80])
                continue
        except Exception as e:
            ris = ('errore', '', url, str(e)[:100])
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

def host_di(nome, hosts):
    h = hosts.get(nome)
    if not h:
        return ''
    p = urlparse(h)
    return '{}://{}'.format(p.scheme or 'https', p.netloc)


def controlla(nome, hosts, ripara=True):
    ris = {'canale': nome, 'stato': '', 'dettagli': [], 'correzione': False, 'host': host_di(nome, hosts)}
    percorso = os.path.join(BASE, nome + '.py')
    src = open(percorso, encoding='utf-8').read()
    try:
        funzioni, menu = leggi_canale(src)
    except SyntaxError as e:
        ris.update(stato='NON ANALIZZABILE', dettagli=['il file non e leggibile da Python 3: %s' % e])
        return ris
    if not funzioni:
        ris.update(stato='NON REGEX', dettagli=['nessuna funzione con @support.scrape: canale a API o personalizzato, non controllato'])
        return ris
    host = ris['host']
    if not host:
        ris.update(stato='SENZA INDIRIZZO', dettagli=['il canale non e in channels.json'])
        return ris

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

    # la home dice se il sito e raggiungibile, parcheggiato o spostato
    st, html, finale, motivo = scarica(host + '/')
    if st != 'ok':
        ris.update(stato='IRRAGGIUNGIBILE' if st == 'errore' else 'CLOUDFLARE', dettagli=['%s (%s)' % (motivo, host)])
        return ris
    if PARCHEGGIATO.search(html[:60000]) or len(g.soup_di(html).find_all('a', href=True)) < 3:
        ris.update(stato='DOMINIO PARCHEGGIATO', dettagli=['la home di %s sembra un dominio in vendita o vuoto' % host])
        return ris
    if 'FlareSolverr' in motivo:
        ris['dettagli'].append('sito protetto da Cloudflare: pagine scaricate con FlareSolverr')
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
        prop = proponi_patron(html, norm, fn['patron'])
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
    out = {}
    for sez in d.values():
        if isinstance(sez, dict):
            for k, v in sez.items():
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
