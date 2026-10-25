"""Merging console mods with the layers below them, object by object and field by field.

A pack's own variants (when / unless layers) already make the files of a pack combination; console mods (a folder with
romfs/Data, no pack manifest) come with no such variants. When a console mod brings a file another mod also brings, the
file is merged instead of replaced:
  base   = the dump's file (what both sides changed from; none when the file is new);
  below  = what the packs (or the console mods under it) made of the file;
  above  = the console mod's file.
For a Unity file (a bundle, resources.assets, globalgamemanagers) every object (by path id) that only one side changed is
taken from that side; an object both changed is merged field by field through its type tree; a field both changed to
different values is a conflict - the upper side wins unless the player picked the lower one (config "merge_choices").
When one side added or removed objects, its file gives the structure (its AssetBundle object, its object set) and the other
side's changed objects are merged into it; when both did, the file cannot be merged and the upper side wins whole.
Textures taken from the other side's file carry their pixels inline (Unity reads inline texture data the same way).
Dpr.bin (the bundle catalog) is merged per bundle record; any other file is taken whole from the upper side.
Results go to udpre/state/merged/<romfs path>, remade only when one of their inputs changed.
"""
import hashlib
import json
import os

import UnityPy
from UnityPy.files.SerializedFile import SerializedFile

from . import unityfiles  # noqa: F401  (lenient AssetBundle header)

MERGE_VERSION = 2           # bump when the merge rules change what a merge writes
UNITY_TOP = ('resources.assets', 'globalgamemanagers', 'globalgamemanagers.assets')
WHOLE_FILE = 'whole file'   # the conflict row (and merge_choices key) of a file one side wins whole


def whole_pick(choices):
    """the player's pick for a file decided whole ('*' = the older spelling of the key)"""
    return choices.get(WHOLE_FILE) or choices.get('*')
# objects decided whole (never field by field): their data only makes sense together
WHOLE_TYPES = ('Texture2D', 'Cubemap', 'Mesh', 'AudioClip', 'Font', 'Shader', 'VideoClip', 'Texture2DArray')


class MergeError(Exception):
    pass


def is_unity(rel):
    return rel.startswith('StreamingAssets/AssetAssistant/') and not rel.endswith('Dpr.bin') or rel in UNITY_TOP


# --- type tree three-way merge ----------------------------------------------------------------------------------------
class Conflicts:
    def __init__(self):
        self.items = []         # (object label, field path, below value, above value, winner)

    def add(self, obj, path, below, above, winner):
        self.items.append((obj, '.'.join(map(str, path)), _short(below), _short(above), winner))


def _short(v):
    s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, (bytes, bytearray)) else f'<{len(v)} bytes>'
    return s if len(s) <= 80 else s[:77] + '...'


def merge3(base, below, above, path, conflicts, obj_label, prefer_below=False):
    """-> merged value. Lists of the same length merge element by element; a list one side only grew (the other kept
    the base's elements) takes the grown side's new elements; any other list change is one value."""
    if below == above:
        return below
    if below == base:
        return above
    if above == base:
        return below
    if isinstance(base, dict) and isinstance(below, dict) and isinstance(above, dict) \
            and base.keys() == below.keys() == above.keys():
        return {k: merge3(base[k], below[k], above[k], path + [k], conflicts, obj_label, prefer_below) for k in base}
    if isinstance(base, list) and isinstance(below, list) and isinstance(above, list):
        n = len(base)
        if len(below) == n and len(above) == n:
            return [merge3(base[i], below[i], above[i], path + [i], conflicts, obj_label, prefer_below) for i in range(n)]
        if len(below) >= n and len(above) >= n:
            head = [merge3(base[i], below[i], above[i], path + [i], conflicts, obj_label, prefer_below) for i in range(n)]
            tail_b, tail_a = below[n:], above[n:]
            if not tail_b or not tail_a or tail_b == tail_a:
                return head + (tail_a or tail_b)
    winner = 'below' if prefer_below else 'above'
    conflicts.add(obj_label, path, below, above, winner)
    return below if prefer_below else above


