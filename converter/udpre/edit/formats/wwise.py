"""Audiokinetic Wwise soundbanks (.bnk), byte-exact - written from general knowledge of the bank layout and the game files.

A bank is a list of chunks (4-char tag, uint32 size, body). The game's banks (Switch, BKHD version 135 = Wwise 2019.2) hold
BKHD DIDX DATA HIRC (695 banks) or BKHD INIT STMG HIRC ENVS PLAT (Init.bnk); no STID chunk. Every chunk is kept as read;
DIDX is decoded into (media id, offset into DATA, size) entries and HIRC into objects (uint8 type, uint32 size, body whose
first uint32 is the object id). An unknown chunk or object type round-trips as raw bytes.

HIRC types (v135): 1 State, 2 Sound, 3 Action, 4 Event, 5 Random/Sequence container, 6 Switch container, 7 Actor-Mixer,
8 Bus, 9 Layer container, 10 Music segment, 11 Music track, 12 Music switch container, 13 Music random/sequence container,
14 Attenuation, 16 FX share set, 17 FX custom, 18 Aux bus, 21 Audio device.

Deep-parsed (Node = a view that records the byte offsets of every id the object holds, so a clone can be re-wired and a
tree leaf re-pointed in place; the body stays the bytes as read):
  Event: id, var-uint action count, action ids.
  Action: id, uint16 action type (0x0403 = Play), uint32 target id, uint8 target-is-bus, props, ... (Play: fade curve,
    uint32 bank id at the end).
  NodeBaseParams (every audio node): FX block, uint8 override-attachment, uint32 override bus, uint32 direct parent,
    priority bits, prop bundle, ranged props, positioning, aux sends (+ uint32 reflections aux bus), advanced settings,
    states, RTPCs. Containers then carry Children (uint32 count + ids) and their own selection data:
    Random/Sequence playlist (uint16 count, {uint32 child, int32 weight}); Switch container (group type/id, default
    switch, switch -> child lists, per-child params); Layer container (layers -> associated children).
  Music nodes: uint8 flags + NodeBaseParams + Children + meter + stingers; Music switch container then transition
    rules, uint8 continue-playback and the decision tree: uint32 depth, depth x uint32 game-sync group ids (the
    "arguments"), depth x uint8 group types (0 switch, 1 state), uint32 tree byte size, uint8 mode, then 12-byte nodes
    {uint32 key, uint32 audio node id | (uint16 first child index, uint16 child count), uint16 weight, uint16 probability}.
    A node is a leaf when it sits at depth == tree depth; key 0 = the "any" (*) branch.
Event names hash with FNV-1 32-bit over the lower-cased name (fnv1()); Wwise_IDs.h next to the banks lists the names
(parse_ids_header()).

Game facts (vanilla dump, same layout in Lumi 2.2F's Delphis_Main.bnk):
  - Delphis_Main.bnk holds all BGM: the 35 music switch containers (none elsewhere), 390 music random/sequence containers,
    691 segments, 840 tracks. PLAY_BGM / PLAY_BGM_CONTEST / PLAY_BGM_GAMEOVER play 6 top containers: four keyed on the
    DSPLAYER state group (field, battle, contest, event trees), one on WEATHER, one on ENVIRONMENT; their children are
    keyed on BGM_FIELD (4-argument tree FADEIN, BGM_FIELD, GINGA_C04, GINGA_D02), BGM_BATTLE, BGM_CONTEST, BGM_EVENT.
    Every *_SILENCE state leaf plays a music random container whose one segment/track plays 382403544.wem (563 B).
  - Pokemon cries: the 14,202 PLAY_PV_* events are all in Delphis_Main.bnk; each is one Play action on a Sound (or a
    switch container); cry media are streamed .wem files (stream type 2).
"""
import struct

