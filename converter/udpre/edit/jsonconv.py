"""JSON converter: Pokemon, trainers and text as JSON files people edit with other tools, and back.

Layouts: English names, made unique (a name that repeats gets a number: "X", "X1", "X2"...; a trailing number is counted
up).
  Pokemon:  one object per personal row in row order: readOnly {personalID, dexID, formIndex, formMax, name, formID,
            legendaryMythical} (ignored on import), validFlag, color, graNo, baseStats {hp, atk, def, spAtk, spDef, spd},
            typing [1-2], catchRate, rank, evYield {...}, heldItems {item1, item2, item3}, sexValue, eggCycles,
            initialFriendship, eggGroups [1-2], growthRate, abilities {ability1, ability2, hiddenAbility}, expYield,
            cmHeight, hgWeight, sinnohDexNumber, compatibleTMs ["<TM item> <move>"], eggTarget, eggTargetFormno,
            eggFormnoKawarazunoishi, eggFormInheritKawarazunoishi, levelUpMoves [{level, move}], eggMoves [...],
            evolutions [{method, parameter, target, targetFormID, level}]
  Trainers: one object per TrainerData row: readOnly {trainerID, name}, trainerTypeID, colorID, fightType, arenaID,
            effectID, gold, useItems [<= 4], hpRecoverFlag, giftItem, nameLabel, aiFlags {basicAI, strongAI, expertAI,
            doubleBattleAI, mercifulAI, canUseItems, canSwitchPokemon}, party [{species, formID, shiny, level, sex,
            nature, ability, moveset [<= 4], heldItem, ballID, seal, ivs {..}, evs {..}}]
  Text:     the 10 languages (Japanese kana, kanji, English, French, Italian, German, Spanish, Korean, Simplified and
            Traditional Chinese): {textAssets: [{assetName, strings: [...]}]}, one string per label; a word's text is
            followed by its event: \\n NewLine, \\w Wait, \\r ScrollPage, \\f ScrollLine, \\e CallBack, \\0 none, nothing
            for End. A name tag is written {Tn} (a string that leaves it out is read too).
Import compares with the current data and keeps only the differences, as ordinary operations of the edit project.
"""
import re

from . import enums
from .game import PERSONAL, MASTER, EFFORTS, TALENTS
from .project import set_op

STAT_KEYS = ['hp', 'atk', 'def', 'spAtk', 'spDef', 'spd']
# PersonalTable stat field per JSON key (the table keeps Speed before the special stats)
STAT_FIELD = dict(zip(STAT_KEYS, ['basic_hp', 'basic_atk', 'basic_def', 'basic_spatk', 'basic_spdef', 'basic_agi']))
EV_SHIFT = {'hp': 0, 'atk': 2, 'def': 4, 'spd': 6, 'spAtk': 8, 'spDef': 10}
AI_KEYS = ['basicAI', 'strongAI', 'expertAI', 'doubleBattleAI', 'mercifulAI', 'canUseItems', 'canSwitchPokemon']
SEX_NAMES = ['Male', 'Female', 'Genderless', 'Random']
TEXT_LANGS = [('jpn', False), ('jpn_kanji', True), ('english', False), ('french', False), ('italian', False),
              ('german', False), ('spanish', False), ('korean', False), ('simp_chinese', False), ('trad_chinese', False)]
MACRO = {0: '\\0', 1: '\\n', 2: '\\w', 3: '\\r', 4: '\\f', 5: '\\e', 7: ''}
MACRO_EV = {'0': 0, 'n': 1, 'w': 2, 'r': 3, 'f': 4, 'e': 5}


class JsonError(ValueError):
    pass


def unique(names):
    """the name list made unique: later repeats get a number appended (or their trailing number counted up)"""
    seen, out = set(), []
    for n in names:
        x = n
        while x in seen:
            m = re.search(r'\d+$', x)
            x = x[:m.start()] + str(int(m.group()) + 1) if m else x + '1'
        seen.add(x)
        out.append(x)
    return out


