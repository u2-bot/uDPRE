"""Copies of Switch asset bundles under new names, for the Pokemon Inserter (a new Pokemon with its own model and icons).

A bundle is found by its catalog record (Dpr.bin: projectName + '/' + assetBundleName under AssetAssistant). A copy gets:
  - a new serialized-file name CAB-<32 hex> (its .resS entry likewise); Unity refuses two loaded bundles with one CAB name;
  - its AssetBundle object's m_Name / m_AssetBundleName = the new bundle name, m_Dependencies and the asset paths of
    m_Container renamed; object names (GameObjects, Textures, meshes ...) renamed by the same rule;
  - texture / mesh stream paths (archive:/CAB-old/CAB-old.resS) and externals that point at other copied bundles
    re-pointed at the copies' new CAB names;
  - a catalog record = a copy of the source's with the new name, renamed asset paths and dependencies.
Renaming is a list of (old text, new text) applied to names and paths (e.g. 'pm0025_00' -> 'pm0494_00', 'pm0025/' ->
'pm0494/'); the catalog must still pass the game's boot lookup (no duplicate names or asset keys) - checked at the end.
"""
import UnityPy
from UnityPy.files.SerializedFile import SerializedFile

from .. import unityfiles  # noqa: F401  (lenient AssetBundle header)
from .gamefiles import AA, EditError

CATALOG = AA + '/Dpr.bin'


def renamed(text, rules):
    for old, new in rules:
        text = text.replace(old, new)
    return text


