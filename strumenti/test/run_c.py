import sys, types, importlib.util, requests, json
host = sys.argv[2]
class Item:
    def __init__(s, **kw): s.__dict__.update(kw); s.__dict__.setdefault('infoLabels', {})
    def __getattr__(s, k): return '' if not k.startswith('__') else (_ for _ in ()).throw(AttributeError(k))
    def clone(s, **kw): d = dict(s.__dict__); d.update(kw); return Item(**d)
sup = types.ModuleType('core.support'); sup.config = types.SimpleNamespace(get_channel_url=lambda *a: host)
sup.menu = lambda f: (lambda *a: f(*a)); sup.info = lambda *a: None; sup.typo = lambda t, k='': t; sup.thumb = lambda *a: ''
sup.server = lambda item, itemlist=None, **k: itemlist; sup.videolibrary = lambda *a: None
class R:
    def __init__(s, r): s.r = r
    @property
    def json(s): return s.r.json()
def dp(url, **o):
    return R(requests.post(url, data=o['post']) if o.get('post') is not None else requests.get(url))
ht = types.ModuleType('core.httptools'); ht.downloadpage = dp; ht.get_user_agent = lambda: 'UA'
tm = types.ModuleType('core.tmdb'); tm.set_infoLabels_itemlist = lambda *a, **k: None
it = types.ModuleType('core.item'); it.Item = Item; it.InfoLabels = dict
core = types.ModuleType('core'); core.support = sup; core.httptools = ht; core.tmdb = tm
pc = types.ModuleType('platformcode'); pc.config = types.SimpleNamespace(get_localized_string=lambda n: 'Pagina successiva', get_setting=lambda *a: False)
pc.logger = types.SimpleNamespace(error=print, debug=lambda *a: None, info=lambda *a: None); pc.platformtools = types.SimpleNamespace(dialog_ok=print)
for n, m in [('core', core), ('core.support', sup), ('core.httptools', ht), ('core.tmdb', tm), ('core.item', it), ('platformcode', pc)]: sys.modules[n] = m
sp = importlib.util.spec_from_file_location('canale', sys.argv[1]); c = importlib.util.module_from_spec(sp); sp.loader.exec_module(c)
m = c.mainlist(Item())
print('menu', [(k, [x[0] for x in v[1:]]) for k, v in m.items() if k in ('film', 'tvshow')])
for idx, tp in (('1', 'movie'), ('2', 'tvshow')):
    l = c.peliculas(Item(channel='x', args=idx, contentType=tp))
    print('sezione', idx, len(l), [(i.title, i.action, i.contentType, i.idv) for i in l[:2]])
serie = [i for i in c.peliculas(Item(channel='x', args='2', contentType='tvshow')) if i.action == 'episodios'][0]
eps = c.episodios(serie); print('episodi', len(eps), [(e.title, e.idv) for e in eps[:2]])
print('play ep', [(v.url, v.license.split('|')[0]) for v in c.findvideos(eps[0])])
film = [i for i in c.peliculas(Item(channel='x', args='0', contentType='movie')) if i.action == 'findvideos'][0]
print('play film', [(v.url, v.manifest) for v in c.findvideos(film)])
print('search', len(c.search(Item(channel='x'), 'matrix')))

clear = [i for i in c.peliculas(Item(channel='x', args='0', contentType='movie')) if i.idv == 'tm1'][0]
print('play senza DRM', [(v.url, v.manifest, v.drm) for v in c.findvideos(clear)])
