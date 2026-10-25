"""Edits of the player's global-metadata.dat (IL2CPP field default values): the type chart and the Global Metadata Editor.

The game takes static array initial data (RuntimeHelpers.InitializeArray) and constant values from the metadata at run
time, so changing a default value's bytes in place changes what the game reads - no rebuild of the player. Fields are named
by image + type + field (formats.il2cppmeta), which is the same in the Switch file, our vanilla player and the
Luminescent players, so one operation applies to whichever player the mods choose and to the Switch file of a console
export. Only same-size edits exist (a default value's size is fixed by its type).
  {"op": "typechart", "values": 18 x 18 of 0 / 2 / 4 / 8}  (rows = attacking type, columns = defending type)
  {"op": "metadata", "image": "Assembly-CSharp.dll", "type": "Ns.Type" or "Outer/Inner", "field": NAME, "hex": BYTES}
"""
from .formats import il2cppmeta


def type_chart(meta):
    """-> 18 x 18 values of the chart in `meta`"""
    values, _ = il2cppmeta.type_chart(meta)
    return values


def apply(meta, op):
    """-> None, or why the operation could not be applied"""
    try:
        if op['op'] == 'typechart':
            il2cppmeta.set_type_chart(meta, op['values'])
            return None
        if op['op'] == 'metadata':
            f = meta.find(op['image'], op['type'], op['field'])
            if f is None or f.default is None:
                return f'no field default value {op["image"]} {op["type"]}.{op["field"]}'
            new = bytes.fromhex(op['hex'])
            if len(new) != f.default.size:
                return f'{op["type"]}.{op["field"]}: {len(new)} bytes given, the value has {f.default.size}'
            meta.patch_default(f, new)
            return None
    except (ValueError, KeyError) as e:
        return str(e)
    return f'unknown metadata operation {op.get("op")}'


def field_list(meta):
    """-> [(image name, [(type full name, [Field with a default value])])], images and types sorted by name, fields in
    declaration order - the Global Metadata Editor's three lists"""
    out = []
    for img in sorted(meta.images, key=lambda i: i.name.lower()):
        types = []
        for t in meta.types(img):
            fs = [f for f in meta.fields(t) if f.default is not None]
            if fs:
                types.append((t.full_name, fs))
        if types:
            out.append((img.name, sorted(types, key=lambda x: x[0].lower())))
    return out
