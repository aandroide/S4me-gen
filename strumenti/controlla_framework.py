# -*- coding: utf-8 -*-
"""Controlla se canali e server S4Me seguono il framework.

  python3 strumenti/controlla_framework.py riparazioni/altadefinizione01.py riparazioni/server/vidxgo.py
  python3 strumenti/controlla_framework.py canali_base --solo-errori

Cartelle: controlla tutti i .py. Il tipo (canale o server) si riconosce da get_video_url.
Esce con 1 se trova almeno un ERRORE. Le regole stanno in strumenti/REGOLE_FRAMEWORK.md.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import framework as fw


def elenco(percorsi):
    for p in percorsi:
        if os.path.isdir(p):
            for r, _, fs in os.walk(p):
                for f in sorted(fs):
                    if f.endswith('.py') and not f.startswith('_'):
                        yield os.path.join(r, f)
        else:
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('percorsi', nargs='+')
    ap.add_argument('--solo-errori', action='store_true')
    a = ap.parse_args()
    errori = avvisi = 0
    for f in elenco(a.percorsi):
        try:
            pb = fw.controlla_file(f)
        except Exception as e:
            print('ERRORE LETTURA %s: %s' % (f, e))
            errori += 1
            continue
        for liv, cod, riga, msg in sorted(pb, key=lambda p: (p[0] != fw.ERRORE, p[2])):
            if liv == fw.ERRORE:
                errori += 1
            else:
                avvisi += 1
                if a.solo_errori:
                    continue
            print('%s %s %s:%s %s' % (liv, cod, f, riga, msg))
    print('Errori: %d, avvisi: %d' % (errori, avvisi))
    sys.exit(1 if errori else 0)


if __name__ == '__main__':
    main()
