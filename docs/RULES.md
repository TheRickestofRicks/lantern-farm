# Lantern Farm rulebook

Numbers come from `rules.json`; if they change, update this file.

This is the plain-language rulebook for Rick and Lumen. It describes how the game works today. Planned work belongs in [ROADMAP.md](ROADMAP.md). Open bugs belong in [BUGS.md](BUGS.md).

A new farm starts on day 1 of spring, with 80G and two June-bearing strawberry seeds. Both players begin in the cabin, on the starting player's turn, at 100 energy and 100 HP.

---

## Turns and day turning

Two players share one farm and take turns. You can only act on your turn.

**End turn** marks you ready for the night. If the other player is already ready, the day turns: evening growth happens, then a new day dawns, and it becomes the starting player's turn again. If they are not ready yet, the turn passes to them and you stay where you are. A player who has already ended can still take the turn back if the other player **passes**.

**Pass** hands the turn to the other player without ending your day. You can keep acting later.

Ending or passing your turn away from the cabin is a silent request to be carried home, unless you are carrying a sleeping bag (the bag is treated as a plan to sleep where you stand). To carry someone, stand on the same tile and carry them to bed. The walk home costs double the usual travel energy, including the climb out if they are in the mine. They are tucked into the cabin bed for free once you reach the door. A carried player still counts as having slept in the cabin.

`go cabin` does not work from inside the mine. Climb out first.

---

## Energy costs

Base energy to wake in the cabin is 100. Comfort bonuses can raise that (see Sleep). Most work spends energy from that pool.

| Action | Energy |
|---|---|
| Step (farm, hills, mine, or town; diagonals count) | 5 (see Movement) |
| Walk inside the cabin | 0 |
| Till, water, chop, or break rock | 10 at a basic tool; 8 copper, 6 iron, 4 gold |
| Plant | 10 |
| Pluck a weed, forage, fertilize, unearth a farm plot, strike a slime, craft, forge, fuel the fireplace or stove, craft a runestone | 5 |
| Unearth a hills stump or mushroom log | 20 |
| Enter the mine, climb down, or climb up | 5 |
| Build the chest | 25 |
| Upgrade the chest | 5 |
| Rest at a mine lantern | 0 (restores 25; see The mine) |
| Enchant (Improved Yield) | 50 |
| Enchant (Superior Yield or Nimble) | 100 |
| Harvest, buy, sell (overnight stall), take, drop, eat, drink, end turn | 0 |
| Sell now at the stall | 50 |

Planting always costs 10. Only till, water, chop, and breaking rock get cheaper as the matching tool is upgraded at the forge.

A gold hoe also tills one neighbouring farm plot, if there is one that needs it. A gold watering can also waters one neighbouring plot that is still dry. A gold axe also chops one neighbouring grown tree, if your pack has room for the wood.

If an action costs more energy than you have, it does not happen.

---

## Movement

Leather boots (your starting pair) cost 5 energy per step everywhere except inside the cabin, which is always free.

Hiking boots (50G at the honour store) cost 4 per step in the hills and the mine, and 5 on the farm and in town. Cabin walking stays free.

A Nimble enchant on the boots you are wearing subtracts 1 from each paid step. It does not change the free cabin walk.

`move to <row> <col>` follows the shortest path, including diagonals, and charges each step.

---

## Sleep, passing out, and HP

Everyone has 100 HP. Energy and HP are separate.

**Sleeping in the cabin.** Ending your turn anywhere inside the cabin is cabin sleep. You wake at the bed. Energy starts at 100, plus any comfort bonuses from last night, and HP fills to 100. A night in the cabin also clears homesickness.

Comfort bonuses only apply to a night spent in the cabin, and they stack:

| Bonus | Extra energy next morning | How you earn it |
|---|---|---|
| Fire | +10 | Fuel the fireplace (stand at it, 5 energy, 1 wood in the backpack) |
| Fed | +10 | Eat at least 10 energy worth of food that day (two small snacks, or one heartier one) |
| Tea | +10 | Drink one herbal tea that day (`drink herbal tea`). One cup per player per day. |
| Sleeping close | +5 | Both of you end the night in the cabin, and anyone who was not carried home still has more than 10 energy. A player who was carried home still qualifies. |

