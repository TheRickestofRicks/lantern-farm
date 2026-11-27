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
- **Orchard (later).** The hills will be convertible into an orchard
  later. Planting saplings comes with that conversion.
- **No elevator.** The mine will not keep an elevator. We're not
  copying Stardew Valley that much. Teleporting comes later via rune
  magic. Until then, travel is by climbing ladders, and ending a turn
  in the mine wakes at the hills entrance. `go cabin` from inside the
  mine stays refused until you climb out to the hills entrance.
- **Phase 3 mine finds.** Grey slimes start on floor 6 (first slime
  type; more types later deeper; never on safe floors). Quartz can
  drop from plain stone rocks on floors 1–4. Runestone ore rocks are
  rare on floors 1–4 and become more frequent deeper; they look
  smooth and rounded, unlike normal rocks.


## Areas and walking

Three area ids: `farm`, `hills`, `mine`, and `town`. The east market
town is described under East market town. A player’s place is
`(area, row, col)`, plus `floor` in the mine. `state["tiles"]` stays
the farm, so old saves and crop / weed ticks keep working. Hills live
under `state["hills"]["tiles"]`.

**Cabin sleep is area-aware.** Only `area == "farm"` at row 1 col 3 is
sleep. Hills (1, 3) is not the cabin.

`move up/down/left/right` (and `go north/south/east/west`) stay inside
the current area, except the cabin ↔ hills r3c3 crossing, which costs
one ordinary step (5 energy). `move to <row> <col>` never jumps areas.
`go cabin` from the hills walks to r3c3 and then to the cabin, charging
every step. From inside the mine it is refused until you climb out
to the hills entrance. There is no combined elevator-then-walk-home
command; rune teleport comes later.

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

Hills tiles are not farmland: no till, plant, water, or fertilizer.
You still stand on a tile to work it, the same as a crop. `unearth` on
the farm (5 energy, shovel) still clears a crop to plain soil. In the
hills, `unearth` only works on a stump or mushroom log: shovel, 20
energy, and the tile returns to plain grass with no resprout. Empty
hills tiles (and the mine) still refuse with “There's nothing to
unearth here in the hills.”

**Trees** grow sapling → young → grown at day turn, with no watering. A
grown tree can be `chop`ped with an **axe** in the pack (10 energy) and
drops **2 wood**, leaving a stump. After the stump's days, it either
resprouts (stump → sapling) or becomes a mushroom log — one exclusive
outcome per tile, never both. Mushroom logs periodically grow oyster
mushrooms (including in winter) that do not count toward the wild
forage cap. Oysters are cook-only and unsellable; they can stand in
for the wild mushroom in mushroom soup. One basic axe starts in the
cabin chest.

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


## Phase 2 — mine, ores, and the forge (built)

`enter mine` (or `go mine`) from the hills entrance at r1c2 opens the
season’s mine. The first entry needs a pickaxe in the pack to pry the
boards; that opening is permanent. Later visits do not need the
pickaxe, but breaking rocks still does. The pickaxe is a shop item
(40G, only one in the world) unlocked once someone steps on the
entrance tile (`mine_entrance_found`).

Floors run **1–25**. The layout is seeded from `weather_seed` plus the
current season and year (no RNG), and it **persists until the season
changes**, then re-rolls. Both players share the same rocks, ores,
and ladders all season. You arrive on a clear exit/shaft tile. The way down is hidden under a random rock that is
not the centre and not the arrival tile; `mine` / `break` reveals the
ladder. Climbing down costs **10**; climbing up costs **5**. `go cabin`
from inside the mine is refused until you climb out to the hills
entrance.

Ore bands (remainder is plain stone): floors 1–4 copper 40%; 6–9
copper 50% iron 15%; 11–14 copper 20% iron 45% gold 5%; 16–19 copper
10% iron 35% gold 25%; 21–24 iron 20% gold 45%. Items are
`copper_ore`, `iron_ore`, and `gold_ore` (aliases copper, iron, and
“gold ore” — not bare “gold”), selling for 8 / 12 / 20G.

