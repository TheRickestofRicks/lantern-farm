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
- Decoration phase for the cabin: a buildable display case at r3c3, rugs, lanterns, and other home decorating. A small dining table is a kitchen upgrade (+5 energy when you eat food at it). The chair is under review (see the floor plan). Cellar stairs go at r1c3 (see Cabin cellar).
- Next week: an action/time-based day-to-night cycle. Each action takes time depending on the action and the tool tier, for example watering is 30 minutes base, 25 with copper, 20 with iron, 15 with gold.
- **First feature next week (Rick, 2026-11-27):** fishing minigame. It waits for next week so it gets built properly instead of squeezed into the end of this week's usage. The centre hills tile becomes a pond. A fishing rod is purchasable (hook and line included), as are bait types with different effectiveness. Bites depend on weather and bait, which affects which fish bite and how often. Overfishing is possible and tracked per species. Late-game activity for both players — one farms and fishes while the other mines, or both fish and camp at the lake.
- Mine depth beyond the first floors.
- Sleeping bag: sleep inside the mine, wake with 50 energy on the same tile without being booted out. It takes a backpack slot (bulky).
- More slime types deeper in the mine (grey slimes from floor 6 are in).
- Fireplace fuel-storage upgrade, so wood can be kept by the fireplace instead of carried from the chest for each load.
- Propane stove, a shop-bought stove that cooks without chopping wood; fuel is purchased from the shop.
- Pantry: see the cooking revamp entry (kitchen upgrade, 10 wood).
- Well-rested bed upgrade (+5 when you sleep in the upgraded bed above 10 energy). Together rest is already in and stays a separate bonus.
- Journal history: the human player can browse journals from previous years in the journal UI, with a “Copy year” / export button that produces a clean text summary of that year to paste to the AI player.
- Further skill uses and fine-tuning of the XP amounts in `rules.json` (granting, the level cap, and the inventory display are in).

## Later

Parked items and leftovers from the design docs (`docs/plan-hills-and-mine.md`, `docs/granular-growth.md`):

- Picking up loose items off the floor costs 1 energy per item (Rick, 2026-11-27; was 5 energy). Dumping a whole pack becomes costly, so a chest is worth building, but grabbing a few things early barely hurts.
  - New games start with a piece of bread to share, to offset part of the early pickup cost.
- Week 2 of development (Rick, 2026-11-27): unique tools, so upgrades apply to each tool rather than farm-wide. For a challenge.
- A mobile-friendly version of the web UI.
- Sound effects and background music (Rick, 2026-11-27): what a real game has.
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
- Open question: a 30-minute nap in bed gives +15, so the chair needs its own niche (usable while the bed is taken, or a cozy bonus by the fire) or becomes decoration only.
- The table is now the small dining table, a kitchen upgrade (see Cabin cellar).

## Idea: basic crafting table first (Rick, 2026-11-27)
- Today the creation table is free from the start. Later, start with a plain basic crafting table instead, and unlock the creation table as an upgrade to it.
- Sprite idea: `docs/art-ideas/basic_crafting_table.png`, a wooden bench with a hammer-and-chisel tool box, a lantern and a small copper nugget. It hints that ore exists but shows nothing magic, so enchanting stays a surprise.

## Idea: seed potatoes (Rick, 2026-11-27)
- Harvested potatoes can be saved and replanted as seed potatoes the next year, so a good harvest feeds next spring's planting.

## Idea: cooking revamp (Rick, 2026-11-27)
- Cooking moves into its own window instead of the sidebar.
- Recipe search inside that window.
- Pantry: a kitchen upgrade built for 10 wood that adds storage to the kitchen. Cooking pulls ingredients from the pantry automatically, so they don't have to be in the backpack.

## Idea: more runestones (Rick, 2026-11-27)
- Raise the base runestone drop to 1–3 per drop. Runes are meant to be plentiful, since spells, altars, crafting and slime friends all use them.
- Not now: we play with the current rate for a while first.

## Idea: cabin floor plan (Rick, 2026-11-27)
- r2c1: the rug spot.
- r3c3: the keepsake display case, as a later upgrade.
- r1c3: stairs down to the cabin cellar.
- r3c2 (kitchen): the small dining table is a kitchen upgrade, not its own tile.
- Superseded 2026-11-27 by the agreed cellar layout: the table at r3c3 and the display case at r1c3.
- The comfort idea folds into napping in bed: trade time (part of the day) for energy.
- Open question (Lumen): how much time a nap costs once the action-time day/night cycle exists, and whether the rug adds a small cozy bonus to it.

