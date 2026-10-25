# uDPRE

Play your own copy of **Pokémon Brilliant Diamond** on Windows. Drop in your dump, run one program once, play.

uDPRE is the Windows player of the uDPR project (the game rebuilt as a native Unity 2019.4 Windows game) plus a converter
that turns **your own** game dump into the data that player reads. No Unity, no setup scripts, no game files downloaded:
everything game-related comes from the dump you made, and stays on your PC.

uDPRE is the successor to uDPR (https://github.com/Manurocker95/uDPR), including the latest features, bug fixes, and mods support.

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

uDPRE updates itself and your mod packs. At every start it reads the signed mod catalogue (a few KB) and, when something
is new, downloads only what changed and installs it, then makes the game data again from your dump. A new build of uDPRE
itself is downloaded, uDPRE closes, the new files are copied in, and uDPRE starts again. Untick **Update mods
automatically** (in the Mods box) to stop the checks; with no internet uDPRE says so and you play on as before.

By hand (or without internet):

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

## Mods

uDPRE converts mods together with your dump, so Luminescent Platinum and its add-ons work on a uDPRE folder.

1. Press **Get mods...** in the Mods box: it lists every pack of the uDPRE catalogue (get, update or remove them; they
   update by themselves at every start unless you untick **Update mods automatically**). A pack folder (one with
   `udpre_mod.json`) put into `mods` by hand works too.
2. **Luminescent Platinum** also needs **your own download of Luminescent Platinum 2.2F for Brilliant Diamond** (from Team
   Luminescent): extract it with 7-Zip into `mods`, or press **Find a mod download...** if it is kept elsewhere. The pack
   holds only the PC version of its game code.
3. Tick the packs in the **Mods** box, press **Convert** (or **Apply**), then **Play**.

- Packs turn on what they need and turn off what they cannot run with. A pack with **options** shows its choices under
  its tick.
- A change of mods makes again only the files it touches; untick everything for the unmodded game. Luminescent keeps its
  saves apart. Extra disk space: about 1.5 GB for Luminescent (plus its download), 2.5 GB more for Dechibified.
- Console mods that only change data (`romfs\Data`, no `exefs`) work too. When two mods change the same file, uDPRE
  merges them value by value; **Merge conflicts...** lets you pick a side. Mods with `exefs`, and patches made for other
  PC builds, need a uDPRE pack instead.
- Console: `uDPRE.exe mods`, `uDPRE.exe locate FOLDER`, `uDPRE.exe convert --mods ID,ID` (`none` = no mods),
  `--options PACK.OPTION=CHOICE`; `uDPRE.exe online` (check), `online update`, `online get ID|all`, `online remove ID`,
  `online rollback ID`.

## Editor and randomizer (Beta)

Beta: it works, but it is new and has had less play-testing than the rest of uDPRE - if something looks wrong, turn
**Use my edits in the game** off and press **Apply** to get the game without your edits back.

**Editor & Randomizer...** (under the Mods box) opens **uDPRE Studio**: one window with a page per kind of game data
(the sidebar), a search box that finds any Pokemon, move, item, trainer or area from anywhere (Ctrl+F), and your edits
in the status bar. It edits the game data of your mod choice and randomizes it. Your edits are kept in
`edits\project.json` as a list of changes, and uDPRE applies them to the game files whenever it converts: tick **Use my
edits in the game**, then press **Apply**. Because the changes are applied again on every conversion, they keep working
when you change the mods underneath (a change to something the new mods do not have is skipped and listed on the Your
edits page).

- **Editing**: pick a record in the sortable table on the left (click a column title to sort; filters above it); records
  you changed are marked with a dot. Changes are kept when you move on - no Save button: an orange strip shows unsaved
  changes with **Keep** (Ctrl+S) and **Discard**, and **Undo my edits to this ...** in the record's header puts the
  original back.
- **Randomize**: start from a preset (Light, Balanced, Chaotic) or tick what to reroll - Pokemon (evolutions, base stats,
  types, abilities and traits, level-up and egg moves, TM compatibility), moves and items, wild Pokemon and the gifts,
  events and items on the ground, trainers, level scaling, the type chart, text and music. **Shape...** sets how new
  numbers are drawn, with a preview over the values your game has now; **Choose...** sets what a pick can land on (equal
  chances or weights). The whole run has a seed, so the same seed and settings give the same game; **Save settings** /
  **Load settings** keep a setup in a file.
- **Pages**: Pokemon (stats, types, abilities, held items, growth, moves, TMs, evolutions, and where it appears in the
  game), moves (with their battle animations and who learns them), TMs, items (with where to get them), shops, the Pickup
  table, wild areas (with the unused GBA slots), special encounters (Trophy Garden, honey trees, Great Marsh), the
  Underground, trainers (party cards, an inline member editor, Showdown text), the Battle Tower, and the type chart.
- **Advanced**: **Add a Pokemon** (a copy of a Pokemon as a new form or a new species, with its own model, icons, menu
  icon and cries - copies under the new Pokemon's names, so a mod can replace them; models or icons a mod already made
  for that number can be used instead), **Game code values** (constant values of the game code), **Mod data files** (the
  ExtraData JSON files some overhaul mods keep in `romfs\Data\ExtraData`) and **Import & export** (Pokemon, trainers and
  text as JSON files, and your edits as a LayeredFS console mod for a Switch or an emulator).
- Mods that keep data outside the game's tables work here too: the format hint file at a console mod's root, and the
  ExtraData starters, honey trees and 256-TM sets (`MonData\TMLearnset`), are read, edited and randomized.
- **Your edits** lists every change and where it is: open one, remove some, undo the last, clear them all, or save them as
  a preset file and open it again later (on another uDPRE folder too).
- New species need a player that accepts species numbers past the game's own limit: uDPRE's player from 0.4.0 on, and
  the Luminescent / Dechibified packs made for it. With an older pack's player the inserted species is skipped.

From a command prompt: `uDPRE.exe editor` opens the window, `uDPRE.exe edits list|on|off|undo|clear`,
`uDPRE.exe randomize SETTINGS.json [--seed N]`, `uDPRE.exe json export|import pokemon|trainers|text FILE`,
`uDPRE.exe export FOLDER`, and `uDPRE.exe convert --edits on|off`.

## Nuzlocke (Beta)

Beta: it works, but it is new and has had less play-testing than the rest of uDPRE - **Off** in the Nuzlocke window
gives you the normal game back at its next start.

**Nuzlocke...** (in the Challenge box) turns the game into a Nuzlocke run, with the rules of
[Nuzlocke University](https://nuzlockeuniversity.ca/nuzlocke-rules/). The game itself enforces them - you do not have to
keep count:

- **The core rules**: a Pokemon that faints is dead (it goes to a box named "Graveyard", or is released; no revive, no
  Pokemon Center brings it back); only the first wild Pokemon of each area can be caught (a ball refuses any other, and the
  message says which Pokemon used the area); every Pokemon you catch or get must be nicknamed.
- **Clauses**: Dupes Clause (by evolution line or species, the dead counting or not), Shiny Clause, Gift Clause (gifts
  count for the area, are free, or are banned), special encounters (legendaries, Spiritomb...), roaming Pokemon, honey
  trees, the Grand Underground, fishing / surfing and escapes each have their own setting.
- **Hardcore Nuzlocke** (one click): no items from the bag in battle except Poke Balls, a level cap at the next boss's
  highest level (Gym Leaders, then the last Elite Four member; taken from the game's own trainers, so Luminescent's and
  your edits' levels count), Set battle style, Pokemon over the cap sit out boss battles.
- **The optional rules** the game can check: Pokemon Center limits, team size, staying in a gym, shops without healing
  items, banned Pokemon / moves / types, Monolocke, TMs, held items, move power, STAB, super-effective moves, evolution
  stages, colours, generations, unique types, box rule, encounter order, Deathless, revives, sacrifices, continuing after a
  wipe-out, perfect IVs, master balls, the starter by Trainer ID. The dialog lists the rules no game can check
  (Completionist, no turning back, blind...).

The settings are a file (`Dpr_Data\StreamingAssets\uDPRE\nuzlocke.txt`) the game reads when it starts - no conversion is
needed, but the game must be one uDPRE converted with 0.4.0 or newer (with Luminescent or Dechibified on: their packs 1.2.5 or
newer). The run (each area's encounter, the graveyard, the level cap) is saved next to your save
(`SaveData.bin.nuzlocke`); **Your run** in the dialog shows it. A new game starts a new run; a save from before you turned
the mode on starts its run where it is. From a command prompt: `uDPRE.exe nuzlocke show`, `uDPRE.exe nuzlocke preset
nuzlocke|hardcore|off`, `uDPRE.exe nuzlocke set level_cap=hard battle_items=balls_only`, `uDPRE.exe nuzlocke run`.

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
