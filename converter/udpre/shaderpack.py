"""Our Windows (Direct3D 11) shader objects, put in place of the Switch ones.

A Switch file holds NVN shader programs no PC GPU runs. Every Shader object the game loads (63 in Dpr/shaders, 11 embedded in
7 other bundles, 9 in resources.assets) gets the data of OUR Windows build of the same shader: compiled by Unity 2019.4.27f1 from
the recovered shader sources of the uDPR project or Unity / TextMesh Pro built-ins. The object keeps its Switch path
ID, so every material and variant collection still points at it.

The pack is made by release/make_release.py from a Windows player build. Entry key = (container, shader name): container =
the bundle path under AssetAssistant ('Dpr/shaders', 'Environments/prefab_map/c10r0101', ...) or 'resources.assets' - Unity
compiles an embedded copy with the variants of ITS bundle's materials, so copies of one shader are not interchangeable.
References inside an entry (m_Dependencies) are stored by meaning, not by ID, and resolved in the target file:
  builtin  - a Unity built-in resource file (same path ID on every platform);
  shaders  - a shader of the `shaders` bundle, by name (its Switch path ID comes from the dump being converted);
  local    - an object of the same file, by type + name.
"""
import copy
import hashlib
import pickle
import zlib

from .unityfiles import ConvertError, add_external, external_index, type_hash, walk_pptrs

SHADERS_IDENT = {'path': 'archive:/CAB-1dc8d26be8722a766953ce9d8a444e8c/CAB-1dc8d26be8722a766953ce9d8a444e8c',
                 'guid': '00' * 16, 'type': 0}
PACK_VERSION = 1


class ShaderPack:
    def __init__(self, path):
        with open(path, 'rb') as f:
            raw = f.read()
        d = pickle.loads(zlib.decompress(raw) if raw[:1] == b'x' else raw)
        if d.get('version') != PACK_VERSION:
            raise ConvertError(f'shader pack {path}: version {d.get("version")}, this converter reads {PACK_VERSION}')
        self.entries = d['entries']           # {(container, name): entry}
        self.info = d.get('info', {})
        self._by_name = None

    def get(self, container, name):
        e = self.entries.get((container, name))
        if e is None:
            raise ConvertError(f'no Windows build of shader "{name}" for {container} in the shader pack')
        return e

    def find(self, container, name):
        """-> (entry, exact). A bundle the pack was not made for (a mod's) that embeds a copy of a game shader gets the build
        of that shader in Dpr/shaders, else in resources.assets, else in the first container holding it: the shaders bundle
        is built with every variant the game's materials use."""
        e = self.entries.get((container, name))
        if e is not None:
            return e, True
        if self._by_name is None:
            self._by_name = {}
            for (c, n) in sorted(self.entries, key=lambda k: (k[0] != 'Dpr/shaders', k[0] != 'resources.assets', k[0])):
                self._by_name.setdefault(n, self.entries[(c, n)])
        e = self._by_name.get(name)
        if e is None:
            raise ConvertError(f'no Windows build of shader "{name}" for {container} in the shader pack')
        return e, False

    def container_digests(self):
        """{container: digest of every shader the pack holds for it} - a container whose digest changes between two
        releases must be converted again (its Shader objects carry the pack's data)."""
        per = {}
        for (container, name), e in sorted(self.entries.items()):
            per.setdefault(container, hashlib.sha1()).update(name.encode() + b'\0' + entry_digest(e).encode())
        return {c: h.hexdigest() for c, h in per.items()}


def entry_digest(e):
    if 'digest' not in e:
        e['digest'] = hashlib.sha1(pickle.dumps((e['tree'], e['refs'], e.get('type_hash')), protocol=4)).hexdigest()
    return e['digest']


def shader_name(obj):
    return obj.read_typetree()['m_ParsedForm']['m_Name']


def local_names(sf, cache):
    """{(type, name): path_id} for the objects of sf a 'local' reference may name (Shader by parsed name, others by m_Name)."""
    key = id(sf)
    if key not in cache:
        m = {}
        for o in sf.objects.values():
            t = o.type.name
            if t == 'Shader':
                n = shader_name(o)
            else:
                try:
                    n = o.peek_name()
                except Exception:
                    continue
            if n is not None:
                m.setdefault((t, n), o.path_id)
        cache[key] = m
    return cache[key]


def apply(obj, sf, entry, switch_shader_ids, cache):
    """Writes entry's Windows shader into obj (a Shader object of sf), references resolved for sf."""
    want = type_hash(obj)
    if entry.get('type_hash') and want and entry['type_hash'] != want:
        raise ConvertError(f'shader {entry["name"]}: Shader type hash {want} in the file, {entry["type_hash"]} in the pack')
    tree = copy.deepcopy(entry['tree'])
    refs = entry['refs']

    def resolve(p):
        if p['m_FileID'] != -1:
            return None
        r = refs[p['m_PathID']]
        k = r['kind']
        if k == 'builtin':
            fid = external_index(sf, r['ident']['path']) or add_external(sf, r['ident'])
            return {'m_FileID': fid, 'm_PathID': r['pid']}
        if k == 'local' and r['type'] == 'Shader' and local_names(sf, cache).get(('Shader', r['name'])) is None \
                and r['name'] in switch_shader_ids:
            k = 'shaders'           # a Dpr/shaders entry used by name in another bundle: its sibling lives in Dpr/shaders
        if k == 'shaders':
            if r['name'] not in switch_shader_ids:
                raise ConvertError(f'shader {entry["name"]}: dependency "{r["name"]}" is not in the dump\'s shaders bundle')
            if sf.name and sf.name.endswith(SHADERS_IDENT['path'].rsplit('/', 1)[-1]):
                return {'m_FileID': 0, 'm_PathID': switch_shader_ids[r['name']]}
            fid = external_index(sf, SHADERS_IDENT['path'].rsplit('/', 1)[-1]) or add_external(sf, SHADERS_IDENT)
            return {'m_FileID': fid, 'm_PathID': switch_shader_ids[r['name']]}
        if k == 'local':
            pid = local_names(sf, cache).get((r['type'], r['name']))
            if pid is None:
                raise ConvertError(f'shader {entry["name"]}: local dependency {r["type"]} "{r["name"]}" not in {sf.name}')
            return {'m_FileID': 0, 'm_PathID': pid}
        raise ConvertError(f'shader {entry["name"]}: unknown reference kind {k}')

    walk_pptrs(tree, resolve)
    obj.save_typetree(tree)
