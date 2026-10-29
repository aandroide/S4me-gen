# -*- coding: utf-8 -*-
"""Confronta due versioni dello stesso canale S4Me (per esempio quella scritta a mano e quella generata) sul sito vero.

Percorre il menu di tutte e due con il codice vero di S4Me (Kodi simulato), pagina per pagina, e confronta: le pagine raggiunte,
quante voci ha ciascuna, gli indirizzi delle voci e, per un campione di contenuti, il video (manifest, DRM, licenza).
Uso: python3 confronta_canali.py riferimento.py generato.py --host https://sito [--out rapporti/confronto]
"""
import argparse, importlib, json, os, re, shutil, sys, traceback

KH = os.environ.get('KH', '/tmp/kh')
ap = argparse.ArgumentParser()
ap.add_argument('riferimento')
ap.add_argument('generato')
ap.add_argument('--host', required=True)
ap.add_argument('--addon', default=os.path.join(KH, 'addon'))
ap.add_argument('--out', default='rapporti/confronto')
ap.add_argument('--profondita', type=int, default=4)
ap.add_argument('--larghezza', type=int, default=3)
a = ap.parse_args()

sys.path.insert(0, KH)
sys.path.insert(0, a.addon)
import fake  # noqa
from platformcode import config
from core.item import Item

config.get_channel_url = lambda *x, **k: a.host
host = a.host.rstrip('/')


def carica(percorso, nome):
    dest = os.path.join(a.addon, 'channels')
    shutil.copy(percorso, os.path.join(dest, nome + '.py'))
    js = os.path.splitext(percorso)[0] + '.json'
    if os.path.exists(js):
        t = open(js, encoding='utf-8').read()
        try:
            j = json.loads(t)
            j['id'] = nome
            t = json.dumps(j, ensure_ascii=False, indent=2)
        except Exception:
            pass
        open(os.path.join(dest, nome + '.json'), 'w', encoding='utf-8').write(t)
    m = importlib.import_module('channels.' + nome)
    m.host = host
    return m


def pulito(t):
    return re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', t or '').strip()


def perc(u):
    return re.sub(r'^https?://[^/]+', '', u or '').split('?')[0].rstrip('/')


def esplora(mod, nome):
    nodi, foglie, errori = {}, [], []
    try:
        top = mod.mainlist(Item(channel=nome)) or []
    except BaseException:
        return nodi, foglie, ['mainlist: ' + traceback.format_exc(limit=2)[-200:]]
    coda = [(i, 0) for i in top]
    while coda:
        it, d = coda.pop(0)
        az = it.action
        if az in ('findvideos', 'play'):
            foglie.append(it)
            continue
        if not az or az in ('search', 'channel_config') or getattr(it, 'nextPage', False) and d > 0 and False:
            continue
        f = getattr(mod, az, None)
        if not f:
            continue
        try:
            figli = f(it) or []
        except BaseException:
            errori.append('%s %s: %s' % (az, it.url, traceback.format_exc(limit=1)[-120:]))
            continue
        chiave = perc(it.url) + ('#' + (getattr(it, 'gruppo', '') or getattr(it, 'day', '') or '') if getattr(it, 'gruppo', '') or getattr(it, 'day', '') else '')
        if chiave and chiave not in nodi:
            nodi[chiave] = {'n': len(figli), 'urls': [perc(c.url) for c in figli if c.url], 'titoli': [pulito(c.title) for c in figli]}
        if d + 1 < a.profondita:
            for c in figli[:a.larghezza]:
                coda.append((c, d + 1))
        for c in figli:
            if c.action in ('findvideos', 'play') and len(foglie) < 400:
                foglie.append(c)
    return nodi, foglie, errori


def video(mod, nome, url):
    try:
        r = mod.findvideos(Item(channel=nome, url=url, fulltitle='x')) or []
    except BaseException:
        return [{'errore': traceback.format_exc(limit=1)[-120:]}]
    out = []
    for v in r:
        lic = getattr(v, 'license', '') or ''
        base, _, resto = lic.partition('|')
        intest = [x.split('=')[0] for x in resto.split('&') if '=' in x][:1]
        out.append({'server': v.server, 'url': v.url, 'drm': getattr(v, 'drm', ''), 'licenza': base,
                    'intestazione': (intest[0].lower() if intest else ''), 'con_token': bool(re.search(r'=eyJ|=[A-Za-z0-9_\-.]{40,}', lic))})
    return out


