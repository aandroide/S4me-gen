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
           ('Generi', ['/genres', 'peliculas', '', 'tvshow']),
           ('Filtro', ['/filter', 'peliculas', '', 'tvshow']),
           ('Calendario', ['/calendar', 'peliculas', '', 'tvshow']),
           ('Classifiche', ['/toplist', 'peliculas', '', 'tvshow']),
           ('Prossime uscite', ['/upcoming', 'peliculas', '', 'tvshow']),
           ('Nuove aggiunte', ['/newest', 'peliculas', '', 'tvshow']),
           ('News', ['/news', 'peliculas', '', 'tvshow']),
           ('Random', ['/random', 'peliculas', '', 'tvshow']),
           ('Feed RSS', ['/rss', 'peliculas', '', 'tvshow'])]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info(item)
    action = 'episodios'
    patron = r'''<a(?=[^>]*class="(?:[^"]*\s)?group(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?block(?:\s[^"]*)?")[^>]*?href="(?P<url>[^"]+)"(?:(?!</a>).)*?<img [^>]*?src="(?P<thumb>[^"]+)"(?:(?!</a>).)*?<h3(?=[^>]*class="(?:[^"]*\s)?line\-clamp\-2(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?font\-semibold(?:\s[^"]*)?")(?=[^>]*class="(?:[^"]*\s)?group\-hover:text\-primary(?:\s[^"]*)?")[^>]*>\s*(?:<[^>]+>\s*)*(?P<title>[^<]+?)(?:\s*\((?P<lang>ITA|SUB[\ \-]?ITA|Sub[\ \-]?Ita)\))?\s*<'''
    # patronNext: pagina successiva non trovata
    #debug = True  # apre regex101 con pagina e regex

    def itemHook(item):
        # la scheda puo puntare a un episodio: la lista episodi sta nella pagina del titolo
        item.url = re.sub(r'''/watch/''', r'''/stream/''', item.url)
        item.url = re.sub(r'''/ep\-\d+/?$''', r'''''', item.url)
        return item
    return locals()


@support.scrape
def episodios(item):
    support.info(item)
    action = 'findvideos'
    # titolo e anno servono a TMDB: se la lista non ha l'anno lo cerco nella pagina della serie
    if not item.infoLabels.get('year'):
        anno = support.match(item.url, patron=r'(?:years=|[Aa]nno|[Uu]scita|[Yy]ear|[Rr]elease)[^<]{0,60}?((?:19|20)\d{2})').match
        if anno:
            item.infoLabels['year'] = anno
    patron = r'''<a(?=[^>]*class="(?:[^"]*\s)?ep\-tile(?:\s[^"]*)?")[^>]*?href="(?P<url>[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?P<episode>\d+)\s*<'''
    if '(?P<episode>' in patron and '(?P<season>' not in patron and not item.season:
        # nessuna stagione nel sito: una sola, cosi S4Me mostra 1x01 e cerca i titoli degli episodi su TMDB
        item.season = '1'
    #debug = True

    def itemHook(it):
        # senza season sull'episodio S4Me salta la ricerca dei titoli su TMDB
        if item.season:
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



def findvideos(item):
    support.info(item)
    itemlist = []
    # la pagina dell'episodio contiene l'iframe del player; il video si legge dalle risposte del player
    url = item.url
    url = url.replace('/watch/', '/stream/', 1)
    data = httptools.downloadpage(url, headers=headers).data
    embed = support.match(data, patron=r'''<iframe(?=[^>]*id="watch\-iframe")[^>]*?(?:data-)?src="([^"]+)"''').match
    if not embed:
        return support.server(item, data=data, headers=headers)
    embed = embed.replace('&amp;', '&')
    if embed.startswith('//'):
        embed = 'https:' + embed
    origine = re.match(r'https?://[^/]+', embed).group(0)
    ref = [['Referer', host + '/']]
    testi = []
    base_e, _, q = embed.partition('?')
    testi.append(httptools.downloadpage(base_e + '/playlist' + ('?' + q if q else ''), headers=ref).data)
    try:
        r = base64.b64decode(json.loads(str(testi[-1])).get('d'))
        for chiave in re.findall(r'(?:^|[?&])[^=&]+=([^&]+)', q):
            t = ''.join(chr(c ^ ord(chiave[n % len(chiave)])) for n, c in enumerate(r))
            if t.startswith('http'):
                testi.insert(0, t)
                break
    except Exception:
        pass
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
