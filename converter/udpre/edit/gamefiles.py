"""The Switch game files as the stack holds them, opened for editing.

Paths are romfs/Data-relative ('StreamingAssets/AssetAssistant/Pml/personal_masterdatas'); bundle() takes the part under
AssetAssistant. A bundle is read with UnityPy; MonoBehaviours are read by m_Name into type trees on first use and written
back when the build saves. A file counts as changed only when its bytes come out different from the source's, so an
operation that sets a value back to what the stack has leaves no file behind. Other files (Dpr.bin, sound banks) are edited
as bytes through raw() / set_raw().
"""
import os

import UnityPy

from .. import mods as modlib
from .. import unityfiles  # noqa: F401  (lenient AssetBundle header for Luminescent's bundles)

AA = modlib.AA


class EditError(ValueError):
    pass


class EditBundle:
    def __init__(self, rel, path):
        self.rel = rel
        self.path = path
        self.env = UnityPy.load(path)
        self._objs = {}             # m_Name -> ObjectReader (MonoBehaviours, first of a name)
        self._by_class = {}         # script class name -> [m_Name]
        self._trees = {}            # m_Name -> type tree (read on use)
        self._raw = {}              # m_Name -> bytes as read
        for o in self.env.objects:
            if o.type.name != 'MonoBehaviour':
                continue
            try:
                name = o.peek_name()
            except Exception:       # a MonoBehaviour without a readable name is never edited
                continue
            self._objs.setdefault(name, o)

    def names(self):
        return list(self._objs)

    def has(self, name):
        return name in self._objs

    def mono(self, name):
        """-> the type tree of the MonoBehaviour named `name` (the same dict on every call; edit it in place)."""
        if name not in self._trees:
            o = self._objs.get(name)
            if o is None:
                raise EditError(f'{self.rel} has no object named {name}')
            self._raw[name] = o.get_raw_data()
            self._trees[name] = o.read_typetree()
        return self._trees[name]

    def script_class(self, name):
        o = self._objs[name]
        try:
            s = o.read().m_Script.read()
            return f'{s.m_Namespace}.{s.m_ClassName}'.lstrip('.')
        except Exception:
            return ''

    def by_class(self, cls):
        """-> [m_Name] of the MonoBehaviours whose script class is `cls` (with or without namespace)."""
        if cls not in self._by_class:
            self._by_class[cls] = [n for n in self._objs
                                   if self.script_class(n) in (cls,) or self.script_class(n).endswith('.' + cls)]
        return self._by_class[cls]

    def changed_objects(self):
        """-> [m_Name] whose tree now writes other bytes than were read."""
        out = []
        for name, tree in self._trees.items():
            o = self._objs[name]
            if o.save_typetree(tree) != self._raw[name]:
                out.append(name)
            o.set_raw_data(self._raw[name])     # save_typetree stored the new bytes; keep the file as read until save()
        return out

    def save(self):
        """-> the bundle's bytes with every changed tree written (None when nothing changed)."""
        changed = self.changed_objects()
        if not changed:
            return None
        for name in changed:
            self._objs[name].save_typetree(self._trees[name])
        data = self.env.file.save(packer='lz4')
        for name in changed:                     # the trees stay editable; a later save() writes them again
            self._objs[name].set_raw_data(self._raw[name])
        return data


class GameFiles:
    """stack: a mods.Stack (without the editor's own layer). Reads come from the top-most source of each path."""

    def __init__(self, stack):
        self.stack = stack
        self._bundles = {}
        self._raw = {}              # romfs rel -> new bytes (non-bundle files)
        self._new = {}              # romfs rel -> bytes of files the stack does not have

    def source(self, rel):
        s = self.stack.index.get(modlib.out_rel(rel))
        if s is None:
            raise EditError(f'the game files have no {rel}')
        return s

    def exists(self, rel):
        return modlib.out_rel(rel) in self.stack.index

    def path(self, rel):
        return self.source(rel).path

    def bundle(self, aa_rel):
        if aa_rel not in self._bundles:
            s = self.source(AA + '/' + aa_rel)
            if s.kind != 'switch':
                raise EditError(f'{aa_rel} comes from a pack as a Windows file - it cannot be edited')
            self._bundles[aa_rel] = EditBundle(aa_rel, s.path)
        return self._bundles[aa_rel]

    def opened(self):
        return dict(self._bundles)

    def read(self, rel):
        """-> the current bytes of a non-bundle file (an edited copy if set_raw was called)."""
        if rel in self._raw:
            return self._raw[rel]
        if rel in self._new:
            return self._new[rel]
        with open(self.path(rel), 'rb') as f:
            return f.read()

    def set_raw(self, rel, data):
        self._raw[rel] = data

    def add_new(self, rel, data):
        """a file the stack does not have (a bundle copy of the Pokemon Inserter)"""
        if self.exists(rel):
            raise EditError(f'{rel} exists already')
        self._new[rel] = data

    def has_new(self, rel):
        return rel in self._new

    def put(self, rel, data):
        """a non-bundle file's new bytes: an edited copy of a stack file, else a new file"""
        if self.exists(rel):
            self._raw[rel] = data
        else:
            self._new[rel] = data

    def changed(self):
        """-> {romfs rel: new bytes} of every file that differs from its source, and the new files."""
        out = dict(self._new)
        for aa_rel, b in self._bundles.items():
            data = b.save()
            if data is not None:
                out[AA + '/' + aa_rel] = data
        for rel, data in self._raw.items():
            with open(self.path(rel), 'rb') as f:
                if f.read() != data:
                    out[rel] = data
        return out


def same_file(path, data):
    return os.path.isfile(path) and os.path.getsize(path) == len(data) and open(path, 'rb').read() == data
