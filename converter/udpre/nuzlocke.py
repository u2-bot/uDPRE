"""Nuzlocke mode: the settings the game reads (Dpr_Data/StreamingAssets/uDPRE/nuzlocke.txt) and the run it keeps.

The rules are enforced by the game player (its Nuzlocke.* code, which reads the file once at start). This module is the
other half of that contract: every key, its values and default, the presets, the file writer, and the reader of the run
file the game saves next to each save (SaveData.bin.nuzlocke: one record a line, fields split by TAB).
Rules: nuzlockeuniversity.ca (the Nuzlocke rules, the Hardcore variant and the optional rules list).
"""
import os
import re

FILE = 'Dpr_Data/StreamingAssets/uDPRE/nuzlocke.txt'
SUPPORT_TYPE = b'NzConfig'          # the player's global-metadata.dat names it when the player has this mode
RULES_URL = 'https://nuzlockeuniversity.ca/nuzlocke-rules/'
HARDCORE_URL = 'https://nuzlockeuniversity.ca/nuzlocke-variants/hardcore-nuzlocke-variant/'

TYPES = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug', 'Ghost', 'Steel', 'Fire', 'Water', 'Grass',
         'Electric', 'Psychic', 'Ice', 'Dragon', 'Dark', 'Fairy']
COLORS = ['Red', 'Blue', 'Yellow', 'Green', 'Black', 'Brown', 'Purple', 'Gray', 'White', 'Pink']
# setup / stat-boosting moves (the optional rule names Dragon Dance, Encore and Substitute as examples)
SETUP_MOVES = [14, 74, 96, 97, 104, 106, 107, 110, 111, 112, 116, 133, 151, 159, 164, 174, 187, 227, 268, 294, 322, 334, 336,
               339, 347, 349, 366, 397, 417, 455, 468, 475, 483, 489, 504, 508, 526, 538]

