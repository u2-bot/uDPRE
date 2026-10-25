"""Pokémon: one personal row (a species or one of its forms) - profile (stats, typing, abilities, wild held items, growth
and breeding, dex data), level-up and egg moves, TM compatibility, evolutions, and where it appears in the game
(PersonalTable, WazaOboeTable, TamagoWazaTable, EvolveTable of Pml/personal_masterdatas)."""
import tkinter as tk
from tkinter import ttk

from ... import enums
from ...game import PERSONAL, STATS
from ...project import set_op
from ..kit import Button, Link, Section, Segmented, frame, label, pill, type_pill
from ..page import RecordPage
from ..theme import C, FONT, stat_color, type_color
from ..widgets import FieldSet, Form, IntField, Table

# PersonalTable.exp_value = the EV yield: 2 bits per stat (game: PersonalSystem ParamID.EFFORT_*)
EV_BITS = [('ev_hp', 0, 'HP'), ('ev_atk', 2, 'Atk'), ('ev_def', 4, 'Def'), ('ev_agi', 6, 'Spe'),
           ('ev_spatk', 8, 'SpA'), ('ev_spdef', 10, 'SpD')]
SHORT = ['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed']
PERSONAL_OBJS = {'PersonalTable', 'WazaOboeTable', 'EvolveTable', 'TamagoWazaTable'}
VIEWS = [('profile', 'Profile'), ('moves', 'Moves'), ('tms', 'TMs'), ('evo', 'Evolution'), ('where', 'Where it appears')]


def ev_unpack(v):
    return {k: (v >> sh) & 3 for k, sh, _ in EV_BITS}


def ev_pack(old, vals):
    v = old
    for k, sh, _ in EV_BITS:
        v = (v & ~(3 << sh)) | ((int(vals.get(k, 0)) & 3) << sh)
    return v


def plural(n, word):
    return f'{n} {word}{"" if n == 1 else "s"}'


def gender_text(v):
    v = int(v or 0)
    if v == 255:
        return 'genderless'
    if v == 254:
        return 'always female'
    if v == 0:
        return 'always male'
    female = v / 256 * 100
    return f'about {100 - female:.0f}% male, {female:.0f}% female'


