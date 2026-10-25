"""Randomizer: every randomizer option, built on the game's own code; one operation {"op": "randomize", "seed",
"settings"}.

run(game, settings, seed, context) is deterministic: one random.Random(seed), options run in a fixed order,
every loop walks the tables in their stored order. It edits the type trees in place through `game`; the type chart goes
through context.metadata_op, the BGM shuffle through the Delphis_Main.bnk bytes. Settings = {option id: value} +
'dist': {option id: distribution spec} (distributions.py) + 'bounds': {name: [min, max, increment]}; an enabled option
without its distribution / percentage uses the analyzer's default for the data as it is when the run starts.
Rules shared by the options:
  - numeric draws only touch a value inside its absolute boundary, and the result is conformed (rounded to the
    boundary's increment, half to even, then clamped);
  - every redraw loop (validity, BST Logic, type themes, type bias, legend acceptance) is capped at CAP tries; then a
    uniform pick among the candidates that satisfy the rule, else the value is kept;
  - only valid ids are produced (analyzer.Pools): valid species/forms (Luminescent: 514 of its 1,010 species rows),
    valid moves, active items (0 where a slot may be empty), named abilities, types < type count, natures < 25;
  - "Evolution Logic" moves a Pokemon to the stage that fits a level (wild / trainer expected evolution levels);
    "High Level Legends" accepts a legendary with probability level%.
Event scripts (Dpr/ev_script; Arg[0] = the command id, argType 1 = a float literal): Scripted Pokemon changes the
literal species of _ADD_POKEMON 218 [1], _ADD_TAMAGO 219 [1], _POKEMON_NAME_EXTRA 322 [2], _WILD_BTL_SET 401 [1],
_SP_WILD_BTL_SET 402 [1] (form [4] -> 0), _FIRST_BTL_SET 403 [1], _ADD_POKEMON_UI 1209 [1] (Luminescent form [6] -> 0),
and, when one of these reads its species from a work, the literal that _LDVAL 60 [2] / _LDVAL_VERSION 840 [1] [2]
loaded into that work earlier in the same script label (nothing else touching the work in between). One species
mapping per script file, so a file that shows a species' name and then gives it stays consistent. Scripted Items
changes the literal item of _FLD_ITEM_EVENT 187 [1] when it is a buyable item.
"""
import random
import struct

from . import analyzer
from . import distributions as dist
from .analyzer import GBA_LISTS, SLOT_LISTS, filled_slots, slot_count
from .game import EFFORTS, STATS, TALENTS

CAP = 200
BOUNDS = {          # name: [min, max, increment]
    'level': [1, 100, 1], 'base_stat': [1, 255, 1], 'catch_rate': [1, 255, 1], 'ev_yield': [0, 3, 1],
    'ev_yield_total': [1, 3, 1], 'friendship': [0, 250, 10], 'exp_yield': [1, 65535, 1], 'levelup_count': [1, 255, 1],
    'egg_count': [0, 255, 1], 'power': [5, 255, 5], 'accuracy': [5, 100, 5], 'pp': [5, 40, 5],
    'trainer_count': [1, 6, 1], 'iv': [0, 31, 1], 'ev': [0, 255, 1], 'ev_total': [0, 510, 1], 'price': [10, 999990, 10],
}
BOUND_LABELS = {'level': 'Level', 'base_stat': 'Base Stat', 'catch_rate': 'Catch Rate', 'ev_yield': 'EV Yield (per stat)',
                'ev_yield_total': 'EV Yield Total', 'friendship': 'Initial Friendship', 'exp_yield': 'EXP Yield',
                'levelup_count': 'Level Up Move Count', 'egg_count': 'Egg Move Count', 'power': 'Power',
                'accuracy': 'Accuracy', 'pp': 'PP', 'trainer_count': 'Trainer Pokemon Count', 'iv': 'IV',
                'ev': 'EV (per stat)', 'ev_total': 'EV Total', 'price': 'Price'}
MOVE_MODES = [('unchanged', 'Unchanged'), ('last', 'Last level-up moves'), ('random', 'Random')]
BGM_MODES = [('permutation', 'Permutation (every track used once)'), ('repeats', 'Random with repeats')]


def _o(tab, group, oid, label, kind, default=None, dist_kind=None, entities=None, parent=None, choices=None, help=''):
    d = {'id': oid, 'tab': tab, 'group': group, 'label': label, 'kind': kind, 'dist': dist_kind, 'entities': entities,
         'parent': parent, 'help': help}
    d['default'] = default if default is not None else {'check': False, 'percent': 0.0, 'number': 0}.get(kind)
    if choices is not None:
        d['choices'] = choices
    return d


