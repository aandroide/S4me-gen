# -*- coding: utf-8 -*-
"""Scarica alcune pagine con un browser vero e salva html, iframe e richieste di rete in pagine/.
Serve per studiare un sito dal runner GitHub quando il mio ambiente non lo raggiunge."""
import json, os, re, sys, time
from urllib.parse import urlparse

OUT = os.environ.get('PAGINE_OUT', 'pagine')


def nome_file(url):
    p = urlparse(url)
    return re.sub(r'\W+', '_', (p.netloc + p.path + ('?' + p.query if p.query else ''))).strip('_')[:80]


def main(urls, attesa=6):
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(locale='it-IT', user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36')
        for url in urls:
            pag = ctx.new_page()
            rete = []
            pag.on('response', lambda r: rete.append({'url': r.url[:300], 'status': r.status, 'tipo': r.request.resource_type,
                                                    'ct': r.headers.get('content-type', '')}))
            nome = nome_file(url)
            try:
                pag.goto(url, wait_until='domcontentloaded', timeout=45000)
                time.sleep(attesa)
                html = pag.content()
                grezzo = ''
                try:
                    grezzo = ctx.request.get(url, timeout=30000).text()
                except Exception as e:
                    grezzo = '# errore: %s' % e
                frames = [{'url': f.url, 'name': f.name} for f in pag.frames]
                open(os.path.join(OUT, nome + '.dom.html'), 'w', encoding='utf-8').write(html[:1500000])
                open(os.path.join(OUT, nome + '.grezzo.html'), 'w', encoding='utf-8').write(grezzo[:1500000])
                json.dump({'url': url, 'finale': pag.url, 'frames': frames, 'rete': rete[:300]},
                          open(os.path.join(OUT, nome + '.rete.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
                print('OK', url, len(html), 'frame:', len(frames))
            except Exception as e:
                print('ERRORE', url, e)
            pag.close()
        br.close()


if __name__ == '__main__':
    main([u for u in sys.argv[1:] if u.startswith('http')])
