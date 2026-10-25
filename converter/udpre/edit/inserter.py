"""Pokemon Inserter: a copy of an existing Pokemon (species + form) as a NEW FORM of a species or as a NEW SPECIES numbered
after the last one, with every table row, text, UI record, model, icon and cry the game looks up for it.

  {"op": "insert", "mode": "form" | "species", "src": [monsno, form], "dst": monsno (form mode), "name": species name
   (species mode), "form_name": text, "copy_assets": true, "models": "auto" | "clone"}
copy_assets: the new Pokemon gets its own model / icon bundles and menu icon sprite (copies under new names, so a model mod
can replace them); false = it shows the source's model and icons. models: when a mod already ships models / icons under
the new names (custom models made for that number; Luminescent's atlas holds Gen 9 icons it does not use yet), "auto" uses
the mod's (a model set must be complete), "clone" copies the source's over them. Cries are always copied, onto new .wem
ids: battle and contest code build cry event names from the species and form numbers (BOPokemon "Play_PV_Btl_{dex:3}_
{form:2}_..", contest "PLAY_PV_BTL_..").

How the game finds a Pokemon's data (BDSP v1.3.0 code, Luminescent the same):
  - PersonalTable row = monsno for form 0, form_index + form - 1 for other forms (a species' form rows are contiguous):
    a new species row goes right after the last species row, a new form right after its species' last form row (or
    where the forms of the next species with forms start); every later row moves down one and every form_index behind
    the insertion point grows by one. WazaOboeTable, EvolveTable and TamagoWazaTable rows follow the personal rows.
  - Messages: ss_monsname and ss_zkn_type by species number; ss_zkn_form by personal row (ZukanInfo formLabelIndex);
    ss_zkn_height / ss_zkn_weight by label name ZKN_HEIGHT_{dex:3}_{form:3}; dp_pokedex_* by species (dump) or by
    personal row (Luminescent's DescText_SetupMessage). A sheet with one label per personal row gets the label inserted
    at the new row's position (later labels renumbered); one per species gets it appended; the others by name.
  - PokemonInfo.Catalog / UIDatabase rows by unique id = monsno*10000 + form*100 + sex*10 + shiny (kept sorted);
    PokemonInfo.Trearuki follows the catalog row by row.
New species also need the player to accept a species number past its own limit (vanilla 493, Luminescent 1,010): see the
player notes in the report; the data is made either way.
"""
import copy
import random
import re

from .game import BATTLE, CONTEST, MASTER, UGDATA, UI
from .gamefiles import AA, EditError

POKEMON_DB = 'Pokemon Database'
CRY_PREFIXES = ['PLAY_PV_', 'PLAY_PV_BTL_', 'PLAY_PV_EV_']
BANK = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch/Delphis_Main.bnk'


def uid(m, f, sex=0, rare=0):
    return m * 10000 + f * 100 + sex * 10 + rare


def _sorted_insert(rows, row, key):
    k = key(row)
    i = 0
    while i < len(rows) and key(rows[i]) < k:
        i += 1
    rows.insert(i, row)
    return i


SUPPORT_TYPE = 'Pml.MonsLimit'      # in a player that takes species numbers past its compiled limit


