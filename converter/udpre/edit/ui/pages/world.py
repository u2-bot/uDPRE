"""World: wild areas (FieldEncountTable_d / _p of gamesettings - per-zone slot lists, rates, forms and the unused GBA
dual-slot lists), special encounters (Trophy Garden, honey trees, Great Marsh) and the Underground (ugdata: levels by
progress, area -> spawn table, spawn tables, rare spawns).

Encounter slot values: monsNo = species | form << 16 (Luminescent puts forms there; the dump never does)."""
import copy
import tkinter as tk
from tkinter import ttk

from ...game import GAMESETTINGS, UGDATA
from ...project import set_op
from ..kit import Button, DataTable, Link, Scroll, Section, Segmented, frame, label
from ..page import Page, RecordPage
from ..theme import C, FONT, type_color
from ..widgets import FieldSet, IntField, Picker, Table

VERSIONS = [('d', 'Brilliant Diamond'), ('p', 'Shining Pearl')]
VERSION_COLORS = {'d': '#2f5fb3', 'p': '#c2417e'}
VERSION_SHORT = {'d': 'BD', 'p': 'SP'}
# slot lists of a zone: (field, title, rate labels)
GROUND = ('ground_mons', 'Ground', ['20%', '20%', '10% (morning)', '10% (morning)', '10%', '10%', '5%', '5%', '4%', '4%',
                                    '1%', '1%'])
ZONE_LISTS = [GROUND, ('tairyo', 'Swarm', ['20%', '20%']), ('day', 'Day', ['10%', '10%']),
              ('night', 'Night', ['10%', '10%']), ('swayGrass', 'Poke Radar', ['10%', '10%', '1%', '1%']),
              ('water_mons', 'Surf', ['60%', '30%', '5%', '4%', '1%']),
              ('boro_mons', 'Old Rod', ['60%', '30%', '5%', '4%', '1%']),
              ('ii_mons', 'Good Rod', ['60%', '30%', '5%', '4%', '1%']),
              ('sugoi_mons', 'Super Rod', ['60%', '30%', '5%', '4%', '1%'])]
GBA_LISTS = [('gbaRuby', 'Dual slot: Ruby'), ('gbaSapp', 'Dual slot: Sapphire'), ('gbaEme', 'Dual slot: Emerald'),
             ('gbaFire', 'Dual slot: FireRed'), ('gbaLeaf', 'Dual slot: LeafGreen')]
RATES = [('encRate_gr', 'Ground'), ('encRate_wat', 'Surf'), ('encRate_turi_boro', 'Old Rod'),
         ('encRate_turi_ii', 'Good Rod'), ('encRate_sugoi', 'Super Rod')]
UG_PROGRESSION = ['1 badge', '2 badges', '3 badges', '4 badges', '5 badges', '6 badges', '7 badges', '8 badges', 'Post-game']
UG_AREAS = {2: 'Spacious Cave', 3: 'Grassland Cave', 4: 'Fountainspring Cave', 5: 'Rocky Cave', 6: 'Volcanic Cave',
            7: 'Swampy Cave', 8: 'Dazzling Cave', 9: 'Whiteout Cave', 10: 'Icy Cave', 11: 'Riverbank Cave',
            12: 'Sandsear Cave', 13: 'Still-Water Cavern', 14: 'Sunlit Cavern', 15: 'Big Bluff Cavern',
            16: 'Stargleam Cavern', 17: 'Glacial Cavern', 18: 'Bogsunk Cavern', 19: 'Typhlo Cavern'}
UG_VERSIONS = [(1, 'Both'), (2, 'Brilliant Diamond'), (3, 'Shining Pearl')]
UG_REQUIREMENTS = [(1, 'None'), (2, 'Strength'), (3, 'Defog'), (4, '7 badges'), (5, 'Waterfall'), (6, 'National Dex')]

# how each list is shown on the page: (field, title, hint)
LAND_VIEW = [('tairyo', 'Swarm', 'replaces the two 20% slots while a mass outbreak is on'),
             ('day', 'Day', 'replaces the two 10% morning slots in the daytime'),
             ('night', 'Night', 'replaces the two 10% morning slots at night'),
             ('swayGrass', 'Poké Radar', 'replaces four slots (10%, 10%, 1%, 1%) while the Poké Radar is in use')]
WATER_VIEW = [('water_mons', 'Surfing', 'encRate_wat'), ('boro_mons', 'Old Rod', 'encRate_turi_boro'),
              ('ii_mons', 'Good Rod', 'encRate_turi_ii'), ('sugoi_mons', 'Super Rod', 'encRate_sugoi')]
METHOD_TITLES = {'ground_mons': 'Grass and caves', 'tairyo': 'Swarm', 'day': 'Day', 'night': 'Night',
                 'swayGrass': 'Poké Radar', 'water_mons': 'Surfing', 'boro_mons': 'Old Rod', 'ii_mons': 'Good Rod',
                 'sugoi_mons': 'Super Rod'}
LIVE_LISTS = [f for f, _, _ in ZONE_LISTS]
WILD_VIEWS = [('glance', 'At a glance'), ('land', 'Grass & caves'), ('water', 'Water'), ('rates', 'Rates & forms'),
              ('gba', 'Unused GBA slots')]
KINDS = ['All areas', 'Grass or cave', 'Surfing', 'Fishing', 'Swarm', 'Poké Radar', 'No wild Pokémon']


def split(v):
    return v & 0xFFFF, v >> 16


def join(species, form):
    return int(species) | (int(form) << 16)


def slot_rows(slots, labels):
    out = []
    for k, s in enumerate(slots):
        sp, fo = split(s['monsNo'])
        out.append([sp, fo, s['minlv'], s['maxlv'], labels[k] if k < len(labels) else 'n/a'])
    return out


def rows_slots(rows, old):
    """table rows -> slot dicts (same count as the file has; keys as the file has them)"""
    out = []
    for r, o in zip(rows, old):
        s = dict(o)
        s['monsNo'], s['minlv'], s['maxlv'] = join(r[0], r[1]), int(r[2]), int(r[3])
        out.append(s)
    return out


def rate_value(lab):
    try:
        return float(str(lab).split('%', 1)[0])
    except ValueError:
        return 0.0


def plural(n, word):
    return f'{n} {word}{"" if n == 1 else "s"}'


