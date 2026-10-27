# -*- coding: utf-8 -*-
"""Percorre un canale S4Me come in Kodi, con il codice vero di S4Me, e verifica che si arrivi al video.

Passi: mainlist, lista titoli, scheda, episodi, findvideos, risoluzione del server, richiesta dei primi byte del video.
Uso: python3 prova_video.py <canale> [--addon /tmp/kh/addon] [--out prove] [--host https://sito]
"""
import argparse, importlib, json, os, re, sys, time, traceback

ap = argparse.ArgumentParser()
ap.add_argument('canale')
ap.add_argument('--addon', default='/tmp/kh/addon')
ap.add_argument('--out', default='prove')
ap.add_argument('--host', default='')
ap.add_argument('--max-voci', type=int, default=3)
args = ap.parse_args()

sys.path.insert(0, '/tmp/kh'); sys.path.insert(0, args.addon)
import fake  # noqa: simula i moduli di Kodi
from platformcode import config
from core import httptools
from core.item import Item

nome = args.canale
os.makedirs(os.path.join(args.out, nome), exist_ok=True)
PAG = os.path.join(args.out, nome, 'pagine')
os.makedirs(PAG, exist_ok=True)

host = args.host
if not host:
    try:
        cj = json.load(open(os.path.join(args.addon, 'channels.json'), encoding='utf-8'))
        for sez in cj.values():
            if isinstance(sez, dict) and nome in sez:
                host = sez[nome]
    except Exception:
        pass
config.get_channel_url = lambda *a, **k: host
log = []
passi = []


def rp(*a):
    riga = ' '.join(str(x) for x in a)
    log.append(riga)
    print(riga, flush=True)


# registra tutte le richieste di rete del canale
rete = []
_orig = httptools.downloadpage


def _dl(url, *a, **k):
    t = time.time()
    r = _orig(url, *a, **k)
    try:
        corpo = r.data if isinstance(r.data, str) else str(r.data)
        rete.append({'url': url if isinstance(url, str) else str(url), 'status': getattr(r, 'code', None), 'byte': len(corpo),
                     'secondi': round(time.time() - t, 1)})
        if len(rete) <= 40:
            open(os.path.join(PAG, '%02d.html' % len(rete)), 'w', encoding='utf-8').write(corpo[:300000])
            rete[-1]['file'] = 'pagine/%02d.html' % len(rete)
    except Exception:
        pass
    return r


httptools.downloadpage = _dl


def passo(titolo, f):
    rp('==', titolo)
    try:
        r = f()
        n = len(r) if hasattr(r, '__len__') else '?'
        rp('   ->', n, 'voci')
        passi.append({'passo': titolo, 'esito': 'OK' if r else 'VUOTO', 'voci': n if r else 0})
        for i in (r or [])[:4]:
            rp('     ', i.action, '|', re.sub(r'\[[^\]]*\]', '', i.title or '')[:60], '|', (i.url or '')[:100])
        return r
    except BaseException:
        rp(traceback.format_exc(limit=5))
        passi.append({'passo': titolo, 'esito': 'ERRORE', 'errore': traceback.format_exc(limit=3)[-400:]})
        return None


def video_ok(url, referer=''):
    """Chiede i primi byte come farebbe Kodi e dice se sembra un video."""
    import requests
    u, _, h = url.partition('|')
    hd = {'User-Agent': 'Mozilla/5.0'}
    for kv in h.split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            hd[k] = v
    hd['Range'] = 'bytes=0-2047'
    try:
        r = requests.get(u, headers=hd, timeout=40, stream=True, allow_redirects=True)
        ct = r.headers.get('Content-Type', '')
        corpo = next(r.iter_content(2048), b'')
        r.close()
        if r.status_code in (200, 206):
            if u.split('?')[0].endswith('.m3u8') or 'mpegurl' in ct.lower() or corpo.startswith(b'#EXTM3U'):
                return corpo.startswith(b'#EXTM3U'), 'm3u8 %s' % r.status_code
            if 'video' in ct.lower() or 'octet-stream' in ct.lower() or u.split('?')[0].endswith(('.mp4', '.mkv', '.ts')):
                return True, '%s %s' % (r.status_code, ct)
            if 'dash' in ct.lower() or corpo.lstrip().startswith(b'<?xml'):
                return True, 'mpd %s' % r.status_code
            return False, '%s %s non sembra un video' % (r.status_code, ct)
        return False, 'HTTP %s' % r.status_code
    except BaseException as ex:
        return False, 'errore %s' % str(ex)[:100]


