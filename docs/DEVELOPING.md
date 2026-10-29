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

## Updates (a new release over the player's folder)

A new release lands over the folder either from the player unzipping it or from uDPRE's own update (next section). At
the end of each conversion `udpre/state/config.json` records a fingerprint: the hash of
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

## Online packs and updates (`converter/udpre/online.py`, `online_ui.py`)

The packs and uDPRE's own zip are hosted files (tags `catalog`, `parts`, `udpre`) that players reach through the relay:
`GET <relay>/v1/file/<tag>/<name>` answers with a short-lived download link (302); downloads resume with HTTP Range. The
relay address is `udpre/release.json` "relay" (`make_release.py --relay URL`);
`udpre/config.json` "online_relay" or `UDPRE_RELAY` override it for tests.

- **Catalogue** (`catalog/catalog.json`): `{"format", "index": <JSON text>, "sig"}`, Ed25519 over the index text
  (`converter/udpre/ed25519.py`, pure Python, checked against RFC 8032). `online.PUBLIC_KEY` is the public half; the
  private half never leaves the build machine.
  A bad signature = nothing is downloaded. The index lists each pack's parts with size + SHA-256, and uDPRE's build
  (`made` time, compared with the running release's).
- **Parts**: per pack, one per top-level folder of 4 MiB or more (split by `crc32(path) % n` past 600 MiB), and `meta` for
  the rest; the first matching rule wins (`online.part_of`). Each part = a deterministic `.tar.xz` named
  `<id>-<part>-<tree[:16]>`, where tree = SHA-256 over sorted `path<TAB>size<TAB>sha256` lines. An unchanged part keeps its
  name, so it is neither uploaded nor downloaded again.
- **Install / update** (`online.install_item`): the new folder is built beside the old (`<pack>.udpre_new`): kept parts are
  hard-linked from the old folder, new parts downloaded (verified by SHA-256, resumable `.part` files in
  `udpre/state/online/downloads`) and unpacked with tarfile's `data` filter; every new part's tree must match the
  catalogue; then the old folder moves to `udpre/state/online/previous/<id>` (one rollback) and the new one takes its
  place. File hashes are cached by size + mtime + file id (`udpre/state/online/hashes.json`), so a check of an installed
  pack reads only changed files; the file id matters because parts unpack with mtime 0 (a changed file of the same size
  must not keep its old hash), and an install / rollback moves a folder's entries along with the folder.
- **The window**: at start (unless "Update mods automatically" is off: config `online_auto`) the check runs before the
  start-up refresh; a new uDPRE build comes first (frozen exe only: unpacked to `udpre/state/online/self`, then
  `apply_update.cmd` waits for uDPRE to exit, robocopies the new files in and starts uDPRE again), then updates of
  installed packs, then the usual refresh/convert of the changed files. No internet = a note, play on.
- **Downloads packs take files from** (`sources`, e.g. Luminescent 2.2F): the client fetches them only when the catalogue
  lists them and no copy is found.

Publishing (build machine) packs every changed part, signs the catalogue, and uploads only the files the host lacks, the
catalogue last. Checks (developer tools of the build machine): the real client against the relay's own code and a test
double of the host: signature, install = byte-identical, part-only update, resume, damaged download, rollback, linked
folder; screenshots of the window.

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

**A pack** is a folder in `mods/` with `udpre_mod.json` (format 1 or 2, read by `converter/udpre/mods.py`; format 2 = a pack
that uses `options` or `min_versions`, which uDPRE 0.2.0 refuses instead of misreading):

| key | meaning |
|---|---|
| `id`, `name`, `version`, `description` | shown in the window; `id` is what `--mods` and the other packs name |
| `order` | layer position, higher = on top (Luminescent 10, Shiny Icons 15, Heal Animation 16, Increased Shiny Odds 17, Easy-Mode 20, Dechibified 30, No Balance 40, FR / Castellano / Latam / IT 50, Darker UI 55, PT-BR 60) |
| `requires`, `conflicts` | ids; the window turns required packs on and conflicting ones off |
| `options` (format 2) | sub-options under the pack's own tick: `[{"id", "name", "default", "choices": [{"id", "name"}]}]`, one exclusive pick per option (e.g. a mod released in several variants). The window shows them as radio buttons under a ticked pack; the console takes `--options PACK.OPTION=CHOICE`. Picks are kept in the config as `options` = `{pack: {option: choice}}` and stay remembered while the pack is off; an option never picked uses its default. A different pick changes the pack's active layers, so only the files of those layers are made again |
| `min_versions` (format 2) | `{pack id: version}`: while that pack is on, it must be at least this version (a pack whose file only a newer player of another pack reads) |
| `sources` | downloads the PLAYER brings (a mod we do not redistribute): `{ID: {"name", "where", "list", "key"}}`; `list` = `sources/ID.json` = `{romfs path: [size, sha1]}` of every file the pack takes from it, `key` = the path that identifies it |
| `layers` | `{"romfs": DIR}` = Switch files with their `romfs/Data` paths, converted like the dump; `{"source": ID}` = the listed files of the player's own download; `{"files": DIR}` = Windows files with their `Dpr_Data` paths, copied (hard-linked when the drive allows). Optional `when` / `unless` (ids) choose variants (the Dechibified version of a translation ...); optional `option` = `{option id: choice id or [choice ids]}` (format 2) makes a layer count only while that choice is picked; later layers of a pack win. Optional `dump` = `{romfs path: dump path}`: a mod file byte-identical to another dump file is taken from the dump instead of shipped. Optional `copy` = `{romfs path: romfs path}`: a file that is a copy of another one of the stack below (a translation's opening = Luminescent's) |
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

## Merging console mods (`converter/udpre/merge.py`)

`mods.Stack` keeps every layer's source of a path (`all_sources`). When a console mod (a folder without a manifest) brings a
file another mod also brings, `merge.apply` writes a merged Switch file to `udpre/state/merged/<path>` and points the stack
at it (packs among themselves keep their own `when` / `unless` variants, which are made for each combination):

- base = the dump's file, lower = what the packs (or the console mods under it) made, upper = the console mod's file;
- Unity files (bundles, resources.assets, globalgamemanagers): per object (path id) - changed on one side only = taken from
  that side; changed on both = a three-way merge of the type trees (dicts by key, lists element by element or by appended
  rows), a value both changed differently = a conflict, the upper side wins unless `config.json` `merge_choices` says
  `below` for that object; textures / meshes / sounds / fonts / shaders are decided whole; files without type trees (player
  files) only whole objects; when one side added or removed objects its file gives the structure, when both did one file
  is used whole (a `whole file` conflict row: upper unless `merge_choices` says `below`);
- `Dpr.bin` per bundle record (`record <name>` picks); other files whole between two mods' files (`whole file` pick; the
  first mod over the dump just replaces it);
