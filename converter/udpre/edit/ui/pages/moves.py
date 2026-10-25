"""Moves (WazaTable of Pml/personal_masterdatas + the move's battle animation row, BattleDataTable.BattleWazaData of
Battle/battle_masterdatas) and TMs (ItemTable.WazaMachine + the TM item's group_id = its compatibility bit).

Both pages show what the record means in plain words (what a move does, who learns it, which TM teaches it) and link to
the Pokémon, item and TM pages."""
import tkinter as tk
from tkinter import ttk

from ... import enums
from ...game import BATTLE, PERSONAL
from ...project import set_op
from ..kit import Link, Section, Segmented, frame, label, pill, type_pill
from ..page import RecordPage
from ..theme import C, FONT
from ..widgets import BitsField, BoolField, FieldSet, FloatField, IntField, Picker, TextField

SEQUENCE_DIR = 'StreamingAssets/AssetAssistant/Battle/btlv/waza/sequence/'
ANIM_FIELDS = [('CmdSeqName', 'Animation'), ('CmdSeqNameLegend', 'Legendary variant'),
               ('NotShortenTurnType0', 'Full-length (turn type 0)'), ('NotShortenTurnType1', 'Full-length (turn type 1)'),
               ('TurnType1', 'Turn type 1'), ('TurnType2', 'Turn type 2'), ('TurnType3', 'Turn type 3'),
               ('TurnType4', 'Turn type 4')]
CATEGORY_COLORS = {0: '#8a93a3', 1: '#c75a2c', 2: '#3f6fd8'}      # Status / Physical / Special
MOVE_VIEWS = [('battle', 'Battle'), ('effects', 'Effects'), ('flags', 'Flags'), ('anim', 'Animation'),
              ('learn', 'Who learns it')]
WAZA_OBJS = {('WazaTable', 'Waza'), ('BattleDataTable', 'BattleWazaData')}


# --- small shared helpers (the items page uses them too) ------------------------------------------------------------
def plural(n, word, many=None):
    return f'{n} {word if n == 1 else (many or word + "s")}'


def fields_grid(parent, specs, columns=2, label_width=14, pady=2):
    """lays out fields in a grid and returns their FieldSet: specs = [(label, key, kind, extra, width)] with kind int /
    float / text / choice / bool / bits (extra = (lo, hi) / choices / bits); a spec None leaves a cell empty"""
    widgets = {}
    for k, spec in enumerate(specs):
        if spec is None:
            continue
        lab, key, kind, extra, width = (list(spec) + [None, None])[:5]
        r, c = divmod(k, columns)
        ttk.Label(parent, text=lab, width=label_width, anchor='e', style='Muted.TLabel').grid(
            row=r, column=2 * c, sticky='e', padx=(0 if c == 0 else 18, 6), pady=pady)
        if kind == 'int':
            lo, hi = extra if extra else (-2 ** 31, 2 ** 32 - 1)
            w = IntField(parent, lo, hi, width=width or 8)
        elif kind == 'float':
            w = FloatField(parent, width=width or 10)
        elif kind == 'text':
            w = TextField(parent, width=width or 24)
        elif kind == 'choice':
            w = Picker(parent, extra, width=width or 22)
        elif kind == 'bool':
            w = BoolField(parent)
        elif kind == 'bits':
            w = BitsField(parent, extra, columns=width or 2)
        else:
            raise ValueError(kind)
        w.grid(row=r, column=2 * c + 1, sticky='w', pady=pady)
        widgets[key] = w
    return FieldSet(widgets)


def watch(fieldset, fn):
    """fn() after a key or a pick in any field of the set (live summaries)"""
    for w in fieldset.widgets.values():
        if isinstance(w, (ttk.Combobox, ttk.Entry, ttk.Spinbox)):
            w.bind('<KeyRelease>', lambda _e: fn(), add='+')
            w.bind('<<ComboboxSelected>>', lambda _e: fn(), add='+')
            w.bind('<FocusOut>', lambda _e: fn(), add='+')
        if isinstance(w, ttk.Spinbox):
            w.configure(command=fn)
        if isinstance(w, BoolField):
            w.var.trace_add('write', lambda *_a: fn())
        if isinstance(w, BitsField):
            for v in w.vars.values():
                v.trace_add('write', lambda *_a: fn())