# --- a grid of inline fields (fixed-count lists: no rows added or removed) ------------------------------------------
class RowGrid(ttk.Frame):
    """Rows of inline fields, edited in place. columns = [(title, kind, extra, width)], kind:
    'rate' (a shown-only value as a chip), 'label' (shown only), 'species' (species picker: a type-colored cue before it,
    click the cue to open the Pokémon), 'form' (form number of the species column before it; its form name shows after),
    'int' (extra = (lo, hi)), 'choice' (extra = [(value, label)]).
    Rows keep the column order of `columns`; `display` = the order the columns are laid out in. wrap = rows per block
    (blocks side by side). get_rows() raises ValueError for a value that is not valid."""

    def __init__(self, master, page, columns, display=None, wrap=None, on_edit=None, numbered=False, action=None):
        super().__init__(master, style='Studio.TFrame')
        self.page = page
        self.columns = columns
        self.display = display or list(range(len(columns)))
        self.wrap = wrap
        self.on_edit = on_edit
        self.numbered = numbered
        self.action = action            # (text, fn(row index))
        self.cells = []                 # per row: {col: widget}
        self.cues = []                  # per row: {species col: canvas}
        self.notes = []                 # per row: {form col: label}
        self.values = []                # per row: the shown-only values
        self._pending = False

    # layout ---------------------------------------------------------------------------------------------------------
    def _span(self):
        n = (1 if self.numbered else 0) + (1 if self.action else 0)
        for c in self.display:
            kind = self.columns[c][1]
            n += 2 if kind in ('species', 'form') else 1
        return n + 1          # a gap column between blocks

    def _build(self, count):
        for w in self.winfo_children():
            w.destroy()
        self.cells, self.cues, self.notes, self.values = [], [], [], []
        per = self.wrap or max(1, count)
        blocks = max(1, -(-count // per))
        span = self._span()
        for b in range(blocks):
            col = b * span
            if self.numbered:
                col += 1
            for c in self.display:
                title, kind = self.columns[c][0], self.columns[c][1]
                if kind == 'species':
                    col += 1
                label(self, title, style='Faint.TLabel').grid(row=0, column=col, sticky='w', padx=(0, 6))
                col += 1
            if b < blocks - 1:
                self.columnconfigure((b + 1) * span - 1, minsize=28)
        for i in range(count):
            b, r = divmod(i, per)
            col = b * span
            gr = r + 1
            cells, cues, notes = {}, {}, {}
            if self.numbered:
                label(self, str(i + 1), style='Faint.TLabel', width=3, anchor='e').grid(row=gr, column=col, sticky='e',
                                                                                       padx=(0, 6))
                col += 1
            for c in self.display:
                title, kind, extra, width = self.columns[c]
                if kind == 'rate':
                    w = tk.Label(self, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9, 'bold'), width=width,
                                 anchor='center')
                    w.grid(row=gr, column=col, sticky='w', padx=(0, 8), pady=1)
                elif kind == 'label':
                    w = label(self, '', style='Muted.TLabel', width=width)
                    w.grid(row=gr, column=col, sticky='w', padx=(0, 8), pady=1)
                elif kind == 'species':
                    cv = tk.Canvas(self, width=12, height=18, bg=C['bg'], highlightthickness=0, cursor='hand2')
                    cv.grid(row=gr, column=col, sticky='w', padx=(0, 4))
                    cv.bind('<Button-1>', lambda _e, i=i, c=c: self._open(i, c))
                    cues[c] = cv
                    col += 1
                    w = Picker(self, self.page.c.species0(), width=width)
                    w.grid(row=gr, column=col, sticky='w', padx=(0, 6), pady=1)
                    self._watch(w, i)
                elif kind == 'choice':
                    w = Picker(self, extra, width=width)
                    w.grid(row=gr, column=col, sticky='w', padx=(0, 6), pady=1)
                    self._watch(w, i)
                else:       # int / form
                    lo, hi = extra if extra else ((0, 255) if kind == 'form' else (-2 ** 31, 2 ** 32 - 1))
                    w = IntField(self, lo, hi, width=width)
                    w.grid(row=gr, column=col, sticky='w', padx=(0, 6), pady=1)
                    self._watch(w, i)
                    if kind == 'form':
                        notes[c] = label(self, '', style='Faint.TLabel', width=14)
                cells[c] = w
                col += 1
            for n in notes.values():        # form names (or a slot's note) at the end of the row
                n.grid(row=gr, column=col, sticky='w')
                col += 1
            if self.action:
                Link(self, self.action[0], lambda i=i: self.action[1](i)).grid(row=gr, column=col, sticky='w')
            self.cells.append(cells)
            self.cues.append(cues)
            self.notes.append(notes)
            self.values.append({})

    def _watch(self, w, i):
        w.bind('<KeyRelease>', lambda _e: self._changed(i), add='+')
        w.bind('<FocusOut>', lambda _e: self._changed(i), add='+')
        if isinstance(w, Picker):
            w.bind('<<ComboboxSelected>>', lambda _e: self._changed(i), add='+')
        else:
            w.configure(command=lambda: self._changed(i))

    def _changed(self, i):
        self._paint(i)
        if self.on_edit and not self._pending:
            self._pending = True
            self.after_idle(self._fire)

    def _fire(self):
        self._pending = False
        if self.on_edit:
            self.on_edit()

    # values ---------------------------------------------------------------------------------------------------------
    def set_rows(self, rows):
        rows = [list(r) for r in rows]
        if len(rows) != len(self.cells):
            self._build(len(rows))
        for i, r in enumerate(rows):
            for c, (title, kind, extra, width) in enumerate(self.columns):
                v = r[c] if c < len(r) else None
                if kind in ('rate', 'label'):
                    self.values[i][c] = v
                    txt = '' if v is None else str(v)
                    if kind == 'rate':
                        txt = txt.split(' ', 1)[0]
                    self.cells[i][c].config(text=txt)
                else:
                    self.cells[i][c].set_value(v)
            self._paint(i)

    def _cell(self, i, c):
        title, kind = self.columns[c][0], self.columns[c][1]
        if kind in ('rate', 'label'):
            return self.values[i].get(c)
        v = self.cells[i][c].get_value()
        if v is None:
            raise ValueError(f'"{self.cells[i][c].get()}" in row {i + 1} is not a valid {title.lower()}')
        return v

    def get_rows(self):
        return [[self._cell(i, c) for c in range(len(self.columns))] for i in range(len(self.cells))]

    def safe_rows(self):
        """the rows, with None where a value is not valid (never raises)"""
        out = []
        for i in range(len(self.cells)):
            row = []
            for c in range(len(self.columns)):
                try:
                    row.append(self._cell(i, c))
                except ValueError:
                    row.append(None)
            out.append(row)
        return out

    def snapshot(self):
        return repr([[w.get() if not isinstance(w, tk.Label) else '' for _c, w in sorted(cells.items())]
                     for cells in self.cells])

    def set_cell(self, i, c, v):
        """(tests and buttons) put a value into a cell as if typed"""
        self.cells[i][c].set_value(v)
        self._changed(i)

    # type cue ---------------------------------------------------------------------------------------------------------
    def _species_form(self, i, c):
        sp = self.cells[i][c].get_value()
        fo = 0
        nxt = c + 1
        if nxt < len(self.columns) and self.columns[nxt][1] == 'form':
            fo = self.cells[i][nxt].get_value() or 0
        return sp, fo

    def _paint(self, i):
        g = self.page.s.game
        for c, cv in self.cues[i].items():
            sp, fo = self._species_form(i, c)
            cv.delete('all')
            r = (g.row(sp, fo) or g.row(sp)) if sp else None
            if r is None:
                cv.create_rectangle(3, 3, 9, 15, outline=C['line2'], fill=C['bg'])
                cv.config(cursor='')
            else:
                t1, t2 = r['type1'], r['type2']
                cv.create_rectangle(2, 2, 10, 9 if t2 != t1 else 16, outline='', fill=type_color(t1))
                if t2 != t1:
                    cv.create_rectangle(2, 9, 10, 16, outline='', fill=type_color(t2))
                cv.config(cursor='hand2')
        for c, n in self.notes[i].items():
            sp = self.cells[i][c - 1].get_value() if c > 0 else None
            fo = self.cells[i][c].get_value() or 0
            txt = ''
            if sp and fo:
                txt = (g.form_name(sp, fo) or '') if g.row(sp, fo) is not None else 'no such form'
            elif self.columns[c - 1][1] == 'species':
                rate = next((v for cc, v in self.values[i].items() if self.columns[cc][1] == 'rate'), None)
                if rate and '(' in str(rate):
                    txt = str(rate).split('(', 1)[1].rstrip(')')
            n.config(text=txt[:22])

    def _open(self, i, c):
        sp, fo = self._species_form(i, c)
        g = self.page.s.game
        if not sp or g.row(sp) is None:
            return
        self.page.app.show('pokemon', (sp, fo if g.row(sp, fo) is not None else 0))


def species_label(g, sp, fo):
    if not sp:
        return '-'
    name = g.pokemon_name(sp, fo) if g.row(sp, fo) is not None else g.species_name(sp)
    return name + (f' ({g.form_name(sp, fo)})' if fo and g.row(sp, fo) is not None and g.form_name(sp, fo) else '')


def cue(master, g, sp, fo):
    """a small type-colored square of a species (two halves for two types)"""
    cv = tk.Canvas(master, width=10, height=14, bg=C['bg'], highlightthickness=0)
    r = (g.row(sp, fo) or g.row(sp)) if sp else None
    if r is not None:
        t1, t2 = r['type1'], r['type2']
        cv.create_rectangle(1, 1, 9, 7 if t2 != t1 else 13, outline='', fill=type_color(t1))
        if t2 != t1:
            cv.create_rectangle(1, 7, 9, 13, outline='', fill=type_color(t2))
    return cv


# --- Wild areas ---------------------------------------------------------------------------------------------------------
class WildPage(RecordPage):
    title = 'Wild areas'
    subtitle = 'Who you meet in each area - grass and caves, swarms, day and night, the Poké Radar, surfing and fishing'
    noun = 'area'
    columns = [('id', 'Zone', 48, 'e'), ('name', 'Area', 160, 'w'), ('lv', 'Levels', 62, 'center'),
               ('mons', 'Pokémon', 62, 'e')]
    list_width = 390

    # --- versions / the file ---------------------------------------------------------------------------------------
    def versions(self):
        return [v for v, _t in self.s.game.encounter_files()]

    def tree(self):
        return dict(self.s.game.encounter_files())[self.version]

    def obj(self):
        return f'FieldEncountTable_{self.version}'

    def zone_row(self, z):
        return next(r for r in self.tree()['table'] if r['zoneID'] == z)

    def extra_left(self, f):
        have = self.versions()
        self.version = 'd' if 'd' in have else (have[0] if have else 'd')
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.vseg = Segmented(row, [(v, n) for v, n in VERSIONS if v in have], command=self.set_version,
                              value=self.version)
        self.vseg.pack(side='left')
        row2 = frame(f)
        row2.pack(fill='x', pady=(6, 0))
        self.kind = ttk.Combobox(row2, values=KINDS, state='readonly', width=16, style='Studio.TCombobox')
        self.kind.current(0)
        self.kind.pack(side='left')
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row2, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))
        row3 = frame(f)
        row3.pack(fill='x', pady=(6, 0))
        label(row3, 'Has Pokémon', style='Muted.TLabel').pack(side='left')
        self.has_mon = Picker(row3, self.c.species0(), width=22)
        self.has_mon.pack(side='left', padx=(6, 0))
        self.has_mon.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.has_mon.bind('<Return>', lambda _e: self._apply_filters())
        Link(row3, 'clear', self._clear_mon).pack(side='left', padx=(6, 0))

    def _clear_mon(self):
        self.has_mon.set('')
        self._apply_filters()

    def set_version(self, v):
        if v == self.version:
            return
        if not self.keep():
            self.vseg.pick(self.version, notify=False)
            return
        self.version = v
        self.refresh()
        self.say(f'Showing the {dict(VERSIONS)[v]} wild areas.')

    def _apply_filters(self):
        kind = self.kind.current()
        ed = self.only_edited.get()
        mon = self.has_mon.get_value() if self.has_mon.get() else None
        rows = {r['zoneID']: r for r in self.tree()['table']}

        def used(r, fields):
            return any(s['monsNo'] for f in fields for s in r.get(f, ()))

        def pred(key, _vals):
            if ed and key not in self.table.edited:
                return False
            r = rows.get(key)
            if r is None:
                return False
            if kind == 1 and not used(r, ['ground_mons']):
                return False
            if kind == 2 and not used(r, ['water_mons']):
                return False
            if kind == 3 and not used(r, ['boro_mons', 'ii_mons', 'sugoi_mons']):
                return False
            if kind == 4 and not used(r, ['tairyo']):
                return False
            if kind == 5 and not used(r, ['swayGrass']):
                return False
            if kind == 6 and used(r, LIVE_LISTS):
                return False
            if mon:
                return any(s['monsNo'] & 0xFFFF == mon for f in LIVE_LISTS for s in r.get(f, ()))
            return True
        self.table.filter(pred=pred if (kind or ed or mon) else None)
        self._count()

    # --- table -----------------------------------------------------------------------------------------------------
    def rows(self):
        return [(r['zoneID'], self._values_of(r)) for r in self.tree()['table']]

    def row(self, key):
        return self._values_of(self.zone_row(key))

    def _stats(self, r):
        slots = [s for f in LIVE_LISTS for s in r.get(f, ()) if s['monsNo']]
        lv = [s['minlv'] for s in slots] + [s['maxlv'] for s in slots]
        return (min(lv) if lv else None, max(lv) if lv else None, len({s['monsNo'] & 0xFFFF for s in slots}))

    def _values_of(self, r):
        lo, hi, n = self._stats(r)
        lv = '—' if lo is None else (f'{lo:>2}' if lo == hi else f'{lo:>2}-{hi}')
        return (r['zoneID'], self.s.game.zone_name(r['zoneID']), lv, n)

    def op_key(self, op):
        if op.get('op') == 'set' and op.get('obj') == self.obj() and op.get('list') == 'table':
            return op.get('key')
        return None

    def record_name(self, key):
        return f'{self.s.game.zone_name(key)} ({VERSION_SHORT.get(self.version, self.version)})'

    def goto(self, key):
        """key = zoneID (opens it in Brilliant Diamond) or (zoneID, version)"""
        self.ensure()
        z, v = (key if isinstance(key, tuple) else (key, 'd'))
        if v != self.version and v in self.versions():
            if not self.keep():
                return
            self.vseg.pick(v, notify=False)
            self.version = v
            self.refresh()
        self.table.select(z)

    # --- record ----------------------------------------------------------------------------------------------------
    def _slot_grid(self, parent, on_edit=None):
        cols = [('Pokémon', 'species', None, 22), ('Form', 'form', (0, 255), 3), ('Min Lv', 'int', (0, 100), 3),
                ('Max Lv', 'int', (0, 100), 3), ('Chance', 'rate', None, 5)]
        g = RowGrid(parent, self, cols, display=[4, 0, 1, 2, 3], on_edit=on_edit or self._live)
        return self.track(g)

    def build(self, body):
        self.views = Segmented(body, WILD_VIEWS, command=self.switch, value='glance')
        self.views.pack(anchor='w', pady=(4, 12))
        self.frames = {v: frame(body) for v, _ in WILD_VIEWS}
        self.grids = {}
        # at a glance
        self.glance = self.frames['glance']
        # grass and caves
        land = self.frames['land']
        top = frame(land)
        top.pack(fill='x')
        sec = Section(top, 'Grass and caves', hint='12 slots, one picked per encounter')
        sec.pack(side='left', anchor='n')
        self.grids['ground_mons'] = self._slot_grid(sec.body)
        self.grids['ground_mons'].pack(anchor='w')
        ch = Section(top, 'Chance by Pokémon')
        ch.pack(side='left', anchor='n', fill='x', expand=True, padx=(20, 14))
        self.chart = tk.Canvas(ch.body, width=184, height=230, bg=C['bg'], highlightthickness=0)
        self.chart.pack(anchor='w')
        for field, title, hint in LAND_VIEW:
            s = Section(land, title, hint=hint)
            s.pack(fill='x', pady=(14, 0))
            self.grids[field] = self._slot_grid(s.body)
            self.grids[field].pack(anchor='w')
        # water
        water = self.frames['water']
        self.water_rate = {}
        for field, title, rate in WATER_VIEW:
            s = Section(water, title, hint='5 slots of a ' + ('step on the water' if field == 'water_mons' else 'bite'))
            s.pack(fill='x', pady=(0, 14))
            self.water_rate[field] = label(s.body, '', style='Faint.TLabel')
            self.water_rate[field].pack(anchor='w', pady=(0, 2))
            self.grids[field] = self._slot_grid(s.body)
            self.grids[field].pack(anchor='w')
        # rates and forms
        rt = self.frames['rates']
        s = Section(rt, 'Encounter rates', hint='how often a Pokémon appears: per step (grass, caves, water) or per cast')
        s.pack(fill='x')
        grid = frame(s.body)
        grid.pack(anchor='w')
        fields = {}
        texts = {'encRate_gr': ('Grass and caves', 'per step; 0 = no wild Pokémon here'),
                 'encRate_wat': ('Surfing', 'per step on the water'),
                 'encRate_turi_boro': ('Old Rod', 'chance of a bite per cast'),
                 'encRate_turi_ii': ('Good Rod', 'chance of a bite per cast'),
                 'encRate_sugoi': ('Super Rod', 'chance of a bite per cast'),
                 'FormProb0': ('Alternate form chance', 'how often the area\'s Pokémon come in their other form'),
                 'Annoon1': ('Unown letter set', 'which Unown letters this area has (the Solaceon Ruins rooms)')}
        for r, (k, _n) in enumerate(RATES + [('FormProb0', ''), ('Annoon1', '')]):
            if k == 'FormProb0':
                s2 = Section(rt, 'Forms')
                s2.pack(fill='x', pady=(16, 0))
                grid = frame(s2.body)
                grid.pack(anchor='w')
            name, hint = texts[k]
            label(grid, name, style='Muted.TLabel', width=20, anchor='e').grid(row=r, column=0, sticky='e', padx=(0, 6),
                                                                              pady=2)
            fields[k] = IntField(grid, 0, 255 if k.startswith('encRate') else 65535, width=7)
            fields[k].grid(row=r, column=1, sticky='w', pady=2)
            label(grid, hint, style='Faint.TLabel').grid(row=r, column=2, sticky='w', padx=(10, 0))
        self.rates = self.track(FieldSet(fields))
        # unused GBA slots
        gba = self.frames['gba']
        note = tk.Frame(gba, bg=C['soft'])
        note.pack(fill='x', pady=(0, 12))
        tk.Label(note, text='The game never uses these lists.', bg=C['soft'], fg=C['text'], font=(FONT, 9, 'bold'),
                 anchor='w').pack(fill='x', padx=12, pady=(8, 0))
        tk.Label(note, text='They are the "dual-slot" lists of Diamond and Pearl (a Game Boy Advance cartridge in the '
                            'second slot). Brilliant Diamond and Shining Pearl still keep them in their data but no '
                            'Pokémon ever comes from them - changing them has no effect in the game.',
                 bg=C['soft'], fg=C['muted'], font=(FONT, 9), wraplength=640, justify='left', anchor='w').pack(
            fill='x', padx=12, pady=(2, 8))
        for field, title in GBA_LISTS:
            s = Section(gba, title.replace('Dual slot: ', 'With ') + ' in the second slot')
            s.pack(fill='x', pady=(0, 12))
            self.grids[field] = self._slot_grid(s.body)
            self.grids[field].pack(anchor='w')
        self.view = 'glance'
        self.switch('glance')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        if view == 'glance' and self.key is not None:
            self._glance()
        if self.scroller is not None:
            self.scroller.top()

    def show(self, z):
        g = self.s.game
        r = self.zone_row(z)
        for field, _, labels in ZONE_LISTS:
            self.grids[field].set_rows(slot_rows(r[field], labels))
        for field, _ in GBA_LISTS:
            self.grids[field].set_rows(slot_rows(r[field], ['—'] * len(r[field])))
        vals = {k: r[k] for k, _ in RATES}
        vals['FormProb0'] = r['FormProb'][0] if r['FormProb'] else 0
        vals['Annoon1'] = r['AnnoonTable'][1] if len(r['AnnoonTable']) > 1 else 0
        self.rates.load(vals)
        lo, hi, n = self._stats(r)
        pills = [(dict(VERSIONS)[self.version], VERSION_COLORS[self.version])]
        if lo is not None:
            pills.append((f'Lv. {lo}' if lo == hi else f'Lv. {lo}-{hi}', C['soft'], C['muted']))
        pills.append((plural(n, 'Pokémon').replace('Pokémons', 'Pokémon'), C['accent_soft'], C['accent']))
        used = [METHOD_TITLES[f].lower() for f in LIVE_LISTS if any(s['monsNo'] for s in r[f])]
        sub = f'Zone {z}' + (' · ' + ', '.join(used) if used else ' · no wild Pokémon here')
        self.set_header(g.zone_name(z), sub, pills)
        self._live()

    def _live(self):
        """the chart, the water rates and the at-a-glance view follow the fields"""
        self._chart()
        rv = self.rates.values()
        for field, _t, rk in WATER_VIEW:
            v = rv.get(rk)
            self.water_rate[field].config(text=f'Encounter rate {v} (change it under Rates & forms)' if v else
                                          'Encounter rate 0: nothing appears this way here (change it under Rates & forms)')
        if self.view == 'glance':
            self._glance()

    def _gathered(self, field):
        """{(species, form): [chance, min lv, max lv]} of a list as the fields show it"""
        out = {}
        for row in self.grids[field].safe_rows():
            sp, fo, lo, hi, rate = row
            if not sp:
                continue
            e = out.setdefault((sp, fo or 0), [0.0, lo or 0, hi or 0])
            e[0] += rate_value(rate)
            e[1] = min(e[1], lo or 0)
            e[2] = max(e[2], hi or 0)
        return out

    def _chart(self):
        cv = self.chart
        cv.delete('all')
        g = self.s.game
        data = sorted(self._gathered('ground_mons').items(), key=lambda kv: -kv[1][0])
        if not data:
            cv.create_text(0, 10, text='No Pokémon in the grass here.', anchor='w', fill=C['faint'], font=(FONT, 9))
            cv.config(height=24)
            return
        cv.config(height=20 * len(data) + 4)
        for k, ((sp, fo), (ch, _lo, _hi)) in enumerate(data):
            y = 2 + 20 * k
            r = g.row(sp, fo) or g.row(sp)
            col = type_color(r['type1']) if r else C['faint']
            cv.create_text(0, y + 8, text=species_label(g, sp, fo)[:14], anchor='w', fill=C['text'], font=(FONT, 9))
            cv.create_rectangle(96, y + 3, 96 + max(2, int(50 * ch / 100)), y + 13, fill=col, outline='')
            cv.create_text(182, y + 8, text=f'{ch:g}%', anchor='e', fill=C['muted'], font=(FONT, 9, 'bold'))

    def _glance(self):
        for w in self.glance.winfo_children():
            w.destroy()
        g = self.s.game
        rv = self.rates.values()
        rate_of = {'ground_mons': 'encRate_gr', 'water_mons': 'encRate_wat', 'boro_mons': 'encRate_turi_boro',
                   'ii_mons': 'encRate_turi_ii', 'sugoi_mons': 'encRate_sugoi'}
        any_ = False
        for field in LIVE_LISTS:
            data = self._gathered(field)
            if not data:
                continue
            any_ = True
            rk = rate_of.get(field)
            hint = f'encounter rate {rv.get(rk, 0)}' if rk else None
            if rk and not rv.get(rk):
                hint = 'encounter rate 0 - never met'
            sec = Section(self.glance, METHOD_TITLES[field], hint=hint,
                          actions=[('Edit', lambda f=field: self.views.pick('water' if f in rate_of and
                                                                            f != 'ground_mons' else 'land'))])
            sec.pack(fill='x', pady=(0, 12))
            box = frame(sec.body)
            box.pack(fill='x')
            for k, ((sp, fo), (ch, lo, hi)) in enumerate(sorted(data.items(), key=lambda kv: -kv[1][0])):
                cell = frame(box)
                cell.grid(row=k // 3, column=k % 3, sticky='w', padx=(0, 22), pady=1)
                cue(cell, g, sp, fo).pack(side='left', padx=(0, 5))
                Link(cell, species_label(g, sp, fo)[:24],
                     lambda sp=sp, fo=fo: self.app.show('pokemon', (sp, fo if g.row(sp, fo) is not None else 0))).pack(
                    side='left')
                lv = f'Lv. {lo}' if lo == hi else f'Lv. {lo}-{hi}'
                label(cell, f'  {lv} · {ch:g}%', style='Muted.TLabel').pack(side='left')
            for c in range(3):
                box.columnconfigure(c, minsize=200)
        if not any_:
            label(self.glance, 'No wild Pokémon in this area (all its lists are empty). Pick Grass & caves or Water to '
                  'add some.', style='Muted.TLabel').pack(anchor='w')
        label(self.glance, 'Click a Pokémon to open it. Chances add up the slots it has in that list.',
              style='Faint.TLabel').pack(anchor='w', pady=(4, 0))

    def collect(self, z):
        """the zone's slot lists, rates and GBA lists -> set operations"""
        g = self.s.game
        r = self.zone_row(z)
        obj = self.obj()
        ops = []
        rows = {f: self.grids[f].get_rows() for f in LIVE_LISTS + [f for f, _ in GBA_LISTS]}   # every value checked first
        for field, new_rows in rows.items():
            new = rows_slots(new_rows, r[field])
            if new != r[field]:
                ops.append(set_op(g, GAMESETTINGS, obj, 'table', r, field, new, key=z))
        v = self.rates.values()
        for k, _ in RATES:
            if k in v and r[k] != v[k]:
                ops.append(set_op(g, GAMESETTINGS, obj, 'table', r, k, v[k], key=z))
        if r['FormProb'] and 'FormProb0' in v and r['FormProb'][0] != v['FormProb0']:
            ops.append(set_op(g, GAMESETTINGS, obj, 'table', r, 'FormProb', [v['FormProb0']] + list(r['FormProb'][1:]), key=z))
        if len(r['AnnoonTable']) > 1 and 'Annoon1' in v and r['AnnoonTable'][1] != v['Annoon1']:
            a = list(r['AnnoonTable'])
            a[1] = v['Annoon1']
            ops.append(set_op(g, GAMESETTINGS, obj, 'table', r, 'AnnoonTable', a, key=z))
        return ops

    def search_items(self):
        g = self.s.game
        return [(f'{r["zoneID"]:03d} {g.zone_name(r["zoneID"])}', r['zoneID']) for r in self.tree()['table']]


# --- pages that keep a whole set of lists (no record table) --------------------------------------------------------------
class _ListsPage(Page):
    """a page header (title, pills, version switch / views), the "Unsaved changes - Keep / Discard" strip, an error line
    and a scrolling body. Subclasses: build(body), load() (data -> widgets), changes() -> [(file, obj, field, value)]
    without applying (ValueError for a bad value); keep() turns them into set operations."""
    what = 'changes'

    def build_page(self):
        self.head = frame(self)
        self.head.pack(fill='x', padx=24, pady=(12, 0))
        self.strip = tk.Frame(self, bg=C['edited_soft'])
        tk.Label(self.strip, text='●  Unsaved changes', bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9, 'bold')).pack(
            side='left', padx=(12, 0), pady=5)
        tk.Label(self.strip, text='kept when you leave this page', bg=C['edited_soft'], fg='#8a4b00',
                 font=(FONT, 9)).pack(side='left', padx=(8, 0))
        Link(self.strip, 'Discard', self.discard, bg=C['edited_soft']).pack(side='right', padx=(8, 12))
        Button(self.strip, 'Keep  (Ctrl+S)', self.keep, kind='primary', small=True).pack(side='right', pady=4)
        self._line = tk.Frame(self, height=1, bg=C['line'])
        self._line.pack(fill='x', padx=24, pady=(8, 0))
        self.error = ttk.Label(self, text='', style='Error.TLabel')
        self.error.pack(anchor='w', padx=24)
        sc = Scroll(self)
        sc.pack(fill='both', expand=True, padx=(24, 0), pady=(4, 8))
        self.scroller = sc
        self.build(sc.body)
        self.load()
        self._poll()

    def build(self, body):
        pass

    def load(self):
        pass

    def changes(self):
        return []

    def dirty(self):
        if not self.built:
            return False
        try:
            return bool(self.changes())
        except ValueError:
            return True
        except tk.TclError:
            return False

    def _poll(self):
        try:
            d = self.dirty()
            if d and not self.strip.winfo_ismapped():
                self.strip.pack(fill='x', padx=24, pady=(8, 0), before=self._line)
            elif not d and self.strip.winfo_ismapped():
                self.strip.pack_forget()
        except tk.TclError:
            return
        self.after(400, self._poll)

    def collect(self):
        g = self.s.game
        return [set_op(g, file, obj, None, None, field, value) for file, obj, field, value in self.changes()]

    def keep(self):
        if not self.built:
            return True
        try:
            ops = self.collect()
        except ValueError as e:
            self.error.config(text=f'Not kept: {e}')
            return False
        self.error.config(text='')
        if not ops:
            return True
        n = self.s.commit(ops)
        self.app.changed(f'Kept {n} change{"s" if n != 1 else ""} to {self.what}.')
        self.load()
        return True

    def discard(self):
        self.error.config(text='')
        self.load()

    def leave(self):
        return self.keep()

    def refresh(self):
        if self.built:
            self.error.config(text='')
            self.load()


