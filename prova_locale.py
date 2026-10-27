# -*- coding: utf-8 -*-
"""Prova i canali S4Me sul tuo computer, con il tuo indirizzo italiano, fino al video.

Uso (dalla cartella del repository):
    python prova_locale.py eurostreaming tantifilm guardaseriecam

Fa da solo: scarica il codice di S4Me (sola lettura) in ./kh, installa i pacchetti che servono,
usa le correzioni di riparazioni/ se esistono, prova ogni canale e scrive i risultati in prove_locali/.
Alla fine crea prove_locali/RISULTATI.txt: e quel file che mi mandi.
"""
import io, json, os, shutil, subprocess, sys, urllib.request, zipfile

# una variabile di Windows (SSLKEYLOGFILE) puntava a un file non scrivibile e rompeva ogni connessione https
os.environ.pop('SSLKEYLOGFILE', None)
QUI = os.path.dirname(os.path.abspath(__file__))
KH = os.path.join(QUI, 'kh')
USCITA = os.path.join(QUI, 'prove_locali')
ZIP_S4ME = 'https://github.com/stream4me/addon/archive/refs/heads/master.zip'


def prepara_venv():
    """Ambiente separato: i pacchetti di prova non toccano quelli gia installati sul computer."""
    venv = os.path.join(KH, 'venv')
    py = os.path.join(venv, 'Scripts' if os.name == 'nt' else 'bin', 'python.exe' if os.name == 'nt' else 'python')
    if not os.path.exists(py):
        print('Creo un ambiente separato per i pacchetti...')
        subprocess.check_call([sys.executable, '-m', 'venv', venv])
    subprocess.check_call([py, '-m', 'pip', 'install', '-q', 'requests', 'beautifulsoup4', 'lxml', 'cryptography', 'urllib3<2'])
    return py


def scarica_s4me():
    dest = os.path.join(KH, 'addon')
    os.makedirs(KH, exist_ok=True)
    print('Scarico il codice di S4Me (sola lettura)...')
    try:
        dati = urllib.request.urlopen(ZIP_S4ME, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(dati)) as z:
            z.extractall(KH)
        cartella = [d for d in os.listdir(KH) if d.startswith('addon-')][0]
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.rename(os.path.join(KH, cartella), dest)
    except Exception as e:
        if not os.path.isdir(dest):
            raise
        print('Download non riuscito (%s): uso la copia gia presente in kh/addon' % e)
    os.makedirs(os.path.join(KH, 'prof'), exist_ok=True)
    shutil.copy(os.path.join(QUI, 'test', 'kodi_finto', 'fake.py'), os.path.join(KH, 'fake.py'))


def main():
    canali = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not canali:
        print('Scrivi i nomi dei canali, per esempio: python prova_locale.py eurostreaming tantifilm')
        return 1
    print('Controllo i pacchetti...')
    os.makedirs(KH, exist_ok=True)
    py = prepara_venv()
    scarica_s4me()
    if canali == ['tutti']:
        cart = os.path.join(KH, 'addon', 'channels')
        canali = sorted(f[:-5] for f in os.listdir(cart) if f.endswith('.json') and os.path.exists(os.path.join(cart, f[:-5] + '.py')))
        print('Provo tutti i %d canali' % len(canali))
    os.makedirs(USCITA, exist_ok=True)
    env = dict(os.environ, KH=KH, PYTHONPATH=os.pathsep.join([KH, os.path.join(KH, 'addon')]), PYTHONIOENCODING='utf-8', RESOLVER_DNS='1')
    for c in canali:
        dest = os.path.join(KH, 'addon', 'channels', c + '.py')
        rip = os.path.join(QUI, 'riparazioni', c + '.py')
        if os.path.exists(rip):
            shutil.copy(rip, dest)
            j = os.path.join(QUI, 'riparazioni', c + '.json')
            if os.path.exists(j):
                shutil.copy(j, os.path.join(KH, 'addon', 'channels', c + '.json'))
            print('%s: uso la correzione di riparazioni/' % c)

    def prova(c):
        os.makedirs(os.path.join(USCITA, c), exist_ok=True)
        env_c = dict(env, LOG_S4ME=os.path.join(USCITA, c, 's4me.log'))
        try:
            subprocess.run([py, '-W', 'ignore', os.path.join(QUI, 'prova_video.py'), c, '--out', USCITA],
                           env=env_c, cwd=QUI, timeout=1500, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return '%s: tempo scaduto' % c
        log = os.path.join(USCITA, c, 'log.txt')
        verdetto = 'nessun risultato'
        if os.path.exists(log):
            ultime = [r for r in open(log, encoding='utf-8', errors='replace').read().splitlines() if 'VERDETTO' in r]
            if ultime:
                verdetto = ultime[-1]
        sez = ''
        try:
            import json as _j
            e = _j.load(open(os.path.join(USCITA, c, 'esito.json'), encoding='utf-8'))
            vuote = [z['voce'] for z in e.get('sezioni', []) if z['esito'] not in ('OK', 'SOTTOMENU')]
            sez = ' | sezioni %s' % e.get('sezioni_riepilogo', '?') + (' | SENZA TITOLI: ' + ', '.join(vuote) if vuote else '')
        except Exception:
            pass
        r = '%s: %s%s' % (c, verdetto, sez)
        print(r, flush=True)
        return r

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        righe = list(ex.map(prova, canali))
    with open(os.path.join(USCITA, 'RISULTATI.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(righe) + '\n')
    shutil.make_archive(os.path.join(QUI, 'prove_locali'), 'zip', USCITA)
    print('\nFatto. Mandami il file prove_locali.zip che trovi in %s' % QUI)
    return 0


if __name__ == '__main__':
    sys.exit(main())
