"""Advanced pages: Add a Pokémon (the Pokémon Inserter as a guided form), Game code values (every field default value of
the player's global-metadata.dat in one searchable table, with a value editor), Mod data files (the ExtraData JSON files a
mod brings, with a live JSON check) and Import & export (Pokémon / Trainers / Text JSON files, and a console mod)."""
import json
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import jsonconv
from ... import metadata as md
from ..kit import Button, DataTable, Link, SearchBox, Section, Segmented, frame, label, type_pill
from ..page import Page
from ..theme import C, FONT, MONO
from ..widgets import Picker
from .typechart import UnsavedStrip, message_box


# --- .NET decimal (16-byte values) ------------------------------------------------------------------------------------
def dotnet_decimal(b):
    """16 bytes in .NET's System.Decimal layout (int32 flags: scale in bits 16-23, sign in bit 31; then hi, lo, mid
    uint32 of the 96-bit integer) -> decimal.Decimal"""
    import decimal
    flags, hi, lo, mid = struct.unpack('<iIII', b)
    scale = (flags >> 16) & 0xFF
    v = decimal.Decimal((hi << 64) | (mid << 32) | lo).scaleb(-scale, decimal.Context(prec=60))
    return -v if flags < 0 else v


def dotnet_decimal_bytes(text):
    """the inverse of dotnet_decimal (ValueError when the text is no number or does not fit 96 bits / scale 28)"""
    import decimal
    try:
        d = decimal.Decimal(text.strip())
    except decimal.InvalidOperation:
        raise ValueError(f'{text!r} is not a number')
    sign, digits, exp = d.as_tuple()
    if not isinstance(exp, int):
        raise ValueError('not a finite number')
    n = int(''.join(map(str, digits)) or '0')
    scale = -exp if exp < 0 else 0
    if exp > 0:
        n *= 10 ** exp
    if scale > 28 or n >= 1 << 96:
        raise ValueError('out of the range of a .NET decimal')
    flags = (scale << 16) | (0x80000000 if sign else 0)
    return struct.pack('<IIII', flags, n >> 64, n & 0xFFFFFFFF, (n >> 32) & 0xFFFFFFFF)


INT_FMT = {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}


def views_of(b):
    """the five readings of a default value's bytes: hex / uint / int / float / text ('n/a' where none fits)"""
    n = len(b)
    fmt = INT_FMT.get(n)
    out = {'hex': ' '.join(f'{x:02X}' for x in b),
           'uint': str(struct.unpack('<' + fmt, b)[0]) if fmt else 'n/a',
           'int': str(struct.unpack('<' + fmt.lower(), b)[0]) if fmt else 'n/a',
           'float': (repr(struct.unpack('<f', b)[0]) if n == 4 else repr(struct.unpack('<d', b)[0]) if n == 8
                     else str(dotnet_decimal(b)) if n == 16 else 'n/a')}
    if n == 2:
        out['text'] = b.decode('utf-16-le', 'replace')
    elif n > 4:
        out['text'] = b[4:].decode('utf-8', 'replace')
    else:
        out['text'] = 'n/a'
    return out


def parse_view(k, t, n):
    """the text of view k -> n bytes (ValueError / KeyError / struct.error when it does not fit)"""
    if k == 'hex':
        parts = t.split()
        return bytes(int(p, 16) & 0xFF for p in parts[:n]) + bytes(n - min(n, len(parts)))
    if k in ('uint', 'int'):
        fmt = INT_FMT[n]
        return struct.pack('<' + (fmt if k == 'uint' else fmt.lower()), int(t))
    if k == 'float':
        if n == 16:
            return dotnet_decimal_bytes(t)
        if n in (4, 8):
            return struct.pack('<f', float(t)) if n == 4 else struct.pack('<d', float(t))
        raise ValueError('no number view for this size')
    if n == 2:
        return (t[:1] or '\0').encode('utf-16-le')[:2]
    body = t.encode('utf-8')[:n - 4]
    return struct.pack('<i', len(body)) + body + bytes(n - 4 - len(body))


def preview(b):
    n = len(b)
    if n in (1, 2, 8):
        return str(struct.unpack('<' + INT_FMT[n], b)[0])
    if n == 4:
        return str(struct.unpack('<i', b)[0])
    h = ' '.join(f'{x:02X}' for x in b[:8])
    return h + (' …' if n > 8 else '')


def card(master, title, text=None, width=None):
    """a white card with a thin border, a bold title and a muted explanation; -> (outer, body)"""
    outer = tk.Frame(master, bg=C['bg'], highlightthickness=1, highlightbackground=C['line2'], highlightcolor=C['line2'])
    inner = frame(outer)
    inner.pack(fill='both', expand=True, padx=16, pady=14)
    tk.Label(inner, text=title, bg=C['bg'], fg=C['text'], font=(FONT, 11, 'bold'), anchor='w').pack(fill='x')
    if text:
        label(inner, text, style='Muted.TLabel', wraplength=width or 300, justify='left').pack(anchor='w', pady=(4, 0))
    body = frame(inner)
    body.pack(fill='both', expand=True, pady=(10, 0))
    return outer, body


def drop_failed(session, n_before):
    """session.run keeps the operation even when it was refused: take it out again (nothing failed stays in your edits)"""
    if len(session.project.ops) > n_before:
        session.remove([len(session.project.ops) - 1])


