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

- Saves: `%USERPROFILE%\AppData\LocalLow\DefaultCompany\Dpr\` (shared with uDPR builds of the game)
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
Direct3D 11, and the converter (`uDPRE.exe`, `udpre_runtime`, `udpre`). Before every release an audit checks that no file in
it holds bytes of the game: no textures, models, sounds, text or scripts of the game ship with uDPRE.

## Legal

uDPRE contains no game data. You need your own legally obtained copy of Pokémon Brilliant Diamond. uDPRE is a fan project and
is not affiliated with or endorsed by Nintendo, The Pokémon Company, Game Freak, ILCA or Creatures. Pokémon is a trademark of
Nintendo, Creatures and Game Freak.

## Building

See [docs/DEVELOPING.md](docs/DEVELOPING.md).

## License

uDPRE's code: MIT (`LICENSE`). Components by others that ship in a release (Unity runtime, Wwise runtime, Python and its
packages): see `THIRD-PARTY-NOTICES.md`.
