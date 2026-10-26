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
    top = [('Archivio', ['/az-list', 'peliculas', '', 'movie']),
           ('In corso', ['/ongoing', 'peliculas', '', 'movie']),
           ('Generi', ['/genres', 'peliculas', '', 'movie']),
           ('Filtro', ['/filter', 'peliculas', '', 'movie']),
           ('Calendario', ['/calendar', 'peliculas', '', 'movie']),
           ('Classifiche', ['/toplist', 'peliculas', '', 'movie']),
           ('Prossime uscite', ['/upcoming', 'peliculas', '', 'movie']),
           ('Nuove aggiunte', ['/newest', 'peliculas', '', 'movie']),
           ('News', ['/news', 'peliculas', '', 'movie']),
           ('Random', ['/random', 'peliculas', '', 'movie']),
           ('Feed RSS', ['/rss', 'peliculas', '', 'movie'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'findvideos'
    patron = r'''<a[^>]*class="group\ block"[^>]*?href="(?P<url>[^"]+)"(?:(?!</a>).)*?<img [^>]*?src="(?P<thumb>[^"]+)"(?:(?!</a>).)*?<h3[^>]*class="line\-clamp\-2\ text\-sm\ font\-semibold\ leading\-snug\ transition\ group\-hover:text\-primary"[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'''
    patronNext = r'''<a [^>]*?href="([^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*Prossime\ uscite'''
    #debug = True  # apre regex101 con pagina e regex
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
    return support.server(item, headers=headers)
