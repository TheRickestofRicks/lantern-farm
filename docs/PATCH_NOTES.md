# Patch notes

## 2026-11-26

Rick and Lumen’s first official-project day on Lantern Farm. A full day of engine, art, and cabin work landed on `main`.

### Cabin

- The cabin is now enterable. From the farm cabin tile, E steps into a 3×3 interior (bed, chest, fireplace, kitchen, door). Walking inside costs no energy; being anywhere inside still counts as sleeping in the cabin. Leave through the door, back onto the farm cabin tile. (`b7361e8`, `33592d5`)
- Storybook art for the floor and furniture, including lit and unlit fireplace and stove. Interior tiles use the same r1 c1 labels as the farm. The cabin chest panel is shown only while you are inside. (`4844f73`, `dd7a74f`)
- The bed quilt was repainted: a centered glowing lantern over a green-left / blue-right aurora, with the glitchy pale patch near the pillows removed. The interior door overlay was inset so it sits fully on the door tile. (`a53abfa`)
- Cabin comfort: a fire and a full belly help you wake. Fuel the fireplace from the fireplace tile with wood from the backpack. The stove is also loaded from the pack (one load cooks for the day and resets at dawn). E on the kitchen opens the recipe book, and asks you to load wood first if the stove is unfueled. The recipe book is visible only at the chest or the kitchen. (`6d741c7`, `86fa5be`, `49aa396`)
- Together rest: when both players sleep in the cabin, each gets +5 energy the next morning. (`dfccb95`)
- After cabin sleep, you wake at the interior bed. Players who passed out still wake where they fell. (`49aa396`)

### Turns and walking

- Pass turn is a same-day hand-off with an optional note; it does not end your day. If you pass while away from the cabin, you are automatically marked as waiting, and the other player can Walk you home (this can reopen their day if they already ended). There is no separate “pass turn home” action. The note field clears after a pass, the same as after end turn. Both players still need to end turn to advance the day. (`9a1675c`, `49aa396`)
- Walk home can bring a partner back to the cabin. (`9a1675c`)
- End turn is no longer bound to plain E. Use Shift+E, then Enter (a note in the box is sent too). (`b7361e8`)

### Energy and food

- Food never raises energy above the base cap of 100. If you are already at 100 or more, you cannot eat that snack; sell it or save it. Wake bonuses (fire, food, tea, together rest) may still start a day above 100. Eat messages and the HUD show energy against 100. (`33207d5`, `df33828`)
- Herbal tea is in the shop: one cup a day, +10 energy at the next cabin wake. Shop seed cards show growing seasons, remaining days, and the remaining grow window. Forged tool tiers are visible. (`1a0b4cc`, `e082081`)
- Bread splits into halves; eat buttons cover half loaves and foraged snacks. Sugar is in for jam. Foraged goods are unsellable and have their own recipes. (`55e7b38`, `8d2c8f0`, `5349c22`, `74d869f`)

### Hills and the mine

- The hills opened, with growing trees, forage, and Storybook art. Stumps can be unearthed or left to send up a sapling or become a mushroom log for oyster mushrooms. Wood stacks in the pack. (`bb058de`, `2e2f97e`, `55e7b38`)
- The mine opened, with a forge at the cabin, mine actions in the web UI, Storybook mine art, and stone from plain rock. The pickaxe appears in a shop Tools section once the mine is found. (`f22f892`, `4b6c38d`, `74d869f`, `e709e37`)
- Chopping a grown tree always reports a success or a clear refusal (still growing, no axe, pack full). A dawn “grown tall” note matches a tree you can chop. `python3 cli.py chop` works without wrapping the verb in `do`. (`this change`)

### Art and UI polish

- Root-crop sprites sit above the tile label. Zucchini fruits each have a blossom at the tip. Missing item icons were added; a red fringe on the sprouting beet was cleaned up. Establishing plants are labeled. (`9499490`, `db08161`, `1b5b352`, `55e7b38`)
- The cabin keeps its weather tile when the fire is lit, with only smoke added. Bonus energy in the HUD is current over the base max. The web Elsewhere block is hidden; the pass-out area is named. Chest order is remembered, and shop/chest grouping was fixed. A legal-command box was added to the page. (`eb081f6`, `df33828`, `8360143`, `dd7a74f`, `021241e`, `4b6c38d`)