T_STATE, T_SOUND, T_ACTION, T_EVENT, T_RANSEQ, T_SWITCH, T_ACTORMIXER, T_BUS, T_LAYER = 1, 2, 3, 4, 5, 6, 7, 8, 9
T_MSEGMENT, T_MTRACK, T_MSWITCH, T_MRANSEQ = 10, 11, 12, 13
TYPE_NAMES = {1: 'State', 2: 'Sound', 3: 'Action', 4: 'Event', 5: 'RanSeqCntr', 6: 'SwitchCntr', 7: 'ActorMixer',
              8: 'Bus', 9: 'LayerCntr', 10: 'MusicSegment', 11: 'MusicTrack', 12: 'MusicSwitchCntr',
              13: 'MusicRanSeqCntr', 14: 'Attenuation', 15: 'DialogueEvent', 16: 'FxShareSet', 17: 'FxCustom',
              18: 'AuxBus', 19: 'LFO', 20: 'Envelope', 21: 'AudioDevice', 22: 'TimeMod'}
ACTION_PLAY = 0x0403
# audio-hierarchy objects Node() parses (children / parent / selection data)
NODE_TYPES = (T_SOUND, T_RANSEQ, T_SWITCH, T_ACTORMIXER, T_LAYER, T_MSEGMENT, T_MTRACK, T_MSWITCH, T_MRANSEQ)


def fnv1(name):
    """Wwise ShortID of a name: FNV-1 32-bit over the lower-cased ASCII bytes."""
    h = 2166136261
    for b in name.lower().encode('utf-8'):
        h = (h * 16777619) & 0xffffffff
        h ^= b
    return h


def parse_ids_header(text):
    """Wwise_IDs.h (shipped next to the banks) -> nested dicts of its namespaces, e.g.
    ids['EVENTS']['PLAY_PV_001_00_00'], ids['STATES']['BGM_BATTLE']['GROUP'], ids['STATES']['BGM_BATTLE']['STATE'][name]."""
    root, stack = {}, []
    cur = root
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('namespace '):
            name = s.split()[1]
            stack.append(cur)
            cur = cur.setdefault(name, {})
        elif s.startswith('}') and 'namespace' in s:
            cur = stack.pop()
        elif s.startswith('static const AkUniqueID'):
            name, val = s[len('static const AkUniqueID'):].split('=')
            cur[name.strip()] = int(val.strip().rstrip(';').rstrip('U'))
    return root.get('AK', root)


# ---------------------------------------------------------------- bank

class Chunk:
    __slots__ = ('tag', 'data')

    def __init__(self, tag, data):
        self.tag, self.data = tag, data


class HObj:
    """One HIRC object: type, body (bytearray; first uint32 = id)."""
    __slots__ = ('type', 'body')

    def __init__(self, type_, body):
        self.type, self.body = type_, bytearray(body)

    @property
    def id(self):
        return struct.unpack_from('<I', self.body, 0)[0]

    @id.setter
    def id(self, v):
        struct.pack_into('<I', self.body, 0, v)

    def __repr__(self):
        return f'<{TYPE_NAMES.get(self.type, self.type)} {self.id}>'


