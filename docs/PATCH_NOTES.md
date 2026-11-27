# Patch notes

## 2026-11-27

- The cabin chest is now a window of its own, like the store, with a draggable grid. There is no starting chest: stand at the north-wall nook (row 1 col 2) in the cabin and `build chest` for 5 wood (the first decoration/building). Base size is 12 slots, stacks of 16. Upgrade at the chest with 8 copper ore (24 slots), then 10 iron ore (36), then 12 gold ore (48); each upgrade changes the banding colour. New games put the hoe, shovel, axe, two watering cans, and the starting strawberry seeds on that cabin floor tile. Existing farms that already had a chest are grandfathered as a built wooden chest; if they held more than 12 stacks, the extras stay as overflow and nothing is deleted.
- Legal Actions now lists every action the engine accepts from the tile you stand on (including `move to r c`, `go east`, `go town`, and `go hills` from the farm cabin tile). The show/hide toggle actually collapses and expands, and this browser still remembers it.
- In Settings, ticking “Taking a break from farming” enables “Maximum turns autopassed” and “Time until autopass”; they stay greyed out only while the box is unticked, including after a save or auto-refresh.
- Runner vine leaves are cropped from the painted storybook strawberry plants and always face up. The stem is still drawn along the mother-to-child line, including on the mother's tile.
- Final storybook snow tiles for the hills grass and hillside (and their current painted originals) are in the pack.

- You can drop items on the tile you stand on anywhere except the cabin chest and the market stall (`drop stone 1`, `drop stone all`). `take` or `pick up` retrieves them from that tile, for free, like chest take/drop. Ground piles are listed in look and in the web UI's This tile panel, with a small badge on the map tile. They persist in the save. Items left in the mine are lost when the mine resets (a new season, or any floor regen); farm, hills, and town drops are unaffected. Legacy mine loot left on a tile is folded into the same ground map.
- `take stone all` from the chest (or the stall, or the ground) now takes as many as will fit in the backpack, instead of refusing when the whole pile is too big. Same-item chest stacks merge on load, and an overfilled stack is split instead of truncated.
- `leave cabin` from any interior tile walks you to the door (free, like other moves inside) and steps out onto the farm cabin tile.
- Snow still waters the soil (no drought, tilled beds stay open) but crops do not grow that day, even if you hand-water them. Dormant plants are unaffected. Forecast and look text say so.
- You can have two pickaxes on the farm. The honour store sells another at 40G while fewer than two exist (counting backpacks, chest, ground, and stall). Forging upgrades the pickaxe in your backpack, so each pickaxe has its own tier.
- The web backpack shows Drop 1 / Drop all on every ground tile (chest and stall keep their own buttons). The This tile panel lists ground items with Take 1 / Take all, using display names (sleeping bag, not sleeping_bag). Legal Actions is a fold-away heading, remembered in this browser, collapsed by default (the list now includes every legal move).
- At a season change, anyone still in the mine is moved to the hills mine entrance (sleeping-bag energy is kept). The day-turn log says the mine shifts with the season. Ground piles left in the mine are cleared when it resets.
- Energy-costing actions check energy first and, when you are short, say e.g. "You're out of energy — breaking rock needs 10 and you have 0."
- After winter, an everbearing plant that starts a new fruiting cycle resets its growth, not just the day count, so it no longer jumps from "day 0 of 7, regrowing" to ready in one watered day. Establishing or first-year runner plants no longer send runners of their own.
- Walking off a slime's tile, or breaking a rock on that tile, gives the slime a free hit (8 damage). There is no separate flee action; just walk away. A mid-day faint still uses `hp_faint_energy` (25).
- Mining, chopping, foraging, harvesting, and slime loot with a full pack no longer refuse. Overflow lands on the tile at your feet.
- HP only fills completely after a night in the cabin. A sleeping bag restores HP up to 50 and never lowers it. Passing out overnight keeps your current HP. A mid-day faint at 0 HP restores HP only up to 50 (`away_hp_restore_cap` in `rules.json`).
- Homesickness: each night away from the cabin (bag or pass-out) subtracts 5 energy the next morning, cumulative, capped at −50. A night in the cabin clears it. If both of you sleep on the same mine floor (or the same tile elsewhere), home is where the heart is — no penalty that night. Look and the web view show the current penalty.
- Runner vines are drawn on both the mother and the child tile and meet at the shared edge. The stem is routed in the mother-to-child direction; leaves and sprigs always face up and are never rotated with the stem.
- Settings (top right of the web UI) has “Taking a break from farming.” When it is on and your turn sits idle for the chosen time (default 30 minutes), the farm votes to end the day for you and passes the turn; no other action is taken on your behalf. The other player's usual turn ping still fires. It stops after the maximum (default 3 turns). Any action of yours turns it off and counts as being back, and you get a short “while you were away” summary. Defaults are off. Settings are stored per player on the farm save, never with login tokens, and work the same for any two people.

