# Developing uDPRE

## Layout

| Path | What |
|---|---|
| `converter/udpre/` | The converter that ships as `uDPRE.exe` (Python 3.13 + UnityPy) |
| `converter/uDPRE.py` | Entry script (PyInstaller, or `py -3.13 -I converter/uDPRE.py ...` from the source tree) |
| `release/` | Tools that make a release from a Windows player build, and the developer checks |
| `release/bundles.txt` | The 13,651 bundles the converter converts (every Dpr.bin record that ships as a file) |

Pinned inputs: `converter/requirements.txt` (runtime), `release/requirements-build.txt` (release tooling).

## How a dump becomes game data

Measured on the Brilliant Diamond v1.3.0 dump against a uDPR Windows player built from it:

- **Bundles** (`bundle.py`). Switch and Windows bundles share the archive format (UnityFS 7, Unity 2019.4.27f1), the
  serialized-file version (21), every engine type hash and the script layouts the game reads. Bundle names and internal
  file names (`CAB-...`) are the same, so references between bundles need no change. The converter changes only:
  - the target-platform field of each serialized file (38 Switch, 19 StandaloneWindows64);
  - texture data (`textures.py`): ASTC and ETC are decoded level by level into RGBA32, exactly the texels the Switch GPU
    samples. DXT1/DXT5-crunched textures are unpacked level by level into plain DXT1/DXT5. Every format a PC GPU reads is
    copied byte for byte. Nothing is re-encoded, so the output is the same on every CPU;
  - Shader objects: each gets the data of our Direct3D 11 build of the same shader from `udpre/shaders.pack`, keeping its
    Switch path ID;
  - a new `.resS` per serialized file (converted texture data plus the untouched mesh streams).
  Every other object keeps its bytes. Output is LZ4 chunk-compressed like Unity's own bundles.
- **resources.assets** (`player.py`): converted like a bundle, plus one rule. StartupSettings names five boot methods
  by assembly-qualified type, three of them in assembly `AssetAssistant`. The uDPR player compiles that code into
  `Assembly-CSharp`, so those strings are rewritten.
- **globalgamemanagers**: our copy (`udpre/base/`) with the dump's ResourceManager (the `Resources.Load` table) put in.
- **Copied as they are**: `Dpr.bin`, `Movie/`, and the Wwise banks (`Audio/GeneratedSoundBanks/Switch` goes to `.../Windows`;
  the Switch-built banks play in the Windows Wwise runtime).

What the release side prepares so the dump's files fit our player (`release/make_player_base.py`):

- **Script registry.** The dump's resources.assets points into `globalgamemanagers.assets` by Switch path IDs (every
  MonoBehaviour's `m_Script`, the script-type table, and fields stored without a type tree). Our registry is renumbered: every
  MonoScript whose class the Switch registry holds takes the Switch path ID, and the rest go above the Switch range.
  MonoManager and GraphicsSettings follow the new IDs.