def scendi(voci, profondita=0):
    """Segue la prima voce di ogni livello fino a trovare le voci da riprodurre."""
    if not voci or profondita > 5:
        return voci
    it = None
    for x in voci:
        if x.action in ('findvideos', 'episodios', 'check', 'peliculas', 'genres', 'menu', 'submenu', 'season', 'seasons', 'play'):
            it = x
            if x.action != 'peliculas' or profondita > 0:
                break
    if it is None:
        return voci
    if it.action == 'play':
        return voci
    f = getattr(ch, it.action, None)
    if not f:
        rp('   azione non trovata nel canale:', it.action)
        return voci
    r = passo('%s su "%s"' % (it.action, re.sub(r'\[[^\]]*\]', '', it.title or '')[:40]), lambda: f(it))
    if not r:
        return None
    if any(x.action == 'play' for x in r):
        return r
    return scendi(r, profondita + 1)


rp('Canale', nome, '| indirizzo', host)
ch = importlib.import_module('channels.' + nome)
esito = {'canale': nome, 'host': host, 'passi': passi, 'video': []}
menu = passo('mainlist', lambda: ch.mainlist(Item(channel=nome, action='mainlist')))
voci_menu = [i for i in (menu or []) if i.action in ('peliculas', 'genres', 'menu', 'submenu', 'newest')][:args.max_voci]
finale = None
for vm in voci_menu:
    lista = passo('lista "%s"' % re.sub(r'\[[^\]]*\]', '', vm.title or '')[:40], lambda: getattr(ch, vm.action)(vm))
    if not lista:
        continue
    r = scendi(lista, 0)
    if r and any(x.action == 'play' for x in r):
        finale = r
        break
if finale:
    for pl in [x for x in finale if x.action == 'play'][:3]:
        rp('== risoluzione', pl.server, (pl.url or '')[:100])
        info = {'server': pl.server, 'url': (pl.url or '')[:200]}
        try:
            if pl.server == 'directo':
                finali = [['directo', pl.url]]
            else:
                from core import servertools
                finali = servertools.resolve_video_urls_for_playing(pl.server, pl.url)[0]
                if isinstance(finali, str):
                    finali = []
        except BaseException:
            rp(traceback.format_exc(limit=3))
            finali = []
        if not finali:
            info['esito'] = 'SERVER NON RISOLVE'
        else:
            u = finali[-1][1] if isinstance(finali[-1], (list, tuple)) else finali[-1]
            ok, det = video_ok(u)
            info.update({'finale': str(u)[:200], 'esito': 'VIDEO OK' if ok else 'VIDEO NON RAGGIUNGIBILE', 'dettaglio': det})
        rp('   ->', info['esito'], info.get('dettaglio', ''))
        esito['video'].append(info)
else:
    rp('Nessuna voce da riprodurre trovata')
esito['rete'] = rete[:60]
if any(v['esito'] == 'VIDEO OK' for v in esito['video']):
    esito['verdetto'] = 'ARRIVA AL VIDEO'
elif esito['video']:
    esito['verdetto'] = 'SI FERMA AL SERVER O AL VIDEO'
else:
    ult = [p for p in passi if p['esito'] != 'OK']
    esito['verdetto'] = 'SI FERMA A: ' + (ult[0]['passo'] if ult else 'ultimo passo, nessuna voce da riprodurre')
rp('VERDETTO:', esito['verdetto'])
json.dump(esito, open(os.path.join(args.out, nome, 'esito.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(os.path.join(args.out, nome, 'log.txt'), 'w', encoding='utf-8').write('\n'.join(log))
