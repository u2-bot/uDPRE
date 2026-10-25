"""IL2CPP global-metadata.dat, version 24 (Unity 2019.4: layout of 24.2-24.4), read + same-size in-place edits.

Written from general knowledge of the format and checked on the game's files (Switch, our vanilla and Lumi players).
Header: uint32 sanity 0xFAB11BAF, int32 version (24), then 32 (offset, byte size) section pairs = 264 bytes; the first
section starts right after it. Sections used here (index: name, record size):
   2 string (NUL-terminated UTF-8, addressed by byte offset)       7 fieldDefaultValues {fieldIndex, typeIndex, dataIndex} 12
   6 parameterDefaultValues {paramIndex, typeIndex, dataIndex} 12  8 fieldAndParameterDefaultValueData (raw blobs)
  11 fields {nameIndex, typeIndex, token} 12                      15 nestedTypes (int32 typedef indices)
  19 typeDefinitions 92 B: 17 int32 {name, namespace, byvalType, byrefType, declaringType, parent, elementType,
     genericContainer, flags, fieldStart, methodStart, eventStart, propertyStart, nestedTypesStart, interfacesStart,
     vtableStart, interfaceOffsetsStart}, 8 uint16 counts {method, property, field, event, nestedType, vtable, interfaces,
     interfaceOffsets}, uint32 bitfield, uint32 token
  20 images 40 B {name, assembly, typeStart, typeCount, exportedTypeStart, exportedTypeCount, entryPoint, token,
     customAttributeStart, customAttributeCount}
  22 metadataUsageLists {start, count} 8   23 metadataUsagePairs {destinationIndex, encodedSource} 8
  24 fieldRefs {typeIndex, fieldIndex (relative to the type's fieldStart)} 8
"typeIndex" values point into the executable's Il2CppType table, which the metadata does not hold; every type definition
carries its own byval type index though, so a field's type is resolved by matching that (byval_types()).

Default value sizes (the data section holds no lengths for fixed-size values):
  primitives by their System type (Boolean/Byte/SByte 1, Char/Int16/UInt16 2, Int32/UInt32/Single 4, Int64/UInt64/Double 8),
  an enum by its underlying type, System.String = int32 byte length + UTF-8 bytes (-1 = null),
  an InitializeArray blob (a <PrivateImplementationDetails> field of type __StaticArrayInitTypeSize=N, or a plain
  long/int field when N is 8/4) = N bytes from the type's name / primitive size.
  Every computed span is cross-checked against the next blob's start (blobs are packed in dataIndex order): 0 mismatches,
  0 values left unsized in the Switch, vanilla-player and Lumi-player files.

Type chart (type_chart / set_type_chart): Pml.Battle.TypeAffinity.TYPE_AFF_TBL is built by the class's .cctor from 18
InitializeArray blobs of 18 bytes (0/2/4/8). The row -> field mapping comes from the .cctor's metadataUsageList (the list
holding TypeAffinity's TypeInfo): its FieldInfo entries are in first-use order = row order, so the mapping does not
depend on the bytes and survives an edited chart. Cross-check: Roslyn names these fields by the SHA-1 of their content,
so in a player built from the vanilla source the 18 names are SHA-1(vanilla row) in the same order (true in all three).
"""
import hashlib
import struct

SANITY = 0xFAB11BAF
N_SECTIONS = 32
SECTIONS = ('stringLiteral', 'stringLiteralData', 'string', 'events', 'properties', 'methods', 'parameterDefaultValues',
            'fieldDefaultValues', 'fieldAndParameterDefaultValueData', 'fieldMarshaledSizes', 'parameters', 'fields',
            'genericParameters', 'genericParameterConstraints', 'genericContainers', 'nestedTypes', 'interfaces',
            'vtableMethods', 'interfaceOffsets', 'typeDefinitions', 'images', 'assemblies', 'metadataUsageLists',
            'metadataUsagePairs', 'fieldRefs', 'referencedAssemblies', 'attributesInfo', 'attributeTypes',
            'unresolvedVirtualCallParameterTypes', 'unresolvedVirtualCallParameterRanges', 'windowsRuntimeTypeNames',
            'exportedTypeDefinitions')
