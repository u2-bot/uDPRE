"""Randomize: every option of the randomizer engine (randomizer.OPTIONS - ids, defaults and the settings file stay the same)
in our own words and layout: categories with counters, toggles whose sub-options wake up with them, starting presets,
and inline editors for how new values are drawn - a shape designer with a live preview over the game's own values, and
a pool editor with weights. Randomize = one more 'randomize' operation of your edits."""
import collections
import copy
import json
import random
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import analyzer, distributions as dist, randomizer as rz
from ..kit import Button, Link, Scroll, SearchBox, Segmented, frame, label
from ..page import Page
from ..theme import C, FONT

# category -> [(group title, [option ids])]
CATS = [
    ('pokemon', 'Pokémon', [
        ('Evolutions', ['evo_dest', 'evo_dest_bst', 'evo_levels']),
        ('Base stats', ['stats_shuffle', 'stats_random', 'stats_bst']),
        ('Types', ['typing', 'typing_double', 'typing_evo']),
        ('Abilities and traits', ['abilities', 'held_items', 'growth', 'catch_rate', 'friendship', 'ev_yield',
                                  'exp_yield']),
        ('Level-up moves', ['levelup_moves', 'levelup_type_bias', 'levelup_levels', 'levelup_count', 'levelup_sort']),
        ('Egg moves', ['egg_moves', 'egg_type_bias', 'egg_count']),
        ('TM compatibility', ['tm_compat', 'tm_compat_pct', 'tm_type_bias', 'tm_evo']),
    ]),
    ('moves', 'Moves & items', [
        ('Moves', ['move_type', 'move_category', 'move_power', 'move_accuracy', 'move_pp', 'tm_moves']),
        ('Items', ['item_prices', 'pickup_items', 'shop_items', 'shop_preserve_mart']),
    ]),
    ('world', 'Wild & world', [
        ('Wild Pokémon', ['wild_species', 'wild_levels', 'wild_evo', 'wild_legends']),
        ('Gifts, events and items on the ground', ['script_species', 'script_legends', 'script_items']),
    ]),
    ('trainers', 'Trainers', [
        ('Their Pokémon', ['trainer_species', 'trainer_evo', 'trainer_themes', 'trainer_legends', 'trainer_count',
                           'trainer_levels']),
        ('Moves and abilities', ['trainer_moves', 'trainer_move_bias', 'trainer_abilities', 'trainer_abilities_any']),
        ('Items', ['trainer_items', 'trainer_item_count', 'trainer_held', 'trainer_held_high']),
        ('Stats and looks', ['trainer_natures', 'trainer_ivs', 'trainer_evs', 'trainer_shiny', 'trainer_shiny_pct']),
    ]),
    ('levels', 'Level scaling', [
        ('Multiply levels before anything is drawn', ['level_coef', 'level_evo', 'level_moves', 'level_wild',
                                                       'level_trainer']),
    ]),
    ('rules', 'Battle rules', [('Type chart', ['type_matchups'])]),
    ('flavor', 'Text & music', [('Text', ['shuffle_text', 'shuffle_text_len']),
                                ('Music', ['shuffle_bgm', 'shuffle_bgm_mode'])]),
    ('limits', 'Limits', [('Limits and rounding', ['bounds'])]),
]
# our own wording: option id -> (label, explanation)
TEXT = {
    'evo_dest': ('Evolve into different Pokémon', 'Every evolution leads to another Pokémon from the pool.'),
    'evo_dest_bst': ('Only into stronger ones', 'The new Pokémon has a higher base stat total than the one evolving.'),
    'evo_levels': ('New evolution levels', 'Draws a new level for every level-based evolution.'),
    'stats_shuffle': ('Shuffle each Pokémon\'s stats', 'The six base stats trade places; the total stays the same.'),
    'stats_random': ('New base stats', 'Draws every base stat again.'),
    'stats_bst': ('Evolutions stay at least as strong',
                  'An evolution or a stronger form keeps a base stat total no lower than the stage before it.'),
    'typing': ('New types', 'Draws new types for every Pokémon.'),
    'typing_double': ('Chance of a second type', ''),
    'typing_evo': ('Families share their types', 'Evolutions take their types from the stage before them.'),
    'tm_compat': ('New TM compatibility', 'Draws which TMs every Pokémon can learn.'),
    'tm_compat_pct': ('Chance to learn each TM', ''),
    'tm_type_bias': ('Prefer TMs of its own types', 'Chance that a TM is picked by matching the Pokémon\'s types.'),
    'tm_evo': ('Evolutions keep their TMs', 'An evolution can learn every TM the stage before it could.'),
    'held_items': ('New wild held items', 'Draws the items wild Pokémon may be holding.'),
    'growth': ('New growth rates', 'How fast each family levels up (one rate per family).'),
    'abilities': ('New abilities', 'Draws all three abilities.'),
    'catch_rate': ('New catch rates', ''),
    'friendship': ('New base friendship', ''),
    'ev_yield': ('New EV yield', 'Draws the total effort points and spreads them over the stats.'),
    'exp_yield': ('New EXP yield', ''),
    'egg_moves': ('New egg moves', ''),
    'egg_type_bias': ('Prefer moves of its own types', 'Chance that an egg move must share a type with the Pokémon.'),
    'egg_count': ('New number of egg moves', ''),
    'levelup_moves': ('New level-up moves', 'The first move is always an attack.'),
    'levelup_type_bias': ('Prefer moves of its own types', 'Chance that a move must share a type with the Pokémon.'),
    'levelup_levels': ('New learn levels', 'Evolved Pokémon also learn moves when they evolve.'),
    'levelup_count': ('New number of level-up moves', ''),
    'levelup_sort': ('Weaker attacks first', 'Attacks are learned in order of power.'),
    'move_type': ('New move types', ''),
    'move_category': ('Swap physical and special', 'Draws the category of every damaging move (status moves stay).'),
    'tm_moves': ('New TM moves', 'Each TM teaches another move.'),
    'move_power': ('New power', ''),
    'move_accuracy': ('New accuracy', ''),
    'move_pp': ('New PP', ''),
    'item_prices': ('New prices', ''),
    'pickup_items': ('New Pickup finds', 'What the Pickup ability brings back.'),
    'shop_items': ('New shop stock', 'What the shops sell.'),
    'shop_preserve_mart': ('Keep the regular Poké Mart', 'Its stock and badge steps stay as they are.'),
    'wild_species': ('New wild Pokémon', 'Grass, caves, water and rods, honey trees, the Great Marsh, the Trophy Garden '
                                         'and the Underground.'),
    'wild_levels': ('New wild levels', 'Wild areas and the Underground.'),
    'wild_evo': ('Right stage for the level', 'A wild Pokémon is the evolution stage that fits its level.'),
    'wild_legends': ('Legendaries only at high levels', 'A legendary is accepted with a chance equal to its level, in %.'),
    'trainer_items': ('New battle items', 'The items trainers use in battle (every trainer may use some).'),
    'trainer_item_count': ('New number of battle items', 'From 0 to 4.'),
    'trainer_count': ('New party sizes', 'Double battles keep at least two Pokémon.'),
    'trainer_levels': ('New levels', ''),
    'trainer_species': ('New Pokémon', 'Draws every party member.'),
    'trainer_evo': ('Right stage for the level', 'A party Pokémon is the evolution stage that fits its level.'),
    'trainer_themes': ('Gym Leaders and the Elite Four keep their type', ''),
    'trainer_legends': ('Legendaries only at high levels', 'A legendary is accepted with a chance equal to its level, in %.'),
    'trainer_held': ('New held items', ''),
    'trainer_held_high': ('Held items mostly at high levels',
                          'An item is drawn with a chance equal to the Pokémon\'s level, in %.'),
    'trainer_natures': ('New natures', ''),
    'trainer_moves': ('Moves', ''),
    'trainer_move_bias': ('Prefer moves of its own types', 'For random moves: chance a move shares a type with it.'),
    'trainer_shiny': ('New shinies', 'Draws which party Pokémon are shiny.'),
    'trainer_shiny_pct': ('Chance to be shiny', ''),
    'trainer_abilities': ('New abilities', 'One of the Pokémon\'s own three abilities.'),
    'trainer_abilities_any': ('Any ability at all', 'Draws from every ability, not just the Pokémon\'s own.'),
    'trainer_ivs': ('New IVs', ''),
    'trainer_evs': ('New EVs', 'Draws the total and spreads it over the stats.'),
    'level_coef': ('Multiply levels by', 'For the parts ticked below; 1 = unchanged.'),
    'level_evo': ('Evolution levels', ''),
    'level_moves': ('Learn levels', ''),
    'level_wild': ('Wild Pokémon', ''),
    'level_trainer': ('Trainer Pokémon', ''),
    'type_matchups': ('New type chart', 'Draws every attacking-defending effect (kept in the game\'s code).'),
    'script_species': ('New gift and event Pokémon', 'Gifts, eggs and fixed encounters of the event scripts (and the '
                                                     'names they show).'),
    'script_legends': ('Legendaries only at high levels', 'A legendary is accepted with a chance equal to the event\'s '
                                                          'level, in %.'),
    'script_items': ('New items on the ground', 'The item balls you pick up.'),
    'shuffle_text': ('Shuffle the game\'s text', 'Swaps messages that have no placeholders.'),
    'shuffle_text_len': ('Only similar lengths', ''),
    'shuffle_bgm': ('Shuffle the music', 'Battle, contest, event and field music.'),
    'shuffle_bgm_mode': ('How', ''),
    'bounds': ('Limits and rounding', 'A value outside its limits is never changed; new values are rounded to the step '
                                      'and kept inside the limits.'),
}
CHOICE_TEXT = {'unchanged': 'Keep them', 'last': 'Its latest level-up moves', 'random': 'Random moves',
               'permutation': 'Each track used once', 'repeats': 'Tracks may repeat'}