# --- Unity files ------------------------------------------------------------------------------------------------------
class UFile:
    """A loaded Unity file: its serialized files' objects by (entry, path id)."""

    def __init__(self, path):
        self.path = path
        self.env = UnityPy.load(path)
        self.sfs = unityfiles.serialized_files(self.env)
        self.objs = {}
        self.typed = set()          # keys of objects whose file carries type trees (player files do not: whole objects)
        for name, sf in self.sfs:
            typed = bool(getattr(sf, '_enable_type_tree', True))
            for pid, o in sf.objects.items():
                self.objs[(name, pid)] = o
                if typed:
                    self.typed.add((name, pid))
        self.raw_entries = {} if isinstance(self.env.file, SerializedFile) else \
            {n: f for n, f in self.env.file.files.items() if not isinstance(f, SerializedFile)}

    def raw(self, key):
        return self.objs[key].get_raw_data()

    def stream_bytes(self, sd, own_dir=None):
        """bytes of an m_StreamData range: a .resS entry of this bundle, or a loose .resS next to the file"""
        if not sd or not sd.get('size'):
            return b''
        name = sd['path'].rsplit('/', 1)[-1]
        if name in self.raw_entries:
            data = self.raw_entries[name].bytes
        else:
            loose = os.path.join(os.path.dirname(self.path), name)
            with open(loose, 'rb') as f:
                data = f.read()
        return bytes(data[sd['offset']:sd['offset'] + sd['size']])


def _label(o):
    try:
        n = o.peek_name()
    except Exception:
        n = ''
    return f'{o.type.name} {n or o.path_id}'.strip()


def _tree(o, f=None, key=None):
    """the object's type tree, or None when it has none (a file without type trees: UnityPy would read only the base
    fields of a MonoBehaviour and writing that back would cut the object)"""
    if f is not None and key not in f.typed:
        return None
    try:
        return o.read_typetree()
    except Exception:
        return None


def _inline_streams(tree, src):
    """a texture tree read from file `src` -> its pixels inline (no stream reference into src's .resS)"""
    sd = tree.get('m_StreamData')
    if isinstance(sd, dict) and sd.get('size') and 'image data' in tree:
        tree['image data'] = src.stream_bytes(sd)
        tree['m_StreamData'] = dict(sd, offset=0, size=0, path='')
        return True
    return not (isinstance(sd, dict) and sd.get('size'))


def merge_unity(base_path, below_path, above_path, choices, conflicts, notes):
    """-> (bytes of the merged file = the structure owner's file with the other side's object changes in it, the owner's
    path - a loose serialized file keeps streaming from the owner's .resS)"""
    B = UFile(base_path) if base_path else None
    L = UFile(below_path)
    A = UFile(above_path)
    base_keys = set(B.objs) if B else set()
    l_struct = set(L.objs) != base_keys
    a_struct = set(A.objs) != base_keys
    if B is None or (l_struct and a_struct):
        below_wins = whole_pick(choices) == 'below'
        conflicts.add(WHOLE_FILE, [], '<lower file>', '<upper file>', 'below' if below_wins else 'above')
        if below_wins:
            notes.append('both sides add or remove objects: the lower layer\'s file is used whole (your pick)')
            return open(below_path, 'rb').read(), below_path
        notes.append('both sides add or remove objects: the upper layer\'s file is used whole')
        return open(above_path, 'rb').read(), above_path
    owner, other = (A, L) if a_struct or not l_struct else (L, A)
    owner_is_above = owner is A
    n_taken = n_merged = 0

    def take_other(o_own, o_other):
        """o_own gets o_other's content; -> False when its streamed data cannot come along"""
        t = _tree(o_other, other, key_now[0])
        if t is None:
            if o_other.type.name in WHOLE_TYPES:
                return False
            o_own.set_raw_data(o_other.get_raw_data())
            return True
        if not _inline_streams(t, other):
            return False
        o_own.save_typetree(t)
        return True

    key_now = [None]
    for key, o_other in other.objs.items():
        key_now[0] = key
        if key not in owner.objs or key not in B.objs:
            continue
        raw_b, raw_other, o_own = B.raw(key), o_other.get_raw_data(), owner.objs[key]
        raw_own = o_own.get_raw_data()
        if raw_other == raw_b or raw_other == raw_own:
            continue                                     # the other side left it alone (or made the same change)
        lab = _label(o_own)
        if raw_own == raw_b:                             # only the other side changed it: take its object
            if take_other(o_own, o_other):
                n_taken += 1
            else:
                notes.append(f'{lab}: its streamed data cannot move between files - kept from the structure owner')
            continue
        pick = choices.get(lab) or choices.get(str(key[1]))
        win_above = pick != 'below'
        tb, t_other, t_own = _tree(B.objs[key], B, key), _tree(o_other, other, key), _tree(o_own, owner, key)
        if o_own.type.name in WHOLE_TYPES or tb is None or t_other is None or t_own is None:
            # pixels, meshes, sounds, fonts: one side's object whole
            conflicts.add(lab, [], '<whole object>', '<whole object>', 'above' if win_above else 'below')
            if win_above != owner_is_above and not take_other(o_own, o_other):
                notes.append(f'{lab}: its streamed data cannot move between files - kept from the structure owner')
            continue
        below_t, above_t = (t_other, t_own) if owner_is_above else (t_own, t_other)
        merged = merge3(tb, below_t, above_t, [], conflicts, lab, prefer_below=pick == 'below')
        o_own.save_typetree(merged)
        n_merged += 1
    notes.append(f'{n_taken} objects taken from the {"lower" if owner_is_above else "upper"} layer, {n_merged} merged '
                 f'field by field, structure from the {"upper" if owner_is_above else "lower"} layer')
    if isinstance(owner.env.file, SerializedFile):
        return owner.env.file.save(), owner.path
    return owner.env.file.save(packer='lz4'), owner.path


