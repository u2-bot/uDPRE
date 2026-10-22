"""Assemble a uDPRE release folder from a Windows player build of the uDPR project (no game data inside).

  py -3.13 -I release/make_release.py PLAYER_DIR SWITCH_DATA OUT_DIR [--census SWITCH_CENSUS.jsonl] [--exe DIST_DIR]
Steps: copy our player files (every file except the game data below) -> make_player_base (renumbered registry + base
globalgamemanagers) -> make_shaderpack -> udpre/bundles.txt + release.json + player_files.json (the files a mod pack's player
replaces, with their hashes) + an empty mods/ folder with its README -> (optional) the frozen converter from DIST_DIR
(release/build_exe.py output) -> audit.
Left out of the release (the converter makes them from the user's dump): StreamingAssets/AssetAssistant (every bundle and
Dpr.bin), StreamingAssets/Audio, StreamingAssets/Movie, resources.assets(.resS), globalgamemanagers (the base copy lives in
udpre/base/), the Unity "DontShip" backup folder and Wwise's desc.txt.
Audit: no release file has the bytes of any dump file or names a build-machine folder (GameAssembly.dll's .pdb path is cut
to the file name first); every serialized file of the release holds only engine settings, MonoScripts, Unity built-in
resources and our renumbered registry (no Texture2D / Mesh / AudioClip / TextAsset / MonoBehaviour).
SWITCH_DATA is read for IDs, names and the audit only - nothing of it is copied.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'converter'))

EXCLUDE_DIRS = {'Dpr_Data/StreamingAssets/AssetAssistant', 'Dpr_Data/StreamingAssets/Audio', 'Dpr_Data/StreamingAssets/Movie',
                'Dpr_BackUpThisFolder_ButDontShipItWithYourGame'}
EXCLUDE_FILES = {'Dpr_Data/resources.assets', 'Dpr_Data/resources.assets.resS', 'Dpr_Data/globalgamemanagers',
                 'Dpr_Data/globalgamemanagers.assets', 'Dpr_Data/StreamingAssets/desc.txt'}
GAME_TYPES = {'Texture2D', 'Cubemap', 'Mesh', 'AudioClip', 'VideoClip', 'TextAsset', 'MonoBehaviour', 'AnimationClip', 'Sprite',
              'Font', 'GameObject'}
ALLOWED_GAMEOBJECT_FILES = {'Dpr_Data/level0'}      # our boot scene: one empty GameObject "Suspend"
# files whose bytes every Unity 2019.4 IL2CPP player shares (Unity's runtime, not the game's): equal to the dump's copy
UNITY_RUNTIME_FILES = {'Dpr_Data/il2cpp_data/Resources/mscorlib.dll-resources.dat'}
# the player files a mod pack's player profile replaces (its game code, company name = save folder, script registry)
PROFILE_FILES = ['GameAssembly.dll', 'Dpr_Data/il2cpp_data/Metadata/global-metadata.dat', 'Dpr_Data/app.info',
                 'Dpr_Data/globalgamemanagers.assets']


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rel_files(root):
    for d, dirs, fs in os.walk(root):
        for f in fs:
            yield os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/')


def copy_player(player, out):
    n = 0
    for rel in sorted(rel_files(player)):
        if rel in EXCLUDE_FILES or any(rel == x or rel.startswith(x + '/') for x in EXCLUDE_DIRS):
            continue
        d = os.path.join(out, *rel.split('/'))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(os.path.join(player, *rel.split('/')), d)
        n += 1
    return n


def neutral_pdb_path(path):
    """The linker writes the absolute path of the build's .pdb into the PE debug directory (CodeView 'RSDS' record); the
    release keeps only the file name (same length, zero-filled). Windows never reads it. -> the old path or None."""
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    i = data.find(b'RSDS')
    while i != -1:
        start = i + 4 + 16 + 4                      # signature, GUID, age
        end = data.find(b'\0', start)
        old = bytes(data[start:end])
        if old.lower().endswith(b'.pdb') and (b':\\' in old or old.startswith(b'/')):
            name = old.replace(b'/', b'\\').rsplit(b'\\', 1)[-1]
            data[start:end] = name + b'\0' * (len(old) - len(name))
            with open(path, 'wb') as f:
                f.write(data)
            return old.decode('ascii', 'replace')
        i = data.find(b'RSDS', i + 4)
    return None


def pyz_top_modules(exe):
    """Top-level module names inside a PyInstaller executable's PYZ archive."""
    import tempfile
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    car = CArchiveReader(exe)
    out = set()
    for name in car.toc:
        if name.lower().endswith('.pyz') or name.upper().startswith('PYZ'):
            fd, tmp = tempfile.mkstemp(suffix='.pyz')
            os.close(fd)
            try:
                with open(tmp, 'wb') as f:
                    f.write(car.extract(name))
                out |= {m.split('.')[0] for m in ZlibArchiveReader(tmp).toc}
            finally:
                os.remove(tmp)
    return out