TD_FMT = '<17i8HII'
TD_SIZE = struct.calcsize(TD_FMT)   # 92
IMG_FMT = '<10i'
PRIM_SIZE = {'System.Boolean': 1, 'System.Byte': 1, 'System.SByte': 1, 'System.Char': 2, 'System.Int16': 2,
             'System.UInt16': 2, 'System.Int32': 4, 'System.UInt32': 4, 'System.Single': 4, 'System.Int64': 8,
             'System.UInt64': 8, 'System.Double': 8, 'System.IntPtr': 8, 'System.UIntPtr': 8}
USAGE_KINDS = {1: 'TypeInfo', 2: 'Il2CppType', 3: 'MethodDef', 4: 'FieldInfo', 5: 'StringLiteral', 6: 'MethodRef'}


class Image:
    __slots__ = ('index', 'name', 'assembly', 'type_start', 'type_count', 'token')

    def __repr__(self):
        return f'<Image {self.name} types {self.type_start}+{self.type_count}>'


class TypeDef:
    __slots__ = ('index', 'name', 'namespace', 'byval', 'byref', 'declaring', 'parent', 'element', 'flags',
                 'field_start', 'field_count', 'method_start', 'method_count', 'nested_start', 'nested_count', 'token',
                 'bitfield', 'image', 'outer')

    @property
    def full_name(self):
        """Namespace.Type, nested types as Outer/Inner (the namespace is the outermost type's)."""
        if self.outer is not None:
            return self.outer.full_name + '/' + self.name
        return f'{self.namespace}.{self.name}' if self.namespace else self.name

    @property
    def is_enum(self):
        return bool(self.bitfield & 2)     # bitfield bit 1 = enum (bit 0 = valuetype)

    def __repr__(self):
        return f'<TypeDef {self.full_name}>'


class Field:
    __slots__ = ('index', 'name', 'type_index', 'token', 'owner', 'default')

    def __repr__(self):
        d = f' default @{self.default.offset}+{self.default.size}' if self.default else ''
        return f'<Field {self.owner.full_name}::{self.name}{d}>'


class Default:
    """A default-value blob: offset = absolute file offset, size in bytes, type_index of the value, data_index =
    offset inside the fieldAndParameterDefaultValueData section."""
    __slots__ = ('offset', 'size', 'type_index', 'data_index', 'how')

    def __repr__(self):
        return f'<Default @{self.offset} {self.size} B ({self.how})>'