PK, MI, EN, MS = 'Pokémon', 'Moves and Items', 'Encounters', 'Misc.'
OPTIONS = [
    # --- Pokemon tab
    _o(PK, 'Evolutions', 'evo_dest', 'Random destinations', 'check', dist_kind='items', entities='personal',
       help='Every species-changing evolution goes to another Pokemon.'),
    _o(PK, 'Evolutions', 'evo_dest_bst', 'BST Logic', 'check', parent='evo_dest',
       help='A new destination must have a higher base stat total than the Pokemon that evolves.'),
    _o(PK, 'Evolutions', 'evo_levels', 'Evolution levels', 'check', dist_kind='numeric',
       help='Redraws the level of every species-changing evolution.'),
    _o(PK, 'Base Stats', 'stats_shuffle', 'Shuffle', 'check', help='Shuffles the six base stats of every Pokemon.'),
    _o(PK, 'Base Stats', 'stats_random', 'Randomize', 'check', dist_kind='numeric', help='Redraws every base stat.'),
    _o(PK, 'Base Stats', 'stats_bst', 'BST Logic', 'check',
       help='Evolutions and superior forms keep a base stat total at least that of their previous stage.'),
    _o(PK, 'Typing', 'typing', 'Randomize typing', 'check', dist_kind='items', entities='types',
       help='Redraws the types of every Pokemon.'),
    _o(PK, 'Typing', 'typing_double', 'Double Typing %', 'percent', parent='typing',
       help='Chance that a Pokemon gets a second type.'),
    _o(PK, 'Typing', 'typing_evo', 'Evolution Logic', 'check', parent='typing',
       help='Evolutions derive their typing from their previous stage like the game does.'),
    _o(PK, 'TM Compatibility', 'tm_compat', 'Randomize TM compatibility', 'check',
       help='Redraws which TMs every Pokemon learns.'),
    _o(PK, 'TM Compatibility', 'tm_compat_pct', 'TM Compatibility %', 'percent', parent='tm_compat',
       help='Chance that a Pokemon learns a TM.'),
    _o(PK, 'TM Compatibility', 'tm_type_bias', 'Type Bias %', 'percent', parent='tm_compat',
       help='Chance that compatibility follows the TM move type instead.'),
    _o(PK, 'TM Compatibility', 'tm_evo', 'Evolution Logic', 'check', parent='tm_compat',
       help='Evolutions learn the TMs of their previous stage.'),
    _o(PK, 'Misc.', 'held_items', 'Wild held items', 'check', dist_kind='items', entities='items',
       help='Redraws the three wild held item slots.'),
    _o(PK, 'Misc.', 'growth', 'Growth rate', 'check', dist_kind='items', entities='growth',
       help='Redraws the growth rate, the same for a whole family.'),
    _o(PK, 'Misc.', 'abilities', 'Abilities', 'check', dist_kind='items', entities='abilities',
       help='Redraws the three abilities.'),
    _o(PK, 'Misc.', 'catch_rate', 'Catch rate', 'check', dist_kind='numeric', help='Redraws the catch rate.'),
    _o(PK, 'Misc.', 'friendship', 'Initial friendship', 'check', dist_kind='numeric',
       help='Redraws the base friendship.'),
    _o(PK, 'Misc.', 'ev_yield', 'EV yield', 'check', dist_kind='numeric',
       help='Redraws the total EV yield and spreads it over the stats.'),
    _o(PK, 'Misc.', 'exp_yield', 'EXP yield', 'check', dist_kind='numeric', help='Redraws the base experience yield.'),
    _o(PK, 'Egg Moves', 'egg_moves', 'Randomize egg moves', 'check', dist_kind='items', entities='moves',
       help='Redraws every egg move.'),
    _o(PK, 'Egg Moves', 'egg_type_bias', 'Type Bias %', 'percent', parent='egg_moves',
       help='Chance that an egg move must share a type with the Pokemon.'),
    _o(PK, 'Egg Moves', 'egg_count', 'Move count', 'check', dist_kind='numeric', help='Redraws how many egg moves.'),
    _o(PK, 'Level Up Moves', 'levelup_moves', 'Randomize level-up moves', 'check', dist_kind='items',
       entities='moves', help='Redraws every level-up move; the level-1 move is always an attack.'),
    _o(PK, 'Level Up Moves', 'levelup_type_bias', 'Type Bias %', 'percent', parent='levelup_moves',
       help='Chance that a level-up move must share a type with the Pokemon.'),
    _o(PK, 'Level Up Moves', 'levelup_levels', 'Learn levels', 'check', dist_kind='numeric',
       help='Redraws the learn levels (evolved Pokemon also get moves on evolution).'),
    _o(PK, 'Level Up Moves', 'levelup_count', 'Move count', 'check', dist_kind='numeric',
       help='Redraws how many level-up moves.'),
    _o(PK, 'Level Up Moves', 'levelup_sort', 'Sort By Power', 'check',
       help='Weaker attacks are learned before stronger ones.'),
    # --- Moves and Items tab
    _o(MI, 'Moves', 'move_type', 'Move typing', 'check', dist_kind='items', entities='types',
       help='Redraws the type of every move.'),
    _o(MI, 'Moves', 'move_category', 'Damage category', 'check', dist_kind='items', entities='damage_category',
       help='Redraws Physical / Special of every damaging move (status moves stay).'),
    _o(MI, 'Moves', 'tm_moves', 'TM moves', 'check', dist_kind='items', entities='moves',
       help='Redraws the move of every TM.'),
    _o(MI, 'Moves', 'move_power', 'Power', 'check', dist_kind='numeric', help='Redraws the power of every move.'),
    _o(MI, 'Moves', 'move_accuracy', 'Accuracy', 'check', dist_kind='numeric', help='Redraws the accuracy.'),
    _o(MI, 'Moves', 'move_pp', 'PP', 'check', dist_kind='numeric', help='Redraws the PP.'),
    _o(MI, 'Items', 'item_prices', 'Item prices', 'check', dist_kind='numeric', help='Redraws every item price.'),
    _o(MI, 'Items', 'pickup_items', 'Pickup items', 'check', dist_kind='items', entities='items',
       help='Redraws the items the Pickup ability finds.'),
    _o(MI, 'Items', 'shop_items', 'Shop items', 'check', dist_kind='items', entities='items',
       help='Redraws what the shops sell.'),
    _o(MI, 'Items', 'shop_preserve_mart', 'Preserve Regular Mart', 'check', parent='shop_items',
       help='Keeps the Poke Mart stock (badge progression) as it is.'),
    # --- Encounters tab
    _o(EN, 'Wild Encounters', 'wild_species', 'Random Pokemon', 'check', dist_kind='items', entities='species',
       help='Redraws wild, honey tree, Great Marsh, Trophy Garden and Underground Pokemon.'),
    _o(EN, 'Wild Encounters', 'wild_levels', 'Levels', 'check', dist_kind='numeric',
       help='Redraws wild and Underground levels.'),
    _o(EN, 'Wild Encounters', 'wild_evo', 'Evolution Logic', 'check',
       help='Wild Pokemon are the stage that fits their level.'),
    _o(EN, 'Wild Encounters', 'wild_legends', 'High Level Legends', 'check',
       help='A legendary is accepted with a chance equal to its level in percent.'),
    _o(EN, 'Trainers', 'trainer_items', 'Random items', 'check', dist_kind='items', entities='items',
       help='Redraws the items trainers use (and lets every trainer use items).'),
    _o(EN, 'Trainers', 'trainer_item_count', 'Item count', 'check', dist_kind='numeric',
       help='Redraws how many items trainers carry (0 to 4).'),
    _o(EN, 'Trainers', 'trainer_count', 'Pokemon count', 'check', dist_kind='numeric',
       help='Redraws the party size (double battles keep at least two).'),
    _o(EN, 'Trainers', 'trainer_levels', 'Levels', 'check', dist_kind='numeric', help='Redraws party levels.'),
    _o(EN, 'Trainers', 'trainer_species', 'Random Pokemon', 'check', dist_kind='items', entities='species',
       help='Redraws the species of every party member.'),
    _o(EN, 'Trainers', 'trainer_evo', 'Evolution Logic', 'check', parent='trainer_species',
       help='Party Pokemon are the stage that fits their level.'),
    _o(EN, 'Trainers', 'trainer_themes', 'Type Themes', 'check', parent='trainer_species',
       help='Gym Leaders and the Elite Four keep their type.'),
    _o(EN, 'Trainers', 'trainer_legends', 'High Level Legends', 'check', parent='trainer_species',
       help='A legendary is accepted with a chance equal to its level in percent.'),
    _o(EN, 'Trainers', 'trainer_held', 'Held items', 'check', dist_kind='items', entities='items',
       help='Redraws the held items of party Pokemon.'),
    _o(EN, 'Trainers', 'trainer_held_high', 'High Level Held Items', 'check', parent='trainer_held',
       help='A held item is redrawn with a chance equal to the level in percent.'),
    _o(EN, 'Trainers', 'trainer_natures', 'Natures', 'check', dist_kind='items', entities='natures',
       help='Redraws the natures.'),
    _o(EN, 'Trainers', 'trainer_moves', 'Moves', 'choice', default='unchanged', dist_kind='items', entities='moves',
       choices=MOVE_MODES, help='Unchanged, the last four level-up moves, or random moves.'),
    _o(EN, 'Trainers', 'trainer_move_bias', 'Type Bias %', 'percent', parent='trainer_moves',
       help='Chance that a random move must share a type with the Pokemon.'),
    _o(EN, 'Trainers', 'trainer_shiny', 'Random Shinies', 'check', help='Redraws which party Pokemon are shiny.'),
    _o(EN, 'Trainers', 'trainer_shiny_pct', 'Shiny %', 'percent', parent='trainer_shiny',
       help='Chance that a party Pokemon is shiny.'),
    _o(EN, 'Trainers', 'trainer_abilities', 'Abilities', 'check', dist_kind='items', entities='abilities',
       help='One of the Pokemon\'s own three abilities (or any ability with Include Unobtainable).'),
    _o(EN, 'Trainers', 'trainer_abilities_any', 'Include Unobtainable', 'check', parent='trainer_abilities',
       help='Draws from the ability distribution instead of the Pokemon\'s own abilities.'),
    _o(EN, 'Trainers', 'trainer_ivs', 'IVs', 'check', dist_kind='numeric', help='Redraws the IVs.'),
    _o(EN, 'Trainers', 'trainer_evs', 'EVs', 'check', dist_kind='numeric',
       help='Redraws the EV total and spreads it over the stats.'),
    # --- Misc tab
    _o(MS, 'Level Multiplier', 'level_coef', 'Level Coefficient', 'number', default=1.0,
       help='Multiplies the levels of the checked targets before any randomization.'),
    _o(MS, 'Level Multiplier', 'level_evo', 'Evolution levels', 'check', parent='level_coef',
       help='Scales evolution levels.'),
    _o(MS, 'Level Multiplier', 'level_moves', 'Level-up moves', 'check', parent='level_coef',
       help='Scales learn levels.'),
    _o(MS, 'Level Multiplier', 'level_wild', 'Wild encounters', 'check', parent='level_coef',
       help='Scales wild and Underground levels.'),
    _o(MS, 'Level Multiplier', 'level_trainer', 'Trainer Pokemon', 'check', parent='level_coef',
       help='Scales trainer party levels.'),
    _o(MS, 'Type Matchups', 'type_matchups', 'Random matchups', 'check', dist_kind='items', entities='type_matchup',
       help='Redraws the type chart (in the player\'s metadata).'),
    _o(MS, 'Scripts', 'script_species', 'Scripted Pokemon', 'check', dist_kind='items', entities='species',
       help='Redraws gift, egg and static-encounter Pokemon of the event scripts (and the names they show).'),
    _o(MS, 'Scripts', 'script_legends', 'High Level Legends', 'check', parent='script_species',
       help='A legendary is accepted with a chance equal to the event\'s level in percent.'),
    _o(MS, 'Scripts', 'script_items', 'Scripted items', 'check', dist_kind='items', entities='items',
       help='Redraws the items of the item balls on the field.'),
    _o(MS, 'Text', 'shuffle_text', 'Shuffle Text', 'check', help='Shuffles every message without placeholders.'),
    _o(MS, 'Text', 'shuffle_text_len', 'Preserve String Length', 'check', parent='shuffle_text',
       help='Only swaps messages of a similar length.'),
    _o(MS, 'Audio', 'shuffle_bgm', 'Shuffle BGM', 'check', help='Shuffles the battle, contest, event and field music.'),
    _o(MS, 'Audio', 'shuffle_bgm_mode', 'Mode', 'choice', default='permutation', parent='shuffle_bgm',
       choices=BGM_MODES, help='Permutation uses every track exactly once.'),
    _o(MS, 'Absolute Boundaries', 'bounds', 'Absolute Boundaries', 'bounds',
       default={k: list(v) for k, v in BOUNDS.items()},
       help='Values outside a boundary are never changed; results are rounded to its increment and clamped.'),
]
OPTION = {o['id']: o for o in OPTIONS}

