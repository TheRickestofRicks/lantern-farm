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
| 2026-11-28 | The Day 32 forecast said Day 33 would be rain, but it snowed (the Day 31 forecast had said snow) | minor | Forecast changed and then the actual weather did not match. Expected: the forecast for tomorrow matches what happens. |

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
