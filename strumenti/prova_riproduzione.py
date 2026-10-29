# -*- coding: utf-8 -*-
"""Apre alcune pagine con il browser, preme play e scrive in rapporti/riproduzione/ cosa e stato richiesto (manifest, token)
e la ricetta imparata. Uso: python3 strumenti/prova_riproduzione.py URL [URL ...]"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s4me_gen as g
import riproduzione as rip

OUT = 'rapporti/riproduzione'


def main(urls):
    os.makedirs(OUT, exist_ok=True)
    s = g.Sessione(headless=True, chrome=bool(os.environ.get('USA_CHROME')))
    campioni, dettagli = [], []
    try:
        for u in urls:
            try:
                c = rip.campione(s, u, g.scarica_grezzo)
            except BaseException as ex:
                print('ERRORE', u, str(ex)[:200])
                continue
            print('==', u)
            print('   manifest:', c['manifest'][:160])
            print('   licenza:', json.dumps(c.get('licenza'), ensure_ascii=False)[:600])
            print('   token:', (c['token'] or {}).get('url', '')[:160], '| cliccato:', c['cliccato'])
            for t in c['tentativi']:
                print('   tentativo:', t)
            for t in c['altre_richieste']:
                print('   richiesta:', t)
            for k in ('drm', 'geolock', 'drmContentId', 'drmTokenEndpoint', 'mainLiveUrl', 'cf_remote_url', 'cf_old_entry_id', 'hostnameCdn', 'hostnameCdnDrm'):
                if k in c['valori']:
                    print('   %s = %s' % (k, c['valori'][k][:120]))
            campioni.append(c)
            dettagli.append({k: v for k, v in c.items() if k not in ('html_grezzo',)})
        ricette = rip.ricetta_da_campioni(campioni)
        print(json.dumps(ricette, indent=1, ensure_ascii=False)[:4000])
        json.dump({'campioni': dettagli, 'ricette': ricette}, open(os.path.join(OUT, 'ricette.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    finally:
        s.chiudi()


if __name__ == '__main__':
    main(sys.argv[1:])
