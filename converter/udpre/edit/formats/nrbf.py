"""MS-NRBF (.NET BinaryFormatter) streams, byte-exact - written from Microsoft's [MS-NRBF] specification.

Layer 1 (Stream): the file as its list of top-level records, each record a small object. A class record keeps its member
values in order; a member of BinaryType Primitive is a plain value, every other member is a nested record (a string, a
MemberReference, ObjectNull, a struct written inline, MemberPrimitiveTyped...). Array records keep their element records
including the ObjectNullMultiple(256) runs, so the writer emits exactly what was read: record order, object ids, library ids,
member type infos, reuse by MemberReference. BinaryLibrary records are kept in front of the record they preceded (BF writes
one right before the first class of its assembly, nested or not).

Facts used (MS-NRBF 2.1-2.7):
  RecordTypeEnum 0 SerializedStreamHeader(rootId, headerId, major, minor), 1 ClassWithId(objectId, metadataId),
  2 SystemClassWithMembers, 3 ClassWithMembers(+libraryId), 4 SystemClassWithMembersAndTypes,
  5 ClassWithMembersAndTypes(+libraryId), 6 BinaryObjectString(objectId, LPS), 7 BinaryArray, 8 MemberPrimitiveTyped,
  9 MemberReference(idRef), 10 ObjectNull, 11 MessageEnd, 12 BinaryLibrary(libraryId, LPS), 13 ObjectNullMultiple256(byte),
  14 ObjectNullMultiple(int32), 15 ArraySinglePrimitive, 16 ArraySingleObject, 17 ArraySingleString.
  ClassInfo = objectId, LPS name, int32 memberCount, memberCount LPS names. MemberTypeInfo = one BinaryTypeEnum byte per
  member, then per member: Primitive(0) / PrimitiveArray(7) a PrimitiveTypeEnum byte, SystemClass(3) an LPS class name,
  Class(4) LPS name + int32 libraryId; String(1) Object(2) ObjectArray(5) StringArray(6) nothing.
  LPS = 7-bit varint byte length + UTF-8. Primitive values are little-endian; DateTime is the raw 64-bit Ticks|Kind word.
  ClassWithId reuses the member layout of the earlier class record whose objectId is its metadataId.

Layer 2 (Manifest): the typed view of Dpr.bin = SmartPoint.AssetAssistant.AssetBundleDownloadManifest
  {int _version; string _projectName; AssetBundleRecord[] _records; string[] _assetBundleNamesWithVariant}
  AssetBundleRecord {string projectName, assetBundleName; RecordedHash hash (struct, inline); DateTime lastWriteTime;
  bool isStreamingSceneAssetBundle; string[] allDependencies, assetPaths; long size}.
  An unmodified manifest saves its original records (byte-identical); any edit re-serializes the object graph the way
  BinaryFormatter does (save() docstring) - measured to reproduce the shipped files too.
The game's boot lookup (AssetBundleDownloadManifest.BuildLookupTables): key = lower-cased asset path without a leading
"assets/"; a duplicate key THROWS, so duplicate_keys() must be empty before a manifest ships.
"""
import struct

# ---------------------------------------------------------------- primitives

# PrimitiveTypeEnum -> struct code. Floats and booleans are kept as raw integers so every bit survives a rewrite.
PRIM = {1: 'B', 2: 'B', 6: 'Q', 7: 'h', 8: 'i', 9: 'q', 10: 'b', 11: 'I', 12: 'q', 13: 'Q', 14: 'H', 15: 'I', 16: 'Q'}
P_BOOL, P_BYTE, P_CHAR, P_DECIMAL, P_DOUBLE, P_INT16, P_INT32, P_INT64 = 1, 2, 3, 5, 6, 7, 8, 9
P_SINGLE, P_TIMESPAN, P_DATETIME, P_STRING = 11, 12, 13, 18
B_PRIMITIVE, B_STRING, B_OBJECT, B_SYSTEMCLASS, B_CLASS, B_OBJECTARRAY, B_STRINGARRAY, B_PRIMITIVEARRAY = range(8)