The morning cap can reach 135 (100 + 10 + 10 + 10 + 5). The fireplace and the stove both go out at dawn. Wood is spent when you fuel them, not at dawn. The stove is for cooking, not for the fire bonus.

**Sleeping bag.** The honour store sells a sleeping bag for 120G. If it is in your backpack and you end the turn outside the cabin, you sleep in it: same spot (including a mine floor), 100 energy, no comfort bonuses. HP is restored up to 50, and already-higher HP is left alone. A season change still evicts everyone in the mine to the hills entrance, bag or not.

**Passing out.** End the turn away from the cabin without a sleeping bag, and you pass out where you fell, waking with 50 energy. HP is unchanged. Passing out in the mine wakes at the hills mine entrance with 50 energy (pack kept), unless you had a sleeping bag and the season did not change.

**Mid-day faint.** If HP reaches 0 (usually from a slime), you faint immediately, wake at the hills mine entrance with 25 energy, and HP is restored only up to 50. The pack is kept.

---

## Homesickness

Each night spent away from the cabin (sleeping bag or passing out) adds a −5 energy penalty the next morning. It stacks, and it is capped at −50. A night in the cabin clears the stacks.

The penalty is subtracted after your wake energy is set, so a sleeping-bag night away currently wakes you at 95 on the first night, then 90, and so on. A first-night grace (a clean 100) is on the bug list; it is not in the game yet.

**Home is where the heart is.** If both of you sleep away from the cabin on the same mine floor (even on different tiles), or on the exact same tile elsewhere, neither of you takes the penalty that night, and the stacks stay as they are. They are not cleared until you sleep in the cabin.

---

## Weather and forecast

Each season has its own mix of weather. Rain, storms, and snow are wet: at dawn they water every farm plot. Snow also pauses growth that day — the soil stays wet, there is no drought, and empty tilled plots stay open, but crops put on no growth, even if you hand-water them. Dormant plants are unaffected. Sun, cloud, and aurora leave the soil as you left it.

Odds out of 100:

| Season | Sun | Cloud | Rain | Storm | Snow | Aurora |
|---|---|---|---|---|---|---|
| Spring | 25 | 20 | 50 | 5 | 0 | 0 |
| Summer | 55 | 15 | 10 | 20 | 0 | 0 |
| Autumn | 26 | 28 | 30 | 10 | 4 | 2 |
| Winter | 20 | 20 | 8 | 0 | 50 | 2 |

The 7-day forecast is made fresh each morning. Tomorrow is right 90% of the time. That chance falls in a straight line to 50% on day 7. Misses are expected; they are not a bug.

Aurora nights are always forecast accurately, and they never appear as a mistaken forecast for some other day. An aurora is a clear night, made for work at the Creation Table.

On a snow day, and again on the first dawn of winter, frost hits annuals that are not frost-hardy. A ripe plant becomes frost-bitten (you can harvest the fruit once, then clear the plant). An unripe plant withers. Perennials and frost-hardy crops are safe. Frost-hardy crops are turnip, radish, carrot, beet, and kabocha. Pumpkin is not frost-hardy.

---

## Crops and growth

The farm is a 3×3 grid. The top-right tile (row 1, column 3) is the cabin. The other eight tiles are plots. You can only till, plant, water, harvest, pluck, fertilize, or unearth the plot you are standing on.

A crop puts on growth in the evening only if it was watered (or rained or snowed on) that day, and only if the weather does not pause growth. Growth fills a 0–100 bar. You can harvest a little early, once growth reaches the crop's threshold (70 for most crops, 75 for carrot, 60 for kabocha and pumpkin). A healthier, more fully grown plant is more likely to give the high end of its yield range. A legal harvest is always at least 1.

Watered plants gain a little health. Dry plants lose health. After a long drought, a plant that is already struggling can wither (six dry days and health at 20 or below, or health at 0). Annuals left out of season also suffer, and they wither after three off-season evenings. Weeds never kill a crop on their own.

**Weeds.** At dawn, 1 or 2 new weeds sprout on tilled or planted plots. Pluck one the same day (5 energy) or, at the next dawn, the plot grows weedy: growth is halved and the plant loses more health. Plucking clears both the weed and the weedy state.