# ======================================================================================================================
class InserterPage(Page):
    title = 'Add a Pokémon'
    subtitle = 'Make a new Pokémon from a copy of an existing one - as a new form of a species, or as a new species'

    def build_page(self):
        c = self.c
        body = frame(self)
        body.pack(fill='both', expand=True, padx=24, pady=(12, 10))
        left = frame(body, width=620)
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        tk.Frame(body, width=1, bg=C['line']).pack(side='left', fill='y', padx=24)
        right = frame(body)
        right.pack(side='left', fill='both', expand=True)

        s1 = Section(left, '1   What to copy', hint='its stats, moves, texts, models, icons and cries')
        s1.pack(fill='x')
        row = frame(s1.body)
        row.pack(fill='x')
        label(row, 'Copy of', style='Muted.TLabel', width=16).pack(side='left')
        self.src = Picker(row, [kv for kv in c.species() if kv[0] != (0, 0)], width=38)
        self.src.pack(side='left')
        self.src_info = frame(s1.body)
        self.src_info.pack(fill='x', pady=(6, 0))

        s2 = Section(left, '2   What it becomes')
        s2.pack(fill='x', pady=(16, 0))
        self.mode = Segmented(s2.body, [('form', 'A new form of a species'), ('species', 'A new species')],
                              command=lambda _v: self._mode_changed(), value='form')
        self.mode.pack(anchor='w')
        self.views = self.mode          # (the screenshot tool's PAGE@VIEW: inserter@species)
        self.form_row = frame(s2.body)
        label(self.form_row, 'Form of', style='Muted.TLabel', width=16).pack(side='left')
        self.dst = Picker(self.form_row, [kv for kv in c.species0() if kv[0] != 0], width=38)
        self.dst.pack(side='left')
        self.species_row = frame(s2.body)
        self.support = tk.Label(self.species_row, text='', bg=C['bg'], font=(FONT, 9), anchor='w', justify='left',
                                wraplength=560)
        self.support.pack(anchor='w')
        self.form_row.pack(fill='x', pady=(8, 0))

        s3 = Section(left, '3   Names')
        s3.pack(fill='x', pady=(16, 0))
        g3 = frame(s3.body)
        g3.pack(anchor='w')
        label(g3, 'Species name', style='Muted.TLabel', width=16).grid(row=0, column=0, sticky='w', pady=2)
        self.sname = ttk.Entry(g3, width=30, style='Studio.TEntry')
        self.sname.grid(row=0, column=1, sticky='w', pady=2)
        self.sname_hint = label(g3, '', style='Faint.TLabel')
        self.sname_hint.grid(row=0, column=2, sticky='w', padx=(8, 0))
        label(g3, 'Form name', style='Muted.TLabel', width=16).grid(row=1, column=0, sticky='w', pady=2)
        self.fname = ttk.Entry(g3, width=30, style='Studio.TEntry')
        self.fname.insert(0, 'New Form')
        self.fname.grid(row=1, column=1, sticky='w', pady=2)
        label(g3, 'shown in the Pokédex', style='Faint.TLabel').grid(row=1, column=2, sticky='w', padx=(8, 0))

        s4 = Section(left, '4   Models and icons', hint='only matters when a mod already has some for the new number')
        s4.pack(fill='x', pady=(16, 0))
        self.models = tk.StringVar(value='auto')
        ttk.Radiobutton(s4.body, text='Use the mod\'s own models / icons (custom ones made for that number)',
                        value='auto', variable=self.models, style='Studio.TRadiobutton').pack(anchor='w')
        ttk.Radiobutton(s4.body, text='Copy the source\'s models / icons over them', value='clone',
                        variable=self.models, style='Studio.TRadiobutton').pack(anchor='w')
        label(s4.body, 'Luminescent\'s icon atlas, for example, already holds icons for Pokémon it does not use yet.',
              style='Faint.TLabel').pack(anchor='w', pady=(4, 0))

        # summary
        label(right, 'What will happen', style='Section.TLabel').pack(anchor='w')
        tk.Frame(right, height=1, bg=C['line']).pack(fill='x', pady=(3, 8))
        self.result_big = tk.Label(right, text='', bg=C['bg'], fg=C['text'], font=(FONT, 15, 'bold'), anchor='w',
                                   justify='left', wraplength=380)
        self.result_big.pack(fill='x')
        self.result_sub = label(right, '', style='Muted.TLabel', wraplength=390, justify='left')
        self.result_sub.pack(anchor='w', pady=(2, 10))
        for text in ('Every table row the game looks up for a Pokémon is copied: stats, typing, abilities, level-up and '
                     'egg moves, TMs, evolutions, Pokédex texts.',
                     'Its models and icons are copied under new names (a model mod can replace them), the menu icon onto '
                     'its own texture, and its cries onto new sound ids.',
                     'A new form goes after the species\' last form; a new species gets the next number after the last '
                     'species. Rows after it move down and every link to them is fixed.',
                     'It is added to your edits: press Apply / Convert in the uDPRE window to put it into the game.'):
            r = frame(right)
            r.pack(fill='x', pady=2)
            label(r, '•', style='Muted.TLabel').pack(side='left', anchor='n')
            label(r, text, style='Studio.TLabel', wraplength=370, justify='left').pack(side='left', padx=(6, 0))
        self.go = Button(right, 'Add the Pokémon', self.insert, kind='primary')
        self.go.pack(anchor='w', pady=(16, 0))
        self.error = tk.Label(right, text='', bg=C['bg'], fg=C['danger'], font=(FONT, 9), anchor='w', justify='left',
                              wraplength=390)
        self.error.pack(fill='x', pady=(8, 0))
        self.done = frame(right)
        self.done.pack(fill='x', pady=(4, 0))

        for w in (self.src, self.dst):
            w.bind('<<ComboboxSelected>>', lambda _e: self.update_summary(), add='+')
            w.bind('<FocusOut>', lambda _e: self.update_summary(), add='+')
            w.bind('<Return>', lambda _e: self.update_summary(), add='+')
        for w in (self.sname, self.fname):
            w.bind('<KeyRelease>', lambda _e: self.update_summary(), add='+')
        self.src.set_value((25, 0))
        self.dst.set_value(25)
        self._mode_changed()

    def _mode_changed(self):
        sp = self.mode.get() == 'species'
        t = self.fname.get().strip()
        if sp and t == 'New Form':
            self.fname.delete(0, 'end')
        elif not sp and not t:
            self.fname.insert(0, 'New Form')
        if sp:
            self.form_row.pack_forget()
            self.species_row.pack(fill='x', pady=(8, 0))
            self.sname.state(['!disabled'])
            self.sname_hint.config(text='the new species\' name')
            from ... import inserter
            ok = inserter.player_supports_new_species(self.s.context)
            if ok:
                self.support.config(fg=C['ok'], text='✓  Your game player takes species numbers past the game\'s own '
                                                     'limit.')
            elif ok is False:
                self.support.config(fg=C['danger'], text='✕  Your game player keeps the game\'s own species limit. A '
                                    'new species needs uDPRE 0.4.0\'s player, or the Luminescent / Dechibified packs from '
                                    '1.2.5: update first.')
            else:
                self.support.config(fg=C['muted'], text='uDPRE cannot read your player\'s code data, so it cannot check '
                                    'whether it takes new species numbers.')
        else:
            self.species_row.pack_forget()
            self.form_row.pack(fill='x', pady=(8, 0))
            self.sname.state(['disabled'])
            self.sname_hint.config(text='a form keeps its species\' name')
        self.update_summary()

    def target(self):
        """-> (monsno, form) the new Pokémon will get, or None (the inserter's own positions)"""
        g = self.s.game
        if self.mode.get() == 'species':
            return g.species_count() + 1, 0
        dm = self.dst.get_value()
        base = g.row(dm) if dm else None
        if base is None:
            return None
        return dm, max(1, base['form_max'])

    def update_summary(self):
        g = self.s.game
        for w in self.src_info.winfo_children():
            w.destroy()
        src = self.src.get_value()
        r = g.row(*src) if src and src != (0, 0) else None
        if r is not None:
            type_pill(self.src_info, g, r['type1']).pack(side='left')
            if r['type2'] != r['type1']:
                type_pill(self.src_info, g, r['type2']).pack(side='left', padx=(4, 0))
            label(self.src_info, f'   BST {g.bst(r)}', style='Muted.TLabel').pack(side='left')
            from ... import inserter
            try:
                gc = inserter.gender_config(g, *src)
            except Exception as e:
                gc = f'({e})'
            label(self.src_info, f'   ·   genders: {gc}', style='Muted.TLabel').pack(side='left')
            Link(self.src_info, 'open', lambda k=tuple(src): self.app.show('pokemon', k)).pack(side='left', padx=(10, 0))
        else:
            label(self.src_info, 'Pick the Pokémon to copy.', style='Faint.TLabel').pack(side='left')
        t = self.target()
        src_name = g.pokemon_name(*src) if r is not None else 'the Pokémon'
        if self.mode.get() == 'species':
            nm = self.sname.get().strip() or 'the new species'
            last = g.species_count()
            self.result_big.config(text=f'{nm}  ·  No. {t[0]:03d}')
            self.result_sub.config(text=f'A copy of {src_name}, numbered after the last species '
                                        f'({g.species_name(last)}, No. {last:03d}).')
        elif t is None:
            self.result_big.config(text='Pick the species')
            self.result_sub.config(text='Choose which species gets the new form.')
        else:
            fn = self.fname.get().strip() or 'a new form'
            self.result_big.config(text=f'{g.species_name(t[0])} ({fn})  ·  No. {t[0]:03d} form {t[1]}')
            self.result_sub.config(text=f'A copy of {src_name} as form {t[1]} of {g.species_name(t[0])}, after its last '
                                        f'form.')

    def insert(self):
        self.error.config(text='')
        src = self.src.get_value()
        if not src or src == (0, 0):
            self.error.config(text='Pick the Pokémon to copy (step 1).')
            return
        mode = self.mode.get()
        op = {'op': 'insert', 'mode': mode, 'src': list(src), 'name': self.sname.get().strip() if mode == 'species'
              else '', 'form_name': self.fname.get().strip(), 'models': self.models.get()}
        if mode == 'species':
            from ... import inserter
            ok = inserter.player_supports_new_species(self.s.context)
            msg = ('A new species needs a player that takes species numbers past the game\'s own limit (uDPRE 0.4.0\'s '
                   'player; the Luminescent / Dechibified packs from 1.2.5). ')
            if ok is False:
                self.error.config(text=msg + 'The player you use keeps the game\'s limit: update it first.')
                return
            if not messagebox.askokcancel(self.title, msg + 'A console mod made from these edits would also need the '
                                          'console game\'s code changed. Add the new species?', parent=self):
                return
        else:
            dst = self.dst.get_value()
            if not dst:
                self.error.config(text='Pick the species that gets the new form (step 2).')
                return
            op['dst'] = dst
        t = self.target()
        n = len(self.s.project.ops)
        w = self.s.run(op)
        if w:
            drop_failed(self.s, n)
            self.app.edits_changed('The Pokémon was not added.')
            self.error.config(text=f'Not added: {w}')
            return
        g = self.s.game
        name = g.pokemon_name(*t) if t and g.row(*t) is not None else 'The new Pokémon'
        self.app.edits_changed(f'Added {name} to your edits.')
        for w_ in self.done.winfo_children():
            w_.destroy()
        box = tk.Frame(self.done, bg=C['ok_soft'])
        box.pack(fill='x')
        tk.Label(box, text=f'✓  Added {name}' + (f'  (No. {t[0]:03d} form {t[1]})' if t else ''), bg=C['ok_soft'],
                 fg=C['ok'], font=(FONT, 9, 'bold')).pack(anchor='w', padx=12, pady=(8, 2))
        tk.Label(box, text='It is in your edits; press Apply / Convert in the uDPRE window to put it into the game.',
                 bg=C['ok_soft'], fg=C['text'], font=(FONT, 9), wraplength=360, justify='left').pack(anchor='w', padx=12)
        if t:
            Link(box, 'Open it on the Pokémon page', lambda k=tuple(t): self.app.show('pokemon', k),
                 bg=C['ok_soft']).pack(anchor='w', padx=12, pady=(2, 8))

    def refresh(self):
        if not self.built:
            return
        c = self.c
        for w in self.done.winfo_children():        # an "Added" note of before an undo would be stale
            w.destroy()
        cur_s, cur_d = self.src.get_value(), self.dst.get_value()
        self.src.set_choices([kv for kv in c.species() if kv[0] != (0, 0)])
        self.dst.set_choices([kv for kv in c.species0() if kv[0] != 0])
        if cur_s:
            self.src.set_value(cur_s)
        if cur_d:
            self.dst.set_value(cur_d)
        self.update_summary()


