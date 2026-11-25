# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Dinostreaming
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
    top = [('Informativa sugli Affiliati', ['/affiliate/', 'peliculas', '', 'movie'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'findvideos'
    patron = r'''<a [^>]*?href="(?P<url>[^"]+)"[^>]*>.*?<img [^>]*?src="(?P<thumb>[^"]+)".*?(?P<title>[^<]+)<'''
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
    return support.server(item, headers=headers)