# trainer type label -> theme type (Sinnoh gym leaders / Elite Four, checked against TrainerTable.TrainerType)
THEMES = {'TR_LEADER1': 5, 'TR_LEADER2': 11, 'TR_LEADER3': 10, 'TR_LEADER4': 1, 'TR_LEADER5': 7, 'TR_LEADER6': 14,
          'TR_LEADER7': 8, 'TR_LEADER8': 12, 'TR_BIGFOUR1': 6, 'TR_BIGFOUR2': 4, 'TR_BIGFOUR3': 9, 'TR_BIGFOUR4': 13}
# Wwise ids (FNV-1 of the names) of the BGM State/Switch groups and of the silent branches the shuffle keeps
BGM_GROUPS = {2944413750, 3369806648, 1799075776, 3346466364}   # BGM_BATTLE, BGM_CONTEST, BGM_EVENT, BGM_FIELD
BGM_SKIP = {0, 748895195, 1454758594, 595984104, 4176813980, 3652652993, 789285764, 191715830, 2460189219, 1302076938}
BANK = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch/Delphis_Main.bnk'
EVSCRIPT = 'Dpr/ev_script'
SPECIES_ARGS = {218: (1,), 219: (1,), 322: (2,), 401: (1,), 402: (1,), 403: (1,), 1209: (1,)}
FORM_ARG = {402: 4, 1209: 6}
LEVEL_ARG = {218: 2, 401: 2, 402: 2, 403: 2, 1209: 2}
EGG_CMD = 219
LDVAL, LDVAL_VERSION, SCWK_TEMP0 = 60, 840, 238
ITEM_BALL = 187
ARG_FLOAT, ARG_WORK = 1, 2
USE_ITEMS = ['UseItem1', 'UseItem2', 'UseItem3', 'UseItem4']


def entities(game, name):
    """-> [(value, label)] of an entity list (item-distribution dialogs)"""
    return analyzer.entities(game, name)


def fbits(v):
    return struct.unpack('<i', struct.pack('<f', float(v)))[0]


def ffrom(d):
    return struct.unpack('<f', struct.pack('<i', d))[0]


class Run:
    def __init__(self, game, settings, seed, context, log):
        self.g = game
        self.s = settings or {}
        self.ctx = context
        self.log = log
        self.rng = random.Random(seed if isinstance(seed, (int, str)) else str(seed))
        self.pools = analyzer.Pools(game)
        self.warnings = []
        self._defaults = None
        self._samplers = {}
        b = dict(BOUNDS)
        for k, v in (self.s.get('bounds') or {}).items():
            if k in b and isinstance(v, (list, tuple)) and len(v) == 3:
                b[k] = [v[0], v[1], v[2] or 1]
        self.bounds = b
        # hidden distributions, measured before anything changes
        self.correlation = self._typing_correlation()
        self.evo_move_count = self._evo_move_count()

    # --- settings ---------------------------------------------------------------------------------------------------
    def defaults(self):
        if self._defaults is None:
            self._defaults = analyzer.default_settings(self.g, self.ctx)
        return self._defaults

    def on(self, oid):
        v = self.s.get(oid)
        return bool(v) and v != 'unchanged'

    def value(self, oid):
        if oid in self.s and self.s[oid] is not None:
            return self.s[oid]
        o = OPTION[oid]
        if o['kind'] == 'percent':
            return self.defaults().get(oid, 0.0)
        return o['default']

    def spec(self, oid):
        d = (self.s.get('dist') or {}).get(oid)
        return d if isinstance(d, dict) and d.get('type') else self.defaults()['dist'][oid]

    def num(self, oid):
        if oid not in self._samplers:
            self._samplers[oid] = dist.Numeric(self.spec(oid))
        return self._samplers[oid]

    def choice(self, oid, allowed):
        """the option's item distribution restricted to `allowed` (each option always passes the same pool)"""
        key = ('choice', oid)
        if key not in self._samplers:
            self._samplers[key] = dist.Choice(self.spec(oid), allowed)
        return self._samplers[key]

    def pct(self, oid):
        try:
            return float(self.value(oid))
        except (TypeError, ValueError):
            return 0.0

    def chance(self, percent):
        return self.rng.random() * 100.0 < percent

    # --- boundaries -------------------------------------------------------------------------------------------------
    def within(self, v, name):
        b = self.bounds[name]
        return b[0] <= v <= b[1]

    def conform(self, v, name):
        mn, mx, inc = self.bounds[name]
        v = round(v / inc) * inc
        return int(max(mn, min(mx, v)))

    def redraw(self, oid, v, name):
        """Next(v) conformed, for a value inside boundary `name` (else v)"""
        if not self.within(v, name):
            return v
        return self.conform(self.num(oid).draw(self.rng, v), name)

    # --- shared helpers ---------------------------------------------------------------------------------------------
    def row(self, pid):
        return self.pools.rows.get(pid)

    def find_stage(self, row, level, mode):
        """mode 0 wild, 1 trainer -> the row of the stage that fits `level`"""
        P = self.pools
        pid = row['id']
        for _ in range(16):
            prev, nxt = P.prev.get(pid), P.next.get(pid)
            if prev and P.past_lv.get(pid, (0, 0))[mode] > level:
                pid = self.rng.choice(prev)
            elif nxt and P.next_lv.get(pid, (analyzer.NEVER,) * 2)[mode] <= level:
                pid = self.rng.choice(nxt)
            else:
                break
        return self.row(pid)

    def legend_ok(self, monsno, level, rule):
        return not rule or not self.pools.is_legend(monsno) or self.chance(level)

    def pick_pokemon(self, oid, cur_dex, level, mode, evo, legends, any_form, theme=None):
        """the species redraw of wild slots / trainer slots: -> a valid personal row, or None (keep the slot)"""
        P = self.pools
        ch = self.choice(oid, P.valid_species_set)
        g = self.g
        for _ in range(CAP):
            dex = ch.draw(self.rng, cur_dex)
            if dex not in P.valid_species_set:
                continue
            r = g.row(dex, self.rng.randrange(P.form_count[dex])) if any_form else P.rows[dex]
            if not P.valid_row(r):
                continue
            if evo:
                r = self.find_stage(r, level, mode)
                if not P.valid_row(r):
                    continue
            if theme is not None and theme not in P.types_of(r):
                continue
            if not self.legend_ok(r['monsno'], level, legends):
                continue
            return r
        if theme is not None:       # no draw of the distribution has the theme: any valid Pokemon of that type
            cands = [P.rows[p] for p in P.valid_pids if theme in P.types_of(P.rows[p])
                     and (any_form or P.rows[p]['id'] == P.rows[p]['monsno'])
                     and (not legends or not P.is_legend(P.rows[p]['monsno']))]
            if cands:
                return self.rng.choice(cands)
        return None

    def biased_move(self, oid, cur, types, bias, exclude=()):
        """Next(move); with P(bias) redrawn until its type is one of `types`"""
        P = self.pools
        ch = self.choice(oid, P.valid_move_set)
        want = self.chance(bias)
        for _ in range(CAP):
            m = ch.draw(self.rng, cur)
            if m not in P.valid_move_set or m in exclude:
                continue
            if not want or P.move_type(m) in types:
                return m
        cands = [m for m in ch.support() if m not in exclude and (not want or P.move_type(m) in types)]
        if cands:
            return self.rng.choice(cands)
        return cur if cur in P.valid_move_set else (ch.support() or [cur])[0]

    def split(self, total, cap, n=6):
        """a random split of total over n stats, each <= cap"""
        total = max(0, min(total, n * cap))
        vals = [0] * n
        while total > 0:
            k = self.rng.choice([i for i in range(n) if vals[i] < cap])
            c = self.rng.randint(1, min(cap - vals[k], total))
            vals[k] += c
            total -= c
        return vals

    def note(self, text):
        self.log(f'randomizer: {text}')

    # --- hidden distributions ---------------------------------------------------------------------------------------
    def _typing_correlation(self):
        """counts of the four relations between a pre-evolution's and its evolution's typing"""
        P = self.pools
        c = {'same': 0, 'add': 0, 'swap': 0, 'none': 0}
        for pid, ns in P.next.items():
            a = P.types_of(P.rows[pid])
            for d in ns:
                b = P.types_of(P.rows[d])
                shared = len(a & b)
                if a == b:
                    c['same'] += 1
                elif len(a) != len(b) and shared == 1:
                    c['add'] += 1
                elif len(a) == len(b) and (shared == 1 or len(a) == 1):
                    c['swap'] += 1
                else:
                    c['none'] += 1
        return c

    def _evo_move_count(self):
        P, g = self.pools, self.g
        obs = []
        for pid in P.valid_pids:
            if P.prev.get(pid):
                obs.append(sum(1 for lv, _m in g.learnset(P.rows[pid]) if lv == 0))
        _mn, _mx, _mid, mean, std = dist.stats(obs)
        return dist.Numeric(dist.numeric('NC', mean=mean, std=std))


