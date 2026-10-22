"""Small helpers over UnityPy shared by the bundle and player-file converters."""
import copy
import io

from UnityPy.enums import BuildTarget
from UnityPy.files.SerializedFile import SerializedFile

SWITCH = 38
WIN64 = 19


class ConvertError(ValueError):
    pass


class StreamFile:
    """A new .resS: chunks 16-byte aligned (as Unity writes them)."""

    def __init__(self):
        self.buf = io.BytesIO()

    def add(self, data):
        pad = (-self.buf.tell()) % 16
        if pad:
            self.buf.write(b'\0' * pad)
        off = self.buf.tell()
        self.buf.write(data)
        return off

    def bytes(self):
        return self.buf.getvalue()

    def __len__(self):
        return self.buf.tell()


class StreamSource:
    """Reads stream ranges of one serialized file out of named byte sources (archive entries or loose files) and records
    every range used, so a converter can prove it carried the whole .resS."""

    def __init__(self, sources):
        self.sources = sources          # {entry name: bytes-like}
        self.used = {}                  # entry name -> list of (offset, size)

    def read(self, sd):
        if not sd or not sd.get('size'):
            return b''
        name = sd['path'].rsplit('/', 1)[-1]
        if name not in self.sources:
            raise ConvertError(f'stream path {sd["path"]} names no known stream file ({sorted(self.sources)})')
        src = self.sources[name]
        off, size = sd['offset'], sd['size']
        if off + size > len(src):
            raise ConvertError(f'stream {name} range {off}+{size} beyond its {len(src)} bytes')
        self.used.setdefault(name, []).append((off, size))
        return bytes(src[off:off + size])

    def uncovered(self):
        """-> {entry name: bytes of that entry no recorded range covers, beyond 16-byte alignment gaps}."""
        out = {}
        for name, src in self.sources.items():
            ranges = sorted(self.used.get(name, []))
            covered, end = 0, 0
            for off, size in ranges:
                if off + size > end:
                    covered += off + size - max(off, end)
                    end = off + size
            gap = len(src) - covered
            if gap > 16 * (len(ranges) + 1):
                out[name] = gap
        return out


def set_windows(sf):
    if sf._m_target_platform != SWITCH:
        raise ConvertError(f'{sf.name}: target platform {sf._m_target_platform}, expected Switch ({SWITCH})')
    sf._m_target_platform = WIN64
    sf.target_platform = BuildTarget(WIN64)


def external_index(sf, path):
    """1-based FileID of the external whose path is `path` (or ends with /path), else None."""
    for i, e in enumerate(sf.externals):
        if e.path == path or e.path.endswith('/' + path):
            return i + 1
    return None


def add_external(sf, ident):
    """Appends a FileIdentifier {path, guid (hex str or bytes), type} -> its 1-based FileID."""
    if not sf.externals:
        raise ConvertError(f'{sf.name}: no external to copy a FileIdentifier layout from')
    e = copy.copy(sf.externals[0])
    e.path = ident['path']
    g = ident.get('guid')
    if g is not None and hasattr(e, 'guid'):
        e.guid = bytes.fromhex(g) if isinstance(g, str) else g
    if hasattr(e, 'type'):
        e.type = ident.get('type', 0)
    sf.externals.append(e)
    return len(sf.externals)


def walk_pptrs(node, fn):
    """Calls fn(pptr_dict) on every {'m_FileID', 'm_PathID'} inside a typetree; fn returns a replacement dict or None.
    Tuples (UnityPy's pair entries, e.g. Material m_TexEnvs) are rebuilt and stored back by the parent."""
    if isinstance(node, dict):
        if set(node.keys()) == {'m_FileID', 'm_PathID'}:
            return fn(node)
        changed = False
        for k, v in node.items():
            r = walk_pptrs(v, fn)
            if r is not None:
                node[k] = r
                changed = True
        return node if changed else None
    if isinstance(node, list):
        changed = False
        for i, v in enumerate(node):
            r = walk_pptrs(v, fn)
            if r is not None:
                node[i] = r
                changed = True
        return node if changed else None
    if isinstance(node, tuple):
        items = list(node)
        return tuple(items) if walk_pptrs(items, fn) is not None else None
    return None


def serialized_files(env):
    """-> [(entry name, SerializedFile)] of a loaded bundle, or [(name, sf)] for a loose serialized file."""
    if isinstance(env.file, SerializedFile):
        return [(env.file.name, env.file)]
    return [(n, f) for n, f in env.file.files.items() if isinstance(f, SerializedFile)]


def type_hash(obj):
    st = obj.serialized_type
    if st is None:
        return None
    h = st.old_type_hash
    return h.hex() if hasattr(h, 'hex') else str(h)
