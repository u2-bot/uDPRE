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
Format 2 adds sub-options: "options": [{"id", "name", "default": choice id, "choices": [{"id", "name"}, ...]}] - each option
is one exclusive choice the player makes under the pack's own tick (e.g. a mod shipped in several variants) - and a layer's
optional "option": {option id: choice id or [choice ids]} (the layer counts only while that choice is picked). The picks live
in the config as {pack id: {option id: choice id}}; an option without a pick uses its default. Format 2 also adds
"min_versions": {pack id: version} - while that pack is on it must be at least this version (e.g. a pack whose file only a
newer Luminescent player reads).
Format 3 adds "widescreen": RULES.json - a pack of screen-shape rules instead of game files (widescreen.py): values of the UI
objects a widescreen mod changes, made at conversion time for the screen shape the pack's "screen" option picks and applied
to whatever the stack holds.
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

FORMAT = 3                  # the newest pack format this uDPRE reads (1 = no sub-options, 2 = no widescreen rules)
FORMATS = (1, 2, 3)
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
        self.options = list(data.get('options', []))
        self.choice = {o['id']: o['default'] for o in self.options}     # the player's picks (set by choose)
        self.min_versions = dict(data.get('min_versions', {}))
        self.widescreen = data.get('widescreen')      # format 3: the rules file of a widescreen pack (widescreen.py)
        self.near_misses = []           # mods-folder downloads that look like a missing source but are not it (discover)

    def option(self, oid):
        return next((o for o in self.options if o['id'] == oid), None)

    def choice_name(self, oid):
        o = self.option(oid)
        return next((c['name'] for c in o['choices'] if c['id'] == self.choice.get(oid)), self.choice.get(oid))

    def set_choice(self, picks):
        """picks {option id: choice id} (unknown options / choices are reported) -> self.choice with defaults filled in."""
        bad = []
        choice = {o['id']: o['default'] for o in self.options}
        for oid, cid in (picks or {}).items():
            o = self.option(oid)
            if o is None:
                bad.append(f'{self.name} has no option "{oid}"')
            elif not any(c['id'] == cid for c in o['choices']):
                bad.append(f'{self.name}: "{cid}" is not a choice of {o["name"]} '
                           f'({", ".join(c["id"] for c in o["choices"])})')
            else:
                choice[oid] = cid
        self.choice = choice
        return bad

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
            if all(w in enabled for w in spec.get('when', [])) and not any(u in enabled for u in spec.get('unless', [])) \
                    and all(self.choice.get(oid) in ([v] if isinstance(v, str) else v)
                            for oid, v in (spec.get('option') or {}).items()):
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
    from . import advice
    where = f'mods\\{os.path.basename(path)}'
    try:
        with open(os.path.join(path, MANIFEST), encoding='utf-8') as f:
            d = json.load(f)
    except ValueError:
        raise ModError(advice.text(f'The mod pack in {where} is damaged ({MANIFEST} cannot be read)',
                                   [advice.redownload_pack('mod', path)]))
    name = d.get('name') or os.path.basename(path)

    def broken(what):
        return ModError(advice.text(f'The {name} pack in {where} is incomplete or damaged: {what}',
                                    [advice.redownload_pack(name, path),
                                     'Extract it with 7-Zip into an empty folder - an extraction that stopped early or '
                                     'Windows\' own zip tool can leave files out']))
    if d.get('format') not in FORMATS:
        newer = isinstance(d.get('format'), int) and d['format'] > max(FORMATS)
        raise ModError(advice.text(
            f'The {name} pack in {where} is made for a ' + ('newer' if newer else 'different') + ' uDPRE (pack format '
            f'{d.get("format")}; this uDPRE {advice.__version__} reads formats {", ".join(map(str, FORMATS))})',
            [advice.newer_udpre() if newer else 'Get the version of the pack made for uDPRE ' + advice.__version__]))
    if not d.get('id'):
        raise broken(f'{MANIFEST} has no id')
    opts = {}
    for o in d.get('options', []):
        ids = [c.get('id') for c in o.get('choices', [])]
        if not o.get('id') or o['id'] in opts or not ids or len(set(ids)) != len(ids) or o.get('default') not in ids:
            raise broken(f'its option "{o.get("id")}" is incomplete')
        opts[o['id']] = set(ids)
    for spec in d.get('layers', []):
        for oid, v in (spec.get('option') or {}).items():
            if oid not in opts or not set([v] if isinstance(v, str) else v) <= opts[oid]:
                raise broken(f'a part of it names the option {oid} = {v}, which it does not describe')
    for sid, s in d.get('sources', {}).items():
        if not os.path.isfile(os.path.join(path, s.get('list', ''))) or not s.get('key'):
            raise broken(f'its list of the {s.get("name", sid)} files is missing')
    for spec in d.get('layers', []):
        kind = next((k for k in KINDS if k in spec), None)
        if kind is None:
            raise broken('a part of it names neither romfs, source nor files')
        if kind == 'source':
            if spec['source'] not in d.get('sources', {}):
                raise broken(f'a part of it takes the download "{spec["source"]}", which it does not describe')
        elif not os.path.isdir(os.path.join(path, spec[kind])):
            raise broken(f'its folder "{spec[kind]}" is missing')
    if d.get('player') and not os.path.isfile(os.path.join(path, d['player'], 'profile.json')):
        raise broken(f'its game player (folder "{d["player"]}") is missing')
    if d.get('widescreen') and not os.path.isfile(os.path.join(path, d['widescreen'])):
        raise broken(f'its screen rules ({d["widescreen"]}) are missing')
    return Mod(path, d)


