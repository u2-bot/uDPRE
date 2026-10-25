"""Randomizer analysis of the loaded data: what is valid, the evolution families, and the default settings derived from the
data (so the defaults follow the mods of the stack: Luminescent's 1,010 species, 6,000 trainers ...).

Validity (used for every pool the randomizer draws from; ids outside these are never produced):
  Pokemon (a personal row): valid_flag != 0 and id > 0; a species = its form-0 row is valid (Luminescent keeps 1,010
  species rows but flags 514 of them valid - the others are never used by its data either).
  Move: isValid != 0 and wazaNo > 0. Item: a row of ItemTable whose flags0 bit 31 (inactive) is clear and no > 0;
  "buyable" = also price > 0. TM: a tm_list() entry (item group 4) whose item is active. Ability: 0 < id < the
  ss_tokusei label count. Type: 0 <= id < type count (names by LABEL ORDER: ss_typename has no TYPENAME_009 label, so
  label numbers are not type ids). Nature 0..24. Growth rate 0..5 and < GrowTable rows. Damage category 1 / 2.
Family data (rebuilt after the evolution options): next/previous stages from every species-changing evolution path
(destination row = (destMonsNo, destFormNo)); within a species, form B is "superior" to A when BST(B) - BST(A) >= 30;
legendary = every form of the species listed in FieldEncountTable_d.legendpoke; expected evolution levels
(wild, trainer) per row from its methods, never-evolves = 65535.
Default settings: numeric options -> Normal Relative with std/2 of the observations (the other five types in
'dist_alt'); item options -> Empirical with the observed counts ('dist_alt' = Uniform over the valid entities);
percentages measured; every option off.
"""
import collections

from . import distributions as dist
from .game import STATS

NEVER = 65535
# evolution methods -> how their expected level is reached
M_FRIEND = {1, 2, 3, 21, 29, 43}
M_LEVEL = {4, 9, 10, 11, 12, 13, 14, 23, 24, 28, 32, 33, 34, 36, 37, 38, 40, 41, 46, 47}
M_ITEM = {5, 8, 17, 18, 22, 25, 26, 27, 39, 42, 44, 45}
M_TRADE = {6, 7}
M_BEAUTY = {16}
M_HOLD = {19, 20, 30, 31}
AFFINITY_VALUES = [0, 2, 4, 8]
DAMAGE_CATEGORIES = [(0, 'Status'), (1, 'Physical'), (2, 'Special')]
GROWTH_NAMES = ['Medium Fast', 'Erratic', 'Fluctuating', 'Medium Slow', 'Fast', 'Slow']
AFFINITY_NAMES = {0: '0x', 2: '1/2x', 4: '1x', 8: '2x'}
SLOT_LISTS = ['ground_mons', 'tairyo', 'day', 'night', 'swayGrass', 'water_mons', 'boro_mons', 'ii_mons', 'sugoi_mons']
GBA_LISTS = ['gbaRuby', 'gbaSapp', 'gbaEme', 'gbaFire', 'gbaLeaf']


def type_names(game):
    """type names by type id = ss_typename label ORDER"""
    names = game.msg.by_index('ss_typename')
    n = max(18, len(names))
    return [names[i] if i < len(names) else f'type {i}' for i in range(n)]


def slot_count(prow):
    n = 0
    while f'P{n + 1}MonsNo' in prow:
        n += 1
    return n


def filled_slots(prow):
    """-> ['P1', ...] prefixes of the party slots that hold a Pokemon"""
    return [f'P{s}' for s in range(1, slot_count(prow) + 1) if prow.get(f'P{s}MonsNo', 0)]


