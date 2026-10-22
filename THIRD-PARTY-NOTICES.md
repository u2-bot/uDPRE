# Third-party notices

uDPRE's own code is under the MIT license (`LICENSE`). A release also contains software by others, each under its own
terms:

| Component | Where in a release | Terms |
|---|---|---|
| Unity 2019.4 runtime (player, IL2CPP runtime, built-in resources) | `UnityPlayer.dll`, `UnityCrashHandler64.exe`, `Dpr_Data/Resources/`, `Dpr_Data/il2cpp_data/` | Unity Technologies; distributed as part of a game built with Unity, under Unity's terms |
| Unity packages compiled into the player (uGUI, TextMesh Pro, Timeline) | `GameAssembly.dll` | Unity Companion License |
| Audiokinetic Wwise 2019.2 sound engine runtime | `Dpr_Data/Plugins/x86_64/AkSoundEngine.dll`, `AkWaapiClient.dll` | Copyright Audiokinetic Inc.; distributed as part of the game's runtime under Audiokinetic's license terms |
| DOTween (compiled into the player) | `GameAssembly.dll` | Copyright Demigiant |
| Python 3.13 and the libraries of its Windows build (OpenSSL, libffi, zlib, bzip2, xz, Tcl/Tk ...) | `udpre_runtime/` | PSF License and the licenses listed in Python's `LICENSE.txt` |
| Python packages of the converter (UnityPy, texture2ddecoder, numpy, lz4, Pillow and their dependencies) | `udpre_runtime/` | each package's own license (MIT, BSD-3-Clause, MIT-CMU, MPL-2.0 ...) |
| PyInstaller bootloader | `uDPRE.exe` | GPL-2.0-or-later with the PyInstaller bootloader exception |
| libvpx 1.17.0 (re-encodes a mod's VP9 movies to VP8) and the mingw-w64 winpthreads runtime it uses; the Windows build of PyAV 19.0.2's wheel | `udpre_runtime/vpx/` | libvpx: BSD-3-Clause with Google's patent grant; winpthreads: MIT (texts in `udpre/licenses/libvpx/`, `udpre/licenses/winpthreads/`) |

Every release carries the license texts of the Python side in `udpre/licenses/`, collected by `release/make_release.py`
from the bundled packages' own metadata (`udpre/licenses/index.txt` lists package, version and license).

uDPRE contains no data of Pokémon Brilliant Diamond. Pokémon is a trademark of Nintendo, Creatures and Game Freak; uDPRE is
not affiliated with or endorsed by them, The Pokémon Company or ILCA.