# =====================================================================================================================
# 4.2 Level multiplier
def level_multiplier(R):
    g = R.g
    c = float(R.value('level_coef') or 1.0)

    def scale(v):
        return R.conform(int(v * c), 'level') if R.within(v, 'level') else v

    if R.on('level_evo'):
        for row in g.evolutions:
            ar = row['ar']
            for i in range(4, len(ar), 5):
                ar[i] = scale(ar[i])
        R.pools.family()
    if R.on('level_moves'):
        for row in g.learnsets:
            ar = row['ar']
            for i in range(0, len(ar) - 1, 2):
                ar[i] = scale(ar[i])
    if R.on('level_wild'):
        for _v, e in g.encounter_files():
            for z in e['table']:
                for k in SLOT_LISTS:
                    for s in z.get(k, []):
                        if R.within((s['minlv'] + s['maxlv']) / 2, 'level'):
                            lo, hi = R.conform(int(s['minlv'] * c), 'level'), R.conform(int(s['maxlv'] * c), 'level')
                            s['minlv'], s['maxlv'] = min(lo, hi), max(lo, hi)
        for r in ug_levels(g):
            if R.within((r['MinLv'] + r['MaxLv']) / 2, 'level'):
                lo, hi = R.conform(int(r['MinLv'] * c), 'level'), R.conform(int(r['MaxLv'] * c), 'level')
                r['MinLv'], r['MaxLv'] = min(lo, hi), max(lo, hi)
    if R.on('level_trainer'):
        for prow in g.trainer_pokes:
            for p in filled_slots(prow):
                prow[p + 'Level'] = scale(prow[p + 'Level'])


def ug_levels(g):
    return g.ug_table('UgEncountLevel')['Data'] if g.has_table('UnderGround/data/ugdata', 'UgEncountLevel') else []


# 4.3 Moves
def moves(R):
    g, P = R.g, R.pools
    if R.on('move_type'):
        ch = R.choice('move_type', set(P.types))
        for m in g.moves:
            m['type'] = ch.draw(R.rng, m['type'])
    if R.on('move_category'):
        ch = R.choice('move_category', {1, 2})
        for m in g.moves:
            if m['damageType'] != 0:
                m['damageType'] = ch.draw(R.rng, m['damageType'])
    if R.on('tm_moves'):
        ch = R.choice('tm_moves', P.valid_move_set)
        for t in g.tms:
            t['wazaNo'] = ch.draw(R.rng, t['wazaNo'])
    for oid, f, b in (('move_power', 'power', 'power'), ('move_accuracy', 'hitPer', 'accuracy'), ('move_pp', 'basePP', 'pp')):
        if R.on(oid):
            for m in g.moves:
                m[f] = R.redraw(oid, m[f], b)


# 4.4 Items
def items(R):
    g, P = R.g, R.pools
    if R.on('item_prices'):
        for it in g.items:
            it['price'] = R.redraw('item_prices', it['price'], 'price')
    if R.on('pickup_items'):
        ch = R.choice('pickup_items', P.active_item_set)
        for row in g.pickup:
            row['ID'] = ch.draw(R.rng, row['ID'])
    if R.on('shop_items'):
        ch = R.choice('shop_items', P.active_item_set)
        shops = g.shops
        lists = ['FixedShop', 'BPShop'] + ([] if R.on('shop_preserve_mart') else ['FS'])
        for name in ('FS', 'FixedShop', 'BPShop'):
            if name in lists:
                for row in shops.get(name, []):
                    row['ItemNo'] = ch.draw(R.rng, row['ItemNo'])


# 4.5 Evolutions
def evolutions(R):
    g, P = R.g, R.pools
    if R.on('evo_dest'):
        ch = R.choice('evo_dest', P.valid_pid_set)
        bst_logic = R.on('evo_dest_bst')
        for row in g.personal:
            if row['id'] <= 0:
                continue
            evos = g.evolution_list(row)
            out = []
            for m, param, dm, df, lvl in evos:
                if dm <= 0 or dm == row['monsno']:
                    out.append((m, param, dm, df, lvl))
                    continue
                cur = g.row(dm, df)
                cur_pid = cur['id'] if cur is not None else -1
                src_bst = g.bst(row)

                def ok(r):
                    return P.valid_row(r) and r['monsno'] != row['monsno'] and (not bst_logic or g.bst(r) > src_bst)
                new = None
                for _ in range(CAP):
                    r = P.rows.get(ch.draw(R.rng, cur_pid))
                    if ok(r):
                        new = r
                        break
                if new is None:
                    cands = [P.rows[p] for p in ch.support() if ok(P.rows.get(p))]
                    new = R.rng.choice(cands) if cands else None
                if new is None:
                    out.append((m, param, dm, df, lvl))
                else:
                    out.append((m, param, new['monsno'], g.form_of(new), lvl))
            if out != evos:
                g.set_evolution_list(row, out)
        P.family()
    if R.on('evo_levels'):
        for row in g.personal:
            evos = g.evolution_list(row)
            out = [(m, pa, dm, df, R.redraw('evo_levels', lvl, 'level') if dm > 0 and dm != row['monsno'] else lvl)
                   for m, pa, dm, df, lvl in evos]
            if out != evos:
                g.set_evolution_list(row, out)
        P.family()


# 4.6 Base stats
def base_stats(R):
    g, P = R.g, R.pools
    shuffle, rand = R.on('stats_shuffle'), R.on('stats_random')
    if shuffle or rand:
        for pid in P.valid_pids:
            row = P.rows[pid]
            vals = [row[s] for s in STATS]
            if shuffle:
                R.rng.shuffle(vals)
            if rand:
                vals = [R.redraw('stats_random', v, 'base_stat') for v in vals]
            for s, v in zip(STATS, vals):
                row[s] = v
    if R.on('stats_bst'):
        bst_logic(R)


