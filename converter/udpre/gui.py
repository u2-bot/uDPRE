"""The uDPRE window: pick the dump once, choose mods, convert, play. Later starts go straight to Play."""
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, install, mods as modlib

TITLE = f'uDPRE {__version__}'


class App:
    def __init__(self, root_dir):
        self.paths = install.Paths(root_dir)
        self.q = queue.Queue()
        self.worker = None
        self.win = tk.Tk()
        self.win.title(TITLE)
        self.win.geometry('680x600')
        self.win.minsize(580, 520)
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
        self.mod_rows = ttk.Frame(self.mods_box)
        self.mod_rows.pack(fill='x', padx=8, pady=4)
        mrow = ttk.Frame(self.mods_box)
        mrow.pack(fill='x', padx=8, pady=(0, 6))
        ttk.Button(mrow, text='Open mods folder', command=self.open_mods).pack(side='left')
        ttk.Button(mrow, text='Look again', command=self.load_mods).pack(side='left', padx=(8, 0))
        self.mod_note = ttk.Label(mrow, text='', foreground='#a33')
        self.mod_note.pack(side='left', padx=(12, 0))
        self.selected = list(cfg.get('mods', []))
        self.mod_vars = {}
        self.found = {}
        self.stage = ttk.Label(self.win, text='')
        self.stage.pack(anchor='w', **pad)
        self.bar = ttk.Progressbar(self.win, mode='determinate', maximum=100)
        self.bar.pack(fill='x', **pad)
        self.log = tk.Text(self.win, height=7, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True, **pad)
        btns = ttk.Frame(self.win)
        btns.pack(fill='x', **pad)
        self.go = ttk.Button(btns, text='Convert', command=self.start)
        self.go.pack(side='right')
        self.play_btn = ttk.Button(btns, text='Play', command=self.play)
        self.play_btn.pack(side='right', padx=(0, 8))
        self.load_mods()
        self.win.after(100, self.poll)
        if self.state == 'refresh' and self.dump_var.get() and self.selected == cfg.get('mods', []) \
                and not self.status.get('reason', '').startswith('the mod choice'):
            self.win.after(400, self.start)       # after an update: refresh on its own, the player only presses Play

    # --- mods ---------------------------------------------------------------------------------------------------------
    def load_mods(self):
        for w in self.mod_rows.winfo_children():
            w.destroy()
        self.found, problems = modlib.discover(self.paths.mods)
        self.selected = [i for i in self.selected if i in self.found]
        self.mod_vars = {}
        if not self.found:
            ttk.Label(self.mod_rows, text='No mod packs. Put a uDPRE mod pack folder into the mods folder, then press '
                                          '"Look again".', wraplength=600).pack(anchor='w')
        for m in sorted(self.found.values(), key=lambda m: (m.order, m.id)):
            v = tk.BooleanVar(value=m.id in self.selected)
            text = f'{m.name}  {m.version}'.strip()
            ttk.Checkbutton(self.mod_rows, text=text, variable=v, command=lambda i=m.id: self.toggle(i)).pack(anchor='w')
            self.mod_vars[m.id] = v
        for t in problems:
            ttk.Label(self.mod_rows, text='Cannot use: ' + t, foreground='#a33', wraplength=600).pack(anchor='w')
        self.refresh()

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
        for i, v in self.mod_vars.items():
            v.set(i in on)
        self.refresh()

    def open_mods(self):
        os.makedirs(self.paths.mods, exist_ok=True)
        os.startfile(self.paths.mods)

    # --- state --------------------------------------------------------------------------------------------------------
    def refresh(self):
        try:
            st = install.status(self.paths)
        except Exception as e:      # a damaged release folder: say so instead of failing to open
            st = {'state': 'convert', 'stale': [], 'reason': f'{type(e).__name__}: {e}', 'mods': []}
        self.status = st
        self.state = st['state']
        mods_changed = self.selected != st.get('mods', [])
        try:
            modlib.choose(self.found, self.selected)
            self.mod_note.config(text='')
        except modlib.ModError as e:
            self.mod_note.config(text=str(e).splitlines()[0])
        names = ', '.join(self.found[i].name for i in self.selected if i in self.found) or 'none'
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
            modlib.choose(self.found, self.selected)
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
        self.worker = threading.Thread(target=self.work, args=(data, list(self.selected)), daemon=True)
        self.worker.start()

    def work(self, data, mods):
        try:
            r = install.run(self.paths.root, data, None,
                            lambda stage, done, total: self.q.put(('progress', stage, done, total)),
                            lambda text: self.q.put(('log', text)), mods=mods)
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
