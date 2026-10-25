"""Pages of the Studio window. Page = any view; RecordPage = a sortable record table on the left and the record on the
right, with auto-keep (leaving a record keeps its changes as operations of your edits), a live "unsaved changes" strip,
edited markers in the table and "Undo edits to this record".

RecordPage subclasses give: columns, rows() -> [(key, values)], build(body), show(key), collect(key) -> operations
(set_op applies and returns them), op_key(op) -> the record an operation edits (or None), and
optionally row(key) -> values (one row again after a change), record_name(key) (messages), extra_left(frame) (filters)."""
import tkinter as tk
from tkinter import messagebox, ttk

from .kit import Button, DataTable, Link, Scroll, SearchBox, frame, pill
from .theme import C, FONT


class Page(ttk.Frame):
    title = ''
    subtitle = ''

    def __init__(self, app, master):
        super().__init__(master, style='Studio.TFrame')
        self.app = app
        self.s = app.session
        self.c = app.choices
        self.built = False

    def ensure(self):
        if not self.built:
            self.built = True
            self.build_page()

    def build_page(self):
        pass

    def on_show(self):
        pass

    def leave(self):
        """True = the page can be left (its pending changes were kept)"""
        return True

    def refresh(self):
        """your edits changed elsewhere (undo, randomize, an import): show the data again"""

    def goto(self, key):
        pass

    def say(self, text):
        self.app.say(text)


