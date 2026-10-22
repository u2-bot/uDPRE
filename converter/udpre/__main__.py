"""uDPRE entry point.

  uDPRE.exe                         window: pick the dump once, convert, play (gui.py)
  uDPRE.exe convert DUMP [--workers N] [--root DIR]   console conversion
  uDPRE.exe status [--root DIR]
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
    if not args:
        from . import gui
        return gui.main(root)
    attach_console(root)
    cmd = args.pop(0)
    from . import install
    if cmd == 'convert':
        if not args:
            print(__doc__)
            return 2
        last = {}

        def progress(stage, done, total):
            k = (stage, done * 100 // max(total, 1))
            if last.get(stage) != k:
                last[stage] = k
                print(f'{stage}: {done}/{total}', flush=True)
        try:
            r = install.run(root, args[0], int(workers) if workers else None, progress, lambda s: print(s, flush=True))
        except (install.DumpError, install.ConvertError) as e:
            print(f'PROBLEM: {e}')
            return 1
        print(f'done: {r}')
        return 0
    if cmd == 'status':
        p = install.Paths(root)
        print({'installed': install.is_installed(p), 'config': install.load_config(p)})
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
