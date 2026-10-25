uDPRE mods folder
=================

Put uDPRE mod packs here: one folder per pack, each holding a file named udpre_mod.json
(for example  mods\Luminescent\udpre_mod.json). Then open uDPRE.exe, tick the mods you want
in the "Mods" box and press Convert (or Apply).

uDPRE does not include any mod pack. Look for uDPRE mod packs online, or ask someone who
already has them.

Luminescent Platinum: the pack holds only the PC version of Luminescent's game code. Put your
own download of Luminescent Platinum 2.2F for Brilliant Diamond here too (get it from Team
Luminescent: https://www.nexusmods.com/pokemonbdsp/mods/1): extract it with 7-Zip
(https://www.7-zip.org) and put the extracted folder (the one with "romfs" and "exefs" inside)
into this mods folder. Or keep it where it is and press "Find a mod download..." in uDPRE.exe.
uDPRE checks every file of it before converting.

Updating a pack: delete its old folder here, then put the new one in (do not copy a new version
over the old folder). When something is wrong, uDPRE.exe says what and what to do: click
"What to do" next to a red line in the Mods box.

- uDPRE converts the mods together with your own dump, so they work with your converted game.
  Patches made for other PC builds (folders you copy over a game folder) do NOT work on a
  uDPRE folder - use the uDPRE pack of that mod instead.
- Packs that need another pack turn it on with them (for example Easy-Mode needs Luminescent).
  Packs that cannot be used together (the French, Spanish and Italian translations) turn each
  other off.
- Some packs have options (for example a mod released in several versions): tick the pack and
  its choices open under it; pick one and press Apply.
- Changing the mods later makes again only the files the change touches.
- Luminescent keeps its saves apart from the unmodded game.

A plain console mod that only changes data (a folder with romfs/Data inside, no exefs) can be
put here too: uDPRE converts its files on top of everything else. Console mods that change the
game code (they have an exefs folder) need a uDPRE pack.
