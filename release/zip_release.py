"""Zip a release folder (make_release.py output) for a GitHub Release: uDPRE-<version>-win64.zip.

  py -3.13 -I release/zip_release.py RELEASE_DIR [OUT_DIR]
Refuses a folder that holds converted game data (udpre/state/, StreamingAssets/AssetAssistant, Audio, Movie,
resources.assets, Dpr_Data/globalgamemanagers) - a release ships none of it - or whose audit did not pass.
"""
import json
import os
import sys
import zipfile

FORBIDDEN = ('udpre/state', 'Dpr_Data/StreamingAssets/AssetAssistant', 'Dpr_Data/StreamingAssets/Audio',
             'Dpr_Data/StreamingAssets/Movie', 'Dpr_Data/resources.assets', 'Dpr_Data/globalgamemanagers')


def main():
    src = os.path.abspath(sys.argv[1])
    out_dir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(src)
    info = json.load(open(os.path.join(src, 'udpre', 'release.json'), encoding='utf-8'))
    audit = open(os.path.join(src, 'udpre', 'audit.txt'), encoding='utf-8').readline()
    if ' 0 problems' not in audit:
        sys.exit(f'audit did not pass: {audit.strip()}')
    files = []
    for d, _, fs in os.walk(src):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), src).replace(os.sep, '/')
            if any(rel == x or rel.startswith(x + '/') or rel.startswith(x + '.') for x in FORBIDDEN):
                if rel != 'Dpr_Data/globalgamemanagers.assets':
                    sys.exit(f'{rel}: converted game data in the release folder - zip a fresh make_release.py output')
            files.append(rel)
    name = f'uDPRE-{info["udpre_version"]}-win64.zip'
    dst = os.path.join(out_dir, name)
    top = f'uDPRE-{info["udpre_version"]}'
    with zipfile.ZipFile(dst + '.part', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in sorted(files):
            z.write(os.path.join(src, *rel.split('/')), f'{top}/{rel}')
    os.replace(dst + '.part', dst)
    print(f'{dst}: {len(files)} files, {os.path.getsize(dst) / 2**20:.1f} MiB')


if __name__ == '__main__':
    main()
