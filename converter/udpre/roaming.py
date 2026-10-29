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
CHOICES = ('Off - as the game (random encounters)',
           'On, and the random encounters too',
           'On, instead of the random encounters')
COMMENT = ('# Wild Pokemon you can see (uDPRE): roaming = 0 | 1 | 2 (as the game | with the random encounters | instead of '
           'them); roaming_count = 1 .. 8 (how many at once)')


def read(root):
    """-> {'mode': 0|1|2, 'count': 1..8} as the game reads them (missing or bad = the defaults)"""
    vals = lan.ini_values(root)
    mode = vals.get('roaming', '0').strip()
    try:
        count = min(max(int(vals.get('roaming_count', DEFAULT_COUNT)), 1), MAX_COUNT)
    except ValueError:
        count = DEFAULT_COUNT
    return {'mode': int(mode) if mode in ('0', '1', '2') else 0, 'count': count}


def write(root, mode, count=DEFAULT_COUNT):
    """sets roaming and roaming_count in pc_settings.ini, every other line kept as it is; -> the file path"""
    count = min(max(int(count), 1), MAX_COUNT)
    return lan.write_keys(root, {'roaming': str(mode if mode in (0, 1, 2) else 0), 'roaming_count': str(count)}, COMMENT)


def summary(vals):
    return CHOICES[vals['mode']] + (f', {vals["count"]} at once' if vals['mode'] else '')


def player_supports(root):
    """-> True / False: the player in this folder has wild Pokemon you can see (None = no player found)"""
    meta = os.path.join(root, 'Dpr_Data', 'il2cpp_data', 'Metadata', 'global-metadata.dat')
    try:
        with open(meta, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return (b'\x00' + SUPPORT_TYPE + b'\x00') in data
