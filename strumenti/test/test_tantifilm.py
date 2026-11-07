# Prova: la serie di tantifilm (pagina con solo il lettore vidxgo) diventa un elenco di episodi da TMDB.
# Si usa una pagina vera salvata dal runner e un finto core.tmdb, senza Kodi.
import ast
import os
import re
import sys
import types

RADICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
CANALE = os.path.join(RADICE, 'riparazioni', 'tantifilm.py')
PAGINA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'tantifilm_serie.html')

fallite = []


class FintoTmdb:
    def __init__(self, **kw):
        self.kw = kw

    def get_id(self):
        return '777' if self.kw.get('external_id') == 'tt35926686' else ''

    def get_list_episodes(self):
        return [{'season_number': 0}, {'season_number': 1}, {'season_number': 2}]

    def get_season(self, s):
        if s == 1:
            return {'episodes': [{'episode_number': 1, 'name': 'Pilota', 'overview': 'p1'},
                                 {'episode_number': 2, 'name': ''}]}
        return {'episodes': [{'episode_number': 1, 'name': 'Ritorno'}]}


core = types.ModuleType('core')
core.tmdb = types.ModuleType('core.tmdb')
core.tmdb.Tmdb = FintoTmdb
sys.modules['core'] = core
sys.modules['core.tmdb'] = core.tmdb


class Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def clone(self, **kw):
        d = dict(self.__dict__)
        d.update(kw)
        return Item(**d)


class Match:
    def __init__(self, match, data=''):
        self.match, self.data = match, data


def match(data, patron=None, headers=None):
    if patron is None:
        return Match(None, data if isinstance(data, str) else '')
    m = re.search(patron, data)
    return Match(m.group(1) if m else '')


chiamate = []
support = types.SimpleNamespace(
    match=match, check_trakt=lambda l: chiamate.append('trakt'),
    videolibrary=lambda l, i: chiamate.append('videoteca'),
    server=lambda item, itemlist=None, data='': itemlist)
logger = types.SimpleNamespace(error=lambda *a: None, info=lambda *a: None, debug=lambda *a: None)

albero = ast.parse(open(CANALE, encoding='utf-8').read())
fn = [n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name in ('episodios', 'findvideos')]
ns = {'support': support, 'logger': logger, 're': re, 'headers': [], 'player_iframe': r'<iframe.*?src="([^"]+)"'}
exec(compile(ast.Module(body=fn, type_ignores=[]), 'tantifilm', 'exec'), ns)

pagina = open(PAGINA, encoding='utf-8', errors='ignore').read()
lista = ns['episodios'](Item(data=pagina, url='https://tanti-film.ink/guarda/x.html', plot='trama'))
titoli = [i.title for i in lista]
if titoli != ['1x01 - Pilota', '1x02', '2x01 - Ritorno']:
    fallite.append('episodi attesi 1x01 - Pilota, 1x02, 2x01 - Ritorno; trovati %s' % titoli)
if lista and lista[0].url != 'https://v.vidxgo.co/35926686/1/1':
    fallite.append('url episodio: %s' % lista[0].url)
if chiamate != ['trakt', 'videoteca']:
    fallite.append('mancano check_trakt e videolibrary: %s' % chiamate)

# l'episodio si apre direttamente su vidxgo, senza scaricare di nuovo la pagina
res = ns['findvideos'](lista[0])
if not res or res[0].server != 'vidxgo':
    fallite.append('findvideos su episodio: %s' % res)

# senza imdb nella pagina non ci sono episodi e non va in errore
if ns['episodios'](Item(data='<html></html>', url='u')) != []:
    fallite.append('pagina senza imdb deve dare elenco vuoto')

if fallite:
    print('\n'.join(fallite))
    sys.exit(1)
print('Prova tantifilm: superata')
