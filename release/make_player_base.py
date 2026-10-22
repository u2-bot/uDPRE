"""Our player's own data files, made to fit the dump's resources.assets (which the converter writes from the dump as it is).

  py -3.13 -I release/make_player_base.py PLAYER_DIR SWITCH_DATA OUT_DIR
Writes OUT_DIR/Dpr_Data/globalgamemanagers.assets and OUT_DIR/udpre/base/globalgamemanagers (+ make_player_base.txt report).

Why: the dump's resources.assets points into globalgamemanagers.assets (the script registry: MonoScripts, Sprites-Default,
PreloadData) by the SWITCH path IDs - every MonoBehaviour's m_Script, the file's script-type table, maybe other fields that a
player file stores without a type tree. Our build numbered its registry its own way. So the registry is renumbered: every
object of ours whose counterpart exists in the Switch registry (MonoScript by namespace + class - SmartPoint.AssetAssistant
moved from AssetAssistant.dll into Assembly-CSharp.dll; Sprites-Default; PreloadData) takes the Switch path ID, the rest get
IDs above the Switch range in their old order. References into the registry are remapped: globalgamemanagers MonoManager
(m_Scripts), GraphicsSettings (m_SpritesDefaultMaterial), ResourceManager (replaced at install time anyway).
globalgamemanagers ScriptMapper (Shader.Find's table) points at shaders in resources.assets by OUR path IDs: they are remapped
by shader name to the Switch resources.assets; entries for shaders the Switch file does not hold (TextMesh Pro copies our
build added) are dropped.
Data / file ids are checked after writing: every remapped reference resolves to an object of the expected type and name.
"""
import os
import sys

import UnityPy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'converter'))
from udpre.unityfiles import walk_pptrs  # noqa: E402

GGM_ASSETS = 'globalgamemanagers.assets'
RESOURCES = 'resources.assets'


def load(path):
    return UnityPy.load(path).file


def registry_keys(sf, unique=True):
    """{key: path id} (unique=False: {key: [path ids]}); key = ('MonoScript', namespace, class, assembly) / (type, name).
    Our build holds three pairs of same-named MonoScripts (MoveType, DataType, RareType: two .cs files of one name, no
    serialized fields) - the Switch registry has no duplicate."""
    out = {}
    for o in sf.objects.values():
        k = registry_keys_one(o)
        if unique and k in out:
            raise SystemExit(f'duplicate registry key {k}')
        if unique:
            out[k] = o.path_id
        else:
            out.setdefault(k, []).append(o.path_id)
    return out


def plan_ids(ours_multi, switch, say):
    sw_by_class = {}
    for k, pid in switch.items():
        if k[0] == 'MonoScript':
            sw_by_class.setdefault(k[1:3], []).append((k[3], pid))
    new = {}
    ours = {}
    for k, pids in ours_multi.items():
        pids = sorted(pids)
        ours[k] = pids[0]            # the first copy may take the Switch id, later copies are numbered above
        if len(pids) > 1:
            say(f'  duplicate {k}: path ids {pids}, {pids[0]} may take the Switch id')
    for k, pid in ours.items():
        if k[0] == 'MonoScript':
            cands = sw_by_class.get(k[1:3], [])
            same = [p for a, p in cands if a == k[3]]
            if same:
                new[pid] = same[0]
            elif len(cands) == 1:
                new[pid] = cands[0][1]
                say(f'  {k[1]}.{k[2]}: {k[3]} <- Switch {cands[0][0]}')
            elif len(cands) > 1:
                raise SystemExit(f'{k}: several Switch scripts of that class in other assemblies {cands}')
        elif k in switch:
            new[pid] = switch[k]
    used = set(new.values())
    if len(used) != len(new):
        raise SystemExit('two of our registry objects map to one Switch path id')
    nxt = max(switch.values()) + 1
    for pid in sorted(p for pids in ours_multi.values() for p in pids):
        if pid not in new:
            while nxt in used:
                nxt += 1
            new[pid] = nxt
            used.add(nxt)
            nxt += 1
    return new


def rekey(sf, idmap):
    objs = list(sf.objects.values())
    for o in objs:
        o.path_id = idmap[o.path_id]
    sf.objects = {o.path_id: o for o in sorted(objs, key=lambda x: x.path_id)}


