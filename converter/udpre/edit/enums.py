"""Fixed game values the editors show by name (BDSP v1.3.0 code: Pml.Personal.EvolveCond, Pml.WazaData.*). Names of
species, moves, items, abilities, natures, types and trainers come from the game's own messages (game.py)."""

EVOLVE_METHODS = [
    (0, 'None'), (1, 'High friendship'), (2, 'High friendship (day)'), (3, 'High friendship (night)'), (4, 'Level up'),
    (5, 'Trade'), (6, 'Trade holding an item'), (7, 'Trade for a species'), (8, 'Use an item'),
    (9, 'Level, Attack > Defense'), (10, 'Level, Attack = Defense'), (11, 'Level, Attack < Defense'),
    (12, 'Level, personality even'), (13, 'Level, personality odd'), (14, 'Level up (Ninjask)'),
    (15, 'Level up, party slot free (Shedinja)'), (16, 'High beauty'), (17, 'Use an item, male'),
    (18, 'Use an item, female'), (19, 'Hold an item, level up (day)'), (20, 'Hold an item, level up (night)'),
    (21, 'Level up knowing a move'), (22, 'Level up with a species in the party'), (23, 'Level, male'),
    (24, 'Level, female'), (25, 'Level up at a magnetic field'), (26, 'Level up at a moss rock'),
    (27, 'Level up at an ice rock'), (28, 'Level up, device upside down'), (29, 'Affection + a move type'),
    (30, 'Level up with a Dark-type in the party'), (31, 'Level up in rain'), (32, 'Level up (day)'),
    (33, 'Level up (night)'), (34, 'Level up, female, form change'), (35, 'Friendship'), (36, 'Game version'),
    (37, 'Game version (day)'), (38, 'Game version (night)'), (39, 'Level up at a snowy mountain'),
    (40, 'Level up (evening)'), (41, 'Level up in Ultra Space'), (42, 'Use an item in Ultra Space'),
    (43, 'Critical hits'), (44, 'Total damage received'), (45, 'Sweets'), (46, 'Level, nature (high)'),
    (47, 'Level, nature (low)'),
]
# what an evolution method's parameter is: 'item', 'move', 'species', 'type', or None (a number / unused)
EVOLVE_PARAM = {6: 'item', 7: 'species', 8: 'item', 17: 'item', 18: 'item', 19: 'item', 20: 'item', 21: 'move',
                22: 'species', 29: 'type', 42: 'item'}

MOVE_TARGETS = [
    (0, 'One other Pokemon (chosen)'), (1, 'User or ally (chosen)'), (2, 'One ally (chosen)'), (3, 'One opponent (chosen)'),
    (4, 'All other Pokemon'), (5, 'All opponents'), (6, 'All allies'), (7, 'User'), (8, 'Every Pokemon'),
    (9, 'A random opponent'), (10, 'The whole field'), (11, 'The opponents\' side'), (12, 'The user\'s side'),
    (13, 'Unknown (depends on the move)'),
]
MOVE_CATEGORIES = [
    (0, 'Damage'), (1, 'Status condition'), (2, 'Stat change'), (3, 'Healing'), (4, 'Damage + status condition'),
    (5, 'Status condition + stat change'), (6, 'Damage + target stat change'), (7, 'Damage + user stat change'),
    (8, 'Drain'), (9, 'One-hit KO'), (10, 'Field effect'), (11, 'Side effect'), (12, 'Force switch'), (13, 'Other'),
]
DAMAGE_TYPES = [(0, 'Status'), (1, 'Physical'), (2, 'Special')]
MOVE_SICK = [
    (0, 'None'), (1, 'Paralysis'), (2, 'Sleep'), (3, 'Freeze'), (4, 'Burn'), (5, 'Poison'), (6, 'Confusion'),
    (7, 'Infatuation'), (8, 'Bind'), (9, 'Nightmare'), (10, 'Curse'), (11, 'Taunt'), (12, 'Torment'), (13, 'Disable'),
    (14, 'Yawn'), (15, 'Heal Block'), (16, 'Gastro Acid'), (17, 'Foresight'), (18, 'Leech Seed'), (19, 'Embargo'),
    (20, 'Perish Song'), (21, 'Ingrain'), (22, 'Trapped'), (23, 'Encore'), (24, 'Throat Chop'), (25, 'Roost'),
    (26, 'Move lock'), (27, 'Charge lock'), (28, 'Choice lock'), (29, 'Lock-On'), (30, 'Lock-On (target)'),
    (31, 'Magnet Rise'), (32, 'Magnet Rise cancelled'), (33, 'Telekinesis'), (34, 'Sky Drop'), (35, 'Accuracy up'),
    (36, 'Aqua Ring'), (37, 'Forced move type'), (38, 'Powder'), (39, 'Uproar'), (40, 'Thrash'), (41, 'Laser Focus'),
    (42, 'Tar Shot'), (43, 'Octolock'), (44, 'Jaw Lock'), (65535, 'Special (move code)'),
]
SICK_CONT = [(0, 'None'), (1, 'Permanent'), (2, 'Turns'), (3, 'While the Pokemon stays'), (4, 'Turns, while it stays')]
RANK_EFFECTS = [(0, 'None'), (1, 'Attack'), (2, 'Defense'), (3, 'Sp. Atk'), (4, 'Sp. Def'), (5, 'Speed'), (6, 'Accuracy'),
                (7, 'Evasion'), (8, 'All stats'), (9, 'Critical ratio'), (10, 'Five stats')]
