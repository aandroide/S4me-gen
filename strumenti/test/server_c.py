import json, base64, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = 8103
FILM = ["Fight Club", "Birdman", "Stay", "Ad Astra", "Shortbus", "Unsane", "Tarzan", "Zorro"]
SERIE = ["The Flash", "Hillbillies", "Dark", "Lost"]
NAV = '<nav><a href="/film">Film</a> <a href="/serie-tv">Serie TV</a> <a href="/privacy">Privacy</a></nav>'

LISTA_JS = '''
async function g(op, v){const r=await fetch('/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operationName:op,variables:v,query:'query '+op+'{x}'})});return r.json();}
async function carica(){
  const tipo=document.body.dataset.tipo, base=document.body.dataset.base;
  const ord=document.getElementById('ord').value;
  const j=await g('GetPopularTitles',{type:tipo,sort:ord,first:6,after:''});
  const app=document.getElementById('app'); app.innerHTML='';
  j.data.popularTitles.edges.forEach(e=>{const n=e.node,c=n.content;const d=document.createElement('div');d.className='tile';
    d.innerHTML='<a href="'+c.fullPath+'"><img src="'+c.posterUrl+'"><h4>'+c.title+'</h4></a>';app.appendChild(d)});
}
document.getElementById('ord').addEventListener('change',carica); carica();
'''
def pagina_lista(tipo, base):
    return ('<html><head><title>L</title></head><body data-tipo="%s" data-base="%s">%s<select id="ord"><option value="POPULAR">Popolari</option><option value="RECENT">Recenti</option></select><div id="app"></div><script>%s</script></body></html>'
            % (tipo, base, NAV, LISTA_JS))
PLAY_JS = '''
async function g(op, v){const r=await fetch('/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operationName:op,variables:v,query:'mutation '+op+'{x}'})});return r.json();}
async function play(id){const j=await g('GetPlay',{input:{offerId:btoa('of|'+id+':IT:jwt:free:hd'),drmType:'widevine'}});
  const s=j.data.getPlayInformation.streams[0]; await fetch(s.manifestUrlDash); await fetch(s.drmConfigs[0].laURL,{method:'POST',body:'abc'});}
'''
def det_film(i):
    return '<html><body>%s<h1>Film</h1><button onclick="play(\'tm%s\')">Guarda gratis</button><script>%s</script></body></html>' % (NAV, i, PLAY_JS)
def det_serie(i):
    js = PLAY_JS + '''
(async()=>{const j=await g('GetEpisodes',{id:'ts%s'});const app=document.getElementById('eps');
 j.data.node.episodes.forEach(e=>{const d=document.createElement('div');d.className='ep';
  d.innerHTML='<span>'+e.content.seasonNumber+'x'+e.content.episodeNumber+' '+e.content.title+'</span> <button onclick="play(\\''+e.id+'\\')">Guarda gratis</button>';app.appendChild(d)});})();
''' % i
    return '<html><body>%s<h1>Serie</h1><div id="eps"></div><script>%s</script></body></html>' % (NAV, js)

def nodo(i, tipo):
    t = 'Movie' if tipo == 'MOVIE' else 'Show'
    L = FILM if tipo == 'MOVIE' else SERIE
    nome = L[i % len(L)] + ('' if i < len(L) else ' %d' % i)
    base = '/film/' if tipo == 'MOVIE' else '/serie-tv/'
    return {'node': {'__typename': t, 'id': ('tm' if tipo == 'MOVIE' else 'ts') + str(i),
                     'content': {'title': nome, 'fullPath': base + str(i), 'originalReleaseYear': 1990 + i,
                                 'shortDescription': 'Trama lunga abbastanza per essere riconosciuta %d' % i,
                                 'posterUrl': '/img/%d.jpg' % i}}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _s(self, body, ct='text/html; charset=utf-8', code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); raw = self.rfile.read(n).decode()
        if self.path != '/graphql': return self._s('lic', 'application/octet-stream')
        j = json.loads(raw); op = j['operationName']; v = j['variables']
        if op == 'GetPopularTitles':
            if v['sort'] not in ('POPULAR', 'RECENT', 'ALPHABETICAL'):
                return self._s(json.dumps({'errors': [{'message': 'invalid enum'}]}), 'application/json')
            off = {'POPULAR': 0, 'RECENT': 10, 'ALPHABETICAL': 20}[v['sort']]
            ed = [nodo(off + i, v['type']) for i in range(6)]
            return self._s(json.dumps({'data': {'popularTitles': {'edges': ed, 'pageInfo': {'endCursor': 'c1', 'hasNextPage': False}}}}), 'application/json')
        if op == 'GetEpisodes':
            eps = [{'id': 'tse%s_%d' % (v['id'], k), 'content': {'title': 'Ep %d' % k, 'seasonNumber': 1 + k // 3, 'episodeNumber': 1 + k % 3}} for k in range(6)]
            return self._s(json.dumps({'data': {'node': {'episodes': eps}}}), 'application/json')
        if op == 'GetPlay':
            oid = base64.b64decode(v['input']['offerId']).decode().split('|')[1].split(':')[0]
            b = 'http://127.0.0.1:%d' % PORT
            if oid in ('tm1', 'tm11'):
                return self._s(json.dumps({'data': {'getPlayInformation': {'streams': [], 'offer': {'streamUrlExternalPlayer': b + '/clear/' + oid + '/index.m3u8'}}}}), 'application/json')
            return self._s(json.dumps({'data': {'getPlayInformation': {'streams': [{'manifestUrlDash': b + '/media/' + oid + '/m.mpd', 'drmConfigs': [{'laURL': b + '/drm/license?playbackId=' + oid}]}]}}}), 'application/json')
        return self._s('{}', 'application/json')
    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/': return self._s('<html><body>%s<h1>Home</h1></body></html>' % NAV)
        if p == '/film': return self._s(pagina_lista('MOVIE', '/film'))
        if p == '/serie-tv': return self._s(pagina_lista('SHOW', '/serie-tv'))
        if p.startswith('/film/'): return self._s(det_film(p.split('/')[-1]))
        if p.startswith('/serie-tv/'): return self._s(det_serie(p.split('/')[-1]))
        if p.endswith('.mpd'): return self._s('<MPD/>', 'application/dash+xml')
        if p.endswith('.jpg'): return self._s(b'\xff', 'image/jpeg')
        return self._s('', code=404)

if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
