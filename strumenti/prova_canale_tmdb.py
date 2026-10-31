# -*- coding: utf-8 -*-
"""Prova un canale con elenco di ID e dati TMDB: liste, ricerca, episodi, server. Uso: python3 prova_canale_tmdb.py <canale>"""
import importlib, json, os, sys, traceback
KH = os.environ.get('KH', '/tmp/kh')
sys.path.insert(0, KH); sys.path.insert(0, os.path.join(KH, 'addon'))
import fake  # noqa
from core.item import Item

nome = sys.argv[1]
ch = importlib.import_module('channels.' + nome)
rep = {'canale': nome, 'passi': []}


def passo(n, f):
    try:
        r = f()
        rep['passi'].append({'passo': n, 'esito': 'OK', 'voci': len(r or []),
                             'esempi': [('%s | %s | tmdb=%s | thumb=%s | plot=%s' % (i.title, i.action, i.infoLabels.get('tmdb_id'), bool(i.thumbnail), bool(i.plot)))[:160] for i in (r or [])[:4]]})
        return r
    except BaseException:
        rep['passi'].append({'passo': n, 'esito': 'ERRORE', 'errore': traceback.format_exc(limit=4)[-600:]})
        return None


menu = passo('mainlist', lambda: ch.mainlist(Item(channel=nome, action='mainlist')))
voci = [i for i in (menu or []) if i.action == 'peliculas']
film = next((v for v in voci if v.contentType == 'movie'), None)
serie = next((v for v in voci if v.contentType == 'tvshow'), None)
lf = passo('lista film', lambda: ch.peliculas(film)) if film else None
ls = passo('lista serie', lambda: ch.peliculas(serie)) if serie else None
if lf:
    p2 = next((i for i in lf if i.action == 'peliculas'), None)
    if p2:
        passo('film pagina 2', lambda: ch.peliculas(p2))
    mv = next((i for i in lf if i.action == 'findvideos'), None)
    if mv:
        fv = passo('findvideos film', lambda: ch.findvideos(mv))
        if fv:
            rep['server_film'] = ['%s %s' % (x.server, x.url) for x in fv]
if ls:
    sr = next((i for i in ls if i.action == 'episodios'), None)
    if sr:
        eps = passo('episodi di "%s"' % sr.fulltitle, lambda: ch.episodios(sr))
        ep = next((i for i in (eps or []) if i.action == 'findvideos'), None)
        if ep:
            fv = passo('findvideos episodio', lambda: ch.findvideos(ep))
            if fv:
                rep['server_episodio'] = ['%s %s' % (x.server, x.url) for x in fv]
passo('ricerca matrix', lambda: ch.search(Item(channel=nome, action='search'), 'matrix'))
passo('ricerca breaking bad', lambda: ch.search(Item(channel=nome, action='search'), 'breaking bad'))
os.makedirs('rapporti/prove', exist_ok=True)
json.dump(rep, open('rapporti/prove/canale_%s.json' % nome, 'w'), indent=1, ensure_ascii=False)
print(json.dumps(rep, indent=1, ensure_ascii=False))
