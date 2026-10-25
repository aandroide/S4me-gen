#!/usr/bin/env python3
"""Cerca un proxy HTTP italiano funzionante tra quelli pubblici e lo scrive come PROXY_URL.

Uso: python3 scegli_proxy.py <sito> [--paese IT] [--max 8]
Scrive PROXY_URL=... nel file indicato da GITHUB_ENV (se esiste) e lo stampa.
I proxy pubblici vanno offline in poche ore: si prova ogni volta, uno per uno, in parallelo.
"""
import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

LISTE = [
    'https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&country={paese}&timeout=6000&ssl=all&anonymity=all',
    'https://www.proxy-list.download/api/v1/get?type=http&country={paese}',
]
CONTROLLI_PAESE = ['https://ipinfo.io/country', 'https://ifconfig.co/country-iso']


def scarica_liste(paese):
    trovati = []
    extra = [u for u in os.environ.get('PROXY_LISTE', '').split() if u]
    for u in extra + LISTE:
        try:
            r = requests.get(u.format(paese=paese), timeout=20)
            for riga in r.text.splitlines():
                m = re.match(r'^\s*(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\s*$', riga)
                if m:
                    trovati.append('%s:%s' % (m.group(1), m.group(2)))
            print('Lista', u.split('?')[0], '->', len(trovati), 'indirizzi finora', flush=True)
        except Exception as ex:
            print('Lista non raggiungibile', u.split('?')[0], str(ex)[:80], flush=True)
    return list(dict.fromkeys(trovati))


def prova(ip_porta, sito, paese):
    p = {'http': 'http://' + ip_porta, 'https': 'http://' + ip_porta}
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
        if r.status_code != 200:
            return None
        return ip_porta
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sito')
    ap.add_argument('--paese', default='IT')
    ap.add_argument('--max', type=int, default=8, help='quanti proxy funzionanti tenere come candidati')
    a = ap.parse_args()
    lista = scarica_liste(a.paese)
    print('Proxy da provare:', len(lista), flush=True)
    buoni = []
    with ThreadPoolExecutor(max_workers=40) as ex:
        futuri = [ex.submit(prova, x, a.sito, a.paese.upper()) for x in lista[:400]]
        for f in as_completed(futuri):
            r = f.result()
            if r:
                buoni.append(r)
                print('Funziona:', r, flush=True)
                if len(buoni) >= a.max:
                    break
    if not buoni:
        print('Nessun proxy italiano funzionante adesso. Riprova tra poco o usa un proxy tuo (segreto PROXY_URL).')
        return 1
    scelto = 'http://' + buoni[0]
    gh = os.environ.get('GITHUB_ENV')
    if gh:
        with open(gh, 'a') as f:
            f.write('PROXY_URL=%s\n' % scelto)
    print('PROXY_URL scelto:', scelto)
    return 0


if __name__ == '__main__':
    sys.exit(main())
