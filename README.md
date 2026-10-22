# uDPRE

Play your own copy of **Pokémon Brilliant Diamond** on Windows. Drop in your dump, run one program once, play.

uDPRE is the Windows player of the uDPR project (the game rebuilt as a native Unity 2019.4 Windows game) plus a converter
that turns **your own** game dump into the data that player reads. No Unity, no setup scripts, no game files downloaded:
everything game-related comes from the dump you made, and stays on your PC.

Mods support incoming.

## What you need

- Windows 10 or 11, 64-bit, a DirectX 11 graphics card
- About **7 GB** of free disk space where you put uDPRE
- 8 GB of RAM recommended; with less, uDPRE runs fewer conversion workers and takes longer
- Your own dump of **Pokémon Brilliant Diamond with the v1.3.0 update applied**, extracted to a folder: the folder that
  holds `romfs` (with `Data` inside). Extract the base game and the v1.3.0 update together. `exefs` is not needed.
  Shining Pearl is not supported yet.

## Play

1. Download the release and unzip it to a folder of its own.
2. Start **uDPRE.exe**.
3. Press **Browse...** and pick your dump folder (the folder with `romfs` in it - uDPRE also finds it one or two levels
   down).
4. Press **Convert**. uDPRE checks that the dump is Brilliant Diamond v1.3.0, then converts it - about a minute on a fast
   desktop, longer on a small laptop. You can close it and start it again; it continues where it stopped.
5. Press **Play**.

After that, start **Dpr.exe** (or uDPRE.exe, then Play) whenever you want to play. Your dump is only read; uDPRE never
changes it. Keep it: a later uDPRE update may need to convert again.

## Mods

uDPRE converts mods together with your dump, so Luminescent Platinum and its add-ons work on a uDPRE folder.

1. Put each **uDPRE mod pack** (a folder with a `udpre_mod.json` file in it) into the `mods` folder of your uDPRE folder.
2. **Luminescent Platinum:** the pack holds only the PC version of Luminescent's game code. Its game data comes from **your
   own download of Luminescent Platinum 2.2F for Brilliant Diamond**: extract it with 7-Zip and put the extracted folder
   (the one with `romfs` and `exefs` inside) into the `mods` folder too. If you keep it somewhere else (an emulator's mod
   folder, for example), press **Find a mod download...** and pick that folder instead. uDPRE checks every file of it
   before converting, and tells you when the download is incomplete or another version.
3. Start **uDPRE.exe**. The packs show up in the **Mods** box. Tick the ones you want, then press **Convert** (or
   **Apply** if your game is already converted).
4. Press **Play**.

- A pack that needs another one turns it on with it. For example, Easy-Mode needs Luminescent. Packs that cannot be used
  together turn each other off. The French, Castellano, Latam and Italian translations are like that; the PT-BR
  translation works with any of them.
- Changing the mods later makes again only the files the change touches. Unticking every mod gives you the unmodded game
  again.
- Luminescent brings its own game code and keeps its saves apart from the unmodded game. Its opening movie is re-encoded
  for Windows on your PC during the conversion (about 15 seconds).
- Mods take extra disk space: about 1.5 GB for Luminescent (plus your extracted download), and 2.5 GB more for
  Dechibified.
- **Patches made for other PC builds** (folders you copy over a game folder) do **not** work on a uDPRE folder. They
  were made against other game files, and copying them over breaks references between the files: pink graphics, missing
  models. Use the uDPRE pack of that mod instead.
- A console mod that only changes data (a folder with `romfs\Data` in it, no `exefs`) can be put in `mods` too. uDPRE
  converts its files on top of everything else. A console mod with `exefs` changes the game code and needs a uDPRE pack.

From a command prompt: `uDPRE.exe mods` lists the packs and the downloads they found, `uDPRE.exe locate "D:\Mods\Lumi"`
points uDPRE at a download kept elsewhere, and `uDPRE.exe convert --mods luminescent,easymode` converts with those mods
(`--mods none` turns them all off).

### Mod credits

