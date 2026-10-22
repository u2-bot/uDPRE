"""Assemble a uDPRE mod pack folder from a build-machine spec (format: converter/udpre/mods.py).

  py -3.13 -I release/make_pack.py SPEC.json OUT_DIR --dump SWITCH_DATA [--census SWITCH_CENSUS.jsonl]
                                   [--forbid DIR]...
SPEC.json:
  {"manifest": {"id", "name", "version", "order", "requires", "conflicts", "description"},
   "layers": [{"dir": "romfs", "kind": "romfs" | "files", "when": [...], "unless": [...], "copy": {REL: REL},
               "sources": [{"tree": DIR, "include": [glob...], "exclude": [glob...]} | {"file": PATH, "as": REL}]}
              | {"kind": "source", "source": ID, "name": TEXT, "where": TEXT, "key": REL, "sources": [...as above...]}],
   "player": {"id": "lumi", "build": PLAYER_DIR, "overlays": [MOD_ROMFS_DATA...]}}          (player optional)
A "source" layer is a mod the PLAYER brings (we do not redistribute it): only its file list (romfs path, size, sha1) goes
into the pack (sources/<ID>.json); the converter finds the player's copy by the key file and checks every file.
--forbid DIR: the audit also fails on a pack file with the bytes of any file under DIR (e.g. the mod the player brings).
Layer files are hard links of their sources (a copy when the drive refuses). A romfs-layer file byte-identical to the dump's
file at the same path is left out (the dump brings it); one byte-identical to another dump file is listed in the layer's
"dump" map (the converter copies that dump file) instead of shipped. The player profile = the build's code files (GameAssembly.dll with its
.pdb path cut to the file name, global-metadata.dat, app.info), its script registry renumbered to the Switch ids
(make_player_base.py), its base globalgamemanagers and its shader pack (make_shaderpack.py, with the mod's Switch files as
overlays).
Audit (pack_report.txt; exit 1 on a problem): no pack file has the bytes of any dump file; no player file names a
build-machine folder; every layer folder exists.
"""
import fnmatch
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_release as mr  # noqa: E402

MANIFEST_KEYS = ('id', 'name', 'version', 'order', 'requires', 'conflicts', 'description')


