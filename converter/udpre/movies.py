"""Movies a Windows player can play.

Unity 2019.4's Windows VideoPlayer decodes VP8 only. The game's own movies are VP8 WebM without audio and are copied as they
are; a mod's movie in VP9 (Luminescent's opening and its stubs) is re-encoded to VP8 here, video only, same size and frame
times: libvpx (vpx.py; 3 Mbit/s, quantizer 4..42, no alt-ref frames - the settings of the uDPR Windows builds) between a
minimal WebM reader and writer (webm.py). Results are cached by the source's sha1, so one opening shared by several
translations is encoded once.
"""
import os
import shutil

from . import vpx, webm

VP8 = 'vp8'


def video_codec(path):
    """-> 'vp8' / 'vp9' of the file's video track, None when it is no WebM video this module reads."""
    try:
        return webm.read_video(path).codec
    except (webm.WebmError, OSError, IndexError):
        return None


def to_vp8(src, dst):
    """Re-encodes the video track of WebM src into a VP8 WebM dst. -> {'frames', 'width', 'height'}."""
    v = webm.read_video(src)
    frames, (w, h) = vpx.to_vp8(v.frames, v.codec)
    tmp = dst + '.part'
    webm.write_video(tmp, webm.Video(w, h, VP8, frames, v.frame_ns))
    os.replace(tmp, dst)
    return {'frames': len(frames), 'width': w, 'height': h}


def place_movie(src, dst, digest, cache_dir):
    """Puts a movie at dst: copied when it is VP8, else the VP8 re-encode (from cache_dir/<digest>.webm when made before).
    -> 'copied' | 'encoded' | 'cached'."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if video_codec(src) == VP8:
        shutil.copyfile(src, dst + '.part')
        os.replace(dst + '.part', dst)
        return 'copied'
    os.makedirs(cache_dir, exist_ok=True)
    cached = os.path.join(cache_dir, digest + '.webm')
    how = 'cached'
    if not os.path.isfile(cached):
        to_vp8(src, cached)
        how = 'encoded'
    shutil.copyfile(cached, dst + '.part')
    os.replace(dst + '.part', dst)
    return how
