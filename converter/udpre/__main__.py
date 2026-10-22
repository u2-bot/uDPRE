"""uDPRE entry point.

  uDPRE.exe                         window: pick the dump once, choose mods, convert, play (gui.py)
  uDPRE.exe convert [DUMP] [--mods ID,ID|none] [--workers N] [--root DIR]
                                    console conversion (no DUMP = the dump of the last conversion; no --mods = the mods chosen
                                    last time; after an update or a mod change it makes only what changed)
  uDPRE.exe mods [--root DIR]       the mod packs in the mods folder, which ones are on, and the downloads they need
  uDPRE.exe locate FOLDER [--root DIR]  a mod download (e.g. Luminescent 2.2F) kept outside the mods folder
  uDPRE.exe status [--root DIR]     ready / refresh needed / not converted
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
    if not args:
        from . import gui
        return gui.main(root)
    attach_console(root)
    cmd = args.pop(0)
    from . import install
    if cmd == 'convert':
        last = {}

        def progress(stage, done, total):
            k = (stage, done * 100 // max(total, 1))
            if last.get(stage) != k:
                last[stage] = k
                print(f'{stage}: {done}/{total}', flush=True)
        chosen = None if mods is None else [m for m in mods.split(',') if m and m != 'none']
        try:
            r = install.run(root, args[0] if args else None, int(workers) if workers else None, progress,
                            lambda s: print(s, flush=True), mods=chosen)
        except (install.DumpError, install.ConvertError) as e:
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
            print(f'PROBLEM: {folder or "(no folder given)"} holds no download a mod pack in {p.mods} needs')
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
        print(f'dump: {cfg.get("dump", "-")}\nmods: {", ".join(cfg.get("mods", [])) or "-"}\n'
              f'last completed: {cfg.get("completed", "-")}')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