# (key, label, kind, choices or default, group, rule note). kind: bool / choice / int / list
SETTINGS = [
    ('enabled', 'Play the game as a Nuzlocke', 'bool', 0, 'Core rules', ''),
    ('permadeath', 'A Pokemon that faints is dead', 'choice', [('box', 'it goes to a box for good'), ('release', 'it is released')],
     'Core rules', 'rule 1'),
    ('graveyard_box', 'Put the dead in the last box, named "Graveyard"', 'bool', 1, 'Core rules', ''),
    ('first_encounter', 'Only the first wild Pokemon of each area may be caught', 'bool', 1, 'Core rules', 'rule 2'),
    ('area_mode', 'An area is', 'choice', [('place', 'a place name (all floors of Mt. Coronet = one area)'),
                                           ('zone', 'every single map')], 'Core rules', ''),
    ('nickname', 'Nicknames', 'choice', [('always', 'every Pokemon must get one'), ('ask', 'the game asks as usual'),
                                         ('off', 'as the game\'s option says')], 'Core rules', 'rule 3'),
    ('dupes', 'Dupes Clause', 'choice', [('line', 'an evolution line you own does not count - keep looking'),
                                         ('species', 'a species you own does not count'), ('off', 'off')], 'Clauses', ''),
    ('dupes_dead', 'Dead Pokemon count as owned (Dupes Clause)', 'bool', 1, 'Clauses', ''),
    ('shiny_clause', 'Shiny Clause: a shiny may always be caught and does not count', 'bool', 1, 'Clauses', ''),
    ('gifts', 'Gift Pokemon and eggs from people', 'choice', [('area', 'count as the area\'s encounter'),
                                                              ('free', 'are free (Gift Clause)'),
                                                              ('banned', 'are banned (go to a box, unusable)')], 'Clauses',
     'rules 15, 36'),
    ('trades', 'In-game trades', 'choice', [('gifts', 'follow the gift rule'), ('area', 'count as the area\'s encounter'),
                                            ('free', 'are free'), ('banned', 'are banned')], 'Clauses', ''),
    ('static', 'Special encounters (legendaries, Spiritomb, Drifloon...)', 'choice',
     [('area', 'count as the area\'s encounter'), ('free', 'are free (Static Clause)'), ('banned', 'may not be caught')],
     'Encounters', ''),
    ('roamers', 'Roaming Pokemon (Mesprit, Cresselia)', 'choice',
     [('area', 'count for the area you meet them in'), ('free', 'are free'), ('banned', 'may not be caught')],
     'Encounters', ''),
    ('honey', 'Honey trees', 'choice', [('area', 'count for their route'), ('own', 'each tree route is its own area'),
                                        ('free', 'are free')], 'Encounters', ''),
    ('underground', 'Grand Underground hideaways', 'choice',
     [('area', 'all of them are one area'), ('hideaway', 'each hideaway is its own area'), ('free', 'are free'),
      ('banned', 'may not be caught')], 'Encounters', ''),
    ('methods', 'Land, surfing and fishing', 'choice', [('shared', 'share the area\'s one encounter'),
                                                        ('separate', 'each get their own first encounter')],
     'Encounters', ''),
    ('escape_retry', 'A first encounter that escapes (flees, Roar, Teleport) may be retried', 'bool', 0, 'Encounters',
     'rule 43'),
    ('free_species', 'Lock-in species, catchable any time (dex numbers)', 'list', '', 'Encounters', 'rule 38'),
    ('battle_items', 'Items from the bag in battle', 'choice',
     [('any', 'allowed'), ('no_healing', 'no healing items'), ('one_healing', 'one healing item a battle'),
      ('balls_only', 'none except Poke Balls (Hardcore)')], 'Hardcore', 'Hardcore rule 1, rules 8, 9'),
    ('level_cap', 'Level cap (the next boss\'s highest level)', 'choice',
     [('off', 'off'), ('hard', 'on: no EXP or Rare Candy past the cap')], 'Hardcore', 'Hardcore rule 2, rule 3'),
    ('cap_offset', 'Levels above the boss\'s highest', 'int', 0, 'Hardcore', 'rule 44'),
    ('cap_boss_exceed', 'Passing the cap during a boss battle is allowed', 'bool', 1, 'Hardcore', 'Hardcore rule 2'),
    ('cap_box_over', 'Pokemon over the cap are boxed before a boss battle', 'bool', 0, 'Hardcore', 'Hardcore rule 2'),
    ('set_mode', 'Set battle style (no switch after a knock-out)', 'bool', 0, 'Hardcore', 'rule 7'),
    ('pokecenter', 'Pokemon Centers', 'choice', [('any', 'allowed'), ('once', 'each one heals once'),
                                                 ('none', 'never heal')], 'More rules', 'rules 1, 2'),
    ('team_size', 'Party no bigger than the next Gym Leader\'s team', 'bool', 0, 'More rules', 'rule 4'),
    ('gym_lock', 'No leaving a gym once its challenge started', 'bool', 0, 'More rules', 'rule 5'),
    ('shop_healing', 'Shops sell healing items', 'bool', 1, 'More rules', 'rule 10 (off = only items you find)'),
    ('banned_species', 'Banned Pokemon (dex numbers)', 'list', '', 'More rules', 'rules 12, 13'),
    ('starter', 'Starter', 'choice', [('keep', 'keep it'), ('retire', 'retire it after your first catch')],
     'More rules', 'rule 14'),
    ('banned_moves', 'Banned moves (move numbers)', 'list', '', 'More rules', 'rule 16'),
    ('tms', 'TMs', 'choice', [('allowed', 'allowed'), ('banned', 'banned (level-up moves only)')], 'More rules', 'rule 17'),
    ('held_items', 'Held items', 'choice', [('allowed', 'allowed'), ('banned', 'banned')], 'More rules', 'rule 20'),
    ('max_power', 'Highest move power allowed (0 = any)', 'int', 0, 'More rules', 'rule 21'),
    ('stab', 'Same-type (STAB) moves', 'choice', [('any', 'allowed'), ('no_stab', 'banned'),
                                                 ('only_stab', 'the only moves allowed')], 'More rules', 'rules 22, 23'),
    ('super_effective', 'Super-effective moves allowed', 'bool', 1, 'More rules', 'rule 24'),
    ('stages', 'Evolution stages', 'choice', [('any', 'any'), ('single', 'single-stage only'),
                                              ('nfe', 'not fully evolved only'),
                                              ('single_or_nfe', 'single-stage or not fully evolved')],
     'More rules', 'rule 25'),
    ('types_banned', 'Banned types', 'types', '', 'More rules', 'rule 26'),
    ('types_only', 'Only these types (Monolocke)', 'types', '', 'More rules', 'rule 27'),
    ('dual_types', 'Dual-type Pokemon', 'choice', [('any', 'allowed'), ('banned', 'banned'), ('only', 'the only ones allowed')],
     'More rules', 'rules 28, 29'),
    ('unique_types', 'No two party Pokemon share a type', 'bool', 0, 'More rules', 'rule 30'),
    ('box_retire', 'A Pokemon put in a box can never come back', 'bool', 0, 'More rules', 'rule 31'),
    ('encounter_order', 'Use Pokemon in the order caught', 'bool', 0, 'More rules', 'rule 32'),
    ('deathless', 'Deathless: the run ends when any Pokemon faints', 'bool', 0, 'More rules', 'rule 33'),
    ('revives', 'Revives (bring a dead Pokemon back)', 'int', 0, 'Easier', 'rule 34'),
    ('sacrifice', 'Release this many living Pokemon to earn a revive (0 = off)', 'int', 0, 'Easier', 'rule 35'),
    ('whiteout', 'When every party Pokemon faints', 'choice', [('end', 'the run is over'),
                                                              ('continue', 'go on with a new team from the box')],
     'Easier', 'rule 45'),
    ('perfect_ivs', 'Pokemon you get have perfect IVs', 'bool', 0, 'Easier', 'rule 40'),
    ('tm_reusable', 'TMs are not used up', 'bool', 0, 'Easier', 'rule 41'),
    ('master_balls', 'Every allowed ball catches', 'bool', 0, 'Easier', 'rule 42'),
    ('colors', 'Only Pokemon of these colours', 'colors', '', 'Variety', 'rule 48'),
    ('generations', 'Only Pokemon of these generations', 'gens', '', 'Variety', 'rule 50'),
    ('starter_by_tid', 'Starter by your Trainer ID\'s last digit (1-3 Grass, 4-6 Water, 7-9 Fire, 0 any)', 'bool', 0,
     'Variety', 'rule 52'),
]
GROUPS = ['Core rules', 'Clauses', 'Encounters', 'Hardcore', 'More rules', 'Easier', 'Variety']
# the number settings' ranges = the player's (NzConfig clamps to the same)
RANGES = {'cap_offset': (0, 99), 'max_power': (0, 999), 'revives': (0, 99), 'sacrifice': (0, 6)}
KEYS = [s[0] for s in SETTINGS]
SPEC = {s[0]: s for s in SETTINGS}

