# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per altadefinizione01
# Il sito alterna due player: vidxgo e vixsrc. Il canale legge la
# pagina, riconosce quale dei due e' presente e usa il metodo giusto
# per episodi e video. Se non riconosce nulla ripiega su vixsrc.
# Formato URL:
#   vixsrc film    https://vixsrc.to/movie/<imdb>?lang=it
#   vixsrc episodio https://vixsrc.to/tv/<imdb>/<s>/<e>?lang=it
#   vidxgo film    https://v.vidxgo.co/<token>
#   vidxgo episodio https://v.vidxgo.co/<token>/<s>/<e>
# dove <token> e' l'imdb senza "tt".
# ------------------------------------------------------------

import html as _html
import re

from core import scrapertools, httptools, support
from core.item import Item
from platformcode import config, logger

host = config.get_channel_url()
headers = [['Referer', host]]

VIX_BASE = 'https://vixsrc.to'
VDX_BASE = 'https://v.vidxgo.co'


_RE_VDX = re.compile(r'vidxgo\.co/([A-Za-z0-9]+)', re.I)
_RE_VIX = re.compile(r'vixsrc\.to/(?:movie|tv)/(tt\d+)', re.I)
_RE_VDX_URL = re.compile(r'vidxgo\.co/([A-Za-z0-9]+)(?:/(\d+)/(\d+))?', re.I)
_RE_VIX_URL = re.compile(r'vixsrc\.to/(movie|tv)/([A-Za-z0-9]+)(?:/(\d+)/(\d+))?', re.I)
_RE_TMDB = re.compile(r'themoviedb\.org/(?:movie|tv)/(\d+)', re.I)


@support.menu
def mainlist(item):
    menu = [
        ('Tutti', ['/lastnews/', 'peliculas', '', 'undefined']),
        ('Al Cinema {submenu}', ['/cinema/', 'peliculas', '', 'undefined']),
        ('Ultimi Aggiornati-Aggiunti {submenu}', ['', 'peliculas', 'update']),
        ('Generi {submenu}', ['', 'genres', 'genres', 'undefined']),
        ('Lettera {submenu}', ['/catalog/a', 'genres', 'orderalf', 'undefined']),
        ('Anni {submenu}', ['', 'genres', 'years', 'undefined']),
        ('Sub-ITA {submenu}', ['/sub-ita/', 'peliculas', '', 'undefined']),
        ('Serie TV', ['/serie-tv/', 'peliculas', '', 'tvshow']),
    ]
    search = ''
    return locals()


