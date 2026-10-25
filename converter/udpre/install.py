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
# ExtraData/ = JSON data an overhaul mod's code reads (copied for a player that reads it)
COPY_PREFIXES = (modlib.AA + '/Dpr.bin', modlib.AUDIO_WIN + '/', 'StreamingAssets/Movie/', 'ExtraData/')
# measured on the whole v1.3.0 dump: 3.83 GiB of Switch bundles -> 5.09 GiB (ASTC decoded to RGBA32, LZ4) = x1.33
BUNDLE_GROWTH = 1.45
MARK = 'StreamingAssets/AssetAssistant/Dpr.bin'


class DumpError(Exception):
    pass


def find_dump(selected):
    """-> the dump's romfs Data folder under / around what the user picked (the dump folder, romfs, romfs/Data, a title-id
    folder above them ...). Raises DumpError with a message a player can act on."""
    from . import advice
    sel = os.path.abspath(selected)
    if not os.path.isdir(sel):
        raise DumpError(advice.text(f'The folder {sel} does not exist (it was moved, renamed, or is on a drive that is not '
                                    f'connected)', ['Press Browse... and pick the folder of your dump where it is now']))
    if os.path.isfile(os.path.join(sel, 'Dpr.exe')) and os.path.isdir(os.path.join(sel, 'udpre')):
        raise DumpError(advice.text(f'{sel} is the uDPRE folder, not your game dump',
                                    ['Press Browse... and pick the folder you extracted your Brilliant Diamond dump to '
                                     '(the one that holds "romfs")']))
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
    looks_mod = any(os.path.isdir(os.path.join(c, 'StreamingAssets')) for c in cands) or \
        any(d.lower() == 'exefs' for d in os.listdir(sel))
    steps = ['Pick the folder you extracted your own Pokemon Brilliant Diamond dump to: it holds a folder "romfs", with '
             '"Data" inside, and "Data" holds "StreamingAssets" and "globalgamemanagers"',
             'If you only have the game as one file (.nsp / .xci), extract its romfs first with your dumping tool - the '
             'base game together with the v1.3.0 update']
    if looks_mod:
        steps.insert(0, 'This looks like a mod, not the game. Mods go into the mods folder of uDPRE; here you pick the '
                        'game itself')
    raise DumpError(advice.text(f'{sel} does not hold the game files of Pokemon Brilliant Diamond', steps))


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_dump(data, bundles, packs=None):
    """-> list of problems, each a text a player can act on (empty = a complete Brilliant Diamond v1.3.0 romfs). packs =
    the mod packs found ({id: Mod}): a dump with a pack's download copied into it is named as such."""
    from . import advice
    redump = ('Extract your dump again into a NEW, empty folder: the base game AND the v1.3.0 update, extracted together '
              '(the update\'s files over the base game\'s), then pick that folder')
    wrong = []
    for rel, want, size in FINGERPRINTS:
        p = os.path.join(data, *rel.split('/'))
        if not os.path.isfile(p):
            return [advice.text(f'Your dump has no {rel}: it is incomplete', [redump])]
        if os.path.getsize(p) != size or sha1(p) != want:
            wrong.append(rel)
    if wrong:
        # whose file is it? a mod copied over the dump (its pack lists the file), else another game / version
        for m in (packs or {}).values():
            for sid in m.sources:
                try:
                    lst = m.source_list(sid)
                except (OSError, ValueError):
                    continue
                for rel in wrong:
                    p = os.path.join(data, *rel.split('/'))
                    if rel in lst and os.path.getsize(p) == lst[rel][0] and sha1(p) == lst[rel][1]:
                        name = m.sources[sid].get('name', sid)
                        if not modlib._is_game_dump(data):
                            return [advice.text(
                                f'{data} is the {name} mod download, not your game dump',
                                ['Press Browse... and pick the folder of your own Brilliant Diamond dump (the whole '
                                 'game, about 8 GB)', f'Keep {name} in the mods folder of uDPRE: the {m.name} pack uses '
                                                      f'it from there'])]
                        return [advice.text(
                            f'Your dump has the files of {name} copied into it ({rel} is the mod\'s). uDPRE needs the game '
                            f'exactly as dumped, with mods kept apart', [redump,
                                                                         f'Keep {name} as its own folder in the mods '
                                                                         f'folder of uDPRE (the {m.name} pack uses it '
                                                                         f'from there)'])]
        if wrong == [MARK]:
            return [advice.text(f'Your dump\'s {MARK} is not the one of Brilliant Diamond v1.3.0: a mod was copied over '
                                f'the dump', [redump, 'Put mods into the mods folder of uDPRE instead of into the dump'])]
        return [advice.text('This is not Pokemon Brilliant Diamond v1.3.0: it is Shining Pearl, an older version of the '
                            'game (without the v1.3.0 update), or a dump with mod files copied into it',
                            ['Dump Pokemon Brilliant Diamond (uDPRE does not work with Shining Pearl) together with its '
                             'v1.3.0 update', redump])]
    bad = []
    aa = os.path.join(data, 'StreamingAssets', 'AssetAssistant')
    missing = [b for b in bundles if not os.path.isfile(os.path.join(aa, *b.split('/')))]
    if missing:
        bad.append(advice.text(f'{len(missing)} of the {len(bundles)} game files are missing from your dump (for example '
                               f'{missing[0]}): the extraction stopped before the end, or files were deleted',
                               [redump, 'Check that the drive has room for the whole game (about 8 GB)']))
    for t in COPY_TREES:
        if not os.path.isdir(os.path.join(data, *t.split('/'))):
            bad.append(advice.text(f'Your dump has no {t} folder: it is incomplete', [redump]))
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
    picked = {source id: folder} downloads the player pointed at outside the mods folder; options = {pack id: {option id:
    choice id}} the picks under the packs' ticks."""

    def __init__(self, p, mod_ids, picked=None, options=None, overrides=None):
        self.found, self.problems = modlib.discover(p.mods, picked)
        self.chosen = modlib.choose(self.found, mod_ids, options)
        # {player path: file} put in place instead of the player's own (the editor's metadata with the type chart edits)
        self.overrides = dict(overrides or {})
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


