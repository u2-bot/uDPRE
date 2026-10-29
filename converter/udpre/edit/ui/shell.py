"""uDPRE Studio - the Editor & Randomizer window: a sidebar of pages, a header with the page title and a search that finds
Pokemon, moves, items, trainers and areas from anywhere, and a status bar with your edits. Every change becomes an
operation of the edit project (edits/project.json); the main window's Apply / Convert builds them into the game."""
import importlib
import tkinter as tk
from tkinter import messagebox, ttk

from ... import winfit
from ..session import Session
from . import theme
from .base import Choices
from .kit import SearchBox, frame
from .theme import C, FONT

TITLE = 'uDPRE - Editor & Randomizer (Beta)'
NAV = [
    ('', [('overview', 'Overview'), ('randomize', 'Randomize')]),
    ('POKÉMON', [('pokemon', 'Pokémon')]),
    ('MOVES & ITEMS', [('moves', 'Moves'), ('tms', 'TMs'), ('items', 'Items'), ('shops', 'Shops'), ('pickup', 'Pickup')]),
    ('WORLD', [('wild', 'Wild areas'), ('special', 'Special encounters'), ('underground', 'Underground')]),
    ('BATTLES', [('trainers', 'Trainers'), ('tower', 'Battle Tower'), ('typechart', 'Type chart')]),
    ('ADVANCED', [('inserter', 'Add a Pokémon'), ('metadata', 'Game code values'), ('extradata', 'Mod data files'),
                  ('json', 'Import & export')]),
    ('', [('edits', 'Your edits')]),
]
PAGES = {   # name -> (module of .pages, class)
    'overview': ('overview', 'OverviewPage'), 'randomize': ('randomize', 'RandomizePage'),
    'pokemon': ('pokemon', 'PokemonPage'), 'moves': ('moves', 'MovesPage'), 'tms': ('moves', 'TMsPage'),
    'items': ('items', 'ItemsPage'), 'shops': ('items', 'ShopsPage'), 'pickup': ('items', 'PickupPage'),
    'wild': ('world', 'WildPage'), 'special': ('world', 'SpecialPage'), 'underground': ('world', 'UndergroundPage'),
    'trainers': ('trainers', 'TrainersPage'), 'tower': ('trainers', 'TowerPage'),
    'typechart': ('typechart', 'TypeChartPage'), 'inserter': ('advanced', 'InserterPage'),
    'metadata': ('advanced', 'MetadataPage'), 'extradata': ('advanced', 'ExtraDataPage'),
    'json': ('advanced', 'ImportExportPage'), 'edits': ('edits', 'EditsPage'),
}
LABELS = {name: lab for _g, items in NAV for name, lab in items}


def _frozen_imports():
    """never called: names every page module for PyInstaller, which cannot follow the importlib loading below (a
    build with --collect-submodules alone ships none of the pages)"""
    from .pages import (advanced, edits, items, moves, overview, pokemon, randomize, trainers,  # noqa: F401
                        typechart, world)


