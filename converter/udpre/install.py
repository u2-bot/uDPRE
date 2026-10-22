"""Dump (+ mod packs) -> playable Windows game, in place in the uDPRE folder.

Layout of a uDPRE folder: Dpr.exe + Dpr_Data/ (our player, no game data), uDPRE.exe (this converter), udpre/ (its data:
shaders.pack, bundles.txt, base/globalgamemanagers, player_files.json, release.json) and mods/ (mod packs, mods.py). The
converter writes the game data into Dpr_Data:
  StreamingAssets/AssetAssistant/<bundles>   converted (bundle.py) from the top-most layer of the stack (the dump, then the
                                             enabled packs' Switch files), in parallel, resumable; Windows files of a pack
                                             are copied as they are;
  resources.assets(+.resS), globalgamemanagers  player.py, from the top-most layer that has them;
  StreamingAssets/AssetAssistant/Dpr.bin, Audio/, Movie/   copied byte for byte (the game reads them as they are).
A pack that brings a player profile (Luminescent needs its own game code) puts its code files over ours; our own files are
kept in udpre/players/vanilla and come back when no such pack is on.
State: udpre/state/done_v<CONVERT_VERSION>.log lists each finished bundle with the source it was made from (dump, or pack id +
version + size + time); a bundle is made again when its source changes, and removed when no layer has it any more. A new
converter version (other output bytes) starts a new log, so every bundle is converted again; outputs are always written to a
.part file and renamed when complete. state/config.json keeps the dump, the chosen mods and a fingerprint of what the data
was made against (player base, shader pack per container, mod set); status() compares it with the folder at every start.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import time

from . import CONVERT_VERSION, movies, mods as modlib
from .unityfiles import ConvertError

# BDSP v1.3.0 (Brilliant Diamond, Switch): files every correct dump has byte-identical (sha1, size) - the same fingerprints
# setup.cmd of uDPR checks (romfs part)
FINGERPRINTS = [
    ('globalgamemanagers', '761d0eacb7181b42079dabcf92187e2306496c33', 177356),
    ('StreamingAssets/AssetAssistant/Dpr.bin', '9c8159aa1aed650b9187d74b4e4d93d3174e7102', 5278300),
]
# dump folders the player needs besides the bundles (Audio: the Switch-built Wwise banks play in the Windows Wwise runtime,
# which looks for them under GeneratedSoundBanks/Windows - mods.out_rel moves them)
COPY_TREES = [modlib.AUDIO_SW, 'StreamingAssets/Movie']
# Switch files a mod layer may carry outside the bundles and the player files: copied byte for byte
COPY_PREFIXES = (modlib.AA + '/Dpr.bin', modlib.AUDIO_WIN + '/', 'StreamingAssets/Movie/')
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
    for t in COPY_TREES:
        if not os.path.isdir(os.path.join(data, *t.split('/'))):
            bad.append(f'{t} is missing - the extraction is incomplete.')
    return bad


class Paths:
    def __init__(self, root):
        self.root = os.path.abspath(root)                       # the uDPRE folder (holds Dpr.exe)
        self.out = os.path.join(self.root, 'Dpr_Data')
        self.data = os.path.join(self.root, 'udpre')
        self.mods = os.path.join(self.root, 'mods')
        self.pack = os.path.join(self.data, 'shaders.pack')
        self.bundles = os.path.join(self.data, 'bundles.txt')
        self.base_ggm = os.path.join(self.data, 'base', 'globalgamemanagers')
        self.player_files = os.path.join(self.data, 'player_files.json')
        self.vanilla_player = os.path.join(self.data, 'players', 'vanilla')
        self.state = os.path.join(self.data, 'state')
        self.done_log = os.path.join(self.state, f'done_v{CONVERT_VERSION}.log')
        self.copied = os.path.join(self.state, 'copied.json')
        self.config = os.path.join(self.state, 'config.json')
        self.aa_out = os.path.join(self.out, 'StreamingAssets', 'AssetAssistant')

    def bundle_list(self):
        return [l.strip() for l in open(self.bundles, encoding='utf-8') if l.strip()]


def _load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.part', 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(path + '.part', path)


def load_config(p):
    return _load_json(p.config, {})


def save_config(p, cfg):
    _save_json(p.config, cfg)


def is_installed(p):
    return status(p)['state'] == 'ready'


def release_info(p):
    """udpre/release.json: uDPRE version, base_version (the uDPR game build the player is) ..."""
    return _load_json(os.path.join(p.data, 'release.json'), {})


class Setup:
    """What a conversion uses besides the dump: the chosen mods, the player profile, the shader pack and player base.
    picked = {source id: folder} downloads the player pointed at outside the mods folder."""

    def __init__(self, p, mod_ids, picked=None):
        self.found, self.problems = modlib.discover(p.mods, picked)
        self.chosen = modlib.choose(self.found, mod_ids)
        self.player_mod = modlib.player_mod(self.chosen)
        if self.player_mod:
            self.profile, self.player_dir = modlib.load_profile(self.player_mod)
            self.pack = os.path.join(self.player_dir, 'udpre', 'shaders.pack')
            self.base_ggm = os.path.join(self.player_dir, 'udpre', 'base', 'globalgamemanagers')
            self.player_id = self.profile.get('id', self.player_mod.id)
        else:
            self.profile, self.player_dir = None, None
            self.pack, self.base_ggm, self.player_id = p.pack, p.base_ggm, 'vanilla'
        self.mod_ids = [m.id for m in self.chosen]


def pack_digests(p, pack):
    """{container: digest} of a shader pack, cached in state/ by the pack file's path + size + mtime."""
    st = os.stat(pack)
    key = f'{os.path.abspath(pack)}|{st.st_size}|{int(st.st_mtime)}'
    cache = os.path.join(p.state, 'pack_digests.json')
    d = _load_json(cache, {})
    if not isinstance(d.get('packs'), dict):
        d = {'packs': {}}
    if key in d['packs']:
        return d['packs'][key]
    from .shaderpack import ShaderPack
    digests = ShaderPack(pack).container_digests()
    d['packs'] = {k: v for k, v in d['packs'].items() if os.path.isfile(k.split('|')[0])}
    d['packs'][key] = digests
    _save_json(cache, d)
    return digests


