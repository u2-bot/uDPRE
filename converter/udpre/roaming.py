"""Wild Pokemon you can see: the overworld's wild Pokemon walk around the player and a battle starts when the player walks
into one, the way the Grand Underground plays them (the game player's PcRoaming code, which reads it once at start).

The settings live in the game's pc_settings.ini (lan.settings_path), next to the LAN keys:
  roaming=0|1|2        0 as the game (default); 1 wild Pokemon you can see + the random encounters; 2 wild Pokemon you can
                       see instead of the random encounters (the Poke Radar's grass, a wandering legendary and a partner's
                       double battles stay)
  roaming_count=1..8   how many walk around the player at once (default 4)
They come from the area's own encounter table (time of day, shinies included), on land and, while surfing, on water.
"""
import os

from . import lan

SUPPORT_TYPE = b'PcRoaming'         # the player's global-metadata.dat names it when the player has them
DEFAULT_COUNT = 4
MAX_COUNT = 8
DEFAULT_CHASE = 25
# how many of them notice you and chase you (roaming_chase, percent); the others only wander
CHASE = ((0, 'None - they only wander'), (25, 'A few (1 in 4)'), (50, 'Half of them'), (100, 'All of them'))
CHOICES = ('Off - as the game (random encounters)',
           'On, and the random encounters too',
           'On, instead of the random encounters')
COMMENT = ('# Wild Pokemon you can see (uDPRE): roaming = 0 | 1 | 2 (as the game | with the random encounters | instead of '
           'them); roaming_count = 1 .. 8 (how many at once); roaming_chase = 0 .. 100 (percent that chase you)')


def read(root):
    """-> {'mode': 0|1|2, 'count': 1..8, 'chase': 0..100} as the game reads them (missing or bad = the defaults)"""
    vals = lan.ini_values(root)
    mode = vals.get('roaming', '0').strip()
    try:
        count = min(max(int(vals.get('roaming_count', DEFAULT_COUNT)), 1), MAX_COUNT)
    except ValueError:
        count = DEFAULT_COUNT
    try:
        chase = min(max(int(vals.get('roaming_chase', DEFAULT_CHASE)), 0), 100)
    except ValueError:
        chase = DEFAULT_CHASE
    return {'mode': int(mode) if mode in ('0', '1', '2') else 0, 'count': count, 'chase': chase}


def write(root, mode, count=DEFAULT_COUNT, chase=DEFAULT_CHASE):
    """sets roaming, roaming_count and roaming_chase in pc_settings.ini, every other line kept as it is; -> the file path"""
    count = min(max(int(count), 1), MAX_COUNT)
    chase = min(max(int(chase), 0), 100)
    return lan.write_keys(root, {'roaming': str(mode if mode in (0, 1, 2) else 0), 'roaming_count': str(count),
                                 'roaming_chase': str(chase)}, COMMENT)


def chase_label(percent):
    """the window's choice for a percent (the nearest of CHASE)"""
    return min(CHASE, key=lambda c: abs(c[0] - percent))[1]


def summary(vals):
    return CHOICES[vals['mode']] + (f', {vals["count"]} at once, {vals["chase"]}% chase you' if vals['mode'] else '')


def _has_them(player_folder):
    meta = os.path.join(player_folder, 'Dpr_Data', 'il2cpp_data', 'Metadata', 'global-metadata.dat')
    try:
        with open(meta, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return (b'\x00' + SUPPORT_TYPE + b'\x00') in data


def player_supports(root):
    """-> True / False: the player in this folder has wild Pokemon you can see (None = no player found)"""
    return _has_them(root)


def support(root, found=None, mod_ids=None):
    """-> (state, pack) for the game in this folder: 'yes'; 'convert' (not converted yet); 'reconvert' (it was made with an
    older copy of the pack giving its game code - the one in the mods folder now has them); 'update_pack' (that pack's own
    game code has none: update the pack); 'update_udpre' (our own player has none: update uDPRE). pack = the mod whose game
    code the folder runs (the top-most mod of the last conversion that brings a player, as the converter picks it), or None.
    found / mod_ids default to the mods folder and the last conversion's mods."""
    from . import install, mods as modlib
    if found is None or mod_ids is None:
        p = install.Paths(root)
        if found is None:
            found, _problems = modlib.discover(p.mods, install.load_config(p).get('sources'))
        if mod_ids is None:
            mod_ids = install.load_config(p).get('mods', [])
    pack = modlib.player_mod(sorted((found[i] for i in mod_ids if i in found), key=lambda m: (m.order, m.id)))
    here = player_supports(root)
    if here:
        return 'yes', pack
    if here is None:
        return 'convert', pack
    if pack is not None:
        return ('reconvert' if _has_them(pack.player_dir()) else 'update_pack'), pack
    return 'update_udpre', None


def support_text(state, pack):
    """what to do, for the window's note and `uDPRE.exe roaming show`"""
    name = f'{pack.name} {pack.version}'.strip() if pack is not None else ''
    return {'yes': 'the game here has them',
            'convert': 'convert first',
            'reconvert': f'the game here was made with an older {pack.name if pack else "pack"}: press Convert',
            'update_pack': f'the game code of {name} has none: update that pack (Get mods...), then convert',
            'update_udpre': 'the game here has none yet: update uDPRE, then convert'}[state]
