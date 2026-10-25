"""Build uDPRE.exe (PyInstaller, one-folder) from converter/.

  py -3.13 -I release/build_exe.py [DIST_DIR]      (default work dir: <repo>/build/, dist: <repo>/build/dist)
Output DIST_DIR = uDPRE.exe + udpre_runtime/ (Python, UnityPy, numpy, texture2ddecoder ...). make_release.py --exe DIST_DIR
copies it into a release folder next to Dpr.exe. One-folder, not one-file: a one-file exe unpacks itself to %TEMP% on every
start and again in each of the converter's worker processes.
libvpx (movies.py re-encodes a mod's VP9 movies to VP8): the two DLLs of PyAV 19.0.2's Windows wheel that make up libvpx
1.17.0 (libvpx, BSD-3-Clause + patent grant; the winpthreads runtime it imports, MIT) go to udpre_runtime/vpx/, checked by
sha256. PyAV itself is NOT bundled: its FFmpeg build links GPL encoders (x264, x265).
Pinned build inputs: converter/requirements.txt, release/requirements-build.txt.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VPX_DLLS = {
    'libvpx-1-dd81d2b55a771749d485047772201cc1.dll': '738629b026940c256dfe988a62062bdc96ae5065d13163bf7e579dc95a4634f4',
    'libwinpthread-1-3e9f18fdf7e856e1e9fedd138e84e874.dll': '3e9f18fdf7e856e1e9fedd138e84e874542e8717272fa7fdae5d0d826e88658c',
}


def vpx_source():
    import importlib.util
    spec = importlib.util.find_spec('av')
    if not spec or not spec.submodule_search_locations:
        sys.exit('PyAV 19.0.2 is not installed (release/requirements-build.txt): it is where the libvpx DLLs come from')
    return os.path.join(os.path.dirname(list(spec.submodule_search_locations)[0]), 'av.libs')


def main():
    work = os.path.join(REPO, 'build')
    dist = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(work, 'dist')
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'uDPRE',
            '--contents-directory', 'udpre_runtime', '--distpath', dist, '--workpath', os.path.join(work, 'pyinstaller'),
            '--specpath', os.path.join(work, 'spec'), '--paths', os.path.join(REPO, 'converter'),
            '--collect-all', 'UnityPy', '--collect-all', 'texture2ddecoder', '--hidden-import', 'udpre.gui',
            '--collect-submodules', 'udpre',            # the Studio's pages are imported by name (importlib)
            '--exclude-module', 'av', '--exclude-module', 'matplotlib', '--exclude-module', 'IPython',
            '--exclude-module', 'pytest', '--exclude-module', 'setuptools',
            os.path.join(REPO, 'converter', 'uDPRE.py')]
    print('>', ' '.join(args), flush=True)
    r = subprocess.run(args)
    if r.returncode:
        return r.returncode
    src = vpx_source()
    dst = os.path.join(dist, 'uDPRE', 'udpre_runtime', 'vpx')
    os.makedirs(dst, exist_ok=True)
    for name, want in VPX_DLLS.items():
        p = os.path.join(src, name)
        got = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.isfile(p) else None
        if got != want:
            sys.exit(f'{p}: sha256 {got}, expected {want} (PyAV 19.0.2 wheel)')
        shutil.copyfile(p, os.path.join(dst, name))
    if glob.glob(os.path.join(dist, 'uDPRE', 'udpre_runtime', 'av*')):
        sys.exit('PyAV ended up in the runtime - it must not ship (GPL encoders in its FFmpeg build)')
    exe = os.path.join(dist, 'uDPRE', 'uDPRE.exe')
    print(f'built {exe} ({os.path.getsize(exe)} bytes); folder {os.path.join(dist, "uDPRE")}; libvpx -> {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
