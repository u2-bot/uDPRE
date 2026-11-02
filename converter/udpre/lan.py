"""LAN play: the build two games must share to meet, and the player's LAN settings.

The game player lists another game's Union Room, Colosseum, Underground, contest or overworld only when both play the same
game: the same LAN protocol, family (Brilliant Diamond / Luminescent), uDPRE release and the same data a link reads (the Pokemon,
battle, contest and Underground files, plus the contest / network tables of Dpr/masterdatas - dpr_tables). Cosmetic and
own-world mods (textures, text, models, trainers, shiny odds, Easy Mode, Dechibified) may differ; No Balance does not. uDPRE
writes Dpr_Data/StreamingAssets/uDPRE/lan.txt at every conversion: family, release, dpr_tables, the mod list in words (label,
shown to games of other builds) and the old pack-list fingerprint (log only). Nuzlocke rules do not count.

The settings live in the game's pc_settings.ini (next to its saves, LocalLow/<company>/<product>/):
  lan=0|1          LAN play on (default 1)
  lan_port=<n>     first port (default 39290); a game takes the first free of n .. n+7 for UDP discovery + TCP
  lan_peers=<a,b>  addresses searched directly besides the broadcasts (Tailscale, a friend over the internet)
  lan_bind=<ipv4>  use only this network adapter
  world=0|1        overworld multiplayer: see the other players of the same build walking around (default 1, needs lan=1)
  world_port=<n>   first port of the overworld session (default 39310, n .. n+7)
  follow=0|1|2     following Pokemon: 0 as the game (the party menu's pick, its outdoor places), 1 the lead Pokemon by itself in
                   those places (default), 2 the lead everywhere it fits (caves, buildings too) - LAN or not
  chat_key=<key>   the overworld chat-phrase key (a Unity KeyCode name, default T; empty = none)
The world host (uDPRE World Host.exe, next to uDPRE.exe) keeps an overworld up while players come and go: start_world_host.
"""
import hashlib
import json
import os
import subprocess

FILE = 'Dpr_Data/StreamingAssets/uDPRE/lan.txt'
SUPPORT_TYPE = b'PcLanConfig'       # the player's global-metadata.dat names it when the player has LAN play
DEFAULT_PORT = 39290
WORLD_PORT = 39310
PORT_SPAN = 8
RULE_NAME = 'uDPRE LAN play'
HOST_RULE_NAME = 'uDPRE World Host'
# the uDPRE version whose game player and LAN data this one plays with: lan.txt's release, so a uDPRE update that changes no
# game code (the converter, the window, the README) still meets the players of that version. Raise it to __version__ with
# every release that ships a new game player or World Host.
LAN_RELEASE = '0.5.8'


def path(root):
    return os.path.join(root, *FILE.split('/'))


def parts(chosen, edits_digest):
    """the build as data: [[pack id, version, [[option, choice], ...]], ...] in stack order + the edits digest"""
    packs = []
    for m in chosen:
        picks = sorted(dict(m.choice).items()) if m.options else []
        packs.append([m.id, str(m.version), [[k, v] for k, v in picks]])
    return {'packs': packs, 'edits': edits_digest or ''}


