"""tkinter building blocks of the Studio pages: a searchable picker, number fields, an editable table and a form built from
a field list (all in the Studio styles)."""
import tkinter as tk
from tkinter import ttk

from .kit import Button, Scroll as ScrollFrame  # noqa: F401  (ScrollFrame: the old name)


class Picker(ttk.Combobox):
    """A combobox over [(value, label)]: typing filters the list; get_value() -> the chosen value (None if the text is no
    entry). Labels are shown as given."""

    def __init__(self, master, choices, width=28, allow_free=False, **kw):
        super().__init__(master, width=width, style='Studio.TCombobox', **kw)
        self.allow_free = allow_free
        self.set_choices(choices)
        self.bind('<KeyRelease>', self._filter)
        self.bind('<FocusOut>', lambda _e: self.configure(values=self._labels))

    def set_choices(self, choices):
        self._choices = list(choices)
        self._labels = [lab for _, lab in self._choices]
        self._by_label = {lab: v for v, lab in self._choices}
        self._by_value = {}
        for v, lab in self._choices:
            self._by_value.setdefault(_hashable(v), lab)
        self.configure(values=self._labels)

    def _filter(self, e):
        if e.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        t = self.get().lower()
        self.configure(values=[lab for lab in self._labels if t in lab.lower()] if t else self._labels)

    def get_value(self):
        t = self.get()
        if t in self._by_label:
            return self._by_label[t]
        if self.allow_free:
            try:
                return int(t)
            except ValueError:
                return None
        head = t.split(' ', 1)[0]
        for v, lab in self._choices:
            if lab.split(' ', 1)[0] == head:
                return v
        return None

    def set_value(self, v):
        lab = self._by_value.get(_hashable(v))
        self.set(lab if lab is not None else ('' if v is None else str(v)))


def _hashable(v):
    return tuple(v) if isinstance(v, list) else v


class IntField(ttk.Spinbox):
    def __init__(self, master, lo=-2 ** 31, hi=2 ** 32 - 1, width=8, **kw):
        super().__init__(master, from_=lo, to=hi, width=width, style='Studio.TSpinbox', **kw)
        self.lo, self.hi = lo, hi

    def get_value(self):
        try:
            v = int(float(self.get()))
        except ValueError:
            return None
        return max(self.lo, min(self.hi, v))

    def set_value(self, v):
        self.delete(0, 'end')
        self.insert(0, '' if v is None else str(v))


class FloatField(ttk.Entry):
    def __init__(self, master, width=10, **kw):
        super().__init__(master, width=width, style='Studio.TEntry', **kw)

    def get_value(self):
        try:
            return float(self.get())
        except ValueError:
            return None

    def set_value(self, v):
        self.delete(0, 'end')
        self.insert(0, '' if v is None else repr(float(v)))


class TextField(ttk.Entry):
    def __init__(self, master, **kw):
        super().__init__(master, style='Studio.TEntry', **kw)

    def get_value(self):
        return self.get()

    def set_value(self, v):
        self.delete(0, 'end')
        self.insert(0, v or '')