class Lookup:
    def __init__(self, pairs):
        self.values = [v for v, _ in pairs]
        self.names = unique([n for _, n in pairs])
        self.by_name = {n.lower(): v for v, n in zip(self.values, self.names)}
        self.by_value = {}
        for v, n in zip(self.values, self.names):
            self.by_value.setdefault(v, n)

    def name(self, v):
        return self.by_value.get(v, str(v))

    def value(self, n, what):
        if n is None:
            raise JsonError(f'{what}: null is not a {what}')
        v = self.by_name.get(str(n).lower())
        if v is None:
            raise JsonError(f'"{n}" is not something that exists ({what})')
        return v


class Tables:
    def __init__(self, g):
        self.g = g
        self.types = Lookup([(k, g.type_name(k)) for k in range(g.type_count())])
        self.items = Lookup([(i['no'], g.item_name(i['no'])) for i in g.items])
        self.abilities = Lookup([(k, g.ability_name(k)) for k in range(g.ability_count())])
        self.moves = Lookup([(m['wazaNo'], g.move_name(m['wazaNo'])) for m in g.moves])
        self.natures = Lookup([(k, g.nature_name(k)) for k in range(g.nature_count())])
        self.species = Lookup([(r['monsno'], g.species_name(r['monsno'])) for r in g.personal if r['id'] == r['monsno']])
        self.growth = Lookup(enums.GROWTH_RATES)
        self.colors = Lookup(enums.COLORS)
        self.egg_groups = Lookup([(k, n if k else '') for k, n in enums.EGG_GROUPS])     # group 0 = ''
        self.tms = Lookup([(bit, f'{g.item_name(it["no"])} {g.move_name(tm["wazaNo"])}') for bit, tm, it in g.tm_list()])


def legends(g):
    out = set()
    for _, t in g.encounter_files()[:1]:
        for r in t.get('legendpoke', []):
            out.add(r['monsNo'])
    return out


# --- Pokemon ----------------------------------------------------------------------------------------------------------
def export_pokemon(g):
    T = Tables(g)
    leg = legends(g)
    out = []
    for r in g.personal:
        m, f = r['monsno'], g.form_of(r)
        ev = r['exp_value']
        er = g.egg_row(m, f)
        bits = g.tm_bits(r)
        out.append({
            'readOnly': {'personalID': r['id'], 'dexID': m, 'formIndex': r['form_index'], 'formMax': r['form_max'],
                         'name': g.species_name(m), 'formID': f, 'legendaryMythical': m in leg},
            'validFlag': bool(r['valid_flag']), 'color': T.colors.name(r['color']), 'graNo': r['gra_no'],
            'baseStats': {k: r[STAT_FIELD[k]] for k in STAT_KEYS},
            'typing': [T.types.name(r['type1'])] + ([T.types.name(r['type2'])] if r['type2'] != r['type1'] else []),
            'catchRate': r['get_rate'], 'rank': r['rank'],
            'evYield': {k: (ev >> EV_SHIFT[k]) & 3 for k in STAT_KEYS},
            'heldItems': {'item1': T.items.name(r['item1']), 'item2': T.items.name(r['item2']),
                          'item3': T.items.name(r['item3'])},
            'sexValue': r['sex'], 'eggCycles': r['egg_birth'], 'initialFriendship': r['initial_friendship'],
            'eggGroups': [T.egg_groups.name(r['egg_group1'])] + ([T.egg_groups.name(r['egg_group2'])]
                                                                 if r['egg_group2'] != r['egg_group1'] else []),
            'growthRate': T.growth.name(r['grow']),
            'abilities': {'ability1': T.abilities.name(r['tokusei1']), 'ability2': T.abilities.name(r['tokusei2']),
                          'hiddenAbility': T.abilities.name(r['tokusei3'])},
            'expYield': r['give_exp'], 'cmHeight': r['height'], 'hgWeight': r['weight'],
            'sinnohDexNumber': r['chihou_zukan_no'],
            'compatibleTMs': [T.tms.name(bit) for bit, _, _ in g.tm_list() if bit < len(bits) and bits[bit]],
            'eggTarget': T.species.name(r['egg_monsno']), 'eggTargetFormno': r['egg_formno'],
            'eggFormnoKawarazunoishi': r.get('egg_formno_kawarazunoishi', 0),
            'eggFormInheritKawarazunoishi': r.get('egg_form_inherit_kawarazunoishi', 0),
            'levelUpMoves': [{'level': lv, 'move': T.moves.name(mv)} for lv, mv in g.learnset(r)],
            'eggMoves': [T.moves.name(mv) for mv in (er['wazaNo'] if er else [])],
            'evolutions': [{'method': e[0], 'parameter': e[1], 'target': T.species.name(e[2]), 'targetFormID': e[3],
                            'level': e[4]} for e in g.evolution_list(r)],
        })
    return out


