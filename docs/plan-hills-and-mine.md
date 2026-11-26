# Hills and the mine

Working plan for Rick and Lumen. Phase 1 is in the tree: hills, growing trees, forage, the axe, HP, off-screen notes, and Storybook art. Items stay whole
counts. Random rolls stay deterministic, in the same style as weather,
weeds, and harvest yields (`weather_mix` / `weed_hash` over
`weather_seed`, day, and a salt). Names in the repo stay **Rick**.

The farm is one 3×3 (`ROWS`/`COLS` in `engine.py`), cabin at row 1
col 3, energy in `rules.json`, a 4-slot pack, a shared cabin chest, and
one Storybook / Classic grid plus an ASCII mini-map. The hills are a
second 3×3, reached only from the cabin. The mine (Phase 2) is a third
kind of 3×3, behind a boarded entrance.


## Settled decisions

- **Entrance path.** Walking north from the **cabin only** (farm row 1
  col 3) enters the hills at the **bottom-right** (hills row 3 col 3).
  Walking south from hills r3c3 returns to the cabin tile. Other farm
  top-row tiles do not lead into the hills.
- **Mine entrance** stays at hills north-centre (row 1 col 2). In
  Phase 1 it is **boarded**, with a hint in look text. Stepping onto
  that tile marks the entrance as found (this later unlocks the
  pickaxe in the shop).
- **Ladder (Phase 2).** The way down is hidden under a **random rock**
  on each floor, not the centre square. Arrival is on a clear tile.
- **Mine floors (Phase 2)** re-roll each **season**, so going deep is a
  seasonal race. Layout is seeded and shared for the whole season.
- **Tools.** One axe and one pickaxe in the world, shared like the hoe.
  The axe starts in the chest in Phase 1. The pickaxe is a **shop
  purchase** that unlocks once someone has found the mine entrance
  (Phase 2).
- **HP.** Max **100**. Snacks heal HP (the same amount they restore
  energy). At 0 HP you pass out and wake at the **mine entrance** with
  **25 energy** (and HP restored). Cabin sleep still grants 100 energy
  and fills HP. Passing out by ending a turn in the field or hills is
  unchanged (50 energy, stay where you are). The pass-out warning
  names the current area ("in the field", "in the hills", later
  "in the mine").
- **Off-screen context.** Whenever a player is in one area, **look
  text (the CLI)** still describes the other areas: where the other
  player is (area and tile), a short summary of the off-screen place
  (hills: trees ready to chop, forage available; farm: crops ready or
  needing water), and the exits (north from the cabin to the hills,
  and so on). The web page shows only the area title above the grid;
  it does not repeat that Elsewhere block. The header still names
  each player's place. The mini-map names the current area. Hills
  tiles use the same `r* c*` labels as the farm (the cabin tile still
  says "cabin").


## Areas and walking

Three area ids: `farm`, `hills`, and later `mine`. A player’s place is
`(area, row, col)`, plus `floor` in the mine. `state["tiles"]` stays
the farm, so old saves and crop / weed ticks keep working. Hills live
under `state["hills"]["tiles"]`.

**Cabin sleep is area-aware.** Only `area == "farm"` at row 1 col 3 is
sleep. Hills (1, 3) is not the cabin.

`move up/down/left/right` (and `go north/south/east/west`) stay inside
the current area, except the cabin ↔ hills r3c3 crossing, which costs
one ordinary step (5 energy). `move to <row> <col>` never jumps areas.
`go cabin` from the hills walks to r3c3 and then to the cabin, charging
every step. From inside the mine (Phase 2) it is refused until you
climb out.

Hills layout:

```
      col 1        col 2            col 3
row 1 hillside     MINE ENTRANCE    hillside
row 2 grass/trees  grass/trees      grass/trees
row 3 grass/trees  grass/trees      grass/trees   ← r3c3: path to the cabin
```

Look text and the web grid show the **viewer’s current area**. The other
area is summarised under “Elsewhere,” and if the other player is not on
this grid, the header names their area and tile. Keyboard 1–9 still
means the current area’s nine tiles.


## Phase 1 — hills, trees, and forage (built)

Hills tiles are not farmland: no till, plant, water, fertilizer, or
unearth. You still stand on a tile to work it, the same as a crop.

**Trees** grow sapling → young → grown at day turn, with no watering. A
grown tree can be `chop`ped with an **axe** in the pack (10 energy) and
drops **2 wood**, leaving a stump that can resprout (stump → sapling).
One basic axe starts in the cabin chest.