Safe floors (5, 10, 15, 20, 25): no rocks, a lantern (`rest` restores
25 energy, once per player per that floor per day, cost 0), and a
visible down ladder (none on 25).

**Elevator (built, to be removed in Phase 3).** Safe floors currently
also have an elevator checkpoint. The elevator (cost 5) runs from
the elevator tile to any reached checkpoint or the entrance. Ending
a turn in the mine (not 0 HP) currently wakes at the last elevator
or the entrance. Decision: no elevator. We're not copying Stardew
Valley that much. Teleporting comes later via rune magic. Phase 3
removes the elevator. Until rune teleport lands, travel between
floors is by climbing ladders, and ending a turn in the mine wakes
at the hills entrance (see Phase 3).

The forge is at town row 2 col 3 (cost 5); see East market town. Upgrade a hoe, watering can, axe,
or pickaxe one tier at a time (copper, then iron, then gold) with 5 of
that tier’s ore. Tiers now only change energy: basic 10, copper 8, iron 6, gold 4.
Iron yield and gold pickaxe splash are parked for a later rune system (Bounty and Shatter).

0 HP still wakes at the hills mine entrance with 25 energy (and full
HP). Until the elevator is removed, ending a turn in the mine (not
0 HP) wakes at the last elevator or the entrance with 50 energy,
pack kept; if the season changes at that dawn, wake at the hills
entrance. After Phase 3 removes the elevator, ending a turn in the
mine wakes at the hills entrance (same 50 energy, pack kept),
including when the season changes. Slimes, quartz, and runestone
ore are Phase 3.

The web view stays free of Elsewhere hints (CLI look may keep them).
Tile labels stay `r*c*`. The header shows weather / energy / HP icons;
player locations live in an Overview panel above This Tile, not in the
top bar.


## Phase 3 — slimes, quartz, runestone, and elevator removal

This is the next mine pass. It adds grey slimes, quartz, and
runestone ore, and it removes the elevator.

**Grey slimes** are the first slime type. They appear from floor 6
on, never on safe floors (5, 10, 15, 20, 25). A non-safe floor can
have several slimes on different tiles, never on the arrival/shaft
tile. More slime types come later, deeper. They deal HP damage.
`strike` and `flee` are only available when you stand on the same
tile as a slime (not a neighbouring tile). Strike targets the slime
on your tile. Max HP stays **100**. Snacks heal HP (the same
amount they restore energy). 0 HP still wakes at the hills mine
entrance with 25 energy (and full HP). Grey slimes drop **goo**,
which goes into one recipe. Each slime has its own HP and drops its
own goo when defeated.

Current numbers (see Open questions if we retune): grey slimes have
**20 HP** and deal **8** damage; slime counts per floor, rolled from
the seasonal seed, are **0–1** on 6–9, **0–2** on 11–14, **1–2** on
16–19, and **1–3** on 21–24; `strike` and `flee` cost **5** energy
each.

**Quartz** drops randomly from plain stone rocks (not ore rocks) on
floors **1–4**. The item is `quartz`. Suggestions, not settled: a
**15%** chance when you mine a plain stone rock on those floors,
selling for **6G**. Other uses are still open.

**Runestone ore rocks** are a distinct rock type: they look **smooth
and rounded**, unlike normal rocks (art note for the sprite; see
Art pass). The item is `runestone_ore`. They are rare on floors
1–4 and become more frequent deeper. This ore feeds later rune
magic (Bounty, Shatter, and teleport). Suggestions, not settled:
they take a small slice of the remainder (plain stone), so they do
not cut into copper, iron, or gold rates — **3%** on floors 1–4,
**6%** on 6–9, **9%** on 11–14, **12%** on 16–19, and **16%** on
21–24; selling for **15G**. What the ore becomes, beyond feeding
rune magic, is still open.