def _loads(path):
    try:
        env = UnityPy.load(path)
        for o in env.objects:
            o.get_raw_data()
        return bool(unityfiles.serialized_files(env))
    except Exception:
        return False


# --- the catalog ------------------------------------------------------------------------------------------------------
RECORD_FIELDS = ('projectName', 'hash', 'lastWriteTime', 'isStreamingSceneAssetBundle', 'allDependencies', 'assetPaths',
                 'size')


def merge_catalog(base_path, below_path, above_path, conflicts, notes, choices=None):
    """Dpr.bin: per bundle record (by name) - a record only the upper side changed or added is taken; one both changed is
    a conflict (upper wins unless merge_choices picks 'below' for 'record <name>'). The result must still pass the game's
    boot lookup (no duplicate names / asset keys)."""
    from .edit.formats import nrbf
    B = nrbf.load(open(base_path, 'rb').read()) if base_path else None
    L = nrbf.load(open(below_path, 'rb').read())
    A = nrbf.load(open(above_path, 'rb').read())
    base = {r.assetBundleName: r.as_dict() for r in B.records} if B else {}
    lower = {r.assetBundleName: r for r in L.records}
    taken = added = clash = 0
    for ra in A.records:
        name = ra.assetBundleName
        da = ra.as_dict()
        if base.get(name) == da:
            continue                                    # the upper side left this record alone
        rl = lower.get(name)
        if rl is None:
            if L.records:
                rec = L.clone(L.records[0], name)
            else:
                raise MergeError('the lower catalog has no record to copy a layout from')
            for f in RECORD_FIELDS:
                setattr(rec, f, da[f])
            added += 1
            continue
        dl = rl.as_dict()
        if dl == da:
            continue
        if dl != base.get(name):
            keep_lower = (choices or {}).get(f'record {name}') == 'below'
            conflicts.add(f'record {name}', [], '<lower record>', '<upper record>', 'below' if keep_lower else 'above')
            clash += 1
            if keep_lower:
                continue
        for f in RECORD_FIELDS:
            if dl[f] != da[f]:
                setattr(rl, f, da[f])
        taken += 1
    bad = L.problems()
    if bad:
        raise MergeError(f'the merged catalog would not boot: {bad[:3]}')
    notes.append(f'catalog: {taken} records taken from the upper layer ({clash} both changed), {added} added')
    return L.save()


# --- references -------------------------------------------------------------------------------------------------------
BUILTIN = ('Library/unity default resources', 'Resources/unity_builtin_extra')


def _cab(path):
    return path.rsplit('/', 1)[-1].lower()