def fingerprint(p, setup):
    """What the converted data was made against: player base globalgamemanagers, shader pack per container, mod set."""
    return {'base_ggm': sha1(setup.base_ggm), 'pack': pack_digests(p, setup.pack), 'player': setup.player_id,
            'mods': modlib.signature(setup.chosen)}


def expected_player(p, setup):
    """{root-relative player file: sha1 it must have} for the chosen player (ours, or a pack's profile)."""
    vanilla = _load_json(p.player_files, {}).get('files', {})
    if setup.profile is None:
        return dict(vanilla)
    return {rel: sha1(os.path.join(setup.player_dir, *rel.split('/'))) for rel in setup.profile['files']}


def status(p):
    """-> {'state': 'ready' | 'refresh' | 'convert', 'stale': [containers to convert again], 'reason': text, 'mods': ids}.
    convert = no complete conversion for this CONVERT_VERSION; refresh = something changed since the conversion (a release
    update of our player base or shaders, the chosen mods, missing files): only the affected files are made again."""
    cfg = load_config(p)
    mod_ids = cfg.get('mods', [])
    if cfg.get('complete_version') != CONVERT_VERSION:
        if cfg.get('complete_version') is not None:
            return {'state': 'convert', 'stale': [], 'reason': 'this uDPRE version converts the game data in a new way',
                    'mods': mod_ids}
        return {'state': 'convert', 'stale': [], 'reason': 'not converted yet', 'mods': mod_ids}
    try:
        setup = Setup(p, mod_ids, cfg.get('sources'))
    except modlib.ModError as e:
        return {'state': 'refresh', 'stale': [], 'reason': f'the mod choice cannot be used: {e}', 'mods': mod_ids}
    old, now = cfg.get('fingerprint') or {}, fingerprint(p, setup)
    stale = sorted(c for c, d in now['pack'].items() if (old.get('pack') or {}).get(c) != d)
    reasons = []
    if stale:
        reasons.append(f'new shaders for {len(stale)} files')
    if old.get('base_ggm') != now['base_ggm'] or old.get('player', 'vanilla') != now['player']:
        reasons.append('a new player')
    if old.get('mods', []) != now['mods']:
        reasons.append('the mods')
    wrong = [rel for rel, h in expected_player(p, setup).items()
             if not os.path.isfile(os.path.join(p.root, *rel.split('/'))) or sha1(os.path.join(p.root, *rel.split('/'))) != h]
    if wrong:
        reasons.append('the player files')
    missing = [x for x in ('globalgamemanagers', 'resources.assets') if not os.path.isfile(os.path.join(p.out, x))]
    if missing:
        reasons.append('missing ' + ', '.join(missing))
    gone = sum(1 for rel in done_map(p) if not os.path.isfile(os.path.join(p.aa_out, *rel.split('/'))))
    if gone:
        reasons.append(f'{gone} converted bundles missing')
    if reasons:
        return {'state': 'refresh', 'stale': stale, 'reason': '; '.join(reasons), 'mods': mod_ids}
    return {'state': 'ready', 'stale': [], 'reason': '', 'mods': mod_ids}