def bst_logic(R):
    """every stage / superior form keeps BST >= its lower relatives: repaired by swapping stats between the pair"""
    g, P = R.g, R.pools

    def higher(pid):
        return P.next.get(pid, []) + P.superior.get(pid, [])

    def lower(pid):
        return P.prev.get(pid, []) + P.inferior.get(pid, [])

    def repair(lo, hi):
        a, b = P.rows[lo], P.rows[hi]
        n = 0
        while g.bst(a) > g.bst(b) and n < 12:
            k = max(range(6), key=lambda i: a[STATS[i]] - b[STATS[i]])
            if a[STATS[k]] - b[STATS[k]] <= 0:
                break
            a[STATS[k]], b[STATS[k]] = b[STATS[k]], a[STATS[k]]
            n += 1
        return n > 0

    work = list(P.valid_pids)
    budget = 50 * len(work) + 100
    while work and budget > 0:
        budget -= 1
        pid = work.pop(0)
        for h in higher(pid):
            if g.bst(P.rows[pid]) > g.bst(P.rows[h]) and repair(pid, h):
                work += [pid, h] + lower(pid)
        for lo in lower(pid):
            if g.bst(P.rows[lo]) > g.bst(P.rows[pid]) and repair(lo, pid):
                work += [lo, pid] + higher(pid)


# 4.7 Typing
def typing(R):
    if not R.on('typing'):
        return
    g, P = R.g, R.pools
    ch = R.choice('typing', set(P.types))
    dbl = R.pct('typing_double')

    def fresh(row):
        t1 = ch.draw(R.rng, row['type1'])
        t2 = ch.draw(R.rng, row['type2']) if R.chance(dbl) else t1
        return t1, t2

    def new_type(old, present):
        for _ in range(CAP):
            t = ch.draw(R.rng, old)
            if t not in present:
                return t
        cands = [t for t in ch.support() if t not in present] or [t for t in P.types if t not in present]
        return R.rng.choice(cands)

    if not R.on('typing_evo'):
        for pid in P.valid_pids:
            r = P.rows[pid]
            r['type1'], r['type2'] = fresh(r)
        return
    corr = dist.Choice(dist.empirical({0: R.correlation['same'], 1: R.correlation['add'], 2: R.correlation['swap'],
                                       3: R.correlation['none']}))
    done = {}

    def derive(pid, seen):
        if pid in done:
            return done[pid]
        r = P.rows[pid]
        prev = [q for q in P.prev.get(pid, []) if q not in seen]
        if not prev:
            t = fresh(r)
        else:
            base = derive(R.rng.choice(prev), seen | {pid})
            kind = corr.pick(R.rng)
            kind = 0 if kind is None else kind
            a, b = base
            if kind == 0:
                t = base
            elif kind == 1:
                if a == b:
                    t = (a, new_type(r['type2'], {a}))
                else:
                    t = (a, a) if R.rng.random() < 0.5 else (b, b)
            elif kind == 2:
                if a == b:
                    n = new_type(r['type1'], {a})
                    t = (n, n)
                elif R.rng.random() < 0.5:
                    t = (new_type(r['type1'], {a, b}), b)
                else:
                    t = (a, new_type(r['type2'], {a, b}))
            else:
                t = fresh(r)
        done[pid] = t
        return t

    for pid in P.valid_pids:
        derive(pid, set())
    for pid in P.valid_pids:
        P.rows[pid]['type1'], P.rows[pid]['type2'] = done[pid]


# 4.8 TM compatibility
def tm_compat(R):
    if not R.on('tm_compat'):
        return
    g, P = R.g, R.pools
    pct, bias = R.pct('tm_compat_pct'), R.pct('tm_type_bias')
    valid = {bit: P.move_type(t['wazaNo']) for bit, t, _it in P.tms}
    done = {}

    def roll(row):
        ts = P.types_of(row)
        bits = [0] * P.tm_bit_count
        for bit in range(P.tm_bit_count):
            if bit in valid:
                bits[bit] = int(valid[bit] in ts) if R.chance(bias) else int(R.chance(pct))
        return bits

    def derive(pid, seen):
        if pid in done:
            return done[pid]
        prev = [q for q in P.prev.get(pid, []) if q not in seen]
        bits = derive(R.rng.choice(prev), seen | {pid}) if prev else roll(P.rows[pid])
        done[pid] = bits
        return bits

    evo = R.on('tm_evo')
    for pid in P.valid_pids:
        if evo:
            derive(pid, set())
        else:
            done[pid] = roll(P.rows[pid])
    for pid in P.valid_pids:
        g.set_tm_bits(P.rows[pid], done[pid])


# 4.9 other personal fields
def personal_misc(R):
    g, P = R.g, R.pools
    if R.on('held_items'):
        ch = R.choice('held_items', P.held_item_set)
        for pid in P.valid_pids:
            r = P.rows[pid]
            for f in ('item1', 'item2', 'item3'):
                r[f] = ch.draw(R.rng, r[f])
    if R.on('growth'):
        ch = R.choice('growth', set(P.growth))
        done = set()
        for m in P.valid_species:
            forms = [r for r in P.species_forms[m] if P.valid_row(r)]
            if not forms or any(q for r in forms for q in P.prev.get(r['id'], []) if P.rows[q]['monsno'] != m):
                continue
            gr = ch.draw(R.rng, R.rng.choice(forms)['grow'])
            todo, seen = [m], set()
            while todo:
                s = todo.pop(0)
                if s in seen:
                    continue
                seen.add(s)
                for r in P.species_forms.get(s, []):
                    if P.valid_row(r):
                        r['grow'] = gr
                        todo += [P.rows[d]['monsno'] for d in P.next.get(r['id'], [])]
            done |= seen
    if R.on('abilities'):
        ch = R.choice('abilities', P.valid_ability_set)
        for pid in P.valid_pids:
            r = P.rows[pid]
            for f in ('tokusei1', 'tokusei2', 'tokusei3'):
                r[f] = ch.draw(R.rng, r[f])
    for oid, f, b in (('catch_rate', 'get_rate', 'catch_rate'), ('friendship', 'initial_friendship', 'friendship'),
                      ('exp_yield', 'give_exp', 'exp_yield')):
        if R.on(oid):
            for pid in P.valid_pids:
                P.rows[pid][f] = R.redraw(oid, P.rows[pid][f], b)
    if R.on('ev_yield'):
        cap = R.bounds['ev_yield'][1]
        for pid in P.valid_pids:
            r = P.rows[pid]
            w = r['exp_value']
            tot = sum((w >> (2 * k)) & 3 for k in range(6))
            tot = R.redraw('ev_yield', tot, 'ev_yield_total')
            vals = R.split(tot, min(3, cap))
            r['exp_value'] = (w & ~0xfff) | sum(v << (2 * k) for k, v in enumerate(vals))


# 4.10 egg moves
def egg_moves(R):
    moves_on, count_on = R.on('egg_moves'), R.on('egg_count')
    if not (moves_on or count_on):
        return
    g, P = R.g, R.pools
    ch = R.choice('egg_moves', P.valid_move_set)
    bias = R.pct('egg_type_bias')
    for pid in P.valid_pids:
        r = P.rows[pid]
        er = P.egg_index.get(g.key_of(r))
        if er is None:
            continue
        ws = list(er['wazaNo'])
        if count_on and R.within(len(ws), 'egg_count'):
            n = R.conform(R.num('egg_count').draw(R.rng, len(ws)), 'egg_count')
            while len(ws) < n:
                if ws:
                    ws.append(R.rng.choice(ws))
                else:
                    v = ch.draw(R.rng, 1)
                    ws.append(v if v in P.valid_move_set else (ch.support() or P.valid_moves)[0])
            while len(ws) > n:
                ws.pop(R.rng.randrange(len(ws)))
        if moves_on:
            ts = P.types_of(r)
            ws = [R.biased_move('egg_moves', w, ts, bias) for w in ws]
        er['wazaNo'] = ws