class RawStr(bytes):
    """An LPS whose bytes are not canonical UTF-8 (or whose length varint is not minimal): written back as read."""
    __slots__ = ()


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]
        self.p += 4
        return v

    def lps(self):
        start = self.p
        n = shift = 0
        while True:
            b = self.u8()
            n |= (b & 0x7f) << shift
            shift += 7
            if not b & 0x80:
                break
        raw = self.d[self.p:self.p + n]
        self.p += n
        try:
            s = raw.decode('utf-8')
        except UnicodeDecodeError:
            return RawStr(self.d[start:self.p])
        if _lps(s) != self.d[start:self.p]:
            return RawStr(self.d[start:self.p])
        return s

    def prim(self, t):
        if t == P_CHAR:     # one UTF-8 encoded char
            b = self.d[self.p]
            n = 1 if b < 0x80 else 2 if b < 0xe0 else 3 if b < 0xf0 else 4
            v = self.d[self.p:self.p + n].decode('utf-8')
            self.p += n
            return v
        if t in (P_DECIMAL, P_STRING):
            return self.lps()
        c = PRIM[t]
        v = struct.unpack_from('<' + c, self.d, self.p)[0]
        self.p += struct.calcsize(c)
        return v


def _lps(s):
    if isinstance(s, RawStr):
        return bytes(s)
    b = s.encode('utf-8')
    n, out = len(b), bytearray()
    while True:
        if n < 0x80:
            out.append(n)
            break
        out.append((n & 0x7f) | 0x80)
        n >>= 7
    return bytes(out) + b


def _prim(t, v):
    if t == P_CHAR:
        return v.encode('utf-8')
    if t in (P_DECIMAL, P_STRING):
        return _lps(v)
    return struct.pack('<' + PRIM[t], v)


# ---------------------------------------------------------------- records

class Record:
    __slots__ = ('pre',)   # BinaryLibrary records written right before this one
    rtype = None


class Header(Record):
    __slots__ = ('root_id', 'header_id', 'major', 'minor')
    rtype = 0


class Library(Record):
    __slots__ = ('lib_id', 'name')
    rtype = 12


class ClassLayout:
    """ClassInfo + MemberTypeInfo shared by a class record and every ClassWithId that points at it."""
    __slots__ = ('name', 'members', 'btypes', 'extra', 'lib_id', 'lib_name', 'typed', 'system')

    def index(self, member):
        return self.members.index(member)


class ClassRec(Record):
    """Record types 1-5. layout is the own (2-5) or the referenced (1) layout; values follow layout.members."""
    __slots__ = ('rtype', 'obj_id', 'meta_id', 'layout', 'values')


class StringRec(Record):
    __slots__ = ('obj_id', 'value')
    rtype = 6


class ArrayRec(Record):
    """Record types 7 (BinaryArray), 15 (primitive), 16 (object), 17 (string). items = element records (or raw values for
    primitive elements); a null run record stands for several elements."""
    __slots__ = ('rtype', 'obj_id', 'atype', 'rank', 'lengths', 'lbounds', 'btype', 'extra', 'items')


class PrimTyped(Record):
    __slots__ = ('ptype', 'value')
    rtype = 8


class MemberRef(Record):
    __slots__ = ('id_ref',)
    rtype = 9


class Null(Record):
    __slots__ = ()
    rtype = 10


class NullRun(Record):
    __slots__ = ('rtype', 'count')   # 13 (byte count) or 14 (int32 count)


class End(Record):
    __slots__ = ()
    rtype = 11


def _new(cls, **kw):
    r = cls.__new__(cls)
    r.pre = None
    for k, v in kw.items():
        setattr(r, k, v)
    return r


# ---------------------------------------------------------------- stream