class Metadata:
    def __init__(self, data):
        self.data = bytearray(data)
        d = self.data
        sanity, self.version = struct.unpack_from('<Ii', d, 0)
        if sanity != SANITY:
            raise ValueError('not an IL2CPP global-metadata.dat')
        pairs = struct.unpack_from(f'<{2 * N_SECTIONS}i', d, 8)
        self.sections = {SECTIONS[i]: (pairs[2 * i], pairs[2 * i + 1]) for i in range(N_SECTIONS)}
        first = min(off for off, size in self.sections.values() if size)
        if self.version != 24 or first != 8 + 8 * N_SECTIONS:
            raise ValueError(f'metadata version {self.version} / header {first} B: only v24.2-24.4 (264-byte header)')
        self._parse()

    # ---- tables
    def table(self, name, fmt):
        off, size = self.sections[name]
        n = struct.calcsize(fmt)
        return [struct.unpack_from(fmt, self.data, off + i) for i in range(0, size - size % n, n)]

    def string(self, index):
        off = self.sections['string'][0] + index
        end = self.data.index(0, off)
        return self.data[off:end].decode('utf-8')

    def _parse(self):
        s = self.string
        self.images = []
        for i, r in enumerate(self.table('images', IMG_FMT)):
            im = Image()
            im.index, im.name, im.assembly, im.type_start, im.type_count, im.token = i, s(r[0]), r[1], r[2], r[3], r[7]
            self.images.append(im)
        self.typedefs = []
        for i, r in enumerate(self.table('typeDefinitions', TD_FMT)):
            t = TypeDef()
            t.index, t.name, t.namespace = i, s(r[0]), s(r[1])
            t.byval, t.byref, t.declaring, t.parent, t.element, t.flags = r[2], r[3], r[4], r[5], r[6], r[8]
            t.field_start, t.method_start, t.nested_start = r[9], r[10], r[13]
            t.method_count, t.field_count, t.nested_count = r[17], r[19], r[21]
            t.bitfield, t.token = r[25], r[26]
            t.image = t.outer = None
            self.typedefs.append(t)
        for im in self.images:
            for t in self.typedefs[im.type_start:im.type_start + im.type_count]:
                t.image = im
        nested = [r[0] for r in self.table('nestedTypes', '<i')]
        for t in self.typedefs:
            for k in nested[t.nested_start:t.nested_start + t.nested_count] if t.nested_count else ():
                self.typedefs[k].outer = t
        self.byval = {}
        for t in self.typedefs:
            self.byval.setdefault(t.byval, t)
        self.fields_ = []
        for i, r in enumerate(self.table('fields', '<3i')):
            f = Field()
            f.index, f.name, f.type_index, f.token, f.owner, f.default = i, s(r[0]), r[1], r[2], None, None
            self.fields_.append(f)
        for t in self.typedefs:
            for f in self.fields_[t.field_start:t.field_start + t.field_count] if t.field_count else ():
                f.owner = t
        self._defaults()

    def _defaults(self):
        base, dsize = self.sections['fieldAndParameterDefaultValueData']
        fdv = self.table('fieldDefaultValues', '<3i')
        pdv = self.table('parameterDefaultValues', '<3i')
        starts = sorted({r[2] for r in fdv + pdv if r[2] >= 0} | {dsize})
        nxt = {a: b for a, b in zip(starts, starts[1:])}
        self.default_checks = {'fields': len(fdv), 'params': len(pdv), 'gap_mismatch': 0, 'by_gap': 0}
        for fi, ti, di in fdv:
            if di < 0:
                continue
            dv = Default()
            dv.type_index, dv.data_index, dv.offset = ti, di, base + di
            size, how = self.value_size(ti, base + di)
            gap = nxt[di] - di
            if size is None:
                size, how = gap, 'gap'
                self.default_checks['by_gap'] += 1
            elif size > gap or (gap - size) >= 4 and how != 'string':
                self.default_checks['gap_mismatch'] += 1
            dv.size, dv.how = size, how
            self.fields_[fi].default = dv

    def value_size(self, type_index, at):
        """(size, how) of a default blob of type type_index stored at file offset at; (None, why) when unknown."""
        t = self.byval.get(type_index)
        if t is None:
            return None, 'type not a definition'
        n = f'{t.namespace}.{t.name}' if t.namespace else t.name
        if n == 'System.String':
            ln = struct.unpack_from('<i', self.data, at)[0]
            return 4 + max(ln, 0), 'string'
        if n in PRIM_SIZE:
            return PRIM_SIZE[n], n
        if t.name.startswith('__StaticArrayInitTypeSize='):
            return int(t.name.split('=')[1]), 'array init'
        if t.is_enum:
            u = self.byval.get(self._enum_underlying(t))
            if u is not None:
                un = f'{u.namespace}.{u.name}'
                if un in PRIM_SIZE:
                    return PRIM_SIZE[un], 'enum ' + un
        return None, n

    def _enum_underlying(self, t):
        # an enum's element type index = its underlying primitive (the value__ field has the same type)
        if t.element >= 0:
            return t.element
        for f in self.fields_[t.field_start:t.field_start + t.field_count]:
            if f.name == 'value__':
                return f.type_index
        return -1

    # ---- API
    def types(self, image):
        im = self.image(image) if isinstance(image, str) else image
        return self.typedefs[im.type_start:im.type_start + im.type_count]

    def image(self, name):
        for im in self.images:
            if im.name == name:
                return im
        raise KeyError(name)

    def type(self, image, full_name):
        for t in self.types(image):
            if t.full_name == full_name:
                return t
        raise KeyError(f'{image}: no type {full_name}')

    def fields(self, t):
        return self.fields_[t.field_start:t.field_start + t.field_count] if t.field_count else []

    def find(self, image, full_type, field):
        for f in self.fields(self.type(image, full_type)):
            if f.name == field:
                return f
        raise KeyError(f'{full_type}::{field}')

    def read_default(self, f):
        d = f.default
        if d is None:
            raise ValueError(f'{f!r} has no default value')
        return bytes(self.data[d.offset:d.offset + d.size])

    def patch_default(self, f, new):
        d = f.default
        if d is None:
            raise ValueError(f'{f!r} has no default value')
        if len(new) != d.size:
            raise ValueError(f'{f!r}: {len(new)} bytes for a {d.size}-byte value (only same-size edits)')
        self.data[d.offset:d.offset + d.size] = new

    def save(self):
        return bytes(self.data)

    def sha1(self):
        return hashlib.sha1(self.data).hexdigest()

    # ---- metadata usages (what a method references, as the generated code's per-method init lists record it)
    def usage_lists(self):
        """[[(kind, index)]] per metadataUsageList; FieldInfo indices are fieldRefs indices."""
        pairs = self.table('metadataUsagePairs', '<2I')
        out = []
        for start, count in self.table('metadataUsageLists', '<2I'):
            out.append([(e >> 29, e & 0x1fffffff) for _dst, e in pairs[start:start + count]])
        return out

    def field_ref(self, index):
        """fieldRefs[index] -> Field (typeIndex resolves through the byval map; fieldIndex is relative)."""
        ti, fi = self.table_row('fieldRefs', '<2i', index)
        t = self.byval.get(ti)
        return None if t is None else self.fields_[t.field_start + fi]

    def table_row(self, name, fmt, index):
        off, _size = self.sections[name]
        return struct.unpack_from(fmt, self.data, off + struct.calcsize(fmt) * index)


