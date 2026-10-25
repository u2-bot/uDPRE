"""Items (ItemTable.Item of Pml/personal_masterdatas), shops (ShopTable of Dpr/masterdatas: Poké Marts, fixed shops,
Battle Point shops) and the Pickup table (MonohiroiTable.MonoHiroi of Dpr/masterdatas).

Items is a record page; Shops and Pickup are whole-table pages with the same unsaved-changes strip and auto-keep: leaving
the page (or the window) keeps what you changed."""
import tkinter as tk
from tkinter import messagebox, ttk

from ... import enums
from ...game import MASTER, PERSONAL
from ...project import set_op
from ..kit import Button, Link, Scroll, Section, Segmented, frame, label, pill
from ..page import Page, RecordPage
from ..theme import C, FONT, text_on
from ..widgets import Picker, Table
from .moves import fields_grid, link_grid, plural, watch

POCKET_COLORS = ['#d9534f', '#e0703a', '#c99a1a', '#4f9d4a', '#5c7fa8', '#7a5cc4', '#c7a033', '#8c6b4f', '#2f6f8f',
                 '#7d8796']
ITEM_VIEWS = [('general', 'General'), ('battle', 'In battle'), ('use', 'When used'), ('flags', 'Flags'),
              ('where', 'Where to get it')]
SHOP_DEFAULT_KEYS = {'FS': ['ItemNo', 'BadgeNum', 'ZoneID'], 'FixedShop': ['ItemNo', 'ShopID'],
                     'BPShop': ['ItemNo', 'NPCID']}


def pocket_name(p):
    return dict(enums.ITEM_POCKETS).get(p, f'pocket {p}')


def strip_bar(owner, master, keep, discard, text='kept when you leave this page'):
    """the orange "Unsaved changes" strip of the whole-table pages (packed by the page's poll)"""
    bar = tk.Frame(master, bg=C['edited_soft'])
    tk.Label(bar, text='●  Unsaved changes', bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9, 'bold')).pack(
        side='left', padx=(12, 0), pady=5)
    tk.Label(bar, text=text, bg=C['edited_soft'], fg='#8a4b00', font=(FONT, 9)).pack(side='left', padx=(8, 0))
    Link(bar, 'Discard', discard, bg=C['edited_soft']).pack(side='right', padx=(8, 12))
    Button(bar, 'Keep  (Ctrl+S)', keep, kind='primary', small=True).pack(side='right', pady=4)
    return bar