**Wild plants** spawn like weeds: 0–2 a day on empty grass, never on the
mine mouth or a tree, capped so the hills do not fill up, seeded from
`weather_seed`, day, and plot. Seasonal: spring wild onion, summer wild
berry, autumn wild mushroom, winter none for now. `forage` costs 5,
like pluck, and goes to the pack (refused if full). The shop doesn't
buy foraged goods (wood still sells at the cabin). Wild onion (+6
energy and HP) and wild berry (+8) are edible raw; wild mushroom is
cook-only, like rhubarb (`eat` says it isn't edible raw). Each has a
cabin recipe: wild onion soup (1 wild onion + 1 milk, +28 energy, 32G),
wild berry jam (2 wild berries, +32 energy, 55G), and mushroom soup
(1 wild mushroom + 1 milk, +32 energy, 40G). Wild berries also count
toward strawberry jam's berry pool, alongside June-bearing and
everbearing strawberries. The hills show weather, including snow, but
have no wet/dry soil.

Existing saves migrate in place: farm tiles, gold, packs, turn, and
energy are untouched. Players gain `area` (default `farm`) and `hp`
(100). Hills are generated from the farm seed and then grown forward
to the current day. The axe is added to the chest only if missing.


## Phase 2 — mine, ores, and the forge (later)

`enter mine` from the (now open) hills entrance starts or joins the
season’s mine. The layout is seeded from `weather_seed` and the current
season, and it **persists until the season changes**, then re-rolls.
Both players share the same rocks and ores all season.

The way down is under a **random rock** on each ordinary floor (not
fixed to the centre). You arrive on a clear tile. Climbing down costs
**10**. Breaking the hiding rock reveals the ladder. Floors run **1–25**.
Ore by depth, pickaxe rules, the forge, tool upgrades, safe floors,
and the elevator stay as previously sketched, except the pickaxe is
bought from the shop after the entrance has been found, and fainting
from 0 HP wakes at the mine entrance with 25 energy.

Safe floors (5, 10, 15, 20, 25): no rocks or slimes, a lantern (`rest`
restores 25 energy, once per player per that floor per day), and an
elevator checkpoint. Passing out by ending a turn in the mine (not 0
HP) should still wake at the last elevator or the entrance with 50
energy, pack kept.


## Phase 3 — slimes and combat (later)

Slimes appear from floor 6 on, never on safe floors. They deal HP
damage. `strike` and `flee` as previously sketched. 100 HP, snacks
heal HP, 0 HP wakes at the mine entrance with 25 energy. Goo drops
for one recipe.


## Energy, commands, and items (Phase 1)

`rules.json` costs: chop 10, forage 5. Move stays 5. Eat, take, drop,
buy, and sell stay free. Two snacks a turn still apply in the hills.
Snacks also heal HP.

Phase 1 commands: `go north` (from the cabin), `go south` (from hills
r3c3), `chop`, `forage`, plus the usual `move`, `go cabin`, `take axe
1`. Legal actions list them so they parse and execute from the printed
list.

Phase 1 items: wood, wild onion, wild berry, wild mushroom, axe,
plus the three forage recipes (wild onion soup, wild berry jam,
mushroom soup).


## Art, mini-map, and the page

Classic SVG fallbacks in `sprites.py` for every new key, then Storybook
grounds / overlays / item icons — the same 512 square PNGs and manifest
pattern as crops.

- **Grounds:** hills grass (and snow), hillside (and snow), boarded
  mine entrance (and snow).
- **Overlays:** tree sapling / young / grown / stump, each wild plant.
- **Items:** axe, wood, wild onion, wild berry, wild mushroom.
  The three forage dishes use Classic SVG placeholders until Storybook
  icons are painted.

Mini-map: the same 3×3 ASCII, headed “Mini map — the farm” or “Mini
map — the hills”. New labels must fit `MAP_LABEL_WIDTH` (10). The web
page keeps the 3×3 `.grid`, titled with the area, and an Elsewhere
note for the off-screen place and the other player. Keys: C chop, G
forage.


## Save format and migration

`migrate_state` is idempotent and does not touch farm tiles, gold,
packs, the chest contents already there, mid-turn energy, or whose
turn it is. Existing farms get `area: "farm"` and `hp` / `hp_max` on
each player, generated hills (grown forward to the current day),
`mine_entrance_found` (false until someone steps on the entrance),
and a basic axe added to the chest only if missing.

`apply_new_day_turns` must copy `area`, `floor`, `hp`, and `pack`. A
player who slept in the real cabin wakes there with full HP; one who
passed out in the hills wakes on that tile. Day turn ticks farm crops
and weeds as today, then tree growth and forage.


## Tests

Follow `test_engine.py`: deterministic, no live save, listed legal
actions parse and execute. Also jsdom coverage for the area grid and
Elsewhere note. First Farm is never loaded or written by this work.

- Migration adds hills and `area=farm` without changing farm tiles,
  gold, packs, energy, or whose turn it is; hills (1, 3) is not the
  cabin.
- North from the cabin enters hills r3c3; south returns to the cabin;
  north from another farm top-row tile is refused; `go cabin` from the
  hills charges the full path.
- Trees grow across days; `chop` needs an axe and yields wood; a stump
  resprouts; forage is deterministic and seasonal; `take axe 1` works.
- Look and the web payload summarise the other area and name the other
  player’s place; the mini-map names the current area.
- Snacks heal HP; HP starts at 100; cabin sleep fills HP.
- Mini-map labels fit; sprite keys round-trip; new pack art is square
  with a transparent item background.


## Build order

1. This document, with the decisions above folded in.
2. **Phase 1 (this pass).** Areas, cabin ↔ hills r3c3, hills, trees,
   forage, axe, wood, HP, off-screen context, look / mini-map / web,
   migration, Storybook art, unit and jsdom tests.
3. **Phase 2.** Open the mine, seasonal floors, random-rock ladder,
   ores, pickaxe shop unlock, forge, upgrades, safe floors, elevator.
4. **Phase 3.** Slimes, strike / flee, goo, and one recipe.

Each phase should be its own playable stretch, not one giant commit.


## Open questions (still, for later phases)

1. Is 25 a good deepest floor, or would we rather cap at 20 or leave
   it open?
2. Forge at the cabin (recommended, matches craft) or at the mine
   mouth?
3. Are the hoe / can upgrade effects (energy drop, then an adjacent
   tile) the ones we want on a farm this small?
4. May we later plant saplings on the hills, or do they stay wild?
5. Should `go cabin` from inside the mine ever mean “elevator, then
   walk home” in one command, at the combined energy cost?
6. Does wood have a use beyond selling and later building (for
   example, forge fuel if coal is short)?
