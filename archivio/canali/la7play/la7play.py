# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per La7play
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
    top = [('Dirette', ['/dirette/la7', 'peliculas', '', 'tvshow']),
           ('Programmi', ['/programmi', 'peliculas', '', 'tvshow']),
           ('Film', ['/film', 'peliculas', '', 'movie']),
           ('Documentari', ['/documentari', 'peliculas', '', 'tvshow'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'findvideos'
    patron = r'''<div(?=[^>]*class="(?:[^"]*\s)?snap\-start(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?shrink\-0(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?cursor\-pointer(?:\s[^"]*)?")(?:(?!<div(?=[^>]*class="(?:[^"]*\s)?snap\-start(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?shrink\-0(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?cursor\-pointer(?:\s[^"]*)?")).)*?<a [^>]*?href="(?P<url>[^"]+)"(?:(?!<div(?=[^>]*class="(?:[^"]*\s)?snap\-start(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?shrink\-0(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?cursor\-pointer(?:\s[^"]*)?")).)*?<img (?=[^>]*?alt="(?P<title>[^"]+)")[^>]*?src="(?P<thumb>[^"]+)"'''
    # patronNext: pagina successiva non trovata
    #debug = True  # apre regex101 con pagina e regex
    return locals()


def search(item, text):
    # TODO: ricerca non rilevata automaticamente, impostare l'url della ricerca del sito
    support.info(text)
    item.url = host + '/?s=' + text.replace(' ', '+')
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
    # la pagina dell'episodio contiene l'iframe del player; il video si legge dalle risposte del player
    url = item.url
    data = httptools.downloadpage(url, headers=headers).data
    embed = support.match(data, patron=r'''<iframe[^>]*?src="((?:https?:)?//[^"]+)"''').match
    if not embed:
        return support.server(item, data=data, headers=headers)
    embed = embed.replace('&amp;', '&')
    if embed.startswith('//'):
        embed = 'https:' + embed
    origine = re.match(r'https?://[^/]+', embed).group(0)
    ref = [['Referer', host + '/']]
    testi = []
    testi.append(httptools.downloadpage(embed, headers=ref).data)
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
                                   url=u + '|Referer=' + origine + '/'))
    if not itemlist:
        return support.server(item, data=embed, headers=ref)
    return support.server(item, itemlist=itemlist)