def done_map(p):
    """{bundle: source key} of the finished bundles (last line wins; uDPRE 0.1.0 lines have no key = made from the dump)."""
    out = {}
    try:
        with open(p.done_log, encoding='utf-8') as f:
            for line in f:
                parts = line.rstrip('\n').split('\t')
                if parts[0]:
                    out[parts[0]] = parts[2] if len(parts) > 2 else 'dump'
    except OSError:
        pass
    return out


def write_done_map(p, done):
    os.makedirs(p.state, exist_ok=True)
    with open(p.done_log + '.part', 'w', encoding='utf-8', newline='\n') as f:
        for rel in sorted(done):
            f.write(f'{rel}\t0\t{done[rel]}\n')
    os.replace(p.done_log + '.part', p.done_log)


# --- worker process ---------------------------------------------------------------------------------------------------
_W = {}


def _init(pack_path, switch_ids):
    from .shaderpack import ShaderPack
    _W['pack'] = ShaderPack(pack_path)
    _W['ids'] = switch_ids


def _job(args):
    src, dst, rel, strict = args
    from . import bundle
    t0 = time.time()
    try:
        st = bundle.convert_bundle(src, dst, rel, _W['pack'], _W['ids'], strict_streams=strict)
        return rel, st, None, time.time() - t0
    except Exception as e:      # reported, the run continues and fails at the end
        import traceback
        return rel, None, f'{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}', time.time() - t0


def switch_shader_ids(shaders_bundle):
    """{shader name: Switch path id} of a Switch Dpr/shaders bundle. Luminescent's copy holds three objects named UI/Custom
    (its pass-through DoF and FXAA keep their path ids); a name keeps the object with the lowest path id."""
    import UnityPy
    from .shaderpack import shader_name
    env = UnityPy.load(shaders_bundle)
    out = {}
    for o in sorted(env.objects, key=lambda o: o.path_id):
        if o.type.name == 'Shader':
            out.setdefault(shader_name(o), o.path_id)
    return out


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


def remove_file(path, stop):
    """Removes a file a mod brought, then its folders up to `stop` that are left empty."""
    if os.path.isfile(path):
        os.remove(path)
    d = os.path.dirname(path)
    stop = os.path.abspath(stop)
    while os.path.abspath(d).startswith(stop + os.sep) and not os.listdir(d):
        os.rmdir(d)
        d = os.path.dirname(d)


