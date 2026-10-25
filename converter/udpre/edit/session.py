"""The editor's working state for one uDPRE folder: the stack the next conversion would use (dump + the chosen mods, console
mods merged), the edit project, and the game data with the project applied. Editors change the game data through
operations (project.py) and commit them; the window and the console commands share this class."""
import os

from .. import install, merge, mods as modlib
from .build import Context, player_metadata_source, project_path
from .game import Game
from .gamefiles import GameFiles
from .project import Project, apply


class Session:
    def __init__(self, root, mod_ids=None, options=None, lang='english', log=print):
        self.p = install.Paths(root)
        self.log = log
        cfg = install.load_config(self.p)
        if not cfg.get('dump') or not os.path.isdir(cfg['dump']):
            raise install.DumpError('Convert your dump once first (the editor reads the dump of the last conversion).')
        ids = cfg.get('mods', []) if mod_ids is None else list(mod_ids)
        self.setup = install.Setup(self.p, ids, cfg.get('sources'), options if options is not None else cfg.get('options'))
        self.stack = modlib.Stack(cfg['dump'], self.setup.chosen, self.p.bundle_list())
        if any(m.raw for m in self.setup.chosen):
            merge.apply(self.stack, self.p.state, cfg['dump'], cfg.get('merge_choices'), log=lambda _s: None)
        self.lang = lang
        self.project = Project(project_path(self.p.root))
        self.warnings = []
        self.reload()

    def mods_text(self):
        return ', '.join(m.name for m in self.setup.chosen) or 'no mods'

    def hints(self):
        return mod_hints(self.setup.chosen)

    def data_checks(self):
        """warnings about tables that do not line up (a mod that forgot rows): the editors still open"""
        g = self.game
        out = []
        n = len(g.personal)
        for name, rows in (('WazaOboeTable (learnsets)', g.learnsets), ('TamagoWazaTable (egg moves)', g.egg_moves),
                           ('EvolveTable (evolutions)', g.evolutions)):
            if len(rows) < n:
                out.append(f'{name} has {len(rows)} rows for {n} Pokemon rows')
        try:
            anim = g.table('Battle/battle_masterdatas', 'BattleDataTable')['BattleWazaData']
            if len(anim) < len(g.moves):
                out.append(f'the move animation table has {len(anim)} rows for {len(g.moves)} moves')
        except Exception:
            pass
        if len(g.msg.labels('ss_itemname')) < len(g.items):
            out.append(f'ss_itemname has {len(g.msg.labels("ss_itemname"))} names for {len(g.items)} items')
        return out

    def reload(self):
        """game data = the stack's files with every operation of the project applied"""
        self.files = GameFiles(self.stack)
        self.game = Game(self.files, self.lang)
        self.game.hints = self.hints()
        src = player_metadata_source(self.p, self.setup)
        self.context = Context(open(src, 'rb').read() if src else None)
        self.warnings = self.data_checks() + apply(self.game, self.project, self.context, self.log)
        return self.warnings

    def commit(self, ops):
        """set operations already applied to the game data -> kept in the project (saved)"""
        if ops:
            self.project.add_sets(ops)
            self.project.save()
        return len(ops)

    def run(self, op):
        """applies one more operation (randomize, type chart ...) and keeps it; -> its warning or None"""
        from . import project as pj
        tmp = pj.Project(data={'ops': [op]})
        w = pj.apply(self.game, tmp, self.context, self.log)
        self.project.add(op)
        self.project.save()
        return w

    def replace(self, index, op):
        """`op` takes the place of operation `index` (a reroll keeps its place among your edits, so edits made after the
        old one still go on top); -> its warning or None"""
        self.project.ops[index] = op
        self.project.save()
        self.reload()
        mine = [str(w) for w in self.warnings if str(w).startswith(f'operation {index + 1} ')]
        return '; '.join(mine) or None

    def undo(self):
        if self.project.ops:
            self.project.ops.pop()
            self.project.save()
            self.reload()

    def remove(self, indexes):
        keep = set(range(len(self.project.ops))) - set(indexes)
        self.project.ops = [op for i, op in enumerate(self.project.ops) if i in keep]
        self.project.save()
        self.reload()

    def clear(self):
        self.project.ops = []
        self.project.save()
        self.reload()

    def open(self, path):
        self.project = Project(path)
        self.project.path = project_path(self.p.root)
        self.project.save()
        self.reload()

    def save_as(self, path):
        self.project.save(path)
        self.project.path = project_path(self.p.root)

    def enabled(self):
        return bool(install.load_config(self.p).get('edits_on'))

    def set_enabled(self, on):
        cfg = install.load_config(self.p)
        cfg['edits_on'] = bool(on)
        install.save_config(self.p, cfg)


HINT_KEYS = ('ugVersionsUnbounded', 'uint16UgTables', 'uint16EncounterTables', 'evolutionMethodCount')


def mod_hints(chosen):
    """format hints a console mod declares in a small JSON file at its root (any file of an object with HINT_KEYS keys,
    read in name order); later mods win"""
    import json
    out = {}
    for m in chosen:
        try:
            names = sorted(n for n in os.listdir(m.path) if n.lower().endswith('.json'))
        except OSError:
            continue
        for n in names:
            f = os.path.join(m.path, n)
            try:
                if not os.path.isfile(f) or os.path.getsize(f) > 65536:
                    continue
                with open(f, encoding='utf-8') as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(d, dict):
                out.update({k: v for k, v in d.items() if k in HINT_KEYS})
    return out
