"""Build udpre/shaders.pack (our Windows shader objects) from a Windows player build of the uDPR project.

  py -3.13 -I release/make_shaderpack.py PLAYER_DIR SWITCH_DATA OUT.pack [--census SWITCH_CENSUS.jsonl]
PLAYER_DIR = a Windows player (…/Dpr.exe beside Dpr_Data); SWITCH_DATA = the dump's romfs/Data (only to list which containers
hold Shader objects the game loads - nothing of the dump goes into the pack).
Containers: every bundle under AssetAssistant that holds a Shader object on the Switch AND is in the release bundle list
(release/bundles.txt), plus resources.assets. Each entry = the Windows Shader typetree with its references stored by meaning
(see converter/udpre/shaderpack.py).
"""
import os
import pickle
import sys
import zlib

import UnityPy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'converter'))
from udpre import shaderpack  # noqa: E402
from udpre.unityfiles import serialized_files, type_hash, walk_pptrs  # noqa: E402

BUILTIN = ('Resources/unity_builtin_extra', 'Library/unity default resources')
SHADERS_CAB = 'CAB-1dc8d26be8722a766953ce9d8a444e8c'


def shader_containers(switch_aa, bundle_list, census=None):
    if census:
        import json
        listed = set(bundle_list)
        rows = (json.loads(l) for l in open(census, encoding='utf-8'))
        return sorted(r['rel'] for r in rows if r['rel'] in listed and r.get('types', {}).get('Shader'))
    out = []
    for rel in bundle_list:
        p = os.path.join(switch_aa, *rel.split('/'))
        env = UnityPy.load(p)
        if any(o.type.name == 'Shader' for _, sf in serialized_files(env) for o in sf.objects.values()):
            out.append(rel)
    return out


def names_of(sf):
    m = {}
    for o in sf.objects.values():
        if o.type.name == 'Shader':
            m[o.path_id] = ('Shader', shaderpack.shader_name(o))
        else:
            try:
                m[o.path_id] = (o.type.name, o.peek_name())
            except Exception:
                m[o.path_id] = (o.type.name, None)
    return m


def material_users(sf):
    """{shader path id (local): set of material names using it} for one serialized file."""
    out = {}
    for o in sf.objects.values():
        if o.type.name == 'Material':
            t = o.read_typetree()
            p = t['m_Shader']
            if p['m_FileID'] == 0 and p['m_PathID']:
                out.setdefault(p['m_PathID'], set()).add(t['m_Name'])
    return out


def pick_duplicates(sf, switch_path, container):
    """Our build can hold two Shader objects of one name (AssetRipper re-exported TextMesh Pro's copies); the Switch file has
    one. -> {path id to SKIP}: of each duplicate group keep the copy whose material users overlap most with the materials
    that use the Switch shader of that name (identical copies: the first)."""
    groups = {}
    for o in sf.objects.values():
        if o.type.name == 'Shader':
            groups.setdefault(shaderpack.shader_name(o), []).append(o)
    dups = {n: g for n, g in groups.items() if len(g) > 1}
    if not dups:
        return set()
    users = material_users(sf)
    sw_env = UnityPy.load(switch_path)
    sw_sf = serialized_files(sw_env)[0][1]
    sw_users = material_users(sw_sf)
    sw_by_name = {shaderpack.shader_name(o): o.path_id for o in sw_sf.objects.values() if o.type.name == 'Shader'}
    skip = set()
    for n, g in dups.items():
        want = sw_users.get(sw_by_name.get(n), set())
        trees = [pickle.dumps(o.read_typetree()) for o in g]
        if all(t == trees[0] for t in trees):
            best = g[0]
        else:
            best = max(g, key=lambda o: (len(users.get(o.path_id, set()) & want), -g.index(o)))
            if not users.get(best.path_id, set()) & want:
                raise SystemExit(f'{container}: {len(g)} different shaders named {n} and no material tells which one '
                                 f'the Switch file means')
        skip |= {o.path_id for o in g if o is not best}
        print(f'  {container}: {n}: {len(g)} copies, kept path id {best.path_id}')
    return skip


def pack_file(path, container, pc_shader_names, entries, switch_path):
    env = UnityPy.load(path)
    for _, sf in serialized_files(env):
        names = None
        skip = pick_duplicates(sf, switch_path, container)
        for o in sf.objects.values():
            if o.type.name != 'Shader' or o.path_id in skip:
                continue
            tree = o.read_typetree()
            name = tree['m_ParsedForm']['m_Name']
            refs = []

            def sym(p):
                fid, pid = p['m_FileID'], p['m_PathID']
                if pid == 0:
                    return None
                nonlocal names
                if fid == 0:
                    names = names or names_of(sf)
                    t, n = names[pid]
                    if n is None:
                        raise SystemExit(f'{container} {name}: local reference to an unnamed {t}')
                    refs.append({'kind': 'local', 'type': t, 'name': n})
                else:
                    e = sf.externals[fid - 1]
                    if e.path in BUILTIN:
                        g = e.guid.hex() if hasattr(e.guid, 'hex') else str(e.guid)
                        refs.append({'kind': 'builtin', 'ident': {'path': e.path, 'guid': g, 'type': getattr(e, 'type', 0)},
                                     'pid': pid})
                    elif e.path.endswith('/' + SHADERS_CAB):
                        refs.append({'kind': 'shaders', 'name': pc_shader_names[pid]})
                    else:
                        raise SystemExit(f'{container} {name}: reference into {e.path} - not packable')
                return {'m_FileID': -1, 'm_PathID': len(refs) - 1}

            walk_pptrs(tree, sym)
            key = (container, name)
            if key in entries:
                raise SystemExit(f'{container}: two shaders named {name}')
            entries[key] = {'name': name, 'tree': tree, 'refs': refs, 'type_hash': type_hash(o)}


def main():
    player, switch_data, out = sys.argv[1:4]
    pc_aa = os.path.join(player, 'Dpr_Data', 'StreamingAssets', 'AssetAssistant')
    sw_aa = os.path.join(switch_data, 'StreamingAssets', 'AssetAssistant')
    bundles = [l.strip() for l in open(os.path.join(HERE, 'bundles.txt'), encoding='utf-8') if l.strip()]
    census = sys.argv[sys.argv.index('--census') + 1] if '--census' in sys.argv else None
    containers = shader_containers(sw_aa, bundles, census)
    print('containers with Shader objects:', containers)
    env = UnityPy.load(os.path.join(pc_aa, 'Dpr', 'shaders'))
    pc_shader_names = {o.path_id: shaderpack.shader_name(o) for o in env.objects if o.type.name == 'Shader'}
    entries = {}
    for c in containers:
        pack_file(os.path.join(pc_aa, *c.split('/')), c, pc_shader_names, entries, os.path.join(sw_aa, *c.split('/')))
    pack_file(os.path.join(player, 'Dpr_Data', 'resources.assets'), 'resources.assets', pc_shader_names, entries,
              os.path.join(switch_data, 'resources.assets'))
    d = {'version': shaderpack.PACK_VERSION, 'entries': entries,
         'info': {'player': os.path.basename(os.path.abspath(player)), 'containers': containers + ['resources.assets']}}
    with open(out + '.part', 'wb') as f:
        f.write(zlib.compress(pickle.dumps(d, protocol=4), 9))
    os.replace(out + '.part', out)
    by = {}
    for c, _ in entries:
        by[c] = by.get(c, 0) + 1
    print(f'{len(entries)} shaders -> {out} ({os.path.getsize(out)} bytes): {by}')


if __name__ == '__main__':
    main()