**Elevator removal.** The elevator is built today and comes out in
this phase. Until rune teleport lands, the way up and down is
climbing ladders (down 5, up 5). `go cabin` from inside the mine
stays refused until you climb out to the hills entrance, then walk
home as usual. Ending a turn in the mine (not 0 HP) wakes at the
hills entrance with 50 energy, pack kept, including when the season
changes — unless you are carrying a sleeping bag (see Mine
difficulty, below). 0 HP still wakes at the hills mine entrance with
25 energy.

Code impact (follow-up for this phase; do not change code from this
document alone):

- `mine.py`: stop placing elevator tiles on safe floors; drop
  `take_elevator` and `parse_elevator_dest`; update leave-mine
  messages; change `wake_place_after_mine_passout` (it currently
  prefers `last_checkpoint` and the elevator tile on that floor)
  so a non-faint pass-out wakes at the hills entrance; drop
  elevator stops from the mine summary and tile descriptions.
- `engine.py`: drop `_reachable_elevator_floors` and the rescue
  path that uses the elevator when it is cheaper; update `go cabin`
  / `go town` refusals that mention the elevator; drop legal
  actions (`elevator`, `elevator N`, `elevator entrance`), the
  verb handler, and help text.
- `rules.json`: the `"elevator": 5` energy cost.
- `hills.py`: the leave-mine hint that mentions the elevator.
- `web.py`: elevator sprite-key parsing, look bits, and action
  buttons.
- `sprites.py` and `packs.py`: the elevator overlay
  (`_elevator_overlay`, the `mine_elevator` key). The Storybook
  PNG can stay unused until a later cleanup.
- Tests: `test_engine.py` cases for safe-floor elevators, elevator
  checkpoints, waking at the last elevator, and mine rescue using
  the elevator when cheaper, plus any case that sets or expects
  elevator actions; `tests/mine-ui.test.js`.
- Other docs (README, ROADMAP) still describe the current
  elevator and will need a matching update when the code lands.
  ROADMAP still says the elevator stays until runes land; this
  plan supersedes that.


## East market town

Built as decided below. Rick asked for a new area: an east market
town, reached by a path east from the farm.

The town is a 3×3, like the hills. The cabin is the travel hub: the
east path leaves from the cabin (farm row 1 col 3, the same tile that
already leads north to the hills) and enters the town at **r1c1**,
which is grassy. **r1c2** is the stall. **r2c1** is the store, so the
entrance is one arrow key from both.

The town has a selling **stall**, a **store**, and a **forge**. The
stall replaces the cabin’s sell option: you drop items into the stall,
and they are sold automatically when the day ends, like a shipping
bin. You can also spend 50 energy to sell everything in the stall
instantly. The store also lives in the town and runs on an honour
system, with no NPCs — coins come straight from the purse. The rest
is grassy, town-like open space, left open for later growth. The town
unlocks on **day 1**.

### Lumen’s suggestions

These are suggestions, not settled decisions:

- Start small: the stall, the forge, a lantern post or two, and the
  path, with grass left for later additions. (The store is now a
  decided part of the first town, alongside the stall, at r2c1.)
- The forge turns mine ore into tool upgrades, which ties the hills,
  the mine, and the town together. A free tile for the forge is
  **r2c3** (mid-right): a short walk from the entrance, and it does
  not sit on the stall/store cluster at r1c2 and r2c1.
- The stall has a blue awning or sign (Lumen’s colour).

### Decisions

- The stall **replaces** the cabin’s sell option. You drop items into
  the stall. They are sold automatically when the **day** ends, like a
  shipping bin. There is also an option to spend **50 energy** to sell
  everything in the stall instantly.
- The town unlocks on day 1.
- The town also contains the **store**, at **r2c1**, so the entrance
  (r1c1) is one arrow key from both the stall (r1c2) and the store.
  The store runs on an honour system with no NPCs. Coins come
  straight from the purse, with a line like “left 20g in the tin.”
