"""libvpx through ctypes: decode VP9 / VP8 frames, encode VP8. libvpx (BSD-3-Clause, Google's patent grant) ships in the
release as udpre_runtime/vpx/ (the 1.17.0 build of PyAV 19.0.2's Windows wheel + the winpthreads runtime it needs - see
release/build_exe.py); from the source tree the same DLLs are taken from an installed `av` package.
The structures below are libvpx 1.17.0's (vpx_encoder.h / vpx_image.h); load() refuses another version.
"""
import ctypes
import glob
import os
import sys
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_int64, c_long, c_size_t, c_uint, c_ulong, c_void_p

VERSION = b'v1.17.0'
IMAGE_ABI = 5
CODEC_ABI = 4 + IMAGE_ABI
DECODER_ABI = 3 + CODEC_ABI
ENCODER_ABI = 18 + CODEC_ABI + (7 + 5)          # + VPX_EXT_RATECTRL_ABI_VERSION (7 + VPX_TPL_ABI_VERSION 5)
IMG_FMT_I420 = 0x102
CX_FRAME_PKT = 0
FRAME_IS_KEY = 0x1
FRAME_IS_INVISIBLE = 0x4
DL_GOOD_QUALITY = 1000000
VP8E_SET_CPUUSED = 13
VP8E_SET_ENABLEAUTOALTREF = 14


class VpxError(RuntimeError):
    pass


class Rational(Structure):
    _fields_ = [('num', c_int), ('den', c_int)]


class FixedBuf(Structure):
    _fields_ = [('buf', c_void_p), ('sz', c_size_t)]


class EncCfg(Structure):
    """The leading fields of vpx_codec_enc_cfg_t (1.17.0) up to kf_max_dist; the library fills a larger buffer."""
    _fields_ = [('g_usage', c_uint), ('g_threads', c_uint), ('g_profile', c_uint), ('g_w', c_uint), ('g_h', c_uint),
                ('g_bit_depth', c_int), ('g_input_bit_depth', c_uint), ('g_timebase', Rational),
                ('g_error_resilient', c_uint), ('g_pass', c_int), ('g_lag_in_frames', c_uint),
                ('rc_dropframe_thresh', c_uint), ('rc_resize_allowed', c_uint), ('rc_scaled_width', c_uint),
                ('rc_scaled_height', c_uint), ('rc_resize_up_thresh', c_uint), ('rc_resize_down_thresh', c_uint),
                ('rc_end_usage', c_int), ('rc_twopass_stats_in', FixedBuf), ('rc_firstpass_mb_stats_in', FixedBuf),
                ('rc_target_bitrate', c_uint), ('rc_min_quantizer', c_uint), ('rc_max_quantizer', c_uint),
                ('rc_undershoot_pct', c_uint), ('rc_overshoot_pct', c_uint), ('rc_buf_sz', c_uint),
                ('rc_buf_initial_sz', c_uint), ('rc_buf_optimal_sz', c_uint), ('rc_2pass_vbr_bias_pct', c_uint),
                ('rc_2pass_vbr_minsection_pct', c_uint), ('rc_2pass_vbr_maxsection_pct', c_uint),
                ('rc_2pass_vbr_corpus_complexity', c_uint), ('kf_mode', c_int), ('kf_min_dist', c_uint),
                ('kf_max_dist', c_uint)]


class Image(Structure):
    _fields_ = [('fmt', c_int), ('cs', c_int), ('range', c_int), ('w', c_uint), ('h', c_uint), ('bit_depth', c_uint),
                ('d_w', c_uint), ('d_h', c_uint), ('r_w', c_uint), ('r_h', c_uint), ('x_chroma_shift', c_uint),
                ('y_chroma_shift', c_uint), ('planes', c_void_p * 4), ('stride', c_int * 4), ('bps', c_int),
                ('user_priv', c_void_p), ('img_data', c_void_p), ('img_data_owner', c_int), ('self_allocd', c_int),
                ('fb_priv', c_void_p)]


class FramePkt(Structure):
    _fields_ = [('buf', c_void_p), ('sz', c_size_t), ('pts', c_int64), ('duration', c_ulong), ('flags', c_uint),
                ('partition_id', c_int)]


class CxPkt(Structure):
    _fields_ = [('kind', c_int), ('_pad', c_int), ('frame', FramePkt)]


_lib = None


def dll_dirs():
    out = []
    base = getattr(sys, '_MEIPASS', None)
    if base:
        out.append(os.path.join(base, 'vpx'))
    try:
        import importlib.util
        spec = importlib.util.find_spec('av')
        if spec and spec.submodule_search_locations:
            out.append(os.path.join(os.path.dirname(list(spec.submodule_search_locations)[0]), 'av.libs'))
    except (ImportError, ValueError):
        pass
    return out


