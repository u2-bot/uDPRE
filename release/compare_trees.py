"""Developer check: do two converted uDPRE folders hold identical game data? (md5 of every file under Dpr_Data)

  py -3.13 -I release/compare_trees.py UDPRE_DIR_A UDPRE_DIR_B
Two conversions of the same dump (other machine, other worker count, source tree vs uDPRE.exe) must give 0 differing files.
"""
import hashlib, os, sys
from concurrent.futures import ThreadPoolExecutor
a, b = sys.argv[1], sys.argv[2]
def files(r):
    out = set()
    for d, _, fs in os.walk(os.path.join(r, 'Dpr_Data')):
        for f in fs:
            out.add(os.path.relpath(os.path.join(d, f), r))
    return out
def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''): h.update(c)
    return h.hexdigest()
fa, fb = files(a), files(b)
print('only a', len(fa - fb), sorted(fa - fb)[:5], 'only b', len(fb - fa), sorted(fb - fa)[:5])
common = sorted(fa & fb)
with ThreadPoolExecutor(8) as ex:
    ha = list(ex.map(lambda r: md5(os.path.join(a, r)), common))
    hb = list(ex.map(lambda r: md5(os.path.join(b, r)), common))
diff = [r for r, x, y in zip(common, ha, hb) if x != y]
print('common', len(common), 'differ', len(diff), diff[:10])
