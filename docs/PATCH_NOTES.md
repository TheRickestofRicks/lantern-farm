# Patch notes

## 2026-11-26

Rick and Lumen’s first official-project day on Lantern Farm. A full day of engine, art, and cabin work landed on `main`.

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

### Art and UI polish

- Root-crop sprites sit above the tile label. Zucchini fruits each have a blossom at the tip. Missing item icons were added; a red fringe on the sprouting beet was cleaned up. Establishing plants are labeled. (`9499490`, `db08161`, `1b5b352`, `55e7b38`)
- The cabin keeps its weather tile when the fire is lit, with only smoke added. Bonus energy in the HUD is current over the base max. The web Elsewhere block is hidden; the pass-out area is named. Chest order is remembered, and shop/chest grouping was fixed. A legal-command box was added to the page. (`eb081f6`, `df33828`, `8360143`, `dd7a74f`, `021241e`, `4b6c38d`)
