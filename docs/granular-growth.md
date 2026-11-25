# Granular crop growth, health, and harvest by the kilogram

Design only — no code in this pass. Written so inventory, till-hold, and
growth can share one quantity model instead of being migrated twice.

The current farm grows a plant in whole watered days, then harvests exactly
one fruit, which withers after two dry days. Rick asked for a more granular
model: each crop has a **growth %** and a **health** value; **yield is in
kg**, set by health and growth; **early harvest** is allowed only after a
minimum growth period (especially kabocha); **withering is rare**, for long
drought or wrong-season extremes, not after two dry days; **weeds and dry
days lower health**; **fertilizer** comes later as a boost to health and
yield.


## Why this sits in front of inventory work

A pack-and-chest inventory is already designed (approved, not yet shipped):

- one hoe and two watering cans, which occupy pack slots
- a 4-slot pack per player; tools take slots
- a shared cabin chest; sell and craft at the cabin
- harvested produce rides in the pack and must be carried home

If that work lands as “one harvest = one item, stack of 8,” a kg yield model
will have to migrate the pack a second time. Produce should be stored in
**kilograms from the start**. Tools, seeds, and seedlings stay as counts.
Till-hold (empty tilled soil reverting after five unwatered days) barely
overlaps and can ship on its own; see [Overlaps](#overlaps-with-work-already-planned).


## What the farm does today

A 15-day season. A watered, weed-free day adds 1 to `days_grown`. A weedy
plot skips every other watered day. After `wither_after_dry_days` (2) the
plant dies. Harvest always adds **1** of that crop to a shared count-map
inventory. Stages are thresholds on `days_grown`.

| Crop | First ripe | Regrow | Full harvest today | Sell | Eat | Notes |
|---|---:|---:|---|---:|---:|---|
| June-bearing strawberry | 7 days, after first winter | 7 | 1 berry | 25G | +30 | Perennial, 8 seasons, runners, fruits spring into early summer |
| Everbearing strawberry | 4 days, first year | 7 | 1 berry | 18G | +20 | Perennial, 8 seasons, runners, through early autumn |
| Kabocha | 17 days, no regrow | — | 1 squash | 50G | +25 | Annual, spring–summer; planted in spring, finishes in summer |
| Turnip / carrot | 9 / 12 days | — | 1 root | 22G / 32G | +12 / +10 | Later content; same rules would apply |

Kabocha’s 17 days already spans a season boundary, which is why early
harvest matters there first.


## Proposed state fields

On each planted tile’s `crop` object, alongside the fields we already keep
(`kind`, `planted_day`, `stage`, `days_grown`, `dry_days`, perennial
bookkeeping):

| Field | Type | Meaning |
|---|---|---|
| `growth` | int 0–100 | Progress of the current fruiting (or first-growth) cycle, as a percent |
| `health` | int 0–100 | Condition. Weeds and dry days pull it down. Starts at 100. |
| `min_harvest_growth` | not stored | Comes from the crop catalog, not the tile |

`days_grown` and `stage` stay for sprite keys, look text, and migration.
`growth` is the source of truth for “how far along is this cycle?” once the
feature ships; `days_grown` can be derived for display (`round(growth / 100 *
cycle_days)`) or kept in sync. `dry_days` stays as a running streak, used
for health loss and the rare wither check, not as an automatic death clock.

Optional later, not in the first cut:

| Field | Type | Meaning |
|---|---|---|
| `fertilized` | bool or int | A later layer. Do not add until fertilizer is a real action. |

On harvested produce in a pack or chest slot:

```text
{"item": "strawberry", "kg": 0.25}
```

Internally store **grams as an integer** (`grams: 250`) and show kilograms
to two decimals, so saves never drift on float rounding. Seeds, seedlings,
tools, and crafted jars/bowls stay `{"item": "hoe", "count": 1}` (or
`{"item": "strawberry_jam", "count": 1}`).

A slot is one or the other: `count` for discrete things, `grams` for loose
produce. Do not mix in one stack.


## Per-day update rules

Run in the evening, when the day turns, after today’s watering is known and
before `watered` is cleared. Dawn rain or snow still counts as watered for
that new day, same as now.

### Growth

- If the plant is **dormant** (perennial in its off season): `growth` does
  not change; `dry_days` resets; health does not drain from ordinary dryness
  (the plant is resting). Weeds can still nibble health, slowly.
- If the plant is **watered** and not dormant: add `growth_per_watered_day`
  from the catalog. First cut: this is `round(100 / cycle_days)` so a fully
  watered, in-season cycle still reaches 100% on the same day it ripens now
  (day 7, 4, or 17). Cap at 100.
- If the plant is **dry**: add **0** growth. (No watered day, no swelling.)
- Weeds **do not skip growth** in this model. They cut health instead, so a
  weedy but watered plant still fills out, just with a poorer picking. This
  is a change from today’s every-other-day skip and should be called out in
  the patch notes.

June-bearing plants that have not yet finished establishment keep today’s
rule: they put on leaves, but the fruiting cycle (`growth` toward a harvest)
does not start until after the first winter. Everbearing may start a
fruiting cycle in the planting year, as they do now.

### Health

Start each new planting at **100**. Soft caps: 0–100 in the first cut.
Fertilizer, later, may raise the cap or apply a yield multiplier without
changing this table.

Each evening a living, non-dormant plant updates health like this:

| Condition today | Health change |
|---|---|
| Watered, not weedy | `+4`, capped at 100 (recovery) |
| Watered, weedy | `−6` |
| Dry, not weedy | `−8` |
| Dry and weedy | `−12` |
| Wrong season (annual in a season it cannot grow, or perennial forced out of dormancy by a bug) | `−20` in addition to the row above |

Health never goes below 0. At 0 the plant withers (see below). Recovery is
deliberately slower than damage, so a neglected bed takes a few kind days
to bounce back, and a long drought is felt at harvest even if the plant
lives.

A newly weeded plot does not get an instant health refund; plucking only
stops further weed drain. (Fertilizer, later, is the instant bump.)

### Withering (rare)

A plant withers only if one of these is true at day turn:

1. `health` has reached **0**.
2. **Long drought:** `dry_days >= 6` and `health <= 20`.
3. **Wrong-season extreme:** an annual that is out of season has been so
   for **3** evenings (health will already be falling ~20/day, so this is
   usually a safety net, not a surprise). Perennials still go dormant at
   the season change instead of withering, as they do now.

Two dry days, by themselves, must not kill a plant. After two dry days a
weed-free plot would be at about `100 - 16 = 84` health and still growing
the next time it rains.

### After harvest

- **Regrowing crops** (both strawberries): `growth` resets to 0. `health`
  stays, minus a small picking stress of **5** (not below 1). The plant
  remains; the next cycle uses `regrow_days` as its cycle length.
- **Single-harvest crops** (kabocha, turnip, carrot): the plant is cleared
  and the bed stays tilled. If till-hold is in play, the empty-bed countdown
  starts at a full 5 days.


## Concrete starting numbers

Cycle length equals today’s `grow_days` / `regrow_days`, so calendars and
sprite thresholds do not have to move on day one. `growth_per_watered_day`
is `ceil(100 / cycle_days)` on the last step so a perfect cycle still hits
100% on the due day (for 17-day kabocha: +6 most days, +4 on the last, or
simply `min(100, growth + round(100/17))` and a “ripe at 100 or on day 17
if watered throughout” snap — implementation can snap to 100 on the due
day if the plant was watered every in-cycle day).

`min_harvest_growth` is the earliest early-pick. Below that, harvest is
refused. Yield uses the formula in the next section.

| | June-bearing strawberry | Everbearing strawberry | Kabocha |
|---|---|---|---|
| Cycle to first fruit | 7 days, after first winter | 4 days, first year | 17 days |
| Later cycles | 7 days | 7 days | none |
| Growth per watered day | ~14% (7-day), snap to 100 on day 7 | ~25% first cycle, then ~14% | ~6% , snap to 100 on day 17 |
| Min. early harvest | **70%** (~day 5 of a 7-day cycle) | **70%** (~day 3 first cycle, day 5 later) | **60%** (~day 10, when today’s “growing” stage begins) |
| Full yield at 100% growth, 100% health | **0.25 kg** | **0.20 kg** | **1.50 kg** |
| Implied sell price | **100G / kg** (25G for a full picking, same as today) | **90G / kg** (18G for a full picking) | **33G / kg**, rounded; a full 1.50 kg squash sells for **50G**, same as today |
| Eat energy | **+120 / kg** (30 per full 0.25 kg picking) | **+100 / kg** (20 per full 0.20 kg) | **+17 / kg**, rounded so 1.50 kg is still **+25** |
| Why these kg figures | A small bowl of berries from one plant; four full pickings fill a 1 kg pack slot | Slightly lighter bowls, more often, and they fruit the first year | One modest kabocha is about 1.5 kg; early-picked fruit is a smaller squash |

Turnip and carrot, when they follow: full yields **0.40 kg** and **0.30 kg**,
prices kept at today’s 22G and 32G per full root (55G/kg and ~107G/kg),
`min_harvest_growth` 70% and 75%. They are not required for the first
build.

### Worked examples

Ideal June-bearing picking: growth 100, health 100 → 0.25 kg, 25G, +30
energy if eaten as the whole bowl.

Picked early at 70% growth, 100% health: `0.25 * 0.70 * 1.00 = 0.18 kg`,
worth 18G.

Picked ripe but battered (100% growth, 50% health): `0.25 * 1.00 * 0.50 =
0.13 kg`, worth 13G.

Kabocha at the first legal early pick, well cared for (60% growth, 100%
health): `1.50 * 0.60 * 1.00 = 0.90 kg`, worth 30G, eat +15. A perfect
squash stays 1.50 kg, 50G, +25.

Kabocha neglected then rescued: say growth 100% but health 40% → 0.60 kg,
20G. The plant lived; the squash is just smaller.


## Yield formula

```text
kg = full_yield_kg * (growth / 100) * (health / 100)
```

Round to the nearest 0.01 kg, minimum **0.01 kg** if the harvest was
allowed (never a 0 kg “success”). Fertilizer, later, should be a third
multiplier (`* fertilizer_bonus`, default 1.00, perhaps 1.20 for a fed
plot) rather than a second health cap, so a later patch does not have to
redo this formula.

Gold and snack energy scale with kg at the per-kilo rates above, then
round to the nearest 1G and 1 energy, minimum 1 if the player is selling
or eating a positive amount.


## Early harvest

`harvest` on a tile is legal when `growth >= min_harvest_growth` for that
kind (and the plant is not dormant, withered, or still establishing in a
way that forbids fruit). It is no longer limited to `stage == "mature"`.

If growth is under the minimum, keep a clear refusal: “The kabocha at the
top-left is only 40% along; it can be picked from 60% (around day 10).”

Ripe (`growth == 100`) is still the best picking, and sprites can keep
using the mature art from the usual threshold. Between min and 100, use
the growing (or a later “filling out”) sprite so a half-ready kabocha does
not look like a finished one.


## How harvest meets the pack and chest

Recommendation, meant to be used when inventory is built:

**Produce is kg-based. Everything else is counted.**

- Pack: 4 slots. A hoe or watering can takes a whole slot (`count: 1`).
  Seeds and seedlings stack by count (proposed cap 8, as already sketched).
  A produce slot holds one kind and up to a **kg cap** — start with
  **1.00 kg** for berries and roots, **2.00 kg** for kabocha, so a perfect
  kabocha almost fills a slot and berries need a trip home after four
  ideal pickings (or sooner if the pack already holds a tool).
- Chest: the same stack rules, looser caps (16 seeds; **8.00 kg** of a
  produce kind per stack, and more stacks are allowed). The chest is where
  a harvest is shared and sold.
- Harvest tries to add kg to the acting player’s pack, stacking onto the
  same kind if a slot already holds it and the cap has room. If the
  leftover kg will not fit, **do not harvest** — say the pack is full and
  nothing was picked. Same “make a trip” pressure as the approved inventory
  design, just in kilograms.
- Sell at the cabin, by kind and kg (`sell strawberry 0.25` or `sell
  strawberry` to sell one pack stack). Price is per kilogram.
- Eat from the pack, by kind. A snack can be a **serving** (proposed:
  0.10 kg of berries, 0.30 kg of kabocha) so energy stays in the same
  range as today’s 2-snacks-a-turn rule, or it can spend a whole stack.
  This is an [open question](#open-questions-for-rick).
- Crafting at the cabin (jam, soup, stew) should be restated in kg once
  those recipes ship. A starting proposal: strawberry jam costs **0.50 kg**
  of strawberries (two ideal June-bearing bowls, or a bit more than two
  everbearing bowls), not “3 berries,” and yields 1 jar (a counted item).
  Kabocha soup costs **0.50 kg** of kabocha. Until inventory ships, do not
  implement the recipes in berry-counts we will only have to rewrite.

Why not “1 kg = 1 slot, no stacking”? A 0.18 kg early picking would waste
a whole slot and make the 4-slot pack feel punishing. Why not unlimited kg
in a slot? Then the “carry it home” rule is flavour only. A modest cap
keeps both the realism and the walk back to the lantern.


## Save migration

Idempotent, and only after a backup of `state.json` (the same caution as
every other live-save change).

Living crops:

- `growth = min(100, round(100 * days_grown / cycle_days))`, using
  `regrow_days` when the plant is mid-regrow, else `grow_days`. A `mature`
  stage snaps to 100.
- `health = 100 - 8 * dry_days - 6 * (1 if weedy else 0)`, floored at 40
  so a currently living plant does not arrive already on death’s door.
  Withered plants stay withered; do not revive them.
- Establishing June-bearing plants (not yet allowed to fruit) get
  `growth = 0` and `health` as above; leaf stage still follows
  `days_established`.

Inventory, if the kg pack has not shipped yet (today’s shared count map):

- 1 strawberry → 250 g, 1 everbearing → 200 g, 1 kabocha → 1500 g, 1
  turnip → 400 g, 1 carrot → 300 g. These are “full, healthy pickings,”
  which is the honest translation of “you already have one fruit.”

Inventory, if a count-based pack/chest has already shipped:

- The same per-item gram table, applied to each produce stack. Tools and
  seeds unchanged. This is exactly the double migration the build order
  below is trying to avoid.

Missing fields on old tiles (`growth`, `health`) are filled once and then
left alone. `untilled_in` for empty tilled beds is a separate, smaller
migration and does not depend on these numbers.


## UI and CLI text

Look / tile description, empty tilled bed (till-hold, if present):

```text
top-center, row 1 col 2 — tilled soil, dry today. Empty. 3 days left until it
reverts if left unwatered.
```

Look / tile description, growing crop:

```text
top-left, row 1 col 1 — June-bearing strawberry, growing, 62% growth, health
88%, watered today. Ready to pick from 70%.
```

At or above the minimum, add a forecast so the kg is not a surprise:

```text
… 80% growth, health 70%. About 0.14 kg if picked now.
```

Ripe:

```text
… ripe, 100% growth, health 55%. About 0.14 kg if picked now. Ready to harvest.
```

Kabocha still too young:

```text
The kabocha at the top-left is only 41% along; it can be picked from 60%.
```

Pack line:

```text
Pack: hoe, watering can, 0.50 kg strawberries, 0.90 kg kabocha
```

(Two tools and two produce stacks — a full 4-slot pack.)

Chest / shop: show kg on hand, price per kg, and a “Sell 0.25 kg” control
(or a small quantity stepper). Legal actions should speak kg too:
`harvest 1 1`, `sell strawberry 0.25`, `eat strawberry` (one serving).

Web tile labels can stay short (“grow 62% · hp 88%” or “ripe · 0.14 kg”)
so the art is not hidden. Storybook and Classic sprites keep the existing
stage set; growth % does not need new pack art in the first cut. A later
pass might add a “filling out” kabocha if early harvest feels visually
wrong on the growing sprite.


## Overlaps with work already planned

**Till-hold (empty tilled soil, 5 days, watering resets).** Independent.
Wire it whenever. The only handshake is: when a kabocha (or root) is
picked, the bed becomes empty and the 5-day countdown starts; watering
that empty bed still resets it so runners have a cared-for plot. Soft
withering means *fewer* surprise empty beds than today’s 2-dry-day deaths,
which makes till-hold and runner space a little more predictable.

**Pack, chest, tools, cabin selling, recipes.** Dependent on this doc’s
quantity model. Build the pack with `count` and `grams` slots from day
one. Do not ship a berry-count harvest into the pack first. Recipes should
be specified in kg (proposal above) when that work starts.

**Weed placement (just shipped).** No conflict. Weeds stay a tile overlay;
this model only changes what they *do* to the plant (health instead of
skipped days).

**Live save.** Day-to-day play is mid-summer with several growing berries
and at least one empty tilled plot. Any of these features that touch
`state.json` must back the file up first and migrate in place. Do not
reset the farm.


## Open questions for Rick

1. **Do these kg amounts feel right?** 0.25 / 0.20 kg bowls of berries and
   a 1.50 kg kabocha are chosen so a full, healthy picking still sells and
   snacks for today’s gold and energy. Bigger bowls (0.50 kg berries, 2 kg
   squash) would make the pack fill faster and make “1 kg cap” tighter.
2. **Pack cap.** 1 kg of berries / 2 kg of kabocha per slot is a starting
   guess. Tighter (0.50 kg) means more walks to the cabin; looser weakens
   that loop.
3. **What is a snack?** A fixed serving (0.10 kg berries, 0.30 kg kabocha)
   keeps the “two snacks a turn” rule close to today’s energy numbers. Eating
   a whole stack might be too much energy from one kabocha. Which do you
   want?
4. **Jam and soup in kg.** Is 0.50 kg strawberries for a jar of jam, and
   0.50 kg kabocha for a soup, about right — or should recipes wait until
   you have cooked with the new yields for a season?
5. **Health recovery.** +4 on a clean watered day, and no refund for
   plucking, is conservative. If neglected plants feel too sour even after
   a week of care, recovery can be bumped before fertilizer exists.
6. **Weeds no longer slow growth, only health.** That is a real change in
   feel: a weedy ripe plant is pickable on time, just lighter. Would you
   rather weeds still slow growth a little (for example half `growth_per
   watered_day`) *and* cut health?
7. **Early-harvest sprites.** Is it all right if a 60–99% kabocha still
   uses the “growing” art until we paint a fuller one?
8. **Fertilizer timing.** First cut has no fertilizer field. When you want
   it, a 1.20× yield multiplier (and maybe a small health bump) can land
   without restating this formula. Any strong preference for item, price,
   or how it is applied (once per cycle vs once per season)?
9. **Precision in commands.** `sell strawberry 0.25` vs selling in 0.05 kg
   steps vs “sell all the strawberries in my pack.” What is comfortable at
   the CLI and in the shop window?


## Suggested build order

1. **Agree on kg amounts, pack caps, and the snack rule** (the questions
   above). This document is the proposal; numbers can move before any
   patch.
2. **Till-hold** can ship at any time, including before the rest. It does
   not depend on growth % or kg.
3. **Pack, chest, and tools, already in kilograms for produce.** Migrate
   the live save once: existing fruit counts become grams; tools start in
   the chest. Legal actions, MCP, CLI, and the web pack/chest UI all speak
   kg for fruit and counts for tools and seeds. This is the foundation.
4. **Add `growth` and `health` to crops, migrate living plants, keep
   today’s harvest-as-full-yield if a plant is `mature` and you have not
   yet switched the yield formula.** Or land 3 and 5 together so a mid-cycle
   plant never sells as a full fruit by mistake.
5. **Yield formula + early harvest + forecast text** (“about 0.14 kg if
   picked now”). Legal harvest at `min_harvest_growth`. Tests for the
   worked examples in this doc.
6. **Soft wither** (drop the 2-dry-day death, use the rare conditions
   above). Update look text so two dry days sound like a health warning,
   not a death sentence.
7. **Fertilizer**, later, as its own small patch: an item, a multiplier,
   no change to the core formula.

Tests should cover: perfect and early yields for all three named crops;
health drain and recovery; a two-day drought that does *not* wither; a
six-day drought at low health that does; pack overflow refusing a harvest;
migration of a mature strawberry into 100% growth, 100% (or migrated)
health, and 250 g in the pack or chest; no mention of private player names
in the repo.