## Idea: day length, sleep debt and naps (Rick, 2026-11-27)
- Days run from 5:30 to 21:30.
- Staying up past 21:30 costs energy the next day.
- Staying up too long makes you sleep in and builds sleep debt: a stacking debuff that lasts until the sleep is paid back.
- Napping in bed pays sleep back: 30 minutes for 15 energy, or 1 hour for 30 energy.
- An early night (going to bed before 21:30) also pays back some sleep debt, so a busy week can't spiral (agreed 2026-11-27).
- Open questions (Lumen): how much energy each late hour costs; whether debt is paid back by early nights, naps, or both; and whether the rug or fire gives naps a small bonus.

## Idea: action-time day-to-night cycle (Rick, 2026-11-27)
- Next week: the day should move from day to night by the time actions take, not only by ending a turn.
- Each action takes time depending on the action and the tool tier. Example: watering is 30 minutes base, 25 with a copper watering can, 20 with iron, 15 with gold.

## Idea: magic system (Rick, 2026-11-27)
- A big future system built on runes. Enchanting is in; teleportation (waystones, homeward rune) is planned.
- Healing spells. Purpose: make adventuring together, passing turns back and forth, a viable play style (healing can target the other player).
- Offensive ranged spells that cost runes (for slimes and the deeper mine).
- Pits to Plums (silly spell, named after RuneScape's Bones to Bananas): turns all stone in your backpack into plums.
- Speak with Creature (see befriending slimes) also belongs here. Lumen's suggestion: imbued rune kinds from the altars could fuel different schools of spells.

## Idea: keepsake display case (Rick, 2026-11-27)
- Built from 5 wood at cabin r3c3 (moved from r1c3 for the cellar stairs), opened like the chest.
- Keepsakes are exempt from spoilage.
- Holds one item per slot (no stacks). Each slot has a placard for its item.
- Each keepsake logs when it was picked up and by whom (e.g. "first runestone, found by Lumen, Day 12").

## Idea: rune altars in the mine (Rick, 2026-11-27)
- A rune altar on every 5th mine floor.
- Generic runestones cut at the Creation Table are imbued at an altar into different kinds of rune.
- Imbued runes are also crafting ingredients and add progression. Lumen's suggestion: deeper altars give stronger kinds (for example earth on floor 5, frost on 10, tide on 15, tying into fishing).

## Idea: befriending slimes (Rick, 2026-11-27)
- Slimes become capturable later through a "Speak with Creature" spell that costs runestones (possibly a specific imbued kind).
- Lumen's suggestion: befriended slimes live in a small pen in the hills, and each colour gives something (for example green goo as fertilizer, grey for ore luck).

## Idea: flowers as gifts (Rick, 2026-11-27)
- A "give item" action specific to flowers: giving a flower to the other player gives them 5 comfort, at most once per day.
- Flowers expire (wilt) so they can't be stockpiled or gamed.
- Vases: a flower in a vase gives the receiver +5 for 3 days.
- Pairs with decorative trees and hanami as reasons to grow pretty things.
- "Comfort" here means energy that comes from something other than food or rest.
- Prairie crocuses are a wild bloom in the hills (Lumen's favourite flower), an early spring forage that can be given as a gift.

## Idea: hill orchard (Rick, 2026-11-27)
- Trees are purchasable, so players can plant an orchard in the hills.
- Cuttings can be taken from trees and planted; they grow faster than wild trees.
- Tree kinds: maple (tappable for syrup), apple, cherry, and pear.
- Cherry blossoms (hanami): while cherries bloom, resting under them together gives +25 energy, once per day.
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

## Party play and the mailbox (idea, 2026-11-27)
- Human/human multiplayer should support 1 to 4 players total, so it can work as a party game.
- With 3 or 4 players, "Note for Lumen" becomes "Note for everyone" (the shared end-of-turn note).
- A mailbox stands outside the cabin for letters to specific players. Standing at it gives a legal move "leave letter to <player>" that opens a text box, and "read mail" when you have mail.
- Agreed with Rick (2026-11-27): letters arrive at the next day turn, like real post, so they feel different from instant notes. The mailbox sprite raises a little flag when someone has unread mail. Maybe let a letter carry one small gift item from the backpack.

## Cabin cellar (agreed with Rick, 2026-11-27)
- Floor plan change: stairs down to the cellar at r1c3 (replacing the display case there). The display case moves to r3c3. The table becomes a small dining table, an upgrade on the kitchen tile (r3c2), instead of its own tile.
- The cellar is a small, dark, lantern-lit room under the cabin, with a lantern hook by the stairs.
- Casks for making non-alcoholic cider (and later other cask goods like apple vinegar or fruit cordial).
- Drying racks for fish, mushrooms and fruit.
- Mushroom logs or beds growing only what's realistic to cultivate in a basement (oyster, shiitake, button/cremini, lion's mane).
- Root bins plus extra storage slots, to take pressure off the chest.
- Gentle spoilage: depending on the item, after a while it sells for less, and after longer it decays entirely. Root bins and the cellar slow it down; dried, pickled and cask goods keep much longer.
- A preserves shelf in the dark that pickles (and jam/honey jars) actually require, tying into the cooking revamp and the pantry.

## Rings, jewellery and the moon (agreed with Rick, 2026-11-27)
- New jewellery slots: two ring slots (two ring fingers) and one necklace slot. The second ring and the necklace hold magic bonuses, to be decided together later (keep them small and cozy, e.g. a lantern pendant that lights the mine).
- Partner rings: a matching pair carved from runestone at the Creation Table, only on an aurora night, and only when both players are in the cabin. Each player has to accept their ring, so a partnership is always mutual. Either can take theirs off any time and the bonus simply stops.
- Wearing a partner ring gives the partner bonuses (sleeping close, homesickness waiver, hanami, etc.), but only when the partners share a tile or floor, so it rewards being together.
- This answers the 3-4 player "both" question: partner mechanics apply to whoever wears the matching ring. In a 3-player game any two can pair up.
- Beds (Rick): the cabin starts with a bunk bed. The double bed is a cabin upgrade. With matching partner rings it enables the sleeping-close bonus; without rings it just works as a two-person bed.
- Ring of self-reliance: for solo games and players without a partner. A flat passive +20 energy cap. Carved alone at the Creation Table on a new moon night. It can't be worn alongside a partner ring; take it off to accept one later.
- Moon cycle: 5 days per cycle, one phase per day (new moon, waxing, full moon, waning, dark crescent), so 3 full cycles per 15-day season. New and full moons can gate rare crafts and events (night foraging, mushroom flushes on the full moon).

## Recipe gaps (audit 2026-11-27, design only; pick recipes together next week)
- 15 of 20 crops have no recipe: radish, lettuce, spinach, pea, beet, potato, bush bean, cucumber, zucchini, tomato, pumpkin, corn, onion, rhubarb, asparagus. Everbearing berries make jam but not strawberry milk (it asks for `strawberry` exactly).
- Rhubarb's description says to cook the stalks or make jam, but neither exists. First fixes: rhubarb jam and strawberry-rhubarb jam.
- Pumpkin soup already has storybook art (`items/pumpkin_soup.png`) and no recipe.
- Grown onions can't make onion soup. Pool onion with wild onion, the same way berries (`JAM_BERRY_ITEMS`) and mushrooms (`SOUP_MUSHROOM_ITEMS`) are pooled.
- Safety net: a pooled garden vegetable soup (any 3 vegetables + milk) and a garden salad (any 3 greens), so no crop is ever an orphan. Special recipes add character on top.
- New cellar mushrooms (shiitake, cremini, lion's mane) join the mushroom soup pool.
- Staples to add, in order: flour (pies, crumble, zucchini bread), eggs, cellar vinegar (pickles for cucumber, beet, radish, onion), salt.
- Winter: only carrot grows, so root bins and the overwintering crops need winter dishes (e.g. creamed spinach, onion soup).

## Small quality-of-life ideas (2026-11-27)
- Keybind: E opens the chest when standing at it (Rick).
- Emoji shortcodes in notes and letters: `:green_heart:` becomes 💚 automatically, just for fun (Rick).

## Open design questions (2026-11-27)
- How homesickness and sleep debt interact: does a sleeping-bag night count as real sleep, does sleeping together on a mine floor waive sleep debt too, and does a cabin nap clear homesickness?
- With 3 or 4 players, mechanics written for "both" or "the other player" (homesickness waiver, sleeping close, hanami, flowers, healing) need a rule. Partly answered by partner rings (see Rings section); still decide flowers and healing.
- Food storage: decide what the pantry, root bins and preserves shelf each hold before building any of them.