# ---------------------------------------------------------------- type chart

# Pml.Battle.TypeAffinity.TYPE_AFF_TBL of the shipped game: [attacking type][defending type], x0 = 0, xH = 2, x1 = 4, x2 = 8;
# types in PokeType order (Normal Fighting Flying Poison Ground Rock Bug Ghost Steel Fire Water Grass Electric Psychic
# Ice Dragon Dark Fairy)
VANILLA_TYPE_CHART = (
    (4, 4, 4, 4, 4, 2, 4, 0, 2, 4, 4, 4, 4, 4, 4, 4, 4, 4),
    (8, 4, 2, 2, 4, 8, 2, 0, 8, 4, 4, 4, 4, 2, 8, 4, 8, 2),
    (4, 8, 4, 4, 4, 2, 8, 4, 2, 4, 4, 8, 2, 4, 4, 4, 4, 4),
    (4, 4, 4, 2, 2, 2, 4, 2, 0, 4, 4, 8, 4, 4, 4, 4, 4, 8),
    (4, 4, 0, 8, 4, 8, 2, 4, 8, 8, 4, 2, 8, 4, 4, 4, 4, 4),
    (4, 2, 8, 4, 2, 4, 8, 4, 2, 8, 4, 4, 4, 4, 8, 4, 4, 4),
    (4, 2, 2, 2, 4, 4, 4, 2, 2, 2, 4, 8, 4, 8, 4, 4, 8, 2),
    (0, 4, 4, 4, 4, 4, 4, 8, 4, 4, 4, 4, 4, 8, 4, 4, 2, 4),
    (4, 4, 4, 4, 4, 8, 4, 4, 2, 2, 2, 4, 2, 4, 8, 4, 4, 8),
    (4, 4, 4, 4, 4, 2, 8, 4, 8, 2, 2, 8, 4, 4, 8, 2, 4, 4),
    (4, 4, 4, 4, 8, 8, 4, 4, 4, 8, 2, 2, 4, 4, 4, 2, 4, 4),
    (4, 4, 2, 2, 8, 8, 2, 4, 2, 2, 8, 2, 4, 4, 4, 2, 4, 4),
    (4, 4, 8, 4, 0, 4, 4, 4, 4, 4, 8, 2, 2, 4, 4, 2, 4, 4),
    (4, 8, 4, 8, 4, 4, 4, 4, 2, 4, 4, 4, 4, 2, 4, 4, 0, 4),
    (4, 4, 8, 4, 8, 4, 4, 4, 2, 2, 2, 8, 4, 4, 2, 8, 4, 4),
    (4, 4, 4, 4, 4, 4, 4, 4, 2, 4, 4, 4, 4, 4, 4, 8, 4, 0),
    (4, 2, 4, 4, 4, 4, 4, 8, 4, 4, 4, 4, 4, 8, 4, 4, 2, 2),
    (4, 8, 4, 2, 4, 4, 4, 4, 2, 2, 4, 4, 4, 4, 4, 8, 8, 4),
)
CHART_VALUES = (0, 2, 4, 8)
N_TYPES = 18
PID = '<PrivateImplementationDetails>'