class Stream:
    """records = top-level records in file order (Header first, End last)."""

    def __init__(self, data=None):
        self.records = []
        self.layouts = {}      # objectId of a defining class record -> ClassLayout
        if data is not None:
            self._parse(memoryview(data) if not isinstance(data, (bytes, bytearray)) else data)

    # ---- reading
    def _parse(self, data):
        r = Reader(bytes(data))
        while True:
            rec = self._record(r)
            self.records.append(rec)
            if isinstance(rec, End):
                break
        if r.p != len(r.d):
            raise ValueError(f'NRBF: {len(r.d) - r.p} bytes after MessageEnd')

    def _record(self, r):
        pre = None
        t = r.u8()
        while t == 12:
            lib = _new(Library, lib_id=r.i32(), name=r.lps())
            (pre := pre or []).append(lib)
            t = r.u8()
        rec = self._body(r, t)
        rec.pre = pre
        return rec

    def _body(self, r, t):
        if t == 0:
            return _new(Header, root_id=r.i32(), header_id=r.i32(), major=r.i32(), minor=r.i32())
        if 1 <= t <= 5:
            oid = r.i32()
            if t == 1:
                meta = r.i32()
                lay = self.layouts[meta]
            else:
                meta = None
                lay = ClassLayout()
                lay.name = r.lps()
                lay.members = [r.lps() for _ in range(r.i32())]
                lay.typed = t in (4, 5)
                lay.system = t in (2, 4)
                lay.btypes, lay.extra = (self._types(r, len(lay.members)) if lay.typed else (None, None))
                lay.lib_id = r.i32() if t in (3, 5) else None
                self.layouts[oid] = lay
            rec = _new(ClassRec, rtype=t, obj_id=oid, meta_id=meta, layout=lay, values=None)
            if lay.typed:
                rec.values = [r.prim(x) if bt == B_PRIMITIVE else self._record(r) for bt, x in zip(lay.btypes, lay.extra)]
            else:
                rec.values = [self._record(r) for _ in lay.members]
            return rec
        if t == 6:
            return _new(StringRec, obj_id=r.i32(), value=r.lps())
        if t == 7:
            oid, at, rank = r.i32(), r.u8(), r.i32()
            lengths = [r.i32() for _ in range(rank)]
            lb = [r.i32() for _ in range(rank)] if at in (3, 4, 5) else None
            bt = r.u8()
            x = self._extra(r, bt)
            n = 1
            for ln in lengths:
                n *= ln
            items = ([r.prim(x) for _ in range(n)] if bt == B_PRIMITIVE else self._items(r, n))
            return _new(ArrayRec, rtype=7, obj_id=oid, atype=at, rank=rank, lengths=lengths, lbounds=lb, btype=bt, extra=x,
                        items=items)
        if t == 8:
            pt = r.u8()
            return _new(PrimTyped, ptype=pt, value=r.prim(pt))
        if t == 9:
            return _new(MemberRef, id_ref=r.i32())
        if t == 10:
            return _new(Null)
        if t == 11:
            return _new(End)
        if t == 13:
            return _new(NullRun, rtype=13, count=r.u8())
        if t == 14:
            return _new(NullRun, rtype=14, count=r.i32())
        if t == 15:
            oid, n, pt = r.i32(), r.i32(), None
            pt = r.u8()
            if pt == P_BYTE:       # byte[] stays one bytes object
                items = r.d[r.p:r.p + n]
                r.p += n
            else:
                items = [r.prim(pt) for _ in range(n)]
            return _new(ArrayRec, rtype=15, obj_id=oid, atype=0, rank=1, lengths=[n], lbounds=None, btype=B_PRIMITIVE,
                        extra=pt, items=items)
        if t in (16, 17):
            oid, n = r.i32(), r.i32()
            return _new(ArrayRec, rtype=t, obj_id=oid, atype=0, rank=1, lengths=[n], lbounds=None,
                        btype=B_OBJECT if t == 16 else B_STRING, extra=None, items=self._items(r, n))
        raise ValueError(f'NRBF: record type {t} at {r.p - 1} not supported')

    def _items(self, r, n):
        items, k = [], 0
        while k < n:
            rec = self._record(r)
            items.append(rec)
            k += rec.count if isinstance(rec, NullRun) else 1
        if k != n:
            raise ValueError('NRBF: null run overruns its array')
        return items

    def _types(self, r, n):
        bts = [r.u8() for _ in range(n)]
        return bts, [self._extra(r, bt) for bt in bts]

    @staticmethod
    def _extra(r, bt):
        if bt in (B_PRIMITIVE, B_PRIMITIVEARRAY):
            return r.u8()
        if bt == B_SYSTEMCLASS:
            return r.lps()
        if bt == B_CLASS:
            return (r.lps(), r.i32())
        return None

    # ---- writing
    def to_bytes(self):
        out = []
        for rec in self.records:
            _write(rec, out)
        return b''.join(out)

    # ---- helpers
    def objects(self):
        """objectId -> record, for every record (nested or not) that carries an id."""
        m = {}
        for rec in self.records:
            _collect(rec, m)
        return m