BOUND_OF = {'evo_levels': 'level', 'stats_random': 'base_stat', 'catch_rate': 'catch_rate', 'friendship': 'friendship',
            'ev_yield': 'ev_yield_total', 'exp_yield': 'exp_yield', 'egg_count': 'egg_count', 'levelup_levels': 'level',
            'levelup_count': 'levelup_count', 'move_power': 'power', 'move_accuracy': 'accuracy', 'move_pp': 'pp',
            'item_prices': 'price', 'wild_levels': 'level', 'trainer_count': 'trainer_count', 'trainer_levels': 'level',
            'trainer_ivs': 'iv', 'trainer_evs': 'ev_total'}
SHAPES = [('NR', 'Near the current value', 'spread'), ('NP', 'Near the current value, in proportion', 'spread %'),
          ('UR', 'Shift it by a random amount', 'from / to'), ('UP', 'Scale it by a random factor', 'from x / to x'),
          ('UC', 'Any value in a range', 'from / to'), ('NC', 'Around one fixed value', 'center / spread')]
PRESETS = [
    ('none', 'Nothing on', {}),
    ('light', 'Light', {'wild_species': True, 'wild_evo': True, 'wild_legends': True, 'trainer_species': True,
                        'trainer_evo': True, 'trainer_themes': True, 'trainer_legends': True, 'script_species': True,
                        'script_legends': True}),
    ('balanced', 'Balanced', {'abilities': True, 'typing': True, 'typing_evo': True, 'stats_shuffle': True,
                              'stats_bst': True, 'levelup_moves': True, 'tm_compat': True, 'tm_evo': True,
                              'held_items': True, 'trainer_held': True, 'trainer_moves': 'last'}),
    ('chaotic', 'Chaotic', {'evo_dest': True, 'stats_shuffle': False, 'stats_random': True, 'move_type': True,
                            'move_power': True, 'move_accuracy': True, 'move_pp': True, 'tm_moves': True,
                            'egg_moves': True, 'item_prices': True, 'pickup_items': True, 'shop_items': True,
                            'shop_preserve_mart': True, 'trainer_moves': 'random', 'trainer_abilities': True,
                            'trainer_natures': True, 'trainer_ivs': True, 'script_items': True, 'shuffle_bgm': True}),
]


