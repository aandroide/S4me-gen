# -*- coding: utf-8 -*-
"""
riproduzione.py: impara da solo come un sito fa partire un video (manifest, token, licenza DRM) e scrive il findvideos.

Il sito mette nella pagina i dati del video (indirizzi, identificativi, indirizzo del server di licenza). Il browser,
quando si preme play, scarica un token e il manifest. Confrontando i dati della pagina con quello che il browser
ha richiesto, si ricava una "ricetta": come ricostruire manifest, token e licenza partendo dalla sola pagina,
senza browser. La ricetta e valida per tutte le pagine dello stesso tipo (per esempio puntate, film, dirette).

Parti:
  valori_pagina(html)      coppie chiave valore piatte dei dati incorporati (prima occorrenza di ogni chiave)
  impara_url(M, valori)    modello che riproduce l'indirizzo M usando i valori della pagina
  impara(...)              raccoglie campioni con il browser e scrive la ricetta
  codice_canale(ricetta)   sorgente di findvideos per il canale generato
"""
import json
import re
from urllib.parse import urlsplit, parse_qsl

# ---------------------------------------------------------------------------
# Parte copiata nel canale
# ---------------------------------------------------------------------------
from urllib.parse import urlsplit as _urlsplit

ESPR = re.compile(r'"([A-Za-z_][\w\-]*)":("(?:[^"\\]|\\.)*"|true|false|-?\d+(?:\.\d+)?)')


def pulisci(h):
    return h.replace('\\"', '"').replace('\\u0026', '&').replace('\\/', '/').replace('\\\\', '\\')


def valori_pagina(h):
    """Prima occorrenza di ogni chiave dei dati incorporati: {chiave: valore come stringa}."""
    out = {}
    for m in ESPR.finditer(pulisci(h)):
        k, v = m.group(1), m.group(2)
        if k in out:
            continue
        if v.startswith('"'):
            v = v[1:-1]
        out[k] = v
    return out


def _ultimo(v):
    return v.split('?')[0].rstrip('/').split('/')[-1]


TRASFORMAZIONI = [
    ('id', lambda v: v),
    ('ultimo', _ultimo),
    ('senza_slash', lambda v: v.strip('/')),
    ('senza_mp4', lambda v: v.replace('.mp4', '')),
    ('prima', lambda v: v.split('|')[0]),
    ('seconda', lambda v: v.split('|')[1] if '|' in v else ''),
    ('origine', lambda v: '%s://%s' % (_urlsplit(v).scheme, _urlsplit(v).netloc) if v.startswith('http') else ''),
]
TR = dict(TRASFORMAZIONI)


def applica(modello, valori):
    out = ''
    for p in modello:
        if p[0] == 'lett':
            out += p[1]
        else:
            v = valori.get(p[1])
            if v is None or v == '':
                return None
            out += TR[p[2]](v)
    return out


def licenza_url(v, sistema='com.widevine.alpha'):
    """Indirizzo del server di licenza dentro il valore della pagina (elenco 'sistema|indirizzo;sistema|indirizzo')."""
    for parte in (v or '').split(';'):
        if parte.lower().startswith(sistema) and '|' in parte:
            return parte.split('|', 1)[1]
    return v if (v or '').startswith('http') else ''


def condizione_ok(c, url, valori):
    if not c:
        return True
    if c[0] == 'percorso':
        return c[1] in url
    if c[0] == 'chiave':
        return valori.get(c[1]) == c[2]
    return True


def indirizzo_token(tk, valori):
    base = applica(tk['base'], valori)
    if not base:
        return None
    q = []
    for k, v in tk['param']:
        x = valori.get(v[1]) if v[0] == 'chiave' else v[1]
        if x is None:
            return None
        q.append('%s=%s' % (k, x))
    return base + ('?' + '&'.join(q) if q else '')


#<<FINE_CANALE


def codice_helper():
    """Sorgente della parte da copiare nel canale."""
    testo = open(__file__, encoding='utf-8').read()
    ini = testo.index('from urllib.parse import urlsplit as _urlsplit')
    fin = testo.index('#<<' + 'FINE_CANALE')
    return testo[ini:fin].rstrip() + '\n'