def _write(rec, out):
    if rec.pre:
        for lib in rec.pre:
            out.append(b'\x0c' + struct.pack('<i', lib.lib_id) + _lps(lib.name))
    t = rec.rtype
    if t == 0:
        out.append(struct.pack('<B4i', 0, rec.root_id, rec.header_id, rec.major, rec.minor))
    elif 1 <= t <= 5:
        lay = rec.layout
        if t == 1:
            out.append(struct.pack('<B2i', 1, rec.obj_id, rec.meta_id))
        else:
            b = [struct.pack('<Bi', t, rec.obj_id), _lps(lay.name), struct.pack('<i', len(lay.members))]
            b += [_lps(m) for m in lay.members]
            if lay.typed:
                b.append(bytes(lay.btypes))
                for bt, x in zip(lay.btypes, lay.extra):
                    b.append(_extra(bt, x))
            if t in (3, 5):
                b.append(struct.pack('<i', lay.lib_id))
            out.append(b''.join(b))
        if lay.typed:
            for bt, x, v in zip(lay.btypes, lay.extra, rec.values):
                if bt == B_PRIMITIVE:
                    out.append(_prim(x, v))
                else:
                    _write(v, out)
        else:
            for v in rec.values:
                _write(v, out)
    elif t == 6:
        out.append(struct.pack('<Bi', 6, rec.obj_id) + _lps(rec.value))
    elif t == 7:
        b = [struct.pack('<BiBi', 7, rec.obj_id, rec.atype, rec.rank), struct.pack(f'<{rec.rank}i', *rec.lengths)]
        if rec.lbounds is not None:
            b.append(struct.pack(f'<{rec.rank}i', *rec.lbounds))
        b.append(bytes([rec.btype]) + _extra(rec.btype, rec.extra))
        out.append(b''.join(b))
        if rec.btype == B_PRIMITIVE:
            out.append(b''.join(_prim(rec.extra, v) for v in rec.items))
        else:
            for it in rec.items:
                _write(it, out)
    elif t == 8:
        out.append(bytes([8, rec.ptype]) + _prim(rec.ptype, rec.value))
    elif t == 9:
        out.append(struct.pack('<Bi', 9, rec.id_ref))
    elif t in (10, 11):
        out.append(bytes([t]))
    elif t == 13:
        out.append(bytes([13, rec.count]))
    elif t == 14:
        out.append(struct.pack('<Bi', 14, rec.count))
    elif t == 15:
        out.append(struct.pack('<BiiB', 15, rec.obj_id, rec.lengths[0], rec.extra))
        if isinstance(rec.items, (bytes, bytearray)):
            out.append(bytes(rec.items))
        else:
            out.append(b''.join(_prim(rec.extra, v) for v in rec.items))
    elif t in (16, 17):
        out.append(struct.pack('<Bii', t, rec.obj_id, rec.lengths[0]))
        for it in rec.items:
            _write(it, out)
    else:
        raise ValueError(f'NRBF: cannot write record type {t}')


def _extra(bt, x):
    if bt in (B_PRIMITIVE, B_PRIMITIVEARRAY):
        return bytes([x])
    if bt == B_SYSTEMCLASS:
        return _lps(x)
    if bt == B_CLASS:
        return _lps(x[0]) + struct.pack('<i', x[1])
    return b''


def _collect(rec, m):
    oid = getattr(rec, 'obj_id', None)
    if oid is not None:
        m[oid] = rec
    if isinstance(rec, ClassRec):
        for v in rec.values:
            if isinstance(v, Record):
                _collect(v, m)
    elif isinstance(rec, ArrayRec) and rec.btype != B_PRIMITIVE:
        for it in rec.items:
            _collect(it, m)


# ---------------------------------------------------------------- object graph

class Obj:
    """A class instance. layout = ClassLayout (member names/types), values in member order; inline = a value type written
    nested in its owner (BF does that for structs; they carry negative object ids)."""
    __slots__ = ('layout', 'values', 'inline')

    def __init__(self, layout, values, inline=False):
        self.layout, self.values, self.inline = layout, values, inline

    def __getitem__(self, member):
        return self.values[self.layout.members.index(member)]

    def __setitem__(self, member, v):
        self.values[self.layout.members.index(member)] = v

    def copy(self):
        """Shallow copy; nested structs are copied too (they are values)."""
        return Obj(self.layout, [v.copy() if isinstance(v, Obj) and v.inline else v for v in self.values], self.inline)


class Arr:
    """An array. kind = the record type it was read from (7, 15, 16, 17) plus the BinaryArray header fields
    (shape only for rank > 1; a rank-1 array's length is len(items))."""
    __slots__ = ('kind', 'atype', 'btype', 'extra', 'lbounds', 'shape', 'items')

    def __init__(self, kind, items, btype=None, extra=None, atype=0, lbounds=None, shape=None):
        self.kind, self.items, self.btype, self.extra = kind, items, btype, extra
        self.atype, self.lbounds, self.shape = atype, lbounds, shape

    def copy(self):
        return Arr(self.kind, list(self.items), self.btype, self.extra, self.atype, self.lbounds, self.shape)


