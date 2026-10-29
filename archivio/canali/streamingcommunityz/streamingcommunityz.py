# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Canale per Streamingcommunityz
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

SEZIONI = [{'nome': 'Titoli',
  'tipo': 'movie',
  'url': '/api/sliders/fetch',
  'params': {'lang': 'it'},
  'body': {'sliders': [{'name': 'genre', 'genre': 'Avventura'},
                       {'name': 'genre', 'genre': 'Thriller'},
                       {'name': 'genre', 'genre': 'televisione film'},
                       {'name': 'genre', 'genre': 'Famiglia'},
                       {'name': 'genre', 'genre': 'Storia'},
                       {'name': 'genre', 'genre': 'Korean drama'}]},
  'lista': 'titles',
  'pag': None,
  'inertia': False},
 {'nome': 'Serie TV',
  'tipo': 'tvshow',
  'url': '/api/sliders/fetch',
  'params': {'lang': 'it'},
  'body': {'sliders': [{'name': 'new-episodes', 'title_type': 'tv', 'genre': None},
                       {'name': 'genre', 'title_type': 'tv', 'genre': 'Action & Adventure'},
                       {'name': 'genre', 'title_type': 'tv', 'genre': 'Animazione'}]},
  'lista': 'titles',
  'pag': None,
  'inertia': False},
 {'nome': 'Film',
  'tipo': 'movie',
  'url': '/api/sliders/fetch',
  'params': {'lang': 'it'},
  'body': {'sliders': [{'name': 'genre', 'title_type': 'movie', 'genre': 'Fantascienza'},
                       {'name': 'genre', 'title_type': 'movie', 'genre': 'Korean drama'},
                       {'name': 'genre', 'title_type': 'movie', 'genre': 'Musica'}]},
  'lista': 'titles',
  'pag': None,
  'inertia': False},
 {'nome': 'Archivio',
  'tipo': 'tvshow',
  'url': '/it/archive',
  'params': {'lang': 'it', 'page': '2'},
  'body': None,
  'lista': 'data',
  'pag': {'dove': 'query', 'chiave': 'page', 'tipo': 'pagina', 'valore': '2'},
  'inertia': False},
 {'nome': 'Premium',
  'tipo': 'tvshow',
  'url': '/it/premium',
  'params': {},
  'body': None,
  'lista': 'props.copy.perks',
  'pag': None,
  'inertia': True}]
CAMPI = {"title": "name", "type": "type", "year": "last_air_date"}
IDS = ["slug", "id"]  # campi che identificano il titolo, in ordine di preferenza
DETTAGLIO = '/it/titles/{id}-{slug}'  # pagina del titolo, {} al posto dell'id (oppure {nome} dei campi di DETT_CAMPI)
DETT_CAMPI = {"id": "id", "slug": "slug"}  # nome usato nel modello -> campo del titolo
EPISODI = {'inertia': True,
 'stagioni': 'props.title.seasons',
 'num_stagione': 'number',
 'stagione_url': '/season-{S}',
 'lista': 'props.loadedSeason.episodes',
 'chiavi': {'title': 'name', 'ids': ['id'], 'plot': 'plot', 'year': 'updated_at', 'episode': 'number'}}


@support.menu
def mainlist(item):
    film = ['',
           ('Titoli', ['', 'peliculas', '0', 'movie']),
           ('Film', ['', 'peliculas', '2', 'movie'])]
    tvshow = ['',
           ('Serie TV', ['', 'peliculas', '1', 'tvshow']),
           ('Archivio', ['', 'peliculas', '3', 'tvshow']),
           ('Premium', ['', 'peliculas', '4', 'tvshow'])]
    search = ''
    return locals()


RICERCA = None
RICERCA_BODY = None
RICERCA_URL = ''
RICERCA_INERTIA = False
RICERCA_LISTA = ''


def prendi(d, path, default=''):
    for p in path.split('.'):
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and p.isdigit() and int(p) < len(d):
            d = d[int(p)]
        elif isinstance(d, list) and d and isinstance(d[0], dict) and not p.isdigit():
            d = d[0].get(p)  # percorso senza indice: si legge il primo elemento della lista
        else:
            return default
        if d is None:
            return default
    return d


