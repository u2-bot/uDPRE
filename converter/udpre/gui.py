"""The uDPRE window: pick the dump once, choose mods, convert, play. Later starts go straight to Play."""
import os
import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__, install, mods as modlib

TITLE = f'uDPRE {__version__}'


class App:
    def __init__(self, root_dir):
        self.paths = install.Paths(root_dir)
        self.q = queue.Queue()
        self.worker = None
        self.win = tk.Tk()
        base = install.release_info(self.paths).get('base_version')
        self.win.title(TITLE + (f' (game base v{base})' if base else ''))
        self.win.geometry('700x700')
        self.win.minsize(600, 660)
        self.win.protocol('WM_DELETE_WINDOW', self.on_close)
        pad = {'padx': 12, 'pady': 6}
        self.head = ttk.Label(self.win, text='', font=('Segoe UI', 12, 'bold'))
        self.head.pack(anchor='w', **pad)
        self.info = ttk.Label(self.win, text='', wraplength=640, justify='left')
        self.info.pack(anchor='w', fill='x', **pad)
        row = ttk.Frame(self.win)
        row.pack(fill='x', **pad)
        cfg = install.load_config(self.paths)
        self.dump_var = tk.StringVar(value=cfg.get('dump', ''))
        self.dump_entry = ttk.Entry(row, textvariable=self.dump_var)
        self.dump_entry.pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(row, text='Browse...', command=self.pick)
        self.browse.pack(side='left', padx=(8, 0))
        self.mods_box = ttk.LabelFrame(self.win, text='Mods (packs in the "mods" folder)')
        self.mods_box.pack(fill='x', **pad)
        # the pack list scrolls once it is taller than MODS_HEIGHT (sub-options open under a ticked pack)
        holder = ttk.Frame(self.mods_box)
        holder.pack(fill='x', padx=8, pady=4)
        self.mod_canvas = tk.Canvas(holder, height=40, highlightthickness=0, borderwidth=0)
        self.mod_scroll = ttk.Scrollbar(holder, orient='vertical', command=self.mod_canvas.yview)
        self.mod_canvas.configure(yscrollcommand=self.mod_scroll.set)
        self.mod_canvas.pack(side='left', fill='x', expand=True)
        self.mod_rows = ttk.Frame(self.mod_canvas)
        self.mod_rows_id = self.mod_canvas.create_window((0, 0), window=self.mod_rows, anchor='nw')
        self.mod_rows.bind('<Configure>', lambda _e: self.fit_mods())
        self.mod_canvas.bind('<Configure>', lambda e: self.mod_canvas.itemconfigure(self.mod_rows_id, width=e.width))
        self.mod_canvas.bind_all('<MouseWheel>', self.wheel)
        mrow = ttk.Frame(self.mods_box)
        mrow.pack(fill='x', padx=8, pady=(0, 6))
        ttk.Button(mrow, text='Open mods folder', command=self.open_mods).pack(side='left')
        ttk.Button(mrow, text='Look again', command=self.load_mods).pack(side='left', padx=(8, 0))
        ttk.Button(mrow, text='Find a mod download...', command=self.locate).pack(side='left', padx=(8, 0))
        self.mod_note = ttk.Label(self.mods_box, text='', foreground='#a33', wraplength=640, justify='left')
        self.mod_note.pack(anchor='w', padx=8, pady=(0, 4))        # its own line: a long reason is never cut
        self.selected = list(cfg.get('mods', []))
        self.options = {k: dict(v) for k, v in (cfg.get('options') or {}).items()}   # picks under the packs' ticks
        self.mod_vars = {}
        self.found = {}
        self.stage = ttk.Label(self.win, text='')
        self.stage.pack(anchor='w', **pad)
        self.bar = ttk.Progressbar(self.win, mode='determinate', maximum=100)
        self.bar.pack(fill='x', **pad)
        btns = ttk.Frame(self.win)
        btns.pack(side='bottom', fill='x', **pad)            # packed before the log: the buttons always stay visible
        self.log = tk.Text(self.win, height=6, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True, **pad)
        base = install.release_info(self.paths).get('base_version')
        ttk.Label(btns, text=f'uDPRE {__version__}' + (f'  ·  game base v{base}' if base else ''),
                  foreground='#666').pack(side='left')
        self.go = ttk.Button(btns, text='Convert', command=self.start)
        self.go.pack(side='right')
        self.play_btn = ttk.Button(btns, text='Play', command=self.play)
        self.play_btn.pack(side='right', padx=(0, 8))
        self.load_mods()
        self.win.after(100, self.poll)
        if self.state == 'refresh' and self.dump_var.get() and self.selected == cfg.get('mods', []) \
                and not self.picks_changed() and not self.status.get('reason', '').startswith('the mod choice'):
            self.win.after(400, self.start)       # after an update: refresh on its own, the player only presses Play

    # --- mods ---------------------------------------------------------------------------------------------------------
    MODS_HEIGHT = 300

    def fit_mods(self):
        self.mod_canvas.configure(scrollregion=self.mod_canvas.bbox('all'))
        h = self.mod_rows.winfo_reqheight()
        self.mod_canvas.configure(height=min(h, self.MODS_HEIGHT))
        if h > self.MODS_HEIGHT:
            self.mod_scroll.pack(side='right', fill='y')
        else:
            self.mod_scroll.pack_forget()
            self.mod_canvas.yview_moveto(0)

    def wheel(self, e):
        w = self.win.winfo_containing(e.x_root, e.y_root)
        while w is not None and w is not self.mod_canvas:
            w = w.master
        if w is self.mod_canvas and self.mod_rows.winfo_reqheight() > self.MODS_HEIGHT:
            self.mod_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')

    def load_mods(self):
        self.found, self.problems = modlib.discover(self.paths.mods, install.load_config(self.paths).get('sources'))
        self.selected = [i for i in self.selected if i in self.found]
        for i, picks in list(self.options.items()):     # a kept pick a newer pack no longer offers = its default again
            m = self.found.get(i)
            if m is not None:
                valid = {o['id']: {c['id'] for c in o['choices']} for o in m.options}
                self.options[i] = {oid: cid for oid, cid in picks.items() if cid in valid.get(oid, ())}
        self.render_mods()

    def render_mods(self):
        for w in self.mod_rows.winfo_children():
            w.destroy()
        self.mod_vars = {}
        if not self.found:
            ttk.Label(self.mod_rows, text='No mod packs. Put a uDPRE mod pack folder into the mods folder, then press '
                                          '"Look again".', wraplength=600).pack(anchor='w')
        for m in sorted(self.found.values(), key=lambda m: (m.order, m.id)):
            v = tk.BooleanVar(value=m.id in self.selected)
            text = f'{m.name}  {m.version}'.strip()
            missing = m.missing_sources()
            if missing:
                text += '   - needs your own ' + ', '.join(m.sources[s].get('name', s) for s in missing)
            row = ttk.Frame(self.mod_rows)
            row.pack(anchor='w', fill='x')
            ttk.Checkbutton(row, text=text, variable=v, command=lambda i=m.id: self.toggle(i)).pack(side='left')
            if m.author or m.url:
                credit = (f'by {m.author}' if m.author else '') + (' · ' if m.author and m.url else '') + \
                         ('mod page' if m.url else '')
                link = ttk.Label(row, text=credit, foreground='#1a5fb4' if m.url else '#666',
                                 cursor='hand2' if m.url else '')
                link.pack(side='left', padx=(10, 0))
                if m.url:
                    link.bind('<Button-1>', lambda _e, u=m.url: webbrowser.open(u))
            self.mod_vars[m.id] = v
            if m.id in self.selected and m.options:
                # the pack's sub-options, under its tick (shown while it is on)
                m.set_choice(self.options.get(m.id))
                for o in m.options:
                    ttk.Label(self.mod_rows, text=o['name'], foreground='#444').pack(anchor='w', padx=(28, 0))
                    ov = tk.StringVar(value=m.choice[o['id']])
                    for c in o['choices']:
                        ttk.Radiobutton(self.mod_rows, text=c['name'], value=c['id'], variable=ov,
                                        command=lambda i=m.id, oid=o['id'], var=ov: self.pick_option(i, oid, var.get())
                                        ).pack(anchor='w', padx=(44, 0))
        for t in self.problems:
            ttk.Label(self.mod_rows, text='Cannot use: ' + t, foreground='#a33', wraplength=600).pack(anchor='w')
        self.refresh()

    def pick_option(self, mod_id, oid, cid):
        self.options.setdefault(mod_id, {})[oid] = cid
        self.refresh()

    def picks_now(self):
        """{pack id: picks with defaults} of the ticked packs that have sub-options - as the window shows them."""
        out = {}
        for i in self.selected:
            m = self.found.get(i)
            if m is not None and m.options:
                m.set_choice(self.options.get(i))
                out[i] = dict(m.choice)
        return out

    def picks_changed(self):
        """the picks differ from the last conversion's (a pick never made = the default, the same either way)."""
        kept = install.load_config(self.paths).get('options') or {}
        for i, now in self.picks_now().items():
            m = self.found[i]
            m.set_choice(kept.get(i))
            if dict(m.choice) != now:
                return True
        return False

    def toggle(self, mod_id):
        on = set(self.selected)
        if self.mod_vars[mod_id].get():
            todo = [mod_id]
            while todo:                                     # what it needs comes on too
                i = todo.pop()
                if i in self.found and i not in on:
                    on.add(i)
                    todo += self.found[i].requires
            for i in list(on):                              # what cannot go with it goes off
                m = self.found.get(i)
                if m and i != mod_id and (i in self.found[mod_id].conflicts or mod_id in m.conflicts):
                    on.discard(i)
        else:
            on.discard(mod_id)
        changed = True
        while changed:                                      # what needs a mod that is off goes off
            changed = False
            for i in list(on):
                if any(r not in on for r in self.found[i].requires):
                    on.discard(i)
                    changed = True
        self.selected = [m.id for m in sorted((self.found[i] for i in on), key=lambda m: (m.order, m.id))]
        self.render_mods()          # a ticked pack's sub-options open under it, an unticked one's close

    def open_mods(self):
        os.makedirs(self.paths.mods, exist_ok=True)
        os.startfile(self.paths.mods)

    def locate(self):
        """A mod download kept outside the mods folder (an emulator's mod folder ...): remembered in the config."""
        needed = [(m, sid) for m in self.found.values() for sid in m.sources]
        if not needed:
            messagebox.showinfo(TITLE, 'None of the mod packs in the mods folder needs a download of its own.')
            return
        d = filedialog.askdirectory(title='Select the folder of your extracted mod download')
        if not d:
            return
        hits = []
        for m, sid in needed:
            data = modlib.find_source(os.path.normpath(d), m, sid)
            if data:
                cfg = install.load_config(self.paths)
                cfg.setdefault('sources', {})[sid] = os.path.normpath(d)
                install.save_config(self.paths, cfg)
                hits.append(f'{m.sources[sid].get("name", sid)}: {data}')
        if hits:
            messagebox.showinfo(TITLE, 'Found:\n' + '\n'.join(dict.fromkeys(hits)))
        else:
            messagebox.showerror(TITLE, 'This folder holds none of the downloads the mod packs need:\n' +
                                 '\n'.join(dict.fromkeys(f'{m.sources[s].get("name", s)} - {m.sources[s].get("where", "")}'
                                                         for m, s in needed)))
        self.load_mods()

    # --- state --------------------------------------------------------------------------------------------------------
    def refresh(self):
        try:
            st = install.status(self.paths)
        except Exception as e:      # a damaged release folder: say so instead of failing to open
            st = {'state': 'convert', 'stale': [], 'reason': f'{type(e).__name__}: {e}', 'mods': []}
        self.status = st
        self.state = st['state']
        mods_changed = self.selected != st.get('mods', []) or self.picks_changed()
        try:
            modlib.choose(self.found, self.selected, self.options)
            self.mod_note.config(text='')
        except modlib.ModError as e:
            self.mod_note.config(text=str(e).splitlines()[0])
        names = ', '.join(self.found[i].name + ''.join(f' ({self.found[i].choice_name(o["id"])})'
                                                         for o in self.found[i].options)
                          for i in self.selected if i in self.found) or 'none'
        if st['state'] == 'ready' and not mods_changed:
            self.head.config(text='Ready to play')
            self.info.config(text=f'Your game data is converted (mods: {names}). Press Play (or start Dpr.exe yourself). '
                                  f'Convert again only to use another dump or other mods.')
            self.play_btn.state(['!disabled'])
            self.go.config(text='Convert again')
        elif st['state'] != 'convert' and mods_changed:
            self.head.config(text='Apply the mod choice')
            self.info.config(text=f'Mods to use: {names}. uDPRE makes again only the files the change touches. '
                                  f'Saves of Luminescent and of the unmodded game are kept apart.')
            self.play_btn.state(['disabled'])
            self.go.config(text='Apply')
        elif st['state'] == 'refresh':
            self.head.config(text='Updating your game data')
            self.info.config(text=f'Changed since the last conversion: {st["reason"]}. uDPRE makes only the files it '
                                  f'needs again, from the dump you used last time. Then press Play.')
            self.play_btn.state(['disabled'])
            self.go.config(text='Update')
        else:
            again = st['reason'].startswith('this uDPRE version')
            self.head.config(text='This update converts your game data again' if again else
                             'Convert your Brilliant Diamond dump')
            self.info.config(text='Pick the folder of your own Pokemon Brilliant Diamond dump with the v1.3.0 update '
                                  'applied (the folder that holds "romfs"). uDPRE converts it into this folder; the dump '
                                  f'itself is only read. Needs about 7 GB of free space here (more with mods). Mods: {names}.')
            self.play_btn.state(['disabled'])
            self.go.config(text='Convert')

    def say(self, text):
        self.log.config(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def pick(self):
        d = filedialog.askdirectory(title='Select your Brilliant Diamond v1.3.0 dump folder')
        if d:
            self.dump_var.set(os.path.normpath(d))

    def start(self):
        if self.worker:
            return
        dump = self.dump_var.get().strip()
        if not dump:
            messagebox.showinfo(TITLE, 'Pick your dump folder first (Browse...).')
            return
        try:
            data = install.find_dump(dump)
            modlib.choose(self.found, self.selected, self.options)
        except install.DumpError as e:
            messagebox.showerror(TITLE, str(e))
            return
        except modlib.ModError as e:
            messagebox.showerror(TITLE, f'This mod choice cannot be used:\n{e}')
            return
        self.dump_var.set(data)
        for w in (self.go, self.browse, self.play_btn):
            w.state(['disabled'])
        self.dump_entry.state(['disabled'])
        self.head.config(text='Converting...')
        self.worker = threading.Thread(target=self.work, args=(data, list(self.selected), self.picks_now()), daemon=True)
        self.worker.start()

    def work(self, data, mods, picks):
        try:
            r = install.run(self.paths.root, data, None,
                            lambda stage, done, total: self.q.put(('progress', stage, done, total)),
                            lambda text: self.q.put(('log', text)), mods=mods, options=picks)
            self.q.put(('done', r))
        except (install.DumpError, install.ConvertError) as e:
            self.q.put(('error', str(e)))
        except Exception as e:      # shown to the player, with the type for a bug report
            self.q.put(('error', f'{type(e).__name__}: {e}'))

    def poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == 'progress':
                    _, stage, done, total = m
                    self.stage.config(text=f'{stage}: {done:,} / {total:,}')
                    self.bar['value'] = 100 * done / max(total, 1)
                elif m[0] == 'log':
                    self.say(m[1])
                elif m[0] == 'done':
                    self.worker = None
                    self.say(f'Finished in {m[1]["seconds"]} s.')
                    self.stage.config(text='Done')
                    self.dump_entry.state(['!disabled'])
                    for w in (self.go, self.browse):
                        w.state(['!disabled'])
                    self.refresh()
                elif m[0] == 'error':
                    self.worker = None
                    self.say('PROBLEM: ' + m[1])
                    self.dump_entry.state(['!disabled'])
                    for w in (self.go, self.browse):
                        w.state(['!disabled'])
                    self.refresh()
                    messagebox.showerror(TITLE, m[1])
        except queue.Empty:
            pass
        self.win.after(100, self.poll)

    def play(self):
        exe = os.path.join(self.paths.root, 'Dpr.exe')
        if not os.path.isfile(exe):
            messagebox.showerror(TITLE, f'Dpr.exe is missing from {self.paths.root}.')
            return
        subprocess.Popen([exe], cwd=self.paths.root)
        self.win.destroy()

    def on_close(self):
        if self.worker and not messagebox.askyesno(TITLE, 'Conversion is running. Stop and close? (Starting again later '
                                                          'continues where it stopped.)'):
            return
        os._exit(0) if self.worker else self.win.destroy()


def main(root_dir):
    App(root_dir).win.mainloop()
    return 0
