"""The name lists the pages' pickers offer (built on first use from the session's game data)."""


class Choices:
    """name lists of the session's game data, built on first use (call clear() after renames)"""

    def __init__(self, session):
        self.s = session
        self._c = {}

    def clear(self):
        self._c = {}

    def _get(self, name, fn):
        if name not in self._c:
            self._c[name] = fn()
        return self._c[name]

    @property
    def g(self):
        return self.s.game

    def species(self):
        """[((monsno, form), label)] of every valid personal row"""
        def make():
            out = [((0, 0), '000 -')]
            for r in self.g.species_rows():
                m, f = self.g.key_of(r)
                out.append(((m, f), f'{m:03d} {self.g.pokemon_name(m, f)}'))
            return out
        return self._get('species', make)

    def species0(self):
        """[(monsno, label)] species only (form 0), with 0 = none"""
        def make():
            out = [(0, '000 -')]
            for r in self.g.species_rows():
                if r['id'] == r['monsno']:
                    out.append((r['monsno'], f'{r["monsno"]:03d} {self.g.species_name(r["monsno"])}'))
            return out
        return self._get('species0', make)

    def moves(self):
        return self._get('moves', lambda: [(m['wazaNo'], f'{m["wazaNo"]:03d} {self.g.move_name(m["wazaNo"])}')
                                           for m in self.g.moves])

    def items(self):
        return self._get('items', lambda: [(i['no'], f'{i["no"]:04d} {self.g.item_name(i["no"])}') for i in self.g.items])

    def abilities(self):
        return self._get('abilities', lambda: [(k, f'{k:03d} {self.g.ability_name(k)}')
                                               for k in range(self.g.ability_count())])

    def natures(self):
        return self._get('natures', lambda: [(k, self.g.nature_name(k)) for k in range(self.g.nature_count())])

    def types(self):
        return self._get('types', lambda: [(k, self.g.type_name(k)) for k in range(self.g.type_count())])

    def trainer_types(self):
        def make():
            out = [(-1, 'None')]
            for tt in self.g.trainer_types:
                if tt['TrainerID'] >= 0 and tt['LabelTrType']:
                    out.append((tt['TrainerID'], f'{tt["TrainerID"]:03d} {self.g.trainer_type_name(tt["TrainerID"])}'))
            return out
        return self._get('trainer_types', make)

    def trainer_names(self):
        """[(label name, text)] of dp_trainers_name"""
        return self._get('trainer_names', lambda: [(lab['labelName'], f'{self.g.msg.text("dp_trainers_name", lab["labelName"])}'
                                                                      f'  [{lab["labelName"]}]')
                                                   for lab in self.g.msg.labels('dp_trainers_name')])

    def forms_of(self, monsno):
        rows = self.g.forms(monsno)
        return [(self.g.form_of(r), f'{self.g.form_of(r)} {self.g.form_name(monsno, self.g.form_of(r)) or ""}'.strip())
                for r in rows] or [(0, '0')]