def _fmt(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f'{v:.3f}'.rstrip('0').rstrip('.')


def shape_text(spec):
    """a numeric spec in plain words"""
    t = spec.get('type')
    p = spec.get('p', 100)
    s = {'NR': lambda: f'Near the current value (most within ±{_fmt(spec["std"])})',
         'NP': lambda: f'Near the current value (most within ±{_fmt(spec["std"] * 100)}% of it)',
         'UR': lambda: f'The current value plus {_fmt(spec["min"])} to {_fmt(spec["max"])}',
         'UP': lambda: f'The current value times {_fmt(spec["min"])} to {_fmt(spec["max"])}',
         'UC': lambda: f'Any value from {_fmt(spec["min"])} to {_fmt(spec["max"])}',
         'NC': lambda: f'Around {_fmt(spec["mean"])} (most within ±{_fmt(spec["std"])})'}.get(t)
    out = s() if s else 'Not set'
    return out + (f'  ·  changes {_fmt(p)}% of the values' if p < 100 else '')


def pool_text(spec):
    if spec.get('type') == 'uniform':
        n = len(spec.get('include', []))
        out = f'Equal chances among {n} choice{"s" if n != 1 else ""}'
    else:
        n = sum(1 for _v, w in dist.weight_pairs(spec.get('weights', [])) if w > 0)
        out = f'Weighted among {n} choice{"s" if n != 1 else ""}'
    p = spec.get('p', 100)
    return out + (f'  ·  changes {_fmt(p)}% of them' if p < 100 else '')


class RandomizePage(Page):
    title = 'Randomize'
    subtitle = 'Reroll the game from one seed - start from a preset, then adjust anything'

    def build_page(self):
        g = self.s.game
        self.observed = {}
        self.defaults = analyzer.default_settings(g, self.s.context, observed=self.observed)
        # what the page showed when it was last left (or randomized): the settings and, per pool / shape, the mode not in
        # use (Weighted weights and Equal chances ticks are kept side by side)
        self.mem = copy.deepcopy(self.defaults.get('dist_alt') or {})
        for oid, alts in (self.s.project.meta.get('randomizer_alt') or {}).items():
            if isinstance(alts, dict):
                self.mem.setdefault(oid, {}).update(copy.deepcopy(alts))
        kept = self.s.project.meta.get('randomizer')
        self.settings = copy.deepcopy(kept if isinstance(kept, dict) else self.defaults)
        self.settings.pop('dist_alt', None)
        self.cat = CATS[0][0]
        self.open_panel = None
        self.make_vars()
        top = frame(self)
        top.pack(fill='x', padx=24, pady=(14, 0))
        label(top, 'Seed', style='Muted.TLabel').pack(side='left')
        kept_seed = self.s.project.meta.get('randomizer_seed')
        self.seed = tk.StringVar(value=str(kept_seed) if kept_seed else str(random.randrange(1, 2 ** 31)))
        ttk.Entry(top, textvariable=self.seed, width=13, style='Studio.TEntry').pack(side='left', padx=(6, 4))
        Button(top, 'New seed', lambda: self.seed.set(str(random.randrange(1, 2 ** 31))), small=True).pack(side='left')
        label(top, 'Start from', style='Muted.TLabel').pack(side='left', padx=(26, 6))
        self.preset = Segmented(top, [(k, n) for k, n, _ in PRESETS], command=self.use_preset, value='')
        self.preset.pack(side='left')
        Button(top, 'Randomize', self.randomize, kind='primary').pack(side='right')
        Link(top, 'Save settings...', self.save_settings).pack(side='right', padx=(0, 16))
        Link(top, 'Load settings...', self.load_settings).pack(side='right', padx=(0, 12))
        # what the seed does: nothing changes until Randomize (then Apply in the uDPRE window)
        self.seed_note = label(self, '', style='Muted.TLabel')
        self.seed_note.pack(fill='x', padx=24, pady=(6, 0))
        self.seed.trace_add('write', lambda *_a: self.after_idle(self.update_seed_note))
        self.update_seed_note()
        tk.Frame(self, height=1, bg=C['line']).pack(fill='x', padx=24, pady=(10, 0))
        bottom = tk.Frame(self, bg=C['soft'])
        bottom.pack(side='bottom', fill='x', padx=24, pady=(0, 10))
        self.summary = tk.Label(bottom, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', justify='left',
                                wraplength=1000)
        self.summary.pack(fill='x', padx=12, pady=7)
        body = frame(self)
        body.pack(fill='both', expand=True, padx=(24, 0))
        self.nav = tk.Frame(body, bg=C['bg'], width=210)
        self.nav.pack(side='left', fill='y', pady=(10, 0))
        self.nav.pack_propagate(False)
        tk.Frame(body, width=1, bg=C['line']).pack(side='left', fill='y', padx=(0, 20))
        self.scroll = Scroll(body)
        self.scroll.pack(side='left', fill='both', expand=True)
        self.render_nav()
        self.render_cat()
        self.update_summary()

    # --- state ----------------------------------------------------------------------------------------------------
    def make_vars(self):
        """one tk variable per option, alive across category switches"""
        self.vars = {}
        for o in rz.OPTIONS:
            oid, kind = o['id'], o['kind']
            cur = self.settings.get(oid, self.defaults.get(oid, o.get('default')))
            if kind == 'check':
                v = tk.BooleanVar(value=bool(cur))
            elif kind in ('percent', 'number'):
                v = tk.StringVar(value=_fmt(cur if cur is not None else 0))
            elif kind == 'choice':
                ids = [c[0] for c in o['choices']]
                v = tk.StringVar(value=cur if cur in ids else ids[0])
            else:
                continue
            v.trace_add('write', lambda *_a: self.after_idle(self.changed))
            self.vars[oid] = (kind, v)
        b = self.settings.get('bounds') or self.defaults.get('bounds') or {}
        self.bound_vars = {name: [tk.StringVar(value=_fmt(x)) for x in list(b.get(name, rz.BOUNDS.get(name)))[:3]]
                           for name in rz.BOUND_LABELS}

    def changed(self):
        self.render_nav()
        self.wake()
        self.update_summary()

    def is_on(self, oid):
        o = rz.OPTION[oid]
        if oid not in self.vars:
            return False
        kind, v = self.vars[oid]
        if kind == 'check':
            return bool(v.get())
        if kind == 'choice':
            return v.get() != o['default']
        if kind == 'number':
            try:
                return float(v.get()) != float(o['default'])
            except ValueError:
                return True
        return False

    def parent_on(self, o):
        p = o.get('parent')
        if not p:
            return True
        po = rz.OPTION[p]
        if po['kind'] == 'check':
            return self.is_on(p)
        if po['kind'] == 'choice':                     # trainer moves: the bias acts on random moves
            return self.vars[p][1].get() == 'random'
        return True                                    # a number parent (level multiplier) does not switch off

    def last_randomize(self):
        """(index, seed) of the randomization your edits hold (the last one), or (None, None)"""
        ops = self.s.project.ops
        for i in range(len(ops) - 1, -1, -1):
            if ops[i].get('op') == 'randomize':
                return i, ops[i].get('seed')
        return None, None

    def update_seed_note(self):
        _i, used = self.last_randomize()
        seed = self.seed.get().strip()
        if used is None:
            t = 'Press Randomize to reroll your game with this seed, then Apply in the uDPRE window.'
        elif str(used) == seed:
            t = 'Your edits hold the randomization made with this seed.'
        else:
            t = (f'Your edits hold a randomization made with seed {used}. Press Randomize to reroll it with this '
                 f'seed, then Apply in the uDPRE window.')
        try:
            self.seed_note.config(text=t)
        except tk.TclError:
            pass

    def current_spec(self, oid):
        return (self.settings.get('dist') or {}).get(oid) or (self.defaults.get('dist') or {}).get(oid) or {}

    def set_spec(self, oid, spec):
        self.settings.setdefault('dist', {})[oid] = spec
        self.mem.setdefault(oid, {})[spec['type']] = dict(spec)
        lab = getattr(self, 'spec_labels', {}).get(oid)
        if lab is not None:
            try:
                lab.config(text=shape_text(spec) if rz.OPTION[oid]['dist'] == 'numeric' else pool_text(spec))
            except tk.TclError:
                pass

    # --- category list --------------------------------------------------------------------------------------------
    def render_nav(self):
        for w in self.nav.winfo_children():
            w.destroy()
        for cid, name, groups in CATS:
            ids = [oid for _t, ids in groups for oid in ids]
            n = sum(1 for oid in ids if self.is_on(oid) and not rz.OPTION[oid].get('parent'))
            on = cid == self.cat
            row = tk.Frame(self.nav, bg=C['accent_soft'] if on else C['bg'], cursor='hand2')
            row.pack(fill='x', pady=1)
            a = tk.Label(row, text=name, bg=row['bg'], fg=C['accent'] if on else C['text'],
                         font=(FONT, 10, 'bold' if on else 'normal'), anchor='w', padx=12, pady=6, cursor='hand2')
            a.pack(side='left', fill='x', expand=True)
            b = tk.Label(row, text=f'{n} on' if n else '', bg=row['bg'], fg=C['accent'] if n else C['faint'],
                         font=(FONT, 8, 'bold'), padx=10, cursor='hand2')
            b.pack(side='right')
            for w in (row, a, b):
                w.bind('<Button-1>', lambda _e, c=cid: self.pick_cat(c))

    def pick_cat(self, cid):
        self.cat = cid
        self.open_panel = None
        self.render_nav()
        self.render_cat()
        self.scroll.top()

    # --- one category ---------------------------------------------------------------------------------------------
    def render_cat(self):
        body = self.scroll.body
        for w in body.winfo_children():
            w.destroy()
        self.rows_w = {}
        self.spec_labels = {}
        groups = next(g for c, _n, g in CATS if c == self.cat)
        for title, ids in groups:
            head = frame(body)
            head.pack(fill='x', pady=(14, 2))
            label(head, title, style='Section.TLabel').pack(side='left')
            tk.Frame(body, height=1, bg=C['line']).pack(fill='x', pady=(2, 6))
            for oid in ids:
                if oid == 'bounds':
                    self.bounds_grid(body)
                else:
                    self.option_row(body, rz.OPTION[oid])
        self.wake()

    def option_row(self, parent, o):
        oid, kind = o['id'], o['kind']
        lab, help_ = TEXT.get(oid, (o['label'], o.get('help', '')))
        child = bool(o.get('parent'))
        box = frame(parent)
        box.pack(fill='x', padx=(28 if child else 0, 0), pady=(3, 3))
        line = frame(box)
        line.pack(fill='x')
        ws = []
        kind_, v = self.vars[oid]
        if kind == 'check':
            cb = ttk.Checkbutton(line, text=lab, variable=v, style='Studio.TCheckbutton')
            cb.pack(side='left')
            ws.append(cb)
        else:
            label(line, lab).pack(side='left')
            if kind in ('percent', 'number'):
                sp = ttk.Spinbox(line, from_=0, to=100 if kind == 'percent' else 10, increment=1 if kind == 'percent'
                                 else 0.1, textvariable=v, width=7, style='Studio.TSpinbox')
                sp.pack(side='left', padx=(8, 2))
                ws.append(sp)
                if kind == 'percent':
                    label(line, '%', style='Muted.TLabel').pack(side='left')
            elif kind == 'choice':
                ids = [c[0] for c in o['choices']]
                cb = ttk.Combobox(line, values=[CHOICE_TEXT.get(c, n) for c, n in o['choices']], state='readonly',
                                  width=26, style='Studio.TCombobox')
                cb.current(ids.index(v.get()))
                cb.bind('<<ComboboxSelected>>', lambda _e, v=v, cb=cb, ids=ids: v.set(ids[cb.current()]))
                cb.pack(side='left', padx=(8, 0))
                ws.append(cb)
        if help_:
            hl = label(box, help_, style='Muted.TLabel', wraplength=820, justify='left')
            hl.pack(anchor='w', padx=(21 if kind == 'check' else 0, 0))
        if o.get('dist'):
            spec = self.current_spec(oid)
            row = frame(box)
            row.pack(anchor='w', padx=(21 if kind == 'check' else 0, 0), pady=(1, 0))
            tag = 'Values:' if o['dist'] == 'numeric' else 'Picks from:'
            label(row, tag, style='Faint.TLabel').pack(side='left')
            sl = tk.Label(row, text=shape_text(spec) if o['dist'] == 'numeric' else pool_text(spec), bg=C['bg'],
                          fg=C['text'], font=(FONT, 9))
            sl.pack(side='left', padx=(6, 10))
            self.spec_labels[oid] = sl
            open_ = self.open_panel == oid
            lk = Link(row, 'Close' if open_ else ('Shape...' if o['dist'] == 'numeric' else 'Choose...'),
                      lambda oid=oid: self.toggle_panel(oid))
            lk.pack(side='left')
            if open_:
                panel = (ShapePanel if o['dist'] == 'numeric' else PoolPanel)(box, self, o)
                panel.pack(fill='x', padx=(21, 0), pady=(6, 8))
        self.rows_w[oid] = ws

    def toggle_panel(self, oid):
        self.open_panel = None if self.open_panel == oid else oid
        y = self.scroll.canvas.yview()[0]
        self.render_cat()
        self.update_idletasks()
        self.scroll.canvas.yview_moveto(y)
        panel = self._find_panel()
        if panel is not None:           # bring the opened editor into view (its option line stays visible above it)
            self.update_idletasks()
            body = self.scroll.body
            top = panel.winfo_rooty() - body.winfo_rooty() - 90
            bottom = top + panel.winfo_height() + 120
            view_h = self.scroll.canvas.winfo_height()
            total = max(1, body.winfo_height())
            first = self.scroll.canvas.yview()[0] * total
            if top < first or bottom > first + view_h:
                self.scroll.canvas.yview_moveto(max(0, top) / total)

    def _find_panel(self):
        stack = [self.scroll.body]
        while stack:
            x = stack.pop()
            if isinstance(x, (ShapePanel, PoolPanel)):
                return x
            stack.extend(x.winfo_children())
        return None

    def wake(self):
        """sub-options follow their parent (off parent = greyed sub-options)"""
        for oid, ws in getattr(self, 'rows_w', {}).items():
            on = self.parent_on(rz.OPTION[oid])
            for w in ws:
                try:
                    if isinstance(w, ttk.Combobox):
                        w.configure(state='readonly' if on else 'disabled')
                    else:
                        w.state(['!disabled'] if on else ['disabled'])
                except tk.TclError:
                    pass

    def bounds_grid(self, parent):
        label(parent, TEXT['bounds'][1], style='Muted.TLabel', wraplength=820, justify='left').pack(anchor='w')
        g = frame(parent)
        g.pack(anchor='w', pady=(8, 0))
        for c, t in enumerate(('', 'Lowest', 'Highest', 'Step')):
            label(g, t, style='Faint.TLabel').grid(row=0, column=c, padx=4, sticky='w')
        for r, (name, lab) in enumerate(rz.BOUND_LABELS.items(), start=1):
            label(g, lab, style='Muted.TLabel').grid(row=r, column=0, sticky='e', padx=(0, 8), pady=1)
            for c, v in enumerate(self.bound_vars[name]):
                ttk.Entry(g, textvariable=v, width=9, style='Studio.TEntry').grid(row=r, column=c + 1, padx=3, pady=1)

    # --- presets, settings files ----------------------------------------------------------------------------------
    def use_preset(self, key):
        over = {}
        for k, _n, o in PRESETS:
            over.update(o)
            if k == key:
                break
        if key == 'none':
            over = {}
        if any(self.is_on(o['id']) for o in rz.OPTIONS) and not messagebox.askyesno(
                'Randomize', 'Start from this preset? The options you set here are replaced (your shapes and pools '
                'stay).', parent=self):
            self.preset.pick('', notify=False)
            return
        s = copy.deepcopy(self.defaults)
        s.pop('dist_alt', None)
        s['dist'] = dict(self.settings.get('dist') or s.get('dist') or {})
        s['bounds'] = self.collect_bounds(quiet=True) or s.get('bounds')
        s.update(over)
        self.settings = s
        self.make_vars()
        self.render_nav()
        self.render_cat()
        self.update_summary()
        self.say(f'Started from "{dict((k, n) for k, n, _ in PRESETS)[key]}". Adjust anything, then press Randomize.')

    def collect_bounds(self, quiet=False):
        out = {}
        for name, vs in self.bound_vars.items():
            try:
                out[name] = [float(v.get()) if '.' in v.get() else int(v.get()) for v in vs]
            except ValueError:
                if quiet:
                    return None
                raise ValueError(f'limit "{rz.BOUND_LABELS[name]}": not a number')
        return out

    def collect(self, lenient=False):
        """the settings the page shows; lenient = a value that is not a number keeps the one held before"""
        s = copy.deepcopy(self.settings)
        for oid, (kind, v) in self.vars.items():
            if kind == 'check':
                s[oid] = bool(v.get())
            elif kind in ('percent', 'number'):
                try:
                    s[oid] = float(v.get())
                except ValueError:
                    if not lenient:
                        raise ValueError(f'"{TEXT.get(oid, (oid,))[0]}": "{v.get()}" is not a number')
            elif kind == 'choice':
                s[oid] = v.get()
        s['bounds'] = self.collect_bounds(quiet=lenient) or s.get('bounds')
        return s

    def kept_alts(self):
        """the pool / shape alternatives that differ from the game's defaults (kept with the settings)"""
        base = self.defaults.get('dist_alt') or {}
        out = {}
        for oid, alts in self.mem.items():
            for typ, spec in alts.items():
                if spec != (base.get(oid) or {}).get(typ):
                    out.setdefault(oid, {})[typ] = copy.deepcopy(spec)
        return out

    def leave(self):
        """the settings are kept whenever the page is left (another page, the window closed), as on every page"""
        if self.built:
            meta = self.s.project.meta
            s, alts, seed = self.collect(lenient=True), self.kept_alts(), self.seed.get().strip()
            if s != meta.get('randomizer') or alts != (meta.get('randomizer_alt') or {}) or \
                    seed != meta.get('randomizer_seed'):
                meta['randomizer'] = s
                meta['randomizer_alt'] = alts
                meta['randomizer_seed'] = seed
                self.s.project.save()
        return True

    def save_settings(self):
        try:
            s = self.collect()
        except ValueError as e:
            messagebox.showerror('Save settings', str(e), parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.json', filetypes=[('Randomizer settings', '*.json')])
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'udpre_randomizer': 1, 'seed': self.seed.get(), 'settings': s}, f, indent=1)
            self.say(f'Settings saved to {path}.')

    def load_settings(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Randomizer settings', '*.json')])
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            self.settings = d['settings']
            self.settings.pop('dist_alt', None)
            self.seed.set(str(d.get('seed', self.seed.get())))
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror('Load settings', f'Not a settings file: {e}', parent=self)
            return
        self.make_vars()
        self.render_nav()
        self.render_cat()
        self.update_summary()
        self.say(f'Settings loaded from {path}.')

    # --- summary, randomize ---------------------------------------------------------------------------------------
    def update_summary(self):
        on = [TEXT.get(o['id'], (o['label'],))[0] for o in rz.OPTIONS if self.is_on(o['id']) and not o.get('parent')
              and o['kind'] != 'number']
        coef = self.vars.get('level_coef')
        if coef and self.is_on('level_coef'):
            on.append(f'levels x{coef[1].get()}')
        prior = self.last_randomize()[0] is not None
        if on:
            t = f'{len(on)} change{"s" if len(on) != 1 else ""} will be drawn: ' + ', '.join(on[:14]) + \
                (f' and {len(on) - 14} more' if len(on) > 14 else '') + '.'
        else:
            t = 'Nothing is ticked yet - pick a preset above or tick what you want to reroll.'
        if prior:
            t += '   Randomize replaces the randomization your edits hold (your other edits stay).'
        self.summary.config(text=t)

    def randomize(self):
        try:
            s = self.collect()
            seed = int(self.seed.get())
        except ValueError as e:
            messagebox.showerror('Randomize', str(e), parent=self)
            return
        on = [o for o in rz.OPTIONS if self.is_on(o['id']) and not o.get('parent')]
        if not on:
            messagebox.showinfo('Randomize', 'Tick at least one thing to reroll first (or pick a preset).', parent=self)
            return
        old, used = self.last_randomize()
        if old is not None and not messagebox.askyesno(
                'Randomize', f'Your edits hold a randomization made with seed {used}. Replace it with a new one from '
                f'seed {seed}? (Your other edits stay.)', parent=self):
            return
        self.say('Randomizing...')
        self.update()
        op = {'op': 'randomize', 'seed': seed, 'settings': s}
        # a reroll takes the old randomization's place: edits made after it still go on top
        w = self.s.replace(old, op) if old is not None else self.s.run(op)
        self.s.project.meta['randomizer'] = s
        self.s.project.meta['randomizer_alt'] = self.kept_alts()
        self.s.project.meta['randomizer_seed'] = str(seed)
        self.s.project.save()
        self.settings = copy.deepcopy(s)
        self.app.edits_changed(f'Randomized with seed {seed}.' + (f' Notes: {w}' if w else '') +
                               ' Press Apply / Convert in the uDPRE window to put it into the game.')
        self.update_summary()
        self.update_seed_note()

    def refresh(self):
        if self.built:
            self.update_summary()
            self.update_seed_note()


class ShapePanel(tk.Frame):
    """how new numbers are drawn: a shape in words, its numbers, the share of values that change, and a preview of one
    draw over the values the game has now"""

    def __init__(self, master, page, o):
        super().__init__(master, bg=C['soft'], highlightthickness=1, highlightbackground=C['line'])
        self.page, self.o, self.oid = page, o, o['id']
        spec = dict(page.current_spec(self.oid) or dist.numeric('NR', std=10))
        self.alts = page.mem.setdefault(self.oid, {})
        self.alts[spec['type']] = dict(spec)          # the shape in use is the one the settings hold
        self.kind = tk.StringVar(value=spec['type'])
        self.p = tk.StringVar(value=_fmt(spec.get('p', 100)))
        left = tk.Frame(self, bg=C['soft'])
        left.pack(side='left', fill='y', padx=12, pady=10)
        tk.Label(left, text='How a new value is picked', bg=C['soft'], fg=C['text'], font=(FONT, 9, 'bold')).pack(
            anchor='w')
        for code, name, _args in SHAPES:
            tk.Radiobutton(left, text=name, value=code, variable=self.kind, bg=C['soft'], activebackground=C['soft'],
                           font=(FONT, 9), anchor='w', command=self.switch).pack(anchor='w')
        self.args_f = tk.Frame(left, bg=C['soft'])
        self.args_f.pack(anchor='w', pady=(8, 0))
        pf = tk.Frame(left, bg=C['soft'])
        pf.pack(anchor='w', pady=(8, 0))
        tk.Label(pf, text='Change', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left')
        sp = ttk.Spinbox(pf, from_=0, to=100, textvariable=self.p, width=6, style='Studio.TSpinbox',
                         command=self.read)
        sp.pack(side='left', padx=4)
        sp.bind('<KeyRelease>', lambda _e: self.read())
        tk.Label(pf, text='% of the values', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left')
        b = tk.Frame(left, bg=C['soft'])
        b.pack(anchor='w', pady=(10, 0))
        Button(b, 'Game\'s own default', self.default, small=True).pack(side='left')
        right = tk.Frame(self, bg=C['soft'])
        right.pack(side='left', fill='both', expand=True, padx=(4, 12), pady=10)
        self.cv = tk.Canvas(right, width=540, height=170, bg=C['bg'], highlightthickness=1,
                            highlightbackground=C['line'])
        self.cv.pack(anchor='w')
        self.stats = tk.Label(right, text='', bg=C['soft'], fg=C['muted'], font=(FONT, 9), justify='left', anchor='w')
        self.stats.pack(anchor='w', pady=(4, 0))
        self.vals = {}
        self.layout(spec)
        self.preview(spec)

    def layout(self, spec):
        for w in self.args_f.winfo_children():
            w.destroy()
        self.vals = {}
        code = self.kind.get()
        names = {'std': 'spread', 'min': 'from', 'max': 'to', 'mean': 'center'}
        for a in dist.ARGS[code]:
            tk.Label(self.args_f, text=names[a], bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left',
                                                                                                   padx=(0, 4))
            x = spec.get(a, 0)
            if code == 'NP' and a == 'std':
                x = x * 100
            v = tk.StringVar(value=_fmt(x))
            e = ttk.Entry(self.args_f, textvariable=v, width=8, style='Studio.TEntry')
            e.pack(side='left', padx=(0, 10))
            e.bind('<KeyRelease>', lambda _e: self.read())
            self.vals[a] = v
        if code == 'NP':
            tk.Label(self.args_f, text='%', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left')

    def spec(self):
        code = self.kind.get()
        try:
            args = {a: float(v.get()) for a, v in self.vals.items()}
            if code == 'NP' and 'std' in args:
                args['std'] /= 100
            return dist.numeric(code, float(self.p.get()), **args)
        except (ValueError, dist.DistError):
            return None

    def switch(self):
        nxt = self.alts.get(self.kind.get())
        if not nxt:
            nxt = dist.numeric_defaults(self.page.observed.get(self.oid, []))[self.kind.get()]
        spec = dict(nxt, p=float(self.p.get() or 100))
        self.layout(spec)
        self.read()

    def default(self):
        six = (self.page.defaults.get('dist_alt') or {}).get(self.oid) or \
            dist.numeric_defaults(self.page.observed.get(self.oid, []))
        spec = dict(six.get(self.kind.get()) or six['NR'])
        self.kind.set(spec['type'])
        self.p.set(_fmt(spec.get('p', 100)))
        self.layout(spec)
        self.read()

    def read(self):
        spec = self.spec()
        if spec is None:
            self.stats.config(text='Every field needs a number.')
            return
        self.page.set_spec(self.oid, spec)
        self.alts[spec['type']] = dict(spec)
        self.preview(spec)

    def bound(self):
        name = BOUND_OF.get(self.oid)
        if self.oid == 'trainer_item_count':
            return 0, 4, 1
        try:
            b = self.page.collect_bounds(quiet=True) or {}
        except Exception:
            b = {}
        return tuple(b.get(name) or rz.BOUNDS.get(name) or (0, 10 ** 9, 1))

    def preview(self, spec):
        obs = list(self.page.observed.get(self.oid, []))
        cv = self.cv
        cv.delete('all')
        if not obs:
            cv.create_text(270, 85, text='No values to preview', fill=C['faint'], font=(FONT, 9))
            return
        rng = random.Random(1234)
        sampler = dist.Numeric(spec)
        mn, mx, inc = self.bound()
        inc = inc or 1
        after = []
        changed = 0
        for x in obs:
            if mn <= x <= mx:
                y = sampler.draw(rng, x)
                y = int(max(mn, min(mx, round(y / inc) * inc)))
            else:
                y = x
            changed += y != x
            after.append(y)
        lo, hi = min(min(obs), min(after)), max(max(obs), max(after))
        if hi == lo:
            hi = lo + 1
        n = 30
        w = (hi - lo) / n
        h1, h2 = collections.Counter(), collections.Counter()
        for x in obs:
            h1[min(n - 1, int((x - lo) / w))] += 1
        for y in after:
            h2[min(n - 1, int((y - lo) / w))] += 1
        top = max(max(h1.values()), max(h2.values()))
        W, H, pad = 540, 170, 24
        bw = (W - 2 * pad) / n
        for k in range(n):
            x0 = pad + k * bw
            for h, col, off in ((h1, '#c4cbd6', 0), (h2, C['accent'], bw / 2)):
                bh = (H - 2 * pad) * h[k] / top
                cv.create_rectangle(x0 + off + 1, H - pad - bh, x0 + off + bw / 2, H - pad, fill=col, outline='')
        cv.create_line(pad, H - pad, W - pad, H - pad, fill=C['line2'])
        cv.create_text(pad, H - pad + 10, text=_fmt(lo), anchor='w', fill=C['muted'], font=(FONT, 8))
        cv.create_text(W - pad, H - pad + 10, text=_fmt(hi), anchor='e', fill=C['muted'], font=(FONT, 8))
        cv.create_rectangle(pad, 8, pad + 10, 16, fill='#c4cbd6', outline='')
        cv.create_text(pad + 14, 12, text='now', anchor='w', fill=C['muted'], font=(FONT, 8))
        cv.create_rectangle(pad + 54, 8, pad + 64, 16, fill=C['accent'], outline='')
        cv.create_text(pad + 68, 12, text='after one draw (preview)', anchor='w', fill=C['muted'], font=(FONT, 8))
        m1, m2 = sum(obs) / len(obs), sum(after) / len(after)
        self.stats.config(text=f'{len(obs):,} values in your game · average {m1:.1f} → {m2:.1f} · '
                               f'{100 * changed / len(obs):.0f}% change · limits {_fmt(mn)}-{_fmt(mx)}, step {_fmt(inc)}')


class PoolPanel(tk.Frame):
    """what a pick can land on: equal chances among the ticked choices, or weights"""

    def __init__(self, master, page, o):
        super().__init__(master, bg=C['soft'], highlightthickness=1, highlightbackground=C['line'])
        self.page, self.o, self.oid = page, o, o['id']
        g = page.s.game
        self.ents = rz.entities(g, o['entities'])
        self.names = dict(self.ents)
        spec = dict(page.current_spec(self.oid) or dist.empirical({}))
        self.alts = page.mem.setdefault(self.oid, {})
        self.alts[spec.get('type', 'empirical')] = dict(spec)   # the mode in use is the one the settings hold
        emp = self.alts.get('empirical') or {}
        uni = self.alts.get('uniform') or {}
        self.weights = {int(k): int(w) for k, w in dist.weight_pairs(emp.get('weights', []))}
        self.include = set(uni['include']) if 'include' in uni else {v for v, w in self.weights.items() if w > 0}
        self.p = tk.StringVar(value=_fmt(spec.get('p', 100)))
        top = tk.Frame(self, bg=C['soft'])
        top.pack(fill='x', padx=12, pady=(10, 4))
        self.mode = Segmented(top, [('empirical', 'Weighted'), ('uniform', 'Equal chances')], command=lambda _v: self.save(),
                              value='uniform' if spec.get('type') == 'uniform' else 'empirical')
        self.mode.pack(side='left')
        tk.Label(top, text='Change', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left', padx=(16, 4))
        sp = ttk.Spinbox(top, from_=0, to=100, textvariable=self.p, width=6, style='Studio.TSpinbox', command=self.save)
        sp.pack(side='left')
        sp.bind('<KeyRelease>', lambda _e: self.save())
        tk.Label(top, text='% of them', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left', padx=(4, 0))
        self.search = SearchBox(top, 'Filter...', on_change=lambda _t: self.render(), width=22)
        self.search.pack(side='right')
        mid = tk.Frame(self, bg=C['soft'])
        mid.pack(fill='x', padx=12)
        self.tree = ttk.Treeview(mid, columns=('in', 'name', 'w', 'share'), show='headings', height=11,
                                 selectmode='extended', style='Studio.Treeview')
        for c, t, w, a in (('in', 'In', 40, 'center'), ('name', 'Choice', 300, 'w'), ('w', 'Weight', 70, 'e'),
                           ('share', 'Share', 80, 'e')):
            self.tree.heading(c, text=t, anchor=a)
            self.tree.column(c, width=w, anchor=a, stretch=c == 'name')
        sb = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='x', expand=True)
        sb.pack(side='left', fill='y')
        self.tree.bind('<Double-1>', lambda _e: self.mark(None))
        self.tree.bind('<space>', lambda _e: self.mark(None))
        bar = tk.Frame(self, bg=C['soft'])
        bar.pack(fill='x', padx=12, pady=(6, 10))
        for t, fn in (('Tick selected', lambda: self.mark(True)), ('Untick selected', lambda: self.mark(False)),
                      ('All', self.all), ('None', self.none), ('As the game has them', self.reset)):
            Button(bar, t, fn, small=True).pack(side='left', padx=(0, 4))
        tk.Label(bar, text='Weight of selected', bg=C['soft'], fg=C['muted'], font=(FONT, 9)).pack(side='left',
                                                                                                    padx=(14, 4))
        self.wv = tk.StringVar(value='12')
        ttk.Entry(bar, textvariable=self.wv, width=6, style='Studio.TEntry').pack(side='left')
        Button(bar, 'Set', self.set_weight, small=True).pack(side='left', padx=(4, 0))
        self.render()

    def uniform(self):
        return self.mode.get() == 'uniform'

    def render(self):
        t = self.search.get_text().lower()
        sel = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        tot = sum(w for w in self.weights.values() if w > 0) if not self.uniform() else len(self.include)
        for v, name in self.ents:
            if t and t not in str(name).lower():
                continue
            if self.uniform():
                on = v in self.include
                w, share = '', (f'{100 / tot:.1f}%' if on and tot else '')
            else:
                w = self.weights.get(v, 0)
                on = w > 0
                share = f'{100 * w / tot:.1f}%' if on and tot else ''
            iid = str(v)
            self.tree.insert('', 'end', iid=iid, values=('✓' if on else '', name, w, share))
            if iid in sel:
                self.tree.selection_add(iid)

    def mark(self, on):
        for iid in self.tree.selection():
            v = int(iid)
            cur = v in self.include if self.uniform() else self.weights.get(v, 0) > 0
            state = (not cur) if on is None else on
            if self.uniform():
                (self.include.add if state else self.include.discard)(v)
            else:
                self.weights[v] = (self.weights.get(v) or 12) if state else 0
                if state and self.weights[v] <= 0:
                    self.weights[v] = 12
        self.save()

    def all(self):
        if self.uniform():
            self.include = {v for v, _ in self.ents}
        else:
            self.weights = {v: (self.weights.get(v) or 12) for v, _ in self.ents}
        self.save()

    def none(self):
        if self.uniform():
            self.include = set()
        else:
            self.weights = {}
        self.save()

    def reset(self):
        alt = (self.page.defaults.get('dist_alt') or {}).get(self.oid) or {}
        self.weights = {int(k): int(w) for k, w in dist.weight_pairs((alt.get('empirical') or {}).get('weights', []))}
        self.include = set((alt.get('uniform') or {}).get('include', []))
        self.save()

    def set_weight(self):
        try:
            w = max(0, int(float(self.wv.get())))
        except ValueError:
            return
        for iid in self.tree.selection():
            self.weights[int(iid)] = w
        if self.uniform():
            self.mode.pick('empirical', notify=False)
        self.save()

    def save(self):
        try:
            p = float(self.p.get())
        except ValueError:
            p = 100.0
        self.alts['empirical'] = dist.empirical({v: w for v, w in self.weights.items() if w}, p)
        self.alts['uniform'] = dist.uniform(self.include, p)
        self.page.set_spec(self.oid, self.alts['uniform' if self.uniform() else 'empirical'])
        self.render()
