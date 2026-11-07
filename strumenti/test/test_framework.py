# Prove del controllo framework: python3 strumenti/test/test_framework.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import framework as fw

fallite = []


def codici(testo, tipo):
    return {c for _, c, _, _ in fw.controlla_codice(testo, tipo)}


def deve(nome, testo, tipo, presenti=(), assenti=()):
    got = codici(testo, tipo)
    for c in presenti:
        if c not in got:
            fallite.append('%s: manca %s (trovati %s)' % (nome, c, sorted(got)))
    for c in assenti:
        if c in got:
            fallite.append('%s: %s non doveva comparire' % (nome, c))


CANALE_BUONO = '''
from core import support, httptools, config
@support.menu
def mainlist(item):
    menu = [('Tutti', ['/a/', 'peliculas', '', 'undefined'])]
    return locals()
@support.scrape
def peliculas(item):
    if item.contentType in ('undefined', ''):
        item.contentType = 'movie'
    typeContentDict = {'movie': ['x']}
    patron = r'(?P<type>x)(?P<url>u)(?P<title>t)'
    return locals()
def episodios(item):
    itemlist = [item.clone(contentType='episode', title='1x01')]
    if config.get_setting('episode_info') and not support.stackCheck(['add_tvshow', 'get_newest']):
        support.tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        for it in itemlist:
            if it.infoLabels.get('title'):
                it.title = '1x01 - ' + it.infoLabels['title']
    support.check_trakt(itemlist)
    support.videolibrary(itemlist, item)
    return itemlist
def findvideos(item):
    return support.server(item)
def search(item, text):
    try:
        return peliculas(item)
    except Exception:
        return []
'''
deve('canale buono', CANALE_BUONO, 'canale',
     assenti=('F01', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F10', 'F12', 'F13'))

# senza controllo episode_info
deve('episode_info mancante', CANALE_BUONO.replace(
    "if config.get_setting('episode_info') and not support.stackCheck(['add_tvshow', 'get_newest']):", 'if True:'),
    'canale', presenti=('F05',))
# senza stackCheck
deve('stackCheck mancante', CANALE_BUONO.replace(" and not support.stackCheck(['add_tvshow', 'get_newest'])", ''),
     'canale', presenti=('F05',))
# successivo a cartella
deve('undefined senza contentType', CANALE_BUONO.replace(
    "    if item.contentType in ('undefined', ''):\n        item.contentType = 'movie'\n", ''),
    'canale', presenti=('F03',))
# TMDB diretto, thread, probe
deve('tmdb diretto', CANALE_BUONO + "\nU = 'https://api.themoviedb.org/3/tv/1'\n", 'canale', presenti=('F08',))
deve('thread', CANALE_BUONO + "\nimport threading\nthreading.Thread(target=print).start()\n", 'canale', presenti=('F10',))
deve('probe', CANALE_BUONO + "\ndef x(v):\n    return v.probe('a')\n", 'canale', presenti=('F13',))
deve('titolo TMDB non in etichetta', CANALE_BUONO.replace("            if it.infoLabels.get('title'):\n                it.title = '1x01 - ' + it.infoLabels['title']\n", '            pass\n'),
     'canale', presenti=('F06',))

SERVER_BUONO = '''
import threading, cloudscraper
def s():
    return cloudscraper.create_scraper(auto_refresh_on_403=False, max_concurrent_requests=16, min_request_interval=0)
def _test_video_exists_impl(u):
    try:
        r = get(u, timeout=(3, 4))
        if r.status_code in (404, 410):
            return False, 'non disponibile'
    except Exception:
        pass
    return True, ''
def test_video_exists(u):
    t = threading.Thread(target=_test_video_exists_impl, args=(u,))
    t.daemon = True
    t.start()
    t.join(8)
    return True, ''
'''
deve('server buono', SERVER_BUONO, 'server', assenti=('S01', 'S02', 'S03', 'S04'))
deve('scraper senza kwargs', SERVER_BUONO.replace(
    'cloudscraper.create_scraper(auto_refresh_on_403=False, max_concurrent_requests=16, min_request_interval=0)',
    'cloudscraper.create_scraper()'), 'server', presenti=('S01',))
deve('thread normale', SERVER_BUONO.replace('    t.daemon = True\n', ''), 'server', presenti=('S02',))
deve('verifica di rete extra', SERVER_BUONO.replace(
    "            return False, 'non disponibile'",
    "            if not get_embed_page(u):\n                return False, 'non disponibile'"), 'server', presenti=('S04',))

if fallite:
    print('\n'.join(fallite))
    sys.exit(1)
print('Prove framework: tutte superate')
