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
LOCALE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'canali_base', 'channels.json.txt')


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


if __name__ == '__main__':
    main()