**Till hold.** An empty tilled plot stays open for 5 days. Watering it, or a wet dawn, resets that timer.

**Fertilizer.** The honour store sells three bags in spring and summer: general (15G), yield-boost (25G), and growth-boost (20G). Feed a plot with `fertilize` while the bag is in your backpack. One bag per plot per season. General gives a small harvest bump, and +10 health when you apply it to a living plant. Yield-boost gives a stronger harvest bump. Growth-boost makes a watered plant put on growth faster (one and a half times the usual step).

**Runners.** June-bearing and everbearing strawberries may send a runner into an orthogonally adjacent tilled, empty plot. Each plant has a 10% chance each active day, at most once per plant per season.

**Perennials.**

- June-bearing strawberries take 7 watered days to establish, do not fruit until the spring after their first winter, then fruit every 7 watered days through spring into the first 5 days of summer. They rest in autumn and winter (no water needed, no wither), live 8 seasons (about two years), and may send runners. A berry sells for 25G and snacks for +30.
- Everbearing starters settle in 4 watered days and fruit in the planting year, every 7 days from spring through summer into the first 5 days of autumn, then rest only in winter. They live 8 seasons and send runners the same way. A berry sells for 18G and snacks for +20.
- Rhubarb and asparagus crowns settle in 10 watered days, fruit after their first winter, in spring, then again every 6 days (rhubarb) or 5 days (asparagus) while in season. Rhubarb lives 12 seasons; asparagus lives 16. Rhubarb is not eaten raw. Asparagus snacks for +10.

Regrowing crops (peas, beans, cucumbers, and the like) reset after a harvest and fruit again in the listed regrow days, if they are still in season.

---

## Seasons

Each season is 15 days. A year is 60 days.

| Season | Days |
|---|---|
| Spring | 1–15 |
| Summer | 16–30 |
| Autumn | 31–45 |
| Winter | 46–60 |

Winter starts on day 46.

---

## Shop, stall, and prices

Walk east from the cabin to town. You arrive at row 1, column 1. The market stall is row 1, column 2. The honour store is row 2, column 1. The forge is row 2, column 3.

Buy at the honour store, standing on that tile. Coins come straight from the purse. Sell at the stall: drop goods there and they sell overnight when the day ends, or `sell now` for 50 energy. The stall does not buy foraged goods, or cooked meals other than jam. Leftover unsellable goods stay in the stall.

