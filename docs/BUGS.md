# Bug triage

New bugs get logged here first instead of being fixed on the spot (Rick, 2026-11-27). We pick from this list on purpose. After weekly usage passes about 50%, only critical bugs get fixed and the rest wait for next week.

Severity: **critical** (blocks play or loses saves), **major** (a feature is broken but there's a workaround), **minor** (cosmetic or inconsistent).

## Open
| Found | Bug | Severity | Notes |
|---|---|---|---|
| 2026-11-27 | Several sprites show red fringes where they were cut out for transparency | minor | Visual only. Rick will fix the sprites himself later. |
| 2026-11-27 | Tile selection cursor stays on your old r/c coordinates after changing area (e.g. cabin to farm) | minor | Visual, slight gameplay effect. Expected: follow your current tile or clear on area change. |
| 2026-11-28 | In the mine, trying to mine with too little energy says "There's nothing to mine here in the mine." | minor | Misleading message. Expected: say you're too tired (not enough energy) to mine that. |
| 2026-11-28 | Forging at the town forge logs "forges the watering can to copper at the cabin" | minor | Wrong place name in the log line. Expected: "at the forge". |
| 2026-11-28 | Forecast strip: the snow day shows its caption inline ("snow (soil stays wet, but crops don't grow)"), unlike the other days | minor | Inconsistent. Expected: just "snow" like the rest, with the soil and growth note in a hover tooltip, if anywhere. |
| 2026-11-28 | Forecast strip: aurora night has no weather sprite of its own and falls back to the sun icon | minor | Missing art. Expected: an aurora SVG in the same style as Lumen's other weather SVGs (we keep using her SVGs for weather art). |
| 2026-11-28 | The "N energy tomorrow" preview (end-turn tooltip and status line) leaves out the homesickness penalty that will apply, e.g. "100 energy tomorrow" in the sleeping bag on a night away | minor | Misleading number. Expected: include homesickness (and note when sharing a tile or floor cancels it), so the preview matches what you actually wake with. |
| 2026-11-28 | The forge can upgrade any tool without the player carrying it (it can sit in the cabin chest) | major | Rule bypass: skips the trip of bringing the tool to town. Expected: only tools in the backpack can be forged. We play honestly until it is fixed. |
| 2026-11-28 | After upgrading the pickaxe to copper, the side panel still calls it "pickaxe" | minor | The inventory already says "copper pickaxe", but the side panel builds item names through a different path. Look into it later: make every view use one naming path. |
| 2026-11-28 | The aurora weather tooltip reads "an aurora night (clear, rare)" | minor | Wording. Rarity does not need to be mentioned. Expected: "an aurora night (clear)" or just "an aurora night". |
| 2026-11-28 | The honour store sells tomato seeds in autumn, but a tomato planted on autumn day 1 was killed by frost on the first snow (Day 33) | major | Shop and frost rules disagree. Rick (2026-11-28): frost does kill tomatoes in real life, so rethink them rather than make them frost-proof (see Roadmap, Tomatoes as a gamble). Fix: stop selling tomato seeds in autumn. |
| 2026-11-28 | ~~The Day 32 forecast said Day 33 would be rain, but it snowed~~ Not a bug | closed | Working as designed (Rick, 2026-11-28): tomorrow's forecast is 90% accurate and day 7 is 50% (`rules.json` forecast near 0.9, far 0.5), so misses and changes are expected. |
| 2026-11-28 | Storybook pack: on snow days, untilled soil shows only a faint dusting of snow, while tilled soil is properly snow-covered | minor | Visual mismatch (Day 35 screenshot: r1c1, r2c2, r3c1, r3c3 look nearly bare next to r1c2, r2c1, r3c2). Expected: the untilled-soil snow sprite carries about as much snow as tilled soil. |
| 2026-11-28 | Harvest and chest log lines say "2 spinachs" | minor | Plural wording. Expected: "spinach" stays uncountable ("2 spinach" or "2 bunches of spinach"). Worth checking other irregular plurals in the same helper. |
| 2026-11-28 | Homesickness applies -5 on the very first night away, so a sleeping bag night wakes you at 95 | major | Rick: the first night away should be free and the sleeping bag should give a clean 100. Expected: stacks start building from the second consecutive night away (first night 0, then -5, -10...). Code: `upcoming_homesickness_penalty` in engine.py adds a step right away. Update the describe.py and MCP help text with it. |
| 2026-11-28 | Can't carry a partner to bed if they have a sleeping bag | minor | Day 46: Rick was at 4 energy two tiles from the cabin, homesick -40, and asked for a save. `carry Ryker to bed` said he wasn't waiting to be carried, because `player_requested_carry` returns False for anyone with a bag. Expected: a partner who ended their turn away can be carried home even with a bag (the cabin clears homesickness, the bag does not). Workaround used: sleep on the same tile. |
| 2026-11-28 | Mid-day faint log says the player wakes with "full HP", but HP is restored only up to 50 | minor | `faint_from_hp` in hills.py sets HP to `away_hp_restore_cap` (50) and then says "full HP" in the log line and the docstring. describe.py, the README, and the later patch notes are already correct. Expected: the faint message should say HP is restored up to 50. |
| 2026-11-28 | Harvesting a perennial, a regrowing crop, or a frost-bitten plant grants no farming XP | minor | `rules.json` lists 4 XP for a harvest, but `harvest()` only calls `grant_xp` on the one-and-done annual path. Planting still grants 1 XP. Expected: any successful harvest grants farming XP. |

## Fixed
| Found | Bug | Fixed in |
|---|---|---|
| 2026-11-27 | After `build chest` at cabin r1c2, ground drops on that tile become unreachable | 7c51fd7 |
| 2026-11-27 | Shop shows "everbearing strawberry seed"; everbearing ones are starters | 7c51fd7 |
| 2026-11-27 | E on the cabin door tile didn't leave the cabin | 3f9354c |
| 2026-11-27 | Hands slot rejected every tool except the pickaxe | fb5eb5d |
| 2026-11-27 | Autopass ended the turn immediately; used count never reset; no countdown | 41f9654 |
| 2026-11-27 | Cabin labelled "cabin" instead of r1 c3 | 8279f91 |

## Won't fix
| Found | Report | Reason |
|---|---|---|
| 2026-11-27 | Sleeping-close bonus (+5) seemed to go missing on some low-energy nights (Days 14, 19) | Working as designed (Rick, 2026-11-28): only one player needs 10 energy to give the cuddle bonus. On Day 23 Rick ended on 5 and Lumen on 35, and both woke at 105. We'll keep an eye on it. |