- Sellable at the stall: everything that sells currently, plus fresh
  produce, jam, wood, stones, ore, and so on. This **widens** today’s
  list (right now the cabin shop only buys jam, and wood still sells
  at the cabin; foraged goods and other cooked meals are unsellable).
- The forge gets more recipes later. Phase 2 already forges each tool
  up copper, then iron, then gold, for 5 of that tier’s ore; that list
  stays, and more can be added later.
- The **forge** is at **r2c3** (decided Nov 26).
- The east path leaves from the cabin, so the cabin is the travel
  hub. It enters the town at r1c1, which is grassy. r1c2 is the
  stall. The town is a 3×3 like the hills.

### How it fits the phase order

Phase 1 (built) is the hills, trees, and forage. Phase 2 (this pass)
is the mine, ores, **and the forge** — the forge already appears in
Phase 2, at the cabin, and already upgrades the hoe, watering can,
axe, and pickaxe with mine ore. Phase 3 is slimes (starting with
grey slimes on floor 6), quartz, runestone ore, and elevator
removal.

Because the town unlocks on day 1, the town (stall and store) came
earlier than a late follow-on after Phase 2 and 3. Moving the
Phase 2 cabin forge into town is natural: ore from the mine is
upgraded at the town forge, farm goods are sold at the stall, and
buying happens at the town store, which ties the hills, the mine,
and the town together, rather than adding a second forge.

### Conflicts with what was already in

These conflicts were resolved when the town was built.

- **Sell** was a cabin action. The stall
  replaces that with a drop-and-sell-when-the-day-ends mechanic,
  plus an optional 50-energy instant sell. Today the shop only buys
  jam (and wood still sells at the cabin); foraged goods and other
  cooked meals are unsellable. The decided stall list is wider:
  current sellables, plus fresh produce, jam, wood, stones, ore, and
  so on.
- **Store / shop** lived at the cabin. Seeds, staples, fertilizer,
  herbal tea, the sleeping bag, and the pickaxe now sell at the honour
  store in town.
- **Pickaxe shop unlock:** the pickaxe appears in the shop only after
  someone finds the mine entrance (`mine_entrance_found`). That
  unlock can stay even if the store moves to town on day 1 — the
  store is open from day 1, but the pickaxe still waits until the
  entrance is found.
- **Forge** was at the cabin. It is now at town row 2 col 3, with the
  same recipes.
- The cabin is already the hub north to the hills (farm r1c3 ↔ hills
  r3c3). East from that same tile is currently out of bounds.

### Open questions

- What about r1c3, r2c2, and row 3? (Lumen suggests leaving them grass
  for later growth.)


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
  and open mine entrance (and snow), mine floor, safe-floor stone.
- **Overlays:** tree sapling / young / grown / stump / mushroom log, each wild plant including oyster mushrooms,
  rocks and ore rocks, an open ladder, a shaft, a lantern, an elevator
  (the elevator overlay is built and comes out in Phase 3). Phase 3
  adds a runestone ore rock (smooth and rounded, unlike normal rocks)
  and grey slime sprites; see Art pass.
- **Items:** axe, wood, wild onion, wild berry, wild mushroom, plus
  Classic SVG placeholders for the pickaxe and copper / iron / gold
  ore (Storybook item icons come later; do not add manifest entries
  without PNGs). The three forage dishes use Classic SVG placeholders
  until Storybook icons are painted.

Mini-map: the same 3×3 ASCII, headed “Mini map — the farm”, “Mini
map — the hills”, or “Mini map — the mine, floor N”. New labels must
fit `MAP_LABEL_WIDTH` (10). The web page keeps the 3×3 `.grid`, titled
with the area. Elsewhere hints stay in the CLI look and in the
payload for that output; they are not shown on the page. Keys: C chop,
G forage, and in the mine, mine / climb / rest / elevator (the
elevator key comes out in Phase 3).


## Art pass

Do these graphics together in one pass, Classic SVG fallbacks and
Storybook art:

- **Runestone ore rock.** Smooth and rounded, unlike normal angular
  rocks. Overlay plus a `runestone_ore` item icon.
