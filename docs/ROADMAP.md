# Lantern Farm roadmap

Rick and Lumen made Lantern Farm an official project.

## Goal

Finish Year 1: all four seasons playable, then settle into daily play sessions.

## Now

Year 1 winter is in play. See Next for the remaining season work.
The east market town is in: stall, honour store, and forge, east of the cabin.

## In (2026-11-27)

- Creation Table at cabin row 2 col 2, free to build. Craft runestones from runestone ore any day (1 ore, 5 energy).
- Inventory window (I, and a button left of Chest): clothes, boots, and hands plus the four general backpack slots. Art style lives in Settings. Leather boots are equipped on migrate so walking still costs 5. The cabin chest now costs 5 wood and 25 energy to build.
- Hiking boots (50G at the honour store) cost 4 energy in the hills and the mine. Nimble (overall level 10, 10 runestones, 100 energy, Creation Table on an aurora night) subtracts 1 from a paid step; cabin walking stays free.
- Cosmetic clothes via `starting_clothes` in the player config. Lumen starts in a blue sweater; the other farm player can start in a green hoodie the same way.
- XP is granted from the `xp` table during play. Skill levels cap at 10; overall level uses the same thresholds on total XP. Progress is shown in the inventory window.
- Aurora nights: very rare clear weather in autumn and winter only, always forecast accurately, cheap veil over the map.
- Pickaxe Improved Yield and Superior Yield, worked at the Creation Table on aurora nights.

## Next

- Winter season, as Year 1 continues toward all four seasons being playable.
- Proposed: overwintering crops (garlic, spinach, kale, winter onion; wild onion planted in autumn sleeps through winter and wakes in spring).
- Decoration phase for the cabin: a buildable display case on the reserved interior tile (r1c3), rugs, lanterns, and other home decorating. Constructable decorations include a table (+5 energy when you eat food at it) and a chair (+10 energy for 30 minutes of time).
- Next week: an action/time-based day-to-night cycle. Each action takes time depending on the action and the tool tier, for example watering is 30 minutes base, 25 with copper, 20 with iron, 15 with gold.
- **First feature next week (Rick, 2026-11-27):** fishing minigame. It waits for next week so it gets built properly instead of squeezed into the end of this week's usage. The centre hills tile becomes a pond. A fishing rod is purchasable (hook and line included), as are bait types with different effectiveness. Bites depend on weather and bait, which affects which fish bite and how often. Overfishing is possible and tracked per species. Late-game activity for both players — one farms and fishes while the other mines, or both fish and camp at the lake.
- Mine depth beyond the first floors.
- Sleeping bag: sleep inside the mine, wake with 50 energy on the same tile without being booted out. It takes a backpack slot (bulky).
- More slime types deeper in the mine (grey slimes from floor 6 are in).
- Fireplace fuel-storage upgrade, so wood can be kept by the fireplace instead of carried from the chest for each load.
- Propane stove, a shop-bought stove that cooks without chopping wood; fuel is purchased from the shop.
- Pantry: a cabin upgrade beside the stove that cooking can draw ingredients from.
- Well-rested bed upgrade (+5 when you sleep in the upgraded bed above 10 energy). Together rest is already in and stays a separate bonus.
- Journal history: the human player can browse journals from previous years in the journal UI, with a “Copy year” / export button that produces a clean text summary of that year to paste to the AI player.
- Further skill uses and fine-tuning of the XP amounts in `rules.json` (granting, the level cap, and the inventory display are in).

## Later

Parked items and leftovers from the design docs (`docs/plan-hills-and-mine.md`, `docs/granular-growth.md`):

- A mobile-friendly version of the web UI.
- Swords or other weapons for fighting slimes, and clothing or armor equipment slots. HP is meant as a progression gate even with the sleeping bag.
- Converting the hills into an orchard with purchasable trees (see "Idea: hill orchard" below).
- Tulips.
- Yearly wet/dry season variants, with hints so the year-to-year change is readable.
- Coffee (+40 energy now, with a sleep penalty). Herbal tea is already in the shop.
- Open questions from granular growth: mixed jam berries, fertilizer prices after a season of play, and the pack stack cap.
- Winter market stall or special order board that occasionally buys a cooked meal.
- The rest of the rune system: Shatter (splash mining), waystones (attune a cleared tile and teleport back for a small energy cost, replacing the removed elevator), and a homeward rune at high levels. Runestone crafting and the first pickaxe yield enchants plus Nimble are already in at the Creation Table.

