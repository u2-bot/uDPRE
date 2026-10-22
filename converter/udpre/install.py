"""Dump -> playable Windows game, in place in the uDPRE folder.

Layout of a uDPRE folder: Dpr.exe + Dpr_Data/ (our player, no game data), uDPRE.exe (this converter) and udpre/ (its data:
shaders.pack, bundles.txt, base/globalgamemanagers, release.json). The converter writes the game data into Dpr_Data:
  StreamingAssets/AssetAssistant/<13,651 bundles>  converted (bundle.py), in parallel, resumable;
  resources.assets(+.resS), globalgamemanagers      player.py;
  StreamingAssets/AssetAssistant/Dpr.bin, Audio/, Movie/   copied byte for byte (the game reads them as they are).
State: udpre/state/done_v<CONVERT_VERSION>.log lists finished bundles; a new converter version (other output bytes) starts a
new log, so every bundle is converted again; outputs are always written to a .part file and renamed when complete.
Updates without a new converter version: state/config.json keeps a fingerprint of what the data was made against (our base
globalgamemanagers, the shader pack per container). A release unzipped over the folder that changes either is noticed at
start (status() == 'refresh'): the player files and only the bundles whose shaders changed are made again, from the dump
used last time.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import time

from . import CONVERT_VERSION
from .unityfiles import ConvertError

# BDSP v1.3.0 (Brilliant Diamond, Switch): files every correct dump has byte-identical (sha1, size) - the same fingerprints
# setup.cmd of uDPR checks (romfs part)
FINGERPRINTS = [
    ('globalgamemanagers', '761d0eacb7181b42079dabcf92187e2306496c33', 177356),
    ('StreamingAssets/AssetAssistant/Dpr.bin', '9c8159aa1aed650b9187d74b4e4d93d3174e7102', 5278300),
]
# (dump path, player path): copied byte for byte. The Switch-built Wwise banks play in the Windows Wwise runtime; it looks for
# them under GeneratedSoundBanks/Windows (the uDPR project's setup and Windows build do the same move).
COPY_TREES = [('StreamingAssets/Audio/GeneratedSoundBanks/Switch', 'StreamingAssets/Audio/GeneratedSoundBanks/Windows'),
              ('StreamingAssets/Movie', 'StreamingAssets/Movie')]
COPY_FILES = ['StreamingAssets/AssetAssistant/Dpr.bin']
# measured on the whole v1.3.0 dump: 3.83 GiB of Switch bundles -> 5.09 GiB (ASTC decoded to RGBA32, LZ4) = x1.33
BUNDLE_GROWTH = 1.45
MARK = 'StreamingAssets/AssetAssistant/Dpr.bin'


class DumpError(Exception):
    pass


def find_dump(selected):
    """-> the dump's romfs Data folder under / around what the user picked (the dump folder, romfs, romfs/Data, a title-id
    folder above them ...). Raises DumpError with a message a player can act on."""
    sel = os.path.abspath(selected)
    if not os.path.isdir(sel):
        raise DumpError(f'{sel} is not a folder.')
    cands = [sel, os.path.join(sel, 'Data'), os.path.join(sel, 'romfs', 'Data'), os.path.dirname(sel)]
    for root, dirs, _ in os.walk(sel):
        depth = root[len(sel):].count(os.sep)
        if depth >= 3:
            dirs[:] = []
            continue
        for d in dirs:
            cands.append(os.path.join(root, d))
    for c in cands:
        if os.path.isfile(os.path.join(c, *MARK.split('/'))) and os.path.isfile(os.path.join(c, 'globalgamemanagers')):
            return c
    raise DumpError(f'No BDSP game files found in {sel}. Pick the folder you extracted the game to (it holds "romfs", '
                    f'with "Data" inside).')


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_dump(data, bundles):
    """-> list of problems (empty = a complete Brilliant Diamond v1.3.0 romfs)."""
    bad = []
    for rel, want, size in FINGERPRINTS:
        p = os.path.join(data, *rel.split('/'))
        if not os.path.isfile(p):
            bad.append(f'{rel} is missing')
        elif os.path.getsize(p) != size or sha1(p) != want:
            bad.append(f'{rel} is not the Brilliant Diamond v1.3.0 file. Dump the game WITH the v1.3.0 update applied '
                       f'(base game + update, extracted together).')
    if bad:
        return bad
    aa = os.path.join(data, 'StreamingAssets', 'AssetAssistant')
    missing = [b for b in bundles if not os.path.isfile(os.path.join(aa, *b.split('/')))]
    if missing:
        bad.append(f'{len(missing)} of {len(bundles)} game files are missing (e.g. {missing[0]}) - the extraction is '
                   f'incomplete.')
    for t, _ in COPY_TREES:
        if not os.path.isdir(os.path.join(data, *t.split('/'))):
            bad.append(f'{t} is missing - the extraction is incomplete.')
    return bad


class Paths:
    def __init__(self, root):
        self.root = os.path.abspath(root)                       # the uDPRE folder (holds Dpr.exe)
        self.out = os.path.join(self.root, 'Dpr_Data')
        self.data = os.path.join(self.root, 'udpre')
        self.pack = os.path.join(self.data, 'shaders.pack')
        self.bundles = os.path.join(self.data, 'bundles.txt')
        self.base_ggm = os.path.join(self.data, 'base', 'globalgamemanagers')
        self.state = os.path.join(self.data, 'state')
        self.done_log = os.path.join(self.state, f'done_v{CONVERT_VERSION}.log')
        self.config = os.path.join(self.state, 'config.json')
        self.aa_out = os.path.join(self.out, 'StreamingAssets', 'AssetAssistant')

    def bundle_list(self):
        return [l.strip() for l in open(self.bundles, encoding='utf-8') if l.strip()]


def load_config(p):
    try:
        with open(p.config, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(p, cfg):
    os.makedirs(p.state, exist_ok=True)
    with open(p.config + '.part', 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=1)
    os.replace(p.config + '.part', p.config)


def is_installed(p):
    return status(p)['state'] == 'ready'


def pack_digests(p):
    """{container: digest} of the release's shader pack, cached in state/ by the pack file's size + mtime."""
    st = os.stat(p.pack)
    key = f'{st.st_size}:{int(st.st_mtime)}'
    cache = os.path.join(p.state, 'pack_digests.json')
    try:
        with open(cache, encoding='utf-8') as f:
            d = json.load(f)
        if d.get('key') == key:
            return d['digests']
    except (OSError, ValueError):
        pass
    from .shaderpack import ShaderPack
    digests = ShaderPack(p.pack).container_digests()
    os.makedirs(p.state, exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump({'key': key, 'digests': digests}, f)
    return digests


def fingerprint(p):
    """What the converted data was made against: our base globalgamemanagers + the shader pack, per container."""
    return {'base_ggm': sha1(p.base_ggm), 'pack': pack_digests(p)}


def status(p):
    """-> {'state': 'ready' | 'refresh' | 'convert', 'stale': [containers to convert again], 'reason': text}.
    convert = no complete conversion for this CONVERT_VERSION; refresh = a release changed our player base or shaders since
    the conversion (or converted files are missing): only the affected files are made again."""
    cfg = load_config(p)
    if cfg.get('complete_version') != CONVERT_VERSION:
        if cfg.get('complete_version') is not None:
            return {'state': 'convert', 'stale': [], 'reason': 'this uDPRE version converts the game data in a new way'}
        return {'state': 'convert', 'stale': [], 'reason': 'not converted yet'}
    old, now = cfg.get('fingerprint') or {}, fingerprint(p)
    stale = sorted(c for c, d in now['pack'].items() if (old.get('pack') or {}).get(c) != d)
    reasons = []
    if stale:
        reasons.append(f'new shaders for {len(stale)} files')
    if old.get('base_ggm') != now['base_ggm']:
        reasons.append('a new player')
    missing = [x for x in ('globalgamemanagers', 'resources.assets') if not os.path.isfile(os.path.join(p.out, x))]
    if missing:
        reasons.append('missing ' + ', '.join(missing))
    gone = sum(1 for b in p.bundle_list() if not os.path.isfile(os.path.join(p.aa_out, *b.split('/'))))
    if gone:
        reasons.append(f'{gone} converted bundles missing')
    if reasons:
        return {'state': 'refresh', 'stale': stale, 'reason': '; '.join(reasons)}
    return {'state': 'ready', 'stale': [], 'reason': ''}


def done_set(p):
    try:
        with open(p.done_log, encoding='utf-8') as f:
            return {l.split('\t')[0] for l in f if l.strip()}
    except OSError:
        return set()


# --- worker process ---------------------------------------------------------------------------------------------------
_W = {}


def _init(pack_path, switch_ids):
    from .shaderpack import ShaderPack
    _W['pack'] = ShaderPack(pack_path)
    _W['ids'] = switch_ids


def _job(args):
    src, dst, rel = args
    from . import bundle
    t0 = time.time()
    try:
        st = bundle.convert_bundle(src, dst, rel, _W['pack'], _W['ids'])
        return rel, st, None, time.time() - t0
    except Exception as e:      # reported, the run continues and fails at the end
        import traceback
        return rel, None, f'{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}', time.time() - t0


def switch_shader_ids(data):
    import UnityPy
    from .shaderpack import shader_name
    env = UnityPy.load(os.path.join(data, 'StreamingAssets', 'AssetAssistant', 'Dpr', 'shaders'))
    return {shader_name(o): o.path_id for o in env.objects if o.type.name == 'Shader'}


def default_workers():
    n = os.cpu_count() or 2
    try:
        import ctypes

        class M(ctypes.Structure):
            _fields_ = [('l', ctypes.c_ulong), ('ml', ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in
                                                                           ('t', 'a', 'tp', 'ap', 'tv', 'av', 'x')]
        m = M()
        m.l = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        # measured with 15 workers, biggest bundles first: one worker peaks at 1.26 GB, the average ~0.8 GB
        ram_workers = int(m.a / 2 ** 30 / 1.5)
    except Exception:
        ram_workers = n
    return max(1, min(n - 1 if n > 2 else n, ram_workers, 16))


def copy_tree(src, dst, progress=None):
    n = 0
    for root, _, files in os.walk(src):
        for fn in files:
            s = os.path.join(root, fn)
            d = os.path.join(dst, os.path.relpath(s, src))
            if os.path.isfile(d) and os.path.getsize(d) == os.path.getsize(s):
                continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d + '.part')
            os.replace(d + '.part', d)
            n += 1
    return n


def run(root, dump_selected=None, workers=None, progress=print, log=print):
    """Converts the dump into the uDPRE folder `root` - everything on a first run, after a release update only what it needs
    (status()). dump_selected None = the dump of the last conversion. progress(stage, done, total) / log(text). Returns a
    summary dict; raises DumpError / ConvertError."""
    p = Paths(root)
    cfg = load_config(p)
    if dump_selected is None:
        dump_selected = cfg.get('dump')
        if not dump_selected:
            raise DumpError('Pick your dump folder first.')
        if not os.path.isdir(dump_selected):
            raise DumpError(f'The dump used last time is gone ({dump_selected}). Pick your dump folder again.')
    data = find_dump(dump_selected)
    bundles = p.bundle_list()
    log(f'dump: {data}')
    problems = verify_dump(data, bundles)
    if problems:
        raise DumpError('\n'.join(problems))
    st0 = status(p)
    stale = set(st0['stale'])
    if st0['state'] == 'refresh':
        log(f'refresh after an update: {st0["reason"]}')
    cfg.update({'dump': data, 'started_version': CONVERT_VERSION})
    cfg.pop('complete_version', None)
    save_config(p, cfg)
    workers = workers or default_workers()
    aa = os.path.join(data, 'StreamingAssets', 'AssetAssistant')
    done = done_set(p)
    todo = [b for b in bundles if b not in done or b in stale or not os.path.isfile(os.path.join(p.aa_out, *b.split('/')))]
    todo.sort(key=lambda b: -os.path.getsize(os.path.join(aa, *b.split('/'))))     # big first: even load at the end
    log(f'{len(bundles)} bundles, {len(bundles) - len(todo)} already converted, {len(todo)} to go, {workers} workers')
    need = int(sum(os.path.getsize(os.path.join(aa, *b.split('/'))) for b in todo) * BUNDLE_GROWTH)
    for s, d in COPY_TREES:
        if not os.path.isdir(os.path.join(p.out, *d.split('/'))):
            need += sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(os.path.join(data, *s.split('/')))
                        for f in fs)
    need += 64 << 20
    free = shutil.disk_usage(p.root).free
    if free < need:
        raise DumpError(f'Not enough free space on the drive of {p.root}: {free / 2**30:.1f} GB free, about '
                        f'{need / 2**30:.1f} GB needed. Free some space (or move the uDPRE folder) and convert again.')
    ids = switch_shader_ids(data)
    t0 = time.time()
    errors = []
    os.makedirs(p.state, exist_ok=True)
    totals = {}
    with open(p.done_log, 'a', encoding='utf-8', newline='\n') as dl, \
            cf.ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(p.pack, ids)) as ex:
        jobs = [(os.path.join(aa, *b.split('/')), os.path.join(p.aa_out, *b.split('/')), b) for b in todo]
        k = len(bundles) - len(todo)
        for rel, st, err, dt in ex.map(_job, jobs, chunksize=1):
            k += 1
            if err:
                errors.append((rel, err))
                log(f'FAILED {rel}: {err.splitlines()[0]}')
            else:
                dl.write(f'{rel}\t{st.get("bytes", 0)}\n')
                dl.flush()
                for key, v in st.items():
                    totals[key] = totals.get(key, 0) + v
            progress('bundles', k, len(bundles))
    log(f'bundles: {time.time() - t0:.0f} s, {len(errors)} failed, totals {totals}')
    if errors:
        with open(os.path.join(p.state, 'errors.txt'), 'w', encoding='utf-8') as f:
            for rel, err in errors:
                f.write(f'== {rel}\n{err}\n')
        raise ConvertError(f'{len(errors)} bundles failed (details: {os.path.join(p.state, "errors.txt")}); run again to retry them')
    from . import player
    from .shaderpack import ShaderPack
    progress('player files', 0, 2)
    pack = ShaderPack(p.pack)
    st = player.convert_resources(data, p.out, pack, ids)
    log(f'resources.assets: {st}')
    player.patch_globalgamemanagers(data, p.base_ggm, p.out)
    progress('player files', 2, 2)
    progress('audio and movies', 0, 1)
    for rel in COPY_FILES:
        d = os.path.join(p.out, *rel.split('/'))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(os.path.join(data, *rel.split('/')), d + '.part')
        os.replace(d + '.part', d)
    copied = sum(copy_tree(os.path.join(data, *s.split('/')), os.path.join(p.out, *d.split('/'))) for s, d in COPY_TREES)
    os.makedirs(os.path.join(p.out, 'StreamingAssets', 'AK'), exist_ok=True)
    progress('audio and movies', 1, 1)
    log(f'copied {copied} audio / movie files')
    cfg['complete_version'] = CONVERT_VERSION
    cfg['completed'] = time.strftime('%Y-%m-%d %H:%M:%S')
    cfg['fingerprint'] = fingerprint(p)
    save_config(p, cfg)
    return {'seconds': round(time.time() - t0), 'bundles': len(bundles), 'totals': totals}