@support.scrape
def peliculas(item):
    support.info('peliculas', item)
    action = "check"

    # il tasto Successivo e' un clone di item: con 'undefined' Kodi lo mostra
    # come cartella. Il tipo vero di ogni titolo lo da typeContentDict.
    if item.contentType in ('undefined', ''):
        item.contentType = 'movie'

    # tipo dal sito: serve ai titoli che TMDB non trova (altrimenti
    # restano 'undefined' e Kodi li mostra come cartelle)
    typeContentDict = {'movie': ['<div class="trdublaj">'],
                       'tvshow': ['<span class="se_num">']}

    if item.text:
        url = host + "/?do=search&subaction=search&titleonly=3&story=" + item.text
        data = httptools.downloadpage(
            url,
            post={'story': item.text, 'do': 'search', 'subaction': 'search'}
        ).data
        patron = r'<div class="cover boxcaption"> +<h2>\s*<a href="(?P<url>[^"]+)">(?P<title>[^<]+).*?src="(?P<thumb>[^"]+).*?(?P<type><div class="trdublaj">|<span class="se_num">)(?P<quality>[^<]+).*?<span class="ml-label">(?P<year>[0-9]+).*?<span class="ml-label">(?P<duration>[^<]+).*?<p>(?P<plot>[^<]+)'

    elif item.args == "search":
        patronBlock = r'</script> <div class="boxgrid caption">(?P<block>.*)<div id="right_bar">'
        patron = (
            r'<div class="cover boxcaption"> +<h2>\s*<a href="(?P<url>[^"]+)">(?P<title>[^<]+).*?'
            r'src="(?P<thumb>[^"]+).*?'
            r'(?P<type><div class="trdublaj">|<span class="se_num">)(?P<quality>[^<]+).*?'
            r'<span class="ml-label">(?P<year>[0-9]+).*?'
            r'<span class="ml-label">(?P<duration>[^<]+).*?'
            r'<p>(?P<plot>[^<]+)'
        )

    elif item.args == 'update':
        patronBlock = r'<div class="widget-title">Ultimi Film Aggiunti/Aggiornati</div>(?P<block>.*?)<div id="alt_menu">'
        patron = (
            r'<li> <a href="(?P<url>https?://[^"]+)" class="ml-mask">(?P<title>[^<]+)</a>.*?'
            r'<div class="ml-item-body" style="background-image:url\((?P<thumb>[^\)]+)\);">.*?'
            r'<li> <span class="ml-imdb"><b>(?P<rating>[^<]+)</b>.*?'
            r'<li><span class="ml-label">(?P<year>\d{4})</span></li>.*?'
            r'<li><span class="ml-label">(?P<duration>[^<]+)</span></li>.*?'
            r'<p class="ml-cat">(?P<genre>.*?)</p>.*?'
            r'<p>(?P<plot>[^<]+)</p>'
        )
        patronNext = ''

    elif item.args == 'orderalf':
        patron = (
            r'<tr class="mlnew">\s*<td class="mlnh-1">\d+</td>\s*'
            r'<td class="mlnh-thumb"><a href="(?P<url>[^"]+)"[^>]*>.*?data-src="(?P<thumb>[^"]+)".*?'
            r'<td class="mlnh-2"><h2>\s*<a[^>]*>(?P<title>[^<]+)</a>.*?'
            r'<td class="mlnh-3">.*?(?P<year>\d{4}).*?</td>.*?'
            r'<td class="mlnh-4">(?P<quality>[^<]*)</td>.*?'
            r'<td class="mlnh-5">(?P<genre>.*?)</td>'
        )
        patronNext = r'<div[^>]*class="[^"]*page[^"]*"[^>]*>.*?<a href="([^"]+)"[^>]*>(?:Next|Avanti|\d+|>)</a>'

    else:
        patronBlock = r'<div class="cover_kapsul ml-mask">(?P<block>.*)<div class="page_nav">'
        patron = (
            r'<div class="cover boxcaption"> +<h2>\s*<a href="(?P<url>[^"]+)">(?P<title>[^<]+).*?'
            r'src="(?P<thumb>[^"]+).*?'
            r'(?P<type><div class="trdublaj">|<span class="se_num">)(?P<quality>[^<]+).*?'
            r'<span class="ml-label">(?P<year>[0-9]+).*?'
            r'<span class="ml-label">(?P<duration>[^<]+).*?'
            r'<p>(?P<plot>[^<]+)'
        )
        patronNext = r'<span>\d</span> <a href="([^"]+)">'

    return locals()


def search(item, text):
    support.info(item, text)
    item.text = text
    try:
        return peliculas(item)
    except:
        import sys
        from core.support import info
        for line in sys.exc_info():
            info("%s" % line)
    return []


@support.scrape
def genres(item):
    support.info('genres', item)
    action = "peliculas"
    blacklist = ['Altadefinizione01']

    if item.args == 'genres':
        patronBlock = r'<ul class="kategori_list">(?P<block>.*?)<div class="tab-pane fade" id="wtab2">'
        patronMenu = '<li><a href="(?P<url>[^"]+)">(?P<title>.*?)</a>'
    elif item.args == 'years':
        patronBlock = r'<ul class="anno_list">(?P<block>.*?)</li> </ul> </div>'
        patronMenu = '<li><a href="(?P<url>[^"]+)">(?P<title>.*?)</a>'
    elif item.args == 'orderalf':
        patronBlock = r'<div class="movies-letter">(?P<block>.*?)<div class="clearfix">'
        patronMenu = '<a title=.*?href="(?P<url>[^"]+)"><span>(?P<title>.*?)</span>'

    return locals()