def import_pokemon(g, data):
    """-> set operations (applied) for every value that differs"""
    T = Tables(g)
    if not isinstance(data, list) or len(data) != len(g.personal):
        raise JsonError(f'Incorrect number of Pokemon: {len(data) if isinstance(data, list) else 0}, these game files '
                        f'have {len(g.personal)}')
    ops = []
    for i, (r, d) in enumerate(zip(g.personal, data)):
        where = f'Pokemon {i} ({g.pokemon_name(r["monsno"], g.form_of(r))})'
        try:
            new = {'valid_flag': 1 if d['validFlag'] else 0, 'color': T.colors.value(d['color'], 'color'),
                   'gra_no': int(d['graNo']), 'get_rate': int(d['catchRate']), 'rank': int(d['rank']),
                   'sex': int(d['sexValue']), 'egg_birth': int(d['eggCycles']),
                   'initial_friendship': int(d['initialFriendship']), 'grow': T.growth.value(d['growthRate'], 'growth rate'),
                   'give_exp': int(d['expYield']), 'height': int(d['cmHeight']), 'weight': int(d['hgWeight']),
                   'chihou_zukan_no': int(d['sinnohDexNumber']), 'egg_monsno': T.species.value(d['eggTarget'], 'species'),
                   'egg_formno': int(d['eggTargetFormno'])}
            for k in STAT_KEYS:
                new[STAT_FIELD[k]] = int(d['baseStats'][k])
            ty = d['typing']
            if not 1 <= len(ty) <= 2:
                raise JsonError('typing needs 1 or 2 types')
            new['type1'] = T.types.value(ty[0], 'type')
            new['type2'] = T.types.value(ty[-1], 'type')
            eg = d['eggGroups']
            if not 1 <= len(eg) <= 2:
                raise JsonError('eggGroups needs 1 or 2 groups')
            new['egg_group1'] = T.egg_groups.value(eg[0], 'egg group')
            new['egg_group2'] = T.egg_groups.value(eg[-1], 'egg group')
            ev = r['exp_value']
            for k in STAT_KEYS:
                ev = (ev & ~(3 << EV_SHIFT[k])) | ((int(d['evYield'][k]) & 3) << EV_SHIFT[k])
            new['exp_value'] = ev
            for k, f in (('item1', 'item1'), ('item2', 'item2'), ('item3', 'item3')):
                new[f] = T.items.value(d['heldItems'][k], 'item')
            for k, f in (('ability1', 'tokusei1'), ('ability2', 'tokusei2'), ('hiddenAbility', 'tokusei3')):
                new[f] = T.abilities.value(d['abilities'][k], 'ability')
            for k, f in (('eggFormnoKawarazunoishi', 'egg_formno_kawarazunoishi'),
                         ('eggFormInheritKawarazunoishi', 'egg_form_inherit_kawarazunoishi')):
                if f in r and k in d:
                    new[f] = int(d[k])
            bits = g.tm_bits(r)                     # bits no TM item stands for stay as they are
            for bit in T.tms.values:
                if bit < len(bits):
                    bits[bit] = 0
            for lab in d.get('compatibleTMs', []):
                bits[T.tms.value(lab, 'TM')] = 1
            tmp = dict(r)
            g.set_tm_bits(tmp, bits)
            ch = g.tm_learnset_json(r, bits)        # a mod's 256-TM set (ExtraData) changes with it
            for w in ('machine1', 'machine2', 'machine3', 'machine4'):
                new[w] = tmp[w]
            for f, v in new.items():
                if f in r and r[f] != v:
                    ops.append(set_op(g, PERSONAL, 'PersonalTable', 'Personal', r, f, v))
            if ch:
                g.set_extradata(*ch)
                ops.append({'op': 'extradata', 'path': ch[0], 'json': ch[1]})
            key = list(g.key_of(r))
            # the order given is kept (the game's own lists are not always sorted by level)
            learn = [(int(x['level']), T.moves.value(x['move'], 'move')) for x in d.get('levelUpMoves', [])]
            if learn != g.learnset(r):
                ops.append(set_op(g, PERSONAL, 'WazaOboeTable', 'WazaOboe', g.learnsets[r['id']], 'ar',
                                  [v for p in learn for v in p], key=key))
            er = g.egg_row(*key)
            eggs = [T.moves.value(x, 'move') for x in d.get('eggMoves', [])]
            if er is not None and eggs != list(er['wazaNo']):
                ops.append(set_op(g, PERSONAL, 'TamagoWazaTable', 'Data', er, 'wazaNo', eggs))
            elif er is None and eggs:
                g.set_egg_moves(key[0], key[1], eggs)
                ops.append({'op': 'eggmoves', 'key': key, 'moves': eggs})
            evos = [(int(e['method']), int(e['parameter']), T.species.value(e['target'], 'species'), int(e['targetFormID']),
                     int(e['level'])) for e in d.get('evolutions', [])]
            if evos != g.evolution_list(r):
                ops.append(set_op(g, PERSONAL, 'EvolveTable', 'Evolve', g.evolutions[r['id']], 'ar',
                                  [v for e in evos for v in e], key=key))
        except (KeyError, TypeError, ValueError) as e:
            raise JsonError(f'{where}: {e}')
    return ops


