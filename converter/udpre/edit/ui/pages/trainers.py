"""Trainers and the Battle Tower.

Trainers: every TrainerTable.TrainerData row (class, name, prize, battle style, items, battle AI) and its TrainerPoke party,
shown as six member cards with the member's editor inline below them, plus the party as Showdown text (live preview,
"Use this party"). Battle Tower: the single / double battle stock rows (which trainers, which Pokémon sets they draw
from) and the Pokémon sets themselves (TowerTrainerTable.TrainerPoke), each set edited like a party member.

The operations: TrainerData set ops with key = the trainer index, TrainerPoke through game.set_party_slots, PokeID of a
stock row, the fields of a tower set."""
import copy
import tkinter as tk
from tkinter import messagebox, ttk

from ... import showdown
from ...game import EFFORTS, MASTER, SLOT_FIELDS, TALENTS
from ...project import set_op
from ..kit import Button, Link, Section, Segmented, frame, label, pill
from ..page import RecordPage
from ..theme import C, FONT, MONO, text_on, type_color
from ..widgets import BitsField, BoolField, FieldSet, IntField, Picker

SEXES = [(0, 'Male'), (1, 'Female'), (2, 'Genderless'), (3, 'Random')]
SEX_MARK = {0: '♂', 1: '♀'}
STAT_SHORT = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']
# the member fields in a fixed order (the order of the operations a save makes)
MEMBER_ORDER = ['MonsNo', 'FormNo', 'Level', 'IsRare', 'Sex', 'Seikaku', 'Tokusei', 'Item', 'Ball', 'Seal',
                'Waza1', 'Waza2', 'Waza3', 'Waza4'] + TALENTS + EFFORTS
# TrainerData fields in a fixed order (the form's fields, then the AI flags)
TRAINER_ORDER = ['TypeID', 'NameLabel', 'FightType', 'Gold', 'ArenaID', 'EffectID', 'UseItem1', 'UseItem2', 'UseItem3',
                 'UseItem4', 'HpRecoverFlag', 'GiftItem', 'AIBit']
# TrainerData.AIBit (enums.AI_FLAGS), worded as what the trainer does
AI_WORDS = [(0, 'Basic tactics'), (1, 'Stronger tactics'), (2, 'Expert tactics'), (3, 'Plays double battles well'),
            (4, 'Goes easy on you (merciful)'), (5, 'Uses its items in battle'), (6, 'Switches Pokémon out')]
BATTLE_STYLES = [(0, 'Single battle'), (1, 'Double battle')]
_clip = {'members': [], 'trainer': None}


def slot_label(g, s):
    return f'Lv. {s.get("Level", 0)} {g.pokemon_name(s.get("MonsNo", 0), s.get("FormNo", 0))}'


def plural(n, word):
    return f'{n} {word}{"" if n == 1 or word.endswith("mon") else "s"}'


def _names(page):
    """showdown.Names of the session's current game (built once per game)"""
    g = page.s.game
    cache = page.__dict__.setdefault('_sd_names', {})
    if id(g) not in cache:
        cache.clear()
        cache[id(g)] = showdown.Names(g)
    return cache[id(g)]


def _types_of(g, s):
    r = g.row(s.get('MonsNo', 0), s.get('FormNo', 0)) or g.row(s.get('MonsNo', 0))
    if r is None:
        return None, None
    return r['type1'], r['type2']


def _bind_all(w, seq, fn):
    w.bind(seq, fn)
    for ch in w.winfo_children():
        _bind_all(ch, seq, fn)


def _grid_label(master, text, r, c, first=False):
    label(master, text, style='Muted.TLabel', anchor='e', width=11).grid(
        row=r, column=c, sticky='e', padx=((0 if first else 18), 6), pady=2)