# rules a game cannot check (the window lists them); BDSP has no HM Pokemon to catch and no Raid Dens
HONOR = [
    ('rule 6', 'Completionist Clause: battle every optional trainer before the next gym'),
    ('rule 11', 'No turning back once you leave a route, area or city'),
    ('rule 18', 'Play blind (no online references)'),
    ('rule 19', 'No damage calculators'),
    ('rule 49', 'Pokemon that fit a theme of your choice'),
    ('rule 39', 'Egg / unreachable moves: the Editor can add them to a learnset'),
    ('rule 37', 'An extra catch for HMs: not needed in BDSP (Secret Moves use no party Pokemon)'),
    ('rule 51', 'Raid Dens: Sword / Shield and Scarlet / Violet only'),
]


def default(key):
    s = SPEC[key]
    if s[2] == 'choice':
        return s[3][0][0]
    return s[3]


def defaults():
    return {k: default(k) for k in KEYS}


PRESETS = {
    'nuzlocke': dict(defaults(), enabled=1),
    'hardcore': dict(defaults(), enabled=1, battle_items='balls_only', level_cap='hard', set_mode=1, cap_box_over=1),
    'off': dict(defaults(), enabled=0),
}
PRESET_NAMES = {'nuzlocke': 'Nuzlocke', 'hardcore': 'Hardcore Nuzlocke', 'off': 'Off'}