# ======================================================================================================================
LIMIT = 600     # rows shown at once (the player has ~65,000 field values)


class MetadataPage(Page):
    title = 'Game code values'
    subtitle = 'Default values of the game code\'s fields and constants (the player\'s global-metadata.dat)'
    columns = [('image', 'Image', 120, 'w'), ('type', 'Type', 200, 'w'), ('field', 'Field', 180, 'w'),
               ('size', 'Bytes', 50, 'e'), ('value', 'Value', 110, 'w')]

    def build_page(self):
        self.top = frame(self)
        self.top.pack(fill='both', expand=True)
        self.key = None
        self.cur = None
        self.base = None
        self._after = None
        self.build_all()
        self._poll()

    def build_all(self):
        for w in self.top.winfo_children():
            w.destroy()
        self.key = None
        self.meta = self.s.context.metadata()
        if self.meta is None:
            message_box(self.top, 'The game code values cannot be shown',
                        'They live in the game player\'s code data (global-metadata.dat), and uDPRE cannot read the one '
                        'of the player you use.',
                        'Convert your dump once with uDPRE (or press Apply in the uDPRE window) so the player files are in '
                        'place, then open the Editor & Randomizer again.')
            return
        self.load_fields()
        bar = frame(self.top)
        bar.pack(fill='x', padx=24, pady=(10, 0))
        self.search = SearchBox(bar, 'Find a value by type or field name...', on_change=lambda _t: self._later(),
                                width=44)
        self.search.pack(side='left')
        imgs = ['All images'] + sorted({k[0] for k, *_ in self.all}, key=str.lower)
        self.img = ttk.Combobox(bar, values=imgs, state='readonly', width=26, style='Studio.TCombobox')
        self.img.current(imgs.index('Assembly-CSharp.dll') if 'Assembly-CSharp.dll' in imgs else 0)
        self.img.pack(side='left', padx=(10, 0))
        self.img.bind('<<ComboboxSelected>>', lambda _e: self.render())
        self.named = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Hide compiler data blocks', variable=self.named, style='Studio.TCheckbutton',
                        command=self.render).pack(side='left', padx=(12, 0))
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(bar, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self.render).pack(side='left', padx=(12, 0))
        main = frame(self.top)
        main.pack(fill='both', expand=True, padx=(24, 0), pady=(8, 10))
        left = frame(main, width=690)
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        self.table = DataTable(left, self.columns, on_select=self._pick)
        self.table.pack(fill='both', expand=True)
        self.count = label(left, '', style='Faint.TLabel')
        self.count.pack(anchor='w', pady=(4, 0))
        tk.Frame(main, width=1, bg=C['line']).pack(side='left', fill='y', padx=(16, 0))
        right = frame(main)
        right.pack(side='left', fill='both', expand=True, padx=(18, 20))
        top = frame(right)
        top.pack(fill='x')
        self.h_title = ttk.Label(top, text='', style='Record.TLabel', wraplength=330)
        self.h_title.pack(anchor='w')
        self.h_sub = label(right, '', style='Muted.TLabel', wraplength=330, justify='left')
        self.h_sub.pack(anchor='w')
        self.h_undo = Link(right, '', self.undo_field)
        self.h_undo.pack(anchor='w', pady=(2, 0))
        self.strip = UnsavedStrip(right, self.keep, self.revert, hint='kept when you leave this value')
        self.strip.place_like(fill='x', pady=(8, 0))
        sec = Section(right, 'Value', hint='edit any view, then Enter')
        sec.pack(fill='x', pady=(12, 0))
        self.strip.before = sec
        self.vars = {}
        for r, (k, lab) in enumerate((('hex', 'Bytes (hex)'), ('uint', 'Whole number'), ('int', 'Signed number'),
                                      ('float', 'Decimal number'), ('text', 'Text'))):
            label(sec.body, lab, style='Muted.TLabel').grid(row=r, column=0, sticky='w', pady=3, padx=(0, 10))
            v = tk.StringVar()
            e = ttk.Entry(sec.body, textvariable=v, width=34, style='Studio.TEntry',
                          **({'font': (MONO, 9)} if k == 'hex' else {}))
            e.grid(row=r, column=1, sticky='we', pady=3)
            e.bind('<Return>', lambda _e, k=k: self.edit(k))
            e.bind('<FocusOut>', lambda _e, k=k: self.edit(k))
            self.vars[k] = (v, e)
        sec.body.columnconfigure(1, weight=1)
        self.error = tk.Label(right, text='', bg=C['bg'], fg=C['danger'], font=(FONT, 9), anchor='w', wraplength=330,
                              justify='left')
        self.error.pack(fill='x', pady=(6, 0))
        tips = Section(right, 'Good to know')
        tips.pack(fill='x', pady=(10, 0))
        label(tips.body, 'The game reads these values when it runs, so a change works without rebuilding the player. '
                         'A value keeps its size. Edits apply to whichever player your mods choose, and to a console '
                         'export.', style='Faint.TLabel', wraplength=340, justify='left').pack(anchor='w')
        self.render()
        self.table.select_first()

    def load_fields(self):
        self.all = []           # (key, haystack, field)
        for img, types in md.field_list(self.meta):
            for tname, fs in types:
                for f in fs:
                    key = (img, tname, f.name)
                    self.all.append((key, f'{img} {tname}.{f.name}'.lower(), f))
        self.by_key = {k: f for k, _h, f in self.all}

    # --- table ----------------------------------------------------------------------------------------------------
    def _later(self):
        if self._after is not None:
            self.after_cancel(self._after)
        self._after = self.after(180, self.render)

    def edited_keys(self):
        return {k for k in (self.op_key(op) for op in self.s.project.ops) if k is not None}

    def render(self):
        self._after = None
        t = self.search.get_text().lower().strip()
        img = self.img.get()
        img = None if img == 'All images' else img
        hide = self.named.get()
        ed = self.edited_keys()
        only = self.only_edited.get()
        hits = []
        total = 0
        for key, hay, f in self.all:
            if img is not None and key[0] != img:
                continue
            if hide and key[1].startswith('<PrivateImplementationDetails>'):
                continue
            if only and key not in ed:
                continue
            if t and t not in hay:
                continue
            total += 1
            if len(hits) < LIMIT:
                hits.append((key, f))
        rows = []
        for key, f in hits:
            try:
                v = preview(self.meta.read_default(f))
            except Exception:
                v = '?'
            rows.append((key, (key[0].replace('.dll', ''), key[1], key[2], f.default.size, v)))
        cur = self.key
        self.table._cur = cur
        self.table.set_rows(rows, ed)
        self.count.config(text=(f'{total:,} values' if total <= LIMIT else
                                f'Showing the first {LIMIT} of {total:,} values - type to narrow them down') +
                          (f'  ·  {len(ed)} edited' if ed else ''))

    def _pick(self, key):
        if self.key is not None and key != self.key and not self.keep():
            return False
        self.load(key)
        return True

    def load(self, key):
        f = self.by_key.get(key)
        if f is None:
            return
        self.key = key
        self.field = f
        self.cur = bytearray(self.meta.read_default(f))
        self.base = bytes(self.cur)
        self.error.config(text='')
        self.h_title.config(text=key[2])
        self.h_sub.config(text=f'{key[1]}\n{key[0]}  ·  {len(self.cur)} byte{"s" if len(self.cur) != 1 else ""} at '
                               f'{f.default.offset:,}')
        n = sum(1 for op in self.s.project.ops if self.op_key(op) == key)
        self.h_undo.config(text=f'Undo my {n} edit{"s" if n != 1 else ""} to this value' if n else '')
        self.show_value()

    def show_value(self):
        vals = views_of(bytes(self.cur))
        for k, (v, e) in self.vars.items():
            e.state(['!disabled'])
            v.set(vals[k])
            if vals[k] == 'n/a':
                e.state(['disabled'])

    def edit(self, k):
        if self.cur is None:
            return
        n = len(self.cur)
        t = self.vars[k][0].get()
        if t == views_of(bytes(self.cur))[k]:
            return
        try:
            new = parse_view(k, t, n)
        except (ValueError, KeyError, struct.error) as e:
            how = {'hex': 'bytes are two hex digits each, like 0A FF', 'uint': 'a whole number from 0 up',
                   'int': 'a whole number', 'float': 'a number like 1.5', 'text': 'text'}[k]
            self.error.config(text=f'Not a value for these {n} bytes ({how}): {e}')
            self.show_value()
            return
        self.error.config(text='')
        self.cur = bytearray(new)
        self.show_value()

    def op_key(self, op):
        if op.get('op') == 'metadata':
            return (op.get('image'), op.get('type'), op.get('field'))
        return None

    # --- keep -----------------------------------------------------------------------------------------------------
    def pending(self):
        """the view whose text was typed but not applied yet (Enter / leaving the box applies it), or None"""
        if self.cur is None:
            return None
        shown = views_of(bytes(self.cur))
        return next((k for k, (v, _e) in self.vars.items() if v.get() != shown[k]), None)

    def dirty(self):
        if self.key is None or self.cur is None:
            return False
        return bytes(self.cur) != self.base or self.pending() is not None

    def _poll(self):
        try:
            if self.meta is not None and self.winfo_exists():
                self.strip.show(self.dirty())
        except (tk.TclError, AttributeError):
            pass
        try:
            self.after(400, self._poll)
        except tk.TclError:
            pass

    def keep(self):
        k = self.pending() if self.key is not None else None
        if k is not None:
            self.edit(k)
            if self.error.cget('text'):
                return False
        if not self.dirty():
            return True
        key = self.key
        n = len(self.s.project.ops)
        w = self.s.run({'op': 'metadata', 'image': key[0], 'type': key[1], 'field': key[2],
                        'hex': bytes(self.cur).hex()})
        if w:
            drop_failed(self.s, n)
            self.error.config(text=f'Not kept: {w}')
            return False
        self.base = bytes(self.cur)
        self.app.edits_changed(f'Kept the new value of {key[1]}.{key[2]}.')
        return True

    def revert(self):
        if self.key is not None:
            self.load(self.key)

    def undo_field(self):
        idx = [i for i, op in enumerate(self.s.project.ops) if self.op_key(op) == self.key]
        if not idx:
            return
        if not messagebox.askyesno('Undo edits', f'Remove your {len(idx)} edit{"s" if len(idx) != 1 else ""} to '
                                   f'{self.key[1]}.{self.key[2]}?', parent=self):
            return
        self.base = bytes(self.cur)
        self.s.remove(idx)
        self.app.edits_changed(f'Removed {len(idx)} edit{"s" if len(idx) != 1 else ""} to {self.key[2]}.')

    def leave(self):
        return self.keep() if self.built else True

    def refresh(self):
        if not self.built:
            return
        key = self.key
        if self.s.context.metadata() is not self.meta or self.meta is None:
            self.build_all()            # the session was read again: new metadata objects
        else:
            self.render()
        if self.meta is not None and key is not None:
            self.goto(key)

    def goto(self, key):
        self.ensure()
        if self.meta is None or not isinstance(key, (tuple, list)) or tuple(key) not in self.by_key:
            return
        key = tuple(key)
        if key not in self.table._iid:
            self.search.clear()
            self.img.current(0)
            self.named.set(False)
            self.only_edited.set(False)
            self.search._in(None)
            self.search.var.set(f'{key[1]}.{key[2]}'.lower())
            self.render()
        self.key = None
        self.table.select(key, notify=False)
        self.load(key)


