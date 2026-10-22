"""Minimal WebM (Matroska) reading and writing for the game's movies: one video track, frames in SimpleBlocks (or Blocks
inside BlockGroups) without lacing - what the game's movies and the mods' movies hold.

read_video(path) -> Video(width, height, codec, frames=[(time in ns, keyframe, bytes)], frame_ns)
write_video(path, video) writes EBML header + Segment(SeekHead, Info, Tracks, Clusters, Cues): a cluster starts at each
keyframe (and at least every 5 s), a CuePoint per cluster, Duration in Info - the layout FFmpeg's WebM muxer writes.
"""
import struct

EBML, DOCTYPE = 0x1A45DFA3, 0x4282
SEGMENT, SEEKHEAD, SEEK, SEEKID, SEEKPOS = 0x18538067, 0x114D9B74, 0x4DBB, 0x53AB, 0x53AC
INFO, TIMESCALE, DURATION, MUXAPP, WRITEAPP = 0x1549A966, 0x2AD7B1, 0x4489, 0x4D80, 0x5741
TRACKS, TRACKENTRY, TRACKNUM, TRACKUID, TRACKTYPE, CODECID, DEFDUR, LACING = \
    0x1654AE6B, 0xAE, 0xD7, 0x73C5, 0x83, 0x86, 0x23E383, 0x9C
VIDEO, PIXW, PIXH = 0xE0, 0xB0, 0xBA
CLUSTER, TIMECODE, SIMPLEBLOCK, BLOCKGROUP, BLOCK, REFBLOCK = 0x1F43B675, 0xE7, 0xA3, 0xA0, 0xA1, 0xFB
CUES, CUEPOINT, CUETIME, CUETRACKPOS, CUETRACK, CUECLUSTERPOS = 0x1C53BB6B, 0xBB, 0xB3, 0xB7, 0xF7, 0xF1
LEVEL1 = {SEEKHEAD, INFO, TRACKS, CLUSTER, CUES, 0x1254C367, 0x1043A770, 0x1941A469}   # + Tags, Chapters, Attachments
CODECS = {'V_VP8': 'vp8', 'V_VP9': 'vp9'}


class WebmError(ValueError):
    pass


class Video:
    def __init__(self, width, height, codec, frames, frame_ns):
        self.width, self.height, self.codec, self.frames, self.frame_ns = width, height, codec, frames, frame_ns


