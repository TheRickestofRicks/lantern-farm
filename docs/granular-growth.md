# Granular crop growth, health, and whole-item yields

Approved design (Rick). This document is the working plan. Produce is
**whole items**, never kilograms. Growth and health are **hidden** stats;
the farm only offers gentle hints in look text. Fertilizer and the pack
are part of the same plan, but they ship in separate patches.

Build order, each a commit of its own:

1. This document.
2. Till-hold: empty tilled soil reverts after 5 days unwatered and unplanted;
   watering resets the countdown.
3. Pack, chest, and tools as **counts**: one hoe, two watering cans, 4-slot
   packs (tools take slots), a shared cabin chest, carry harvest home, sell
   and craft at the cabin, two or three cozy recipes.
4. Hidden growth and health, a weighted yield roll, early harvest, gentle
   hints, and soft withering.
5. Fertilizer (one application per plot per season, three kinds), with a
   simple placeholder granule overlay and Classic SVG fallback. Painted
   Storybook art can wait.


## What changes, in short

Today a plant grows in whole watered days and harvests as exactly one
fruit, then withers after two dry days. Under this model:

- Each crop has hidden `growth` (0–100) and `health` (0–100).
- Harvest yields **whole items**. Strawberry plants give **1–3** berries;
  kabocha gives **1–2** squash. The yield is **never less than 1** if the
  harvest is allowed.
- The count is a **weighted random roll** from hidden growth and health:
  closer to 100% growth and higher health means a better chance of the
  high end. The roll is deterministic for a given plant and harvest
  (seeded from day, plot, and harvest index) so tests and replays agree.
- Early harvest is allowed once growth reaches a minimum threshold, with
  a weaker roll because growth is not yet 100%.
- Growth and health are never printed as numbers. Look text uses gentle
  hints instead: “looks a little thirsty,” “thriving,” “struggling.”
- Weeds **slow growth and cut health**.
- Withering is rare: long drought, health falling to 0, or wrong-season
  extremes — not after two dry days.
- Fertilizer is a later patch: one application per plot per season, three
  kinds (general, yield-boost, growth-boost). The soil is marked
  fertilized, the kind is named in look text, and a simple teal/green
  granule overlay sits on the dirt (placeholder art is fine until a
  painted Storybook pass).


## Overlaps with pack and till-hold

**Till-hold** does not depend on growth or yield. It can (and should)
ship first. When a single-harvest crop is picked, the bed becomes empty
and the 5-day countdown starts; watering that empty bed still resets it,
so runners keep a cared-for plot. Soft withering later means fewer
surprise empty beds than today’s two-dry-day deaths.

**Pack, chest, and tools** stay **count-based**. That matches this yield
model: a harvest of 2 strawberries is two items in the pack, stacking
with others of the same kind, not a weight. Tools, seeds, seedlings, and
crafted food are counts too. There is no kilogram field.

**Live save.** Back up `state.json` before any of these migrations. The
existing kabocha (and any other shared-inventory produce or seeds) move
to the cabin chest. Living plants get `growth` from `days_grown` and
`health` 100. Tools start in the chest. Do not start a new farm.


## Till-hold (step 2)

An empty tilled plot that stays unplanted reverts to untilled after **5**
consecutive days without being watered. Watering — a player with a can,
or dawn rain, storm, or snow — **resets** the countdown to 5. A cared-for
empty bed stays tilled so runners have somewhere to go.

- New tile field: `untilled_in` (days left), only meaningful on empty
  tilled soil. Start at 5 when the bed is tilled, when a plant is cleared,
  or when the plot is watered.
- Each evening, if the bed is still empty and tilled: reset to 5 if it
  was watered today, otherwise subtract 1. At 0, `tilled` becomes false.
- Dawn wet weather should reset immediately so morning look text already
  shows a full 5 days.
- Planted plots (including dormant perennials) do not tick. Withered
  plants still occupying the bed do tick, as the bed is not a living
  planting; clearing them leaves the soil tilled with a fresh 5 if you
  till or harvest them away.
- Look / tile text, for example: “tilled soil, dry today. Empty. 3 days
  left until it reverts if left unwatered.”


## Pack, chest, and tools (step 3)

Approved inventory, all whole items:

- **One hoe** in the world, required to till, occupies a pack slot.
- **Two watering cans**, required to water, one slot each.
- Each player has a **4-slot pack**. Tools do not stack in the pack
  (one tool per slot). Seeds, produce, and crafted food stack (cap 8
  is a fine starting number).
- A **shared chest** at the cabin. Tools may stack in the chest (both
  cans in one chest slot). The chest is where items are shared.
- **Harvest goes into the pack.** If there is no room, the harvest is
  refused and the plant is left as it was — walk home, drop something,
  come back.
- **Sell and craft at the cabin.** Selling is allowed from the pack or
  the chest while you are there. Bought seeds go into the pack if they
  fit, otherwise into the chest.
- **Eat** from your pack, anywhere. Two snacks a turn, as today.
- Commands: `take <item> [count]`, `drop <item> [count]`, `craft <recipe>`
  (aliases `put` for drop). Only at the cabin for take, drop, buy, sell,
  and craft.

Migration: the old shared `inventory` count map is poured into the chest.
Missing tools are added to the chest (never duplicated if someone already
holds them). Packs start empty. A totals view may be kept on the state
for older readers, but packs and the chest are the source of truth. The
live kabocha and strawberry seeds go to the chest.

`apply_new_day_turns` must **preserve packs** when it rebuilds player
slots, or everyone will wake up empty-handed.

### Recipes (craft at the cabin)

| Recipe | Ingredients | Result | Role |
|---|---|---|---|
| Strawberry jam | 3 strawberries (either June-bearing or a mix with everbearing, counted as strawberries of any kind? — see open question; default: **3 `strawberry` or 3 `everbearing`, or a mix of 3 berries**) | 1 jar of jam | Snack (+50 energy) and sellable (90G) |
| Kabocha soup | 1 kabocha | 1 bowl of soup | Primarily a snack (**+45 energy**), sellable at a modest 40G |
| Root stew (third, optional) | 1 carrot + 1 turnip | 1 stew | Snack (+40 energy), sellable at 60G |

Default: jam accepts any combination of `strawberry` and `everbearing`
totalling 3 berries, so early everbearing pickings can be put up too.


## Hidden growth and health (step 4)

On each living crop, alongside the fields already stored:

| Field | Type | Meaning |
|---|---|---|
| `growth` | int 0–100 | Hidden progress of the current fruiting or first-growth cycle |
| `health` | int 0–100 | Hidden condition. Starts at 100 on a new planting and on migration of living plants. |

`days_grown` and `stage` remain for sprite keys and migration. Once this
ships, `growth` is the source of truth for the cycle; `days_grown` can
stay in sync for art (`stage` still flips at the usual thresholds).
`dry_days` remains a streak, used for health drain and the rare wither
check, not as an automatic death clock.

These numbers are **never shown** in look text, the web tile label, the
CLI, or the shop. Players only get the hints below.

### Per-day rules (evening, before `watered` is cleared)

**Growth**

- Dormant perennials: growth does not change; dry-day streak resets;
  ordinary dryness does not drain health. Weeds may still nibble health
  slowly (half the usual weed drain).
- Watered and not dormant: add `growth_per_watered_day`, about
  `round(100 / cycle_days)`, so a perfect watered cycle still reaches
  100% on the same day the plant ripens today (day 7, 4, or 17). Cap 100.
  Snap to 100 on the due day if the plant was watered throughout.
- Dry: add 0 growth.
- **Weedy and watered:** growth is **slowed**, not skipped entirely.
  Add half the usual `growth_per_watered_day` (round half up on odd
  days so a 7-day cycle still finishes, just later). And health is cut
  (below). This replaces today’s every-other-day skip.

June-bearing plants still establish in the first year without starting a
fruiting cycle, as they do now. Everbearing may fruit in the planting
year.

**Health**

| Condition today | Health change |
|---|---|
| Watered, not weedy | `+4`, capped at 100 (slow recovery) |
| Watered, weedy | `−6` |
| Dry, not weedy | `−8` |
| Dry and weedy | `−12` |
| Wrong season (annual out of its seasons) | `−20` in addition to the row above |

Health never goes below 0. Plucking weeds stops further weed drain but
does not refund health.

**Withering (rare)**

A plant withers only if, at day turn:

1. `health` has reached 0, or
2. **Long drought:** `dry_days >= 6` and `health <= 20`, or
3. **Wrong-season extreme:** an annual has been out of season for 3
   evenings. Perennials still go dormant at the season change, as now.

Two dry days must not, by themselves, kill a plant.

**After harvest**

- Strawberries (both kinds): `growth` resets to 0; `health` stays, minus
  a picking stress of 5 (not below 1). The next cycle uses `regrow_days`.
- Kabocha, turnip, carrot: the plant is cleared; the bed stays tilled
  and till-hold starts at 5.

### Early harvest

`harvest` is legal when `growth >= min_harvest_growth` for that kind
(and the plant is not dormant, withered, or still establishing). It is
no longer limited to `stage == "mature"`.

| Crop | Cycle | Min. early harvest | Yield range |
|---|---|---|---|
| June-bearing strawberry | 7 days (after first winter), then 7 | **70%** (~day 5) | **1–3** |
| Everbearing strawberry | 4 days first year, then 7 | **70%** | **1–3** |
| Kabocha | 17 days, no regrow | **60%** (~day 10, today’s “growing” stage) | **1–2** |
| Turnip / carrot (same rules, later focus) | 9 / 12 days | **70%** / **75%** | **1–2** |

If growth is under the minimum, refuse with a hint, not a percentage:
“The kabocha at the top-left is still filling out; it isn’t ready to
pick yet.”

### Yield roll

When a harvest is allowed, roll an integer in the crop’s range, **minimum
1**. Higher hidden growth and hidden health shift the weights toward the
top of the range. Early picks (growth above the minimum but under 100)
can still roll well if health is high, but the typical result is lower.

Let `q = (growth / 100) * (health / 100)` (0–1). Fertilizer later may
adjust `q` or the weights; see step 5.

For a 1–3 crop (strawberries), using a deterministic roll `r` in 0–99
from `weed_hash(day, row, col, salt=harvest_index)`:

- Chance of 3 ≈ `5 + 75 * q^1.5` percent
- Chance of 2 or 3 ≈ that plus `20 + 40 * q` percent, capped at 100
- Otherwise 1

Worked feel (not printed to the player):

- Perfect (q = 1): usually 3, sometimes 2, rarely 1.
- Early and well cared for (growth 70, health 100, q = 0.70): a mix of
  1 and 2, with 3 uncommon.
- Ripe but battered (growth 100, health 50, q = 0.50): mostly 1 or 2.

For a 1–2 crop (kabocha and roots):

- Chance of 2 ≈ `15 + 70 * q` percent; otherwise 1.

A perfect kabocha is usually 2 squash; an early or stressed one is
usually 1, and never 0.

Gold and snacks: each item still sells and eats at today’s per-item
prices and `eat_energy`. Two berries are two snacks if you eat them
separately (still capped at two snacks a turn).

### Gentle hints (no numbers)

Look text may use one or two of these, not a stat block:

| Situation | Hint |
|---|---|
| High health, watered, not weedy, growth not yet ready | “thriving” |
| High health, ripe or in the early-pick window | “looks ready to pick” / “could be picked, though it might still put on more” |
| Mid health, ordinary care | “getting along” |
| Low health | “struggling” |
| Dry (and not just watered by rain) | “looks a little thirsty” / “is drying out” if the dry streak is longer |
| Weedy | “is a little crowded by weeds” |
| Just planted, low growth | “just getting started” |
| Dormant | keep today’s resting-until-spring language |
| Withered | keep today’s withered language |

Examples:

```text
top-left, row 1 col 1 — June-bearing strawberry, growing, watered today. It is thriving.
top-center — kabocha, dry today. It looks a little thirsty, but it could be picked, though it might still put on more.
bottom-left — everbearing strawberry, watered today. It is struggling and is a little crowded by weeds.
```

Never say “62% growth,” “health 88,” or the upcoming roll. After a
harvest, the log can say how many were picked: “Lumen harvests 2
strawberries at the top-left.”


## Fertilizer (step 5)

One application **per plot per season**. Three kinds, sold at the shop in
**spring and summer** (sensible starting prices, in the same range as
seed packets):