def link_grid(parent, entries, columns=3, cap=150, more_text='more'):
    """entries = [(text, command)] as links in a grid (the first `cap`), then '... and N more'"""
    box = frame(parent)
    box.pack(fill='x', anchor='w')
    for k, (text, fn) in enumerate(entries[:cap]):
        Link(box, text, fn).grid(row=k // columns, column=k % columns, sticky='w', padx=(0, 22))
    if len(entries) > cap:
        label(parent, f'... and {len(entries) - cap} {more_text}', style='Muted.TLabel').pack(anchor='w')
    return box


def data_token(game, session):
    """changes whenever the game data or your edits change (cache key of derived indexes)"""
    ops = session.project.ops
    return (id(game), len(ops), id(ops[-1]) if ops else None)


def learners(page):
    """{wazaNo: {'level': {key}, 'egg': {key}, 'tm': {key}}} over every Pokémon row (cached per data state)"""
    g = page.s.game
    tok = data_token(g, page.s)
    if getattr(page, '_learn_tok', None) == tok:
        return page._learn
    out = {}

    def add(mv, kind, key):
        if mv:
            out.setdefault(mv, {}).setdefault(kind, set()).add(key)
    tms = g.tm_list()
    for r in g.species_rows():
        key = g.key_of(r)
        try:
            for _lv, mv in g.learnset(r):
                add(mv, 'level', key)
        except (IndexError, KeyError):
            pass
        try:
            bits = g.tm_bits(r)
        except Exception:
            bits = []
        for bit, t, _it in tms:
            if bit < len(bits) and bits[bit]:
                add(t['wazaNo'], 'tm', key)
    for e in g.egg_moves:
        for mv in e.get('wazaNo') or []:
            add(mv, 'egg', (e.get('no', 0), e.get('formNo', 0)))
    page._learn, page._learn_tok = out, tok
    return out


def tm_label(game, t):
    return game.item_name(t['itemNo'])


# --- Moves -------------------------------------------------------------------------------------------------------------
class MovesPage(RecordPage):
    title = 'Moves'
    subtitle = 'Every move: power, accuracy and PP, what it does, its flags and animation - and who learns it'
    noun = 'move'
    columns = [('no', 'No.', 44, 'e'), ('name', 'Name', 128, 'w'), ('type', 'Type', 66, 'w'), ('cat', 'Category', 64, 'w'),
               ('pow', 'Power', 44, 'e'), ('acc', 'Acc.', 40, 'e'), ('pp', 'PP', 34, 'e')]
    list_width = 470

    # --- table ----------------------------------------------------------------------------------------------------
    def extra_left(self, f):
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.type_filter = ttk.Combobox(row, values=['All types'] + [n for _, n in self.c.types()], state='readonly',
                                        width=13, style='Studio.TCombobox')
        self.type_filter.current(0)
        self.type_filter.pack(side='left')
        self.type_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.cat_filter = ttk.Combobox(row, values=['All categories'] + [n for _, n in enums.DAMAGE_TYPES],
                                       state='readonly', width=13, style='Studio.TCombobox')
        self.cat_filter.current(0)
        self.cat_filter.pack(side='left', padx=(6, 0))
        self.cat_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))
        self.hide_unused = tk.BooleanVar()
        ttk.Checkbutton(row, text='Hide unused', variable=self.hide_unused, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(8, 0))

    def _apply_filters(self):
        t = self.type_filter.current() - 1
        cat = self.cat_filter.current() - 1
        ed, hide = self.only_edited.get(), self.hide_unused.get()

        def pred(key, _vals):
            if ed and key not in self.table.edited:
                return False
            m = self.move(key)
            if m is None:
                return False
            if hide and not m['isValid']:
                return False
            if t >= 0 and m['type'] != t:
                return False
            return cat < 0 or m['damageType'] == cat
        self.table.filter(pred=pred)
        self._count()

    def move(self, n):
        ms = self.s.game.moves
        if 0 <= n < len(ms) and ms[n]['wazaNo'] == n:
            return ms[n]
        return next((m for m in ms if m['wazaNo'] == n), None)

    def rows(self):
        return [(m['wazaNo'], self._values(m)) for m in self.s.game.moves if m['wazaNo']]

    def row(self, key):
        m = self.move(key)
        return self._values(m) if m else None

    def _values(self, m):
        g = self.s.game
        cat = dict(enums.DAMAGE_TYPES).get(m['damageType'], str(m['damageType']))
        name = g.move_name(m['wazaNo']) + ('' if m['isValid'] else '  (unused)')
        acc = '—' if m['hitPer'] > 100 else m['hitPer']
        return (f'{m["wazaNo"]:03d}', name, g.type_name(m['type']), cat, m['power'] or '—', acc, m['basePP'])

    def op_key(self, op):
        if op.get('op') == 'set' and (op.get('obj'), op.get('list')) in WAZA_OBJS:
            return op.get('key')
        return None

    def record_name(self, key):
        return self.s.game.move_name(key)

    def search_items(self):
        g = self.s.game
        return [(f'{m["wazaNo"]:03d} {g.move_name(m["wazaNo"])}', m['wazaNo']) for m in g.moves if m['wazaNo']]

    # --- record ---------------------------------------------------------------------------------------------------
    def build(self, body):
        c = self.c
        self.views = Segmented(body, MOVE_VIEWS, command=self.switch, value='battle')
        self.views.pack(anchor='w', pady=(4, 12))
        self.frames = {v: frame(body) for v, _ in MOVE_VIEWS}
        # battle
        b = self.frames['battle']
        s = Section(b, 'Basics', hint='accuracy 101 = never misses · power 0 = no damage of its own')
        s.pack(fill='x')
        self.main = self.track(fields_grid(s.body, [
            ('Type', 'type', 'choice', c.types(), 16), ('Category', 'damageType', 'choice', enums.DAMAGE_TYPES, 16),
            ('Power', 'power', 'int', (0, 255), 6), ('Accuracy', 'hitPer', 'int', (0, 255), 6),
            ('PP', 'basePP', 'int', (0, 255), 6), ('In the game', 'isValid', 'bool'),
        ], columns=2, label_width=12))
        self.summary = tk.Label(s.body, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', justify='left',
                                padx=10, pady=6, wraplength=560)
        self.summary.grid(row=3, column=0, columnspan=4, sticky='we', pady=(8, 0))
        s = Section(b, 'How it hits')
        s.pack(fill='x', pady=(16, 0))
        self.misc = self.track(fields_grid(s.body, [
            ('Kind of effect', 'category', 'choice', enums.MOVE_CATEGORIES, 31),
            ('Priority', 'priority', 'int', (-128, 127), 6),
            ('Targets', 'target', 'choice', enums.MOVE_TARGETS, 31), ('Critical rank', 'criticalRank', 'int', (0, 255), 6),
            ('Hits at least', 'hitCountMin', 'int', (0, 255), 6), ('Hits at most', 'hitCountMax', 'int', (0, 255), 6),
            ('Flinch %', 'shrinkPer', 'int', (0, 255), 6), ('AI sequence', 'aiSeqNo', 'int', (0, 65535), 6),
        ], columns=2, label_width=13))
        label(s.body, 'Hits 0 / 0 = one hit · priority above 0 moves first (Quick Attack +1) · critical rank 1 = high '
              'critical-hit ratio', style='Faint.TLabel').grid(row=4, column=0, columnspan=4, sticky='w', pady=(4, 0))
        s = Section(b, 'Healing and recoil')
        s.pack(fill='x', pady=(16, 0))
        self.heal = self.track(fields_grid(s.body, [
            ('Of damage dealt %', 'damageRecoverRatio', 'int', (-128, 127), 6),
            ('Of max HP %', 'hpRecoverRatio', 'int', (-128, 127), 6),
        ], columns=2, label_width=17))
        label(s.body, 'Positive = the user heals that share (Giga Drain 50, Recover 50) · negative = recoil (Double-Edge '
              '-33)', style='Faint.TLabel').grid(row=1, column=0, columnspan=4, sticky='w', pady=(4, 0))
        # effects
        e = self.frames['effects']
        s = Section(e, 'Status condition', hint='chance 0 = always (when the move hits)')
        s.pack(fill='x')
        self.sick = self.track(fields_grid(s.body, [
            ('Condition', 'sickID', 'choice', enums.MOVE_SICK, 20), ('Chance %', 'sickPer', 'int', (0, 255), 6),
            ('Lasts', 'sickCont', 'choice', enums.SICK_CONT, 20), None,
            ('Turns, at least', 'sickTurnMin', 'int', (0, 255), 6), ('Turns, at most', 'sickTurnMax', 'int', (0, 255), 6),
        ], columns=2, label_width=13))
        self.sick_text = tk.Label(s.body, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', padx=10,
                                  pady=6, justify='left', wraplength=560)
        self.sick_text.grid(row=3, column=0, columnspan=4, sticky='we', pady=(8, 0))
        s = Section(e, 'Stat changes', hint='up to three · stages -6 to +6 · chance 0 = always')
        s.pack(fill='x', pady=(16, 0))
        grid = frame(s.body)
        grid.pack(anchor='w')
        for col, t in enumerate(('', 'Stat', 'Stages', 'Chance %')):
            label(grid, t, style='Faint.TLabel').grid(row=0, column=col, sticky='w', padx=(0, 10))
        rk = {}
        for k in (1, 2, 3):
            label(grid, f'Change {k}', style='Muted.TLabel').grid(row=k, column=0, sticky='e', padx=(0, 10), pady=2)
            rk[f'rankEffType{k}'] = Picker(grid, enums.RANK_EFFECTS, width=16)
            rk[f'rankEffType{k}'].grid(row=k, column=1, sticky='w', padx=(0, 10), pady=2)
            rk[f'rankEffValue{k}'] = IntField(grid, -128, 127, width=5)
            rk[f'rankEffValue{k}'].grid(row=k, column=2, sticky='w', padx=(0, 10), pady=2)
            rk[f'rankEffPer{k}'] = IntField(grid, 0, 255, width=5)
            rk[f'rankEffPer{k}'].grid(row=k, column=3, sticky='w', pady=2)
        self.rank = self.track(FieldSet(rk))
        self.rank_text = tk.Label(s.body, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', padx=10,
                                  pady=6, justify='left', wraplength=560)
        self.rank_text.pack(fill='x', pady=(8, 0))
        # flags
        fl = self.frames['flags']
        s = Section(fl, 'Move flags', hint='what the battle rules check about this move')
        s.pack(fill='x')
        self.flags = self.track(FieldSet({'flags': BitsField(s.body, enums.MOVE_FLAGS, columns=2)}))
        self.flags.widgets['flags'].pack(anchor='w')
        self.flag_text = label(s.body, '', style='Muted.TLabel')
        self.flag_text.pack(anchor='w', pady=(8, 0))
        # animation
        an = self.frames['anim']
        s = Section(an, 'Battle animation', hint='sequence files of the game (btlv/waza/sequence)')
        s.pack(fill='x')
        self.anim_note = tk.Label(s.body, text='', bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9), anchor='w',
                                  padx=10, pady=6)
        names = sorted({k[len(SEQUENCE_DIR):] for k in self.s.stack.index if k.startswith(SEQUENCE_DIR)})
        self.seq_count = len(names)
        seqs = [('', '(none)')] + [(n, n) for n in names]
        self.anim_box = frame(s.body)
        self.anim_box.pack(anchor='w')
        self.anim = self.track(fields_grid(self.anim_box, [(lab, f, 'choice', seqs, 26) for f, lab in ANIM_FIELDS],
                                           columns=1, label_width=22))
        label(s.body, 'Type to filter a list of ' + plural(self.seq_count, 'sequence') + '. "(none)" = no animation for '
              'that case. Copying another move\'s sequence gives this move its look.', style='Faint.TLabel',
              wraplength=560).pack(anchor='w', pady=(8, 0))
        self.anim_copy = frame(s.body)
        self.anim_copy.pack(anchor='w', pady=(4, 0))
        # who learns it
        self.learn_box = frame(self.frames['learn'])
        self.learn_box.pack(fill='both', expand=True)
        for fs in (self.main, self.misc, self.heal, self.sick, self.rank, self.flags):
            watch(fs, self._live)
        self.switch('battle')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        if view == 'learn' and self.key is not None:
            self._learn_view()
        if self.scroller is not None:
            self.scroller.top()

    def anim_row(self, n):
        t = self.s.game.table(BATTLE, 'BattleDataTable')['BattleWazaData']
        if 0 <= n < len(t) and t[n]['WazaNo'] == n:
            return t[n]
        return next((r for r in t if r['WazaNo'] == n), None)

    def on_show(self):
        if self.built and self.key is not None:
            self._subtitle()

    def show(self, n):
        g = self.s.game
        m = self.move(n)
        pp = self.pill_parent()
        pills = [type_pill(pp, g, m['type']),
                 pill(pp, dict(enums.DAMAGE_TYPES).get(m['damageType'], '?'), CATEGORY_COLORS.get(m['damageType'], '#8a93a3'))]
        if not m['isValid']:
            pills.append(pill(pp, 'not in the game', C['danger_soft'], C['danger']))
        self.set_header(g.move_name(n), '', pills)
        for fs in (self.main, self.misc, self.heal, self.sick, self.rank, self.flags):
            fs.load(m)
        a = self.anim_row(n)
        for w in self.anim.widgets.values():
            w.configure(state='normal')
        self.anim.load(a or {})
        if not a:
            for w in self.anim.widgets.values():
                w.configure(state='disabled')
        if a:
            self.anim_note.pack_forget()
        else:
            self.anim_note.config(text='This move has no animation row in BattleWazaData - there is nothing to set here.')
            self.anim_note.pack(fill='x', pady=(0, 8), before=self.anim_box)
        for w in self.anim_copy.winfo_children():
            w.destroy()
        if a:
            label(self.anim_copy, 'Same animation as:', style='Muted.TLabel').pack(side='left')
            same = [r['WazaNo'] for r in g.table(BATTLE, 'BattleDataTable')['BattleWazaData']
                    if r['WazaNo'] != n and r['WazaNo'] and a.get('CmdSeqName') and r.get('CmdSeqName') == a['CmdSeqName']]
            if not same:
                label(self.anim_copy, ' no other move', style='Muted.TLabel').pack(side='left')
            for w in same[:6]:
                Link(self.anim_copy, g.move_name(w), lambda w=w: self.goto(w)).pack(side='left', padx=(8, 0))
        self._subtitle()
        self._live()
        if getattr(self, 'view', None) == 'learn':
            self._learn_view()

    def _subtitle(self):
        g = self.s.game
        n = self.key
        if n is None:
            return
        parts = [f'No. {n:03d}']
        tms = [tm_label(g, t) for t in g.tms if t['wazaNo'] == n]
        if tms:
            parts.append('taught by ' + ', '.join(tms))
        lr = learners(self).get(n, {})
        who = set().union(*lr.values()) if lr else set()
        parts.append(f'{plural(len(who), "Pokémon", "Pokémon")} learn it' if who else 'no Pokémon learns it')
        self.h_sub.config(text=' · '.join(parts))

    def _live(self):
        try:
            v = {}
            for fs in (self.main, self.misc, self.heal, self.sick, self.rank, self.flags):
                v.update(fs.values())
        except tk.TclError:
            return
        g = self.s.game
        cat = dict(enums.DAMAGE_TYPES).get(v.get('damageType'), '?')
        bits = [f'{g.type_name(v.get("type", 0))} · {cat}']
        pw, acc = v.get('power', 0), v.get('hitPer', 0)
        if v.get('damageType') and pw:
            bits.append(f'{pw} power')
        bits.append('never misses' if acc and acc > 100 else f'{acc}% accuracy')
        bits.append(f'{v.get("basePP", 0)} PP (up to {v.get("basePP", 0) * 8 // 5} with PP Max)')
        lo, hi = v.get('hitCountMin', 0), v.get('hitCountMax', 0)
        if hi > 1:
            bits.append(f'hits {lo}-{hi} times' if lo != hi else f'hits {hi} times')
        if v.get('priority'):
            bits.append(f'priority {v["priority"]:+d}')
        if v.get('shrinkPer'):
            bits.append(f'{v["shrinkPer"]}% flinch')
        if v.get('damageRecoverRatio', 0) > 0:
            bits.append(f'heals {v["damageRecoverRatio"]}% of the damage')
        elif v.get('damageRecoverRatio', 0) < 0:
            bits.append(f'{-v["damageRecoverRatio"]}% recoil')
        if v.get('hpRecoverRatio', 0) > 0:
            bits.append(f'heals {v["hpRecoverRatio"]}% of max HP')
        self.summary.config(text='  ·  '.join(bits))
        sid = v.get('sickID', 0)
        if not sid:
            self.sick_text.config(text='It causes no status condition.')
        else:
            name = dict(enums.MOVE_SICK).get(sid, f'condition {sid}')
            per = v.get('sickPer', 0)
            t = (f'{per}% chance to cause {name}' if per else f'Causes {name}')
            cont = v.get('sickCont', 0)
            if cont:
                t += f' · lasts: {dict(enums.SICK_CONT).get(cont, cont)}'
            a, b = v.get('sickTurnMin', 0), v.get('sickTurnMax', 0)
            if b:
                t += f' · {a}-{b} turns' if a != b else f' · {b} turns'
            self.sick_text.config(text=t + '.')
        who = 'the user' if v.get('target') == 7 or v.get('category') == 7 else 'the target'
        lines = []
        for k in (1, 2, 3):
            st = v.get(f'rankEffType{k}', 0)
            if not st:
                continue
            val, per = v.get(f'rankEffValue{k}', 0), v.get(f'rankEffPer{k}', 0)
            name = dict(enums.RANK_EFFECTS).get(st, f'stat {st}')
            verb = 'Raises' if val > 0 else 'Lowers'
            lines.append(f'{verb} {who}\'s {name} by {plural(abs(val), "stage")}' + (f' ({per}% chance)' if per else ''))
        self.rank_text.config(text='\n'.join(lines) if lines else 'It changes no stats.')
        fl = self.flags.widgets['flags']
        on = [n for b, n in enums.MOVE_FLAGS if fl.vars[b].get()]
        self.flag_text.config(text=f'{len(on)} flag{"" if len(on) == 1 else "s"} on' + (': ' + ', '.join(on[:6]) +
                                                                                     (' ...' if len(on) > 6 else '')
                                                                                     if on else ''))

    def collect(self, n):
        g = self.s.game
        m = self.move(n)
        new = {}
        for fs in (self.main, self.misc, self.heal, self.sick, self.rank, self.flags):
            new.update(fs.values())
        ops = [set_op(g, PERSONAL, 'WazaTable', 'Waza', m, f, v) for f, v in new.items() if f in m and m[f] != v]
        a = self.anim_row(n)
        if a is not None:
            for f, v in self.anim.values().items():
                if a.get(f) != v:
                    ops.append(set_op(g, BATTLE, 'BattleDataTable', 'BattleWazaData', a, f, v))
        return ops

    # --- who learns it --------------------------------------------------------------------------------------------
    def refresh(self):
        self._learn_tok = None
        super().refresh()

    def _learn_view(self):
        box = self.learn_box
        for w in box.winfo_children():
            w.destroy()
        g = self.s.game
        n = self.key
        tms = [(i, t) for i, t in enumerate(g.tms) if t['wazaNo'] == n]
        s = Section(box, 'Taught by TM')
        s.pack(fill='x', pady=(0, 14))
        if tms:
            link_grid(s.body, [(f'{tm_label(g, t)}  (machine {t["machineNo"]})', lambda i=i: self.app.show('tms', i))
                               for i, t in tms])
        else:
            label(s.body, 'No TM teaches it.', style='Muted.TLabel').pack(anchor='w')
        lr = learners(self).get(n, {})
        for kind, title, none in (('level', 'Learned by leveling up', 'No Pokémon learns it by level.'),
                                  ('tm', 'Can learn it from its TM', 'No Pokémon has the TM bit set.' if tms else None),
                                  ('egg', 'Egg move of', 'It is no Pokémon\'s egg move.')):
            keys = sorted(lr.get(kind, ()))
            if none is None and not keys:
                continue
            s = Section(box, title, hint=plural(len(keys), 'Pokémon', 'Pokémon') + (' - click to open' if keys else ''))
            s.pack(fill='x', pady=(0, 14))
            if not keys:
                label(s.body, none, style='Muted.TLabel').pack(anchor='w')
                continue
            link_grid(s.body, [(g.pokemon_name(*k), lambda k=k: self.app.show('pokemon', k)) for k in keys],
                      cap=120, more_text='more Pokémon')


