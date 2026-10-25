"""Showdown team text <-> trainer party slots (TrainerPoke slot fields of game.SLOT_FIELDS).

Export, per Pokemon (blocks separated by a blank line):
  Name[-Form] [(M)|(F)] [@ Item] / [Level: n] (when not 100) / Ability: A / [Shiny: Yes] / [EVs: n HP / ...] (non-zero) /
  Nature Nature / [IVs: ...] (stats != 31) / - Move (each non-empty move)
Forms are named Showdown's way: the species name, a hyphen and the form's short name, made from the game's own form
name (ss_zkn_form: "Wash Rotom" -> Rotom-Wash, "Origin Forme" -> Giratina-Origin, "Alolan Form" -> -Alola) with a table of
Showdown's irregular names. Import takes that name, the game's own "Species (Form name)", or the plain species (form 0);
a nickname line "Nick (Species)" is understood too. Sex: (M) 0, (F) 1, none -> 3 (random), genderless species -> 2.
Unknown names are reported as problems instead of becoming invalid ids.
"""
import re

STAT_TOKENS = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']
TALENTS = ['TalentHp', 'TalentAtk', 'TalentDef', 'TalentSpAtk', 'TalentSpDef', 'TalentAgi']
EFFORTS = ['EffortHp', 'EffortAtk', 'EffortDef', 'EffortSpAtk', 'EffortSpDef', 'EffortAgi']
REGIONAL = {'alolan': 'Alola', 'galarian': 'Galar', 'hisuian': 'Hisui', 'paldean': 'Paldea'}
DROP_WORDS = {'forme', 'form', 'cloak', 'mode', 'style', 'pattern', 'size', 'flower', 'face', 'plumage', 'kyurem', 'rotom',
              'core', 'color', 'colour', 'sea', 'breed'}
IRREGULAR = {('Unown', 'One form'): '', ('Castform', 'Normal Form'): '', ('Deoxys', 'Normal Forme'): '',
             ('Burmy', 'Plant Cloak'): '', ('Wormadam', 'Plant Cloak'): '', ('Shellos', 'West Sea'): '',
             ('Gastrodon', 'West Sea'): '', ('Giratina', 'Altered Forme'): '', ('Shaymin', 'Land Forme'): '',
             ('Rotom', 'Rotom'): '', ('Cherrim', 'Overcast Form'): '', ('Arceus', 'Normal'): ''}


def form_suffix(species, form_name):
    """'Wash Rotom' -> 'Wash', 'Mega Charizard X' -> 'Mega-X', 'Alolan Form' -> 'Alola'; '' = the base form"""
    if not form_name:
        return ''
    if (species, form_name) in IRREGULAR:
        return IRREGULAR[(species, form_name)]
    words = [w for w in re.split(r'[\s]+', form_name.replace(species, ' ')) if w]
    out = []
    for w in words:
        lw = w.lower().strip('()')
        if lw in REGIONAL:
            out.append(REGIONAL[lw])
        elif lw not in DROP_WORDS:
            out.append(re.sub(r'[^A-Za-z0-9%]', '', w))
    return '-'.join(x for x in out if x)


class Names:
    """name <-> id tables of one game (English names as the stack has them), case-insensitive"""

    def __init__(self, game):
        self.g = game
        self.species = {}           # lower name -> (monsno, form)
        self.show = {}              # (monsno, form) -> Showdown name
        for r in game.species_rows():
            m, f = game.key_of(r)
            sp = game.species_name(m)
            if f == 0:
                self.show[(m, 0)] = sp
                self.species.setdefault(sp.lower(), (m, 0))
                continue
            fname = game.form_name(m, f)
            suf = form_suffix(sp, fname)
            name = f'{sp}-{suf}' if suf else f'{sp}-{f}'
            self.show[(m, f)] = name
            self.species.setdefault(name.lower(), (m, f))
            self.species.setdefault(f'{sp} ({fname})'.lower(), (m, f))
        self.moves = _index([(m['wazaNo'], game.move_name(m['wazaNo'])) for m in game.moves if m['wazaNo']])
        self.items = _index([(i['no'], game.item_name(i['no'])) for i in game.items if i['no']])
        self.abilities = _index([(k, game.ability_name(k)) for k in range(1, game.ability_count())])
        self.natures = _index([(k, game.nature_name(k)) for k in range(game.nature_count())])

    def pokemon(self, text):
        return self.species.get(text.strip().lower())


def _index(pairs):
    out = {}
    for v, n in pairs:
        out.setdefault(n.lower(), v)
    return out