# 4.11 level-up moves
def levelup_moves(R):
    moves_on, levels_on, count_on = R.on('levelup_moves'), R.on('levelup_levels'), R.on('levelup_count')
    if not (moves_on or levels_on or count_on):
        return
    g, P = R.g, R.pools
    ch = R.choice('levelup_moves', P.valid_move_set)
    bias = R.pct('levelup_type_bias')
    damaging = [m for m in P.valid_moves if R.within(P.move_rows[m]['power'], 'power')]

    def is_attack(m):
        mr = P.move_rows.get(m)
        return mr is not None and R.within(mr['power'], 'power')

    for pid in P.valid_pids:
        r = P.rows[pid]
        if pid >= len(g.learnsets):
            continue
        ls = [list(e) for e in g.learnset(r)]
        if not R.within(len(ls), 'levelup_count'):
            continue
        if count_on:
            n = R.conform(R.num('levelup_count').draw(R.rng, len(ls)), 'levelup_count')
            if n > 0 and not ls:        # an empty learnset (boundary minimum 0) grows from one (Next(1), Next(1)) entry
                ls.append([R.conform(R.num('levelup_levels').draw(R.rng, 1), 'level'),
                           R.biased_move('levelup_moves', 1, P.types_of(r), 0.0)])
            while len(ls) < n:
                ls.append(list(R.rng.choice(ls)))
            while len(ls) > n:
                ls.pop(R.rng.randrange(len(ls)))
        if not ls:
            if count_on:
                g.set_learnset(r, [])
            continue
        if moves_on:
            ts = P.types_of(r)
            for e in ls:
                e[1] = R.biased_move('levelup_moves', e[1], ts, bias)
        if levels_on:
            for e in ls:
                e[0] = R.redraw('levelup_levels', e[0], 'level')
            if P.prev.get(pid):
                k = max(0, min(len(ls), int(R.evo_move_count.draw(R.rng, 0))))
                for _ in range(k):
                    R.rng.choice(ls)[0] = 0
        # the level-1 move is an attack
        first = R.rng.choice(ls)
        first[0] = 1
        att = [e for e in ls if is_attack(e[1])]
        if att:
            o = R.rng.choice(att)
            first[1], o[1] = o[1], first[1]
        elif damaging:
            first[1] = R.rng.choice(damaging)
        ls.sort(key=lambda e: e[0])
        if R.on('levelup_sort'):
            idx = [i for i, e in enumerate(ls) if e[0] != 0 and is_attack(e[1])]
            lv = sorted(ls[i][0] for i in idx)
            mv = sorted((ls[i][1] for i in idx), key=lambda m: P.move_rows[m]['power'])
            for i, l_, m in zip(idx, lv, mv):
                ls[i] = [l_, m]
            ls.sort(key=lambda e: e[0])
        g.learnsets[pid]['ar'] = [v for e in ls for v in e]


# 4.12 wild encounters
def wild(R):
    sp_on, lv_on = R.on('wild_species'), R.on('wild_levels')
    if not (sp_on or lv_on):
        return
    g, P = R.g, R.pools
    evo, legends = R.on('wild_evo'), R.on('wild_legends')
    form16 = P.form_encounters
    for _v, e in g.encounter_files():
        for z in e['table']:
            for k in SLOT_LISTS + GBA_LISTS:
                for s in z.get(k, []):
                    if not s['monsNo']:
                        continue
                    if lv_on and R.within((s['minlv'] + s['maxlv']) / 2, 'level'):
                        a = R.conform(R.num('wild_levels').draw(R.rng, s['minlv']), 'level')
                        b = R.conform(R.num('wild_levels').draw(R.rng, s['maxlv']), 'level')
                        s['minlv'], s['maxlv'] = min(a, b), max(a, b)
                        if evo and not sp_on:
                            cur = g.row(s['monsNo'] & 0xffff, s['monsNo'] >> 16)
                            if P.valid_row(cur):
                                n = R.find_stage(cur, (s['minlv'] + s['maxlv']) / 2, 0)
                                if P.valid_row(n):
                                    s['monsNo'] = encode(g, n, form16)
                    if sp_on:
                        lvl = (s['minlv'] + s['maxlv']) / 2
                        r = R.pick_pokemon('wild_species', s['monsNo'] & 0xffff, lvl, 0, evo, legends, form16)
                        if r is not None:
                            s['monsNo'] = encode(g, r, form16)
        if sp_on:
            ch = R.choice('wild_species', P.valid_species_set)
            for s in e.get('mistu', []):
                for f in ('Normal', 'Rare', 'SuperRare'):
                    s[f] = species_only(R, ch, s[f])
            for s in e.get('safari', []):
                s['MonsNo'] = species_only(R, ch, s['MonsNo'])
            for s in e.get('urayama', []):
                s['monsNo'] = species_only(R, ch, s['monsNo'])
    if sp_on:
        ch = R.choice('wild_species', P.valid_species_set)
        form_mode = P.ug_versions_free or P.ug_form16
        for _n, t in g.ug_tables():
            for r in t['table']:
                if not r['monsno']:
                    continue
                dex = draw_species(R, ch, r['monsno'] & 0xffff)
                if dex is None:
                    continue
                if form_mode:
                    vf = [k for k, fr in enumerate(P.species_forms[dex]) if P.valid_row(fr)]
                    form = g.form_of(P.species_forms[dex][R.rng.choice(vf)]) if vf else 0
                    if P.ug_versions_free:
                        r['version'] = form
                    r['monsno'] = dex | (form << 16) if P.ug_form16 else dex
                else:
                    r['monsno'] = dex
        if g.has_table('UnderGround/data/ugdata', 'UgSpecialPokemon'):
            for r in g.ug_table('UgSpecialPokemon')['Sheet1']:
                if r['monsno']:
                    r['monsno'] = species_only(R, ch, r['monsno'])
    if lv_on:
        for r in ug_levels(g):
            if R.within((r['MinLv'] + r['MaxLv']) / 2, 'level'):
                a = R.conform(R.num('wild_levels').draw(R.rng, r['MinLv']), 'level')
                b = R.conform(R.num('wild_levels').draw(R.rng, r['MaxLv']), 'level')
                r['MinLv'], r['MaxLv'] = min(a, b), max(a, b)
    extradata_encounters(R, sp_on, lv_on, evo, legends)


def extradata_encounters(R, sp_on, lv_on, evo, legends):
    """ExtraData starters ({monsNo, formNo, level, itemNo}) and honey trees ({slots: [{maxlv, minlv, monsNo, formNo}]})
    of a mod that brings them (romfs/Data/ExtraData/Encounters/...): randomized like the wild slots"""
    g, P = R.g, R.pools

    def stage_only(d, lvl):
        """Evolution Logic on a levels-only run: the current Pokemon moved to the stage fitting the new level"""
        cur = g.row(d['monsNo'], d.get('formNo', 0) or 0)
        if P.valid_row(cur):
            n = R.find_stage(cur, lvl, 0)
            if P.valid_row(n) and n is not cur:
                d['monsNo'], d['formNo'] = n['monsno'], g.form_of(n)
                return True
        return False
    for rel, d in g.extradata('Encounters/Starter'):
        if not d.get('monsNo'):
            continue
        changed = False
        if lv_on and isinstance(d.get('level'), (int, float)) and R.within(d['level'], 'level'):
            d['level'] = R.conform(R.num('wild_levels').draw(R.rng, d['level']), 'level')
            changed = True
            if evo and not sp_on:
                stage_only(d, d['level'])
        if sp_on:
            r = R.pick_pokemon('wild_species', d['monsNo'], d.get('level', 5), 0, evo, legends, True)
            if r is not None:
                d['monsNo'], d['formNo'] = r['monsno'], g.form_of(r)
                changed = True
        if changed:
            g.set_extradata(rel, d)
    for rel, d in g.extradata('Encounters/HoneyTrees'):
        changed = False
        for s in d.get('slots', []):
            if not s.get('monsNo'):
                continue
            if lv_on and R.within((s['minlv'] + s['maxlv']) / 2, 'level'):
                a = R.conform(R.num('wild_levels').draw(R.rng, s['minlv']), 'level')
                b = R.conform(R.num('wild_levels').draw(R.rng, s['maxlv']), 'level')
                s['minlv'], s['maxlv'] = min(a, b), max(a, b)
                changed = True
                if evo and not sp_on:
                    stage_only(s, (s['minlv'] + s['maxlv']) / 2)
            if sp_on:
                r = R.pick_pokemon('wild_species', s['monsNo'], (s['minlv'] + s['maxlv']) / 2, 0, evo, legends, True)
                if r is not None:
                    s['monsNo'], s['formNo'] = r['monsno'], g.form_of(r)
                    changed = True
        if changed:
            g.set_extradata(rel, d)