def load():
    global _lib
    if _lib is not None:
        return _lib
    for d in dll_dirs():
        hits = glob.glob(os.path.join(d, 'libvpx*.dll'))
        if hits:
            os.add_dll_directory(d)
            lib = ctypes.CDLL(hits[0])
            break
    else:
        raise VpxError('libvpx is missing from this uDPRE folder (udpre_runtime/vpx) - unzip the uDPRE release again')
    lib.vpx_codec_version_str.restype = c_char_p
    if lib.vpx_codec_version_str() != VERSION:
        raise VpxError(f'libvpx {lib.vpx_codec_version_str()!r}, this uDPRE needs {VERSION!r}')
    for name in ('vpx_codec_vp9_dx', 'vpx_codec_vp8_dx', 'vpx_codec_vp8_cx'):
        getattr(lib, name).restype = c_void_p
    lib.vpx_codec_dec_init_ver.argtypes = [c_void_p, c_void_p, c_void_p, c_long, c_int]
    lib.vpx_codec_decode.argtypes = [c_void_p, c_char_p, c_uint, c_void_p, c_long]
    lib.vpx_codec_get_frame.argtypes = [c_void_p, POINTER(c_void_p)]
    lib.vpx_codec_get_frame.restype = POINTER(Image)
    lib.vpx_codec_enc_config_default.argtypes = [c_void_p, c_void_p, c_uint]
    lib.vpx_codec_enc_init_ver.argtypes = [c_void_p, c_void_p, c_void_p, c_long, c_int]
    lib.vpx_codec_encode.argtypes = [c_void_p, c_void_p, c_int64, c_ulong, c_long, c_ulong]
    lib.vpx_codec_get_cx_data.argtypes = [c_void_p, POINTER(c_void_p)]
    lib.vpx_codec_get_cx_data.restype = POINTER(CxPkt)
    lib.vpx_codec_control_.argtypes = [c_void_p, c_int, c_int]
    lib.vpx_codec_destroy.argtypes = [c_void_p]
    lib.vpx_codec_error_detail.argtypes = [c_void_p]
    lib.vpx_codec_error_detail.restype = c_char_p
    lib.vpx_codec_err_to_string.restype = c_char_p
    _lib = lib
    return lib


def _check(lib, ctx, rc, what):
    if rc:
        detail = lib.vpx_codec_error_detail(ctx) if ctx is not None else None
        raise VpxError(f'{what}: {lib.vpx_codec_err_to_string(rc).decode()}' + (f' ({detail.decode()})' if detail else ''))


def to_vp8(frames, codec, bit_rate_kbps=3000, min_q=4, max_q=42, cpu_used=2, kf_max=120, threads=None):
    """frames = [(time ns, keyframe, compressed frame)] of a VP9 / VP8 stream -> [(time ns, keyframe, VP8 frame)], and
    (width, height). Every decoded frame is encoded with its own timestamp (time base 1 ms)."""
    lib = load()
    dctx = ctypes.create_string_buffer(512)
    ectx = ctypes.create_string_buffer(512)
    iface = lib.vpx_codec_vp9_dx() if codec == 'vp9' else lib.vpx_codec_vp8_dx()
    _check(lib, None, lib.vpx_codec_dec_init_ver(dctx, iface, None, 0, DECODER_ABI), 'decoder init')
    cfg_buf = ctypes.create_string_buffer(4096)
    cfg = EncCfg.from_buffer(cfg_buf)
    out, size, enc_ready = [], None, False
    times = [t // 1_000_000 for t, _, _ in frames]

    def drain():
        it = c_void_p()
        while True:
            p = lib.vpx_codec_get_cx_data(ectx, byref(it))
            if not p:
                return
            pk = p.contents
            if pk.kind == CX_FRAME_PKT and not pk.frame.flags & FRAME_IS_INVISIBLE:
                out.append((pk.frame.pts * 1_000_000, bool(pk.frame.flags & FRAME_IS_KEY),
                            ctypes.string_at(pk.frame.buf, pk.frame.sz)))
    try:
        for k, (t, _, data) in enumerate(frames):
            _check(lib, dctx, lib.vpx_codec_decode(dctx, data, len(data), None, 0), f'decode frame {k}')
            it = c_void_p()
            img = lib.vpx_codec_get_frame(dctx, byref(it))
            if not img:
                continue
            im = img.contents
            if im.fmt != IMG_FMT_I420:
                raise VpxError(f'frame {k}: image format {im.fmt:#x}, only 8-bit 4:2:0 is handled')
            if not enc_ready:
                size = (im.d_w, im.d_h)
                _check(lib, None, lib.vpx_codec_enc_config_default(lib.vpx_codec_vp8_cx(), cfg_buf, 0), 'encoder config')
                if (cfg.g_w, cfg.g_h, cfg.g_timebase.num, cfg.g_timebase.den) != (320, 240, 1, 30):
                    raise VpxError('libvpx encoder config layout is not the expected one')
                cfg.g_w, cfg.g_h = size
                cfg.g_timebase = Rational(1, 1000)
                cfg.g_threads = threads or min(8, os.cpu_count() or 1)
                cfg.rc_target_bitrate = bit_rate_kbps
                cfg.rc_min_quantizer, cfg.rc_max_quantizer = min_q, max_q
                cfg.kf_max_dist = kf_max
                _check(lib, None, lib.vpx_codec_enc_init_ver(ectx, lib.vpx_codec_vp8_cx(), cfg_buf, 0, ENCODER_ABI),
                       'encoder init')
                _check(lib, ectx, lib.vpx_codec_control_(ectx, VP8E_SET_CPUUSED, cpu_used), 'cpu-used')
                _check(lib, ectx, lib.vpx_codec_control_(ectx, VP8E_SET_ENABLEAUTOALTREF, 0), 'auto-alt-ref')
                enc_ready = True
            if (im.d_w, im.d_h) != size:
                raise VpxError(f'frame {k}: size changes to {im.d_w}x{im.d_h}')
            dur = max(1, (times[k + 1] - times[k]) if k + 1 < len(times) else times[k] - times[k - 1] if k else 33)
            _check(lib, ectx, lib.vpx_codec_encode(ectx, ctypes.addressof(im), times[k], dur, 0, DL_GOOD_QUALITY),
                   f'encode frame {k}')
            drain()
        if enc_ready:
            _check(lib, ectx, lib.vpx_codec_encode(ectx, None, -1, 0, 0, DL_GOOD_QUALITY), 'encoder flush')
            drain()
    finally:
        lib.vpx_codec_destroy(dctx)
        if enc_ready:
            lib.vpx_codec_destroy(ectx)
    if not out:
        raise VpxError('no frame decoded')
    return out, size
