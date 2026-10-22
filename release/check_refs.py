"""Developer check: references between the bundles of a converted (or patched) game folder.

  py -3.13 -I release/check_refs.py OUT_AA [--full LIST] [--shaders SHADERS_BUNDLE] [--workers N] [--report OUT.tsv]
OUT_AA = .../Dpr_Data/StreamingAssets/AssetAssistant. Every bundle's object table is read (CAB name -> path id -> type).
Checked in EVERY bundle: each Material's m_Shader resolves to a Shader object (a dangling one draws pink - the failure of a
PC patch copied over a uDPRE folder). With --full LIST (bundle paths, one per line): every PPtr of every object of those
bundles must resolve to an object of the CAB it names (Unity's built-in resource files are not checked).
--shaders: take the Dpr/shaders object table from that file instead (to show what a foreign shaders bundle would break).
Exit 1 when any reference dangles. The report lists every dangling reference: bundle, object, field owner type, target.
"""
import concurrent.futures as cf
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'converter'))

BUILTIN = ('Library/unity default resources', 'Resources/unity_builtin_extra')


def cab_of(path):
    return path.rsplit('/', 1)[-1].lower()


def scan(args):
    """-> (rel, [(cab, {pid: type})], [(owner pid, owner type, target cab, pid, need type or None)], error)"""
    path, rel, full = args
    import UnityPy
    from udpre.unityfiles import serialized_files, walk_pptrs
    tables, refs = [], []
    try:
        env = UnityPy.load(path)
        for name, sf in serialized_files(env):
            me = cab_of(name)
            tables.append((me, {pid: o.type.name for pid, o in sf.objects.items()}))
            ext = [e.path for e in sf.externals]

            def target(fid):
                if fid == 0:
                    return me
                p = ext[fid - 1]
                return None if p in BUILTIN else cab_of(p)
            for pid, o in sf.objects.items():
                t = o.type.name
                if not full and t != 'Material':
                    continue
                try:
                    tree = o.read_typetree()
                except Exception as e:
                    refs.append((pid, t, None, None, f'unreadable: {type(e).__name__}'))
                    continue
                if t == 'Material':
                    s = tree.get('m_Shader') or {}
                    if s.get('m_PathID'):
                        tc = target(s['m_FileID'])
                        if tc:
                            refs.append((pid, t, tc, s['m_PathID'], 'Shader'))
                if full:
                    def take(p, pid=pid, t=t):
                        if p['m_PathID']:
                            tc = target(p['m_FileID'])
                            if tc:
                                refs.append((pid, t, tc, p['m_PathID'], None))
                    walk_pptrs(tree, take)
        return rel, tables, refs, None
    except Exception as e:
        return rel, tables, refs, f'{type(e).__name__}: {e}'


def main():
    a = sys.argv[1:]
    flags = {'--full', '--workers', '--report', '--shaders'}
    opt = {f: a[a.index(f) + 1] for f in flags if f in a}
    out_aa = [x for i, x in enumerate(a) if x not in flags and (i == 0 or a[i - 1] not in flags)][0]
    full = set()
    if '--full' in opt:
        full = {l.strip() for l in open(opt['--full'], encoding='utf-8') if l.strip()}
    rels = []
    for d, _, fs in os.walk(out_aa):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), out_aa).replace(os.sep, '/')
            if rel != 'Dpr.bin' and not rel.endswith(('.manifest', '.part')):
                rels.append(rel)
    jobs = [(os.path.join(out_aa, *r.split('/')), r, r in full) for r in sorted(rels)]
    index, owner, refs_by, errors = {}, {}, {}, []
    with cf.ProcessPoolExecutor(max_workers=int(opt.get('--workers', os.cpu_count() - 1))) as ex:
        for i, (rel, tables, refs, err) in enumerate(ex.map(scan, jobs, chunksize=8)):
            if err:
                errors.append((rel, err))
            for cab, table in tables:
                # the language variants of a bundle (.en / .fr / ...) share one CAB name by design; the game loads one
                if cab in index:
                    index[cab] = {**index[cab], **table}
                else:
                    index[cab] = table
                owner.setdefault(cab, rel)
            refs_by[rel] = refs
            if (i + 1) % 2000 == 0:
                print(f'  {i + 1}/{len(jobs)}', flush=True)
    if '--shaders' in opt:
        _, tables, _, _ = scan((opt['--shaders'], 'Dpr/shaders', False))
        for cab, table in tables:
            index[cab] = table
    bad, n_mat, n_full, bad_mat = [], 0, 0, 0
    for rel, refs in refs_by.items():
        for opid, otype, cab, pid, need in refs:
            if cab is None:
                bad.append((rel, opid, otype, '-', '-', need))
                continue
            if need == 'Shader':
                n_mat += 1
            else:
                n_full += 1
            t = index.get(cab, {}).get(pid)
            if t is None:
                bad.append((rel, opid, otype, cab, pid, ('material shader: ' if need else '') +
                            ('missing CAB' if cab not in index else 'missing object')))
            elif need and t != need:
                bad.append((rel, opid, otype, cab, pid, f'material shader: is a {t}, not a {need}'))
            else:
                continue
            bad_mat += need == 'Shader'
    by_bundle = {}
    for b in bad:
        by_bundle[b[0]] = by_bundle.get(b[0], 0) + 1
    print(f'{len(jobs)} bundles read ({len(errors)} errors); {n_mat} material shader references, {bad_mat} of them '
          f'dangling; {n_full} references in {len(full)} fully checked bundles; {len(bad)} dangling in all, in '
          f'{len(by_bundle)} bundles')
    for rel, n in sorted(by_bundle.items(), key=lambda kv: -kv[1])[:15]:
        print(f'  {n:6} {rel}')
    for rel, err in errors[:10]:
        print(f'  ERROR {rel}: {err}')
    if '--report' in opt:
        with open(opt['--report'], 'w', encoding='utf-8', newline='\n') as f:
            f.write('bundle\tobject\towner_type\ttarget_cab\ttarget_pid\tproblem\n')
            for b in bad:
                f.write('\t'.join(str(x) for x in b) + '\n')
            for rel, err in errors:
                f.write(f'{rel}\t-\t-\t-\t-\tERROR {err}\n')
    return 1 if bad or errors else 0


if __name__ == '__main__':
    sys.exit(main())
