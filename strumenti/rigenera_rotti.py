# -*- coding: utf-8 -*-
"""Per i canali che il controllo giornaliero trova rotti e che leggono i titoli dai dati della pagina, riscrive tutto il canale
con il generatore (non solo le sezioni rotte) e, se esiste una versione scritta a mano in riparazioni/, la confronta.

Uso: python3 rigenera_rotti.py [--massimo 3] [canale ...]
"""
import argparse, json, os, subprocess, sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
ap = argparse.ArgumentParser()
ap.add_argument('canali', nargs='*')
ap.add_argument('--massimo', type=int, default=3)
a = ap.parse_args()

stato = json.load(open(os.path.join(RADICE, 'rapporti', 'correzioni', 'stato.json'), encoding='utf-8'))
scelti = [x for x in stato if x.get('rigenerabile') and x['stato'] in ('ROTTO', 'CORRETTO IN PARTE', 'CORRETTO')
          and (not a.canali or x['canale'] in a.canali)][:a.massimo]
if not scelti:
    print('Nessun canale da riscrivere.')
    sys.exit(0)
for x in scelti:
    nome, host = x['canale'], x.get('host')
    out = os.path.join(RADICE, 'rapporti', 'correzioni', nome, 'rigenerato')
    print('== %s: riscrittura completa da %s' % (nome, host), flush=True)
    try:
        subprocess.run([sys.executable, os.path.join(QUI, 's4me_gen.py'), host, '--nome', nome, '--out', out, '--attesa', '6',
                        '--senza-profilo'], cwd=RADICE, timeout=1500, check=False)
    except subprocess.TimeoutExpired:
        print('tempo scaduto per', nome)
        continue
    mano = os.path.join(RADICE, 'riparazioni', nome + '.py')
    gen = os.path.join(out, nome + '.py')
    if os.path.exists(mano) and os.path.exists(gen):
        print('confronto con la versione scritta a mano', flush=True)
        env = dict(os.environ, PYTHONPATH='/tmp/kh:/tmp/kh/addon')
        subprocess.run([sys.executable, '-W', 'ignore', os.path.join(QUI, 'confronta_canali.py'), mano, gen, '--host', host,
                        '--out', os.path.join(RADICE, 'rapporti', 'correzioni', nome)], cwd=RADICE, env=env, timeout=1500, check=False)