class BundleCloner:
    """existing = what to do when a mod already ships bundles at the new names (a custom model made for the new Pokemon):
    'auto' = use the mod's bundles when it ships the whole set (an incomplete set is refused), 'clone' = copy the source's
    bundles over them."""

    def __init__(self, g, rng, existing='auto'):
        self.g = g
        self.rng = rng
        self.existing = existing
        self.jobs = []              # (project, old name, new name, rules or None = the model rules)
        self.model_rules = []       # every model rename of this insert: a shared bundle holds several models' assets
        self.done = []
        self.from_mod = []          # new names whose bundle a mod already ships (used as it is)
        self._man = None

    def catalog(self):
        if self._man is None:
            from .formats import nrbf
            self._man = getattr(self.g.files, '_catalog', None)
            if self._man is None:
                self._man = nrbf.load(self.g.files.read(CATALOG))
                self.g.files._catalog = self._man           # one catalog object per build, saved by finish()
        return self._man

    def exists(self, project, name):
        return self.g.files.exists(f'{AA}/{project}/{name}') or self.g.files.has_new(f'{AA}/{project}/{name}')

    def clone_model(self, old_base, new_base):
        """the battle + field bundles of model old_base and every 'Pokemon Database' bundle they depend on"""
        man = self.catalog()
        sm, sx = old_base[2:6], old_base[7:9]
        dm, dx = new_base[2:6], new_base[7:9]
        rules = [(f'pm{sm}_{sx}', f'pm{dm}_{dx}'), (f'pm{sm}/', f'pm{dm}/')]
        for r in rules:
            if r not in self.model_rules:
                self.model_rules.append(r)
        for kind in ('battle', 'field'):
            r = man.find(f'pokemons/{kind}/{old_base}')
            if r is None:
                continue
            for n in [r.assetBundleName] + list(r.allDependencies or []):
                dep = man.find(n)
                if dep is None or dep.projectName != 'Pokemon Database':
                    continue
                new = renamed(n, rules)
                if new != n and not any(j[1] == n for j in self.jobs):
                    self.jobs.append((dep.projectName, n, new, None))

    def clone(self, project, old, new, rename_map):
        rules = list(rename_map.items())
        self.jobs.append((project, old, new, rules))

    def finish(self):
        man = self.catalog()
        # model names are renamed with every model rule (longest first: pm0025_00 before a shorter folder rule)
        mrules = sorted(self.model_rules, key=lambda r: -len(r[0]))
        self.jobs = [(pj, o, renamed(o, mrules) if r is None else n, mrules if r is None else r)
                     for pj, o, n, r in self.jobs]
        there = [j for j in self.jobs if self.exists(j[0], j[2])]
        if there and self.existing != 'clone':
            if len(there) != len(self.jobs):
                raise EditError(f'a mod ships {len(there)} of the {len(self.jobs)} bundles at the new names ({there[0][0]}/'
                                f'{there[0][2]} ...): that set is incomplete - pick "copy the source\'s models" to copy '
                                'the source\'s bundles over them')
            # a mod made these bundles for the new Pokemon (custom models): they are used as they are
            for project, old, new, rules in self.jobs:
                src = man.find(old)
                if man.find(new) is None and src is not None:
                    man.clone(src, new, asset_paths=[renamed(p, rules) for p in (src.assetPaths or [])],
                              allDependencies=[next((j[2] for j in self.jobs if j[1] == d), d)
                                               for d in (src.allDependencies or [])])
                self.from_mod.append(new)
            bad = man.problems()
            if bad:
                raise EditError(f'the mod\'s bundles would break the catalog: {bad[:3]}')
            self.g.files.set_raw(CATALOG, man.save())
            return
        cab = {}
        envs = []
        for project, old, new, rules in self.jobs:
            rel = f'{AA}/{project}/{old}'
            if not self.g.files.exists(rel):
                raise EditError(f'the game files have no {project}/{old}')
            env = UnityPy.load(self.g.files.path(rel))
            for n, f in env.file.files.items():
                if isinstance(f, SerializedFile):
                    cab[n] = 'CAB-' + ''.join(self.rng.choice('0123456789abcdef') for _ in range(32))
            envs.append((project, old, new, rules, env))
        for project, old, new, rules, env in envs:
            bf = env.file
            files = {}
            for n, f in bf.files.items():
                if isinstance(f, SerializedFile):
                    self._rewrite(f, n, cab, old, new, rules)
                    files[cab[n]] = f
                    f.name = cab[n]
                else:
                    base = n[:-5] if n.endswith('.resS') else n
                    files[cab.get(base, base) + n[len(base):]] = f
            bf.files = files
            self.g.files.put(f'{AA}/{project}/{new}', bf.save(packer='lz4'))     # over a mod's own one with 'clone'
            src = man.find(old)
            if src is not None:
                paths = [renamed(p, rules) for p in (src.assetPaths or [])]
                deps = [next((j[2] for j in self.jobs if j[1] == d), d) for d in (src.allDependencies or [])]
                rec = man.find(new)
                if rec is None:
                    man.clone(src, new, asset_paths=paths, allDependencies=deps)
                else:                                   # the mod's record now describes the copy
                    rec.assetPaths, rec.allDependencies = paths, deps
            self.done.append(new)
        bad = man.problems()
        if bad:
            raise EditError(f'the copied bundles would break the catalog: {bad[:3]}')
        self.g.files.set_raw(CATALOG, man.save())

    def _rewrite(self, sf, name, cab, old, new, rules):
        for e in sf.externals:
            for o_cab, n_cab in cab.items():
                if o_cab in e.path:
                    e.path = e.path.replace(o_cab, n_cab)
        for o in sf.objects.values():
            t = o.type.name
            if t not in ('AssetBundle', 'Texture2D', 'Mesh', 'GameObject', 'AnimationClip', 'Material', 'Sprite',
                         'Avatar', 'AnimatorController'):
                continue
            try:
                tree = o.read_typetree()
            except Exception:
                continue
            changed = False
            if t == 'AssetBundle':
                tree['m_Name'] = tree['m_AssetBundleName'] = new
                tree['m_Dependencies'] = [next((j[2] for j in self.jobs if j[1] == d), d) for d in tree['m_Dependencies']]
                tree['m_Container'] = [(renamed(k, rules), v) for k, v in tree['m_Container']]
                changed = True
            if isinstance(tree.get('m_Name'), str) and t != 'AssetBundle':
                nn = renamed(tree['m_Name'], rules)
                if nn != tree['m_Name']:
                    tree['m_Name'] = nn
                    changed = True
            sd = tree.get('m_StreamData')
            if isinstance(sd, dict) and sd.get('path'):
                p = sd['path']
                for o_cab, n_cab in cab.items():
                    p = p.replace(o_cab, n_cab)
                if p != sd['path']:
                    sd['path'] = p
                    changed = True
            if changed:
                o.save_typetree(tree)


# --- the menu icon: a sprite of the TextureMass SpriteAtlas -----------------------------------------------------------
TEXTUREMASS = 'UIs/textures_mass/texturemass'