# ------------------------- rilevamento player -------------------------

def _imdb_from_data(data):
    for patron in (r'<p id="imdb">(tt\d+)</p>',
                   r"var imdb = '(tt\d+)'",
                   r'itemprop="imdb"[^>]*content="(tt\d+)"'):
        m = support.match(data, patron=patron).match
        if m:
            return m
    return None


def _attr_tag(tag, nome):
    """Valore di un attributo di un tag HTML (o '' se manca); src non si confonde con data-src."""
    m = re.search(r'(?<![\w-])' + re.escape(nome) + r'\s*=\s*["\']([^"\']*)["\']', tag or '', re.I)
    return m.group(1).strip() if m else ''


def _corpo(data):
    """La pagina del titolo senza la barra laterale (id=right_bar), che contiene le
    stagioni di altri titoli."""
    d = data or ''
    i = d.find('id="right_bar"')
    if i < 0:
        i = d.find("id='right_bar'")
    return d[:i] if i > 0 else d


def _episodi_sito(data):
    """Episodi elencati dalla pagina stessa (tab delle stagioni, struttura classica del sito
    e di StreamFlix): pannelli id="season-N" con <li><a allowfullscreen data-link data-num
    data-title> e i mirror (a[data-link], senza 4K). Ritorna una lista di dict con
    s, e, title, plot e links; vuota se la pagina non ha questa struttura."""
    out = []
    corpo = _corpo(data)
    for pezzo in re.split(r'(?=<div\b[^>]*\bid=["\']season-\d+["\'])', corpo):
        ms = re.match(r'<div\b[^>]*\bid=["\']season-(\d+)["\']', pezzo, re.I)
        if not ms:
            continue
        stagione = int(ms.group(1))
        for li in re.findall(r'<li\b[^>]*>(.*?)</li>', pezzo, re.S | re.I):
            principale = None
            for a in re.finditer(r'<a\b([^>]*)>(.*?)</a>', li, re.S | re.I):
                if 'allowfullscreen' in a.group(1) and _attr_tag(a.group(1), 'data-link'):
                    principale = a
                    break
            if not principale:
                continue
            num = _attr_tag(principale.group(1), 'data-num')
            mn = re.search(r'(\d+)\s*$', num.split('x')[-1]) if num else None
            if not mn:
                mn = re.search(r'\d+', re.sub(r'<[^>]+>', '', principale.group(2)))
            if not mn:
                continue
            episodio = int(mn.group(1) if mn.lastindex else mn.group(0))

            titolo, trama = '', ''
            dt = _html.unescape(_attr_tag(principale.group(1), 'data-title')).strip()
            if ':' in dt:
                titolo, trama = [x.strip() for x in dt.split(':', 1)]
            else:
                titolo = dt

            links = []
            for a in re.finditer(r'<a\b([^>]*)>(.*?)</a>', li, re.S | re.I):
                link = _attr_tag(a.group(1), 'data-link')
                if not link:
                    continue
                if '4k' in re.sub(r'<[^>]+>', '', a.group(2)).lower():
                    continue
                if link.startswith('//'):
                    link = 'https:' + link
                if link not in links:
                    links.append(link)
            if links:
                out.append({'s': stagione, 'e': episodio, 'title': titolo, 'plot': trama, 'links': links})
    return out