| Kind | Price (starting) | Effect |
|---|---:|---|
| General fertilizer | 15G | Small health bump now (+10, cap 100) and a small yield nudge (`q + 0.10`, cap 1.00) |
| Yield-boost fertilizer | 25G | A stronger yield nudge (`q + 0.25`, cap 1.00) |
| Growth-boost fertilizer | 20G | Faster growth (about +50% `growth_per_watered_day` on watered days) |

You must stand on the plot, with the bag in your pack, and the plot must
be soil (empty or planted). A plot already fertilized this season
refuses a second bag. At the next season change the status clears and
the plot may be fed again.

Tile field, first cut:

```text
{"fertilizer": {"kind": "general" | "yield" | "growth", "season": "summer", "year": 1}}
```

Look text: “fertilized (general)” or “fed with yield-boost fertilizer,”
plus the usual crop hints. The soil itself can be described as
fertilized even when empty.

Art, first cut: **placeholders are enough.** A Classic SVG of little
teal and green granules on the dirt, and a simple Storybook overlay PNG
in the same spirit (scattered dots, transparent ground). A painted
Storybook pass can replace the placeholder later. Layering: ground →
granules → crop → weeds, so the pellets sit on the soil and still show
at the edges of a plant.

Shop: buy at the cabin, like seeds. The bag is a counted pack item
(`fertilizer_general`, `fertilizer_yield`, `fertilizer_growth`).


## Save migration

Always back up `state.json` first. Idempotent.

- **Till-hold:** empty tilled plots missing `untilled_in` get 5 (or a
  reset to 5 if they are already watered this morning).
- **Pack / chest:** pour the legacy `inventory` map into the chest;
  place one hoe and two watering cans in the chest if the world does
  not already have them; give every player an empty 4-slot pack. The
  live kabocha and strawberry seeds therefore start in the chest.
- **Growth / health:** for each living (not withered) plant,
  `growth = min(100, round(100 * days_grown / cycle_days))`, with a
  mature stage snapping to 100; `health = 100`. Establishing
  June-bearing plants that cannot fruit yet get `growth = 0` and
  `health = 100`.
- **Fertilizer:** plots with no fertilizer field are unfertilized.
  Do not invent a bag already in the chest.

Do not reset the farm. A fresh save is a later idea, once there is fuller
art, at least one plant per season, trees, and the like.


## UI, CLI, and MCP

- Legal actions, CLI help, MCP tool descriptions, and the web page all
  learn `take`, `drop`, `craft`, and (in step 5) `fertilize [kind]`.
- The pack is shown as four slots. The chest is listed in look text and
  in the cabin shop panel (take / drop / craft / buy / sell when you are
  at the cabin; if you are not, the shop says to walk there).
- Keyboard: keep T / W / P / H / Q / S. `S` opens the cabin panel. Eat
  stays available from the pack. A `fertilize` button or shop-bought bag
  plus a key can come in step 5 (`F` is free if we want it).
- Item icons may be simple placeholder SVGs until painted art exists.
- Storybook crop and soil art already shipped stays as it is.


## Open questions (small leftovers)

Most of the model is approved. Only nits remain:

1. May jam be made from a mix of June-bearing and everbearing berries
   (the default in this doc), or only from June-bearing?
2. Is root stew wanted in the first crafting patch, or only jam and soup?
3. Fertilizer prices (15 / 25 / 20) can move after a season of play.
4. Pack stack cap of 8 is a guess; tools stay unstacked in the pack
   either way.


## Suggested tests (by step)

- Till-hold: five dry evenings revert an empty bed; a watering or a wet
  dawn resets to 5; a planted bed does not revert; look text names the
  days left.
- Pack: till without a hoe fails; water without a can fails; harvest of
  2 berries needs room and then sits in the pack; a full pack refuses
  the harvest; buy / sell / craft / take / drop only at the cabin; packs
  survive a day turn; the live-style migration puts tools and the old
  inventory in the chest.
- Growth: two dry days do not wither; a long drought at low health
  does; a weedy watered plant grows more slowly and loses health; early
  harvest is refused below the threshold and allowed above it; a perfect
  plant can roll the top of its range; a harvest always yields at least
  1; hints contain no raw percentages; migration of a mature plant is
  growth 100, health 100.
- Fertilizer: second bag in the same season is refused; effects match
  the kind; the granule overlay (placeholder) layers under the crop;
  shop sells the three bags in spring and summer only.

No private player names in the repository.