class Bank:
    """chunks = every chunk in order; .version/.bank_id from BKHD; .media = DIDX entries [(id, offset, size)];
    .objects = HIRC objects in order (None if the bank has no HIRC)."""

    def __init__(self, data):
        self.chunks = []
        self.media = None
        self.objects = None
        p = 0
        while p < len(data):
            tag, n = struct.unpack_from('<4sI', data, p)
            body = data[p + 8:p + 8 + n]
            if len(body) != n:
                raise ValueError(f'bnk: chunk {tag} overruns the file')
            p += 8 + n
            if tag == b'DIDX':
                if n % 12:
                    raise ValueError('bnk: DIDX size not a multiple of 12')
                self.media = [struct.unpack_from('<3I', body, i) for i in range(0, n, 12)]
                body = None
            elif tag == b'HIRC':
                cnt = struct.unpack_from('<I', body, 0)[0]
                objs, q = [], 4
                for _ in range(cnt):
                    t, sz = struct.unpack_from('<BI', body, q)
                    objs.append(HObj(t, body[q + 5:q + 5 + sz]))
                    q += 5 + sz
                if q != n:
                    raise ValueError('bnk: HIRC object sizes do not add up')
                self.objects = objs
                body = None
            self.chunks.append(Chunk(tag, body))
        bk = self.chunk(b'BKHD')
        self.version, self.bank_id = struct.unpack_from('<2I', bk.data, 0) if bk else (None, None)
        self._index = None

    def chunk(self, tag):
        for c in self.chunks:
            if c.tag == tag:
                return c
        return None

    def to_bytes(self):
        out = []
        for c in self.chunks:
            if c.tag == b'DIDX':
                body = b''.join(struct.pack('<3I', *m) for m in self.media)
            elif c.tag == b'HIRC':
                body = struct.pack('<I', len(self.objects)) + b''.join(
                    struct.pack('<BI', o.type, len(o.body)) + bytes(o.body) for o in self.objects)
            else:
                body = c.data
            out.append(struct.pack('<4sI', c.tag, len(body)) + body)
        return b''.join(out)

    def media_bytes(self, media_id):
        d = self.chunk(b'DATA').data
        for i, off, sz in self.media or ():
            if i == media_id:
                return d[off:off + sz]
        return None

    def add_media(self, media_id, data):
        """a new DIDX entry with its bytes appended to DATA (16-byte aligned, as the banks store media)"""
        dc = self.chunk(b'DATA')
        if self.media is None or dc is None:
            raise ValueError('bnk: no DIDX/DATA chunk to add media to')
        off = (len(dc.data) + 15) & ~15
        dc.data = dc.data + b'\0' * (off - len(dc.data)) + bytes(data)
        self.media.append((media_id, off, len(data)))
        self.media.sort()

    # ---- HIRC lookup
    def index(self):
        """{id: object} (first object of an id; ids are unique per bank in the game's files except type-1 States)."""
        if self._index is None:
            self._index = {}
            for o in self.objects or ():
                self._index.setdefault(o.id, o)
        return self._index

    def get(self, oid):
        return self.index().get(oid)

    def of_type(self, t):
        return [o for o in self.objects or () if o.type == t]

    def add(self, obj):
        self.objects.append(obj)
        self._index = None

    def event(self, name_or_id):
        oid = fnv1(name_or_id) if isinstance(name_or_id, str) else name_or_id
        o = self.get(oid)
        return o if o is not None and o.type == T_EVENT else None


# ---------------------------------------------------------------- cursor

class _Cur:
    __slots__ = ('b', 'p', 'refs', 'kids_off')

    def __init__(self, b, p=0):
        self.b, self.p, self.refs, self.kids_off = b, p, [], None

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.b, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]
        self.p += 4
        return v

    def var(self):
        """Wwise var-uint: 7 bits per byte, high bit = more, most significant group first."""
        v = 0
        while True:
            b = self.u8()
            v = (v << 7) | (b & 0x7f)
            if not b & 0x80:
                return v

    def ref(self, kind):
        """An id field: remembered as (offset, kind) so a clone can remap it."""
        self.refs.append((self.p, kind))
        return self.u32()

    def skip(self, n):
        self.p += n


# ref kinds: 'node' = an audio node of the actor-mixer/music hierarchy (children, playlists, tree leaves...);
# 'parent' = DirectParentID; others are left alone by a clone (buses, attenuations, game syncs, media)