def export(game, slots, names=None):
    names = names or Names(game)
    blocks = []
    for s in slots:
        if not s.get('MonsNo'):
            continue
        key = (s['MonsNo'], s.get('FormNo', 0))
        name = names.show.get(key) or game.species_name(s['MonsNo'])
        line = name + {0: ' (M)', 1: ' (F)'}.get(s.get('Sex'), '')
        if s.get('Item'):
            line += f' @ {game.item_name(s["Item"])}'
        out = [line]
        if s.get('Level', 100) != 100:
            out.append(f'Level: {s["Level"]}')
        out.append(f'Ability: {game.ability_name(s.get("Tokusei", 0))}')
        if s.get('IsRare'):
            out.append('Shiny: Yes')
        evs = [f'{s.get(f, 0)} {t}' for f, t in zip(EFFORTS, STAT_TOKENS) if s.get(f, 0)]
        if evs:
            out.append('EVs: ' + ' / '.join(evs))
        out.append(f'{game.nature_name(s.get("Seikaku", 0))} Nature')
        ivs = [f'{s.get(f, 31)} {t}' for f, t in zip(TALENTS, STAT_TOKENS) if s.get(f, 31) != 31]
        if ivs:
            out.append('IVs: ' + ' / '.join(ivs))
        for k in (1, 2, 3, 4):
            if s.get(f'Waza{k}'):
                out.append(f'- {game.move_name(s[f"Waza{k}"])}')
        blocks.append('\n'.join(out))
    return '\n\n'.join(blocks) + ('\n' if blocks else '')


def _stats(text, into, fields):
    for part in text.split('/'):
        m = re.match(r'\s*(\d+)\s+(\w+)', part)
        if not m:
            raise ValueError(f'cannot read "{part.strip()}"')
        tok = m.group(2).lower()
        for f, t in zip(fields, STAT_TOKENS):
            if t.lower() == tok:
                into[f] = int(m.group(1))
                break
        else:
            raise ValueError(f'unknown stat "{m.group(2)}"')


def parse(game, text, base=None, names=None):
    """-> (slots, problems). base = the slots the party had (a parsed Pokemon starts from the slot it replaces for the
    fields Showdown text does not carry: ball, seal); every Showdown field gets Showdown's default when absent."""
    names = names or Names(game)
    problems = []
    slots = []
    blocks = [b for b in re.split(r'\n\s*\n', text.strip().replace('\r', '')) if b.strip()]
    for bi, block in enumerate(blocks):
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        old = (base[bi] if base and bi < len(base) else {}) or {}
        s = {'MonsNo': 0, 'FormNo': 0, 'IsRare': 0, 'Level': 100, 'Sex': 3, 'Seikaku': 0, 'Tokusei': 0, 'Item': 0,
             'Ball': old.get('Ball', 0), 'Seal': old.get('Seal', 0), 'Waza1': 0, 'Waza2': 0, 'Waza3': 0, 'Waza4': 0}
        s.update({f: 31 for f in TALENTS})
        s.update({f: 0 for f in EFFORTS})
        head = lines[0]
        item = None
        if '@' in head:
            head, item = head.split('@', 1)
        head = head.strip()
        sex = None
        m = re.search(r'\((M|F)\)\s*$', head)
        if m:
            sex = 0 if m.group(1) == 'M' else 1
            head = head[:m.start()].strip()
        nick = re.match(r'^.*\(([^()]+)\)$', head)
        key = names.pokemon(head) or (names.pokemon(nick.group(1)) if nick else None)
        if key is None:
            problems.append(f'Pokemon {bi + 1}: unknown species "{head}"')
            continue
        s['MonsNo'], s['FormNo'] = key
        row = game.row(*key)
        s['Sex'] = sex if sex is not None else (2 if row is not None and row['sex'] == 255 else 3)
        if item is not None:
            iv = names.items.get(item.strip().lower())
            if iv is None:
                problems.append(f'Pokemon {bi + 1}: unknown item "{item.strip()}"')
            else:
                s['Item'] = iv
        moves = []
        for l in lines[1:]:
            low = l.lower()
            try:
                if l.startswith('-'):
                    mv = l[1:].strip()
                    mid = 237 if mv.lower().startswith('hidden power') else names.moves.get(mv.lower())
                    if mid is None:
                        problems.append(f'Pokemon {bi + 1}: unknown move "{mv}"')
                    else:
                        moves.append(mid)
                elif low.startswith('ability:'):
                    a = names.abilities.get(l.split(':', 1)[1].strip().lower())
                    if a is None:
                        problems.append(f'Pokemon {bi + 1}: unknown ability "{l.split(":", 1)[1].strip()}"')
                    else:
                        s['Tokusei'] = a
                elif low.startswith('level:'):
                    s['Level'] = max(1, min(100, int(l.split(':', 1)[1])))
                elif low.startswith('shiny:'):
                    s['IsRare'] = 1 if 'yes' in low else 0
                elif low.startswith('evs:'):
                    _stats(l.split(':', 1)[1], s, EFFORTS)
                elif low.startswith('ivs:'):
                    _stats(l.split(':', 1)[1], s, TALENTS)
                elif low.endswith(' nature'):
                    n = names.natures.get(l.rsplit(' ', 1)[0].strip().lower())
                    if n is None:
                        problems.append(f'Pokemon {bi + 1}: unknown nature "{l}"')
                    else:
                        s['Seikaku'] = n
            except ValueError as e:
                problems.append(f'Pokemon {bi + 1}: {e}')
        if len(moves) > 4:
            problems.append(f'Pokemon {bi + 1}: more than 4 moves - the first 4 are kept')
        for k, mv in enumerate(moves[:4]):
            s[f'Waza{k + 1}'] = mv
        slots.append(s)
    return slots, problems
