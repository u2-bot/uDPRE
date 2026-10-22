"""release/bundles.txt = the bundles uDPRE converts: every record of the dump's Dpr.bin catalog that ships as a file.

  py -3.13 -I release/make_bundle_list.py CATALOG_TSV SWITCH_DATA [PLAYER_DIR]
CATALOG_TSV = a TSV dump of romfs/Data/StreamingAssets/AssetAssistant/Dpr.bin (one record per line: project, bundle name, ...).
The 401 shipped files in no record (sub-project manifests, Dpr/tmpshader, unused animation / sprite bundles) are unreachable
through AssetManager and are not converted. With PLAYER_DIR the list is compared with that Windows player's bundle set.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def tree_files(root):
    out = set()
    for d, _, fs in os.walk(root):
        for f in fs:
            if f != 'Dpr.bin' and not f.endswith('.manifest'):
                out.add(os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/'))
    return out


def main():
    cat, sw_data = sys.argv[1:3]
    sw = os.path.join(sw_data, 'StreamingAssets', 'AssetAssistant')
    recs = [l.rstrip('\n').split('\t') for l in open(cat, encoding='utf-8') if not l.startswith('#')]
    have, missing = [], []
    for r in recs:
        rel = r[0] + '/' + r[1]
        (have if os.path.isfile(os.path.join(sw, *rel.split('/'))) else missing).append(rel)
    print(f'records {len(recs)}: {len(have)} ship as files, {len(missing)} do not: {missing}')
    print(f'shipped files in no record: {len(tree_files(sw) - set(have))}')
    if len(sys.argv) > 3:
        pc = tree_files(os.path.join(sys.argv[3], 'Dpr_Data', 'StreamingAssets', 'AssetAssistant'))
        print(f'player {len(pc)} bundles: list-only {sorted(set(have) - pc)[:10]}, player-only {sorted(pc - set(have))[:10]}')
    with open(os.path.join(HERE, 'bundles.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(sorted(have)) + '\n')
    print(f'-> {os.path.join(HERE, "bundles.txt")} ({len(have)} bundles)')


if __name__ == '__main__':
    main()