def cerca_chiave(d, chiave):
    # cerca una chiave (per esempio endCursor) in qualsiasi punto della risposta
    if isinstance(d, dict):
        if d.get(chiave) not in (None, ''):
            return d[chiave]
        for v in d.values():
            r = cerca_chiave(v, chiave)
            if r not in (None, ''):
                return r
    elif isinstance(d, list):
        for v in d:
            r = cerca_chiave(v, chiave)
            if r not in (None, ''):
                return r
    return None


def cerca_lista(d, chiave_titolo):
    # prima lista di oggetti che contengono il campo del titolo
    if isinstance(d, list):
        if d and isinstance(d[0], dict) and prendi(d[0], chiave_titolo):
            return d
        for v in d:
            r = cerca_lista(v, chiave_titolo)
            if r:
                return r
    elif isinstance(d, dict):
        for v in d.values():
            r = cerca_lista(v, chiave_titolo)
            if r:
                return r
    return []


_INERTIA = {}


def intestazioni_inertia():
    # siti Inertia.js: la versione dei file cambia a ogni aggiornamento del sito, si legge dalla home
    if 'v' not in _INERTIA:
        versione = ''
        try:
            pagina = httptools.downloadpage(host + '/', headers={'Referer': host + '/'}).data
            m = re.search(r'data-page="([^"]+)"', pagina)
            if m:
                from html import unescape
                versione = json.loads(unescape(m.group(1))).get('version', '')
        except Exception:
            logger.error('Versione Inertia non letta')
        _INERTIA['v'] = versione
    return {'X-Inertia': 'true', 'X-Inertia-Version': _INERTIA['v'], 'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/html, application/xhtml+xml'}


def sezione(item):
    return SEZIONI[int(item.args)] if str(item.args).isdigit() and int(item.args) < len(SEZIONI) else SEZIONI[0]


def chiama(item):
    sez = sezione(item)
    PAGINAZIONE = sez['pag']
    params = dict(sez['params'])
    body = json.loads(json.dumps(sez['body'])) if sez['body'] is not None else None
    url = sez['url'] if sez['url'].startswith('http') else host + sez['url']
    pagina = int(item.pagina) if item.pagina else 1
    if item.search_text and RICERCA_BODY is not None:
        body = json.loads(RICERCA_BODY.replace('__TESTO__', json.dumps(item.search_text)[1:-1]))
        url = RICERCA_URL or url
    elif item.search_text and RICERCA:
        intest = {'Referer': host + '/'}
        if RICERCA_INERTIA:
            intest.update(intestazioni_inertia())
        return httptools.downloadpage(RICERCA % item.search_text.replace(' ', '+'), headers=intest).json
    if PAGINAZIONE:
        ch = PAGINAZIONE['chiave']
        if PAGINAZIONE['dove'] == 'query':
            bersaglio = params
        else:
            bersaglio = body.get('variables') if 'variables' in body else body
        if PAGINAZIONE['tipo'] == 'cursore':
            if item.after:
                bersaglio[ch] = item.after
        elif PAGINAZIONE['tipo'] == 'pagina':
            bersaglio[ch] = pagina
        else:
            bersaglio[ch] = (pagina - 1) * int(PAGINAZIONE.get('passo', 20))
    url = url + ('?' + urlencode(params) if params else '')
    opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
    if sez.get('inertia'):
        opt['headers'].update(intestazioni_inertia())
    if body is not None:
        opt['post'] = json.dumps(body)
    return httptools.downloadpage(url, **opt).json


def url_in_chiaro(d):
    # primo url di manifest (m3u8 o mpd) presente in qualsiasi punto della risposta
    if isinstance(d, str):
        return d if re.match(r'https?://', d) and re.search(r'\.(m3u8|mpd)(\?|$)', d) else ''
    if isinstance(d, dict):
        valori = d.values()
    elif isinstance(d, list):
        valori = d
    else:
        return ''
    for v in valori:
        r = url_in_chiaro(v)
        if r:
            return r
    return ''


