# -*- coding: utf-8 -*-
"""
esplora_dati.py: per i siti che mettono i dati nella pagina (Next.js), capisce cosa sa fare il sito oltre alle liste:

  - voci di menu che sono elenchi di canali (dirette, guide tv): pagine sorelle /sezione/nome
  - elenchi completi che la pagina non mostra interi, presi dalle richieste GraphQL persistite del sito
    (gli identificativi si leggono nei file JavaScript: nome dell'operazione e codice di 16 cifre esadecimali)
  - ricerca con paginazione tramite la richiesta di ricerca del sito
  - riproduzione: manifest, token e licenza imparati dal browser (vedi riproduzione.py)

Tutto cio che trova finisce nel contesto (ctx) da cui s4me_gen.genera_dati scrive il canale.
"""
import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import dati_incorporati as di
import riproduzione as rip

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'


def percorso_di(url):
    return urlsplit(url).path.rstrip('/') or '/'


def richiedi(url, base, timeout=20):
    import requests
    try:
        r = requests.get(url, headers={'User-Agent': UA, 'Referer': base + '/', 'Accept': 'application/json'}, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


# ---------------------------------------------------------------------------
# Operazioni GraphQL persistite
# ---------------------------------------------------------------------------

def operazioni_js(testi):
    """{codice: nome} delle richieste persistite elencate nei file JavaScript (nome:"16 cifre esadecimali")."""
    ops = {}
    for t in testi:
        for m in re.finditer(r'([A-Za-z_]\w*):"([0-9a-f]{16})"', t):
            ops.setdefault(m.group(2), m.group(1))
    return ops


def codifica(variabili, separatori=(',', ':'), ordinate=True):
    t = json.dumps(variabili, separators=separatori, sort_keys=ordinate, ensure_ascii=False)
    return base64.urlsafe_b64encode(t.encode('utf-8')).decode('ascii').rstrip('=')


def _percorsi(rec):
    return {di._unisci('x://h', x['url']).split('://h')[-1].split('?')[0].rstrip('/') for x in rec}


def completa_liste(base, ops, liste_pagina, rp=print):
    """Per ogni elenco della pagina cerca la richiesta senza parametri che restituisce lo stesso elenco ma piu completo.
    liste_pagina: {percorso_pagina: [record]}. Restituisce {percorso_pagina: [codici]} (il migliore per primo)."""
    if not ops:
        return {}

    def prova(c):
        st, t = richiedi('%s/api/gql/%s' % (base, c), base)
        if st != 200 or not t.lstrip().startswith('{'):
            return c, None
        try:
            r = di.rileva_json(json.loads(t))
        except Exception:
            return c, None
        return c, r

    with ThreadPoolExecutor(8) as ex:
        risposte = [x for x in ex.map(prova, list(ops)) if x[1]]
    rp('  operazioni provate: %d | con un elenco: %d' % (len(ops), len(risposte)))
    out = {}
    for pagina, rec in liste_pagina.items():
        mie = {x['url'].split('?')[0].rstrip('/') for x in rec}
        mie |= {u.replace(base, '') for u in mie}
        migliori = []
        for c, r in risposte:
            elenco = [x for _, g in r['gruppi'] for x in g]
            comuni = len(_percorsi(elenco) & {di._unisci('x://h', u).split('://h')[-1].rstrip('/') for u in mie})
            if comuni >= 0.5 * len(rec) and len(elenco) > 1.15 * len(rec):
                migliori.append((len(elenco), c, ops[c]))
        migliori.sort(reverse=True)
        if migliori:
            n0 = migliori[0][0]
            out[pagina] = [c for n, c, _ in migliori if n >= 0.9 * n0]
            rp('  %s: la pagina mostra %d titoli, la richiesta %s (%s) ne da %d' % (
                pagina, len(rec), migliori[0][2], migliori[0][1], n0))
    return out


def trova_ricerca_ops(base, ops, rp=print):
    """Richiesta di ricerca completa (non i suggerimenti) dal nome dell'operazione. Restituisce il dizionario di ctx['search_gql'] o None."""
    cand = [(c, n) for c, n in ops.items() if re.search(r'search|ricerca', n, re.I) and not re.search(r'suggest|most|view|hbbtv', n, re.I)]
    for c, n in cand:
        for chiave in ('q', 'query', 'text', 'term', 'search', 'key'):
            var = {chiave: 'matrix'}
            st, t = richiedi('%s/api/gql/%s/%s' % (base, c, codifica(var)), base)
            if st != 200:
                continue
            try:
                r = di.rileva_json(json.loads(t))
            except Exception:
                continue
            if r and r['n'] >= 3:
                rp('Ricerca completa: operazione %s (%s), parametro "%s", %d risultati per "matrix"' % (n, c, chiave, r['n']))
                return {'esempio': '%s/api/gql/%s/%s' % (base, c, codifica(var)), 'payload': {chiave: '__TESTO__'},
                        'prefisso': '/api/gql/%s/' % c, 'separatori': (',', ':'), 'ordinate': True, 'pagine': True, 'chiave_testo': chiave}
    return None


# ---------------------------------------------------------------------------
# Esplorazione
# ---------------------------------------------------------------------------

def esplora(s, ctx, base, args, rp, cattura, grezzo_fn, pagina_elenco):
    """Riempie ctx con: menu (solo le voci utili), azioni_menu, canali_azione, elenchi_api, ricette_video."""
    import os
    rip.CARTELLA = os.path.join(getattr(args, 'out', 'canali_generati'), 'riproduzione')
    voci_ok, azioni, canali_azione = [], {}, {}
    liste_pagina, pagine_video, giocabili = {}, [], []
    pagine_viste = []

    for nome, url in ctx['menu']:
        h = grezzo_fn(url)
        pagine_viste.append(url)
        perc = percorso_di(url)
        fr = di.canali_fratelli(h, perc)
        if fr:
            voci_ok.append((nome, url))
            azioni[url] = 'canali'
            figlio = base + fr[0][1] if not fr[0][1].startswith('http') else fr[0][1]
            hf = grezzo_fn(figlio)
            pagine_viste.append(figlio)
            r = di.rileva(hf)
            gruppi = bool(r and r['firma'].get('gruppo'))
            sezione = perc.strip('/').split('/')[0]
            canali_azione[sezione] = 'peliculas' if gruppi else 'findvideos'
            rp('Voce "%s": elenco di canali %s | ogni canale apre %s' % (
                nome, [x[0] for x in fr], 'i giorni (elenco a gruppi)' if gruppi else 'il video'))
            if not gruppi:
                pagine_video += [base + p for _, p in fr]
            else:
                for _, gg in r['gruppi']:
                    for x in gg:
                        if not _e_serie(x['url']):
                            giocabili.append(di._unisci(base, x['url']))
            continue
        r = di.rileva(h)
        if r and r['n'] >= 3:
            voci_ok.append((nome, url))
            rec = [x for _, g in r['gruppi'] for x in g]
            if not r['firma'].get('gruppo'):
                liste_pagina[perc] = rec
            for x in rec:
                if not _e_serie(x['url']):
                    giocabili.append(di._unisci(base, x['url']))
            pagine_video.append(url)
            rp('Voce "%s": %d titoli nei dati della pagina' % (nome, r['n']))
        else:
            rp('Voce "%s" scartata: nessun elenco nei dati della pagina (%s)' % (nome, perc))
    if voci_ok:
        ctx['menu'] = voci_ok
    ctx['azioni_menu'] = azioni
    ctx['canali_azione'] = canali_azione

    # elenchi completi dalle richieste del sito
    h0 = grezzo_fn(pagina_elenco)
    testi = rip.testi_js(h0, base)
    ops = operazioni_js(testi)
    rp('Richieste persistite trovate nei file JavaScript:', len(ops))
    ctx['operazioni'] = ops
    if liste_pagina:
        ctx['elenchi_api'] = completa_liste(base, ops, liste_pagina, rp)

    # titoli mostrati in altre pagine ma assenti dall'elenco completo
    if ctx.get('elenchi_api'):
        try:
            trova_extra(ctx, base, grezzo_fn, pagine_viste, rp)
        except BaseException as ex:
            rp('Ricerca di titoli mancanti non completata: %s' % str(ex)[:100])

    # ricerca completa
    ric = trova_ricerca_ops(base, ops, rp)
    if ric:
        ctx['search_gql'] = ric

    # riproduzione
    campioni = []
    visti = set()
    cand = []
    for u in pagine_video + diversi(giocabili, base, 4):
        if u not in visti:
            visti.add(u)
            cand.append(u)
    rp('Pagine in cui provo la riproduzione:', len(cand))
    for u in cand[:10]:
        try:
            c = rip.campione(s, u, grezzo_fn, attesa=8, rp=rp)
        except BaseException as ex:
            rp('  riproduzione non provata in %s: %s' % (u, str(ex)[:80]))
            continue
        campioni.append(c)
        rp('  %s -> manifest %s | token %s' % (u, 'si' if c['manifest'] else 'no', 'si' if c['token'] else 'no'))
    cattura['riproduzione'] = {'campioni': [{k: v for k, v in c.items() if k not in ('html_grezzo', 'valori')} for c in campioni]}
    if campioni:
        def esiste(u):
            st, _ = richiedi(u, base)
            return st == 200
        ricette = rip.ricetta_da_campioni(campioni, rp, esiste)
        for ric in ricette:
            sel = [c for c in campioni if c['manifest'] and rip.condizione_ok(ric['condizione'], c['url'], c['valori'])]
            rp('  ricetta (%s): condizione %s | campioni che la soddisfano: %d | manifest ricostruito: %s' % (
                'DRM con token' if ric.get('token') else 'senza DRM', ric['condizione'], len(sel),
                [bool(rip.applica(ric['manifest'], c['valori'])) for c in sel]))
        ctx['ricette_video'] = ricette
        rp('Ricette di riproduzione:', len(ricette))
        try:
            verifica_ricette(ctx, base, grezzo_fn, giocabili, rp)
        except BaseException as ex:
            rp('Verifica delle ricette non completata: %s' % str(ex)[:100])


def _risposta_video(url, base):
    """(ok, dettaglio): il manifest risponde e sembra un manifest."""
    import requests
    try:
        r = requests.get(url, headers={'User-Agent': UA, 'Referer': base + '/', 'Origin': base}, timeout=20, stream=True)
        inizio = next(r.iter_content(512), b'').decode('utf-8', 'ignore')
        return r.status_code in (200, 206) and ('#EXTM3U' in inizio or '<MPD' in inizio or '<?xml' in inizio), '%s %s' % (r.status_code, inizio[:30].replace('\n', ' '))
    except Exception as e:
        return False, str(e)[:60]


def verifica_ricette(ctx, base, grezzo_fn, giocabili, rp, massimo=24):
    """Applica le ricette a molte pagine (anche vecchie) e controlla che i manifest rispondano."""
    pagine = list(giocabili)
    # puntate di alcuni programmi dell'elenco completo
    elenco = []
    for perc, codici in (ctx.get('elenchi_api') or {}).items():
        for c in codici[:1]:
            st, t = richiedi('%s/api/gql/%s' % (base, c), base)
            try:
                r = di.rileva_json(json.loads(t))
                elenco = [x for _, g in r['gruppi'] for x in g]
            except Exception:
                pass
    for x in elenco[:8]:
        u = di._unisci(base, x['url']).rstrip('/')
        h = grezzo_fn(u + '/puntate') or grezzo_fn(u)
        r = di.rileva(h) if h else None
        if r:
            for _, g in r['gruppi']:
                pagine += [di._unisci(base, y['url']) for y in g if not _e_serie(y['url'])][-3:]
    visti, scelte = set(), []
    for u in pagine:
        if u not in visti:
            visti.add(u)
            scelte.append(u)
    passo = max(1, len(scelte) // massimo)
    scelte = scelte[::passo][:massimo]
    esito = {}
    for u in scelte:
        valori = rip.valori_pagina(grezzo_fn(u))
        for i, ric in enumerate(ctx['ricette_video']):
            if rip.condizione_ok(ric['condizione'], u, valori):
                url = rip.applica(ric['manifest'], valori)
                if not url:
                    esito.setdefault(i, []).append((u, False, 'manifest non ricostruito'))
                    break
                ok, det = _risposta_video(url, base)
                esito.setdefault(i, []).append((u, ok, det + ' | ' + url[:140]))
                break
        else:
            esito.setdefault(-1, []).append((u, False, 'nessuna ricetta per questa pagina'))
    for i, lst in sorted(esito.items()):
        rp('  verifica ricetta %s: %d pagine, %d ok' % (i, len(lst), sum(1 for x in lst if x[1])))
        for u, ok, det in lst:
            if not ok:
                rp('    NON RIESCE: %s | %s' % (u, det))
    ctx['verifica_video'] = {str(i): [sum(1 for x in l if x[1]), len(l)] for i, l in esito.items()}


def _forma(url):
    """Forma dell'indirizzo: numero di pezzi del percorso e se ha un numero in fondo."""
    p = [x for x in urlsplit(url).path.split('/') if x]
    return (len(p), bool(re.search(r'-\d{4,}$', url.split('?')[0])))


def trova_extra(ctx, base, grezzo_fn, pagine_viste, rp):
    """Per ogni elenco completo preso dalla API cerca nelle altre pagine liste dello stesso tipo con titoli in piu."""
    ctx['elenchi_extra'], ctx['ordina_elenchi'] = {}, {}
    for perc, codici in ctx['elenchi_api'].items():
        st, t = richiedi('%s/api/gql/%s' % (base, codici[0]), base)
        r = di.rileva_json(json.loads(t))
        principale = [x for _, g in r['gruppi'] for x in g]
        chiavi = {x['url'].split('?')[0].rstrip('/') for x in principale}
        forma = {_forma(di._unisci(base, x['url'])) for x in principale}
        titoli = [x['titolo'] for x in principale]
        ctx['ordina_elenchi'][perc] = titoli == sorted(titoli, key=str.lower)
        for pagina in pagine_viste:
            h = grezzo_fn(pagina)
            for lista in di.rileva_tutte(h):
                rec = lista['record']
                if not lista['firma'].get('immagine'):
                    continue
                mie = {x['url'].split('?')[0].rstrip('/') for x in rec}
                if len(mie & chiavi) < 0.3 * len(mie):
                    continue
                if {_forma(di._unisci(base, x['url'])) for x in rec} - forma:
                    continue
                nuovi = [x for x in rec if x['url'].split('?')[0].rstrip('/') not in chiavi]
                if nuovi:
                    ctx['elenchi_extra'].setdefault(perc, []).append((percorso_di(pagina), lista['firma']))
                    rp('  %s: la pagina %s mostra anche %s' % (perc, percorso_di(pagina), [x['titolo'] for x in nuovi]))
                    chiavi |= {x['url'].split('?')[0].rstrip('/') for x in nuovi}
                    break


def _e_serie(url):
    return not re.search(r'-\d{4,}/?$', url.split('?')[0])


def diversi(urls, base, n):
    """Indirizzi con la prima parte del percorso diversa, al massimo n."""
    out, visti = [], set()
    for u in urls:
        seg = urlsplit(u).path.strip('/').split('/')[0]
        if seg not in visti:
            visti.add(seg)
            out.append(u)
        if len(out) >= n:
            break
    return out
