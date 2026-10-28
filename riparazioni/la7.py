# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per La7 (nuovo sito la7play.it, riscritto)
# ------------------------------------------------------------

import base64
import html as _html
import json
import re
from datetime import datetime, timedelta

from core import support, httptools
from platformcode import logger

DRM = 'com.widevine.alpha'
host = 'https://www.la7play.it'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
headers = {'User-Agent': UA, 'Referer': host + '/', 'Origin': host}
# identificativi delle query interne del sito (/api/gql/<id>)
GQL_PROGRAMMI = ['75b0227f0361abcf', 'f7034d55158fc906']
GQL_RICERCA = '4da1e384f8a63808'
LIVE = [('La7', '/dirette/la7'), ('La7Cinema', '/dirette/la7-cinema')]
RIVEDI = [('La7', '/guida-tv-rivedi/la7'), ('La7Cinema', '/guida-tv-rivedi/la7-cinema')]


@support.menu
def mainlist(item):
    top = [('Dirette {bold}', ['', 'live']),
           ('Rivedi oggi {bold}', ['', 'replay_channels'])]

    menu = [('Programmi TV {bullet bold}', ['/programmi', 'peliculas', '', 'tvshow']),
            ('Film La7 {bullet bold}', ['/film', 'film', '', 'movie']),
            ('TG La7 {bullet bold}', ['/tgla7/puntate', 'episodios', '', 'tvshow'])]

    search = ''
    return locals()


# ---------------------------------------------------------------- utilita

def _scarica(url):
    try:
        return httptools.downloadpage(url, headers=headers).data or ''
    except Exception as e:
        logger.error('la7: download fallito %s %s' % (url, e))
        return ''


def _pulisci(h):
    return h.replace('\\"', '"').replace('\\u0026', '&').replace('\\/', '/')


def _ld(h):
    """Nodi JSON-LD della pagina (blocco @graph)."""
    nodi = []
    for blocco in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S):
        try:
            j = json.loads(blocco)
        except Exception:
            continue
        nodi.extend(j.get('@graph', [j]) if isinstance(j, dict) else j)
    return nodi


def _elementi(h, tipi=None):
    """Elementi della prima ItemList della pagina, filtrati per @type."""
    out = []
    for nodo in _ld(h):
        if nodo.get('@type') != 'ItemList':
            continue
        for el in nodo.get('itemListElement', []):
            it = el.get('item', el)
            if isinstance(it, dict) and (not tipi or it.get('@type') in tipi):
                out.append(it)
        if out:
            break
    return out


def _img(it):
    i = it.get('image', '')
    if isinstance(i, dict):
        i = i.get('url', '')
    return i or ''


def _roma(iso):
    """Orario italiano da una data UTC ISO (ora legale europea)."""
    try:
        d = datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S')
    except Exception:
        return ''
    def ultima_domenica(anno, mese):
        g = datetime(anno, mese, 31)
        return g - timedelta(days=(g.weekday() + 1) % 7)
    inizio = ultima_domenica(d.year, 3).replace(hour=1)
    fine = ultima_domenica(d.year, 10).replace(hour=1)
    d = d + timedelta(hours=2 if inizio <= d < fine else 1)
    return d.strftime('%H:%M')


def _programmi():
    for ident in GQL_PROGRAMMI:
        try:
            j = json.loads(_scarica('%s/api/gql/%s' % (host, ident)))
            righe = j['data']['graphqlTuttiProgrammi']['results']
            if righe:
                return righe
        except Exception:
            continue
    return []


# ---------------------------------------------------------------- dirette e rivedi

def live(item):
    itemlist = []
    for nome, percorso in LIVE:
        itemlist.append(item.clone(title=support.typo(nome, 'bold'), fulltitle=nome, url=host + percorso,
                                   action='findvideos', forcethumb=True, no_return=True))
    return support.thumb(itemlist, live=True)


def replay_channels(item):
    itemlist = []
    for nome, percorso in RIVEDI:
        itemlist.append(item.clone(title=support.typo(nome, 'bold'), fulltitle=nome, url=host + percorso,
                                   action='replay', forcethumb=True))
    return support.thumb(itemlist, live=True)