class EditorApp:
    def __init__(self, root_dir, master=None, mod_ids=None, options=None, on_change=None):
        self.win = tk.Toplevel(master) if master is not None else tk.Tk()
        self.win.title(TITLE)
        winfit.fit(self.win, 1360, 860, 1120, 700)
        self.win.configure(bg=C['bg'])
        theme.setup(self.win)
        self.on_change = on_change
        lab = tk.Label(self.win, text='Reading the game data of your mod choice...', bg=C['bg'], fg=C['muted'],
                       font=(FONT, 12))
        lab.pack(padx=20, pady=60)
        self.win.update()
        try:
            self.session = Session(root_dir, mod_ids, options, log=lambda _s: None)
        except Exception as e:
            lab.destroy()
            messagebox.showerror(TITLE, f'The editor cannot open: {e}', parent=self.win)
            self.win.destroy()
            raise
        lab.destroy()
        self.choices = Choices(self.session)
        self.pages = {}
        self.current = None
        self._index = None
        self._build()
        self.win.bind('<Control-s>', lambda _e: self.keep_current())
        self.win.bind('<Control-f>', lambda _e: self.focus_search())
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.changed()
        self.show('overview')

    # --- layout -------------------------------------------------------------------------------------------------------
    def _build(self):
        side = tk.Frame(self.win, bg=C['side'], width=210)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        tk.Label(side, text='uDPRE Studio', bg=C['side'], fg='#ffffff', font=(FONT, 13, 'bold'), anchor='w').pack(
            fill='x', padx=18, pady=(16, 0))
        tk.Label(side, text='Editor & Randomizer · Beta', bg=C['side'], fg=C['side_head'], font=(FONT, 8),
                 anchor='w').pack(fill='x', padx=18, pady=(0, 10))
        self.nav = {}
        for group, items in NAV:
            if group:
                tk.Label(side, text=group, bg=C['side'], fg=C['side_head'], font=(FONT, 7, 'bold'), anchor='w').pack(
                    fill='x', padx=18, pady=(12, 2))
            else:
                tk.Frame(side, height=8, bg=C['side']).pack(fill='x')
            for name, text in items:
                row = tk.Frame(side, bg=C['side'], cursor='hand2')
                row.pack(fill='x', padx=8)
                lab = tk.Label(row, text=text, bg=C['side'], fg=C['side_text'], font=(FONT, 10), anchor='w', padx=10,
                               pady=4, cursor='hand2')
                lab.pack(side='left', fill='x', expand=True)
                badge = tk.Label(row, text='', bg=C['side'], fg=C['side_text'], font=(FONT, 8, 'bold'), padx=6)
                badge.pack(side='right', padx=(0, 6))
                for w in (row, lab, badge):
                    w.bind('<Button-1>', lambda _e, n=name: self.show(n))
                    w.bind('<Enter>', lambda _e, n=name: self._hover(n, True))
                    w.bind('<Leave>', lambda _e, n=name: self._hover(n, False))
                self.nav[name] = (row, lab, badge)
        tk.Label(side, text=f'mods: {self.session.mods_text()}', bg=C['side'], fg=C['side_head'], font=(FONT, 8),
                 wraplength=180, justify='left', anchor='w').pack(side='bottom', fill='x', padx=18, pady=12)
        main = frame(self.win)
        main.pack(side='left', fill='both', expand=True)
        head = frame(main)
        head.pack(fill='x', padx=24, pady=(14, 8))
        titles = frame(head)
        titles.pack(side='left', fill='x', expand=True)
        self.title = ttk.Label(titles, text='', style='Title.TLabel')
        self.title.pack(anchor='w')
        self.subtitle = ttk.Label(titles, text='', style='Muted.TLabel')
        self.subtitle.pack(anchor='w')
        self.search = SearchBox(head, 'Find a Pokémon, move, item, trainer or area   (Ctrl+F)', self._search, width=46)
        self.search.pack(side='right', anchor='n', pady=(4, 0))
        self.search.bind('<Down>', lambda _e: self._results_focus())
        self.search.bind('<Return>', lambda _e: self._results_go(0))
        self.search.bind('<Escape>', lambda _e: self._results_close())
        self.search.bind('<FocusOut>', lambda _e: self.win.after(200, self._results_close_unless_focus))
        tk.Frame(main, height=1, bg=C['line']).pack(fill='x')
        status = tk.Frame(main, bg=C['soft'])
        status.pack(side='bottom', fill='x')
        tk.Frame(main, height=1, bg=C['line']).pack(side='bottom', fill='x')
        self.msg = tk.Label(status, text='', bg=C['soft'], fg=C['muted'], font=(FONT, 9), anchor='w')
        self.msg.pack(side='left', padx=16, pady=5)
        self.use_var = tk.BooleanVar(value=self.session.enabled())
        tk.Checkbutton(status, text='Use my edits in the game', variable=self.use_var, command=self.toggle_use,
                       bg=C['soft'], activebackground=C['soft'], font=(FONT, 9), fg=C['text']).pack(side='right',
                                                                                                padx=(6, 14))
        self.count = tk.Label(status, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9, 'bold'))
        self.count.pack(side='right')
        self.content = frame(main)
        self.content.pack(fill='both', expand=True)
        self.results = None

    def _hover(self, name, on):
        if name == self.current:
            return
        row, lab, badge = self.nav[name]
        bg = C['side_hover'] if on else C['side']
        for w in (row, lab, badge):
            w.config(bg=bg)

    def _paint_nav(self):
        for name, (row, lab, badge) in self.nav.items():
            on = name == self.current
            bg = C['side_active'] if on else C['side']
            for w in (row, lab, badge):
                w.config(bg=bg)
            lab.config(fg='#ffffff' if on else C['side_text'], font=(FONT, 10, 'bold' if on else 'normal'))

    # --- pages --------------------------------------------------------------------------------------------------------
    def page(self, name):
        if name not in self.pages:
            mod, cls = PAGES[name]
            m = importlib.import_module(f'.pages.{mod}', __package__)
            self.pages[name] = getattr(m, cls)(self, self.content)
        return self.pages[name]

    def show(self, name, key=None):
        if name not in PAGES:
            return
        if self.current is not None and self.current != name:
            cur = self.pages.get(self.current)
            if cur is not None and not cur.leave():
                self.say('Fix the value the page shows in red first (or press Discard).')
                return
            if cur is not None:
                cur.pack_forget()
        self._results_close()
        p = self.page(name)
        if self.current != name:
            self.current = name
            self._paint_nav()
            self.title.config(text=p.title or LABELS.get(name, name))
            self.subtitle.config(text=p.subtitle)
            p.pack(fill='both', expand=True)
            self.win.update_idletasks()
            p.ensure()
            p.on_show()
        if key is not None:
            p.goto(key)

    def keep_current(self):
        p = self.pages.get(self.current)
        if p is not None and hasattr(p, 'keep'):
            p.keep()

    def close(self):
        p = self.pages.get(self.current)
        if p is not None and not p.leave():
            if not messagebox.askyesno(TITLE, 'A value on this page cannot be kept (shown in red). Close and lose that '
                                       'change?', parent=self.win):
                return
        self.win.destroy()

    # --- your edits ---------------------------------------------------------------------------------------------------
    def changed(self, msg=None):
        s = self.session
        n = len(s.project.ops)
        self.count.config(text=f'{n} change{"s" if n != 1 else ""} in your edits' + ('' if n else ''))
        self.nav['edits'][2].config(text=str(n) if n else '')
        if msg:
            self.say(msg)
        if self.on_change:
            self.on_change()
        p = self.pages.get('overview')
        if p is not None and p.built and self.current != 'overview':
            p.stale = True

    def edits_changed(self, msg=None):
        """operations were removed / replaced / run (undo, randomize, import): every page shows the data again"""
        self.choices.clear()
        self._index = None
        for p in self.pages.values():
            if p.built:
                p.refresh()
        self.changed(msg)

    def reload(self):
        self.session.reload()
        self.edits_changed()

    def toggle_use(self):
        self.session.set_enabled(self.use_var.get())
        self.say('Your edits are used in the game from the next Apply / Convert.' if self.use_var.get() else
                 'Your edits are kept but not used in the game (from the next Apply / Convert).')
        self.changed()

    def say(self, text):
        self.msg.config(text=text or '')

    # --- search everywhere --------------------------------------------------------------------------------------------
    def focus_search(self):
        self.search.focus_set()
        self.search.select_range(0, 'end')

    def index(self):
        if self._index is None:
            g = self.session.game
            out = []
            for name, lab in LABELS.items():
                out.append((f'Page · {lab}', name, None))
            for key, lab in self.choices.species():
                if key != (0, 0):
                    out.append((f'Pokémon · {lab}', 'pokemon', key))
            for m in g.moves:
                if m['wazaNo']:
                    out.append((f'Move · {m["wazaNo"]:03d} {g.move_name(m["wazaNo"])}', 'moves', m['wazaNo']))
            for it in g.items:
                nm = g.item_name(it['no'])
                if nm and nm != '-':
                    out.append((f'Item · {it["no"]:04d} {nm}', 'items', it['no']))
            for i in range(len(g.trainers)):
                t = g.trainers[i]
                out.append((f'Trainer · {i:04d} {g.trainer_type_name(t["TypeID"])} {g.trainer_name(i)}', 'trainers', i))
            try:
                tree = dict(g.encounter_files()).get('d')
                for r in (tree or {}).get('table', []):
                    out.append((f'Area · {r["zoneID"]:03d} {g.zone_name(r["zoneID"])}', 'wild', r['zoneID']))
            except Exception:
                pass
            self._index = out
        return self._index

    def _search(self, text):
        t = text.strip().lower()
        if len(t) < 2:
            self._results_close()
            return
        hits = []
        for lab, page, key in self.index():
            name = lab.split(' · ', 1)[1].lower()
            if t in name:
                hits.append((0 if name.split(' ', 1)[-1].startswith(t) or name.startswith(t) else 1, lab, page, key))
        hits.sort(key=lambda h: (h[0], h[1]))
        self._hits = hits[:60]
        self._results_show()

    def _results_show(self):
        if not self._hits:
            self._results_close()
            return
        if self.results is None:
            self.results = tk.Toplevel(self.win)
            self.results.overrideredirect(True)
            self.results.configure(bg=C['line2'])
            self.rlist = tk.Listbox(self.results, font=(FONT, 9), height=14, activestyle='none', bd=0,
                                    highlightthickness=0, selectbackground=C['select'], selectforeground=C['text'])
            self.rlist.pack(fill='both', expand=True, padx=1, pady=1)
            self.rlist.bind('<Return>', lambda _e: self._results_go(None))
            self.rlist.bind('<Double-1>', lambda _e: self._results_go(None))
            self.rlist.bind('<ButtonRelease-1>', lambda _e: self._results_go(None))
            self.rlist.bind('<Escape>', lambda _e: self._results_close())
            self.rlist.bind('<FocusOut>', lambda _e: self.win.after(200, self._results_close_unless_focus))
        self.rlist.delete(0, 'end')
        for _r, lab, _p, _k in self._hits:
            self.rlist.insert('end', '  ' + lab)
        x = self.search.winfo_rootx()
        y = self.search.winfo_rooty() + self.search.winfo_height() + 2
        w = max(self.search.winfo_width(), 420)
        self.results.geometry(f'{w}x{min(14, len(self._hits)) * 19 + 4}+{x + self.search.winfo_width() - w}+{y}')
        self.results.deiconify()
        self.results.lift()

    def _results_focus(self):
        if self.results is not None and self.results.winfo_viewable():
            self.rlist.focus_set()
            self.rlist.selection_clear(0, 'end')
            self.rlist.selection_set(0)
            self.rlist.activate(0)

    def _results_go(self, idx):
        if self.results is None or not getattr(self, '_hits', None):
            return
        if idx is None:
            s = self.rlist.curselection()
            if not s:
                return
            idx = s[0]
        _r, lab, page, key = self._hits[idx]
        self._results_close()
        self.search.clear()
        self.win.focus_set()
        self.show(page, key)

    def _results_close_unless_focus(self):
        f = self.win.focus_get() if self.win.winfo_exists() else None
        if f is not None and (f is self.search or (self.results is not None and str(f).startswith(str(self.results)))):
            return
        self._results_close()

    def _results_close(self):
        if self.results is not None:
            self.results.withdraw()


def main(root_dir):
    app = EditorApp(root_dir)
    app.win.mainloop()