## 2026-11-26

Rick and Lumen’s first official-project day on Lantern Farm. A full day of engine, art, and cabin work landed on `main`.

### Mine Phase 3

- Grey slimes appear from floor 6 down, never on safe floors. They have 20 HP and deal 8 damage. `strike` and `flee` cost 5 energy and are only available when you stand on the same tile as a slime (not a neighbour). A non-safe floor can have several slimes on different tiles, never the shaft: 0–1 on 6–9, 0–2 on 11–14, 1–2 on 16–19, and 1–3 on 21–24, rolled from the seasonal seed. A strike deals 10 damage to the slime on your tile; the slime hits back unless that blow defeats it. Each defeated slime drops its own goo, which the stall buys for 8G (no recipe yet). At 0 HP you still wake at the hills mine entrance with 25 energy and full HP. Older single-slime saves are migrated. (`b56dbca`, `6ac2d06`)
- Quartz can drop from plain stone rocks on floors 1–4 (15% chance) and sells for 6G. Runestone ore rocks are smooth and rounded: rare on floors 1–4 (3%) and more common deeper (6% / 9% / 12% / 16%). The stall buys runestone ore for 15G. Stand-in Classic SVG sprites are in; a full art pass comes later. (`b56dbca`)
- The elevator is gone. Climb the ladders to travel the mine. `go cabin` from inside is still refused until you climb out to the hills entrance. Ending a turn in the mine now wakes at the hills entrance with 50 energy (pack kept), including when the season changes. Carrying someone out of the mine no longer uses a lift shortcut. Older saves lose elevator tiles on load. (`b56dbca`)
- Climbing down a ladder costs 5 energy (was 10), the same as climbing up. The honour store sells a sleeping bag for 120G. It takes one backpack slot. End your turn with it in your pack, and not in a cabin bed, and you sleep in the bag: you wake on the same tile (including the same mine floor) with 100 energy and no comfort bonuses. Without the bag, a mine pass-out still wakes at the hills entrance with 50 energy. Look and the web UI show the bag and the “You'll sleep in the sleeping bag…” line. (`this change`)
- Typed take/drop commands now accept forged tool display names, so `take copper pickaxe 1` (as shown in the legal-actions list) works, not only `take pickaxe 1`. The same for copper/iron/gold hoes, watering cans, and axes. (`this change`)

### Cabin

