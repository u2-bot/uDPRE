"""The player's own data files that come from the dump (or from a mod that changes them).

resources.assets (+ .resS): the dump's file converted like a bundle (platform, textures, shaders) plus one rule:
  StartupSettings names five boot methods by assembly-qualified type, three of them in assembly "AssetAssistant"; our build
  compiles SmartPoint.AssetAssistant into Assembly-CSharp, so those names point there (Type.GetType would return null and the
  boot sequence would skip AssetManager / SceneBrowser / SectionCounter ...). Player files carry no type trees, so the strings
  are rewritten in the raw object bytes (Unity string = int32 length + bytes + padding to 4).
  References from it into globalgamemanagers.assets use the Switch path IDs: the release renumbers our script registry to them
  (release/make_player_base.py), so the file needs no reference edits.
globalgamemanagers: ours (from udpre/base/) with the dump's ResourceManager object = the Resources.Load table, whose entries
  point at the converted resources.assets by the Switch path IDs. Both files list their externals in the same order.
"""
import os
import struct

import UnityPy

from . import bundle
from .unityfiles import ConvertError

ASM_OLD = b', AssetAssistant, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null'
ASM_NEW = b', Assembly-CSharp, Version=1.6.28.12450, Culture=neutral, PublicKeyToken=null'
STARTUP_REWRITES_EXPECTED = 5          # BDSP v1.3.0


def _printable(b):
    return all(32 <= c < 127 for c in b)


def rewrite_strings(raw, old, new):
    """Every Unity string in raw (one object's bytes; objects start 8-aligned, so offsets here align like the file) that
    contains `old` -> `new` in its place. A string = int32 length + bytes, then padding to the next multiple of 4.
    -> (bytes, count)."""
    out = bytearray()
    pos = 0
    n = 0
    i = raw.find(old)
    while i != -1:
        start = None
        for p in range(i - 4, max(pos, i - 4096) - 1, -1):
            ln = struct.unpack_from('<i', raw, p)[0]
            if 0 < ln < 4096 and p + 4 + ln >= i + len(old) and _printable(raw[p + 4:p + 4 + ln]):
                start = p
                break
        if start is None:
            raise ConvertError('assembly name found outside a serialized string')
        ln = struct.unpack_from('<i', raw, start)[0]
        end = start + 4 + ln
        padded_end = (end + 3) & ~3
        if any(raw[end:padded_end]):
            raise ConvertError('serialized string not followed by zero padding')
        text = raw[start + 4:end].replace(old, new)
        out += raw[pos:start]
        out += struct.pack('<i', len(text)) + text
        out += b'\0' * ((-len(out)) % 4)      # out and raw[padded_end:] both continue 4-aligned
        pos = padded_end
        n += text.count(new)
        i = raw.find(old, pos)
    out += raw[pos:]
    return bytes(out), n


def convert_resources(src, res_src, out_data, pack, switch_shader_ids):
    """src / res_src = the Switch resources.assets and resources.assets.resS (the dump's, or a mod's - Luminescent ships its
    own resources.assets and streams from the dump's .resS); out_data = the player's Dpr_Data. Writes resources.assets +
    resources.assets.resS."""
    res_name = 'resources.assets.resS'
    with open(res_src, 'rb') as f:
        sources = {res_name: f.read()}
    env = UnityPy.load(src)
    sf = env.file
    stats = {'startup_strings': 0}

    def rules(obj):
        if obj.type.name == 'MonoBehaviour':
            try:
                name = obj.peek_name()
            except Exception:
                return False
            if name == 'StartupSettings':
                raw = obj.get_raw_data()
                new, n = rewrite_strings(raw, ASM_OLD, ASM_NEW)
                if n != STARTUP_REWRITES_EXPECTED:
                    raise ConvertError(f'StartupSettings: {n} AssetAssistant type names, expected {STARTUP_REWRITES_EXPECTED}')
                obj.set_raw_data(new)
                stats['startup_strings'] = n
                return True
        return False

    # a mod's resources.assets over the dump's .resS (Luminescent moved three loading icons inline) leaves .resS ranges no
    # object of it reads: the whole-stream check holds only when both files come from the same place
    same = os.path.dirname(os.path.abspath(src)) == os.path.dirname(os.path.abspath(res_src))
    new_res = bundle.convert_serialized(sf, sources, res_name, 'resources.assets', pack, switch_shader_ids, stats, rules,
                                        strict_streams=same)
    if not stats['startup_strings']:
        raise ConvertError('resources.assets has no StartupSettings')
    data = sf.save()
    _write(os.path.join(out_data, 'resources.assets'), data)
    _write(os.path.join(out_data, res_name), new_res.get(res_name, b''))
    stats['bytes'] = len(data)
    return stats


def patch_globalgamemanagers(sw_file, base_file, out_data):
    """Our globalgamemanagers (base_file) with the ResourceManager object of the Switch globalgamemanagers sw_file (the dump's,
    or a mod's) -> out_data/globalgamemanagers."""
    sw = UnityPy.load(sw_file).file
    ours = UnityPy.load(base_file).file
    if [e.path for e in sw.externals] != [e.path for e in ours.externals]:
        raise ConvertError(f'globalgamemanagers externals differ: {[e.path for e in sw.externals]} vs '
                           f'{[e.path for e in ours.externals]}')
    rm_sw = [o for o in sw.objects.values() if o.type.name == 'ResourceManager']
    rm_ours = [o for o in ours.objects.values() if o.type.name == 'ResourceManager']
    if len(rm_sw) != 1 or len(rm_ours) != 1:
        raise ConvertError('expected one ResourceManager in each globalgamemanagers')
    rm_ours[0].set_raw_data(rm_sw[0].get_raw_data())
    data = ours.save()
    _write(os.path.join(out_data, 'globalgamemanagers'), data)
    return {'bytes': len(data)}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
