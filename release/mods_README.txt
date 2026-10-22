uDPRE mods folder
=================

Put uDPRE mod packs here: one folder per pack, each holding a file named udpre_mod.json
(for example  mods\Luminescent\udpre_mod.json). Then open uDPRE.exe, tick the mods you want
in the "Mods" box and press Convert (or Apply).

- uDPRE converts the mods together with your own dump, so they work with your converted game.
  Patches made for other PC builds (folders you copy over a game folder) do NOT work on a
  uDPRE folder - use the uDPRE pack of that mod instead.
- Packs that need another pack turn it on with them (for example Easy-Mode needs Luminescent).
  Packs that cannot be used together (the French, Spanish and Italian translations) turn each
  other off.
- Changing the mods later makes again only the files the change touches.
- Luminescent keeps its saves apart from the unmodded game.

A plain console mod (a folder with romfs/Data inside) can be put here too: uDPRE converts its
files on top of everything else. Console mods that change the game code (they have an exefs
folder) cannot be used this way.