class BitsField(ttk.Frame):
    """checkboxes for named bits of one integer"""

    def __init__(self, master, bits, columns=2, **kw):
        super().__init__(master, style='Studio.TFrame', **kw)
        self.vars = {}
        for k, (bit, name) in enumerate(bits):
            v = tk.BooleanVar()
            ttk.Checkbutton(self, text=name, variable=v, style='Studio.TCheckbutton').grid(
                row=k // columns, column=k % columns, sticky='w', padx=(0, 16), pady=1)
            self.vars[bit] = v
        self._value = 0

    def get_value(self):
        v = self._value
        for bit, var in self.vars.items():
            v = (v | (1 << bit)) if var.get() else (v & ~(1 << bit))
        return v

    def set_value(self, v):
        self._value = int(v or 0)
        for bit, var in self.vars.items():
            var.set(bool(self._value >> bit & 1))


class Form(ttk.Frame):
    """fields = [(label, key, kind, extra)], kind: int / float / text / choice (extra = [(v, label)]) / bits (extra =
    [(bit, name)]) / bool. load(dict) shows a record, values() -> {key: value} of every field."""

    def __init__(self, master, fields, columns=2, label_width=18, **kw):
        super().__init__(master, style='Studio.TFrame', **kw)
        self.widgets = {}
        for k, (label, key, kind, *extra) in enumerate(fields):
            extra = extra[0] if extra else None
            r, c = divmod(k, columns)
            ttk.Label(self, text=label, width=label_width, anchor='e', style='Muted.TLabel').grid(
                row=r, column=2 * c, sticky='e', padx=(0 if c == 0 else 18, 6), pady=2)
            if kind == 'int':
                lo, hi = extra if extra else (-2 ** 31, 2 ** 32 - 1)
                w = IntField(self, lo, hi)
            elif kind == 'float':
                w = FloatField(self)
            elif kind == 'text':
                w = TextField(self, width=30)
            elif kind == 'choice':
                w = Picker(self, extra)
            elif kind == 'bits':
                w = BitsField(self, extra)
            elif kind == 'bool':
                w = BoolField(self)
            else:
                raise ValueError(kind)
            w.grid(row=r, column=2 * c + 1, sticky='w', pady=2)
            self.widgets[key] = w

    def load(self, rec):
        for key, w in self.widgets.items():
            w.set_value(rec.get(key))

    def values(self):
        out = {}
        for key, w in self.widgets.items():
            v = w.get_value()
            if v is not None:
                out[key] = v
        return out

    def snapshot(self):
        return tuple((k, repr(w.get_value())) for k, w in self.widgets.items())


class FieldSet:
    """Form's load / values / snapshot over fields the caller lays out itself: widgets = {key: field}"""

    def __init__(self, widgets=None):
        self.widgets = dict(widgets or {})

    load = Form.load
    values = Form.values
    snapshot = Form.snapshot


class BoolField(ttk.Checkbutton):
    def __init__(self, master, **kw):
        self.var = tk.BooleanVar()
        super().__init__(master, variable=self.var, style='Studio.TCheckbutton', **kw)

    def get_value(self):
        return int(self.var.get())

    def set_value(self, v):
        self.var.set(bool(v))


class Table(ttk.Frame):
    """An editable grid: columns = [(title, kind, extra, width)], kind as in Form (int / float / text / choice / label).
    Double-click a cell to edit; Add / Remove / Up / Down when rows_editable."""

    def __init__(self, master, columns, height=8, rows_editable=True, new_row=None, on_change=None, **kw):
        super().__init__(master, style='Studio.TFrame', **kw)
        self.columns = columns
        self.on_change = on_change          # (row list, column, old value) after a cell edit changed a value
        self.new_row = new_row or (lambda: [0 if c[1] in ('int', 'choice') else '' for c in columns])
        self.tree = ttk.Treeview(self, columns=[str(i) for i in range(len(columns))], show='headings', height=height,
                                 selectmode='browse', style='Studio.Treeview')
        for i, (title, kind, extra, width) in enumerate(columns):
            self.tree.heading(str(i), text=title, anchor='w')
            self.tree.column(str(i), width=width, stretch=True)
        self.tree.tag_configure('odd', background='#f8fafc')
        sb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        sb.grid(row=0, column=1, sticky='ns')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rows = []
        self.tree.bind('<Double-1>', self._edit)
        self.tree.bind('<Return>', lambda _e: self._edit_selected())
        if rows_editable:
            bar = ttk.Frame(self, style='Studio.TFrame')
            bar.grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 0))
            for text, fn in (('+ Add', self.add), ('Remove', self.remove), ('Move up', lambda: self.move(-1)),
                             ('Move down', lambda: self.move(1))):
                Button(bar, text, fn, small=True).pack(side='left', padx=(0, 4))
        self._editor = None

    def _choices(self, col, row):
        extra = self.columns[col][2]
        return extra(row) if callable(extra) else extra

    def _label(self, col, v, row=None):
        title, kind, extra, _ = self.columns[col]
        if kind == 'choice':
            for val, lab in (self._choices(col, row) or []):
                if val == v:
                    return lab
        return '' if v is None else str(v)

    def set_rows(self, rows):
        self.rows = [list(r) for r in rows]
        self._render()

    def get_rows(self):
        return [list(r) for r in self.rows]

    def snapshot(self):
        return repr(self.rows)

    def _render(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            self.tree.insert('', 'end', iid=str(i), values=[self._label(c, v, r) for c, v in enumerate(r)],
                             tags=['odd'] if i % 2 else [])
        if select is not None and 0 <= select < len(self.rows):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def add(self):
        i = self._sel()
        i = len(self.rows) if i is None else i + 1
        self.rows.insert(i, list(self.new_row()))
        self._render(i)

    def remove(self):
        i = self._sel()
        if i is not None:
            del self.rows[i]
            self._render(min(i, len(self.rows) - 1))

    def move(self, d):
        i = self._sel()
        if i is None or not 0 <= i + d < len(self.rows):
            return
        self.rows[i], self.rows[i + d] = self.rows[i + d], self.rows[i]
        self._render(i + d)

    def _edit_selected(self):
        i = self._sel()
        if i is None:
            return
        for c, col in enumerate(self.columns):
            if col[1] != 'label':
                self._open(i, c)
                return

    def _edit(self, e):
        row = self.tree.identify_row(e.y)
        col = self.tree.identify_column(e.x)
        if not row or not col:
            return
        self._open(int(row), int(col[1:]) - 1)

    def _open(self, r, c):
        if self._editor is not None:
            self._editor.destroy()
        bbox = self.tree.bbox(str(r), str(c))
        if not bbox:
            return
        x, y, w, h = bbox
        title, kind, extra, _ = self.columns[c]
        if kind == 'label':             # shown only (a slot's rate ...)
            return
        if kind == 'choice':
            choices = self._choices(c, self.rows[r])
            if choices is None:         # this row's cell takes a plain number
                ed = IntField(self.tree)
            else:
                ed = Picker(self.tree, choices, width=max(10, w // 7))
        elif kind == 'int':
            ed = IntField(self.tree, *(extra or (-2 ** 31, 2 ** 32 - 1)))
        elif kind == 'float':
            ed = FloatField(self.tree)
        else:
            ed = TextField(self.tree)
        ed.set_value(self.rows[r][c])
        ed.place(x=x, y=y, width=max(w, 120 if kind == 'choice' else w), height=h)
        ed.focus_set()

        def done(_e=None):
            v = ed.get_value()
            if v is not None:
                old = self.rows[r][c]
                self.rows[r][c] = v
                if self.on_change is not None and v != old:
                    self.on_change(self.rows[r], c, old)
            ed.destroy()
            self._editor = None
            self._render(r)
        ed.bind('<Return>', done)
        ed.bind('<FocusOut>', done)
        ed.bind('<Escape>', lambda _e: (ed.destroy(), setattr(self, '_editor', None)))
        self._editor = ed
