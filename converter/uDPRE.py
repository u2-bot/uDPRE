"""Entry script for uDPRE.exe (PyInstaller) and for running from the source tree: py -3.13 -I converter/uDPRE.py ..."""
import multiprocessing
import os
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from udpre.__main__ import main
    sys.exit(main())