def replay(item):
    itemlist = []
    for ev in _elementi(_scarica(item.url), ('BroadcastEvent',)):
        lavoro = ev.get('workFeatured') or {}
        url = lavoro.get('url')
        if not url:
            continue
        titolo = _html.unescape(ev.get('name', ''))
        itemlist.append(item.clone(title=support.typo('%s - %s' % (_roma(ev.get('startDate', '')), titolo), 'bold'),
                                   contentTitle=titolo, fulltitle=titolo, show=titolo, url=url,
                                   plot=_html.unescape(ev.get('description', '')),
                                   thumbnail=_img(lavoro), fanart=_img(lavoro), action='findvideos', forcethumb=True))
    return itemlist


# ---------------------------------------------------------------- programmi, puntate, film

def peliculas(item):
    itemlist = []
    for r in _programmi():
        titolo = _html.unescape(r.get('titolo', '')).strip()
        percorso = r.get('pathname', '')
        if not titolo or not percorso:
            continue
        plot = _html.unescape(re.sub(r'<[^>]+>', '', r.get('occhiello', '') or '')).replace('\xa0', ' ').strip()
        thumb = r.get('img', '') or ''
        if thumb.startswith('/'):
            thumb = host + thumb
        itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=titolo, show=titolo, contentSerieName=titolo,
                                   plot=plot, thumbnail=thumb, fanart=thumb, url=host + percorso, action='episodios'))
    itemlist.sort(key=lambda i: i.fulltitle.lower())
    return itemlist


def episodios(item):
    url = item.url
    pagina = int(item.page or 1) if hasattr(item, 'page') and item.page else 1
    if '/puntate' not in url:
        url = url.rstrip('/') + '/puntate'
    base = url.split('?')[0]
    h = _scarica(base + ('?page=%d' % pagina if pagina > 1 else ''))
    elementi = _elementi(h, ('TVEpisode',))
    if not elementi and pagina == 1:
        elementi = _elementi(_scarica(base.replace('/puntate', '')), ('TVEpisode', 'TVClip'))
    itemlist = []
    for ep in elementi:
        titolo = _html.unescape(ep.get('name', '')).strip()
        if not ep.get('url'):
            continue
        data = ep.get('datePublished', '')[:10]
        itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=titolo, show=item.fulltitle or titolo,
                                   contentTitle=titolo, url=ep['url'], thumbnail=_img(ep), fanart=_img(ep),
                                   plot=data, action='findvideos', forcethumb=True))
    if len(elementi) >= 20:
        itemlist.append(item.clone(title=support.typo(support.config.get_localized_string(30992), 'color std bold'),
                                   url=base, page=pagina + 1, action='episodios', nextPage=True, thumbnail=support.thumb()))
    return itemlist


def film(item):
    itemlist = []
    for f in _elementi(_scarica(host + '/film'), ('Movie',)):
        titolo = _html.unescape(f.get('name', '')).strip()
        if not f.get('url'):
            continue
        itemlist.append(item.clone(title=support.typo(titolo, 'bold'), fulltitle=titolo, contentTitle=titolo,
                                   url=f['url'], thumbnail=_img(f), fanart=_img(f), contentType='movie',
                                   action='findvideos', forcethumb=True))
    return itemlist


def _codifica(variabili):
    """Variabili della query come le codifica il sito: JSON con chiavi ordinate, base64 url senza padding."""
    t = json.dumps(variabili, separators=(',', ':'), sort_keys=True, ensure_ascii=False)
    return base64.urlsafe_b64encode(t.encode('utf-8')).decode('ascii').rstrip('=')