# --- a party member / tower set editor ------------------------------------------------------------------------------
class MemberEditor(ttk.Frame):
    """the fields of one TrainerPoke slot / tower set: species, form, level, shiny, gender, nature, ability, held item,
    ball, seal, four moves, IVs and EVs (compact six-stat grids). .fields = a FieldSet in MEMBER_ORDER."""

    def __init__(self, master, page, on_change=None):
        super().__init__(master, style='Studio.TFrame')
        self.page = page
        self.on_change = on_change
        c = page.c
        w = {}
        top = frame(self)
        top.pack(anchor='w', fill='x')
        _grid_label(top, 'Species', 0, 0, True)
        w['MonsNo'] = Picker(top, c.species0(), width=24)
        w['MonsNo'].grid(row=0, column=1, sticky='w', pady=2)
        _grid_label(top, 'Form', 0, 2)
        w['FormNo'] = Picker(top, [(0, '0')], width=22, allow_free=True)
        w['FormNo'].grid(row=0, column=3, sticky='w', pady=2)
        _grid_label(top, 'Level', 1, 0, True)
        lv = frame(top)
        lv.grid(row=1, column=1, sticky='w')
        w['Level'] = IntField(lv, 1, 100, width=5)
        w['Level'].pack(side='left')
        w['IsRare'] = BoolField(lv, text='Shiny  ★')
        w['IsRare'].pack(side='left', padx=(14, 0))
        _grid_label(top, 'Gender', 1, 2)
        w['Sex'] = Picker(top, SEXES, width=22)
        w['Sex'].grid(row=1, column=3, sticky='w', pady=2)
        _grid_label(top, 'Nature', 2, 0, True)
        w['Seikaku'] = Picker(top, c.natures(), width=24)
        w['Seikaku'].grid(row=2, column=1, sticky='w', pady=2)
        _grid_label(top, 'Ability', 2, 2)
        w['Tokusei'] = Picker(top, c.abilities(), width=22)
        w['Tokusei'].grid(row=2, column=3, sticky='w', pady=2)
        self.ab_hint = label(top, '', style='Faint.TLabel')
        self.ab_hint.grid(row=3, column=3, sticky='w')
        _grid_label(top, 'Held item', 3, 0, True)
        w['Item'] = Picker(top, c.items(), width=24)
        w['Item'].grid(row=3, column=1, sticky='w', pady=2)
        _grid_label(top, 'Ball id', 4, 0, True)
        bs = frame(top)
        bs.grid(row=4, column=1, sticky='w')
        w['Ball'] = IntField(bs, 0, 255, width=5)
        w['Ball'].pack(side='left')
        label(bs, 'Seal', style='Muted.TLabel').pack(side='left', padx=(14, 6))
        w['Seal'] = IntField(bs, width=6)
        w['Seal'].pack(side='left')
        self.move_bars = []
        for k in range(4):
            r, col = 5 + k // 2, 2 * (k % 2)
            _grid_label(top, f'Move {k + 1}', r, col, col == 0)
            cell = frame(top)
            cell.grid(row=r, column=col + 1, sticky='w', pady=2)
            p = Picker(cell, c.moves(), width=22)
            p.pack(side='left')
            bar = tk.Frame(cell, width=5, height=20, bg=C['line'])
            bar.pack(side='left', padx=(4, 0))
            self.move_bars.append(bar)
            w[f'Waza{k + 1}'] = p
        tk.Frame(top, height=6, bg=C['bg']).grid(row=4, column=2)
        grid = frame(self)
        grid.pack(anchor='w', pady=(10, 0))
        label(grid, 'IVs 0-31 · EVs 0-255 per stat, 510 in all', style='Faint.TLabel').grid(
            row=0, column=7, sticky='w', padx=(12, 0))
        for k, n in enumerate(STAT_SHORT):
            label(grid, n, style='Faint.TLabel', anchor='center').grid(row=0, column=k + 1)
        label(grid, 'IVs', style='Muted.TLabel', width=5, anchor='e').grid(row=1, column=0, sticky='e', padx=(0, 6))
        label(grid, 'EVs', style='Muted.TLabel', width=5, anchor='e').grid(row=2, column=0, sticky='e', padx=(0, 6))
        for k, f in enumerate(TALENTS):
            w[f] = IntField(grid, 0, 31, width=4)
            w[f].grid(row=1, column=k + 1, padx=2, pady=2)
        for k, f in enumerate(EFFORTS):
            w[f] = IntField(grid, 0, 255, width=4)
            w[f].grid(row=2, column=k + 1, padx=2, pady=2)
        links = frame(grid)
        links.grid(row=1, column=7, sticky='w', padx=(12, 0))
        Link(links, 'all 31', lambda: self._fill(TALENTS, 31)).pack(side='left')
        Link(links, 'all 0', lambda: self._fill(TALENTS, 0)).pack(side='left', padx=(8, 0))
        ev = frame(grid)
        ev.grid(row=2, column=7, sticky='w', padx=(12, 0))
        self.ev_total = label(ev, '', style='Muted.TLabel')
        self.ev_total.pack(side='left')
        Link(ev, 'clear', lambda: self._fill(EFFORTS, 0)).pack(side='left', padx=(8, 0))
        self.w = w
        self.fields = FieldSet({k: w[k] for k in MEMBER_ORDER})
        w['MonsNo'].bind('<<ComboboxSelected>>', lambda _e: self._species_changed(), add='+')
        w['MonsNo'].bind('<FocusOut>', lambda _e: self._species_changed(), add='+')
        for k in MEMBER_ORDER:
            ww = w[k]
            if isinstance(ww, Picker):
                ww.bind('<<ComboboxSelected>>', lambda _e: self._changed(), add='+')
            if isinstance(ww, (IntField, Picker)):
                ww.bind('<FocusOut>', lambda _e: self._changed(), add='+')
            if isinstance(ww, IntField):
                ww.bind('<KeyRelease>', lambda _e: self._totals(), add='+')
                ww.configure(command=self._changed)
            if isinstance(ww, BoolField):
                ww.configure(command=self._changed)
        self._species = None

    @property
    def g(self):
        return self.page.s.game

    def _fill(self, keys, v):
        for k in keys:
            self.w[k].set_value(v)
        self._changed()

    def load(self, slot):
        self.fields.load(slot)
        self._species = None
        self._species_changed(keep_form=True)
        self.w['FormNo'].set_value(slot.get('FormNo', 0))
        self._totals()

    def values(self):
        return self.fields.values()

    def _species_changed(self, keep_form=False):
        m = self.w['MonsNo'].get_value()
        if m is None or m == self._species:
            return
        self._species = m
        forms = self.page.c.forms_of(m) if m else [(0, '0')]
        fw = self.w['FormNo']
        cur = fw.get_value()
        fw.set_choices(forms)
        if not keep_form:
            fw.set_value(cur if cur in [v for v, _ in forms] else 0)
        r = self.g.row(m) if m else None
        if r is not None:
            ab = [self.g.ability_name(r['tokusei1'])]
            if r['tokusei2'] != r['tokusei1']:
                ab.append(self.g.ability_name(r['tokusei2']))
            if r['tokusei3'] not in (r['tokusei1'], r['tokusei2']):
                ab.append(self.g.ability_name(r['tokusei3']) + ' (hidden)')
            self.ab_hint.config(text='Its abilities: ' + ' · '.join(ab))
        else:
            self.ab_hint.config(text='')
        if not keep_form:
            self._changed()

    def _totals(self):
        tot = sum(int(self.w[f].get_value() or 0) for f in EFFORTS)
        self.ev_total.config(text=f'{tot} / 510', style='Error.TLabel' if tot > 510 else 'Muted.TLabel')
        g = self.g
        for k, bar in enumerate(self.move_bars):
            mid = self.w[f'Waza{k + 1}'].get_value()
            mv = g.moves[mid] if mid and 0 <= mid < len(g.moves) and g.moves[mid]['wazaNo'] == mid else None
            bar.config(bg=type_color(mv['type']) if mv else C['line'])

    def _changed(self):
        self._totals()
        if self.on_change:
            self.on_change()


# --- Showdown text of a party / of sets --------------------------------------------------------------------------------
class ShowdownPane(ttk.Frame):
    """editable Showdown text (left) and what it reads as (right, live); on_use(slots) takes the parsed Pokémon"""

    def __init__(self, master, page, use_text, on_use, single=False, hint=''):
        super().__init__(master, style='Studio.TFrame')
        self.page = page
        self.on_use = on_use
        self.single = single
        self.base = []
        self._after = None
        bar = frame(self)
        bar.pack(fill='x')
        Button(bar, use_text, self._use, kind='primary', small=True).pack(side='left')
        Link(bar, 'Start again from the current data', self.reset).pack(side='left', padx=(14, 0))
        Link(bar, 'Copy text', self._copy).pack(side='left', padx=(14, 0))
        if hint:
            label(self, hint, style='Faint.TLabel', wraplength=600, justify='left').pack(anchor='w', pady=(4, 0))
        pan = frame(self)
        pan.pack(fill='both', expand=True, pady=(6, 0))
        label(pan, 'Showdown text  (paste a team here)', style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        label(pan, 'What it reads as', style='Muted.TLabel').grid(row=0, column=1, sticky='w', padx=(10, 0))
        self.text = tk.Text(pan, width=40, height=26, font=(MONO, 9), wrap='none', undo=True, bd=0,
                            highlightthickness=1, highlightbackground=C['line2'], highlightcolor=C['accent'],
                            bg=C['bg'], fg=C['text'], insertbackground=C['text'], padx=6, pady=4)
        self.text.grid(row=1, column=0, sticky='nsew')
        self.prev = tk.Text(pan, width=40, height=26, font=(FONT, 9), wrap='word', bd=0, highlightthickness=1,
                            highlightbackground=C['line'], bg=C['soft'], fg=C['text'], padx=8, pady=4)
        self.prev.grid(row=1, column=1, sticky='nsew', padx=(10, 0))
        self.prev.tag_configure('bad', foreground=C['danger'])
        self.prev.tag_configure('ok', foreground=C['ok'])
        self.prev.tag_configure('head', font=(FONT, 9, 'bold'))
        self.prev.tag_configure('dim', foreground=C['muted'])
        self.prev.config(state='disabled')
        pan.columnconfigure(0, weight=1)
        pan.columnconfigure(1, weight=1)
        pan.rowconfigure(1, weight=1)
        self.text.bind('<KeyRelease>', lambda _e: self._soon())
        self.text.bind('<<Paste>>', lambda _e: self._soon(), add='+')

    def load(self, slots):
        self.base = copy.deepcopy(list(slots))
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', showdown.export(self.page.s.game, self.base, _names(self.page)))
        self.text.edit_reset()
        self.preview()

    def reset(self):
        self.load(self.base)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get('1.0', 'end').strip() + '\n')
        self.page.say('Showdown text copied to the clipboard.')

    def _soon(self):
        if self._after is not None:
            self.after_cancel(self._after)
        self._after = self.after(300, self.preview)

    def parse(self):
        slots, problems = showdown.parse(self.page.s.game, self.text.get('1.0', 'end'), self.base, _names(self.page))
        if self.single:
            if len(slots) > 1:
                problems = problems + [f'only the first Pokémon is used (the text has {len(slots)})']
            slots = slots[:1]
        elif len(slots) > 6:
            problems = problems + [f'a party holds six Pokémon - the text has {len(slots)}, the first six are used']
        return slots, problems

    def preview(self):
        self._after = None
        g = self.page.s.game
        try:
            slots, problems = self.parse()
        except Exception as e:      # a parse crash must not kill the page
            slots, problems = [], [f'cannot read the text: {e}']
        p = self.prev
        p.config(state='normal')
        p.delete('1.0', 'end')
        if problems:
            p.insert('end', plural(len(problems), 'problem') + '\n', ('bad', 'head'))
            for x in problems:
                p.insert('end', '•  ' + x + '\n', 'bad')
            p.insert('end', '\n')
        else:
            p.insert('end', 'Reads cleanly' + (f' - {plural(len(slots), "Pokémon")}' if slots else '') + '\n\n',
                     ('ok', 'head'))
        for k, s in enumerate(slots[:6] if not self.single else slots):
            head = f'{k + 1}.  {slot_label(g, s)}{"  " + SEX_MARK[s["Sex"]] if s.get("Sex") in SEX_MARK else ""}'
            head += '  ★' if s.get('IsRare') else ''
            p.insert('end', head + '\n', 'head')
            item = g.item_name(s['Item']) if s.get('Item') else 'no item'
            p.insert('end', f'     @ {item} · {g.nature_name(s.get("Seikaku", 0))} · '
                            f'{g.ability_name(s.get("Tokusei", 0))}\n', 'dim')
            mv = [g.move_name(s[f'Waza{i}']) for i in (1, 2, 3, 4) if s.get(f'Waza{i}')]
            p.insert('end', '     ' + (' · '.join(mv) or 'no moves') + '\n')
        p.config(state='disabled')

    def _use(self):
        slots, problems = self.parse()
        if not slots:
            messagebox.showinfo('Showdown text', 'The text has no Pokémon that can be read.'
                                + ('\n\n' + '\n'.join(problems[:12]) if problems else ''), parent=self)
            return
        if problems and not messagebox.askyesno('Showdown text', 'Some lines could not be read:\n' +
                                                '\n'.join(problems[:12]) + '\n\nUse what could be read?', parent=self):
            return
        self.on_use(slots)


