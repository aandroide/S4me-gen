# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Tantifilm
# ------------------------------------------------------------

from core import support
from core.item import Item
from platformcode import logger
from platformcode import config


host = config.get_channel_url()
headers = [['Referer', host]]

player_iframe = r'<iframe.*?src="([^"]+)"[^>]+></iframe>\s*<\/div'

@support.menu
def mainlist(item):

    top = [('Generi', ['', 'genres'])]
    film = ['/film']
    tvshow = ['/serie-tv/']
    search = ''

    return locals()


@support.scrape
def genres(item):

    blacklist = ['Ultimi Film Aggiornati', 'Anime', 'Serie TV Altadefinizione', 'HD AltaDefinizione', 'Al Cinema', 'Serie TV', 'Miniserie', 'Programmi Tv', 'Live', 'Trailers', 'Serie TV Aggiornate', 'Aggiornamenti', 'Featured']
    patronMenu = '<li><a href="(?P<url>[^"]+)"><span></span>(?P<title>[^<]+)</a></li>'
    patron_block = '<ul class="table-list">(.*?)</ul>'
    action = 'peliculas'

    return locals()


def search(item, text):    
    item.url = "{}/?{}".format(host, support.urlencode({'story': text,'do':'search', 'subaction':'search'}))
    #item.url = host + "/?story=" + texto
    try:
        item.args = 'search'
        return peliculas(item)

    # Continua la ricerca in caso di errore
    except:
        import sys
        for line in sys.exc_info():
            logger.error("%s" % line)
        return []

@support.scrape
def peliculas(item):
    action = 'check'
    # la pagina non distingue piu film e serie nell'elenco (non c'e piu se_num): il tipo si ricava dal percorso.
    # In ricerca resta undefined (TMDB cerca in entrambi); altrove con undefined i titoli senza scheda TMDB
    # e il tasto Successivo verrebbero mostrati come cartelle
    if item.args == 'search':
        item.contentType = 'undefined'
    elif 'serie-tv' in item.url:
        item.contentType = 'tvshow'
    else:
        item.contentType = 'movie'
    if item.args == 'search':
        patron = r'<div class="film.*?<a href="(?P<url>[^"]+)" title="(?P<title>.*?) \(-?(?P<year>\d{4})[^"]+".*?<img[^s]+src="(?P<thumb>[^"]+)".*?(?:class="calitate"> <p>)(?P<quality>.*?)(?:</p>)'
    else:
        patronNext = r'<b class="nextpostslink">.*?<a href="([^"]+)">'
        if 'serie-tv' in item.url:
            patron = r'<div class="mediaWrap mediaWrapAlt"> <a href="(?P<url>[^"]+)" title="(?P<title>.*?) \(-?(?P<year>\d{4})[^"]+".*?<img[^s]+src="(?P<thumb>[^"]+)".*?(?:class="se_num">|class="calitate">\s*<p>\s*)(?P<quality>.*?)(?:</span>|\s*</p>)'
        else:
            patron = r'<div class="mediaWrap mediaWrapAlt"> <a href="(?P<url>[^"]+)" title="(?P<title>.*?) \(-?(?P<year>\d{4})[^"]+".*?<img[^s]+src="(?P<thumb>[^"]+)".*?(?:class="se_num">|class="calitate"> <p> )(?P<quality>.*?)(?:</span>| </p>)'
        patronBlock = r'<div id="main_col">(?P<block>.*?)<!-- main_col -->'

    def itemHook(item):
        # titoli senza anno sul sito escono come (-0001)
        if str(item.infoLabels.get('year', '')) in ('0001', '1'):
            item.infoLabels['year'] = ''
        return item

    return locals()

def episodios(item):
    # la pagina della serie non elenca piu gli episodi: contiene solo il lettore vidxgo, che si apre con l'id IMDb.
    # Stagioni ed episodi si leggono da TMDB (core: cache, limite di richieste e nuovi tentativi gia gestiti)
    from core import tmdb
    data = getattr(item, 'data', '') or support.match(item.url, headers=headers).data
    imdb = support.match(data, patron=r"""var\s+imdb\s*=\s*['"]tt(\d+)""").match
    if not imdb:
        imdb = support.match(data, patron=r"/uploads/[^\"' ]*?/tt(\d{6,9})\.").match
    if not imdb:
        return []
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
            itemlist.append(item.clone(action='findvideos', title=titolo, contentType='episode', contentSeason=s,
                                       contentEpisodeNumber=e, season=s, episode=e,
                                       plot=ep.get('overview') or item.plot,
                                       url='https://v.vidxgo.co/%s/%s/%s' % (imdb, s, e), server='vidxgo', data=''))
    support.check_trakt(itemlist)
    support.videolibrary(itemlist, item)
    return itemlist


def check(item):
    item.data = support.match(item.url, headers=headers).data
    check = support.match(item.data, patron=r'<div class="category-film">(.*?)</div>').match
    if 'sub' in check.lower():
        item.contentLanguage = 'Sub-ITA'
    logger.debug("CHECK : ", check)
    if 'serie' in check.lower():
        item.contentType = 'tvshow'
        return episodios(item)
    else:
        item.contentTitle = item.fulltitle
        item.contentType = 'movie'
        return findvideos(item)


def findvideos(item):
    # episodio con indirizzo vidxgo gia pronto (costruito in episodios)
    if 'vidxgo.co/' in (item.url or ''):
        return support.server(item, itemlist=[item.clone(action='play', title='vidxgo', server='vidxgo')])

    if item.server_links:
        return support.server(item, data = item.server_links)

    data = support.match(item.url).data
    itemlist = []
    # il lettore del sito e vidxgo: l'indirizzo si costruisce con l'id IMDb (o TMDB) scritto nello script
    imdb = support.match(data, patron=r"""var\s+imdb\s*=\s*['"]tt(\d+)""").match
    if not imdb:
        imdb = support.match(data, patron=r"/uploads/[^\"' ]*?/tt(\d{6,9})\.").match
    if imdb:
        chiave = imdb
    else:
        tmdb_id = support.match(data, patron=r"themoviedb\.org/(?:movie|tv)/(\d+)").match
        chiave = 'tm' + tmdb_id if tmdb_id else ''
    if chiave:
        itemlist.append(item.clone(action='play', title='vidxgo', url='https://v.vidxgo.co/' + chiave, server='vidxgo'))

    video_url = support.match(data, patron=player_iframe).match

    if (video_url == ''):
       return support.server(item, itemlist=itemlist) if itemlist else []

    itemlist += [item.clone(action="play", url=srv) for srv in support.match(video_url, patron='<li class="(?:active)?" data-link=\"([^"]+)').matches]
    itemlist = support.server(item,itemlist=itemlist)
    return itemlist