def fingerprint(chosen, edits_digest):
    data = json.dumps(parts(chosen, edits_digest), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(data.encode('ascii')).hexdigest()


def label(chosen, edits_digest):
    """the build in words (the game's log names it when it skips a session of another build)"""
    if not chosen:
        text = 'Brilliant Diamond'
    else:
        names = []
        for m in chosen:
            n = f'{m.name} {m.version}'.strip()
            if m.options:
                n += ' (' + ', '.join(f'{o.get("name", o["id"])}: {m.choice_name(o["id"])}' for o in m.options) + ')'
            names.append(n)
        text = ' + '.join(names)
    if edits_digest:
        text += ' + your edits ' + str(edits_digest)[:8]
    return text.replace('\n', ' ')


# the tables of Dpr/masterdatas a link reads (contests, network settings); its other 1,140 tables are the player's own world
DPR_TABLES = ('ContestCommonData', 'ContestWazaInfo', 'NetworkData')


def _monobehaviour_body(raw, name):
    """a MonoBehaviour's own data: past m_GameObject, m_Enabled, m_Script (whose path id differs between players of one game)
    and m_Name; the whole object when the header does not read as expected"""
    try:
        n = int.from_bytes(raw[28:32], 'little')
        if raw[32:32 + n].decode('utf-8') == name:
            return raw[(32 + n + 3) & ~3:]
    except (UnicodeDecodeError, ValueError):
        pass
    return raw


def dpr_tables_digest(root):
    """sha256 (hex) of DPR_TABLES in the game's converted Dpr/masterdatas, or None (no file / a table missing)"""
    p = os.path.join(root, 'Dpr_Data', 'StreamingAssets', 'AssetAssistant', 'Dpr', 'masterdatas')
    if not os.path.isfile(p):
        return None
    import UnityPy
    found = {}
    for obj in UnityPy.load(p).objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        try:
            name = obj.peek_name()
        except Exception:
            continue
        if name in DPR_TABLES and name not in found:
            found[name] = _monobehaviour_body(obj.get_raw_data(), name)
    if len(found) != len(DPR_TABLES):
        return None
    h = hashlib.sha256()
    for name in DPR_TABLES:
        h.update(name.encode('ascii') + len(found[name]).to_bytes(4, 'little') + found[name])
    return h.hexdigest()


def family_of(player_id):
    """the game a player is: Luminescent (lumi, lumi-dechib, ...) or Brilliant Diamond"""
    return 'lumi' if str(player_id or '').startswith('lumi') else 'bdsp'


def code_of(chosen, player_id):
    """the build of the game code a link runs: a Luminescent player (Luminescent's own or Dechibified's, built together from
    one code base) = the Luminescent pack's version; the vanilla player ships with uDPRE, so the release covers it"""
    if family_of(player_id) != 'lumi':
        return 'release'
    for m in chosen:
        if m.id == 'luminescent':
            return f'luminescent-{m.version}'
    return 'lumi'


def write(root, chosen, edits_digest, player_id='vanilla'):
    """-> the fingerprint written to lan.txt (the mod list; the game matches players by what they play -
    family, release and the shared game data, PcLanConfig - and shows this list only in words)"""
    fp = fingerprint(chosen, edits_digest)
    p = path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        tables = dpr_tables_digest(root)
    except Exception:
        tables = None   # the game then counts the whole Dpr/masterdatas file (strict)
    lines = ['# uDPRE LAN play - written by uDPRE at every conversion. Two games meet when they play the same game: same family,',
             '# same uDPRE release, same Pokemon / battle / contest / Underground data. Cosmetic mods may differ.',
             f'fingerprint={fp}', f'label={label(chosen, edits_digest)}', f'family={family_of(player_id)}',
             f'release={LAN_RELEASE}', f'code={code_of(chosen, player_id)}']
    if tables:
        lines.append(f'dpr_tables={tables[:16]}')
    tmp = p + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, p)
    return fp


def read(root):
    out = {}
    try:
        with open(path(root), encoding='utf-8') as f:
            for line in f:
                k, eq, v = line.strip().partition('=')
                if eq and not k.startswith('#'):
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def player_supports(root):
    """-> True / False: the player in this folder has LAN play (None = no player found)"""
    meta = os.path.join(root, 'Dpr_Data', 'il2cpp_data', 'Metadata', 'global-metadata.dat')
    try:
        with open(meta, 'rb') as f:
            data = f.read()
    except OSError:
        return None
    return (b'\x00' + SUPPORT_TYPE + b'\x00') in data


# --- the game's settings file -----------------------------------------------------------------------------------------------

def settings_path(root):
    """-> LocalLow/<company>/<product>/pc_settings.ini of this folder's game, or None (no player here)"""
    try:
        with open(os.path.join(root, 'Dpr_Data', 'app.info'), encoding='utf-8') as f:
            company, product = (f.read().splitlines() + ['', ''])[:2]
    except OSError:
        return None
    return os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'AppData', 'LocalLow', company.strip(),
                        product.strip(), 'pc_settings.ini')