A = carica(a.riferimento, 'confr_rif')
B = carica(a.generato, 'confr_gen')
na, fa, ea = esplora(A, 'confr_rif')
nb, fb, eb = esplora(B, 'confr_gen')

righe = ['# Confronto dei canali', '', 'Riferimento: `%s`' % a.riferimento, 'Generato: `%s`' % a.generato, 'Sito: %s' % host, '']
solo_a = sorted(set(na) - set(nb))
solo_b = sorted(set(nb) - set(na))
comuni = sorted(set(na) & set(nb))
righe += ['## Pagine raggiunte', '', 'In tutte e due: %d | solo nel riferimento: %d | solo nel generato: %d' % (len(comuni), len(solo_a), len(solo_b)), '']
uguali = [k for k in comuni if na[k]['urls'] == nb[k]['urls']]
righe += ['Pagine con le stesse voci negli stessi indirizzi: %d su %d' % (len(uguali), len(comuni)), '']
for k in comuni:
    if na[k]['urls'] != nb[k]['urls']:
        sa, sb = set(na[k]['urls']), set(nb[k]['urls'])
        righe.append('- `%s`: riferimento %d voci, generato %d voci | solo riferimento: %d | solo generato: %d' % (k, na[k]['n'], nb[k]['n'], len(sa - sb), len(sb - sa)))
        for u in sorted(sa - sb)[:3]:
            righe.append('    solo riferimento: %s' % u)
        for u in sorted(sb - sa)[:3]:
            righe.append('    solo generato: %s' % u)
if solo_a:
    righe += ['', 'Pagine solo nel riferimento: ' + ', '.join('`%s`' % x for x in solo_a[:20])]
if solo_b:
    righe += ['', 'Pagine solo nel generato: ' + ', '.join('`%s`' % x for x in solo_b[:20])]
if ea or eb:
    righe += ['', '## Errori', ''] + ['- riferimento: ' + e for e in ea[:5]] + ['- generato: ' + e for e in eb[:5]]

# video: contenuti raggiunti da tutte e due, uno per tipo di indirizzo
ua = {perc(i.url): i.url for i in fa}
ub = {perc(i.url): i.url for i in fb}
comuni_v = [u for u in ua if u in ub]
scelti, visti = [], set()
for u in comuni_v:
    k = u.strip('/').split('/')[0] + '/' + (u.strip('/').split('/')[1] if u.count('/') > 2 else '')
    if k not in visti:
        visti.add(k)
        scelti.append(u)
for u in comuni_v:
    if len(scelti) >= 10:
        break
    if u not in scelti:
        scelti.append(u)
scelti = scelti[:10]
righe += ['', '## Video', '', 'Contenuti raggiunti da tutte e due: %d (provati %d)' % (len(comuni_v), len(scelti)), '']
ok_v = 0
for u in scelti:
    va, vb = video(A, 'confr_rif', ua[u]), video(B, 'confr_gen', ub[u])
    stesso = va == vb
    ok_v += stesso
    righe.append('- %s `%s`' % ('UGUALE' if stesso else 'DIVERSO', u))
    if not stesso:
        righe.append('    riferimento: %s' % json.dumps(va)[:400])
        righe.append('    generato: %s' % json.dumps(vb)[:400])
    elif va:
        righe.append('    %s | %s | DRM %s | token %s' % (va[0].get('server'), va[0].get('url', '')[:110], va[0].get('drm') or 'no', va[0].get('con_token')))
righe += ['', '## Esito', '', ('IDENTICI: stesse pagine, stesse voci, stessi video.' if (not solo_a and not solo_b and len(uguali) == len(comuni) and ok_v == len(scelti))
                              else 'DIFFERENZE: vedi sopra (pagine uguali %d/%d, video uguali %d/%d).' % (len(uguali), len(comuni), ok_v, len(scelti)))]
os.makedirs(a.out, exist_ok=True)
nome_out = os.path.splitext(os.path.basename(a.riferimento))[0]
open(os.path.join(a.out, nome_out + '.md'), 'w', encoding='utf-8').write('\n'.join(righe) + '\n')
print('\n'.join(righe))