def _rgba_page(tex):
    """the first image level of an atlas page Texture2D tree -> (RGBA32 bytes, width, height) in Unity's row order"""
    import texture2ddecoder
    from .. import textures
    fmt, w, h = tex['m_TextureFormat'], tex['m_Width'], tex['m_Height']
    data = bytes(tex['image data'])
    if fmt == textures.RGBA32:
        return data[:w * h * 4], w, h
    if fmt in textures.ASTC or fmt in textures.ETC:
        img, _used = textures._decode_image(fmt, w, h, 1, data)
        return img, w, h
    dec = {10: texture2ddecoder.decode_bc1, 12: texture2ddecoder.decode_bc3, 25: texture2ddecoder.decode_bc7}.get(fmt)
    if dec is None:
        raise EditError(f'the atlas page has texture format {fmt}, which the Inserter cannot read')
    return textures._bgra_to_rgba(dec(data[:textures.image_bytes(fmt, w, h, 1)], w, h), w, h), w, h


def _stream(env, sd):
    """the bytes a texture streams from a .resS entry of its bundle"""
    name = sd['path'].rsplit('/', 1)[-1]
    f = env.file.files.get(name)
    if f is None:
        raise EditError(f'the bundle has no {name}')
    return bytes(f.bytes[sd['offset']:sd['offset'] + sd['size']])