def _ini_lines(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read().splitlines()
    except OSError:
        return []


def ini_values(root):
    """-> {key: value} of pc_settings.ini (keys lower case; a repeated key: the first line wins, as the game reads it)"""
    vals = {}
    p = settings_path(root)
    for line in _ini_lines(p) if p else []:
        k, eq, v = line.strip().partition('=')
        k = k.strip().lower()
        if eq and not k.startswith('#') and k not in vals:
            vals[k] = v.strip()
    return vals


def write_keys(root, new, comment):
    """sets the keys of `new` in pc_settings.ini, every other line kept as it is; keys not there yet go at the end in that
    order, under the comment line; -> the file path"""
    p = settings_path(root)
    if not p:
        raise OSError('no game in this folder yet (convert first)')
    lines, done = [], set()
    for line in _ini_lines(p):
        k = line.strip().partition('=')[0].strip().lower()
        if k in new and not k.startswith('#'):
            if k not in done:
                lines.append(f'{k}={new[k]}')
                done.add(k)
            continue
        lines.append(line)
    missing = [k for k in new if k not in done]
    if missing:
        lines.append(comment)
        lines += [f'{k}={new[k]}' for k in missing]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, p)
    return p


def read_settings(root):
    """-> {'lan': bool, 'port': int, 'peers': [str], 'bind': str, 'world': bool} as the game reads them (missing = defaults)"""
    vals = ini_values(root)
    try:
        port = int(vals.get('lan_port', DEFAULT_PORT))
        if not 0 < port < 65536 - PORT_SPAN:
            port = DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    peers = [x.strip() for x in vals.get('lan_peers', '').replace(';', ',').replace(' ', ',').split(',') if x.strip()]
    try:
        world_port = int(vals.get('world_port', WORLD_PORT))
        if not 0 < world_port < 65536 - PORT_SPAN:
            world_port = WORLD_PORT
    except ValueError:
        world_port = WORLD_PORT
    follow = vals.get('follow', '1').strip()
    return {'lan': vals.get('lan', '1').strip() != '0', 'port': port, 'peers': peers, 'bind': vals.get('lan_bind', ''),
            'world': vals.get('world', '1').strip() != '0', 'world_port': world_port,
            'follow': int(follow) if follow in ('0', '1', '2') else 1}


FOLLOW_CHOICES = ('Off - as the game (the party menu\'s pick, outdoors)',
                  'The lead Pokemon, where the game lets one follow (outdoors)',
                  'The lead Pokemon, everywhere it fits (caves and buildings too)')


def write_settings(root, lan=True, port=DEFAULT_PORT, peers=(), bind='', world=True, follow=1):
    """sets the lan keys, world and follow in pc_settings.ini, every other line kept as it is; -> the file path"""
    new = {'lan': '1' if lan else '0', 'lan_port': str(int(port)), 'lan_peers': ','.join(peers), 'lan_bind': bind.strip(),
           'world': '1' if world else '0', 'follow': str(follow if follow in (0, 1, 2) else 1)}
    return write_keys(root, new, '# LAN play (uDPRE): lan = 1 | 0; lan_port = first port (UDP + TCP, 8 in a row); '
                                 'lan_peers = addresses; lan_bind = one adapter; world = 1 | 0 (see the other players in the '
                                 'overworld); follow = 0 | 1 | 2 (following Pokemon: as the game | the lead outdoors | the lead '
                                 'everywhere it fits)')


# --- the world host -----------------------------------------------------------------------------------------------------------

HOST_EXE = 'uDPRE World Host.exe'


def world_host_exe(app_dir):
    """-> the world host next to uDPRE.exe, or None (a source checkout has none)"""
    p = os.path.join(app_dir, HOST_EXE)
    return p if os.path.isfile(p) else None