# --- trainers ---------------------------------------------------------------------------------------------------------
def export_trainers(g):
    T = Tables(g)
    out = []
    for i, t in enumerate(g.trainers):
        p = g.trainer_party(i)
        party = []
        for s in (g.party_slots(p) if p else []):
            party.append({'species': T.species.name(s['MonsNo']), 'formID': s['FormNo'], 'shiny': bool(s['IsRare']),
                          'level': s['Level'], 'sex': SEX_NAMES[s['Sex']] if 0 <= s['Sex'] < 4 else None,
                          'nature': T.natures.name(s['Seikaku']), 'ability': T.abilities.name(s['Tokusei']),
                          'moveset': [T.moves.name(s[f'Waza{k}']) for k in (1, 2, 3, 4) if s[f'Waza{k}']],
                          'heldItem': T.items.name(s['Item']), 'ballID': s['Ball'], 'seal': s['Seal'],
                          'ivs': {k: s[f] for k, f in zip(STAT_KEYS, TALENTS)},
                          'evs': {k: s[f] for k, f in zip(STAT_KEYS, EFFORTS)}})
        out.append({'readOnly': {'trainerID': i, 'name': g.trainer_name(i)}, 'trainerTypeID': t['TypeID'],
                    'colorID': t['ColorID'], 'fightType': t['FightType'], 'arenaID': t['ArenaID'],
                    'effectID': t['EffectID'], 'gold': t['Gold'],
                    'useItems': [T.items.name(t[f'UseItem{k}']) for k in (1, 2, 3, 4) if t[f'UseItem{k}']],
                    'hpRecoverFlag': bool(t['HpRecoverFlag']), 'giftItem': t['GiftItem'], 'nameLabel': t['NameLabel'],
                    'aiFlags': {k: bool(t['AIBit'] >> b & 1) for b, k in enumerate(AI_KEYS)}, 'party': party})
    return out


