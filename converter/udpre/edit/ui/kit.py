"""uDPRE Studio's building blocks: buttons, pills, a segmented control, sections, a sortable data table with edited
markers, a search box, stat bars and a scrollable page body."""
import tkinter as tk
from tkinter import ttk

from .theme import C, FONT, stat_color, text_on, type_color

BUTTONS = {   # kind: (background, hover, text, border)
    'primary': (C['accent'], C['accent_hover'], '#ffffff', C['accent']),
    'secondary': (C['bg'], C['soft'], C['text'], C['line2']),
    'ghost': (C['bg'], C['soft'], C['accent'], C['bg']),
    'danger': (C['bg'], C['danger_soft'], C['danger'], C['line2']),
}


class Button(tk.Label):
    """a flat button (tk label): kind primary / secondary / ghost / danger"""

    def __init__(self, master, text, command=None, kind='secondary', small=False, **kw):
        bg, hover, fg, border = BUTTONS[kind]
        super().__init__(master, text=text, bg=bg, fg=fg, cursor='hand2', padx=10 if small else 14,
                         pady=2 if small else 5, font=(FONT, 9, 'bold' if kind == 'primary' else 'normal'),
                         highlightthickness=1, highlightbackground=border, highlightcolor=border, **kw)
        self.command = command
        self.colors = (bg, hover)
        self.fg = fg
        self.enabled = True
        self.bind('<Enter>', lambda _e: self.enabled and self.config(bg=self.colors[1]))
        self.bind('<Leave>', lambda _e: self.config(bg=self.colors[0]))
        self.bind('<Button-1>', self._click)

    def _click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.config(fg=self.fg if on else C['faint'], cursor='hand2' if on else '')


class Link(tk.Label):
    def __init__(self, master, text, command, bg=None, **kw):
        super().__init__(master, text=text, fg=C['accent'], bg=bg or C['bg'], cursor='hand2', font=(FONT, 9), **kw)
        self.bind('<Button-1>', lambda _e: command())
        self.bind('<Enter>', lambda _e: self.config(font=(FONT, 9, 'underline')))
        self.bind('<Leave>', lambda _e: self.config(font=(FONT, 9)))


def pill(master, text, bg, fg=None, bold=True):
    return tk.Label(master, text=text, bg=bg, fg=fg or text_on(bg), padx=8, pady=1,
                    font=(FONT, 8, 'bold' if bold else 'normal'))


def type_pill(master, game, t):
    return pill(master, game.type_name(t) if t is not None else '-', type_color(t))


class Segmented(tk.Frame):
    """one-of-several switch: options = [(value, label)]; command(value) on a click"""

    def __init__(self, master, options, command=None, value=None, bg=None):
        super().__init__(master, bg=C['line2'], padx=1, pady=1)
        self.command = command
        self.items = {}
        for v, lab in options:
            w = tk.Label(self, text=lab, padx=12, pady=3, font=(FONT, 9), cursor='hand2')
            w.pack(side='left', padx=(0, 1))
            w.bind('<Button-1>', lambda _e, v=v: self.pick(v))
            self.items[v] = w
        self.value = value if value is not None else (options[0][0] if options else None)
        self._paint()

    def _paint(self):
        for v, w in self.items.items():
            on = v == self.value
            w.config(bg=C['accent'] if on else C['bg'], fg='#ffffff' if on else C['text'])

    def pick(self, v, notify=True):
        self.value = v
        self._paint()
        if notify and self.command:
            self.command(v)

    def get(self):
        return self.value


class Section(ttk.Frame):
    """a titled block of a page: title (+ hint) above a thin rule; .body holds the content"""

    def __init__(self, master, title, hint=None, actions=(), **kw):
        super().__init__(master, style='Studio.TFrame', **kw)
        head = ttk.Frame(self, style='Studio.TFrame')
        head.pack(fill='x')
        ttk.Label(head, text=title, style='Section.TLabel').pack(side='left')
        if hint:
            ttk.Label(head, text=hint, style='Muted.TLabel').pack(side='left', padx=(10, 0))
        for text, fn in reversed(list(actions)):
            Link(head, text, fn).pack(side='right', padx=(10, 0))
        tk.Frame(self, height=1, bg=C['line']).pack(fill='x', pady=(3, 6))
        self.body = ttk.Frame(self, style='Studio.TFrame')
        self.body.pack(fill='both', expand=True)