- **ScriptMapper** (Shader.Find's table) is pointed at the Switch resources.assets shaders by name.

## Updates (players unzip a new release over their folder)

uDPRE has no auto-update. At the end of each conversion `udpre/state/config.json` records a fingerprint: the hash of
`udpre/base/globalgamemanagers` and a digest per container of `udpre/shaders.pack`. At every start `install.status()`
compares it with the files now in the folder:

| Change in the release | What uDPRE does at the next start |
|---|---|
| Player only (new `GameAssembly.dll`, registry, base globalgamemanagers) | remakes resources.assets + globalgamemanagers (seconds) |
| A shader in the pack | also converts again the bundles whose shaders changed (the pack has 8 bundle containers) |
| `CONVERT_VERSION` bumped | converts every bundle again (a new `done_v<N>.log`) |

The window starts that refresh on its own with the dump of the last conversion, so after an update the player presses
only Play. Rule: bump `CONVERT_VERSION` in `converter/udpre/__init__.py` whenever a change alters the bytes the converter
writes for bundles.

## Making a release

Input: a Windows IL2CPP player build of the uDPR project (`Dpr.exe` + `Dpr_Data`), and a BD v1.3.0 dump on the build
machine. The dump is used for IDs, names and the audit; nothing of it is copied into the release.

```
py -3.13 -m pip install -r converter/requirements.txt -r release/requirements-build.txt
py -3.13 -I release/build_exe.py                         # -> build/dist/uDPRE (uDPRE.exe + udpre_runtime/)
py -3.13 -I release/make_release.py PLAYER_DIR DUMP/romfs/Data OUT_DIR --base-version 1.2.3 --exe build/dist/uDPRE
```

`make_release.py` copies the player without its game data, builds the player base and the shader pack, copies
`LICENSE`, `THIRD-PARTY-NOTICES.md`, `README.md` and the license texts of every package in the converter runtime
(`udpre/licenses/`), writes `udpre/release.json` (with `base_version` = the version of the uDPR game build the player is;
the window shows it as "game base v..."), and runs the **audit**. The audit fails the release when any file has the bytes of a dump file (Unity's
own `mscorlib.dll-resources.dat` is the one allowed match), or when a serialized file of ours holds textures, meshes,
sounds, text, scripts' data or other game objects.

`release/make_bundle_list.py` rebuilds `bundles.txt` from a TSV dump of the catalog. It is needed only if the catalog
changes.

## Checks before a release

1. Convert the dump into the release folder: `OUT_DIR/uDPRE.exe convert DUMP` (about 60 s with 16 workers).
2. `release/verify_bundle.py DUMP/romfs/Data/StreamingAssets/AssetAssistant OUT_DIR/Dpr_Data/StreamingAssets/AssetAssistant
   --list release/bundles.txt`: every object of every bundle against its Switch source (decoded textures equal, mesh
   streams equal, every other object byte-identical).
3. `release/compare_trees.py` against a second conversion (other worker count or machine): 0 differing files.
4. In game:
   - a **new game from no save** (language select, intro, the first room);
   - a field save (city);
   - a wild battle;
   - and whatever the release changed.
   Player.log should hold no errors beyond the expected missing-script line for Wwise's Switch settings object.

## Publishing

`py -3.13 -I release/zip_release.py OUT_DIR` makes `uDPRE-<version>-win64.zip` from a fresh `make_release.py` output (it
refuses a folder that holds converted data or failed its audit). Attach the zip to a GitHub Release with a short changelog;
players unzip it over their folder (see Updates above).

## Measurements (BD v1.3.0)

- Bundles: 3.83 GiB in, 5.09 GiB out (13,774 textures decoded, 105 uncrunched, 27,061 copied, 70 shaders replaced).
- Converted folder: 6.1 GB.
- Time: 58-68 s with 15-16 workers on a 16-core desktop, about 10 minutes on one core.
- RAM: one worker peaks at 1.26 GB; `default_workers` budgets 1.5 GB of free RAM per worker.

## Mod packs

**Why a PC patch cannot go on a uDPRE folder.** A converted bundle keeps its Switch path IDs; bundles of a Windows build of
the project carry the IDs Unity gave them. Same CAB names, different object IDs: every reference from one set into the
other dangles. Measured on `Dpr/shaders`: 63 of 63 shaders have other IDs. Copying a PC Luminescent patch over a uDPRE folder
leaves 31,623 of the 45,169 material shader references pointing at nothing (`release/check_refs.py --shaders`), and the
game draws those materials pink. So mods go through the converter in Switch form, with the dump.

**A pack** is a folder in `mods/` with `udpre_mod.json` (format 1, read by `converter/udpre/mods.py`):

| key | meaning |
|---|---|
| `id`, `name`, `version`, `description` | shown in the window; `id` is what `--mods` and the other packs name |
| `order` | layer position, higher = on top (Luminescent 10, Easy-Mode 20, Dechibified 30, No Balance 40, FR / Castellano / Latam / IT 50, PT-BR 60) |
| `requires`, `conflicts` | ids; the window turns required packs on and conflicting ones off |
| `sources` | downloads the PLAYER brings (a mod we do not redistribute): `{ID: {"name", "where", "list", "key"}}`; `list` = `sources/ID.json` = `{romfs path: [size, sha1]}` of every file the pack takes from it, `key` = the path that identifies it |
| `layers` | `{"romfs": DIR}` = Switch files with their `romfs/Data` paths, converted like the dump; `{"source": ID}` = the listed files of the player's own download; `{"files": DIR}` = Windows files with their `Dpr_Data` paths, copied (hard-linked when the drive allows). Optional `when` / `unless` (ids) choose variants (the Dechibified version of a translation ...); later layers of a pack win. Optional `dump` = `{romfs path: dump path}`: a mod file byte-identical to another dump file is taken from the dump instead of shipped. Optional `copy` = `{romfs path: romfs path}`: a file that is a copy of another one of the stack below (a translation's opening = Luminescent's) |
| `player` | folder of a player profile: `profile.json` (`id`, `files`), the code files at their root-relative paths (`GameAssembly.dll`, `global-metadata.dat`, `app.info`, the renumbered `globalgamemanagers.assets`), `udpre/base/globalgamemanagers`, `udpre/shaders.pack` |

**The Luminescent pack ships none of Luminescent's files.** It holds our port of Lumi's game code (the console mod's
`exefs` patches the Switch executable, which a PC player does not have), its shader pack and registry, and the list of the
3,446 files of Lumi 2.2F (BD) it uses. The player extracts their own Lumi download into `mods/` (any depth) or points at it
(window: "Find a mod download...", console: `locate FOLDER`, kept in the config as `sources`). `mods.discover` finds it by
the key file (`Dpr.bin`, size + sha1), claims that folder (so its `exefs` is not refused as a code mod), and
`install.verify_sources` checks every listed file's sha1 before converting (cached by path + size + time in
`state/source_hashes.json`). Bundle keys of source files are their sha1, so moving the download converts nothing again.
Converted from the player's download, the 3,135 Lumi bundles are byte-identical to the ones converted from the files
themselves.