# ======================================================================================================================
class ExtraDataPage(Page):
    title = 'Mod data files'
    subtitle = 'The extra JSON data files some overhaul mods bring (romfs/Data/ExtraData) - their game code reads them'
    columns = [('file', 'File', 300, 'w'), ('size', 'Entries', 60, 'e')]

    def build_page(self):
        self.top = frame(self)
        self.top.pack(fill='both', expand=True)
        self.key = None
        self._after = None
        self.build_all()
        self._poll()

    def build_all(self):
        for w in self.top.winfo_children():
            w.destroy()
        self.key = None
        self.files = self.s.game.extradata()
        if not self.files:
            message_box(self.top, 'None of your mods brings data files',
                        'Some overhaul mods keep extra data as JSON files in romfs/Data/ExtraData (starters, honey trees, '
                        'TM learnsets ...), read by their own game code. None of the mods you chose has them, so there is '
                        'nothing to edit here.',
                        f'Your mods: {self.s.mods_text()}.')
            return
        main = frame(self.top)
        main.pack(fill='both', expand=True, padx=(24, 0), pady=(10, 10))
        left = frame(main, width=400)
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        self.search = SearchBox(left, 'Filter files...', on_change=lambda t: self.table.filter(t))
        self.search.pack(fill='x')
        self.table = DataTable(left, self.columns, on_select=self._pick)
        self.table.pack(fill='both', expand=True, pady=(6, 0))
        self.count = label(left, f'{len(self.files)} file{"s" if len(self.files) != 1 else ""}', style='Faint.TLabel')
        self.count.pack(anchor='w', pady=(4, 0))
        tk.Frame(main, width=1, bg=C['line']).pack(side='left', fill='y', padx=(16, 0))
        right = frame(main)
        right.pack(side='left', fill='both', expand=True, padx=(18, 20))
        head = frame(right)
        head.pack(fill='x')
        self.h_title = ttk.Label(head, text='', style='Record.TLabel')
        self.h_title.pack(side='left')
        self.h_undo = Link(head, '', self.undo_file)
        self.h_undo.pack(side='right')
        self.h_sub = label(right, '', style='Muted.TLabel')
        self.h_sub.pack(anchor='w')
        self.strip = UnsavedStrip(right, self.keep, self.revert, hint='kept when you leave this file')
        self.strip.place_like(fill='x', pady=(8, 0))
        tools = frame(right)
        tools.pack(fill='x', pady=(8, 6))
        self.strip.before = tools
        self.valid = tk.Label(tools, text='', bg=C['bg'], font=(FONT, 9, 'bold'), anchor='w')
        self.valid.pack(side='left')
        Button(tools, 'Format', self.format, small=True).pack(side='right')
        box = tk.Frame(right, bg=C['line2'], padx=1, pady=1)
        box.pack(fill='both', expand=True)
        inner = tk.Frame(box, bg=C['bg'])
        inner.pack(fill='both', expand=True)
        self.text = tk.Text(inner, font=(MONO, 10), wrap='none', bd=0, highlightthickness=0, undo=True,
                            fg=C['text'], bg=C['bg'], insertbackground=C['text'], padx=6, pady=4)
        ys = ttk.Scrollbar(inner, orient='vertical', command=self.text.yview)
        xs = ttk.Scrollbar(inner, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side='right', fill='y')
        xs.pack(side='bottom', fill='x')
        self.text.pack(side='left', fill='both', expand=True)
        self.text.tag_configure('err', background=C['danger_soft'])
        self.text.bind('<KeyRelease>', lambda _e: self._later())
        self.reload_rows()
        self.table.select_first()

    def op_key(self, op):
        return op.get('path') if op.get('op') == 'extradata' else None

    def reload_rows(self):
        rows = []
        for rel, obj in self.files:
            n = len(obj) if isinstance(obj, (list, dict)) else 1
            rows.append((rel, (rel[len('ExtraData/'):], n)))
        ed = {k for k in (self.op_key(op) for op in self.s.project.ops) if k is not None}
        self.table.set_rows(rows, ed)

    def _pick(self, key):
        if self.key is not None and key != self.key and not self.keep():
            return False
        self.load(key)
        return True

    def load(self, rel):
        obj = dict(self.files).get(rel)
        if obj is None:
            return
        self.key = rel
        self.base_obj = obj
        self.base_text = json.dumps(obj, indent=2, ensure_ascii=False)
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.base_text)
        self.text.edit_reset()
        folder, _, name = rel.rpartition('/')
        self.h_title.config(text=name)
        self.h_sub.config(text=folder)
        n = sum(1 for op in self.s.project.ops if self.op_key(op) == rel)
        self.h_undo.config(text=f'Undo my {n} edit{"s" if n != 1 else ""} to this file' if n else '')
        self.validate()

    def _later(self):
        if self._after is not None:
            self.after_cancel(self._after)
        self._after = self.after(250, self.validate)

    def parse(self):
        """-> (object, None) or (None, JSONDecodeError)"""
        try:
            return json.loads(self.text.get('1.0', 'end-1c')), None
        except json.JSONDecodeError as e:
            return None, e

    def validate(self):
        self._after = None
        self.text.tag_remove('err', '1.0', 'end')
        obj, err = self.parse()
        if err is None:
            self.valid.config(text='✓  Valid JSON', fg=C['ok'])
        else:
            self.valid.config(text=f'✕  Error at line {err.lineno}, column {err.colno}: {err.msg}', fg=C['danger'])
            self.text.tag_add('err', f'{err.lineno}.0', f'{err.lineno}.end+1c')
        self.strip.show(self.dirty())
        return obj, err

    def format(self):
        obj, err = self.validate()
        if err is not None:
            self.text.see(f'{err.lineno}.0')
            return
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', json.dumps(obj, indent=2, ensure_ascii=False))
        self.validate()

    def dirty(self):
        if self.key is None:
            return False
        t = self.text.get('1.0', 'end-1c')
        if t == self.base_text:
            return False
        obj, err = self.parse()
        return err is not None or obj != self.base_obj

    def _poll(self):
        try:
            if self.files and self.winfo_exists():
                self.strip.show(self.dirty())
        except (tk.TclError, AttributeError):
            pass
        try:
            self.after(400, self._poll)
        except tk.TclError:
            pass

    def keep(self):
        if not self.dirty():
            return True
        rel = self.key
        obj, err = self.validate()
        if err is not None:
            self.say(f'Not kept: the file is not valid JSON (line {err.lineno}). Fix it or press Revert.')
            self.text.see(f'{err.lineno}.0')
            return False
        n = len(self.s.project.ops)
        w = self.s.run({'op': 'extradata', 'path': rel, 'json': obj})
        if w:
            drop_failed(self.s, n)
            self.valid.config(text=f'Not kept: {w}', fg=C['danger'])
            return False
        self.base_obj = obj
        self.base_text = self.text.get('1.0', 'end-1c')
        self.app.edits_changed(f'Kept your changes to {rel.rpartition("/")[2]}.')
        return True

    def revert(self):
        if self.key is not None:
            self.load(self.key)

    def undo_file(self):
        idx = [i for i, op in enumerate(self.s.project.ops) if self.op_key(op) == self.key]
        if not idx or not messagebox.askyesno('Undo edits', f'Remove your {len(idx)} edit{"s" if len(idx) != 1 else ""}'
                                              f' to {self.key}?', parent=self):
            return
        self.base_text = self.text.get('1.0', 'end-1c')
        self.base_obj, _ = self.parse()
        self.s.remove(idx)
        self.app.edits_changed(f'Removed {len(idx)} edit{"s" if len(idx) != 1 else ""} to {self.key}.')

    def leave(self):
        return self.keep() if self.built else True

    def refresh(self):
        if not self.built:
            return
        key = self.key
        self.build_all()
        if self.files and key is not None:
            self.goto(key)

    def goto(self, key):
        self.ensure()
        if self.files and key in dict(self.files):
            self.key = None
            self.table.select(key, notify=False)
            self.load(key)


