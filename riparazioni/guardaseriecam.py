# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per 'guardaserie_live'
# By: Napster32
# ------------------------------------------------------------
# Rev: 0.0
# Update 11-06-2020
# fix:
# 1. Emissione

# possibilità di miglioramento: inserire menu per genere - lista serie tv e gestire le novità

from core import support
from core.support import info
from platformcode import logger, config

host = config.get_channel_url()
headers = [['Referer', host]]


@support.menu
def mainlist(item):
    # la voce "Per Lettera" non esiste piu sul sito (risponde 404): al suo posto popolari e generi
    tvshow = ['/serietv-streaming',
              ('Popolari', ['/serietv-popolari/', 'peliculas', '']),
              ('Generi', ['/serietv-streaming', 'genres', 'genres'])
              ]
    return locals()


@support.scrape
def genres(item):
    action = 'peliculas'
    blacklist = ['Netflix', 'In Arrivo']
    patronBlock = r'>Genere</span>(?P<block>.*?)</ul>'
    patronMenu = r'<a class="dropdown-item" href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]+)</a>'
    return locals()


@support.scrape
def peliculas(item):
    # il sito ora usa il tema con i blocchi movieItem (titolo, anno, trama negli attributi data-)
    patron = (r'<div class="movieItem"[^>]*?data-title="(?P<title>[^"]*)"[^>]*?data-year="(?P<year>\d+)"'
              r'[^>]*?data-text="(?P<plot>[^"]*)"[^>]*>.*?<a href="(?P<url>[^"]+)"[^>]*>.*?<img\s+src="\s*(?P<thumb>[^"]+?)\s*"')
    patronNext = r'<div id="nav-load"><a href="([^"]+)"'
    action = 'episodios'

    def itemHook(i):
        if i.thumbnail and i.thumbnail.startswith('/'):
            i.thumbnail = host + i.thumbnail
        return i

    return locals()


def episodios(item):
    # la pagina della serie contiene solo un selettore scritto in JavaScript (12 stagioni x 24 episodi finti):
    # stagioni ed episodi veri si leggono da TMDB con l'id IMDb, il lettore e vidxgo
    from core import tmdb
    data = support.match(item).data
    imdb = support.match(data, patron=r"var imdb = 'tt(\d+)'").match
    if not imdb:
        return []
    # core tmdb: cache, limite di richieste e nuovi tentativi sono gia gestiti
    try:
        tmdb_id = tmdb.Tmdb(external_id='tt' + imdb, external_source='imdb_id', search_type='tv').get_id()
        if not tmdb_id:
            return []
        serie = tmdb.Tmdb(id_Tmdb=tmdb_id, search_type='tv')
        stagioni = [st.get('season_number') for st in serie.get_list_episodes()]
    except Exception:
        logger.error('TMDB non raggiungibile per tt' + imdb)
        return []
    itemlist = []
    for s in stagioni:
        if not s:
            continue
        try:
            dettaglio = serie.get_season(s) or {}
        except Exception:
            continue
        for ep in dettaglio.get('episodes', []) or []:
            e = ep.get('episode_number')
            nome = ep.get('name') or ''
            titolo = '%sx%02d' % (s, e) + (' - ' + nome if nome else '')
            itemlist.append(item.clone(action='findvideos', title=titolo, contentType='episode', contentSeason=s, contentEpisode=e,
                                       season=s, episode=e, plot=ep.get('overview') or item.plot,
                                       url='https://v.vidxgo.co/%s/%s/%s' % (imdb, s, e), server='vidxgo', data=''))
    return itemlist


def search(item, text):
    support.info('search', text)
    item.contentType = 'tvshow'
    itemlist = []
    text = text.replace(' ', '+')
    item.url = host + '/index.php?story=%s&do=search&subaction=search' % (text)
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            info('search log:', line)
        return []


def findvideos(item):
    logger.debug()
    # episodio con indirizzo vidxgo gia pronto
    if 'vidxgo.co/' in (item.url or ''):
        return support.server(item, itemlist=[item.clone(action='play', title='vidxgo', server='vidxgo')])
    # film o altre pagine: l'indirizzo vidxgo si costruisce con l'id IMDb dello script
    data = support.match(item).data
    imdb = support.match(data, patron=r"var imdb = 'tt(\d+)'").match
    if imdb:
        return support.server(item, itemlist=[item.clone(action='play', title='vidxgo', url='https://v.vidxgo.co/' + imdb, server='vidxgo')])
    return support.server(item, data)