# --- Items -------------------------------------------------------------------------------------------------------------
class ItemsPage(RecordPage):
    title = 'Items'
    subtitle = 'Every item: pocket and price, what it does in battle and when used, its flags - and where to get it'
    noun = 'item'
    columns = [('no', 'No.', 48, 'e'), ('name', 'Name', 150, 'w'), ('pocket', 'Pocket', 92, 'w'),
               ('price', 'Price', 62, 'e'), ('bp', 'BP', 44, 'e')]
    list_width = 470

    def extra_left(self, f):
        row = frame(f)
        row.pack(fill='x', pady=(6, 0))
        self.pocket_filter = ttk.Combobox(row, values=['All pockets'] + [n for _, n in enums.ITEM_POCKETS],
                                          state='readonly', width=14, style='Studio.TCombobox')
        self.pocket_filter.current(0)
        self.pocket_filter.pack(side='left')
        self.pocket_filter.bind('<<ComboboxSelected>>', lambda _e: self._apply_filters())
        self.only_edited = tk.BooleanVar()
        ttk.Checkbutton(row, text='Edited only', variable=self.only_edited, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(10, 0))
        self.hide_unused = tk.BooleanVar()
        ttk.Checkbutton(row, text='Hide unused', variable=self.hide_unused, style='Studio.TCheckbutton',
                        command=self._apply_filters).pack(side='left', padx=(8, 0))

    def _apply_filters(self):
        k = self.pocket_filter.current() - 1
        pocket = enums.ITEM_POCKETS[k][0] if k >= 0 else None
        ed, hide = self.only_edited.get(), self.hide_unused.get()

        def pred(key, _vals):
            if ed and key not in self.table.edited:
                return False
            it = self.s.game.item(key)
            if it is None:
                return False
            if hide and it['flags0'] >> enums.ITEM_UNUSED_BIT & 1:
                return False
            return pocket is None or it['fld_pocket'] == pocket
        self.table.filter(pred=pred)
        self._count()

    def rows(self):
        return [(it['no'], self._values(it)) for it in self.s.game.items]

    def row(self, key):
        it = self.s.game.item(key)
        return self._values(it) if it else None

    def _values(self, it):
        g = self.s.game
        unused = it['flags0'] >> enums.ITEM_UNUSED_BIT & 1
        return (f'{it["no"]:04d}', g.item_name(it['no']) + ('  (unused)' if unused else ''), pocket_name(it['fld_pocket']),
                it['price'], it['bp_price'] or '')

    def op_key(self, op):
        if op.get('op') == 'set' and op.get('obj') == 'ItemTable' and op.get('list') == 'Item':
            return op.get('key')
        return None

    def record_name(self, key):
        return self.s.game.item_name(key)

    def search_items(self):
        g = self.s.game
        return [(f'{it["no"]:04d} {g.item_name(it["no"])}', it['no']) for it in g.items]

    # --- record ---------------------------------------------------------------------------------------------------
    def build(self, body):
        c = self.c
        self.views = Segmented(body, ITEM_VIEWS, command=self.switch, value='general')
        self.views.pack(anchor='w', pady=(4, 12))
        self.frames = {v: frame(body) for v, _ in ITEM_VIEWS}
        g_ = self.frames['general']
        s = Section(g_, 'Bag and shops')
        s.pack(fill='x')
        self.bag = self.track(fields_grid(s.body, [
            ('Pocket', 'fld_pocket', 'choice', enums.ITEM_POCKETS, 18), ('Sort index', 'sort', 'int', (0, 65535), 7),
            ('Price', 'price', 'int', None, 9), ('BP price', 'bp_price', 'int', None, 9),
        ], columns=2, label_width=11))
        self.price_text = label(s.body, '', style='Muted.TLabel')
        self.price_text.grid(row=2, column=0, columnspan=4, sticky='w', pady=(6, 0))
        s = Section(g_, 'What kind of item it is')
        s.pack(fill='x', pady=(16, 0))
        self.kind = self.track(fields_grid(s.body, [
            ('Item type', 'type', 'choice', enums.ITEM_TYPES, 18), ('Icon id', 'iconid', 'int', None, 7),
            ('Group', 'group', 'choice', enums.ITEM_GROUPS, 18), ('Group index', 'group_id', 'int', (0, 255), 7),
            ('In the game', 'valid', 'bool'),
        ], columns=2, label_width=11))
        self.kind_text = label(s.body, '', style='Faint.TLabel', wraplength=600, justify='left')
        self.kind_text.grid(row=3, column=0, columnspan=4, sticky='w', pady=(6, 0))
        # in battle
        b = self.frames['battle']
        s = Section(b, 'Moves that use the item', hint='Fling throws it · Natural Gift (berries) · Pluck / Bug Bite eat it')
        s.pack(fill='x')
        self.battle = self.track(fields_grid(s.body, [
            ('Fling power', 'nage_atc', 'int', (0, 255), 6), None,
            ('Natural Gift power', 'sizen_atc', 'int', (0, 255), 6),
            ('Natural Gift type', 'sizen_type', 'choice', c.types() + [(31, 'None')], 14),
            ('Pluck effect', 'tuibamu_eff', 'choice', enums.PLUCK, 14), None,
        ], columns=2, label_width=16))
        s = Section(b, 'When held', hint='the hold-effect id the battle code runs and its value')
        s.pack(fill='x', pady=(16, 0))
        self.held = self.track(fields_grid(s.body, [
            ('Hold effect', 'eqp', 'int', (0, 255), 6), ('Effect value', 'atc', 'int', (0, 255), 6),
        ], columns=2, label_width=16))
        self.battle_text = tk.Label(b, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w', justify='left',
                                    padx=10, pady=6, wraplength=600)
        self.battle_text.pack(fill='x', pady=(14, 0))
        # when used
        u = self.frames['use']
        s = Section(u, 'What using it does')
        s.pack(fill='x')
        self.funcs = self.track(fields_grid(s.body, [
            ('Outside battle', 'field_func', 'choice', enums.FIELD_FUNCS, 20),
            ('In battle', 'battle_func', 'choice', enums.BATTLE_FUNCS, 18),
            ('Work type', 'wk_cmn', 'int', (0, 255), 6),
        ], columns=2, label_width=13))
        self.use_text = tk.Label(s.body, text='', bg=C['soft'], fg=C['text'], font=(FONT, 9), anchor='w',
                                 justify='left', padx=10, pady=6, wraplength=600)
        self.use_text.grid(row=2, column=0, columnspan=4, sticky='we', pady=(8, 0))
        cols = frame(u)
        cols.pack(fill='x', pady=(16, 0))
        left, right = frame(cols), frame(cols)
        left.pack(side='left', anchor='n', padx=(0, 30))
        right.pack(side='left', anchor='n')
        s = Section(left, 'Healing')
        s.pack(fill='x')
        self.heal = self.track(fields_grid(s.body, [
            ('HP restored', 'wk_prm_hp_rcv', 'int', (0, 255), 6), ('PP restored', 'wk_prm_pp_rcv', 'int', (0, 255), 6),
        ], columns=1, label_width=12))
        s = Section(left, 'Stat stages in battle')
        s.pack(fill='x', pady=(14, 0))
        self.boost = self.track(fields_grid(s.body, [
            ('Critical ratio', 'wk_critical_up', 'int', (0, 255), 6), ('Attack', 'wk_atc_up', 'int', (0, 255), 6),
            ('Defense', 'wk_def_up', 'int', (0, 255), 6), ('Sp. Atk', 'wk_spa_up', 'int', (0, 255), 6),
            ('Sp. Def', 'wk_spd_up', 'int', (0, 255), 6), ('Speed', 'wk_agi_up', 'int', (0, 255), 6),
            ('Accuracy', 'wk_hit_up', 'int', (0, 255), 6),
        ], columns=1, label_width=12))
        s = Section(right, 'Effort values (EVs)')
        s.pack(fill='x')
        self.evs = self.track(fields_grid(s.body, [
            ('HP', 'wk_prm_hp_exp', 'int', (-128, 127), 6), ('Attack', 'wk_prm_pow_exp', 'int', (-128, 127), 6),
            ('Defense', 'wk_prm_def_exp', 'int', (-128, 127), 6), ('Sp. Atk', 'wk_prm_spa_exp', 'int', (-128, 127), 6),
            ('Sp. Def', 'wk_prm_spd_exp', 'int', (-128, 127), 6), ('Speed', 'wk_prm_agi_exp', 'int', (-128, 127), 6),
        ], columns=1, label_width=12))
        s = Section(right, 'Friendship change', hint='by current friendship')
        s.pack(fill='x', pady=(14, 0))
        self.friend = self.track(fields_grid(s.body, [
            ('0 - 99', 'wk_friend1', 'int', (-128, 127), 6), ('100 - 199', 'wk_friend2', 'int', (-128, 127), 6),
            ('200 - 255', 'wk_friend3', 'int', (-128, 127), 6),
        ], columns=1, label_width=12))
        # flags
        fl = self.frames['flags']
        s = Section(fl, 'Item flags', hint='"In the game" is on the General view')
        s.pack(fill='x')
        self.flags = self.track(fields_grid(s.body, [('', 'flags0', 'bits', enums.ITEM_FLAGS, 2)], columns=1,
                                            label_width=1))
        # where to get it
        self.where = frame(self.frames['where'])
        self.where.pack(fill='both', expand=True)
        self.forms = (self.bag, self.kind, self.battle, self.held, self.funcs, self.heal, self.boost, self.evs,
                      self.friend, self.flags)
        for fs in self.forms:
            watch(fs, self._live)
        self.switch('general')

    def switch(self, view):
        self.view = view
        for v, f in self.frames.items():
            if v == view:
                f.pack(fill='both', expand=True)
            else:
                f.pack_forget()
        if view == 'where' and self.key is not None:
            self._where()
        if self.scroller is not None:
            self.scroller.top()

    def show(self, n):
        g = self.s.game
        it = g.item(n)
        rec = dict(it, valid=0 if it['flags0'] >> enums.ITEM_UNUSED_BIT & 1 else 1)
        for fs in self.forms:
            fs.load(rec)
        pp = self.pill_parent()
        p = it['fld_pocket']
        pills = [pill(pp, pocket_name(p), POCKET_COLORS[p] if 0 <= p < len(POCKET_COLORS) else '#7d8796')]
        if it['group'] == 4:
            pills.append(pill(pp, f'TM bit {it["group_id"]}', C['accent_soft'], C['accent']))
        if not rec['valid']:
            pills.append(pill(pp, 'not in the game', C['danger_soft'], C['danger']))
        self.set_header(g.item_name(n), f'No. {n:04d} · ' + dict(enums.ITEM_TYPES).get(it['type'], f'type {it["type"]}'),
                        pills)
        self._live()
        if getattr(self, 'view', None) == 'where':
            self._where()

    def _vals(self):
        v = {}
        for fs in self.forms:
            v.update(fs.values())
        return v

    def _live(self):
        try:
            v = self._vals()
        except tk.TclError:
            return
        g = self.s.game
        price, bp = v.get('price', 0), v.get('bp_price', 0)
        t = (f'Shops sell it for {price:,}; you get {price // 2:,} when you sell it.' if price else
             'Price 0: it cannot be sold to a shop.')
        if bp:
            t += f'  Battle Point shops: {bp} BP.'
        self.price_text.config(text=t)
        k = []
        if v.get('group') == 4:
            k.append(f'A TM: Pokémon learn it through compatibility bit {v.get("group_id", 0)} (the TMs page).')
        if not v.get('valid', 1):
            k.append('Not in the game: the game treats it as an unused item.')
        self.kind_text.config(text='  '.join(k))
        b = []
        if v.get('nage_atc'):
            b.append(f'Fling: {v["nage_atc"]} power.')
        if v.get('sizen_atc'):
            b.append(f'Natural Gift: {v["sizen_atc"]} power, {g.type_name(v.get("sizen_type", 0)) if v.get("sizen_type") != 31 else "no"} type.')
        if v.get('tuibamu_eff'):
            b.append(f'Pluck / Bug Bite give the {dict(enums.PLUCK).get(v["tuibamu_eff"])} Berry effect.')
        if v.get('eqp'):
            b.append(f'Held: hold effect {v["eqp"]} (value {v.get("atc", 0)}).')
        self.battle_text.config(text=' '.join(b) or 'It does nothing special in battle: no Fling power, no Natural Gift, '
                                                    'no hold effect.')
        u = []
        ff, bf = v.get('field_func', 0), v.get('battle_func', 0)
        if ff:
            u.append(f'Outside battle: {dict(enums.FIELD_FUNCS).get(ff, ff)}.')
        if bf:
            u.append(f'In battle: {dict(enums.BATTLE_FUNCS).get(bf, bf)}.')
        if v.get('wk_prm_hp_rcv'):
            u.append(f'Restores {v["wk_prm_hp_rcv"]} HP.')
        if v.get('wk_prm_pp_rcv'):
            u.append(f'Restores {v["wk_prm_pp_rcv"]} PP.')
        st = [(n, v.get(f)) for n, f in (('critical ratio', 'wk_critical_up'), ('Attack', 'wk_atc_up'),
                                          ('Defense', 'wk_def_up'), ('Sp. Atk', 'wk_spa_up'), ('Sp. Def', 'wk_spd_up'),
                                          ('Speed', 'wk_agi_up'), ('accuracy', 'wk_hit_up')) if v.get(f)]
        if st:
            u.append('Raises ' + ', '.join(f'{n} +{x}' for n, x in st) + '.')
        ev = [(n, v.get(f)) for n, f in (('HP', 'wk_prm_hp_exp'), ('Attack', 'wk_prm_pow_exp'), ('Defense', 'wk_prm_def_exp'),
                                          ('Sp. Atk', 'wk_prm_spa_exp'), ('Sp. Def', 'wk_prm_spd_exp'),
                                          ('Speed', 'wk_prm_agi_exp')) if v.get(f)]
        if ev:
            u.append('EVs: ' + ', '.join(f'{n} {x:+d}' for n, x in ev) + '.')
        fr = [v.get(f, 0) for f in ('wk_friend1', 'wk_friend2', 'wk_friend3')]
        if any(fr):
            u.append('Friendship ' + ' / '.join(f'{x:+d}' for x in fr) + ' (low / mid / high).')
        self.use_text.config(text=' '.join(u) or 'Using it does nothing by itself (no function, no values).')

    def collect(self, n):
        g = self.s.game
        it = g.item(n)
        new = self._vals()
        valid = new.pop('valid', 1)
        flags = new.get('flags0', it['flags0'])
        flags = (flags & ~(1 << enums.ITEM_UNUSED_BIT)) | ((0 if valid else 1) << enums.ITEM_UNUSED_BIT)
        new['flags0'] = flags & 0xFFFFFFFF if it['flags0'] >= 0 else flags
        return [set_op(g, PERSONAL, 'ItemTable', 'Item', it, f, v) for f, v in new.items() if f in it and it[f] != v]

    # --- where to get it ------------------------------------------------------------------------------------------
    def _where(self):
        box = self.where
        for w in box.winfo_children():
            w.destroy()
        g = self.s.game
        n = self.key
        shops = g.shops
        found = False
        fs = [r for r in shops.get('FS', []) if r.get('ItemNo') == n]
        if fs:
            found = True
            s = Section(box, 'Poké Marts', actions=[('Open the shops', lambda: self.app.show('shops', 'FS'))])
            s.pack(fill='x', pady=(0, 14))
            for r in fs:
                where = 'every Poké Mart' if r.get('ZoneID', -1) < 0 else g.zone_name(r['ZoneID'])
                b = r.get('BadgeNum', 0)
                label(s.body, f'•  {where}, ' + (f'from {plural(b, "badge")}' if b else 'from the start')).pack(anchor='w')
        for field, title, kf, word in (('FixedShop', 'Fixed shops', 'ShopID', 'shop'),
                                       ('BPShop', 'Battle Point shops', 'NPCID', 'clerk')):
            rows = [r for r in shops.get(field, []) if r.get('ItemNo') == n]
            if rows:
                found = True
                s = Section(box, title, actions=[('Open the shops', lambda f=field: self.app.show('shops', f))])
                s.pack(fill='x', pady=(0, 14))
                ids = sorted({r.get(kf, 0) for r in rows})
                label(s.body, f'{word.capitalize()} id{"s" if len(ids) > 1 else ""} ' + ', '.join(map(str, ids)) +
                      (f' · {g.item(n)["bp_price"]} BP' if field == 'BPShop' and g.item(n) else '')).pack(anchor='w')
        pk = [(i, r) for i, r in enumerate(g.pickup) if r['ID'] == n]
        if pk and n:
            found = True
            s = Section(box, 'Pickup', actions=[('Open Pickup', lambda: self.app.show('pickup'))])
            s.pack(fill='x', pady=(0, 14))
            for i, r in pk:
                br = [k for k, x in enumerate(r['Ratios']) if x]
                label(s.body, f'•  row {i + 1}: in {plural(len(br), "level bracket")}, up to {max(r["Ratios"] or [0])}%'
                      ).pack(anchor='w')
        tms = [(i, t) for i, t in enumerate(g.tms) if t['itemNo'] == n]
        if tms:
            found = True
            s = Section(box, 'TM')
            s.pack(fill='x', pady=(0, 14))
            for i, t in tms:
                Link(s.body, f'Teaches {g.move_name(t["wazaNo"])} (machine {t["machineNo"]})',
                     lambda i=i: self.app.show('tms', i)).pack(anchor='w')
        held = []
        if n:
            for r in g.species_rows():
                slots = [lab for f, lab in (('item1', '50%'), ('item2', '5%'), ('item3', 'third slot')) if r.get(f) == n]
                if slots:
                    held.append((g.key_of(r), slots))
        if held:
            found = True
            s = Section(box, 'Held by wild Pokémon', hint=plural(len(held), 'Pokémon', 'Pokémon') + ' - click to open')
            s.pack(fill='x', pady=(0, 14))
            link_grid(s.body, [(f'{g.pokemon_name(*k)} ({", ".join(sl)})', lambda k=k: self.app.show('pokemon', k))
                               for k, sl in held], columns=3, cap=120, more_text='more Pokémon')
        if not found:
            label(box, 'No shop sells it, Pickup does not find it and no wild Pokémon holds it. (Items placed on the map '
                  'or given in events are in the game\'s scripts, not here.)', style='Muted.TLabel', wraplength=600,
                  justify='left').pack(anchor='w')


