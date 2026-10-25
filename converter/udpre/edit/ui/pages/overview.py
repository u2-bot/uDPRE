"""Overview: what the editor works on (your mod choice and its game data), the state of your edits, and the places to
start."""
import tkinter as tk

from ..kit import Button, Section, frame, label
from ..page import Page
from ..theme import C, FONT

TILES = [
    ('randomize', 'Randomize', 'Reroll Pokémon, moves, encounters, trainers and more from one seed.'),
    ('pokemon', 'Pokémon', 'Stats, typing, abilities, moves, TMs and evolutions of every Pokémon and form.'),
    ('trainers', 'Trainers', 'Every trainer\'s party, items and battle style; Showdown import and export.'),
    ('wild', 'Wild areas', 'What appears in grass, caves, water and on fishing rods, per area.'),
    ('typechart', 'Type chart', 'How strong each type is against every other type.'),
    ('inserter', 'Add a Pokémon', 'A new form or a whole new species, copied from one you pick.'),
]


class OverviewPage(Page):
    title = 'Overview'
    subtitle = 'What you are editing and where to start'

    def build_page(self):
        self.stale = False
        self.wrap = frame(self)
        self.wrap.pack(fill='both', expand=True, padx=24, pady=16)
        self.render()

    def on_show(self):
        if getattr(self, 'stale', False):
            self.stale = False
            self.render()

    def refresh(self):
        if self.built:
            self.render()

    def render(self):
        for w in self.wrap.winfo_children():
            w.destroy()
        s, g = self.s, self.s.game
        cols = frame(self.wrap)
        cols.pack(fill='x')
        left = Section(cols, 'Your game data', hint='the dump of your last conversion + your mod choice')
        left.pack(side='left', fill='both', expand=True, padx=(0, 24))
        mods = [m.name for m in s.setup.chosen] or ['No mods - the game as it ships']
        for m in mods:
            label(left.body, '•  ' + m).pack(anchor='w')
        counts = [(len(list(g.species_rows())), 'Pokémon and forms'), (sum(1 for m in g.moves if m['wazaNo']), 'moves'),
                  (len(g.items), 'items'), (len(g.trainers), 'trainers')]
        row = frame(left.body)
        row.pack(anchor='w', pady=(10, 0))
        for n, what in counts:
            box = frame(row)
            box.pack(side='left', padx=(0, 28))
            tk.Label(box, text=f'{n:,}', bg=C['bg'], fg=C['text'], font=(FONT, 16, 'bold')).pack(anchor='w')
            label(box, what, style='Muted.TLabel').pack(anchor='w')
        right = Section(cols, 'Your edits')
        right.pack(side='left', fill='both', expand=True)
        n = len(s.project.ops)
        on = s.enabled()
        tk.Label(right.body, text=f'{n} change{"s" if n != 1 else ""}', bg=C['bg'], fg=C['text'],
                 font=(FONT, 16, 'bold')).pack(anchor='w')
        state = ('used in the game' if on else 'not used in the game - tick "Use my edits in the game" below') if n else \
            'nothing changed yet'
        label(right.body, state, style='Muted.TLabel').pack(anchor='w')
        if n:
            label(right.body, 'They reach the game when you press Apply / Convert in the uDPRE window.',
                  style='Muted.TLabel').pack(anchor='w', pady=(6, 0))
        b = frame(right.body)
        b.pack(anchor='w', pady=(10, 0))
        Button(b, 'See every change', lambda: self.app.show('edits')).pack(side='left')
        if s.warnings:
            warn = Section(self.wrap, 'Needs a look', hint=f'{len(s.warnings)} note(s) about these game files')
            warn.pack(fill='x', pady=(22, 0))
            for w in s.warnings[:8]:
                label(warn.body, '•  ' + w, style='Error.TLabel', wraplength=980).pack(anchor='w')
            if len(s.warnings) > 8:
                label(warn.body, f'... and {len(s.warnings) - 8} more on the Your edits page.',
                      style='Muted.TLabel').pack(anchor='w')
        start = Section(self.wrap, 'Start here')
        start.pack(fill='x', pady=(22, 0))
        grid = frame(start.body)
        grid.pack(fill='x')
        for k, (name, title, text) in enumerate(TILES):
            self.tile(grid, name, title, text).grid(row=k // 3, column=k % 3, sticky='nsew', padx=(0, 12), pady=(0, 12))
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform='tiles')

    def tile(self, master, name, title, text):
        t = tk.Frame(master, bg=C['bg'], highlightthickness=1, highlightbackground=C['line2'], cursor='hand2')
        a = tk.Label(t, text=title, bg=C['bg'], fg=C['text'], font=(FONT, 11, 'bold'), anchor='w', cursor='hand2')
        a.pack(fill='x', padx=14, pady=(12, 0))
        b = tk.Label(t, text=text, bg=C['bg'], fg=C['muted'], font=(FONT, 9), anchor='w', justify='left',
                     wraplength=300, cursor='hand2')
        b.pack(fill='x', padx=14, pady=(2, 12))
        for w in (t, a, b):
            w.bind('<Button-1>', lambda _e: self.app.show(name))
            w.bind('<Enter>', lambda _e: [x.config(bg=C['accent_soft']) for x in (t, a, b)])
            w.bind('<Leave>', lambda _e: [x.config(bg=C['bg']) for x in (t, a, b)])
        return t