def search(item, text):
    q = str(getattr(item, 'search', '') or text).strip()
    if not q:
        return []
    pagina = int(getattr(item, 'page', 0) or 1)
    var = {'q': q}
    if pagina > 1:
        var['page'] = pagina
    try:
        j = json.loads(_scarica('%s/api/gql/%s/%s' % (host, GQL_RICERCA, _codifica(var))))
        dati = j['data']['siteSearch']
    except Exception as e:
        logger.error('la7: ricerca fallita %s' % e)
        return []
    itemlist = []
    for gruppo in dati.get('groups', []):
        if gruppo.get('contentType') == 'article':
            continue
        for h in gruppo.get('hits', []):
            url = h.get('url')
            if not url:
                continue
            titolo = _html.unescape(h.get('title', '')).strip()
            programma = h.get('propertyName') or ''
            thumb = h.get('imageUrl') or ''
            video = bool(re.search(r'-\d{5,}$', url))
            plot = _html.unescape(h.get('excerpt') or '')
            itemlist.append(item.clone(
                title=support.typo(titolo + (' (%s)' % programma if programma and video else ''), 'bold'),
                fulltitle=titolo, contentTitle=titolo, show=programma or titolo, url=host + url,
                thumbnail=thumb, fanart=thumb, plot=plot, forcethumb=True,
                action='findvideos' if video else 'episodios'))
    if pagina < int(dati.get('totalPages') or 1):
        itemlist.append(item.clone(title=support.typo(support.config.get_localized_string(30992), 'color std bold'),
                                   search=q, page=pagina + 1, action='search_page', nextPage=True,
                                   thumbnail=support.thumb()))
    return itemlist


def search_page(item):
    return search(item, item.search)


# ---------------------------------------------------------------- video

def _token(endpoint, ident, tipo):
    try:
        data = httptools.downloadpage('%s?id=%s&contentType=%s' % (endpoint, ident, tipo), headers=headers).data
        j = json.loads(data)
        return j.get('preAuthToken') or j.get('token') or j.get('auth') or ''
    except Exception as e:
        logger.error('la7: token non ottenuto %s' % e)
        return ''


def _licenza(server, token):
    for parte in server.split(';'):
        if parte.lower().startswith(DRM):
            url = parte.split('|', 1)[1]
            return '%s|preAuthorization=%s&Origin=%s&Referer=%s/|R{SSM}|' % (url, token, host, host + '/')
    return ''


def findvideos(item):
    h = _pulisci(_scarica(item.url))

    def g(rx):
        m = re.search(rx, h)
        return m.group(1) if m else ''

    endpoint = g(r'"drmTokenEndpoint":"([^"]+)"')
    ident = g(r'"drmContentId":"([^"]+)"')
    server = g(r'"drmLicenseServer":"([^"]+)"')
    url = ''
    drm = False
    tipo = 'VOD'

    if '/dirette/' in item.url:
        principale = g(r'"mainLiveUrl":"([^"]+)"').split('|')[0]
        url = principale
        drm = True
        tipo = 'LIVE'
    else:
        remoto = g(r'"cf_remote_url":"([^"]+)"')
        if not remoto:
            logger.error('la7: video non trovato in %s' % item.url)
            return []
        vecchio = g(r'"cf_old_entry_id":"([^"]+)"')
        drm = g(r'"drm":(true|false)') == 'true'
        if drm:
            base = g(r'"hostnameCdnDrm":"([^"]+)"').rstrip('/')
            nome = remoto.lstrip('/').split('/')[-1]
            url = '%s/%s/DASH/%s.mpd' % (base, nome, nome)
        else:
            base = g(r'"hostnameCdn":"([^"]+)"').rstrip('/')
            percorso = (remoto if remoto.startswith('/') else '/' + remoto).replace('.mp4', '')
            if not vecchio:
                parti = []
                for p in percorso.split(','):
                    p = p.strip()
                    parti.append(p if not p or p.startswith('/nk/') else ('/nk' + p if p.startswith('/') else '/nk/' + p))
                percorso = ','.join(parti)
            url = '%s/local/hls/,%s,.mp4.urlset/master.m3u8' % (base, percorso)

    if not url:
        return []
    it = item.clone(title='Direct', server='directo', url=url, action='play')
    if drm:
        token = _token(endpoint, ident, tipo)
        it.drm = DRM
        it.license = _licenza(server, token)
    return support.server(it, itemlist=[it], Download=False, Videolibrary=False)
