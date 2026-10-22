"""Switch texture data -> data a Windows (Direct3D 11) player samples.

Rules (census of the BDSP v1.3.0 romfs: 41,017 Texture2D + 10 Cubemap):
  - formats a PC GPU / Unity Windows player reads as they are (DXT1/5, BC4/5/6H/7, RGBA32, RGB24, Alpha8, R8, RGBA64 ...) are
    copied byte for byte;
  - ASTC (13,795 textures) and ETC (mods only) are decoded level by level from their own blocks into RGBA32 = exactly the texels
    the Switch GPU samples (texture2ddecoder's ASTC decoder matches the console's output). No re-encoding: no quality loss,
    and the same bytes on every CPU;
  - DXT1Crunched / DXT5Crunched (105 textures) are unpacked level by level into plain DXT1 / DXT5 (crunch stores real DXT
    blocks per level; unpacking is lossless).
Layout: an image = its mip levels in order (largest first); a Cubemap holds m_ImageCount images one after another.
"""
import math

import numpy as np
import texture2ddecoder

RGBA32, DXT1, DXT5 = 4, 10, 12

# formats copied byte for byte (Unity TextureFormat ids)
NATIVE = {1, 3, 4, 5, 7, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 24, 25, 26, 27, 62, 63, 72, 73, 74}
# ASTC: (block width, block height); 48-53 = ASTC_RGB_*, 54-59 = ASTC_RGBA_* (same block data)
ASTC = {48: (4, 4), 49: (5, 5), 50: (6, 6), 51: (8, 8), 52: (10, 10), 53: (12, 12),
        54: (4, 4), 55: (5, 5), 56: (6, 6), 57: (8, 8), 58: (10, 10), 59: (12, 12)}
# ETC family: (bytes per 4x4 block, decoder -> BGRA)
ETC = {34: (8, texture2ddecoder.decode_etc1), 45: (8, texture2ddecoder.decode_etc2),
       46: (8, texture2ddecoder.decode_etc2a1), 47: (16, texture2ddecoder.decode_etc2a8)}
# crunched -> the plain format its levels unpack to
CRUNCHED = {28: DXT1, 29: DXT5}

# bytes per texel / per 4x4 block, for the size check of native formats
TEXEL_BYTES = {1: 1, 3: 3, 4: 4, 5: 4, 7: 2, 9: 2, 13: 2, 14: 4, 15: 2, 16: 4, 17: 8, 18: 4, 19: 8, 20: 16, 62: 2, 63: 1,
               72: 4, 73: 6, 74: 8}
BLOCK4_BYTES = {10: 8, 12: 16, 24: 16, 25: 16, 26: 8, 27: 16}


class TextureError(ValueError):
    pass


def mip_dims(w, h, n):
    return [(max(1, w >> i), max(1, h >> i)) for i in range(n)]


def image_bytes(fmt, w, h, mips):
    """Bytes one image (all its levels) of a native / ASTC / ETC format takes; None when unknown."""
    if fmt in TEXEL_BYTES:
        return sum(lw * lh * TEXEL_BYTES[fmt] for lw, lh in mip_dims(w, h, mips))
    if fmt in BLOCK4_BYTES:
        return sum(((lw + 3) // 4) * ((lh + 3) // 4) * BLOCK4_BYTES[fmt] for lw, lh in mip_dims(w, h, mips))
    if fmt in ASTC:
        bw, bh = ASTC[fmt]
        return sum(math.ceil(lw / bw) * math.ceil(lh / bh) * 16 for lw, lh in mip_dims(w, h, mips))
    if fmt in ETC:
        return sum(((lw + 3) // 4) * ((lh + 3) // 4) * ETC[fmt][0] for lw, lh in mip_dims(w, h, mips))
    return None


def _bgra_to_rgba(bgra, w, h):
    return np.ascontiguousarray(np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]]).tobytes()


def _decode_image(fmt, w, h, mips, data):
    out, off = [], 0
    if fmt in ASTC:
        bw, bh = ASTC[fmt]
        for lw, lh in mip_dims(w, h, mips):
            n = math.ceil(lw / bw) * math.ceil(lh / bh) * 16
            lvl = data[off:off + n]
            if len(lvl) != n:
                raise TextureError(f'ASTC data short at level {lw}x{lh}: needs {n}, has {len(lvl)}')
            off += n
            out.append(_bgra_to_rgba(texture2ddecoder.decode_astc(lvl, lw, lh, bw, bh), lw, lh))
    else:
        block, dec = ETC[fmt]
        for lw, lh in mip_dims(w, h, mips):
            n = ((lw + 3) // 4) * ((lh + 3) // 4) * block
            lvl = data[off:off + n]
            if len(lvl) != n:
                raise TextureError(f'ETC data short at level {lw}x{lh}: needs {n}, has {len(lvl)}')
            off += n
            out.append(_bgra_to_rgba(dec(lvl, lw, lh), lw, lh))
    return b''.join(out), off


def convert(fmt, w, h, mips, images, data):
    """-> (new_format, new_data, kind) for one Texture2D / Cubemap payload. kind = 'copy' | 'decoded' | 'uncrunched'."""
    if fmt in NATIVE:
        return fmt, data, 'copy'
    if fmt in ASTC or fmt in ETC:
        per = image_bytes(fmt, w, h, mips)
        if len(data) < per * images:
            raise TextureError(f'format {fmt} {w}x{h} x{mips} x{images}: {len(data)} bytes, needs {per * images}')
        parts = []
        for i in range(images):
            img, used = _decode_image(fmt, w, h, mips, data[i * per:(i + 1) * per])
            parts.append(img)
        return RGBA32, b''.join(parts), 'decoded'
    if fmt in CRUNCHED:
        if images != 1:
            raise TextureError(f'crunched texture with {images} images')
        levels = [texture2ddecoder.unpack_unity_crunch(bytes(data), i) for i in range(mips)]
        want = image_bytes(CRUNCHED[fmt], w, h, mips)
        got = sum(len(x) for x in levels)
        if got != want:
            raise TextureError(f'crunched {w}x{h} x{mips}: unpacked {got} bytes, expected {want}')
        return CRUNCHED[fmt], b''.join(levels), 'uncrunched'
    raise TextureError(f'texture format {fmt} has no Windows conversion')