- **Grey slime sprites.** The first slime type, for floor 6 and
  deeper (never on safe floors).
- **Sleeping bag item icon.** The bag is in the game with a simple
  Classic SVG placeholder (`BAG` on a warm brown square). Paint a
  proper rolled blanket for Storybook in this pass.
- **Prettier Storybook town tiles.** Stall, honour store, forge,
  and grass. The current tiles work; this is a prettier pass.
- **Redo the snow tile graphics.** The current Storybook farm snow
  grounds show a pale path down the middle that shouldn't be there.
  That path is visible on `soil_snow`, and the same mid-tile
  brightening is on `soil_wet_snow`, `soil_tilled_snow`, and
  `soil_watered_snow`. `hills_grass_snow` and `hillside_snow` are
  also brighter down the middle. Redo them as even snow cover, with
  no path. Include the other snow grounds in the same pass so
  winter stays consistent: `mine_entrance_closed_snow`,
  `town_grass_snow`, and `cabin_snow`.

Classic SVG functions in `sprites.py` that draw snow tiles (redo
these in the same pass where they show a path or need to match the
new Storybook snow):

- `_snow_ground_overlay(tilled)` — a soft snow blanket on Classic
  farm soil tiles, applied from `svg_for_key` when the tile is
  snowy.
- `_hills_ground(kind, snow=False)` — Classic hills grass, hillside,
  and mine-entrance grounds. When `snow` is true it swaps to a
  winter palette and adds flakes. Hillside tiles also draw a stroke
  across the middle (`M0 70 Q 80 40 160 78`) in both weather and
  snow, which can read as a path. `svg_hills_tile` composes this.
- `_town_ground(snow=False)` — Classic town grounds. It always
  draws a central path and cobble rectangle, including under snow.
  `svg_town_tile` composes this plus the stall, store, and forge
  overlays.
- `_cabin_sky(weather)` and `_cabin_weather_overlay(weather)` —
  used by `svg_cabin` for the snowy cabin (winter fills, a snow cap
  on the roof, and falling flakes).


## Save format and migration

`migrate_state` is idempotent and does not touch farm tiles, gold,
packs, the chest contents already there, mid-turn energy, or whose
turn it is. Existing farms get `area: "farm"` and `hp` / `hp_max` on
each player, generated hills (grown forward to the current day),
`mine_entrance_found` (false until someone steps on the entrance),
and a basic axe added to the chest only if missing.

`apply_new_day_turns` must copy `area`, `floor`, `hp`, and `pack`. A
player who slept in the real cabin wakes there with full HP; one who
passed out in the hills wakes on that tile; one who passed out in the
mine currently wakes at the last elevator or the hills entrance
(the hills entrance if the season just changed). After Phase 3
removes the elevator, a pass-out in the mine wakes at the hills
entrance, including when the season changes. Existing farms get a `mine`
block on first load; that migration does not touch farm tiles, gold,
packs, the chest, mid-turn energy, or whose turn it is. Day turn ticks
farm crops and weeds as today, then tree growth and forage, then
re-rolls the mine when the season changes (the entrance stays open).


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
  resprouts or becomes a mushroom log; forage is deterministic and seasonal;
  `take axe 1` works.
- Look and the web payload summarise the other area and name the other
  player’s place; the mini-map names the current area.
- Snacks heal HP; HP starts at 100; cabin sleep fills HP.
- Mini-map labels fit; sprite keys round-trip; new pack art is square
  with a transparent item background.