def path(root):
    return os.path.join(root, *FILE.split('/'))


def normalize(key, value):
    """-> the value as the file stores it, or raises ValueError"""
    if key not in SPEC:
        raise ValueError(f'unknown setting "{key}" (uDPRE.exe nuzlocke show lists them)')
    kind = SPEC[key][2]
    v = str(value).strip().lower()
    if kind == 'bool':
        if v in ('1', 'on', 'yes', 'true'):
            return 1
        if v in ('0', 'off', 'no', 'false'):
            return 0
        raise ValueError(f'{key}: write 1 or 0')
    if kind == 'choice':
        ok = [c for c, _ in SPEC[key][3]]
        if v not in ok:
            raise ValueError(f'{key}: one of {", ".join(ok)}')
        return v
    if kind == 'int':
        lo, hi = RANGES.get(key, (0, 999))
        if not re.fullmatch(r'\d{1,4}', v) or not lo <= int(v) <= hi:
            raise ValueError(f'{key}: a whole number from {lo} to {hi}')
        return int(v)
    nums = [n for n in re.split(r'[\s,;]+', v) if n]
    if not all(n.isdigit() for n in nums):
        raise ValueError(f'{key}: numbers split by commas')
    return ','.join(str(int(n)) for n in nums)


def read(root):
    """-> {key: value} (defaults for keys the file lacks; no file = defaults, enabled 0)"""
    out = defaults()
    try:
        with open(path(root), encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                k = k.strip().lower()
                if k in SPEC:
                    try:
                        out[k] = normalize(k, v)
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def write(root, values):
    vals = defaults()
    for k, v in values.items():
        vals[k] = normalize(k, v)
    p = path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    lines = ['# uDPRE Nuzlocke settings - written by uDPRE (window: Nuzlocke...; console: uDPRE.exe nuzlocke).',
             '# The game reads this file when it starts. Rules: ' + RULES_URL]
    group = None
    for k in KEYS:
        s = SPEC[k]
        if s[4] != group:
            group = s[4]
            lines.append(f'# --- {group}')
        lines.append(f'{k}={vals[k]}')
    tmp = p + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, p)
    return vals


def preset_of(values):
    """-> the preset name the values equal, else 'custom'"""
    for name, pv in PRESETS.items():
        if all(str(values.get(k)) == str(pv[k]) for k in KEYS):
            return name
    return 'custom' if int(values.get('enabled') or 0) else 'off'


def summary(values):
    if not int(values.get('enabled') or 0):
        return 'off'
    name = preset_of(values)
    return PRESET_NAMES.get(name, 'custom rules')


def player_supports(root):
    """-> True / False: the player in this folder has the Nuzlocke mode (None = no player found)"""
    meta = os.path.join(root, 'Dpr_Data', 'il2cpp_data', 'Metadata', 'global-metadata.dat')
    try:
        with open(meta, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return (b'\x00' + SUPPORT_TYPE + b'\x00') in data


# --- the run (the game's side file) --------------------------------------------------------------------------------

def save_dirs(root):
    """-> the save folders of this folder's game (LocalLow/<company>/<product>/nn/save/<app>/<user>), newest first"""
    try:
        with open(os.path.join(root, 'Dpr_Data', 'app.info'), encoding='utf-8') as f:
            company, product = (f.read().splitlines() + ['', ''])[:2]
    except OSError:
        return []
    base = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'AppData', 'LocalLow', company.strip(),
                        product.strip(), 'nn', 'save')
    out = []
    if os.path.isdir(base):
        for app in os.listdir(base):
            for user in os.listdir(os.path.join(base, app)) if os.path.isdir(os.path.join(base, app)) else []:
                d = os.path.join(base, app, user)
                if os.path.isfile(os.path.join(d, 'SaveData.bin')):
                    out.append(d)
    out.sort(key=lambda d: os.path.getmtime(os.path.join(d, 'SaveData.bin')), reverse=True)
    return out