**Movies** (`movies.py`): the Windows player decodes VP8 only. A movie a mod brings is copied when VP8 and re-encoded to
VP8 otherwise: `webm.py` reads the WebM (one video track, no lacing), `vpx.py` decodes VP9 and encodes VP8 with libvpx 1.17.0
through ctypes (3 Mbit/s, quantizer 4..42, no alt-ref, keyframe at most every 120 frames, video only, each frame keeps its
timestamp: the settings of the uDPR Windows builds), `webm.py` writes SeekHead / Info / Tracks / Clusters / Cues like the
game's own movies. Lumi's VP9 opening takes ~12 s, with the same PSNR against the VP9 source as our PC builds' FFmpeg copy
(35-38.5 dB); ffprobe reads the result without a warning. Results are cached in `state/movies/` by the source's sha1.
libvpx ships as two DLLs taken from PyAV's wheel at build time (`release/build_exe.py`, sha256-pinned); PyAV / FFmpeg do not
ship (that FFmpeg build links the GPL encoders x264 / x265).

**What the converter does with packs** (`install.run`, `mods.Stack`): every `Dpr_Data` path gets the top-most source of the
stack dump -> enabled packs' active layers. Bundles are converted from that source (strict whole-stream proof only for the
dump: mod tools leave replaced texture data in a `.resS` with nothing pointing at it), Windows files are copied,
`resources.assets` / `.resS` / the `ResourceManager` of `globalgamemanagers` / `Dpr.bin` / audio / movies come from their
top-most layer. The top-most pack with a player puts its code files over ours; ours wait in `udpre/players/vanilla` (by the
hashes in `udpre/player_files.json`) and come back when no such pack is on. The done log keeps each bundle's source key (pack
id + version + size + time, or `dump`): changing the mods converts only the bundles whose source changed and removes the
ones no layer has any more; `state/copied.json` does the same for copied files.

Two Luminescent quirks the converter accepts, both proven safe: an AssetBundle object longer than its type tree (72 bytes,
`chapter111`; read leniently, never written) and meshes ending in 4 zero bytes the type tree does not describe (read when
the object equals the re-written tree + at most 16 zero bytes; the tail is kept). A mod bundle that embeds a game shader the
pack was not built for gets that shader's build from `Dpr/shaders` (`ShaderPack.find`).

**Making a pack** (build machine): `release/make_pack.py SPEC.json OUT_DIR --dump DUMP/romfs/Data [--census ...]`. The spec
names each layer's sources (folders with include / exclude globs, or single files) and, for a code mod, the Windows player
built with it (profile = its code files + `make_player_base.py` + `make_shaderpack.py --overlay <the mod's romfs/Data>`).
Layer files are hard links. A romfs file byte-identical to the dump's at the same path is left out, and one identical to
another dump file goes into the `dump` map. A `source` layer writes only the file list. The audit fails on any file with the
bytes of a dump file or of a `--forbid DIR` folder (every pack is built with `--forbid <the Lumi 2.2F download>`), or a
player file naming a build-machine folder. Our fixes to a mod are applied to its Switch files (typetree edits, RGBA32 texture writes),
never by taking a bundle out of a Windows build. Windows bundles are allowed only where no Switch form exists (the
Dechibified wardrobe), with every shader reference already rebased to the Switch IDs.

**Checks for a pack:**
1. convert the dump + the pack into a test folder;
2. `release/verify_bundle.py MOD_ROMFS_AA OUT_AA --list <the pack's bundles>`: every object against its Switch source;
3. `release/check_refs.py OUT_AA --full <the pack's bundles>`: every material shader reference in the whole folder resolves,
   and every reference of the pack's bundles. Run the same on a hard-linked tree of the Switch files (dump + the pack's romfs):
   the dangling references must be the same set (the mod's own);
4. switch mods on and off (`convert --mods ...`, `--mods none`): only the touched files are redone, and the no-mod state is
   the plain conversion again (`verify_bundle.py` over every bundle against the dump, player files = the release's).

Measured (Luminescent 2.2F): 14,685 bundles; 3,135 Luminescent bundles verify object by object; 45,169 material shader
references, 0 dangling; 2,230 dangling references in Luminescent's bundles, the same set on the Switch files (the mod's own:
e.g. the corrupt `pm0487_12_00` it ships, left out of the pack so the dump's file serves the record).

## Open items

- Shining Pearl dumps: fingerprints and an SP player are not done.
- A compact texture option (BC7 instead of RGBA32 for colour maps) for GPUs with little video memory.
- Auto-update (a signed manifest on the Releases page, checked at start) - not planned for now.