def _node_base(c, v):
    c.skip(1)                        # bIsOverrideParentFX
    nfx = c.u8()
    if nfx:
        c.skip(1 + 7 * nfx)          # bitsFxBypass, {u8 index, u32 fx id, u8 share set, u8 rendered}
    c.skip(1)                        # bOverrideAttachmentParams
    c.u32()                          # OverrideBusId
    c.ref('parent')
    c.skip(1)                        # priority / midi bits
    n = c.u8()
    c.skip(n + 4 * n)                # AkPropBundle<AkPropValue>
    n = c.u8()
    c.skip(n + 8 * n)                # AkPropBundle<RANGE> (min, max)
    bits = c.u8()                    # positioning
    if bits & 0x02:                  # has listener-relative routing -> 3D bits
        c.skip(1)
    if bits & 0x01 and (bits >> 5) & 3:   # 3D automation (path)
        c.skip(1 + 4)                # ePathMode, TransitionTime
        nv = c.u32()
        c.skip(16 * nv)              # vertices (x, y, z, duration)
        npl = c.u32()
        c.skip(8 * npl + 12 * npl)   # playlist items + automation ranges
    aux = c.u8()
    if aux & 0x08:
        c.skip(16)                   # 4 aux bus ids
    c.skip(4)                        # reflections aux bus (v135)
    c.skip(6)                        # adv settings: bits, virtual queue, u16 max instances, below threshold, bits
    n = c.var()                      # state props
    c.skip(3 * n)
    for _ in range(c.var()):         # state groups
        c.skip(5)                    # group id, sync type
        c.skip(8 * c.var())          # {state id, state instance id}
    _rtpcs(c)


def _rtpcs(c):
    for _ in range(c.u16()):
        c.skip(4 + 1 + 1)            # RTPC id, type, accum
        c.var()                      # param id
        c.skip(4 + 1)                # curve id, scaling
        c.skip(12 * c.u16())         # {x, y, interp}


def _source(c):
    """AkBankSourceData: plugin id, stream type, media id, in-memory size, source bits (+ params of a source plugin)."""
    plugin = c.u32()
    c.skip(1)
    c.ref('media')
    c.skip(4 + 1)
    if plugin & 0xf == 2:            # source plugin (tone generator...): sized parameter block
        c.skip(c.u32())


def _children(c):
    c.kids_off = c.p                 # uint32 count + ids (ascending)
    return [c.ref('node') for _ in range(c.u32())]


def _music_node(c, v):
    c.skip(1)                        # uFlags
    _node_base(c, v)
    kids = _children(c)
    c.skip(8 + 8 + 4 + 1 + 1 + 1)    # meter: grid period, grid offset, tempo, beats per bar, beat value, flag
    n = c.u32()
    for _ in range(n):               # stingers: trigger, segment, sync, cue filter, don't-repeat, lookahead
        c.skip(4)
        c.ref('node')
        c.skip(16)
    return kids


def _trans_rules(c):
    for _ in range(c.u32()):
        for _ in range(c.u32()):
            c.ref('node_or_any')     # source ids (-1 = any)
        for _ in range(c.u32()):
            c.ref('node_or_any')     # destination ids
        c.skip(4 + 4 + 4 + 4 + 4 + 1)            # src rule: time, curve, offset, sync type, cue filter, play post-exit
        c.skip(4 + 4 + 4 + 4)                    # dst rule: time, curve, offset, cue filter
        c.ref('node_or_any')                     # jump-to id
        c.skip(2 + 2 + 1 + 1)                    # jump-to type, entry type, play pre-entry, match source cue name
        if c.u8():                               # transition object
            c.ref('node')
            c.skip(12 + 12 + 1 + 1)