The mods are the work of their authors; the uDPRE packs only make them run on the uDPR Windows player. Each mod's line in
the Mods box links to its page. Please endorse and support the authors there:

| Mod | Author | Page |
|---|---|---|
| Luminescent Platinum 2.2F | Team Luminescent | https://www.nexusmods.com/pokemonbdsp/mods/1 |
| Easy-Mode patch for Luminescent Platinum | Blupblurp | https://www.nexusmods.com/pokemonbdsp/mods/53 |
| Dechibified Platinum | Adomin8er | https://www.nexusmods.com/pokemonbdsp/mods/38 |
| No Balance Changes for Luminescent Platinum | ClemiNeko | https://www.nexusmods.com/pokemonbdsp/mods/48 |
| Luminescent Platinum French Translation Patch | Team French | https://www.nexusmods.com/pokemonbdsp/mods/44 |
| Luminescent Platinum Spanish Translation (Castellano, Latam) | Blupblurp | https://www.nexusmods.com/pokemonbdsp/mods/49 |
| Luminescent Platinum - IT Language | hangel87 | https://www.nexusmods.com/pokemonbdsp/mods/91 |
| Luminescent Platinum - Traducao PT-BR | Jeeeff07 | https://www.nexusmods.com/pokemonbdsp/mods/84 |

## Updates

1. Download the new release from the Releases page.
2. Unzip it **over your uDPRE folder** and let it overwrite the files.
3. Start **uDPRE.exe** once. It sees what the update changed and makes only those files again from the dump you used last
   time - usually a few seconds; an update that changes the conversion itself converts everything again (about the same
   time as the first run). Then press Play.

Start uDPRE.exe (not Dpr.exe) the first time after an update. If you moved or deleted the dump, uDPRE asks for it again.
Saves are not stored in the uDPRE folder, so they always carry over. To be told about new releases, use Watch > Custom >
Releases on the repository page.

## Saves and settings

- Saves: `%USERPROFILE%\AppData\LocalLow\DefaultCompany\Dpr\` (shared with uDPR builds of the game); with the
  Luminescent pack: `%USERPROFILE%\AppData\LocalLow\DefaultCompanyLumi\`
- Settings: `pc_settings.ini` in the same folder, and the in-game Options menu (resolution, frame rate, V-Sync, keyboard and
  controller buttons, fast-forward)

## When something goes wrong

uDPRE says what it needs in plain words (wrong game version, missing files, not enough disk space). Running it from a command
prompt shows the full log:

```
uDPRE.exe convert "D:\Dumps\BDSP"     (later: uDPRE.exe convert - uses the same dump again)
uDPRE.exe status                      (ready / update refresh needed / not converted)
```

The conversion log of the last run is in `udpre\state\`. When reporting a problem, include `udpre\state\errors.txt` (if there
is one) and the game's log: `%USERPROFILE%\AppData\LocalLow\DefaultCompany\Dpr\Player.log`.

## What is in a release

Our player (`Dpr.exe`, `GameAssembly.dll`, `Dpr_Data` without any game data), Unity's runtime, the shader programs compiled for
Direct3D 11, the converter (`uDPRE.exe`, `udpre_runtime`, `udpre`) and an empty `mods` folder. Before every release an audit
checks that no file in it holds bytes of the game: no textures, models, sounds, text or scripts of the game ship with uDPRE.
Mod packs are separate downloads. They never hold a file of the game, and the Luminescent pack holds none of
Luminescent's own files either: they come from your own Luminescent download.

## Legal

uDPRE contains no game data. You need your own legally obtained copy of Pokémon Brilliant Diamond. uDPRE is a fan project and
is not affiliated with or endorsed by Nintendo, The Pokémon Company, Game Freak, ILCA or Creatures. Pokémon is a trademark of
Nintendo, Creatures and Game Freak.

## Building

See [docs/DEVELOPING.md](docs/DEVELOPING.md).

## License

uDPRE's code: MIT (`LICENSE`). Components by others that ship in a release (Unity runtime, Wwise runtime, Python and its
packages): see `THIRD-PARTY-NOTICES.md`.