# --- Trainers ---------------------------------------------------------------------------------------------------------
class TrainersPage(RecordPage):
    title = 'Trainers'
    subtitle = 'Every trainer battle: who it is, its party, the items it uses and how it fights'
    noun = 'trainer'
    columns = [('no', 'No.', 46, 'e'), ('cls', 'Class', 112, 'w'), ('name', 'Name', 92, 'w'), ('party', 'Party', 44, 'e'),
               ('top', 'Top Lv.', 52, 'e'), ('battle', 'Battle', 56, 'w')]
    list_width = 448
    VIEWS = [('party', 'Party'), ('showdown', 'Showdown text'), ('trainer', 'Trainer & battle AI')]

    # --- table ----------------------------------------------------------------------------------------------------
    def extra_left(self, f):
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.cls_filter = ttk.Combobox(row, values=['All classes'], state='readonly', width=22,
                                       style='Studio.TCombobox')
        self.cls_filter.current(0)
        self.cls_filter.pack(side='left')
        self.cls_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))
        self.only_double = tk.BooleanVar()
        ttk.Checkbutton(row, text='Double battles', variable=self.only_double, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))

    def _apply_filters(self):
        cls = self.cls_filter.get() if self.cls_filter.current() > 0 else None
        ed, dbl = self.only_edited.get(), self.only_double.get()

        def pred(key, vals):
            if ed and key not in self.table.edited:
                return False
            if dbl and vals[5] != 'Double':
                return False
            return cls is None or vals[1] == cls
        self.table.filter(pred=pred if (cls or ed or dbl) else None)
        self._count()

    def _class_names(self):
        g = self.s.game
        out = {}
        for tt in g.trainer_types:
            out.setdefault(tt['TrainerID'], g.msg.text('dp_trainers_type', tt['LabelTrType'], tt['LabelTrType']))
        return out

    def _parties(self):
        """{trainer index: its TrainerPoke row} and {party row ID: trainer index} (game.trainer_party's rule: the row
        whose ID is the index, the first one when several)"""
        g = self.s.game
        by_id = {}
        for r in g.trainer_pokes:
            by_id.setdefault(r['ID'], r)
        self._pidx = {i: i for i in range(len(g.trainers)) if i in by_id}
        self._pidx_game = id(g)
        return by_id

    def _party_index(self):
        if getattr(self, '_pidx_game', None) != id(self.s.game):
            self._parties()
        return self._pidx

    def rows(self):
        g = self.s.game
        cls = self._class_names()
        by_id = self._parties()
        out = []
        for i, t in enumerate(g.trainers):
            out.append((i, self._values(i, t, by_id.get(i), cls)))
        names = sorted({v[1] for _k, v in out if v[1]}, key=str.lower)
        if hasattr(self, 'cls_filter'):
            self.cls_filter.configure(values=['All classes'] + names)
        return out

    def row(self, key):
        g = self.s.game
        return self._values(key, g.trainers[key], g.trainer_party(key), self._class_names())

    def _values(self, i, t, p, cls):
        g = self.s.game
        slots = g.party_slots(p) if p else []
        top = max((s.get('Level', 0) for s in slots), default='')
        c = cls.get(t['TypeID'], f'type {t["TypeID"]}') if t['TypeID'] >= 0 else ''
        return (f'{i:04d}', c, g.trainer_name(i), len(slots), top, 'Double' if t.get('FightType') else 'Single')

    def op_key(self, op):
        if op.get('op') != 'set' or op.get('obj') != 'TrainerTable':
            return None
        if op.get('list') == 'TrainerData':
            return op.get('key')
        if op.get('list') == 'TrainerPoke':
            return self._party_index().get(op.get('key'))
        return None

    def record_name(self, key):
        g = self.s.game
        t = g.trainers[key]
        return f'{g.trainer_type_name(t["TypeID"])} {g.trainer_name(key)}'.strip()

    # --- record ---------------------------------------------------------------------------------------------------
    def build(self, body):
        self.members = []
        self.sel = None
        self._shown = None
        self.view = 'party'
        top = frame(body)
        top.pack(fill='x', pady=(4, 12))
        self.views = Segmented(top, self.VIEWS, command=self.switch, value='party')
        self.views.pack(side='left')
        Link(top, 'Paste trainer', self.paste_trainer).pack(side='right', padx=(12, 20))
        Link(top, 'Copy trainer', self.copy_trainer).pack(side='right')
        self.frames = {v: frame(body) for v, _ in self.VIEWS}
        self._build_party(self.frames['party'])
        sd = self.frames['showdown']
        self.sd = ShowdownPane(sd, self, 'Use this party', self._use_showdown,
                               hint='Edit or paste the team; the right side shows what it reads as. "Use this party" '
                                    'replaces the party (Keep saves it). Ball and seal stay from the slot replaced.')
        self.sd.pack(fill='both', expand=True, padx=(0, 20))
        self._build_trainer(self.frames['trainer'])
        self.switch('party')

    def _build_party(self, f):
        sec = Section(f, 'Party', hint='click a Pokémon to edit it below')
        sec.pack(fill='x', padx=(0, 20))
        self.cards = frame(sec.body)
        self.cards.pack(fill='x')
        for k in range(6):
            self.cards.columnconfigure(k, weight=1, uniform='card')
        bar = frame(sec.body)
        bar.pack(fill='x', pady=(8, 0))
        self.pbtn = {}
        for name, text, fn in (('add', '+ Add', self.add_member), ('remove', 'Remove', self.remove_member),
                               ('left', '◀ Move left', lambda: self.move_member(-1)),
                               ('right', 'Move right ▶', lambda: self.move_member(1)),
                               ('copy', 'Copy', self.copy_members), ('copyall', 'Copy party', self.copy_party),
                               ('paste', 'Paste', self.paste_members)):
            b = Button(bar, text, fn, small=True)
            b.pack(side='left', padx=(0, 4))
            self.pbtn[name] = b
        self.clip_note = label(bar, '', style='Faint.TLabel')
        self.clip_note.pack(side='left', padx=(8, 0))
        self.no_party = label(f, '', style='Muted.TLabel')
        self.ed_box = frame(f)
        self.ed_box.pack(fill='x', padx=(0, 20), pady=(16, 0))
        head = frame(self.ed_box)
        head.pack(fill='x')
        self.ed_title = label(head, '', style='Section.TLabel')
        self.ed_title.pack(side='left')
        self.ed_link = Link(head, '', self._open_species)
        self.ed_link.pack(side='right')
        tk.Frame(self.ed_box, height=1, bg=C['line']).pack(fill='x', pady=(3, 6))
        self.editor = MemberEditor(self.ed_box, self, on_change=self._flush)
        self.editor.pack(fill='x')

    def _build_trainer(self, f):
        c = self.c
        w = {}
        s1 = Section(f, 'Trainer')
        s1.pack(fill='x', padx=(0, 20))
        g1 = s1.body
        _grid_label(g1, 'Class', 0, 0, True)
        w['TypeID'] = Picker(g1, c.trainer_types(), width=24)
        w['TypeID'].grid(row=0, column=1, sticky='w', pady=2)
        _grid_label(g1, 'Name', 0, 2)
        w['NameLabel'] = Picker(g1, c.trainer_names(), width=24)
        w['NameLabel'].grid(row=0, column=3, sticky='w', pady=2)
        _grid_label(g1, 'Battle style', 1, 0, True)
        w['FightType'] = Picker(g1, BATTLE_STYLES, width=24)
        w['FightType'].grid(row=1, column=1, sticky='w', pady=2)
        _grid_label(g1, 'Prize money', 1, 2)
        pm = frame(g1)
        pm.grid(row=1, column=3, sticky='w')
        w['Gold'] = IntField(pm, 0, 255, width=6)
        w['Gold'].pack(side='left')
        label(pm, 'base value, 0-255', style='Faint.TLabel').pack(side='left', padx=(8, 0))
        _grid_label(g1, 'Arena id', 2, 0, True)
        w['ArenaID'] = IntField(g1, width=8)
        w['ArenaID'].grid(row=2, column=1, sticky='w', pady=2)
        _grid_label(g1, 'Effect id', 2, 2)
        w['EffectID'] = IntField(g1, width=8)
        w['EffectID'].grid(row=2, column=3, sticky='w', pady=2)
        _grid_label(g1, 'Gift item', 3, 0, True)
        w['GiftItem'] = Picker(g1, c.items(), width=24)
        w['GiftItem'].grid(row=3, column=1, sticky='w', pady=2)
        _grid_label(g1, 'Restores HP', 3, 2)
        w['HpRecoverFlag'] = BoolField(g1)
        w['HpRecoverFlag'].grid(row=3, column=3, sticky='w', pady=2)
        s2 = Section(f, 'Items it uses', hint='the items it can use in battle')
        s2.pack(fill='x', padx=(0, 20), pady=(16, 0))
        for k in range(4):
            _grid_label(s2.body, f'Item {k + 1}', k // 2, 2 * (k % 2), k % 2 == 0)
            w[f'UseItem{k + 1}'] = Picker(s2.body, c.items(), width=24)
            w[f'UseItem{k + 1}'].grid(row=k // 2, column=2 * (k % 2) + 1, sticky='w', pady=2)
        s3 = Section(f, 'Battle AI', hint='how the trainer picks its moves')
        s3.pack(fill='x', padx=(0, 20), pady=(16, 0))
        w['AIBit'] = BitsField(s3.body, AI_WORDS, columns=2)
        w['AIBit'].pack(anchor='w')
        self.ai_note = label(s3.body, '', style='Faint.TLabel')
        self.ai_note.pack(anchor='w', pady=(4, 0))
        for v in w['AIBit'].vars.values():
            v.trace_add('write', lambda *_a: self._ai_note())
        self.tfields = self.track(FieldSet({k: w[k] for k in TRAINER_ORDER}))

    def _ai_note(self):
        try:
            v = self.tfields.widgets['AIBit'].get_value()
        except tk.TclError:
            return
        self.ai_note.config(text=f'Stored as the number {v}' + ('' if v else ' (no AI flags: plays at random)'))

    def switch(self, view):
        if view != self.view:
            self._flush()
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        if view == 'showdown' and self.key is not None:
            self.sd.load(self.members)
        if self.scroller is not None:
            self.scroller.top()

    def show(self, i):
        g = self.s.game
        t = g.trainers[i]
        p = g.trainer_party(i)
        self.members = g.party_slots(p) if p else []
        self.has_party = p is not None
        if not (self._shown == i and self.sel is not None and self.sel < len(self.members)):
            self.sel = 0 if self.members else None
        self._shown = i
        self.tfields.load(t)
        self._ai_note()
        cls = g.trainer_type_name(t['TypeID']) if t['TypeID'] >= 0 else ''
        pills = []
        if t.get('FightType'):
            pills.append(('Double battle', C['accent']))
        pills.append((plural(len(self.members), 'Pokémon'), C['soft'], C['muted']))
        if self.members:
            pills.append((f'Lv. {max(s.get("Level", 0) for s in self.members)}', C['soft'], C['muted']))
        pills.append((f'Prize {t.get("Gold", 0)}', C['soft'], C['muted']))
        sub = f'Trainer {i:04d}' + (f' · {cls}' if cls else '') + f' · name label {t["NameLabel"]}'
        if p is None:
            sub += ' · no party row (the party cannot be changed)'
        self.set_header(f'{cls} {g.trainer_name(i)}'.strip(), sub, pills)
        self._render_cards()
        self._load_member()
        if self.view == 'showdown':
            self.sd.load(self.members)

    def extra_state(self):
        self._flush()
        return (repr(self.members),)

    def collect(self, i):
        self._flush()
        g = self.s.game
        t = g.trainers[i]
        new = self.tfields.values()
        ops = [set_op(g, MASTER, 'TrainerTable', 'TrainerData', t, f, v, key=i) for f, v in new.items()
               if f in t and t[f] != v]
        p = g.trainer_party(i)
        if p is None:
            raise ValueError(f'trainer {i} has no party row')
        tmp = dict(p)
        g.set_party_slots(tmp, self.members)
        for f, v in tmp.items():
            if p[f] != v:
                ops.append(set_op(g, MASTER, 'TrainerTable', 'TrainerPoke', p, f, v))
        return ops

    # --- party cards ----------------------------------------------------------------------------------------------
    def _render_cards(self):
        for w in self.cards.winfo_children():
            w.destroy()
        self._card_w = {}
        for k, s in enumerate(self.members[:6]):
            self._card(k, s)
        if len(self.members) < 6 and getattr(self, 'has_party', True):
            add = tk.Frame(self.cards, bg=C['soft'], highlightthickness=1, highlightbackground=C['line'],
                           cursor='hand2')
            add.grid(row=0, column=len(self.members), sticky='nsew', padx=(0, 6))
            tk.Label(add, text='+\nAdd a Pokémon', bg=C['soft'], fg=C['muted'], font=(FONT, 9),
                     justify='center').pack(expand=True, pady=30)
            _bind_all(add, '<Button-1>', lambda _e: self.add_member())
        n = len(self.members)
        on = self.sel is not None
        self.pbtn['add'].set_enabled(n < 6 and getattr(self, 'has_party', True))
        self.pbtn['remove'].set_enabled(on)
        self.pbtn['left'].set_enabled(on and self.sel > 0)
        self.pbtn['right'].set_enabled(on and self.sel < n - 1)
        self.pbtn['copy'].set_enabled(on)
        self.pbtn['copyall'].set_enabled(n > 0)
        self.pbtn['paste'].set_enabled(bool(_clip['members']) and getattr(self, 'has_party', True))
        self.clip_note.config(text=f'clipboard: {plural(len(_clip["members"]), "Pokémon")}' if _clip['members'] else '')

    def _card(self, k, s):
        g = self.s.game
        on = k == self.sel
        bg = C['accent_soft'] if on else C['bg']
        old = self._card_w.get(k)
        if old is not None:
            old.destroy()
        f = tk.Frame(self.cards, bg=bg, highlightthickness=2 if on else 1,
                     highlightbackground=C['accent'] if on else C['line2'], cursor='hand2')
        f.grid(row=0, column=k, sticky='nsew', padx=(0, 6))
        self._card_w[k] = f
        t1, t2 = _types_of(g, s)
        band = tk.Frame(f, height=5, bg=bg)
        band.pack(fill='x')
        band.pack_propagate(False)
        tk.Frame(band, bg=type_color(t1)).pack(side='left', fill='both', expand=True)
        if t2 is not None and t2 != t1:
            tk.Frame(band, bg=type_color(t2)).pack(side='left', fill='both', expand=True)
        head = tk.Frame(f, bg=bg)
        head.pack(fill='x', padx=6, pady=(4, 0))
        tk.Label(head, text=f'{k + 1}', bg=bg, fg=C['faint'], font=(FONT, 8)).pack(side='right', anchor='n')
        tk.Label(head, text=g.pokemon_name(s.get('MonsNo', 0), s.get('FormNo', 0)), bg=bg, fg=C['text'],
                 font=(FONT, 9, 'bold'), wraplength=84, justify='left', anchor='w').pack(side='left', fill='x')
        marks = f'Lv. {s.get("Level", 0)}'
        if s.get('Sex') in SEX_MARK:
            marks += '  ' + SEX_MARK[s['Sex']]
        line = tk.Frame(f, bg=bg)
        line.pack(fill='x', padx=6)
        tk.Label(line, text=marks, bg=bg, fg=C['text'], font=(FONT, 9)).pack(side='left')
        if s.get('IsRare'):
            tk.Label(line, text='★', bg=bg, fg='#d18b00', font=(FONT, 9, 'bold')).pack(side='left', padx=(4, 0))
        ty = tk.Frame(f, bg=bg)
        ty.pack(fill='x', padx=6, pady=(2, 0))
        for t in ([t1] if t2 is None or t2 == t1 else [t1, t2]):
            if t is None:
                continue
            tk.Label(ty, text=g.type_name(t), bg=type_color(t), fg=text_on(type_color(t)), font=(FONT, 7, 'bold'),
                     padx=3).pack(side='left', padx=(0, 3))
        item = g.item_name(s['Item']) if s.get('Item') else 'no item'
        tk.Label(f, text='@ ' + item, bg=bg, fg=C['muted'] if s.get('Item') else C['faint'], font=(FONT, 8),
                 wraplength=96, justify='left', anchor='w').pack(fill='x', padx=6, pady=(4, 0))
        mv = tk.Frame(f, bg=bg)
        mv.pack(fill='x', padx=6, pady=(3, 6))
        if not any(s.get(f'Waza{n}') for n in (1, 2, 3, 4)):
            tk.Label(mv, text='no moves set\n(default moves)', bg=bg, fg=C['faint'], font=(FONT, 8),
                     anchor='w', justify='left').pack(fill='x')
        for n in (1, 2, 3, 4):
            m = s.get(f'Waza{n}')
            if m or any(s.get(f'Waza{x}') for x in (1, 2, 3, 4)):
                tk.Label(mv, text=g.move_name(m) if m else '-', bg=bg, fg=C['text'] if m else C['faint'],
                         font=(FONT, 8), anchor='w', wraplength=96, justify='left').pack(fill='x')
        _bind_all(f, '<Button-1>', lambda _e, k=k: self.pick_member(k))

    def _load_member(self):
        if self.sel is None or self.sel >= len(self.members):
            self.ed_box.pack_forget()
            if not self.members:
                self.no_party.config(text='No Pokémon in this party.' + (' Add one with "+ Add" or paste a team as '
                                                                          'Showdown text.' if getattr(
                                                                              self, 'has_party', True) else ''))
                self.no_party.pack(anchor='w', pady=(12, 0))
            return
        self.no_party.pack_forget()
        if not self.ed_box.winfo_ismapped():
            self.ed_box.pack(fill='x', padx=(0, 20), pady=(16, 0))
        s = self.members[self.sel]
        self.editor.load(s)
        self._ed_head(s)

    def _ed_head(self, s):
        g = self.s.game
        self.ed_title.config(text=f'Pokémon {self.sel + 1} of {len(self.members)} · '
                                  f'{g.pokemon_name(s.get("MonsNo", 0), s.get("FormNo", 0))}')
        self.ed_link.config(text=f'Open {g.species_name(s.get("MonsNo", 0))} on the Pokémon page' if s.get('MonsNo')
                            else '')

    def _flush(self):
        """the member editor's values -> the selected member (and its card)"""
        if self.sel is None or self.sel >= len(self.members):
            return
        try:
            vals = self.editor.values()
        except tk.TclError:
            return
        m = self.members[self.sel]
        new = dict(m, **vals)
        if new != m:
            self.members[self.sel] = new
            self._card(self.sel, new)
            self._ed_head(new)

    def _open_species(self):
        self._flush()
        if self.sel is None:
            return
        s = self.members[self.sel]
        m, f = s.get('MonsNo', 0), s.get('FormNo', 0)
        if not m:
            return
        g = self.s.game
        self.app.show('pokemon', (m, f) if g.row(m, f) is not None and (f == 0 or g.row(m, f)['valid_flag']) else (m, 0))

    def pick_member(self, k):
        self._flush()
        if k == self.sel:
            return
        self.sel = k
        self._render_cards()
        self._load_member()

    def _after_party_change(self, sel):
        self.sel = sel if self.members and sel is not None else (0 if self.members else None)
        if self.sel is not None:
            self.sel = max(0, min(self.sel, len(self.members) - 1))
        self._render_cards()
        self._load_member()

    def add_member(self):
        self._flush()
        if not getattr(self, 'has_party', True):
            return
        if len(self.members) >= 6:
            self.say('A party holds six Pokémon at most.')
            return
        new = copy.deepcopy(self.members[-1]) if self.members else {f: 0 for f in SLOT_FIELDS}
        if not self.members:
            new.update({'MonsNo': 1, 'Level': 5, 'Sex': 3, 'Seal': -1})
        self.members.append(new)
        self._after_party_change(len(self.members) - 1)

    def remove_member(self):
        self._flush()
        if self.sel is None:
            return
        del self.members[self.sel]
        self._after_party_change(self.sel)

    def move_member(self, d):
        self._flush()
        i = self.sel
        if i is None or not 0 <= i + d < len(self.members):
            return
        self.members[i], self.members[i + d] = self.members[i + d], self.members[i]
        self._after_party_change(i + d)

    def copy_members(self):
        self._flush()
        if self.sel is not None:
            _clip['members'] = [copy.deepcopy(self.members[self.sel])]
            self._render_cards()
            self.say(f'Copied {slot_label(self.s.game, self.members[self.sel])}.')

    def copy_party(self):
        self._flush()
        _clip['members'] = copy.deepcopy(self.members)
        self._render_cards()
        self.say(f'Copied the party ({plural(len(self.members), "Pokémon")}).')

    def paste_members(self):
        """the clipboard replaces the selected Pokémon (several: from there on), or joins the party when none is
        selected; six at most"""
        self._flush()
        if not _clip['members'] or not getattr(self, 'has_party', True):
            return
        if self.sel is not None:
            at = self.sel
            self.members[at:at + 1] = copy.deepcopy(_clip['members'])
        else:
            at = len(self.members)
            self.members += copy.deepcopy(_clip['members'])
        self.members = self.members[:6]
        self._after_party_change(at)

    def _use_showdown(self, slots):
        self.members = [dict(s) for s in slots[:6]]
        self.sel = 0 if self.members else None
        self._render_cards()
        self._load_member()
        self.views.pick('party')
        self.say(f'The party is now the {plural(len(self.members), "Pokémon")} of the Showdown text - '
                 f'leave the trainer or press Keep to save it.')

    def copy_trainer(self):
        self._flush()
        _clip['trainer'] = (self.tfields.values(), copy.deepcopy(self.members))
        self.say(f'Copied {self.record_name(self.key)} (details, AI and party).')

    def paste_trainer(self):
        if not _clip['trainer'] or self.key is None:
            self.say('Copy a trainer first.')
            return
        vals, members = _clip['trainer']
        self.tfields.load(vals)
        self._ai_note()
        if getattr(self, 'has_party', True):
            self.members = copy.deepcopy(members)
        self.sel = 0 if self.members else None
        self._render_cards()
        self._load_member()
        if self.view == 'showdown':
            self.sd.load(self.members)
        self.say('Pasted the copied trainer - leave the trainer or press Keep to save it.')


# --- Battle Tower -----------------------------------------------------------------------------------------------------
STOCK = {'single': ('TowerSingleStockTable', 'TowerSingleStock'), 'double': ('TowerDoubleStockTable', 'TowerDoubleStock')}
TOWER_MODES = [('single', 'Single battles'), ('double', 'Double battles'), ('set', 'Pokémon sets')]


class TowerPage(RecordPage):
    """keys: ('single', stock row ID), ('double', stock row ID), ('set', Pokémon set ID)"""
    title = 'Battle Tower'
    subtitle = 'The Battle Tower\'s trainers, the Pokémon sets each one draws from, and the sets themselves'
    noun = 'Battle Tower entry'
    nouns = 'entries'
    columns = [('id', 'ID', 84, 'e'), ('name', 'Trainer', 140, 'w'), ('info', 'Pokémon sets', 168, 'w')]
    list_width = 448
    TITLES = {'single': ('ID', 'Trainer', 'Pokémon sets'), 'double': ('ID', 'Trainers', 'Pokémon sets'),
              'set': ('Set ID', 'Pokémon', 'Level · item')}

    def extra_left(self, f):
        self.mode = 'single'
        self.views = Segmented(f, TOWER_MODES, command=self.switch_mode, value='single')
        self.views.pack(anchor='w', pady=(6, 0))
        row = frame(f)
        row.pack(fill='x', pady=(4, 0))
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left')

    def _apply_filters(self):
        if self.only_edited.get():
            self.table.filter(pred=lambda key, _v: key in self.table.edited)
        else:
            self.table.filter(pred=None)
        self._count()

    def _count(self):
        n, m = self.table.count(), len(self.table.rows)
        keys = {k for k, _ in self.table.rows}
        ed = len(self.table.edited & keys)
        many = {'single': 'single-battle entries', 'double': 'double-battle entries', 'set': 'Pokémon sets'}[self.mode]
        self.count.config(text=(f'{n} of {m} {many}' if n != m else f'{m} {many}') + (f'  ·  {ed} edited' if ed else ''))

    def switch_mode(self, mode):
        if mode == self.mode:
            return
        if not self.keep():
            self.views.pick(self.mode, notify=False)
            return
        self._set_mode(mode)
        self.table.select_first()

    def _set_mode(self, mode):
        self.mode = mode
        self.views.pick(mode, notify=False)
        self.key = None
        self._base = None
        self.table.columns = [(c[0], t, c[2], c[3]) for c, t in zip(self.columns, self.TITLES[mode])]
        self.table.sort = None
        self.reload_rows()
        for m, fr in self.bodies.items():
            if m == ('set' if mode == 'set' else 'stock'):
                fr.pack(fill='both', expand=True)
            else:
                fr.pack_forget()

    def goto(self, key):
        self.ensure()
        if isinstance(key, tuple) and len(key) == 2 and key[0] in ('single', 'double', 'set'):
            if key[0] != self.mode:
                if not self.keep():
                    return
                self._set_mode(key[0])
            self.table.select(key)

    # --- data -----------------------------------------------------------------------------------------------------
    def stock_rows(self, mode):
        obj, lst = STOCK[mode]
        return self.s.game.table(MASTER, obj)[lst]

    def stock_row(self, key):
        return next((r for r in self.stock_rows(key[0]) if r['ID'] == key[1]), None)

    def sets(self):
        return {p['ID']: p for p in self.s.game.tower['TrainerPoke']}

    def tname(self, tid):
        g = self.s.game
        tt = g.tower['TrainerData']
        if 0 <= tid < len(tt):
            t = tt[tid]
            name = g.msg.text('dp_trainers_name', t['NameLabel'], t['NameLabel'])
            cls = g.trainer_type_name(t['TrainerType']) if 'TrainerType' in t else ''
            return f'{cls} {name}'.strip()
        return '-'

    @staticmethod
    def tids(r):
        return [t for t in (r['TrainerID'] if isinstance(r['TrainerID'], list) else [r['TrainerID']]) if t >= 0]

    def rows(self):
        g = self.s.game
        sets = self.sets()
        if self.mode == 'set':
            return [(('set', p['ID']), self._set_values(p)) for p in g.tower['TrainerPoke']]
        out = []
        for r in self.stock_rows(self.mode):
            out.append(((self.mode, r['ID']), self._stock_values(r, sets)))
        return out

    def row(self, key):
        if key[0] == 'set':
            p = self.sets().get(key[1])
            return self._set_values(p) if p else None
        r = self.stock_row(key)
        return self._stock_values(r, self.sets()) if r else None

    def _set_values(self, p):
        g = self.s.game
        item = g.item_name(p['Item']) if p.get('Item') else 'no item'
        return (p['ID'], g.pokemon_name(p['MonsNo'], p['FormNo']), f'Lv. {p["Level"]} · {item}')

    def _stock_values(self, r, sets):
        g = self.s.game
        names = []
        for pid in r['PokeID']:
            p = sets.get(pid)
            names.append(g.species_name(p['MonsNo']) if p else f'#{pid}?')
        return (r['ID'], ' & '.join(self.tname(t) for t in self.tids(r)), ', '.join(names))

    def op_key(self, op):
        if op.get('op') != 'set':
            return None
        obj = op.get('obj')
        if obj == 'TowerTrainerTable' and op.get('list') == 'TrainerPoke':
            return ('set', op.get('key'))
        for mode, (o, lst) in STOCK.items():
            if obj == o and op.get('list') == lst:
                return (mode, op.get('key'))
        return None

    def record_name(self, key):
        g = self.s.game
        if key[0] == 'set':
            p = self.sets().get(key[1])
            return f'set {key[1]} ({g.pokemon_name(p["MonsNo"], p["FormNo"])})' if p else f'set {key[1]}'
        r = self.stock_row(key)
        who = ' & '.join(self.tname(t) for t in self.tids(r)) if r else ''
        return f'{"double" if key[0] == "double" else "single"}-battle entry {key[1]}' + (f' ({who})' if who else '')

    # --- record ---------------------------------------------------------------------------------------------------
    def build(self, body):
        self.pickers = []
        self.bodies = {'stock': frame(body), 'set': frame(body)}
        self._build_stock(self.bodies['stock'])
        self._build_set(self.bodies['set'])
        self.bodies['stock'].pack(fill='both', expand=True)

    def _build_stock(self, f):
        top = frame(f)
        top.pack(fill='x', pady=(4, 12))
        self.stock_views = Segmented(top, [('sets', 'Pokémon sets'), ('showdown', 'Showdown text')],
                                     command=self._stock_view, value='sets')
        self.stock_views.pack(side='left')
        self.st_frames = {'sets': frame(f), 'showdown': frame(f)}
        sec = Section(self.st_frames['sets'], 'Who you battle')
        sec.pack(fill='x', padx=(0, 20))
        self.who = frame(sec.body)
        self.who.pack(fill='x')
        sec = Section(self.st_frames['sets'], 'Pokémon sets it draws from',
                      hint='the tower picks this entry\'s team from these sets')
        sec.pack(fill='x', padx=(0, 20), pady=(16, 0))
        self.slots = frame(sec.body)
        self.slots.pack(fill='x')
        self.sd_stock = ShowdownPane(self.st_frames['showdown'], self, 'Apply to these sets', self._stock_showdown,
                                     hint='The text of every set this entry uses, in order. "Apply to these sets" '
                                          'changes those sets right away (other entries that use them see it too).')
        self.sd_stock.pack(fill='both', expand=True, padx=(0, 20))
        self.stock_view = 'sets'
        self.st_frames['sets'].pack(fill='both', expand=True)

    def _build_set(self, f):
        top = frame(f)
        top.pack(fill='x', pady=(4, 12))
        self.set_views = Segmented(top, [('set', 'Set'), ('showdown', 'Showdown text'), ('used', 'Used by')],
                                   command=self._set_view, value='set')
        self.set_views.pack(side='left')
        self.set_link = Link(top, '', self._open_species)
        self.set_link.pack(side='right', padx=(0, 20))
        self.se_frames = {'set': frame(f), 'showdown': frame(f), 'used': frame(f)}
        self.editor = MemberEditor(self.se_frames['set'], self)
        self.editor.pack(fill='x', padx=(0, 20))
        self.set_fields = self.track(self.editor.fields)
        self.sd_set = ShowdownPane(self.se_frames['showdown'], self, 'Use this text', self._set_showdown, single=True,
                                   hint='"Use this text" puts the parsed set into the form (Keep saves it).')
        self.sd_set.pack(fill='both', expand=True, padx=(0, 20))
        self.used = frame(self.se_frames['used'])
        self.used.pack(fill='both', expand=True, padx=(0, 20))
        self.set_view = 'set'
        self.se_frames['set'].pack(fill='both', expand=True)

    def _stock_view(self, v):
        self.stock_view = v
        for k, fr in self.st_frames.items():
            fr.pack(fill='both', expand=True) if k == v else fr.pack_forget()
        if v == 'showdown' and self.key is not None and self.key[0] != 'set':
            self.sd_stock.load(self._chosen_sets())

    def _set_view(self, v):
        self.set_view = v
        for k, fr in self.se_frames.items():
            fr.pack(fill='both', expand=True) if k == v else fr.pack_forget()
        if self.key is not None and self.key[0] == 'set':
            if v == 'showdown':
                self.sd_set.load([dict(self.sets()[self.key[1]], **self.editor.values())])
            elif v == 'used':
                self._used_by(self.key[1])

    def set_choices(self):
        g = self.s.game
        cache = self.__dict__.setdefault('_set_choice', {})
        if cache.get('game') is not g:
            cache['game'] = g
            cache['list'] = [(p['ID'], f'{p["ID"]}  {g.pokemon_name(p["MonsNo"], p["FormNo"])}  Lv. {p["Level"]}')
                             for p in g.tower['TrainerPoke']]
        return cache['list']

    def show(self, key):
        g = self.s.game
        if key[0] == 'set':
            p = self.sets()[key[1]]
            self.editor.load(p)
            t1, t2 = _types_of(g, p)
            pills = [pill(self.pill_parent(), g.type_name(t), type_color(t)) for t in
                     ([t1] if t2 is None or t2 == t1 else [t1, t2]) if t is not None]
            pills.append((f'Lv. {p["Level"]}', C['soft'], C['muted']))
            n = sum(1 for m in STOCK for r in self.stock_rows(m) if key[1] in r['PokeID'])
            pills.append((f'used by {n} entr{"y" if n == 1 else "ies"}', C['soft'], C['muted']))
            self.set_header(g.pokemon_name(p['MonsNo'], p['FormNo']) + ('  ★' if p.get('IsRare') else ''),
                            f'Battle Tower Pokémon set {key[1]}', pills)
            self.set_link.config(text=f'Open {g.species_name(p["MonsNo"])} on the Pokémon page')
            if self.set_view == 'showdown':
                self.sd_set.load([dict(p)])
            elif self.set_view == 'used':
                self._used_by(key[1])
            return
        r = self.stock_row(key)
        tids = self.tids(r)
        for w in self.who.winfo_children():
            w.destroy()
        tt = g.tower['TrainerData']
        for t in tids:
            line = frame(self.who)
            line.pack(fill='x', pady=1)
            label(line, self.tname(t), style='Studio.TLabel', font=(FONT, 10, 'bold')).pack(side='left')
            extra = f'   tower trainer {t}'
            if 0 <= t < len(tt):
                extra += f' · name label {tt[t]["NameLabel"]}'
            label(line, extra, style='Muted.TLabel').pack(side='left')
        label(self.who, f'Battle music {r.get("BattleBGM", "-")} · victory music {r.get("WinBGM", "-")}',
              style='Faint.TLabel').pack(anchor='w', pady=(4, 0))
        for w in self.slots.winfo_children():
            w.destroy()
        self.pickers = []
        self.summaries = []
        ch = self.set_choices()
        for k, pid in enumerate(r['PokeID']):
            label(self.slots, f'Set {k + 1}', style='Muted.TLabel', width=6, anchor='e').grid(
                row=2 * k, column=0, sticky='e', padx=(0, 6), pady=(4, 0))
            p = Picker(self.slots, ch, width=36)
            p.set_value(pid)
            p.grid(row=2 * k, column=1, sticky='w', pady=(4, 0))
            p.bind('<<ComboboxSelected>>', lambda _e, k=k: self._summary(k), add='+')
            p.bind('<FocusOut>', lambda _e, k=k: self._summary(k), add='+')
            Link(self.slots, 'Open set', lambda k=k: self._open_set(k)).grid(row=2 * k, column=2, sticky='w',
                                                                              padx=(12, 0), pady=(4, 0))
            sm = frame(self.slots)
            sm.grid(row=2 * k + 1, column=1, columnspan=2, sticky='w', pady=(2, 4))
            self.pickers.append(p)
            self.summaries.append(sm)
            self._summary(k)
        mode = 'Double battle' if key[0] == 'double' else 'Single battle'
        pills = [(mode, C['accent'] if key[0] == 'double' else C['soft'], None if key[0] == 'double' else C['muted']),
                 (plural(len(r['PokeID']), 'set'), C['soft'], C['muted'])]
        self.set_header(' & '.join(self.tname(t) for t in tids) or 'No trainer',
                        f'{mode} entry {r["ID"]} · Battle Tower', pills)
        if self.stock_view == 'showdown':
            self.sd_stock.load(self._chosen_sets())

    def _summary(self, k):
        g = self.s.game
        sm = self.summaries[k]
        for w in sm.winfo_children():
            w.destroy()
        p = self.sets().get(self.pickers[k].get_value())
        if p is None:
            label(sm, 'not a Pokémon set - pick one from the list', style='Error.TLabel').pack(side='left')
            return
        t1, t2 = _types_of(g, p)
        for t in ([t1] if t2 is None or t2 == t1 else [t1, t2]):
            if t is not None:
                tk.Label(sm, text=g.type_name(t), bg=type_color(t), fg=text_on(type_color(t)), font=(FONT, 7, 'bold'),
                         padx=3).pack(side='left', padx=(0, 3))
        item = g.item_name(p['Item']) if p.get('Item') else 'no item'
        mv = ' · '.join(g.move_name(p[f'Waza{i}']) for i in (1, 2, 3, 4) if p.get(f'Waza{i}'))
        label(sm, f' {g.nature_name(p["Seikaku"])} · @ {item} · {mv}', style='Muted.TLabel').pack(side='left')

    def _chosen_sets(self):
        sets = self.sets()
        return [dict(sets[x]) for x in (p.get_value() for p in self.pickers) if x in sets]

    def extra_state(self):
        if self.key is not None and self.key[0] != 'set':
            return tuple(repr(p.get_value()) for p in self.pickers)
        return ()

    def collect(self, key):
        g = self.s.game
        if key[0] == 'set':
            p = self.sets()[key[1]]
            return [set_op(g, MASTER, 'TowerTrainerTable', 'TrainerPoke', p, f, v)
                    for f, v in self.editor.values().items() if f in p and p[f] != v]
        obj, lst = STOCK[key[0]]
        r = self.stock_row(key)
        ids = [p.get_value() for p in self.pickers]
        if None in ids:
            raise ValueError('pick a Pokémon set for every slot')
        if ids != list(r['PokeID']):
            return [set_op(g, MASTER, obj, lst, r, 'PokeID', ids)]
        return []

    # --- actions --------------------------------------------------------------------------------------------------
    def _open_set(self, k):
        pid = self.pickers[k].get_value()
        if pid is None or pid not in self.sets():
            return
        self.goto(('set', pid))

    def _open_species(self):
        if self.key is None or self.key[0] != 'set':
            return
        v = self.editor.values()
        m, f = v.get('MonsNo', 0), v.get('FormNo', 0)
        if m:
            g = self.s.game
            self.app.show('pokemon', (m, f) if g.row(m, f) is not None else (m, 0))

    def _set_showdown(self, slots):
        p = self.sets()[self.key[1]]
        self.editor.load(dict(p, **slots[0]))
        self.set_views.pick('set')
        self.say('The set now holds the Showdown text - leave the set or press Keep to save it.')

    def _stock_showdown(self, parsed):
        """the Showdown save: the parsed Pokémon -> the fields of the sets this entry uses, kept now"""
        if not self.keep():
            return
        g = self.s.game
        recs = self.sets()
        ids = [p.get_value() for p in self.pickers]
        ops = []
        for pid, new in zip(ids, parsed):
            rec = recs.get(pid)
            if rec is not None:
                for f2, v in new.items():
                    if f2 in rec and f2 != 'ID' and rec[f2] != v:
                        ops.append(set_op(g, MASTER, 'TowerTrainerTable', 'TrainerPoke', rec, f2, v))
        n = self.s.commit(ops)
        self.__dict__.pop('_set_choice', None)
        self.app.changed(f'Kept {plural(n, "change")} to the Pokémon sets of {self.record_name(self.key)}.')
        self.reload_rows()
        self.load(self.key)

    def _used_by(self, pid):
        for w in self.used.winfo_children():
            w.destroy()
        hits = {m: [r for r in self.stock_rows(m) if pid in r['PokeID']] for m in STOCK}
        if not any(hits.values()):
            label(self.used, 'No single or double battle entry uses this set.', style='Muted.TLabel').pack(anchor='w')
            return
        for m, rows in hits.items():
            if not rows:
                continue
            sec = Section(self.used, 'Single battles' if m == 'single' else 'Double battles',
                          hint=f'{len(rows)} entr{"y" if len(rows) == 1 else "ies"} - click to open')
            sec.pack(fill='x', pady=(0, 14))
            box = frame(sec.body)
            box.pack(fill='x')
            for k, r in enumerate(rows[:60]):
                who = ' & '.join(self.tname(t) for t in self.tids(r))
                Link(box, f'{r["ID"]}  {who}', lambda key=(m, r['ID']): self.goto(key)).grid(
                    row=k // 2, column=k % 2, sticky='w', padx=(0, 24))
            if len(rows) > 60:
                label(sec.body, f'... and {len(rows) - 60} more', style='Muted.TLabel').pack(anchor='w')

    def refresh(self):
        self.__dict__.pop('_set_choice', None)
        super().refresh()