class Pools:
    """Validity sets, lookups and family data of the current game state."""

    def __init__(self, game):
        self.g = game
        P = game.personal
        self.rows = {r['id']: r for r in P}
        self.valid_pids = sorted(r['id'] for r in P if r['valid_flag'] and r['id'] > 0)
        self.valid_pid_set = set(self.valid_pids)
        self.species = sorted(r['monsno'] for r in P if r['id'] == r['monsno'] and r['monsno'] > 0)
        self.valid_species = sorted(m for m in self.species if self.rows[m]['valid_flag'])
        self.valid_species_set = set(self.valid_species)
        self.species_forms = {m: game.forms(m) for m in self.species}
        self.form_count = {m: max(1, self.rows[m]['form_max']) for m in self.species}
        M = game.moves
        self.move_rows = {m['wazaNo']: m for m in M}
        self.valid_moves = sorted(m['wazaNo'] for m in M if m['isValid'] and m['wazaNo'] > 0)
        self.valid_move_set = set(self.valid_moves)
        self.item_rows = {it['no']: it for it in game.items}
        self.active_items = sorted(n for n, it in self.item_rows.items() if n > 0 and not (it['flags0'] >> 31) & 1)
        self.active_item_set = set(self.active_items)
        self.buyable_items = [n for n in self.active_items if self.item_rows[n]['price'] > 0]
        self.buyable_item_set = set(self.buyable_items)
        self.held_item_set = self.active_item_set | {0}
        self.ability_count = game.ability_count()
        self.valid_abilities = list(range(1, self.ability_count))
        self.valid_ability_set = set(self.valid_abilities)
        self.type_names = type_names(game)
        self.type_count = len(self.type_names)
        self.types = list(range(self.type_count))
        self.natures = list(range(25))
        self.growth = [i for i in range(len(GROWTH_NAMES)) if i < len(game.grow)]
        self.tms = [(bit, t, it) for bit, t, it in game.tm_list() if not (it['flags0'] >> 31) & 1]
        self.tm_bit_count = game.tm_set_size()      # 128, or 256 with a mod's ExtraData TM learnsets
        self.egg_index = {(r['no'], r['formNo']): r for r in game.egg_moves}
        self.legend_species = set()
        for v, e in game.encounter_files():
            if v == 'd':
                self.legend_species = {lp['monsNo'] & 0xffff for lp in e.get('legendpoke', [])}
        self.form_encounters = any(s['monsNo'] > 0xffff for _v, e in game.encounter_files() for z in e['table']
                                   for k in SLOT_LISTS + GBA_LISTS for s in z.get(k, []))
        ug = [r for _n, t in game.ug_tables() for r in t['table']]
        self.ug_form16 = any(r['monsno'] > 0xffff for r in ug)
        self.ug_versions_free = any(r['version'] < 1 or r['version'] > 3 for r in ug)
        # a mod's hint file (session.mod_hints) declares the variants outright (the data may not show them)
        hints = getattr(game, 'hints', None) or {}
        for attr, key in (('form_encounters', 'uint16EncounterTables'), ('ug_form16', 'uint16UgTables'),
                          ('ug_versions_free', 'ugVersionsUnbounded')):
            if key in hints:
                setattr(self, attr, bool(hints[key]))
        self.family()

    # --- validity --------------------------------------------------------------------------------------------------
    def valid_row(self, row):
        return row is not None and row['valid_flag'] != 0 and row['id'] > 0

    def row_of(self, monsno, form=0):
        return self.g.row(monsno, form)

    def types_of(self, row):
        return {row['type1'], row['type2']}

    def move_type(self, waza):
        m = self.move_rows.get(waza)
        return m['type'] if m else -1

    def is_legend(self, monsno):
        return monsno in self.legend_species

    # --- family ----------------------------------------------------------------------------------------------------
    def family(self):
        """next / prev stages, superior / inferior forms, expected evolution levels"""
        g = self.g
        nxt = collections.defaultdict(set)
        prv = collections.defaultdict(set)
        self.paths = {}
        for r in g.personal:
            if r['id'] <= 0:
                continue
            ps = []
            for e in g.evolution_list(r):
                m, _param, dm, df, lvl = e
                if dm <= 0 or dm == r['monsno']:
                    continue
                d = g.row(dm, df)
                if d is None:
                    continue
                ps.append((m, lvl, d['id']))
                if self.valid_row(d) and self.valid_row(r):
                    nxt[r['id']].add(d['id'])
                    prv[d['id']].add(r['id'])
            self.paths[r['id']] = ps
        self.next = {k: sorted(v) for k, v in nxt.items()}
        self.prev = {k: sorted(v) for k, v in prv.items()}
        sup = collections.defaultdict(set)
        inf = collections.defaultdict(set)
        for m, rows in self.species_forms.items():
            rows = [r for r in rows if self.valid_row(r)]
            for a in rows:
                for b in rows:
                    if a is not b and g.bst(b) - g.bst(a) >= 30:
                        sup[a['id']].add(b['id'])
                        inf[b['id']].add(a['id'])
        self.superior = {k: sorted(v) for k, v in sup.items()}
        self.inferior = {k: sorted(v) for k, v in inf.items()}
        self._levels = {}
        self.next_lv = {}
        self.past_lv = {}
        for pid in sorted(self.paths):
            pair = self._evo_pair(pid, set())
            self.next_lv[pid] = pair if pair is not None else (NEVER, NEVER)
        for pid, ps in self.paths.items():
            pair = self._levels.get(pid) or (0, 0)
            for _m, _l, d in ps:
                cur = self.past_lv.get(d, (0, 0))
                self.past_lv[d] = (max(cur[0], pair[0]), max(cur[1], pair[1]))

    def _evo_pair(self, pid, seen):
        """(wild, trainer) level at which row pid evolves (None if no method gives one); the last matching path wins"""
        if pid in self._levels:
            return self._levels[pid]
        if pid in seen:
            return None
        seen = seen | {pid}
        base = (0, 0)
        for q in self.prev.get(pid, []):
            pq = self._evo_pair(q, seen) or (0, 0)
            base = (max(base[0], pq[0]), max(base[1], pq[1]))
        if base == (0, 0):
            base = (1, 1)
        out = None
        for m, lvl, _d in self.paths.get(pid, []):
            if m in M_FRIEND:
                out = (base[0] + 16, base[1] + 16)
            elif m in M_LEVEL:
                out = (lvl, lvl)
            elif m in M_ITEM:
                out = (base[0] + 32, base[1] + 16)
            elif m in M_TRADE:
                out = (base[0] + 48, base[1] + 16)
            elif m in M_BEAUTY:
                out = (base[0] + 48, base[1] + 32)
            elif m in M_HOLD:
                out = (lvl + 16, lvl)
        self._levels[pid] = out
        return out

    def stage_rows(self):
        """valid rows without a previous stage (base stages)"""
        return [p for p in self.valid_pids if not self.prev.get(p)]


