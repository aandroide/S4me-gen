import sys, types, os
KH = os.environ.get('KH', '/tmp/kh')
from unittest.mock import MagicMock
class Fake(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith('__'): raise AttributeError(n)
        m = MagicMock(name=self.__name__+'.'+n)
        setattr(self, n, m); return m
for n in ['xbmc','xbmcgui','xbmcplugin','xbmcaddon','xbmcvfs','xbmcdrm']:
    m = Fake(n); sys.modules[n] = m
import xbmcaddon
import re as _re
DEF={}
try:
    _x=open(os.path.join(KH,'addon','resources','settings.xml'),encoding='utf-8').read()
    for _m in _re.finditer(r'<setting[^>]*id="([^"]+)"[^>]*>(.*?)</setting>|<setting[^>]*id="([^"]+)"[^>]*/>',_x,_re.S):
        _id=_m.group(1) or _m.group(3); _b=_m.group(2) or ''
        _d=_re.search(r'<default>(.*?)</default>',_b)
        DEF[_id]=_d.group(1) if _d else ''
except Exception as e: print('settings',e)
DEF['chrome_ua_version']='124.0.0.0'
class A:
    def __init__(s,*a,**k): pass
    def getAddonInfo(s,k): return {'path':os.path.join(KH,'addon'),'profile':os.path.join(KH,'prof'),'id':'plugin.video.s4me','version':'1.7.8','name':'s4me'}.get(k.lower(),'') or os.path.join(KH,'x')
    def getSetting(s,k): return DEF.get(k,'')
    def setSetting(s,*a): pass
    def getLocalizedString(s,i): return 'str%d'%i
xbmcaddon.Addon = A
import xbmc, xbmcvfs
xbmc.translatePath = lambda p: p
xbmcvfs.translatePath = lambda p: p
xbmc.getInfoLabel = lambda k: '21.0.0 (21.0.0) Git:fake' if k == 'System.BuildVersion' else ''
xbmc.getCondVisibility = lambda k: False
xbmc.executebuiltin = lambda *a,**k: None
xbmc.LOGINFO=1;xbmc.LOGDEBUG=0;xbmc.LOGERROR=2;xbmc.LOGWARNING=3;xbmc.LOGNONE=4
xbmc.log = lambda *a,**k: None
import sys; sys.path.append(os.path.join(KH,'addon','lib'))
from platformcode import config as _cfg
_orig = _cfg.get_setting
_DFL = {'view_mode_channel': '50,50', 'view_mode_tvshow': '50,50', 'info_language': 0, 'tmdb_threads': 4, 'episode_info': False, 'videolibrary_tmdb': False, 'resolve_priority': 0, 'resolve_stop': False, 'resolver_dns': False, 'proxy_use': False}
def _gs(name, channel='', server='', default=None):
    try:
        v = _orig(name, channel, server, default)
    except Exception:
        v = None
    if v is None or v == '':
        return default if default is not None else _DFL.get(name, v)
    return v
_cfg.get_setting = _gs
_cfg.get_localized_string = lambda i: 'txt%d %%s' % i
import types as _t, requests as _rq
for _n in ['lib.requests_toolbelt', 'lib.requests_toolbelt.adapters', 'lib.requests_toolbelt.adapters.host_header_ssl']:
    _m = _t.ModuleType(_n); _m.__path__ = []; sys.modules[_n] = _m
sys.modules['lib.requests_toolbelt.adapters.host_header_ssl'].HostHeaderSSLAdapter = _rq.adapters.HTTPAdapter
sys.modules['lib.requests_toolbelt.adapters'].host_header_ssl = sys.modules['lib.requests_toolbelt.adapters.host_header_ssl']
sys.modules['lib.requests_toolbelt'].adapters = sys.modules['lib.requests_toolbelt.adapters']
import os as _os, xbmcvfs as _v
_v.exists = lambda p: _os.path.exists(p)
def _ld(p):
    n = _os.listdir(p); return [x for x in n if _os.path.isdir(_os.path.join(p, x))], [x for x in n if not _os.path.isdir(_os.path.join(p, x))]
_v.listdir = _ld
class _F:
    def __init__(s, p, m='r'): s.p, s.m = p, m; s.f = open(p, m.replace('w', 'w') + ('b' if 'b' in m else ''), **({} if 'b' in m else {'encoding': 'utf-8'}))
    def read(s, n=-1): return s.f.read(n) if n != -1 else s.f.read()
    def write(s, d): return s.f.write(d) or True
    def close(s): s.f.close()
    def size(s): return _os.path.getsize(s.p)
    def seek(s, *a): return s.f.seek(*a)
_v.File = _F
_v.mkdirs = lambda p: _os.makedirs(p, exist_ok=True) or True
_v.mkdir = _v.mkdirs
_v.delete = lambda p: (_os.remove(p) or True)