- a console mod file that does not load on its own is dropped (the lower layer's file is used); the converter does the same
  for a damaged mod bundle that is not shared (`install.run`, recorded under the mod file's key).
- **references**: a merged bundle must not make a reference dangle that does not dangle with the lower layer's files (a
  console mod made for the unmodded game, merged over a mod that rebuilt a model, would). Every merged bundle and every
  bundle depending on one (the catalog's dependency lists) is checked against its dependencies; a new dangling reference
  sends the merged dependency that lost the object (and a merged file making it) back to the lower layer's file, until none
  is left (`_reference_pass`, cached in `merged/refs.json`).
The report (`merged/report.json`: per file the mods, conflicts, notes, `reverted`) feeds the window's **Merge conflicts...**
list. Measured: Sky-Battlen't 3.0 (a vanilla console mod) over Luminescent + 7 add-ons: 1,721 shared files; first merge 31 s;
1,698 merged per object / field, 20 structure fallbacks, 3 damaged mod files left out; the reference pass sends 24 back
(the Mewtwo, Steelix, Wailord and Giratina models Luminescent rebuilt). Dangling references in those 1,719 bundles: Luminescent alone
182, the console mod's files taken whole 1,093, merged 201 (the extra = the console mod's own AssetBundle objects the
checker cannot read, also in "whole"); material shader references 0 dangling.

## Editor & Randomizer (`converter/udpre/edit/`)

| Module | What |
|---|---|
| `gamefiles.py` | the stack's Switch files opened for editing (UnityPy type trees by m_Name; raw files; new files) |
| `game.py` | the tables with names and keys (personal rows, learnsets, evolutions, TMs, trainers, encounters, UG, ...) |
| `text.py` | message sheets: label text <-> words, engine strWidth from the game font atlas |
| `project.py` | the edit project = ordered operations, replay, keys, `describe` |
| `build.py` | the build = the project replayed on the current stack -> `udpre/state/editor/{romfs,player}` |
| `session.py` | the editor's working state (stack + project + game data with the project applied) |
| `randomizer.py`, `analyzer.py`, `distributions.py` | every randomizer option, defaults from the data, distributions |
| `metadata.py` | type chart + field default value edits of the player's global-metadata.dat |
| `jsonconv.py`, `showdown.py` | JSON converter, Showdown team text |
| `inserter.py`, `assets.py` | Pokemon Inserter; bundle copies with new CAB names + catalog records |
| `export.py` | the edits as a console mod (LayeredFS) |
| `formats/` | `nrbf.py` (Dpr.bin = .NET BinaryFormatter), `wwise.py` (sound banks v135), `il2cppmeta.py` (metadata v24) |
| `ui/` | uDPRE Studio, the window (tkinter): `shell.py`, `page.py`, `kit.py`, `theme.py`, `widgets.py`, `pages/` |

**The layer.** `install.run` (when `config.json` `edits_on`) replays `edits/project.json` on the stack it is about to
convert and adds the files that came out different as the top-most layer (order 100000, above console mods); the edited
player metadata goes in as a player override (`Setup.overrides`, `expected_player`, `apply_player`). The fingerprint holds
the project's digest (`edits`), so `status()` asks for Apply after an edit. A file is rewritten only when its bytes change,
so an unchanged project converts nothing again.

**Operations** address rows by keys that mean the same in every mod's files (`[monsno, form]` for personal / learnset /
evolution rows, `wazaNo`, item `no`, `zoneID`, TrainerPoke `ID` ...); a key the current files do not have is skipped and
reported (`state/editor/report.txt`, the Your edits page). Randomize = one operation with its seed and settings: the same game
state + settings + seed always give the same bytes.