- Phase 2: the entrance stays boarded until a pickaxe pries it; the
  shop hides the pickaxe until the entrance is found, then sells one;
  enter arrives on a clear floor-1 tile; layouts are deterministic for
  the same seed and season and re-roll when the season changes; the
  ladder is not on the centre, is hidden under a rock, and is revealed
  when mined; climb down costs 5; ores follow the depth bands; safe
  floors have no rocks, a once-a-day rest, and (until Phase 3) an
  elevator; passing out in the mine currently wakes at the last
  elevator or the entrance (the entrance if the season changes); 0
  HP still wakes at the hills entrance with 25 energy; forge
  upgrades reduce tool energy; legal actions and short names
  execute; `go cabin` is refused from the mine; migration does not
  touch farm tiles, gold, packs, energy, or whose turn it is. First
  Farm is never loaded or written. Phase 3 tests: grey slimes from
  floor 6, never on safe floors, with depth-band counts and never on
  the arrival tile; `strike` / `flee` only when you stand on the same
  tile as a slime; multiple slimes on a floor keep their own HP and
  goo; older single-slime saves migrate to a list; quartz drops from
  plain stone on floors 1–4; runestone ore rocks are rare early and
  more frequent deeper; no elevator actions or tiles; ending a turn
  in the mine wakes at the hills entrance unless a sleeping bag is
  in the backpack (same floor and tile, 100 energy, no comfort
  bonuses); climb down costs 5; the honour store sells a sleeping
  bag for 120G; `go cabin` stays refused until you climb out;
  `take copper pickaxe` (and other forged tool display names) parses.



## Mine difficulty

Play feedback: Rick only reached floor 2. Climbing down cost 10 and
ending a turn in the mine sent you back to the hills entrance with
50 energy, so a deeper run was hard to afford. Two changes address
that:

- Climbing down a ladder costs **5** energy (the same as climbing
  up).
- The honour store sells a **sleeping bag** for **120G** (in the
  100–150G range; about three pickaxes, less than a good jam sale).
  It takes one backpack slot (pack stack 1, like a tool). Ending a
  turn with the bag in your pack, when you are not in a cabin bed,
  uses it automatically: you sleep in the bag and wake on the same
  spot with **100 energy** and **no comfort bonuses** (no fireplace,
  no herbal tea, no full-belly bonus, no double-bed / together
  rest). In the mine that means the same floor and tile, and the
  floor state is kept. Without the bag, existing rules are
  unchanged (mine pass-out still wakes at the hills entrance with
  50 energy). The look line and web UI show “You'll sleep in the
  sleeping bag…” when this applies. A simple Classic SVG
  placeholder stands in for the item icon until the art pass.

## Build order

1. This document, with the decisions above folded in.
2. **Phase 1.** Areas, cabin ↔ hills r3c3, hills, trees, forage, axe,
   wood, HP, off-screen context, look / mini-map / web, migration,
   Storybook art, unit and jsdom tests.
3. **Phase 2 (built).** Open the mine, seasonal floors,
   random-rock ladder, ores, pickaxe shop unlock, forge, upgrades,
   safe floors, elevator, web mine view, status icons, and Overview.
4. **Phase 3.** Grey slimes from floor 6 (more types later deeper),
   strike / flee, goo and one recipe, quartz from plain stone on
   floors 1–4, runestone ore rocks (rare early, more frequent
   deeper), and elevator removal (climb ladders in the meantime;
   ending a turn in the mine wakes at the hills entrance). Rune
   teleport comes later.
5. **Art pass.** The graphics listed under Art pass, done together
   in one pass: runestone ore rock, grey slime, prettier Storybook
   town tiles, and redone snow tiles.

Each phase should be its own playable stretch, not one giant commit.


## Open questions (still, for later phases)

1. Deepest floor is 25 for this pass (decided).
2. The forge is at town row 2 col 3 (moved from the cabin; see East
   market town).
3. Tool tiers cost 10 / 8 / 6 / 4 energy (basic / copper / iron / gold).
   Iron +1 yield and gold pickaxe splash are reserved for a later rune
   system (Bounty and Shatter).
4. May we later plant saplings on the hills, or do they stay wild?
   **Decided:** the hills will be convertible into an orchard later.
   Planting saplings comes with that conversion. See Later.
5. Should `go cabin` from inside the mine ever mean “elevator, then
   walk home” in one command, at the combined energy cost?
   **Decided: no.** There is no elevator. `go cabin` stays refused
   until you climb out to the hills entrance, then walk home as
   usual. Teleporting comes later via rune magic (a homeward rune,
   and waystones).