def place(src, dst, link=False):
    """src -> dst through dst.part (link=True: a hard link when the drive allows it, else a copy)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.part'
    if os.path.exists(tmp):
        os.remove(tmp)
    if link:
        try:
            os.link(src, tmp)
        except OSError:
            shutil.copyfile(src, tmp)
    else:
        shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def apply_player(p, setup, cfg, log):
    """Puts the chosen player's code files in place. Our own files (listed with their sha1 in udpre/player_files.json) are
    kept in udpre/players/vanilla before a pack's profile replaces them, and come back from there."""
    vanilla = _load_json(p.player_files, {}).get('files', {})
    if setup.profile is not None and not vanilla:
        raise ConvertError('udpre/player_files.json is missing - unzip the uDPRE release over this folder again')
    for rel, h in vanilla.items():
        cur = os.path.join(p.root, *rel.split('/'))
        bak = os.path.join(p.vanilla_player, *rel.split('/'))
        if os.path.isfile(cur) and sha1(cur) == h and not (os.path.isfile(bak) and sha1(bak) == h):
            place(cur, bak)
    changed = 0
    want = expected_player(p, setup)
    for rel, h in want.items():
        cur = os.path.join(p.root, *rel.split('/'))
        if os.path.isfile(cur) and sha1(cur) == h:
            continue
        if setup.profile is not None:
            src = os.path.join(setup.player_dir, *rel.split('/'))
        else:
            src = os.path.join(p.vanilla_player, *rel.split('/'))
            if not os.path.isfile(src) or sha1(src) != h:
                raise ConvertError(f'{rel} is not the one of this uDPRE release and no copy of it is kept - unzip the '
                                   f'uDPRE release over this folder again')
        try:
            place(src, cur)
        except PermissionError:
            raise ConvertError(f'{rel} is in use - close the game and convert again')
        changed += 1
    for rel in cfg.get('player_extra', []):
        f = os.path.join(p.root, *rel.split('/'))
        if rel not in want and os.path.isfile(f):
            os.remove(f)
    cfg['player_extra'] = [r for r in want if r not in vanilla]
    log(f'player: {setup.player_id} ({changed} files put in place)')


