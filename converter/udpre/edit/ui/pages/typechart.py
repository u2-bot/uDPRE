"""Type chart: the 18 x 18 matchup grid of the player's global-metadata.dat as a heat grid (rows = the attacking type,
columns = the defending type), with a readout of the cell under the pointer and a panel of what the chosen type hits
hard / poorly when it attacks and what hurts / fails to hurt it when it defends. Kept as one {"op": "typechart"}
operation (metadata.py).

Also home of UnsavedStrip, the "Unsaved changes - Keep / Revert" cue the non-record pages of this group share."""
import copy
import tkinter as tk

from ...metadata import type_chart
from ..kit import Button, Link, Section, frame, label, pill
from ..page import Page
from ..theme import C, FONT, text_on, type_color

N = 18
CYCLE = [0, 2, 4, 8]
WORD = {0: 'no effect (0×)', 2: 'not very effective (½×)', 4: 'normal damage (1×)', 8: 'super effective (2×)'}
MULT = {0: '0×', 2: '½×', 4: '1×', 8: '2×'}
# heat colors: background, text, mark
HEAT = {0: ('#38404d', '#ffffff', '0'), 2: ('#f6c4bf', '#7a1d1d', '½'), 4: ('#f5f7fa', '#b4bccb', '·'),
        8: ('#8fd17f', '#0f3d16', '2')}
CELL = 30
ROW_HEAD = 92
COL_HEAD = 34


class UnsavedStrip(tk.Frame):
    """the orange "● Unsaved changes" strip of a page: Keep (Ctrl+S) and Revert; show(on) packs / hides it"""

    def __init__(self, master, keep, revert, hint='kept when you leave this page', before=None):
        super().__init__(master, bg=C['edited_soft'])
        self.before = before
        tk.Label(self, text='●  Unsaved changes', bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9, 'bold')).pack(
            side='left', padx=(12, 0), pady=5)
        self.hint = tk.Label(self, text=hint, bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9))
        self.hint.pack(side='left', padx=(8, 0))
        Link(self, 'Revert', revert, bg=C['edited_soft']).pack(side='right', padx=(8, 12))
        Button(self, 'Keep  (Ctrl+S)', keep, kind='primary', small=True).pack(side='right', pady=4)
        self.pack_kw = {}

    def place_like(self, **pack_kw):
        self.pack_kw = pack_kw
        return self

    def show(self, on):
        try:
            if on and not self.winfo_ismapped():
                kw = dict(self.pack_kw)
                if self.before is not None:
                    kw['before'] = self.before
                self.pack(**kw)
            elif not on and self.winfo_ismapped():
                self.pack_forget()
        except tk.TclError:
            pass


def message_box(master, title, text, hint=None):
    """a friendly full-page notice (no data to show)"""
    f = frame(master)
    f.pack(fill='both', expand=True, padx=40, pady=60)
    label(f, title, style='Section.TLabel').pack(anchor='w')
    label(f, text, style='Muted.TLabel', wraplength=720, justify='left').pack(anchor='w', pady=(6, 0))
    if hint:
        label(f, hint, style='Faint.TLabel', wraplength=720, justify='left').pack(anchor='w', pady=(10, 0))
    return f