def _file_info(path):
    """-> (path, ({cab: path ids}, {(target cab, path id)}, [dependency bundle names])) of one Unity file"""
    from .unityfiles import walk_pptrs
    tables, refs, deps = {}, set(), []
    try:
        env = UnityPy.load(path)
        for name, sf in unityfiles.serialized_files(env):
            me = _cab(name)
            tables[me] = set(sf.objects)
            ext = [e.path for e in sf.externals]
            typed = bool(getattr(sf, '_enable_type_tree', True))
            for o in sf.objects.values():
                if not typed:
                    break
                try:
                    tree = o.read_typetree()
                except Exception:
                    continue
                if o.type.name == 'AssetBundle':
                    deps = list(tree.get('m_Dependencies') or [])

                def take(p, me=me, ext=ext):
                    fid, pid = p['m_FileID'], p['m_PathID']
                    if pid and 0 <= fid <= len(ext):
                        tgt = me if fid == 0 else (None if ext[fid - 1] in BUILTIN else _cab(ext[fid - 1]))
                        if tgt:
                            refs.add((tgt, pid))
                walk_pptrs(tree, take)
    except Exception:
        pass
    return path, (tables, refs, deps)


class RefIndex:
    """per Unity file: its CAB names -> object path ids, the bundles it depends on (AssetBundle m_Dependencies) and every
    reference it makes into another CAB (from the type trees). Cached by path; prefetch() reads many in parallel."""

    def __init__(self):
        self.cache = {}

    def prefetch(self, paths, workers=None):
        todo = sorted({p for p in paths if p and p not in self.cache})
        if len(todo) < 32:
            return
        import concurrent.futures as cf
        from .install import default_workers
        with cf.ProcessPoolExecutor(max_workers=workers or default_workers()) as ex:
            for path, info in ex.map(_file_info, todo, chunksize=16):
                self.cache[path] = info

    def info(self, path):
        if path not in self.cache:
            self.cache[path] = _file_info(path)[1]
        return self.cache[path]

    def dangling(self, path, resolve, owners=None):
        """references of the file at `path` that point at no object; resolve(bundle name) -> the path of that dependency in
        the stack looked at (or None). CABs no dependency provides are not judged. owners: filled with {cab: dependency
        bundle name} (which dependency should have had the object)."""
        tables, refs, deps = self.info(path)
        known = dict(tables)
        todo, seen = list(deps), set()
        while todo and len(seen) < 64:
            d = todo.pop()
            if d in seen:
                continue
            seen.add(d)
            p = resolve(d)
            if p is None:
                continue
            t2, _, d2 = self.info(p)
            for cab, pids in t2.items():
                if cab not in known:
                    known[cab] = pids
                    if owners is not None:
                        owners[cab] = d
            todo += d2
        return {(cab, pid) for cab, pid in refs if cab in known and pid not in known[cab]}


def _bundle_resolver(index, overrides=None):
    """bundle name (as m_Dependencies has it) -> its file in the stack (Pokemon Database / UIs ... are project folders)"""
    from .mods import AA
    by_name = {}
    for k, s in index.items():
        if k.startswith(AA + '/'):
            rest = k[len(AA) + 1:]
            by_name.setdefault(rest.split('/', 1)[1] if '/' in rest else rest, k)
            by_name.setdefault(rest, k)

    def resolve(name):
        k = by_name.get(name)
        if k is None:
            return None
        if overrides and k in overrides:
            return overrides[k]
        return index[k].path
    return resolve