def _tmdb_from_data(data, tipo=None):
    """Id TMDB della pagina, dalla riga fonteTrama (themoviedb.org/movie|tv/<id>).
    Con tipo='tv' si preferisce il link delle serie."""
    if tipo == 'tv':
        m = re.search(r'themoviedb\.org/tv/(\d+)', data or '', re.I)
        if m:
            return m.group(1)
    m = _RE_TMDB.search(data or '')
    return m.group(1) if m else None


def _detect_player(data):
    """Guarda quale player e' presente nella pagina. Prima cerca l'URL
    scritto per intero; se manca (l'iframe e' creato da JavaScript, come
    'https://v.vidxgo.co/' + key) usa il solo nome del player. Se ce ne
    sono due vince quello che compare per primo.
    Ritorna (nome, riferimento, incerto): incerto e' True quando non ne
    compare nessuno oppure compaiono entrambi."""
    page = (data or '').replace('\\/', '/')
    mv = _RE_VDX.search(page)
    mx = _RE_VIX.search(page)
    if mv or mx:
        incerto = bool(mv and mx)
        if mv and (not mx or mv.start() < mx.start()):
            return 'vidxgo', mv.group(1), incerto
        return 'vixsrc', mx.group(1), incerto

    nv = re.search(r'vidxgo', page, re.I)
    nx = re.search(r'vixsrc', page, re.I)
    if nv or nx:
        incerto = bool(nv and nx)
        if nv and (not nx or nv.start() < nx.start()):
            return 'vidxgo', None, incerto
        return 'vixsrc', None, incerto
    return None, None, True


def _player_info(data, tipo='movie'):
    """Raccoglie player, imdb, id TMDB e token vidxgo (imdb senza 'tt',
    oppure 'tm' + id TMDB se manca l'imdb, come fa il sito)."""
    imdb_id = _imdb_from_data(data)
    tmdb_id = _tmdb_from_data(data, tipo)
    player, ref, incerto = _detect_player(data)
    token = None

    if player == 'vidxgo':
        token = ref
        if not imdb_id and ref and ref.isdigit():
            imdb_id = 'tt' + ref
    elif player == 'vixsrc':
        imdb_id = imdb_id or ref

    # Pagina non chiara: si offrono comunque entrambi i player (_url_player)
    if not player:
        player = 'vixsrc'

    if not token:
        if imdb_id:
            token = imdb_id[2:]
        elif tmdb_id:
            token = 'tm' + tmdb_id

    support.info('Player: %s, imdb: %s, tmdb: %s, token: %s' % (player, imdb_id, tmdb_id, token))
    return {'player': player, 'imdb': imdb_id, 'tmdb': tmdb_id, 'token': token}


def _vixsrc_url(ident, season=None, episode=None):
    """ident puo' essere un imdb (tt...) o un id TMDB."""
    if season and episode:
        return '%s/tv/%s/%s/%s?lang=it' % (VIX_BASE, ident, season, episode)
    return '%s/movie/%s?lang=it' % (VIX_BASE, ident)


def _vidxgo_url(token, season=None, episode=None):
    if season and episode:
        return '%s/%s/%s/%s' % (VDX_BASE, token, season, episode)
    return '%s/%s' % (VDX_BASE, token)


def _stagioni_tmdb(tmdb_id, imdb_id=None):
    """Coppie (stagione, episodio) dalla struttura delle stagioni di TMDB, con gli
    strumenti del core (Tmdb.get_list_episodes: cache, limite e retry gia' gestiti).
    Gli episodi che il player non ha li scarta il test_video_exists del server."""
    from core import tmdb
    try:
        if not tmdb_id and imdb_id:
            tmdb_id = tmdb.Tmdb(external_id=imdb_id, external_source='imdb_id',
                                search_type='tv').get_id()
        if not tmdb_id:
            return [], None
        stagioni = tmdb.Tmdb(id_Tmdb=tmdb_id, search_type='tv').get_list_episodes()
    except Exception as e:
        logger.error('TMDB stagioni: %s' % e)
        return [], tmdb_id
    coppie = []
    for st in stagioni:
        n = st.get('season_number')
        if not n:  # salta gli speciali (stagione 0)
            continue
        inizio = st.get('start_from') or 1
        for e in range(inizio, inizio + int(st.get('episode_count') or 0)):
            coppie.append((int(n), int(e)))
    return coppie, tmdb_id


