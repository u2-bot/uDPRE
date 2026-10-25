"""The build: the edit project replayed on the current stack -> the editor's layer, the top-most of the stack.

  udpre/state/editor/romfs/<romfs path>    Switch files that came out different from the stack's (converted like a mod's)
  udpre/state/editor/player/<player path>  the player's global-metadata.dat with the type chart / field default edits
  udpre/state/editor/report.txt            what the last build did, with the operations it had to skip
A file is rewritten only when its bytes change, so a build that changes nothing converts nothing again. The edits are kept
in edits/project.json (the window's editor writes it); config.json "edits_on" says whether the conversion uses them.
"""
import os
import shutil
import time

from .. import mods as modlib
from . import BUILD_VERSION
from .gamefiles import GameFiles, same_file
from .game import Game
from .project import Project, apply

LAYER_ID = 'edits'
LAYER_ORDER = 100000            # above every pack and console mod: the edits see what all of them made
PLAYER_METADATA = 'Dpr_Data/il2cpp_data/Metadata/global-metadata.dat'
SWITCH_METADATA = 'Managed/Metadata/global-metadata.dat'


def project_path(root):
    return os.path.join(root, 'edits', 'project.json')


def out_dir(p):
    return os.path.join(p.state, 'editor')


class Context:
    """What operations need besides the tables: the player's metadata (type chart, field default values)."""

    def __init__(self, metadata_bytes=None, label='player'):
        self._meta_src = metadata_bytes
        self.meta = None
        self.label = label
        self.meta_changed = False
        self.notes = []

    def metadata(self):
        if self.meta is None:
            if self._meta_src is None:
                return None
            from .formats import il2cppmeta
            self.meta = il2cppmeta.Metadata(self._meta_src)
        return self.meta

    def metadata_op(self, op):
        from . import metadata
        m = self.metadata()
        if m is None:
            return f'no {self.label} metadata to edit'
        w = metadata.apply(m, op)
        if w is None:
            self.meta_changed = True
        return w

    def metadata_bytes(self):
        return self.meta.save() if self.meta is not None and self.meta_changed else None


def player_metadata_source(p, setup):
    """-> the path of the chosen player's own global-metadata.dat (never an edited copy)"""
    import json
    from ..install import sha1
    if setup.profile is not None:
        f = os.path.join(setup.player_dir, *PLAYER_METADATA.split('/'))
        return f if os.path.isfile(f) else None
    try:
        with open(p.player_files, encoding='utf-8') as fh:
            want = json.load(fh).get('files', {}).get(PLAYER_METADATA)
    except (OSError, ValueError):
        want = None
    for f in (os.path.join(p.vanilla_player, *PLAYER_METADATA.split('/')), os.path.join(p.root, *PLAYER_METADATA.split('/'))):
        if os.path.isfile(f) and (want is None or sha1(f) == want):
            return f
    return None


def _write_tree(root, files):
    """files {rel: bytes} -> root/rel (unchanged files untouched); other files under root removed. -> changed count"""
    n = 0
    keep = set()
    for rel, data in files.items():
        dst = os.path.join(root, *rel.split('/'))
        keep.add(os.path.normcase(os.path.abspath(dst)))
        if same_file(dst, data):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst + '.part', 'wb') as f:
            f.write(data)
        os.replace(dst + '.part', dst)
        n += 1
    if os.path.isdir(root):
        for d, _, fs in os.walk(root, topdown=False):
            for f in fs:
                full = os.path.join(d, f)
                if os.path.normcase(os.path.abspath(full)) not in keep:
                    os.remove(full)
            if d != root and not os.listdir(d):
                os.rmdir(d)
    return n


class Result:
    def __init__(self):
        self.layer = None           # a mods.Mod for the stack, or None (nothing changed)
        self.overrides = {}         # {player path: edited file}
        self.warnings = []
        self.changed = []
        self.digest = ''


def build(p, stack, setup, log=print, project=None):
    """Replays the project on `stack` (a mods.Stack without the editor's layer). -> Result"""
    t0 = time.time()
    project = project or Project(project_path(p.root))
    r = Result()
    r.digest = project.digest()
    root = out_dir(p)
    if not project.ops:
        clear(p)
        return r
    files = GameFiles(stack)
    game = Game(files)
    from .session import mod_hints
    game.hints = mod_hints(setup.chosen)
    src = player_metadata_source(p, setup)
    ctx = Context(open(src, 'rb').read() if src else None)
    r.warnings = apply(game, project, ctx, log)
    changed = files.changed()
    n = _write_tree(os.path.join(root, 'romfs'), changed)
    meta = ctx.metadata_bytes()
    player = {PLAYER_METADATA: meta} if meta is not None else {}
    _write_tree(os.path.join(root, 'player'), player)
    r.overrides = {rel: os.path.join(root, 'player', *rel.split('/')) for rel in player}
    r.changed = sorted(changed) + sorted(player)
    if changed:
        r.layer = modlib.Mod(root, {'id': LAYER_ID, 'name': 'Your edits (Editor & Randomizer)', 'order': LAYER_ORDER,
                                    'version': f'b{BUILD_VERSION}', 'layers': [{'romfs': 'romfs'}]})
    with open(os.path.join(root, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write(f'edit project: {project.path} ({len(project.ops)} operations, digest {r.digest})\n')
        f.write(f'built {time.strftime("%Y-%m-%d %H:%M:%S")} in {time.time() - t0:.1f} s; {len(r.changed)} files changed '
                f'({n} rewritten)\n')
        for c in r.changed:
            f.write(f'  {c}\n')
        for w in r.warnings:
            f.write(f'SKIPPED {w}\n')
    log(f'edits: {len(project.ops)} operations -> {len(r.changed)} changed files ({n} rewritten) in '
        f'{time.time() - t0:.1f} s' + (f', {len(r.warnings)} skipped (udpre/state/editor/report.txt)' if r.warnings else ''))
    return r


def clear(p):
    root = out_dir(p)
    for sub in ('romfs', 'player'):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
