"""uDPRE entry point.

  uDPRE.exe                         window: pick the dump once, choose mods, convert, play (gui.py)
  uDPRE.exe convert [DUMP] [--mods ID,ID|none] [--options ID.OPTION=CHOICE,...] [--workers N] [--root DIR]
                                    console conversion (no DUMP = the dump of the last conversion; no --mods = the mods chosen
                                    last time; --options = picks under a pack's tick, e.g. --options shinyodds.odds=6, the
                                    other picks stay as last time; after an update or a mod change it makes only what changed)
  uDPRE.exe mods [--root DIR]       the mod packs in the mods folder, which ones are on, their options, the downloads they need
  uDPRE.exe locate FOLDER [--root DIR]  a mod download (e.g. Luminescent 2.2F) kept outside the mods folder
  uDPRE.exe status [--root DIR]     ready / refresh needed / not converted
  uDPRE.exe convert ... --edits on|off   use your edits (Editor & Randomizer) in this conversion or not
Editor & Randomizer, Beta (edits/project.json; a conversion builds them into the game when they are on):
  uDPRE.exe editor                  the Editor & Randomizer window
  uDPRE.exe edits [list|on|off|undo|clear]
  uDPRE.exe randomize SETTINGS.json [--seed N]   one more randomization (a file the Randomize page's "Save settings" wrote)
  uDPRE.exe json export|import pokemon|trainers|text FILE   the JSON converter
  uDPRE.exe export FOLDER           your edits as a console / emulator mod (LayeredFS romfs) in an empty FOLDER
Mod packs online (the window checks at every start and updates installed packs itself; "Get mods..." gets new ones):
  uDPRE.exe online [check]          what the catalogue has: installed / update ready / not installed
  uDPRE.exe online update           install every update of the installed packs
  uDPRE.exe online get ID[,ID...]|all   get packs (and the downloads they need, e.g. Luminescent 2.2F)
  uDPRE.exe online remove ID | rollback ID
Nuzlocke, Beta (the game enforces the rules; they apply the next time it starts):
  uDPRE.exe nuzlocke [show]         the settings (Dpr_Data/StreamingAssets/uDPRE/nuzlocke.txt) and every key
  uDPRE.exe nuzlocke preset nuzlocke|hardcore|off
  uDPRE.exe nuzlocke set KEY=VALUE [KEY=VALUE ...]   e.g. set level_cap=hard battle_items=balls_only
  uDPRE.exe nuzlocke run            the run of the newest save: areas, the graveyard, the level cap
Wild Pokemon you can see, Beta (they walk around the overworld, walk into one to battle it; the game reads it when it starts):
  uDPRE.exe roaming [show]          the setting (pc_settings.ini roaming / roaming_count)
  uDPRE.exe roaming 0|1|2           off (as the game) | on, with the random encounters | on, instead of them
  uDPRE.exe roaming count N         how many at once (1 .. 8, default 4)
  uDPRE.exe roaming chase N         the percent of them that chase you (0 .. 100, default 25; the others only wander)
LAN play, Beta (Union Room, Colosseum, Underground, contests with other uDPRE players; the game reads it when it starts):
  uDPRE.exe lan [show]              the settings, this game's build and the firewall rule
  uDPRE.exe lan on|off
  uDPRE.exe lan port N              first port (default 39290; UDP + TCP, 8 in a row)
  uDPRE.exe lan peers A[,B...]|-    friends' addresses searched directly (Tailscale, the internet); - = none
  uDPRE.exe lan bind IP|-           use only the adapter with this address; - = every adapter
  uDPRE.exe lan world on|off        the overworld: see the other players walking around (battle, trade, team up with them)
  uDPRE.exe lan follow 0|1|2        following Pokemon: as the game | the lead outdoors | the lead everywhere it fits
  uDPRE.exe lan host                start a world host (keeps the overworld up while players come and go)
  uDPRE.exe lan firewall            add the Windows Firewall rule (asks for administrator rights)
Without --root the uDPRE folder is the one holding the executable (frozen) or the current folder.
"""
import os
import sys