# --- whole-table pages -------------------------------------------------------------------------------------------------
class TablePage(Page):
    """a page that edits whole tables: an "Unsaved changes" strip while it differs from the data, Keep / Discard, and
    auto-keep when the page (or the window) is left. Subclasses: build_body(frame), load(), snapshot(), collect(),
    op_match(op), what (messages)."""
    what = 'this page'

    def build_page(self):
        self._base = None
        top = frame(self)
        top.pack(fill='x', padx=24, pady=(12, 0))
        self.top = top
        self.undo_link = Link(top, '', self.undo_all)
        self.undo_link.pack(side='right')
        self.strip = strip_bar(self, self, self.keep, self.discard)
        self._strip_after = tk.Frame(self, height=1, bg=C['line'])
        self._strip_after.pack(fill='x', padx=24, pady=(8, 0))
        self.error = ttk.Label(self, text='', style='Error.TLabel')
        self.error.pack(anchor='w', padx=24)
        self.main = frame(self)
        self.main.pack(fill='both', expand=True, padx=24, pady=(4, 12))
        self.build_body(self.main)
        self.load()
        self._poll()

    def build_body(self, f):
        pass

    def snapshot(self):
        return ()

    def collect(self):
        return []

    def op_match(self, op):
        return False

    def on_snapshot_change(self):
        pass

    def load(self):
        """data -> widgets (subclasses fill, then call super().load())"""
        self.error.config(text='')
        self._base = self.snapshot()
        self._last = self._base
        self._undo_text()
        self.on_snapshot_change()

    def _ops(self):
        return [i for i, op in enumerate(self.s.project.ops) if self.op_match(op)]

    def _undo_text(self):
        n = len(self._ops())
        self.undo_link.config(text=f'Undo my {n} edit{"s" if n != 1 else ""} to {self.what}' if n else '')

    def dirty(self):
        if self._base is None:
            return False
        try:
            return self.snapshot() != self._base
        except tk.TclError:
            return False

    def _poll(self):
        try:
            snap = self.snapshot()
            d = self._base is not None and snap != self._base
            if snap != getattr(self, '_last', None):
                self._last = snap
                self.on_snapshot_change()
            if d and not self.strip.winfo_ismapped():
                self.strip.pack(fill='x', padx=24, pady=(8, 0), before=self._strip_after)
            elif not d and self.strip.winfo_ismapped():
                self.strip.pack_forget()
        except tk.TclError:
            return
        self.after(400, self._poll)

    def keep(self):
        if not self.built or not self.dirty():
            return True
        try:
            ops = self.collect()
        except ValueError as e:
            self.error.config(text=f'Not kept: {e}')
            return False
        n = self.s.commit(ops)
        self.app.changed(f'Kept {n} change{"s" if n != 1 else ""} to {self.what}.' if n else
                         f'Nothing changed in {self.what}.')
        self.load()
        return True

    def discard(self):
        self.load()

    def leave(self):
        return self.keep() if self.built else True

    def refresh(self):
        if self.built:
            self.load()

    def undo_all(self):
        idx = self._ops()
        if not idx:
            return
        if not messagebox.askyesno('Undo edits', f'Remove your {len(idx)} edit{"s" if len(idx) != 1 else ""} to '
                                   f'{self.what}? It goes back to how the game data (with your mods) has it.',
                                   parent=self):
            return
        self._base = self.snapshot()
        self.s.remove(idx)
        self.app.edits_changed(f'Removed {len(idx)} edit{"s" if len(idx) != 1 else ""} to {self.what}.')


