"""Mod packs: what lies in <uDPRE folder>/mods, which ones are on, and the layer stack they make over the dump.

A mod pack is a folder with udpre_mod.json (format 1):
  id, name, version, author + url (credit: the mod's authors and its own page), order (layer position: higher = on top),
  requires / conflicts (ids), player (optional folder of a player
  profile), sources (optional: downloads the PLAYER brings - {id: {"name", "where", "list", "key"}}; list = a JSON file
  {romfs path: [size, sha1]} of the files the pack uses, key = the romfs path that identifies the download), layers = list of
    {"romfs": DIR}    SWITCH files with their romfs/Data paths, converted like the dump;
    {"source": ID}    the listed Switch files of the player's own download ID (a mod we do not redistribute);
    {"files": DIR}    WINDOWS files with their Dpr_Data paths, copied as they are;
  each with optional "when": [ids], "unless": [ids] (the layer counts only when every id in "when" is on and none in "unless"),
  optional "dump": {romfs path: dump path} (a mod file byte-identical to another dump file, taken from the dump) and optional
  "copy": {romfs path: romfs path} (a file that is a copy of another one of the stack below, e.g. a translation's opening
  movie = the base mod's). Later layers of one pack override earlier ones.
Switch files go through the same conversion as the dump, so the pack's bundles and the dump's keep pointing at each other by
the Switch path IDs.
A player's download is found anywhere under the mods folder (any folder holding romfs/Data whose key file has the listed
size and sha1), or at a folder the player picked (config "sources"). Every listed file is checked against its sha1 before a
conversion uses it (install.verify_sources).
A folder without udpre_mod.json that holds romfs/Data (a plain LayeredFS mod made for the console) is taken as a data-only mod
on top of everything, unless it also carries exefs/ code: such a mod needs a uDPRE pack with its player, and is refused -
except when it is the download a pack names as its source.
"""
import hashlib
import json
import os

FORMAT = 1
MANIFEST = 'udpre_mod.json'
RAW_ORDER = 1000
AA = 'StreamingAssets/AssetAssistant'
AUDIO_SW = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch'
AUDIO_WIN = 'StreamingAssets/Audio/GeneratedSoundBanks/Windows'
KINDS = ('romfs', 'source', 'files')
SEARCH_DEPTH = 6


class ModError(ValueError):
    pass


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


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
        self.author = data.get('author', '')            # the mod's author(s), credited in the window
        self.url = data.get('url', '')                  # the mod's own page (Nexus Mods)
        self.sources = dict(data.get('sources', {}))
        self.source_paths = {}          # source id -> romfs/Data folder of the player's download (found by discover)
        self._lists = {}

    def source_list(self, sid):
        """{romfs path: [size, sha1]} of the files the pack takes from download sid."""
        if sid not in self._lists:
            with open(os.path.join(self.path, self.sources[sid]['list']), encoding='utf-8') as f:
                self._lists[sid] = json.load(f)
        return self._lists[sid]

    def missing_sources(self):
        return [sid for sid in self.sources if sid not in self.source_paths]

    def active_layers(self, enabled):
        """-> [(kind, folder or source id, spec)] of the layers that count with these mods on."""
        out = []
        for spec in self.layers:
            if all(w in enabled for w in spec.get('when', [])) and not any(u in enabled for u in spec.get('unless', [])):
                kind = next(k for k in KINDS if k in spec)
                out.append((kind, spec[kind], spec))
        return out

    def player_dir(self):
        return os.path.join(self.path, self.player) if self.player else None

    def __repr__(self):
        return f'Mod({self.id} {self.version})'


def _romfs_datas(folder, depth=SEARCH_DEPTH):
    """-> every romfs/Data folder under folder (up to `depth` levels down)."""
    out = []
    for root, dirs, _ in os.walk(folder):
        if root[len(folder):].count(os.sep) >= depth:
            dirs[:] = []
            continue
        if os.path.basename(root).lower() == 'romfs' and os.path.isdir(os.path.join(root, 'Data')):
            out.append(os.path.join(root, 'Data'))
            dirs[:] = []
    return out


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
    for sid, s in d.get('sources', {}).items():
        if not os.path.isfile(os.path.join(path, s.get('list', ''))) or not s.get('key'):
            raise ModError(f'{d["id"]}: the file list of source {sid} is missing - the pack is incomplete')
    for spec in d.get('layers', []):
        kind = next((k for k in KINDS if k in spec), None)
        if kind is None:
            raise ModError(f'{d["id"]}: a layer names neither romfs, source nor files')
        if kind == 'source':
            if spec['source'] not in d.get('sources', {}):
                raise ModError(f'{d["id"]}: a layer takes source {spec["source"]}, which the pack does not describe')
        elif not os.path.isdir(os.path.join(path, spec[kind])):
            raise ModError(f'{d["id"]}: layer folder {spec[kind]} is missing - the pack is incomplete')
    if d.get('player') and not os.path.isfile(os.path.join(path, d['player'], 'profile.json')):
        raise ModError(f'{d["id"]}: player folder {d["player"]} has no profile.json - the pack is incomplete')
    return Mod(path, d)


def matches_source(data, mod, sid):
    """Is the romfs/Data folder `data` the download `sid` of `mod`? (its key file has the listed size and sha1)"""
    key = mod.sources[sid]['key']
    size, digest = mod.source_list(sid)[key]
    p = os.path.join(data, *key.split('/'))
    return os.path.isfile(p) and os.path.getsize(p) == size and sha1(p) == digest