def fingerprint(p, setup, edits=None):
    """What the converted data was made against: player base globalgamemanagers, shader pack per container, mod set, and
    the edit project's digest when the edits are on."""
    return {'base_ggm': sha1(setup.base_ggm), 'pack': pack_digests(p, setup.pack), 'player': setup.player_id,
            'mods': modlib.signature(setup.chosen), 'edits': edits,
            'merge': load_config(p).get('merge_choices') if any(m.raw for m in setup.chosen) else None}


def edits_digest(p, cfg):
    """the digest of edits/project.json when the conversion uses the edits (config edits_on), else None"""
    if not cfg.get('edits_on'):
        return None
    from .edit import build as editbuild
    from .edit.project import Project
    try:
        return Project(editbuild.project_path(p.root)).digest()
    except Exception as e:      # a damaged project: status() says so, the conversion reports the error
        return f'unreadable: {e}'


def kept_overrides(cfg):
    """{player path: file} the last build made (edited metadata), while the edits are on"""
    if not cfg.get('edits_on'):
        return {}
    return {rel: f for rel, f in ((cfg.get('edits') or {}).get('overrides') or {}).items() if os.path.isfile(f)}


def expected_player(p, setup):
    """{root-relative player file: sha1 it must have} for the chosen player (ours, or a pack's profile), with the editor's
    overrides."""
    vanilla = _load_json(p.player_files, {}).get('files', {})
    if setup.profile is None:
        want = dict(vanilla)
    else:
        want = {rel: sha1(os.path.join(setup.player_dir, *rel.split('/'))) for rel in setup.profile['files']}
    for rel, f in setup.overrides.items():
        if rel in want:
            want[rel] = sha1(f)
    return want


