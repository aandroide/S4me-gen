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
    patron = r'''<a(?=[^>]*class="group\ block")[^>]*?href="(?P<url>[^"]+)"(?:(?!</a>).)*?<img [^>]*?src="(?P<thumb>[^"]+)"(?:(?!</a>).)*?<h3(?=[^>]*class="line\-clamp\-2\ text\-sm\ font\-semibold\ leading\-snug\ transition\ group\-hover:text\-primary")[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)(?:\s*\((?P<lang>ITA|SUB[\ \-]?ITA|Sub[\ \-]?Ita|CR)\))?\s*<'''
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
    # il sito ha una sola stagione per titolo: S4Me mostra 1x01 e cerca i titoli degli episodi su TMDB
    if not item.season:
        item.season = '1'
    data = httptools.downloadpage(item.url, headers=headers).data
    # l'anno sta solo nella pagina della serie: titolo e anno servono a TMDB per trovare la serie giusta
    anno = support.match(data, patron=r'years=(\d{4})').match or support.match(data, patron=r'Uscita</span>\s*<span[^>]*>[^<]*?(\d{4})').match
    if anno and not item.infoLabels.get('tmdb_id'):
        item.infoLabels['year'] = anno
        item.infoLabels['tvshowtitle'] = item.contentSerieName or item.fulltitle
        try:
            tmdb.set_infoLabels_item(item, seekTmdb=True)
        except Exception:
            pass
    patron = r'''<a href="(?P<url>/watch/[^"]+/ep-(?P<episode>\d+))"[^>]*class="ep-tile"'''

    def itemHook(it):
        # senza season sull'episodio S4Me salta la ricerca dei titoli su TMDB
        it.season = item.season
        return it

    def itemlistHook(itemlist):
        # S4Me scrive il titolo dell'episodio solo nelle info, non nell'etichetta: lo aggiungo accanto a 1x01
        if config.get_setting('episode_info') and itemlist and itemlist[0].season:
            try:
                tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
            except Exception:
                pass
            for it in itemlist:
                nome = it.infoLabels.get('title') if it.infoLabels else ''
                if nome and nome != it.fulltitle and nome not in it.title:
                    it.title += support.typo(nome, '-- bold')
        return itemlist
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


def decodifica(testo, chiave):
    # il player nasconde gli indirizzi: base64 e XOR con il token dell'embed
    try:
        r = base64.b64decode(testo)
        return ''.join(chr(c ^ ord(chiave[n % len(chiave)])) for n, c in enumerate(r))
    except Exception:
        return ''


def findvideos(item):
    support.info(item)
    itemlist = []
    # la pagina dell'episodio e /stream/<titolo>/ep-N: contiene l'iframe del player (play.marscdn.org)
    url = item.url.replace('/watch/', '/stream/', 1)
    data = httptools.downloadpage(url, headers=headers).data
    embed = support.match(data, patron=r'<iframe(?=[^>]*id="watch-iframe")[^>]*?src="([^"]+)"').match
    if not embed:
        return support.server(item, data=data, headers=headers)
    embed = embed.replace('&amp;', '&')
    if embed.startswith('//'):
        embed = 'https:' + embed
    origine = re.match(r'https?://[^/]+', embed).group(0)
    # il player chiede /embed/<id>/playlist?token=..&expires=.. e riceve {"d": indirizzo cifrato, ...}
    base_e, _, q = embed.partition('?')
    chiave = support.match(q, patron=r'token=([^&]+)').match
    testo = str(httptools.downloadpage(base_e + '/playlist' + ('?' + q if q else ''), headers=[['Referer', embed]]).data)
    video = ''
    try:
        d = json.loads(testo).get('d')
        if d and chiave:
            video = decodifica(d, chiave)
    except Exception:
        pass
    if not video.startswith('http'):
        m = re.search(r'https?://[^"\'\s<>\\]+?\.(?:mp4|m3u8)[^"\'\s<>\\]*', testo.replace('\\/', '/'))
        video = m.group(0).replace('&amp;', '&') if m else ''
    if video.startswith('http'):
        itemlist.append(item.clone(action='play', title=support.config.get_localized_string(30137), server='directo',
                                   url=video + '|Referer=' + origine + '/'))
        return support.server(item, itemlist=itemlist)
    return support.server(item, data=embed, headers=[['Referer', host + '/']])