# --- Special encounters ------------------------------------------------------------------------------------------------
SPECIAL_VIEWS = [('garden', 'Trophy Garden'), ('honey', 'Honey trees'), ('marsh', 'Great Marsh')]


class SpecialPage(_ListsPage):
    title = 'Special encounters'
    subtitle = 'The Trophy Garden, honey trees and the Great Marsh - their own Pokémon lists, one set per version'
    what = 'the special encounters'

    def tree(self):
        return dict(self.s.game.encounter_files())[self.version]

    def obj(self):
        return f'FieldEncountTable_{self.version}'

    def build(self, body):
        have = [v for v, _t in self.s.game.encounter_files()]
        self.version = 'd' if 'd' in have else (have[0] if have else 'd')
        row = frame(self.head)
        row.pack(fill='x')
        self.vseg = Segmented(row, [(v, n) for v, n in VERSIONS if v in have], command=self.set_version,
                              value=self.version)
        self.vseg.pack(side='left')
        self.views = Segmented(row, SPECIAL_VIEWS, command=self.switch, value='garden')
        self.views.pack(side='left', padx=(18, 0))
        self.summary = label(row, '', style='Muted.TLabel')
        self.summary.pack(side='left', padx=(18, 0))
        self.frames = {v: frame(body) for v, _ in SPECIAL_VIEWS}
        sp_cols = [('Pokémon', 'species', None, 22), ('Form', 'form', (0, 255), 3)]
        f = self.frames['garden']
        s = Section(f, 'Trophy Garden', hint='the Pokémon Mansion\'s garden: the Pokémon it can have each day')
        s.pack(fill='x')
        self.ura = RowGrid(s.body, self, sp_cols, numbered=True, wrap=8, on_edit=self._summary)
        self.ura.pack(anchor='w')
        f = self.frames['honey']
        s = Section(f, 'Honey trees', hint='a slathered tree picks one row by its chance, then its normal, rare or '
                                           'super rare Pokémon')
        s.pack(fill='x')
        self.honey = RowGrid(s.body, self, [('Chance', 'int', (0, 255), 4), ('Normal', 'species', None, 20),
                                            ('Rare', 'species', None, 20), ('Super rare', 'species', None, 20)],
                             numbered=True, on_edit=self._summary)
        self.honey.pack(anchor='w')
        self.honey_total = label(s.body, '', style='Muted.TLabel')
        self.honey_total.pack(anchor='w', pady=(6, 0))
        f = self.frames['marsh']
        s = Section(f, 'Great Marsh', hint='the Safari Zone of Pastoria City: the Pokémon of its areas')
        s.pack(fill='x')
        self.safari = RowGrid(s.body, self, sp_cols, numbered=True, wrap=22, on_edit=self._summary)
        self.safari.pack(anchor='w')
        label(body, 'Click the colored square before a Pokémon to open it. The number of rows is fixed by the game.',
              style='Faint.TLabel').pack(anchor='w', side='bottom', pady=(10, 0))
        self.view = 'garden'
        self.switch('garden')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        self.scroller.top()
        self._summary()

    def set_version(self, v):
        if v == self.version:
            return
        if not self.keep():
            self.vseg.pick(self.version, notify=False)
            return
        self.version = v
        self.load()
        self.say(f'Showing the {dict(VERSIONS)[v]} special encounters.')

    def _data_rows(self):
        t = self.tree()
        return ([list(split(r['monsNo'])) for r in t['urayama']],
                [[r['Rate'], r['Normal'], r['Rare'], r['SuperRare']] for r in t['mistu']],
                [list(split(r['MonsNo'])) for r in t['safari']])

    def load(self):
        ura, honey, saf = self._data_rows()
        self.ura.set_rows(ura)
        self.honey.set_rows(honey)
        self.safari.set_rows(saf)
        self._summary()

    def _summary(self):
        if not hasattr(self, 'safari'):
            return
        grid = {'garden': self.ura, 'honey': self.honey, 'marsh': self.safari}[self.view]
        rows = grid.safe_rows()
        if self.view == 'honey':
            mons = {m for r in rows for m in r[1:] if m}
            total = sum(r[0] or 0 for r in rows)
            self.honey_total.config(text=f'Chances add up to {total}' + ('' if total == 100 else
                                                                         '  (the game expects 100)'))
        else:
            mons = {(r[0], r[1]) for r in rows if r[0]}
        self.summary.config(text=f'{dict(VERSIONS)[self.version]} · {plural(len(rows), "row")} · '
                                 f'{len(mons)} different Pokémon')

    def changes(self):
        """the changes to Trophy Garden, honey trees and Great Marsh, without applying"""
        t = self.tree()
        obj = self.obj()
        out = []
        ura = [dict(o, monsNo=join(*r)) for o, r in zip(t['urayama'], self.ura.get_rows())]
        if ura != t['urayama']:
            out.append((GAMESETTINGS, obj, 'urayama', ura))
        honey = [dict(o, Rate=int(r[0]), Normal=int(r[1]), Rare=int(r[2]), SuperRare=int(r[3]))
                 for o, r in zip(t['mistu'], self.honey.get_rows())]
        if honey != t['mistu']:
            out.append((GAMESETTINGS, obj, 'mistu', honey))
        saf = [dict(o, MonsNo=join(*r)) for o, r in zip(t['safari'], self.safari.get_rows())]
        if saf != t['safari']:
            out.append((GAMESETTINGS, obj, 'safari', saf))
        return out


