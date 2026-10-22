"""Mod packs: what lies in <uDPRE folder>/mods, which ones are on, and the layer stack they make over the dump.

A mod pack is a folder with udpre_mod.json (format 1):
  id, name, version, order (layer position: higher = on top), requires / conflicts (ids), player (optional folder of a player
  profile), layers = [{"romfs": DIR} | {"files": DIR}, optional "when": [ids], "unless": [ids], optional "dump":
  {romfs path: dump path} = files of the mod that are byte-identical to a dump file, taken from the dump].
  A romfs layer holds SWITCH files with their romfs/Data paths; they go through the same conversion as the dump, so the pack's
  bundles and the dump's keep pointing at each other by the Switch path IDs. A files layer holds WINDOWS files with their
  Dpr_Data paths, copied as they are. Later layers of one pack override earlier ones; a layer counts only when every id in
  "when" is on and none in "unless".
A folder without udpre_mod.json that holds romfs/Data (a plain LayeredFS mod made for the console) is taken as a data-only mod
on top of everything, unless it also carries exefs/ code: such a mod needs a uDPRE pack with its player, and is refused.
"""
import json
import os

FORMAT = 1
MANIFEST = 'udpre_mod.json'
RAW_ORDER = 1000
AA = 'StreamingAssets/AssetAssistant'
AUDIO_SW = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch'
AUDIO_WIN = 'StreamingAssets/Audio/GeneratedSoundBanks/Windows'


class ModError(ValueError):
    pass


class Mod:
    def __init__(self, path, data, raw=False):
        self.path = path
        self.raw = raw
        self.id = data['id']
        self.name = data.get('name', self.id)
        self.version = str(data.get('version', ''))
        self.order = int(data.get('order', RAW_ORDER))
        self.requires = list(data.get('requires', []))
        self.conflicts = list(data.get('conflicts', []))
        self.player = data.get('player')
        self.layers = list(data.get('layers', []))
        self.description = data.get('description', '')

    def active_layers(self, enabled):
        """-> [(kind, folder, spec)] of the layers that count with these mods on."""
        out = []
        for spec in self.layers:
            if all(w in enabled for w in spec.get('when', [])) and not any(u in enabled for u in spec.get('unless', [])):
                kind = 'romfs' if 'romfs' in spec else 'files'
                out.append((kind, spec[kind], spec))
        return out

    def player_dir(self):
        return os.path.join(self.path, self.player) if self.player else None

    def __repr__(self):
        return f'Mod({self.id} {self.version})'


def _find_romfs_data(folder):
    """-> the romfs/Data folder inside a plain LayeredFS mod (up to 3 levels down), else None."""
    for root, dirs, _ in os.walk(folder):
        if root[len(folder):].count(os.sep) >= 3:
            dirs[:] = []
            continue
        if os.path.basename(root).lower() == 'romfs' and os.path.isdir(os.path.join(root, 'Data')):
            return os.path.join(root, 'Data')
    return None


def _has_exefs(folder):
    for root, dirs, _ in os.walk(folder):
        if root[len(folder):].count(os.sep) >= 3:
            dirs[:] = []
            continue
        if any(d.lower() == 'exefs' for d in dirs):
            return True
    return False


def load_manifest(path):
    with open(os.path.join(path, MANIFEST), encoding='utf-8') as f:
        d = json.load(f)
    if d.get('format') != FORMAT:
        raise ModError(f'{os.path.basename(path)}: mod pack format {d.get("format")}, this uDPRE reads format {FORMAT} - '
                       f'get the uDPRE release the pack was made for')
    if not d.get('id'):
        raise ModError(f'{os.path.basename(path)}: {MANIFEST} has no id')
    for spec in d.get('layers', []):
        kind = 'romfs' if 'romfs' in spec else 'files' if 'files' in spec else None
        if kind is None:
            raise ModError(f'{d["id"]}: a layer names neither romfs nor files')
        if not os.path.isdir(os.path.join(path, spec[kind])):
            raise ModError(f'{d["id"]}: layer folder {spec[kind]} is missing - the pack is incomplete')
    if d.get('player') and not os.path.isfile(os.path.join(path, d['player'], 'profile.json')):
        raise ModError(f'{d["id"]}: player folder {d["player"]} has no profile.json - the pack is incomplete')
    return Mod(path, d)


def discover(mods_dir):
    """-> ({id: Mod}, [problem texts]). Problems are packs that cannot be used (shown, not fatal)."""
    found, problems = {}, []
    if not os.path.isdir(mods_dir):
        return found, problems
    for name in sorted(os.listdir(mods_dir)):
        path = os.path.join(mods_dir, name)
        if not os.path.isdir(path):
            continue
        try:
            if os.path.isfile(os.path.join(path, MANIFEST)):
                m = load_manifest(path)
            else:
                data = _find_romfs_data(path)
                if data is None:
                    continue
                if _has_exefs(path):
                    problems.append(f'{name}: this mod changes the game code (exefs), so it needs a uDPRE mod pack made '
                                    f'for it; the console version cannot be used as it is.')
                    continue
                m = Mod(path, {'id': 'raw:' + name, 'name': name + ' (console mod, data only)',
                               'layers': [{'romfs': os.path.relpath(data, path)}]}, raw=True)
            if m.id in found:
                problems.append(f'{name}: id {m.id} is also used by {os.path.basename(found[m.id].path)} - ignored')
                continue
            found[m.id] = m
        except (ModError, OSError, ValueError, KeyError) as e:
            problems.append(f'{name}: {e}')
    return found, problems