class Boxed:
    """A primitive boxed in an Object-typed member (MemberPrimitiveTyped)."""
    __slots__ = ('ptype', 'value')

    def __init__(self, ptype, value):
        self.ptype, self.value = ptype, value


class NStr(str):
    """A string read from the stream: its Python identity stands for the .NET instance (a shared instance is written once
    and then referenced, exactly like BinaryFormatter). A plain str a caller assigns is a new instance."""


def decode(stream):
    """Layer 1 -> graph. Returns (root object, {library id: library name})."""
    recs = stream.objects()
    libs = {}
    for rec in stream.records:
        _libs(rec, libs)
    for lay in stream.layouts.values():
        lay.lib_name = libs.get(lay.lib_id) if lay.lib_id is not None else None
    memo = {}

    def val(rec, nested):
        if isinstance(rec, MemberRef):
            if rec.id_ref in memo:
                return memo[rec.id_ref]
            return val(recs[rec.id_ref], False)
        if isinstance(rec, Null):
            return None
        if isinstance(rec, StringRec):
            if rec.obj_id not in memo:
                memo[rec.obj_id] = rec.value if isinstance(rec.value, RawStr) else NStr(rec.value)
            return memo[rec.obj_id]
        if isinstance(rec, PrimTyped):
            return Boxed(rec.ptype, rec.value)
        if isinstance(rec, ClassRec):
            if rec.obj_id in memo:
                return memo[rec.obj_id]
            o = Obj(rec.layout, None, nested)
            memo[rec.obj_id] = o
            lay = rec.layout
            if lay.typed:
                o.values = [v if bt == B_PRIMITIVE else val(v, True) for bt, v in zip(lay.btypes, rec.values)]
            else:
                o.values = [val(v, True) for v in rec.values]
            return o
        if isinstance(rec, ArrayRec):
            if rec.obj_id in memo:
                return memo[rec.obj_id]
            a = Arr(rec.rtype, None, rec.btype, rec.extra, rec.atype, rec.lbounds, rec.lengths if rec.rank != 1 else None)
            memo[rec.obj_id] = a
            if rec.btype == B_PRIMITIVE:
                a.items = rec.items if isinstance(rec.items, (bytes, bytearray)) else list(rec.items)
            else:
                items = []
                for it in rec.items:
                    if isinstance(it, NullRun):
                        items.extend([None] * it.count)
                    else:
                        items.append(val(it, True))
                a.items = items
            return a
        raise ValueError(f'NRBF: unexpected {type(rec).__name__} as a value')

    return val(recs[stream.records[0].root_id], False), libs


def _libs(rec, libs):
    for lib in rec.pre or ():
        libs[lib.lib_id] = lib.name
    if isinstance(rec, ClassRec):
        for v in rec.values:
            if isinstance(v, Record):
                _libs(v, libs)
    elif isinstance(rec, ArrayRec) and rec.btype != B_PRIMITIVE:
        for it in rec.items:
            _libs(it, libs)