def crc32(data):
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def parse_run(text, save_bytes=None):
    """-> dict of the run file (state, areas, deaths, ...); 'paired' False when it belongs to another save"""
    run = {'state': 'none', 'areas': [], 'deaths': [], 'owned': [], 'pc': [], 'messages': [], 'paired': None,
           'valid': False}
    lines = text.split('\n')
    end = [i for i, ln in enumerate(lines) if ln.startswith('end\t')]
    if not lines or not lines[0].startswith('NZLK\t') or not end:
        return run
    body = '\n'.join(lines[:end[-1]]) + '\n'
    run['valid'] = lines[end[-1]].split('\t')[1].strip() == f'{crc32(body.encode("utf-8")):08x}'
    for ln in lines[:end[-1]]:
        f = ln.split('\t')
        tag = f[0]
        if tag == 'save' and len(f) >= 3 and save_bytes is not None:
            run['paired'] = f[1] == f'{crc32(save_bytes):08x}' and int(f[2]) == len(save_bytes)
        elif tag == 'state':
            run['state'] = f[1]
        elif tag == 'info' and len(f) >= 7:
            run.update(start_badges=int(f[1]), revives_used=int(f[2]), revives_earned=int(f[3]),
                       sacrificed=int(f[4]), last_cap=int(f[5]))
        elif tag == 'area' and len(f) >= 7:
            run['areas'].append({'key': f[1], 'status': f[2], 'monsno': int(f[3]), 'form': int(f[4]), 'result': f[5],
                                 'name': f[6], 'species': f[7] if len(f) > 7 else ''})
        elif tag == 'death' and len(f) >= 7:
            run['deaths'].append({'monsno': int(f[1]), 'form': int(f[2]), 'level': int(f[3]), 'nick': f[4],
                                  'place': f[5], 'cause': f[6], 'species': f[7] if len(f) > 7 else ''})
        elif tag == 'owned':
            run['owned'].append(int(f[1]))
        elif tag == 'pc':
            run['pc'].append(int(f[1]))
        elif tag == 'msg':
            run['messages'].append(f[1])
    return run


def load_run(root):
    """-> (run dict, save folder) of the newest save of this folder's game, or (None, None)"""
    for d in save_dirs(root):
        side = os.path.join(d, 'SaveData.bin.nuzlocke')
        if not os.path.isfile(side):
            continue
        try:
            with open(side, encoding='utf-8') as f:
                text = f.read()
            with open(os.path.join(d, 'SaveData.bin'), 'rb') as f:
                save = f.read()
        except OSError:
            continue
        return parse_run(text, save), d
    return None, None


def run_text(run, species_name=None):
    """the run as plain lines (console / window)"""
    if run is None:
        return ['No Nuzlocke run saved yet (it starts in the game; it is saved with the game\'s save).']
    lines = []
    if run.get('paired') is False:
        lines.append('This run file belongs to an older save: the game starts a new run at its next save.')
    state = {'active': 'running', 'lost': 'LOST', 'won': 'WON', 'none': 'not started'}.get(run['state'], run['state'])
    caught = [a for a in run['areas'] if a['status'] == 'caught']
    used = [a for a in run['areas'] if a['status'] == 'used']
    lines.append(f'Run: {state} - {len(caught)} caught, {len(used)} areas used without a catch, '
                 f'{len(run["deaths"])} dead' +
                 (f', revives used {run.get("revives_used", 0)}' if run.get('revives_used') else ''))
    if run.get('last_cap', -1) > 0:
        lines.append(f'Level cap: Lv {run["last_cap"]}')
    def name(rec):
        return rec.get('species') or (species_name(rec['monsno']) if species_name else f'#{rec["monsno"]}')

    if run['areas']:
        lines.append('')
        lines.append('Areas:')
        for a in run['areas']:
            what = name(a) + (' (caught)' if a['status'] == 'caught' else f' ({a["result"]})')
            lines.append(f'  {a["name"] or a["key"]}: {what}')
    if run['deaths']:
        lines.append('')
        lines.append('Graveyard:')
        for d in run['deaths']:
            lines.append(f'  {d["nick"]} ({name(d)}, Lv {d["level"]}) - {d["place"]}, {d["cause"]}')
    return lines