def run(root, dump_selected=None, workers=None, progress=print, log=print, mods=None):
    """Converts the dump (+ the chosen mods) into the uDPRE folder `root` - everything on a first run, later only what
    changed (status()). dump_selected None = the dump of the last conversion; mods None = the mods chosen last time (a list
    of pack ids). progress(stage, done, total) / log(text). Returns a summary dict; raises DumpError / ConvertError."""
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
    mod_ids = list(cfg.get('mods', []) if mods is None else mods)
    try:
        setup = Setup(p, mod_ids, cfg.get('sources'))
        stack = modlib.Stack(data, setup.chosen, bundles)
        shaders_src = stack.shaders_bundle()
    except modlib.ModError as e:
        raise DumpError(str(e))
    for m in setup.chosen:
        log(f'mod: {m.name} {m.version}' + ''.join(f'; your {m.sources[s].get("name", s)}: {d}'
                                                    for s, d in m.source_paths.items()))
    verify_sources(p, setup, progress)
    odd = sorted(k for k, s in stack.copies().items() if s.kind == 'switch' and not k.startswith(COPY_PREFIXES))
    if odd:
        raise DumpError(f'A mod changes files uDPRE cannot convert yet: {", ".join(odd[:5])}')
    old_fp = cfg.get('fingerprint') or {}
    st0 = status(p)
    if st0['state'] == 'refresh':
        log(f'refresh: {st0["reason"]}')
    cfg.update({'dump': data, 'mods': setup.mod_ids, 'started_version': CONVERT_VERSION})
    cfg.pop('complete_version', None)
    save_config(p, cfg)
    workers = workers or default_workers()
    from .shaderpack import ShaderPack
    pack = ShaderPack(setup.pack)
    pack_now = pack_digests(p, setup.pack)
    stale = {c for c, d in pack_now.items() if (old_fp.get('pack') or {}).get(c) != d}

    def key_of(rel, s):
        # a bundle holding shaders also depends on the Dpr/shaders bundle its shader references are resolved in
        return s.key + (f'|shaders={shaders_src.key}' if s.kind == 'switch' and rel in pack_now else '')

    want = {rel: (s, key_of(rel, s)) for rel, s in stack.bundles().items()}
    done = done_map(p)
    removed = [r for r in done if r not in want]
    for rel in removed:
        remove_file(os.path.join(p.aa_out, *rel.split('/')), p.aa_out)
        done.pop(rel)
    write_done_map(p, done)
    todo = [(rel, s, key) for rel, (s, key) in want.items()
            if done.get(rel) != key or (s.kind == 'switch' and rel in stale)
            or not os.path.isfile(os.path.join(p.aa_out, *rel.split('/')))]
    convert = [t for t in todo if t[1].kind == 'switch']
    copy = [t for t in todo if t[1].kind == 'windows']
    convert.sort(key=lambda t: -os.path.getsize(t[1].path))       # big first: even load at the end
    log(f'{len(want)} bundles: {len(want) - len(todo)} already made, {len(convert)} to convert, {len(copy)} to copy, '
        f'{len(removed)} removed, {workers} workers')
    copied_old = _load_json(p.copied, None)
    need = int(sum(os.path.getsize(t[1].path) for t in convert) * BUNDLE_GROWTH)
    need += sum(os.path.getsize(s.path) for k, s in stack.copies().items()
                if not os.path.isfile(os.path.join(p.out, *k.split('/'))))
    need += 64 << 20
    free = shutil.disk_usage(p.root).free
    if free < need:
        raise DumpError(f'Not enough free space on the drive of {p.root}: {free / 2**30:.1f} GB free, about '
                        f'{need / 2**30:.1f} GB needed. Free some space (or move the uDPRE folder) and convert again.')
    ids = switch_shader_ids(shaders_src.path)
    t0 = time.time()
    errors = []
    totals = {}
    total_n = len(want)
    k = total_n - len(todo)
    with open(p.done_log, 'a', encoding='utf-8', newline='\n') as dl:
        for rel, s, key in copy:
            place(s.path, os.path.join(p.aa_out, *rel.split('/')), link=True)
            dl.write(f'{rel}\t{os.path.getsize(s.path)}\t{key}\n')
            k += 1
            totals['copied'] = totals.get('copied', 0) + 1
            progress('bundles', k, total_n)
        dl.flush()
        if convert:
            keys = {rel: key for rel, _, key in convert}
            with cf.ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(setup.pack, ids)) as ex:
                jobs = [(s.path, os.path.join(p.aa_out, *rel.split('/')), rel, s.mod is None) for rel, s, _ in convert]
                for rel, st, err, dt in ex.map(_job, jobs, chunksize=1):
                    k += 1
                    if err:
                        errors.append((rel, err))
                        log(f'FAILED {rel}: {err.splitlines()[0]}')
                    else:
                        dl.write(f'{rel}\t{st.get("bytes", 0)}\t{keys[rel]}\n')
                        dl.flush()
                        for key2, v in st.items():
                            totals[key2] = totals.get(key2, 0) + v
                    progress('bundles', k, total_n)
    log(f'bundles: {time.time() - t0:.0f} s, {len(errors)} failed, totals {totals}')
    if errors:
        with open(os.path.join(p.state, 'errors.txt'), 'w', encoding='utf-8') as f:
            for rel, err in errors:
                f.write(f'== {rel}\n{err}\n')
        raise ConvertError(f'{len(errors)} bundles failed (details: {os.path.join(p.state, "errors.txt")}); run again to retry them')
    write_done_map(p, done_map(p))
    from . import player
    progress('player files', 0, 3)
    apply_player(p, setup, cfg, log)
    progress('player files', 1, 3)
    st = player.convert_resources(stack.player_source('resources.assets'), stack.player_source('resources.assets.resS'),
                                  p.out, pack, ids)
    log(f'resources.assets: {st}')
    player.patch_globalgamemanagers(stack.player_source('globalgamemanagers'), setup.base_ggm, p.out)
    progress('player files', 3, 3)
    progress('audio and movies', 0, 1)
    copied = copy_files(p, stack, copied_old)
    os.makedirs(os.path.join(p.out, 'StreamingAssets', 'AK'), exist_ok=True)
    progress('audio and movies', 1, 1)
    log(f'copied {copied["copied"]} files (catalog, audio, movies, mod files), removed {copied["removed"]}'
        + (f', {copied["encoded"]} movies re-encoded to VP8' if copied['encoded'] else ''))
    cfg['complete_version'] = CONVERT_VERSION
    cfg['completed'] = time.strftime('%Y-%m-%d %H:%M:%S')
    cfg['fingerprint'] = fingerprint(p, setup)
    save_config(p, cfg)
    return {'seconds': round(time.time() - t0), 'bundles': total_n, 'totals': totals, 'mods': setup.mod_ids,
            'player': setup.player_id}


