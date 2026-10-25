"""Your edits: every operation of the edit project in a filterable table (what it does, where - with a jump to its page
and record), Remove / Undo last / Clear all, presets (Open / Save as), whether the game uses them, and the operations the
current mods skip (session.undo / remove / clear / open / save_as)."""
import importlib
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...game import BATTLE, GAMESETTINGS, MASTER, PERSONAL, UGDATA
from ...project import describe
from ..kit import Button, DataTable, Link, SearchBox, Section, frame, label
from ..page import Page, RecordPage
from ..shell import LABELS, PAGES
from ..theme import C, FONT

POKEMON_OBJS = {'PersonalTable', 'WazaOboeTable', 'EvolveTable', 'TamagoWazaTable', 'AddPersonalTable'}
OP_PAGE = {'randomize': 'randomize', 'typechart': 'typechart', 'metadata': 'metadata', 'insert': 'inserter',
           'extradata': 'extradata', 'eggmoves': 'pokemon'}
WARN_RE = re.compile(r'operation (\d+) \(')


def page_of(op):
    """-> (page name, fallback key) the operation belongs to, or (None, None)"""
    k = op.get('op')
    if k in OP_PAGE:
        key = None
        if k == 'eggmoves':
            key = tuple(op.get('key') or ())
        elif k == 'metadata':
            key = (op.get('image'), op.get('type'), op.get('field'))
        elif k == 'extradata':
            key = op.get('path')
        return OP_PAGE[k], key
    if k != 'set':
        return None, None
    f, obj, lst, key = op.get('file'), op.get('obj') or '', op.get('list'), op.get('key')
    if obj in POKEMON_OBJS:
        return 'pokemon', tuple(key) if isinstance(key, list) else None
    if obj == 'WazaTable' or (f == BATTLE and obj == 'BattleDataTable'):
        return 'moves', key
    if obj == 'ItemTable':
        return ('tms', None) if lst == 'WazaMachine' or op.get('field') == 'group_id' else ('items', key)
    if obj == 'ShopTable':
        return 'shops', None
    if obj == 'MonohiroiTable':
        return 'pickup', None
    if obj.startswith('FieldEncountTable'):
        return ('wild', key) if lst == 'table' else ('special', None)
    if f == UGDATA or obj.startswith('Ug'):
        return 'underground', None
    if obj == 'TrainerTable':
        return 'trainers', key
    if obj.startswith('Tower'):
        return 'tower', None
    if f in (MASTER, GAMESETTINGS, PERSONAL):
        return None, None
    return None, None