class Node:
    """Parsed view of an audio-hierarchy object: refs = [(offset, kind)] of every id field found; children, parent;
    for a music switch container also .tree (DecisionTree)."""

    def __init__(self, obj, version=135):
        self.obj = obj
        self.tree = None
        self.playlist = None
        b = obj.body
        c = _Cur(b, 4)
        t = obj.type
        self.children = []
        if t == T_SOUND:
            _source(c)
            _node_base(c, version)
        elif t == T_ACTORMIXER:
            _node_base(c, version)
            self.children = _children(c)
        elif t == T_RANSEQ:
            _node_base(c, version)
            c.skip(2 + 2 + 2 + 4 + 4 + 4 + 2 + 1 + 1 + 1 + 1)
            self.children = _children(c)
            self.playlist = []
            for _ in range(c.u16()):
                self.playlist.append(c.ref('node'))
                c.skip(4)            # weight
        elif t == T_SWITCH:
            _node_base(c, version)
            c.skip(1)                # group type
            c.ref('gamesync')
            c.ref('gamesync')        # default switch
            c.skip(1)                # continuous validation
            self.children = _children(c)
            for _ in range(c.u32()):
                c.ref('gamesync')
                for _ in range(c.u32()):
                    c.ref('node')
            for _ in range(c.u32()):
                c.ref('node')
                c.skip(1 + 1 + 4 + 4)
        elif t == T_LAYER:
            _node_base(c, version)
            self.children = _children(c)
            for _ in range(c.u32()):
                c.skip(4)            # layer id
                _rtpcs(c)
                c.skip(4 + 1)        # rtpc id, rtpc type
                for _ in range(c.u32()):
                    c.ref('node')
                    c.skip(12 * c.u32())
            c.skip(1)                # continuous validation
        elif t == T_MSEGMENT:
            self.children = _music_node(c, version)
            c.skip(8)                # duration
            for _ in range(c.u32()):     # markers: id, f64 position, uint32-length name
                c.skip(4 + 8)
                c.skip(c.u32())
        elif t == T_MTRACK:
            c.skip(1)                # uFlags
            for _ in range(c.u32()):     # sources (AkBankSourceData)
                _source(c)
            n = c.u32()
            for _ in range(n):       # playlist: track id, source id, cache id, play at, begin/end trim, duration
                c.skip(4)
                c.ref('media')
                c.skip(4 + 8 * 4)
            if n:
                c.skip(4)            # sub-track count
            for _ in range(c.u32()):     # clip automation: clip index, type, points
                c.skip(8)
                c.skip(12 * c.u32())
            _node_base(c, version)
            if c.u8() == 3:          # eTrackType switch: group type/id, default, associations, transition params
                c.skip(1)
                c.ref('gamesync')
                c.ref('gamesync')
                for _ in range(c.u32()):
                    c.ref('gamesync')
                c.skip(12 + 4 + 4 + 12)
            c.skip(4)                # look-ahead time
        elif t in (T_MSWITCH, T_MRANSEQ):
            self.children = _music_node(c, version)
            _trans_rules(c)
            if t == T_MSWITCH:
                c.skip(1)            # bIsContinuePlayback
                self.tree = DecisionTree(obj, c)
            else:
                self.playlist = []
                for _ in range(c.u32()):     # playlist items (flat list, 30 bytes each)
                    self.playlist.append(c.ref('node'))   # segment id (0 for a group item)
                    c.skip(4)        # playlist item id
                    c.skip(4 + 4 + 2 + 2 + 2 + 4 + 2 + 1 + 1)   # children, type, loop x3, weight, avoid repeat, flags
        else:
            raise ValueError(f'no node parser for HIRC type {t}')
        if c.p != len(b):
            raise ValueError(f'{obj!r}: parsed {c.p} of {len(b)} bytes')
        self.refs = c.refs
        self.children_off = c.kids_off
        self.parent_off = next(o for o, k in self.refs if k == 'parent')

    @property
    def parent(self):
        return struct.unpack_from('<I', self.obj.body, self.parent_off)[0]


class DecisionTree:
    """Music switch container decision tree, edited in place in the container's body.
    arguments = [(game-sync group id, group type)], nodes = [[key, audio_or_children, weight, probability]]."""

    def __init__(self, obj, c):
        self.obj = obj
        depth = c.u32()
        groups = [c.u32() for _ in range(depth)]
        types = [c.u8() for _ in range(depth)]
        self.arguments = list(zip(groups, types))
        size = c.u32()
        self.mode = c.u8()
        self.base = c.p
        if size % 12:
            raise ValueError('decision tree size not a multiple of 12')
        self.count = size // 12
        c.skip(size)
        self.depth = depth

    def _raw(self, i):
        return struct.unpack_from('<IIHH', self.obj.body, self.base + 12 * i)

    def node(self, i):
        key, v, w, pr = self._raw(i)
        return key, v, w, pr

    def leaves(self):
        """[(index, [key per level], audio node id)] for every leaf (walk from the root, depth = number of arguments)."""
        out = []

        def walk(i, level, path):
            key, v, _w, _p = self._raw(i)
            path = path + [key] if level else path
            if level == self.depth:
                out.append((i, path, v))
                return
            first, n = v & 0xffff, v >> 16
            for j in range(first, first + n):
                walk(j, level + 1, path)
        if self.count:
            walk(0, 0, [])
        return out

    def set_leaf(self, index, audio_node_id):
        """Re-point leaf `index` (from leaves()) to another audio node id; the container body is patched in place."""
        struct.pack_into('<I', self.obj.body, self.base + 12 * index + 4, audio_node_id)


