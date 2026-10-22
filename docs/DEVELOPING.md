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

Rule: bump `CONVERT_VERSION` in `converter/udpre/__init__.py` whenever a change alters the bytes the converter writes.
Installed folders then convert everything again.

## Making a release

Input: a Windows IL2CPP player build of the uDPR project (`Dpr.exe` + `Dpr_Data`), and a BD v1.3.0 dump on the build
machine. The dump is used for IDs, names and the audit; nothing of it is copied into the release.

```
py -3.13 -m pip install -r converter/requirements.txt -r release/requirements-build.txt
py -3.13 -I release/build_exe.py                         # -> build/dist/uDPRE (uDPRE.exe + udpre_runtime/)
py -3.13 -I release/make_release.py PLAYER_DIR DUMP/romfs/Data OUT_DIR --exe build/dist/uDPRE
```

`make_release.py` copies the player without its game data, builds the player base and the shader pack, writes
`udpre/release.json`, and runs the **audit**. The audit fails the release when any file has the bytes of a dump file (Unity's
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

## Measurements (BD v1.3.0)

- Bundles: 3.83 GiB in, 5.09 GiB out (13,774 textures decoded, 105 uncrunched, 27,061 copied, 70 shaders replaced).
- Converted folder: 6.1 GB.
- Time: 58-68 s with 15-16 workers on a 16-core desktop, about 10 minutes on one core.
- RAM: one worker peaks at 1.26 GB; `default_workers` budgets 1.5 GB of free RAM per worker.

## Open items

- Shining Pearl dumps: fingerprints and an SP player are not done.
- Mods (Luminescent Platinum and its add-ons): the converter handles Switch bundles generally, so a mod's romfs could go
  through the same path with a mod-built player. Not wired up yet.
- A compact texture option (BC7 instead of RGBA32 for colour maps) for GPUs with little video memory.
