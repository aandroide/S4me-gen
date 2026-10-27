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
    tvshow = ['/serietv-streaming',
              ('Per Lettera', ['/serietv-streaming/A', 'list', 'Serie-Tv per Lettera'])
              ]
    return locals()


@support.scrape
def list(item):
    patronMenu = r'<a title="(?P<title>[^"]+)" href="(?P<url>[^"]+)'
    action = 'peliculas'
    return locals()


@support.scrape
def peliculas(item):
    # debug = True
    patron = r'<div class="mlnh-thumb"><a href="(?P<url>[^"]+)[^>]+title="(?P<title>[^"]+).*?<img src="(?P<thumb>[^"]+).*?hdn">[^<]*(?P<year>[0-9]{4})'
    patronNext = 'pagenavi.*?<a href="([^"]+)">\d+'
    action = 'episodios'
    return locals()


def episodios(item):
    # la pagina della serie contiene solo un selettore scritto in JavaScript (12 stagioni x 24 episodi finti):
    # stagioni ed episodi veri si leggono da TMDB con l'id IMDb, il lettore e vidxgo
    import json
    from core import httptools
    data = support.match(item).data
    imdb = support.match(data, patron=r"var imdb = 'tt(\d+)'").match
    if not imdb:
        return []
    api = 'https://api.themoviedb.org/3'
    key = 'a1ab8b8669da03637a4b98fa39c39228'
    try:
        trovato = json.loads(httptools.downloadpage('%s/find/tt%s?api_key=%s&external_source=imdb_id&language=it' % (api, imdb, key)).data or '{}')
        tmdb_id = trovato['tv_results'][0]['id']
        serie = json.loads(httptools.downloadpage('%s/tv/%s?api_key=%s&language=it' % (api, tmdb_id, key)).data or '{}')
    except Exception:
        logger.error('TMDB non raggiungibile per tt' + imdb)
        return []
    itemlist = []
    for stagione in serie.get('seasons', []):
        s = stagione.get('season_number')
        if not s:
            continue
        try:
            dettaglio = json.loads(httptools.downloadpage('%s/tv/%s/season/%s?api_key=%s&language=it' % (api, tmdb_id, s, key)).data or '{}')
        except Exception:
            continue
        for ep in dettaglio.get('episodes', []):
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