def _episodio(item, season, episode, url, titolo=None):
    new_item = item.clone(action='findvideos', contentType='episode', data='',
                          season=season, episode=episode,
                          contentSeason=season, contentEpisodeNumber=episode,
                          contentSerieName=item.fulltitle if item.fulltitle else item.title,
                          thumbnail=item.thumbnail, contentThumbnail=item.thumbnail,
                          fanart=item.fanart, contentFanart=item.fanart, url=url,
                          title=f"{season}x{episode:02d}" + (f" - {titolo}" if titolo else ''))
    return new_item


def episodios(item):
    support.info('episodios', item)

    data = item.data if hasattr(item, 'data') and item.data else httptools.downloadpage(item.url).data
    itemlist = []

    # 1) episodi elencati dalla pagina del sito (titoli, trame e mirror reali)
    for ep in _episodi_sito(data):
        new_item = _episodio(item, ep['s'], ep['e'], item.url, ep['title'])
        if ep['plot']:
            new_item.plot = ep['plot']
        new_item.links_sito = ep['links']
        itemlist.append(new_item)

    # 2) altrimenti le stagioni di TMDB (core) e l'URL del player
    # (anche se la pagina elenca un solo episodio: la lista del sito e' incompleta)
    if len(itemlist) <= 1:
        sito = itemlist
        itemlist = []
        info = _player_info(data, 'tv')
        imdb_id, token, player = info['imdb'], info['token'], info['player']
        if not imdb_id and not token:
            support.info('IMDB ID non trovato per la serie!')
            return sito
        # l'id della pagina e' quello giusto: quello dell'item puo' essere di un film
        # omonimo (la ricerca TMDB dell'elenco parte come film)
        tmdb_id = info['tmdb']
        if not tmdb_id and item.infoLabels.get('mediatype') in ('tvshow', 'season', 'episode'):
            tmdb_id = item.infoLabels.get('tmdb_id')
        coppie, tmdb_id = _stagioni_tmdb(tmdb_id, imdb_id)
        if not coppie:
            support.info('Nessuna stagione disponibile da TMDB')
            return sito
        for season, episode in coppie:
            if player == 'vidxgo' and token:
                url = _vidxgo_url(token, season, episode)
            else:
                url = _vixsrc_url(imdb_id or tmdb_id, season, episode)
            new_item = _episodio(item, season, episode, url)
            new_item.imdb_id = imdb_id
            if tmdb_id:
                new_item.infoLabels['tmdb_id'] = tmdb_id
            itemlist.append(new_item)

    support.info('Generati %d episodi' % len(itemlist))

    # Info episodio da TMDB solo se l'utente l'ha attivata (come gli altri canali)
    if config.get_setting('episode_info') and not support.stackCheck(['add_tvshow', 'get_newest']):
        support.tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        # il core scrive il titolo TMDB in infoLabels: lo porto nell'etichetta
        for it in itemlist:
            t = it.infoLabels.get('title')
            if t and not it.title.endswith(' - ' + t):
                it.title = '%dx%02d - %s' % (int(it.season), int(it.episode), t)
    support.check_trakt(itemlist)
    support.videolibrary(itemlist, item)
    return itemlist