def status(p):
    """-> {'state': 'ready' | 'refresh' | 'convert', 'stale': [containers to convert again], 'reason': text, 'mods': ids}.
    convert = no complete conversion for this CONVERT_VERSION; refresh = something changed since the conversion (a release
    update of our player base or shaders, the chosen mods, missing files): only the affected files are made again."""
    cfg = load_config(p)
    mod_ids = cfg.get('mods', [])
    opts = cfg.get('options', {})
    if cfg.get('complete_version') != CONVERT_VERSION:
        if cfg.get('complete_version') is not None:
            return {'state': 'convert', 'stale': [], 'reason': 'this uDPRE version converts the game data in a new way',
                    'mods': mod_ids, 'options': opts}
        return {'state': 'convert', 'stale': [], 'reason': 'not converted yet', 'mods': mod_ids, 'options': opts}
    try:
        setup = Setup(p, mod_ids, cfg.get('sources'), opts, kept_overrides(cfg))
    except modlib.ModError as e:
        return {'state': 'refresh', 'stale': [], 'reason': f'the mod choice cannot be used: {e}', 'mods': mod_ids,
                'options': opts}
    old, now = cfg.get('fingerprint') or {}, fingerprint(p, setup, edits_digest(p, cfg))
    stale = sorted(c for c, d in now['pack'].items() if (old.get('pack') or {}).get(c) != d)
    reasons = []
    if stale:
        reasons.append(f'new shaders for {len(stale)} files')
    if old.get('base_ggm') != now['base_ggm'] or old.get('player', 'vanilla') != now['player']:
        reasons.append('a new player')
    if old.get('mods', []) != now['mods']:
        reasons.append('the mods')
    if old.get('edits') != now['edits']:
        reasons.append('your edits')
    if old.get('merge') != now['merge']:
        reasons.append('the merge choices')
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
        return {'state': 'refresh', 'stale': stale, 'reason': '; '.join(reasons), 'mods': mod_ids, 'options': opts}
    return {'state': 'ready', 'stale': [], 'reason': '', 'mods': mod_ids, 'options': opts}


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
        from . import advice
        raise ConvertError(advice.text('This uDPRE folder is incomplete (udpre/player_files.json is missing)',
                                       [advice.unzip_udpre_again()]))
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
        if rel in setup.overrides:
            src = setup.overrides[rel]
        elif setup.profile is not None:
            src = os.path.join(setup.player_dir, *rel.split('/'))
        else:
            src = os.path.join(p.vanilla_player, *rel.split('/'))
            if not os.path.isfile(src) or sha1(src) != h:
                from . import advice
                raise ConvertError(advice.text(f'The game file {rel} is not the one of this uDPRE release (a patch or '
                                               f'another build was copied over the folder), and uDPRE has no copy of the '
                                               f'right one', [advice.unzip_udpre_again(),
                                                              'Do not copy patches made for other PC builds into a '
                                                              'uDPRE folder: use uDPRE mod packs']))
        try:
            place(src, cur)
        except PermissionError:
            from . import advice
            raise ConvertError(advice.text(f'{rel} is in use, so uDPRE cannot replace it',
                                           ['Close the game (Dpr.exe) - check the taskbar and Task Manager - then '
                                            'press Convert again']))
        changed += 1
    for rel in cfg.get('player_extra', []):
        f = os.path.join(p.root, *rel.split('/'))
        if rel not in want and os.path.isfile(f):
            os.remove(f)
    cfg['player_extra'] = [r for r in want if r not in vanilla]
    log(f'player: {setup.player_id} ({changed} files put in place)')