def pill_rows(master, items, per_row=6, empty='none'):
    """type pills [(text, color)] wrapped in rows (a gray 'none' when empty)"""
    for w in master.winfo_children():
        w.destroy()
    if not items:
        label(master, empty, style='Faint.TLabel').grid(row=0, column=0, sticky='w')
        return
    for k, (text, col) in enumerate(items):
        pill(master, text, col).grid(row=k // per_row, column=k % per_row, sticky='w', padx=(0, 4), pady=(0, 3))


class TypeChartPage(Page):
    title = 'Type chart'
    subtitle = 'How much damage each type does to each other type - click a cell to change it'

    def build_page(self):
        self.values = None
        self.orig = None
        self.sel = 0
        self.hover = None               # (a, d) under the pointer
        self.note_box = None
        self.top = frame(self)
        self.top.pack(fill='both', expand=True)
        self.load()
        self._poll()

    # --- data -----------------------------------------------------------------------------------------------------
    def load(self):
        for w in self.top.winfo_children():
            w.destroy()
        self.values = None
        m = self.s.context.metadata()
        if m is None:
            message_box(self.top, 'The type chart cannot be shown',
                        'The type chart lives in the game player\'s code data (global-metadata.dat), and uDPRE cannot '
                        'read the one of the player you use.',
                        'Convert your dump once with uDPRE (or press Apply in the uDPRE window) so the player files are in '
                        'place, then open the Editor & Randomizer again.')
            return
        try:
            vals = type_chart(m)
        except ValueError as e:
            message_box(self.top, 'The type chart cannot be found',
                        f'The player you use does not hold the type chart where uDPRE looks for it ({e}).',
                        'This happens with a player uDPRE does not know. Your other edits are not affected.')
            return
        self.values = [list(r) for r in vals]
        self.orig = copy.deepcopy(self.values)
        self.build_chart()

    def build_chart(self):
        g = self.s.game
        self.names = [g.type_name(t) for t in range(N)]
        body = frame(self.top)
        body.pack(fill='both', expand=True, padx=24, pady=(10, 10))
        left = frame(body)
        left.pack(side='left', fill='y')
        self.strip = UnsavedStrip(left, self.keep, self.revert).place_like(fill='x', pady=(0, 8))
        self.readout = tk.Label(left, text='', bg=C['bg'], fg=C['text'], font=(FONT, 11), anchor='w')
        self.readout.pack(fill='x')
        self.strip.before = self.readout
        label(left, 'Rows attack, columns defend.  Click a cell = next value, right click = previous.  '
                    'Click a type name to see its matchups.', style='Faint.TLabel').pack(anchor='w', pady=(0, 6))
        w = ROW_HEAD + N * CELL + 2
        h = COL_HEAD + N * CELL + 2
        self.cv = tk.Canvas(left, width=w, height=h, bg=C['bg'], highlightthickness=0)
        self.cv.pack(anchor='w')
        self.cv.bind('<Motion>', self._motion)
        self.cv.bind('<Leave>', lambda _e: self._set_hover(None))
        self.cv.bind('<Button-1>', lambda e: self._click(e, 1))
        self.cv.bind('<Button-3>', lambda e: self._click(e, -1))
        leg = frame(left)
        leg.pack(anchor='w', pady=(8, 0))
        for v in (8, 4, 2, 0):
            bg, fg, mark = HEAT[v]
            tk.Label(leg, text=mark, bg=bg, fg=fg, width=3, font=(FONT, 9, 'bold')).pack(side='left')
            label(leg, MULT[v] + ' ' + WORD[v].split(' (')[0], style='Muted.TLabel').pack(side='left', padx=(4, 14))
        self.changes = label(left, '', style='Faint.TLabel')
        self.changes.pack(anchor='w', pady=(6, 0))
        tk.Frame(body, width=1, bg=C['line']).pack(side='left', fill='y', padx=24)
        right = frame(body)
        right.pack(side='left', fill='both', expand=True)
        self.side_head = frame(right)
        self.side_head.pack(fill='x')
        att = Section(right, 'When it attacks')
        att.pack(fill='x', pady=(14, 0))
        self.att = {}
        for v, text in ((8, 'Super effective (2×) on'), (2, 'Not very effective (½×) on'), (0, 'No effect on')):
            label(att.body, text, style='Muted.TLabel').pack(anchor='w', pady=(2, 2))
            self.att[v] = frame(att.body)
            self.att[v].pack(anchor='w', pady=(0, 6))
        de = Section(right, 'When it defends')
        de.pack(fill='x', pady=(10, 0))
        self.de = {}
        for v, text in ((8, 'Weak to (takes 2×)'), (2, 'Resists (takes ½×)'), (0, 'Immune to (takes 0×)')):
            label(de.body, text, style='Muted.TLabel').pack(anchor='w', pady=(2, 2))
            self.de[v] = frame(de.body)
            self.de[v].pack(anchor='w', pady=(0, 6))
        self.draw()
        self.side()
        self._set_hover(None)

    # --- drawing --------------------------------------------------------------------------------------------------
    def _xy(self, a, d):
        x = ROW_HEAD + d * CELL
        y = COL_HEAD + a * CELL
        return x, y

    def draw(self):
        cv = self.cv
        cv.delete('all')
        for t in range(N):
            col = type_color(t)
            on = t == self.sel
            x, _ = self._xy(0, t)
            cv.create_rectangle(x + 1, 4, x + CELL - 1, COL_HEAD - 4, fill=col, outline=C['text'] if on else col,
                                width=2 if on else 1, tags=('hd', f'col{t}'))
            cv.create_text(x + CELL / 2, COL_HEAD / 2, text=self.names[t][:3].upper(), fill=text_on(col),
                           font=(FONT, 7, 'bold'), tags=('hd', f'col{t}'))
            _, y = self._xy(t, 0)
            cv.create_rectangle(2, y + 1, ROW_HEAD - 6, y + CELL - 1, fill=col, outline=C['text'] if on else col,
                                width=2 if on else 1, tags=('hd', f'row{t}'))
            cv.create_text(ROW_HEAD - 12, y + CELL / 2, text=self.names[t], anchor='e', fill=text_on(col),
                           font=(FONT, 8, 'bold'), tags=('hd', f'row{t}'))
        for a in range(N):
            for d in range(N):
                self.paint(a, d)
        s = self.sel        # the chosen type's row (attacking) and column (defending), framed
        x0, y0 = self._xy(s, 0)
        cv.create_rectangle(x0 - 1, y0, x0 + N * CELL + 1, y0 + CELL, outline=C['text'], width=1, tags='band')
        x0, y0 = self._xy(0, s)
        cv.create_rectangle(x0, y0 - 1, x0 + CELL, y0 + N * CELL + 1, outline=C['text'], width=1, tags='band')
        self.cv.create_rectangle(0, 0, 0, 0, outline=C['accent'], width=2, tags='hov')

    def paint(self, a, d):
        cv = self.cv
        cv.delete(f'c{a}_{d}')
        v = self.values[a][d]
        bg, fg, mark = HEAT.get(v, ('#f2d64b', '#3d3200', str(v)))
        x, y = self._xy(a, d)
        changed = v != self.orig[a][d]
        cv.create_rectangle(x + 1, y + 1, x + CELL - 1, y + CELL - 1, fill=bg,
                            outline=C['edited'] if changed else C['bg'], width=2 if changed else 1,
                            tags=('cell', f'c{a}_{d}'))
        cv.create_text(x + CELL / 2, y + CELL / 2, text=mark, fill=fg, font=(FONT, 10 if v != 4 else 9, 'bold'),
                       tags=('cell', f'c{a}_{d}'))
        cv.tag_raise('band')
        cv.tag_raise('hov')

    def _at(self, e):
        """-> ('cell', a, d) / ('row', t) / ('col', t) / None for a canvas point"""
        if e.x >= ROW_HEAD and e.y >= COL_HEAD:
            d = (e.x - ROW_HEAD) // CELL
            a = (e.y - COL_HEAD) // CELL
            if 0 <= a < N and 0 <= d < N:
                return ('cell', a, d)
        elif e.y < COL_HEAD and e.x >= ROW_HEAD:
            d = (e.x - ROW_HEAD) // CELL
            if 0 <= d < N:
                return ('col', d)
        elif e.x < ROW_HEAD and e.y >= COL_HEAD:
            a = (e.y - COL_HEAD) // CELL
            if 0 <= a < N:
                return ('row', a)
        return None

    def _motion(self, e):
        hit = self._at(e)
        self._set_hover(hit)

    def _set_hover(self, hit):
        if self.values is None:
            return
        self.hover = hit
        if hit and hit[0] == 'cell':
            _, a, d = hit
            x, y = self._xy(a, d)
            self.cv.coords('hov', x, y, x + CELL, y + CELL)
            v = self.values[a][d]
            self.readout.config(text=f'{self.names[a]} attacking {self.names[d]}:  {MULT.get(v, v)}  -  '
                                     f'{WORD.get(v, "an unusual value")}' +
                                     ('   (changed, not kept yet)' if v != self.orig[a][d] else ''))
            self.cv.config(cursor='hand2')
        else:
            self.cv.coords('hov', 0, 0, 0, 0)
            if hit:
                self.readout.config(text=f'{self.names[hit[1]]}: click to see its matchups')
                self.cv.config(cursor='hand2')
            else:
                self.readout.config(text='Point at a cell to read it.')
                self.cv.config(cursor='')

    def _click(self, e, k):
        hit = self._at(e)
        if not hit:
            return
        if hit[0] == 'cell':
            _, a, d = hit
            v = self.values[a][d]
            if v not in CYCLE:
                self.say('That cell holds an unusual value; it is left as it is.')
                return
            self.values[a][d] = CYCLE[(CYCLE.index(v) + k) % 4]
            self.paint(a, d)
            self._set_hover(hit)
            if self.sel in (a, d):
                self.side()
        else:
            self.sel = hit[1]
            self.draw()
            self.side()
            self._set_hover(hit)

    def side(self):
        t = self.sel
        for w in self.side_head.winfo_children():
            w.destroy()
        top = frame(self.side_head)
        top.pack(fill='x')
        tk.Label(top, text=self.names[t], bg=C['bg'], fg=C['text'], font=(FONT, 16, 'bold')).pack(side='left')
        pill(top, 'type', type_color(t)).pack(side='left', padx=(10, 0))
        n_att = sum(1 for d in range(N) if self.values[t][d] == 8)
        n_weak = sum(1 for a in range(N) if self.values[a][t] == 8)
        label(self.side_head, f'Hits {n_att} type{"s" if n_att != 1 else ""} super effectively · weak to '
                              f'{n_weak} type{"s" if n_weak != 1 else ""}', style='Muted.TLabel').pack(anchor='w')
        for v in (8, 2, 0):
            pill_rows(self.att[v], [(self.names[d], type_color(d)) for d in range(N) if self.values[t][d] == v])
            pill_rows(self.de[v], [(self.names[a], type_color(a)) for a in range(N) if self.values[a][t] == v])

    # --- unsaved / keep -------------------------------------------------------------------------------------------
    def dirty(self):
        return self.values is not None and self.values != self.orig

    def _poll(self):
        try:
            if self.values is not None and self.cv.winfo_exists():
                d = self.dirty()
                self.strip.show(d)
                n = sum(1 for a in range(N) for b in range(N) if self.values[a][b] != self.orig[a][b])
                self.changes.config(text=f'{n} cell{"s" if n != 1 else ""} changed (outlined in orange)' if n else '')
        except tk.TclError:
            return
        self.after(400, self._poll)

    def keep(self):
        if not self.dirty():
            return True
        vals = copy.deepcopy(self.values)
        n_ops = len(self.s.project.ops)
        w = self.s.run({'op': 'typechart', 'values': vals})
        if w:
            if len(self.s.project.ops) > n_ops:
                self.s.remove([len(self.s.project.ops) - 1])    # nothing that failed stays in your edits
            self.readout.config(text=f'Not kept: {w}')
            return False
        self.orig = copy.deepcopy(vals)
        self.app.edits_changed('Type chart kept in your edits (the player\'s code data is edited at the next Apply).')
        return True

    def revert(self):
        if self.values is None:
            return
        self.values = copy.deepcopy(self.orig)
        self.draw()
        self.side()

    def leave(self):
        return self.keep() if self.built else True

    def refresh(self):
        if self.built:
            sel = self.sel
            self.load()
            self.sel = sel
            if self.values is not None:
                self.draw()
                self.side()

    def goto(self, key):
        self.ensure()
        if isinstance(key, int) and 0 <= key < N and self.values is not None:
            self.sel = key
            self.draw()
            self.side()