def _is_game_dump(data, at_least=10000):
    """a romfs/Data folder that holds the whole game: the dump has ~14,000 files under AssetAssistant, a big overhaul mod
    (Luminescent: 3,137, with its own catalog, shaders and globalgamemanagers) far fewer"""
    if not os.path.isfile(os.path.join(data, 'globalgamemanagers')):
        return False
    n = 0
    for _root, _dirs, files in os.walk(os.path.join(data, *AA.split('/'))):
        n += len(files)
        if n >= at_least:
            return True
    return False


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
                    from . import advice
                    other = found[m.id]
                    v_other, v_this = other.version or 'no version', m.version or 'no version'
                    problems.append(advice.text(
                        f'You have the {m.name} pack twice: mods\\{os.path.basename(other.path)} ({v_other}) and '
                        f'mods\\{name} ({v_this}); uDPRE uses the first one',
                        ['Delete the folder of the older version from the mods folder, then press "Look again"']))
                    continue
                found[m.id] = m
            else:
                datas = _romfs_datas(path)
                if datas:
                    raw.append((name, path, datas))
        except ModError as e:
            problems.append(str(e))
        except (OSError, ValueError, KeyError) as e:
            from . import advice
            problems.append(advice.text(f'mods\\{name} cannot be read ({type(e).__name__}: {e})',
                                        ['If it is a mod pack, download it again and replace the folder',
                                         'If it is not a mod, move it out of the mods folder']))
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
    from . import advice
    wanting = [(m, sid) for m in found.values() for sid in m.missing_sources()]
    for name, path, datas in raw:
        if name in claimed:
            continue
        if any(_is_game_dump(d) for d in datas):
            problems.append(advice.text(
                f'mods\\{name} is a copy of the whole game (a dump), not a mod',
                ['Move it out of the mods folder (move it, do not delete it - it is your game)',
                 'Pick it as your dump instead: Browse... at the top of the window']))
            continue
        if _has_exefs(path):
            if wanting:
                # most often: the download a pack needs, but another version / the Shining Pearl one / not extracted right
                for m, sid in wanting:
                    m.near_misses.append(f'mods\\{name}')
                need = '; '.join(f'the {m.name} pack needs exactly {m.sources[sid].get("name", sid)}' for m, sid in wanting)
                problems.append(advice.text(
                    f'mods\\{name} changes the game code (it has an "exefs" folder) and is not a download a pack is waiting '
                    f'for ({need})',
                    ['If it is meant to be that download: it is another version of the mod, the Shining Pearl version, or '
                     'not all of it was extracted - get exactly the version named above for Brilliant Diamond and extract '
                     'it with 7-Zip into a new folder',
                     'If it is another mod: Switch mods that change the game code need a uDPRE pack made for them - move '
                     'it out of the mods folder']))
            else:
                problems.append(advice.text(
                    f'mods\\{name} changes the game code (it has an "exefs" folder); a Switch mod like that only works on '
                    f'PC through a uDPRE mod pack made for it',
                    ['Move it out of the mods folder (it is not used)',
                     'If a uDPRE pack of this mod exists, put that pack into the mods folder instead']))
            continue
        m = Mod(path, {'id': 'raw:' + name, 'name': name + ' (console mod, data only)',
                       'layers': [{'romfs': os.path.relpath(datas[0], path)}]}, raw=True)
        if m.id not in found:
            found[m.id] = m
    return found, problems


