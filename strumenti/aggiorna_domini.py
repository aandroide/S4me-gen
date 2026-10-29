#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggiorna_domini.py: scarica channels.json dalla repo ufficiale di S4Me (solo lettura) e aggiorna
canali_base/channels.json.txt con gli indirizzi attuali dei siti.

Se il download non riesce o il file non e valido, la copia locale resta com'e e il programma esce con 0.
"""
import json
import os
import sys

import requests

SORGENTI = [
    'https://raw.githubusercontent.com/stream4me/addon/master/channels.json',
    'https://raw.githubusercontent.com/stream4me/addon/main/channels.json',
]
LOCALE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'canali_base', 'channels.json.txt')
CARTELLA = os.path.dirname(LOCALE)
ELENCO = 'https://api.github.com/repos/stream4me/addon/contents/channels?ref=%s'


def aggiorna_canali(ramo):
    """Scarica i file dei canali (.py e .json) che sono cambiati o nuovi nella repo ufficiale."""
    h = {'Accept': 'application/vnd.github+json'}
    if os.environ.get('GH_TOKEN'):
        h['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    try:
        r = requests.get(ELENCO % ramo, headers=h, timeout=30)
        elenco = r.json() if r.status_code == 200 else None
    except Exception as e:
        print('Elenco dei canali non scaricato:', str(e)[:100])
        return
    if not isinstance(elenco, list):
        # senza l'elenco della API si aggiornano i file che ci sono gia
        print('Elenco dei canali non disponibile: controllo solo i file gia presenti (i canali nuovi non si vedono)')
        elenco = [{'name': n, 'type': 'file', 'download_url': 'https://raw.githubusercontent.com/stream4me/addon/%s/channels/%s' % (ramo, n)}
                  for n in sorted(os.listdir(CARTELLA)) if n.endswith(('.py', '.json')) and n != 'channels.json.txt']
    nuovi, cambiati, errori = [], [], 0
    for f in elenco:
        n = f.get('name', '')
        if f.get('type') != 'file' or not n.endswith(('.py', '.json')) or n.startswith(('__init__', '0example')):
            continue
        try:
            c = requests.get(f['download_url'], timeout=30)
            if c.status_code != 200 or not c.content:
                raise ValueError('HTTP %s' % c.status_code)
        except Exception as e:
            errori += 1
            print('File non scaricato:', n, str(e)[:80])
            continue
        dest = os.path.join(CARTELLA, n)
        if os.path.exists(dest):
            if open(dest, 'rb').read() == c.content:
                continue
            cambiati.append(n)
        else:
            nuovi.append(n)
        open(dest, 'wb').write(c.content)
    online = {f['name'] for f in elenco if isinstance(f, dict)}
    spariti = sorted(f for f in os.listdir(CARTELLA) if f.endswith(('.py', '.json')) and f not in online
                     and not f.startswith(('0example', '__init__')))
    for n in cambiati:
        print('Canale modificato nella repo ufficiale:', n)
    for n in nuovi:
        print('Canale nuovo nella repo ufficiale:', n)
    for n in spariti:
        print('Canale non piu nella repo ufficiale (copia locale lasciata):', n)
    if not cambiati and not nuovi:
        print('Nessun file dei canali modificato')


def piatto(d):
    out = {}
    for sez, v in d.items():
        if isinstance(v, dict):
            for k, u in v.items():
                if isinstance(u, str):
                    out.setdefault(k, u)
    return out


def main():
    nuovo = None
    for u in SORGENTI:
        try:
            r = requests.get(u, timeout=30)
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, dict) and isinstance(d.get('direct'), dict) and len(d['direct']) >= 10:
                    nuovo = (u, d, r.text)
                    break
        except Exception as e:
            print('Scaricamento non riuscito da', u, str(e)[:100])
    if not nuovo:
        print('channels.json ufficiale non scaricato: resta la copia della repo')
        return
    vecchio = json.load(open(LOCALE, encoding='utf-8')) if os.path.exists(LOCALE) else {}
    a, b = piatto(vecchio), piatto(nuovo[1])
    cambi = [(k, a.get(k), b[k]) for k in sorted(b) if a.get(k) != b[k]]
    tolti = sorted(set(a) - set(b))
    print('Sorgente:', nuovo[0])
    for k, x, y in cambi:
        print('Indirizzo %s: %s -> %s' % (k, x or '(nuovo canale)', y))
    for k in tolti:
        print('Canale non piu in channels.json:', k)
    if not cambi and not tolti:
        print('Nessun indirizzo cambiato')
    open(LOCALE, 'w', encoding='utf-8').write(nuovo[2] if nuovo[2].endswith('\n') else nuovo[2] + '\n')
    aggiorna_canali('main' if '/main/' in nuovo[0] else 'master')


if __name__ == '__main__':
    main()