## Idea: snow days pause plant growth (Rick, 2026-11-26)
- On snow days, crops don't advance a growth stage (growth is paused, not lost).
- Open questions: does watering still count/carry over? Do greenhouse or indoor plants ignore it? Show a "snowed in — growth paused" note on affected tiles.

## Idea: plants going to seed + seed maker (Rick, 2026-11-27)
- Mature crops left unharvested can go to seed.
- A seed maker (like Stardew's), crafted for 5 stone and 20 wood, turns a crop into seeds.
- Suggestions: it takes about a day to finish so it fits turns; a small chance of a bonus seed; plants left long may flower first.
- Open questions: how many seeds per crop? Does going to seed replace the harvest (you lose the crop)? How many days after mature until it flowers or goes to seed? Where does the seed maker live (cabin, farm)? Can it take any harvested crop, or only ones that went to seed on the plot?

## Idea: constructable table and chair (Rick, 2026-11-27)
- Cabin decorations you can build: a table and a chair.
- Eating food at the table gives +5 energy.
- Sitting in the chair gives +10 energy for 30 minutes of time.

## Idea: action-time day-to-night cycle (Rick, 2026-11-27)
- Next week: the day should move from day to night by the time actions take, not only by ending a turn.
- Each action takes time depending on the action and the tool tier. Example: watering is 30 minutes base, 25 with a copper watering can, 20 with iron, 15 with gold.

## Idea: hill orchard (Rick, 2026-11-27)
- Trees are purchasable, so players can plant an orchard in the hills.
- Open to decide when we scope it: which trees, where they're sold, what they cost, how long they take to grow, what they yield by season, and which hills tiles can take one.

## Idea: fishing minigame (Rick, 2026-11-27)
- The centre hills tile becomes a pond.
- A fishing rod is purchasable (hook and line included), as are bait types with different effectiveness.
- Bites depend on weather and bait type, which affects which fish bite and how often.
- Overfishing is possible and tracked per species.
- Purpose: late-game activities for both players — one farms and fishes while the other mines, or both fish and camp at the lake.

## In: skills / XP (Rick, 2026-11-27; granted 2026-11-27)
- Experience amounts live in one `xp` table in `rules.json` so they are easy to tune. They are granted during play, with skill levels capped at 10 and overall level taken from total XP.
- Mining XP differs per rock: plain stone 2, copper ore 5, iron ore 8, gold ore 12, runestone ore 15. A +5 bonus applies when a gem drops (today that is quartz from plain stone on floors 1–4).
- Woodcutting: 5 XP per tree chopped.
- Farming: 1 XP per plant and 4 XP per harvest. Watering gives 0.
- Combat: 10 XP per slime.

## In: chest redesign (Rick, 2026-11-27; built 2026-11-27)
- The chest is its own window, like the store, with a draggable grid of rows and columns. You can drag to rearrange slots and drag between the backpack and the chest.
- Build one in the cabin at the north-wall nook (row 1 col 2) for 5 wood. That is the first decoration/building mechanic. There is no starting chest.
- Starting size: 12 slots in 1 row, stacks of 16 (double the pack's 8). Numbers live in `rules.json` (`chest.build`, `chest.tiers`).
- Upgrades go copper (8 copper ore, 24 slots), then iron (10 iron ore, 36 slots), then gold (12 gold ore, 48 slots). Each change also rebands the chest.
- New games start with the hoe, shovel, axe, two watering cans, and the starting strawberry seeds as ground drops on that same cabin tile.
- Existing farms that already had a chest are grandfathered as a built wooden chest. If they held more than 12 stacks, the extras stay as overflow (nothing is deleted; the chest is not auto-upgraded).

## In: sleeping-bag homesickness (Rick, 2026-11-27; built 2026-11-27)
- A penalty so the sleeping bag isn't nearly free. "Home is where the heart is."
- Each night slept away from the cabin (sleeping bag or passing out) reduces next-morning energy by 5, cumulative, capped at −50. Numbers live in `rules.json` (`homesickness.energy_penalty`, `homesickness.max_penalty`).
- A night in the cabin clears it.
- If both players sleep on the same mine floor the same night (or on the same tile elsewhere), neither takes the penalty that night and the counter stays put.
- Homesickness is shown on the look status line and in the web view (e.g. homesick −15).

## Bag of holding (idea)
- Backpack upgrade from 4 to 8 slots, called the "bag of holding", unlocked with rune enchantments.
