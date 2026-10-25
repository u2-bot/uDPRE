"""The Nuzlocke dialog of the uDPRE window: presets, every rule, the run of the newest save, the rules a game cannot check."""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import nuzlocke as nz


class NuzlockeDialog:
    def __init__(self, parent, root_dir, title, on_change=None):
        self.root = root_dir
        self.title = title
        self.on_change = on_change
        self.win = tk.Toplevel(parent)
        self.win.title('Nuzlocke (Beta) - ' + title)
        self.win.geometry('760x720')
        self.win.minsize(640, 520)
        self.win.transient(parent)
        self.vars = {}
        self.values = nz.read(root_dir)

        top = ttk.Frame(self.win)
        top.pack(fill='x', padx=12, pady=(10, 4))
        ttk.Label(top, text='Nuzlocke', font=('Segoe UI', 12, 'bold')).pack(side='left')
        link = ttk.Label(top, text='The rules (nuzlockeuniversity.ca)', foreground='#06c', cursor='hand2')
        link.pack(side='right')
        link.bind('<Button-1>', lambda _e: webbrowser.open(nz.RULES_URL))
        sup = nz.player_supports(root_dir)
        note = ('The game enforces every rule below. Changes take effect the next time the game starts.' if sup else
                'The game in this folder has no Nuzlocke mode yet: convert once (uDPRE 0.4.0 or newer; with Luminescent '
                'or Dechibified on, their packs 1.2.5 or newer), then the rules below apply.' if sup is False else
                'Convert your dump first; the rules apply to the converted game.')
        ttk.Label(self.win, text=note, wraplength=720, justify='left',
                  foreground='#333' if sup else '#a33').pack(anchor='w', padx=12)
        prow = ttk.Frame(self.win)
        prow.pack(fill='x', padx=12, pady=6)
        ttk.Label(prow, text='Presets:').pack(side='left')
        for name in ('nuzlocke', 'hardcore', 'off'):
            ttk.Button(prow, text=nz.PRESET_NAMES[name], command=lambda n=name: self.apply_preset(n)).pack(side='left', padx=(8, 0))
        self.preset_label = ttk.Label(prow, text='', foreground='#555')
        self.preset_label.pack(side='left', padx=(12, 0))

        book = ttk.Notebook(self.win)
        book.pack(fill='both', expand=True, padx=12, pady=4)
        rules = ttk.Frame(book)
        run = ttk.Frame(book)
        honor = ttk.Frame(book)
        book.add(rules, text='Rules')
        book.add(run, text='Your run')
        book.add(honor, text='Not checked by the game')
        self.build_rules(rules)
        self.build_run(run)
        self.build_honor(honor)

        btns = ttk.Frame(self.win)
        btns.pack(fill='x', padx=12, pady=10)
        self.saved = ttk.Label(btns, text='', foreground='#555')
        self.saved.pack(side='left')
        ttk.Button(btns, text='Close', command=self.win.destroy).pack(side='right')
        ttk.Button(btns, text='Save', command=self.save).pack(side='right', padx=(0, 8))
        self.load_values(self.values)

    # --- the rules tab ---------------------------------------------------------------------------------------------
    def build_rules(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(canvas)
        iid = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(iid, width=e.width))
        canvas.bind('<Enter>', lambda _e: canvas.bind_all('<MouseWheel>', lambda ev: canvas.yview_scroll(-ev.delta // 120, 'units')))
        canvas.bind('<Leave>', lambda _e: canvas.unbind_all('<MouseWheel>'))
        for group in nz.GROUPS:
            box = ttk.LabelFrame(inner, text=group)
            box.pack(fill='x', padx=4, pady=4)
            box.columnconfigure(1, weight=1)
            r = 0
            for key, label, kind, choices, g, rule in nz.SETTINGS:
                if g != group:
                    continue
                self.add_row(box, r, key, label, kind, choices, rule)
                r += 1

    def add_row(self, box, r, key, label, kind, choices, rule):
        tail = f'  ({rule})' if rule else ''
        if kind == 'bool':
            v = tk.IntVar()
            ttk.Checkbutton(box, text=label + tail, variable=v, command=self.changed).grid(row=r, column=0, columnspan=2,
                                                                                         sticky='w', padx=8, pady=2)
        elif kind == 'choice':
            ttk.Label(box, text=label + tail).grid(row=r, column=0, sticky='w', padx=8, pady=2)
            v = tk.StringVar()
            names = [n for _, n in choices]
            cb = ttk.Combobox(box, textvariable=v, values=names, state='readonly', width=52)
            cb.grid(row=r, column=1, sticky='we', padx=8, pady=2)
            cb.bind('<<ComboboxSelected>>', lambda _e: self.changed())
        elif kind == 'int':
            ttk.Label(box, text=label + tail).grid(row=r, column=0, sticky='w', padx=8, pady=2)
            v = tk.StringVar()
            lo, hi = nz.RANGES.get(key, (0, 999))
            sp = ttk.Spinbox(box, from_=lo, to=hi, textvariable=v, width=6, command=self.changed)
            sp.grid(row=r, column=1, sticky='w', padx=8, pady=2)
            sp.bind('<KeyRelease>', lambda _e: self.changed())
        elif kind == 'list':
            ttk.Label(box, text=label + tail).grid(row=r, column=0, sticky='w', padx=8, pady=2)
            v = tk.StringVar()
            cell = ttk.Frame(box)
            cell.grid(row=r, column=1, sticky='we', padx=8, pady=2)
            e = ttk.Entry(cell, textvariable=v)
            e.pack(side='left', fill='x', expand=True)
            e.bind('<KeyRelease>', lambda _e: self.changed())
            if key == 'banned_moves':
                ttk.Button(cell, text='Add setup moves', command=lambda: self.add_numbers('banned_moves', nz.SETUP_MOVES)).pack(
                    side='left', padx=(6, 0))
        else:   # types / colors / gens: tick boxes
            ttk.Label(box, text=label + tail).grid(row=r, column=0, sticky='nw', padx=8, pady=2)
            names = nz.TYPES if kind == 'types' else nz.COLORS if kind == 'colors' else [f'Gen {i}' for i in range(1, 10)]
            base = 1 if kind == 'gens' else 0
            cell = ttk.Frame(box)
            cell.grid(row=r, column=1, sticky='we', padx=8, pady=2)
            ticks = []
            for i, n in enumerate(names):
                tv = tk.IntVar()
                ttk.Checkbutton(cell, text=n, variable=tv, command=self.changed).grid(row=i // 6, column=i % 6, sticky='w')
                ticks.append((i + base, tv))
            v = ticks
        self.vars[key] = v

    def add_numbers(self, key, numbers):
        have = [n for n in self.vars[key].get().replace(';', ',').split(',') if n.strip()]
        for n in numbers:
            if str(n) not in [h.strip() for h in have]:
                have.append(str(n))
        self.vars[key].set(','.join(h.strip() for h in have))
        self.changed()

    def load_values(self, values):
        for key, label, kind, choices, g, rule in nz.SETTINGS:
            v = self.vars[key]
            val = values.get(key, nz.default(key))
            if kind == 'bool':
                v.set(int(val))
            elif kind == 'choice':
                v.set(dict(choices).get(str(val), choices[0][1]))
            elif kind in ('int', 'list'):
                v.set(str(val))
            else:
                chosen = {int(x) for x in str(val).split(',') if x.strip().isdigit()}
                for num, tv in v:
                    tv.set(1 if num in chosen else 0)
        self.changed(dirty=False)

    def collect(self):
        out = {}
        for key, label, kind, choices, g, rule in nz.SETTINGS:
            v = self.vars[key]
            if kind == 'bool':
                out[key] = int(v.get())
            elif kind == 'choice':
                back = {n: c for c, n in choices}
                out[key] = back.get(v.get(), choices[0][0])
            elif kind in ('int', 'list'):
                out[key] = v.get().strip() or ('0' if kind == 'int' else '')
            else:
                out[key] = ','.join(str(num) for num, tv in v if tv.get())
        return out

    def changed(self, dirty=True):
        try:
            vals = {k: nz.normalize(k, v) for k, v in self.collect().items()}
            self.preset_label.config(text='Now: ' + nz.summary(vals))
        except ValueError as e:
            self.preset_label.config(text=str(e))
        if dirty:
            self.saved.config(text='Not saved yet')

    def apply_preset(self, name):
        self.load_values(nz.PRESETS[name])
        self.saved.config(text='Not saved yet')

    def save(self):
        try:
            vals = nz.write(self.root, self.collect())
        except ValueError as e:
            messagebox.showerror(self.title, f'A setting needs a fix:\n{e}', parent=self.win)
            return
        except OSError as e:
            messagebox.showerror(self.title, f'The settings could not be written:\n{e}', parent=self.win)
            return
        self.saved.config(text='Saved: ' + nz.summary(vals) + ' - the game uses it the next time it starts')
        if self.on_change:
            self.on_change()

    # --- the run tab -----------------------------------------------------------------------------------------------
    def build_run(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=6, pady=6)
        ttk.Label(row, text='The newest save of this game (read from the run file the game keeps next to it).',
                  foreground='#555').pack(side='left')
        ttk.Button(row, text='Refresh', command=self.show_run).pack(side='right')
        self.run_text = tk.Text(parent, wrap='word', font=('Consolas', 9), state='disabled')
        self.run_text.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        self.show_run()

    def show_run(self):
        run, folder = nz.load_run(self.root)
        lines = nz.run_text(run)
        if folder:
            lines += ['', f'Save folder: {folder}']
        self.run_text.config(state='normal')
        self.run_text.delete('1.0', 'end')
        self.run_text.insert('end', '\n'.join(lines))
        self.run_text.config(state='disabled')

    def build_honor(self, parent):
        ttk.Label(parent, text='These rules are a promise you keep yourself - no game data says what they mean:',
                  wraplength=700, justify='left').pack(anchor='w', padx=8, pady=8)
        for rule, text in nz.HONOR:
            ttk.Label(parent, text=f'{rule}: {text}', wraplength=700, justify='left').pack(anchor='w', padx=16, pady=2)
        hc = ttk.Label(parent, text='The Hardcore variant (nuzlockeuniversity.ca)', foreground='#06c', cursor='hand2')
        hc.pack(anchor='w', padx=8, pady=(16, 0))
        hc.bind('<Button-1>', lambda _e: webbrowser.open(nz.HARDCORE_URL))