def simile(a, b):
    na = re.sub(r'[^a-z0-9]', '', (a or '').lower())
    nb = re.sub(r'[^a-z0-9]', '', (b or '').lower())
    if not na or not nb:
        return 0
    if na in nb or nb in na:
        return 1
    return difflib.SequenceMatcher(None, na, nb).ratio()


def verificaTmdb(itemlist):
    # se TMDB ha scelto un altro titolo (risultato sbagliato) si torna ai dati del sito
    for it in itemlist:
        info = it.infoLabels
        if not info.get('tmdb_id') or not it.sito_title:
            continue
        trovati = [info.get('originaltitle'), info.get('title')]
        if max([simile(it.sito_title, t) for t in trovati]) >= 0.9:
            continue
        logger.debug('TMDB scartato per', it.sito_title, trovati)
        pulite = {'year': it.sito_year} if it.sito_year else {}
        if it.contentType == 'movie':
            pulite['title'] = it.sito_title
        else:
            pulite['tvshowtitle'] = it.sito_title
        if it.sito_plot:
            pulite['plot'] = it.sito_plot
        it.__dict__['infoLabels'] = InfoLabels(pulite)
        it.thumbnail = it.sito_thumb
        it.fanart = ''


def peliculas(item):
    logger.debug()
    itemlist = []
    sez = sezione(item)
    PAGINAZIONE = sez['pag']
    risposta = chiama(item)
    lista = prendi(risposta, RICERCA_LISTA if (item.search_text and RICERCA_LISTA) else sez['lista'], [])
    if not lista:
        lista = cerca_lista(risposta, CAMPI.get('title', 'title'))
    for el in lista:
        titolo = prendi(el, CAMPI.get('title', 'title'))
        if not titolo:
            continue
        idv = ''
        for k in IDS:
            idv = prendi(el, k)
            if idv:
                break
        anno = prendi(el, CAMPI['year']) if 'year' in CAMPI else ''
        m = re.search(r'(19|20)\d{2}', str(anno))
        anno = m.group(0) if m else ''
        url = ''
        if DETTAGLIO:
            if DETT_CAMPI:
                dett = DETTAGLIO.format(**{n: str(prendi(el, k) or '') for n, k in DETT_CAMPI.items()})
            else:
                dett = DETTAGLIO.format(idv)
            url = host + dett if dett.startswith('/') else dett
        thumb = prendi(el, CAMPI['thumb']) if 'thumb' in CAMPI else ''
        thumb = str(thumb).replace('{profile}', 's332').replace('{format}', 'jpg')
        if thumb.startswith('/'):
            thumb = host + thumb
        plot = prendi(el, CAMPI['plot']) if 'plot' in CAMPI else ''
        tipo = sez['tipo']
        if 'type' in CAMPI:
            tipo = 'tvshow' if re.search(r'show|serie|tv|series', str(prendi(el, CAMPI['type'])), re.I) else 'movie'
        comuni = dict(channel=item.channel, title=titolo, fulltitle=titolo, show=titolo,
                      thumbnail=thumb, url=url, idv=str(idv),
                      sito_title=titolo, sito_year=anno, sito_plot=str(plot or ''), sito_thumb=thumb)
        if tipo == 'tvshow':
            itemlist.append(Item(action='episodios', contentType='tvshow', contentSerieName=titolo,
                                 infoLabels={'tvshowtitle': titolo, 'year': anno} if anno else {'tvshowtitle': titolo},
                                 **comuni))
        else:
            itemlist.append(Item(action='findvideos', contentType='movie', contentTitle=titolo,
                                 infoLabels={'year': anno} if anno else {}, **comuni))
    try:
        tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        verificaTmdb(itemlist)
    except:
        logger.error('TMDB non disponibile')

    if itemlist and PAGINAZIONE and not item.search_text:
        if PAGINAZIONE['tipo'] == 'cursore':
            fine = cerca_chiave(risposta, 'endCursor')
            ancora = cerca_chiave(risposta, 'hasNextPage')
            if fine and ancora is not False:
                itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'),
                                           action='peliculas', after=fine, thumbnail=support.thumb()))
        else:
            itemlist.append(item.clone(title=support.typo(config.get_localized_string(30992), 'color kod bold'),
                                       action='peliculas', pagina=(int(item.pagina) if item.pagina else 1) + 1,
                                       thumbnail=support.thumb()))
    return itemlist