# --- observations ----------------------------------------------------------------------------------------------------
def within(v, b):
    return b[0] <= v <= b[1]


def bias_percent(pairs, double_pct, type_count):
    """Type Bias % from (pokemon types, move type) pairs: s = % matching; u = (100 + double%) / types; 100(s-u)/(100-u)"""
    if not pairs:
        return 0.0
    s = 100.0 * sum(1 for ts, t in pairs if t in ts) / len(pairs)
    u = (100.0 + double_pct) / type_count
    return round(max(0.0, 100.0 * (s - u) / (100.0 - u)) if u < 100 else 0.0, 3)


def current_chart(context):
    """-> the 18x18 chart of the context's metadata, else the vanilla chart"""
    from .formats import il2cppmeta
    m = None
    try:
        m = context.metadata() if context is not None else None
    except Exception:
        m = None
    if m is not None:
        try:
            return il2cppmeta.type_chart(m)[0]
        except Exception:
            pass
    return [list(r) for r in il2cppmeta.VANILLA_TYPE_CHART]


def default_settings(game, context=None, observed=None):
    """-> a complete settings dict: every option off, distributions and percentages derived from the data
    (context: optional build.Context - its player metadata gives the type chart's counts; observed: a dict that receives
    {numeric option id: [the values the game has now]} and {item option id: Counter of ids} - the Studio's previews)"""
    from . import randomizer as rz
    pools = Pools(game)
    g = game
    B = {k: list(v) for k, v in rz.BOUNDS.items()}
    obs = collections.defaultdict(list)          # numeric option -> observed values
    cnt = collections.defaultdict(collections.Counter)   # item option -> counts
    valid = [pools.rows[p] for p in pools.valid_pids]
    rows_all = [r for r in g.personal if r['id'] > 0]
    # evolution
    for r in rows_all:
        for m, _p, dm, df, lvl in g.evolution_list(r):
            if within(lvl, B['level']):
                obs['evo_levels'].append(lvl)
    for pid, ns in pools.next.items():
        for d in ns:
            cnt['evo_dest'][d] += 1
    # stats, typing, misc personal
    for r in rows_all:
        for s in STATS:
            if within(r[s], B['base_stat']):
                obs['stats_random'].append(r[s])
        cnt['typing'][r['type1']] += 1
        if r['type2'] != r['type1']:
            cnt['typing'][r['type2']] += 1
        for f in ('item1', 'item2', 'item3'):
            cnt['held_items'][r[f]] += 1
        cnt['growth'][r['grow']] += 1
        for f in ('tokusei1', 'tokusei2', 'tokusei3'):
            cnt['abilities'][r[f]] += 1
        for opt, f, b in (('catch_rate', 'get_rate', 'catch_rate'), ('friendship', 'initial_friendship', 'friendship'),
                          ('exp_yield', 'give_exp', 'exp_yield')):
            if within(r[f], B[b]):
                obs[opt].append(r[f])
        tot = sum((r['exp_value'] >> (2 * k)) & 3 for k in range(6))
        if within(tot, B['ev_yield_total']):
            obs['ev_yield'].append(tot)
    allp = g.personal
    double = 100.0 * sum(1 for r in allp if r['type1'] != r['type2']) / max(1, len(allp))
    tc = pools.type_count
    # TMs
    tm_pairs = []
    comp = []
    for bit, t, _it in pools.tms:
        n = 0
        for r in rows_all:
            if g.tm_bits(r)[bit]:
                n += 1
                tm_pairs.append((pools.types_of(r), pools.move_type(t['wazaNo'])))
        comp.append(n / max(1, len(allp)))
    tm_pct = round(100.0 * sum(comp) / len(comp), 3) if comp else 0.0
    # egg + level-up moves
    egg_pairs, lv_pairs = [], []
    for r in rows_all:
        er = pools.egg_index.get(g.key_of(r))
        if er is not None:
            ws = er['wazaNo']
            if within(len(ws), B['egg_count']):
                obs['egg_count'].append(len(ws))
            for w in ws:
                cnt['egg_moves'][w] += 1
                egg_pairs.append((pools.types_of(r), pools.move_type(w)))
        ls = g.learnset(r) if r['id'] < len(g.learnsets) else []
        if within(len(ls), B['levelup_count']):
            obs['levelup_count'].append(len(ls))
        for lvl, w in ls:
            cnt['levelup_moves'][w] += 1
            lv_pairs.append((pools.types_of(r), pools.move_type(w)))
            if within(lvl, B['level']):
                obs['levelup_levels'].append(lvl)
    # moves
    for m in g.moves:
        cnt['move_type'][m['type']] += 1
        if m['damageType'] != 0:
            cnt['move_category'][m['damageType']] += 1
        for opt, f, b in (('move_power', 'power', 'power'), ('move_accuracy', 'hitPer', 'accuracy'),
                          ('move_pp', 'basePP', 'pp')):
            if within(m[f], B[b]):
                obs[opt].append(m[f])
    for t in g.tms:
        cnt['tm_moves'][t['wazaNo']] += 1
    # items
    for it in g.items:
        if within(it['price'], B['price']):
            obs['item_prices'].append(it['price'])
    for row in g.pickup:
        cnt['pickup_items'][row['ID']] += 1
    shops = g.shops
    for row in shops.get('FS', []) + shops.get('FixedShop', []):
        cnt['shop_items'][row['ItemNo']] += 1
    # wild
    for _v, e in g.encounter_files():
        for z in e['table']:
            for k in SLOT_LISTS:
                for s in z.get(k, []):
                    if s['monsNo']:
                        cnt['wild_species'][s['monsNo'] & 0xffff] += 1
                        obs['wild_levels'] += [s['minlv'], s['maxlv']]
        for s in e.get('urayama', []):
            if s['monsNo']:
                cnt['wild_species'][s['monsNo'] & 0xffff] += 1
        for s in e.get('mistu', []):
            for f in ('Normal', 'Rare', 'SuperRare'):
                if s[f]:
                    cnt['wild_species'][s[f] & 0xffff] += 1
        for s in e.get('safari', []):
            if s['MonsNo']:
                cnt['wild_species'][s['MonsNo'] & 0xffff] += 1
    for _n, t in g.ug_tables():
        for r in t['table']:
            if r['monsno']:
                cnt['wild_species'][r['monsno'] & 0xffff] += 1
    if g.has_table('UnderGround/data/ugdata', 'UgEncountLevel'):
        for r in g.ug_table('UgEncountLevel')['Data']:
            obs['wild_levels'] += [r['MinLv'], r['MaxLv']]
    # trainers
    tr_pairs = []
    slots = rare = 0
    for t in g.trainers:
        its = [t[f] for f in ('UseItem1', 'UseItem2', 'UseItem3', 'UseItem4') if t.get(f)]
        obs['trainer_item_count'].append(len(its))
        for i in its:
            cnt['trainer_items'][i] += 1
    for prow in g.trainer_pokes:
        fs = filled_slots(prow)
        if within(len(fs), B['trainer_count']):
            obs['trainer_count'].append(len(fs))
        for p in fs:
            slots += 1
            rare += 1 if prow[p + 'IsRare'] == 1 else 0
            if within(prow[p + 'Level'], B['level']):
                obs['trainer_levels'].append(prow[p + 'Level'])
            cnt['trainer_species'][prow[p + 'MonsNo']] += 1
            cnt['trainer_natures'][prow[p + 'Seikaku']] += 1
            cnt['trainer_abilities'][prow[p + 'Tokusei']] += 1
            if prow[p + 'Item']:
                cnt['trainer_held'][prow[p + 'Item']] += 1
            r = g.row(prow[p + 'MonsNo'], prow[p + 'FormNo'])
            for k in range(1, 5):
                w = prow[f'{p}Waza{k}']
                if w:
                    cnt['trainer_moves'][w] += 1
                    if r is not None:
                        tr_pairs.append((pools.types_of(r), pools.move_type(w)))
            ivs = [prow[p + f] for f in ('TalentHp', 'TalentAtk', 'TalentDef', 'TalentSpAtk', 'TalentSpDef', 'TalentAgi')]
            obs['trainer_ivs'] += [v for v in ivs if within(v, B['iv'])]
            evs = sum(prow[p + f] for f in ('EffortHp', 'EffortAtk', 'EffortDef', 'EffortSpAtk', 'EffortSpDef', 'EffortAgi'))
            if within(evs, B['ev_total']):
                obs['trainer_evs'].append(evs)
    # scripts
    from . import randomizer
    for opt, vals in randomizer.script_literals(game, pools).items():
        for v in vals:
            cnt[opt][v] += 1
    # type chart: the context's (player metadata) chart when given, else the vanilla chart
    cnt['type_matchups'].update(chart_counts(current_chart(context)))
    out = {}
    dists, alts = {}, {}
    for o in rz.OPTIONS:
        oid = o['id']
        if o['kind'] == 'check' or o['kind'] == 'choice':
            out[oid] = o['default']
        elif o['kind'] == 'percent':
            out[oid] = o['default']
        elif o['kind'] in ('number',):
            out[oid] = o['default']
        if o.get('dist') == 'numeric':
            six = dist.numeric_defaults(obs.get(oid, []))
            dists[oid] = six['NR']
            alts[oid] = six
        elif o.get('dist') == 'items':
            ent = o['entities']
            dists[oid] = dist.empirical(dict(cnt.get(oid, {})))
            alts[oid] = {'empirical': dists[oid], 'uniform': dist.uniform(valid_entities(pools, ent, oid))}
    out['typing_double'] = round(double, 3)
    out['tm_compat_pct'] = tm_pct
    out['tm_type_bias'] = bias_percent(tm_pairs, double, tc)
    out['egg_type_bias'] = bias_percent(egg_pairs, double, tc)
    out['levelup_type_bias'] = bias_percent(lv_pairs, double, tc)
    out['trainer_move_bias'] = bias_percent(tr_pairs, double, tc)
    out['trainer_shiny_pct'] = round(100.0 * rare / slots, 3) if slots else 0.0
    out['level_coef'] = 1.0
    out['dist'] = dists
    out['dist_alt'] = alts
    out['bounds'] = B
    if observed is not None:
        observed.update({k: list(v) for k, v in obs.items()})
        observed.update({k: collections.Counter(v) for k, v in cnt.items()})
    return out


