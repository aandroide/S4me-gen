import sys, importlib, traceback
sys.path.insert(0,'/tmp/kh'); sys.path.insert(0,'/tmp/kh/addon')
import fake
from platformcode import config
HOST = sys.argv[2] if len(sys.argv)>2 else 'http://127.0.0.1:8765'
config.get_channel_url = lambda *a, **k: HOST
from core.item import Item
nome = sys.argv[1]
ch = importlib.import_module('channels.' + nome)
def mostra(l, n=4):
    print('  ->', len(l), 'voci')
    for i in l[:n]:
        print('    ', i.action, '|', i.title[:60].replace('\n',' '), '|', i.url[:90] if i.url else '', '|', i.contentType)
def prova(titolo, f):
    print('==', titolo)
    try:
        r = f(); mostra(r); return r
    except Exception:
        traceback.print_exc(limit=6)
m = prova('mainlist', lambda: ch.mainlist(Item(channel=nome, action='mainlist')))
voce = [i for i in (m or []) if i.action == 'peliculas']
if voce:
    p = prova('peliculas ' + voce[0].title, lambda: ch.peliculas(voce[0]))
    if p:
        sch = p[0]
        e = prova('apri scheda ' + sch.title[:40] + ' (' + sch.action + ')', lambda: getattr(ch, sch.action)(sch))
        if e:
            ep = [x for x in e if x.action == 'findvideos']
            if ep:
                prova('findvideos ' + ep[0].title[:30], lambda: ch.findvideos(ep[0]))
