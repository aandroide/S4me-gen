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
    ('prima', lambda v: v.split('|')[0]),
    ('seconda', lambda v: v.split('|')[1] if '|' in v else ''),
    ('origine', lambda v: '%s://%s' % (urlsplit(v).scheme, urlsplit(v).netloc) if v.startswith('http') else ''),
]
TR = dict(TRASFORMAZIONI)


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
                    usato[j] = (k, nome)
                usato[i] = (k, nome, True)
                for j in range(i + 1, i + lung):
                    usato[j] = 'dentro'
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


def applica(modello, valori):
    out = ''
    for p in modello:
        if p[0] == 'lett':
            out += p[1]
        else:
            v = valori.get(p[1])
            if v is None:
                return None
            out += TR[p[2]](v)
    return out


def impara_token(url, valori, corpo_json):
    """Ricetta del token: indirizzo con i parametri (letterali o presi dalla pagina) e nome del campo nella risposta."""
    parti = urlsplit(url)
    base = '%s://%s%s' % (parti.scheme, parti.netloc, parti.path)
    param = []
    for k, v in parse_qsl(parti.query, keep_blank_values=True):
        if re.fullmatch(r'\d{10,13}', v):
            continue  # marcatore anti cache
        da_pagina = [c for c, x in valori.items() if x == v and c not in ('id',)]
        param.append((k, ('chiave', da_pagina[0]) if da_pagina else ('lett', v)))
    base_k = [c for c, x in valori.items() if x == base]
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
    return {'base': ('chiave', base_k[0]) if base_k else ('lett', base), 'param': param, 'campo': campo}


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
    """Apre la pagina, prova i pulsanti di avvio finche parte il manifest, e ricava manifest e token."""
    h = grezzo_fn(url)
    valori = valori_pagina(h)
    s.vai(url, attesa=4)
    net_tot = list(s.net)
    man, tok, cliccato = _manifest(net_tot), _token(net_tot, ''), 'autoplay' if _manifest(net_tot) else ''
    tentativi = []
    if not man:
        from s4me_gen import PLAY_SELETTORI
        for sel in PLAY_SELETTORI + ['video']:
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
    altri = [e['url'][:110] for e in net_tot if e.get('tipo') in ('fetch', 'xhr', 'other') and not re.search(r'google|doubleclick|permutive|tncid|adsrvr|pubmatic|adform|onetag|demdex|ipify|iab|rcsmetrics|/api/gql/', e['url'])]
    return {'url': url, 'valori': valori, 'manifest': man,
            'token': ({'url': tok['url'], 'corpo': tok.get('body') or ''} if tok else None),
            'cliccato': cliccato, 'tentativi': tentativi, 'altre_richieste': altri[:25], 'html_grezzo': h}


def ricetta_da_campioni(campioni, rp=print):
    """Una ricetta per gruppo di campioni con lo stesso comportamento (con o senza token)."""
    gruppi = {}
    for c in campioni:
        if not c['manifest']:
            rp('  campione senza manifest: %s' % c['url'])
            continue
        gruppi.setdefault(bool(c['token']), []).append(c)
    ricette = []
    for con_token, lista in gruppi.items():
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
               'esempio': lista[0]['url']}
        if con_token:
            c0 = lista[0]
            ric['token'] = impara_token(c0['token']['url'], c0['valori'], c0['token']['corpo'])
            ric['licenza'] = trova_licenza(c0['valori'])
        # condizione: chiave booleana della pagina che separa questo gruppo dall'altro
        ric['condizione'] = None
        ricette.append((con_token, ric, lista))
    # condizione tra i gruppi
    if len(ricette) > 1:
        tutti = [c for _, _, l in ricette for c in l]
        chiavi = set.intersection(*[{k for k, v in c['valori'].items() if v in ('true', 'false')} for c in tutti])
        for k in sorted(chiavi):
            sep = True
            for con, ric, lista in ricette:
                vals = {c['valori'][k] for c in lista}
                if len(vals) != 1:
                    sep = False
            if sep and len({tuple({c['valori'][k] for c in l}) for _, _, l in ricette}) == len(ricette):
                for con, ric, lista in ricette:
                    ric['condizione'] = (k, lista[0]['valori'][k])
                break
    return [r for _, r, _ in ricette]