def main():
    player, switch_data, out = sys.argv[1:4]
    pdata = os.path.join(player, 'Dpr_Data')
    log = []

    def say(s):
        print(s)
        log.append(s)

    sw_reg = load(os.path.join(switch_data, GGM_ASSETS))
    reg = load(os.path.join(pdata, GGM_ASSETS))
    sw_keys, keys_multi = registry_keys(sw_reg), registry_keys(reg, unique=False)
    idmap = plan_ids(keys_multi, sw_keys, say)
    sw_ids = set(sw_keys.values())
    kept = sum(1 for p in idmap.values() if p in sw_ids)
    say(f'registry: {len(idmap)} objects, {kept} take a Switch path id, {len(idmap) - kept} numbered above '
        f'{max(sw_ids)}; Switch registry {len(sw_keys)} objects')
    missing = [k for k in sw_keys if k[0] == 'MonoScript' and sw_keys[k] not in idmap.values()]
    asm = {}
    for k in missing:
        asm[k[3]] = asm.get(k[3], 0) + 1
    say(f'Switch scripts with no class of ours (by assembly): {asm}')
    # local references inside the registry (none expected beyond PreloadData's)
    for o in reg.objects.values():
        if o.type.name == 'MonoScript':
            continue
        tree = o.read_typetree()

        def loc(p):
            if p['m_FileID'] == 0 and p['m_PathID'] in idmap:
                return {'m_FileID': 0, 'm_PathID': idmap[p['m_PathID']]}
            return None
        if walk_pptrs(tree, loc) is not None:
            o.save_typetree(tree)
    rekey(reg, idmap)

    # globalgamemanagers
    ggm = load(os.path.join(pdata, 'globalgamemanagers'))
    ext = [e.path for e in ggm.externals]
    reg_fid = ext.index(GGM_ASSETS) + 1
    res_fid = ext.index(RESOURCES) + 1
    pc_res = load(os.path.join(pdata, RESOURCES))
    sw_res = load(os.path.join(switch_data, RESOURCES))

    def shader_names(sf):
        return {o.path_id: o.read_typetree()['m_ParsedForm']['m_Name'] for o in sf.objects.values() if o.type.name == 'Shader'}
    pc_sh, sw_sh = shader_names(pc_res), shader_names(sw_res)
    sw_sh_by_name = {}
    for pid, n in sw_sh.items():
        sw_sh_by_name.setdefault(n, pid)
    counts = {}
    for o in ggm.objects.values():
        t = o.type.name
        tree = o.read_typetree()

        def remap(p, t=t):
            if p['m_FileID'] == reg_fid and p['m_PathID']:
                counts[(t, 'registry')] = counts.get((t, 'registry'), 0) + 1
                return {'m_FileID': reg_fid, 'm_PathID': idmap[p['m_PathID']]}
            return None
        changed = walk_pptrs(tree, remap) is not None
        if t == 'ScriptMapper':
            pairs = tree['m_Shaders']['m_ObjectToName']
            new_pairs = []
            for pair in pairs:
                p, name = pair
                if p['m_FileID'] == res_fid:
                    n = pc_sh.get(p['m_PathID'])
                    if n is None or n != name:
                        raise SystemExit(f'ScriptMapper: {name} -> resources.assets {p["m_PathID"]} = {n}')
                    if n not in sw_sh_by_name:
                        counts['ScriptMapper dropped'] = counts.get('ScriptMapper dropped', 0) + 1
                        say(f'  ScriptMapper: dropped {name} (not in the Switch resources.assets)')
                        continue
                    pair = ({'m_FileID': res_fid, 'm_PathID': sw_sh_by_name[n]}, name)
                    counts['ScriptMapper remapped'] = counts.get('ScriptMapper remapped', 0) + 1
                new_pairs.append(pair)
            tree['m_Shaders']['m_ObjectToName'] = new_pairs
            changed = True
        if changed:
            o.save_typetree(tree)
    say(f'globalgamemanagers references remapped: {counts}')

    os.makedirs(os.path.join(out, 'Dpr_Data'), exist_ok=True)
    os.makedirs(os.path.join(out, 'udpre', 'base'), exist_ok=True)
    p_reg = os.path.join(out, 'Dpr_Data', GGM_ASSETS)
    p_ggm = os.path.join(out, 'udpre', 'base', 'globalgamemanagers')
    with open(p_reg, 'wb') as f:
        f.write(reg.save())
    with open(p_ggm, 'wb') as f:
        f.write(ggm.save())

    # check: re-read, every MonoManager script resolves to a MonoScript; the same classes as before
    reg2, ggm2 = load(p_reg), load(p_ggm)
    before = {pid: k for k, pids in keys_multi.items() for pid in pids}
    back = {new: old for old, new in idmap.items()}
    for o in reg2.objects.values():
        k = registry_keys_one(o)
        if before.get(back.get(o.path_id)) != k:
            raise SystemExit(f'check: registry object {o.path_id} is {k}, expected {before.get(back.get(o.path_id))}')
    for k, pid in sw_keys.items():
        o = reg2.objects.get(pid)
        if o is not None and k[0] == 'MonoScript':
            mk = registry_keys_one(o)
            if mk[1:3] != k[1:3]:
                raise SystemExit(f'check: Switch id {pid} = {k} but ours holds {mk}')
    say(f'check: {len(reg2.objects)} registry objects carry their own class; every shared Switch id holds the same class')
    for o in ggm2.objects.values():
        if o.type.name == 'MonoManager':
            scripts = o.read_typetree()['m_Scripts']
            bad = [p for p in scripts if p['m_FileID'] == reg_fid and p['m_PathID'] not in reg2.objects]
            if bad:
                raise SystemExit(f'check: {len(bad)} MonoManager scripts do not resolve')
            say(f'check: MonoManager {len(scripts)} scripts resolve')
    say(f'-> {os.path.relpath(p_reg, out)}\n-> {os.path.relpath(p_ggm, out)}')
    with open(os.path.join(out, 'udpre', 'make_player_base.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(log) + '\n')


def registry_keys_one(o):
    if o.type.name == 'MonoScript':
        t = o.read_typetree()
        return ('MonoScript', t.get('m_Namespace', ''), t['m_ClassName'], t['m_AssemblyName'])
    if o.type.name == 'PreloadData':
        return ('PreloadData', '')
    return (o.type.name, o.peek_name())


if __name__ == '__main__':
    main()