def start_world_host(app_dir, root):
    """starts the world host for this folder's game build in its own console window (it runs until that window closes);
    -> True when started"""
    exe = world_host_exe(app_dir)
    if not exe:
        return False
    s = read_settings(root)
    args = [exe, '--game', os.path.abspath(root), '--port', str(s['world_port'])]
    if s['bind']:
        args += ['--bind', s['bind']]
    if s['peers']:
        args += ['--peers', ','.join(s['peers'])]
    try:
        subprocess.Popen(args, cwd=app_dir, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        return True
    except OSError:
        return False


# --- Windows Firewall ---------------------------------------------------------------------------------------------------------

def game_exe(root):
    return os.path.join(root, 'Dpr.exe')


#
# Windows asks the first time a program listens, with only "Private networks" ticked: Allow then also writes a BLOCK rule for
# public networks (Cancel: block rules), and a block rule beats every allow rule. A PC whose network is "public" (often a server
# or a wired PC; VPN adapters too) then drops everything from other players - a forwarded port from the internet included -
# while the same program works over a network Windows counts as private. So the rules are read per program and per network kind,
# through Windows' own firewall object (HNetCfg.FwPolicy2: no administrator rights, the same in every Windows language), and
# "Allow LAN play..." turns off the block rules of the game and the world host and allows both on every network kind.

FW_DOMAIN, FW_PRIVATE, FW_PUBLIC = 1, 2, 4
FW_ALL = 0x7FFFFFFF
FW_KINDS = ((FW_DOMAIN, 'work (domain)'), (FW_PRIVATE, 'private'), (FW_PUBLIC, 'public'))

_FW_READ = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$p = New-Object -ComObject HNetCfg.FwPolicy2
'CUR ' + [int]$p.CurrentProfileTypes
foreach ($r in $p.Rules) {
  if ($r.Direction -eq 1 -and $r.Enabled -and $r.ApplicationName) { 'R ' + [int]$r.Action + ' ' + [int]$r.Profiles + ' ' + $r.ApplicationName }
}
'''

_FW_ALLOW = r'''
$ErrorActionPreference = 'Stop'
$p = New-Object -ComObject HNetCfg.FwPolicy2
function Norm($s) { try { [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($s)).ToLowerInvariant() } catch { '' } }
$bad = 0
foreach ($it in $items) {
  try {
    $want = Norm $it[0]
    $ours = $null
    foreach ($r in @($p.Rules)) {
      if ($r.Direction -ne 1 -or -not $r.ApplicationName -or (Norm $r.ApplicationName) -ne $want) { continue }
      if ($r.Action -eq 0) { if ($r.Enabled) { $r.Enabled = $false } }
      elseif ($r.Name -eq $it[1] -and $ours -eq $null) { $ours = $r }
    }
    if ($ours -eq $null) {
      $ours = New-Object -ComObject HNetCfg.FWRule
      $ours.Name = $it[1]
      $ours.Description = $it[2]
      $ours.ApplicationName = $it[0]
      $ours.Direction = 1
      $ours.Action = 1
      $ours.Profiles = 0x7FFFFFFF
      $ours.Enabled = $true
      $p.Rules.Add($ours)
    } else {
      $ours.Profiles = 0x7FFFFFFF
      $ours.Enabled = $true
    }
  } catch { $bad++ }
}
exit $bad
'''


def _ps_encoded(script):
    import base64
    return base64.b64encode(script.encode('utf-16-le')).decode('ascii')


def _ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def _elevated_cmd(encoded, elevate=True):
    """-> the command that runs an encoded script as administrator (Windows' prompt) and exits with its exit code; 99 when the
    prompt was answered No or could not start (elevate=False: the same without the prompt, for tests)"""
    ps = ("try { $q = Start-Process -FilePath powershell " + ("-Verb RunAs " if elevate else "") +
          "-WindowStyle Hidden -Wait -PassThru -ErrorAction Stop -ArgumentList "
          "'-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + encoded + "'; "
          "if ($q -eq $null) { exit 99 }; exit $q.ExitCode } catch { exit 99 }")
    return ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', ps]


def _norm(p):
    return os.path.normcase(os.path.abspath(os.path.expandvars(p)))


def firewall_programs(root, app_dir=None):
    """-> [(path, rule name, what it is)]: this folder's game and, when it is there, the world host"""
    out = [(os.path.abspath(game_exe(root)), RULE_NAME, 'the game')]
    host = world_host_exe(app_dir or root)
    if host:
        out.append((os.path.abspath(host), HOST_RULE_NAME, 'the world host'))
    return out


def read_firewall():
    """-> (current network kinds bitmask, [(action 0 block / 1 allow, network kinds bitmask, program)]) of the enabled inbound
    program rules, or None (cannot tell: no Windows Firewall, e.g. Proton)"""
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand',
                              _ps_encoded(_FW_READ)], capture_output=True, timeout=60,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    cur, rules = None, []
    for line in out.stdout.decode('utf-8', 'replace').splitlines():
        line = line.strip()
        if line.startswith('CUR '):
            try:
                cur = int(line[4:])
            except ValueError:
                pass
        elif line.startswith('R '):
            bits = line[2:].split(' ', 2)
            if len(bits) == 3:
                try:
                    rules.append((int(bits[0]), int(bits[1]), bits[2]))
                except ValueError:
                    pass
    return None if cur is None else (cur, rules)


def program_status(rules, exe, current=0):
    """-> (status, kinds) for one program from read_firewall's rules. status: 'allowed' (every network kind it may meet:
    private, public and work when this PC is on one), 'blocked' (a block rule on such a kind - kinds = the blocked kinds),
    'partial' (allowed only on some - kinds = the missing ones), 'none' (no rule: Windows will ask)"""
    want = FW_PRIVATE | FW_PUBLIC | (current & FW_DOMAIN)
    me = _norm(exe)
    allow = block = 0
    for action, kinds, prog in rules:
        try:
            if _norm(prog) != me:
                continue
        except (TypeError, ValueError):
            continue
        if action == 0:
            block |= kinds
        elif action == 1:
            allow |= kinds
    if block & want:
        return 'blocked', block & want
    if allow & want == want:
        return 'allowed', 0
    if allow:
        return 'partial', want & ~allow
    return 'none', want


def kinds_text(kinds):
    return ' and '.join(name for bit, name in FW_KINDS if kinds & bit) or 'no'


def firewall_status(root, app_dir=None):
    """-> [(what, path, status, kinds)] for this folder's game and world host, or None (cannot tell)"""
    fw = read_firewall()
    if fw is None:
        return None
    cur, rules = fw
    return [(what, exe) + program_status(rules, exe, cur) for exe, _name, what in firewall_programs(root, app_dir)]


def firewall_rule_present(root, app_dir=None):
    """-> True (the game and the world host are allowed on every network kind) / False / None (cannot tell)"""
    st = firewall_status(root, app_dir)
    if st is None:
        return None
    return all(s == 'allowed' for _w, _p, s, _k in st)


def firewall_summary(st):
    """the firewall_status list in words, one line per program"""
    if st is None:
        return ['cannot tell (no Windows Firewall here, or Windows did not answer)']
    out = []
    for what, _exe, status, kinds in st:
        if status == 'allowed':
            out.append(f'{what}: allowed')
        elif status == 'blocked':
            out.append(f'{what}: BLOCKED on {kinds_text(kinds)} networks - nobody can reach it there, a forwarded port '
                       'included (Allow LAN play... fixes it)')
        elif status == 'partial':
            out.append(f'{what}: allowed, but not on {kinds_text(kinds)} networks (Allow LAN play... fixes it)')
        else:
            out.append(f'{what}: no rule yet - Windows asks when it starts (Allow LAN play... allows it everywhere)')
    return out


def allow_firewall(root, app_dir=None, wait=False):
    """through Windows' own administrator prompt: turns off the inbound BLOCK rules of this folder's Dpr.exe and world host
    (Windows writes them when its first question is answered with only "Private" ticked, or Cancel) and allows both on every
    network kind (home, work, public - VPN adapters are often 'public'). -> True when the prompt was started (wait=False), or
    when it ran and every rule was made (wait=True)."""
    desc = {RULE_NAME: 'Overworld, Union Room, Colosseum, Underground and contests with other uDPRE players',
            HOST_RULE_NAME: 'The uDPRE world host: the overworld of every uDPRE player who joins this PC'}
    # an ArrayList: @(@(a, b, c)) with one program would flatten into three strings
    items = ''.join('[void]$items.Add(@(' + ', '.join(_ps_quote(x) for x in (exe, name, desc[name])) + '))\n'
                    for exe, name, _what in firewall_programs(root, app_dir))
    cmd = _elevated_cmd(_ps_encoded('$items = New-Object System.Collections.ArrayList\n' + items + _FW_ALLOW))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        if not wait:
            subprocess.Popen(cmd, creationflags=flags)
            return True
        return subprocess.run(cmd, capture_output=True, timeout=600, creationflags=flags).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