6. Does wood have a use beyond selling and later building (for
   example, forge fuel if coal is short)? `fuel fireplace` now spends
   5 energy and one wood (pack or chest) to lay a fire for the night.
   Cabin sleepers get +10 wake energy, and +10 more if that player ate
   at least 10 energy worth of food that day, up to 120. Forge fuel
   can still wait.
7. What does runestone ore become, exactly — carving and imbuing
   steps, waystone and homeward-rune details, and any other uses?
8. What is quartz used for besides selling (crafting, decoration,
   rune work)?
9. Grey slime numbers: HP, damage, counts per floor, and the energy
   cost of `strike` / `flee`. Current values are in Phase 3, still
   open to retune.
10. Later slime types: which colours, and from which floors?
11. What is the one goo recipe?

## Later (after all art is working)

These are parked until the current art and engine work is in and playing
well. Design notes only; not built yet.

- **Orchard.** The hills will be convertible into an orchard later.
  Planting saplings comes with that conversion. This answers the old
  open question about planting in the hills: yes, through the
  orchard, not as a freeform plant-anywhere change now.

- **Rune magic.** Replaces the elevator. Rare runestone ore (see
  Phase 3) can be carved and imbued for (1) tool enchantments —
  Bounty (+1 yield) and Shatter (splash), (2) waystones — attune a
  cleared tile and teleport back to it for a small energy cost, and
  (3) a homeward rune at high levels (teleport home). Details of
  carving, imbuing, and what else runestone ore becomes are still
  open.

- **Cabin interior.** Built. Press E (enter cabin) from the farm cabin
  tile to step into a 3×3 interior, same idea as entering the mine.
  Leaving is from the door tile, back onto the farm cabin tile.
  Walking inside costs no energy. Being anywhere in the interior still
  counts as “in the cabin” for sleep and together rest. Plain E is
  enter/interact; end turn by keybind is Shift+E then Enter.

  Layout, finalized (rows top to bottom, columns left to right):

      (1,1) double bed    (1,2) chest         (1,3) empty floor
      (2,1) free floor    (2,2) free floor    (2,3) fireplace
      (3,1) door          (3,2) kitchen       (3,3) free floor

  The top-right empty tile is reserved for a buildable display case
  later; it stays plain floor in this pass. Fuel the fireplace from
  the fireplace tile, open the cabin chest from the chest tile, and
  cook from the kitchen tile after loading wood from the backpack (one
  load cooks for the day and resets at dawn). The web recipe book is
  shown only at the chest (r1c2) or the kitchen (r3c2). Fireplace fuel
  also comes from the backpack, not straight from the chest. Ending a
  turn anywhere inside is still cabin sleep; players who slept in the
  cabin wake at the double bed (r1c1). The upgraded-bed “well rested”
  bonus stays parked until that upgrade exists. Decorating the home is
  a later follow-on. Storybook art for the floor and furniture
  (including lit/unlit fireplace and stove) is in. Interior tile labels
  use the same r1 c1 style as the farm. The web CABIN CHEST panel is
  shown only while you are inside the interior.

- **Fireplace fuel storage.** An upgrade that keeps wood near the fireplace so you don't have to carry each load from the chest.

- **Propane stove.** A shop-bought stove that cooks without chopping wood; fuel is purchased from the shop instead of loaded from the pack.

- **Tulips.**

- **Yearly wet/dry season variants**, with hints so the year-to-year
  change is readable.

- **Coffee** (+40 energy now, with a sleep penalty). Herbal tea is in
  the shop already: one cup a day, +10 at the next cabin wake.

- **Well rested.** An upgraded bed (not built yet) will give +5 “well
  rested” when you sleep in it above 10 energy. Parked until the bed
  upgrade exists. Together rest (both sleeping in the cabin) is already
  in the engine and is a separate bonus.

