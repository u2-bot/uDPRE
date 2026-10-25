"""An edit project: edits/<name>.json in the uDPRE folder = {"format": 1, "ops": [...]}, replayed in order.

Operations (every one addresses rows by keys that mean the same in any mod's files, never by file offsets):
  {"op": "set", "file": BUNDLE, "obj": NAME, "list": FIELD, "key": KEY, "field": F, "value": V}
        one field of one row (list + key) or of the object itself (no list); value = any JSON value (a whole list too).
        KEY per table: PersonalTable / WazaOboeTable / EvolveTable rows -> [monsno, form]; TamagoWazaTable -> [no, formNo];
        AddPersonalTable -> [monsno, formno]; WazaTable -> wazaNo; ItemTable.Item -> no; ItemTable.WazaMachine ->
        machineNo; FieldEncountTable_*.table -> zoneID; TrainerPoke rows -> ID; every other list -> the row index.
  {"op": "text", "lang": "english" | "*", "sheet": "ss_monsname", "label": L, "text": T}    a message label (text form)
  {"op": "words", "lang": ..., "sheet": ..., "label": L, "words": [...]}                    a label's exact word list
  {"op": "randomize", "seed": N, "settings": {...}}                                         randomizer.py
  {"op": "typechart", "values": [[18 x 18]]}                                                0 / 2 / 4 / 8 per cell
  {"op": "metadata", "image": I, "type": "Ns.Type", "field": F, "hex": BYTES}             a field default value
  {"op": "insert", ...}                                                                     inserter.py
  {"op": "extradata", "path": "ExtraData/...json", "json": {...}}                         a mod's ExtraData JSON file
        (an ExtraData/MonData/TMLearnset file the files lack is made: a TM past 128 on a Pokemon without one)
  {"op": "eggmoves", "key": [monsno, form], "moves": [...]}       egg moves of a Pokemon with no TamagoWazaTable row
An operation whose row is not in the current files (a Luminescent-only species with Luminescent off) is skipped and
reported; the others still apply.
"""
import copy
import hashlib
import json
import os

from . import BUILD_VERSION
from .gamefiles import EditError

FORMAT = 1

PERSONAL_KEYED = {'PersonalTable', 'WazaOboeTable', 'EvolveTable'}
FIELD_KEYS = {
    ('TamagoWazaTable', 'Data'): ('no', 'formNo'),
    ('AddPersonalTable', 'AddPersonal'): ('monsno', 'formno'),
    ('WazaTable', 'Waza'): ('wazaNo',),
    ('ItemTable', 'Item'): ('no',),
    ('ItemTable', 'WazaMachine'): ('machineNo',),
    ('TrainerTable', 'TrainerPoke'): ('ID',),
    ('TowerTrainerTable', 'TrainerPoke'): ('ID',),
    ('TowerSingleStockTable', 'TowerSingleStock'): ('ID',),
    ('TowerDoubleStockTable', 'TowerDoubleStock'): ('ID',),
    ('BattleDataTable', 'BattleWazaData'): ('WazaNo',),
}


def key_fields(obj, lst):
    if obj.startswith('FieldEncountTable_') and lst == 'table':
        return ('zoneID',)
    return FIELD_KEYS.get((obj, lst))