# ======================================================================================================================
class ImportExportPage(Page):
    title = 'Import & export'
    subtitle = 'Your game data as JSON files to edit elsewhere, and your edits as a mod for the console or an emulator'
    MODES = [('Pokémon', 'Stats, typing, abilities, moves, TMs and evolutions of every Pokémon.', 'IOPokemon.json',
              jsonconv.export_pokemon, jsonconv.import_pokemon),
             ('Trainers', 'Every trainer and their party: levels, moves, items, natures.', 'IOTrainers.json',
              jsonconv.export_trainers, jsonconv.import_trainers),
             ('Text', 'The game\'s text, every language: names, descriptions, dialogue.', 'IOText.json',
              jsonconv.export_text, jsonconv.import_text)]

    def build_page(self):
        body = frame(self)
        body.pack(fill='both', expand=True, padx=24, pady=(14, 10))
        label(body, 'JSON files', style='Section.TLabel').pack(anchor='w')
        label(body, 'Pokémon, trainers and text as JSON files (English names). Importing keeps only the values that '
                    'differ from your game data, as changes in your edits - you can undo them on the Your edits page.',
              style='Muted.TLabel', wraplength=1000, justify='left').pack(anchor='w', pady=(2, 10))
        row = frame(body)
        row.pack(fill='x')
        self.notes = {}
        for k, (name, text, fname, _ex, _im) in enumerate(self.MODES):
            outer, b = card(row, name, text, width=290)
            outer.grid(row=0, column=k, sticky='nsew', padx=(0 if k == 0 else 14, 0))
            row.columnconfigure(k, weight=1, uniform='c')
            bb = frame(b)
            bb.pack(anchor='w')
            Button(bb, 'Export...', lambda k=k: self.export_json(k), kind='primary', small=True).pack(side='left')
            Button(bb, 'Import...', lambda k=k: self.import_json(k), small=True).pack(side='left', padx=(8, 0))
            label(b, f'file name: {fname}', style='Faint.TLabel').pack(anchor='w', pady=(8, 0))
            self.notes[k] = tk.Label(b, text='', bg=C['bg'], fg=C['muted'], font=(FONT, 9), anchor='w', justify='left',
                                     wraplength=290)
            self.notes[k].pack(fill='x', pady=(4, 0))
        label(body, 'Console mod', style='Section.TLabel').pack(anchor='w', pady=(26, 0))
        tk.Frame(body, height=1, bg=C['line']).pack(fill='x', pady=(3, 10))
        outer, b = card(body, 'Export as a console mod (LayeredFS)',
                        'Writes your edits as a romfs mod folder for the console or an emulator, made from the same game '
                        'files as here (your dump plus the console mods you chose, merged). Pick an EMPTY folder.',
                        width=900)
        outer.pack(fill='x')
        top = frame(b)
        top.pack(fill='x')
        Button(top, 'Export a console mod...', self.export_console, kind='primary').pack(side='left')
        self.console_note = tk.Label(top, text='', bg=C['bg'], fg=C['muted'], font=(FONT, 9), anchor='w',
                                     justify='left', wraplength=700)
        self.console_note.pack(side='left', padx=(14, 0))
        self.console_link = frame(b)
        self.console_link.pack(fill='x')
        label(b, 'A Pokémon added as a new species also needs the console game\'s code changed; the console mod has the '
                 'data only.', style='Faint.TLabel', wraplength=900, justify='left').pack(anchor='w', pady=(10, 0))

    def export_json(self, k):
        name, _t, fname, ex, _im = self.MODES[k]
        path = filedialog.asksaveasfilename(parent=self, initialfile=fname, defaultextension='.json',
                                            filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(ex(self.s.game), f, indent=2, ensure_ascii=False)
        except OSError as e:
            self.notes[k].config(text=f'Not written: {e}', fg=C['danger'])
            return
        self.notes[k].config(text=f'✓  Written to {path}', fg=C['ok'])
        self.say(f'{name} exported to {path}.')

    def import_json(self, k):
        name, _t, _f, _ex, im = self.MODES[k]
        path = filedialog.askopenfilename(parent=self, filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            ops = im(self.s.game, data)
        except (ValueError, OSError) as e:
            self.app.reload()                  # an import that failed half-way leaves nothing behind
            self.notes[k].config(text=f'Not imported: {e}', fg=C['danger'])
            return
        n = self.s.commit(ops)
        self.app.edits_changed(f'{n} change{"s" if n != 1 else ""} imported from {name} JSON into your edits.')
        self.notes[k].config(text=f'✓  {n} change{"s" if n != 1 else ""} imported into your edits' if n else
                             'Nothing differs from your game data: nothing to import.', fg=C['ok'] if n else C['muted'])

    def export_console(self):
        from ...export import ExportError, export
        ops = self.s.project.ops
        if not ops:
            if not messagebox.askyesno('Export', 'Your edits are empty: the folder would hold only the files uDPRE '
                                       'merged from several console mods (if any). Export anyway?', parent=self):
                return
        elif not any(op.get('op') == 'randomize' for op in ops):
            if not messagebox.askyesno('Export', 'You have not randomized anything yet (Randomize page). Export your '
                                       'other edits anyway?', parent=self):
                return
        d = filedialog.askdirectory(parent=self, title='Pick an EMPTY folder for the console mod')
        if not d:
            return
        for w in self.console_link.winfo_children():
            w.destroy()
        self.console_note.config(text='Writing the console mod...', fg=C['muted'])
        self.update_idletasks()
        try:
            r = export(self.s, d, log=lambda _s: None)
        except (ExportError, OSError) as e:
            self.console_note.config(text=f'Not exported: {e}', fg=C['danger'])
            return
        self.console_note.config(text=f'✓  {len(r["files"])} files written to {d}.', fg=C['ok'])
        self.say(f'Console mod written to {d}.')
        if r['warnings']:
            n = len(r['warnings'])
            label(self.console_link, f'{n} operation{"s were" if n != 1 else " was"} skipped with these mods.',
                  style='Error.TLabel').pack(side='left', pady=(6, 0))
            Link(self.console_link, 'See them on Your edits', lambda: self.app.show('edits')).pack(
                side='left', padx=(8, 0), pady=(6, 0))

