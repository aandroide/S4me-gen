# -*- coding: utf-8 -*-
"""Raccoglie rapporti/prove/<canale>/esito.json e scrive rapporti/prove/RAPPORTO_VIDEO.md."""
import glob, json, os, sys
from collections import defaultdict

QUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
prove = os.path.join(QUI, 'rapporti', 'prove')
gruppi = defaultdict(list)
righe = {}
for f in sorted(glob.glob(os.path.join(prove, '*', 'esito.json'))):
    try:
        e = json.load(open(f, encoding='utf-8'))
    except Exception:
        continue
    v = e.get('verdetto', 'SENZA ESITO')
    chiave = 'ARRIVA AL VIDEO' if v.startswith('ARRIVA') else 'SI FERMA AL SERVER O AL VIDEO' if v.startswith('SI FERMA AL SERVER') else 'SI FERMA PRIMA DEL VIDEO'
    gruppi[chiave].append(e['canale'])
    righe[e['canale']] = e
mancanti = [d for d in os.listdir(prove) if os.path.isdir(os.path.join(prove, d)) and not os.path.exists(os.path.join(prove, d, 'esito.json'))] if os.path.isdir(prove) else []
out = ['# Controllo fino al video', '',
       'Riepilogo: ' + ', '.join('%s %d' % (k, len(v)) for k, v in sorted(gruppi.items())) + (', SENZA ESITO %d' % len(mancanti) if mancanti else ''), '']
for k in ('ARRIVA AL VIDEO', 'SI FERMA AL SERVER O AL VIDEO', 'SI FERMA PRIMA DEL VIDEO'):
    if not gruppi.get(k):
        continue
    out += ['## %s (%d)' % (k, len(gruppi[k])), '']
    for c in sorted(gruppi[k]):
        e = righe[c]
        out.append('### %s' % c)
        out.append('Sito: %s | verdetto: %s' % (e.get('host'), e.get('verdetto')))
        for p in e.get('passi', []):
            if p.get('esito') != 'OK':
                out.append('- passo "%s": %s %s' % (p['passo'], p['esito'], (p.get('errore') or '')[-160:].replace('\n', ' ')))
        for v in e.get('video', []):
            out.append('- server %s: %s %s' % (v.get('server'), v.get('esito'), v.get('dettaglio', v.get('nota', ''))))
        out.append('')
if mancanti:
    out += ['## SENZA ESITO (%d)' % len(mancanti), '', 'Il tempo e finito prima di concludere: ' + ' '.join(sorted(mancanti)), '']
open(os.path.join(prove, 'RAPPORTO_VIDEO.md'), 'w', encoding='utf-8').write('\n'.join(out))
json.dump({c: righe[c].get('verdetto') for c in righe}, open(os.path.join(prove, 'stato_video.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n'.join(out[:6]))