- The cabin is now enterable. From the farm cabin tile, E steps into a 3×3 interior (bed, chest, fireplace, kitchen, door). Walking inside costs no energy; being anywhere inside still counts as sleeping in the cabin. Leave through the door, back onto the farm cabin tile. (`b7361e8`, `33592d5`)
- Storybook art for the floor and furniture, including lit and unlit fireplace and stove. Interior tiles use the same r1 c1 labels as the farm. The cabin chest panel is shown only while you are inside. (`4844f73`, `dd7a74f`)
- The bed quilt was repainted: a centered glowing lantern over a green-left / blue-right aurora, with the glitchy pale patch near the pillows removed. The interior door overlay was inset so it sits fully on the door tile. (`a53abfa`)
- Cabin comfort: a fire and a full belly help you wake. Fuel the fireplace from the fireplace tile with wood from the backpack. The stove is also loaded from the pack (one load cooks for the day and resets at dawn). E at an unfueled stove fuels it when you have pack wood; if the stove is already fueled, E opens the recipe book. Fuel fireplace and Fuel stove buttons appear only on the matching tile, and only when they can be used — no greyed-out placeholders. Take/Drop appear only at the chest; Sell only in the cabin. The recipe book is visible only at the chest or the kitchen. (`6d741c7`, `86fa5be`, `49aa396`, this change)
- Cooking uses ingredients from the backpack only, never the chest. If something is missing, the refusal lists it and tells you to take it from the chest first. Recipe have/need counts are backpack counts too. (`this change`)
- The shop only buys jam for now (strawberry jam, wild berry jam, and other jams). Soups, stews, toast, strawberry milk, bread and butter, buttered kabocha, and other cooked meals are not sold. Their prices stay in the data for a later market stall. (`this change`)
- Together rest: when both players sleep in the cabin, each gets +5 energy the next morning. (`dfccb95`)
- After cabin sleep, you wake at the interior bed. Players who passed out still wake where they fell. (`49aa396`)

### Turns and walking

- Pass turn is a same-day hand-off with an optional note; it does not end your day. The line is short: “Rick passes the turn to Lumen.” If you pass while away from the cabin, you are silently marked as waiting (the wait is not announced in the log or status). The other player can carry you to bed from the same tile. There is no separate “pass turn home” action. The note field clears after a pass, the same as after end turn. (`9a1675c`, `49aa396`, this change)
- Carry to bed (formerly “walk X home”) takes both of you to the cabin bed at the same double-movement cost as walking to the cabin door. The log is a short tuck-in line. The old “walk X home” wording still works. (`9a1675c`, this change)
- Ending the turn away from the cabin is a silent request to be carried, the same as passing while away — not only the old carry flag. Carry to bed also works in the mine: stand on the same tile, and it brings them up the ladders and home to the cabin bed at double the usual travel cost. They sleep in the cabin, not as a pass-out. If you don't have the energy, the refusal names the cost. (`this change`)
- End turn is a ready-for-bed vote: it marks you ready and hands the turn over. The day turns only when both players are ready. Passing the turn back clears the recipient’s ready flag so they can act again. Ready state is shown in the web HUD and in CLI look. (`this change`)
- Enter in the note box always ends the turn (and sends a note if you typed one). The Pass turn button passes immediately, including any note already in the box. End turn is also Shift+E, then Enter. (`b7361e8`, this change)
- Dawn and the green web banner are concise. After a day turns, you see a short status (day, season, weather, ready crops, weeds, wake energy, whose turn) rather than the long dawn paragraph. Full detail stays in the log. The banner refreshes when the turn changes (polling or the notify hook), so it shows what the other player just did — their note, a ready-for-bed line, and “Your turn” — not your own stale last action. Waiting to be carried is never announced there. (`this change`)

### Energy and food

- Food never raises energy above the base cap of 100. If you are already at 100 or more, you cannot eat that snack; sell it or save it. Wake bonuses (fire, food, tea, together rest) may still start a day above 100. Eat messages and the HUD show energy against 100. (`33207d5`, `df33828`)
- Herbal tea is in the shop: one cup a day, +10 energy at the next cabin wake. Shop seed cards show growing seasons, remaining days, and the remaining grow window. Forged tool tiers are visible. (`1a0b4cc`, `e082081`)
- Bread splits into halves; eat buttons cover half loaves and foraged snacks. Sugar is in for jam. Foraged goods are unsellable and have their own recipes. (`55e7b38`, `8d2c8f0`, `5349c22`, `74d869f`)

