"""Problem texts a player can act on without help: what happened, then numbered steps of what to do (the window shows them
in its message box and log, the console after "PROBLEM:"). Every message names the exact folder, pack, version and download
it is about; links come from the packs themselves (their mod page), never guessed."""
import os

from . import __version__

RELEASES = 'https://github.com/u2-bot/uDPRE/releases'
SEVEN_ZIP = 'https://www.7-zip.org'


def text(problem, steps=(), details=None):
    """'<problem>.\n\nWhat to do:\n  1. ...' (+ a details line for a report when the cause is technical)"""
    out = problem.strip()
    if out and out[-1] not in '.!?:)':
        out += '.'
    steps = [s for s in steps if s]
    if steps:
        out += '\n\nWhat to do:\n' + '\n'.join(f'  {i}. {s}' for i, s in enumerate(steps, 1))
    if details:
        out += f'\n\n(Details for a bug report: {details})'
    return out


def folder(path, root=None):
    """a path as the player sees it (relative to the uDPRE folder when inside it)"""
    path = os.path.normpath(path)
    if root:
        try:
            rel = os.path.relpath(path, root)
            if not rel.startswith('..'):
                return rel
        except ValueError:
            pass
    return path


def get_from(mod):
    """'from <url> (by <author>)' for a pack's mod page, or ''"""
    if not mod.url:
        return ''
    return f'from {mod.url}' + (f' (by {mod.author})' if mod.author else '')


def pack_folder(path):
    """mods/<name> (as Windows shows it) for a folder in a mods folder, else the path"""
    path = os.path.normpath(path)
    if os.path.basename(os.path.dirname(path)).lower() == 'mods':
        return os.path.join('mods', os.path.basename(path))
    return path


def update_pack(mod, least=None, root=None):
    """the step that replaces a pack with a newer version"""
    where = pack_folder(mod.path) if mod.path else 'mods'
    return (f'Get the newest {mod.name} uDPRE pack' + (f' ({least} or newer)' if least else '') +
            f' and REPLACE the folder {where} with it (delete the old folder first; do not copy the new one over it)')


def redownload_pack(mod_or_name, path=None, root=None):
    name = getattr(mod_or_name, 'name', mod_or_name)
    path = path or getattr(mod_or_name, 'path', None)
    where = f' and replace the folder {pack_folder(path)} with it' if path else ' and put it into the mods folder again'
    return f'Download the {name} uDPRE pack again{where} (delete the old folder first)'


def newer_udpre():
    return (f'Download the newest uDPRE from {RELEASES} and unzip it over this uDPRE folder (this is uDPRE {__version__}; '
            f'your converted game, mods, edits and saves stay)')


def unzip_udpre_again():
    return (f'Unzip the uDPRE release (uDPRE-{__version__}-win64.zip, from {RELEASES}) over this folder again - your '
            f'converted game, mods, edits and saves stay. If an antivirus removed a file, allow it and unzip again')


def source_missing(mod, sid, picked_wrong=None):
    """a pack needs the player's own download of a mod (Luminescent Platinum 2.2F ...) and none was found"""
    s = mod.sources[sid]
    name = s.get('name', sid)
    steps = [f'Download the original {name} {get_from(mod)}'.rstrip() + ' - the mod itself, from its author. The uDPRE pack '
             f'holds only the PC version of its code, not the mod',
             f'Extract the download with 7-Zip ({SEVEN_ZIP}) into a new folder',
             'Put that folder - the one that has "romfs" (and "exefs") inside - into the mods folder of uDPRE, then press '
             '"Look again". Or press "Find a mod download..." and pick the folder where it is']
    if picked_wrong:
        steps.append(f'{picked_wrong} is not it: it is another version of the mod, the Shining Pearl one, or not fully '
                     f'extracted - it must be exactly {name}')
    return text(f'The {mod.name} pack needs your own copy of {name}, and uDPRE did not find it', steps)
