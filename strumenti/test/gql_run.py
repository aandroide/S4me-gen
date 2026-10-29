import sys, json, types, importlib.util, tempfile, os
sys.path.insert(0, '..'); sys.path.insert(0, '.')
import s4me_gen as g

def nodo(i, tipo):
    return {"node": {"__typename": tipo, "id": "%s%d" % ('ts' if tipo == 'Show' else 'tm', i),
                     "content": {"title": "Titolo %d" % i, "fullPath": "/it/x/%d" % i, "originalReleaseYear": 2000 + i,
                                 "shortDescription": "Una trama abbastanza lunga %d per essere una trama" % i,
                                 "posterUrl": "/poster/%d/{profile}/x.{format}" % i}}}
def risposta(dopo):
    base = 0 if not dopo else 20
    return {"data": {"popularTitles": {"edges": [nodo(base + i, 'Show' if i % 2 else 'Movie') for i in range(6)],
                                       "pageInfo": {"endCursor": "C2" if not dopo else "", "hasNextPage": not dopo}}}}
req = {"operationName": "GetPopularTitles", "variables": {"first": 40, "after": "", "offset": 0}, "query": "query{x}"}
net = [{'url': 'https://apis.jw.com/graphql', 'method': 'POST', 'ct': 'application/json', 'post': json.dumps(req),
        'body': json.dumps(risposta(''))}]
api = g.trova_elenco_api(net)
pag = {'dove': 'corpo', 'chiave': 'after', 'tipo': 'cursore', 'valore': ''}
ctx = {'base': 'https://www.jw.com', 'tipo': 'movie', 'api': api, 'pag': pag, 'search_api': '', 'manifest': None,
       'search_body': {'url': 'https://apis.jw.com/graphql', 'post': json.dumps(dict(req, variables={"first": 40, "q": "__TESTO__"}))}}
cod = g.genera_api('Prova', ctx)
d = tempfile.mkdtemp(); f = os.path.join(d, 'prova.py'); open(f, 'w').write(cod)

class Item:
    def __init__(s, **kw): s.__dict__.update(kw); s.__dict__.setdefault('infoLabels', {})
    def __getattr__(s, k): return '' if not k.startswith('__') else (_ for _ in ()).throw(AttributeError(k))
    def clone(s, **kw): d = dict(s.__dict__); d.update(kw); return Item(**d)
host = 'https://www.jw.com'
sup = types.ModuleType('core.support'); sup.config = types.SimpleNamespace(get_channel_url=lambda *a: host)
sup.menu = lambda f: f; sup.info = lambda *a: None; sup.typo = lambda s, t='': s; sup.thumb = lambda *a: ''
sup.server = lambda item, itemlist=None, **k: itemlist
chiamate = []
class R:
    def __init__(s, j): s.json = j
def dp(url, **o):
    body = json.loads(o['post']); chiamate.append(body['variables'])
    if 'q' in body['variables']: return R(risposta(''))
    return R(risposta(body['variables'].get('after', '')))
ht = types.ModuleType('core.httptools'); ht.downloadpage = dp; ht.get_user_agent = lambda: 'UA'
tm = types.ModuleType('core.tmdb'); tm.set_infoLabels_itemlist = lambda *a, **k: None
it = types.ModuleType('core.item'); it.Item = Item; it.InfoLabels = dict
core = types.ModuleType('core'); core.support = sup; core.httptools = ht; core.tmdb = tm
pc = types.ModuleType('platformcode'); pc.config = types.SimpleNamespace(get_localized_string=lambda n: 'Pagina successiva')
pc.logger = types.SimpleNamespace(error=print, debug=lambda *a: None); pc.platformtools = types.SimpleNamespace(dialog_ok=print)
for n, m in [('core', core), ('core.support', sup), ('core.httptools', ht), ('core.tmdb', tm), ('core.item', it), ('platformcode', pc)]: sys.modules[n] = m
sp = importlib.util.spec_from_file_location('prova', f); c = importlib.util.module_from_spec(sp); sp.loader.exec_module(c)
l = c.peliculas(Item(channel='x'))
print(len(l), [(i.title, i.action, i.contentType, i.thumbnail) for i in l[:2]], l[-1].title, l[-1].after)
l2 = c.peliculas(l[-1]); print('pag2', len(l2), l2[0].title, [i.title for i in l2 if i.action == 'peliculas'])
s = c.search(Item(channel='x'), 'matrix'); print('search', len(s), chiamate[-1])
print(chiamate)