# --- the stack --------------------------------------------------------------------------------------------------------
def _digest(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def apply(stack, state_dir, dump_data, choices_all, log=print):
    """Replaces, in stack.index, every file a console mod brings on top of another mod's with the merged file.
    -> {romfs path: {'mods': [...], 'conflicts': [...], 'notes': [...]}} (also written to state_dir/merged/report.json)"""
    from .mods import Source, out_rel
    out_root = os.path.join(state_dir, 'merged')
    report_path = os.path.join(out_root, 'report.json')
    try:
        with open(report_path, encoding='utf-8') as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    report = {}
    keep = set()
    lower = {}                  # romfs path -> the Source the packs (or the dump) give it: what a merge falls back to
    for rel, srcs in stack.all_sources.items():
        mods_ = [s for s in srcs if s.mod is not None]
        raw = [s for s in mods_ if s.raw]
        if not raw or len(mods_) < 2:
            continue
        base = srcs[0] if srcs[0].mod is None else None
        below = [s for s in mods_ if not s.raw]
        cur = below[-1] if below else base
        chain = raw if cur is not None else raw[1:]
        if cur is None:
            cur = raw[0]
        lower[rel] = cur
        choices = (choices_all or {}).get(rel, {})
        key = _digest(MERGE_VERSION, rel, [s.key for s in srcs], choices)
        out = os.path.join(out_root, *rel.split('/'))
        entry = old.get(rel)
        if entry and entry.get('key') == key and os.path.isfile(out):
            report[rel] = entry
        else:
            conflicts, notes = Conflicts(), []
            path = cur.path
            data = None
            owner = cur.path
            lower_is_mod = cur is not base          # a whole-file pick is between two mods' files, never the dump's
            for s in chain:
                c = Conflicts()
                try:
                    if rel.endswith('Dpr.bin'):
                        data = merge_catalog(base.path if base else None, path, s.path, c, notes, choices)
                    elif is_unity(rel):
                        data, own = merge_unity(base.path if base else None, path, s.path, choices, c, notes)
                        owner = s.path if own == s.path else owner
                    elif not lower_is_mod:
                        data = open(s.path, 'rb').read()        # the first mod over the dump: its file, no conflict
                    else:
                        below_wins = whole_pick(choices) == 'below'
                        data = open(path if below_wins else s.path, 'rb').read()
                        c.add(WHOLE_FILE, [], '<lower file>', '<upper file>', 'below' if below_wins else 'above')
                    lower_is_mod = True
                except Exception as e:
                    if is_unity(rel) and not _loads(s.path):
                        # the console mod's own file is damaged (it does not load on its own): the layer below stays
                        notes.append(f'the console mod\'s file cannot be read ({type(e).__name__}: {e}); the file of the '
                                     f'layer below is used')
                        data = open(path, 'rb').read()
                    else:
                        notes.append(f'not merged ({type(e).__name__}: {e}); the upper layer\'s file is used')
                        data = open(s.path, 'rb').read()
                conflicts.items += c.items
                if data is not None:
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out + '.part', 'wb') as f:
                        f.write(data)
                    os.replace(out + '.part', out)
                    path = out
            report[rel] = {'key': key, 'mods': [s.mod for s in mods_], 'conflicts': conflicts.items, 'notes': notes,
                           'owner': owner}
            log(f'merged {rel}: {len(mods_)} mods, {len(conflicts.items)} conflicts')
        if os.path.isfile(out):
            keep.add(rel)
            top = srcs[-1]
            stack.index[out_rel(rel)] = Source('switch', out, f'merge:{key}', top.mod, raw=True)
            if rel == 'resources.assets':
                # the merged file streams from its structure owner's .resS
                res = os.path.join(os.path.dirname(report[rel].get('owner') or ''), 'resources.assets.resS')
                for s in stack.all_sources.get('resources.assets.resS', []):
                    if os.path.normcase(os.path.abspath(s.path)) == os.path.normcase(os.path.abspath(res)):
                        stack.index['resources.assets.resS'] = s
    _reference_pass(stack, report, keep, lower, out_root, log)
    # outputs no longer needed
    for rel in list(old):
        if rel not in keep:
            f = os.path.join(out_root, *rel.split('/'))
            if os.path.isfile(f):
                os.remove(f)
    os.makedirs(out_root, exist_ok=True)
    with open(report_path + '.part', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    os.replace(report_path + '.part', report_path)
    return report


def _catalog_dependents(stack):
    """{bundle name: [romfs paths of the bundles that depend on it]} from the stack's catalog (Dpr.bin allDependencies)"""
    from .mods import AA, out_rel
    from .edit.formats import nrbf
    src = stack.index.get(out_rel(AA + '/Dpr.bin'))
    out = {}
    try:
        man = nrbf.load(open(src.path, 'rb').read())
    except Exception:
        return out
    for r in man.records:
        rel = f'{AA}/{r.projectName}/{r.assetBundleName}'
        for d in r.allDependencies or ():
            out.setdefault(d, []).append(rel)
    return out


def _reference_pass(stack, report, keep, lower, out_root, log):
    """A merged bundle must not make a reference dangle that does not dangle with the lower layer's files (a console mod
    made for the unmodded game, merged over a mod that rebuilt a model, would). Checked: every merged bundle and every
    bundle depending on one (the catalog's dependency lists); a new dangling reference sends the merged file that should
    have the object - and a merged file making it - back to the lower layer's, repeated until none is left. The result is
    kept in merged/refs.json by the digest of every merged file's inputs, so an unchanged stack does not check again."""
    from .mods import AA, out_rel
    merged = sorted(rel for rel in keep if rel.startswith(AA + '/') and not rel.endswith('Dpr.bin') and is_unity(rel))
    if not merged:
        return
    key = _digest('refs', MERGE_VERSION, [(rel, report[rel]['key']) for rel in merged])
    cache_path = os.path.join(out_root, 'refs.json')
    try:
        with open(cache_path, encoding='utf-8') as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    if cache.get('key') == key:
        back = cache.get('reverted', {})
    else:
        idx = RefIndex()
        low_paths = {out_rel(rel): src.path for rel, src in lower.items()}
        name_of = {rel: rel[len(AA) + 1:].split('/', 1)[1] for rel in merged if '/' in rel[len(AA) + 1:]}
        by_name = {v: k for k, v in name_of.items()}
        dependents = _catalog_dependents(stack)
        back = {}
        live = set(merged)
        # the files the check reads, read in parallel first: the merged ones, their lower versions, the dependents, and
        # (second round) every dependency they name
        first = set(merged)
        for rel in merged:
            first.update(dependents.get(name_of.get(rel), []))
        paths = {stack.index[out_rel(r)].path for r in first if out_rel(r) in stack.index}
        paths |= {lower[r].path for r in first if r in lower}
        idx.prefetch(paths)
        res0 = _bundle_resolver(stack.index)
        res1 = _bundle_resolver(stack.index, low_paths)
        deps = {d for p in paths for d in idx.info(p)[2]}
        idx.prefetch({res0(d) for d in deps} | {res1(d) for d in deps})
        for _ in range(8):
            res_now = _bundle_resolver(stack.index)
            res_low = _bundle_resolver(stack.index, low_paths)
            cands = set(live) | set(back)
            for rel in live:
                cands.update(dependents.get(name_of.get(rel), []))
            found = {}
            for rel in sorted(cands):
                k = out_rel(rel)
                if k not in stack.index:
                    continue
                owners = {}
                low = lower.get(rel)
                now = idx.dangling(stack.index[k].path, res_now, owners)
                was = idx.dangling(low.path if low is not None else stack.index[k].path, res_low)
                new = now - was
                if not new:
                    continue
                if rel in live:
                    found[rel] = found.get(rel, 0) + len(new)
                for cab, _pid in new:
                    dep = by_name.get(owners.get(cab))
                    if dep in live:
                        found[dep] = found.get(dep, 0) + 1
            if not found:
                break
            for rel, n in found.items():
                stack.index[out_rel(rel)] = lower[rel]
                back[rel] = back.get(rel, 0) + n
                live.discard(rel)
        with open(cache_path + '.part', 'w', encoding='utf-8') as f:
            json.dump({'key': key, 'reverted': back}, f, indent=1)
        os.replace(cache_path + '.part', cache_path)
    for rel, n in back.items():
        stack.index[out_rel(rel)] = lower[rel]
        e = report[rel]
        e['reverted'] = n
        note = "kept the lower layer's file: merged, references would point at objects that are not there"
        if note not in e['notes']:
            e['notes'].append(note)
    if back:
        log(f'{len(back)} merged files kept from the lower layer (with them merged, references would not resolve)')


def clear(state_dir):
    """removes the merged files (uDPRE's own cache) when no console mod is chosen"""
    import shutil
    d = os.path.join(state_dir, 'merged')
    if os.path.isdir(d):
        shutil.rmtree(d)
