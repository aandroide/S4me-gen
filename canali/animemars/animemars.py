# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Animemars
# Generato da s4me_gen.py: controllare le regex e provare ogni voce del menu
# ------------------------------------------------------------

import json
import re
import base64
import difflib
from urllib.parse import urlencode

from core import support, httptools, tmdb
from core.item import Item, InfoLabels
from platformcode import config, logger, platformtools

host = support.config.get_channel_url().rstrip('/')
headers = [['Referer', host + '/']]


@support.menu
def mainlist(item):
    top = [('Archivio', ['/az-list', 'peliculas', '', 'tvshow']),
           ('In corso', ['/ongoing', 'peliculas', '', 'tvshow']),
           ('Nuove aggiunte', ['/newest', 'peliculas', '', 'tvshow']),
           ('Prossime uscite', ['/upcoming', 'peliculas', '', 'tvshow'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'episodios'
    anime = True
    patron = r'''<a(?=[^>]*class="group\ block")[^>]*?href="(?P<url>[^"]+)"(?:(?!</a>).)*?<img [^>]*?src="(?P<thumb>[^"]+)"(?:(?!</a>).)*?<h3(?=[^>]*class="line\-clamp\-2\ text\-sm\ font\-semibold\ leading\-snug\ transition\ group\-hover:text\-primary")[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'''
    #debug = True  # apre regex101 con pagina e regex

    def itemHook(item):
        # le schede delle novita puntano all'episodio: la lista episodi sta nella pagina /stream/<titolo>
        item.url = re.sub(r'/(?:watch|stream)/([^/]+)(?:/ep-\d+)?/?$', r'/stream/\1', item.url)
        return item
    return locals()


@support.scrape
def episodios(item):
    support.info(item)
    anime = True
    action = 'findvideos'
    patron = r'''<a href="(?P<url>/watch/[^"]+/ep-(?P<episode>\d+))"[^>]*class="ep-tile"'''
    return locals()


def search(item, text):
    support.info(text)
    item.url = host + '/filter?key=%s' % text.replace(' ', '+')
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []


def findvideos(item):
    support.info(item)
    itemlist = []
    # la pagina dell'episodio e /stream/<titolo>/ep-N: il player e un iframe (play.marscdn.org) presente nell'html
    url = item.url.replace('/watch/', '/stream/')
    data = httptools.downloadpage(url, headers=headers).data
    embed = support.match(data, patron=r'<iframe[^>]*id="watch-iframe"[^>]*src="([^"]+)"').match
    if not embed:
        return support.server(item, data=data, headers=headers)
    embed = embed.replace('&amp;', '&')
    if embed.startswith('//'):
        embed = 'https:' + embed
    ref = [['Referer', host + '/']]
    # il player legge l'elenco dei file da /embed/<id>/playlist?<stessi parametri>
    playlist = re.sub(r'/embed/(\d+)\?', r'/embed/\1/playlist?', embed)
    testi = [httptools.downloadpage(playlist, headers=ref).data,
             httptools.downloadpage(embed, headers=ref).data]
    visti = []
    for t in testi:
        t = str(t).replace('\\/', '/')
        for u in re.findall(r'https?://[^"\'\s<>\\]+?\.(?:mp4|m3u8)[^"\'\s<>\\]*', t):
            u = u.replace('&amp;', '&')
            if u not in visti:
                visti.append(u)
        if visti:
            break
    for u in visti:
        itemlist.append(item.clone(action='play', title=support.config.get_localized_string(30137), server='directo',
                                   url=u + '|Referer=https://play.marscdn.org/'))
    if not itemlist:
        itemlist = support.server(item, data=embed, headers=ref)
        return itemlist
    return support.server(item, itemlist=itemlist)