# --- Shops -------------------------------------------------------------------------------------------------------------
SHOP_LISTS = [('FS', 'Poké Marts'), ('FixedShop', 'Fixed shops'), ('BPShop', 'Battle Point shops')]
SHOP_HINTS = {
    'FS': 'What Poké Marts sell: an item appears once you have the badges it needs; zone "All" = every Poké Mart, '
          'a zone = only the mart there.',
    'FixedShop': 'Fixed shops (the department store counters, special clerks): each row is one item of the shop with '
                 'that id.',
    'BPShop': 'Battle Point shops (Battle Park exchange): each row is one item of the clerk with that NPC id; its price '
              'is the item\'s BP price (Items page).',
}


class ShopsPage(TablePage):
    title = 'Shops'
    subtitle = 'What every Poké Mart, fixed shop and Battle Point shop sells'
    what = 'the shops'

    def build_body(self, f):
        g = self.s.game
        from ...zonecodes import CODES
        zones = sorted({r['ZoneID'] for r in g.shops['FS']} | set(range(len(CODES))))
        self.zchoices = [(-1, 'All (every Poké Mart)')] + [(z, f'{z:03d} {g.zone_name(z)}') for z in zones if z >= 0]
        self.views = Segmented(self.top, SHOP_LISTS, command=self.switch, value='FS')
        self.views.pack(side='left')
        self.hint = label(f, '', style='Muted.TLabel', wraplength=980, justify='left')
        self.hint.pack(anchor='w', pady=(0, 8))
        cols = frame(f)
        cols.pack(fill='both', expand=True)
        left = frame(cols)
        left.pack(side='left', fill='both', expand=True)
        tk.Frame(cols, width=1, bg=C['line']).pack(side='left', fill='y', padx=16)
        right = frame(cols, width=380)
        right.pack(side='left', fill='y')
        right.pack_propagate(False)
        self.tables = {}
        self.table_frames = {}
        items = self.c.items()
        for field, cols_, new in [
            ('FS', [('Item', 'choice', items, 240), ('Badges needed', 'int', (0, 8), 100),
                    ('Zone', 'choice', self.zchoices, 260)], lambda: [0, 0, -1]),
            ('FixedShop', [('Item', 'choice', items, 280), ('Shop id', 'int', (0, 65535), 100)], lambda: [0, 0]),
            ('BPShop', [('Item', 'choice', items, 280), ('NPC id', 'int', (0, 65535), 100)], lambda: [0, 0]),
        ]:
            tf = frame(left)
            t = Table(tf, cols_, height=20, new_row=new)
            t.pack(fill='both', expand=True)
            label(tf, 'Double-click a cell to change it · + Add puts a row under the selected one · rows with no item are '
                  'dropped when kept · the order is the order the shop lists them', style='Faint.TLabel',
                  wraplength=560, justify='left').pack(anchor='w', pady=(4, 0))
            rows = g.shops.get(field) or []
            keys = list(rows[0].keys()) if rows else list(SHOP_DEFAULT_KEYS[field])
            self.tables[field] = (t, keys)
            self.table_frames[field] = tf
        head = frame(right)
        head.pack(fill='x')
        self.sum_title = label(head, '', style='Section.TLabel')
        self.sum_title.pack(side='left')
        tk.Frame(right, height=1, bg=C['line']).pack(fill='x', pady=(3, 6))
        sc = Scroll(right)
        sc.pack(fill='both', expand=True)
        self.summary = sc.body
        self.view = 'FS'
        self.switch('FS')

    def switch(self, field):
        self.view = field
        for f, tf in self.table_frames.items():
            if f == field:
                tf.pack(fill='both', expand=True)
            else:
                tf.pack_forget()
        self.hint.config(text=SHOP_HINTS[field])
        self.on_snapshot_change()

    def goto(self, key):
        self.ensure()
        if key in self.tables:
            self.views.pick(key)

    def load(self):
        g = self.s.game
        for field, (t, keys) in self.tables.items():
            t.set_rows([[r[k] for k in keys] for r in g.shops.get(field) or []])
        self._labels()
        super().load()

    def _labels(self):
        ed = {op.get('field') for op in self.s.project.ops if self.op_match(op)}
        g = self.s.game
        for field, title in SHOP_LISTS:
            n = len(g.shops.get(field) or [])
            self.views.items[field].config(text=f'{title}  {n}' + ('  ●' if field in ed else ''))

    def snapshot(self):
        return tuple(t.snapshot() for t, _k in self.tables.values())

    def op_match(self, op):
        return op.get('op') == 'set' and op.get('obj') == 'ShopTable' and op.get('list') is None and \
            op.get('field') in self.tables

    def collect(self):
        g = self.s.game
        ops = []
        for field, (t, keys) in self.tables.items():
            rows = [dict(zip(keys, (int(v) for v in r))) for r in t.get_rows() if r and r[0]]
            if rows != g.shops[field]:
                ops.append(set_op(g, MASTER, 'ShopTable', None, None, field, rows))
        return ops

    def on_snapshot_change(self):
        if not hasattr(self, 'summary'):
            return
        for w in self.summary.winfo_children():
            w.destroy()
        g = self.s.game
        field = self.view
        t, _keys = self.tables[field]
        rows = [r for r in t.get_rows() if r and r[0]]
        self.sum_title.config(text=f'What it sells  ·  {plural(len(rows), "item")}')
        groups = {}
        if field == 'FS':
            for it, badges, zone in rows:
                groups.setdefault((0 if zone < 0 else 1, zone, badges), []).append(it)
        else:
            for it, sid in rows:
                groups.setdefault((0, sid, 0), []).append(it)
        last_zone = object()
        for (kind, zone, badges), items in sorted(groups.items()):
            if field == 'FS':
                if zone != last_zone:
                    last_zone = zone
                    label(self.summary, 'Every Poké Mart' if zone < 0 else f'Only at {g.zone_name(zone)}',
                          style='Section.TLabel').pack(anchor='w', pady=(8, 2))
                head = 'From the start' if badges == 0 else f'With {plural(badges, "badge")}'
            else:
                head = ('Shop' if field == 'FixedShop' else 'Clerk (NPC)') + f' {zone}'
            label(self.summary, f'{head}  ·  {len(items)}', style='Muted.TLabel').pack(anchor='w', pady=(6, 0))
            names = ', '.join(g.item_name(i) for i in items)
            label(self.summary, names, wraplength=340, justify='left').pack(anchor='w')


