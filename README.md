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
- Controllers: Xbox and most PC pads work as they are. **DualSense, DualShock 4, Switch Pro Controller and Joy-Cons** work
  directly over USB or Bluetooth (Beta), without Steam Input or DS4Windows, with rumble and with motion for the Pokedex's sound
  effects. Buttons go by position, as on the Switch (a DualSense's Circle is A, Cross is B); the on-screen prompts keep the
  Switch's letters. `pad_native=0` in pc_settings.ini turns this off, `pad_motion=0` / `pad_rumble=0` just those two.
- Typing (your name, nicknames, box names, codes): in the game's own window - type on the keyboard (your IME works for
  Japanese, Korean and Chinese), or pick characters from the on-screen grid with a controller (A type, B delete, Y space,
  L / R page, + OK) or the mouse. `swkbd=dialog` in pc_settings.ini brings back the old separate dialog window.

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

**Ultrawide and 16:10 screens:** the game is laid out for 16:9. The **True Ultrawide UI** pack lays it out for your screen
instead: on 21:9 and 32:9 the menus, battle screens, Pokedex, Town Map, Poketch, Bag, contests, cutscenes and battle-start
effects use the whole width; on 16:10 (1920x1200, 2560x1600, Steam Deck) they use the whole height and the 3D view keeps the
full 16:9 width. Under its tick pick the **Screen shape**: **This PC's screen** (the shape of your main monitor when you
convert - convert again after changing monitors) or a listed shape (`--options widescreen.screen=3440x1440`). It works
under every other pack. Play at a resolution of that shape (Options > Resolution); a window of another shape still shows
the whole game, with empty space at the sides or at the top and bottom.

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

## Wild Pokemon you can see (Beta)

The overworld's wild Pokemon walk around you, the way the Grand Underground's do: walk into one to battle it. Pick it in the
**Wild Pokemon you can see** box of the uDPRE window:

- **Off** - as the game: random encounters in grass, caves and water (the default).
- **On, and the random encounters too** - both.
- **On, instead of the random encounters** - walking through grass or a cave starts no battle by itself; you choose which
  Pokemon to fight. The Poke Radar's shaking grass, a wandering legendary and the double battles of a partner travelling
  with you stay as they are.

They come from the area's own encounter table (the same species, levels and time of day - with Luminescent, its own
encounter slots; a shiny shows as one), on land and, while you surf, on the water. Touching one plays the Underground's
encounter. They appear and go only where the camera does not show them, and the others stay where they were over a battle.
A Repel keeps the random encounters away, not these: you see them and can walk around them, as in the Grand Underground.
With a LAN Team Up partner close by, walking into one starts your two-against-two battle, as a random encounter does.
**In a LAN world** (overworld on) every player on the same map sees the same wild Pokemon: the same species, level and shininess,
walking the same paths. The first player to touch one battles it; the others see it stand still until that battle ends. Caught,
defeated or fled, it is gone for everyone and a new one comes after a while; run away and it walks on, anyone may battle it.
Each player sees those of the ground on foot and those of the water while surfing. One that comes while you look at its spot
grows in after a few seconds, and one whose time is up shrinks away.
**Chase you** sets how many of them notice you and run at you (none, a few - the default, half, all; `roaming_chase` =
0 .. 100 percent); the others only wander. After a battle the ones around you leave you a few seconds to walk away.
**At once** sets how many walk around you (1 - 8, default 4). The setting is in `pc_settings.ini` (`roaming=0|1|2`,
`roaming_count=1..8`); the game reads it when it starts - no conversion is needed, but the game must come with uDPRE 0.5.2
or newer. The unmodded game and Luminescent keep their settings apart; what you choose here goes with the folder, so a
conversion that switches it between them takes your choice along (the LAN settings too). From a command prompt:
`uDPRE.exe roaming show`, `uDPRE.exe roaming 0|1|2`, `uDPRE.exe roaming count N`, `uDPRE.exe roaming chase N`.

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

## LAN play (Beta)

Everything the Switch plays over local wireless, played with other uDPRE players on your network or, with one reachable player,
over the internet (see **Over the internet** below): the **Union Room** (greetings, trades, battles, records, Ball Capsules), the
**Colosseum** (single, double and four-player multi battles), the **Grand Underground** (up to 8 players: digging together, Secret
Bases) and **Super Contest Shows**. In the game, pick local communication (Local Play) where the game offers it, as on the Switch.
Nintendo's own online features (GTS, Wonder Trade, online battles, Mystery Gift over the internet) still need Nintendo's servers
and stay offline.