# WazaTable.flags bits (Pml.WazaData.WazaFlag)
MOVE_FLAGS = [
    (0, 'Makes contact'), (1, 'Two-turn move'), (2, 'Needs recharge'), (3, 'Blocked by Protect'),
    (4, 'Reflected by Magic Coat'), (5, 'Stolen by Snatch'), (6, 'Copied by Mirror Move'), (7, 'Punch move'),
    (8, 'Sound move'), (9, 'Fails under Gravity'), (10, 'Thaws the user'), (11, 'Reaches every position'),
    (12, 'Blocked by Heal Block'), (13, 'Ignores Substitute'), (14, 'Fails in Sky Battles'), (15, 'Effect to ally'),
    (16, 'Dance move'), (17, 'Metronome can call it'),
]
GENDERS = [(0, 'Male'), (1, 'Female'), (2, 'Genderless / random')]
SEX_RATIO = [(0, 'Male only'), (31, '87.5% male'), (63, '75% male'), (127, '50% male'), (191, '25% male'),
             (225, '12.5% male'), (254, 'Female only'), (255, 'Genderless')]
GROWTH_RATES = [(0, 'Medium Fast'), (1, 'Erratic'), (2, 'Fluctuating'), (3, 'Medium Slow'), (4, 'Fast'), (5, 'Slow')]
EGG_GROUPS = [(0, '-'), (1, 'Monster'), (2, 'Water 1'), (3, 'Bug'), (4, 'Flying'), (5, 'Field'), (6, 'Fairy'),
              (7, 'Grass'), (8, 'Human-Like'), (9, 'Water 3'), (10, 'Mineral'), (11, 'Amorphous'), (12, 'Water 2'),
              (13, 'Ditto'), (14, 'Dragon'), (15, 'Undiscovered')]
COLORS = [(0, 'Red'), (1, 'Blue'), (2, 'Yellow'), (3, 'Green'), (4, 'Black'), (5, 'Brown'), (6, 'Purple'), (7, 'Gray'),
          (8, 'White'), (9, 'Pink')]
# TrainerData.AIBit bits
AI_FLAGS = [(0, 'Basic AI'), (1, 'Strong AI'), (2, 'Expert AI'), (3, 'Double battle AI'), (4, 'Merciful AI'),
            (5, 'Uses items'), (6, 'Switches Pokemon')]