class Scroll(ttk.Frame):
    """a vertically scrolling white body (.body); the wheel scrolls the one under the pointer"""

    def __init__(self, master, **kw):
        super().__init__(master, style='Studio.TFrame', **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, bg=C['bg'])
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, style='Studio.TFrame')
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind_all('<MouseWheel>', self._wheel, add='+')

    def _wheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None and w is not self.canvas:
            if isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox)):
                return              # those scroll themselves
            w = getattr(w, 'master', None)
        if w is self.canvas and self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')

    def top(self):
        self.canvas.yview_moveto(0)


class SearchBox(ttk.Entry):
    """an entry with a gray placeholder; on_change(text) after each key (text '' while the placeholder shows)"""

    def __init__(self, master, placeholder, on_change=None, width=30, **kw):
        self.var = tk.StringVar()
        super().__init__(master, textvariable=self.var, width=width, style='Studio.TEntry', **kw)
        self.placeholder = placeholder
        self.on_change = on_change
        self._ph = False
        self._show_ph()
        self.bind('<FocusIn>', self._in)
        self.bind('<FocusOut>', lambda _e: self._show_ph())
        self.bind('<KeyRelease>', self._key)

    def _show_ph(self):
        if not self.var.get():
            self._ph = True
            self.var.set(self.placeholder)
            self.configure(foreground=C['faint'])

    def _in(self, _e):
        if self._ph:
            self._ph = False
            self.var.set('')
            self.configure(foreground=C['text'])

    def _key(self, e):
        if e.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        if self.on_change:
            self.on_change(self.get_text())

    def get_text(self):
        return '' if self._ph else self.var.get()

    def clear(self):
        self._ph = False
        self.var.set('')
        self.configure(foreground=C['text'])
        self._show_ph()


def _sort_key(v):
    s = str(v)
    try:
        return (0, float(s.replace(',', '').replace('%', '').strip() or 'nan'), '')
    except ValueError:
        return (1, 0.0, s.lower())


class DataTable(ttk.Frame):
    """A sortable table of records: columns = [(id, title, width, anchor)]; set_rows([(key, values)], edited=keys).
    A first narrow column marks edited records (their row text in the edited color). Click a header to sort (numbers as
    numbers). on_select(key) -> False refuses the move (the selection goes back)."""

    def __init__(self, master, columns, on_select=None, height=20, marker=True, on_activate=None):
        super().__init__(master, style='Studio.TFrame')
        self.columns = list(columns)
        self.marker = marker
        ids = (['_m'] if marker else []) + [c[0] for c in self.columns]
        self.tree = ttk.Treeview(self, columns=ids, show='headings', selectmode='browse', height=height,
                                 style='Studio.Treeview')
        if marker:
            self.tree.heading('_m', text='')
            self.tree.column('_m', width=22, minwidth=22, stretch=False, anchor='center')
        for cid, title, width, anchor in self.columns:
            self.tree.heading(cid, text=title, anchor=anchor, command=lambda c=cid: self.sort_by(c))
            self.tree.column(cid, width=width, minwidth=30, anchor=anchor, stretch=cid == self.columns[-1][0] or
                             width >= 160)
        self.tree.tag_configure('odd', background=C['stripe'])
        self.tree.tag_configure('edited', foreground='#a85600')
        sb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.on_select = on_select
        self.on_activate = on_activate
        self.rows = []              # [(key, values)]
        self.edited = set()
        self.text = ''
        self.pred = None
        self.sort = None            # (column id, reverse)
        self._iid = {}              # key -> iid
        self._key = {}              # iid -> key
        self._cur = None
        self._quiet = False
        self.tree.bind('<<TreeviewSelect>>', self._picked)
        if on_activate:
            self.tree.bind('<Double-1>', lambda _e: self.current() is not None and on_activate(self.current()))

    def set_rows(self, rows, edited=None):
        self.rows = list(rows)
        if edited is not None:
            self.edited = set(edited)
        self.render()

    def set_edited(self, keys):
        self.edited = set(keys)
        for iid, key in self._key.items():
            self._tag(iid, key)

    def _tag(self, iid, key):
        idx = self.tree.index(iid)
        tags = (['odd'] if idx % 2 else []) + (['edited'] if key in self.edited else [])
        self.tree.item(iid, tags=tags)
        if self.marker:
            self.tree.set(iid, '_m', '●' if key in self.edited else '')

    def filter(self, text=None, pred=None):
        if text is not None:
            self.text = text.lower().strip()
        self.pred = pred
        self.render()

    def visible(self):
        t = self.text
        out = []
        for key, vals in self.rows:
            if self.pred is not None and not self.pred(key, vals):
                continue
            if t and t not in ' '.join(str(v) for v in vals).lower():
                continue
            out.append((key, vals))
        if self.sort:
            cid, rev = self.sort
            i = [c[0] for c in self.columns].index(cid)
            out.sort(key=lambda kv: _sort_key(kv[1][i]), reverse=rev)
        return out

    def render(self):
        self._quiet = True
        self.tree.delete(*self.tree.get_children())
        self._iid, self._key = {}, {}
        for n, (key, vals) in enumerate(self.visible()):
            iid = str(n)
            ed = key in self.edited
            self.tree.insert('', 'end', iid=iid, values=((('●' if ed else ''),) if self.marker else ()) + tuple(vals),
                             tags=(['odd'] if n % 2 else []) + (['edited'] if ed else []))
            self._iid[key] = iid
            self._key[iid] = key
        if self._cur in self._iid:
            self.tree.selection_set(self._iid[self._cur])
            self.tree.see(self._iid[self._cur])
        self._quiet = False
        for cid, title, _w, anchor in self.columns:
            arrow = (' ▼' if self.sort[1] else ' ▲') if self.sort and self.sort[0] == cid else ''
            self.tree.heading(cid, text=title + arrow)

    def sort_by(self, cid):
        rev = bool(self.sort and self.sort[0] == cid and not self.sort[1])
        self.sort = (cid, rev)
        self.render()

    def update_row(self, key, values):
        self.rows = [(k, values if k == key else v) for k, v in self.rows]
        iid = self._iid.get(key)
        if iid is not None:
            self.tree.item(iid, values=((('●' if key in self.edited else ''),) if self.marker else ()) + tuple(values))

    def _picked(self, _e):
        if self._quiet:
            return
        s = self.tree.selection()
        if not s:
            return
        key = self._key.get(s[0])
        if key == self._cur:
            return
        if self.on_select is not None and self.on_select(key) is False:
            self.select(self._cur, notify=False)
            return
        self._cur = key

    def select(self, key, notify=True):
        if key not in self._iid:
            if notify and key is not None and any(k == key for k, _ in self.rows):
                self.text, self.pred = '', None      # a jump to a record the filter hides: show everything
                self.render()
            if key not in self._iid:
                return False
        self._quiet = True
        self.tree.selection_set(self._iid[key])
        self.tree.see(self._iid[key])
        self._quiet = False
        prev, self._cur = self._cur, key
        if notify and self.on_select is not None and key != prev:
            if self.on_select(key) is False:
                self.select(prev, notify=False)
                return False
        return True

    def select_first(self):
        kids = self.tree.get_children()
        if kids:
            return self.select(self._key[kids[0]])
        return False

    def first_key(self):
        kids = self.tree.get_children()
        return self._key[kids[0]] if kids else None

    def current(self):
        return self._cur

    def count(self):
        return len(self.tree.get_children())