def episodios(item):
    logger.debug()
    itemlist = []
    if not EPISODI:
        platformtools.dialog_ok('Streamingcommunityz', 'Episodi non rilevati sul sito')
        return []
    ch = EPISODI['chiavi']
    if EPISODI.get('inertia'):
        # la pagina del titolo elenca le stagioni, ogni stagione ha la sua pagina con gli episodi
        intest = {'Referer': host + '/'}
        intest.update(intestazioni_inertia())
        pagina_titolo = item.url if item.url.startswith('http') else host + item.url
        r0 = httptools.downloadpage(pagina_titolo, headers=intest).json
        numeri = []
        for st in prendi(r0, EPISODI['stagioni'], []):
            try:
                numeri.append(int(float(prendi(st, EPISODI['num_stagione']))))
            except (ValueError, TypeError):
                continue
        elenco = []
        for n in numeri or [1]:
            r1 = httptools.downloadpage(pagina_titolo + EPISODI['stagione_url'].format(S=n), headers=intest).json
            for ep in (prendi(r1, EPISODI['lista'], []) or cerca_lista(r1, ch.get('title', 'title'))):
                elenco.append((n, ep))
    else:
        url = EPISODI['url'].replace('{ID}', item.idv)
        if not url.startswith('http'):
            url = host + url
        opt = {'headers': {'Referer': host + '/', 'Content-Type': 'application/json'}}
        if EPISODI['body']:
            opt['post'] = EPISODI['body'].replace('{ID}', item.idv)
        risposta = httptools.downloadpage(url, **opt).json
        lista = prendi(risposta, EPISODI['lista'], []) or cerca_lista(risposta, ch.get('title', 'title'))
        elenco = [(None, ep) for ep in lista]
    titolo_serie = item.sito_title or item.contentSerieName or item.fulltitle
    anno = item.sito_year or item.infoLabels.get('year', '')
    for stagione_nota, ep in elenco:
        try:
            stagione = stagione_nota if stagione_nota is not None else int(float(prendi(ep, ch['season'])))
            numero = int(float(prendi(ep, ch['episode'])))
        except (ValueError, TypeError, KeyError):
            continue
        nome = prendi(ep, ch['title']) if 'title' in ch else ''
        idv = ''
        for k in ch.get('ids', []):
            idv = prendi(ep, k)
            if idv:
                break
        itemlist.append(Item(channel=item.channel,
                             action='findvideos',
                             contentType='episode',
                             title=support.typo('{}x{:02d}'.format(stagione, numero) + (' - ' + nome if nome else ''), 'bold'),
                             fulltitle=titolo_serie,
                             show=titolo_serie,
                             contentSerieName=titolo_serie,
                             contentSeason=stagione,
                             contentEpisodeNumber=numero,
                             infoLabels={'season': stagione, 'episode': numero,
                                         'tvshowtitle': titolo_serie, 'year': anno},
                             thumbnail=item.thumbnail,
                             idv=str(idv),
                             url=item.url if EPISODI.get('inertia') else ''))
    if itemlist and config.get_setting('episode_info'):
        try:
            tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)
        except:
            logger.error('TMDB non disponibile')
    support.videolibrary(itemlist, item)
    return itemlist



def search(item, text):
    # TODO: ricerca non rilevata automaticamente
    return []


def findvideos(item):
    support.info(item)
    # TODO: sorgente del video non rilevata automaticamente: se la pagina del titolo ha iframe
    # o link ai server, support.server li trova da solo
    return support.server(item, headers=headers)
