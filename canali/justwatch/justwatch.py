# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Justwatch
# Generato da s4me_gen.py: controllare le regex e provare ogni voce del menu
# ------------------------------------------------------------

import json
from urllib.parse import urlencode

from core import support, httptools
from core.item import Item
from platformcode import config, logger

host = support.config.get_channel_url().rstrip('/')
headers = [['Referer', host + '/']]


@support.menu
def mainlist(item):
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'episodios'
    patron = r'''<div[^>]*class="title\-list\-grid__item".*?<a [^>]*?href="(?P<url>[^"]+)".*?<img [^>]*?src="(?P<thumb>[^"]+)".*?<img [^>]*?alt="(?P<title>[^"]+)"'''
    patronNext = r'''<a [^>]*?rel="next"[^>]*?href="([^"]+)"|<a [^>]*?href="([^"]+)"[^>]*?rel="next"'''
    #debug = True  # apre regex101 con pagina e regex
    return locals()


@support.scrape
def episodios(item):
    support.info(item)
    action = 'findvideos'
    patron = r'''<a[^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'''
    #debug = True
    return locals()


def search(item, text):
    support.info(text)
    item.url = host + '/it/cerca?q=%s' % text.replace(' ', '+')
    try:
        return peliculas(item)
    except:
        import sys
        for line in sys.exc_info():
            logger.error('%s' % line)
        return []


def findvideos(item):
    support.info(item)
    return support.server(item, headers=headers)