def link(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def matches(rel, globs):
    return any(fnmatch.fnmatchcase(rel, g) for g in globs)


def layer_files(layer):
    """-> {rel: source path} of one layer (later sources win)."""
    out = {}
    for s in layer['sources']:
        if 'file' in s:
            out[s['as']] = s['file']
            continue
        root = s['tree']
        for rel in mr.rel_files(root):
            if s.get('include') and not matches(rel, s['include']):
                continue
            if matches(rel, s.get('exclude', [])):
                continue
            out[rel] = os.path.join(root, *rel.split('/'))
    return out


def same_bytes(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    return mr.sha1(a) == mr.sha1(b)


def run(args):
    print('>', ' '.join(os.path.basename(x) if i == 0 else x for i, x in enumerate(args)), flush=True)
    r = subprocess.run([sys.executable, '-I'] + args)
    if r.returncode:
        sys.exit(f'step failed: {args[0]}')


def make_player(spec, out, dump, census):
    build = spec['build']
    pdir = os.path.join(out, 'player')
    files = []
    for rel in mr.PROFILE_FILES:
        if rel == 'Dpr_Data/globalgamemanagers.assets':
            continue                    # made by make_player_base
        dst = os.path.join(pdir, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(build, *rel.split('/')), dst)
        files.append(rel)
    old = mr.neutral_pdb_path(os.path.join(pdir, 'GameAssembly.dll'))
    print(f'GameAssembly.dll debug path {old!r} -> file name only' if old else 'GameAssembly.dll: no absolute .pdb path')
    run([os.path.join(HERE, 'make_player_base.py'), build, dump, pdir])
    files.append('Dpr_Data/globalgamemanagers.assets')
    cmd = [os.path.join(HERE, 'make_shaderpack.py'), build, dump, os.path.join(pdir, 'udpre', 'shaders.pack')]
    for c in census:
        cmd += ['--census', c]
    for ov in spec.get('overlays', []):
        cmd += ['--overlay', ov]
    run(cmd)
    with open(os.path.join(pdir, 'profile.json'), 'w', encoding='utf-8') as f:
        json.dump({'id': spec['id'], 'files': sorted(files), 'build': os.path.basename(os.path.abspath(build))}, f, indent=1)
    return pdir


class Twins:
    """Files of a folder by size, hashed on demand: twin(path) -> the folder-relative path of a file with the same bytes."""

    def __init__(self, root):
        self.root = root
        self.sizes = {}
        self.hashes = {}
        for rel in mr.rel_files(root):
            self.sizes.setdefault(os.path.getsize(os.path.join(root, *rel.split('/'))), []).append(rel)

    def twin(self, src):
        h = None
        for rel in self.sizes.get(os.path.getsize(src), []):
            if rel not in self.hashes:
                self.hashes[rel] = mr.sha1(os.path.join(self.root, *rel.split('/')))
            h = h or mr.sha1(src)
            if self.hashes[rel] == h:
                return rel
        return None


def source_layer(layer, out):
    """A layer the player brings (a mod we do not redistribute): writes sources/<id>.json = {romfs path: [size, sha1]} of
    the files the pack takes from it. -> (manifest 'sources' entry, layer entry, report line)."""
    sid = layer['source']
    files = layer_files(layer)
    listing = {rel: [os.path.getsize(src), mr.sha1(src)] for rel, src in sorted(files.items())}
    key = layer['key']
    if key not in listing:
        sys.exit(f'source {sid}: key file {key} is not among its files')
    os.makedirs(os.path.join(out, 'sources'), exist_ok=True)
    with open(os.path.join(out, 'sources', f'{sid}.json'), 'w', encoding='utf-8') as f:
        json.dump(listing, f, indent=0)
    desc = {'name': layer['name'], 'where': layer['where'], 'list': f'sources/{sid}.json', 'key': key}
    line = (f'source {sid} ({layer["name"]}): {len(listing)} files the player brings, '
            f'{sum(v[0] for v in listing.values()) / 2**20:.1f} MiB (listed by size + sha1, not shipped)')
    return desc, {'source': sid}, line


def main():
    a = sys.argv[1:]
    flags = {'--dump', '--census', '--forbid'}
    dump = a[a.index('--dump') + 1]
    census = [a[i + 1] for i, x in enumerate(a) if x == '--census']
    forbid = [a[i + 1] for i, x in enumerate(a) if x == '--forbid']
    spec_path, out = [x for i, x in enumerate(a) if x not in flags and (i == 0 or a[i - 1] not in flags)][:2]
    with open(spec_path, encoding='utf-8') as f:
        spec = json.load(f)
    out = os.path.abspath(out)
    if os.path.exists(out) and os.listdir(out):
        sys.exit(f'{out} is not empty - give a new folder')
    os.makedirs(out, exist_ok=True)
    report = []
    manifest = {'format': 1}
    manifest.update({k: spec['manifest'][k] for k in MANIFEST_KEYS if k in spec['manifest']})
    manifest['layers'] = []
    dump_twins = Twins(dump)
    dump_twin = dump_twins.twin
    for layer in spec['layers']:
        if layer['kind'] == 'source':
            desc, entry, line = source_layer(layer, out)
            manifest.setdefault('sources', {})[layer['source']] = desc
            for k in ('when', 'unless'):
                if layer.get(k):
                    entry[k] = layer[k]
            manifest['layers'].append(entry)
            report.append(line)
            continue
        files = layer_files(layer)
        dropped, aliases = [], {}
        n = size = 0
        for rel, src in sorted(files.items()):
            if layer['kind'] == 'romfs':
                d = os.path.join(dump, *rel.split('/'))
                if os.path.isfile(d) and same_bytes(src, d):
                    dropped.append(rel)
                    continue
                twin = dump_twin(src)
                if twin:
                    aliases[rel] = twin
                    continue
            link(src, os.path.join(out, layer['dir'], *rel.split('/')))
            n += 1
            size += os.path.getsize(src)
        os.makedirs(os.path.join(out, layer['dir']), exist_ok=True)
        entry = {layer['kind']: layer['dir']}
        for k in ('when', 'unless'):
            if layer.get(k):
                entry[k] = layer[k]
        if aliases:
            entry['dump'] = aliases
        if layer.get('copy'):
            entry['copy'] = layer['copy']
        manifest['layers'].append(entry)
        report.append(f'layer {layer["dir"]} ({layer["kind"]}{", when " + ",".join(layer["when"]) if layer.get("when") else ""}'
                      f'{", unless " + ",".join(layer["unless"]) if layer.get("unless") else ""}): {n} files, '
                      f'{size / 2**20:.1f} MiB; {len(dropped)} left out as byte-identical to the dump; {len(aliases)} taken '
                      f'from another dump file with the same bytes')
        report += [f'  left out: {r}' for r in dropped[:50]]
    markers_from = [dump, os.path.dirname(HERE)]
    if spec.get('player'):
        pdir = make_player(spec['player'], out, dump, census)
        manifest['player'] = 'player'
        markers_from.append(spec['player']['build'])
    with open(os.path.join(out, 'udpre_mod.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=1)
    # audit: no file with the bytes of a dump file or of a --forbid folder (a mod we do not redistribute); no
    # build-machine folder named in the player files
    problems = []
    markers = mr.local_markers(*markers_from)
    forbidden = [Twins(f) for f in forbid]
    total = 0
    for rel in mr.rel_files(out):
        p = os.path.join(out, *rel.split('/'))
        total += 1
        twin = None if rel.endswith('mscorlib.dll-resources.dat') else dump_twin(p)
        if twin:
            problems.append(f'{rel} has the bytes of dump file {twin}')
        for ft in forbidden:
            t = ft.twin(p)
            if t:
                problems.append(f'{rel} has the bytes of {os.path.join(ft.root, t)}')
        if rel.startswith('player/') and not rel.endswith('.json'):
            with open(p, 'rb') as f:
                low = f.read().lower()
            hit = next((m for m in markers if m.lower() in low), None)
            if hit:
                problems.append(f'{rel} names a build-machine folder')
    report.append(f'audit: {total} files, {len(problems)} problems')
    report += ['  ' + x for x in problems]
    with open(os.path.join(out, 'pack_report.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report[:60]))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