### Hills and the mine

- The hills opened, with growing trees, forage, and Storybook art. Stumps can be unearthed or left to send up a sapling or become a mushroom log for oyster mushrooms. Wood stacks in the pack. (`bb058de`, `2e2f97e`, `55e7b38`)
- The mine opened, with a forge at the cabin, mine actions in the web UI, Storybook mine art, and stone from plain rock. The pickaxe appears in a shop Tools section once the mine is found. (`f22f892`, `4b6c38d`, `74d869f`, `e709e37`)
- Chopping a grown tree always reports a success or a clear refusal (still growing, no axe, pack full). A dawn “grown tall” note matches a tree you can chop. `python3 cli.py chop` works without wrapping the verb in `do`. (`this change`)


### East market town

- A 3×3 market town is east of the cabin tile, unlocked from day 1. Walk east from the cabin (or `go town`) to enter at town row 1 col 1. The stall is row 1 col 2, the honour store row 2 col 1, and the forge row 2 col 3. The rest is grass. Town tiles show the same rN cN labels as the hills; building names stay in the tooltip. (`this change`)
- The stall replaces selling at the cabin. Drop goods into the stall; they sell automatically when the day ends. Spend 50 energy at the stall to sell everything now. The stall takes what the cabin shop used to buy, plus fresh produce, jam, wood, stone, and ore, at the existing prices. Foraged goods and cooked meals other than jam still are not sold. `drop <item> all`, `put all <item> in stall`, and the Put all in stall button all work. Each backpack item has one put-in-stall button (with the later gold hint) plus Put all when you are holding more than one. (`this change`)
- Buying moved to the honour store. There is no shopkeeper: coins come straight from the purse, with a line like “left 20G in the tin.” The pickaxe stays hidden until someone finds the mine entrance. The Shop button and S key open the store only while you are standing on that tile. (`this change`)
- The forge moved from the cabin to town row 2 col 3, with the same upgrade recipes. (`this change`)
- Older saves gain the town on load without changing the day, season, weather, gold, energy, or the current turn. (`this change`)

### Tools

- Forged tool tiers now only change energy: basic 10, copper 8, iron 6, gold 4, for the hoe, watering can, axe, and pickaxe. Iron no longer adds +1 yield, and a gold pickaxe no longer breaks a neighbouring rock. Existing upgraded tools keep their tier. (`this change`)

### Frost and snowy hills

- On a snow day, and on the first morning of winter even if it is sunny, non-hardy annuals are caught by frost. Unripe plants are killed; ripe fruit becomes frost-bitten and can be harvested once, then the spent plant must be cleared. Hardy crops (turnip, radish, carrot, beet, and kabocha) stand the frost and do not wither from winter air alone. Perennials still go dormant for the season. (`this change`)
- Storybook hills on a snow day are mostly snow: a packed-snow path with only sparse edge tufts, a quieter hillside, and bare winter trees, stumps, and mushroom logs with snow on top. Frost-bitten crop sprites were added for the plants frost can bite. (`this change`)
- Withered and frost-bitten plants no longer show “watered today” or the bare-soil “days left until it reverts” countdown. (`this change`)

### Art and UI polish

- Root-crop sprites sit above the tile label. Zucchini fruits each have a blossom at the tip. Missing item icons were added; a red fringe on the sprouting beet was cleaned up. Establishing plants are labeled. (`9499490`, `db08161`, `1b5b352`, `55e7b38`)
- The cabin keeps its weather tile when the fire is lit, with only smoke added. Bonus energy in the HUD is current over the base max. The web Elsewhere block is hidden; the pass-out area is named. Chest order is remembered, and shop/chest grouping was fixed. A legal-command box was added to the page. (`eb081f6`, `df33828`, `8360143`, `dd7a74f`, `021241e`, `4b6c38d`)