class PokemonPage(RecordPage):
    title = 'Pokémon'
    subtitle = 'Every Pokémon and form: stats, typing, moves, TMs, evolutions - and where each one appears'
    noun = 'Pokémon'
    nouns = 'Pokémon'
    columns = [('no', 'No.', 52, 'e'), ('name', 'Name', 150, 'w'), ('types', 'Types', 112, 'w'), ('bst', 'BST', 46, 'e')]
    list_width = 400

    # --- table ----------------------------------------------------------------------------------------------------
    def extra_left(self, f):
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.type_filter = ttk.Combobox(row, values=['All types'] + [n for _, n in self.c.types()], state='readonly',
                                        width=16, style='Studio.TCombobox')
        self.type_filter.current(0)
        self.type_filter.pack(side='left')
        self.type_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))

    def _apply_filters(self):
        k = self.type_filter.current() - 1
        ed = self.only_edited.get()

        def pred(key, _vals):
            if ed and key not in self.table.edited:
                return False
            if k >= 0:
                r = self.s.game.row(*key)
                return r is not None and k in (r['type1'], r['type2'])
            return True
        self.table.filter(pred=pred)
        self._count()

    def rows(self):
        return [(k, self._values(k)) for k, _lab in self.c.species() if k != (0, 0)]

    def row(self, key):
        return self._values(key)

    def _values(self, key):
        g = self.s.game
        r = g.row(*key)
        types = g.type_name(r['type1']) + ('' if r['type2'] == r['type1'] else ' / ' + g.type_name(r['type2']))
        name = g.pokemon_name(*key) + (f'  (form {key[1]})' if key[1] else '')
        return (f'{key[0]:03d}', name, types, sum(r[s] for s in STATS))

    def op_key(self, op):
        if op.get('op') == 'set' and op.get('obj') in PERSONAL_OBJS and isinstance(op.get('key'), list):
            return tuple(op['key'])
        if op.get('op') == 'eggmoves':
            return tuple(op['key'])
        return None

    def record_name(self, key):
        return self.s.game.pokemon_name(*key)

    # --- record ---------------------------------------------------------------------------------------------------
    def build(self, body):
        c = self.c
        self.views = Segmented(body, VIEWS, command=self.switch, value='profile')
        self.views.pack(anchor='w', pady=(4, 12))
        self.frames = {v: frame(body) for v, _ in VIEWS}
        p = self.frames['profile']
        st = Section(p, 'Base stats', hint='EV yield = the effort points it gives when beaten (0-3 per stat)')
        st.pack(fill='x')
        grid = frame(st.body)
        grid.pack(anchor='w')
        label(grid, 'Base', style='Faint.TLabel').grid(row=0, column=1, sticky='w')
        label(grid, 'EV yield', style='Faint.TLabel').grid(row=0, column=3, sticky='w', padx=(14, 0))
        stat_w, ev_w, self.bar_cv = {}, {}, {}
        ev_of = {'basic_hp': 'ev_hp', 'basic_atk': 'ev_atk', 'basic_def': 'ev_def', 'basic_spatk': 'ev_spatk',
                 'basic_spdef': 'ev_spdef', 'basic_agi': 'ev_agi'}
        for r, (k, n) in enumerate(zip(STATS, SHORT), start=1):
            label(grid, n, style='Muted.TLabel', width=8, anchor='e').grid(row=r, column=0, sticky='e', padx=(0, 6), pady=2)
            stat_w[k] = IntField(grid, 0, 255, width=5)
            stat_w[k].grid(row=r, column=1, sticky='w', pady=2)
            stat_w[k].bind('<KeyRelease>', lambda _e: self._bars())
            stat_w[k].configure(command=self._bars)
            cv = tk.Canvas(grid, width=300, height=16, bg=C['bg'], highlightthickness=0)
            cv.grid(row=r, column=2, sticky='w', padx=(10, 0))
            self.bar_cv[k] = cv
            ev_w[ev_of[k]] = IntField(grid, 0, 3, width=3)
            ev_w[ev_of[k]].grid(row=r, column=3, sticky='w', padx=(14, 0), pady=2)
        label(grid, 'Total', style='Muted.TLabel', width=8, anchor='e').grid(row=7, column=0, sticky='e', padx=(0, 6),
                                                                             pady=(4, 0))
        self.total = tk.Label(grid, text='', bg=C['bg'], fg=C['text'], font=(FONT, 11, 'bold'))
        self.total.grid(row=7, column=1, sticky='w', pady=(4, 0))
        self.stats = self.track(FieldSet(stat_w))
        self.evs = self.track(FieldSet(ev_w))
        ty = Section(p, 'Typing and abilities')
        ty.pack(fill='x', pady=(16, 0))
        self.main = self.track(Form(ty.body, [
            ('Type 1', 'type1', 'choice', c.types()), ('Type 2', 'type2', 'choice', c.types()),
            ('Ability 1', 'tokusei1', 'choice', c.abilities()), ('Ability 2', 'tokusei2', 'choice', c.abilities()),
            ('Hidden ability', 'tokusei3', 'choice', c.abilities()),
        ], columns=2, label_width=14))
        self.main.pack(anchor='w')
        held = Section(p, 'Held when found in the wild')
        held.pack(fill='x', pady=(16, 0))
        self.held = self.track(Form(held.body, [
            ('Common (50%)', 'item1', 'choice', c.items()), ('Rare (5%)', 'item2', 'choice', c.items()),
            ('Third slot', 'item3', 'choice', c.items())], columns=2, label_width=14))
        self.held.pack(anchor='w')
        gr = Section(p, 'Growth and breeding')
        gr.pack(fill='x', pady=(16, 0))
        self.misc = self.track(Form(gr.body, [
            ('Catch rate', 'get_rate', 'int', (0, 255)), ('Base friendship', 'initial_friendship', 'int', (0, 255)),
            ('EXP yield', 'give_exp', 'int', (0, 65535)), ('Growth rate', 'grow', 'choice', enums.GROWTH_RATES),
            ('Gender ratio', 'sex', 'int', (0, 255)), ('Egg cycles', 'egg_birth', 'int', (0, 255)),
            ('Egg group 1', 'egg_group1', 'choice', enums.EGG_GROUPS), ('Egg group 2', 'egg_group2', 'choice', enums.EGG_GROUPS),
            ('Hatches as', 'egg_monsno', 'choice', c.species0()), ('Hatch form', 'egg_formno', 'int', (0, 255)),
        ], columns=2, label_width=14))
        self.misc.pack(anchor='w')
        self.gender = label(gr.body, '', style='Muted.TLabel')
        self.gender.pack(anchor='w', pady=(4, 0))
        self.misc.widgets['sex'].bind('<KeyRelease>', lambda _e: self._gender())
        self.misc.widgets['sex'].configure(command=self._gender)
        dx = Section(p, 'Pokédex and appearance')
        dx.pack(fill='x', pady=(16, 0))
        self.dex = self.track(Form(dx.body, [
            ('Color', 'color', 'choice', enums.COLORS), ('Height (cm)', 'height', 'int', (0, 65535)),
            ('Weight (0.1 kg)', 'weight', 'int', (0, 65535)), ('Sinnoh dex no.', 'chihou_zukan_no', 'int', (0, 65535)),
            ('Graphic no.', 'gra_no', 'int', (0, 65535)), ('Rank', 'rank', 'int', (0, 255)),
            ('In the game', 'valid_flag', 'bool'),
        ], columns=2, label_width=14))
        self.dex.pack(anchor='w')
        # moves
        m = self.frames['moves']
        cols = frame(m)
        cols.pack(fill='both', expand=True)
        lf = Section(cols, 'Level-up moves', hint='level 0 = learned on evolving')
        lf.pack(side='left', fill='both', expand=True, padx=(0, 24))
        self.learn = self.track(Table(lf.body, [('Level', 'int', (0, 255), 60), ('Move', 'choice', c.moves(), 240)],
                                      height=20, new_row=lambda: [1, 0]))
        self.learn.pack(fill='both', expand=True)
        ef = Section(cols, 'Egg moves')
        ef.pack(side='left', fill='both', expand=True)
        self.eggs = self.track(Table(ef.body, [('Move', 'choice', c.moves(), 240)], height=20, new_row=lambda: [0]))
        self.eggs.pack(fill='both', expand=True)
        label(m, 'Double-click a cell to change it.', style='Faint.TLabel').pack(anchor='w', pady=(6, 0))
        # TMs
        t = self.frames['tms']
        bar = frame(t)
        bar.pack(fill='x')
        self.tm_count = label(bar, '', style='Section.TLabel')
        self.tm_count.pack(side='left')
        for text, fn in (('None', lambda: self._tm_all(False)), ('All', lambda: self._tm_all(True)),
                         ('Its own types only', self._tm_stab)):
            Button(bar, text, fn, small=True).pack(side='right', padx=(6, 0))
        self.tm_grid = frame(t)
        self.tm_grid.pack(fill='x', pady=(10, 0))
        self.tm_vars = {}
        g = self.s.game
        self.tm_moves = {}
        for k, (bit, tm, it) in enumerate(sorted(g.tm_list(), key=lambda x: x[0])):
            v = tk.BooleanVar()
            v.trace_add('write', lambda *_a: self._tm_label())
            cell = frame(self.tm_grid)
            cell.grid(row=k // 4, column=k % 4, sticky='w', padx=(0, 18), pady=1)
            mv = next((x for x in g.moves if x['wazaNo'] == tm['wazaNo']), None)
            tcol = type_color(mv['type']) if mv else C['faint']
            tk.Frame(cell, width=4, height=16, bg=tcol).pack(side='left', padx=(0, 4))
            ttk.Checkbutton(cell, text=f'{g.item_name(it["no"])}  {g.move_name(tm["wazaNo"])}', variable=v,
                            style='Studio.TCheckbutton').pack(side='left')
            self.tm_vars[bit] = v
            self.tm_moves[bit] = mv
        # evolution
        e = self.frames['evo']
        self.evo_from = frame(e)
        self.evo_from.pack(fill='x')
        es = Section(e, 'Evolves into', hint='method, its parameter (item / move / species / type, or a number), result')
        es.pack(fill='both', expand=True, pady=(12, 0))
        top_m = max([x[0] for r in g.personal for x in g.evolution_list(r)] + [47])
        top_m = max(top_m, int((getattr(g, 'hints', None) or {}).get('evolutionMethodCount') or 0) - 1)
        methods = enums.EVOLVE_METHODS + [(k, f'Method {k}') for k in range(48, top_m + 1)]
        self.evos = self.track(Table(es.body, [('How', 'choice', methods, 190), ('With', 'choice', self._param_choices, 160),
                                               ('Becomes', 'choice', c.species0(), 160),
                                               ('Form', 'choice', self._form_choices, 100),
                                               ('Level', 'int', (0, 65535), 50)], height=10,
                                     new_row=lambda: [4, 0, 0, 0, 1], on_change=self._evo_changed))
        self.evos.pack(fill='both', expand=True)
        # where it appears
        self.where = frame(self.frames['where'])
        self.where.pack(fill='both', expand=True)
        self._refs = None
        self.switch('profile')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        if view == 'where' and self.key is not None:
            self._where()
        if self.scroller is not None:
            self.scroller.top()

    def show(self, key):
        g = self.s.game
        r = g.row(*key)
        pills = [type_pill(self.pill_parent(), g, r['type1'])]
        if r['type2'] != r['type1']:
            pills.append(type_pill(self.pill_parent(), g, r['type2']))
        pills.append(pill(self.pill_parent(), f'BST {sum(r[s] for s in STATS)}', C['soft'], C['muted']))
        sub = f'No. {key[0]:03d}' + (f' · form {key[1]}' if key[1] else '') + f' · personal row {r["id"]}'
        if not r.get('valid_flag', 1):
            sub += ' · not in the game (its "In the game" box is off)'
        self.set_header(g.pokemon_name(*key), sub, pills)
        for form in (self.stats, self.main, self.held, self.misc, self.dex):
            form.load(r)
        self._bars()
        self._gender()
        self.evs.load(ev_unpack(r['exp_value']))
        self.learn.set_rows([list(x) for x in g.learnset(r)])
        er = g.egg_row(*key)
        self.eggs.set_rows([[mv] for mv in (er['wazaNo'] if er else [])])
        bits = g.tm_bits(r)
        for b, v in self.tm_vars.items():
            v.set(bool(bits[b]) if b < len(bits) else False)
        self._tm_label()
        self.evos.set_rows([[x[0], x[1], x[2], x[3], x[4]] for x in g.evolution_list(r)])
        self._evo_from(key)
        if getattr(self, 'view', None) == 'where':
            self._where()

    def extra_state(self):
        return tuple(v.get() for v in self.tm_vars.values())

    def collect(self, key):
        g = self.s.game
        r = g.row(*key)
        ops = []
        new = {}
        for form in (self.stats, self.main, self.held, self.misc, self.dex):
            new.update(form.values())
        new['exp_value'] = ev_pack(r['exp_value'], self.evs.values())
        for f, v in new.items():
            if f in r and r[f] != v:
                ops.append(set_op(g, PERSONAL, 'PersonalTable', 'Personal', r, f, v))
        bits = g.tm_bits(r)
        for b, v in self.tm_vars.items():
            if b < len(bits):
                bits[b] = int(v.get())
        tmp = dict(r)
        g.set_tm_bits(tmp, bits)
        ch = g.tm_learnset_json(r, bits)            # a mod's 256-TM set (ExtraData) changes with it
        for w in ('machine1', 'machine2', 'machine3', 'machine4'):
            if w in r and tmp[w] != r[w]:
                ops.append(set_op(g, PERSONAL, 'PersonalTable', 'Personal', r, w, tmp[w]))
        if ch:
            g.set_extradata(*ch)
            ops.append({'op': 'extradata', 'path': ch[0], 'json': ch[1]})
        learn = [(int(a), int(b)) for a, b in self.learn.get_rows() if b]        # row order kept (Move up / down)
        if learn != g.learnset(r):
            ar = [v for pair in learn for v in pair]
            ops.append(set_op(g, PERSONAL, 'WazaOboeTable', 'WazaOboe', g.learnsets[r['id']], 'ar', ar, key=list(key)))
        er = g.egg_row(*key)
        eggs = [int(mv[0]) for mv in self.eggs.get_rows() if mv[0]]
        if er is not None and eggs != list(er['wazaNo']):
            ops.append(set_op(g, PERSONAL, 'TamagoWazaTable', 'Data', er, 'wazaNo', eggs))
        elif er is None and eggs:
            g.set_egg_moves(key[0], key[1], eggs)
            ops.append({'op': 'eggmoves', 'key': list(key), 'moves': eggs})
        evos = [tuple(int(x or 0) for x in ev) for ev in self.evos.get_rows() if ev[0]]
        if evos != g.evolution_list(r):
            ar = [v for ev in evos for v in ev]
            ops.append(set_op(g, PERSONAL, 'EvolveTable', 'Evolve', g.evolutions[r['id']], 'ar', ar, key=list(key)))
        return ops

    # --- profile helpers ------------------------------------------------------------------------------------------
    def _bars(self):
        v = self.stats.values()
        for k, cv in self.bar_cv.items():
            x = int(v.get(k, 0) or 0)
            cv.delete('all')
            cv.create_rectangle(0, 3, 300, 13, fill=C['soft'], outline='')
            cv.create_rectangle(0, 3, max(2, int(300 * min(x, 255) / 255)), 13, fill=stat_color(x), outline='')
        self.total.config(text=str(sum(int(v.get(k, 0) or 0) for k in STATS)))

    def _gender(self):
        v = self.misc.widgets['sex'].get_value()
        self.gender.config(text=f'Gender ratio {v} = {gender_text(v)}.   0 always male · 127 half · 254 always female · '
                                f'255 genderless' if v is not None else '')

    # --- TMs ------------------------------------------------------------------------------------------------------
    def _tm_label(self):
        n = sum(1 for v in self.tm_vars.values() if v.get())
        self.tm_count.config(text=f'Learns {n} of {len(self.tm_vars)} TMs')

    def _tm_all(self, on):
        for v in self.tm_vars.values():
            v.set(on)

    def _tm_stab(self):
        t = (self.main.widgets['type1'].get_value(), self.main.widgets['type2'].get_value())
        for b, v in self.tm_vars.items():
            mv = self.tm_moves.get(b)
            v.set(bool(mv and mv['type'] in t))

    # --- evolution ------------------------------------------------------------------------------------------------
    def _param_choices(self, row):
        kind = enums.EVOLVE_PARAM.get(row[0] if row else 0)
        return {'item': self.c.items(), 'move': self.c.moves(), 'species': self.c.species0(),
                'type': self.c.types()}.get(kind)

    def _form_choices(self, row):
        g = self.s.game
        dex = row[2] if row else 0
        forms = g.forms(dex) if dex else []
        return [(g.form_of(r), f'{g.form_of(r)} {g.pokemon_name(dex, g.form_of(r))}') for r in forms] or [(0, '0')]

    def _evo_changed(self, row, col, _old):
        """a new destination starts at its form 0; a new method at parameter 0"""
        if col == 2:
            row[3] = 0
        elif col == 0:
            row[1] = 0

    def _evo_from(self, key):
        for w in self.evo_from.winfo_children():
            w.destroy()
        g = self.s.game
        srcs = []
        for r in g.personal:
            for x in g.evolution_list(r):
                if x[2] == key[0] and x[3] == key[1] and r['id']:
                    srcs.append((g.key_of(r), x))
        sec = Section(self.evo_from, 'Evolves from')
        sec.pack(fill='x')
        if not srcs:
            label(sec.body, 'Nothing evolves into it - it is the first stage (or a Pokémon of its own).',
                  style='Muted.TLabel').pack(anchor='w')
        meth = dict(enums.EVOLVE_METHODS)
        for k, x in srcs:
            row = frame(sec.body)
            row.pack(anchor='w')
            Link(row, g.pokemon_name(*k), lambda k=k: self.goto(k)).pack(side='left')
            how = meth.get(x[0], f'method {x[0]}') + (f', level {x[4]}' if x[4] else '')
            label(row, f'   {how}', style='Muted.TLabel').pack(side='left')

    # --- where it appears -----------------------------------------------------------------------------------------
    def refresh(self):
        self._refs = None
        super().refresh()

    def references(self):
        """{monsno: {'wild': {(zone, version)}, 'special': {...}, 'trainers': {(i, level)}, 'tower': {pid}}}"""
        if self._refs is not None:
            return self._refs
        g = self.s.game
        refs = {}

        def add(mon, kind, what):
            refs.setdefault(mon & 0xFFFF, {}).setdefault(kind, set()).add(what)
        for ver, tree in g.encounter_files():
            for z in tree['table']:
                for f, v in z.items():
                    if isinstance(v, list) and v and isinstance(v[0], dict) and 'monsNo' in v[0]:
                        for s in v:
                            if s['monsNo']:
                                add(s['monsNo'], 'wild', (z['zoneID'], ver))
            for r in tree.get('urayama', []):
                add(r['monsNo'], 'special', f'Trophy Garden ({ver.upper()})')
            for r in tree.get('mistu', []):
                for f in ('Normal', 'Rare', 'SuperRare'):
                    add(r[f], 'special', f'Honey trees ({ver.upper()})')
            for r in tree.get('safari', []):
                add(r['MonsNo'], 'special', f'Great Marsh ({ver.upper()})')
        for i in range(len(g.trainers)):
            p = g.trainer_party(i)
            for s in (g.party_slots(p) if p else []):
                if s.get('MonsNo'):
                    add(s['MonsNo'], 'trainers', (i, s.get('Level', 0)))
        for p in g.tower['TrainerPoke']:
            add(p['MonsNo'], 'tower', p['ID'])
        self._refs = refs
        return refs

    def _where(self):
        for w in self.where.winfo_children():
            w.destroy()
        g = self.s.game
        refs = self.references().get(self.key[0], {})
        if not refs:
            label(self.where, 'It does not appear in any wild area, trainer party or Battle Tower set.',
                  style='Muted.TLabel').pack(anchor='w')
        wild = sorted(refs.get('wild', ()))
        if wild:
            sec = Section(self.where, 'Wild areas', hint=plural(len({z for z, _ in wild}), 'area') + ' - click to open')
            sec.pack(fill='x', pady=(0, 14))
            zones = {}
            for z, ver in wild:
                zones.setdefault(z, []).append(ver.upper())
            box = frame(sec.body)
            box.pack(fill='x')
            for k, (z, vers) in enumerate(sorted(zones.items())):
                Link(box, f'{g.zone_name(z)}  ({"/".join(vers)})', lambda z=z: self.app.show('wild', z)).grid(
                    row=k // 3, column=k % 3, sticky='w', padx=(0, 24))
        if refs.get('special'):
            sec = Section(self.where, 'Special encounters')
            sec.pack(fill='x', pady=(0, 14))
            for what in sorted(refs['special']):
                Link(sec.body, what, lambda: self.app.show('special')).pack(anchor='w')
        tr = sorted(refs.get('trainers', ()))
        if tr:
            sec = Section(self.where, 'Trainers', hint=plural(len({i for i, _ in tr}), 'trainer') + ' - click to open')
            sec.pack(fill='x', pady=(0, 14))
            box = frame(sec.body)
            box.pack(fill='x')
            seen = {}
            for i, lv in tr:
                seen.setdefault(i, []).append(lv)
            for k, (i, lvs) in enumerate(sorted(seen.items())[:150]):
                t = g.trainers[i]
                Link(box, f'{g.trainer_type_name(t["TypeID"])} {g.trainer_name(i)}  (Lv. {", ".join(map(str, lvs))})',
                     lambda i=i: self.app.show('trainers', i)).grid(row=k // 3, column=k % 3, sticky='w', padx=(0, 24))
            if len(seen) > 150:
                label(sec.body, f'... and {len(seen) - 150} more', style='Muted.TLabel').pack(anchor='w')
        if refs.get('tower'):
            sec = Section(self.where, 'Battle Tower sets')
            sec.pack(fill='x')
            ids = sorted(refs['tower'])
            box = frame(sec.body)
            box.pack(fill='x')
            for k, pid in enumerate(ids[:60]):
                Link(box, f'Set {pid}', lambda pid=pid: self.app.show('tower', ('set', pid))).grid(
                    row=k // 6, column=k % 6, sticky='w', padx=(0, 18))
            if len(ids) > 60:
                label(sec.body, f'... and {len(ids) - 60} more', style='Muted.TLabel').pack(anchor='w')