def chart_counts(chart):
    c = collections.Counter(v for row in chart for v in row)
    return {v: c.get(v, 0) for v in AFFINITY_VALUES}


def valid_entities(pools, ent, oid=None):
    """the ids the Uniform alternative includes (exactly the valid entities)"""
    if ent == 'species':
        return pools.valid_species
    if ent == 'personal':
        return pools.valid_pids
    if ent == 'moves':
        return pools.valid_moves
    if ent == 'items':
        return pools.buyable_items
    if ent == 'abilities':
        return pools.valid_abilities
    if ent == 'types':
        return pools.types
    if ent == 'natures':
        return pools.natures
    if ent == 'growth':
        return pools.growth
    if ent == 'damage_category':
        return [1, 2]
    if ent == 'type_matchup':
        return list(AFFINITY_VALUES)
    return []


def entities(game, name, pools=None):
    """-> [(value, label)] for the item-distribution dialog of entity list `name`"""
    pools = pools or Pools(game)
    g = game
    if name == 'species':
        return [(m, f'{m:03d} {g.species_name(m)}') for m in pools.species]
    if name == 'personal':
        out = []
        for r in g.personal:
            m, f = g.key_of(r)
            out.append((r['id'], f'{r["id"]:04d} {g.pokemon_name(m, f)}'))
        return out
    if name == 'moves':
        return [(m['wazaNo'], f'{m["wazaNo"]:03d} {g.move_name(m["wazaNo"])}') for m in g.moves]
    if name == 'items':
        return [(it['no'], f'{it["no"]:04d} {g.item_name(it["no"])}') for it in g.items]
    if name == 'abilities':
        return [(i, f'{i:03d} {g.ability_name(i)}') for i in range(pools.ability_count)]
    if name == 'types':
        return list(enumerate(pools.type_names))
    if name == 'natures':
        return [(i, g.nature_name(i)) for i in pools.natures]
    if name == 'growth':
        return [(i, GROWTH_NAMES[i]) for i in pools.growth]
    if name == 'damage_category':
        return list(DAMAGE_CATEGORIES)
    if name == 'type_matchup':
        return [(v, AFFINITY_NAMES[v]) for v in AFFINITY_VALUES]
    raise KeyError(name)