class _BFWriter:
    """Graph -> bytes in the order System.Runtime.Serialization.Formatters.Binary's ObjectWriter produces:
    one id counter for objects, strings, libraries and value types; the root takes id 1; a class needs its library id
    first (a BinaryLibrary record right before the first class record of that assembly); a string is written inline with a
    new id on first sight and referenced afterwards; a reference-type member gets an id when first seen and is queued
    (written later as a top-level record, FIFO); a struct is written inline with id -counter; the first record of a class
    carries the member type info (ClassWithMembersAndTypes), later ones are ClassWithId pointing at it; a run of nulls in an
    array is ObjectNull (1) / ObjectNullMultiple256 (< 256) / ObjectNullMultiple."""

    def __init__(self, libs):
        self.n = 0
        self.ids = {}        # id(python object) -> object id
        self.keep = []       # keeps every numbered object alive while ids are keyed by id()
        self.lib_ids = {}
        self.old_libs = libs
        self.meta = {}       # (class name, library name) -> object id of the defining record
        self.queue = []
        self.out = []

    def next(self):
        self.n += 1
        return self.n

    def ref_id(self, o):
        # BF bumps its counter on EVERY object/string lookup, a repeat sighting included (measured: a MemberReference to
        # a shared string skips one id in the shipped Dpr.bin); a new object takes the bumped value
        i = self.next()
        k = id(o)
        if k in self.ids:
            return self.ids[k], False
        self.ids[k] = i
        self.keep.append(o)
        return i, True

    def lib(self, name, pre):
        if name not in self.lib_ids:
            self.lib_ids[name] = self.next()
            pre.append(struct.pack('<Bi', 12, self.lib_ids[name]) + _lps(name))
        return self.lib_ids[name]

    def run(self, root, header):
        rid, _ = self.ref_id(root)
        self.out.append(struct.pack('<B4i', 0, rid, header[1], header[2], header[3]))
        self.queue.append(root)
        qi = 0
        while qi < len(self.queue):
            o = self.queue[qi]
            qi += 1
            if isinstance(o, Obj):
                self.cls(o, self.ids[id(o)])
            else:
                self.arr(o, self.ids[id(o)])
        self.out.append(b'\x0b')
        return b''.join(self.out)

    def cls(self, o, oid):
        lay = o.layout
        pre = []
        lib_id = self.lib(lay.lib_name, pre) if lay.lib_name is not None else None
        key = (lay.name, lay.lib_name)
        if key not in self.meta:
            extra = lay.extra
            if lay.typed:   # member classes of another assembly need their library first
                extra = [(x[0], self.lib(self.old_libs[x[1]], pre)) if bt == B_CLASS else x
                         for bt, x in zip(lay.btypes, lay.extra)]
        self.out.extend(pre)
        if key in self.meta:
            self.out.append(struct.pack('<B2i', 1, oid, self.meta[key]))
        else:
            self.meta[key] = oid
            t = (4 if lay.typed else 2) if lay.lib_name is None else (5 if lay.typed else 3)
            b = [struct.pack('<Bi', t, oid), _lps(lay.name), struct.pack('<i', len(lay.members))]
            b += [_lps(m) for m in lay.members]
            if lay.typed:
                b.append(bytes(lay.btypes))
                b += [_extra(bt, x) for bt, x in zip(lay.btypes, extra)]
            if lib_id is not None:
                b.append(struct.pack('<i', lib_id))
            self.out.append(b''.join(b))
        if lay.typed:
            for bt, x, v in zip(lay.btypes, lay.extra, o.values):
                if bt == B_PRIMITIVE:
                    self.out.append(_prim(x, v))
                else:
                    self.member(v)
        else:
            for v in o.values:
                self.member(v)

    def member(self, v):
        if v is None:
            self.out.append(b'\x0a')
        elif isinstance(v, (str, RawStr)):
            i, new = self.ref_id(v)
            if not new:
                self.out.append(struct.pack('<Bi', 9, i))
            else:
                self.out.append(struct.pack('<Bi', 6, i) + (bytes(v) if isinstance(v, RawStr) else _lps(v)))
        elif isinstance(v, Boxed):
            self.out.append(bytes([8, v.ptype]) + _prim(v.ptype, v.value))
        elif isinstance(v, Obj) and v.inline:
            self.cls(v, -self.next())
        else:
            i, new = self.ref_id(v)
            if new:
                self.queue.append(v)
            self.out.append(struct.pack('<Bi', 9, i))

    def arr(self, a, oid):
        n = len(a.items)
        if a.kind == 15:
            self.out.append(struct.pack('<BiiB', 15, oid, n, a.extra))
            it = a.items
            self.out.append(bytes(it) if isinstance(it, (bytes, bytearray)) else b''.join(_prim(a.extra, v) for v in it))
            return
        if a.kind in (16, 17):
            self.out.append(struct.pack('<Bii', a.kind, oid, n))
        else:
            shape = a.shape or [n]
            pre, x = [], a.extra
            if a.btype == B_CLASS:
                x = (x[0], self.lib(self.old_libs[x[1]], pre))
            self.out.extend(pre)
            b = [struct.pack('<BiBi', 7, oid, a.atype, len(shape)), struct.pack(f'<{len(shape)}i', *shape)]
            if a.lbounds is not None:
                b.append(struct.pack(f'<{len(shape)}i', *a.lbounds))
            b.append(bytes([a.btype]) + _extra(a.btype, x))
            self.out.append(b''.join(b))
            if a.btype == B_PRIMITIVE:
                self.out.append(b''.join(_prim(a.extra, v) for v in a.items))
                return
        nulls = 0
        for it in a.items:
            if it is None:
                nulls += 1
                continue
            if nulls:
                self.nulls(nulls)
                nulls = 0
            self.member(it)
        if nulls:
            self.nulls(nulls)

    def nulls(self, k):
        self.out.append(b'\x0a' if k == 1 else bytes([13, k]) if k < 256 else struct.pack('<Bi', 14, k))