FIGHT_TYPES = [(0, 'Single'), (1, 'Double')]
AFFINITY = [(0, 'No effect (0x)'), (2, 'Not very effective (0.5x)'), (4, 'Normal (1x)'), (8, 'Super effective (2x)')]


def name_of(table, value, default=None):
    for v, n in table:
        if v == value:
            return n
    return default if default is not None else str(value)

# ItemTable fields (Pml.Item.ItemData)
ITEM_TYPES = [(0, 'Bag pocket item'), (1, 'Medicine'), (2, 'Hold item'), (3, 'Misc'), (4, 'Battle item'), (5, 'Poke Ball'),
              (6, 'Mail'), (7, 'TM'), (8, 'Berry'), (9, 'Key item'), (10, 'Treasure'), (255, 'None')]
ITEM_GROUPS = [(0, 'None'), (1, 'Poke Ball'), (2, 'Bag pocket'), (3, 'Berry'), (4, 'TM'), (5, 'Group 5'), (6, 'Gem'),
               (7, 'Mega Stone'), (8, 'Z-Crystal'), (9, 'Z-Crystal (held)'), (10, 'Rotom Power'), (11, 'Candy')]
ITEM_POCKETS = [(0, 'Medicine'), (1, 'Poke Balls'), (2, 'Battle items'), (3, 'Berries'), (4, 'Other items'), (5, 'TMs'),
                (6, 'Treasures'), (7, 'Ingredients'), (8, 'Key items'), (9, 'Unknown')]
FIELD_FUNCS = [(0, 'None'), (1, 'Use on a Pokemon'), (2, 'Teach a TM'), (3, 'Bicycle'), (4, 'Honey'), (5, 'Toggle'),
               (6, 'Evolution item'), (7, 'Escape Rope'), (8, 'Change ability'), (9, 'Eon Flute'), (10, 'Function 10'),
               (11, 'Mail'), (12, 'Berry'), (13, 'Super Rod'), (14, 'Vs. Recorder'), (15, 'Change form'),
               (16, 'Function 16'), (17, 'Change form (fusion)'), (18, 'Rotom Power'), (19, 'Explorer Kit'),
               (20, 'Guidebook'), (21, 'Poffin Case'), (22, 'Poke Radar'), (23, 'Sprayduck'), (24, 'Vs. Seeker'),
               (25, 'Old Rod'), (26, 'Good Rod'), (27, 'Azure Flute'), (28, 'Point Card'), (29, 'DS Sounds')]
BATTLE_FUNCS = [(0, 'None'), (1, 'Poke Ball'), (2, 'Use on a Pokemon'), (3, 'Escape')]
PLUCK = [(0, 'None')] + list(enumerate(['Cheri', 'Chesto', 'Pecha', 'Rawst', 'Aspear', 'Leppa', 'Oran', 'Persim', 'Lum',
                                        'Sitrus', 'Figy', 'Wiki', 'Mago', 'Aguav', 'Iapapa', 'Liechi', 'Ganlon', 'Salac',
                                        'Petaya', 'Apicot', 'Lansat', 'Starf', 'Micle'], start=1))
# ItemTable.flags0 bits; bit 31 = the item is NOT in use
ITEM_FLAGS = [(0, 'Special effect'), (1, 'Important'), (2, 'Registerable'), (3, 'Single-use hold item'),
              (4, 'Selectable in battle'), (5, 'Usable repeatedly'), (6, 'Holdable'), (7, 'WORK_TYPE'),
              (8, 'Guard Spec. effect'), (9, 'Level / EXP increase'), (10, 'Restores one move\'s PP'),
              (11, 'Restores all PP'), (12, 'PP Up'), (13, 'PP Max'), (14, 'EV increase'), (15, 'Cures sleep'),
              (16, 'Cures poison'), (17, 'Cures burn'), (18, 'Cures freeze'), (19, 'Cures paralysis'),
              (20, 'Cures confusion'), (21, 'Cures infatuation'), (22, 'Revives one'), (23, 'Revives all'),
              (24, 'Evolution item')]
ITEM_UNUSED_BIT = 31