def import_trainers(g, data):
    T = Tables(g)
    if not isinstance(data, list) or len(data) != len(g.trainers):
        raise JsonError(f'Incorrect number of trainers: these game files have {len(g.trainers)}')
    ops = []
    for i, (t, d) in enumerate(zip(g.trainers, data)):
        try:
            items = [T.items.value(x, 'item') for x in d.get('useItems', [])]
            if len(items) > 4:
                raise JsonError('more than 4 items')
            ai = t['AIBit']
            for b, k in enumerate(AI_KEYS):
                ai = (ai | (1 << b)) if d['aiFlags'].get(k) else (ai & ~(1 << b))
            new = {'TypeID': int(d['trainerTypeID']), 'ColorID': int(d['colorID']), 'FightType': int(d['fightType']),
                   'ArenaID': int(d['arenaID']), 'EffectID': int(d.get('effectID', t['EffectID'])), 'Gold': int(d['gold']),
                   'HpRecoverFlag': 1 if d['hpRecoverFlag'] else 0, 'GiftItem': int(d['giftItem']),
                   'NameLabel': str(d['nameLabel']), 'AIBit': ai}
            for k in (1, 2, 3, 4):
                new[f'UseItem{k}'] = items[k - 1] if k - 1 < len(items) else 0
            for f, v in new.items():
                if f in t and t[f] != v:
                    ops.append(set_op(g, MASTER, 'TrainerTable', 'TrainerData', t, f, v, key=i))
            p = g.trainer_party(i)
            if p is None:
                continue
            slots = []
            for x in d.get('party', []):
                sp = T.species.value(x['species'], 'species')
                if g.row(sp, int(x['formID'])) is None:
                    raise JsonError(f'{x["species"]} has no form {x["formID"]}')
                mv = [T.moves.value(n, 'move') for n in x.get('moveset', [])]
                if len(mv) > 4:
                    raise JsonError('more than 4 moves')
                s = {'MonsNo': sp, 'FormNo': int(x['formID']), 'IsRare': 1 if x['shiny'] else 0, 'Level': int(x['level']),
                     'Sex': SEX_NAMES.index(x['sex']) if x.get('sex') in SEX_NAMES else 3,
                     'Seikaku': T.natures.value(x['nature'], 'nature'), 'Tokusei': T.abilities.value(x['ability'], 'ability'),
                     'Item': T.items.value(x['heldItem'], 'item'), 'Ball': int(x['ballID']), 'Seal': int(x['seal'])}
                for k in (1, 2, 3, 4):
                    s[f'Waza{k}'] = mv[k - 1] if k - 1 < len(mv) else 0
                for k, f in zip(STAT_KEYS, TALENTS):
                    s[f] = int(x['ivs'][k])
                for k, f in zip(STAT_KEYS, EFFORTS):
                    s[f] = int(x['evs'][k])
                slots.append(s)
            if len(slots) > 6:
                raise JsonError('more than 6 Pokemon')
            tmp = dict(p)
            g.set_party_slots(tmp, slots)
            for f, v in tmp.items():
                if p[f] != v:
                    ops.append(set_op(g, MASTER, 'TrainerTable', 'TrainerPoke', p, f, v))
        except (KeyError, TypeError, ValueError) as e:
            raise JsonError(f'trainer {i}: {e}')
    return ops


