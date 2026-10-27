"""Screen shapes other than the game's 16:9: a pack's widescreen rules applied to the game files of the current stack.

A widescreen pack (udpre_mod.json "widescreen": RULES.json, pack format 3) carries no game files, only rules: the values its
UI changes give to positions, anchors, sizes, animation values and particle sizes at three canvas widths - 1280 units (the
game: 16:9), 1608 and 1720 (the mod's 3216x1440 and 3440x1440 versions). A conversion with the pack on makes each value for
the chosen screen shape (piecewise linear through the three widths, extended past the last) and writes the files that change
as one more layer above the packs, like the Editor & Randomizer's layer: the rules work on whatever the stack holds (the
dump, Luminescent's or Darker UI's bundles), so the pack works under every other pack.

The canvas: the game lays its UI out on 1280 x 720 units. A screen wider than 16:9 shows 720 units in height and more in
width (W = 720 x width / height); a narrower one (16:10) shows 1280 in width and more in height (H = 1280 x height / width).
Wider: every rule applies at W. Narrower: only the rules that make an object fill its parent apply (the mod's other changes
are made for wide screens and are the game's own values at W = 1280), and particle sizes grow by H / 720.

The player reads Dpr_Data/StreamingAssets/uDPRE/widescreen.txt (written here) and lays its UI out for the same canvas.
"""
import hashlib
import json
import os
import struct
import sys
import time

from . import mods as modlib

LAYER_ID = 'widescreen'
LAYER_ORDER = 99000             # above every pack and console mod, below the Editor & Randomizer's layer
REF_W, REF_H = 1280.0, 720.0
OPTION = 'screen'               # the pack's option: "auto" (this PC's screen) or a shape "<width>x<height>"
SETTINGS_FILE = 'StreamingAssets/uDPRE/widescreen.txt'
FILL = {('m_AnchorMin', 'x'): 0, ('m_AnchorMin', 'y'): 0, ('m_AnchorMax', 'x'): 1, ('m_AnchorMax', 'y'): 1,
        ('m_SizeDelta', 'x'): 0, ('m_SizeDelta', 'y'): 0, ('m_AnchoredPosition', 'x'): 0, ('m_AnchoredPosition', 'y'): 0,
        ('m_LocalPosition', 'x'): 0, ('m_LocalPosition', 'y'): 0}
BUILD_VERSION = 1               # bump when a rule changes what the build writes for the same rules + stack


def pack_of(chosen):
    """-> the chosen pack with widescreen rules (the top-most), or None"""
    found = [m for m in chosen if getattr(m, 'widescreen', None)]
    return found[-1] if found else None


def display_size():
    """-> (width, height) of this PC's main screen in pixels (its display mode: real pixels whatever the Windows scaling,
    without making the window DPI-aware), or None"""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        mode = ctypes.create_string_buffer(220)                 # DEVMODEW
        struct.pack_into('<H', mode, 68, 220)                   # dmSize
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, mode):     # ENUM_CURRENT_SETTINGS of the main screen
            w, h = struct.unpack_from('<II', mode, 172)         # dmPelsWidth, dmPelsHeight
            if w > 0 and h > 0:
                return w, h
        user32 = ctypes.windll.user32
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)     # the scaled desktop: the same shape
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def shape_of(mod):
    """-> (screen width, screen height, words) the pack's pick asks for"""
    pick = mod.choice.get(OPTION, 'auto')
    if pick == 'auto':
        size = display_size()
        if size is None:
            return 1920, 1080, 'this PC\'s screen (not found: 16:9)'
        return size[0], size[1], f'this PC\'s screen ({size[0]}x{size[1]})'
    try:
        w, h = (int(x) for x in pick.lower().split('x'))
        if w > 0 and h > 0:
            return w, h, f'{w}x{h}'
    except ValueError:
        pass
    return 1920, 1080, f'{pick} (unknown: 16:9)'


def fingerprint(chosen):
    """what a conversion's screen shape is made for: 'WIDTHxHEIGHT' of the picked shape, None without a widescreen pack"""
    mod = pack_of(chosen)
    if mod is None:
        return None
    sw, sh, _ = shape_of(mod)
    return f'{sw}x{sh}'


def canvas(sw, sh):
    """screen size -> (W, H) canvas units: 1280 x 720 at 16:9, wider or taller otherwise"""
    if sw * REF_H >= sh * REF_W:
        return REF_H * sw / sh, REF_H
    return REF_W, REF_W * sh / sw