def find_source(folder, mod, sid):
    """-> the romfs/Data folder of download sid inside / at `folder`, else None."""
    cands = [folder] if os.path.isfile(os.path.join(folder, *mod.sources[sid]['key'].split('/'))) else []
    for c in cands + _romfs_datas(folder):
        if matches_source(c, mod, sid):
            return c
    return None


def discover(mods_dir, picked=None):
    """-> ({id: Mod}, [problem texts]). Problems are packs that cannot be used (shown, not fatal). picked = {source id:
    folder} the player chose for downloads kept outside the mods folder."""
    found, problems, raw = {}, [], []
    if not os.path.isdir(mods_dir):
        return found, problems
    for name in sorted(os.listdir(mods_dir)):
        path = os.path.join(mods_dir, name)
        if not os.path.isdir(path):
            continue
        try:
            if os.path.isfile(os.path.join(path, MANIFEST)):
                m = load_manifest(path)
                if m.id in found:
                    problems.append(f'{name}: id {m.id} is also used by {os.path.basename(found[m.id].path)} - ignored')
                    continue
                found[m.id] = m
            else:
                datas = _romfs_datas(path)
                if datas:
                    raw.append((name, path, datas))
        except (ModError, OSError, ValueError, KeyError) as e:
            problems.append(f'{name}: {e}')
    # the downloads packs need: in the mods folder (a raw folder, or inside a pack folder), or where the player pointed
    claimed = set()
    datas_all = [(n, d) for n, _, ds in raw for d in ds] + \
                [(None, d) for m in found.values() if m.sources for d in _romfs_datas(m.path)]
    for m in found.values():
        for sid in m.sources:
            try:
                for n, d in datas_all:
                    if matches_source(d, m, sid):
                        m.source_paths[sid] = d
                        claimed.add(n)
                        break
                else:
                    p = (picked or {}).get(sid)
                    if p and os.path.isdir(p):
                        d = find_source(p, m, sid)
                        if d:
                            m.source_paths[sid] = d
            except (OSError, ValueError, KeyError) as e:
                problems.append(f'{os.path.basename(m.path)}: {e}')
    for name, path, datas in raw:
        if name in claimed:
            continue
        if _has_exefs(path):
            problems.append(f'{name}: this mod changes the game code (exefs), so it needs a uDPRE mod pack made for it; '
                            f'the console version cannot be used as it is.')
            continue
        m = Mod(path, {'id': 'raw:' + name, 'name': name + ' (console mod, data only)',
                       'layers': [{'romfs': os.path.relpath(datas[0], path)}]}, raw=True)
        if m.id not in found:
            found[m.id] = m
    return found, problems


def source_text(m, sid):
    s = m.sources[sid]
    return f'{m.name} needs your own copy of {s.get("name", sid)}: {s.get("where", "")}'.rstrip(': ')


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
    pairs = set()
    for m in chosen:
        for r in m.requires:
            if r not in on:
                bad.append(f'{m.name} needs {found[r].name if r in found else r}')
        for c in m.conflicts:
            if c in on and frozenset((m.id, c)) not in pairs:
                pairs.add(frozenset((m.id, c)))
                bad.append(f'{m.name} cannot be used together with {found[c].name if c in found else c}')
        for sid in m.missing_sources():
            bad.append(source_text(m, sid))
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
    """One file of the stack: kind 'switch' (convert / take from a Switch file) or 'windows' (copy as is). sha1 = its digest
    when known up front (a listed download file)."""
    __slots__ = ('kind', 'path', 'key', 'mod', 'sha1')

    def __init__(self, kind, path, key, mod, digest=None):
        self.kind, self.path, self.key, self.mod, self.sha1 = kind, path, key, mod, digest


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
                tag = f'{m.id}@{m.version}/{kind}:{d}'
                # files of the mod that are byte-identical to another dump file (Luminescent re-uses game sounds under new
                # ids): the pack names the dump file instead of carrying its bytes
                for rel, dump_rel in (spec.get('dump') or {}).items():
                    src = os.path.join(dump_data, *dump_rel.split('/'))
                    if not os.path.isfile(src):
                        raise ModError(f'{m.name}: needs the dump file {dump_rel}, which is missing')
                    self.index[out_rel(rel)] = Source('switch', src, f'{tag}:dump={dump_rel}', m.id)
                if kind == 'source':
                    root = m.source_paths[d]
                    for rel, (size, digest) in m.source_list(d).items():
                        self.index[out_rel(rel)] = Source('switch', os.path.join(root, *rel.split('/')),
                                                          f'{tag}:{digest}', m.id, digest)
                else:
                    root = os.path.join(m.path, d)
                    for rel, full in _walk(root):
                        if rel.endswith('.manifest') or rel.endswith('.part'):
                            continue
                        st = os.stat(full)
                        key = f'{tag}:{st.st_size}:{st.st_mtime_ns}'
                        if kind == 'romfs':
                            self.index[out_rel(rel)] = Source('switch', full, key, m.id)
                        else:
                            self.index[rel] = Source('windows', full, 'copy:' + key, m.id)
                # a file that is a copy of another one of the stack (a translation's opening = the base mod's)
                for rel, src_rel in (spec.get('copy') or {}).items():
                    s = self.index.get(out_rel(src_rel))
                    if s is None:
                        raise ModError(f'{m.name}: needs {src_rel} from the mods below it, which none of them has')
                    self.index[out_rel(rel)] = Source(s.kind, s.path, f'{tag}:copy={s.key}', m.id, s.sha1)

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