**Game facts the editor relies on** (BDSP v1.3.0 code, the same in Luminescent): names are read by position in their sheet
(`MessageManager.GetNameMessage(file, int)`); a TM's compatibility bit = its item's `group_id - 1`; Luminescent's wild slots
hold `species | form << 16`; an empty party slot is Seal -1 / Sex 3 / Ball 28 in the dump and all 0 in Luminescent; the type
chart = the 18 InitializeArray blobs of `Pml.Battle.TypeAffinity` in global-metadata (found through its static
constructor's metadata usage list, so an edited chart maps the same way); a form row = `form_index + form - 1`, so an
inserted row moves every later row; `ss_zkn_form` is read by personal row, height / weight by label, `dp_pokedex_*` by
species (dump) or personal row (Luminescent); cry events are named from the numbers (`Play_PV_Btl_{dex}_{form}_..`), so an
inserted Pokemon gets copies of the source's events, whose sounds play new media ids (streamed `<id>.wem` copies in
`Audio/GeneratedSoundBanks/Switch`, one new id per source media); the menu icon is a sprite of the TextureMass SpriteAtlas
asked by name (`UIManager.GetAtlasSprite(TEXTUREMASS, PokemonIcon.AssetName)`), so the copy is a new sprite + render-data
entry on its own RGBA32 texture cut from the atlas page (the atlas's render data map is not sorted: appended). A mod's
256-TM sets are `ExtraData/MonData/TMLearnset/monsno_<dex>_formno_<form>.json` {set01..set08}: the set is 256 long when
the first species has one, machine1..4 keep the low 128 bits, a bit past 128 on a Pokemon without one makes the file (op
`extradata`); a Pokemon with no TamagoWazaTable row gets one in personal order (op `eggmoves`). A new species is accepted
only by a player with the type `Pml.MonsLimit` (species limits read from the data).

**Checks** (developer tools of the build machine): JSON export -> import = 0 changes on the dump and on Luminescent; the
inserter's personal-table invariants and catalog boot rule; every new bundle converts; an end-to-end conversion with edits
on: `verify_bundle.py` of the edited bundles against the editor layer, `check_refs.py --full` over them, `status` ready; edits
off returns the folder to its plain conversion.

**uDPRE Studio (`ui/`).** One window, `shell.EditorApp` (`window.py` re-exports it) = a sidebar of pages (`NAV`,
`PAGES` -> `ui/pages/<module>.py`, imported by name; PyInstaller cannot follow that, so `shell._frozen_imports()` names
every page module - a new page goes there too), a search over Pokemon / moves / items / trainers / areas, and a status
bar with your edits. `page.RecordPage` = a sortable `kit.DataTable` of records + the record on the right; subclasses give
`columns`, `rows()`, `build()`, `show()`, `collect()` (set operations) and `op_key(op)` (edited markers, "Undo my edits
to this ..."). Changes are kept when the record / page / window is left (snapshot of the tracked widgets vs the shown
record); no Save buttons, no modal editors. Only `Studio.*` ttk styles (`theme.setup`): the main uDPRE window shares
the style database. The Randomize page keeps `randomizer.OPTIONS` ids and the settings file, in its own wording
(`pages/randomize.py` TEXT, CATS, PRESETS); its shape preview samples `distributions.Numeric` over the values
`analyzer.default_settings(..., observed=)` reports. Its settings are kept when the page is left (project meta
`randomizer`, `randomizer_seed`, and `randomizer_alt` = each pool / shape's other mode where it differs from the
defaults). Randomize replaces the randomization the edits hold, at its place (`Session.replace`: edits made after it
stay on top); a note under the seed says which seed the edits hold. Checks (developer tools of the build machine): every page saved on
the dump and on Luminescent (the operations it makes, the data changes, edited markers, undo), the Randomize page's
settings, JSON import / export and the console-mod export, and screenshots of any page / record / view.

## Nuzlocke mode (`converter/udpre/nuzlocke.py`, `nuzlocke_ui.py`)

The rules live in the **player** (the uDPR project's `Nuzlocke.*` code + hooks in the battle client, the
EXP calculator, the register window, the box, the bag, shops, the Pokemon Center command, door warps, saves). uDPRE only
writes the settings and reads the run:

- `Dpr_Data/StreamingAssets/uDPRE/nuzlocke.txt` = `key=value` lines (`nuzlocke.SETTINGS` = every key, its values, default
  and rule; the player's `NzConfig` reads the same keys once at start; no file / `enabled=0` = the shipped game). The
  converter never removes it (it removes only files it copied).
- The run: `SaveData.bin.nuzlocke` / `Backup.bin.nuzlocke` next to the saves (LocalLow/<app.info company>/<product>/nn/
  save/<app>/<user>/), UTF-8 lines split by TAB (`NZLK 1`, `save <crc32> <length>` of the paired save, `state`, `info`,
  `area`, `death`, `owned`, `pc`, `order`, `nick`, `msg`, `end <crc32 of the lines before>`). A file whose `save` line does
  not match its save is another save's: the player starts a new run.
- Player support: the player's `global-metadata.dat` names the type `NzConfig` (uDPRE 0.4.0's player and the 1.2.5 packs'
  players on).
- Areas = the zone's `PokePlaceName` (MapInfo, at run time); level caps = the first battle of each Gym Leader (trainer ids
  175 240 242 241 243 179 244 245, each tied to its badge flag) and the last Elite Four member (188) read from the loaded
  TrainerTable: the lowest ace among the leaders whose badge is missing = vanilla 14 22 30 30 36 39 42 49 / 63, Luminescent
  2.2F 16 26 33 39 44 53 56 62 / 75. A dead Pokemon carries `0x4E5A0001` in `CoreParam.palma` (a field the game never
  uses).

Check (a developer tool of the build machine): a harness compiled against the player's assembly runs the player's own `NzConfig.Apply` / `NzRun.BuildSaveFile` / `ApplyLoaded` outside Unity: every key of every preset and of
a set that changes every key reaches the right player field; the run file pairs, restores, and refuses another save or a
changed byte; `nuzlocke.parse_run` reads the same file.

## Wild Pokemon you can see (`converter/udpre/roaming.py`)

The **player** does it (the uDPR project's `PcRoaming`: the Underground's symbol encounters on the overworld, from the
area's own encounter table); uDPRE only writes the setting:

- `pc_settings.ini` (LocalLow/<app.info company>/<product>/, the file of the LAN keys) `roaming=0|1|2` (0 = the shipped
  game, 1 = with the random encounters, 2 = instead of them) and `roaming_count=1..8` (default 4); the player reads them
  once at start, the first line of a key wins. `lan.write_keys` writes them (every other line kept), `lan.ini_values` reads.
- Player support: the player's `global-metadata.dat` names the type `PcRoaming` (uDPRE 0.5.2's players on).

## Open items

- Shining Pearl dumps: fingerprints and an SP player are not done.
- A compact texture option (BC7 instead of RGBA32 for colour maps) for GPUs with little video memory.
