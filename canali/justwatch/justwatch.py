# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Justwatch
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
    top = [('Titoli', ['/it', 'peliculas', '', 'movie'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'findvideos'
    patron = r'''<div[^>]*class="title\-list\-grid__item"(?:(?!<div[^>]*class="title\-list\-grid__item").)*?<a [^>]*?href="(?P<url>[^"]*?/(?P<type>serie\-tv|film)/[^"]*)"(?:(?!<div[^>]*class="title\-list\-grid__item").)*?<img (?=[^>]*?alt="(?P<title>[^"]+)")[^>]*?src="(?P<thumb>[^"]+)"'''
    patronNext = r'''<a [^>]*?rel="next"[^>]*?href="([^"]+)"|<a [^>]*?href="([^"]+)"[^>]*?rel="next"'''
    #debug = True  # apre regex101 con pagina e regex
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