def run(root, dump_selected=None, workers=None, progress=print, log=print, mods=None, options=None, edits=None):
    """Converts the dump (+ the chosen mods) into the uDPRE folder `root` - everything on a first run, later only what
    changed (status()). dump_selected None = the dump of the last conversion; mods None = the mods chosen last time (a list
    of pack ids); options = picks under the packs' ticks {pack id: {option id: choice id}}, laid over the picks kept from
    last time; edits None = use the edit project as last time, True / False = use it / not. progress(stage, done, total) /
    log(text). Returns a summary dict; raises DumpError / ConvertError."""
    from . import advice
    p = Paths(root)
    cfg = load_config(p)
    if dump_selected is None:
        dump_selected = cfg.get('dump')
        if not dump_selected:
            raise DumpError(advice.text('uDPRE does not know your dump yet',
                                        ['Press Browse... and pick the folder of your Brilliant Diamond dump, then '
                                         'Convert (from the console: uDPRE.exe convert "D:\\Dumps\\BDSP")']))
        if not os.path.isdir(dump_selected):
            raise DumpError(advice.text(f'The dump you used last time is not there any more ({dump_selected}): it was '
                                        f'moved, renamed, or is on a drive that is not connected',
                                        ['Connect the drive, or press Browse... and pick the dump where it is now, '
                                         'then Convert']))
    data = find_dump(dump_selected)
    bundles = p.bundle_list()
    log(f'dump: {data}')
    try:
        packs_found = modlib.discover(p.mods, cfg.get('sources'))[0]
    except OSError:
        packs_found = {}
    problems = verify_dump(data, bundles, packs_found)
    if problems:
        raise DumpError('\n\n'.join(problems))
    mod_ids = list(cfg.get('mods', []) if mods is None else mods)
    opts = {k: dict(v) for k, v in cfg.get('options', {}).items()}
    for k, v in (options or {}).items():
        opts.setdefault(k, {}).update(v)
    try:
        setup = Setup(p, mod_ids, cfg.get('sources'), opts)
        stack = modlib.Stack(data, setup.chosen, bundles)
        shaders_src = stack.shaders_bundle()
    except modlib.ModError as e:
        raise DumpError(str(e))     # already a text with what to do (mods.py / advice.py)
    for m in setup.chosen:
        log(f'mod: {m.name} {m.version}' + ''.join(f'; {o["name"]}: {m.choice_name(o["id"])}' for o in m.options)
            + ''.join(f'; your {m.sources[s].get("name", s)}: {d}' for s, d in m.source_paths.items()))
    verify_sources(p, setup, progress)
    if any(m.raw for m in setup.chosen):
        # console mods that bring a file another mod also brings: merged object by object (merge.py)
        from . import merge
        progress('merging console mods', 0, 1)
        rep = merge.apply(stack, p.state, data, cfg.get('merge_choices'), log)
        n_conf = sum(len(v['conflicts']) for v in rep.values())
        if rep:
            log(f'merged {len(rep)} files that console mods share with other mods ({n_conf} conflicts, '
                f'udpre/state/merged/report.json)')
        progress('merging console mods', 1, 1)
    else:
        from . import merge
        merge.clear(p.state)        # no console mod: the merged files of an earlier choice are not needed
    if edits is not None:
        cfg['edits_on'] = bool(edits)
    edit_digest = None
    if cfg.get('edits_on'):
        from .edit import build as editbuild
        progress('your edits', 0, 1)
        try:
            built = editbuild.build(p, stack, setup, log)
        except Exception as e:      # a project the current files cannot take: the conversion stops before changing anything
            raise DumpError(advice.text(
                'Your edits (Editor & Randomizer) could not be applied to the game files of this mod choice. Nothing was '
                'changed', ['To play now without them: untick "Use my edits in the game" and press Apply',
                            'To fix them: open Editor & Randomizer, Your edits page, and undo or remove the last changes, '
                            'then tick "Use my edits" again and press Apply',
                            'Edits made with other mods ticked can need those mods: tick the same mods as when you made '
                            'them'], details=f'{type(e).__name__}: {e}'))
        edit_digest = built.digest
        if built.layer is not None:
            stack = modlib.Stack(data, setup.chosen + [built.layer], bundles)
        setup.overrides = dict(built.overrides)
        cfg['edits'] = {'digest': built.digest, 'overrides': built.overrides, 'changed': built.changed,
                        'skipped': len(built.warnings)}
        progress('your edits', 1, 1)
    else:
        cfg.pop('edits', None)
        from .edit import build as editbuild
        editbuild.clear(p)
    odd_src = {k: s for k, s in stack.copies().items() if s.kind == 'switch' and not k.startswith(COPY_PREFIXES)}
    if odd_src:
        names = {m.id: m for m in setup.chosen}
        by_mod = {}
        for k, s in sorted(odd_src.items()):
            by_mod.setdefault(names[s.mod].name if s.mod in names else 'your dump', []).append(k)
        raise DumpError(advice.text(
            'A mod brings Switch files uDPRE cannot use on PC: ' +
            '; '.join(f'{n} ({", ".join(v[:3])}{" ..." if len(v) > 3 else ""})' for n, v in by_mod.items()),
            ['Untick that mod (or move its folder out of the mods folder) and press Apply',
             'Files like these (game code, the Switch player\'s own files) only work on a console; a uDPRE pack of the '
             'mod is needed to use it on PC']))
    old_fp = cfg.get('fingerprint') or {}
    st0 = status(p)
    if st0['state'] == 'refresh':
        log(f'refresh: {st0["reason"]}')
    # picks of packs that are off stay remembered for when they come back on
    opts.update(modlib.picks(setup.chosen))
    cfg.update({'dump': data, 'mods': setup.mod_ids, 'options': opts, 'started_version': CONVERT_VERSION})
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
        drive = os.path.splitdrive(p.root)[0] or p.root
        raise DumpError(advice.text(
            f'Not enough free space on drive {drive}: {free / 2**30:.1f} GB free, about {need / 2**30:.1f} GB needed for '
            f'this conversion', [f'Free at least {(need - free) / 2**30 + 0.5:.1f} GB on {drive} (empty the Recycle Bin, '
                                 f'delete or move big files), then press Convert again',
                                 'Or move the whole uDPRE folder to a drive with more room and convert there']))
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
    if errors:
        # a mod's bundle that does not even load on its own (a damaged file the mod ships) is made from the layer below
        from .merge import _loads
        still = []
        with open(p.done_log, 'a', encoding='utf-8', newline='\n') as dl:
            for rel, err in errors:
                s = want[rel][0]
                lower = [x for x in stack.all_sources.get(modlib.AA + '/' + rel, []) if x is not s and x.kind == 'switch']
                if s.mod is None or _loads(s.path) or not lower:
                    still.append((rel, err))
                    continue
                below = lower[-1]
                try:
                    from . import bundle
                    from .shaderpack import ShaderPack as _SP
                    st = bundle.convert_bundle(below.path, os.path.join(p.aa_out, *rel.split('/')), rel, _SP(setup.pack),
                                               ids, strict_streams=below.mod is None)
                    # recorded under the mod file's own key: it is not tried again until the mod's file changes
                    dl.write(f'{rel}\t{st.get("bytes", 0)}\t{want[rel][1]}\n')
                    log(f'{rel}: the file {s.mod} brings is damaged (it does not load) - made from the layer below')
                except Exception as e:
                    still.append((rel, f'{err}\nlayer below: {type(e).__name__}: {e}'))
        errors = still
    log(f'bundles: {time.time() - t0:.0f} s, {len(errors)} failed, totals {totals}')
    if errors:
        report = os.path.join(p.state, 'errors.txt')
        with open(report, 'w', encoding='utf-8') as f:
            for rel, err in errors:
                f.write(f'== {rel}\n{err}\n')
        names = {m.id: m.name for m in setup.chosen}
        from_mods = {}
        n_dump = 0
        for rel, _err in errors:
            s = want[rel][0]
            if s.mod is None:
                n_dump += 1
            else:
                from_mods.setdefault(names.get(s.mod, s.mod), []).append(rel)
        steps = ['Press Convert again: only the files that failed are made again (a full disk or a busy PC can stop a '
                 'few of them)']
        for n, v in from_mods.items():
            steps.append(f'{len(v)} of them come from {n}: if they fail again, that mod\'s files are damaged - download '
                         f'it again and replace its folder, or untick it')
        if n_dump:
            steps.append(f'{n_dump} of them come from your dump: if they fail again, your dump is damaged - extract it '
                         f'again into an empty folder and pick that folder')
        steps.append(f'If nothing helps, report it with the file {report}')
        raise ConvertError(advice.text(f'{len(errors)} of the game files could not be converted', steps))
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
    cfg['fingerprint'] = fingerprint(p, setup, edit_digest)
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
            from . import advice
            name = m.sources[sid].get('name', sid)
            n_all = len(m.source_list(sid))
            many = len(bad) > n_all // 10
            raise DumpError(advice.text(
                f'Your copy of {name} ({root}) is ' + ('another version of the mod' if many else 'incomplete or changed') +
                f': {len(bad)} of the {n_all} files the {m.name} pack needs are missing or different (for example '
                f'{"; ".join(bad[:2])})',
                [f'Download {name} again {advice.get_from(m)}'.rstrip() + (f' - exactly {name}, for Brilliant Diamond'
                                                                           if many else ''),
                 f'Extract it with 7-Zip ({advice.SEVEN_ZIP}) into a NEW folder (Windows\' own zip tool and extractions '
                 f'that stopped early leave files out), and do not change or add files in it',
                 f'Replace the old folder with it (in the mods folder, or wherever "Find a mod download..." points), then '
                 f'press Convert']))
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