def load_rules(mod):
    with open(os.path.join(mod.path, mod.widescreen), encoding='utf-8') as f:
        return json.load(f)


def _is_fill(obj):
    """every edit of the object makes it fill its parent (anchors 0..1, no size, no offset)"""
    for e in obj['edits']:
        f = e['f']
        if len(f) != 2 or tuple(f) not in FILL or e['v'][1] != e['v'][2] or e['v'][2] != FILL[tuple(f)]:
            return False
    return True


def value_at(v, w):
    """the value at canvas width w from its values at the rule widths (piecewise linear, extended past the last)"""
    w0, w1, w2 = 1280.0, 1608.0, 1720.0
    v0, v1, v2 = v
    if w <= w0:
        return v0
    if v1 == v2:                # a change that does not depend on the width
        return v2
    if w <= w1:
        return v0 + (v1 - v0) * (w - w0) / (w1 - w0)
    return v1 + (v2 - v1) * (w - w1) / (w2 - w1)


def _f32_word(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def _word_f32(word):
    return struct.unpack('<f', struct.pack('<I', word & 0xFFFFFFFF))[0]


def _get(tree, path):
    cur = tree
    for k in path[:-1]:
        cur = cur[k]
    return cur, path[-1]


def _same(a, b):
    return a == b or (isinstance(a, float) and isinstance(b, float) and abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b)))


class Result:
    def __init__(self):
        self.layer = None
        self.digest = ''
        self.changed = []
        self.notes = []
        self.shape = ''


def out_dir(p):
    return os.path.join(p.state, 'widescreen')


def _object_name(obj, tree):
    if isinstance(tree, dict) and 'm_GameObject' in tree:
        try:
            return obj.assets_file.objects[tree['m_GameObject']['m_PathID']].read_typetree().get('m_Name', '')
        except Exception:
            return ''
    return tree.get('m_Name', '') if isinstance(tree, dict) else ''


def apply_file(path, objs, w, h, notes, rel):
    """the rules of one file -> its new bytes (None when nothing changes)"""
    import UnityPy
    from . import unityfiles  # noqa: F401  (lenient AssetBundle header for Luminescent's bundles)
    env = UnityPy.load(path)
    by_pid = {}
    for o in env.objects:
        by_pid[o.path_id] = o
    wide = w > REF_W + 1e-6
    tall = h > REF_H + 1e-6
    changed = []
    for spec in objs:
        if spec.get('pc_skip'):
            continue
        is_particle = spec['type'] == 'ParticleSystem'
        if not wide and not (tall and (is_particle or _is_fill(spec))):
            continue
        o = by_pid.get(spec['pid'])
        if o is None or o.type.name != spec['type']:
            notes.append(f'{rel}: no {spec["type"]} {spec["name"]} ({spec["pid"]}) - skipped')
            continue
        tree = o.read_typetree()
        if _object_name(o, tree) != spec['name']:
            notes.append(f'{rel}: object {spec["pid"]} is "{_object_name(o, tree)}", not "{spec["name"]}" - skipped')
            continue
        raw = o.get_raw_data()
        for e in spec['edits']:
            try:
                parent, key = _get(tree, e['f'])
                cur = parent[key]
            except (KeyError, IndexError, TypeError):
                notes.append(f'{rel}: {spec["name"]} has no {".".join(map(str, e["f"]))} - skipped')
                continue
            bits = e.get('bits', False)
            cur_v = _word_f32(cur) if bits else cur
            if wide:
                want = value_at(e['v'], w)
            elif is_particle:
                want = e['v'][0] * h / REF_H         # a taller screen: the effect covers H / 720 more height
            else:
                want = e['v'][2]                     # a taller screen: the object fills its parent, as on a wide one
            if not _same(float(cur_v), float(e['v'][0])):
                # another mod below changed this value: move it by what the rule adds (anchors and pivots are set)
                field = str(e['f'][-2]) if len(e['f']) > 1 else ''
                if field not in ('m_AnchorMin', 'm_AnchorMax', 'm_Pivot'):
                    want = cur_v + (want - e['v'][0])
                notes.append(f'{rel}: {spec["name"]} {".".join(map(str, e["f"]))} is {cur_v} below this pack (the game '
                             f'has {e["v"][0]}) - changed relative to it')
            if bits:
                parent[key] = _f32_word(want)
            elif isinstance(cur, int) and not isinstance(cur, bool):
                parent[key] = int(round(want))
            else:
                parent[key] = float(want)
        # save_typetree returns the new bytes and keeps them for the file's save (get_raw_data still reads the old ones)
        if o.save_typetree(tree) != raw:
            changed.append(spec['pid'])
        else:
            o.set_raw_data(raw)
    if not changed:
        return None
    if rel == 'resources.assets':
        return env.file.save()
    return env.file.save(packer='lz4')