def check(item):
    support.info('CHECK chiamata per:', item)
    item.data = httptools.downloadpage(item.url).data

    is_tvshow = False
    if 'show_id' in item.data:
        is_tvshow = True
    elif 'Serie TV' in item.data and 'Durata episodio' in item.data:
        is_tvshow = True
    elif 'vixsrc.to/tv/' in item.data:
        is_tvshow = True
    elif re.search(r'vidxgo\.co/[A-Za-z0-9]+/\d+/\d+', item.data.replace('\\/', '/')):
        is_tvshow = True
    elif _episodi_sito(item.data):
        # la pagina elenca gli episodi nei tab delle stagioni
        is_tvshow = True
    elif re.search(r'id=["\']vidxgo-player["\']', item.data):
        # iframe delle serie (quello dei film e' vidxgo-player-film)
        is_tvshow = True

    if is_tvshow:
        item.contentType = 'tvshow'
        support.info('Rilevata serie TV, chiamando episodios')
        return episodios(item)
    else:
        item.contentType = 'movie'
        support.info('Rilevato film, chiamando findvideos')
        return findvideos(item)


def newest(categoria):
    support.info(categoria)
    itemlist = []
    item = Item()
    try:
        if categoria == "peliculas":
            item.url = host
            item.action = "peliculas"
            item.contentType = 'movie'
            itemlist = peliculas(item)
            if itemlist and itemlist[-1].action == "peliculas":
                itemlist.pop()
    except:
        import sys
        for line in sys.exc_info():
            logger.error("{0}".format(line))
        return []
    return itemlist


def _url_player(imdb_id, tmdb_id, token, season=None, episode=None, primo='vidxgo'):
    """Gli URL di tutti e due i player, il preferito per primo."""
    vdx = _vidxgo_url(token, season, episode) if token else None
    ident = imdb_id or tmdb_id
    vix = _vixsrc_url(ident, season, episode) if ident else None
    ordine = [vix, vdx] if primo == 'vixsrc' else [vdx, vix]
    return [u for u in ordine if u]


def findvideos(item):
    support.info('findvideos', item)

    # episodio preso dalla pagina del sito: i link dei mirror sono gia' nell'item
    if getattr(item, 'links_sito', None):
        return support.server(item, item.links_sito)

    # Passo 1: l'URL dell'item e' gia' quello di un player (episodi creati da
    # episodios): si ricava l'altro e si offrono entrambi, come StreamFlix.
    mv = _RE_VDX_URL.search(item.url or '')
    mx = _RE_VIX_URL.search(item.url or '')
    if mv or mx:
        imdb_id = getattr(item, 'imdb_id', None)
        tmdb_id = None
        if mv:
            primo = 'vidxgo'
            token = mv.group(1)
            season, episode = mv.group(2), mv.group(3)
            if not imdb_id and token.isdigit():
                imdb_id = 'tt' + token
            if token.startswith('tm'):
                tmdb_id = token[2:]
        else:
            primo = 'vixsrc'
            ident = mx.group(2)
            season, episode = mx.group(3), mx.group(4)
            if ident.startswith('tt'):
                imdb_id = ident
            else:
                tmdb_id = ident
            token = imdb_id[2:] if imdb_id else 'tm' + ident
        urls = _url_player(imdb_id, tmdb_id, token, season, episode, primo)
        support.info(f'URL dei due player: {urls}')
        return support.server(item, urls)

    # Passo 2: URL del sito, si legge la pagina e si riconosce il player.
    data = item.data if hasattr(item, 'data') and item.data else httptools.downloadpage(item.url).data

    is_episode = item.contentType == 'episode' or (hasattr(item, 'season') and item.season)

    info = _player_info(data, 'tv' if is_episode else 'movie')
    imdb_id = info['imdb']
    token = info['token']

    if not imdb_id and not token:
        support.info('IMDB ID non trovato!')
        return []

    season = (getattr(item, 'season', 1) or 1) if is_episode else None
    episode = (getattr(item, 'episode', 1) or 1) if is_episode else None

    urls = _url_player(imdb_id, info['tmdb'], token, season, episode, info['player'])
    support.info(f'URL generati: {urls}')
    return support.server(item, urls)