def choose(found, enabled_ids):
    """Enabled ids -> the mods in layer order (bottom first). Raises ModError naming every problem."""
    bad = []
    chosen = []
    on = set(enabled_ids)
    for i in enabled_ids:
        if i not in found:
            bad.append(f'mod "{i}" is not in the mods folder')
            continue
        chosen.append(found[i])
    for m in chosen:
        for r in m.requires:
            if r not in on:
                bad.append(f'{m.name} needs {found[r].name if r in found else r}')
        for c in m.conflicts:
            if c in on:
                bad.append(f'{m.name} cannot be used together with {found[c].name if c in found else c}')
    if bad:
        raise ModError('\n'.join(dict.fromkeys(bad)))
    return sorted(chosen, key=lambda m: (m.order, m.id))


def signature(chosen):
    """What a conversion was made with: per mod id, version and the layers it used (they change with the other mods)."""
    on = {m.id for m in chosen}
    return [[m.id, m.version, [f'{kind}:{d}' for kind, d, _ in m.active_layers(on)]] for m in chosen]


def player_mod(chosen):
    """The top-most chosen mod that brings a player profile, else None (our vanilla player)."""
    for m in reversed(chosen):
        if m.player:
            return m
    return None


def out_rel(romfs_rel):
    """romfs/Data path -> Dpr_Data path (the Switch-built Wwise banks go to the folder the Windows runtime reads)."""
    if romfs_rel == AUDIO_SW or romfs_rel.startswith(AUDIO_SW + '/'):
        return AUDIO_WIN + romfs_rel[len(AUDIO_SW):]
    return romfs_rel


def _walk(root):
    for d, _, fs in os.walk(root):
        for f in fs:
            full = os.path.join(d, f)
            yield os.path.relpath(full, root).replace(os.sep, '/'), full


class Source:
    """One file of the stack: kind 'switch' (convert / take from a Switch file) or 'windows' (copy as is)."""
    __slots__ = ('kind', 'path', 'key', 'mod')

    def __init__(self, kind, path, key, mod):
        self.kind, self.path, self.key, self.mod = kind, path, key, mod


class Stack:
    """The dump + the chosen mods' active layers. index: Dpr_Data path -> the top-most Source."""

    def __init__(self, dump_data, chosen, bundle_list):
        self.dump = dump_data
        self.chosen = chosen
        self.index = {}
        on = {m.id for m in chosen}
        aa = os.path.join(dump_data, *AA.split('/'))
        for rel in bundle_list:
            self.index[AA + '/' + rel] = Source('switch', os.path.join(aa, *rel.split('/')), 'dump', None)
        for top in ('resources.assets', 'resources.assets.resS', 'globalgamemanagers', AA + '/Dpr.bin'):
            self.index[top] = Source('switch', os.path.join(dump_data, *top.split('/')), 'dump', None)
        for tree in (AUDIO_SW, 'StreamingAssets/Movie'):
            base = os.path.join(dump_data, *tree.split('/'))
            for rel, full in _walk(base):
                self.index[out_rel(tree + '/' + rel)] = Source('switch', full, 'dump', None)
        for m in chosen:
            for kind, d, spec in m.active_layers(on):
                root = os.path.join(m.path, d)
                # files of the mod that are byte-identical to another dump file (Luminescent re-uses game sounds under new
                # ids): the pack names the dump file instead of carrying its bytes
                for rel, dump_rel in (spec.get('dump') or {}).items():
                    src = os.path.join(dump_data, *dump_rel.split('/'))
                    if not os.path.isfile(src):
                        raise ModError(f'{m.name}: needs the dump file {dump_rel}, which is missing')
                    self.index[out_rel(rel)] = Source('switch', src, f'{m.id}@{m.version}/{d}:dump={dump_rel}', m.id)
                for rel, full in _walk(root):
                    if rel.endswith('.manifest') or rel.endswith('.part'):
                        continue
                    st = os.stat(full)
                    key = f'{m.id}@{m.version}/{d}:{st.st_size}:{st.st_mtime_ns}'
                    if kind == 'romfs':
                        self.index[out_rel(rel)] = Source('switch', full, key, m.id)
                    else:
                        self.index[rel] = Source('windows', full, 'copy:' + key, m.id)

    def bundles(self):
        """{bundle path under AssetAssistant: Source} - every file there except the catalog."""
        pre = AA + '/'
        return {k[len(pre):]: s for k, s in self.index.items() if k.startswith(pre) and k != AA + '/Dpr.bin'}

    def copies(self):
        """{Dpr_Data path: Source} copied byte for byte: catalog, audio, movies, and every Windows file outside the bundles."""
        pre = AA + '/'
        out = {}
        for k, s in self.index.items():
            if k in ('resources.assets', 'resources.assets.resS', 'globalgamemanagers'):
                continue
            if k.startswith(pre) and k != AA + '/Dpr.bin':
                continue
            out[k] = s
        return out

    def player_source(self, name):
        s = self.index.get(name)
        if s is None or s.kind != 'switch':
            raise ModError(f'{name}: no Switch copy in the dump or the mods')
        return s.path

    def shaders_bundle(self):
        s = self.index.get(AA + '/Dpr/shaders')
        if s is None:
            raise ModError('Dpr/shaders is missing')
        return s


def load_profile(mod):
    """-> (profile dict, player folder) of a mod that brings a player."""
    d = mod.player_dir()
    with open(os.path.join(d, 'profile.json'), encoding='utf-8') as f:
        prof = json.load(f)
    for rel in prof.get('files', []):
        if not os.path.isfile(os.path.join(d, *rel.split('/'))):
            raise ModError(f'{mod.name}: player file {rel} is missing - the pack is incomplete')
    for rel in ('udpre/base/globalgamemanagers', 'udpre/shaders.pack'):
        if not os.path.isfile(os.path.join(d, *rel.split('/'))):
            raise ModError(f'{mod.name}: player file {rel} is missing - the pack is incomplete')
    return prof, d