def encode(root, libs, header=(1, -1, 1, 0)):
    """Graph -> NRBF bytes in BinaryFormatter order (every id assigned afresh; see _BFWriter)."""
    return _BFWriter(libs).run(root, header)


# ---------------------------------------------------------------- Dpr.bin

MANIFEST_CLASS = 'SmartPoint.AssetAssistant.AssetBundleDownloadManifest'
RECORD_CLASS = 'SmartPoint.AssetAssistant.AssetBundleRecord'
TICKS_MASK = (1 << 62) - 1     # DateTime binary = Ticks (100 ns since 0001-01-01) | Kind << 62 (1 = Utc)


def lookup_key(path):
    """BuildLookupTables' asset-path key: lower case, a leading "assets/" removed."""
    k = path.lower()
    return k[len('assets/'):] if k.startswith('assets/') else k


def _strings(arr):
    return None if arr is None else arr.items


class BundleRecord:
    """One AssetBundleRecord (a view over its graph object; edits go straight into the graph).
    Serialized fields: projectName, assetBundleName (str), hash (RecordedHash = 4 x uint32 u0..u3), lastWriteTime (DateTime
    raw 64-bit word), isStreamingSceneAssetBundle (bool), allDependencies, assetPaths (string[]), size (int64)."""
    __slots__ = ('obj',)

    def __init__(self, obj):
        self.obj = obj

    projectName = property(lambda s: s.obj['projectName'], lambda s, v: s.obj.__setitem__('projectName', v))
    assetBundleName = property(lambda s: s.obj['assetBundleName'], lambda s, v: s.obj.__setitem__('assetBundleName', v))
    lastWriteTime = property(lambda s: s.obj['lastWriteTime'], lambda s, v: s.obj.__setitem__('lastWriteTime', v))
    size = property(lambda s: s.obj['size'], lambda s, v: s.obj.__setitem__('size', v))

    @property
    def isStreamingSceneAssetBundle(self):
        return bool(self.obj['isStreamingSceneAssetBundle'])

    @isStreamingSceneAssetBundle.setter
    def isStreamingSceneAssetBundle(self, v):
        self.obj['isStreamingSceneAssetBundle'] = 1 if v else 0

    @property
    def hash(self):
        h = self.obj['hash']
        return tuple(h.values)

    @hash.setter
    def hash(self, v):
        v = [int(x) & 0xffffffff for x in v]
        if len(v) != 4:
            raise ValueError('RecordedHash = 4 uint32')
        self.obj['hash'].values = v

    @property
    def hash_hex(self):
        """The 32-hex-digit Hash128 string RecordedHash.Parse reads (each 8-digit group byte-swapped into its uint)."""
        return ''.join(struct.pack('<I', u).hex() for u in self.hash)

    @hash_hex.setter
    def hash_hex(self, s):
        self.hash = [struct.unpack('<I', bytes.fromhex(s[i * 8:i * 8 + 8]))[0] for i in range(4)]

    def _arr(self, m):
        return _strings(self.obj[m])

    def _set_arr(self, m, items):
        a = self.obj[m]
        if items is None:
            self.obj[m] = None
        elif a is None:
            self.obj[m] = Arr(17, list(items), B_STRING)
        else:
            a.items = list(items)

    allDependencies = property(lambda s: s._arr('allDependencies'), lambda s, v: s._set_arr('allDependencies', v))
    assetPaths = property(lambda s: s._arr('assetPaths'), lambda s, v: s._set_arr('assetPaths', v))

    @property
    def last_write_datetime(self):
        import datetime
        return datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=(self.lastWriteTime & TICKS_MASK) // 10)

    def set_last_write(self, dt, kind=1):
        import datetime
        ticks = (dt.replace(tzinfo=None) - datetime.datetime(1, 1, 1)) // datetime.timedelta(microseconds=1) * 10
        self.lastWriteTime = ticks | (kind << 62)

    def as_dict(self):
        return {'projectName': self.projectName, 'assetBundleName': self.assetBundleName, 'hash': self.hash,
                'lastWriteTime': self.lastWriteTime, 'isStreamingSceneAssetBundle': self.isStreamingSceneAssetBundle,
                'allDependencies': None if self.allDependencies is None else list(self.allDependencies),
                'assetPaths': None if self.assetPaths is None else list(self.assetPaths), 'size': self.size}

    def __repr__(self):
        return f'<BundleRecord {self.projectName}/{self.assetBundleName} {self.size} B>'