def impara_url(m, valori):
    """Modello [('lett', testo) | ('chiave', k, trasformazione)] che ricostruisce m. Restituisce None se non copre nulla."""
    cand = []
    for k, v in valori.items():
        if not isinstance(v, str) or len(v) < 4:
            continue
        for nome, f in TRASFORMAZIONI:
            try:
                s = f(v)
            except Exception:
                continue
            if len(s) >= 4 and s in m:
                cand.append((len(s), k, nome, s))
    cand.sort(key=lambda c: (-c[0], c[1]))
    usato = [None] * len(m)
    for lung, k, nome, s in cand:
        pos = 0
        while True:
            i = m.find(s, pos)
            if i < 0:
                break
            if all(usato[j] is None for j in range(i, i + lung)):
                for j in range(i, i + lung):
                    usato[j] = 'dentro'
                usato[i] = (k, nome, True)
            pos = i + 1
    modello, lett, i = [], '', 0
    while i < len(m):
        u = usato[i]
        if isinstance(u, tuple) and len(u) == 3:
            if lett:
                modello.append(('lett', lett))
                lett = ''
            k, nome, _ = u
            s = TR[nome](valori[k])
            modello.append(('chiave', k, nome))
            i += len(s)
        else:
            lett += m[i]
            i += 1
    if lett:
        modello.append(('lett', lett))
    if not any(p[0] == 'chiave' for p in modello):
        return None
    return modello


def senza_marcatore(url):
    """Toglie dall'indirizzo i parametri che sono solo un marcatore anti cache (numero di 10 o piu cifre)."""
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not re.fullmatch(r'\d{10,13}', v)]
    return p, q


def impara_token(url, valori, corpo_json):
    """Ricetta del token: indirizzo base e parametri (letterali o presi dalla pagina) e campo della risposta."""
    parti, query = senza_marcatore(url)
    base = '%s://%s%s' % (parti.scheme, parti.netloc, parti.path)
    mod_base = impara_url(base, valori) or [('lett', base)]
    param = []
    for k, v in query:
        chiavi = [c for c, x in valori.items() if x == v and v != '']
        if chiavi and re.fullmatch(r'[\w\-]{1,}', v) and not re.fullmatch(r'[A-Z]{2,}', v):
            pref = [c for c in chiavi if re.search(r'id$', c, re.I) or k.lower() in c.lower()]
            param.append((k, ('chiave', (pref or chiavi)[0])))
        else:
            param.append((k, ('lett', v)))
    campo = ''
    try:
        j = json.loads(corpo_json)

        def cerca(o):
            if isinstance(o, dict):
                for kk, vv in o.items():
                    if isinstance(vv, str) and len(vv) >= 20 and re.search(r'token|auth|jwt', kk, re.I):
                        return kk
                    r = cerca(vv)
                    if r:
                        return r
            return None
        campo = cerca(j) or ''
    except Exception:
        pass
    return {'base': mod_base, 'param': param, 'campo': campo}


def trova_licenza(valori):
    """Chiave della pagina che contiene l'indirizzo del server di licenza Widevine."""
    for k, v in valori.items():
        if isinstance(v, str) and re.search(r'widevine', v, re.I) and 'http' in v:
            return k
    return None


def intestazione_licenza(testi_js):
    """Nome dell'intestazione che porta il token alla licenza, cercato nei file JavaScript del sito."""
    for t in testi_js:
        if not re.search(r'widevine|licen[cs]e', t, re.I):
            continue
        m = re.search(r'["\']?(preAuthorization|x-[\w-]*auth[\w-]*|authorization)["\']?\s*:', t, re.I)
        if m:
            return m.group(1)
    return ''


def testi_js(html, base, massimo=60):
    """Scarica i file JavaScript collegati alla pagina (per cercare il nome dell'intestazione della licenza)."""
    import requests
    from urllib.parse import urljoin
    urls = []
    for u in re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', html) + re.findall(r'"(/_next/static/[^"]+\.js)"', html):
        u = urljoin(base, u)
        if u not in urls and urlsplit(u).netloc == urlsplit(base).netloc:
            urls.append(u)
    testi = []
    for u in urls[:massimo]:
        try:
            r = requests.get(u, timeout=15)
            if r.status_code == 200:
                testi.append(r.text)
        except Exception:
            pass
    return testi


# ---------------------------------------------------------------------------
# Campioni con il browser
# ---------------------------------------------------------------------------

def _manifest(net):
    for e in net:
        if re.search(r'\.(mpd|m3u8)(\?|$)', e['url']) and e.get('status') == 200:
            return e['url']
    return ''


def _token(net, host_sito):
    for e in net:
        if e.get('status') != 200 or '/api/gql/' in e['url'] or e.get('tipo') not in ('fetch', 'xhr', 'other'):
            continue
        if 'json' not in (e.get('ct') or ''):
            continue
        b = e.get('body') or ''
        try:
            j = json.loads(b)
        except Exception:
            continue
        s = json.dumps(j)
        if re.search(r'"[\w]*(token|auth)[\w]*"\s*:\s*"[^"]{20,}"', s, re.I):
            return e
    return None