def _write_tree(root, files):
    from .edit.build import _write_tree as wt
    return wt(root, files)


def build(p, stack, setup, log=print):
    """The chosen widescreen pack's rules on `stack` (a mods.Stack without this layer). -> Result (layer None when the pack is
    off or the screen is 16:9)."""
    r = Result()
    mod = pack_of(setup.chosen)
    root = out_dir(p)
    if mod is None:
        clear(p)
        return r
    t0 = time.time()
    sw, sh, words = shape_of(mod)
    w, h = canvas(sw, sh)
    r.shape = f'{words}: canvas {w:.1f} x {h:.1f} units'
    rules = load_rules(mod)
    files = rules.get('files', {})
    h_rules = hashlib.sha1(json.dumps(rules, sort_keys=True).encode('utf-8')).hexdigest()
    keys = []
    for rel in sorted(files):
        s = stack.index.get(modlib.out_rel(rel))
        keys.append(f'{rel}={s.key if s else "-"}')
    r.digest = hashlib.sha1(f'b{BUILD_VERSION}|{h_rules}|{w:.4f}x{h:.4f}|{"|".join(keys)}'.encode('utf-8')).hexdigest()
    settings = (f'# uDPRE widescreen - written by uDPRE at every conversion with the {mod.name} pack on. The player lays its '
                f'UI out for this canvas.\n'
                f'shape={sw}x{sh}\ncanvas_width={w:.4f}\ncanvas_height={h:.4f}\npack={mod.id} {mod.version}\n')
    marker = os.path.join(root, 'digest.txt')
    try:
        with open(marker, encoding='utf-8') as f:
            same = f.read().strip() == r.digest
    except OSError:
        same = False
    out = {}
    if same and os.path.isdir(os.path.join(root, 'romfs')):
        for d, _, fs in os.walk(os.path.join(root, 'romfs')):
            for fn in fs:
                full = os.path.join(d, fn)
                out[os.path.relpath(full, os.path.join(root, 'romfs')).replace(os.sep, '/')] = None
        log(f'widescreen: {r.shape} - files made last time are still right')
    else:
        notes = []
        new = {}
        if w > REF_W + 1e-6 or h > REF_H + 1e-6:
            for rel in sorted(files):
                s = stack.index.get(modlib.out_rel(rel))
                if s is None or s.kind != 'switch':
                    notes.append(f'{rel}: not a Switch file of the stack - skipped')
                    continue
                data = apply_file(s.path, files[rel], w, h, notes, rel)
                if data is not None:
                    new[rel] = data
        n = _write_tree(os.path.join(root, 'romfs'), new)
        out = dict.fromkeys(new)
        r.notes = notes
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, 'report.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(f'{mod.name} {mod.version}: {r.shape}\nbuilt {time.strftime("%Y-%m-%d %H:%M:%S")} in '
                    f'{time.time() - t0:.1f} s; {len(new)} files changed ({n} rewritten)\n')
            for rel in sorted(new):
                f.write(f'  {rel}\n')
            for note in notes:
                f.write(f'NOTE {note}\n')
        with open(marker, 'w', encoding='utf-8', newline='\n') as f:
            f.write(r.digest + '\n')
        log(f'widescreen: {r.shape} -> {len(new)} changed files ({n} rewritten) in {time.time() - t0:.1f} s'
            + (f', {len(notes)} notes (udpre/state/widescreen/report.txt)' if notes else ''))
    _write_tree(os.path.join(root, 'files'), {SETTINGS_FILE: settings.encode('utf-8')})
    r.changed = sorted(out)
    layers = [{'files': 'files'}]
    if out:
        layers.insert(0, {'romfs': 'romfs'})
    r.layer = modlib.Mod(root, {'id': LAYER_ID + '-build', 'name': f'{mod.name} ({words})', 'order': LAYER_ORDER,
                                'version': f'b{BUILD_VERSION}', 'layers': layers})
    return r


def clear(p):
    import shutil
    root = out_dir(p)
    for sub in ('romfs', 'files'):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
    try:
        os.remove(os.path.join(root, 'digest.txt'))
    except OSError:
        pass
