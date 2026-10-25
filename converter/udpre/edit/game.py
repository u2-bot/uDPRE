"""The game data the editor works on: the masterdata tables of the stack, with names and the keys operations address.

Tables are the MonoBehaviours' own type trees (XLSXContent.*), so every field a mod's files carry is kept, and a mod with
more rows (Luminescent: 1,466 personal rows, 6,000 trainers) is read the same way as the dump. Facts used here, measured on
BDSP v1.3.0 and Luminescent 2.2F:
  - PersonalTable.Personal: row `id` = index; species rows 0..N have id == monsno (form 0); other forms follow, a species'
    form_index pointing at its first other-form row (form f = row form_index + f - 1), form_max = its form count.
  - WazaOboeTable.WazaOboe[i].ar / EvolveTable.Evolve[i].ar belong to personal row i: learnset = (level, move) pairs,
    evolutions = (method, param, species, form, level) tuples.
  - TamagoWazaTable.Data rows = (no, formNo) -> wazaNo list; ItemTable.WazaMachine = TMs (itemNo, machineNo, wazaNo);
    Personal.machine1..machine4 = the TM compatibility bits (machineNo 1 = machine1 bit 0).
  - TrainerTable.TrainerData[i] = trainer i, TrainerPoke row ID i = its party of up to six (P1.. P6 fields).
"""
from .gamefiles import EditError
from .text import Messages

PERSONAL = 'Pml/personal_masterdatas'
MASTER = 'Dpr/masterdatas'
GAMESETTINGS = 'Dpr/scriptableobjects/gamesettings'
UGDATA = 'UnderGround/data/ugdata'
BATTLE = 'Battle/battle_masterdatas'
UI = 'UIs/masterdatas/uimasterdatas'
CONTEST = 'Contest/md/contest_masterdatas'
EVSCRIPT = 'Dpr/ev_script'

STATS = ['basic_hp', 'basic_atk', 'basic_def', 'basic_spatk', 'basic_spdef', 'basic_agi']
STAT_NAMES = ['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed']
SLOT_FIELDS = ['MonsNo', 'FormNo', 'IsRare', 'Level', 'Sex', 'Seikaku', 'Tokusei', 'Waza1', 'Waza2', 'Waza3', 'Waza4', 'Item',
               'Ball', 'Seal', 'TalentHp', 'TalentAtk', 'TalentDef', 'TalentSpAtk', 'TalentSpDef', 'TalentAgi', 'EffortHp',
               'EffortAtk', 'EffortDef', 'EffortSpAtk', 'EffortSpDef', 'EffortAgi']
TALENTS = ['TalentHp', 'TalentAtk', 'TalentDef', 'TalentSpAtk', 'TalentSpDef', 'TalentAgi']
EFFORTS = ['EffortHp', 'EffortAtk', 'EffortDef', 'EffortSpAtk', 'EffortSpDef', 'EffortAgi']
TM_WORDS = ['machine1', 'machine2', 'machine3', 'machine4']
# an overhaul mod's 256-TM sets: ExtraData/MonData/TMLearnset/monsno_<dex>_formno_<form>.json {set01..set08}, bit i of
# setNN = TM index (NN-1)*32 + i; when a Pokemon has one it is that Pokemon's TM set (machine1..4 = its low 128 bits)
TM_LEARNSET = 'ExtraData/MonData/TMLearnset'
TM_SET_WORDS = ['set%02d' % i for i in range(1, 9)]


def pairs(ar, n):
    return [tuple(ar[i:i + n]) for i in range(0, len(ar) - n + 1, n)]


def flat(rows):
    return [v for r in rows for v in r]