def campione(s, url, grezzo_fn, attesa=8, rp=print):
    """Apre la pagina, prova i pulsanti di avvio finche parte il manifest, e ricava manifest, token e licenza."""
    h = grezzo_fn(url)
    s.vai(url, attesa=4)
    net_tot = list(s.net)
    man, tok, cliccato = _manifest(net_tot), _token(net_tot, ''), 'autoplay' if _manifest(net_tot) else ''
    tentativi = []
    if not man:
        from s4me_gen import PLAY_SELETTORI
        for sel in (PLAY_SELETTORI + ['video'])[:3]:
            try:
                loc = s.page.locator(sel)
                n = loc.count()
            except Exception:
                continue
            for i in range(min(n, 3)):
                try:
                    if not loc.nth(i).is_visible():
                        continue
                    s.net = []
                    loc.nth(i).click(timeout=3000, force=True)
                except Exception:
                    continue
                s.page.wait_for_timeout(int(attesa * 1000))
                st = s.stato()
                net = st.get('net', [])
                net_tot += net
                tentativi.append('%s #%d -> manifest %s token %s' % (sel, i, 'si' if _manifest(net) else 'no', 'si' if _token(net, '') else 'no'))
                man, tok = _manifest(net_tot), _token(net_tot, '')
                if man:
                    cliccato = '%s #%d' % (sel, i)
                    break
            if man:
                break
    try:
        s.page.screenshot(path='rapporti/riproduzione/%s.png' % re.sub(r'\W+', '_', url)[-60:])
    except Exception:
        pass
    # valori: quelli della pagina e, per le chiavi che mancano, quelli delle risposte JSON viste mentre il video partiva
    # (una pagina di elenco puo far partire un video i cui dati arrivano da una richiesta)
    valori = valori_pagina(h)
    for e in net_tot:
        if e.get('status') == 200 and 'json' in (e.get('ct') or '') and e.get('body') and e is not tok:
            for k, v in valori_pagina(e['body']).items():
                valori.setdefault(k, v)
    altri = [e['url'][:110] for e in net_tot if e.get('tipo') in ('fetch', 'xhr', 'other') and not re.search(r'google|doubleclick|permutive|tncid|adsrvr|pubmatic|adform|onetag|demdex|ipify|iab|rcsmetrics|/api/gql/', e['url'])]
    intest = ''
    if tok:
        intest = intestazione_licenza(testi_js(h, url))
    lic = None
    for e in net_tot:
        if e.get('method') == 'POST' and re.search(r'licen[cs]e|widevine|drm', e['url'], re.I) and not re.search(r'permutive|google', e['url']):
            lic = {'url': e['url'], 'hdr': e.get('hdr') or {}, 'stato': e.get('status')}
            break
    return {'url': url, 'valori': valori, 'manifest': man, 'licenza': lic, 'intestazione': intest,
            'token': ({'url': tok['url'], 'corpo': tok.get('body') or ''} if tok else None),
            'cliccato': cliccato, 'tentativi': tentativi, 'altre_richieste': altri[:25], 'html_grezzo': h}


def _gruppo(c):
    """Campioni dello stesso tipo: stesso esito (con o senza token) e stessi parametri di testo del token (per esempio VOD o LIVE)."""
    if not c.get('token'):
        return (False, ())
    _, q = senza_marcatore(c['token']['url'])
    return (True, tuple(sorted((k, v) for k, v in q if not re.fullmatch(r'[\w\-]*\d[\w\-]*', v))))


def _segmento(url):
    p = urlsplit(url).path.strip('/').split('/')
    return p[0] if p and p[0] else ''


def _condizioni(gruppi):
    """Per ogni gruppo una condizione che vale per tutti i suoi campioni e per nessuno degli altri (o None).
    Ordine di preferenza: chiave booleana col nome di un lettore (drm, live...), parte iniziale dell'indirizzo, altra chiave booleana."""
    risultato = []
    for i, lista in enumerate(gruppi):
        altri = [c for j, l in enumerate(gruppi) if j != i for c in l]
        scelta = None
        if altri:
            chiavi = set.intersection(*[{k for k, v in c['valori'].items() if v in ('true', 'false')} for c in lista])
            buone = []
            for k in sorted(chiavi):
                vals = {c['valori'][k] for c in lista}
                if len(vals) == 1 and all(a['valori'].get(k) not in vals for a in altri):
                    buone.append(('chiave', k, next(iter(vals))))
            lettore = [b for b in buone if re.search(r'drm|live|vod|stream|video|player|protect|premium', b[1], re.I)]
            segs = {_segmento(c['url']) for c in lista}
            percorso = None
            if len(segs) == 1 and segs != {''} and all(_segmento(a['url']) not in segs for a in altri):
                percorso = ('percorso', '/%s/' % next(iter(segs)))
            scelta = (lettore or [None])[0] or percorso or (buone or [None])[0]
        risultato.append(scelta)
    return risultato


