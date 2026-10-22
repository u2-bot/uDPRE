"""The uDPRE window: pick the dump once, convert, play. Later starts go straight to Play."""
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, install

TITLE = f'uDPRE {__version__}'


class App:
    def __init__(self, root_dir):
        self.paths = install.Paths(root_dir)
        self.q = queue.Queue()
        self.worker = None
        self.win = tk.Tk()
        self.win.title(TITLE)
        self.win.geometry('640x420')
        self.win.minsize(560, 380)
        self.win.protocol('WM_DELETE_WINDOW', self.on_close)
        pad = {'padx': 12, 'pady': 6}
        self.head = ttk.Label(self.win, text='', font=('Segoe UI', 12, 'bold'))
        self.head.pack(anchor='w', **pad)
        self.info = ttk.Label(self.win, text='', wraplength=600, justify='left')
        self.info.pack(anchor='w', fill='x', **pad)
        row = ttk.Frame(self.win)
        row.pack(fill='x', **pad)
        self.dump_var = tk.StringVar(value=install.load_config(self.paths).get('dump', ''))
        self.dump_entry = ttk.Entry(row, textvariable=self.dump_var)
        self.dump_entry.pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(row, text='Browse...', command=self.pick)
        self.browse.pack(side='left', padx=(8, 0))
        self.stage = ttk.Label(self.win, text='')
        self.stage.pack(anchor='w', **pad)
        self.bar = ttk.Progressbar(self.win, mode='determinate', maximum=100)
        self.bar.pack(fill='x', **pad)
        self.log = tk.Text(self.win, height=8, wrap='word', state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True, **pad)
        btns = ttk.Frame(self.win)
        btns.pack(fill='x', **pad)
        self.go = ttk.Button(btns, text='Convert', command=self.start)
        self.go.pack(side='right')
        self.play_btn = ttk.Button(btns, text='Play', command=self.play)
        self.play_btn.pack(side='right', padx=(0, 8))
        self.refresh()
        self.win.after(100, self.poll)

    def refresh(self):
        done = install.is_installed(self.paths)
        if done:
            self.head.config(text='Ready to play')
            self.info.config(text='Your game data is converted. Press Play (or start Dpr.exe yourself). Convert again only '
                                  'after a uDPRE update asks for it, or to use another dump.')
            self.play_btn.state(['!disabled'])
            self.go.config(text='Convert again')
        else:
            self.head.config(text='Convert your Brilliant Diamond dump')
            self.info.config(text='Pick the folder of your own Pokemon Brilliant Diamond dump with the v1.3.0 update '
                                  'applied (the folder that holds "romfs"). uDPRE converts it into this folder; the dump '
                                  'itself is only read. Needs about 7 GB of free space here.')
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
        except install.DumpError as e:
            messagebox.showerror(TITLE, str(e))
            return
        self.dump_var.set(data)
        for w in (self.go, self.browse, self.play_btn):
            w.state(['disabled'])
        self.dump_entry.state(['disabled'])
        self.head.config(text='Converting...')
        self.worker = threading.Thread(target=self.work, args=(data,), daemon=True)
        self.worker.start()

    def work(self, data):
        try:
            r = install.run(self.paths.root, data, None,
                            lambda stage, done, total: self.q.put(('progress', stage, done, total)),
                            lambda text: self.q.put(('log', text)))
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