def default_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.getcwd()


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def parse_options(text):
    """'shinyodds.odds=6,other.x=y' -> {'shinyodds': {'odds': '6'}, 'other': {'x': 'y'}}"""
    out = {}
    for item in filter(None, (t.strip() for t in (text or '').split(','))):
        key, sep, choice = item.partition('=')
        mod, dot, oid = key.partition('.')
        if not (sep and dot and mod and oid and choice):
            raise ValueError(f'--options {item}: write it as PACK.OPTION=CHOICE (uDPRE.exe mods lists them)')
        out.setdefault(mod, {})[oid] = choice
    return out


def attach_console(root):
    """uDPRE.exe is built windowed (no console for the window); the console commands print to the console they ran from,
    or - started without one - to udpre/state/console.log."""
    if sys.stdout is not None:
        return
    import ctypes
    if ctypes.windll.kernel32.AttachConsole(-1):
        sys.stdout = open('CONOUT$', 'w', buffering=1, encoding='utf-8', errors='replace')
    else:
        d = os.path.join(root, 'udpre', 'state')
        os.makedirs(d, exist_ok=True)
        sys.stdout = open(os.path.join(d, 'console.log'), 'a', buffering=1, encoding='utf-8', errors='replace')
    sys.stderr = sys.stdout


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    root = opt(args, '--root', default_root())
    workers = opt(args, '--workers')
    mods = opt(args, '--mods')
    options = opt(args, '--options')
    edits = opt(args, '--edits')
    seed = opt(args, '--seed')
    if not args:
        from . import gui
        return gui.main(root)
    if args[0] == 'editor':
        from .edit.ui import window
        return window.main(root) or 0
    attach_console(root)
    cmd = args.pop(0)
    from . import install
    if cmd in ('edits', 'randomize', 'json', 'export'):
        return edit_command(root, cmd, args, seed)
    if cmd == 'convert':
        last = {}

        def progress(stage, done, total):
            k = (stage, done * 100 // max(total, 1))
            if last.get(stage) != k:
                last[stage] = k
                print(f'{stage}: {done}/{total}', flush=True)
        chosen = None if mods is None else [m for m in mods.split(',') if m and m != 'none']
        try:
            picks = parse_options(options)
            dump = args[0] if args and args[0] != '-' else None         # '-' (or nothing) = the dump used last time
            r = install.run(root, dump, int(workers) if workers else None, progress,
                            lambda s: print(s, flush=True), mods=chosen, options=picks,
                            edits=None if edits is None else edits.lower() in ('on', '1', 'yes', 'true'))
        except (install.DumpError, install.ConvertError, ValueError) as e:
            print(f'PROBLEM: {e}')
            return 1
        print(f'done: {r}')
        return 0
    if cmd == 'mods':
        from . import mods as modlib
        p = install.Paths(root)
        cfg = install.load_config(p)
        found, problems = modlib.discover(p.mods, cfg.get('sources'))
        on = cfg.get('mods', [])
        print(f'mods folder: {p.mods}')
        for m in sorted(found.values(), key=lambda m: (m.order, m.id)):
            extra = ''.join([f'  needs {",".join(m.requires)}' if m.requires else '',
                             f'  not with {",".join(m.conflicts)}' if m.conflicts else ''])
            print(f'  [{"x" if m.id in on else " "}] {m.id:<14} {m.name} {m.version}{extra}')
            if m.author or m.url:
                print(f'        by {m.author or "-"}' + (f'  {m.url}' if m.url else ''))
            m.set_choice((cfg.get('options') or {}).get(m.id))
            for o in m.options:
                print(f'        option {m.id}.{o["id"]} - {o["name"]}:')
                for c in o['choices']:
                    mark = '*' if m.choice[o['id']] == c['id'] else ' '
                    print(f'          ({mark}) {c["id"]:<8} {c["name"]}' + ('  (default)' if c['id'] == o['default'] else ''))
            for sid in m.sources:
                where = m.source_paths.get(sid)
                print(f'        your {m.sources[sid].get("name", sid)}: '
                      + (where if where else f'NOT FOUND - {m.sources[sid].get("where", "")}'))
        for t in problems:
            print(f'  cannot use: {t}')
        return 0
    if cmd == 'locate':
        from . import mods as modlib
        p = install.Paths(root)
        cfg = install.load_config(p)
        folder = os.path.abspath(args[0]) if args else ''
        found, _ = modlib.discover(p.mods, cfg.get('sources'))
        hits = []
        for m in found.values():
            for sid in m.sources:
                data = modlib.find_source(folder, m, sid) if os.path.isdir(folder) else None
                if data:
                    cfg.setdefault('sources', {})[sid] = folder
                    hits.append(f'{m.sources[sid].get("name", sid)}: {data}')
        if not hits:
            from . import advice
            need = [f'The {m.name} pack needs exactly {m.sources[s].get("name", s)} {advice.get_from(m)}'.rstrip()
                    for m in found.values() for s in m.sources]
            print('PROBLEM: ' + advice.text(
                f'{folder or "(no folder given)"} holds none of the downloads your mod packs need',
                (need or [f'No pack in {p.mods} needs a download of its own']) +
                ['Give the folder you extracted that download to (with 7-Zip) - the one that has "romfs" inside: '
                 'uDPRE.exe locate "D:\\Mods\\Luminescent"']))
            return 1
        install.save_config(p, cfg)
        print('found ' + '; '.join(dict.fromkeys(hits)))
        return 0
    if cmd == 'status':
        p = install.Paths(root)
        st = install.status(p)
        cfg = install.load_config(p)
        info = install.release_info(p)
        print(f'uDPRE {info.get("udpre_version", "?")}, game base v{info.get("base_version", "?")}')
        print(f'state: {st["state"]}' + (f' ({st["reason"]})' if st['reason'] else ''))
        if st['stale']:
            print(f'bundles to convert again: {", ".join(st["stale"])}')
        on = cfg.get('mods', [])
        picks = ', '.join(f'{mid}.{oid}={cid}' for mid, d in (cfg.get('options') or {}).items() if mid in on
                          for oid, cid in d.items())
        print(f'dump: {cfg.get("dump", "-")}\nmods: {", ".join(on) or "-"}' + (f'\noptions: {picks}' if picks else '') +
              f'\nlast completed: {cfg.get("completed", "-")}')
        return 0
    if cmd == 'nuzlocke':
        return nuzlocke_command(root, args)
    if cmd == 'lan':
        return lan_command(root, args)
    if cmd == 'roaming':
        return roaming_command(root, args)
    if cmd == 'online':
        return online_command(root, args)
    print(__doc__)
    return 2


def online_command(root, args):
    from . import install, online
    p = install.Paths(root)
    sub = args.pop(0) if args else 'check'
    try:
        index = online.fetch_index(p)
        pl = online.plan(p, index)
    except online.OnlineError as e:
        print(f'The mod catalogue cannot be read: {e}')
        return 1
    if sub == 'check':
        if pl['udpre']:
            print(f'uDPRE: a new build ({pl["udpre"].get("version", "")}, {pl["udpre"]["build"]}) - the window updates itself;'
                  f' or unzip the new release over this folder')
        for it in pl['packs']:
            e = it['entry']
            extra = f' ({online.size_text(it["bytes"])})' if it['state'] in ('update', 'available') else ''
            print(f'  {e["id"]:<22} {e.get("version", ""):<12} {it["state"]}{extra}')
        for s in pl['sources']:
            if s['state'] == 'missing':
                print(f'  download {s["entry"]["name"]}: needed, {online.size_text(s["bytes"])}')
        return 0
    if sub in ('update', 'get'):
        want = {x for a in args for x in a.split(',') if x}
        if sub == 'update':
            items = [i for i in pl['packs'] if i['state'] == 'update']
        else:
            ids = {i['entry']['id'] for i in pl['packs']}
            bad = sorted(want - ids - {'all'})
            if not want or bad:
                print(f'uDPRE.exe online get ID[,ID...] | all   (unknown: {", ".join(bad)})' if bad else
                      'uDPRE.exe online get ID[,ID...] | all')
                return 1
            items = [i for i in pl['packs'] if i['state'] in ('update', 'available') and
                     ('all' in want or i['entry']['id'] in want)]
        relay = online.relay_url(p)
        for it in items:
            online.install_item(p, relay, it['entry'], it['path'], set(it['parts']), log=print)
        for s in online.plan(p, index)['sources']:
            if s['state'] == 'missing':
                online.install_item(p, relay, s['entry'], s['path'], set(s['parts']), log=print)
        print('done' if items else 'nothing to do' + (' (uDPRE itself has a new build - see "online check")'
                                                    if pl['udpre'] else ''))
        return 0
    if sub in ('remove', 'rollback'):
        for pid in args:
            it = next((i for i in pl['packs'] if i['entry']['id'] == pid), None)
            if it is None or it['state'] not in ('installed', 'update'):
                print(f'{pid}: not an installed pack')
                return 1
            (online.remove_pack if sub == 'remove' else online.rollback)(p, pid, it['path'])
            print(f'{pid}: {"removed (kept in udpre/state/online/previous)" if sub == "remove" else "previous version back"}')
        return 0
    print('uDPRE.exe online [check | update | get ID,...|all | remove ID | rollback ID]')
    return 2


def roaming_command(root, args):
    from . import lan, roaming
    sub = args.pop(0) if args else 'show'
    w = roaming.read(root)
    if sub == 'show':
        state, pack = roaming.support(root)
        print(f'wild Pokemon you can see: {w["mode"]} ({roaming.summary(w)})  '
              f'({lan.settings_path(root) or "no game here yet"})')
        print('game: ' + ('has them' if state == 'yes' else roaming.support_text(state, pack)))
        return 0
    try:
        if sub in ('0', '1', '2'):
            w['mode'] = int(sub)
        elif sub == 'count' and args and args[0].isdigit() and 1 <= int(args[0]) <= roaming.MAX_COUNT:
            w['count'] = int(args[0])
        elif sub == 'chase' and args and args[0].isdigit() and 0 <= int(args[0]) <= 100:
            w['chase'] = int(args[0])
        else:
            print(f'uDPRE.exe roaming [show | 0 | 1 | 2 | count 1..{roaming.MAX_COUNT} | chase 0..100]')
            return 1
        p = roaming.write(root, w['mode'], w['count'], w['chase'])
    except OSError as e:
        print(f'roaming: {e}')
        return 1
    print(f'saved to {p} - restart the game if it is running')
    return 0


def lan_command(root, args):
    from . import lan
    sub = args.pop(0) if args else 'show'
    s = lan.read_settings(root)
    if sub == 'show':
        sup = lan.player_supports(root)
        info = lan.read(root)
        print(f'LAN play: {"on" if s["lan"] else "off"}, port {s["port"]}, peers {", ".join(s["peers"]) or "-"}, '
              f'adapter {s["bind"] or "every"}, overworld {"on" if s["world"] else "off"}, '
              f'following Pokemon {s["follow"]} ({lan.FOLLOW_CHOICES[s["follow"]]})  '
              f'({lan.settings_path(root) or "no game here yet"})')
        print('game: ' + ('has LAN play' if sup else 'NO LAN play - convert with uDPRE 0.5.0' if sup is False else 'not converted'))
        print('build: ' + (f'{info.get("fingerprint", "")[:16]}  {info.get("label", "")}' if info else 'not written yet (convert)'))
        fw = lan.firewall_rule_present(root)
        print('firewall: ' + ('allowed' if fw else 'no rule yet (uDPRE.exe lan firewall)' if fw is False else 'cannot tell'))
        return 0
    if sub == 'firewall':
        ok = lan.allow_firewall(root)
        print('Answer Windows\' administrator prompt to add the rule.' if ok else 'Windows did not start the prompt.')
        return 0 if ok else 1
    if sub == 'host':
        ok = lan.start_world_host(root, root)
        print('World host started in its own window (close it to stop).' if ok else
              f'No world host here ({lan.HOST_EXE} comes with the uDPRE release).')
        return 0 if ok else 1
    try:
        if sub in ('on', 'off'):
            s['lan'] = sub == 'on'
        elif sub == 'port' and args:
            s['port'] = int(args[0])
            if not 1024 <= s['port'] < 65536 - lan.PORT_SPAN:
                raise ValueError(f'the port must be 1024 .. {65535 - lan.PORT_SPAN}')
        elif sub == 'peers' and args:
            s['peers'] = [] if args[0] == '-' else [x.strip() for x in ' '.join(args).replace(';', ',').split(',') if x.strip()]
        elif sub == 'bind' and args:
            s['bind'] = '' if args[0] == '-' else args[0].strip()
        elif sub == 'world' and args and args[0] in ('on', 'off'):
            s['world'] = args[0] == 'on'
        elif sub == 'follow' and args and args[0] in ('0', '1', '2'):
            s['follow'] = int(args[0])
        else:
            print('uDPRE.exe lan [show | on | off | port N | peers A[,B...]|- | bind IP|- | world on|off | follow 0|1|2 | '
                  'host | firewall]')
            return 1
        p = lan.write_settings(root, s['lan'], s['port'], s['peers'], s['bind'], s['world'], s['follow'])
    except (ValueError, OSError) as e:
        print(f'lan: {e}')
        return 1
    print(f'saved to {p} - restart the game if it is running')
    return 0


def nuzlocke_command(root, args):
    from . import nuzlocke as nz
    sub = args.pop(0) if args else 'show'
    vals = nz.read(root)
    if sub == 'show':
        print(f'Nuzlocke: {nz.summary(vals)}  ({nz.path(root)})')
        if nz.player_supports(root) is False:
            print('The game in this folder has no Nuzlocke mode yet: convert first (uDPRE 0.4.0 or newer).')
        for key, label, kind, choices, group, rule in nz.SETTINGS:
            allowed = '|'.join(c for c, _ in choices) if kind == 'choice' else \
                '1|0' if kind == 'bool' else 'number' if kind == 'int' else 'numbers,split,by,commas'
            print(f'  {key}={vals[key]}    [{allowed}] {label}' + (f' ({rule})' if rule else ''))
        print('Presets: ' + ', '.join(nz.PRESETS) + '   (uDPRE.exe nuzlocke preset hardcore)')
        return 0
    if sub in ('preset', 'off', 'set'):
        try:
            if sub == 'off':
                vals['enabled'] = 0
            elif sub == 'preset':
                name = args[0].lower() if args else ''
                if name not in nz.PRESETS:
                    print(f'Presets: {", ".join(nz.PRESETS)}')
                    return 1
                vals = dict(nz.PRESETS[name])
            else:
                if not args:
                    print('uDPRE.exe nuzlocke set KEY=VALUE [KEY=VALUE ...]   (uDPRE.exe nuzlocke show lists the keys)')
                    return 1
                for item in args:
                    k, sep, v = item.partition('=')
                    if not sep:
                        raise ValueError(f'{item}: write it as KEY=VALUE')
                    vals[k.strip().lower()] = nz.normalize(k.strip().lower(), v)
            vals = nz.write(root, vals)
        except ValueError as e:
            print(e)
            return 1
        print(f'Nuzlocke: {nz.summary(vals)} - saved; the game uses it the next time it starts')
        return 0
    if sub == 'run':
        run, folder = nz.load_run(root)
        print('\n'.join(nz.run_text(run)))
        if folder:
            print(f'\nSave folder: {folder}')
        return 0
    print('uDPRE.exe nuzlocke [show | preset nuzlocke|hardcore|off | set KEY=VALUE ... | off | run]')
    return 2


def edit_command(root, cmd, args, seed):
    import json
    from . import install
    from .edit.project import describe
    p = install.Paths(root)
    if cmd == 'edits':
        from .edit import build as editbuild
        from .edit.project import Project
        what = args[0] if args else 'list'
        cfg = install.load_config(p)
        if what in ('on', 'off'):
            cfg['edits_on'] = what == 'on'
            install.save_config(p, cfg)
            print(f'edits {what} - the next conversion (convert / the window\'s Apply) uses this')
            return 0
        proj = Project(editbuild.project_path(root))
        if what == 'undo' and proj.ops:
            proj.ops.pop()
            proj.save(editbuild.project_path(root))
        elif what == 'clear':
            proj.ops = []
            proj.save(editbuild.project_path(root))
        print(f'edits: {len(proj.ops)} operations, {"ON" if cfg.get("edits_on") else "off"}')
        for i, op in enumerate(proj.ops):
            print(f'  {i + 1:4d}  {describe(op)}')
        return 0
    from .edit.session import Session
    try:
        s = Session(root, log=lambda t: print(t, flush=True))
    except (install.DumpError, ValueError) as e:
        print(f'PROBLEM: {e}')
        return 1
    if cmd == 'randomize':
        if not args:
            print('PROBLEM: give the settings file (the Randomize page\'s "Save settings")')
            return 1
        with open(args[0], encoding='utf-8') as f:
            d = json.load(f)
        settings = d.get('settings', d)
        sd = int(seed if seed is not None else d.get('seed', 1))
        w = s.run({'op': 'randomize', 'seed': sd, 'settings': settings})
        print(f'randomized (seed {sd})' + (f'; notes: {w}' if w else '') + f'; {len(s.project.ops)} operations')
        return 0
    if cmd == 'json':
        from .edit import jsonconv
        if len(args) < 3 or args[0] not in ('export', 'import') or args[1] not in ('pokemon', 'trainers', 'text'):
            print('PROBLEM: uDPRE.exe json export|import pokemon|trainers|text FILE')
            return 1
        ex = {'pokemon': jsonconv.export_pokemon, 'trainers': jsonconv.export_trainers, 'text': jsonconv.export_text}
        im = {'pokemon': jsonconv.import_pokemon, 'trainers': jsonconv.import_trainers, 'text': jsonconv.import_text}
        if args[0] == 'export':
            with open(args[2], 'w', encoding='utf-8') as f:
                json.dump(ex[args[1]](s.game), f, indent=2, ensure_ascii=False)
            print(f'{args[1]} written to {args[2]}')
            return 0
        try:
            with open(args[2], encoding='utf-8') as f:
                ops = im[args[1]](s.game, json.load(f))
        except (ValueError, OSError) as e:
            print(f'PROBLEM: {e}')
            return 1
        s.commit(ops)
        print(f'{len(ops)} changes imported into your edits')
        return 0
    if cmd == 'export':
        from .edit.export import ExportError, export
        if not args:
            print('PROBLEM: give an empty folder')
            return 1
        try:
            r = export(s, args[0], log=lambda t: print(t, flush=True))
        except (ExportError, OSError) as e:
            print(f'PROBLEM: {e}')
            return 1
        print(f'{len(r["files"])} files written' + (f'; {len(r["warnings"])} operations skipped' if r['warnings'] else ''))
        return 0
    return 2


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