def add_atlas_sprite(data, src_name, new_name, rng, replace=False):
    """the TextureMass bundle's bytes -> (new bytes or None, note): a sprite `new_name` for its SpriteAtlas (the game asks it
    by name: UIManager.GetAtlasSprite(TEXTUREMASS, PokemonIcon.AssetName)) = a copy of sprite `src_name` on its own RGBA32
    texture '<new_name>_Texture2D' holding the source sprite's pixels (cut from its atlas page), so a mod can give the new
    Pokemon its own icon by replacing that texture. Registered in the atlas (packed sprites, names, render data map under a
    new random key) and in the bundle's container like the game's own sprites. When the atlas has a sprite new_name already
    (a mod's icon made for that number: Luminescent ships Gen 9 icons it does not use yet) it is kept (None) - or, with
    replace, made the copy (same object, name and key)."""
    import copy
    env = UnityPy.load(data)
    sf = next(f for f in env.file.files.values() if isinstance(f, SerializedFile))
    objs = sf.objects
    atlas_o = next((o for o in objs.values() if o.type.name == 'SpriteAtlas'), None)
    ab_o = next((o for o in objs.values() if o.type.name == 'AssetBundle'), None)
    if atlas_o is None or ab_o is None:
        raise EditError('the TextureMass bundle has no SpriteAtlas')
    atlas = atlas_o.read_typetree()
    names = atlas['m_PackedSpriteNamesToIndex']
    if new_name in names and not replace:
        return None, f'menu icon {new_name}: the mod\'s own icon used'
    if src_name not in names:
        raise EditError(f'the atlas has no sprite {src_name}')
    sp_ptr = atlas['m_PackedSprites'][names.index(src_name)]
    sp_o = objs.get(sp_ptr['m_PathID'])
    if sp_ptr['m_FileID'] != 0 or sp_o is None:
        raise EditError(f'sprite {src_name} is not in the atlas bundle')
    sprite = sp_o.read_typetree()
    key = sprite['m_RenderDataKey']
    entry = next((v for k, v in atlas['m_RenderDataMap'] if k == key), None)
    if entry is None:
        raise EditError(f'the atlas has no render data for {src_name}')
    page_o = objs.get(entry['texture']['m_PathID'])
    if entry['texture']['m_FileID'] != 0 or page_o is None:
        raise EditError(f'the atlas page of {src_name} is not in the bundle')
    page = page_o.read_typetree()
    if isinstance(page.get('m_StreamData'), dict) and page['m_StreamData'].get('size'):
        page['image data'] = _stream(env, page['m_StreamData'])
    rgba, pw, ph = _rgba_page(page)
    # the sprite's rect on the page: from atlasRectOffset, the size of the sprite rect (m_Rect)
    ax, ay = int(round(entry['atlasRectOffset']['x'])), int(round(entry['atlasRectOffset']['y']))
    w, h = int(round(sprite['m_Rect']['width'])), int(round(sprite['m_Rect']['height']))
    out = bytearray(w * h * 4)
    x0, x1 = max(0, ax), min(pw, ax + w)
    for y in range(h):
        sy = ay + y
        if 0 <= sy < ph and x0 < x1:
            out[(y * w + (x0 - ax)) * 4:(y * w + (x1 - ax)) * 4] = rgba[(sy * pw + x0) * 4:(sy * pw + x1) * 4]
    # only the source sprite's own texels: the rest of its rect on the page belongs to neighbouring sprites
    import math
    tr = entry['textureRect']
    kx0, ky0 = max(0, math.floor(tr['x'] - ax)), max(0, math.floor(tr['y'] - ay))
    kx1, ky1 = min(w, math.ceil(tr['x'] - ax + tr['width'])), min(h, math.ceil(tr['y'] - ay + tr['height']))
    for y in range(h):
        row = y * w * 4
        if not ky0 <= y < ky1:
            out[row:row + w * 4] = bytes(w * 4)
            continue
        out[row:row + kx0 * 4] = bytes(kx0 * 4)
        out[row + kx1 * 4:row + w * 4] = bytes((w - kx1) * 4)
    used = set(objs)

    def new_pid():
        while True:
            v = rng.getrandbits(63) - (1 << 62)
            if v and v not in used:
                used.add(v)
                return v
    # the texture: a copy of the page object with the cut pixels inline (RGBA32, one level)
    tex_o = copy.copy(page_o)
    tex_o.path_id = new_pid()
    tex = dict(page, m_Name=f'{new_name}_Texture2D', m_Width=w, m_Height=h, m_CompleteImageSize=w * h * 4,
               m_TextureFormat=4, m_MipCount=1, m_ImageCount=1)
    tex['m_StreamData'] = dict(page.get('m_StreamData') or {}, offset=0, size=0, path='')
    tex['image data'] = bytes(out)
    objs[tex_o.path_id] = tex_o
    tex_o.save_typetree(tex)
    # the copy's render data points at the new texture (the same rects, relative to the sprite rect)
    ne = copy.deepcopy(entry)
    ne['texture'] = {'m_FileID': 0, 'm_PathID': tex_o.path_id}
    ne['textureRect'] = dict(entry['textureRect'], x=entry['textureRect']['x'] - ax, y=entry['textureRect']['y'] - ay)
    ne['atlasRectOffset'] = dict(entry['atlasRectOffset'], x=0.0, y=0.0)
    ne['uvTransform'] = dict(entry['uvTransform'], y=entry['uvTransform']['y'] - ax, w=entry['uvTransform']['w'] - ay)
    nsprite = copy.deepcopy(sprite)
    nsprite['m_Name'] = new_name
    if new_name in names:
        # replace: the mod's sprite object becomes the copy (its name, key and container entry stay)
        tgt_o = objs[atlas['m_PackedSprites'][names.index(new_name)]['m_PathID']]
        nkey = tgt_o.read_typetree()['m_RenderDataKey']
        nsprite['m_RenderDataKey'] = nkey
        tgt_o.save_typetree(nsprite)
        rdm = atlas['m_RenderDataMap']
        i = next((k for k, (kk, _v) in enumerate(rdm) if kk == nkey), None)
        if i is None:
            rdm.append([nkey, ne])
        else:
            rdm[i] = [nkey, ne]
        atlas_o.save_typetree(atlas)
        return env.file.save(packer='lz4'), f'menu icon {new_name} ({w}x{h}, own texture, over the mod\'s)'
    # the sprite: a copy of the source's with the new name and a new render data key
    nkey = copy.deepcopy(key)
    for i in range(4):
        nkey[0][f'data[{i}]'] = rng.getrandbits(32)
    nsprite['m_RenderDataKey'] = nkey
    spr_o = copy.copy(sp_o)
    spr_o.path_id = new_pid()
    objs[spr_o.path_id] = spr_o
    spr_o.save_typetree(nsprite)
    atlas['m_PackedSprites'].append({'m_FileID': 0, 'm_PathID': spr_o.path_id})
    names.append(new_name)
    atlas['m_RenderDataMap'].append([nkey, ne])
    atlas_o.save_typetree(atlas)
    # the bundle's container: an entry like the source sprite's (path renamed, kept sorted), its preload = the sprite
    ab = ab_o.read_typetree()
    src_c = next(((p, v) for p, v in ab['m_Container'] if v['asset']['m_PathID'] == sp_o.path_id), None)
    if src_c is not None:
        path = src_c[0].replace(src_name, new_name)
        ab['m_PreloadTable'].append({'m_FileID': 0, 'm_PathID': spr_o.path_id})
        item = (path, {'preloadIndex': len(ab['m_PreloadTable']) - 1, 'preloadSize': 1,
                       'asset': {'m_FileID': 0, 'm_PathID': spr_o.path_id}})
        cont = ab['m_Container']
        i = next((k for k, (p, _v) in enumerate(cont) if p > path), len(cont))
        cont.insert(i, item)
        ab_o.save_typetree(ab)
    return env.file.save(packer='lz4'), f'menu icon {new_name} ({w}x{h}, own texture)'
