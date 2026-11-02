# -*- coding: utf-8 -*-
"""Percorre le chiamate del canale discoveryplus e scrive struttura e risultati in rapporti/prove/discoveryplus/."""
import json, os, uuid, collections, requests

OUT = 'rapporti/prove/discoveryplus'
os.makedirs(OUT, exist_ok=True)
LOG = open(OUT + '/log.txt', 'w', encoding='utf-8')
def p(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n'); LOG.flush()

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
host = 'https://www.discoveryplus.com/it'
s = requests.Session()
s.headers.update({'User-Agent': UA, 'Referer': host, 'Origin': 'https://www.discoveryplus.com'})
deviceId = uuid.uuid4().hex

def get(url, **kw):
    try:
        r = s.get(url, timeout=30, **kw)
    except Exception as e:
        p('ERRORE', url[:120], e); return None, None
    p('GET', r.status_code, url[:140])
    try:
        return r, r.json()
    except Exception:
        p('  non json:', r.text[:200].replace('\n', ' '))
        return r, None

def struttura(d, nome):
    inc = d.get('included', []) if isinstance(d, dict) else []
    cnt = collections.Counter(x.get('type') for x in inc)
    p('  %s: chiavi=%s  included=%s' % (nome, list(d.keys()) if isinstance(d, dict) else type(d), dict(cnt)))
    visti = set()
    for x in inc:
        t = x.get('type')
        if t in visti: continue
        visti.add(t)
        p('    tipo %s attributi=%s relazioni=%s' % (t, sorted((x.get('attributes') or {}).keys())[:25], sorted((x.get('relationships') or {}).keys())[:15]))
    json.dump(d, open(OUT + '/' + nome + '.json', 'w', encoding='utf-8'), ensure_ascii=False)

p('== 1 realm-config')
r, d = get('https://prod-realmservice.mercury.dnitv.com/realm-config/www.discoveryplus.com%2Fit%2Fepg')
if not d:
    raise SystemExit
p('  chiavi', list(d.keys()), 'domain=', d.get('domain'))
domain = 'https://' + d['domain']

p('== 2 token')
r, d = get('{}/token?deviceId={}&realm=dplay&shortlived=true'.format(domain, deviceId))
try:
    token = d['data']['attributes']['token']
    p('  token ok, lunghezza', len(token))
except Exception as e:
    p('  token NON letto:', e, str(d)[:300]); raise SystemExit
s.headers.update({'Cookie': 'st={}'.format(token), 'content-type': 'application/json',
                  'x-disco-client': 'WEB:UNKNOWN:dplus_us:2.46.0', 'x-disco-params': 'realm=dplay,siteLookupKey=dplus_it'})

p('== 3 dirette (routes/home)')
r, d = get(domain + '/cms/routes/home?include=default&decorators=playbackAllowed')
canale = None
if d:
    struttura(d, 'home')
    ch = [k for k in d.get('included', []) if k.get('type') == 'channel']
    p('  canali totali', len(ch))
    for k in ch[:60]:
        a = k.get('attributes', {})
        p('   canale', a.get('name'), 'live=', a.get('hasLiveStream'), 'packages=', a.get('packages'), 'alt=', a.get('alternateId'))
    live = [k for k in ch if k.get('attributes', {}).get('hasLiveStream') and 'Free' in k.get('attributes', {}).get('packages', [])]
    p('  dirette Free', len(live))
    if live: canale = live[0]

p('== 4 programmi (routes/browse)')
r, d = get(domain + '/cms/routes/browse?include=default')
tutti = None
if d:
    struttura(d, 'browse')
    links = [k for k in d.get('included', []) if k.get('type') == 'link']
    p('  link totali', len(links))
    for k in links[:40]:
        a = k.get('attributes', {})
        p('   link', a.get('title', a.get('name')), 'packages=', a.get('packages'))
        if (a.get('title', a.get('name')) == 'Tutti') and 'Free' in a.get('packages', []):
            tutti = k['relationships']['linkedContent']['data']['id']
    p('  id Tutti', tutti)

show = None
if tutti:
    p('== 5 collezione Tutti')
    r, d = get('{}/cms/collections/{}?include=default'.format(domain, tutti))
    if d:
        struttura(d, 'tutti')
        shows = [k for k in d.get('included', []) if k.get('type') == 'show']
        free = [k for k in shows if 'Free' in str(k.get('relationships', {}).get('contentPackages', {}).get('data', [])) and k['attributes'].get('episodeCount')]
        p('  show', len(shows), 'free con episodi', len(free))
        for k in free[:5]:
            p('   ', k['attributes'].get('name'), k['attributes'].get('alternateId'), k['attributes'].get('seasonNumbers'))
        if free: show = free[0]

ep = None
if show:
    p('== 6 stagioni', show['attributes']['alternateId'])
    r, d = get('{}/cms/routes/show/{}?include=default'.format(domain, show['attributes']['alternateId']))
    if d:
        struttura(d, 'show')
        cols = [k for k in d.get('included', []) if k.get('type') == 'collection']
        for k in cols[:10]:
            comp = (k.get('attributes') or {}).get('component') or {}
            p('   collezione', k.get('id'), (k.get('attributes') or {}).get('title'), 'component=', list(comp.keys())[:8])
        for k in cols:
            comp = (k.get('attributes') or {}).get('component') or {}
            if 'filters' in comp:
                f = comp['filters'][0]
                opt = f['options'][0]
                p('  filtro', f.get('id') if isinstance(f, dict) else '', 'opzione0', opt, 'mandatoryParams=', comp.get('mandatoryParams'))
                r, d2 = get('{}/cms/collections/{}?include=default&{}&{}'.format(domain, k['id'], opt['parameter'], comp['mandatoryParams']))
                if d2:
                    struttura(d2, 'episodi')
                    vids = [x for x in d2.get('included', []) if x.get('type') == 'video']
                    free = [x for x in vids if 'Free' in str(x.get('relationships', {}).get('contentPackages', {}).get('data', []))]
                    p('  video', len(vids), 'free', len(free))
                    if free: ep = free[0]
                break

def playback(content, ident, nome):
    post = {content + 'Id': ident,
            'deviceInfo': {'adBlocker': 'true', 'drmSupported': 'true', 'hwDecodingCapabilities': [], 'screen': {'width': 1920, 'height': 1080}, 'player': {'width': 1920, 'height': 1080}},
            'wisteriaProperties': {'advertiser': {'firstPlay': 0, 'fwIsLat': 0}, 'device': {'browser': {'name': 'chrome', 'version': '124'}, 'type': 'desktop'},
                                   'platform': 'desktop', 'product': 'dplus_emea', 'sessionId': deviceId,
                                   'streamProvider': {'suspendBeaconing': 0, 'hlsVersion': 6, 'pingConfig': 1}}}
    try:
        r = s.post('{}/playback/v3/{}PlaybackInfo'.format(domain, content), json=post, timeout=30)
    except Exception as e:
        p('ERRORE playback', e); return
    p('POST', r.status_code, content + 'PlaybackInfo')
    try:
        d = r.json()
    except Exception:
        p('  non json', r.text[:200]); return
    json.dump(d, open(OUT + '/playback_' + nome + '.json', 'w', encoding='utf-8'), ensure_ascii=False)
    at = (d.get('data') or {}).get('attributes') or {}
    st = (at.get('streaming') or [{}])[0]
    p('  attributi', list(at.keys()), 'streaming0 chiavi', list(st.keys()), 'drm', (st.get('protection') or {}).get('drmEnabled'), 'url', str(st.get('url'))[:100])
    if not at: p('  risposta', str(d)[:400])

if ep:
    p('== 7 riproduzione episodio', ep['attributes'].get('name'))
    playback('video', ep['id'], 'episodio')
if canale:
    p('== 8 riproduzione diretta', canale['attributes'].get('name'))
    playback('channel', canale['id'], 'diretta')
p('FINE')