# --- TMs ---------------------------------------------------------------------------------------------------------------
class TMsPage(RecordPage):
    title = 'TMs'
    subtitle = 'Which move each TM teaches, its item and compatibility bit - and how many Pokémon can learn it'
    noun = 'TM'
    columns = [('tm', 'TM', 70, 'w'), ('move', 'Move', 130, 'w'), ('type', 'Type', 70, 'w'), ('bit', 'Bit', 40, 'e'),
               ('mons', 'Pokémon', 60, 'e')]
    list_width = 430

    def extra_left(self, f):
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.type_filter = ttk.Combobox(row, values=['All types'] + [n for _, n in self.c.types()], state='readonly',
                                        width=13, style='Studio.TCombobox')
        self.type_filter.current(0)
        self.type_filter.pack(side='left')
        self.type_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))

    def _apply_filters(self):
        t = self.type_filter.current() - 1
        ed = self.only_edited.get()

        def pred(key, _vals):
            if ed and key not in self.table.edited:
                return False
            if t >= 0:
                m = self._move(self.s.game.tms[key]['wazaNo'])
                return m is not None and m['type'] == t
            return True
        self.table.filter(pred=pred)
        self._count()

    def _move(self, n):
        ms = self.s.game.moves
        if 0 <= n < len(ms) and ms[n]['wazaNo'] == n:
            return ms[n]
        return next((m for m in ms if m['wazaNo'] == n), None)

    def bit_counts(self):
        """{bit: number of Pokémon rows with it set} (cached per data state)"""
        g = self.s.game
        tok = data_token(g, self.s)
        if getattr(self, '_bits_tok', None) == tok:
            return self._bits
        out = {}
        for r in g.species_rows():
            try:
                bits = g.tm_bits(r)
            except Exception:
                continue
            for b, v in enumerate(bits):
                if v:
                    out[b] = out.get(b, 0) + 1
        self._bits, self._bits_tok = out, tok
        return out

    def bit_of(self, t):
        it = self.s.game.item(t['itemNo'])
        return it['group_id'] if it is not None else 0

    def rows(self):
        return [(i, self._values(i)) for i in range(len(self.s.game.tms))]

    def row(self, key):
        return self._values(key)

    def _values(self, i):
        g = self.s.game
        t = g.tms[i]
        m = self._move(t['wazaNo'])
        bit = self.bit_of(t)
        it = g.item(t['itemNo'])
        is_tm = it is not None and it['group'] == 4 and bit > 0
        n = self.bit_counts().get(bit - 1, 0) if is_tm else '—'
        return (tm_label(g, t), g.move_name(t['wazaNo']), g.type_name(m['type']) if m else '-', bit, n)

    def op_key(self, op):
        if op.get('op') != 'set' or op.get('obj') != 'ItemTable':
            return None
        g = self.s.game
        if op.get('list') == 'WazaMachine':
            return next((i for i, t in enumerate(g.tms) if t['machineNo'] == op.get('key')), None)
        if op.get('list') == 'Item' and op.get('field') == 'group_id':
            return next((i for i, t in enumerate(g.tms) if t['itemNo'] == op.get('key')), None)
        return None

    def record_name(self, i):
        g = self.s.game
        t = g.tms[i]
        return f'{tm_label(g, t)} ({g.move_name(t["wazaNo"])})'

    def build(self, body):
        s = Section(body, 'What this TM is')
        s.pack(fill='x')
        self.form = self.track(fields_grid(s.body, [
            ('TM item', 'itemNo', 'choice', self.c.items(), 28), ('Teaches the move', 'wazaNo', 'choice', self.c.moves(), 28),
            ('Compatibility bit', 'group_id', 'int', (0, 255), 6)], columns=1, label_width=16))
        watch(self.form, self._live)
        self.live = tk.Label(s.body, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', justify='left',
                             padx=10, pady=6, wraplength=600)
        self.live.grid(row=3, column=0, columnspan=2, sticky='we', pady=(8, 0))
        self.links = frame(s.body)
        self.links.grid(row=4, column=0, columnspan=2, sticky='w', pady=(6, 0))
        label(s.body, 'The compatibility bit is the TM item\'s group id: a Pokémon can learn this TM when bit (group id '
              '- 1) of its TM compatibility is set - tick it per Pokémon on the Pokémon page, TMs view. The machine '
              'number is the row\'s id and is not edited.', style='Faint.TLabel', wraplength=600, justify='left').grid(
            row=5, column=0, columnspan=2, sticky='w', pady=(10, 0))
        self.who = Section(body, 'Pokémon that can learn it')
        self.who.pack(fill='x', pady=(18, 0))

    def show(self, i):
        g = self.s.game
        t = g.tms[i]
        it = g.item(t['itemNo'])
        m = self._move(t['wazaNo'])
        pp = self.pill_parent()
        pills = []
        if m:
            pills = [type_pill(pp, g, m['type']),
                     pill(pp, dict(enums.DAMAGE_TYPES).get(m['damageType'], '?'),
                          CATEGORY_COLORS.get(m['damageType'], '#8a93a3'))]
        self.set_header(f'{tm_label(g, t)}  {g.move_name(t["wazaNo"])}',
                        f'Machine {t["machineNo"]} · row {i} of the TM table · item {t["itemNo"]:04d}', pills)
        self.form.load(dict(t, group_id=it['group_id'] if it else 0))
        self._live()
        self._who(i)

    def _live(self):
        g = self.s.game
        v = self.form.values()
        it = g.item(v['itemNo']) if v.get('itemNo') is not None else None
        bit = v.get('group_id', 0)
        notes = []
        m = self._move(v['wazaNo']) if v.get('wazaNo') is not None else None
        if m:
            cat = dict(enums.DAMAGE_TYPES).get(m['damageType'], '?')
            pw = f'{m["power"]} power, ' if m['power'] else ''
            notes.append(f'Teaches {g.move_name(m["wazaNo"])}: {g.type_name(m["type"])} {cat.lower()}, {pw}'
                         f'{"never misses" if m["hitPer"] > 100 else str(m["hitPer"]) + "% accuracy"}, {m["basePP"]} PP.')
        if it is not None and it['group'] != 4:
            notes.append(f'Note: {g.item_name(it["no"])} is not a TM item (its item group is '
                         f'{dict(enums.ITEM_GROUPS).get(it["group"], it["group"])}), so the game does not count it as a TM.')
        if bit <= 0:
            notes.append('Bit 0 = no Pokémon can learn it from this TM.')
        else:
            n = self.bit_counts().get(bit - 1, 0)
            notes.append(f'{plural(n, "Pokémon", "Pokémon")} have bit {bit} set in their TM compatibility.')
            twins = [tm_label(g, t) for k, t in enumerate(g.tms) if k != self.key and self.bit_of(t) == bit
                     and t['itemNo'] != v.get('itemNo') and (g.item(t['itemNo']) or {}).get('group') == 4]
            if twins:
                notes.append('The same bit is used by ' + ', '.join(twins[:4]) + ' - those Pokémon learn both.')
        self.live.config(text='\n'.join(notes))
        for w in self.links.winfo_children():
            w.destroy()
        if m:
            Link(self.links, f'Open the move {g.move_name(m["wazaNo"])}', lambda n=m['wazaNo']: self.app.show('moves', n)
                 ).pack(side='left', padx=(0, 18))
        if it is not None:
            Link(self.links, f'Open the item {g.item_name(it["no"])}', lambda n=it['no']: self.app.show('items', n)
                 ).pack(side='left')

    def _who(self, i):
        body = self.who.body
        for w in body.winfo_children():
            w.destroy()
        g = self.s.game
        t = g.tms[i]
        bit = self.bit_of(t) - 1
        if bit < 0:
            label(body, 'None - the TM has no compatibility bit.', style='Muted.TLabel').pack(anchor='w')
            return
        keys = []
        for r in g.species_rows():
            try:
                bits = g.tm_bits(r)
            except Exception:
                continue
            if bit < len(bits) and bits[bit]:
                keys.append(g.key_of(r))
        if not keys:
            label(body, 'No Pokémon has this bit set.', style='Muted.TLabel').pack(anchor='w')
            return
        label(body, plural(len(keys), 'Pokémon', 'Pokémon') + ' - click one to open it', style='Faint.TLabel').pack(
            anchor='w', pady=(0, 4))
        link_grid(body, [(g.pokemon_name(*k), lambda k=k: self.app.show('pokemon', k)) for k in keys], cap=150,
                  more_text='more Pokémon')

    def collect(self, i):
        g = self.s.game
        t = g.tms[i]
        v = self.form.values()
        ops = []
        for f in ('itemNo', 'wazaNo'):
            if f in v and t[f] != v[f]:
                ops.append(set_op(g, PERSONAL, 'ItemTable', 'WazaMachine', t, f, v[f], key=t['machineNo']))
        it = g.item(t['itemNo'])
        if it is not None and 'group_id' in v and it['group_id'] != v['group_id']:
            ops.append(set_op(g, PERSONAL, 'ItemTable', 'Item', it, 'group_id', v['group_id']))
        return ops

    def refresh(self):
        self._bits_tok = None
        super().refresh()