# --- Underground ---------------------------------------------------------------------------------------------------------
UG_VIEWS = [('levels', 'Levels by progress'), ('areas', 'Areas'), ('tables', 'Spawn tables'), ('rare', 'Rare spawns')]


class UndergroundPage(_ListsPage):
    title = 'Underground'
    subtitle = 'The Grand Underground\'s Pokémon hideaways: their levels, which table each area uses, and rare spawns'
    what = 'the Underground'

    def build(self, body):
        g = self.s.game
        row = frame(self.head)
        row.pack(fill='x')
        self.views = Segmented(row, UG_VIEWS, command=self.switch, value='levels')
        self.views.pack(side='left')
        self.summary = label(row, '', style='Muted.TLabel')
        self.summary.pack(side='left', padx=(18, 0))
        self.frames = {v: frame(body) for v, _ in UG_VIEWS}
        names = sorted(n for n, _t in g.ug_tables())
        # levels
        f = self.frames['levels']
        top = frame(f)
        top.pack(fill='x')
        s = Section(top, 'Levels by progress', hint='the level range of the hideaway Pokémon at each point of the story')
        s.pack(side='left', anchor='n')
        self.levels = RowGrid(s.body, self, [('Progress', 'label', None, 10), ('Min level', 'int', (1, 100), 4),
                                             ('Max level', 'int', (1, 100), 4)], on_edit=self._lv_chart)
        self.levels.pack(anchor='w')
        ch = Section(top, 'Level ranges')
        ch.pack(side='left', anchor='n', padx=(28, 16), fill='x', expand=True)
        self.lv_chart = tk.Canvas(ch.body, width=360, height=240, bg=C['bg'], highlightthickness=0)
        self.lv_chart.pack(anchor='w')
        # areas
        f = self.frames['areas']
        s = Section(f, 'Which spawn table each hideaway uses', hint='several areas can share one table')
        s.pack(fill='x')
        self.areas = RowGrid(s.body, self, [('Area', 'label', None, 24), ('Spawn table', 'choice', [(n, n) for n in names],
                                                                          18), ('Pokémon at once', 'label', None, 14)],
                             wrap=10, action=('open table', self._open_area))
        self.areas.pack(anchor='w')
        # spawn tables
        f = self.frames['tables']
        cols = frame(f)
        cols.pack(fill='both', expand=True)
        left = frame(cols, width=290)
        left.pack(side='left', fill='y')
        self.table_list = DataTable(left, [('name', 'Table', 110, 'w'), ('n', 'Pokémon', 60, 'e'),
                                           ('areas', 'Areas', 90, 'w')], on_select=self.show_table, height=14)
        self.table_list.pack(fill='both', expand=True)
        right = frame(cols)
        right.pack(side='left', fill='both', expand=True, padx=(20, 16))
        self.table_title = label(right, '', style='Section.TLabel')
        self.table_title.pack(anchor='w')
        self.table_hint = label(right, '', style='Muted.TLabel')
        self.table_hint.pack(anchor='w', pady=(0, 6))
        # mod variants (a mod's hint file, or seen in the data): forms in the high 16 bits of monsno, and
        # "version" values outside 1..3
        hints = getattr(g, 'hints', {}) or {}
        rows_all = [r for _, t in g.ug_tables() for r in t['table']]
        self.form16 = bool(hints.get('uint16UgTables', any(r['monsno'] > 0xFFFF for r in rows_all)))
        self.free_ver = bool(hints.get('ugVersionsUnbounded', any(not 1 <= (r['version'] or 1) <= 3 for r in rows_all)))
        sp = self.c.species0()
        tcols = [('Pokémon', 'choice', sp, 220)] + ([('Form', 'int', (0, 255), 50)] if self.form16 else []) + \
            [('Version', 'int', (0, 255), 80) if self.free_ver else ('Version', 'choice', UG_VERSIONS, 150),
             ('Needs', 'choice', UG_REQUIREMENTS, 140)]
        self.spawn = Table(right, tcols, height=16, new_row=lambda: [1, 0, 1, 1] if self.form16 else [1, 1, 1])
        self.spawn.pack(fill='both', expand=True)
        label(right, 'Double-click a cell to change it. "Needs" = what the player must have before it appears. Rows '
                     'with no Pokémon are dropped; the table is kept sorted by species number.',
              style='Faint.TLabel', wraplength=520, justify='left').pack(anchor='w', pady=(6, 0))
        # rare spawns
        f = self.frames['rare']
        s = Section(f, 'Rare spawns', hint='the rare Pokémon an area can show, with their chance in each version')
        s.pack(fill='both', expand=True)
        areas = [(k, f'{k} {n}') for k, n in UG_AREAS.items()]
        self.rare = Table(s.body, [('Area', 'choice', areas, 200), ('Pokémon', 'choice', sp, 210),
                                   ('Version', 'choice', UG_VERSIONS, 140), ('BD chance %', 'float', None, 100),
                                   ('SP chance %', 'float', None, 100)], height=18, new_row=lambda: [2, 1, 1, 1.0, 1.0])
        self.rare.pack(fill='both', expand=True)
        label(s.body, 'Double-click a cell to change it. Rows with no Pokémon are dropped; the list is kept sorted by '
                      'area.', style='Faint.TLabel').pack(anchor='w', pady=(6, 0))
        self.cur = None
        self.edited = {}
        self.view = 'levels'
        self.switch('levels')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        self.scroller.top()
        self._summary()

    # data -> rows -----------------------------------------------------------------------------------------------------
    def _trees(self):
        g = self.s.game
        self.levels_tree = g.ug_table('UgEncountLevel')
        self.marks = g.ug_table('UgRandMark')
        self.tables = dict(g.ug_tables())
        self.special = g.ug_table('UgSpecialPokemon')

    def _spawn_rows(self, name):
        return [([r['monsno'] & 0xFFFF, r['monsno'] >> 16] if self.form16 else [r['monsno']]) +
                [r['version'] if self.free_ver else (r['version'] or 1), r['zukanflag'] or 1]
                for r in self.tables[name]['table']]

    def _level_rows(self):
        return [[UG_PROGRESSION[k] if k < len(UG_PROGRESSION) else str(k), r['MinLv'], r['MaxLv']]
                for k, r in enumerate(self.levels_tree['Data'])]

    def _area_rows(self):
        return [[f'{r["id"]} {UG_AREAS.get(r["id"], "")}'.strip(), r['FileName'], f'{r.get("min", "?")}-{r.get("max", "?")}']
                for r in self.marks['table']]

    def _rare_rows(self):
        return [[r['id'], r['monsno'], r['version'], r['Dspecialrate'] / 10, r['Pspecialrate'] / 10]
                for r in self.special['Sheet1']]

    def load(self):
        self._trees()
        self.levels.set_rows(self._level_rows())
        self._lv_chart()
        self.areas.set_rows(self._area_rows())
        self.rare.set_rows(self._rare_rows())
        self._summary()
        self.edited = {}
        cur = self.cur if self.cur in self.tables else (sorted(self.tables)[0] if self.tables else None)
        self.cur = None
        self._table_rows()
        if cur is not None:
            self.table_list.select(cur, notify=False)
            self.show_table(cur)

    def _table_rows(self):
        users = {}
        for r in self.marks['table']:
            users.setdefault(r['FileName'], []).append(r['id'])
        edited = {op.get('obj') for op in self.s.project.ops if op.get('file') == UGDATA}
        self.table_list.set_rows([(n, (n.replace('UgEncount_', 'Table '), len(t['table']),
                                       ', '.join(map(str, users.get(n, []))) or 'none'))
                                  for n, t in sorted(self.tables.items())], edited & set(self.tables))

    def show_table(self, name):
        """the spawn table editor shows `name` (the rows of the one it showed are remembered until Keep)"""
        if self.cur is not None:
            self.edited[self.cur] = self.spawn.get_rows()
        self.cur = name
        rows = self.edited[name] if name in self.edited else self._spawn_rows(name)
        self.spawn.set_rows(rows)
        users = [f'{r["id"]} {UG_AREAS.get(r["id"], "")}'.strip() for r in self.marks['table'] if r['FileName'] == name]
        self.table_title.config(text=name.replace('UgEncount_', 'Spawn table '))
        self.table_hint.config(text=('Used by area ' + ', '.join(users)) if users else 'No area uses this table now.')
        if self.table_list.current() != name:
            self.table_list.select(name, notify=False)
        return True

    def _open_area(self, i):
        rows = self.areas.safe_rows()
        name = rows[i][1] if i < len(rows) else None
        if name in self.tables:
            self.views.pick('tables')
            self.show_table(name)

    def _lv_chart(self):
        cv = self.lv_chart
        cv.delete('all')
        rows = self.levels.safe_rows()
        top = max([r[2] or 0 for r in rows] + [10])
        scale = 280 / top
        for k, (name, lo, hi) in enumerate(rows):
            y = 4 + 24 * k
            lo, hi = lo or 0, hi or 0
            cv.create_rectangle(0, y + 6, 280, y + 14, fill=C['soft'], outline='')
            cv.create_rectangle(int(lo * scale), y + 4, max(int(hi * scale), int(lo * scale) + 3), y + 16,
                                fill=C['accent'] if lo <= hi else C['danger'], outline='')
            cv.create_text(290, y + 10, text=f'{lo}-{hi}' if lo <= hi else f'{lo}-{hi} (!)', anchor='w',
                           fill=C['muted'], font=(FONT, 9))
        cv.config(height=24 * len(rows) + 8)

    def _summary(self):
        if not hasattr(self, 'tables'):
            return
        n = len({r['monsno'] for t in self.tables.values() for r in t['table']})
        self.summary.config(text=f'{plural(len(self.marks["table"]), "area")} · {plural(len(self.tables), "spawn table")}'
                                 f' · {n} different Pokémon · {plural(len(self.special["Sheet1"]), "rare spawn")}')

    # rows -> changes (the old UgEditor.collect, without applying) ----------------------------------------------------
    def changes(self):
        out = []
        lvr = self.levels.get_rows()
        lv = [dict(o, MinLv=int(r[1]), MaxLv=int(r[2])) for o, r in zip(self.levels_tree['Data'], lvr)]
        if lv != self.levels_tree['Data']:
            out.append((UGDATA, 'UgEncountLevel', 'Data', lv))
        marks = [dict(o, FileName=r[1]) for o, r in zip(self.marks['table'], self.areas.get_rows())]
        if marks != self.marks['table']:
            out.append((UGDATA, 'UgRandMark', 'table', marks))
        edited = dict(self.edited)
        if self.cur is not None:
            edited[self.cur] = self.spawn.get_rows()
        for name, rows in edited.items():
            if rows == self._spawn_rows(name):          # shown, not changed
                continue
            old = self.tables[name]['table']
            tmpl = old[0] if old else {'monsno': 0, 'version': 1, 'zukanflag': 1}
            if self.form16:
                vals = [({**tmpl, 'monsno': int(r[0]) | (int(r[1]) << 16), 'version': int(r[2]), 'zukanflag': int(r[3])})
                        for r in rows if r[0]]
            else:
                vals = [({**tmpl, 'monsno': int(r[0]), 'version': int(r[1]), 'zukanflag': int(r[2])}) for r in rows if r[0]]
            new = sorted(vals, key=lambda x: x['monsno'] & 0xFFFF)
            if new != old:
                out.append((UGDATA, name, 'table', new))
        rare = self.rare.get_rows()
        if rare != self._rare_rows():
            old = self.special['Sheet1']
            tmpl = old[0] if old else {}
            new = sorted(({**tmpl, 'id': int(r[0]), 'monsno': int(r[1]), 'version': int(r[2]),
                           'Dspecialrate': int(round(float(r[3]) * 10)), 'Pspecialrate': int(round(float(r[4]) * 10))}
                          for r in rare if r[1]), key=lambda x: x['id'])
            if new != old:
                out.append((UGDATA, 'UgSpecialPokemon', 'Sheet1', copy.deepcopy(new)))
        return out

    def keep(self):
        cur = self.cur
        ok = super().keep()
        if ok and cur is not None and self.built:
            self.table_list.select(cur, notify=False)
        return ok
