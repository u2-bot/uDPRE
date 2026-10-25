"""Editor & Randomizer: edits of the game data, kept as a project of operations and re-applied to whatever the stack holds.

A project (edits/<name>.json in the uDPRE folder) is an ordered list of operations - set a field, randomize with a seed and
settings, edit the type chart, insert a Pokemon ... The build replays them on the Switch files of the current stack (the
dump, the chosen packs, the console mods) and writes the files that came out different as one more layer on top, which the
converter then converts like any mod. Changing the mods below changes nothing in the project: the next build applies the
same operations to the new files.
"""
# bump when a rule changes what the build writes for the same project + stack
BUILD_VERSION = 1
