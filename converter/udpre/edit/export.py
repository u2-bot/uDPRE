"""Export the edits as a console / emulator mod: a LayeredFS folder <out>/romfs/Data/... holding every Switch file the edit
project changes (made from the same stack as the game: the dump + the chosen packs' Switch files + merged console mods),
and - when the project edits the type chart or other field default values - the dump's own Managed/Metadata/
global-metadata.dat with the same edits (the Switch game reads it the way our player reads its own).
With merged=True the files uDPRE merged from several console mods go in too (a console cannot merge them itself).
A pack's own files are NOT copied: a console player installs those mods first, then this folder over them."""
import os
import shutil

from .build import Context, SWITCH_METADATA
from .gamefiles import GameFiles
from .game import Game
from .project import apply


def export(session, out_dir, merged=True, log=print):
    """-> {'files': [romfs paths written], 'warnings': [...]}"""
    s = session
    files = GameFiles(s.stack)
    game = Game(files, s.lang)
    game.hints = s.hints()          # the same table layouts the editor and the PC build read
    # the metadata the console game runs: the top mod's own copy when a chosen mod ships one, else the dump's
    srcs = [x for x in (getattr(s.stack, 'all_sources', {}) or {}).get(SWITCH_METADATA, []) if os.path.isfile(x.path)]
    meta_src = srcs[-1].path if srcs else os.path.join(s.stack.dump, *SWITCH_METADATA.split('/'))
    ctx = Context(open(meta_src, 'rb').read() if os.path.isfile(meta_src) else None, 'Switch')
    warnings = apply(game, s.project, ctx, log)
    out = {}
    if merged:
        mdir = os.path.join(s.p.state, 'merged')
        for d, _, fs in os.walk(mdir):
            for f in fs:
                if f in ('report.json',) or f.endswith('.part'):
                    continue
                full = os.path.join(d, f)
                out[os.path.relpath(full, mdir).replace(os.sep, '/')] = ('copy', full)
    for rel, data in files.changed().items():
        out[rel] = ('data', data)
    meta = ctx.metadata_bytes()
    if meta is not None:
        out[SWITCH_METADATA] = ('data', meta)
    if BANK in out:
        out[AUDIO_SOURCES] = ('data', audio_sources(game, out[BANK][1]).encode('utf-8'))
    import json
    root = os.path.join(out_dir, 'romfs', 'Data')
    manifest = os.path.join(out_dir, MANIFEST)
    if os.path.isdir(out_dir) and os.listdir(out_dir) and not os.path.isfile(manifest):
        raise ExportError(f'{out_dir} is not empty and was not made by uDPRE - pick an empty folder')
    if os.path.isfile(manifest):                    # only what the last export of this folder wrote is removed
        with open(manifest, encoding='utf-8') as f:
            for rel in json.load(f).get('files', []):
                p = os.path.join(root, *rel.split('/'))
                if os.path.isfile(p) and rel not in out:
                    os.remove(p)
    for rel, (kind, v) in sorted(out.items()):
        dst = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if kind == 'copy':
            shutil.copyfile(v, dst)
        else:
            with open(dst, 'wb') as f:
                f.write(v)
    with open(os.path.join(out_dir, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('Made by uDPRE from your edits (Editor & Randomizer) for Pokemon Brilliant Diamond v1.3.0.\n'
                f'Mods it was made on: {s.mods_text()}. Install those mods first, then put this folder\'s romfs over them '
                '(LayeredFS: atmosphere/contents/0100000011D90000/ on a Switch, or the emulator\'s mod folder).\n')
    with open(manifest, 'w', encoding='utf-8') as f:
        json.dump({'files': sorted(out), 'mods': s.mods_text()}, f, indent=1)
    log(f'exported {len(out)} files to {out_dir}')
    return {'files': sorted(out), 'warnings': warnings}


class ExportError(ValueError):
    pass


BANK = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch/Delphis_Main.bnk'
AUDIO_SOURCES = 'StreamingAssets/Audio/GeneratedSoundBanks/Switch/AudioSources.txt'


def audio_sources(game, bank_bytes):
    """the cry list a console modder uses to find a Pokemon's .wem: per Pokemon its five PLAY_PV_<dex>_<form>_<n> events
    and the .wem ids each plays (event -> action -> sound / container -> media)"""
    from .formats import wwise
    bank = wwise.Bank(bank_bytes)
    banks = wwise.Banks({'Delphis_Main': bank})
    lines = []
    for r in game.species_rows():
        m, f = game.key_of(r)
        for i in range(5):
            name = f'PLAY_PV_{m:03d}_{f:02d}_{i:02d}'
            plays = banks.plays(name)
            if not plays:
                continue
            media = set()
            for _aid, _t, target, _o in plays:
                if target:
                    media |= wwise.reachable(bank, target)[1]
            lines.append(f'{name} {game.pokemon_name(m, f)}' + ''.join(f' -> {x}.wem' for x in sorted(media)))
    return '\n'.join(lines) + '\n'


MANIFEST = 'udpre_export.json'
