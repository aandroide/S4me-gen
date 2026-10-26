#!/usr/bin/env python3
"""Cerca un proxy italiano (SOCKS5 o HTTP) funzionante tra quelli pubblici e lo scrive come PROXY_URL.

Uso: python3 scegli_proxy.py <sito> [--paese IT] [--max 8]
Scrive PROXY_URL=... nel file indicato da GITHUB_ENV (se esiste) e lo stampa.
I proxy pubblici vanno offline in poche ore: ogni volta si provano tutti, in parallelo.
Per i SOCKS5 serve il pacchetto PySocks (pip install requests[socks]).
"""
import argparse
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# liste gia divise per paese: (indirizzo, protocollo predefinito se le righe non lo indicano)
LISTE = [
    ('https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&country={paese}&timeout=10000', 'http'),
    ('https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&country={paese}&timeout=8000', 'socks5'),
    ('https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&country={paese}&timeout=8000&ssl=all&anonymity=all', 'http'),
    ('https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/{paese}/data.txt', 'http'),
    ('https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/{paese}/data.txt', 'http'),
    ('https://www.proxy-list.download/api/v1/get?type=socks5&country={paese}', 'socks5'),
    ('https://www.proxy-list.download/api/v1/get?type=http&country={paese}', 'http'),
]
# liste di tutto il mondo: si tengono solo gli indirizzi del paese
GREZZE = [
    ('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt', 'socks5'),
    ('https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt', 'socks5'),
    ('https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt', 'socks5'),
    ('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt', 'http'),
]
CONTROLLI_PAESE = ['https://ipinfo.io/country', 'https://ifconfig.co/country-iso']
RIGA_RE = re.compile(r'^\s*(?:(socks5|socks4|https?)://)?(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\b', re.I)


def leggi_json(testo, paese):
    """Elenco JSON di proxy5.net: ip_address, port, protocols, country_code, is_working."""
    try:
        d = json.loads(testo)
    except Exception:
        return None
    if not isinstance(d, list):
        return None
    out = []
    for x in d:
        if not isinstance(x, dict) or 'ip_address' not in x or x.get('country_code', paese) != paese:
            continue
        if x.get('is_working') is False:
            continue
        pr = [p.upper() for p in x.get('protocols', [])]
        sch = 'socks5' if 'SOCKS5' in pr else ('http' if ('HTTP' in pr or 'HTTPS' in pr) else None)
        if sch:
            out.append('%s://%s:%s' % (sch, x['ip_address'], x['port']))
    return out


def leggi_indirizzi(testo, predefinito='http', paese='IT'):
    """Righe 'ip:porta' oppure 'protocollo://ip:porta' (o un JSON di proxy5) -> elenco di 'protocollo://ip:porta'."""
    if testo.lstrip()[:1] in ('[', '{'):
        j = leggi_json(testo, paese)
        if j is not None:
            return j
    out = []
    for riga in testo.splitlines():
        m = RIGA_RE.match(riga)
        if m:
            sch = (m.group(1) or predefinito).lower()
            if sch == 'https':
                sch = 'http'
            if sch == 'socks4':
                continue  # il browser lo gestisce, ma la prova con requests no
            out.append('%s://%s:%s' % (sch, m.group(2), m.group(3)))
    return out


def scarica_liste(paese):
    trovati = []
    extra = [(u, 'http') for u in os.environ.get('PROXY_LISTE', '').split() if u]
    for u, pred in extra + LISTE:
        try:
            r = requests.get(u.format(paese=paese), timeout=20)
            nuovi = leggi_indirizzi(r.text, pred, paese)
            trovati += nuovi
            print('Lista', u.split('?')[0].replace('https://', '')[:70], '->', len(nuovi), 'indirizzi', flush=True)
        except Exception as ex:
            print('Lista non raggiungibile', u.split('?')[0][:70], str(ex)[:60], flush=True)
    # liste salvate nel repo (istantanee): servono se le liste online non rispondono
    cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxy_locali')
    if os.path.isdir(cartella):
        for nome in sorted(os.listdir(cartella)):
            try:
                nuovi = leggi_indirizzi(open(os.path.join(cartella, nome), encoding='utf-8').read(), 'http', paese)
                trovati += nuovi
                print('Lista salvata', nome, '->', len(nuovi), 'indirizzi', flush=True)
            except Exception as ex:
                print('Lista salvata non letta', nome, str(ex)[:60], flush=True)
    return list(dict.fromkeys(trovati))