def encode(g, row, form16):
    return row['monsno'] | (g.form_of(row) << 16) if form16 else row['monsno']


def draw_species(R, ch, cur):
    for _ in range(CAP):
        v = ch.draw(R.rng, cur)
        if v in R.pools.valid_species_set:
            return v
    return None


def species_only(R, ch, cur):
    """a plain species field (honey trees, Great Marsh, Trophy Garden, UG specials): a valid species, form kept 0"""
    if not cur:
        return cur
    v = draw_species(R, ch, cur & 0xffff)
    return cur if v is None else v


# 4.13 trainers
def trainers(R):
    g, P = R.g, R.pools
    rng = R.rng
    if R.on('trainer_items') or R.on('trainer_item_count'):
        ch = R.choice('trainer_items', P.active_item_set)
        for t in g.trainers:
            its = [t[f] for f in USE_ITEMS if t.get(f)]
            if R.on('trainer_item_count'):
                n = max(0, min(4, R.num('trainer_item_count').draw(rng, len(its))))
                while len(its) < n:
                    if its:
                        its.append(rng.choice(its))
                    else:
                        v = ch.draw(rng, 1)
                        its.append(v if v in P.active_item_set else (ch.support() or [1])[0])
                while len(its) > n:
                    its.pop(rng.randrange(len(its)))
            if R.on('trainer_items'):
                its = [ch.draw(rng, i) for i in its]
                t['AIBit'] = t['AIBit'] | 0x20
            for k, f in enumerate(USE_ITEMS):
                t[f] = its[k] if k < len(its) else 0
    if R.on('trainer_count'):
        g.empty_slot()          # measured before any party changes
        for i, prow in enumerate(g.trainer_pokes):
            slots = g.party_slots(prow)
            n0 = len(slots)
            if not R.within(n0, 'trainer_count'):
                continue
            nmax = slot_count(prow)
            n = min(nmax, R.conform(R.num('trainer_count').draw(rng, n0), 'trainer_count'))
            tr = trainer_of(g, prow, i)
            if tr is not None and tr.get('FightType') == 1:
                n = max(n, min(2, nmax))
            while len(slots) < n:
                slots.append(dict(rng.choice(slots)) if slots else dict(g.empty_slot()))   # a blank member if empty
            while len(slots) > n:
                slots.pop(rng.randrange(len(slots)))
            if len(slots) != n0:
                g.set_party_slots(prow, slots)
    themes = trainer_themes(g) if R.on('trainer_themes') else {}
    evo, legends = R.on('trainer_evo'), R.on('trainer_legends')
    mode = R.value('trainer_moves')
    for i, prow in enumerate(g.trainer_pokes):
        fs = filled_slots(prow)
        if not fs:
            continue
        tr = trainer_of(g, prow, i)
        theme = themes.get(tr['TypeID']) if tr is not None else None
        for p in fs:
            if R.on('trainer_levels'):
                prow[p + 'Level'] = R.redraw('trainer_levels', prow[p + 'Level'], 'level')
            lvl = prow[p + 'Level']
            if R.on('trainer_species'):
                r = R.pick_pokemon('trainer_species', prow[p + 'MonsNo'], lvl, 1, evo, legends, True, theme)
                if r is not None:
                    prow[p + 'MonsNo'], prow[p + 'FormNo'], prow[p + 'Sex'] = r['monsno'], g.form_of(r), 3
            if R.on('trainer_held') and (not R.on('trainer_held_high') or R.chance(lvl)):
                prow[p + 'Item'] = R.choice('trainer_held', P.held_item_set).draw(rng, prow[p + 'Item'])
            if R.on('trainer_natures'):
                prow[p + 'Seikaku'] = R.choice('trainer_natures', set(P.natures)).draw(rng, prow[p + 'Seikaku'])
            row = g.row(prow[p + 'MonsNo'], prow[p + 'FormNo'])
            if mode == 'last' and row is not None:
                ls = [m for lv, m in sorted(g.learnset(row), key=lambda e: e[0]) if lv <= lvl and m in P.valid_move_set]
                last = []
                for m in reversed(ls):
                    if m not in last:
                        last.append(m)
                    if len(last) == 4:
                        break
                last.reverse()
                for k in range(4):
                    prow[f'{p}Waza{k + 1}'] = last[k] if k < len(last) else 0
            elif mode == 'random' and row is not None:
                ts = P.types_of(row)
                cur = [prow[f'{p}Waza{k}'] for k in range(1, 5)]
                new = []
                for w in cur:
                    if w:
                        new.append(R.biased_move('trainer_moves', w, ts, R.pct('trainer_move_bias'), exclude=new))
                for k in range(4):
                    prow[f'{p}Waza{k + 1}'] = new[k] if k < len(new) else 0
            if R.on('trainer_shiny'):
                prow[p + 'IsRare'] = 1 if R.chance(R.pct('trainer_shiny_pct')) else 0
            if R.on('trainer_abilities') and row is not None:
                if R.on('trainer_abilities_any'):
                    prow[p + 'Tokusei'] = R.choice('trainer_abilities', P.valid_ability_set).draw(rng, prow[p + 'Tokusei'])
                else:
                    own = [row[f] for f in ('tokusei1', 'tokusei2', 'tokusei3') if row[f] in P.valid_ability_set]
                    if own:
                        prow[p + 'Tokusei'] = rng.choice(own)
            if R.on('trainer_ivs'):
                ivs = [prow[p + f] for f in TALENTS]
                if R.within(sum(ivs) / 6, 'iv'):
                    for f in TALENTS:
                        prow[p + f] = R.conform(R.num('trainer_ivs').draw(rng, prow[p + f]), 'iv')
            if R.on('trainer_evs'):
                tot = sum(prow[p + f] for f in EFFORTS)
                if R.within(tot, 'ev_total'):
                    tot = R.conform(R.num('trainer_evs').draw(rng, tot), 'ev_total')
                    for f, v in zip(EFFORTS, R.split(tot, R.bounds['ev'][1])):
                        prow[p + f] = v


def trainer_of(g, prow, i):
    T = g.trainers
    tid = prow.get('ID', i)
    return T[tid] if 0 <= tid < len(T) else None


def trainer_themes(g):
    """TrainerData.TypeID -> theme type, from the trainer type labels (TR_LEADER1_01 ...)"""
    out = {}
    for tt in g.trainer_types:
        lab = tt.get('LabelTrType') or ''
        for key, ty in THEMES.items():
            if (key + '_') in lab:
                out[tt['TrainerID']] = ty
    return out


# 4.14 type matchups
def type_matchups(R):
    if not R.on('type_matchups'):
        return None
    from .formats import il2cppmeta
    ctx = R.ctx
    m = None
    try:
        m = ctx.metadata() if ctx is not None else None
    except Exception as e:
        return f'Random matchups skipped: the player metadata cannot be read ({e})'
    if m is None:
        return 'Random matchups skipped: no player metadata to edit'
    try:
        chart = il2cppmeta.type_chart(m)[0]
    except Exception as e:
        return f'Random matchups skipped: the type chart is not found in the metadata ({e})'
    ch = R.choice('type_matchups', set(analyzer.AFFINITY_VALUES))
    new = [[ch.draw(R.rng, v) if v in analyzer.AFFINITY_VALUES else v for v in row] for row in chart]
    op = {'op': 'typechart', 'values': new}
    try:
        return ctx.metadata_op(op)
    except ImportError:          # the metadata operation module is not there yet: write the chart directly
        il2cppmeta.set_type_chart(m, new)
        ctx.meta_changed = True
        return None


# 4.15 scripts
def script_files(g):
    try:
        b = g.files.bundle(EVSCRIPT)
    except Exception:
        return []
    out = []
    for n in sorted(b.names()):
        t = b.mono(n)
        if isinstance(t, dict) and 'Scripts' in t:
            out.append((n, t))
    return out