class Project:
    def __init__(self, path=None, data=None):
        self.path = path
        d = data if data is not None else (self._read(path) if path and os.path.isfile(path) else {})
        if d and d.get('format', FORMAT) > FORMAT:
            raise EditError(f'{path}: edit project format {d.get("format")}, this uDPRE reads up to {FORMAT}')
        self.ops = list(d.get('ops', []))
        self.meta = {k: v for k, v in d.items() if k not in ('format', 'ops')}

    @staticmethod
    def _read(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def to_json(self):
        return dict(self.meta, format=FORMAT, ops=self.ops)

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.part', 'w', encoding='utf-8') as f:
            json.dump(self.to_json(), f, indent=1, ensure_ascii=False)
        os.replace(path + '.part', path)
        self.path = path

    def digest(self):
        blob = json.dumps({'v': BUILD_VERSION, 'ops': self.ops}, sort_keys=True, ensure_ascii=False).encode('utf-8')
        return hashlib.sha1(blob).hexdigest()

    def add(self, op):
        self.ops.append(op)

    def add_sets(self, ops):
        """appends set operations, folding a set of the same address into the latest one (an editor saved twice)"""
        for op in ops:
            addr = _address(op)
            if addr is not None and self.ops and _address(self.ops[-1]) == addr:
                self.ops[-1] = op
            else:
                self.ops.append(op)


def _address(op):
    if op.get('op') != 'set':
        return None
    return (op.get('file'), op.get('obj'), op.get('list'), json.dumps(op.get('key')), op.get('field'))


# --- locating rows ----------------------------------------------------------------------------------------------------
def row_key(game, obj, lst, i, row):
    """the key a set operation uses for row i of obj.lst"""
    if obj in PERSONAL_KEYED:
        prow = game.personal[row['id']] if obj != 'PersonalTable' else row
        return list(game.key_of(prow))
    kf = key_fields(obj, lst)
    if kf:
        v = [row.get(k) for k in kf]
        return v if len(v) > 1 else v[0]
    return i


def find_row(game, file, obj, lst, key):
    rows = game.table(file, obj)[lst]
    if obj in PERSONAL_KEYED:
        prow = game.row(*key)
        if prow is None:
            return None
        if obj == 'PersonalTable':
            return prow
        i = prow['id']
        return rows[i] if i < len(rows) else None
    kf = key_fields(obj, lst)
    if kf:
        want = key if isinstance(key, list) else [key]
        for r in rows:
            if [r.get(k) for k in kf] == want:
                return r
        return None
    return rows[key] if isinstance(key, int) and 0 <= key < len(rows) else None


def set_op(game, file, obj, lst, row_or_none, field, value, key=None):
    """-> the set operation that writes `value` (also applies it)"""
    if lst is not None and key is None:
        rows = game.table(file, obj)[lst]
        i = next(k for k, r in enumerate(rows) if r is row_or_none)
        key = row_key(game, obj, lst, i, row_or_none)
    op = {'op': 'set', 'file': file, 'obj': obj, 'field': field, 'value': copy.deepcopy(value)}
    if lst is not None:
        op['list'], op['key'] = lst, key
    apply_set(game, op)
    return op


def diff_ops(game, file, obj, lst, row, before, after):
    """-> set operations for the fields of `after` that differ from `before` (dicts of one row), applied to the row"""
    ops = []
    for f, v in after.items():
        if before.get(f) != v:
            ops.append(set_op(game, file, obj, lst, row, f, v))
    return ops


def apply_set(game, op):
    tree = game.table(op['file'], op['obj'])
    if op.get('list') is None:
        target = tree
    else:
        target = find_row(game, op['file'], op['obj'], op['list'], op['key'])
        if target is None:
            return f'{op["obj"]}.{op["list"]} has no row {op["key"]}'
    f = op['field']
    if f not in target:
        return f'{op["obj"]}: no field {f}'
    old = target[f]
    if isinstance(old, bool) or not isinstance(old, (int, float)) or isinstance(op['value'], (list, dict, str)):
        target[f] = copy.deepcopy(op['value'])
    elif isinstance(old, int):
        target[f] = int(op['value'])
    else:
        target[f] = float(op['value'])
    return None


def apply_text(game, op):
    from .text import LANGS, Messages
    langs = LANGS if op.get('lang') == '*' else [op.get('lang', 'english')]
    hit = False
    for lang in langs:
        m = game.msg if lang == game.msg.lang else Messages(game.files, lang)
        hit |= m.set_text(op['sheet'], op['label'], op['text'])
    return None if hit else f'no message label {op["sheet"]}/{op["label"]}'


def apply_words(game, op):
    from .text import LANGS, Messages
    langs = LANGS if op.get('lang') == '*' else [op.get('lang', 'english')]
    hit = False
    for lang in langs:
        m = game.msg if lang == game.msg.lang else Messages(game.files, lang)
        lab = m.label(op['sheet'], op['label'])
        if lab is not None:
            lab['wordDataArray'] = copy.deepcopy(op['words'])
            hit = True
    return None if hit else f'no message label {op["sheet"]}/{op["label"]}'


def apply(game, project, context, log=print):
    """Replays every operation on game; context = the build's helpers (player metadata, seed log ...). -> [warnings]"""
    from . import randomizer
    warnings = []
    for k, op in enumerate(project.ops):
        kind = op.get('op')
        try:
            if kind == 'set':
                w = apply_set(game, op)
            elif kind == 'text':
                w = apply_text(game, op)
            elif kind == 'words':
                w = apply_words(game, op)
            elif kind == 'eggmoves':
                ok = game.set_egg_moves(op['key'][0], op['key'][1], op['moves'])
                w = None if ok else f'these game files have no Pokemon {op["key"]}'
            elif kind == 'extradata':
                from .game import TM_LEARNSET
                if not game.files.exists(op['path']) and not op['path'].startswith(TM_LEARNSET + '/'):
                    w = f'these game files have no {op["path"]}'
                else:
                    game.set_extradata(op['path'], op['json'])
                    w = None
            elif kind == 'randomize':
                w = randomizer.run(game, op.get('settings') or {}, op.get('seed', 0), context, log)
            elif kind in ('typechart', 'metadata'):
                w = context.metadata_op(op)
            elif kind == 'insert':
                from . import inserter
                w = inserter.apply(game, op, context, log)
            else:
                w = f'unknown operation {kind}'
        except EditError as e:
            w = str(e)
        if w:
            warnings.append(f'operation {k + 1} ({kind}): {w}' if isinstance(w, str) else w)
    return warnings


def describe(op, game=None):
    k = op.get('op')
    if k == 'set':
        key = op.get('key')
        where = f'{op["obj"]}' + (f'.{op["list"]}[{key}]' if op.get('list') is not None else '')
        v = op['value']
        vs = f'{len(v)} values' if isinstance(v, (list, dict)) else repr(v)
        return f'set {where}.{op["field"]} = {vs}'
    if k == 'text':
        return f'text {op["sheet"]}/{op["label"]} = {op["text"][:40]!r}'
    if k == 'randomize':
        on = [i for i, v in (op.get('settings') or {}).items() if v is True]
        return f'randomize (seed {op.get("seed")}): {len(on)} options on'
    if k == 'typechart':
        return 'type chart'
    if k == 'metadata':
        return f'metadata {op.get("type")}.{op.get("field")}'
    if k == 'insert':
        return f'insert {op.get("mode", "")}: {op.get("name", "")}'
    if k == 'extradata':
        return f'ExtraData {op.get("path")}'
    if k == 'eggmoves':
        return f'egg moves of {op.get("key")} = {len(op.get("moves") or [])} moves (new TamagoWazaTable row)'
    return k or '?'