def filtra_per_paese(indirizzi, paese, massimo=1500):
    """Tiene solo gli IP del paese con la ricerca a blocchi di ip-api (limite del servizio: 15 richieste al minuto)."""
    ip_di = {}
    for x in indirizzi:
        ip_di.setdefault(x.split('://')[1].split(':')[0], []).append(x)
    ips = list(ip_di)
    random.shuffle(ips)
    ips = ips[:massimo]
    tenuti = []
    for i in range(0, len(ips), 100):
        try:
            r = requests.post('http://ip-api.com/batch?fields=query,countryCode', json=ips[i:i + 100], timeout=20)
            for d in r.json():
                if d.get('countryCode') == paese:
                    tenuti += ip_di.get(d.get('query'), [])
        except Exception as ex:
            print('Controllo del paese non riuscito:', str(ex)[:80], flush=True)
            break
    print('Indirizzi %s nelle liste mondiali: %d su %d controllati' % (paese, len(tenuti), len(ips)), flush=True)
    return tenuti


def prova(proxy, sito, paese):
    sch = proxy.split('://')[0]
    url = proxy.replace('socks5://', 'socks5h://')
    p = {'http': url, 'https': url}
    try:
        ok_paese = False
        for c in CONTROLLI_PAESE:
            try:
                r = requests.get(c, proxies=p, timeout=8)
                if r.status_code == 200 and r.text.strip().upper()[:2] == paese:
                    ok_paese = True
                    break
            except Exception:
                continue
        if not ok_paese:
            return None
        r = requests.get(sito, proxies=p, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        return proxy if r.status_code == 200 else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sito')
    ap.add_argument('--paese', default='IT')
    ap.add_argument('--max', type=int, default=8, help='quanti proxy funzionanti tenere come candidati')
    a = ap.parse_args()
    paese = a.paese.upper()
    lista = scarica_liste(paese)
    grezzi = []
    for u, pred in GREZZE:
        try:
            r = requests.get(u, timeout=25)
            nuovi = leggi_indirizzi(r.text, pred)
            grezzi += nuovi
            print('Lista mondiale', u.split('/')[3], u.rsplit('/', 1)[-1], '->', len(nuovi), 'indirizzi', flush=True)
        except Exception as ex:
            print('Lista mondiale non raggiungibile', u.split('/')[3], str(ex)[:60], flush=True)
    if grezzi:
        lista += filtra_per_paese(list(dict.fromkeys(grezzi)), paese)
    lista = list(dict.fromkeys(lista))
    # prima i SOCKS5, che sono i piu numerosi e di solito i piu stabili
    lista.sort(key=lambda x: 0 if x.startswith('socks5') else 1)
    print('Proxy da provare:', len(lista), flush=True)
    buoni = []
    with ThreadPoolExecutor(max_workers=40) as ex:
        futuri = [ex.submit(prova, x, a.sito, paese) for x in lista[:500]]
        for f in as_completed(futuri):
            r = f.result()
            if r:
                buoni.append(r)
                print('Funziona:', r, flush=True)
                if len(buoni) >= a.max:
                    break
    if not buoni:
        print('Nessun proxy italiano funzionante adesso. Il run continua senza proxy: riprova piu tardi o usa un proxy tuo (segreto PROXY_URL).')
        return 0
    scelto = buoni[0]
    gh = os.environ.get('GITHUB_ENV')
    if gh:
        with open(gh, 'a') as f:
            f.write('PROXY_URL=%s\n' % scelto)
    print('PROXY_URL scelto:', scelto)
    return 0


if __name__ == '__main__':
    sys.exit(main())