class Game:
    def __init__(self, files, lang='english'):
        self.files = files
        self.msg = Messages(files, lang)
        self._names = {}

    # --- raw tables ---------------------------------------------------------------------------------------------------
    def table(self, bundle, obj):
        return self.files.bundle(bundle).mono(obj)

    def has_table(self, bundle, obj):
        try:
            return self.files.bundle(bundle).has(obj)
        except EditError:
            return False

    @property
    def personal(self):
        return self.table(PERSONAL, 'PersonalTable')['Personal']

    @property
    def learnsets(self):
        return self.table(PERSONAL, 'WazaOboeTable')['WazaOboe']

    @property
    def evolutions(self):
        return self.table(PERSONAL, 'EvolveTable')['Evolve']

    @property
    def egg_moves(self):
        return self.table(PERSONAL, 'TamagoWazaTable')['Data']

    @property
    def add_personal(self):
        return self.table(PERSONAL, 'AddPersonalTable')['AddPersonal']

    @property
    def moves(self):
        return self.table(PERSONAL, 'WazaTable')['Waza']

    @property
    def items(self):
        return self.table(PERSONAL, 'ItemTable')['Item']

    @property
    def tms(self):
        return self.table(PERSONAL, 'ItemTable')['WazaMachine']

    @property
    def grow(self):
        return self.table(PERSONAL, 'GrowTable')['Data']

    @property
    def trainer_table(self):
        return self.table(MASTER, 'TrainerTable')

    @property
    def trainers(self):
        return self.trainer_table['TrainerData']

    @property
    def trainer_pokes(self):
        return self.trainer_table['TrainerPoke']

    @property
    def trainer_types(self):
        return self.trainer_table['TrainerType']

    @property
    def tower(self):
        return self.table(MASTER, 'TowerTrainerTable')

    @property
    def shops(self):
        return self.table(MASTER, 'ShopTable')

    @property
    def pickup(self):
        return self.table(MASTER, 'MonohiroiTable')['MonoHiroi']

    def encounter_files(self):
        """-> [(version letter, FieldEncountTable tree)] - d = Brilliant Diamond, p = Shining Pearl"""
        b = self.files.bundle(GAMESETTINGS)
        return [(v, b.mono(f'FieldEncountTable_{v}')) for v in ('d', 'p') if b.has(f'FieldEncountTable_{v}')]

    def ug_tables(self):
        b = self.files.bundle(UGDATA)
        return sorted((n, b.mono(n)) for n in b.names() if n.startswith('UgEncount_'))

    def ug_table(self, name):
        return self.files.bundle(UGDATA).mono(name)

    # --- personal rows ------------------------------------------------------------------------------------------------
    def species_count(self):
        """highest species number with a species row"""
        return max(r['monsno'] for r in self.personal if r['id'] == r['monsno'])

    def form_of(self, row):
        if row['id'] == row['monsno']:
            return 0
        return row['id'] - row['form_index'] + 1

    def key_of(self, row):
        return row['monsno'], self.form_of(row)

    def row(self, monsno, form=0):
        P = self.personal
        if form == 0:
            r = P[monsno] if monsno < len(P) else None
            return r if r is not None and r['monsno'] == monsno and r['id'] == monsno else None
        base = self.row(monsno)
        if base is None or form >= base['form_max']:
            return None
        i = base['form_index'] + form - 1
        return P[i] if 0 <= i < len(P) and P[i]['monsno'] == monsno else None

    def forms(self, monsno):
        """-> [personal rows of every form of a species, form 0 first]"""
        base = self.row(monsno)
        if base is None:
            return []
        out = [base]
        for f in range(1, max(1, base['form_max'])):
            r = self.row(monsno, f)
            if r is not None:
                out.append(r)
        return out

    def species_rows(self):
        """every valid personal row except the egg / null row 0"""
        return [r for r in self.personal if r['monsno'] > 0 and r['valid_flag']]

    def learnset(self, row):
        return pairs(self.learnsets[row['id']]['ar'], 2)

    def set_learnset(self, row, moves):
        self.learnsets[row['id']]['ar'] = flat(moves)

    def evolution_list(self, row):
        return pairs(self.evolutions[row['id']]['ar'], 5)

    def set_evolution_list(self, row, evos):
        self.evolutions[row['id']]['ar'] = flat(evos)

    def egg_row(self, monsno, form=0):
        for r in self.egg_moves:
            if r['no'] == monsno and r['formNo'] == form:
                return r
        return None

    def set_egg_moves(self, monsno, form, moves):
        """the egg moves of one Pokemon; one without a TamagoWazaTable row (a mod that left rows out) gets a row, placed in
        personal order (after the row of the nearest earlier Pokemon). -> False when there is no such Pokemon"""
        import copy
        prow = self.row(monsno, form)
        if prow is None:
            return False
        er = self.egg_row(monsno, form)
        if er is not None:
            er['wazaNo'] = list(moves)
            return True
        eggs = self.egg_moves
        order = {self.key_of(r): r['id'] for r in self.personal}
        pos = 0
        for k, r in enumerate(eggs):
            if order.get((r['no'], r['formNo']), -1) < prow['id']:
                pos = k + 1
        new = copy.deepcopy(eggs[0]) if eggs else {}
        new.update(no=monsno, formNo=form, wazaNo=list(moves))
        eggs.insert(pos, new)
        return True

    def tm_learnsets(self):
        """{(monsno, form): romfs path} of the ExtraData TM learnsets (stack files + ones the edits made)"""
        if 'tmls' not in self._names:
            import re
            pat = re.compile(r'monsno_(\d+)_formno_(\d+)\.json$', re.I)
            out = {}
            pre = TM_LEARNSET + '/'
            for k in list(self.files.stack.index) + list(self.files._new):
                if k.startswith(pre):
                    m = pat.search(k)
                    if m:
                        out[(int(m.group(1)), int(m.group(2)))] = k
            self._names['tmls'] = out
        return self._names['tmls']

    def tm_set_size(self):
        """the TM bit set's length: 256 when the first valid Pokemon has an ExtraData TM learnset, else 128"""
        first = next(iter(self.species_rows()), None)
        if first is not None and self.key_of(first) in self.tm_learnsets():
            return 32 * len(TM_SET_WORDS)
        return 32 * len(TM_WORDS)

    def _tm_json(self, key):
        import json
        rel = self.tm_learnsets().get(key)
        if rel is None:
            return None, None
        try:
            obj = json.loads(self.files.read(rel).decode('utf-8-sig'))
        except (ValueError, UnicodeDecodeError, OSError, EditError):
            return rel, None
        return rel, obj if isinstance(obj, dict) else None

    def tm_bits(self, row):
        """the Pokemon's TM set as a list of 0/1 (tm_set_size() long)"""
        size = self.tm_set_size()
        _rel, obj = self._tm_json(self.key_of(row)) if 'monsno' in row else (None, None)
        words = [obj.get(w, 0) for w in TM_SET_WORDS] if obj is not None else [row.get(w, 0) for w in TM_WORDS]
        bits = []
        for v in words:
            v = int(v or 0) & 0xFFFFFFFF
            bits += [(v >> b) & 1 for b in range(32)]
        return (bits + [0] * size)[:max(size, len(bits))]

    def tm_learnset_json(self, row, bits):
        """-> (romfs path, the JSON the bits need) when the Pokemon's ExtraData TM learnset must change (a set of 256 that
        has one, or a bit past 128 in a game of 256-TM sets), else None"""
        size = self.tm_set_size()
        rel, obj = self._tm_json(self.key_of(row))
        if rel is None:
            if size <= 32 * len(TM_WORDS) or not any(bits[32 * len(TM_WORDS):size]):
                return None
            m, f = self.key_of(row)
            rel = f'{TM_LEARNSET}/monsno_{m}_formno_{f}.json'
            obj = {}
        new = dict(obj or {})
        for k, w in enumerate(TM_SET_WORDS):
            v = 0
            for b in range(32):
                if k * 32 + b < len(bits) and bits[k * 32 + b]:
                    v |= 1 << b
            new[w] = v
        return None if new == obj else (rel, new)

    def set_tm_bits(self, row, bits):
        """machine1..4 = the low 128 bits; the ExtraData TM learnset too when the Pokemon has (or now needs) one - a row
        copy (no personal id) only gets its machine words"""
        for k, w in enumerate(TM_WORDS):
            v = 0
            for b in range(32):
                if k * 32 + b < len(bits) and bits[k * 32 + b]:
                    v |= 1 << b
            row[w] = v
        i = row.get('id', -1)
        if 0 <= i < len(self.personal) and self.personal[i] is row:
            ch = self.tm_learnset_json(row, bits)
            if ch:
                self.set_extradata(*ch)

    def item(self, no):
        """the ItemTable row of item `no` (rows are in id order; looked up by field when a mod reorders them)"""
        it = self.items
        if 0 <= no < len(it) and it[no]['no'] == no:
            return it[no]
        return next((r for r in it if r['no'] == no), None)

    def tm_list(self):
        """-> [(bit index 0-based, WazaMachine row, item row)]: a TM's number is its ITEM's group_id when the item's group
        is 4 (WAZA_MACHINE) - ItemTableExtensions.GetWazaMashineNo; CheckWazaMachine tests bit (number - 1)"""
        out = []
        size = self.tm_set_size()
        for t in self.tms:
            it = self.item(t['itemNo'])
            if it is not None and it['group'] == 4 and 0 < it['group_id'] <= size:
                out.append((it['group_id'] - 1, t, it))
        return out

    def bst(self, row):
        return sum(row[s] for s in STATS)

    # --- names --------------------------------------------------------------------------------------------------------
    def _numbered(self, sheet, prefix):
        """{number: name}: the game reads these names BY POSITION in the sheet (MessageManager.GetNameMessage(file, int)
        -> MsbtDataModel.GetLabelDataByIndex = labelDataArray[index]); label names do not always follow (ss_typename has
        no TYPENAME_009, 215 ss_itemname labels are numbered otherwise)"""
        if sheet not in self._names:
            from .text import plain
            self._names[sheet] = {k: plain(lab) for k, lab in enumerate(self.msg.labels(sheet))}
        return self._names[sheet]

    def name_label(self, sheet, number):
        """the label name at position `number` of a name sheet (what a rename edits)"""
        labs = self.msg.labels(sheet)
        return labs[number]['labelName'] if 0 <= number < len(labs) else None

    def species_name(self, monsno):
        return self._numbered('ss_monsname', 'MONSNAME_').get(monsno, f'#{monsno}')

    def form_name(self, monsno, form):
        n = self.msg.text('ss_zkn_form', f'ZKN_FORM_{monsno:03d}_{form:03d}')
        return n

    def pokemon_name(self, monsno, form=0):
        n = self.species_name(monsno)
        if form:
            f = self.form_name(monsno, form)
            return f'{n} ({f})' if f else f'{n} (form {form})'
        return n

    def move_name(self, n):
        return self._numbered('ss_wazaname', 'WAZANAME_').get(n, f'move {n}')

    def item_name(self, n):
        return self._numbered('ss_itemname', 'ITEMNAME_').get(n, f'item {n}')

    def ability_name(self, n):
        return self._numbered('ss_tokusei', 'TOKUSEI_').get(n, f'ability {n}')

    def nature_name(self, n):
        return self._numbered('ss_seikaku', 'SEIKAKU_').get(n, f'nature {n}')

    def type_name(self, n):
        return self._numbered('ss_typename', 'TYPENAME_').get(n, f'type {n}')

    def type_count(self):
        return max(18, len(self._numbered('ss_typename', 'TYPENAME_')))

    def nature_count(self):
        return max(25, len(self._numbered('ss_seikaku', 'SEIKAKU_')))

    def ability_count(self):
        """abilities = the labels of ss_tokusei (by position, like every name sheet)"""
        return len(self.msg.labels('ss_tokusei'))

    def trainer_name(self, i):
        t = self.trainers[i]
        return self.msg.text('dp_trainers_name', t['NameLabel'], t['NameLabel'])

    def trainer_type_name(self, type_id):
        for tt in self.trainer_types:
            if tt['TrainerID'] == type_id:
                return self.msg.text('dp_trainers_type', tt['LabelTrType'], tt['LabelTrType'])
        return f'type {type_id}'

    # --- ExtraData (JSON data some overhaul mods' code reads: romfs/Data/ExtraData/...) --------------------------------
    def extradata(self, sub=''):
        """-> [(romfs path, parsed JSON)] of the stack's ExtraData files under ExtraData/<sub> (edited copies included)"""
        import json
        pre = 'ExtraData/' + (sub.strip('/') + '/' if sub else '')
        out = []
        for k in sorted(self.files.stack.index):
            if k.startswith(pre) and k.lower().endswith('.json'):
                try:
                    out.append((k, json.loads(self.files.read(k).decode('utf-8-sig'))))
                except (ValueError, UnicodeDecodeError):
                    continue
        return out

    def set_extradata(self, rel, obj):
        """an ExtraData JSON file's new content (pretty-printed, same keys); a TM learnset the stack lacks is made"""
        import json
        new = not self.files.exists(rel) and not self.files.has_new(rel)
        self.files.put(rel, json.dumps(obj, indent=2, ensure_ascii=False).encode('utf-8'))
        if new:
            self._names.pop('tmls', None)

    def zone_name(self, zone):
        """'C04 Eterna City' - the zone code (ZoneID) and the place name its MapInfo row names; -1 = 'All'"""
        if zone is None or zone < 0:
            return 'All'
        if 'zones' not in self._names:
            from .zonecodes import CODES
            names = {}
            try:
                zd = self.files.bundle(GAMESETTINGS).mono('MapInfo')['ZoneData']
                for z in zd:
                    names[z['ZoneID']] = self.msg.text('dp_fld_areaname', z['PokePlaceName'])
            except EditError:
                pass
            self._names['zones'] = (CODES, names)
        codes, names = self._names['zones']
        code = codes[zone] if 0 <= zone < len(codes) else f'zone {zone}'
        return f'{code} {names.get(zone, "")}'.strip()

    def trainer_party(self, i):
        """-> the TrainerPoke row of trainer i (ID == i), else None"""
        P = self.trainer_pokes
        if i < len(P) and P[i]['ID'] == i:
            return P[i]
        for r in P:
            if r['ID'] == i:
                return r
        return None

    def party_slots(self, poke_row, prefix_fmt='P{}'):
        """-> [{field: value} of each filled slot (MonsNo != 0)] of a TrainerPoke row"""
        out = []
        for s in range(1, 7):
            p = prefix_fmt.format(s)
            if poke_row.get(p + 'MonsNo', 0):
                out.append({f: poke_row.get(p + f) for f in SLOT_FIELDS})
        return out

    def empty_slot(self):
        """the field values an empty party slot has in this stack's trainer table (the dump: Seal -1, Sex 3, Ball 28;
        Luminescent: all 0) - the most common empty slot"""
        if 'empty_slot' not in self._names:
            from collections import Counter
            c = Counter()
            for r in self.trainer_pokes:
                for s in range(1, 7):
                    p = f'P{s}'
                    if p + 'MonsNo' in r and r[p + 'MonsNo'] == 0:
                        c[tuple(r.get(p + f, 0) for f in SLOT_FIELDS)] += 1
            vals = c.most_common(1)[0][0] if c else tuple(0 for _ in SLOT_FIELDS)
            self._names['empty_slot'] = dict(zip(SLOT_FIELDS, vals))
        return self._names['empty_slot']

    def set_party_slots(self, poke_row, slots, prefix_fmt='P{}'):
        """slots (dicts of SLOT_FIELDS) -> the row's six slots; a slot that stays empty keeps its bytes, one that becomes
        empty gets the table's own empty-slot values"""
        empty = self.empty_slot()
        for s in range(1, 7):
            p = prefix_fmt.format(s)
            src = slots[s - 1] if s - 1 < len(slots) else None
            if src is None or not src.get('MonsNo'):
                if poke_row.get(p + 'MonsNo', 0) == 0:
                    continue
                src = empty
            for f in SLOT_FIELDS:
                if p + f in poke_row:
                    poke_row[p + f] = src.get(f, empty.get(f, 0))