# ---------------------------------------------------------------- events

def reachable(bank, oid):
    """(node ids, media ids) reachable from audio node oid through children / playlists / tree leaves (one bank).
    A music-switch leaf is "silence" in this game when its media set is the one short silent .wem every *_SILENCE state
    leaf plays (382403544.wem, 563 B, in the vanilla and Lumi Delphis_Main.bnk)."""
    nodes, media, todo = set(), set(), [oid]
    while todo:
        i = todo.pop()
        if i in nodes or i in (0, 0xffffffff):
            continue
        o = bank.get(i)
        if o is None or o.type not in NODE_TYPES:
            continue
        nodes.add(i)
        for off, kind in Node(o, bank.version).refs:
            v = struct.unpack_from('<I', o.body, off)[0]
            if kind == 'media':
                media.add(v)
            elif kind in ('node', 'node_or_any'):
                todo.append(v)
    return nodes, media


def event_actions(obj):
    """Event -> [action ids]."""
    c = _Cur(obj.body, 4)
    n = c.var()
    ids = [c.u32() for _ in range(n)]
    if c.p != len(obj.body):
        raise ValueError(f'{obj!r}: event size mismatch')
    return ids


def action_info(obj):
    """Action -> (action type, target id, target is a bus)."""
    t, target, bus = struct.unpack_from('<HIB', obj.body, 4)
    return t, target, bus


