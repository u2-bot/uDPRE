"""The uDPRE window: pick the dump once, choose mods, convert, play. Later starts go straight to Play."""
import os
import queue
import subprocess
import sys
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
        self.win.geometry('700x880')
        self.win.minsize(600, 800)
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
        ttk.Button(mrow, text='Get mods...', command=self.open_get_mods).pack(side='left', padx=(8, 0))
        orow = ttk.Frame(self.mods_box)
        orow.pack(fill='x', padx=8, pady=(0, 4))
        self.online_auto = tk.BooleanVar(value=bool(install.load_config(self.paths).get('online_auto', True)))
        ttk.Checkbutton(orow, text='Update mods automatically', variable=self.online_auto,
                        command=self.toggle_online_auto).pack(side='left')
        self.online_note = ttk.Label(orow, text='', foreground='#555', wraplength=440, justify='left')
        self.online_note.pack(side='left', padx=(12, 0))
        self.online_plan = None
        self.mod_note = ttk.Label(self.mods_box, text='', foreground='#a33', wraplength=640, justify='left')
        self.mod_note.pack(anchor='w', padx=8, pady=(0, 4))        # its own line: a long reason is never cut
        self.mod_note_full = ''                                     # the whole text (what to do), shown on a click
        self.mod_note.bind('<Button-1>', lambda _e: self.mod_note_full and messagebox.showinfo(TITLE, self.mod_note_full))
        self.merge_row = ttk.Frame(self.mods_box)
        self.merge_row.pack(fill='x', padx=8, pady=(0, 4))
        self.merge_text = ttk.Label(self.merge_row, text='', foreground='#555', wraplength=520, justify='left')
        self.merge_text.pack(side='left')
        self.merge_btn = ttk.Button(self.merge_row, text='Merge conflicts...', command=self.show_merge)
        self.edits_box = ttk.LabelFrame(self.win, text='Your edits: Editor & Randomizer (Beta)')
        self.edits_box.pack(fill='x', **pad)
        erow = ttk.Frame(self.edits_box)
        erow.pack(fill='x', padx=8, pady=6)
        self.edits_var = tk.BooleanVar(value=bool(cfg.get('edits_on')))
        ttk.Checkbutton(erow, text='Use my edits in the game', variable=self.edits_var,
                        command=self.toggle_edits).pack(side='left')
        ttk.Button(erow, text='Editor & Randomizer...', command=self.open_editor).pack(side='left', padx=(12, 0))
        self.edits_note = ttk.Label(erow, text='', foreground='#555')
        self.edits_note.pack(side='left', padx=(12, 0))
        self.nz_box = ttk.LabelFrame(self.win, text='Challenge: Nuzlocke (Beta)')
        self.nz_box.pack(fill='x', **pad)
        nrow = ttk.Frame(self.nz_box)
        nrow.pack(fill='x', padx=8, pady=6)
        ttk.Button(nrow, text='Nuzlocke...', command=self.open_nuzlocke).pack(side='left')
        self.nz_note = ttk.Label(nrow, text='', foreground='#555')
        self.nz_note.pack(side='left', padx=(12, 0))
        self.nz_refresh()
        self.selected = list(cfg.get('mods', []))
        self.options = {k: dict(v) for k, v in (cfg.get('options') or {}).items()}   # picks under the packs' ticks
        self.opts_open = set()      # (pack id, option id) whose choices are listed; the others show one line
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
        reason = self.status.get('reason', '')
        self.auto_start = self.state == 'refresh' and self.dump_var.get() and self.selected == cfg.get('mods', []) \
            and not self.picks_changed() and not reason.startswith('the mod choice') \
            and 'your edits' not in reason and 'merge choices' not in reason
        from . import online
        if online.relay_url(self.paths) and self.online_auto.get():
            self.win.after(300, lambda: self.online_check(auto=True))   # updates first, then the refresh below
        elif self.auto_start:
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
                text += '   - needs the original mod download'
            row = ttk.Frame(self.mod_rows)
            row.pack(anchor='w', fill='x')
            ttk.Checkbutton(row, text=text, variable=v, command=lambda i=m.id: self.toggle(i)).pack(side='left')
            if missing:
                from . import advice
                help_text = '\n\n'.join(advice.source_missing(m, s, ', '.join(m.near_misses) or None) for s in missing)
                hl = ttk.Label(row, text='What to do', foreground='#1a5fb4', cursor='hand2')
                hl.pack(side='left', padx=(10, 0))
                hl.bind('<Button-1>', lambda _e, t=help_text: messagebox.showinfo(TITLE, t))
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
                # the pack's sub-options, under its tick (while it is on): one line with the current choice - a click
                # lists the choices, picking one folds them away again
                m.set_choice(self.options.get(m.id))
                for o in m.options:
                    key = (m.id, o['id'])
                    is_open = key in self.opts_open
                    cur = next((c['name'] for c in o['choices'] if c['id'] == m.choice[o['id']]), m.choice[o['id']])
                    head = ttk.Label(self.mod_rows, text=f'{"▼" if is_open else "▶"}  {o["name"]}: {cur}',
                                     foreground='#444', cursor='hand2')
                    head.pack(anchor='w', padx=(28, 0))
                    head.bind('<Button-1>', lambda _e, k=key: self.fold_option(k))
                    if not is_open:
                        continue
                    ov = tk.StringVar(value=m.choice[o['id']])
                    for c in o['choices']:
                        ttk.Radiobutton(self.mod_rows, text=c['name'], value=c['id'], variable=ov,
                                        command=lambda i=m.id, oid=o['id'], var=ov: self.pick_option(i, oid, var.get())
                                        ).pack(anchor='w', padx=(44, 0))
        for t in self.problems:
            # the problem line in the list; its steps (what to do) one click away
            first, _, rest = t.partition('\n\n')
            row = ttk.Frame(self.mod_rows)
            row.pack(anchor='w', fill='x')
            ttk.Label(row, text='Cannot use: ' + first, foreground='#a33', wraplength=520, justify='left').pack(
                side='left', anchor='w')
            if rest:
                link = ttk.Label(row, text='What to do', foreground='#1a5fb4', cursor='hand2')
                link.pack(side='left', anchor='n', padx=(8, 0))
                link.bind('<Button-1>', lambda _e, t=t: messagebox.showinfo(TITLE, t))
        self.refresh()

    def pick_option(self, mod_id, oid, cid):
        self.options.setdefault(mod_id, {})[oid] = cid
        self.opts_open.discard((mod_id, oid))       # picked: back to one line
        self.render_mods()

    def fold_option(self, key):
        self.opts_open ^= {key}
        self.render_mods()

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
        if mod_id in on:            # just ticked: its choices are listed once, so the player sees them
            self.opts_open |= {(mod_id, o['id']) for o in self.found[mod_id].options}
        self.render_mods()          # a ticked pack's sub-options open under it, an unticked one's close

    def open_mods(self):
        os.makedirs(self.paths.mods, exist_ok=True)
        os.startfile(self.paths.mods)

    # --- edits and merging ----------------------------------------------------------------------------------------------
    def toggle_edits(self):
        cfg = install.load_config(self.paths)
        cfg['edits_on'] = bool(self.edits_var.get())
        install.save_config(self.paths, cfg)
        self.refresh()

    def edits_count(self):
        from .edit import build as editbuild
        from .edit.project import Project
        try:
            return len(Project(editbuild.project_path(self.paths.root)).ops)
        except Exception:
            return 0

    def open_editor(self):
        if self.worker:
            return
        if not install.load_config(self.paths).get('dump'):
            messagebox.showinfo(TITLE, 'Convert your dump once first; the editor works on the converted game\'s files.')
            return
        try:
            modlib.choose(self.found, self.selected, self.options)
        except modlib.ModError as e:
            messagebox.showerror(TITLE, f'This mod choice cannot be used:\n{e}')
            return
        from .edit.ui.window import EditorApp
        try:
            EditorApp(self.paths.root, self.win, list(self.selected), self.picks_now(), on_change=self.refresh)
        except Exception as e:      # shown already by the editor; keep the main window usable
            self.say(f'editor: {type(e).__name__}: {e}')

    # --- Nuzlocke ------------------------------------------------------------------------------------------------------
    def nz_refresh(self):
        from . import nuzlocke as nz
        vals = nz.read(self.paths.root)
        text = 'Nuzlocke: ' + nz.summary(vals)
        if int(vals.get('enabled') or 0) and nz.player_supports(self.paths.root) is False:
            text += ' - the game here has no Nuzlocke mode yet (convert first)'
        self.nz_note.config(text=text)

    def open_nuzlocke(self):
        from .nuzlocke_ui import NuzlockeDialog
        NuzlockeDialog(self.win, self.paths.root, TITLE, on_change=self.nz_refresh)

    def show_merge(self):
        import json
        rep_path = os.path.join(self.paths.state, 'merged', 'report.json')
        try:
            with open(rep_path, encoding='utf-8') as f:
                rep = json.load(f)
        except (OSError, ValueError):
            rep = {}
        top = tk.Toplevel(self.win)
        top.title('Console mods merged with the other mods')
        top.geometry('980x560')
        ttk.Label(top, text='Files that console mods share with other mods are merged object by object. Where both '
                            'changed the same value, the upper mod wins; double-click a row to keep the lower mod\'s '
                            'object instead (press Apply afterwards).', wraplength=940, justify='left').pack(
            anchor='w', padx=8, pady=6)
        tree = ttk.Treeview(top, columns=('file', 'obj', 'field', 'low', 'up', 'win'), show='headings')
        for c, t, w in (('file', 'File', 220), ('obj', 'Object', 180), ('field', 'Field', 140), ('low', 'Lower mod', 150),
                        ('up', 'Upper mod', 150), ('win', 'Kept', 70)):
            tree.heading(c, text=t)
            tree.column(c, width=w)
        tree.pack(fill='both', expand=True, padx=8)
        cfg = install.load_config(self.paths)
        picks = cfg.get('merge_choices') or {}
        rows = {}
        for rel, r in sorted(rep.items()):
            for k, (obj, field, low, up, win) in enumerate(r.get('conflicts', [])[:400]):
                win = picks.get(rel, {}).get(obj, win)
                iid = tree.insert('', 'end', values=(rel.split('/')[-1], obj, field, low, up, 'lower' if win == 'below'
                                                     else 'upper'))
                rows[iid] = (rel, obj)

        def flip(_e):
            sel = tree.focus()
            if sel not in rows:
                return
            rel, obj = rows[sel]
            c = install.load_config(self.paths)
            mc = c.setdefault('merge_choices', {}).setdefault(rel, {})
            mc[obj] = 'above' if mc.get(obj) == 'below' else 'below'
            install.save_config(self.paths, c)
            for iid, (r2, o2) in rows.items():
                if r2 == rel and o2 == obj:
                    v = list(tree.item(iid, 'values'))
                    v[5] = 'lower' if mc[obj] == 'below' else 'upper'
                    tree.item(iid, values=v)
            self.refresh()
        tree.bind('<Double-1>', flip)

    def merge_summary(self):
        import json
        try:
            with open(os.path.join(self.paths.state, 'merged', 'report.json'), encoding='utf-8') as f:
                rep = json.load(f)
        except (OSError, ValueError):
            rep = {}
        raw_on = any(i.startswith('raw:') for i in self.selected)
        if not rep or not raw_on:
            self.merge_text.config(text='')
            self.merge_btn.pack_forget()
            return
        n = sum(len(r.get('conflicts', [])) for r in rep.values())
        self.merge_text.config(text=f'{len(rep)} files your console mods share with other mods are merged '
                                    f'({n} values both changed).')
        self.merge_btn.pack(side='left', padx=(8, 0))

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
            from . import advice
            messagebox.showerror(TITLE, advice.text(
                f'{os.path.normpath(d)} holds none of the downloads your mod packs need',
                [f'The {m.name} pack needs exactly {m.sources[s].get("name", s)} (the original mod, {advice.get_from(m)})'
                 .replace(', )', ')') for m, s in needed] +
                ['Pick the folder you extracted that download to (with 7-Zip) - the one that has "romfs" inside',
                 'If it is another version of the mod or the Shining Pearl one, get the version named above']))
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
        n_edits = self.edits_count()
        self.edits_note.config(text=f'{n_edits} change(s) in your edits' + ('' if self.edits_var.get() else ' (not used)'))
        edits_changed = 'your edits' in st.get('reason', '') or 'merge choices' in st.get('reason', '')
        mods_changed = mods_changed or edits_changed
        self.merge_summary()
        try:
            modlib.choose(self.found, self.selected, self.options)
            self.mod_note.config(text='', cursor='')
            self.mod_note_full = ''
        except modlib.ModError as e:
            self.mod_note_full = str(e)
            more = len(str(e).splitlines()) > 1
            self.mod_note.config(text=str(e).splitlines()[0] + ('   (click: what to do)' if more else ''),
                                 cursor='hand2')
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
            self.head.config(text='Apply your changes' if edits_changed else 'Apply the mod choice')
            self.info.config(text=f'Mods to use: {names}.' + (' Your edits changed.' if edits_changed else '') +
                                  ' uDPRE makes again only the files the change touches. '
                                  'Saves of Luminescent and of the unmodded game are kept apart.')
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
            self.say('uDPRE is still busy (checking for, or downloading, mod updates) - press again when it has finished.')
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
        self.worker = threading.Thread(target=self.work, args=(data, list(self.selected), self.picks_now(),
                                                              bool(self.edits_var.get())), daemon=True)
        self.worker.start()

    def work(self, data, mods, picks, edits):
        try:
            r = install.run(self.paths.root, data, None,
                            lambda stage, done, total: self.q.put(('progress', stage, done, total)),
                            lambda text: self.q.put(('log', text)), mods=mods, options=picks, edits=edits)
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
                    if stage.startswith('Downloading'):
                        self.stage.config(text=f'{stage}: {done / 2**20:.1f} / {total / 2**20:.1f} MiB')
                    else:
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
                elif m[0] == 'online_plan':
                    self.worker = None
                    self._online_after((m[1], m[2]), m[3], m[4])
                elif m[0] == 'online_error':
                    self.worker = None
                    self.online_note.config(text='Mod updates could not be checked: ' + m[1].splitlines()[0][:160])
                    if self.auto_start:
                        self.auto_start = False
                        self.start()
                elif m[0] == 'online_done':
                    self.stage.config(text='Mods updated')
                    self.load_mods()
                    self.online_idle()
                    if m[1]:
                        self.say('Installed: ' + ', '.join(m[1]))
                    self.online_note.config(text='Mods are up to date')
                    if (self.auto_start or any(i in self.selected for i in m[1])) and self.dump_var.get() \
                            and self.state != 'convert':
                        self.auto_start = False
                        self.start()                   # the updated packs' files are made again at once
                elif m[0] == 'online_failed':
                    self.say('PROBLEM (mod update): ' + m[1])
                    self.online_note.config(text='A mod update failed - see the log; your mods are as they were')
                    self.online_idle()
                    if self.auto_start:
                        self.auto_start = False
                        self.start()
                elif m[0] == 'online_restart':
                    from . import online
                    self.say('Restarting uDPRE to finish its update...')
                    online.run_self_update(m[1])
                    os._exit(0)
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
            from . import advice
            messagebox.showerror(TITLE, advice.text(f'The game (Dpr.exe) is missing from {self.paths.root}',
                                                    [advice.unzip_udpre_again()]))
            return
        subprocess.Popen([exe], cwd=self.paths.root)
        self.win.destroy()

    # --- online mod packs (online.py) ------------------------------------------------------------------------------------
    def toggle_online_auto(self):
        cfg = install.load_config(self.paths)
        cfg['online_auto'] = bool(self.online_auto.get())
        install.save_config(self.paths, cfg)
        if self.online_auto.get() and not self.worker:
            self.online_check(auto=True)

    def online_check(self, auto=False, then=None):
        """read the catalogue + compare (a thread); auto = install what it finds (uDPRE first, then the packs)"""
        if self.worker:
            return
        self.online_note.config(text='Checking for mod updates...')
        self.worker = threading.Thread(target=self._online_check_work, args=(auto, then), daemon=True)
        self.worker.start()

    def _online_check_work(self, auto, then):
        from . import online
        try:
            index = online.fetch_index(self.paths)
            pl = online.plan(self.paths, index)
            self.q.put(('online_plan', index, pl, auto, then))
        except Exception as e:      # offline, relay down, a damaged catalogue: say it, play on
            self.q.put(('online_error', f'{type(e).__name__ if not isinstance(e, online.OnlineError) else ""}'
                                        f'{": " if not isinstance(e, online.OnlineError) else ""}{e}'))

    def online_apply(self, index, items, self_update=None):
        """install items (plan entries) one after another in a thread; self_update = the catalogue's uDPRE entry"""
        if self.worker:
            return
        for w in (self.go, self.play_btn):
            w.state(['disabled'])
        self.worker = threading.Thread(target=self._online_apply_work, args=(index, items, self_update), daemon=True)
        self.worker.start()

    def _online_apply_work(self, index, items, self_update):
        from . import online
        relay = online.relay_url(self.paths)
        log = lambda text: self.q.put(('log', text))   # noqa: E731
        try:
            if self_update:
                cmd = online.prepare_self_update(self.paths, relay, self_update, log=log,
                                                 progress=lambda d, s: self.q.put(('progress', 'Downloading uDPRE', d, s)))
                self.q.put(('online_restart', cmd))
                return
            done = []
            for it in items:
                e = it['entry']
                online.install_item(self.paths, relay, e, it['path'], set(it['parts']), log=log,
                                    progress=lambda d, s, n=e['name']: self.q.put(('progress', f'Downloading {n}', d, s)))
                done.append(e['id'])
            # the downloads the new / updated packs take files from (e.g. Luminescent 2.2F), when no copy is found
            for s in online.plan(self.paths, index)['sources']:
                if s['state'] == 'missing':
                    online.install_item(self.paths, relay, s['entry'], s['path'], set(s['parts']), log=log,
                                        progress=lambda d, sz, n=s['entry']['name']:
                                        self.q.put(('progress', f'Downloading {n}', d, sz)))
            self.q.put(('online_done', done))
        except Exception as e:
            self.q.put(('online_failed', f'{type(e).__name__}: {e}' if not isinstance(e, online.OnlineError) else str(e)))

    def online_idle(self):
        """after a download (done or failed): the buttons online_apply greyed come back, then refresh() decides Play"""
        self.worker = None
        self.dump_entry.state(['!disabled'])
        for w in (self.go, self.browse):
            w.state(['!disabled'])
        self.refresh()

    def _online_after(self, plan_result, auto, then):
        """what the check found: install it (auto), or go on with the start-up refresh"""
        from . import online
        index, pl = plan_result
        self.online_plan = (index, pl)
        self.online_note.config(text=online.summary(pl))
        if then:
            then(index, pl)
            return
        failed = online.self_update_failed(self.paths, pl['udpre']['build']) if pl['udpre'] else None
        if auto and pl['udpre'] and failed:
            self.say(f'uDPRE {pl["udpre"].get("version", "")} has a new build, but the last update to it did not finish '
                     f'({failed}). Download the release and unzip it over this folder by hand.')
        elif auto and pl['udpre']:
            if getattr(sys, 'frozen', False):
                self.say(f'uDPRE has a new build ({pl["udpre"].get("version", "")}): updating, then uDPRE starts again.')
                self.online_apply(index, [], self_update=pl['udpre'])
                return
            self.say('uDPRE has a new build (this copy runs from its source: update it with git).')
        updates = [i for i in pl['packs'] if i['state'] == 'update']
        missing = [s for s in pl['sources'] if s['state'] == 'missing']
        if auto and (updates or missing):
            self.say('Updating: ' + ', '.join(i['entry']['name'] for i in updates + missing))
            self.online_apply(index, updates)
            return
        if self.auto_start:
            self.auto_start = False
            self.start()

    def open_get_mods(self):
        from .online_ui import GetModsDialog
        GetModsDialog(self)

    def on_close(self):
        if self.worker and not messagebox.askyesno(TITLE, 'uDPRE is working (converting or downloading). Stop and close? '
                                                          '(Starting again later continues where it stopped.)'):
            return
        os._exit(0) if self.worker else self.win.destroy()


def main(root_dir):
    App(root_dir).win.mainloop()
    return 0