def species_sites(g, pools, tree):
    """-> [(arg dict, cmd id, level or None)] of every literal species argument (direct or traced through a work)"""
    sites = []
    for sc in tree['Scripts']:
        loads = {}          # work index -> [(arg dict)] of the literal load that last wrote it
        for c in sc['Commands']:
            a = c['Arg']
            if not a:
                continue
            cid = a[0]['data']
            if cid == LDVAL and len(a) >= 3 and a[1]['argType'] == ARG_WORK:
                loads[a[1]['data']] = [a[2]] if a[2]['argType'] == ARG_FLOAT else []
                continue
            if cid == LDVAL_VERSION and len(a) >= 3:
                loads[SCWK_TEMP0] = [x for x in a[1:3] if x['argType'] == ARG_FLOAT]
                continue
            if cid in SPECIES_ARGS:
                lvl = None
                li = LEVEL_ARG.get(cid)
                if li is not None and li < len(a) and a[li]['argType'] == ARG_FLOAT:
                    lvl = ffrom(a[li]['data'])
                if cid == EGG_CMD:
                    lvl = 1
                for i in SPECIES_ARGS[cid]:
                    if i >= len(a):
                        continue
                    if a[i]['argType'] == ARG_FLOAT:
                        sites.append((a[i], cid, lvl, a))
                    elif a[i]['argType'] == ARG_WORK:
                        for x in loads.pop(a[i]['data'], []):
                            sites.append((x, cid, lvl, a))
                continue
            for x in a[1:]:     # any other use of a work ends the trace of its load
                if x['argType'] == ARG_WORK:
                    loads.pop(x['data'], None)
    out = []
    for arg, cid, lvl, a in sites:
        v = ffrom(arg['data'])
        if v == int(v) and int(v) in pools.valid_species_set:
            out.append((arg, cid, lvl, a))
    return out


def script_literals(g, pools):
    """the observations of the two script options (analyzer defaults)"""
    sp, it = [], []
    for _n, t in script_files(g):
        for arg, _c, _l, _a in species_sites(g, pools, t):
            sp.append(int(ffrom(arg['data'])))
        for sc in t['Scripts']:
            for c in sc['Commands']:
                a = c['Arg']
                if a and a[0]['data'] == ITEM_BALL and len(a) > 1 and a[1]['argType'] == ARG_FLOAT:
                    v = ffrom(a[1]['data'])
                    if v == int(v) and int(v) in pools.buyable_item_set:
                        it.append(int(v))
    return {'script_species': sp, 'script_items': it}


def scripts(R):
    g, P = R.g, R.pools
    if R.on('script_species'):
        ch = R.choice('script_species', P.valid_species_set)
        legends = R.on('script_legends')
        for _n, t in script_files(g):
            sites = species_sites(g, P, t)
            if not sites:
                continue
            levels = {}         # species -> the highest literal level the file uses it at (None: no level)
            for arg, _c, lvl, _a in sites:
                v = int(ffrom(arg['data']))
                if lvl is None:
                    levels.setdefault(v, None)
                else:
                    levels[v] = max(levels.get(v) or 0, lvl)
            mapping = {}
            for old in sorted(levels):
                lvl = levels[old]
                new = None
                for _ in range(CAP):
                    v = ch.draw(R.rng, old)
                    if v in P.valid_species_set and (lvl is None or R.legend_ok(v, lvl, legends)):
                        new = v
                        break
                mapping[old] = new if new is not None else old
            for arg, cid, _l, a in sites:
                old = int(ffrom(arg['data']))
                new = mapping[old]
                if new != old:
                    arg['data'] = fbits(new)
                    fi = FORM_ARG.get(cid)
                    if fi is not None and fi < len(a) and a[fi]['argType'] == ARG_FLOAT:
                        a[fi]['data'] = fbits(0)
    if R.on('script_items'):
        ch = R.choice('script_items', P.active_item_set)
        for _n, t in script_files(g):
            for sc in t['Scripts']:
                for c in sc['Commands']:
                    a = c['Arg']
                    if a and a[0]['data'] == ITEM_BALL and len(a) > 1 and a[1]['argType'] == ARG_FLOAT:
                        v = ffrom(a[1]['data'])
                        if v == int(v) and int(v) in P.buyable_item_set:
                            n = ch.draw(R.rng, int(v))
                            if n != int(v):
                                a[1]['data'] = fbits(n)


# 4.16 text
def shuffle_text(R):
    if not R.on('shuffle_text'):
        return
    from .text import LANGS
    g = R.g
    sets = {}
    for rel in ['Message/common_msbt'] + [f'Message/{lang}' for lang in LANGS]:
        try:
            b = g.files.bundle(rel)
        except Exception:
            continue
        for n in sorted(b.names()):
            t = b.mono(n)
            if not isinstance(t, dict) or 'labelDataArray' not in t:
                continue
            key = (t.get('langID', 0), t.get('isKanji', 0))
            for lab in t['labelDataArray']:
                ws = lab.get('wordDataArray') or []
                if not ws or any(w['tagIndex'] >= 0 or w['eventID'] == 5 for w in ws):
                    continue
                text = ''.join(w['str'] + ('\n' if w['eventID'] in (1, 3, 4) else '') for w in ws)
                if text:
                    sets.setdefault(key, []).append((lab, text))
    keep = R.on('shuffle_text_len')
    for key in sorted(sets):
        cands = sets[key]
        for lab, _t in cands:
            lab['wordDataArray'][-1]['eventID'] = 7
        buckets = {}
        for lab, text in cands:
            buckets.setdefault(text_bucket(lab, text) if keep else 0, []).append(lab)
        for bk in sorted(buckets):
            labs = buckets[bk]
            arrays = [lab['wordDataArray'] for lab in labs]
            R.rng.shuffle(arrays)
            for lab, arr in zip(labs, arrays):
                lab['wordDataArray'] = arr


def text_bucket(lab, text):
    ws = lab['wordDataArray']
    n = len(ws) if len(ws) > 1 else len(text)
    for k, lim in enumerate((3, 8, 21, 55)):
        if n < lim:
            return k if len(ws) == 1 else k + 5
    return 4 if len(ws) == 1 else 9


# 4.17 BGM
def shuffle_bgm(R):
    if not R.on('shuffle_bgm'):
        return None
    try:
        from .formats import wwise
    except ImportError:
        return 'Shuffle BGM skipped: the soundbank library (formats/wwise.py) is missing'
    g = R.g
    try:
        src = g.files.source(BANK)
    except Exception:
        return 'Shuffle BGM skipped: the game files have no Delphis_Main.bnk'
    if getattr(src, 'kind', 'switch') != 'switch':
        return 'Shuffle BGM skipped: Delphis_Main.bnk comes from a pack as a Windows file'
    bank = wwise.Bank(g.files.read(BANK))
    perm = R.value('shuffle_bgm_mode') != 'repeats'
    n = 0
    for obj in bank.of_type(wwise.T_MSWITCH):
        tree = wwise.Node(obj, bank.version or 135).tree
        if tree is None:
            continue
        for pos, (group, _gtype) in enumerate(tree.arguments):
            if group not in BGM_GROUPS:
                continue
            leaves = [(i, aid) for i, path, aid in tree.leaves()
                      if len(path) > pos and path[pos] not in BGM_SKIP and aid]
            if len(leaves) < 2:
                continue
            tracks = sorted({aid for _i, aid in leaves})
            if perm:
                ids = [aid for _i, aid in leaves]
                R.rng.shuffle(ids)
            else:
                ids = [R.rng.choice(tracks) for _ in leaves]
            for (i, old), new in zip(leaves, ids):
                if new != old:
                    tree.set_leaf(i, new)
                    n += 1
    if n:
        g.files.set_raw(BANK, bank.to_bytes())
    return None


# =====================================================================================================================
def run(game, settings, seed, context, log=print):
    """Randomizes the game data in place. -> None, or a list of warnings"""
    R = Run(game, settings, seed, context, log)
    warnings = []
    level_multiplier(R)
    moves(R)
    items(R)
    evolutions(R)
    base_stats(R)
    typing(R)
    tm_compat(R)
    personal_misc(R)
    egg_moves(R)
    levelup_moves(R)
    wild(R)
    trainers(R)
    for step in (type_matchups, scripts, shuffle_text, shuffle_bgm):
        w = step(R)
        if w:
            warnings.append(w)
    warnings += R.warnings
    return warnings or None