# --- text -------------------------------------------------------------------------------------------------------------
def _sheets(g, lang):
    """[(sheet tree)] of one language in file order (Message/<lang> then the language's sheets of common_msbt)"""
    out = []
    for rel in (f'Message/{lang}', 'Message/common_msbt'):
        try:
            b = g.files.bundle(rel)
        except Exception:
            continue
        for n in b.names():
            if n.startswith(lang + '_') and (lang != 'jpn' or not n.startswith('jpn_kanji_')):
                t = b.mono(n)
                if 'labelDataArray' in t:
                    out.append(t)
    return out


def macro(label):
    out = []
    for w in label.get('wordDataArray') or []:
        out.append(('{T%d}' % w['tagIndex']) if w['patternID'] == 5 else w['str'])
        out.append(MACRO.get(w['eventID'], '\\0'))
    return ''.join(out)


def export_text(g):
    return [{'textAssets': [{'assetName': t['m_Name'], 'strings': [macro(l) for l in t['labelDataArray']]}
                            for t in _sheets(g, lang)]} for lang, _ in TEXT_LANGS]


def from_macro(s, widths, last_style):
    """a macro string -> wordDataArray (name tags {Tn} kept as tag words)"""
    parts = re.split(r'\\(.)', s)
    words = []
    for k in range(0, len(parts), 2):
        txt = parts[k]
        ev = MACRO_EV.get(parts[k + 1]) if k + 1 < len(parts) else 7
        if k + 1 < len(parts) and ev is None:
            raise JsonError(f'Unknown macro \\{parts[k + 1]}')
        for piece in re.split(r'(\{T\d+\})', txt):
            if piece.startswith('{T') and piece.endswith('}'):
                words.append({'patternID': 5, 'eventID': 0, 'tagIndex': int(piece[2:-1]), 'tagValue': 0.0, 'str': '',
                              'strWidth': -1.0})
            elif piece:
                words.append({'patternID': 0, 'eventID': 0, 'tagIndex': -1, 'tagValue': 0.0, 'str': piece,
                              'strWidth': float(widths.width(piece))})
        if ev:
            if words and words[-1]['eventID'] == 0 and words[-1]['patternID'] in (0, 5):
                words[-1]['eventID'] = ev
                if words[-1]['patternID'] == 0 and ev != 7:
                    words[-1]['patternID'] = 7
            else:
                words.append({'patternID': 7, 'eventID': ev, 'tagIndex': -1, 'tagValue': 0.0, 'str': '',
                              'strWidth': 0.0 if ev != 7 else -1.0})
    if words and words[-1]['eventID'] == 7 and words[-1]['patternID'] == 0 and last_style[0] == 7:
        words[-1]['patternID'] = 7
    return words


def import_text(g, data):
    from .text import Widths
    if not isinstance(data, list) or len(data) != len(TEXT_LANGS):
        raise JsonError(f'Incorrect number of languages: {len(TEXT_LANGS)} expected')
    widths = Widths(g.files)
    ops = []
    for (lang, _), d in zip(TEXT_LANGS, data):
        sheets = _sheets(g, lang)
        assets = d.get('textAssets', [])
        if len(assets) != len(sheets):
            raise JsonError(f'Incorrect number of text assets for {lang}: {len(assets)}, the game has {len(sheets)}')
        for t, a in zip(sheets, assets):
            labels = t['labelDataArray']
            if len(a['strings']) != len(labels):
                raise JsonError(f'Incorrect number of strings in {t["m_Name"]}')
            for lab, s in zip(labels, a['strings']):
                if macro(lab) == s:
                    continue
                ws = lab.get('wordDataArray') or []
                lab['wordDataArray'] = from_macro(s, widths, (ws[-1]['patternID'], ws[-1]['eventID']) if ws else (0, 7))
                ops.append({'op': 'words', 'lang': lang, 'sheet': t['m_Name'][len(lang) + 1:], 'label': lab['labelName'],
                            'words': lab['wordDataArray']})
    return ops
