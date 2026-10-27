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
ap.add_argument('--voce', default='', help='prova solo le voci di menu il cui titolo contiene questo testo')
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
        if re.sub(r'\[[^\]]*\]', '', x.title or '').strip().endswith('>') and len(voci) == 1:
            rp('   la lista non ha titoli: c e solo la pagina successiva')
            return None
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
voci_menu = [i for i in (menu or []) if i.action in ('peliculas', 'genres', 'menu', 'submenu', 'newest')][:50]
if args.voce:
    voci_menu = [v for v in voci_menu if args.voce.lower() in re.sub(r'\[[^\]]*\]', '', v.title or '').lower()]
voci_menu = voci_menu[:args.max_voci]
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
    giocabili = [x for x in finale if x.action == 'play']
    giocabili = [x for x in giocabili if 'youtube' not in (x.url or '') and x.server != 'youtube'] or giocabili
    for pl in giocabili[:3]:
        rp('== risoluzione', pl.server, (pl.url or '')[:100])
        info = {'server': pl.server, 'url': (pl.url or '')[:200]}
        try:
            if pl.server == 'directo':
                finali = [['directo', pl.url]]
            else:
                from core import servertools
                import concurrent.futures as cf
                ex_ = cf.ThreadPoolExecutor(max_workers=1)
                fut = ex_.submit(servertools.resolve_video_urls_for_playing, pl.server, pl.url)
                try:
                    finali = fut.result(timeout=90)[0]
                except cf.TimeoutError:
                    info['nota'] = 'il server non risponde entro 90 secondi'
                    finali = []
                ex_.shutdown(wait=False, cancel_futures=True)
                if isinstance(finali, str):
                    info['nota'] = finali[:200]
                    finali = []
        except BaseException:
            rp(traceback.format_exc(limit=3))
            finali = []
        if not finali:
            info['modulo_server'] = os.path.exists(os.path.join(args.addon, 'servers', '%s.py' % pl.server)) or pl.server == 'directo'
            info['esito'] = 'SERVER NON RISOLVE' if info['modulo_server'] else 'SERVER NON SUPPORTATO DA S4ME'
            try:
                import requests as _rq
                rr = _rq.get(pl.url.partition('|')[0], timeout=30, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36', 'Referer': host.rstrip('/') + '/', 'Accept-Language': 'it-IT,it;q=0.9'})
                info['pagina_server'] = {'status': rr.status_code, 'inizio': rr.text[:300]}
                if rr.status_code in (403, 429, 503) or 'you have been blocked' in rr.text or 'Just a moment' in rr.text:
                    info['esito'] = 'NON VERIFICABILE DA GITHUB (il server del video blocca l\'IP: HTTP %s)' % rr.status_code
            except BaseException:
                pass
            if pl.server == 'vidxgo':
                # l'API del lettore: /t/<id> risponde con un JSON che contiene l'indirizzo del flusso
                try:
                    import requests as _rq
                    tid = pl.url.rstrip('/').split('/vidxgo.co/')[-1]
                    for hd in ({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0', 'Referer': pl.url, 'Accept': 'application/json, text/plain, */*'},
                               {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0', 'Referer': host.rstrip('/') + '/', 'Origin': host.rstrip('/'), 'Accept': '*/*'}):
                        rr = _rq.get('https://v.vidxgo.co/t/' + tid, headers=hd, timeout=30)
                        info.setdefault('api_t', []).append({'referer': hd['Referer'], 'status': rr.status_code, 'inizio': rr.text[:300]})
                        rp('   api /t/', tid, 'referer', hd['Referer'], '->', rr.status_code, rr.text[:120].replace('\n', ' '))
                except BaseException as ex:
                    rp('   api /t/ errore', str(ex)[:100])
        else:
            u = finali[-1][1] if isinstance(finali[-1], (list, tuple)) else finali[-1]
            ok, det = video_ok(u)
            info.update({'finale': str(u)[:200], 'esito': 'VIDEO OK' if ok else 'VIDEO NON RAGGIUNGIBILE', 'dettaglio': det})
        rp('   ->', info['esito'], info.get('dettaglio', ''), info.get('nota', ''))
        esito['video'].append(info)
else:
    rp('Nessuna voce da riprodurre trovata')
esito['rete'] = rete[:60]
if any(v['esito'] == 'VIDEO OK' for v in esito['video']):
    esito['verdetto'] = 'ARRIVA AL VIDEO'
elif esito['video']:
    esito['verdetto'] = 'SI FERMA AL SERVER O AL VIDEO: ' + esito['video'][0]['esito']
else:
    ult = [p for p in passi if p['esito'] != 'OK']
    esito['verdetto'] = 'SI FERMA A: ' + (ult[0]['passo'] if ult else 'ultimo passo, nessuna voce da riprodurre')
rp('VERDETTO:', esito['verdetto'])
json.dump(esito, open(os.path.join(args.out, nome, 'esito.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(os.path.join(args.out, nome, 'log.txt'), 'w', encoding='utf-8').write('\n'.join(log))
