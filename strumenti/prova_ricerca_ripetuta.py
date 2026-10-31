# -*- coding: utf-8 -*-
"""Ripete la ricerca di un canale piu volte e misura esito e tempi. Uso: python3 prova_ricerca_ripetuta.py <canale> <ripetizioni> <testo>..."""
import importlib, json, os, sys, time, traceback
KH = os.environ.get('KH', '/tmp/kh')
sys.path.insert(0, KH); sys.path.insert(0, os.path.join(KH, 'addon'))
import fake  # noqa
from core.item import Item
nome, n = sys.argv[1], int(sys.argv[2])
testi = [t for a in sys.argv[3:] for t in a.split('|')]
ch = importlib.import_module('channels.' + nome)
diag_animeunity = nome == 'animeunity'
rep = {'canale': nome, 'host': getattr(ch, 'host', ''), 'prove': []}
if diag_animeunity:
    import json as _j
    try:
        r0 = ch.httptools.downloadpage(ch.host + '/archivio')
        rep['archivio'] = {'codice': r0.code, 'byte': len(r0.data or ''), 'csrf': ch.csrf_token[:8] if ch.csrf_token else '', 'inizio': (r0.data or '')[:200]}
        r1 = ch.httptools.downloadpage(ch.host + '/archivio/get-animes', headers=ch.headers, post=_j.dumps({'title': 'one piece', 'offset': 0}))
        rep['get_animes'] = {'codice': r1.code, 'byte': len(r1.data or ''), 'inizio': (r1.data or '')[:300]}
    except BaseException:
        rep['diag_errore'] = traceback.format_exc(limit=3)[-400:]
for t in testi:
    for i in range(n):
        t0 = time.time()
        try:
            r = ch.search(Item(channel=nome, action='search'), t) or []
            esito = 'OK' if r else 'VUOTO'
            if not r and os.environ.get('DIRETTO'):
                try:
                    ch.peliculas(Item(channel=nome, action='peliculas', args={'title': t}, url=ch.host))
                except BaseException:
                    err = traceback.format_exc(limit=4)[-500:]
            ex = ['%s | %s | %s' % (x.title[:60], x.action, x.contentType) for x in r[:6]]
            err = locals().get('err', '')
        except BaseException:
            esito, ex, err = 'ERRORE', [], traceback.format_exc(limit=3)[-300:]
        rep['prove'].append({'testo': t, 'n': i + 1, 'esito': esito, 'voci': len(r) if esito == 'OK' else 0,
                             'secondi': round(time.time() - t0, 1), 'esempi': ex, 'errore': err})
        time.sleep(2)
os.makedirs('rapporti/prove', exist_ok=True)
json.dump(rep, open('rapporti/prove/ricerca_%s.json' % nome, 'w'), indent=1, ensure_ascii=False)
print(json.dumps(rep, indent=1, ensure_ascii=False))
