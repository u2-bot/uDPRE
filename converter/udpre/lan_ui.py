"""The LAN play dialog of the uDPRE window: on / off, port, friends' addresses, one adapter, the Windows Firewall rule, and the
build two games must share."""
import socket
import tkinter as tk
from tkinter import messagebox, ttk

from . import lan, winfit


def local_addresses():
    """-> this PC's IPv4 addresses (for the adapter choice and to tell friends)"""
    out = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            a = info[4][0]
            if a not in out and not a.startswith('127.'):
                out.append(a)
    except OSError:
        pass
    return out


class LanDialog:
    def __init__(self, parent, root_dir, title, on_change=None, app_dir=None):
        self.root = root_dir
        self.on_change = on_change
        self.win = tk.Toplevel(parent)
        self.win.title('LAN play (Beta) - ' + title)
        winfit.fit(self.win, 720, 760, 600, 520)
        self.win.transient(parent)
        s = lan.read_settings(root_dir)
        btns = ttk.Frame(self.win)
        btns.pack(side='bottom', fill='x', padx=12, pady=10)       # before the content: a short window cuts it, not these

        ttk.Label(self.win, text='LAN play', font=('Segoe UI', 12, 'bold')).pack(anchor='w', padx=12, pady=(10, 2))
        sup = lan.player_supports(root_dir)
        intro = ('Play the Union Room, the Colosseum, the Grand Underground and Super Contests with other uDPRE players on '
                 'your network, the way the Switch plays them over local wireless: in the game, pick "local communication" '
                 '(Local Play). With the overworld on, players of the same game also see each other walking around '
                 'Sinnoh - each keeps their own game and story. Everyone needs the same game (below), not the same mods.')
        if sup is False:
            intro += ('\n\nThe game in this folder has no LAN play yet: convert once with uDPRE 0.5.0 (with Luminescent or '
                      'Dechibified on, their packs made for 0.5.0).')
        elif sup is None:
            intro += '\n\nConvert your dump first.'
        ttk.Label(self.win, text=intro, wraplength=680, justify='left',
                  foreground='#a33' if sup is False else '#333').pack(anchor='w', padx=12)

        box = ttk.LabelFrame(self.win, text='Settings (the game reads them when it starts)')
        box.pack(fill='x', padx=12, pady=8)
        box.columnconfigure(1, weight=1)
        self.on_var = tk.BooleanVar(value=s['lan'])
        ttk.Checkbutton(box, text='LAN play on', variable=self.on_var).grid(row=0, column=0, columnspan=3, sticky='w', padx=8, pady=4)
        ttk.Label(box, text='Port:').grid(row=1, column=0, sticky='w', padx=8)
        self.port_var = tk.StringVar(value=str(s['port']))
        ttk.Entry(box, textvariable=self.port_var, width=8).grid(row=1, column=1, sticky='w')
        ttk.Label(box, text=f'UDP + TCP, {lan.PORT_SPAN} in a row (default {lan.DEFAULT_PORT}); everyone uses the same',
                  foreground='#555').grid(row=1, column=2, sticky='w', padx=8)
        ttk.Label(box, text='Friends\' addresses:').grid(row=2, column=0, sticky='w', padx=8, pady=(6, 0))
        self.peers_var = tk.StringVar(value=', '.join(s['peers']))
        ttk.Entry(box, textvariable=self.peers_var).grid(row=2, column=1, columnspan=2, sticky='we', padx=(0, 8), pady=(6, 0))
        ttk.Label(box, text='Only needed when the game cannot find them by itself: over Tailscale, or across the internet. '
                            'One reachable player is enough: forward UDP + TCP 39310-39317 on that router, and the others '
                            'enter that address here (comma-separated). Rooms, battles and Team Up then travel through '
                            'the overworld link. A LAN, ZeroTier, Radmin VPN or Hamachi needs nothing here.',
                  foreground='#555', wraplength=640, justify='left').grid(row=3, column=0, columnspan=3, sticky='w', padx=8)
        ttk.Label(box, text='Adapter:').grid(row=4, column=0, sticky='w', padx=8, pady=(6, 6))
        self.bind_var = tk.StringVar(value=s['bind'] or 'every adapter')
        ttk.Combobox(box, textvariable=self.bind_var, values=['every adapter'] + local_addresses(), width=22).grid(
            row=4, column=1, sticky='w', pady=(6, 6))
        self.world_var = tk.BooleanVar(value=s['world'])
        ttk.Checkbutton(box, text='Overworld: see the other players walking around (each keeps their own game)',
                        variable=self.world_var).grid(row=5, column=0, columnspan=3, sticky='w', padx=8, pady=(0, 6))
        ttk.Label(box, text='Following Pokemon:').grid(row=6, column=0, sticky='w', padx=8, pady=(0, 6))
        self.follow_var = tk.StringVar(value=lan.FOLLOW_CHOICES[s['follow']])
        ttk.Combobox(box, textvariable=self.follow_var, values=list(lan.FOLLOW_CHOICES), state='readonly', width=58).grid(
            row=6, column=1, columnspan=2, sticky='w', pady=(0, 6))
        mine = local_addresses()
        ttk.Label(box, text=('This PC: ' + ', '.join(mine)) if mine else '', foreground='#555').grid(
            row=4, column=2, sticky='w', padx=8)

        fw = ttk.LabelFrame(self.win, text='Windows Firewall')
        fw.pack(fill='x', padx=12, pady=4)
        frow = ttk.Frame(fw)
        frow.pack(fill='x', padx=8, pady=6)
        self.fw_note = ttk.Label(frow, text='', wraplength=470, justify='left')
        self.fw_note.pack(side='left')
        ttk.Button(frow, text='Allow LAN play...', command=self.allow).pack(side='right')
        self.app_dir = app_dir
        self.fw_refresh()

        host = ttk.LabelFrame(self.win, text='World host')
        host.pack(fill='x', padx=12, pady=4)
        hrow = ttk.Frame(host)
        hrow.pack(fill='x', padx=8, pady=6)
        has_host = bool(app_dir and lan.world_host_exe(app_dir))
        ttk.Label(hrow, text=('Keeps the overworld up while players come and go: run it on a PC that stays on (it plays no '
                              'game of its own and uses this folder\'s build). Press Allow LAN play... above first on that '
                              'PC, or Windows may let it through on private networks only.')
                  if has_host else 'The world host comes with the uDPRE release (uDPRE World Host.exe).',
                  wraplength=470, justify='left').pack(side='left')
        ttk.Button(hrow, text='Start a world host', command=self.start_host,
                   state='normal' if has_host else 'disabled').pack(side='right')

        bb = ttk.LabelFrame(self.win, text='This game\'s build')
        bb.pack(fill='x', padx=12, pady=4)
        info = lan.read(root_dir)
        text = (('Luminescent Platinum' if info.get('family') == 'lumi' else 'Brilliant Diamond') + ', LAN play of uDPRE ' +
                info.get('release', '?') + '\nmods: ' + info.get('label', '')) if info else \
            'Not written yet: convert once with uDPRE 0.5.0.'
        ttk.Label(bb, text=text, wraplength=680, justify='left').pack(anchor='w', padx=8, pady=(6, 2))
        ttk.Label(bb, text='Players meet when they play the same game: Brilliant Diamond or Luminescent, the same LAN '
                           'play version (above) and the same Pokemon, battle, contest and Underground data. Cosmetic and own-world mods '
                           '(Darker UI, icons, translations, Dechibified, Easy Mode, shiny odds), the game language and '
                           'Nuzlocke rules may differ; No Balance, or edits to Pokemon, moves or items, must match. In the '
                           'game, the chat box\'s player list (P) shows games nearby that cannot join you, and why.',
                  foreground='#555', wraplength=680, justify='left').pack(anchor='w', padx=8, pady=(0, 6))

        self.saved = ttk.Label(btns, text='', foreground='#555')
        self.saved.pack(side='left')
        ttk.Button(btns, text='Close', command=self.win.destroy).pack(side='right')
        ttk.Button(btns, text='Save', command=self.save).pack(side='right', padx=(0, 8))

    def fw_refresh(self):
        st = lan.firewall_status(self.root, self.app_dir)
        self.fw_state = st
        if st is None:
            self.fw_note.config(text='To host, Windows must let other players reach this PC. If they cannot, press Allow '
                                     '(it asks for administrator rights).', foreground='#333')
        elif all(s == 'allowed' for _w, _p, s, _k in st):
            self.fw_note.config(text='Allowed on every network: other players can reach ' +
                                     ' and '.join(w for w, _p, _s, _k in st) + ' on this PC.', foreground='#262')
        else:
            blocked = any(s == 'blocked' for _w, _p, s, _k in st)
            self.fw_note.config(text='\n'.join(lan.firewall_summary(st)) +
                                ('\nPress Allow (it asks for administrator rights).' if blocked else
                                 '\nTo host, press Allow (it asks for administrator rights).'),
                                foreground='#a33' if blocked else '#333')

    def start_host(self):
        st = getattr(self, 'fw_state', None)
        host = [x for x in (st or []) if x[0] == 'the world host']
        if host and host[0][2] != 'allowed' and messagebox.askyesno(
                'LAN play', 'Windows Firewall does not let other players reach the world host on every network ('
                + lan.firewall_summary(host)[0] + ').\n\nAllow it first? Windows asks for administrator rights.',
                parent=self.win):
            # wait for the rule: a world host started before it makes Windows ask again (and write its block rule)
            self.saved.config(text='Answer Windows\' prompt to allow the game and the world host.')
            self.win.update_idletasks()
            if not lan.allow_firewall(self.root, self.app_dir, wait=True):
                messagebox.showwarning('LAN play', 'The firewall rules were not made (the prompt was answered No, or '
                                       'Windows refused). The world host starts anyway.', parent=self.win)
            self.fw_refresh()
        if not lan.start_world_host(self.app_dir, self.root):
            messagebox.showerror('LAN play', 'The world host did not start.', parent=self.win)
            return
        self.saved.config(text='World host started in its own window (close that window to stop it).')

    def allow(self):
        if not lan.allow_firewall(self.root, self.app_dir):
            messagebox.showerror('LAN play', 'Windows did not start the administrator prompt.', parent=self.win)
            return
        for ms in (4000, 10000, 20000):
            self.win.after(ms, self.fw_refresh)
        self.saved.config(text='Answer Windows\' prompt to allow the game and the world host.')

    def save(self):
        try:
            port = int(self.port_var.get().strip())
            if not 1024 <= port < 65536 - lan.PORT_SPAN:
                raise ValueError
        except ValueError:
            messagebox.showerror('LAN play', f'The port must be a number from 1024 to {65535 - lan.PORT_SPAN}.', parent=self.win)
            return
        peers = [x.strip() for x in self.peers_var.get().replace(';', ',').split(',') if x.strip()]
        bind = self.bind_var.get().strip()
        if bind == 'every adapter':
            bind = ''
        try:
            follow = lan.FOLLOW_CHOICES.index(self.follow_var.get()) if self.follow_var.get() in lan.FOLLOW_CHOICES else 1
            p = lan.write_settings(self.root, self.on_var.get(), port, peers, bind, self.world_var.get(), follow)
        except OSError as e:
            messagebox.showerror('LAN play', f'Could not save: {e}', parent=self.win)
            return
        self.saved.config(text='Saved - restart the game if it is running.')
        if self.on_change:
            self.on_change()
