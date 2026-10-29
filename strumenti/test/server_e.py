# -*- coding: utf-8 -*-
"""Finto animemars: scheda, pagina /watch intermedia, dettaglio /stream, episodio con iframe, embed e playlist."""
import http.server, json, os, re, sys

AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'animemars')
PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ORIG = 'hack-roots-12ifn'


def leggi(n):
    return open(os.path.join(AQUI, n), encoding='utf-8').read()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def invia(self, corpo, ct='text/html; charset=utf-8', codice=200):
        b = corpo.encode('utf-8') if isinstance(corpo, str) else corpo
        self.send_response(codice)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split('?')[0]
        host = 'http://127.0.0.1:%d' % PORTA
        m = re.match(r'^/(watch|stream)/([^/]+)(?:/(ep-\d+))?$', p)
        if p == '/':
            return self.invia(leggi('home.html'))
        if m:
            tipo, slug, ep = m.groups()
            if tipo == 'watch':
                t = leggi('guarda.html')
            elif ep:
                t = leggi('episodio.html').replace('https://play.marscdn.org', host)
            else:
                t = leggi('serie.html')
            t = t.replace(ORIG, slug)
            if ep:
                t = re.sub(r'/ep-1\b', '/' + ep, t)
            return self.invia(t)
        if re.match(r'^/embed/\d+$', p):
            return self.invia('<html><body><video id="v" controls></video><script>'
                              'fetch(location.pathname + "/playlist" + location.search).then(r => r.json()).then(j => {'
                              'document.getElementById("v").src = j.playlist[0].sources[0].file;});</script></body></html>')
        if re.match(r'^/embed/\d+/playlist$', p):
            # come il sito vero: {"d": indirizzo in base64 con XOR del token, "p": "", "t": ""}
            import base64
            tok = (re.search(r'token=([^&]+)', self.path) or [None, ''])[1]
            url = host + '/media/ep.mp4?token=abc&expires=9'
            d = base64.b64encode(bytes(ord(c) ^ ord(tok[i % len(tok)]) for i, c in enumerate(url))).decode()
            return self.invia(json.dumps({'d': d, 'p': '', 't': ''}), 'application/json')
        if p.startswith('/media/'):
            return self.invia(b'\x00' * 2048, 'video/mp4')
        if p in ('/search', '/filter', '/az-list', '/ongoing', '/newest', '/upcoming'):
            return self.invia(leggi('home.html'))
        self.invia('404', codice=404)


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', PORTA), H).serve_forever()