class Banks:
    """Several banks seen together (the game loads Init + Delphis_Main + the per-scene banks): id lookup across banks,
    the set of used ids, event lookup by name and the event-duplication helper."""

    def __init__(self, banks):
        self.banks = dict(banks)        # name -> Bank

    def used_ids(self):
        s = set()
        for b in self.banks.values():
            for o in b.objects or ():
                s.add(o.id)
            for m in b.media or ():
                s.add(m[0])
            s.add(b.bank_id)
        return s

    def find(self, oid):
        """[(bank name, object)] for every bank holding object oid."""
        return [(n, b.get(oid)) for n, b in self.banks.items() if b.get(oid) is not None]

    def event(self, name_or_id):
        oid = fnv1(name_or_id) if isinstance(name_or_id, str) else name_or_id
        for n, b in self.banks.items():
            e = b.event(oid)
            if e is not None:
                return n, e
        return None, None

    def plays(self, name_or_id):
        """What an event plays: [(action id, action type, target id, target object or None)] (same bank)."""
        bn, ev = self.event(name_or_id)
        if ev is None:
            return []
        b = self.banks[bn]
        out = []
        for aid in event_actions(ev):
            a = b.get(aid)
            if a is None:
                out.append((aid, None, None, None))
                continue
            t, target, _bus = action_info(a)
            out.append((aid, t, target, b.get(target)))
        return out

    def duplicate_event(self, src, new_name, extra_used=(), media_map=None):
        """Copy event src (name or id) as new_name (its id = fnv1(new_name)) with the whole playback chain under fresh ids:
        the event, its actions, every node an action targets and all their descendants (children, playlists, switch
        assignments, tree leaves). References inside the copy are re-wired to the copies; references leaving the copy
        (buses, attenuations, game syncs, media, the parent of a copied top node) stay. A copied top node is added to its
        parent's Children list (an actor-mixer: inheritance only; a playlist/switch/tree parent never selects a child
        it has no entry for). Fresh ids are unused in every bank given (plus extra_used).
        media_map (a dict, shared by the calls of one copy): the copied sounds get NEW media ids too (old -> new kept in
        it; an old id already in it reuses its new id); media embedded in the bank (DIDX) is duplicated there, a streamed
        <id>.wem the caller copies to <new id>.wem.
        Returns {old id: new id} (event included)."""
        bn, ev = self.event(src)
        if ev is None:
            raise KeyError(f'event {src} not found')
        bank = self.banks[bn]
        new_eid = fnv1(new_name)
        used = self.used_ids() | set(extra_used) | set((media_map or {}).values())
        if new_eid in used:
            raise ValueError(f'event id {new_eid} ({new_name}) is already used')
        used.add(new_eid)
        # collect: actions + node closure (within the event's bank)
        actions = [bank.get(a) for a in event_actions(ev)]
        if any(a is None for a in actions):
            raise ValueError('an action of the event is not in its bank')
        nodes, order, tops = {}, [], []

        def visit(oid, top):
            if oid in nodes or oid == 0:
                return
            o = bank.get(oid)
            if o is None or o.type not in NODE_TYPES:
                return
            nd = Node(o, bank.version)
            nodes[oid] = nd
            order.append(o)
            if top:
                tops.append(nd)
            for off, kind in nd.refs:
                if kind in ('node', 'node_or_any'):
                    visit(struct.unpack_from('<I', o.body, off)[0], False)
        for a in actions:
            t, target, isbus = action_info(a)
            if not isbus:
                visit(target, True)
        mapping = {ev.id: new_eid}
        seed = new_eid

        def fresh():
            nonlocal seed
            while True:
                seed = fnv1(f'{new_name}#{seed}')
                if seed not in used and seed not in (0, 0xffffffff):
                    used.add(seed)
                    return seed
        for a in actions:
            mapping[a.id] = fresh()
        for o in order:
            mapping[o.id] = fresh()

        def remap(body, refs):
            for off, kind in refs:
                if kind in ('node', 'node_or_any', 'parent'):
                    v = struct.unpack_from('<I', body, off)[0]
                    if v in mapping:
                        struct.pack_into('<I', body, off, mapping[v])
                elif kind == 'media' and media_map is not None:
                    v = struct.unpack_from('<I', body, off)[0]
                    if v in (0, 0xffffffff):
                        continue
                    if v not in media_map:
                        media_map[v] = fresh()
                        data = bank.media_bytes(v) if bank.media else None
                        if data is not None:
                            bank.add_media(media_map[v], data)
                    struct.pack_into('<I', body, off, media_map[v])
        new_objs = []
        for o in order:
            n = HObj(o.type, o.body)
            remap(n.body, nodes[o.id].refs)
            n.id = mapping[o.id]
            new_objs.append(n)
        for a in actions:
            n = HObj(a.type, a.body)
            n.id = mapping[a.id]
            t, target, isbus = action_info(a)
            if not isbus and target in mapping:
                struct.pack_into('<I', n.body, 6, mapping[target])
            new_objs.append(n)
        e = HObj(ev.type, ev.body)
        e.id = new_eid
        c = _Cur(e.body, 4)
        for _ in range(c.var()):
            aid = struct.unpack_from('<I', e.body, c.p)[0]
            struct.pack_into('<I', e.body, c.p, mapping[aid])
            c.skip(4)
        new_objs.append(e)
        # top nodes join their parent's Children list
        for nd in tops:
            p = nd.parent
            po = bank.get(p) if p else None
            if po is not None and po.type in (T_ACTORMIXER, T_RANSEQ, T_SWITCH, T_LAYER):
                _add_child(po, mapping[nd.obj.id], bank.version)
        for n in new_objs:
            bank.add(n)
        return mapping


def _add_child(parent, child_id, version):
    """Insert child_id into a container's Children list (kept ascending, as the banks have it)."""
    nd = Node(parent, version)
    if child_id in nd.children:
        return
    new = sorted(nd.children + [child_id])
    at = nd.children_off
    parent.body[at:at + 4 + 4 * len(nd.children)] = struct.pack(f'<I{len(new)}I', len(new), *new)
