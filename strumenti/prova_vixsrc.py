# -*- coding: utf-8 -*-
"""Prova Vixsrc come server: findvideos di un canale con un ID TMDb dato, poi risoluzione e richiesta dei primi byte.
Uso: python3 prova_vixsrc.py <canale> <id tmdb> [film|serie] [--host https://sito]"""
import importlib, json, os, sys, traceback
KH = os.environ.get('KH', '/tmp/kh')
sys.path.insert(0, KH); sys.path.insert(0, os.path.join(KH, 'addon'))
import fake  # noqa
from core.item import Item
from core import servertools, httptools
import requests

nome, tmdb = sys.argv[1], sys.argv[2]
tipo = sys.argv[3] if len(sys.argv) > 3 else 'film'
host = ''
if '--host' in sys.argv:
    host = sys.argv[sys.argv.index('--host') + 1]
ch = importlib.import_module('channels.' + nome)
it = Item(channel=nome, action='findvideos', url=(host or ch.host) + '/it/watch/1', fulltitle='Prova')
it.infoLabels['tmdb_id'] = tmdb
if tipo != 'film':
    it.infoLabels['tmdb_id_show'] = tmdb
if tipo == 'film':
    it.contentType = 'movie'
else:
    it.contentType = 'episode'
    it.season, it.episode = 1, 1
res = {'canale': nome, 'tmdb': tmdb, 'voci': [], 'esito': 'NESSUN SERVER VIXSRC'}
try:
    voci = ch.findvideos(it)
except BaseException:
    voci = []
    res['errore'] = traceback.format_exc(limit=3)[-400:]
for v in voci:
    res['voci'].append('%s | %s | %s' % (v.action, v.server, (v.url or '')[:100]))
vix = [v for v in voci if v.server == 'vixsrc']
if vix:
    res['esito'] = 'SERVER VIXSRC PRESENTE'
    try:
        urls = servertools.resolve_video_urls_for_playing('vixsrc', vix[0].url)[0]
        res['risolto'] = [[str(u[0]), str(u[1])[:160]] for u in urls][:3]
        if urls:
            u = str(urls[0][1]).partition('|')[0]
            r = requests.get(u, timeout=30, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://vixsrc.to/'})
            res['video'] = '%s %s' % (r.status_code, r.text[:20].replace('\n', ' '))
            res['master'] = r.text[:900]
            res['master_endlist'] = '#EXT-X-ENDLIST' in r.text
            import re as _re
            from urllib.parse import urljoin
            fig = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith('#')]
            if fig:
                c = requests.get(urljoin(u, fig[0]), timeout=30, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://vixsrc.to/'})
                res['figlio'] = '%s %s' % (c.status_code, c.text[:400])
                res['figlio_endlist'] = '#EXT-X-ENDLIST' in c.text
                res['figlio_tipo'] = _re.findall(r'#EXT-X-PLAYLIST-TYPE:[A-Z]+', c.text)
            res['esito'] = 'VIDEO OK' if r.status_code == 200 and r.text.startswith('#EXTM3U') else 'RISOLTO MA NON UN VIDEO'
        else:
            res['esito'] = 'SERVER PRESENTE, NESSUN VIDEO RISOLTO'
    except BaseException:
        res['esito'] = 'ERRORE NELLA RISOLUZIONE'
        res['errore'] = traceback.format_exc(limit=3)[-400:]
os.makedirs('rapporti/prove', exist_ok=True)
json.dump(res, open('rapporti/prove/vixsrc_%s_%s.json' % (nome, tipo), 'w'), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))