class EditsPage(Page):
    title = 'Your edits'
    subtitle = 'Every change you made, in the order the game gets them - remove, undo, save or open a set of edits'
    columns = [('no', 'No.', 52, 'e'), ('where', 'Where', 250, 'w'), ('what', 'What', 520, 'w'),
               ('state', 'With these mods', 120, 'w')]

    def build_page(self):
        body = frame(self)
        body.pack(fill='both', expand=True, padx=24, pady=(12, 10))
        # summary + actions
        top = frame(body)
        top.pack(fill='x')
        self.big = tk.Label(top, text='', bg=C['bg'], fg=C['text'], font=(FONT, 15, 'bold'))
        self.big.pack(side='left')
        self.use_lab = tk.Label(top, text='', bg=C['bg'], font=(FONT, 9, 'bold'), padx=8, pady=1)
        self.use_lab.pack(side='left', padx=(12, 0))
        ttk.Checkbutton(top, text='Use my edits in the game', variable=self.app.use_var, style='Studio.TCheckbutton',
                        command=self._toggle).pack(side='left', padx=(12, 0))
        for text, fn, kind in (('Save as preset...', self.save_preset, 'secondary'),
                               ('Open preset...', self.open_preset, 'secondary'),
                               ('Clear all', self.clear_all, 'danger'),
                               ('Undo last', self.undo, 'secondary')):
            Button(top, text, fn, kind=kind, small=True).pack(side='right', padx=(8, 0))
        self.hint = label(body, '', style='Muted.TLabel')
        self.hint.pack(anchor='w', pady=(2, 0))
        # filters
        bar = frame(body)
        bar.pack(fill='x', pady=(10, 0))
        self.search = SearchBox(bar, 'Filter your edits...', on_change=lambda _t: self._apply(), width=40)
        self.search.pack(side='left')
        self.kind = ttk.Combobox(bar, values=['Every page'], state='readonly', width=22, style='Studio.TCombobox')
        self.kind.current(0)
        self.kind.pack(side='left', padx=(10, 0))
        self.kind.bind('<<ComboboxSelected>>', lambda _e: self._apply())
        self.only_skipped = tk.BooleanVar()
        ttk.Checkbutton(bar, text='Skipped only', variable=self.only_skipped, style='Studio.TCheckbutton',
                        command=self._apply).pack(side='left', padx=(12, 0))
        self.remove_btn = Button(bar, 'Remove selected', self.remove_sel, kind='danger', small=True)
        self.remove_btn.pack(side='right')
        self.count = label(bar, '', style='Faint.TLabel')
        self.count.pack(side='right', padx=(0, 12))
        # table
        self.table = DataTable(body, self.columns, on_select=lambda _k: self._sel_changed(), marker=False,
                               height=14, on_activate=self.open_op)
        self.table.tree.configure(selectmode='extended')
        self.table.tree.bind('<<TreeviewSelect>>', lambda _e: self._sel_changed(), add='+')
        self.table.tree.bind('<Delete>', lambda _e: self.remove_sel())
        self.table.tree.tag_configure('skipped', foreground=C['danger'])
        self.table.pack(fill='both', expand=True, pady=(6, 0))
        sel = frame(body)
        sel.pack(fill='x', pady=(6, 0))
        self.sel_lab = label(sel, '', style='Muted.TLabel')
        self.sel_lab.pack(side='left')
        self.sel_link = Link(sel, '', self.open_current)
        self.sel_link.pack(side='left', padx=(10, 0))
        label(sel, 'Double-click a row to open it · Ctrl/Shift+click selects several · Delete removes them',
              style='Faint.TLabel').pack(side='right')
        # problems
        self.prob = Section(body, 'Skipped with your current mods',
                            hint='the rows these edits change are not in the game files of this mod choice')
        self.prob.pack(fill='x', pady=(12, 0))
        pb = tk.Frame(self.prob.body, bg=C['line2'], padx=1, pady=1)
        pb.pack(fill='x')
        self.plist = tk.Listbox(pb, height=4, font=(FONT, 9), bd=0, highlightthickness=0, activestyle='none',
                                fg=C['danger'], selectbackground=C['danger_soft'], selectforeground=C['danger'])
        self.plist.pack(fill='x')
        self.plist.bind('<<ListboxSelect>>', lambda _e: self._problem_pick())
        self.prob_ok = label(self.prob.body, '', style='Muted.TLabel')
        self.render()

    # --- data -----------------------------------------------------------------------------------------------------
    def locate(self, op):
        """-> (page name or None, key or None, 'Where' text)"""
        name, key = page_of(op)
        if name is None:
            k = op.get('op')
            if k in ('text', 'words'):
                return None, None, f'Text · {op.get("sheet")}'
            if k == 'set':
                return None, None, f'Game data · {op.get("obj")}'
            return None, None, k or '?'
        p = self._page(name)
        if p is not None and hasattr(p, 'op_key'):
            try:
                k2 = p.op_key(op)
                if k2 is not None:
                    key = k2
            except Exception:
                pass
        where = LABELS.get(name, name)
        if key is not None:
            nm = None
            if p is not None and type(p).record_name is not RecordPage.record_name and hasattr(p, 'record_name'):
                try:
                    nm = p.record_name(key)
                except Exception:
                    nm = None
            if nm is None:
                nm = self._name(name, key)
            if nm:
                where += f' · {nm}'
        return name, key, where

    def _page(self, name):
        """the page object (for its op_key / record_name): the app's when it exists, else an unbuilt one of our own
        (creating the app's page here would change app.pages while edits_changed walks it)"""
        if name in self.app.pages:
            return self.app.pages[name]
        if not hasattr(self, '_probes'):
            self._probes = {}
        if name not in self._probes:
            try:
                mod, cls = PAGES[name]
                m = importlib.import_module(f'.{mod}', __package__)
                self._probes[name] = getattr(m, cls)(self.app, self)
            except Exception:
                self._probes[name] = None
        return self._probes[name]

    def _name(self, name, key):
        g = self.s.game
        try:
            if name == 'pokemon':
                return g.pokemon_name(*key)
            if name == 'moves':
                return g.move_name(key)
            if name == 'items':
                return g.item_name(key)
            if name == 'trainers':
                t = g.trainers[key]
                return f'{g.trainer_type_name(t["TypeID"])} {g.trainer_name(key)}'.strip()
            if name == 'wild':
                return g.zone_name(key)
            if name == 'metadata':
                return f'{key[1]}.{key[2]}'
            if name == 'extradata':
                return str(key).rpartition('/')[2]
        except Exception:
            return str(key)
        return str(key)

    def skipped(self):
        """{operation index: warning} of session.warnings that name an operation; [other warnings]"""
        by, other = {}, []
        for w in self.s.warnings:
            m = WARN_RE.match(str(w))
            if m:
                by.setdefault(int(m.group(1)) - 1, str(w))
            else:
                other.append(str(w))
        return by, other

    def render(self):
        ops = self.s.project.ops
        self.where = {}
        rows = []
        pages = set()
        by, other = self.skipped()
        self.warn_by = by
        for i, op in enumerate(ops):
            name, key, where = self.locate(op)
            self.where[i] = (name, key, where)
            if name:
                pages.add(LABELS.get(name, name))
            try:
                what = describe(op)
            except Exception:
                what = str(op.get('op'))
            rows.append((i, (i + 1, where, what, '⚠ skipped' if i in by else 'applies')))
        kinds = ['Every page'] + sorted(pages) + (['Text'] if any(op.get('op') in ('text', 'words') for op in ops)
                                                  else [])
        cur = self.kind.get()
        self.kind.configure(values=kinds)
        if cur not in kinds:
            self.kind.current(0)
        self.table.set_rows(rows)
        self._apply()
        # summary
        n = len(ops)
        on = self.app.use_var.get()
        self.big.config(text=f'{n} change{"s" if n != 1 else ""}' if n else 'No changes yet')
        self.use_lab.config(text='used in the game' if on else 'not used in the game',
                            bg=C['ok_soft'] if on else C['soft'], fg=C['ok'] if on else C['muted'])
        self.hint.config(text=('They go into the game at the next Apply / Convert in the uDPRE window.' if on else
                               'They are kept, but the game does not use them until you tick "Use my edits in the '
                               'game".') if n else 'Changes you keep on any page appear here.')
        # problems
        self.plist.delete(0, 'end')
        self.problems = []
        for i in sorted(by):
            self.problems.append(i)
            self.plist.insert('end', '  ' + by[i].splitlines()[0])
        for w in other:
            self.problems.append(None)
            self.plist.insert('end', '  ' + w.splitlines()[0])
        if self.problems:
            self.prob_ok.pack_forget()
            self.plist.master.pack(fill='x')
            self.plist.configure(height=min(4, len(self.problems)))
        else:
            self.plist.master.pack_forget()
            self.prob_ok.config(text='None - every change applies to the game files of your current mods.')
            self.prob_ok.pack(anchor='w')
        self._sel_changed()

    def _apply(self):
        t = self.search.get_text().lower().strip()
        k = self.kind.get()
        sk = self.only_skipped.get()

        def pred(key, vals):
            if sk and key not in self.warn_by:
                return False
            if k == 'Text':
                return vals[1].startswith('Text · ')
            if k != 'Every page':
                return vals[1] == k or vals[1].startswith(k + ' · ')
            return True
        self.table.text = t
        self.table.filter(pred=pred)
        for iid, key in self.table._key.items():
            if key in self.warn_by:
                tags = list(self.table.tree.item(iid, 'tags')) + ['skipped']
                self.table.tree.item(iid, tags=tags)
        n, m = self.table.count(), len(self.table.rows)
        self.count.config(text=f'{n} of {m} shown' if n != m else '')

    def selected(self):
        return sorted(self.table._key[iid] for iid in self.table.tree.selection() if iid in self.table._key)

    def _sel_changed(self):
        sel = self.selected()
        self.remove_btn.set_enabled(bool(sel))
        if not sel:
            self.sel_lab.config(text='')
            self.sel_link.config(text='')
        elif len(sel) == 1:
            name, key, where = self.where.get(sel[0], (None, None, ''))
            self.sel_lab.config(text=f'Change {sel[0] + 1}:')
            self.sel_link.config(text=f'Open {where}  →' if name else '')
        else:
            self.sel_lab.config(text=f'{len(sel)} changes selected')
            self.sel_link.config(text='')

    # --- actions --------------------------------------------------------------------------------------------------
    def open_op(self, i):
        name, key, _w = self.where.get(i, (None, None, ''))
        if name:
            self.app.show(name, key)

    def open_current(self):
        sel = self.selected()
        if len(sel) == 1:
            self.open_op(sel[0])

    def _problem_pick(self):
        s = self.plist.curselection()
        if not s or self.problems[s[0]] is None:
            return
        i = self.problems[s[0]]
        if i not in self.table._iid:
            self.search.clear()
            self.kind.current(0)
            self.only_skipped.set(False)
            self.table.text = ''
            self._apply()
        iid = self.table._iid.get(i)
        if iid is not None:
            self.table.tree.selection_set(iid)
            self.table.tree.see(iid)

    def _toggle(self):
        self.app.toggle_use()
        self.render()

    def undo(self):
        if not self.s.project.ops:
            self.say('Your edits are empty: nothing to undo.')
            return
        what = describe(self.s.project.ops[-1])
        self.s.undo()
        self.app.edits_changed(f'Undid the last change ({what}).')

    def remove_sel(self):
        sel = self.selected()
        if not sel:
            return
        if not messagebox.askyesno(self.title, f'Remove {len(sel)} change{"s" if len(sel) != 1 else ""} from your edits?'
                                   , parent=self):
            return
        self.s.remove(sel)
        self.app.edits_changed(f'Removed {len(sel)} change{"s" if len(sel) != 1 else ""}.')

    def clear_all(self):
        if self.s.project.ops and messagebox.askyesno(self.title, 'Remove every change of your edits?', parent=self):
            n = len(self.s.project.ops)
            self.s.clear()
            self.app.edits_changed(f'Removed all {n} changes.')

    def save_preset(self):
        d = os.path.join(self.s.p.root, 'edits')
        path = filedialog.asksaveasfilename(parent=self, initialdir=d, defaultextension='.json',
                                            filetypes=[('uDPRE edits', '*.json')])
        if path:
            self.s.save_as(path)
            self.say(f'Your edits were saved as {path}.')

    def open_preset(self):
        d = os.path.join(self.s.p.root, 'edits')
        path = filedialog.askopenfilename(parent=self, initialdir=d, filetypes=[('uDPRE edits', '*.json')])
        if path and messagebox.askyesno(self.title, 'Replace your current edits with this file\'s?', parent=self):
            try:
                self.s.open(path)
            except Exception as e:
                messagebox.showerror(self.title, f'That file cannot be opened: {e}', parent=self)
                return
            self.app.edits_changed(f'Opened {os.path.basename(path)}: {len(self.s.project.ops)} changes.')

    # --- page hooks -----------------------------------------------------------------------------------------------
    def on_show(self):
        self.render()

    def refresh(self):
        if self.built:
            self.render()
