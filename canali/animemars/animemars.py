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
    action = 'findvideos'
    patron = r'''<a(?=[^>]*class="group\ block")[^>]*?href="(?P<url>[^"]+)"(?:(?!</a>).)*?<img [^>]*?src="(?P<thumb>[^"]+)"(?:(?!</a>).)*?<h3(?=[^>]*class="line\-clamp\-2\ text\-sm\ font\-semibold\ leading\-snug\ transition\ group\-hover:text\-primary")[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)\s*<'''
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