**Overworld (Beta):** players of the same game also see each other walking around Sinnoh - in the same city or on the same
route, in their own outfits, with their names, cycling, surfing and with their following Pokemon. Everyone keeps their own game:
your save, story and world are yours. Walk up to another player and press A:

- **Battle**: a Single or Double link battle right there; both of you are back where you stood afterwards. With a Team Up
  partner nearby, **Multi Battle (2 vs 2)** challenges the other player's team: you and your partner against them and theirs,
  each player choosing and commanding their own Pokemon (the Colosseum's Multi rules). Only the two leaders are asked; the
  partners join by themselves (if one of them can't right now, it is called off for all four).
- **Trade**: the Union Room's trade, anywhere. Both games save it as one step: a crash or a lost link mid-trade never copies or
  loses a Pokemon (an unfinished trade is settled the next time you two meet).
- **Team Up**: walk up to your friend, press A, pick **Team Up**, and your friend accepts. While you are on the same map and
  within about 20 m of each other, a wild Pokemon or an ordinary Trainer that one of you runs into becomes a battle
  for both of you (two against two) if the other one wants it. The one who ran into it sees "Waiting for ... to join" (or
  picks **Battle alone**); the other keeps playing and gets a note at the bottom of the screen for 5 seconds ("... ran into
  a wild Snover! Join and a wild Rattata comes at you.  RT: join (5)" - the second wild Pokemon is only there if you join)
  - **RT** on a controller or **P** on the keyboard joins. No press in time, or busy in a battle of
  their own, too far away or on another map, and the battle goes on alone. Each of
  you gains experience for your own Pokemon and the full prize money; a catch
  belongs to whoever threw the ball, and both of you register what you saw. While both wild Pokemon are up, a Poke Ball asks
  which one to throw at; catching one does not end the battle while the other is still up, so either of you can catch the
  second too (two catches = two Pokedex screens afterwards). A Trainer you beat together counts as beaten for both of you
  (Team Galactic stays part of each player's own story);
  one the joining player had already beaten pays them no prize money (experience as usual). Gym
  Leaders, the Elite Four, the Champion, rivals, a Trainer with a single Pokemon, legendary Pokemon (the roaming ones too), and
  fishing, honey, Safari and Poke Radar encounters stay solo. In a Nuzlocke run each game keeps its own
  run's rules for its own Pokemon (fainting, level cap, battle items, clauses); a team wild battle uses up the area's encounter
  for both of you, either of the two wild Pokemon may be the one you catch, and once you have caught yours the other one is
  your partner's to catch. The Poke Balls and medicine your partner uses come out of their own bag, and their ball is thrown
  by their own trainer on both screens.
- **Trainer Card**, **Emote** and **Say** (preset phrases, shown over your head to everyone in the map; on the field the
  **T** key opens them too, `chat_key=` in pc_settings.ini changes the key; "Type a message..." at the top opens the keyboard).
- **Chat box** (bottom-left): a small Chat button with a count of unread lines; new lines pop up above it. **Enter** (or
  **LT**) opens it and you keep walking while it is open. Enter types a line to every player in the world, whatever map they
  are in (Enter sends, Esc cancels the line); with a controller, **LB** opens the keyboard (the left stick or the d-pad moves,
  A types, + sends, - cancels). A line also shows over your head to those near you. Scroll with the mouse wheel,
  PageUp / PageDown or the right stick; Esc or LT closes it. LT and RT do not talk to people while you play in a LAN world.
- **Player list** (top-left): everyone in your world and where they are (the route or town; "here" = the same place as you,
  "nearby" = the same map, "busy" = in a battle, a contest or a room), then the games nearby that cannot join you, greyed,
  with the reason. **P** (or **RT**) hides and shows the player list and the chat box together.
  `chat_open_key=` / `chat_list_key=` in pc_settings.ini change the keys. There is no word filter: play with people you know.
- Names over other players are on dark plates (your Team Up partner's dot is gold). A player in a battle (wild ones too)
  stays where they stood, with a battle balloon over their head; the player list says "in a battle".
- **World news**: a small pop-up at the top right when anyone in the world catches, hatches or evolves a Pokemon or beats a
  Trainer, and a **Log** tab in the chat box that keeps every line (wild Pokemon defeated too). **G** on the keyboard opens the
  Log (`chat_log_key=` changes it); on a controller **LT** goes Chat -> Log -> closed. Options > **World Pop-ups** and
  **World Log** turn each off (`world_toasts=0`, `world_log=0` in pc_settings.ini).

**Following Pokemon:** your lead Pokemon walks with you (`uDPRE.exe lan follow 0|1|2`, or the LAN window): 0 as the game (the
party menu's choice, outdoors), 1 the lead by itself where the game lets one follow (the default), 2 the lead everywhere it fits,
caves and buildings too. Others see your follower as you see theirs.

**World host:** the overworld is hosted by one of the players' games. On a network it moves to another game when that player
quits. Over the internet only the reachable player can host it, so when that player quits the others lose the world, and any
room running through it. A world host (`uDPRE World Host.exe`, the LAN window's **Start a world host**, `uDPRE.exe lan host`)
keeps it up on a PC that stays on - it plays no game of its own; press **Allow LAN play...** on that PC first (Windows
Firewall, below). Turn the overworld off with the **Overworld** box in the LAN
window (`uDPRE.exe lan world off`).

- **Same game, not the same mods**: players meet when they play the same game - Brilliant Diamond or Luminescent, the same
  LAN play version (a uDPRE update that changes no game code keeps it: 0.5.5 and 0.5.6 meet; 0.5.11 meets only 0.5.11, and a
  separate world host must be the `uDPRE World Host.exe` of uDPRE 0.5.11; the LAN window shows it) and the
  same Pokemon, battle, contest and Underground data. Cosmetic and own-world mods (Darker UI, Shiny Icons,
  Heal Animation, translations, Dechibified, Easy Mode, Increased Shiny Odds), the game language and Nuzlocke rules may differ;
  No Balance, or edits to Pokemon, moves or items, must match. In the game the chat box's player list (**P**) shows the games
  nearby that cannot join you, greyed, with the reason. With different mods each game shows its own: a Dechibified player's
  wardrobe outfit shows to other Dechibified players (overworld, battles, trainer cards) and to everyone else as their last
  ordinary outfit, and in a Team Up Trainer battle the Trainer's Pokemon are the
  leader's (an Easy Mode leader brings Easy Mode Trainers). **LAN play...** shows this game's build.
- **Windows Firewall**: the PC that hosts the world must let others reach it. On that PC press **Allow LAN play...** in the LAN
  window (or `uDPRE.exe lan firewall`) before you host: it lets the game and the world host through on every network and turns
  off the rules that block them. Windows' own question when a program starts ticks only "Private networks", and then blocks
  that program on "public" ones - many PCs (and VPN adapters) are on a "public" network, and a block wins over a forwarded port.
  The LAN window shows what Windows lets through. **Works over Tailscale or on the home network but not through a forwarded
  port** = this block: press **Allow LAN play...** on the host PC.
- **Over the internet**: there is no uDPRE server, so **one** player has to be reachable. Everyone joins that player's world, and
  Team Up, battles, the Union Room, the Colosseum, the Underground and contests all travel through the overworld link when two
  players cannot reach each other directly. All players need the overworld on. Two ways:
  - **Port forwarding, no VPN**: one player forwards UDP **and** TCP 39310-39317 on their router to their PC (the same port
    numbers outside and inside; games find the world over UDP first, then join over TCP) and presses **Allow LAN play...**
    there. Everyone else adds that player's public address under **Friends' addresses**; the forwarding player adds nothing.
    Start in any order. A world host on that PC shows each player who joins.
  - **A virtual network**: ZeroTier, Radmin VPN or Hamachi need nothing else. With Tailscale, the others add one player's
    address under **Friends' addresses**.

  If nobody can forward a port (some internet providers do not allow it), you need a virtual network. A room running through the
  overworld link passes through the world host, so it is slower than a direct link. With the overworld turned off there is no such
  link: a room then needs UDP + TCP 39290-39297 open on the PC of the player who opens it, and the others need that address.
- From a command prompt: `uDPRE.exe lan show`, `uDPRE.exe lan peers 100.64.0.5`, `uDPRE.exe lan firewall`.

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