The shop sells a seed when the days left in this season, plus the following consecutive growing seasons, are enough for that crop to finish (planting today still gets tonight's growth). Perennial starters and crowns use a fixed shop-season list instead of that window: everbearing starters in spring and summer, rhubarb and asparagus crowns in spring. Staples, the sleeping bag, and hiking boots are year-round. Fertilizer is spring and summer only. A pickaxe (40G) appears after someone finds the mine entrance, and the farm may have up to two.

Annual shop windows today (day of the season, inclusive):

| Crop | Grow days | Buy | Sell | Eat | Yield | Grows in | Shop window |
|---|---|---|---|---|---|---|---|
| June-bearing strawberry | 7, then every 7 | 15G | 25G | 30 | 1–3 | Spring, summer | Spring; summer days 1–9 |
| Everbearing strawberry | 4, then every 7 | 40G | 18G | 20 | 1–3 | Spring, summer, autumn | Any day of spring or summer |
| Turnip | 9 | 8G | 22G | 12 | 1–2 | Spring, autumn | Spring and autumn, days 1–7 |
| Radish | 4 | 6G | 14G | 8 | 1–3 | Spring, autumn | Spring and autumn, days 1–12 |
| Lettuce | 7 | 7G | 18G | 8 | 1–2 | Spring, summer, autumn | Spring, summer; autumn days 1–9 |
| Spinach | 6 | 7G | 16G | 8 | 1–2 | Spring, summer, autumn | Spring, summer; autumn days 1–10 |
| Pea | 10, then every 4 | 12G | 15G | 8 | 1–3 | Spring, summer | Spring; summer days 1–6 |
| Carrot | 12 | 12G | 32G | 10 | 1–2 | All year | All year |
| Beet | 11 | 10G | 24G | 12 | 1–2 | Spring, summer, autumn | Spring, summer; autumn days 1–5 |
| Potato | 14 | 14G | 20G | 12 | 2–3 | Spring, summer | Spring; summer days 1–2 |
| Bush bean | 10, then every 4 | 11G | 16G | 8 | 1–3 | Spring, summer | Spring; summer days 1–6 |
| Cucumber | 11, then every 3 | 13G | 20G | 10 | 1–2 | Spring, summer | Spring; summer days 1–5 |
| Zucchini | 9, then every 3 | 13G | 18G | 12 | 1–2 | Spring, summer | Spring; summer days 1–7 |
| Tomato | 14, then every 4 | 16G | 22G | 12 | 1–3 | Spring, summer, autumn | Spring, summer; autumn days 1–2 |
| Kabocha | 30 | 20G | 50G | 25 | 1–2 | Spring, summer, autumn | Spring; summer day 1 only |
| Pumpkin | 33 | 18G | 45G | 20 | 1–2 | Spring, summer, autumn | Spring days 1–13 |
| Corn | 28 | 14G | 24G | 14 | 1–2 | Spring, summer, autumn | Spring; summer days 1–3 |
| Onion | 31 | 9G | 20G | 8 | 1–2 | Spring, summer, autumn | Spring only |
| Rhubarb crown | 10 to settle, then every 6 | 25G | 28G | — | 1–3 | Spring, summer | Any day of spring |
| Asparagus crown | 10 to settle, then every 5 | 30G | 32G | 10 | 1–3 | Spring, summer | Any day of spring |

Tomato seeds are still sold on autumn days 1–2, but the first snow (or the first winter dawn) can kill a non-hardy tomato. That mismatch is on the bug list.

**Staples, year-round:**

| Item | Buy | Sell | Eat |
|---|---|---|---|
| Bread | 8G | 4G | 5 (a loaf splits; a half-loaf is also 5, and is not sold) |
| Butter | 10G | 5G | 6 |
| Milk | 8G | 4G | 8 |
| Sugar | 5G | 2G | — |
| Herbal tea | 15G | 7G | drink for the +10 morning bonus |

**Materials the stall will buy:** wood 4G, stone 1G, copper ore 8G, iron ore 12G, gold ore 20G, quartz 6G, runestone ore 15G, a finished runestone 20G, slime goo 8G. Unused seeds sell back for half their shop price, rounded down.

You may eat up to two snacks a turn, from the backpack. Eating spends the item instead of selling it.

---

## Chest and backpack

Each player has a 4-slot backpack. Ordinary items stack to 8 in the pack. Tools, clothes, boots, and a sleeping bag each take their own pack slot (stack of 1). Harvest goes into the backpack.

There is no starting chest. The hoe, shovel, axe, two watering cans, and the starting strawberry seeds begin on the cabin floor at row 1, column 2. Stand there and `build chest` for 5 wood (25 energy). A wooden chest has 12 slots, in one row of 12, with stacks of 16.

Upgrade the chest at the chest tile (5 energy), paying ore from the backpack or chest:

| Tier | Ore cost | Slots |
|---|---|---|
| Wood (built) | 5 wood to build | 12 (1×12) |
| Copper | 8 copper ore | 24 (2×12) |
| Iron | 10 iron ore | 36 (3×12) |
| Gold | 12 gold ore | 48 (4×12) |

`take` and `drop` at the chest move stacks between the backpack and the chest. Anywhere else except the stall, `drop` leaves items on the tile, and `take` or `pick up` retrieves them. Items left in the mine disappear when the mine resets. Drops on the farm, in the hills, and in town stay put.

---

## Tools and the forge

Starting tools: 1 hoe, 2 watering cans, 1 shovel, 1 axe. A pickaxe is bought after the mine entrance is found, up to two on the farm.

Till needs the hoe in your backpack. Water needs a watering can. Unearth needs the shovel. Chop needs the axe. Breaking rock needs the pickaxe.

Upgrade the hoe, watering can, axe, or pickaxe at the town forge (stand there, 5 energy, 5 ore of the next tier). The order is copper, then iron, then gold. Use cost becomes 8, then 6, then 4. Forge tiers do not add extra yield; pickaxe enchants do (see Runestones).

---

## The hills

Walk north from the cabin to a second 3×3: the hills. You arrive at the bottom-right hill (row 3, column 3). Walk south from that tile to come home.

Trees grow on their own: sapling (3 days) to young (4 days) to grown. `chop` a grown tree for 2 wood. The stump sits for 4 days; one in three stumps becomes a mushroom log, and the rest send up a new sapling. Unearth a stump (20 energy, shovel) for 1 wood, leaving plain grass that will not resprout. A mushroom log gives no wood when unearthed.

Mushroom logs last one year (60 days). Every 3 days in season they may sprout oyster mushrooms. Oyster mushrooms (and wild autumn mushrooms) are not safe to eat raw; cook them into mushroom soup.

Wild plants can be foraged (5 energy) in season, 0 to 2 new plants a day, with at most 2 waiting on the hills at once:

| Season | Forage | Eat raw | Notes |
|---|---|---|---|
| Spring | Wild onion | 6 | Also cooks into wild onion soup |
| Summer | Wild berry | 8 | Also cooks into wild berry jam, or counts as a jam berry |
| Autumn | Wild mushroom | — | Cook into mushroom soup |
| Winter | — | — | No wild forage |

The stall does not buy foraged goods. Cook them, or eat the ones that are safe raw.

The boarded mine entrance is on the north-centre hill (row 1, column 2). Finding it lets the shop sell a pickaxe. `enter mine` with a pickaxe in the pack pries the boards.

---

## The mine

The mine is a 3×3 on each floor, floors 1 to 25. Floors re-roll each season. The ladder down is hidden under a plain stone on ordinary floors, or standing open on a safe floor. Breaking the hidden stone uncovers the way down.

Every fifth floor (5, 10, 15, 20, 25) is safe: no rocks, no slimes, and a lantern. `rest` at the lantern once a day, on that floor, to recover 25 energy (not above your usual 100 cap).

Ordinary-floor rocks, out of 100 (the rest is plain stone; runestone is taken from that remainder):

| Floors | Copper | Iron | Gold | Runestone |
|---|---|---|---|---|
| 1–4 | 40 | 0 | 0 | 3 |
| 6–9 | 50 | 15 | 0 | 6 |
| 11–14 | 20 | 45 | 5 | 9 |
| 16–19 | 10 | 35 | 25 | 12 |
| 21–24 | 0 | 20 | 45 | 16 |

Plain stone on floors 1–4 can drop quartz (15% chance, plus any gem bonus from a pickaxe enchant). Improved Yield adds +5 to that chance; Superior Yield adds +10. Those enchants also have a 25% or 50% chance to yield one extra ore when you break a rock.

Grey slimes appear from floor 6 on, never on safe floors. A slime has 20 HP and deals 8 damage. `strike` (5 energy) when you stand on the same tile; a strike deals 10 damage. The slime hits back unless that blow defeats it. Walking off the tile, or breaking a rock on it, gives the slime a free hit (its usual 8 damage). There is no separate flee action. A defeated slime drops goo (the stall pays 8G). Counts per floor: 0–1 on floors 6–9, 0–2 on 11–14, 1–2 on 16–19, and 1–3 on 21–24.

---

## Runestones and enchanting

The Creation Table sits in the middle of the cabin (row 2, column 2). It is free to build if it is not already there. Craft runestones here any day: 1 runestone ore becomes 1 runestone, for 5 energy.

Enchanting happens only on an aurora night, at the table:

| Enchant | On | Need | Cost | Effect |
|---|---|---|---|---|
| Improved Yield | Pickaxe | Mining level 5 | 5 runestones, 50 energy | 25% chance of +1 ore; +5 quartz chance |
| Superior Yield | Pickaxe | Mining level 10 | 10 runestones, 100 energy | 50% chance of +1 ore; +10 quartz chance. Replaces Improved Yield. |
| Nimble | Boots you are wearing | Overall level 10 (out of 50) | 10 runestones, 100 energy | Paid steps cost 1 less. Cabin walking stays free. |

---

## Cooking

Cook at the kitchen (cabin row 3, column 2). First load the stove: stand there, with 1 wood in the backpack, for 5 energy. The stove stays lit for the rest of that day and goes out at dawn. Ingredients must be in the backpack, not the chest.

Jam and kabocha soup start in the recipe book. Other recipes are learned when you have all the ingredients at the cabin, or when you cook them. `recipes` lists the book. Only jams are sellable; other meals are for eating.

Strawberry jam can be made with June-bearing strawberries, everbearing strawberries, or wild berries (3 berries and 1 sugar). Mushroom soup can use a wild mushroom or an oyster mushroom, plus milk.

| Recipe | Ingredients | Eat | Sell? |
|---|---|---|---|
| Strawberry jam | 3 berries, 1 sugar | 40 | 90G |
| Wild berry jam | 3 wild berries, 1 sugar | 32 | 55G |
| Rhubarb strawberry jam | 2 rhubarb, 1 strawberry, 1 sugar | 45 | 95G |
| Kabocha soup | 1 kabocha | 55 | no |
| Pumpkin soup | 1 pumpkin | 52 | no |
| Root stew | 1 carrot, 1 turnip | 50 | no |
| Bread and butter | 1 bread, 1 butter | 22 | no |
| Jam toast | 1 bread, 1 strawberry jam | 58 | no |
| Strawberry milk | 1 milk, 1 strawberry | 45 | no |
| Buttered kabocha | 1 kabocha, 1 butter | 42 | no |
| Kabocha cream soup | 1 kabocha, 1 milk, 1 butter | 70 | no |
| Wild onion soup | 1 wild onion, 1 milk | 28 | no |
| Mushroom soup | 1 mushroom, 1 milk | 32 | no |
| Garden salad | 1 lettuce, 1 tomato, 1 cucumber | 36 | no |
| Roasted potatoes | 2 potatoes, 1 butter | 42 | no |

Crafting a meal costs 5 energy.

---

## The cabin

The cabin is its own 3×3 room. Enter from the farm cabin tile; you arrive at the door. Leave through the door, or walk to it (free) and step out onto the farm doorstep. Being anywhere inside counts as "in the cabin" for sleep and for sleeping close.

```
      col 1          col 2              col 3
row 1 double bed     chest              floor (reserved for a display case)
row 2 floor          Creation Table     fireplace
row 3 door           kitchen            floor
```

The farm around it:

```
      col 1      col 2      col 3
row 1 farmland   farmland   CABIN  ← north to the hills, east to town
row 2 farmland   farmland   farmland
row 3 farmland   farmland   farmland
```

Rows and columns are 1-indexed. Row 1 is the top, column 1 is the left.

---

## Skills

There are five skills, each capped at level 10. Overall level is the sum of the five (it starts at 5 and caps at 50). Thresholds for levels 1–10 are 0, 40, 100, 200, 350, 550, 800, 1100, 1500, and 2000 XP.

| Skill | XP |
|---|---|
| Mining | Stone 2, copper ore 5, iron ore 8, gold ore 12, runestone ore 15, plus 5 if the rock dropped quartz |
| Woodcutting | 5 per grown tree chopped |
| Farming | 1 to plant, 4 to harvest a one-and-done crop (watering grants none; perennial, regrowing, and frost-bitten harvests grant no farming XP today) |
| Foraging | 3 per pick |
| Combat | 10 per slime |

---

## Planned changes

These are not in the game yet. Details live in [ROADMAP.md](ROADMAP.md).

- Chest and tool upgrades may all cost 8 ore per tier, so one full backpack stack pays for one upgrade. Today chests cost 8 copper, then 10 iron, then 12 gold, and tools cost 5 ore.
- A runestone drop-rate raise (to 1–2 or 1–3, after a depth tally) is planned, because the magic system will spend runes on every spellcast.
- Selectable cabin flooring, earned or bought from rotating honour-store stock, is planned as part of decorating the cabin.
- See [BUGS.md](BUGS.md) for open bugs that change how a rule feels, including first-night homesickness, carry blocked by a sleeping bag, and tomato seeds still sold in early autumn.