def _vint(b, pos, keep_marker):
    first = b[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8:
        raise WebmError(f'bad EBML number at {pos}')
    value = first if keep_marker else first & (mask - 1)
    for i in range(1, length):
        value = (value << 8) | b[pos + i]
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return value, length, unknown


def _children(b, start, end):
    """(id, data start, data end) of the elements in b[start:end]; an unknown-size element ends at the next level-1 element
    (a live-written Cluster) or at end."""
    pos = start
    while pos < end:
        eid, n = _vint(b, pos, True)[:2]
        size, m, unknown = _vint(b, pos + n, False)
        data = pos + n + m
        if unknown:
            stop = data
            while stop < end:
                cid, cn = _vint(b, stop, True)[:2]
                if cid in LEVEL1:
                    break
                csize, cm, _ = _vint(b, stop + cn, False)
                stop += cn + cm + csize
            yield eid, data, stop
            pos = stop
            continue
        if data + size > end:
            raise WebmError(f'element {eid:#x} runs past its parent')
        yield eid, data, data + size
        pos = data + size


def _uint(b, s, e):
    return int.from_bytes(b[s:e], 'big')


def read_video(path):
    with open(path, 'rb') as f:
        b = f.read()
    top = list(_children(b, 0, len(b)))
    if not top or top[0][0] != EBML:
        raise WebmError(f'{path}: not an EBML file')
    doctype = next((b[s:e].decode('ascii', 'replace') for i, s, e in _children(b, top[0][1], top[0][2]) if i == DOCTYPE), '')
    if doctype not in ('webm', 'matroska'):
        raise WebmError(f'{path}: doctype {doctype!r}')
    seg = next(((s, e) for i, s, e in top if i == SEGMENT), None)
    if seg is None:
        raise WebmError(f'{path}: no Segment')
    scale = 1_000_000
    track, codec, w, h, defdur = None, None, 0, 0, 0
    blocks = []
    for i, s, e in _children(b, *seg):
        if i == INFO:
            for j, s2, e2 in _children(b, s, e):
                if j == TIMESCALE:
                    scale = _uint(b, s2, e2)
        elif i == TRACKS:
            for j, s2, e2 in _children(b, s, e):
                if j != TRACKENTRY:
                    continue
                f = {k: (s3, e3) for k, s3, e3 in _children(b, s2, e2)}
                if TRACKTYPE in f and _uint(b, *f[TRACKTYPE]) == 1 and track is None:
                    track = _uint(b, *f[TRACKNUM])
                    codec = CODECS.get(b[slice(*f[CODECID])].decode('ascii', 'replace').rstrip('\0'))
                    defdur = _uint(b, *f[DEFDUR]) if DEFDUR in f else 0
                    if VIDEO in f:
                        v = {k: (s4, e4) for k, s4, e4 in _children(b, *f[VIDEO])}
                        w, h = _uint(b, *v[PIXW]), _uint(b, *v[PIXH])
        elif i == CLUSTER:
            base = 0
            for j, s2, e2 in _children(b, s, e):
                if j == TIMECODE:
                    base = _uint(b, s2, e2)
                elif j == SIMPLEBLOCK:
                    blocks.append((base, s2, e2, None))
                elif j == BLOCKGROUP:
                    kids = list(_children(b, s2, e2))
                    blk = next(((s3, e3) for k, s3, e3 in kids if k == BLOCK), None)
                    if blk:
                        blocks.append((base, blk[0], blk[1], not any(k == REFBLOCK for k, _, _ in kids)))
    if track is None or codec is None:
        raise WebmError(f'{path}: no VP8 / VP9 video track')
    frames = []
    for base, s, e, key in blocks:
        tn, n, _ = _vint(b, s, False)
        if tn != track:
            continue
        rel = struct.unpack_from('>h', b, s + n)[0]
        flags = b[s + n + 2]
        if flags & 0x06:
            raise WebmError(f'{path}: laced video blocks are not handled')
        frames.append(((base + rel) * scale, bool(flags & 0x80) if key is None else key, bytes(b[s + n + 3:e])))
    if not frames:
        raise WebmError(f'{path}: no video frames')
    frames.sort(key=lambda fr: fr[0])
    if not defdur and len(frames) > 1:
        steps = sorted(frames[k + 1][0] - frames[k][0] for k in range(len(frames) - 1))
        defdur = steps[len(steps) // 2]
    return Video(w, h, codec, frames, defdur or 33_333_333)


def _id(i):
    return i.to_bytes((i.bit_length() + 7) // 8, 'big')


def _size(n):
    for length in range(1, 9):
        if n < (1 << (7 * length)) - 1:
            return ((1 << (7 * length)) | n).to_bytes(length, 'big')
    raise WebmError('element too large')


def _el(i, payload):
    return _id(i) + _size(len(payload)) + payload


def _u(i, v, width=None):
    n = width or max(1, (v.bit_length() + 7) // 8)
    return _el(i, v.to_bytes(n, 'big'))


def write_video(path, video, app='uDPRE'):
    """video.frames = [(time ns, keyframe, VP8 frame bytes)] in display order (no invisible frames)."""
    ms = [(t // 1_000_000, key, data) for t, key, data in video.frames]
    clusters = []
    for t, key, data in ms:
        if not clusters or (key and t > clusters[-1][0]) or t - clusters[-1][0] > 5000:
            clusters.append((t, []))
        clusters[-1][1].append((t, key, data))
    blobs, cue_times = [], []
    for start, frs in clusters:
        body = _u(TIMECODE, start)
        for t, key, data in frs:
            body += _el(SIMPLEBLOCK, b'\x81' + struct.pack('>hB', t - start, 0x80 if key else 0) + data)
        blobs.append(_el(CLUSTER, body))
        cue_times.append(start if frs[0][1] else None)
    last = ms[-1][0] + max(1, video.frame_ns // 1_000_000)
    info = _el(INFO, _u(TIMESCALE, 1_000_000) + _el(MUXAPP, app.encode()) + _el(WRITEAPP, app.encode()) +
               _el(DURATION, struct.pack('>d', float(last))))
    tracks = _el(TRACKS, _el(TRACKENTRY, _u(TRACKNUM, 1) + _u(TRACKUID, 1) + _u(LACING, 0) + _el(CODECID, b'V_VP8') +
                                       _u(TRACKTYPE, 1) + _u(DEFDUR, video.frame_ns) +
                                       _el(VIDEO, _u(PIXW, video.width) + _u(PIXH, video.height))))

    def seekhead(pos_info, pos_tracks, pos_cues):
        return _el(SEEKHEAD, b''.join(_el(SEEK, _el(SEEKID, _id(i)) + _u(SEEKPOS, p, 8))
                                      for i, p in ((INFO, pos_info), (TRACKS, pos_tracks), (CUES, pos_cues))))
    sh_len = len(seekhead(0, 0, 0))                     # fixed-width positions: its size does not depend on them
    pos_info = sh_len
    pos_tracks = pos_info + len(info)
    pos = pos_tracks + len(tracks)
    cluster_pos = []
    for blob in blobs:
        cluster_pos.append(pos)
        pos += len(blob)
    cues = _el(CUES, b''.join(_el(CUEPOINT, _u(CUETIME, t) + _el(CUETRACKPOS, _u(CUETRACK, 1) + _u(CUECLUSTERPOS, p)))
                              for t, p in zip(cue_times, cluster_pos) if t is not None))
    segment = seekhead(pos_info, pos_tracks, pos) + info + tracks + b''.join(blobs) + cues
    header = _el(EBML, _u(0x4286, 1) + _u(0x42F7, 1) + _u(0x42F2, 4) + _u(0x42F3, 8) + _el(DOCTYPE, b'webm') +
                 _u(0x4287, 2) + _u(0x4285, 2))
    with open(path, 'wb') as f:
        f.write(header + _id(SEGMENT) + (0x0100000000000000 | len(segment)).to_bytes(8, 'big') + segment)