def verify_sources(p, setup, progress):
    """Every file a chosen pack takes from the player's own download must have the size and sha1 the pack lists (the mod
    version it was made for, extracted completely). Digests are cached by path + size + time in state/source_hashes.json."""
    cache_path = os.path.join(p.state, 'source_hashes.json')
    cache = _load_json(cache_path, {})
    jobs = [(m, sid) for m in setup.chosen for sid in m.sources]
    total = sum(len(m.source_list(sid)) for m, sid in jobs)
    k = 0
    for m, sid in jobs:
        root = m.source_paths[sid]
        bad = []
        for rel, (size, digest) in m.source_list(sid).items():
            k += 1
            f = os.path.join(root, *rel.split('/'))
            if not os.path.isfile(f):
                bad.append(f'{rel} is missing')
                continue
            st = os.stat(f)
            if st.st_size != size:
                bad.append(f'{rel} has another size')
                continue
            c = cache.get(f)
            if c and c[0] == st.st_size and c[1] == st.st_mtime_ns:
                h = c[2]
            else:
                h = sha1(f)
                cache[f] = [st.st_size, st.st_mtime_ns, h]
            if h != digest:
                bad.append(f'{rel} has other contents')
            if k % 100 == 0 or k == total:
                progress('checking your mod downloads', k, total)
        if bad:
            _save_json(cache_path, cache)
            name = m.sources[sid].get('name', sid)
            raise DumpError(f'Your copy of {name} ({root}) is incomplete or another version: {len(bad)} of the '
                            f'{len(m.source_list(sid))} files the {m.name} pack needs are missing or differ '
                            f'({"; ".join(bad[:3])}). Extract the original {name} download again (with 7-Zip).')
    if jobs:
        _save_json(cache_path, cache)


def copy_files(p, stack, copied_old):
    """Every file the stack copies byte for byte -> Dpr_Data; files a previous conversion copied that no layer has any more
    are removed. copied_old None = no record yet (a first conversion, or a folder converted by uDPRE 0.1.0): a dump file
    already there with the same size is taken as copied."""
    want = stack.copies()
    rec = dict(copied_old or {})
    n = removed = encoded = 0
    for rel in [r for r in rec if r not in want]:
        f = os.path.join(p.out, *rel.split('/'))
        if os.path.isfile(f):
            removed += 1
        remove_file(f, os.path.join(p.out, 'StreamingAssets'))
        rec.pop(rel)
    for rel, s in sorted(want.items()):
        dst = os.path.join(p.out, *rel.split('/'))
        if os.path.isfile(dst):
            if rec.get(rel) == s.key:
                continue
            if copied_old is None and s.key == 'dump' and os.path.getsize(dst) == os.path.getsize(s.path):
                rec[rel] = s.key
                continue
        if s.key != 'dump' and rel.startswith('StreamingAssets/Movie/') and rel.lower().endswith('.webm'):
            # a mod's movie: copied when VP8, else re-encoded (the Windows player decodes VP8 only)
            how = movies.place_movie(s.path, dst, s.sha1 or sha1(s.path), os.path.join(p.state, 'movies'))
            encoded += how == 'encoded'
        else:
            place(s.path, dst, link=s.kind == 'windows')
        rec[rel] = s.key
        n += 1
    _save_json(p.copied, rec)
    return {'copied': n, 'removed': removed, 'encoded': encoded}