def gender_config(game, monsno, form):
    """what the source's non-shiny PokemonInfo catalog rows say about its genders (shown by the Inserter; it does not change
    what is copied): 'Male only' / 'Female only' / 'Genderless' (one row, Sex 0 / 1 / 2), 'Male/Female' (two rows, one
    model), 'Male/Female variants' (two rows, two models), 'none' (no row)"""
    rows = [r for r in game.table(MASTER, 'PokemonInfo')['Catalog']
            if r['UniqueID'] // 100 == monsno * 100 + form and not r.get('Rare')]
    if not rows:
        return 'none'
    if len(rows) == 1:
        return {0: 'Male only', 1: 'Female only', 2: 'Genderless'}.get(rows[0]['Sex'], f'Sex {rows[0]["Sex"]}')
    if len(rows) == 2:
        same = rows[0]['AssetBundleName'] == rows[1]['AssetBundleName']
        return 'Male/Female' if same else 'Male/Female variants'
    return f'{len(rows)} catalog rows (unexpected)'


def player_supports_new_species(context):
    """-> True / False for the chosen player (its global-metadata has the type), None when there is no player metadata"""
    m = context.metadata() if context is not None else None
    if m is None:
        return None
    try:
        m.type('Assembly-CSharp.dll', SUPPORT_TYPE)
        return True
    except KeyError:
        return False


def apply(game, op, context, log=print):
    """-> None or why it could not be done (the game data is left as it was in that case: checks come first)"""
    if op.get('mode') == 'species':
        ok = player_supports_new_species(context)
        if ok is False and getattr(context, 'label', 'player') == 'player':
            from .. import advice
            return advice.text(
                f'A new species from the Pokemon Inserter ({op.get("name") or "new species"}) was left out: the game '
                f'player you use keeps the game\'s own species limit',
                ['Without the Luminescent / Dechibified packs: update uDPRE to 0.4.0 or newer - ' + advice.newer_udpre(),
                 'With Luminescent or Dechibified on: update those packs to 1.2.5 or newer (replace their folders in the '
                 'mods folder), then press Apply'])
        if getattr(context, 'label', '') == 'Switch':
            context.notes.append('new species need the console game\'s code changed too (exefs); the console mod has the '
                                 'data only')
    try:
        return Inserter(game, op, context, log).run()
    except EditError as e:
        return str(e)


class Inserter:
    def __init__(self, g, op, context, log):
        self.g, self.op, self.ctx, self.log = g, op, context, log
        self.rng = random.Random(hash((tuple(op['src']), op.get('dst'), op.get('name'), op['mode'])) & 0xFFFFFFFF)
        self.notes = []

    # --- checks + positions -------------------------------------------------------------------------------------------
    def run(self):
        g, op = self.g, self.op
        sm, sf = op['src']
        self.src = g.row(sm, sf)
        if self.src is None or sm == 0:
            return f'the source Pokemon {sm} form {sf} is not in these game files'
        self.sm, self.sf = sm, sf
        P = g.personal
        n_species = g.species_count()
        if op['mode'] == 'species':
            self.dm, self.df = n_species + 1, 0
            self.pos = n_species + 1
            if self.pos < len(P) and P[self.pos]['id'] == P[self.pos]['monsno']:
                return 'the personal table has a species row after the last species - not inserted'
        elif op['mode'] == 'form':
            dm = int(op['dst'])
            base = g.row(dm)
            if base is None or dm == 0:
                return f'species {dm} is not in these game files'
            self.dm = dm
            self.df = max(1, base['form_max'])
            if base['form_max'] > 1:
                self.pos = base['form_index'] + base['form_max'] - 1
            else:
                later = [r['form_index'] for r in P if r['id'] == r['monsno'] and r['monsno'] > dm and r['form_max'] > 1]
                self.pos = min(later) if later else len(P)
        else:
            return f'unknown insert mode {op["mode"]}'
        self.copy_assets = op.get('copy_assets', True)
        self.old_personal = len(P)
        self.old_species = n_species
        self.variants = [r for r in g.table(MASTER, 'PokemonInfo')['Catalog'] if r['UniqueID'] // 100 == sm * 100 + sf]
        if not self.variants:
            return 'the source has no PokemonInfo catalog rows (model data)'
        self.personal()
        self.messages()
        self.catalog()
        self.ui()
        self.battle()
        if op['mode'] == 'species':
            self.species_only()
        self.cries()
        self.log(f'inserted {g.pokemon_name(self.dm, self.df)} ({self.dm} form {self.df}) as personal row {self.pos}; '
                 + '; '.join(self.notes))
        return None

    # --- personal tables ----------------------------------------------------------------------------------------------
    def personal(self):
        g, pos = self.g, self.pos
        P = g.personal
        # a mod's 256-TM set (ExtraData TM learnset) of the source goes to the new Pokemon too (read before rows move)
        _rel, tm_json = g._tm_json(g.key_of(self.src))
        new = copy.deepcopy(self.src)
        for r in P:
            if r['id'] >= pos:
                r['id'] += 1
            if r['form_index'] >= pos:
                r['form_index'] += 1
        new['id'] = pos
        new['monsno'] = self.dm
        P.insert(pos, new)
        if self.op['mode'] == 'species':
            new['form_index'], new['form_max'] = 0, 1
            new['egg_monsno'] = self.dm if self.src['egg_monsno'] == self.sm else self.src['egg_monsno']
        else:
            forms = [r for r in P if r['monsno'] == self.dm]
            first_alt = min(r['id'] for r in forms if r['id'] != self.dm)
            for r in forms:
                r['form_max'] = self.df + 1
                r['form_index'] = first_alt
        for lst, mk in ((g.learnsets, lambda r, i: dict(copy.deepcopy(r), id=i)),
                        (g.evolutions, lambda r, i: dict(copy.deepcopy(r), id=i))):
            src = lst[self.src_old_id()]
            for r in lst:
                if r['id'] >= pos:
                    r['id'] += 1
            lst.insert(pos, mk(src, pos))
        eggs = g.egg_moves
        er = g.egg_row(self.sm, self.sf)
        new_egg = dict(copy.deepcopy(er) if er else {'no': self.dm, 'formNo': self.df, 'wazaNo': []},
                       no=self.dm, formNo=self.df)
        eggs.insert(min(pos, len(eggs)), new_egg)
        ap = g.add_personal
        src_ap = next((r for r in ap if r['monsno'] == self.sm and r['formno'] == self.sf), None)
        if src_ap is not None and not any(r['monsno'] == self.dm and r['formno'] == self.df for r in ap):
            ap.append(dict(copy.deepcopy(src_ap), monsno=self.dm, formno=self.df))
        if tm_json is not None:
            from .game import TM_LEARNSET
            rel = f'{TM_LEARNSET}/monsno_{self.dm}_formno_{self.df}.json'
            if rel not in g.tm_learnsets().values():
                g.set_extradata(rel, copy.deepcopy(tm_json))
                self.notes.append('ExtraData TM learnset copied')

    def src_old_id(self):
        """the source row's index in the lists that were not shifted yet (learnsets / evolutions before their insert)"""
        sid = self.src['id']
        return sid - 1 if sid > self.pos else sid

    # --- messages -----------------------------------------------------------------------------------------------------
    def messages(self):
        from .text import LANGS, Messages
        g = self.g
        sp_name = self.op.get('name') or g.species_name(self.sm)
        form_name = self.op.get('form_name', '')
        for lang in LANGS:
            m = g.msg if lang == g.msg.lang else Messages(g.files, lang)
            for sheet in ('ss_zkn_form', 'ss_zkn_height', 'ss_zkn_weight', 'dp_pokedex_diamond', 'dp_pokedex_pearl',
                          'ss_monsname', 'dlp_whitelist_monsname', 'ss_zkn_type'):
                t = m.sheet(sheet)
                if t is None:
                    continue
                self._sheet(m, sheet, t, sp_name, form_name)

    def _sheet(self, m, sheet, t, sp_name, form_name):
        arr = t['labelDataArray']
        n = len(arr)
        dm, df, sm, sf = self.dm, self.df, self.sm, self.sf
        prefix = {'ss_zkn_form': 'ZKN_FORM', 'ss_zkn_height': 'ZKN_HEIGHT', 'ss_zkn_weight': 'ZKN_WEIGHT',
                  'dp_pokedex_diamond': 'DP_pokedex_diamond', 'dp_pokedex_pearl': 'DP_pokedex_pearl',
                  'ss_monsname': 'MONSNAME', 'dlp_whitelist_monsname': 'MONSNAME', 'ss_zkn_type': 'ZKN_TYPE'}[sheet]
        by_row = n == self.old_personal
        by_species = n == self.old_species + 1
        if sheet in ('ss_monsname', 'dlp_whitelist_monsname', 'ss_zkn_type') or (by_species and not by_row):
            if self.op['mode'] != 'species':
                return                                      # species-indexed: a new form needs no label
            src = m.label(sheet, f'{prefix}_{sm:03d}')
            new = copy.deepcopy(src) if src else copy.deepcopy(arr[-1])
            new['labelName'] = f'{prefix}_{dm:03d}'
            at = dm if sheet != 'dlp_whitelist_monsname' else n
            if at < n:                                      # a sheet longer than the species list: keep the order
                return
            new['labelIndex'] = new['arrayIndex'] = n
            arr.append(new)
            m._index.pop(sheet, None)
            if sheet in ('ss_monsname', 'dlp_whitelist_monsname'):
                m.set_text(sheet, new['labelName'], sp_name)
            return
        name_src = f'{prefix}_{sm:03d}_{sf:03d}'
        name_new = f'{prefix}_{dm:03d}_{df:03d}'
        src = m.label(sheet, name_src)
        if src is None and sheet == 'ss_zkn_form':
            src = arr[self.src_old_id()] if self.src_old_id() < n else None
        new = copy.deepcopy(src) if src is not None else copy.deepcopy(arr[-1])
        new['labelName'] = name_new
        if by_row:
            at = min(self.pos, n)
            for lab in arr:
                if lab['labelIndex'] >= at:
                    lab['labelIndex'] += 1
                if lab['arrayIndex'] >= at:
                    lab['arrayIndex'] += 1
            new['labelIndex'] = new['arrayIndex'] = at
            arr.insert(at, new)
        else:
            new['labelIndex'] = max(l['labelIndex'] for l in arr) + 1 if arr else 0
            new['arrayIndex'] = n
            arr.append(new)
        m._index.pop(sheet, None)
        if sheet == 'ss_zkn_form':
            m.set_text(sheet, name_new, form_name)

    # --- catalog + UI -------------------------------------------------------------------------------------------------
    def model_name(self, old):
        """model bundle name pmDDDD_XX_RR (XX = the species' model variant: a form or a gender model, RR shiny) -> the
        new Pokemon's: a new species keeps the variant numbers, a new form takes numbers no model of its species uses"""
        if not self.copy_assets:
            return old
        m = re.match(r'^pm(\d{4})_(\d{2})(.*)$', old)
        if not m:
            return old
        x = int(m.group(2))
        if x not in self.x_map:
            if self.op['mode'] == 'species':
                self.x_map[x] = x
            else:
                used = self.used_variants()
                nxt = max(used | set(self.x_map.values()) | {10}) + 1
                if nxt > 99:
                    raise EditError(f'species {self.dm} has no free model number left')
                self.x_map[x] = nxt
        return f'pm{self.dm:04d}_{self.x_map[x]:02d}{m.group(3)}'

    def used_variants(self):
        pre = f'{AA}/{POKEMON_DB}/pokemons/battle/pm{self.dm:04d}_'
        used = set()
        for k in self.g.files.stack.index:
            if k.startswith(pre):
                try:
                    used.add(int(k[len(pre):len(pre) + 2]))
                except ValueError:
                    pass
        for r in self.g.table(MASTER, 'PokemonInfo')['Catalog']:
            m = re.match(r'^pm(\d{4})_(\d{2})', r['AssetBundleName'] or '')
            if m and int(m.group(1)) == self.dm:
                used.add(int(m.group(2)))
        return used

    def catalog(self):
        g = self.g
        pi = g.table(MASTER, 'PokemonInfo')
        cat, trea = pi['Catalog'], pi.get('Trearuki')
        self.renames = {}
        self.x_map = {}
        for v in sorted(self.variants, key=lambda r: r['UniqueID']):
            new = copy.deepcopy(v)
            new['UniqueID'] = uid(self.dm, self.df, v['Sex'], v['Rare'])
            new['No'] = new['MonsNo'] = self.dm
            new['FormNo'] = self.df
            if self.op['mode'] == 'species':
                new['SinnohNo'] = 0
            if v['AssetBundleName']:
                nb = self.model_name(v['AssetBundleName'])
                self.renames[v['AssetBundleName']] = nb
                new['AssetBundleName'] = nb
            if any(r['UniqueID'] == new['UniqueID'] for r in cat):
                continue
            src_i = cat.index(v)
            i = _sorted_insert(cat, new, lambda r: r['UniqueID'])
            if trea is not None and len(trea) + 1 == len(cat) and src_i < len(trea):
                trea.insert(i, copy.deepcopy(trea[src_i if src_i < i else src_i]))
        if self.copy_assets:
            self.copy_models()

    def ui(self):
        g = self.g
        db = g.table(UI, 'UIDatabase')
        self.voice_events = {}
        for v in self.variants:
            ou, nu = v['UniqueID'], uid(self.dm, self.df, v['Sex'], v['Rare'])
            for sheet in ('PokemonIcon', 'AshiatoIcon', 'PokemonVoice', 'ZukanDisplay', 'ZukanCompareHeight'):
                rows = db.get(sheet)
                if rows is None or any(r['UniqueID'] == nu for r in rows):
                    continue
                src = next((r for r in rows if r['UniqueID'] == ou), None)
                if src is None:
                    continue
                new = dict(copy.deepcopy(src), UniqueID=nu)
                if sheet == 'PokemonIcon' and self.copy_assets:
                    for kb, ka in (('AssetBundleNameLarge', 'AssetNameLarge'), ('AssetBundleNameDP', 'AssetNameDP')):
                        if new.get(kb):
                            nb, na = self.copy_icon(new[kb], new[ka])
                            new[kb], new[ka] = nb, na
                    if new.get('AssetName'):
                        na = self.copy_menu_icon(new['AssetName'])
                        if na != new['AssetName']:
                            new['AssetBundleName'] = new.get('AssetBundleName', '').replace(new['AssetName'], na)
                            new['AssetName'] = na
                if sheet == 'PokemonVoice':
                    self.voice_events[nu] = new
                _sorted_insert(rows, new, lambda r: r['UniqueID'])
        if self.op['mode'] == 'species':
            sps = db.get('SearchPokeIconSex')
            if sps is not None and not any(r['MonsNo'] == self.dm for r in sps):
                src = next((r for r in sps if r['MonsNo'] == self.sm), None)
                if src is not None:
                    sps.append(dict(copy.deepcopy(src), MonsNo=self.dm))
            dt = g.table(UI, 'DistributionTable') if g.has_table(UI, 'DistributionTable') else None
            if dt is not None:
                for k in ('Diamond_FieldTable', 'Diamond_DungeonTable', 'Pearl_FieldTable', 'Pearl_DungeonTable'):
                    rows = dt.get(k)
                    if rows is not None and len(rows) == self.dm and self.sm < len(rows):
                        rows.append(copy.deepcopy(rows[self.sm]))

    def battle(self):
        g = self.g
        mt = g.table(BATTLE, 'BattleDataTable')['MotionTimingData']
        for sex in sorted({v['Sex'] for v in self.variants}):
            if any(r['MonsNo'] == self.dm and r['FormNo'] == self.df and r['Sex'] == sex for r in mt):
                continue
            src = next((r for r in mt if r['MonsNo'] == self.sm and r['FormNo'] == self.sf and r['Sex'] == sex), None) \
                or next((r for r in mt if r['MonsNo'] == self.sm and r['FormNo'] == self.sf), None)
            if src is not None:
                mt.append(dict(copy.deepcopy(src), MonsNo=self.dm, FormNo=self.df, Sex=sex))

    def species_only(self):
        g = self.g
        if g.has_table(UGDATA, 'UgPokemonData'):
            t = g.table(UGDATA, 'UgPokemonData')['table']
            src = next((r for r in t if r['monsno'] == self.sm), None)
            if src is not None and not any(r['monsno'] == self.dm for r in t):
                t.append(dict(copy.deepcopy(src), monsno=self.dm))
        if g.has_table(CONTEST, 'ContestConfigDatas'):
            cc = g.table(CONTEST, 'ContestConfigDatas')
            rm = cc.get('ResultMotion')
            if rm is not None:
                src = next((r for r in rm if r.get('monsNo') == self.sm), None)
                if src is not None and not any(r.get('monsNo') == self.dm for r in rm):
                    rm.append(dict(copy.deepcopy(src), monsNo=self.dm, id=len(rm)))

    # --- cries --------------------------------------------------------------------------------------------------------
    def cries(self):
        """every cry event the source has under its numbers -> the same chain under the new numbers' names"""
        from .formats import wwise
        g = self.g
        if not g.files.exists(BANK):
            self.notes.append('no sound bank: cries not copied')
            return
        bank = wwise.Bank(g.files.read(BANK))
        group = {'Delphis_Main': bank}
        init = BANK.rsplit('/', 1)[0] + '/Init.bnk'
        if g.files.exists(init):
            group['Init'] = wwise.Bank(g.files.read(init))        # its ids count as used too
        banks = wwise.Banks(group)
        # the copied sounds play their own <new id>.wem (a copy of the source's), so a mod can give the new Pokemon its
        # own cry without touching the source's; one new id per source media, shared by all the copied events
        from ..mods import out_rel
        audio = BANK.rsplit('/', 1)[0]
        pre_out = out_rel(audio) + '/'
        wems = set()
        for k in list(g.files.stack.index) + list(g.files._new):
            k = out_rel(k)
            if k.startswith(pre_out) and k.endswith('.wem') and k[len(pre_out):-4].isdigit():
                wems.add(int(k[len(pre_out):-4]))
        media = {}
        made = 0
        for pre in CRY_PREFIXES:
            for i in range(10):
                src = f'{pre}{self.sm:03d}_{self.sf:02d}_{i:02d}'
                dst = f'{pre}{self.dm:03d}_{self.df:02d}_{i:02d}'
                if banks.event(src)[1] is None or banks.event(dst)[1] is not None:
                    continue
                banks.duplicate_event(src, dst, extra_used=wems, media_map=media)
                made += 1
        copied = 0
        for old, new in sorted(media.items()):
            src_wem, dst_wem = f'{audio}/{old}.wem', f'{audio}/{new}.wem'
            if g.files.exists(src_wem) or g.files.has_new(src_wem):
                g.files.add_new(dst_wem, g.files.read(src_wem))
                copied += 1
        if media:
            self.notes.append(f'{len(media)} cry media ids new ({copied} .wem files copied)')
        for row in self.voice_events.values():
            m = re.match(r'(?i)(play_pv_)(\d{3})_(\d{2})_(\d{2})$', row.get('WwiseEvent', ''))
            if m and int(m.group(2)) == self.sm and int(m.group(3)) == self.sf:
                cand = f'{m.group(1)}{self.dm:03d}_{self.df:02d}_{m.group(4)}'
                if banks.event(cand)[1] is not None:
                    row['WwiseEvent'] = cand
        if made:
            g.files.set_raw(BANK, bank.to_bytes())
        self.notes.append(f'{made} cry events copied')

    # --- assets -------------------------------------------------------------------------------------------------------
    def copy_models(self):
        """battle / field / animation / common bundles of every renamed model -> copies under the new names, with new
        CAB names, their references to each other remapped, and the catalog (Dpr.bin) records added"""
        from .assets import BundleCloner
        c = BundleCloner(self.g, self.rng, self.op.get('models', 'auto'))
        for old, new in self.renames.items():
            if old == new:
                continue
            c.clone_model(old, new)
        c.finish()
        self.notes.append(f'{len(c.done)} model bundles copied' if not c.from_mod else
                          f'{len(c.from_mod)} model bundles a mod made for the new Pokemon used')

    def copy_menu_icon(self, asset_name):
        """the menu icon (a sprite of the TextureMass atlas) -> a sprite named for the new Pokemon on its own texture"""
        from .assets import TEXTUREMASS, add_atlas_sprite
        done = self.__dict__.setdefault('menu_icons', {})
        if asset_name in done:
            return done[asset_name]
        new_name = re.sub(r'^pm\d{4}_\d{2}', f'pm{self.dm:04d}_{self.df:02d}', asset_name)
        done[asset_name] = asset_name
        if new_name == asset_name:
            return asset_name
        rel = f'{AA}/{TEXTUREMASS}'
        g = self.g
        try:
            if g.files.source(rel).kind != 'switch':
                raise EditError('it comes from a pack as a Windows file')
            data, note = add_atlas_sprite(g.files.read(rel), asset_name, new_name, self.rng,
                                          replace=self.op.get('models', 'auto') == 'clone')
        except EditError as e:
            self.notes.append(f'menu icon {asset_name} kept ({e})')
            return asset_name
        if data is not None:
            g.files.set_raw(rel, data)
        self.notes.append(note)
        done[asset_name] = new_name
        return new_name

    def copy_icon(self, bundle_name, asset_name):
        """an icon bundle (one per sprite; several variants can share one) -> a copy named for the new Pokemon"""
        from .assets import BundleCloner
        done = self.__dict__.setdefault('icons', {})
        if bundle_name in done:
            return done[bundle_name]
        new_asset = re.sub(r'^pm\d{4}_\d{2}', f'pm{self.dm:04d}_{self.df:02d}', asset_name)
        new_bundle = bundle_name.replace(asset_name, new_asset)
        if new_bundle == bundle_name:
            return bundle_name, asset_name
        c = BundleCloner(self.g, self.rng, self.op.get('models', 'auto'))
        try:
            c.clone('UIs', bundle_name, new_bundle, {asset_name: new_asset})
            c.finish()
        except EditError as e:
            self.notes.append(f'icon {bundle_name} kept ({e})')
            done[bundle_name] = (bundle_name, asset_name)
            return done[bundle_name]
        done[bundle_name] = (new_bundle, new_asset)
        return done[bundle_name]