def source_text(m, sid):
    from . import advice
    return advice.source_missing(m, sid, ', '.join(m.near_misses) or None)


def version_key(v):
    """'1.2.4' -> (1, 2, 4); non-numeric parts sort as 0 ('2.2F-rev1' -> (2, 2, 0))."""
    out = []
    for part in str(v).replace('-', '.').split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit()) if part[:1].isdigit() else ''
        out.append(int(digits) if digits else 0)
    return tuple(out)


def choose(found, enabled_ids, options=None):
    """Enabled ids (+ options = {pack id: {option id: choice id}}, the picks under each pack's tick) -> the mods in layer
    order (bottom first), each with its choice set. Raises ModError naming every problem."""
    from . import advice
    bad = []
    chosen = []
    on = set(enabled_ids)
    for i in enabled_ids:
        if i not in found:
            bad.append(advice.text(
                f'The mod "{i}" was on last time, but its pack is no longer in the mods folder',
                ['Put the pack back into the mods folder and press "Look again"',
                 'Or leave it out: the next conversion goes on without it (from the console: convert --mods with the '
                 'packs you want)']))
            continue
        chosen.append(found[i])
        for b in found[i].set_choice((options or {}).get(i)):
            bad.append(advice.text(b, ['Pick one of the choices shown under the pack\'s tick, then press Apply']))
    pairs = set()
    for m in chosen:
        for r in m.requires:
            if r not in on:
                if r in found:
                    bad.append(advice.text(f'The {m.name} pack works only on top of {found[r].name}',
                                           [f'Tick {found[r].name} too (it is in your mods folder), then press Apply']))
                else:
                    bad.append(advice.text(f'The {m.name} pack works only on top of the "{r}" pack, which is not in your '
                                           f'mods folder',
                                           [f'Get the "{r}" uDPRE pack, put it into the mods folder, press "Look again" '
                                            f'and tick it', f'Or untick {m.name}']))
        for c in m.conflicts:
            if c in on and frozenset((m.id, c)) not in pairs:
                pairs.add(frozenset((m.id, c)))
                other = found[c].name if c in found else c
                bad.append(advice.text(f'{m.name} and {other} cannot be used together',
                                       [f'Untick one of them, then press Apply']))
        for v_id, least in m.min_versions.items():
            other = found.get(v_id)
            if v_id in on and other is not None and version_key(other.version) < version_key(least):
                bad.append(advice.text(
                    f'The {m.name} pack needs {other.name} {least} or newer, and your {other.name} pack is '
                    f'{other.version or "an old version without a number"}',
                    [advice.update_pack(other, least), 'Press "Look again", then Apply']))
        for sid in m.missing_sources():
            bad.append(source_text(m, sid))
    if bad:
        raise ModError('\n\n'.join(dict.fromkeys(bad)))
    return sorted(chosen, key=lambda m: (m.order, m.id))


def signature(chosen):
    """What a conversion was made with: per mod id, version and the layers it used (they change with the other mods and the
    picks), + the picks of a pack with sub-options."""
    on = {m.id for m in chosen}
    return [[m.id, m.version, [f'{kind}:{d}' for kind, d, _ in m.active_layers(on)]] + ([dict(m.choice)] if m.options else [])
            for m in chosen]