class StatBars(tk.Canvas):
    """six base stats as colored bars with their values, and the total"""

    def __init__(self, master, names, width=360):
        super().__init__(master, width=width, height=22 * (len(names) + 1) + 4, bg=C['bg'], highlightthickness=0)
        self.names = names
        self.w = width

    def show(self, values):
        self.delete('all')
        lab_w, num_w = 70, 36
        bar_max = self.w - lab_w - num_w - 8
        for k, (n, v) in enumerate(zip(self.names, values)):
            y = 4 + 22 * k
            self.create_text(lab_w - 6, y + 9, text=n, anchor='e', fill=C['muted'], font=(FONT, 9))
            self.create_text(lab_w + num_w - 6, y + 9, text=str(v), anchor='e', fill=C['text'], font=(FONT, 9, 'bold'))
            x0 = lab_w + num_w
            self.create_rectangle(x0, y + 3, x0 + bar_max, y + 15, fill=C['soft'], outline='')
            ln = max(2, int(bar_max * min(int(v or 0), 255) / 255))
            self.create_rectangle(x0, y + 3, x0 + ln, y + 15, fill=stat_color(int(v or 0)), outline='')
        y = 4 + 22 * len(self.names)
        self.create_text(lab_w - 6, y + 9, text='Total', anchor='e', fill=C['muted'], font=(FONT, 9, 'bold'))
        self.create_text(lab_w + num_w - 6, y + 9, text=str(sum(int(v or 0) for v in values)), anchor='e',
                         fill=C['text'], font=(FONT, 10, 'bold'))


def label(master, text, style='Studio.TLabel', **kw):
    return ttk.Label(master, text=text, style=style, **kw)


def frame(master, **kw):
    return ttk.Frame(master, style='Studio.TFrame', **kw)


def hline(master, pady=6):
    f = tk.Frame(master, height=1, bg=C['line'])
    f.pack(fill='x', pady=pady)
    return f
