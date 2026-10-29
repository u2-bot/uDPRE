"""The Get mods dialog of the uDPRE window: every pack of the online catalogue - get, update or remove it."""
import tkinter as tk
from tkinter import messagebox, ttk

from . import winfit

STATE_TEXT = {'installed': 'installed', 'update': 'update ready', 'available': 'not installed',
              'managed': 'installed (linked folder - updated where it lives)'}


class GetModsDialog:
    def __init__(self, app):
        from . import online
        self.app = app
        self.win = tk.Toplevel(app.win)
        self.win.title('Get mods - ' + app.win.title())
        winfit.fit(self.win, 720, 560)
        self.win.transient(app.win)
        top = ttk.Frame(self.win)
        top.pack(fill='x', padx=12, pady=(10, 4))
        ttk.Label(top, text='Mod packs', font=('Segoe UI', 12, 'bold')).pack(side='left')
        self.note = ttk.Label(self.win, text='Reading the mod catalogue...', foreground='#555', wraplength=690,
                              justify='left')
        self.note.pack(anchor='w', padx=12)
        cols = ('pack', 'state', 'version', 'size')
        self.tree = ttk.Treeview(self.win, columns=cols, show='headings', selectmode='extended', height=16)
        self.tree.heading('pack', text='Pack', anchor='w')
        self.tree.heading('state', text='State')
        self.tree.heading('version', text='Version')
        self.tree.heading('size', text='Download')
        self.tree.column('pack', width=300)
        self.tree.column('state', width=200)
        self.tree.column('version', width=90)
        self.tree.column('size', width=90, anchor='e')
        self.tree.pack(fill='both', expand=True, padx=12, pady=6)
        self.tree.bind('<<TreeviewSelect>>', lambda _e: self.show_selected())
        self.desc = ttk.Label(self.win, text='', wraplength=690, justify='left')
        self.desc.pack(anchor='w', padx=12)
        btns = ttk.Frame(self.win)
        btns.pack(fill='x', padx=12, pady=10)
        ttk.Button(btns, text='Get / update selected', command=self.get_selected).pack(side='left')
        ttk.Button(btns, text='Get all', command=self.get_all).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Remove selected', command=self.remove_selected).pack(side='left', padx=(8, 0))
        ttk.Button(btns, text='Close', command=self.win.destroy).pack(side='right')
        self.items = {}
        self.index = None
        if not online.relay_url(app.paths):
            self.note.config(text='This uDPRE has no download address (udpre/release.json "relay").')
            return
        if app.worker:
            self.note.config(text='uDPRE is busy (converting or downloading) - open Get mods again when it has finished.')
            return
        app.online_check(auto=False, then=self.fill)

    def fill(self, index, pl):
        from . import online
        if not self.win.winfo_exists():
            return
        self.index = index
        self.tree.delete(*self.tree.get_children())
        self.items = {}
        for it in sorted(pl['packs'], key=lambda i: (i['entry'].get('order') or 0, i['entry']['name'])):
            e = it['entry']
            size = it['bytes'] if it['state'] in ('update', 'available') else 0
            iid = self.tree.insert('', 'end', values=(e['name'], STATE_TEXT.get(it['state'], it['state']),
                                                      e.get('version', ''), online.size_text(size) if size else ''))
            self.items[iid] = it
        src = [s for s in pl['sources'] if s['state'] == 'missing']
        extra = (' Packs that need another download (' + ', '.join(s['entry']['name'] for s in src) + ') get it too.') \
            if src else ''
        self.note.config(text='Pick packs and press Get. New packs appear in the Mods list - tick the ones to play with. '
                              'Every file is checked against the signed catalogue.' + extra)

    def show_selected(self):
        sel = self.tree.selection()
        if len(sel) == 1:
            e = self.items[sel[0]]['entry']
            by = f' - by {e["author"]}' if e.get('author') else ''
            self.desc.config(text=(e.get('description') or '') + by)

    def _run(self, items):
        items = [i for i in items if i['state'] in ('update', 'available')]
        if not items:
            messagebox.showinfo('Get mods', 'Those packs are installed and up to date.', parent=self.win)
            return
        from . import online
        if not messagebox.askyesno('Get mods', f'Download {online.size_text(sum(i["bytes"] for i in items))} for: ' +
                                   ', '.join(i['entry']['name'] for i in items) + '?', parent=self.win):
            return
        self.app.online_apply(self.index, items)
        self.win.destroy()

    def get_selected(self):
        self._run([self.items[i] for i in self.tree.selection()])

    def get_all(self):
        self._run(list(self.items.values()))

    def remove_selected(self):
        from . import online
        sel = [self.items[i] for i in self.tree.selection() if self.items[i]['state'] in ('installed', 'update')]
        if not sel or self.app.worker:
            return
        if not messagebox.askyesno('Get mods', 'Remove ' + ', '.join(i['entry']['name'] for i in sel) +
                                   '? (Each is kept in udpre\\state\\online\\previous until the next removal or update.)',
                                   parent=self.win):
            return
        for it in sel:
            if it['entry']['id'] in self.app.selected:
                self.app.selected.remove(it['entry']['id'])
            online.remove_pack(self.app.paths, it['entry']['id'], it['path'])
        self.app.load_mods()
        self.app.refresh()
        self.app.online_check(auto=False, then=self.fill)