def picks(chosen):
    """{pack id: {option id: choice id}} of the chosen packs that have sub-options (what the config keeps)."""
    return {m.id: dict(m.choice) for m in chosen if m.options}


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


class _Index(dict):
    """The stack's path -> top-most Source map while it is built; history keeps every layer's Source of a path (bottom
    first), for merging (merge.py). Keys are Dpr_Data paths; history keys the romfs paths of Switch files."""

    def __init__(self):
        super().__init__()
        self.history = {}

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        if v.kind == 'switch':
            rel = AUDIO_SW + k[len(AUDIO_WIN):] if k.startswith(AUDIO_WIN) else k
            self.history.setdefault(rel, []).append(v)


class Source:
    """One file of the stack: kind 'switch' (convert / take from a Switch file) or 'windows' (copy as is). sha1 = its digest
    when known up front (a listed download file); raw = it comes from a console mod (no pack manifest)."""
    __slots__ = ('kind', 'path', 'key', 'mod', 'sha1', 'raw')

    def __init__(self, kind, path, key, mod, digest=None, raw=False):
        self.kind, self.path, self.key, self.mod, self.sha1, self.raw = kind, path, key, mod, digest, raw


class Stack:
    """The dump + the chosen mods' active layers. index: Dpr_Data path -> the top-most Source."""

    def __init__(self, dump_data, chosen, bundle_list):
        self.dump = dump_data
        self.chosen = chosen
        self.index = _Index()
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
                        from . import advice
                        raise ModError(advice.text(
                            f'The {m.name} pack uses the game file {dump_rel} of your dump, and your dump does not have '
                            f'it', ['Your dump is incomplete: extract it again into an empty folder (with the v1.3.0 '
                                    'update) and pick that folder']))
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
                            self.index[out_rel(rel)] = Source('switch', full, key, m.id, raw=m.raw)
                        else:
                            self.index[rel] = Source('windows', full, 'copy:' + key, m.id, raw=m.raw)
                # a file that is a copy of another one of the stack (a translation's opening = the base mod's)
                for rel, src_rel in (spec.get('copy') or {}).items():
                    s = self.index.get(out_rel(src_rel))
                    if s is None:
                        from . import advice
                        raise ModError(advice.text(
                            f'The {m.name} pack takes {src_rel} from the pack it builds on, and none of the packs you '
                            f'ticked has it', [f'Tick the pack {m.name} is made for (its description in the Mods box '
                                               f'names it)', f'If it is ticked already, update both packs to their newest '
                                               f'versions']))
                    self.index[out_rel(rel)] = Source(s.kind, s.path, f'{tag}:copy={s.key}', m.id, s.sha1)
        self.all_sources = self.index.history      # romfs path -> every layer's Source, bottom first (merge.py)
        self.index = dict(self.index)

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
            from . import advice
            raise ModError(advice.text(f'Neither your dump nor your mods have the game file {name}',
                                       ['Your dump is incomplete: extract it again into an empty folder and pick that '
                                        'folder']))
        return s.path

    def shaders_bundle(self):
        s = self.index.get(AA + '/Dpr/shaders')
        if s is None:
            from . import advice
            raise ModError(advice.text('Your dump has no StreamingAssets/AssetAssistant/Dpr/shaders',
                                       ['Your dump is incomplete: extract it again into an empty folder and pick that '
                                        'folder']))
        return s


def load_profile(mod):
    """-> (profile dict, player folder) of a mod that brings a player."""
    d = mod.player_dir()
    with open(os.path.join(d, 'profile.json'), encoding='utf-8') as f:
        prof = json.load(f)
    from . import advice
    for rel in list(prof.get('files', [])) + ['udpre/base/globalgamemanagers', 'udpre/shaders.pack']:
        if not os.path.isfile(os.path.join(d, *rel.split('/'))):
            raise ModError(advice.text(f'The {mod.name} pack is incomplete: its game player file {rel} is missing',
                                       [advice.redownload_pack(mod), 'Extract it with 7-Zip into an empty folder (an '
                                        'antivirus may also have removed the file: allow it)']))
    return prof, d