def type_chart_fields(meta, image='Assembly-CSharp.dll'):
    """The 18 <PrivateImplementationDetails> fields TypeAffinity's static constructor copies into TYPE_AFF_TBL, in row
    order - found WITHOUT looking at their content, so an already edited chart maps the same way:
    the generated code initializes every method's metadata references from one metadataUsageList, in first-use order; the
    .cctor's list is the one that holds TypeAffinity's TypeInfo and the FieldInfo references of its InitializeArray blobs,
    and its first 18 FieldInfos with an 18-byte blob are rows 0..17 (the 19th FieldInfo is the 56-byte VALUE_ table).
    Returns (fields, report) - report says whether each field's name equals the SHA-1 of the vanilla row (Roslyn names
    these fields by the content hash, so the names tell the rows of the SOURCE the player was compiled from)."""
    ta = meta.type(image, 'Pml.Battle.TypeAffinity')
    cands = []
    for lst in meta.usage_lists():
        if (1, ta.byval) not in lst:
            continue
        rows = []
        for kind, idx in lst:
            if kind != 4:
                continue
            f = meta.field_ref(idx)
            if f is not None and f.owner.name == PID and f.owner.outer is None and f.default and f.default.size == N_TYPES:
                rows.append(f)
        if len(rows) >= N_TYPES:
            cands.append(rows[:N_TYPES])
    if len(cands) != 1:
        raise ValueError(f'type chart: {len(cands)} candidate .cctor usage lists (expected 1)')
    fields = cands[0]
    if len({f.index for f in fields}) != N_TYPES:
        raise ValueError('type chart: two rows share one blob (the source chart has identical rows)')
    names = [hashlib.sha1(bytes(r)).hexdigest().upper() == f.name for r, f in zip(VANILLA_TYPE_CHART, fields)]
    return fields, {'names_match_vanilla_source': all(names), 'per_row': names}


def type_chart(meta):
    """-> (18x18 list of values 0/2/4/8 = x0/xH/x1/x2, [Field per row])."""
    fields, _ = type_chart_fields(meta)
    return [list(meta.read_default(f)) for f in fields], fields


def set_type_chart(meta, values):
    """Write an 18x18 chart (values 0/2/4/8) into the 18 row blobs in place."""
    if len(values) != N_TYPES or any(len(r) != N_TYPES for r in values):
        raise ValueError('type chart must be 18 x 18')
    if any(v not in CHART_VALUES for r in values for v in r):
        raise ValueError('type chart values are 0 (x0), 2 (xH), 4 (x1), 8 (x2)')
    fields, _ = type_chart_fields(meta)
    for r, f in zip(values, fields):
        meta.patch_default(f, bytes(r))
