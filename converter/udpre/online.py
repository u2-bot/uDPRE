"""Mod packs online: the signed catalogue, update checks, downloads and installs, and uDPRE's own update.

The packs live as release files of a private repository; a relay (a Cloudflare Worker that holds a read-only token) answers
GET <relay>/v1/file/<release tag>/<file name> with a redirect to a short-lived download link. Its address comes with the
release (udpre/release.json "relay"); config.json "online_relay" or the UDPRE_RELAY environment variable override it.

The catalogue (release "catalog", file catalog.json) = {"format", "index": <JSON text>, "sig": <base64>} signed with the key
whose public half is PUBLIC_KEY: nothing the catalogue does not list by SHA-256 is ever installed. The index lists uDPRE's
own build and every pack (and the downloads packs need) as PARTS: each part = the pack's files matched by a rule (a path
prefix, optionally one bucket of crc32(path) % n, the first matching rule wins) packed as one .tar.xz, with a "tree" digest
of its files. A part whose files on disk give the same tree is kept, so a code-only update downloads only the part that
changed. Installing builds the new folder next to the old one (kept parts hard-linked), checks every new part's tree, then
swaps; the old folder waits in udpre/state/online/previous for one rollback.
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zlib

from . import __version__, ed25519, install, mods as modlib

FORMAT = 1
CATALOG_TAG = 'catalog'
CATALOG_NAME = 'catalog.json'
PUBLIC_KEY = bytes.fromhex('f6c497b1ee15b30d7f77f4afd437e905fd0c62576e9cbfdec5c908c5118839a7')
USER_AGENT = f'uDPRE/{__version__}'
CHUNK = 1 << 20


class OnlineError(RuntimeError):
    pass


def _dir(p, *sub):
    d = os.path.join(p.state, 'online', *sub)
    os.makedirs(d, exist_ok=True)
    return d


def relay_url(p):
    cfg = install.load_config(p)
    url = os.environ.get('UDPRE_RELAY') or cfg.get('online_relay') or install.release_info(p).get('relay') or ''
    return url.rstrip('/')


def enabled(p):
    """automatic checks: on unless config.json says "online_auto": false (the window's tick)"""
    return install.load_config(p).get('online_auto', True)


def size_text(n):
    return f'{n / 2**20:.1f} MiB' if n >= 1 << 20 else f'{max(1, round(n / 1024))} KiB'


def file_url(relay, tag, name):
    return f'{relay}/v1/file/{tag}/{name}'


# --- HTTP -------------------------------------------------------------------------------------------------------------

def _open(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=dict({'User-Agent': USER_AGENT}, **(headers or {})))
    return urllib.request.urlopen(req, timeout=timeout)


def get_bytes(url, limit=64 << 20):
    try:
        with _open(url) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise OnlineError(f'{url}: HTTP {e.code}') from None
    except (urllib.error.URLError, OSError) as e:
        raise OnlineError(f'{url}: {getattr(e, "reason", e)}') from None
    if len(data) > limit:
        raise OnlineError(f'{url}: larger than expected')
    return data


def download(url, dest, size, sha256, progress=None, stop=None):
    """-> dest, a file of `size` bytes whose SHA-256 is `sha256`. Resumes a .part left by an earlier try (HTTP Range)."""
    if os.path.isfile(dest) and os.path.getsize(dest) == size and _sha256(dest) == sha256:
        return dest
    part = dest + '.part'
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    if have > size:
        os.remove(part)
        have = 0
    for attempt in range(4):
        try:
            headers = {'Range': f'bytes={have}-'} if have else {}
            with _open(url, headers, timeout=60) as r:
                if have and r.status != 206:        # the server sent the whole file: start over
                    have = 0
                with open(part, 'ab' if have else 'wb') as f:
                    while True:
                        if stop and stop():
                            raise OnlineError('stopped')
                        buf = r.read(CHUNK)
                        if not buf:
                            break
                        f.write(buf)
                        have += len(buf)
                        if progress:
                            progress(have, size)
            break
        except OnlineError:
            raise
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise OnlineError(f'download failed: {getattr(e, "reason", e)}') from None
            time.sleep(2 * (attempt + 1))
            have = os.path.getsize(part) if os.path.isfile(part) else 0
    if have != size:
        raise OnlineError(f'download incomplete: {have} of {size} bytes')
    if _sha256(part) != sha256:
        os.remove(part)
        raise OnlineError('download damaged (its SHA-256 differs from the catalogue) - it will be fetched again')
    os.replace(part, dest)
    return dest


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for buf in iter(lambda: f.read(CHUNK), b''):
            h.update(buf)
    return h.hexdigest()


# --- the catalogue ----------------------------------------------------------------------------------------------------

def parse_catalog(raw, key=PUBLIC_KEY):
    """catalog.json bytes -> the index (dict), only when its signature is good"""
    try:
        env = json.loads(raw.decode('utf-8'))
        text, sig = env['index'], base64.b64decode(env['sig'])
    except (ValueError, KeyError, TypeError):
        raise OnlineError('the mod catalogue cannot be read') from None
    if not ed25519.verify(key, text.encode('utf-8'), sig):
        raise OnlineError('the mod catalogue is not signed by the uDPRE key - nothing is downloaded')
    index = json.loads(text)
    if index.get('format') != FORMAT:
        raise OnlineError(f'the mod catalogue has format {index.get("format")}; this uDPRE reads {FORMAT} - update uDPRE')
    return index


def fetch_index(p):
    relay = relay_url(p)
    if not relay:
        raise OnlineError('no download address in this uDPRE (udpre/release.json "relay")')
    return parse_catalog(get_bytes(file_url(relay, CATALOG_TAG, CATALOG_NAME)))


# --- parts and trees --------------------------------------------------------------------------------------------------

def part_of(rel, parts):
    """-> the name of the part a file belongs to (first matching rule), or None"""
    for pt in parts:
        pre = pt.get('prefix', '')
        if not rel.startswith(pre):
            continue
        b = pt.get('bucket')
        if b and zlib.crc32(rel.encode('utf-8')) % b[1] != b[0]:
            continue
        return pt['name']
    return None


def walk(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.endswith('.udpre_new')]
        for f in fn:
            if f.endswith('.part'):
                continue
            out.append(os.path.relpath(os.path.join(dp, f), root).replace('\\', '/'))
    return sorted(out)


class Hashes:
    """SHA-256 of files, cached by path + size + mtime + file id (udpre/state/online/hashes.json). The file id matters:
    unpacked parts all carry the same fixed mtime, so a changed file of the same size would otherwise keep its old hash."""

    def __init__(self, p):
        self.path = os.path.join(_dir(p), 'hashes.json')
        try:
            with open(self.path, encoding='utf-8') as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.dirty = False

    def get(self, path):
        st = os.stat(path)
        k = os.path.abspath(path)
        v = self.data.get(k)
        if v and len(v) > 3 and v[0] == st.st_size and v[1] == st.st_mtime_ns and v[3] == st.st_ino:
            return v[2]
        h = _sha256(path)
        self.data[k] = [st.st_size, st.st_mtime_ns, h, st.st_ino]
        self.dirty = True
        return h

    def move(self, src, dst):
        """the folder src was renamed to dst: src's entries follow it, the entries dst had before go"""
        s, d = os.path.abspath(src) + os.sep, os.path.abspath(dst) + os.sep
        data = {k: v for k, v in self.data.items() if not k.startswith(d)}
        for k in [k for k in data if k.startswith(s)]:
            data[d + k[len(s):]] = data.pop(k)
        self.data = data
        self.dirty = True

    def save(self):
        if self.dirty:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
            self.dirty = False


def tree(root, rels, hashes):
    h = hashlib.sha256()
    for rel in sorted(rels):
        full = os.path.join(root, *rel.split('/'))
        h.update(f'{rel}\t{os.path.getsize(full)}\t{hashes.get(full)}\n'.encode('utf-8'))
    return h.hexdigest()


def local_trees(root, parts, hashes):
    """-> {part name: tree} of the files under root (parts with no file there are missing)"""
    groups = {}
    for rel in walk(root):
        name = part_of(rel, parts)
        if name:
            groups.setdefault(name, []).append(rel)
    return {name: tree(root, rels, hashes) for name, rels in groups.items()}, groups


# --- what to do -------------------------------------------------------------------------------------------------------

def _is_link(path):
    return os.path.islink(path) or (hasattr(os.path, 'isjunction') and os.path.isjunction(path))


def plan(p, index, log=lambda s: None):
    """-> {'udpre': entry or None, 'packs': [item], 'sources': [item]}. A pack item: {'entry', 'state': 'installed' |
    'update' | 'available' | 'managed', 'path', 'parts': [names to download], 'bytes'}."""
    hashes = Hashes(p)
    found, _problems = modlib.discover(p.mods, install.load_config(p).get('sources'))
    out = {'udpre': None, 'packs': [], 'sources': []}
    u = index.get('udpre')
    mine = install.release_info(p).get('made', '')
    if u and u.get('build') and u['build'] != mine and u['build'] > mine:
        out['udpre'] = u
    for entry in index.get('packs', []):
        m = found.get(entry['id'])
        item = {'entry': entry, 'path': m.path if m else os.path.join(p.mods, entry['folder']), 'parts': [], 'bytes': 0}
        if m is None:
            item['state'] = 'available'
            item['parts'] = [pt['name'] for pt in entry['parts']]
        elif _is_link(m.path) or _is_link(os.path.dirname(m.path)) and os.path.dirname(m.path) != p.mods:
            item['state'] = 'managed'          # a link to a folder kept elsewhere: never written through
        else:
            trees, _g = local_trees(m.path, entry['parts'], hashes)
            item['parts'] = [pt['name'] for pt in entry['parts'] if trees.get(pt['name']) != pt['tree']]
            item['state'] = 'update' if item['parts'] else 'installed'
        item['bytes'] = sum(pt['asset']['size'] for pt in entry['parts'] if pt['name'] in item['parts'])
        out['packs'].append(item)
    hashes.save()
    # the downloads the packs need (e.g. Luminescent 2.2F): fetched only when no copy is found
    need = {sid for m in found.values() for sid in m.missing_sources()}
    for entry in index.get('sources', []):
        state = 'missing' if entry['id'] in need else 'present'
        out['sources'].append({'entry': entry, 'state': state, 'path': os.path.join(p.mods, entry['folder']),
                               'parts': [pt['name'] for pt in entry['parts']] if state == 'missing' else [],
                               'bytes': sum(pt['asset']['size'] for pt in entry['parts']) if state == 'missing' else 0})
    return out


def sources_for(index, pack_entry):
    """the catalogue's downloads a pack takes files from (its "sources" ids)"""
    want = set(pack_entry.get('sources', []))
    return [s for s in index.get('sources', []) if s['id'] in want]


# --- installing -------------------------------------------------------------------------------------------------------

def _link_or_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _extract(archive, dest):
    with tarfile.open(archive, 'r:xz') as t:
        try:
            t.extractall(dest, filter='data')
        except TypeError:                       # Python without extraction filters
            for mbr in t.getmembers():
                n = mbr.name.replace('\\', '/')
                if n.startswith('/') or '..' in n.split('/') or not (mbr.isfile() or mbr.isdir()):
                    raise OnlineError(f'unsafe path in a download: {n}')
            t.extractall(dest)


def install_item(p, relay, entry, path, need, log=print, progress=None, stop=None):
    """Download the parts `need` of a pack (or download) entry and make `path` hold exactly the entry's files."""
    if _is_link(path):
        raise OnlineError(f'{path} is a link to a folder elsewhere - uDPRE does not write through it')
    hashes = Hashes(p)
    new = path + '.udpre_new'
    if os.path.exists(new):
        shutil.rmtree(new)                      # a stopped earlier try (only ever made by uDPRE)
    os.makedirs(new)
    downloads = _dir(p, 'downloads')
    total = sum(pt['asset']['size'] for pt in entry['parts'] if pt['name'] in need)
    done = 0
    try:
        groups = local_trees(path, entry['parts'], hashes)[1] if os.path.isdir(path) else {}
        for pt in entry['parts']:
            if stop and stop():
                raise OnlineError('stopped')
            if pt['name'] not in need:
                for rel in groups.get(pt['name'], []):
                    _link_or_copy(os.path.join(path, *rel.split('/')), os.path.join(new, *rel.split('/')))
                continue
            a = pt['asset']
            log(f'{entry["name"]}: downloading {pt["name"]} ({size_text(a["size"])})')
            dest = os.path.join(downloads, a['sha256'] + '.tar.xz')
            download(file_url(relay, a['tag'], a['name']), dest, a['size'], a['sha256'],
                     progress=(lambda d, s, base=done: progress(base + d, total)) if progress else None, stop=stop)
            done += a['size']
            log(f'{entry["name"]}: unpacking {pt["name"]}')
            _extract(dest, new)
        # every part as the catalogue says (the downloaded ones are checked here, the kept ones were compared before)
        trees, _g = local_trees(new, entry['parts'], hashes)
        bad = [pt['name'] for pt in entry['parts'] if pt['name'] in need and trees.get(pt['name']) != pt['tree']]
        if bad:
            raise OnlineError(f'{entry["name"]}: unpacked files differ from the catalogue ({", ".join(bad)})')
    except BaseException:
        shutil.rmtree(new, ignore_errors=True)
        raise
    prev = _dir(p, 'previous')
    old = os.path.join(prev, entry['id'])
    if os.path.isdir(path):
        if os.path.exists(old):
            shutil.rmtree(old)
        os.replace(path, old)
        hashes.move(path, old)
    os.replace(new, path)
    hashes.move(new, path)                      # the hashes just checked are the installed files' now
    for pt in entry['parts']:
        if pt['name'] in need:
            try:
                os.remove(os.path.join(downloads, pt['asset']['sha256'] + '.tar.xz'))
            except OSError:
                pass
    hashes.save()
    log(f'{entry["name"]} {entry.get("version", "")}: installed in {os.path.relpath(path, p.root)}')


def rollback(p, pack_id, path):
    """put the previous version of a pack back (the one an update replaced)"""
    old = os.path.join(_dir(p, 'previous'), pack_id)
    if not os.path.isdir(old):
        raise OnlineError('no earlier version of this pack is kept')
    tmp = path + '.udpre_new'
    hashes = Hashes(p)
    if os.path.isdir(path):
        os.replace(path, tmp)
        hashes.move(path, tmp)
    os.replace(old, path)
    hashes.move(old, path)
    if os.path.isdir(tmp):
        os.replace(tmp, old)
        hashes.move(tmp, old)
    hashes.save()


def remove_pack(p, pack_id, path):
    """a pack the window removes: moved to udpre/state/online/previous (one undo), not deleted"""
    old = os.path.join(_dir(p, 'previous'), pack_id)
    if os.path.exists(old):
        shutil.rmtree(old)
    os.replace(path, old)


# --- uDPRE itself -----------------------------------------------------------------------------------------------------

def prepare_self_update(p, relay, u, log=print, progress=None, stop=None):
    """Download + unpack uDPRE's new build next to it; -> the command that applies it after this process ends."""
    import zipfile
    if not getattr(sys, 'frozen', False):
        raise OnlineError('uDPRE runs from its source here: update it with git, not online')
    a = u['asset']
    d = _dir(p, 'self')
    zpath = os.path.join(d, a['sha256'] + '.zip')
    log(f'uDPRE {u.get("version", "")}: downloading ({size_text(a["size"])})')
    download(file_url(relay, a['tag'], a['name']), zpath, a['size'], a['sha256'], progress=progress, stop=stop)
    new = os.path.join(d, 'new')
    if os.path.exists(new):
        shutil.rmtree(new)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            nn = n.replace('\\', '/')
            if nn.startswith('/') or '..' in nn.split('/') or ':' in nn:
                raise OnlineError(f'unsafe path in the uDPRE download: {n}')
        z.extractall(new)
    tops = os.listdir(new)
    src = os.path.join(new, tops[0]) if len(tops) == 1 and os.path.isdir(os.path.join(new, tops[0])) else new
    if not os.path.isfile(os.path.join(src, 'uDPRE.exe')):
        raise OnlineError('the uDPRE download has no uDPRE.exe')
    cmd = os.path.join(d, 'apply_update.cmd')
    failed = os.path.join(d, 'update_failed.txt')
    if os.path.exists(failed):
        os.remove(failed)
    with open(os.path.join(d, 'last_attempt.txt'), 'w', encoding='utf-8') as f:
        f.write(u.get('build', ''))
    q = lambda path: path.replace('%', '%%')    # noqa: E731 - a batch file expands %...%
    with open(cmd, 'w', encoding='utf-8') as f:
        # cmd reads a batch file in the console code page: switch it to UTF-8 first, so any folder name works
        # the Windows tools by full path: another "find" or "ping" earlier on PATH (Git's, say) would break the wait
        f.write('@echo off\r\n'
                'chcp 65001 >nul\r\n'
                'set "S=%SystemRoot%\\System32"\r\n'
                ':wait\r\n'
                '"%S%\\tasklist.exe" /FI "PID eq %1" /NH 2>nul | "%S%\\find.exe" " %1 " >nul '
                '&& ("%S%\\ping.exe" -n 2 127.0.0.1 >nul & goto wait)\r\n'
                f'"%S%\\robocopy.exe" "{q(src)}" "{q(p.root)}" /E /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\n'
                f'if errorlevel 8 (echo robocopy failed with code %errorlevel% > "{q(failed)}") '
                f'else (rmdir /s /q "{q(new)}" & del "{q(zpath)}")\r\n'
                f'cd /d "{q(p.root)}"\r\n'
                f'start "" "{q(os.path.join(p.root, "uDPRE.exe"))}"\r\n')
    return cmd


def self_update_failed(p, build):
    """-> a reason when the last self-update to `build` did not take (then the window does not try it again on its own)"""
    d = os.path.join(p.state, 'online', 'self')
    failed = os.path.join(d, 'update_failed.txt')
    if os.path.isfile(failed):
        return open(failed, encoding='utf-8', errors='replace').read().strip() or 'the copy failed'
    try:
        last = open(os.path.join(d, 'last_attempt.txt'), encoding='utf-8').read().strip()
    except OSError:
        return None
    return 'this build was installed but uDPRE still reports the old one' if last == build else None


def run_self_update(cmd):
    """start the prepared update; the caller exits right after (the command waits for this process)"""
    import subprocess
    # a hidden console the command's tools share (DETACHED_PROCESS would flash a window per tool); "call" keeps the
    # quotes of a path with spaces or parentheses intact under cmd /c
    flags = 0x00000200 | 0x08000000    # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(['cmd', '/d', '/c', 'call', cmd, str(os.getpid())], creationflags=flags, close_fds=True,
                     cwd=os.path.dirname(cmd))


def summary(pl):
    """one line for the window"""
    upd = [i['entry']['name'] for i in pl['packs'] if i['state'] == 'update']
    parts = []
    if pl['udpre']:
        parts.append(f'uDPRE {pl["udpre"].get("version", "")} (new build)')
    parts += upd
    if not parts:
        return 'Everything is up to date'
    return 'Updates: ' + ', '.join(parts)