def collect_licenses(runtime, dst):
    """License texts of everything the frozen converter bundles -> dst/<distribution>/..., plus Python's LICENSE.txt (its
    Windows build's libraries: OpenSSL, libffi, zlib, bzip2, xz, Tcl/Tk ...) and PyInstaller's COPYING.txt (bootloader).
    Distributions = those owning a top-level module or package found in the runtime folder. -> number of distributions."""
    import importlib.metadata as md
    owners = md.packages_distributions()
    mods = {entry.split('.')[0] for entry in os.listdir(runtime)}
    mods |= pyz_top_modules(os.path.join(os.path.dirname(runtime), 'uDPRE.exe'))   # pure-Python packages live in the PYZ
    names = set()
    for mod in mods:
        for dist in owners.get(mod, []):
            names.add(dist)
    names |= {'pyinstaller'}
    os.makedirs(dst, exist_ok=True)
    index = []
    for name in sorted(names, key=str.lower):
        try:
            meta = md.metadata(name)
            files = [f for f in (md.files(name) or []) if any(k in f.name.upper() for k in ('LICEN', 'COPYING', 'NOTICE'))]
        except md.PackageNotFoundError:
            continue
        lic = (meta.get('License-Expression') or '').strip()
        if not lic:
            lic = '; '.join(c.split('::')[-1].strip() for c in meta.get_all('Classifier') or [] if c.startswith('License'))
        if not lic:
            lic = (meta.get('License') or '').strip().splitlines()[0] if meta.get('License') else 'see files'
        d = os.path.join(dst, meta['Name'])
        for f in files:
            src = f.locate()
            if os.path.isfile(src):
                t = os.path.join(d, str(f).split('.dist-info/', 1)[-1].replace('/', '_'))
                os.makedirs(d, exist_ok=True)
                shutil.copyfile(src, t)
        index.append(f'{meta["Name"]}\t{meta["Version"]}\t{lic}')
    py = os.path.join(sys.base_prefix, 'LICENSE.txt')
    if os.path.isfile(py):
        os.makedirs(os.path.join(dst, 'Python'), exist_ok=True)
        shutil.copyfile(py, os.path.join(dst, 'Python', 'LICENSE.txt'))
        index.append(f'Python\t{sys.version.split()[0]}\tPSF-2.0 (+ the bundled libraries listed in its LICENSE.txt)')
    if os.path.isdir(os.path.join(runtime, 'vpx')):
        # libvpx + the winpthreads runtime it imports (build_exe.py; no package metadata of their own)
        for sub, files in (('libvpx', ('libvpx-LICENSE.txt', 'libvpx-PATENTS.txt')), ('winpthreads', ('winpthreads-COPYING.txt',))):
            os.makedirs(os.path.join(dst, sub), exist_ok=True)
            for f in files:
                shutil.copyfile(os.path.join(HERE, 'licenses', f), os.path.join(dst, sub, f.split('-', 1)[1]))
        index.append('libvpx (udpre_runtime/vpx)\t1.17.0\tBSD-3-Clause + Google patent grant (PATENTS.txt)')
        index.append('winpthreads (udpre_runtime/vpx, mingw-w64)\t-\tMIT')
    with open(os.path.join(dst, 'index.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('package\tversion\tlicense\n' + '\n'.join(index) + '\n')
    return len(index)


def run(args):
    print('>', ' '.join(args), flush=True)
    r = subprocess.run([sys.executable, '-I'] + args)
    if r.returncode:
        sys.exit(f'step failed: {args[0]}')


def local_markers(*paths):
    """Strings that would tie a release file to the build machine: the top folder of each input path (e.g. 'D:\\Work'),
    in the spellings binaries use."""
    out = set()
    for p in paths:
        parts = os.path.abspath(p).split(os.sep)
        if len(parts) > 1 and parts[1]:
            top = parts[0] + '\\' + parts[1]
            out |= {top.encode(), top.replace('\\', '/').encode(), top.encode('utf-16-le')}
    return out


def audit(out, switch_data, markers=()):
    import UnityPy
    problems = []
    dump_hashes = {}
    sizes = {}
    for rel in rel_files(switch_data):
        p = os.path.join(switch_data, *rel.split('/'))
        sizes.setdefault(os.path.getsize(p), []).append(p)
    n = 0
    for rel in rel_files(out):
        p = os.path.join(out, *rel.split('/'))
        n += 1
        if markers and rel != 'udpre/audit.txt':
            with open(p, 'rb') as f:
                blob = f.read()
            low = blob.lower()
            hit = next((m for m in markers if m.lower() in low), None)
            if hit:
                problems.append(f'{rel} names a build-machine folder ({hit.decode("utf-16-le") if b"\0" in hit else hit.decode()})')
        same_size = sizes.get(os.path.getsize(p), [])
        if same_size and rel not in UNITY_RUNTIME_FILES:
            h = sha1(p)
            for q in same_size:
                if q not in dump_hashes:
                    dump_hashes[q] = sha1(q)
                if dump_hashes[q] == h:
                    problems.append(f'{rel} has the bytes of dump file {q}')
        if rel.startswith('Dpr_Data/') and not rel.startswith('Dpr_Data/il2cpp_data') and not rel.startswith('Dpr_Data/Plugins'):
            try:
                env = UnityPy.load(p)
                objs = list(env.objects)
            except Exception:
                objs = []
            for o in objs:
                t = o.type.name
                if t in GAME_TYPES and not (t == 'GameObject' and rel in ALLOWED_GAMEOBJECT_FILES):
                    if rel.startswith('Dpr_Data/Resources/'):
                        continue                    # Unity's own built-in resources (default resources, builtin extra)
                    problems.append(f'{rel}: holds a {t} object')
                    break
    return n, problems


def main():
    a = sys.argv[1:]
    census = a[a.index('--census') + 1] if '--census' in a else None
    exe = a[a.index('--exe') + 1] if '--exe' in a else None
    flags = {'--census', '--exe'}
    pos = [x for i, x in enumerate(a) if x not in flags and (i == 0 or a[i - 1] not in flags)]
    player, switch_data, out = (os.path.abspath(x) for x in pos[:3])
    if os.path.exists(out) and os.listdir(out):
        aside = f'{out}_{time.strftime("%Y%m%d_%H%M%S")}'
        os.rename(out, aside)
        print(f'previous release folder moved aside: {aside}')
    os.makedirs(out)
    n = copy_player(player, out)
    print(f'player files copied: {n}')
    old = neutral_pdb_path(os.path.join(out, 'GameAssembly.dll'))
    print(f'GameAssembly.dll debug path {old!r} -> file name only' if old else 'GameAssembly.dll: no absolute .pdb path')
    run([os.path.join(HERE, 'make_player_base.py'), player, switch_data, out])
    run([os.path.join(HERE, 'make_shaderpack.py'), player, switch_data, os.path.join(out, 'udpre', 'shaders.pack')] +
        (['--census', census] if census else []))
    shutil.copyfile(os.path.join(HERE, 'bundles.txt'), os.path.join(out, 'udpre', 'bundles.txt'))
    from udpre import CONVERT_VERSION, __version__
    info = {'udpre_version': __version__, 'convert_version': CONVERT_VERSION, 'player': os.path.basename(player),
            'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'game': 'Pokemon Brilliant Diamond v1.3.0 (Switch dump, romfs)'}
    if exe:
        for rel in rel_files(exe):
            d = os.path.join(out, *rel.split('/'))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(os.path.join(exe, *rel.split('/')), d)
        info['exe'] = os.path.basename(os.path.abspath(exe))
        n = collect_licenses(os.path.join(exe, 'udpre_runtime'), os.path.join(out, 'udpre', 'licenses'))
        print(f'license texts collected: {n} packages')
    for f in ('LICENSE', 'THIRD-PARTY-NOTICES.md', 'README.md'):
        shutil.copyfile(os.path.join(REPO, f), os.path.join(out, f))
    with open(os.path.join(out, 'udpre', 'release.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=1)
    # the player files a mod pack's profile may replace: the converter keeps ours aside and puts them back by these hashes
    with open(os.path.join(out, 'udpre', 'player_files.json'), 'w', encoding='utf-8') as f:
        json.dump({'files': {rel: sha1(os.path.join(out, *rel.split('/'))) for rel in PROFILE_FILES}}, f, indent=1)
    os.makedirs(os.path.join(out, 'mods'), exist_ok=True)
    shutil.copyfile(os.path.join(HERE, 'mods_README.txt'), os.path.join(out, 'mods', 'README.txt'))
    files, problems = audit(out, switch_data, local_markers(player, switch_data, REPO))
    rep = os.path.join(out, 'udpre', 'audit.txt')
    with open(rep, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'{files} release files; {len(problems)} problems\n' + '\n'.join(problems) + '\n')
    print(f'audit: {files} files, {len(problems)} problems -> {rep}')
    for p in problems[:20]:
        print('  ', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
