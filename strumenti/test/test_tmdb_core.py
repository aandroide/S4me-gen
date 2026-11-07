# Prova: i canali portati sul core TMDB (casacinema, guardaserieicu, guardaseriecam) ricevono id e titoli
# da un finto core.tmdb. Si eseguono solo le funzioni interessate, senza Kodi.
import ast
import os
import re
import sys
import traceback
import types

RADICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'riparazioni')
chiamate = []


class FintoTmdb:
    host = 'https://api.themoviedb.org/3'
    api = 'chiave-finta'

    def __init__(self, **kw):
        chiamate.append(('init', kw))
        self.kw = kw
        self.search_id = kw.get('id_Tmdb') or ''

    def get_id(self):
        return '1399' if self.kw.get('external_id') == 'tt0944947' else ''

    def get_season(self, s):
        if s == 1:
            return {'episodes': [{'episode_number': 1, 'name': 'Inverno sta arrivando', 'overview': 'x'},
                                 {'episode_number': 2, 'name': 'Episodio 2'}]}
        return {}

    def get_list_episodes(self):
        return [{'season_number': 0, 'episode_count': 1, 'start_from': 1},
                {'season_number': 1, 'episode_count': 2, 'start_from': 1}]

    @staticmethod
    def get_json(url, cache=True):
        chiamate.append(('get_json', url))
        return {'imdb_id': 'tt0944947'} if '/tv/' in url else {}


def modulo_tmdb():
    m = types.ModuleType('core.tmdb')
    m.Tmdb = FintoTmdb
    m.host = FintoTmdb.host
    m.api = FintoTmdb.api
    core = types.ModuleType('core')
    core.tmdb = m
    sys.modules['core'] = core
    sys.modules['core.tmdb'] = m


def carica(nome, funzioni):
    """Esegue solo le funzioni indicate e le costanti semplici del file."""
    testo = open(os.path.join(RADICE, nome + '.py'), encoding='utf-8').read()
    albero = ast.parse(testo)
    pezzi = []
    for n in albero.body:
        if isinstance(n, ast.FunctionDef) and n.name in funzioni:
            pezzi.append(n)
        elif isinstance(n, ast.Assign) and isinstance(n.value, (ast.Dict, ast.Constant)):
            pezzi.append(n)
    ns = {'re': re, 'traceback': traceback,
          'logger': types.SimpleNamespace(info=lambda *a: None, error=lambda *a: None)}
    exec(compile(ast.Module(body=pezzi, type_ignores=[]), nome, 'exec'), ns)
    return ns


fallite = []


def verifica(cond, msg):
    if not cond:
        fallite.append(msg)


modulo_tmdb()
for nome in ('guardaserieicu', 'casacinema'):
    chiamate.clear()
    ns = carica(nome, ('_tmdb_id_from_token', '_season_titles', '_episode_titles', '_imdb_from_tm'))
    verifica(ns['_tmdb_id_from_token']('tm603') == 603, '%s: token tm' % nome)
    verifica(ns['_tmdb_id_from_token']('0944947') == 1399, '%s: id da imdb' % nome)
    verifica(ns['_tmdb_id_from_token']('9999999') is False, '%s: imdb sconosciuto' % nome)
    titoli = ns['_episode_titles']('0944947', [(1, 1), (1, 2)])
    verifica(titoli == {(1, 1): 'Inverno sta arrivando'}, '%s: titoli stagione, trovati %s' % (nome, titoli))
    if nome == 'casacinema':
        verifica(ns['_imdb_from_tm']('tm1399') == '0944947', 'casacinema: imdb da tm')
    verifica(not any(c[0] == 'get_json' and 'themoviedb' in c[1] and 'api_key=a1ab' in c[1] for c in chiamate),
             '%s: usa ancora la chiave scritta nel canale' % nome)

# guardaseriecam.episodios con support e Item finti
testo = open(os.path.join(RADICE, 'guardaseriecam.py'), encoding='utf-8').read()
fn = next(n for n in ast.parse(testo).body if isinstance(n, ast.FunctionDef) and n.name == 'episodios')


class Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)
    def clone(self, **kw):
        d = dict(self.__dict__); d.update(kw); return Item(**d)


class Match:
    def __init__(self, match, data=''):
        self.match, self.data = match, data


def match(a, patron=None):
    return Match("0944947" if patron else None, "var imdb = 'tt0944947'")


ns = {'support': types.SimpleNamespace(match=match, info=lambda *a: None),
      'logger': types.SimpleNamespace(error=lambda *a: None, info=lambda *a: None)}
exec(compile(ast.Module(body=[fn], type_ignores=[]), 'guardaseriecam', 'exec'), ns)
lista = ns['episodios'](Item(plot='trama', url='u'))
verifica(len(lista) == 2, 'guardaseriecam: attesi 2 episodi, trovati %d' % len(lista))
verifica(lista and lista[0].title == '1x01 - Inverno sta arrivando', 'guardaseriecam: titolo %s' % (lista[0].title if lista else ''))
verifica(lista and lista[0].url == 'https://v.vidxgo.co/0944947/1/1', 'guardaseriecam: url')

if fallite:
    print('\n'.join(fallite))
    sys.exit(1)
print('Prove core TMDB: tutte superate')