def varianti_manifest(m):
    """Manifest alternativi sullo stesso sito (HLS al posto di DASH), da verificare."""
    out = []
    if re.search(r'/dash/', m) and m.endswith('manifest.mpd'):
        out.append(m.replace('/dash/', '/hls/').replace('manifest.mpd', 'master.m3u8'))
    return out


def ricetta_da_campioni(campioni, rp=print, esiste=None):
    """Una ricetta per ogni gruppo di campioni con lo stesso comportamento. esiste(url) dice se un indirizzo risponde."""
    gruppi = {}
    for c in campioni:
        if not c['manifest']:
            rp('  campione senza manifest: %s' % c['url'])
            continue
        gruppi.setdefault(_gruppo(c), []).append(c)
    liste = list(gruppi.values())
    condizioni = _condizioni(liste)
    ricette = []
    for lista, cond in zip(liste, condizioni):
        con_token = bool(lista[0].get('token'))
        migliore, punti = None, -1
        for c in lista:
            mod = impara_url(c['manifest'], c['valori'])
            if not mod:
                continue
            ok = sum(1 for d in lista if applica(mod, d['valori']) == d['manifest'])
            if ok > punti:
                migliore, punti = mod, ok
        if not migliore:
            rp('  nessun modello di manifest per il gruppo %s' % ('con token' if con_token else 'senza token'))
            continue
        ric = {'token': None, 'licenza': None, 'manifest': migliore, 'campioni': len(lista), 'riprodotti': punti,
               'esempio': lista[0]['url'], 'condizione': cond}
        if con_token:
            c0 = lista[0]
            ric['token'] = impara_token(c0['token']['url'], c0['valori'], c0['token']['corpo'])
            ric['licenza'] = trova_licenza(c0['valori'])
            nome = c0.get('intestazione') or ''
            if c0.get('licenza') and c0['licenza'].get('hdr'):
                for hk, hv in c0['licenza']['hdr'].items():
                    if hv and hv in json.dumps(c0['token']['corpo']) and not nome.lower() == hk.lower():
                        nome = hk
            ric['intestazione'] = nome
        elif esiste:
            for v in varianti_manifest(lista[0]['manifest']):
                mod = impara_url(v, lista[0]['valori'])
                if mod and applica(mod, lista[0]['valori']) == v and esiste(v):
                    rp('  preferisco la variante %s' % v[:100])
                    ric['manifest'] = mod
                    break
        ricette.append(ric)
    # prima le ricette con condizione, poi quella senza
    ricette.sort(key=lambda r: r['condizione'] is None)
    return ricette


FUNZIONI_VIDEO = r'''
RICETTE_VIDEO = __RICETTE__
DRM_SISTEMA = 'com.widevine.alpha'


def _token_video(tk, valori):
    url = indirizzo_token(tk, valori)
    if not url:
        return ''
    try:
        j = json.loads(httptools.downloadpage(url, headers=headers).data)
    except Exception as e:
        logger.error('token non ottenuto %s' % e)
        return ''
    return j.get(tk['campo']) or j.get('preAuthToken') or j.get('token') or j.get('auth') or ''


def findvideos(item):
    support.info(item)
    valori = valori_pagina(_pagina(item.url))
    for ric in RICETTE_VIDEO:
        if not condizione_ok(ric.get('condizione'), item.url, valori):
            continue
        url = applica(ric['manifest'], valori)
        if not url:
            continue
        it = item.clone(title='Direct', server='directo', url=url, action='play')
        if ric.get('token'):
            token = _token_video(ric['token'], valori)
            licenza = licenza_url(valori.get(ric['licenza']), DRM_SISTEMA)
            if token and licenza:
                it.drm = DRM_SISTEMA
                it.license = '%s|%s=%s&Origin=%s&Referer=%s/|R{SSM}|' % (licenza, ric['intestazione'], token, host, host + '/')
        return support.server(it, itemlist=[it], Download=False, Videolibrary=False)
    return support.server(item, headers=headers)
'''


def codice_canale(ricette):
    """Sorgente di findvideos (con le ricette) per il canale generato."""
    import pprint
    return FUNZIONI_VIDEO.replace('__RICETTE__', pprint.pformat(ricette, width=110, sort_dicts=False))
