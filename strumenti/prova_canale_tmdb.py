# -*- coding: utf-8 -*-
"""Prova un canale con elenco di ID e dati TMDB: liste, ricerca, episodi, server. Uso: python3 prova_canale_tmdb.py <canale>"""
import importlib, json, os, sys, traceback
KH = os.environ.get('KH', '/tmp/kh')
sys.path.insert(0, KH); sys.path.insert(0, os.path.join(KH, 'addon'))
import fake  # noqa
from core.item import Item
from platformcode import config, logger
try:
    config.set_setting('tmdb_active', True)
    config.set_setting('episode_info', True)
except Exception as e:
    print('impostazioni', e)
_gs = config.get_setting
config.get_setting = lambda k, *a, **kw: True if k in ('tmdb_active', 'episode_info') else _gs(k, *a, **kw)
from core import tmdb
print('tmdb_active =', config.get_setting('tmdb_active'))
try:
    o = tmdb.Tmdb(id_Tmdb='603', search_type='movie')
    print('TMDB prova 603:', o.result.get('title'))
except BaseException:
    traceback.print_exc()

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
for t in [i for i in (menu or []) if i.action == 'sezione']:
    r = passo('sezione %s' % t.args, lambda: ch.sezione(t))
    rep['sez_' + t.args] = [x.title for x in (r or [])[:5]]
for azione in ('piattaforme', 'generi'):
    for t in [i for i in (menu or []) if i.action == azione]:
        sub = passo('%s %s' % (azione, t.args), lambda: getattr(ch, azione)(t))
        rep['%s_%s' % (azione, t.args)] = [x.title for x in (sub or [])]
        for x in (sub or [])[:12]:
            r = passo('%s > %s' % (azione, x.title), lambda: ch.sezione(x))
            rep['voce_%s_%s_%s' % (azione, t.args, x.title)] = len(r or [])
passo('ricerca matrix', lambda: ch.search(Item(channel=nome, action='search'), 'matrix'))
passo('ricerca breaking bad', lambda: ch.search(Item(channel=nome, action='search'), 'breaking bad'))

def serie_cercata(q):
    r = ch.search(Item(channel=nome, action='search'), q) or []
    sr = next((i for i in r if i.action == 'episodios'), None)
    rep['cerca_' + q] = [('%s | %s | %s' % (i.title, i.action, i.url)) for i in r[:6]]
    if not sr:
        return
    eps = passo('episodi di %s' % q, lambda: ch.episodios(sr))
    for ep in [i for i in (eps or []) if i.action == 'findvideos'][:3]:
        fv = passo('findvideos %s' % ep.title, lambda: ch.findvideos(ep))
        rep['server_%s_%s' % (q, ep.url)] = ['%s %s' % (x.server, x.url) for x in (fv or [])]
        rep['campi_%s' % ep.url] = dict(contentType=ep.contentType, season=ep.season, episode=ep.episode, tmdb=ep.infoLabels.get('tmdb_id'), mediatype=ep.infoLabels.get('mediatype'))


serie_cercata('lol chi ride e fuori')
serie_cercata('stranger things')
os.makedirs('rapporti/prove', exist_ok=True)
json.dump(rep, open('rapporti/prove/canale_%s.json' % nome, 'w'), indent=1, ensure_ascii=False)
print(json.dumps(rep, indent=1, ensure_ascii=False))