class RecordPage(Page):
    columns = []
    list_width = 340
    noun = 'record'
    nouns = None                    # plural of noun (default noun + s)
    scroll_body = True
    sortable_default = None         # (column id, reverse) to start sorted

    def build_page(self):
        self.key = None
        self._base = None
        self.tracked = []
        left = frame(self, width=self.list_width)
        left.pack(side='left', fill='y', padx=(16, 0), pady=(10, 12))
        left.pack_propagate(False)
        self.search = SearchBox(left, f'Filter {self.title}...', on_change=lambda t: self._filter(t))
        self.search.pack(fill='x')
        self.filters = frame(left)
        self.filters.pack(fill='x')
        self.extra_left(self.filters)
        self.table = DataTable(left, self.columns, on_select=self._pick)
        self.table.pack(fill='both', expand=True, pady=(6, 0))
        if self.sortable_default:
            self.table.sort = self.sortable_default
        self.count = ttk.Label(left, text='', style='Faint.TLabel')
        self.count.pack(anchor='w', pady=(4, 0))
        tk.Frame(self, width=1, bg=C['line']).pack(side='left', fill='y', padx=(14, 0))
        right = frame(self)
        right.pack(side='left', fill='both', expand=True)
        head = frame(right)
        head.pack(fill='x', padx=20, pady=(12, 0))
        top = frame(head)
        top.pack(fill='x')
        self.h_title = ttk.Label(top, text='', style='Record.TLabel')
        self.h_title.pack(side='left')
        self.h_pills = frame(top)
        self.h_pills.pack(side='left', padx=(12, 0))
        self.h_undo = Link(top, '', self.undo_record)
        self.h_undo.pack(side='right')
        self.h_sub = ttk.Label(head, text='', style='Muted.TLabel')
        self.h_sub.pack(anchor='w')
        self.strip = tk.Frame(right, bg=C['edited_soft'])
        tk.Label(self.strip, text='●  Unsaved changes', bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9, 'bold')).pack(
            side='left', padx=(12, 0), pady=5)
        tk.Label(self.strip, text='kept when you leave this record', bg=C['edited_soft'], fg='#8a4b00',
                 font=(FONT, 9)).pack(side='left', padx=(8, 0))
        Link(self.strip, 'Discard', self.discard, bg=C['edited_soft']).pack(side='right', padx=(8, 12))
        Button(self.strip, 'Keep  (Ctrl+S)', self.keep, kind='primary', small=True).pack(side='right', pady=4)
        line = tk.Frame(right, height=1, bg=C['line'])
        line.pack(fill='x', padx=20, pady=(8, 0))
        self._strip_after = line
        self.error = ttk.Label(right, text='', style='Error.TLabel')
        self.error.pack(anchor='w', padx=20)
        if self.scroll_body:
            sc = Scroll(right)
            sc.pack(fill='both', expand=True, padx=(20, 0), pady=(4, 0))
            self.scroller = sc
            self.body = sc.body
        else:
            self.scroller = None
            self.body = frame(right)
            self.body.pack(fill='both', expand=True, padx=20, pady=(6, 10))
        self.build(self.body)
        self.reload_rows()
        self.table.select_first()
        self._poll()

    # --- subclass hooks --------------------------------------------------------------------------------------------
    def extra_left(self, frame_):
        pass

    def rows(self):
        return []

    def row(self, key):
        return dict(self.rows()).get(key)

    def build(self, body):
        pass

    def show(self, key):
        pass

    def collect(self, key):
        return []

    def op_key(self, op):
        return None

    def record_name(self, key):
        return self.h_title.cget('text') or str(key)

    def extra_state(self):
        return ()

    # --- helpers ---------------------------------------------------------------------------------------------------
    def track(self, *widgets):
        """widgets whose value counts for "unsaved changes" (Form, Table, BitsField, tk variables ...)"""
        self.tracked.extend(widgets)
        return widgets[0] if len(widgets) == 1 else widgets

    def set_header(self, title, subtitle='', pills=()):
        self.h_title.config(text=title)
        self.h_sub.config(text=subtitle)
        keep = {str(p) for p in pills if isinstance(p, tk.Widget)}
        for w in self.h_pills.winfo_children():
            if str(w) not in keep:
                w.destroy()
        for p in pills:
            (p if isinstance(p, tk.Widget) else pill(self.h_pills, *p)).pack(side='left', padx=(0, 4))

    def pill_parent(self):
        return self.h_pills

    def snapshot(self):
        out = []
        for w in self.tracked:
            if hasattr(w, 'snapshot'):
                out.append(w.snapshot())
            elif hasattr(w, 'get_value'):
                out.append(repr(w.get_value()))
            else:
                out.append(repr(w.get()))
        return tuple(out) + tuple(self.extra_state())

    def dirty(self):
        if self.key is None or self._base is None:
            return False
        try:
            return self.snapshot() != self._base
        except tk.TclError:
            return False

    def _poll(self):
        try:
            d = self.dirty()
            if d and not self.strip.winfo_ismapped():
                self.strip.pack(fill='x', padx=20, pady=(8, 0), before=self._strip_after)
            elif not d and self.strip.winfo_ismapped():
                self.strip.pack_forget()
        except tk.TclError:
            return
        self._poll_id = self.after(400, self._poll)

    def destroy(self):
        if getattr(self, '_poll_id', None):
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
        super().destroy()

    def _filter(self, text):
        self.table.filter(text)
        self._count()

    def _count(self):
        n, m = self.table.count(), len(self.table.rows)
        ed = len(self.table.edited)
        many = self.nouns or self.noun + 's'
        self.count.config(text=(f'{n} of {m} {many}' if n != m else f'{m} {many}') +
                          (f'  ·  {ed} edited' if ed else ''))

    def edited_keys(self):
        out = set()
        for op in self.s.project.ops:
            try:
                k = self.op_key(op)
            except Exception:
                k = None
            if k is not None:
                out.add(k)
        return out

    def reload_rows(self):
        self.table.set_rows(self.rows(), self.edited_keys())
        self._count()

    # --- record flow -----------------------------------------------------------------------------------------------
    def _pick(self, key):
        if self.key is not None and key != self.key and not self.keep():
            return False
        self.load(key)
        return True

    def load(self, key):
        self.key = key
        self.error.config(text='')
        self.show(key)
        self._base = self.snapshot()
        n = sum(1 for op in self.s.project.ops if self._safe_key(op) == key)
        self.h_undo.config(text=f'Undo my {n} edit{"s" if n != 1 else ""} to this {self.noun}' if n else '')
        if self.scroller is not None:
            self.scroller.top()

    def _safe_key(self, op):
        try:
            return self.op_key(op)
        except Exception:
            return None

    def keep(self):
        """the form's changes -> operations of your edits; False when a value is refused (the record stays)"""
        if not self.dirty():
            return True
        try:
            ops = self.collect(self.key)
        except ValueError as e:
            self.error.config(text=f'Not kept: {e}')
            return False
        n = self.s.commit(ops)
        name = self.record_name(self.key)
        vals = self.row(self.key)
        if vals is not None:
            self.table.update_row(self.key, vals)
        self.table.set_edited(self.edited_keys())
        self._count()
        self.app.changed(f'Kept {n} change{"s" if n != 1 else ""} to {name}.' if n else None)
        self.load(self.key)
        return True

    def discard(self):
        if self.key is not None:
            self.load(self.key)

    def leave(self):
        return self.keep() if self.built else True

    def refresh(self):
        if not self.built:
            return
        key = self.key
        self.key = None
        self._base = None
        self.reload_rows()
        if key is None or not self.table.select(key, notify=False):
            key = self.table.first_key()
            if key is None:
                return
            self.table.select(key, notify=False)
        self.load(key)

    def goto(self, key):
        self.ensure()
        self.table.select(key)

    def undo_record(self):
        idx = [i for i, op in enumerate(self.s.project.ops) if self._safe_key(op) == self.key]
        if not idx:
            return
        name = self.record_name(self.key)
        if not messagebox.askyesno('Undo edits', f'Remove your {len(idx)} edit{"s" if len(idx) != 1 else ""} to '
                                   f'{name}? It goes back to how the game data (with your mods) has it.',
                                   parent=self):
            return
        self._base = self.snapshot()            # what the form shows now is dropped with the edits
        self.s.remove(idx)
        self.app.edits_changed(f'Removed {len(idx)} edit{"s" if len(idx) != 1 else ""} to {name}.')