# --- Pickup ------------------------------------------------------------------------------------------------------------
def _mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02x}' for x, y in zip(pa, pb))


def heat(v):
    if v <= 0:
        return C['bg']
    return _mix('#e8effd', '#1f4fb8', min(v, 40) / 40)


class PickupPage(TablePage):
    title = 'Pickup'
    subtitle = 'What the Pickup ability finds: the chance of each item in each level bracket'
    what = 'the Pickup table'

    def build_body(self, f):
        g = self.s.game
        self.n = max((len(r['Ratios']) for r in g.pickup), default=10)     # 10 brackets in the dump; mods may differ
        label(self.top, 'Each column is a level bracket of the Pokémon with Pickup; a cell is the chance (out of 100) '
              'that it finds that item. Every bracket should add up to 100.', style='Muted.TLabel').pack(side='left')
        cell_w = 50 if self.n <= 10 else 44

        def columns(grid):
            grid.columnconfigure(0, minsize=30)
            grid.columnconfigure(1, minsize=196)
            for k in range(self.n):
                grid.columnconfigure(2 + k, minsize=cell_w)
        # fixed head: bracket names and the per-bracket totals (always in view), then the rows scroll under it
        head = frame(f)
        head.pack(fill='x')
        columns(head)
        heads = ['', 'Item'] + [(f'Lv {10 * k + 1}-{10 * k + 10}' if self.n == 10 else f'Bracket {k + 1}')
                                for k in range(self.n)]
        for col, h in enumerate(heads):
            label(head, h, style='Faint.TLabel', anchor='w' if col < 2 else 'center').grid(
                row=0, column=col, sticky='we', padx=1, pady=(0, 3))
        label(head, 'Total', style='Section.TLabel').grid(row=1, column=1, sticky='e', padx=(0, 10))
        self.totals = []
        for k in range(self.n):
            t = tk.Label(head, text='', font=(FONT, 9, 'bold'), bg=C['bg'], padx=2, pady=3)
            t.grid(row=1, column=2 + k, padx=1, sticky='we')
            self.totals.append(t)
        self.total_note = label(head, '', style='Muted.TLabel', wraplength=900, justify='left')
        self.total_note.grid(row=2, column=1, columnspan=1 + self.n, sticky='w', pady=(4, 0))
        tk.Frame(f, height=1, bg=C['line2']).pack(fill='x', pady=(6, 4))
        sc = Scroll(f)
        sc.pack(fill='both', expand=True)
        grid = sc.body
        columns(grid)
        self.pickers, self.cells = [], []
        for i, r in enumerate(g.pickup):
            label(grid, str(i + 1), style='Faint.TLabel').grid(row=i, column=0, sticky='e', padx=(0, 6))
            p = Picker(grid, self.c.items(), width=24)
            p.grid(row=i, column=1, sticky='w', padx=(0, 8), pady=1)
            self.pickers.append(p)
            row = []
            for k in range(self.n):
                e = tk.Entry(grid, width=4, justify='center', relief='flat', font=(FONT, 9), highlightthickness=1,
                             highlightbackground=C['line'], highlightcolor=C['accent'], disabledbackground=C['soft'])
                e.grid(row=i, column=2 + k, padx=1, pady=1, ipady=2, sticky='we')
                if k >= len(r['Ratios']):
                    e.configure(state='disabled')
                e.bind('<KeyRelease>', lambda _e, e_=e: (self._paint(e_), self.on_snapshot_change()))
                e.bind('<FocusOut>', lambda _e, e_=e: self._paint(e_))
                row.append(e)
            self.cells.append(row)
        label(grid, 'Type a chance in a cell (0-255); darker = likelier. Item 0 (None) marks the end of the list.',
              style='Faint.TLabel').grid(row=len(g.pickup), column=1, columnspan=1 + self.n, sticky='w', pady=(8, 0))
        for p in self.pickers:
            p.bind('<<ComboboxSelected>>', lambda _e: self.on_snapshot_change(), add='+')

    def load(self):
        g = self.s.game
        for i, r in enumerate(g.pickup):
            if i >= len(self.pickers):
                break
            self.pickers[i].set_value(r['ID'])
            for k, e in enumerate(self.cells[i]):
                st = e.cget('state')
                e.configure(state='normal')
                e.delete(0, 'end')
                e.insert(0, str(r['Ratios'][k]) if k < len(r['Ratios']) else '')
                e.configure(state=st)
                self._paint(e)
        super().load()

    def _num(self, e):
        t = e.get().strip()
        try:
            return int(float(t)) if t else 0
        except ValueError:
            return None

    def _paint(self, e):
        if e.cget('state') == 'disabled':
            return
        v = self._num(e)
        if v is None:
            e.configure(bg=C['danger_soft'], fg=C['danger'])
            return
        bg = heat(v)
        e.configure(bg=bg, fg=text_on(bg) if v > 0 else C['faint'])

    def snapshot(self):
        return (tuple(repr(p.get_value()) for p in self.pickers),
                tuple(tuple(e.get() for e in row) for row in self.cells))

    def op_match(self, op):
        return op.get('op') == 'set' and op.get('obj') == 'MonohiroiTable'

    def on_snapshot_change(self):
        if not hasattr(self, 'totals'):
            return
        bad = []
        ends = 0
        for k in range(self.n):
            tot = 0
            for i, row in enumerate(self.cells):
                if self.pickers[i].get_value() == 0:
                    continue
                v = self._num(row[k]) if row[k].cget('state') != 'disabled' else 0
                tot += v or 0
            ok = tot == 100
            self.totals[k].config(text=str(tot), bg=C['ok_soft'] if ok else C['danger_soft'],
                                  fg=C['ok'] if ok else C['danger'])
            if not ok:
                bad.append(k)
        for i, p in enumerate(self.pickers):
            if p.get_value() == 0:
                ends += 1
        note = ('Every bracket adds up to 100.' if not bad else
                f'{plural(len(bad), "bracket")} do{"es" if len(bad) == 1 else ""} not add up to 100 '
                f'({", ".join(self._bracket(k) for k in bad)}): the leftover chance finds nothing, an excess is never '
                f'reached.')
        if ends:
            note += (f'  {plural(ends, "row")} with item 0 (None) {"is" if ends == 1 else "are"} the end of the list and '
                     f'not counted.')
        self.total_note.config(text=note)

    def _bracket(self, k):
        return f'Lv {10 * k + 1}-{10 * k + 10}' if self.n == 10 else f'bracket {k + 1}'

    def collect(self):
        g = self.s.game
        rows = []
        for i, r in enumerate(g.pickup):
            item = self.pickers[i].get_value()
            if item is None:
                raise ValueError(f'row {i + 1}: "{self.pickers[i].get()}" is no item')
            vals = []
            for k, e in enumerate(self.cells[i]):
                if k >= len(r['Ratios']):
                    vals.append(0)
                    continue
                v = self._num(e)
                if v is None:
                    raise ValueError(f'row {i + 1}, {self._bracket(k)}: "{e.get()}" is not a number')
                vals.append(max(0, min(255, v)))
            rows.append([item] + vals)
        ops = []
        for i, (r, new) in enumerate(zip(g.pickup, rows)):
            if r['ID'] != new[0]:
                ops.append(set_op(g, MASTER, 'MonohiroiTable', 'MonoHiroi', r, 'ID', int(new[0]), key=i))
            ratios = [int(x) for x in new[1:1 + len(r['Ratios'])]]
            if list(r['Ratios']) != ratios:
                ops.append(set_op(g, MASTER, 'MonohiroiTable', 'MonoHiroi', r, 'Ratios', ratios, key=i))
        return ops