class Manifest:
    """Dpr.bin. records = list of BundleRecord in file order (add/remove by editing the list or with the helpers);
    variants = _assetBundleNamesWithVariant (list of str); version, projectName. save() writes the graph in
    BinaryFormatter order - an unmodified manifest comes out byte-identical (measured on the shipped, Lumi and Dechibified
    files)."""

    def __init__(self, data):
        self.stream = Stream(data)
        self.root, self.libs = decode(self.stream)
        if self.root.layout.name != MANIFEST_CLASS:
            raise ValueError(f'Dpr.bin root is {self.root.layout.name}')
        h = self.stream.records[0]
        self.header = (h.root_id, h.header_id, h.major, h.minor)
        self.records = [BundleRecord(o) for o in self.root['_records'].items]
        self.stream = None   # the graph is the truth from here on

    version = property(lambda s: s.root['_version'], lambda s, v: s.root.__setitem__('_version', v))
    projectName = property(lambda s: s.root['_projectName'], lambda s, v: s.root.__setitem__('_projectName', v))

    @property
    def variants(self):
        return _strings(self.root['_assetBundleNamesWithVariant'])

    def find(self, name):
        for r in self.records:
            if r.assetBundleName == name:
                return r
        return None

    def index(self, name):
        for i, r in enumerate(self.records):
            if r.assetBundleName == name:
                return i
        raise KeyError(name)

    def clone(self, src, new_name, asset_paths=None, index=None, **fields):
        """A copy of record src (a BundleRecord or a bundle name) under new_name: new objects (they get new object ids on
        save), the same dependency/path strings. asset_paths replaces the paths - a clone that keeps them makes
        duplicate lookup keys, which the game refuses. fields = any other field to set. Inserted at index (default: end)."""
        if isinstance(src, str):
            src = self.find(src) or _missing(src)
        o = src.obj.copy()
        for m in ('allDependencies', 'assetPaths'):
            if o[m] is not None:
                o[m] = o[m].copy()
        rec = BundleRecord(o)
        rec.assetBundleName = str(new_name)
        if asset_paths is not None:
            rec.assetPaths = asset_paths
        for k, v in fields.items():
            if not hasattr(BundleRecord, k):
                raise AttributeError(k)
            setattr(rec, k, v)
        self.add(rec, index)
        return rec

    def add(self, rec, index=None):
        if index is None:
            self.records.append(rec)
        else:
            self.records.insert(index, rec)
        return rec

    def remove(self, rec):
        if isinstance(rec, str):
            rec = self.find(rec) or _missing(rec)
        self.records.remove(rec)

    def duplicate_names(self):
        seen, dup = set(), []
        for r in self.records:
            if r.assetBundleName in seen:
                dup.append(r.assetBundleName)
            seen.add(r.assetBundleName)
        return dup

    def duplicate_keys(self):
        """{lookup key: [bundle names]} for every asset-path key more than one path maps to (game boot throws on any)."""
        owner, dup = {}, {}
        for r in self.records:
            for p in r.assetPaths or ():
                if p is None:
                    continue
                k = lookup_key(p)
                if k in owner:
                    dup.setdefault(k, [owner[k]]).append(r.assetBundleName)
                else:
                    owner[k] = r.assetBundleName
        return dup

    def problems(self):
        """What the game's BuildLookupTables would throw on (ToDictionary on names, Dictionary.Add on path keys)."""
        out = [f'duplicate bundle name {n}' for n in self.duplicate_names()]
        out += [f'duplicate asset key {k}: {", ".join(v)}' for k, v in self.duplicate_keys().items()]
        out += [f'{r.assetBundleName}: null asset path' for r in self.records if r.assetPaths and None in r.assetPaths]
        return out

    def save(self):
        self.root['_records'].items = [r.obj for r in self.records]
        return encode(self.root, self.libs, self.header)


def _missing(name):
    raise KeyError(f'no record {name}')


def load(data):
    return Manifest(data)
